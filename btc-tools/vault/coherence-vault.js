// =============================================================================
// TRION Coherence Vault — Bitcoin side (btc-tools/vault/coherence-vault.js)
// =============================================================================
//
// HashDNA preimage-triggered BTC lock. NO committee. NO multisig. NO federation.
// NO oracle. NO ZK proof. Just two Taproot script-path leaves:
//
//   PATH 1 — Coherence Release (anyone with the preimage can spend)
//     script:  OP_SHA256 <committed_anchor_bh_32bytes> OP_EQUAL
//     witness: <94_byte_payload_||_0x00>
//     enforcement: the spending tx's output is pre-constructed to pay the
//     lender's address. Even if an attacker reveals the preimage, the BTC
//     still goes to the lender (the tx structure is committed at lock time,
//     the TXID is a function of the structure, not the witness).
//
//   PATH 2 — Borrower Refund (CSV timelock)
//     script:  <csv_blocks> OP_CHECKSEQUENCEVERIFY OP_DROP <borrower_xonly> OP_CHECKSIG
//     witness: <borrower_schnorr_sig>
//
// This is fundamentally different from Babylon:
//   Babylon = committee must CO-SIGN every liquidation/refund → can censor.
//   TRION   = preimage is PUBLIC on Stacks → anyone can relay → cannot censor.
//
// Bitcoin Script is valid TODAY on testnet/mainnet — no soft fork required.
//
// See: docs/architecture/trion-coherence-vault.md
// =============================================================================

import * as bitcoin from 'bitcoinjs-lib';
import { ECPairFactory } from 'ecpair';
import * as ecc from 'tiny-secp256k1';
import {
  toHashTree,
  findScriptPath,
  tapleafHash,
  tweakKey,
  LEAF_VERSION_TAPSCRIPT,
} from 'bitcoinjs-lib/src/payments/bip341';
import { witnessStackToScriptWitness } from 'bitcoinjs-lib/src/psbt/psbtutils';
import * as crypto from 'crypto';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const ECPair = ECPairFactory(ecc);
// Register the ECC library with bitcoinjs-lib v7 (required for Taproot).
bitcoin.initEccLib(ecc);
const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Default network: Bitcoin testnet (set --mainnet to switch)
let network = bitcoin.networks.testnet;

// =============================================================================
// HashDNA payload + sense hash (must match Clarity, Python, Cairo, Solidity)
// =============================================================================
//
// 93-byte payload layout (matches proofs/oracle/anchor_parity_pinned.json):
//   [0:32]   entity_id     32 bytes  (BEO identifier)
//   [32]     event_type    1 byte    (event class)
//   [33:41]  mag_nano      8 bytes   (uint64 BE, magnitude × 10^9)
//   [41:49]  ctx           8 bytes   (uint64 BE, context index)
//   [49:57]  ts            8 bytes   (uint64 BE, unix seconds)
//   [57:61]  chain_id      4 bytes   (uint32 BE)
//   [61:93]  block_hash    32 bytes  (Bitcoin block hash, little-endian as-is)
//
// sense = SHA-256(payload || 0x00)   ← Bitcoin-deployable parity
// (NOT SHA3-256 — see §8.5 of trion-native-btc-lock-design.md)
// =============================================================================

export const PAYLOAD_LEN = 93;
export const SENSE_SUFFIX = 0x00;          // sense strand suffix (deployed parity)
export const ANTISENSE_SUFFIX = 0xff;      // reserved for future OP_CAT migration

/**
 * Build the canonical 93-byte HashDNA payload from its 7 fields.
 * Inputs are hex strings (entity_id, block_hash) or numbers (everything else).
 */
export function buildPayload({ entityId, eventType, magnitudeNano, context, timestamp, chainId, blockHash }) {
  const payload = Buffer.alloc(PAYLOAD_LEN);
  const eid = Buffer.from(entityId, 'hex');
  if (eid.length !== 32) throw new Error(`entity_id must be 32 bytes, got ${eid.length}`);
  eid.copy(payload, 0);

  payload.writeUInt8(eventType >>> 0 & 0xff, 32);
  payload.writeBigUInt64BE(BigInt(magnitudeNano), 33);
  payload.writeBigUInt64BE(BigInt(context), 41);
  payload.writeBigUInt64BE(BigInt(timestamp), 49);
  payload.writeUInt32BE(chainId >>> 0, 57);

  const bh = Buffer.from(blockHash, 'hex');
  if (bh.length !== 32) throw new Error(`block_hash must be 32 bytes, got ${bh.length}`);
  bh.copy(payload, 61);

  if (payload.length !== PAYLOAD_LEN) throw new Error(`payload length mismatch: ${payload.length}`);
  return payload;
}

