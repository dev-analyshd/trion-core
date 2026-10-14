/**
 * broadcast-preimage-v2.mjs — Build + sign + broadcast the PREIMAGE-REVEAL
 * spend transaction on Bitcoin testnet.
 *
 * This is the NOVEL path — the HashDNA preimage triggers the BTC release.
 * No signature needed — the 80-byte preimage IS the authorization.
 */

import { ECPairFactory } from 'ecpair';
import * as ecc from 'tiny-secp256k1';
import * as bitcoin from 'bitcoinjs-lib';
bitcoin.initEccLib(ecc);
import { witnessStackToScriptWitness } from 'bitcoinjs-lib/src/psbt/psbtutils';
import * as fs from 'fs';
import * as crypto from 'crypto';

const network = bitcoin.networks.testnet;

// ─── Read vault state ──────────────────────────────────────────────────────
const vault = JSON.parse(fs.readFileSync('/tmp/vault-state-v2.json', 'utf-8'));
console.log('=== Coherence Vault Preimage-Reveal Spend (v2) ===');
console.log(`Vault address: ${vault.vaultAddress}`);
console.log(`committed anchor_bh: ${vault.committedAnchorBH}`);
console.log(`payload: ${vault.payloadHex} (${vault.payloadLength} bytes)`);
console.log(`lender: ${vault.lenderAddress}`);
console.log('');

// ─── Fetch the vault UTXO ──────────────────────────────────────────────────
const VAULT_ADDR = vault.vaultAddress;
console.log(`Fetching UTXOs for ${VAULT_ADDR}...`);
const utxosResp = await fetch(`https://mempool.space/testnet/api/address/${VAULT_ADDR}/utxo`);
const utxos = await utxosResp.json();

if (!utxos || utxos.length === 0) {
  console.error('VAULT NOT FUNDED YET!');
  console.log(`\n>>> Send testnet BTC to: ${VAULT_ADDR} <<<`);
  console.log('>>> Then re-run this script <<<');
  process.exit(1);
}

const utxo = utxos[0];
console.log(`UTXO found: txid=${utxo.txid} vout=${utxo.vout} value=${utxo.value} sats`);
console.log(`Confirmed: ${utxo.status.confirmed}`);

// Wait for confirmation if needed
if (!utxo.status.confirmed) {
  console.log('Waiting for confirmation...');
  for (let i = 0; i < 60; i++) {
    await new Promise(r => setTimeout(r, 30000));
    const resp = await fetch(`https://mempool.space/testnet/api/address/${VAULT_ADDR}/utxo`);
    const updated = await resp.json();
    if (updated[0]?.status?.confirmed) {
      console.log(`Confirmed at block ${updated[0].status.block_height}`);
      utxo.status = updated[0].status;
      break;
    }
    process.stdout.write(`\r  Waiting... (${(i+1)*30}s)`);
  }
}

const fundingTxid = utxo.txid;
const fundingVout = utxo.vout;
const fundingAmount = utxo.value;

// ─── Build the preimage-reveal spend tx ────────────────────────────────────
const payload = Buffer.from(vault.payloadHex, 'hex');
const releaseScript = Buffer.from(vault.releaseScript.split(',').map(b => parseInt(b)));
const controlBlock = Buffer.from(vault.releaseControlBlock, 'hex');

console.log(`\n=== Release Script ===`);
console.log(`  hex: ${releaseScript.toString('hex')}`);
console.log(`  decoded: OP_SHA256 <${vault.committedAnchorBH}> OP_EQUAL`);
console.log(`  length: ${releaseScript.length} bytes`);

// Verify: SHA-256(payload) should equal committedAnchorBH
const computedHash = crypto.createHash('sha256').update(payload).digest('hex');
console.log(`\n=== Hash Verification ===`);
console.log(`  SHA-256(payload): ${computedHash}`);
console.log(`  committed_bh:     ${vault.committedAnchorBH}`);
console.log(`  match: ${computedHash === vault.committedAnchorBH}`);

if (computedHash !== vault.committedAnchorBH) {
  console.error('HASH MISMATCH! Aborting.');
  process.exit(1);
}

// ─── Build the raw transaction ──────────────────────────────────────────────
const tx = new bitcoin.Transaction();
tx.version = 2;

// Add input (the vault UTXO)
tx.addInput(
  Buffer.from(fundingTxid, 'hex').reverse(),
  fundingVout,
  0xfffffffe // standard sequence (no CSV for this path)
);

// Add output (send to lender)
const feeSats = 1000;
const sendAmount = fundingAmount - feeSats;
const lenderOutput = bitcoin.address.toOutputScript(vault.lenderAddress, network);
tx.addOutput(lenderOutput, BigInt(sendAmount));

console.log(`\n=== Spend Transaction ===`);
console.log(`  Input: ${fundingTxid}:${fundingVout} (${fundingAmount} sats)`);
console.log(`  Output: ${sendAmount} sats -> ${vault.lenderAddress} (lender)`);
console.log(`  Fee: ${feeSats} sats`);

