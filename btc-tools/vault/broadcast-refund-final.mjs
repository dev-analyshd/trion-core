/**
 * broadcast-refund-final.mjs — CSV refund spend with EXACT original scripts.
 */
import { ECPairFactory } from 'ecpair';
import * as ecc from 'tiny-secp256k1';
import * as bitcoin from 'bitcoinjs-lib';
bitcoin.initEccLib(ecc);
import { toHashTree, tweakKey } from 'bitcoinjs-lib/src/payments/bip341';
import { witnessStackToScriptWitness } from 'bitcoinjs-lib/src/psbt/psbtutils';
import * as fs from 'fs';

const ECPair = ECPairFactory(ecc);
const network = bitcoin.networks.testnet;

const vault = JSON.parse(fs.readFileSync('/tmp/vault-state-live.json', 'utf-8'));

const fundingTxid = '688222635d1c86cae125ba4cf33b660b4d686e11ef15107a3547f7e724ab15d2';
const fundingVout = 0;
const fundingAmount = 128310;
const csvBlocks = vault.csvBlocks;

const borrower = ECPair.fromWIF(vault.borrowerWif, network);
const internalPubkey = Buffer.from(vault.internalPubkey, 'hex');

// Use the EXACT original scripts (stored as comma-separated decimal)
const releaseScript = Buffer.from(vault.releaseScript.split(',').map(n => parseInt(n)));
const refundScript = Buffer.from(vault.refundScript.split(',').map(n => parseInt(n)));
const controlBlock = Buffer.from(vault.refundControlBlock, 'hex');

// Rebuild the tree with EXACT original scripts
const tree = [{ output: releaseScript }, { output: refundScript }];
const p2tr = bitcoin.payments.p2tr({ internalPubkey, scriptTree: tree, network });

console.log('=== CSV Refund (exact original scripts) ===');
console.log(`Vault address: ${p2tr.address} (match: ${p2tr.address === vault.vaultAddress})`);
console.log(`Refund script: ${refundScript.toString('hex')}`);
console.log(`Control block: ${controlBlock.toString('hex').slice(0, 40)}...`);
console.log();

// Compute Merkle root and tweak
const hashTree = toHashTree(tree);
const merkleRoot = hashTree.hash;
const tweakHash = bitcoin.crypto.taggedHash('TapTweak', Buffer.concat([internalPubkey, merkleRoot]));
const tweakedPrivKey = ecc.privateAdd(borrower.privateKey, tweakHash);
console.log(`Merkle root: ${Buffer.from(merkleRoot).toString('hex')}`);
console.log(`Tweaked privkey: ${Buffer.from(tweakedPrivKey).toString('hex').slice(0, 20)}...`);

// Build raw transaction
const tx = new bitcoin.Transaction();
tx.version = 2;
const inputHash = Buffer.from(fundingTxid, 'hex').reverse();
tx.addInput(inputHash, fundingVout, csvBlocks);

const borrowerP2wpkh = bitcoin.payments.p2wpkh({ pubkey: borrower.publicKey, network });
const feeSats = 1000;
const sendAmount = fundingAmount - feeSats;
tx.addOutput(borrowerP2wpkh.output, BigInt(sendAmount));

console.log(`Input: ${fundingTxid}:0 (${fundingAmount} sats)`);
console.log(`Output: ${sendAmount} sats -> ${borrowerP2wpkh.address}`);
console.log(`Fee: ${feeSats} sats, CSV: ${csvBlocks} blocks`);

// Compute tapleaf hash
const tapleafHash = bitcoin.crypto.taggedHash('TapLeaf', Buffer.concat([
  Buffer.from([0xc0]),
  bitcoin.script.compile(refundScript),
]));
console.log(`Tapleaf hash: ${Buffer.from(tapleafHash).toString('hex')}`);

// Compute BIP-341 sighash — for script-path spend, MUST pass leafHash
// The leafHash makes the sighash specific to this script leaf
const sighash = tx.hashForWitnessV1(
  0,
  [Buffer.from(vault.vaultOutputScript, 'hex')],
  [BigInt(fundingAmount)],
  bitcoin.Transaction.SIGHASH_ALL,
  tapleafHash, // leaf hash — REQUIRED for script-path spend
);
console.log(`Sighash: ${Buffer.from(sighash).toString('hex')}`);