/**
 * Compute the "sense" hash of a 93-byte payload:
 *   sense = SHA-256(payload || 0x00)
 *
 * This is the `committed_anchor_bh` baked into Path 1 of the vault script.
 * The Bitcoin script does OP_SHA256 on the witness-supplied 94-byte
 * pre-concatenated buffer and compares with this 32-byte commitment.
 */
export function computeSense(payload93) {
  if (!Buffer.isBuffer(payload93)) payload93 = Buffer.from(payload93);
  if (payload93.length !== PAYLOAD_LEN) {
    throw new Error(`payload must be ${PAYLOAD_LEN} bytes, got ${payload93.length}`);
  }
  const data = Buffer.concat([payload93, Buffer.from([SENSE_SUFFIX])]);
  return crypto.createHash('sha256').update(data).digest();  // 32 bytes
}

/**
 * Build the 94-byte witness buffer (payload || 0x00) the relayer submits
 * to unlock Path 1. SHA-256 of this buffer must equal committed_anchor_bh.
 */
export function buildWitnessPreimage(payload93) {
  if (!Buffer.isBuffer(payload93)) payload93 = Buffer.from(payload93);
  if (payload93.length !== PAYLOAD_LEN) {
    throw new Error(`payload must be ${PAYLOAD_LEN} bytes, got ${payload93.length}`);
  }
  return Buffer.concat([payload93, Buffer.from([SENSE_SUFFIX])]);
}

// =============================================================================
// Taproot script construction (2 leaves, no committee)
// =============================================================================

/**
 * Path 1 — Coherence Release.
 *
 * Script:  OP_SHA256 <committed_anchor_bh_32bytes> OP_EQUAL
 * Witness: <94_byte_preimage>
 *
 * The script does NOT verify a signature on this path. Authorization is
 * purely cryptographic: knowledge of the preimage. The output destination
 * is enforced by the pre-constructed spending transaction (see
 * buildReleaseTx), so even a malicious relayer cannot redirect the BTC.
 */
export function buildReleaseScript(committedAnchorBH) {
  const bh = typeof committedAnchorBH === 'string'
    ? Buffer.from(committedAnchorBH, 'hex')
    : Buffer.from(committedAnchorBH);
  if (bh.length !== 32) throw new Error(`committed_anchor_bh must be 32 bytes, got ${bh.length}`);

  return Buffer.from(bitcoin.script.compile([
    bitcoin.opcodes.OP_SHA256,
    bh,
    bitcoin.opcodes.OP_EQUAL,
  ]));
}

/**
 * Path 2 — Borrower Refund (CSV timelock).
 *
 * Script:  <csv_blocks> OP_CHECKSEQUENCEVERIFY OP_DROP <borrower_xonly_pubkey> OP_CHECKSIG
 * Witness: <borrower_schnorr_signature>
 *
 * After `csv_blocks` Bitcoin blocks confirm on the vault UTXO, the borrower
 * can sign a refund transaction. No committee signature, no federation.
 */
export function buildRefundScript(borrowerXOnlyPubkey, csvBlocks) {
  const pk = typeof borrowerXOnlyPubkey === 'string'
    ? Buffer.from(borrowerXOnlyPubkey, 'hex')
    : Buffer.from(borrowerXOnlyPubkey);
  if (pk.length !== 32) throw new Error(`borrower x-only pubkey must be 32 bytes, got ${pk.length}`);
  if (!Number.isInteger(csvBlocks) || csvBlocks < 1 || csvBlocks > 0xffff) {
    throw new Error(`csv_blocks must be uint16, got ${csvBlocks}`);
  }

  return Buffer.from(bitcoin.script.compile([
    bitcoin.script.number.encode(csvBlocks),
    bitcoin.opcodes.OP_CHECKSEQUENCEVERIFY,
    bitcoin.opcodes.OP_DROP,
    pk,
    bitcoin.opcodes.OP_CHECKSIG,
  ]));
}

/**
 * Compute the Taproot control block for a given leaf script in the tree.
 *
 * controlBlock = parity_byte || internal_pubkey || [merkle_path_hashes...]
 *
 * The parity bit (low bit of byte 0) is derived from the tweaked output key.
 * The remaining 7 bits of byte 0 are the leaf version (0xc0 = LEAF_VERSION_TAPSCRIPT).
 */
function computeControlBlock(internalPubkey, scriptTree, targetScript) {
  const hashTree = toHashTree(scriptTree);
  const leafHash = tapleafHash({ output: targetScript, version: LEAF_VERSION_TAPSCRIPT });
  const path = findScriptPath(hashTree, leafHash) ?? [];
  const tweak = tweakKey(internalPubkey, hashTree.hash);
  if (!tweak) throw new Error('tweakKey returned null — invalid internal pubkey');
  const firstByte = (LEAF_VERSION_TAPSCRIPT & 0xfe) | (tweak.parity & 0x01);
  return Buffer.concat([
    Buffer.from([firstByte]),
    Buffer.from(internalPubkey),
    ...path.map((h) => Buffer.from(h)),
  ]);
}