// ─── Build the witness ─────────────────────────────────────────────────────
// The release script is: OP_SHA256 <hash> OP_EQUAL
// Execution: witness pushes payload on stack → OP_SHA256 hashes it → <hash> pushed → OP_EQUAL checks
// Witness: [payload (80 bytes), releaseScript (35 bytes), controlBlock (65 bytes)]
const witness = [
  payload,        // 80-byte preimage
  releaseScript, // 35-byte script
  controlBlock,  // 65-byte control block
];

console.log(`\n=== Witness Stack ===`);
console.log(`  [0] payload: ${payload.length} bytes`);
console.log(`  [1] script: ${releaseScript.length} bytes`);
console.log(`  [2] controlBlock: ${controlBlock.length} bytes`);
console.log(`  Total witness size: ${payload.length + releaseScript.length + controlBlock.length + 3} bytes`);

// Check: payload is 80 bytes — within the 80-byte standardness limit!
if (payload.length > 80) {
  console.error(`PAYLOAD TOO LARGE: ${payload.length} > 80 bytes (witness standardness limit)`);
  process.exit(1);
}
console.log(`  Payload within 80-byte limit: ✅`);

// Set the witness
tx.setWitness(0, witness);

const rawTxHex = tx.toHex();
const txid = tx.getId();
console.log(`\n=== Signed Transaction ===`);
console.log(`  txid: ${txid}`);
console.log(`  raw hex: ${rawTxHex}`);
console.log(`  length: ${rawTxHex.length / 2} bytes`);

// ─── Broadcast ──────────────────────────────────────────────────────────────
console.log(`\n=== Broadcasting to Bitcoin testnet ===`);
try {
  const resp = await fetch('https://mempool.space/testnet/api/tx', {
    method: 'POST',
    headers: { 'Content-Type': 'text/plain' },
    body: rawTxHex,
  });
  const text = await resp.text();
  if (resp.ok) {
    const broadcastTxid = text.replace(/"/g, '').trim();
    console.log(`  ✅ BROADCAST SUCCESS!`);
    console.log(`  txid: ${broadcastTxid}`);
    console.log(`  Explorer: https://mempool.space/testnet/tx/${broadcastTxid}`);

    // Wait for confirmation
    console.log(`\n  Waiting for confirmation...`);
    let confirmed = false;
    let blockHeight = null;
    for (let i = 0; i < 120; i++) {
      await new Promise(r => setTimeout(r, 30000));
      try {
        const statusResp = await fetch(`https://mempool.space/testnet/api/tx/${broadcastTxid}`);
        const statusData = await statusResp.json();
        if (statusData.status?.confirmed) {
          confirmed = true;
          blockHeight = statusData.status.block_height;
          console.log(`  ✅ CONFIRMED at block ${blockHeight}!`);
          break;
        }
      } catch {}
      process.stdout.write(`\r  Waiting... (${(i+1)*30}s)`);
    }

    // Save results
    const results = {
      step: 'preimage-reveal-spend',
      status: 'broadcast_success',
      confirmed,
      blockHeight,
      fundingTxid,
      fundingVout,
      fundingAmount,
      spendTxid: broadcastTxid,
      sendAmount,
      fee: feeSats,
      vaultAddress: vault.vaultAddress,
      lenderAddress: vault.lenderAddress,
      committedAnchorBH: vault.committedAnchorBH,
      payloadHex: vault.payloadHex,
      payloadLength: vault.payloadLength,
      releaseScript: vault.releaseScript,
      releaseControlBlock: vault.releaseControlBlock,
      explorerUrl: `https://mempool.space/testnet/tx/${broadcastTxid}`,
      witness: {
        payload: `${payload.length} bytes`,
        script: `${releaseScript.length} bytes`,
        controlBlock: `${controlBlock.length} bytes`,
      },
      timestamp: new Date().toISOString(),
      description: 'REAL Bitcoin testnet transaction spending a TRION Coherence Vault UTXO via the PREIMAGE-REVEAL script path. The 80-byte HashDNA payload is the SOLE authorization — no signature, no committee, no multisig. This is the novel cryptographic primitive: the Deterministic Behavioral Preimage.',
    };
    fs.writeFileSync(
      '/home/z/my-project/trion-core/proofs/btcp-zero-bridge/stacks/btc-testnet-preimage-results.json',
      JSON.stringify(results, null, 2)
    );
    console.log(`\n  Results saved!`);
  } else {
    console.error(`  ❌ BROADCAST FAILED: ${resp.status} ${text}`);
    fs.writeFileSync('/tmp/preimage-tx-hex.txt', rawTxHex);
    console.log(`  Raw tx saved to /tmp/preimage-tx-hex.txt`);
  }
} catch (e) {
  console.error(`  ❌ Broadcast error: ${e.message}`);
  fs.writeFileSync('/tmp/preimage-tx-hex.txt', rawTxHex);
}
