/**
 * TRION Protocol — Relayer KMS Abstraction Layer
 * ===============================================
 *
 * Whitepaper mandate (Finding #10 in audit):
 *   "HSM (Thales Luna 7 / YubiHSM 2) — NON-NEGOTIABLE"
 *
 * This module abstracts the wallet-creation path so the relayer can use:
 *   1. Plaintext env var (RELAYER_PRIVATE_KEY) — for development only
 *   2. AWS KMS — production signing via AWS Key Management Service
 *   3. Google Cloud KMS — production signing via GCP KMS
 *   4. YubiHSM 2 — hardware-backed signing via yubihsm-shell
 *   5. Thales Luna 7 — enterprise HSM via PKCS#11
 *
 * The relayer detects which mode to use via the KMS_PROVIDER env var:
 *   KMS_PROVIDER=env      (default, dev) — use RELAYER_PRIVATE_KEY
 *   KMS_PROVIDER=aws      (production)   — use AWS_KMS_KEY_ID
 *   KMS_PROVIDER=gcp      (production)   — use GCP_KMS_KEY_NAME
 *   KMS_PROVIDER=yubihsm  (production)   — use YUBIHSM_KEY_ID + YUBIHSM_AUTH_KEY
 *   KMS_PROVIDER=pkcs11   (production)   — use PKCS11_MODULE_PATH + PKCS11_KEY_ID
 *
 * Each provider exposes a unified interface:
 *   - `signMessage(payload)` → 65-byte EIP-191 (personal_sign) signature.
 *     The relayer uses this to construct the `bytes[] calldata signatures`
 *     array required by TRIONExecutionGate and TRIONOracleV3.
 *   - `signDigest(digest)`   → 65-byte r||s||v signature over a raw 32-byte
 *     digest. Used by the KmsEthersSigner adapter (below) to sign actual
 *     EIP-155/EIP-1559 transactions — the private key never leaves the
 *     KMS/HSM boundary, only signature bytes do.
 *
 * Ethereum addresses are derived with Keccak-256 (ethers `keccak256`) —
 * NOT NIST SHA3-256. The previous `createHash("sha3-256")` derivation
 * (audit finding S7) produced wrong addresses for every non-env provider,
 * so the signature v-recovery verification could never pass.
 *
 * SECURITY NOTE: The `env` provider is the ONLY one that exposes the raw
 * private key in memory. All other providers keep the key material inside
 * the HSM/KMS boundary and return only the signature bytes.
 *
 * Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
 * License: CC0
 */

import { ethers, keccak256, hexlify } from "ethers";

// secp256k1 group order — used for EIP-2 canonical low-s normalization
const SECP256K1_N = 0xfffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364141n;

// ── Provider enum ─────────────────────────────────────────────────────────────

const KMS_PROVIDER = (process.env.KMS_PROVIDER || "env").toLowerCase();

const PROVIDERS = {
  ENV:     "env",      // RELAYER_PRIVATE_KEY (dev only)
  AWS:     "aws",      // AWS KMS
  GCP:     "gcp",      // Google Cloud KMS
  YUBIHSM: "yubihsm",  // YubiHSM 2
  PKCS11:  "pkcs11",   // Thales Luna 7 / generic PKCS#11
};

// ── Provider implementations ──────────────────────────────────────────────────

/**
 * Create a wallet/signer based on the configured KMS_PROVIDER.
 * Returns an object with `address`, `signMessage(payload: bytes) → bytes`
 * (EIP-191) and `signDigest(digest: bytes32) → bytes` (raw digest — for
 * transaction signing via KmsEthersSigner).
 *
 * @returns {Promise<{address: string, signMessage: (payload: Uint8Array) => Promise<Uint8Array>, signDigest: (digest: Uint8Array) => Promise<Uint8Array>, provider: string}>}
 */
export async function createSigner() {
  switch (KMS_PROVIDER) {
    case PROVIDERS.ENV:
      return createEnvSigner();
    case PROVIDERS.AWS:
      return createAwsKmsSigner();
    case PROVIDERS.GCP:
      return createGcpKmsSigner();
    case PROVIDERS.YUBIHSM:
      return createYubiHsmSigner();
    case PROVIDERS.PKCS11:
      return createPkcs11Signer();
    default:
      throw new Error(
        `Unknown KMS_PROVIDER "${KMS_PROVIDER}". ` +
        `Valid values: ${Object.values(PROVIDERS).join(", ")}`
      );
  }
}

