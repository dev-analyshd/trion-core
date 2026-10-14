/**
 * broadcast-preimage-spend.mjs — Build + sign + broadcast the preimage-reveal
 * spend transaction on Bitcoin testnet.
 *
 * This spends the funded Coherence Vault UTXO via the preimage-reveal script
 * path. No signature needed — the 93-byte HashDNA payload IS the authorization.
 */

import { ECPairFactory } from 'ecpair';
import * as ecc from 'tiny-secp256k1';
import * as bitcoin from 'bitcoinjs-lib';
bitcoin.initEccLib(ecc);
import * as fs from 'fs';
import { witnessStackToScriptWitness } from 'bitcoinjs-lib/src/psbt/psbtutils';

const ECPair = ECPairFactory(ecc);
const network = bitcoin.networks.testnet;

// ─── Read vault state ──────────────────────────────────────────────────────
const vault = JSON.parse(fs.readFileSync('/tmp/vault-state-live.json', 'utf-8'));
console.log('=== Coherence Vault Preimage-Reveal Spend ===');
console.log(`Vault address: ${vault.vaultAddress}`);
console.log(`anchor_bh: ${vault.committedAnchorBH}`);
console.log(`Lender: ${vault.lenderAddress}`);
console.log('');

// ─── Funding UTXO (from mempool.space) ─────────────────────────────────────
const fundingTxid = '688222635d1c86cae125ba4cf33b660b4d686e11ef15107a3547f7e724ab15d2';
const fundingVout = 0;
const fundingAmount = 128310; // sats

console.log('=== Funding UTXO ===');
console.log(`  txid: ${fundingTxid}`);
console.log(`  vout: ${fundingVout}`);
console.log(`  value: ${fundingAmount} sats`);
console.log('');

// ─── Build the preimage-reveal spend tx ─────────────────────────────────────
const payload = Buffer.from(vault.payloadHex, 'hex');
const releaseScript = Buffer.from(vault.releaseScript.split(',').map(b => parseInt(b)), 'hex');
// Actually the releaseScript in vault-state is stored as comma-separated bytes.
// Let's use the hex version instead. The committedAnchorBH is the hash.
// releaseScript = OP_SHA256 <hash> OP_EQUAL = 0xa8 <32-byte-hash> 0x87

// Rebuild the release script properly
const committedHash = Buffer.from(vault.committedAnchorBH, 'hex');
const releaseScriptHex = Buffer.concat([
  Buffer.from([0xa8]), // OP_SHA256
  Buffer.from([0x20]), // push 32 bytes
  committedHash,
  Buffer.from([0x87]), // OP_EQUAL
]);
console.log(`Release script hex: ${releaseScriptHex.toString('hex')}`);
console.log(`Release script length: ${releaseScriptHex.length} bytes`);

const controlBlock = Buffer.from(vault.releaseControlBlock, 'hex');
console.log(`Control block: ${controlBlock.toString('hex').slice(0, 40)}...`);
console.log(`Control block length: ${controlBlock.length} bytes`);
console.log('');

// ─── Build the PSBT ─────────────────────────────────────────────────────────
const psbt = new bitcoin.Psbt({ network });

psbt.addInput({
  hash: fundingTxid,
  index: fundingVout,
  witnessUtxo: {
    script: Buffer.from(vault.vaultOutputScript, 'hex'),
    value: BigInt(fundingAmount),
  },
  tapLeafScript: [{
    leafVersion: 0xc0,
    script: releaseScriptHex,
    controlBlock: controlBlock,
  }],
});

// Output: send to lender (minus fee)
const feeSats = 1000; // ~1 sat/vB for ~150 vbyte tx
const sendAmount = BigInt(fundingAmount - feeSats);
psbt.addOutput({
  address: vault.lenderAddress,
  value: sendAmount,
});

console.log('=== Spend Transaction ===');
console.log(`  Input: ${fundingAmount} sats (vault UTXO)`);
console.log(`  Output: ${sendAmount} sats -> ${vault.lenderAddress}`);
console.log(`  Fee: ${feeSats} sats`);
console.log('');

// ─── Finalize with the preimage witness ────────────────────────────────────
// The committed hash is SHA-256(payload || 0x00), so the witness must push
// (payload || 0x00) as a single 94-byte item for OP_SHA256 to hash correctly.
const payloadWithSuffix = Buffer.concat([payload, Buffer.from([0x00])]);
const witness = [
  payloadWithSuffix,   // the 94-byte preimage (payload || 0x00)
  releaseScriptHex,   // the script
  controlBlock,       // the control block
];

console.log('=== Witness Stack ===');
console.log(`  [0] payload: ${payload.length} bytes (${payload.toString('hex').slice(0, 40)}...)`);
console.log(`  [1] script: ${releaseScriptHex.length} bytes`);
console.log(`  [2] controlBlock: ${controlBlock.length} bytes`);
console.log('');

psbt.finalizeInput(0, () => ({
  finalScriptWitness: witnessStackToScriptWitness(witness),
}));

const signedTx = psbt.extractTransaction();
const rawTxHex = signedTx.toHex();
const spendTxid = signedTx.getId();

console.log('=== Signed Transaction ===');
console.log(`  txid: ${spendTxid}`);
console.log(`  raw hex: ${rawTxHex.slice(0, 80)}...`);
console.log(`  total length: ${rawTxHex.length} hex chars (${rawTxHex.length / 2} bytes)`);
console.log('');

// ─── Broadcast to Bitcoin testnet ──────────────────────────────────────────
console.log('=== Broadcasting to Bitcoin testnet via mempool.space ===');

try {
  const resp = await fetch('https://mempool.space/testnet/api/tx', {
    method: 'POST',
    headers: { 'Content-Type': 'text/plain' },
    body: rawTxHex,
  });
  const text = await resp.text();
  if (resp.ok) {
    const broadcastTxid = text.replace(/"/g, '').trim();
    console.log(`  BROADCAST SUCCESS!`);
    console.log(`  txid: ${broadcastTxid}`);
    console.log(`  Explorer: https://mempool.space/testnet/tx/${broadcastTxid}`);
    console.log('');

    // Save results
    const results = {
      step: 'preimage-reveal-spend',
      status: 'broadcast_success',
      fundingTxid: fundingTxid,
      fundingVout: fundingVout,
      fundingAmount: fundingAmount,
      spendTxid: broadcastTxid,
      sendAmount: sendAmount,
      fee: feeSats,
      vaultAddress: vault.vaultAddress,
      lenderAddress: vault.lenderAddress,
      committedAnchorBH: vault.committedAnchorBH,
      payloadHex: vault.payloadHex,
      explorerUrl: `https://mempool.space/testnet/tx/${broadcastTxid}`,
      timestamp: new Date().toISOString(),
    };

    fs.writeFileSync(
      '/home/z/my-project/trion-core/proofs/btcp-zero-bridge/stacks/btc-testnet-live-results.json',
      JSON.stringify(results, null, 2)
    );
    console.log('Results saved to proofs/btcp-zero-bridge/stacks/btc-testnet-live-results.json');
  } else {
    console.error(`  BROADCAST FAILED: ${resp.status} ${text}`);
    console.log(`  Raw tx hex saved for debugging: ${rawTxHex.slice(0, 200)}...`);
    fs.writeFileSync('/tmp/raw-tx-hex.txt', rawTxHex);
  }
} catch (e) {
  console.error(`  Broadcast error: ${e.message}`);
  console.log(`  Raw tx hex: ${rawTxHex}`);
  fs.writeFileSync('/tmp/raw-tx-hex.txt', rawTxHex);
}
