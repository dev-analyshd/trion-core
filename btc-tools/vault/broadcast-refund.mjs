/**
 * broadcast-refund.mjs — Build + sign + broadcast the CSV refund spend
 * transaction on Bitcoin testnet.
 *
 * This spends the funded Coherence Vault UTXO via the CSV refund script path.
 * The borrower signs after the timelock expires. This path has a standard
 * signature witness (not a large preimage), so it's standard.
 *
 * BUT: the CSV is set to 6 blocks, and the funding tx was confirmed at block
 * 5158914. We need the current block to be >= 5158914 + 6 = 5158920.
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
console.log('=== Coherence Vault CSV Refund Spend ===');
console.log(`Vault address: ${vault.vaultAddress}`);
console.log(`Borrower WIF: ${vault.borrowerWif}`);
console.log('');

// ─── Funding UTXO ──────────────────────────────────────────────────────────
const fundingTxid = '688222635d1c86cae125ba4cf33b660b4d686e11ef15107a3547f7e724ab15d2';
const fundingVout = 0;
const fundingAmount = 128310;
const csvBlocks = vault.csvBlocks; // 6

// ─── Load borrower key ─────────────────────────────────────────────────────
const borrower = ECPair.fromWIF(vault.borrowerWif, network);
console.log(`Borrower pubkey: ${Buffer.from(borrower.publicKey).toString('hex')}`);

// ─── Build the refund script ───────────────────────────────────────────────
const internalPubkey = Buffer.from(vault.internalPubkey, 'hex');
const refundScript = Buffer.from(vault.refundScript.split(',').map(b => parseInt(b)), 'hex');

// Actually, the refundScript in vault-state is stored as comma-separated bytes.
// Let me rebuild it properly.
// refundScript = <csv_blocks> OP_CHECKSEQUENCEVERIFY OP_DROP <pubkey> OP_CHECKSIG
const csvNum = bitcoin.script.number.encode(csvBlocks);
const refundScriptHex = Buffer.concat([
  csvNum,                    // CSV blocks (e.g., 0x06 for 6)
  Buffer.from([0xb2]),       // OP_CHECKSEQUENCEVERIFY
  Buffer.from([0x75]),       // OP_DROP
  internalPubkey,            // 32-byte x-only pubkey
  Buffer.from([0xac]),       // OP_CHECKSIG
]);
console.log(`Refund script hex: ${refundScriptHex.toString('hex')}`);
console.log(`Refund script length: ${refundScriptHex.length} bytes`);
console.log('');

// ─── Get the control block for the refund path ─────────────────────────────
const controlBlock = Buffer.from(vault.refundControlBlock, 'hex');
console.log(`Control block: ${controlBlock.toString('hex').slice(0, 40)}...`);
console.log('');

// ─── Build the PSBT ────────────────────────────────────────────────────────
const psbt = new bitcoin.Psbt({ network });

psbt.addInput({
  hash: fundingTxid,
  index: fundingVout,
  witnessUtxo: {
    script: Buffer.from(vault.vaultOutputScript, 'hex'),
    value: BigInt(fundingAmount),
  },
  sequence: csvBlocks, // BIP-68 relative timelock
  tapLeafScript: [{
    leafVersion: 0xc0,
    script: refundScriptHex,
    controlBlock: controlBlock,
  }],
});

// Output: send back to borrower (minus fee)
const feeSats = 1000;
const sendAmount = BigInt(fundingAmount - feeSats);
const borrowerP2wpkh = bitcoin.payments.p2wpkh({ pubkey: borrower.publicKey, network }).address;
psbt.addOutput({
  address: borrowerP2wpkh,
  value: sendAmount,
});

console.log('=== Refund Transaction ===');
console.log(`  Input: ${fundingAmount} sats (vault UTXO)`);
console.log(`  Output: ${fundingAmount - feeSats} sats -> ${borrowerP2wpkh} (borrower)`);
console.log(`  Fee: ${feeSats} sats`);
console.log(`  CSV: ${csvBlocks} blocks (relative timelock)`);
console.log('');

// ─── Sign with the borrower's key (script path) ────────────────────────────
// For Taproot script path with OP_CHECKSIG, we need to sign with the
// tweaked key pair. The tweak is derived from the internal pubkey + the
// Merkle root of the script tree.
const tweak = vault.tweak ? Buffer.from(vault.tweak, 'hex') : null;
console.log(`Tweak: ${tweak ? tweak.toString('hex').slice(0, 20) + '...' : 'null'}`);

// For script-path spending, we sign with the internal key + tweak
// bitcoinjs-lib v7 supports this via the tweaked signer
const tweakedSigner = tweak
  ? borrower.tweak(tweak, { network })
  : borrower;

try {
  psbt.signInput(0, tweakedSigner);
  console.log('Signature: OK');
} catch (e) {
  console.log(`Signing with tweaked signer failed: ${e.message}`);
  // Try without tweak
  try {
    psbt.signInput(0, borrower);
    console.log('Signature (no tweak): OK');
  } catch (e2) {
    console.log(`Signing without tweak also failed: ${e2.message}`);
  }
}

// ─── Finalize ───────────────────────────────────────────────────────────────
try {
  psbt.finalizeInput(0);
  console.log('Finalize: OK');
} catch (e) {
  console.log(`Finalize failed: ${e.message}`);
  // Try manual finalization
  const input = psbt.data.inputs[0];
  const leafScript = input.tapLeafScript[0];
  const sig = input.tapScriptSigs[0]?.signature;
  if (sig) {
    const witness = [sig, leafScript.script, leafScript.controlBlock];
    psbt.finalizeInput(0, () => ({
      finalScriptWitness: witnessStackToScriptWitness(witness),
    }));
    console.log('Manual finalize: OK');
  }
}

const signedTx = psbt.extractTransaction();
const rawTxHex = signedTx.toHex();
const spendTxid = signedTx.getId();

console.log('');
console.log('=== Signed Transaction ===');
console.log(`  txid: ${spendTxid}`);
console.log(`  raw hex: ${rawTxHex.slice(0, 80)}...`);
console.log(`  length: ${rawTxHex.length / 2} bytes`);
console.log('');

// ─── Broadcast ─────────────────────────────────────────────────────────────
console.log('=== Broadcasting to Bitcoin testnet ===');
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

    // Save results
    const results = {
      step: 'csv-refund-spend',
      status: 'broadcast_success',
      fundingTxid,
      fundingVout,
      fundingAmount,
      spendTxid: broadcastTxid,
      sendAmount: Number(sendAmount),
      fee: feeSats,
      vaultAddress: vault.vaultAddress,
      borrowerAddress: borrowerP2wpkh,
      csvBlocks,
      explorerUrl: `https://mempool.space/testnet/tx/${broadcastTxid}`,
      timestamp: new Date().toISOString(),
    };
    fs.writeFileSync(
      '/home/z/my-project/trion-core/proofs/btcp-zero-bridge/stacks/btc-testnet-live-results.json',
      JSON.stringify(results, null, 2)
    );
    console.log('Results saved!');
  } else {
    console.error(`  BROADCAST FAILED: ${resp.status} ${text}`);
    fs.writeFileSync('/tmp/refund-tx-hex.txt', rawTxHex);
    console.log(`  Raw tx saved to /tmp/refund-tx-hex.txt`);
  }
} catch (e) {
  console.error(`  Broadcast error: ${e.message}`);
  fs.writeFileSync('/tmp/refund-tx-hex.txt', rawTxHex);
}
