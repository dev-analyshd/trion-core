import { ECPairFactory } from 'ecpair';
import * as ecc from 'tiny-secp256k1';
import * as bitcoin from 'bitcoinjs-lib';
bitcoin.initEccLib(ecc);
import * as fs from 'fs';

const ECPair = ECPairFactory(ecc);
const network = bitcoin.networks.testnet;
const vault = JSON.parse(fs.readFileSync('/tmp/vault-state-live.json', 'utf-8'));
const borrower = ECPair.fromWIF(vault.borrowerWif, network);
const refundScript = Buffer.from(vault.refundScript.split(',').map(n => parseInt(n)));

// Build the same PSBT
const psbt = new bitcoin.Psbt({ network });
psbt.addInput({
  hash: '688222635d1c86cae125ba4cf33b660b4d686e11ef15107a3547f7e724ab15d2',
  index: 0,
  witnessUtxo: {
    script: Buffer.from(vault.vaultOutputScript, 'hex'),
    value: BigInt(128310),
  },
  sequence: 6,
  tapLeafScript: [{
    leafVersion: 0xc0,
    script: refundScript,
    controlBlock: Buffer.from(vault.refundControlBlock, 'hex'),
  }],
});
const p2wpkh = bitcoin.payments.p2wpkh({ pubkey: borrower.publicKey, network });
psbt.addOutput({ address: p2wpkh.address, value: BigInt(127310) });

// Sign with a signer that captures the hash
const capturedHashes = [];
const signer = {
  publicKey: borrower.publicKey,
  signSchnorr: (hash) => {
    capturedHashes.push(Buffer.from(hash).toString('hex'));
    return Buffer.from(ecc.signSchnorr(hash, borrower.privateKey));
  },
};

psbt.signInput(0, signer);
console.log('PSBT-computed sighash:', capturedHashes[0]);

// Compute tapleaf hash
const tapleafHash = bitcoin.crypto.taggedHash('TapLeaf', Buffer.concat([
  Buffer.from([0xc0]),
  bitcoin.script.compile(refundScript),
]));

// Now compute the sighash manually using the CACHE tx
const cacheTx = psbt.__CACHE.__TX;
console.log('Cache tx inputs:', cacheTx.ins.length);
console.log('Cache tx input 0 sequence:', cacheTx.ins[0].sequence);

// Compute sighash using the CACHE tx
const cacheSighash = cacheTx.hashForWitnessV1(
  0,
  [Buffer.from(vault.vaultOutputScript, 'hex')],
  [BigInt(128310)],
  bitcoin.Transaction.SIGHASH_DEFAULT,
  tapleafHash,
);
console.log('Cache sighash:      ', Buffer.from(cacheSighash).toString('hex'));
console.log('Match PSBT:', capturedHashes[0] === Buffer.from(cacheSighash).toString('hex'));

// Now sign with the PSBT's sighash and broadcast
const sig = ecc.signSchnorr(Buffer.from(capturedHashes[0], 'hex'), borrower.privateKey);
console.log('\nSig:', Buffer.from(sig).toString('hex').slice(0, 40));

// Verify
const xOnly = Buffer.from(borrower.publicKey).slice(1, 33);
const valid = ecc.verifySchnorr(Buffer.from(capturedHashes[0], 'hex'), xOnly, sig);
console.log('Verify:', valid);

// Build the final tx manually (not from PSBT which requires finalization)
const finalTx = new bitcoin.Transaction();
finalTx.version = 2;
finalTx.addInput(
  Buffer.from('688222635d1c86cae125ba4cf33b660b4d686e11ef15107a3547f7e724ab15d2', 'hex').reverse(),
  0,
  6
);
finalTx.addOutput(p2wpkh.output, BigInt(127310));

import { witnessStackToScriptWitness } from 'bitcoinjs-lib/src/psbt/psbtutils';
const witness = [Buffer.from(sig), refundScript, Buffer.from(vault.refundControlBlock, 'hex')];
finalTx.setWitness(0, witness);

const rawTxHex = finalTx.toHex();
console.log('\ntxid:', finalTx.getId());
console.log('raw:', rawTxHex);

console.log('\nBroadcasting...');
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
    description: 'Real Bitcoin testnet transaction spending a TRION Coherence Vault UTXO via the CSV refund script path.',
  };
  fs.writeFileSync(
    '/home/z/my-project/trion-core/proofs/btcp-zero-bridge/stacks/btc-testnet-live-results.json',
    JSON.stringify(results, null, 2)
  );
  console.log('Results saved!');
} else {
  console.error('\nFAILED:', resp.status, text);
}