// ── ENV provider (development) ────────────────────────────────────────────────

function createEnvSigner() {
  const privateKey = process.env.RELAYER_PRIVATE_KEY;
  if (!privateKey) {
    throw new Error(
      "RELAYER_PRIVATE_KEY not set. Either set it for dev mode or " +
      "configure KMS_PROVIDER=aws|gcp|yubihsm|pkcs11 for production."
    );
  }
  const pk = privateKey.startsWith("0x") ? privateKey : "0x" + privateKey;
  const wallet = new ethers.Wallet(pk);
  console.warn(
    "[KMS] WARNING: Using env-var private key (development mode). " +
    "For production, set KMS_PROVIDER=aws|gcp|yubihsm|pkcs11."
  );

  /** Sign a raw 32-byte digest (NO EIP-191 prefix) → 65-byte r||s||v. */
  const signDigest = async (digest) => {
    assertDigest32(digest);
    const sig = wallet.signingKey.sign(ethers.getBytes(digest));
    return ethers.getBytes(sig.serialized);
  };

  return {
    address: wallet.address,
    // EIP-191: prefix with "\x19Ethereum Signed Message:\n<len>" + payload
    signMessage: async (payload) =>
      signDigest(ethers.getBytes(ethers.hashMessage(payload))),
    signDigest,
    provider: PROVIDERS.ENV,
  };
}

// ── AWS KMS provider ──────────────────────────────────────────────────────────

async function createAwsKmsSigner() {
  const keyId = process.env.AWS_KMS_KEY_ID;
  const region = process.env.AWS_REGION || "us-east-1";
  if (!keyId) {
    throw new Error("AWS_KMS_KEY_ID not set (required when KMS_PROVIDER=aws)");
  }
  // Dynamic import — only required when this provider is selected
  let kmsClient, getPublicKey, signCommand;
  try {
    const mod = await import("@aws-sdk/client-kms");
    kmsClient = new mod.KMSClient({ region });
    getPublicKey = mod.GetPublicKeyCommand;
    signCommand = mod.SignCommand;
  } catch (e) {
    throw new Error(
      "AWS KMS provider requires @aws-sdk/client-kms. Install: " +
      "npm install @aws-sdk/client-kms"
    );
  }

  // Fetch the public key to derive the Ethereum address
  const pubResp = await kmsClient.send(new getPublicKey({ KeyId: keyId }));
  const pubKey = pubResp.PublicKey;
  // Derive Ethereum address: keccak256(uncompressed_pubkey[1:])[12:32]
  // (Keccak-256 via ethers — NOT NIST SHA3-256; audit finding S7 fix)
  const address = ethAddressFromPublicKey(pubKey);

  console.log(`[KMS] AWS KMS signer ready: key=${keyId.slice(0, 16)}… addr=${address}`);

  /** Sign a raw 32-byte digest inside KMS → canonical 65-byte r||s||v. */
  const signDigest = async (digest) => {
    assertDigest32(digest);
    const digestBytes = ethers.getBytes(digest);
    const resp = await kmsClient.send(new signCommand({
      KeyId: keyId,
      // MessageType DIGEST: AWS signs this exact 32-byte digest as-is.
      // (The old MessageType RAW made AWS pre-hash with SHA-256 — a digest
      // Ethereum's keccak-based EIP-191/EIP-155 verification can never match.)
      Message: digestBytes,
      MessageType: "DIGEST",
      SigningAlgorithm: "ECDSA_SHA_256",
    }));
    // AWS KMS returns a DER-encoded signature; convert to r||s||v
    return derSignatureToEth(Buffer.from(resp.Signature), digestBytes, address);
  };

  return {
    address,
    // EIP-191 (personal_sign) quorum signature via the KMS
    signMessage: async (payload) =>
      signDigest(ethers.getBytes(ethers.hashMessage(payload))),
    signDigest,
    provider: PROVIDERS.AWS,
  };
}

// ── GCP KMS provider ──────────────────────────────────────────────────────────