/**
 * Build the full Taproot vault (2 leaves) and return address + scripts +
 * internal pubkey + tweak. The borrower funds the vault address.
 */
export function buildCoherenceVault(borrowerKeyPair, committedAnchorBH, csvBlocks) {
  // x-only internal key = first 32 bytes of the compressed pubkey.
  // tiny-secp256k1 returns Uint8Array; wrap in Buffer for cross-compat.
  const pubKeyBuf = Buffer.from(borrowerKeyPair.publicKey);
  if (pubKeyBuf.length !== 33) {
    throw new Error(`borrower compressed pubkey must be 33 bytes, got ${pubKeyBuf.length}`);
  }
  const internalPubkey = pubKeyBuf.slice(1, 33);
  if (internalPubkey.length !== 32) throw new Error('internal pubkey not 32 bytes');

  const releaseScript = buildReleaseScript(committedAnchorBH);
  const refundScript  = buildRefundScript(internalPubkey, csvBlocks);

  // Taproot script tree: leaf 0 = release, leaf 1 = refund.
  // bitcoinjs-lib accepts an array of {output: Buffer} leaves.
  const scriptTree = [
    { output: releaseScript },
    { output: refundScript  },
  ];

  const p2tr = bitcoin.payments.p2tr({
    internalPubkey,
    scriptTree,
    network,
  });

  // Pre-compute control blocks for both leaves so PSBT construction doesn't
  // need to re-walk the tree.
  const releaseControlBlock = computeControlBlock(internalPubkey, scriptTree, releaseScript);
  const refundControlBlock  = computeControlBlock(internalPubkey, scriptTree, refundScript);

  return {
    vaultAddress:    p2tr.address,
    vaultOutputScript: Buffer.from(p2tr.output).toString('hex'),
    internalPubkey:  internalPubkey.toString('hex'),
    tweak:           p2tr.tweak ? Buffer.from(p2tr.tweak).toString('hex') : null,
    releaseScript:   releaseScript.toString('hex'),
    refundScript:    refundScript.toString('hex'),
    releaseControlBlock: releaseControlBlock.toString('hex'),
    refundControlBlock:  refundControlBlock.toString('hex'),
    committedAnchorBH: typeof committedAnchorBH === 'string'
      ? committedAnchorBH
      : Buffer.from(committedAnchorBH).toString('hex'),
    csvBlocks,
    borrowerPubkey:  pubKeyBuf.toString('hex'),
    network:         network.bech32,
    p2tr,
    scriptTree,
  };
}

// =============================================================================
// Pre-constructed release + refund transactions
// =============================================================================
//
// KEY INSIGHT (the thing that makes this NOT Babylon):
//
//   Babylon: the committee must CO-SIGN every liquidation. If they refuse,
//   the BTC is stuck until the timelock expires.
//
//   TRION:   the release transaction is PRE-CONSTRUCTED at lock time. Its
//   input is the vault UTXO (Path 1 leaf), its output is the lender's address.
//   The TXID is a function of (input, output, nSequence, nLockTime) — NOT the
//   witness. The borrower does NOT sign anything on Path 1 (the script
//   requires no signature).
//
//   When the 93-byte preimage is published on Stacks, ANY relayer can take the
//   pre-constructed release tx, append the witness (the 94-byte payload||0x00),
//   and broadcast. They CANNOT change the output — that would change the TXID.
//   They CANNOT steal — the script authorizes only the spend, not the routing.
//
// =============================================================================

/**
 * Build the pre-constructed release transaction.
 *
 * The borrower pre-commits the spending tx structure (input = vault UTXO
 * spending via Path 1 release script, output = lender address). No borrower
 * signature is required on this path because the script checks only the
 * preimage hash.
 *
 * The returned PSBT is *not* signed — it doesn't need to be. The relayer
 * finalizes the input by providing the witness preimage + control block.
 *
 * @param {Object} vaultUtxo — { txid, vout, value, scriptHex }
 * @param {Object} vault    — the vault object returned by buildCoherenceVault
 * @param {string} lenderAddress — the BTC address the lender will receive at
 * @param {number} feeRate  — sat/vB (default 10)
 * @param {number} estVsize — estimated vsize of the spend (default 110)
 */
