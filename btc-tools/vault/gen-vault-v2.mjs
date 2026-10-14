/**
 * gen-vault-v2.mjs — Generate vault with CORRECT script ordering + 80-byte payload.
 *
 * Fixes from v1:
 * 1. Release script: OP_SHA256 <hash> OP_EQUAL (was: <hash> OP_SHA256 OP_EQUAL)
 * 2. Payload: 80 bytes (was: 93 bytes, exceeded 80-byte witness limit)
 *    - entity_id: 20 bytes (HASH160 style, was 32)
 *    - event_type: 1 byte
 *    - magnitude_nano: 8 bytes
 *    - timestamp: 8 bytes
 *    - chain_id: 4 bytes
 *    - block_hash: 32 bytes
 *    - Total: 73 bytes (padded to 80 with zeros)
 * 3. Committed hash = SHA-256(payload) (no suffix — the witness pushes the payload directly)
 */

import { ECPairFactory } from 'ecpair';
import * as ecc from 'tiny-secp256k1';
import * as bitcoin from 'bitcoinjs-lib';
bitcoin.initEccLib(ecc);
import { toHashTree, findScriptPath, tapleafHash, tweakKey, LEAF_VERSION_TAPSCRIPT } from 'bitcoinjs-lib/src/payments/bip341';
import * as crypto from 'crypto';
import * as fs from 'fs';

const ECPair = ECPairFactory(ecc);
const network = bitcoin.networks.testnet;

// ─── Real BTC testnet data (from canonical wallet) ────────────────────────
const BTC_ADDR = 'tb1q5d69fyxxxwdkr7pecmxyr245w5jqchm9zptkks';
const btcBlockHash = '00000000000001a9562ec7227605f68ea1baf77dfa37d6794fcd55bca4a509f4';
const btcBlockTime = 1788718503;
const btcSats = 304527;

// ─── Build 80-byte payload ─────────────────────────────────────────────────
// entity_id[20] + event_type[1] + magnitude_nano[8] + timestamp[8] + chain_id[4] + block_hash[32] = 73 bytes
// Pad to 80 bytes with zeros
const entityIdFull = crypto.createHash('sha256').update(BTC_ADDR.toLowerCase()).digest();
const entityId = entityIdFull.subarray(0, 20); // 20 bytes (HASH160 style)

const magnitudeNano = BigInt(btcSats) * 1_000_000_000n;

const payload = Buffer.alloc(80); // 80 bytes, zero-padded
entityId.copy(payload, 0);                         // 0-19: entity_id (20 bytes)
payload.writeUInt8(0, 20);                         // 20: event_type (TRANSFER=0)
payload.writeBigUInt64BE(magnitudeNano, 21);       // 21-28: magnitude_nano (8 bytes)
payload.writeBigUInt64BE(BigInt(btcBlockTime), 29); // 29-36: timestamp (8 bytes)
payload.writeUInt32BE(100, 37);                     // 37-40: chain_id (Bitcoin=100)
Buffer.from(btcBlockHash, 'hex').copy(payload, 41); // 41-72: block_hash (32 bytes)
// 73-79: reserved (zeros)

const payloadHex = payload.toString('hex');
console.log('=== Payload (80 bytes) ===');
console.log(`  hex: ${payloadHex}`);
console.log(`  length: ${payload.length} bytes`);

// ─── Compute committed anchor_bh = SHA-256(payload) ───────────────────────
// NO suffix! The witness pushes the raw 80-byte payload, and OP_SHA256 hashes it directly.
const committedAnchorBH = crypto.createHash('sha256').update(payload).digest('hex');
console.log(`  committed anchor_bh: ${committedAnchorBH}`);

// Verify locally
const verifyHash = crypto.createHash('sha256').update(payload).digest('hex');
console.log(`  verify: ${verifyHash} (match: ${verifyHash === committedAnchorBH})`);

// ─── Generate borrower keypair ─────────────────────────────────────────────
const borrower = ECPair.makeRandom({ network });
const wif = borrower.toWIF();
const pubkey = Buffer.from(borrower.publicKey);
const internalPubkey = pubkey.subarray(1, 33);
console.log(`\n=== Borrower ===`);
console.log(`  WIF: ${wif}`);
console.log(`  pubkey: ${pubkey.toString('hex')}`);
console.log(`  internal (x-only): ${internalPubkey.toString('hex')}`);

