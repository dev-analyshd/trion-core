/**
 * broadcast-refund-v4.mjs — Build + sign + broadcast CSV refund spend.
 * Bypasses PSBT entirely — builds the raw transaction manually.
 */
import { ECPairFactory } from 'ecpair';
import * as ecc from 'tiny-secp256k1';
import * as bitcoin from 'bitcoinjs-lib';
bitcoin.initEccLib(ecc);
import * as fs from 'fs';
import { toHashTree, tweakKey } from 'bitcoinjs-lib/src/payments/bip341';
import { witnessStackToScriptWitness } from 'bitcoinjs-lib/src/psbt/psbtutils';

const ECPair = ECPairFactory(ecc);
const network = bitcoin.networks.testnet;

const vault = JSON.parse(fs.readFileSync('/tmp/vault-state-live.json', 'utf-8'));

const fundingTxid = '688222635d1c86cae125ba4cf33b660b4d686e11ef15107a3547f7e724ab15d2';
const fundingVout = 0;
const fundingAmount = 128310;
const csvBlocks = vault.csvBlocks; // 6

const borrower = ECPair.fromWIF(vault.borrowerWif, network);
const internalPubkey = Buffer.from(vault.internalPubkey, 'hex');
const controlBlock = Buffer.from(vault.refundControlBlock, 'hex');

// Build scripts
const releaseScript = Buffer.concat([
  Buffer.from([0xa8, 0x20]),
  Buffer.from(vault.committedAnchorBH, 'hex'),
  Buffer.from([0x87]),
]);
const csvNum = bitcoin.script.number.encode(csvBlocks);
const refundScript = Buffer.concat([
  csvNum, Buffer.from([0xb2, 0x75]), internalPubkey, Buffer.from([0xac]),
]);

const scriptTree = [{ output: releaseScript }, { output: refundScript }];
const hashTree = toHashTree(scriptTree);
const merkleRoot = hashTree.hash;

// Compute the tweak
const tweakHash = bitcoin.crypto.taggedHash('TapTweak', Buffer.concat([
  internalPubkey,
  merkleRoot,
]));

// Compute the tweaked private key
const tweakedPrivKey = ecc.privateAdd(borrower.privateKey, tweakHash);
console.log('=== CSV Refund (raw tx) ===');
console.log(`Tweaked privkey: ${Buffer.from(tweakedPrivKey).toString('hex').slice(0, 20)}...`);

// Build the raw transaction
const tx = new bitcoin.Transaction();
tx.version = 2;

// Add input
const inputHash = Buffer.from(fundingTxid, 'hex').reverse();
tx.addInput(inputHash, fundingVout, csvBlocks); // sequence = csvBlocks for BIP-68

// Add output (send to borrower's p2wpkh)
const borrowerP2wpkh = bitcoin.payments.p2wpkh({ pubkey: borrower.publicKey, network });
const feeSats = 1000;
const sendAmount = fundingAmount - feeSats;
const outputScript = borrowerP2wpkh.output;
tx.addOutput(outputScript, BigInt(sendAmount));

console.log(`Input: ${fundingTxid}:${fundingVout} (${fundingAmount} sats)`);
console.log(`Output: ${sendAmount} sats -> ${borrowerP2wpkh.address}`);
console.log(`Fee: ${feeSats} sats`);
console.log(`CSV: ${csvBlocks} blocks`);

// Compute the tapleaf hash
const tapleafHash = bitcoin.crypto.taggedHash('TapLeaf', Buffer.concat([
  Buffer.from([0xc0]),
  bitcoin.script.compile(refundScript),
]));
console.log(`Tapleaf hash: ${Buffer.from(tapleafHash).toString('hex')}`);

// Compute the BIP-341 sighash for script-path spend
const prevoutScripts = [Buffer.from(vault.vaultOutputScript, 'hex')];
const prevoutValues = [BigInt(fundingAmount)];

const sighash = tx.hashForWitnessV1(
  0,
  prevoutScripts,
  prevoutValues,
  bitcoin.Transaction.SIGHASH_DEFAULT,
);
console.log(`Sighash: ${Buffer.from(sighash).toString('hex')}`);

// Sign with Schnorr using the tweaked private key
const sig = ecc.signSchnorr(sighash, tweakedPrivKey);
console.log(`Schnorr sig: ${Buffer.from(sig).toString('hex').slice(0, 40)}... (${sig.length} bytes)`);

// Build the witness: [sig+SIGHASH_DEFAULT, script, controlBlock]
const sigWithHashType = Buffer.concat([Buffer.from(sig), Buffer.from([0x00])]);
const witness = [sigWithHashType, refundScript, controlBlock];
const witnessSerialized = witnessStackToScriptWitness(witness);
// Initialize the witness array for this input
tx.ins[0].witness = [];
tx.setWitness(0, witness);

const rawTxHex = tx.toHex();
const txid = tx.getId();
console.log(`\ntxid: ${txid}`);
console.log(`raw hex: ${rawTxHex}`);
console.log(`length: ${rawTxHex.length / 2} bytes`);

// Broadcast
console.log('\nBroadcasting...');
const resp = await fetch('https://mempool.space/testnet/api/tx', {
  method: 'POST',
  headers: { 'Content-Type': 'text/plain' },
  body: rawTxHex,
});
const text = await resp.text();
if (resp.ok) {
  const broadcastTxid = text.replace(/"/g, '').trim();
  console.log(`\nBROADCAST SUCCESS!`);
  console.log(`txid: ${broadcastTxid}`);
  console.log(`Explorer: https://mempool.space/testnet/tx/${broadcastTxid}`);

  const results = {
    step: 'csv-refund-spend',
    status: 'broadcast_success',
    fundingTxid,
    spendTxid: broadcastTxid,
    sendAmount,
    fee: feeSats,
    vaultAddress: vault.vaultAddress,
    borrowerAddress: borrowerP2wpkh.address,
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
  console.error(`\nBROADCAST FAILED: ${resp.status} ${text}`);
  fs.writeFileSync('/tmp/refund-tx-hex.txt', rawTxHex);
}