async function createGcpKmsSigner() {
  const keyName = process.env.GCP_KMS_KEY_NAME;
  if (!keyName) {
    throw new Error("GCP_KMS_KEY_NAME not set (required when KMS_PROVIDER=gcp)");
  }
  let kms;
  try {
    const mod = await import("@google-cloud/kms");
    kms = new mod.KeyManagementServiceClient();
  } catch (e) {
    throw new Error(
      "GCP KMS provider requires @google-cloud/kms. Install: " +
      "npm install @google-cloud/kms"
    );
  }

  const [pubResp] = await kms.getPublicKey({ name: keyName });
  // pubResp.pem is a PEM-encoded EC public key
  const address = deriveEthAddressFromPem(pubResp.pem);

  console.log(`[KMS] GCP KMS signer ready: key=${keyName.slice(-32)} addr=${address}`);

  /** Sign a raw 32-byte digest inside KMS → canonical 65-byte r||s||v. */
  const signDigest = async (digest) => {
    assertDigest32(digest);
    const digestBytes = ethers.getBytes(digest);
    const [signResp] = await kms.cryptoKeyVersionsAsymmetricSign({
      name: keyName,
      // GCP signs the provided 32-byte digest as-is (it is NOT re-hashed),
      // so the keccak-based EIP-191/EIP-155 digest can be fed straight in.
      digest: { sha256: digestBytes },
    });
    // GCP returns a DER-encoded signature; convert to r||s||v
    return derSignatureToEth(Buffer.from(signResp.signature), digestBytes, address);
  };

  return {
    address,
    signMessage: async (payload) =>
      signDigest(ethers.getBytes(ethers.hashMessage(payload))),
    signDigest,
    provider: PROVIDERS.GCP,
  };
}

// ── YubiHSM 2 provider ────────────────────────────────────────────────────────

async function createYubiHsmSigner() {
  const keyId = parseInt(process.env.YUBIHSM_KEY_ID || "0", 10);
  const authKey = parseInt(process.env.YUBIHSM_AUTH_KEY || "1", 10);
  const password = process.env.YUBIHSM_PASSWORD;
  if (!password) {
    throw new Error(
      "YUBIHSM_PASSWORD not set (required when KMS_PROVIDER=yubihsm)"
    );
  }
  // YubiHSM connector runs on localhost:12345 by default
  const connectorUrl = process.env.YUBIHSM_CONNECTOR_URL || "http://localhost:12345";

  // Fetch the public key from the YubiHSM via the HTTP connector
  const pubResp = await fetch(`${connectorUrl}/connector/api/v1/keys/${keyId}/public`, {
    headers: { "X-Auth-Key": authKey.toString(), "X-Auth-Password": password },
  });
  if (!pubResp.ok) {
    throw new Error(`YubiHSM public key fetch failed: ${pubResp.status} ${pubResp.statusText}`);
  }
  const pubKeyInfo = await pubResp.json();
  // Keccak-256 address derivation (audit finding S7 fix)
  const address = ethAddressFromPublicKey(pubKeyInfo.public_key);

  console.log(`[KMS] YubiHSM signer ready: key_id=${keyId} addr=${address}`);

  /** Sign a raw 32-byte digest on the HSM → canonical 65-byte r||s||v. */
  const signDigest = async (digest) => {
    assertDigest32(digest);
    const digestBytes = ethers.getBytes(digest);
    // Sign via the connector's sign-ecdsa endpoint (signs the given digest)
    const signResp = await fetch(`${connectorUrl}/connector/api/v1/keys/${keyId}/sign-ecdsa`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Auth-Key": authKey.toString(),
        "X-Auth-Password": password,
      },
      body: JSON.stringify({
        digest: hexlify(digestBytes).slice(2),
      }),
    });
    if (!signResp.ok) {
      throw new Error(`YubiHSM sign failed: ${signResp.status} ${signResp.statusText}`);
    }
    const sigInfo = await signResp.json();
    // Response signature is DER-encoded; convert to r||s||v
    return derSignatureToEth(Buffer.from(sigInfo.signature, "hex"), digestBytes, address);
  };

  return {
    address,
    signMessage: async (payload) =>
      signDigest(ethers.getBytes(ethers.hashMessage(payload))),
    signDigest,
    provider: PROVIDERS.YUBIHSM,
  };
}

// ── PKCS#11 provider (Thales Luna 7 and generic HSMs) ─────────────────────────

