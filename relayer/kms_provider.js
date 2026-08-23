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
 * Each provider exposes a unified `signMessage(payload)` interface returning
 * a 65-byte EIP-191 signature. The relayer uses this to construct the
 * `bytes[] calldata signatures` array required by TRIONExecutionGate
 * and TRIONOracleV3.
 *
 * SECURITY NOTE: The `env` provider is the ONLY one that exposes the raw
 * private key in memory. All other providers keep the key material inside
 * the HSM/KMS boundary and return only the signature bytes.
 *
 * Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
 * License: CC0
 */

import { ethers } from "ethers";
import { createHash } from "node:crypto";

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
 * Returns an object with `address` and `signMessage(payload: bytes) → bytes`.
 *
 * @returns {Promise<{address: string, signMessage: (payload: Uint8Array) => Promise<Uint8Array>}>}
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
  return {
    address: wallet.address,
    signMessage: async (payload) => {
      // EIP-191: prefix with "\x19Ethereum Signed Message:\n32" + payload
      const digest = ethers.hashMessage(payload);
      const sig = await wallet.signMessage(payload);
      return ethers.getBytes(sig);
    },
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
  const address = "0x" +
    createHash("sha3-256").update(Buffer.from(pubKey).slice(1, 65)).digest("hex").slice(24);

  console.log(`[KMS] AWS KMS signer ready: key=${keyId.slice(0, 16)}… addr=${address}`);

  return {
    address,
    signMessage: async (payload) => {
      const resp = await kmsClient.send(new signCommand({
        KeyId: keyId,
        Message: payload,
        MessageType: "RAW",
        SigningAlgorithm: "ECDSA_SHA_256",
      }));
      // AWS KMS returns DER-encoded signature; convert to r||s||v
      const derSig = Buffer.from(resp.Signature);
      const { r, s } = parseDerSignature(derSig);
      // Recover v by attempting both 27 and 28
      const digest = ethers.hashMessage(payload);
      let v = 27;
      let sigBytes = ethers.getBytes(
        ethers.Signature.from({ r: "0x" + r.toString("hex"), s: "0x" + s.toString("hex"), v }).serialized
      );
      // Verify against the address; flip v if needed
      const recovered = ethers.recoverAddress(payload, sigBytes);
      if (recovered.toLowerCase() !== address.toLowerCase()) {
        v = 28;
        sigBytes = ethers.getBytes(
          ethers.Signature.from({ r: "0x" + r.toString("hex"), s: "0x" + s.toString("hex"), v }).serialized
        );
      }
      return sigBytes;
    },
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
  // pubResp.pem is a PEM-encoded EC P-256 public key
  const address = deriveEthAddressFromPem(pubResp.pem);

  console.log(`[KMS] GCP KMS signer ready: key=${keyName.slice(-32)} addr=${address}`);

  return {
    address,
    signMessage: async (payload) => {
      const digest = await kms.cryptoKeyVersionsAsymmetricSign({
        name: keyName,
        digest: { sha256: payload },
      });
      const derSig = Buffer.from(digest[0].signature);
      const { r, s } = parseDerSignature(derSig);
      // Recover v same as AWS
      let v = 27;
      let sigBytes = ethers.getBytes(
        ethers.Signature.from({ r: "0x" + r.toString("hex"), s: "0x" + s.toString("hex"), v }).serialized
      );
      const recovered = ethers.recoverAddress(payload, sigBytes);
      if (recovered.toLowerCase() !== address.toLowerCase()) {
        v = 28;
        sigBytes = ethers.getBytes(
          ethers.Signature.from({ r: "0x" + r.toString("hex"), s: "0x" + s.toString("hex"), v }).serialized
        );
      }
      return sigBytes;
    },
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
  const address = "0x" +
    createHash("sha3-256").update(Buffer.from(pubKeyInfo.public_key, "hex").slice(1, 65)).digest("hex").slice(24);

  console.log(`[KMS] YubiHSM signer ready: key_id=${keyId} addr=${address}`);

  return {
    address,
    signMessage: async (payload) => {
      // Sign via the connector's sign-ecdsa endpoint
      const signResp = await fetch(`${connectorUrl}/connector/api/v1/keys/${keyId}/sign-ecdsa`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Auth-Key": authKey.toString(),
          "X-Auth-Password": password,
        },
        body: JSON.stringify({
          digest: createHash("sha256").update(payload).digest("hex"),
        }),
      });
      if (!signResp.ok) {
        throw new Error(`YubiHSM sign failed: ${signResp.status} ${signResp.statusText}`);
      }
      const sigInfo = await signResp.json();
      const derSig = Buffer.from(sigInfo.signature, "hex");
      const { r, s } = parseDerSignature(derSig);
      // Recover v
      let v = 27;
      let sigBytes = ethers.getBytes(
        ethers.Signature.from({ r: "0x" + r.toString("hex"), s: "0x" + s.toString("hex"), v }).serialized
      );
      const recovered = ethers.recoverAddress(payload, sigBytes);
      if (recovered.toLowerCase() !== address.toLowerCase()) {
        v = 28;
        sigBytes = ethers.getBytes(
          ethers.Signature.from({ r: "0x" + r.toString("hex"), s: "0x" + s.toString("hex"), v }).serialized
        );
      }
      return sigBytes;
    },
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
  const address = "0x" +
    createHash("sha3-256").update(ecPoint.slice(1, 65)).digest("hex").slice(24);

  console.log(`[KMS] PKCS#11 signer ready: module=${modulePath} key=${keyId} addr=${address}`);

  return {
    address,
    signMessage: async (payload) => {
      const privKeyObj = session.find({ id: Buffer.from(keyId, "hex"), class: 3 /* PRIVATE_KEY */ })[0];
      if (!privKeyObj) {
        throw new Error(`PKCS#11 private key with id ${keyId} not found`);
      }
      // Sign the SHA-256 hash of the payload
      const hash = createHash("sha256").update(payload).digest();
      const derSig = privKeyObj.sign("SHA256", hash);  // returns DER
      const { r, s } = parseDerSignature(Buffer.from(derSig));
      // Recover v
      let v = 27;
      let sigBytes = ethers.getBytes(
        ethers.Signature.from({ r: "0x" + r.toString("hex"), s: "0x" + s.toString("hex"), v }).serialized
      );
      const recovered = ethers.recoverAddress(payload, sigBytes);
      if (recovered.toLowerCase() !== address.toLowerCase()) {
        v = 28;
        sigBytes = ethers.getBytes(
          ethers.Signature.from({ r: "0x" + r.toString("hex"), s: "0x" + s.toString("hex"), v }).serialized
        );
      }
      return sigBytes;
    },
    provider: PROVIDERS.PKCS11,
  };
}

// ── Helpers ───────────────────────────────────────────────────────────────────

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
  // The last 65 bytes are the uncompressed EC point (04 || X || Y)
  const point = raw.slice(-65);
  if (point[0] !== 0x04) {
    throw new Error("Expected uncompressed EC point (prefix 0x04)");
  }
  return "0x" + createHash("sha3-256").update(point.slice(1)).digest("hex").slice(24);
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
      const testPayload = ethers.toUtf8Bytes("test message");
      return signer.signMessage(testPayload).then((sig) => {
        console.log(`✓ Sign message: ${signer.address} returned ${sig.length}-byte signature`);
      });
    })
    .catch((e) => {
      console.error(`✗ Signer creation failed: ${e.message}`);
      process.exit(1);
    });
}

export { PROVIDERS, KMS_PROVIDER };