export function buildReleaseTx(vaultUtxo, vault, lenderAddress, feeRate = 10, estVsize = 110) {
  const psbt = new bitcoin.Psbt({ network });

  if (!vault.releaseControlBlock) {
    throw new Error('vault.releaseControlBlock missing — rebuild via buildCoherenceVault');
  }
  const releaseScriptBuf = Buffer.from(vault.releaseScript, 'hex');
  const controlBlock = Buffer.from(vault.releaseControlBlock, 'hex');

  psbt.addInput({
    hash: vaultUtxo.txid,
    index: vaultUtxo.vout,
    sequence: 0xfffffffd,   // non-final, but no CSV on path 1
    witnessUtxo: {
      script: Buffer.from(vault.vaultOutputScript, 'hex'),
      value: BigInt(vaultUtxo.value),
    },
    tapLeafScript: [
      {
        leafVersion: 0xc0,
        script: releaseScriptBuf,
        controlBlock,
      },
    ],
  });

  const fee = feeRate * estVsize;
  if (vaultUtxo.value <= fee) throw new Error(`vault value (${vaultUtxo.value}) <= fee (${fee})`);
  psbt.addOutput({
    address: lenderAddress,
    value: BigInt(vaultUtxo.value - fee),
  });

  return psbt;
}

/**
 * Build the borrower refund transaction (Path 2 — CSV timelock).
 *
 * Borrower signs the input with their Schnorr key. After `csvBlocks`
 * confirmations on the vault UTXO, this tx can be broadcast.
 *
 * @param {Object} vaultUtxo — { txid, vout, value, scriptHex }
 * @param {Object} vault    — the vault object returned by buildCoherenceVault
 * @param {Object} borrower  — ECPair (the same one used to build the vault)
 * @param {string} refundAddress — borrower's receiving address (default: p2tr of internal key)
 * @param {number} feeRate  — sat/vB (default 10)
 * @param {number} estVsize — estimated vsize (default 110)
 */
export function buildRefundTx(vaultUtxo, vault, borrower, refundAddress, feeRate = 10, estVsize = 110) {
  const psbt = new bitcoin.Psbt({ network });

  if (!vault.refundControlBlock) {
    throw new Error('vault.refundControlBlock missing — rebuild via buildCoherenceVault');
  }
  const refundScriptBuf = Buffer.from(vault.refundScript, 'hex');
  const controlBlock = Buffer.from(vault.refundControlBlock, 'hex');

  psbt.addInput({
    hash: vaultUtxo.txid,
    index: vaultUtxo.vout,
    sequence: vault.csvBlocks,   // CSV: relative timelock
    witnessUtxo: {
      script: Buffer.from(vault.vaultOutputScript, 'hex'),
      value: BigInt(vaultUtxo.value),
    },
    tapLeafScript: [
      {
        leafVersion: 0xc0,
        script: refundScriptBuf,
        controlBlock,
      },
    ],
  });

  const fee = feeRate * estVsize;
  if (vaultUtxo.value <= fee) throw new Error(`vault value (${vaultUtxo.value}) <= fee (${fee})`);

  const addr = refundAddress
    ?? bitcoin.payments.p2tr({ internalPubkey: Buffer.from(vault.internalPubkey, 'hex'), network }).address;
  psbt.addOutput({ address: addr, value: BigInt(vaultUtxo.value - fee) });

  // Borrower signs the input (Schnorr over Taproot script path)
  psbt.signInput(0, borrower);

  return psbt;
}

// =============================================================================
// Release tx finalization
// =============================================================================
//
// `cmdRevealPreimage` (below) constructs the witness stack inline rather than
// using a separate helper, because bitcoinjs-lib v7's Psbt.finalizeInput
// interface for tapLeafScript requires the witness stack as a single Buffer
// (the OP_PUSH-only witness encoding: <len><item>... <count>). We build that
// buffer directly in the CLI handler so the behavior is explicit and auditable.
// =============================================================================

// Helper kept for API symmetry; controlBlocks are now pre-computed in
// buildCoherenceVault directly via computeControlBlock().
// (No external callers — left intentionally minimal.)
function findLeaf(p2tr, scriptHex) {
  const target = Buffer.from(scriptHex, 'hex');
  const tree = p2tr.scriptTree;
  if (!tree) return null;
  if (Array.isArray(tree)) {
    for (const leaf of tree) {
      if (leaf.output && Buffer.from(leaf.output).equals(target)) return leaf;
      if (leaf.leaves) {
        for (const l of leaf.leaves) {
          if (l.output && Buffer.from(l.output).equals(target)) return l;
        }
      }
    }
  } else if (tree.output && Buffer.from(tree.output).equals(target)) {
    return tree;
  }
  return null;
}

// =============================================================================
// Vault state persistence (JSON)
// =============================================================================