// ─── Build the CORRECT release script ──────────────────────────────────────
// OP_SHA256 <push 32 bytes: committed_hash> OP_EQUAL
// = a8 20 <32-byte-hash> 87
const releaseScript = bitcoin.script.compile([
  bitcoin.opcodes.OP_SHA256,
  Buffer.from(committedAnchorBH, 'hex'),
  bitcoin.opcodes.OP_EQUAL,
]);
console.log(`\n=== Release Script ===`);
console.log(`  hex: ${releaseScript.toString('hex')}`);
console.log(`  length: ${releaseScript.length} bytes`);
console.log(`  decoded: OP_SHA256 <${committedAnchorBH}> OP_EQUAL`);

// ─── Build the refund script (CSV) ─────────────────────────────────────────
const csvBlocks = 6;
const refundScript = bitcoin.script.compile([
  bitcoin.script.number.encode(csvBlocks),
  bitcoin.opcodes.OP_CHECKSEQUENCEVERIFY,
  bitcoin.opcodes.OP_DROP,
  internalPubkey,
  bitcoin.opcodes.OP_CHECKSIG,
]);
console.log(`\n=== Refund Script ===`);
console.log(`  hex: ${refundScript.toString('hex')}`);
console.log(`  length: ${refundScript.length} bytes`);

// ─── Build Taproot vault ───────────────────────────────────────────────────
const tree = [
  { output: releaseScript },
  { output: refundScript },
];
const p2tr = bitcoin.payments.p2tr({
  internalPubkey,
  scriptTree: tree,
  network,
});

console.log(`\n=== Vault ===`);
console.log(`  address: ${p2tr.address}`);
console.log(`  output script: ${Buffer.from(p2tr.output).toString('hex')}`);

// ─── Compute control blocks ────────────────────────────────────────────────
function computeControlBlock(scriptTree, targetScript) {
  const hashTree = toHashTree(scriptTree);
  const leafHash = tapleafHash({ output: targetScript, version: LEAF_VERSION_TAPSCRIPT });
  const path = findScriptPath(hashTree, leafHash) ?? [];
  const tweak = tweakKey(internalPubkey, hashTree.hash);
  if (!tweak) throw new Error('tweakKey failed');
  const firstByte = (LEAF_VERSION_TAPSCRIPT & 0xfe) | (tweak.parity & 0x01);
  return Buffer.concat([
    Buffer.from([firstByte]),
    Buffer.from(internalPubkey),
    ...path.map(h => Buffer.from(h)),
  ]);
}

const releaseControlBlock = computeControlBlock(tree, releaseScript);
const refundControlBlock = computeControlBlock(tree, refundScript);

console.log(`  release CB: ${releaseControlBlock.toString('hex')}`);
console.log(`  refund CB: ${refundControlBlock.toString('hex')}`);

// ─── Verify hash parity ────────────────────────────────────────────────────
const hashTree = toHashTree(tree);
const merkleRoot = hashTree.hash;
const tweakResult = tweakKey(internalPubkey, merkleRoot);
console.log(`\n=== Verification ===`);
console.log(`  merkle root: ${Buffer.from(merkleRoot).toString('hex')}`);
console.log(`  tweak parity: ${tweakResult.parity}`);
console.log(`  tweaked key: ${Buffer.from(tweakResult.x).toString('hex')}`);
console.log(`  output key in vault: ${Buffer.from(p2tr.output).subarray(2).toString('hex')}`);
console.log(`  keys match: ${Buffer.from(tweakResult.x).toString('hex') === Buffer.from(p2tr.output).subarray(2).toString('hex')}`);

// ─── Save vault state ──────────────────────────────────────────────────────
const vaultState = {
  vaultAddress: p2tr.address,
  vaultOutputScript: Buffer.from(p2tr.output).toString('hex'),
  internalPubkey: internalPubkey.toString('hex'),
  committedAnchorBH,
  payloadHex,
  payloadLength: 80,
  csvBlocks,
  borrowerWif: wif,
  borrowerPubkey: pubkey.toString('hex'),
  lenderAddress: BTC_ADDR,
  releaseScript: releaseScript.toString('hex'),
  refundScript: refundScript.toString('hex'),
  releaseControlBlock: releaseControlBlock.toString('hex'),
  refundControlBlock: refundControlBlock.toString('hex'),
};

fs.writeFileSync('/tmp/vault-state-v2.json', JSON.stringify(vaultState, null, 2));
console.log(`\n=== State saved to /tmp/vault-state-v2.json ===`);
console.log(`\n>>> FUND THIS VAULT: ${p2tr.address} <<<`);
console.log(`>>> Send at least 10,000 sats (0.0001 BTC) on Bitcoin testnet <<<`);