async function createPkcs11Signer() {
  const modulePath = process.env.PKCS11_MODULE_PATH;
  const keyId = process.env.PKCS11_KEY_ID;
  const pin = process.env.PKCS11_PIN;
  const slot = parseInt(process.env.PKCS11_SLOT || "0", 10);
  if (!modulePath || !keyId || !pin) {
    throw new Error(
      "PKCS11_MODULE_PATH, PKCS11_KEY_ID, PKCS11_PIN all required when KMS_PROVIDER=pkcs11"
    );
  }
  let pkcs11;
  try {
    pkcs11 = (await import("graphene-pk11")).default;
  } catch (e) {
    throw new Error(
      "PKCS#11 provider requires graphene-pk11. Install: " +
      "npm install graphene-pk11"
    );
  }

  const mod = new pkcs11.PKCS11();
  mod.load(modulePath);
  mod.open(slot, 1, pin);  // 1 = RW session

  // Get the public key to derive Ethereum address
  const session = mod.session;
  const pubKeyObj = session.find({ id: Buffer.from(keyId, "hex"), class: 2 /* PUBLIC_KEY */ })[0];
  if (!pubKeyObj) {
    throw new Error(`PKCS#11 key with id ${keyId} not found`);
  }
  // Extract the EC point — for secp256k1, this is an uncompressed point
  const ecPoint = pubKeyObj.point;
  // Keccak-256 address derivation (audit finding S7 fix); also unwraps the
  // ASN.1 OCTET STRING some PKCS#11 modules wrap the point in
  const address = ethAddressFromPublicKey(ecPoint);

  console.log(`[KMS] PKCS#11 signer ready: module=${modulePath} key=${keyId} addr=${address}`);

  /** Sign a raw 32-byte digest on the HSM → canonical 65-byte r||s||v. */
  const signDigest = async (digest) => {
    assertDigest32(digest);
    const digestBytes = ethers.getBytes(digest);
    const privKeyObj = session.find({ id: Buffer.from(keyId, "hex"), class: 3 /* PRIVATE_KEY */ })[0];
    if (!privKeyObj) {
      throw new Error(`PKCS#11 private key with id ${keyId} not found`);
    }
    // CKM_ECDSA signs the precomputed digest directly (no re-hashing) —
    // required for keccak-based EIP-191/EIP-155 verification
    const derSig = privKeyObj.sign("ECDSA", Buffer.from(digestBytes));
    return derSignatureToEth(Buffer.from(derSig), digestBytes, address);
  };

  return {
    address,
    signMessage: async (payload) =>
      signDigest(ethers.getBytes(ethers.hashMessage(payload))),
    signDigest,
    provider: PROVIDERS.PKCS11,
  };
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Buffer → BigInt (big-endian; empty buffer → 0n). */
function bufToBigInt(buf) {
  return BigInt("0x" + (buf.toString("hex") || "0"));
}

/**
 * Assert that `digest` is exactly 32 bytes — the only thing an ECDSA
 * secp256k1 signer may sign.
 * @param {Uint8Array|string} digest
 */
function assertDigest32(digest) {
  const bytes = ethers.getBytes(digest);
  if (bytes.length !== 32) {
    throw new Error(`signDigest: digest must be 32 bytes, got ${bytes.length}`);
  }
}

/**
 * Derive an Ethereum address from an secp256k1 public key using Keccak-256.
 *
 * Ethereum addresses are the last 20 bytes of keccak256(X || Y) — Keccak-256
 * (pre-NIST padding), NOT Node's createHash("sha3-256") (NIST SHA3-256,
 * different padding → different digest). The previous SHA3-based derivation
 * produced wrong addresses for every non-env KMS provider (audit finding S7),
 * so the providers' signature v-recovery verification could never pass.
 *
 * Accepts:
 *   - a 65-byte uncompressed point (04 || X || Y) as Buffer/Uint8Array
 *   - the same as a hex string (with or without 0x prefix)
 *   - a DER SubjectPublicKeyInfo blob (AWS KMS GetPublicKey / GCP KMS PEM
 *     body) — the uncompressed point is the trailing 65 bytes
 *
 * @param {Buffer|Uint8Array|string} pubKey
 * @returns {string} 0x-prefixed 40-hex-char address
 */
export function ethAddressFromPublicKey(pubKey) {
  let point = typeof pubKey === "string"
    ? Buffer.from(pubKey.replace(/^0x/i, ""), "hex")
    : Buffer.from(pubKey);
  if (point.length > 65) {
    // DER SubjectPublicKeyInfo (or ASN.1 OCTET STRING) wrapper — the
    // uncompressed EC point is the trailing 65 bytes
    point = point.subarray(point.length - 65);
  }
  if (point.length !== 65 || point[0] !== 0x04) {
    throw new Error(
      `Expected 65-byte uncompressed secp256k1 public key (04 || X || Y), got ${point.length} byte(s)`
    );
  }
  const pubkeyNoPrefixHex = hexlify(point.subarray(1, 65)); // 04-stripped point
  // getAddress() applies the EIP-55 checksum (and validates the length)
  return ethers.getAddress("0x" + keccak256(pubkeyNoPrefixHex).slice(-40));
}

/**
 * Convert a DER-encoded secp256k1 ECDSA signature (as returned by AWS KMS,
 * GCP KMS, YubiHSM 2 and PKCS#11 HSMs) over `digest` into the canonical
 * 65-byte Ethereum form r||s||v with v ∈ {27, 28}.
 *
 * `s` is normalized to its low form (EIP-2) and `v` is recovered by
 * verifying the signature against the derived `address`. This is the check
 * that proves the KMS key really owns the address: if the key and the
 * address disagree the recovery can never succeed, so we fail closed and
 * throw instead of returning an unverifiable signature.
 *
 * @param {Buffer} der DER-encoded ECDSA signature
 * @param {Uint8Array} digest 32-byte digest that was signed
 * @param {string} address expected Ethereum address
 * @returns {Uint8Array} 65-byte r||s||v signature
 */
function derSignatureToEth(der, digest, address) {
  const { r, s } = parseDerSignature(der);
  const rBig = bufToBigInt(r);
  let sBig = bufToBigInt(s);
  if (sBig > SECP256K1_N / 2n) {
    sBig = SECP256K1_N - sBig; // EIP-2: canonical low-s
  }
  const rHex = rBig.toString(16).padStart(64, "0");
  const sHex = sBig.toString(16).padStart(64, "0");
  for (const v of [27, 28]) {
    // serialized = 65-byte r||s||v as a 0x-hex string (recoverAddress takes
    // a hex string / Signature, not a raw Uint8Array)
    const sigHex = ethers.Signature.from({ r: "0x" + rHex, s: "0x" + sHex, v }).serialized;
    if (ethers.recoverAddress(digest, sigHex).toLowerCase() === address.toLowerCase()) {
      return ethers.getBytes(sigHex);
    }
  }
  throw new Error(
    "KMS signature does not recover to the derived address — the KMS key and " +
    "the derived Ethereum address do not match (wrong key or wrong digest)"
  );
}

/**
 * Parse a DER-encoded ECDSA signature into its r and s components.
 * DER format: 0x30 <len> 0x02 <rlen> <r> 0x02 <slen> <s>
 * @param {Buffer} der
 * @returns {{r: Buffer, s: Buffer}}
 */
function parseDerSignature(der) {
  if (der[0] !== 0x30) throw new Error("Invalid DER signature: missing SEQ tag");
  const rLen = der[3];
  const r = der.slice(4, 4 + rLen);
  const sLen = der[4 + rLen + 1];
  const s = der.slice(4 + rLen + 2, 4 + rLen + 2 + sLen);
  return { r, s };
}

/**
 * Derive an Ethereum address from a PEM-encoded EC public key.
 * @param {string} pem
 * @returns {string}
 */
function deriveEthAddressFromPem(pem) {
  // Strip PEM headers and decode base64
  const b64 = pem
    .replace("-----BEGIN PUBLIC KEY-----", "")
    .replace("-----END PUBLIC KEY-----", "")
    .replace(/\s/g, "");
  const raw = Buffer.from(b64, "base64");
  // raw is a DER SubjectPublicKeyInfo; ethAddressFromPublicKey() takes the
  // trailing 65 bytes (the uncompressed EC point) and applies Keccak-256
  // (audit finding S7 fix — was createHash("sha3-256"))
  return ethAddressFromPublicKey(raw);
}

// ── ethers-compatible signer adapter ──────────────────────────────────────────

/**
 * KmsEthersSigner — wraps a KMS provider signer ({ address, signMessage,
 * signDigest }) in an ethers v6 AbstractSigner so it can be used anywhere
 * ethers expects a Signer:
 *
 *   - signMessage()     → EIP-191 quorum signatures produced inside the KMS
 *   - sendTransaction() → EIP-155/EIP-1559 transaction signing: the digest
 *                         keccak256(rlp(unsigned tx)) is signed inside the
 *                         KMS/HSM via signDigest() and the signed tx is
 *                         broadcast through the connected provider
 *
 * The private key never leaves the KMS/HSM boundary — only signature bytes.
 */
export class KmsEthersSigner extends ethers.AbstractSigner {
  #kms;

  /**
   * @param {{address: string, signMessage: Function, signDigest: Function}} kmsSigner
   * @param {null | import("ethers").Provider} provider
   */
  constructor(kmsSigner, provider) {
    super(provider);
    this.#kms = kmsSigner;
  }

  async getAddress() { return this.#kms.address; }

  connect(provider) { return new KmsEthersSigner(this.#kms, provider); }

  async signMessage(message) {
    const payload = typeof message === "string"
      ? ethers.toUtf8Bytes(message)
      : ethers.getBytes(message);
    return hexlify(await this.#kms.signMessage(payload));
  }

  async signTransaction(tx) {
    // AbstractSigner.sendTransaction() passes an already-populated
    // Transaction; direct callers may pass a TransactionLike.
    let unsignedTx = tx;
    if (!(unsignedTx instanceof ethers.Transaction)) {
      const populated = this.provider
        ? await this.populateTransaction(unsignedTx)
        : { ...unsignedTx };
      // `from` is this signer's own address — not part of the signed payload
      delete populated.from;
      unsignedTx = ethers.Transaction.from(populated);
    }
    // The digest a signer must authorize: keccak256(rlp(unsigned tx)) —
    // transactions are NOT EIP-191 prefixed
    const digest = ethers.getBytes(unsignedTx.unsignedHash);
    const sigBytes = await this.#kms.signDigest(digest);
    // v ∈ {27,28} → yParity; ethers serializes EIP-155 v = chainId*2 + 35 + yParity
    unsignedTx.signature = ethers.Signature.from(hexlify(sigBytes));
    return unsignedTx.serialized;
  }

  // sendTransaction() is inherited from ethers.AbstractSigner:
  //   populateTransaction → signTransaction → provider.broadcastTransaction
}

// ── Self-test ─────────────────────────────────────────────────────────────────

if (import.meta.url === `file://${process.argv[1]}`) {
  console.log("=== KMS Provider Self-test ===");
  console.log(`Configured provider: ${KMS_PROVIDER}`);
  console.log(`Available providers: ${Object.values(PROVIDERS).join(", ")}`);
  console.log("");
  console.log("Environment variables per provider:");
  console.log("  env     : RELAYER_PRIVATE_KEY");
  console.log("  aws     : AWS_KMS_KEY_ID, AWS_REGION");
  console.log("  gcp     : GCP_KMS_KEY_NAME");
  console.log("  yubihsm : YUBIHSM_KEY_ID, YUBIHSM_AUTH_KEY, YUBIHSM_PASSWORD, YUBIHSM_CONNECTOR_URL");
  console.log("  pkcs11  : PKCS11_MODULE_PATH, PKCS11_KEY_ID, PKCS11_PIN, PKCS11_SLOT");
  console.log("");

  createSigner()
    .then((signer) => {
      console.log(`✓ Signer ready: provider=${signer.provider} address=${signer.address}`);
      const testDigest = ethers.getBytes(ethers.keccak256(ethers.toUtf8Bytes("test digest")));
      return signer.signDigest(testDigest).then((sig) => {
        console.log(`✓ Sign digest : ${signer.address} returned ${sig.length}-byte r||s||v signature`);
        const testPayload = ethers.toUtf8Bytes("test message");
        return signer.signMessage(testPayload).then((sig2) => {
          console.log(`✓ Sign message: ${signer.address} returned ${sig2.length}-byte EIP-191 signature`);
        });
      });
    })
    .catch((e) => {
      console.error(`✗ Signer creation failed: ${e.message}`);
      process.exit(1);
    });
}

export { PROVIDERS, KMS_PROVIDER };