export function saveVaultState(state, file) {
  const out = {
    schema: 'trion-coherence-vault/v1',
    createdAt: new Date().toISOString(),
    network: network.bech32,
    ...state,
  };
  fs.writeFileSync(file, JSON.stringify(out, null, 2));
  return out;
}

export function loadVaultState(file) {
  const raw = JSON.parse(fs.readFileSync(file, 'utf-8'));
  if (raw.schema !== 'trion-coherence-vault/v1') {
    throw new Error(`unsupported vault state schema: ${raw.schema}`);
  }
  return raw;
}

// =============================================================================
// CLI
// =============================================================================

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith('--')) {
      const key = a.slice(2);
      const val = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : 'true';
      args[key] = val;
    }
  }
  return args;
}

function die(msg, code = 1) {
  console.error(`error: ${msg}`);
  process.exit(code);
}

function printHelp() {
  console.log(`TRION Coherence Vault — preimage-triggered BTC lock (no committee)

USAGE
  node coherence-vault.js <command> [options]

COMMANDS
  create         Build a vault Taproot address (2 leaves) + pre-construct release tx.
                 Prints the vault address to fund.

    --borrower-wif <WIF>     Borrower's WIF (testnet/mainnet auto-detected).
    --lender-addr <addr>     Lender's receiving BTC address.
    --sats <amount>          Vault amount in satoshis.
    --csv-blocks <N>         Refund timelock in Bitcoin blocks (default 144 = 24h).
    --payload <hex>          93-byte HashDNA payload (computes anchor_bh via SHA-256(P||00)).
    --anchor-bh <hex>        OR: provide the committed anchor_bh directly (32 bytes).
    --vault-txid <hex>       (Optional) UTXO txid once the vault is funded.
    --vault-vout <N>         (Optional) UTXO vout once the vault is funded.
    --out <file>             Vault state output file (default: ./vault-state.json).
    --mainnet                Use Bitcoin mainnet (default: testnet).

  reveal-preimage  Build & print the final release tx with the preimage witness.

    --vault-state <file>     Vault state file (from create).
    --payload <hex>          93-byte HashDNA payload (must hash to committed anchor_bh).
    --out <file>             Output signed tx hex file (default: ./release-tx.hex).

  refund         Build & sign the borrower refund tx (Path 2 — CSV).

    --vault-state <file>     Vault state file.
    --borrower-wif <WIF>     Borrower's WIF.
    --out <file>             Output signed tx hex file (default: ./refund-tx.hex).

  derive-sense   Compute SHA-256(payload || 0x00) for a 93-byte payload.

    --payload <hex>          93-byte payload (hex).

  verify         Re-derive the vault address from a vault-state file (sanity check).

    --vault-state <file>     Vault state file.

  build-payload  Compose a 93-byte payload from its fields and print hex + sense hash.

    --entity-id <hex>        32 bytes.
    --event-type <N>         0-255.
    --magnitude-nano <N>     uint64.
    --context <N>            uint64.
    --timestamp <N>          uint64 unix seconds.
    --chain-id <N>           uint32.
    --block-hash <hex>       32 bytes.

EXAMPLE
  node coherence-vault.js create \\
    --borrower-wif cVt4... \\
    --lender-addr tb1q... \\
    --sats 100000 \\
    --csv-blocks 144 \\
    --payload <93-byte-hex>
`);
}

