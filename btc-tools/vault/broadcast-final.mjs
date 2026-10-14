import { ECPairFactory } from 'ecpair';
import * as ecc from 'tiny-secp256k1';
import * as bitcoin from 'bitcoinjs-lib';
bitcoin.initEccLib(ecc);
import { witnessStackToScriptWitness } from 'bitcoinjs-lib/src/psbt/psbtutils';
import * as fs from 'fs';

const ECPair = ECPairFactory(ecc);
const network = bitcoin.networks.testnet;
const vault = JSON.parse(fs.readFileSync('/tmp/vault-state-live.json', 'utf-8'));
const borrower = ECPair.fromWIF(vault.borrowerWif, network);
const refundScript = Buffer.from(vault.refundScript.split(',').map(n => parseInt(n)));
const controlBlock = Buffer.from(vault.refundControlBlock, 'hex');

// Compute tapleaf hash
const tapleafHash = bitcoin.crypto.taggedHash('TapLeaf', Buffer.concat([
  Buffer.from([0xc0]),
  bitcoin.script.compile(refundScript),
]));

// Build the raw transaction
const tx = new bitcoin.Transaction();
tx.version = 2;
tx.addInput(
  Buffer.from('688222635d1c86cae125ba4cf33b660b4d686e11ef15107a3547f7e724ab15d2', 'hex').reverse(),
  0,
  6 // sequence = CSV blocks
);

const p2wpkh = bitcoin.payments.p2wpkh({ pubkey: borrower.publicKey, network });
tx.addOutput(p2wpkh.output, BigInt(127310));

// Compute sighash WITH leafHash (for script-path spend)
const sighash = tx.hashForWitnessV1(
  0,
  [Buffer.from(vault.vaultOutputScript, 'hex')],
  [BigInt(128310)],
  bitcoin.Transaction.SIGHASH_DEFAULT, // 0x00
  tapleafHash,
);

console.log('Sighash:', Buffer.from(sighash).toString('hex'));

// Sign with original (non-tweaked) private key
const sig = ecc.signSchnorr(sighash, borrower.privateKey);
console.log('Sig:', Buffer.from(sig).toString('hex').slice(0, 40));

// Verify locally
const xOnlyPubkey = Buffer.from(borrower.publicKey).slice(1, 33);
const valid = ecc.verifySchnorr(sighash, xOnlyPubkey, sig);
console.log('Local verify:', valid);

// For SIGHASH_DEFAULT (0x00), the witness signature is 64 bytes (no hash type byte)
const witness = [Buffer.from(sig), refundScript, controlBlock];
tx.setWitness(0, witness);

const rawTxHex = tx.toHex();
const txid = tx.getId();
console.log('txid:', txid);
console.log('raw:', rawTxHex);

// Broadcast
console.log('Broadcasting...');
const resp = await fetch('https://mempool.space/testnet/api/tx', {
  method: 'POST',
  headers: { 'Content-Type': 'text/plain' },
  body: rawTxHex,
});
const text = await resp.text();
if (resp.ok) {
  const broadcastTxid = text.replace(/"/g, '').trim();
  console.log('\nBROADCAST SUCCESS!');
  console.log('txid:', broadcastTxid);
  console.log('Explorer: https://mempool.space/testnet/tx/' + broadcastTxid);

  const results = {
    step: 'csv-refund-spend',
    status: 'broadcast_success',
    fundingTxid: '688222635d1c86cae125ba4cf33b660b4d686e11ef15107a3547f7e724ab15d2',
    spendTxid: broadcastTxid,
    sendAmount: 127310,
    fee: 1000,
    vaultAddress: vault.vaultAddress,
    borrowerAddress: p2wpkh.address,
    csvBlocks: 6,
    explorerUrl: 'https://mempool.space/testnet/tx/' + broadcastTxid,
    timestamp: new Date().toISOString(),
    description: 'Real Bitcoin testnet transaction spending a TRION Coherence Vault UTXO via the CSV refund script path. The borrower reclaims their BTC after the relative timelock expires.',
  };
  fs.writeFileSync(
    '/home/z/my-project/trion-core/proofs/btcp-zero-bridge/stacks/btc-testnet-live-results.json',
    JSON.stringify(results, null, 2)
  );
  console.log('Results saved!');
} else {
  console.error('\nFAILED:', resp.status, text);
}