// For Taproot SCRIPT-PATH spend with OP_CHECKSIG:
// The signature is verified against the TWEAKED internal pubkey, not the raw one.
// BIP-342: "The key for OP_CHECKSIG is the x-only pubkey top stack item.
// The key is NOT the internal key; it is whatever is in the script."
// Since we put the internal pubkey in the script, the verification
// uses BIP-340 verification against that x-only pubkey.
//
// BUT: the signing key for script-path is the TWEAKED key!
// Because the output was locked to the tweaked key (via Taproot),
// and script-path spends prove inclusion in the Merkle tree,
// the signature is made with the tweaked key (original + tweak).
//
// Actually no. BIP-342 says: OP_CHECKSIG in Taproot context
// uses BIP-340 verification against the pubkey on the stack.
// The pubkey on the stack is the internal pubkey.
// So we sign with the internal private key.
//
// BUT: the issue might be that we need to use SIGHASH_DEFAULT (0x00)
// not SIGHASH_ALL (0x01) for Taproot.
// Let me try SIGHASH_DEFAULT with the leafHash.
console.log('Trying SIGHASH_DEFAULT with leafHash');
const sighashDefault = tx.hashForWitnessV1(
  0,
  [Buffer.from(vault.vaultOutputScript, 'hex')],
  [BigInt(fundingAmount)],
  bitcoin.Transaction.SIGHASH_DEFAULT, // 0x00
  tapleafHash,
);
const sigDefault = ecc.signSchnorr(sighashDefault, borrower.privateKey);
console.log(`Sig with SIGHASH_DEFAULT: ${Buffer.from(sigDefault).toString('hex').slice(0, 40)}...`);

// Also try with tweaked key + SIGHASH_DEFAULT
const sigTweakedDefault = ecc.signSchnorr(sighashDefault, tweakedPrivKey);
console.log(`Sig with tweaked key: ${Buffer.from(sigTweakedDefault).toString('hex').slice(0, 40)}...`);

// Verify which signature is valid against the internal pubkey
const validOrig = ecc.verifySchnorr(sighashDefault, internalPubkey, sigDefault);
const validTweaked = ecc.verifySchnorr(sighashDefault, internalPubkey, sigTweakedDefault);
console.log(`Original key valid: ${validOrig}`);
console.log(`Tweaked key valid: ${validTweaked}`);

// Use whichever is valid
let sig, hashType;
if (validOrig) {
  sig = sigDefault;
  hashType = bitcoin.Transaction.SIGHASH_DEFAULT; // 0x00
  console.log('Using original key + SIGHASH_DEFAULT');
} else if (validTweaked) {
  sig = sigTweakedDefault;
  hashType = bitcoin.Transaction.SIGHASH_DEFAULT; // 0x00
  console.log('Using tweaked key + SIGHASH_DEFAULT');
} else {
  // Try SIGHASH_ALL with both keys
  const sighashAll = tx.hashForWitnessV1(
    0,
    [Buffer.from(vault.vaultOutputScript, 'hex')],
    [BigInt(fundingAmount)],
    bitcoin.Transaction.SIGHASH_ALL, // 0x01
    tapleafHash,
  );
  const sigOrigAll = ecc.signSchnorr(sighashAll, borrower.privateKey);
  const sigTweakedAll = ecc.signSchnorr(sighashAll, tweakedPrivKey);
  const validOrigAll = ecc.verifySchnorr(sighashAll, internalPubkey, sigOrigAll);
  const validTweakedAll = ecc.verifySchnorr(sighashAll, internalPubkey, sigTweakedAll);
  console.log(`SIGHASH_ALL - original valid: ${validOrigAll}, tweaked valid: ${validTweakedAll}`);

  if (validOrigAll) {
    sig = sigOrigAll;
    hashType = bitcoin.Transaction.SIGHASH_ALL;
    console.log('Using original key + SIGHASH_ALL');
  } else if (validTweakedAll) {
    sig = sigTweakedAll;
    hashType = bitcoin.Transaction.SIGHASH_ALL;
    console.log('Using tweaked key + SIGHASH_ALL');
  } else {
    console.error('No valid signature found!');
    process.exit(1);
  }
}

console.log(`Schnorr sig: ${Buffer.from(sig).toString('hex').slice(0, 40)}... (${sig.length} bytes)`);

// Build witness: [sig(+hashType), refundScript, controlBlock]
// For SIGHASH_DEFAULT (0x00): signature is 64 bytes, NO hash type byte appended
// For other types (0x01+): signature is 65 bytes (64 sig + 1 hash type)
let sigForWitness;
if (hashType === bitcoin.Transaction.SIGHASH_DEFAULT) {
  sigForWitness = Buffer.from(sig); // 64 bytes, no hash type byte
} else {
  sigForWitness = Buffer.concat([Buffer.from(sig), Buffer.from([hashType])]); // 65 bytes
}
console.log(`Witness sig: ${sigForWitness.length} bytes`);

const witness = [sigForWitness, refundScript, controlBlock];
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
    description: 'Real Bitcoin testnet transaction spending a TRION Coherence Vault UTXO via the CSV refund script path. The borrower reclaims their BTC after the relative timelock expires.',
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