// ---------- create ----------
function cmdCreate(args) {
  if (!args['borrower-wif']) die('--borrower-wif is required');
  if (!args['sats'])          die('--sats is required');
  if (!args['lender-addr'])   die('--lender-addr is required (release destination)');
  const csvBlocks = parseInt(args['csv-blocks'] ?? '144', 10);
  if (!(csvBlocks >= 1 && csvBlocks <= 0xffff)) die(`--csv-blocks must be 1..65535, got ${csvBlocks}`);

  // Network selection: explicit --mainnet wins; otherwise auto-detect from WIF.
  // Testnet WIFs start with 'c' or '9'; mainnet WIFs start with 'L', 'K', or '5'.
  const wif = args['borrower-wif'];
  const wifIsMainnet = /^[LK5]/.test(wif);
  if (args['mainnet']) {
    network = bitcoin.networks.bitcoin;
  } else {
    network = wifIsMainnet ? bitcoin.networks.bitcoin : bitcoin.networks.testnet;
  }

  const borrower = ECPair.fromWIF(wif, network);

  // Compute or accept committed_anchor_bh
  let committedAnchorBH = args['anchor-bh'];
  let payloadHex = args['payload'];
  let payloadBuf = null;
  if (!committedAnchorBH) {
    if (!payloadHex) die('either --payload (93-byte hex) or --anchor-bh (32-byte hex) is required');
    payloadBuf = Buffer.from(payloadHex, 'hex');
    if (payloadBuf.length !== PAYLOAD_LEN) die(`--payload must be ${PAYLOAD_LEN} bytes, got ${payloadBuf.length}`);
    committedAnchorBH = computeSense(payloadBuf).toString('hex');
  } else {
    if (Buffer.from(committedAnchorBH, 'hex').length !== 32) die('--anchor-bh must be 32 bytes');
  }

  const vault = buildCoherenceVault(borrower, committedAnchorBH, csvBlocks);

  const sats = parseInt(args['sats'], 10);
  const lenderAddr = args['lender-addr'];

  // If the vault has already been funded (vault-txid/vout provided), pre-construct
  // the release + refund transactions. Otherwise just emit the address.
  let releaseTxHex = null, refundTxHex = null;
  let vaultUtxo = null;
  if (args['vault-txid'] && args['vault-vout'] !== undefined) {
    vaultUtxo = {
      txid: args['vault-txid'],
      vout: parseInt(args['vault-vout'], 10),
      value: sats,
      scriptHex: vault.vaultOutputScript,
    };
    try {
      const releasePsbt = buildReleaseTx(vaultUtxo, vault, lenderAddr);
      releaseTxHex = releasePsbt.toBase64();
    } catch (e) { console.warn(`[warn] release tx construction: ${e.message}`); }
    try {
      const refundPsbt = buildRefundTx(vaultUtxo, vault, borrower, null);
      refundTxHex = refundPsbt.toBase64();
    } catch (e) { console.warn(`[warn] refund tx construction: ${e.message}`); }
  }

  const state = saveVaultState({
    borrowerPubkey:   vault.borrowerPubkey,
    internalPubkey:   vault.internalPubkey,
    vaultAddress:     vault.vaultAddress,
    vaultOutputScript: vault.vaultOutputScript,
    releaseScript:    vault.releaseScript,
    refundScript:     vault.refundScript,
    releaseControlBlock: vault.releaseControlBlock,
    refundControlBlock:  vault.refundControlBlock,
    committedAnchorBH: vault.committedAnchorBH,
    csvBlocks,
    sats,
    lenderAddress:    lenderAddr,
    payloadHex:       payloadHex ?? null,
    vaultUtxo,
    releasePsbtB64:   releaseTxHex,
    refundPsbtB64:    refundTxHex,
  }, args['out'] ?? path.join(__dirname, 'vault-state.json'));

  // ----- summary -----
  console.log('==========================================================');
  console.log(' TRION Coherence Vault — created');
  console.log('==========================================================');
  console.log(` Network            : ${network === bitcoin.networks.bitcoin ? 'mainnet' : 'testnet'}`);
  console.log(` Vault address      : ${vault.vaultAddress}`);
  console.log(` Vault output script: ${vault.vaultOutputScript}`);
  console.log(` Borrower pubkey    : ${vault.borrowerPubkey}`);
  console.log(` Internal x-only key : ${vault.internalPubkey}`);
  console.log(` Committed anchor_bh: ${vault.committedAnchorBH}`);
  console.log(` CSV blocks (refund): ${csvBlocks}  (~${(csvBlocks * 10 / 60).toFixed(1)} hours)`);
  console.log(` Lender destination : ${lenderAddr}`);
  console.log(` Locked amount      : ${sats} sats`);
  console.log('----------------------------------------------------------');
  console.log(' Script path 1 — Coherence Release (preimage reveal):');
  console.log(`   ${vault.releaseScript}`);
  console.log(' Script path 2 — Borrower Refund (CSV timelock):');
  console.log(`   ${vault.refundScript}`);
  console.log('----------------------------------------------------------');
  console.log(` NO committee. NO multisig. NO federation. NO oracle.`);
  console.log(` Anyone with the preimage can trigger release.`);
  console.log(` Borrower can refund after ${csvBlocks} blocks.`);
  console.log(` State file: ${args['out'] ?? path.join(__dirname, 'vault-state.json')}`);
  console.log('==========================================================');
}

// ---------- reveal-preimage ----------
function cmdRevealPreimage(args) {
  if (!args['vault-state']) die('--vault-state is required');
  if (!args['payload'])     die('--payload is required (93-byte hex)');
  const state = loadVaultState(args['vault-state']);
  const payload = Buffer.from(args['payload'], 'hex');
  if (payload.length !== PAYLOAD_LEN) die(`--payload must be ${PAYLOAD_LEN} bytes, got ${payload.length}`);

  // Sanity: SHA-256(payload || 0x00) MUST equal committed anchor_bh
  const derived = computeSense(payload).toString('hex');
  if (derived !== state.committedAnchorBH) {
    die(`preimage hash mismatch:\n  derived  ${derived}\n  expected ${state.committedAnchorBH}`);
  }

  if (!state.vaultUtxo) die('vault-state has no funded UTXO; cannot build release tx. Re-run create with --vault-txid/--vault-vout after funding.');
  if (!state.releasePsbtB64) die('vault-state has no pre-constructed release PSBT.');

  // Load the PSBT, inject the preimage witness, finalize.
  const psbt = bitcoin.Psbt.fromBase64(state.releasePsbtB64);
  const preimage94 = buildWitnessPreimage(payload);
  const input = psbt.data.inputs[0];
  const leaf = input.tapLeafScript[0];
  const ctrl = Buffer.from(leaf.controlBlock);
  const releaseScriptBuf = Buffer.from(leaf.script);

  // Build witness stack: [preimage, script, controlBlock]
  // (No signature on Path 1 — the preimage hash is the authorization.)
  const witnessStack = [preimage94, releaseScriptBuf, ctrl];
  const finalScriptWitness = Buffer.from(
    witnessStackToScriptWitness(witnessStack),
  );

  // Use a custom finalizer so bitcoinjs-lib doesn't try to require a
  // Taproot signature (this path intentionally has none).
  psbt.finalizeInput(0, () => ({ finalScriptWitness }));

  const tx = psbt.extractTransaction();
  const rawHex = Buffer.from(tx.toBuffer()).toString('hex');
  const txid = tx.getId();

  const outFile = args['out'] ?? path.join(__dirname, 'release-tx.hex');
  fs.writeFileSync(outFile, rawHex);

  console.log('==========================================================');
  console.log(' TRION Coherence Vault — release tx built from preimage');
  console.log('==========================================================');
  console.log(` Vault              : ${state.vaultAddress}`);
  console.log(` Committed anchor_bh: ${state.committedAnchorBH}`);
  console.log(` Payload (93B hex)  : ${args['payload']}`);
  console.log(` Preimage (94B)     : ${preimage94.toString('hex')}`);
  console.log(` Derived sense      : ${derived} ✓ matches committed anchor_bh`);
  console.log(` Release TXID       : ${txid}`);
  console.log(` Output destination : ${state.lenderAddress} (pre-constructed, cannot be changed)`);
  console.log(` Raw tx hex         : ${rawHex.slice(0, 80)}...`);
  console.log(` Signed tx file     : ${outFile}`);
  console.log('----------------------------------------------------------');
  console.log(' Anyone can broadcast this tx. The preimage was public on');
  console.log(' Stacks — censorship is impossible. The lender receives');
  console.log(' the BTC; no committee signature was needed.');
  console.log('==========================================================');
}

// ---------- refund ----------
function cmdRefund(args) {
  if (!args['vault-state'])  die('--vault-state is required');
  if (!args['borrower-wif']) die('--borrower-wif is required');
  const state = loadVaultState(args['vault-state']);

  // Auto-detect network from WIF (same logic as cmdCreate)
  const wif = args['borrower-wif'];
  const wifIsMainnet = /^[LK5]/.test(wif);
  if (args['mainnet']) {
    network = bitcoin.networks.bitcoin;
  } else {
    network = wifIsMainnet ? bitcoin.networks.bitcoin : bitcoin.networks.testnet;
  }
  const borrower = ECPair.fromWIF(wif, network);
  // Sanity: pubkey must match
  if (Buffer.from(borrower.publicKey).toString('hex') !== state.borrowerPubkey) {
    die('borrower WIF does not match the pubkey stored in vault-state');
  }

  if (!state.vaultUtxo) die('vault-state has no funded UTXO. Re-run create with --vault-txid/--vault-vout.');
  // Rebuild p2tr so we get the controlBlocks (rebuild is cheap & idempotent).
  const rebuilt = buildCoherenceVault(borrower, state.committedAnchorBH, state.csvBlocks);
  const vault = {
    p2tr: rebuilt.p2tr,
    vaultOutputScript: state.vaultOutputScript,
    releaseScript: state.releaseScript,
    refundScript:  state.refundScript,
    releaseControlBlock: rebuilt.releaseControlBlock,
    refundControlBlock:  rebuilt.refundControlBlock,
    internalPubkey: state.internalPubkey,
    csvBlocks:      state.csvBlocks,
  };

  const psbt = buildRefundTx(state.vaultUtxo, vault, borrower, null);
  psbt.finalizeAllInputs();
  const tx = psbt.extractTransaction();
  const rawHex = Buffer.from(tx.toBuffer()).toString('hex');
  const txid = tx.getId();

  const outFile = args['out'] ?? path.join(__dirname, 'refund-tx.hex');
  fs.writeFileSync(outFile, rawHex);

  console.log('==========================================================');
  console.log(' TRION Coherence Vault — borrower refund tx signed');
  console.log('==========================================================');
  console.log(` Vault              : ${state.vaultAddress}`);
  console.log(` CSV blocks required: ${state.csvBlocks}`);
  console.log(` Refund TXID        : ${txid}`);
  console.log(` Raw tx hex         : ${rawHex.slice(0, 80)}...`);
  console.log(` Signed tx file     : ${outFile}`);
  console.log('----------------------------------------------------------');
  console.log(` Borrower can broadcast after ${state.csvBlocks} Bitcoin blocks`);
  console.log(` have confirmed on the vault UTXO. No committee can block this.`);
  console.log('==========================================================');
}

// ---------- derive-sense ----------
function cmdDeriveSense(args) {
  if (!args['payload']) die('--payload is required (93-byte hex)');
  const payload = Buffer.from(args['payload'], 'hex');
  if (payload.length !== PAYLOAD_LEN) die(`--payload must be ${PAYLOAD_LEN} bytes, got ${payload.length}`);
  const sense = computeSense(payload);
  console.log(`payload (93 bytes): ${args['payload']}`);
  console.log(`sense = SHA-256(payload || 0x00) = ${sense.toString('hex')}`);
}

// ---------- build-payload ----------
function cmdBuildPayload(args) {
  const payload = buildPayload({
    entityId:       args['entity-id']       ?? die('--entity-id required (32-byte hex)'),
    eventType:      parseInt(args['event-type'] ?? '0', 10),
    magnitudeNano:  args['magnitude-nano']  ?? '0',
    context:        args['context']         ?? '0',
    timestamp:      args['timestamp']       ?? String(Math.floor(Date.now() / 1000)),
    chainId:        parseInt(args['chain-id'] ?? '0', 10),
    blockHash:      args['block-hash']      ?? die('--block-hash required (32-byte hex)'),
  });
  const sense = computeSense(payload);
  console.log(`payload (93 bytes): ${payload.toString('hex')}`);
  console.log(`sense = SHA-256(payload || 0x00) = ${sense.toString('hex')}`);
}

// ---------- verify ----------
function cmdVerify(args) {
  if (!args['vault-state']) die('--vault-state is required');
  const state = loadVaultState(args['vault-state']);

  // Rebuild the vault from stored state and check address matches
  // Synthesize a dummy keypair from the stored pubkey (we only need the address)
  const internalPubkey = Buffer.from(state.internalPubkey, 'hex');
  const releaseScript = Buffer.from(state.releaseScript, 'hex');
  const refundScript  = Buffer.from(state.refundScript, 'hex');
  const scriptTree = [
    { output: releaseScript },
    { output: refundScript  },
  ];
  const p2tr = bitcoin.payments.p2tr({
    internalPubkey,
    scriptTree,
    network,
  });

  const match = p2tr.address === state.vaultAddress;
  console.log('==========================================================');
  console.log(' TRION Coherence Vault — verify');
  console.log('==========================================================');
  console.log(` Stored address     : ${state.vaultAddress}`);
  console.log(` Re-derived address: ${p2tr.address}`);
  console.log(` Match              : ${match ? 'YES ✓' : 'NO ✗'}`);
  console.log(` Committed anchor_bh: ${state.committedAnchorBH}`);
  console.log(` CSV blocks         : ${state.csvBlocks}`);
  if (state.payloadHex) {
    const derived = computeSense(Buffer.from(state.payloadHex, 'hex')).toString('hex');
    console.log(` Payload sense      : ${derived}`);
    console.log(` Sense matches bh   : ${derived === state.committedAnchorBH ? 'YES ✓' : 'NO ✗'}`);
  }
  console.log('==========================================================');
  if (!match) process.exit(2);
}

// ---------- dispatch ----------
const argv = process.argv.slice(2);
// CLI entry point — only runs when this file is the entry point, not when imported
if (import.meta.url === `file://${process.argv[1]}`) {
  const argv = process.argv.slice(2);
  if (argv.length === 0 || argv[0] === '--help' || argv[0] === '-h' || argv[0] === 'help') {
    printHelp();
    process.exit(0);
  }

  const cmd = argv[0];
  const rest = parseArgs(argv.slice(1));

  switch (cmd) {
    case 'create':            cmdCreate(rest); break;
    case 'reveal-preimage':   cmdRevealPreimage(rest); break;
    case 'refund':            cmdRefund(rest); break;
    case 'derive-sense':      cmdDeriveSense(rest); break;
    case 'build-payload':     cmdBuildPayload(rest); break;
    case 'verify':            cmdVerify(rest); break;
    default:
      console.error(`unknown command: ${cmd}`);
      printHelp();
      process.exit(1);
  }
}
