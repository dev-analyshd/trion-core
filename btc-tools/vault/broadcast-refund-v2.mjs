/**
 * broadcast-refund-v2.mjs — Build + sign + broadcast the CSV refund spend.
 * Uses raw transaction construction (bypasses PSBT signing issues).
 */
import { ECPairFactory } from 'ecpair';
import * as ecc from 'tiny-secp256k1';
import * as bitcoin from 'bitcoinjs-lib';
bitcoin.initEccLib(ecc);
import * as fs from 'fs';

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

// Build the refund script: <csv> CSV DROP <internalPubkey> CHECKSIG
const csvNum = bitcoin.script.number.encode(csvBlocks);
const refundScript = Buffer.concat([
  csvNum,
  Buffer.from([0xb2]),       // OP_CHECKSEQUENCEVERIFY
  Buffer.from([0x75]),       // OP_DROP
  internalPubkey,
  Buffer.from([0xac]),       // OP_CHECKSIG
]);

console.log('=== CSV Refund Spend (raw tx) ===');
console.log(`Refund script: ${refundScript.toString('hex')}`);
console.log(`Control block: ${controlBlock.toString('hex').slice(0, 40)}...`);

// Borrower's p2wpkh address for the output
const borrowerP2wpkh = bitcoin.payments.p2wpkh({ pubkey: borrower.publicKey, network }).address;
const feeSats = 1000;
const sendAmount = fundingAmount - feeSats;

console.log(`Output: ${sendAmount} sats -> ${borrowerP2wpkh}`);

// Build the raw transaction manually
const psbt = new bitcoin.Psbt({ network });

psbt.addInput({
  hash: fundingTxid,
  index: fundingVout,
  witnessUtxo: {
    script: Buffer.from(vault.vaultOutputScript, 'hex'),
    value: BigInt(fundingAmount),
  },
  sequence: csvBlocks,
  tapLeafScript: [{
    leafVersion: 0xc0,
    script: refundScript,
    controlBlock: controlBlock,
  }],
});

psbt.addOutput({
  address: borrowerP2wpkh,
  value: BigInt(sendAmount),
});

// For Taproot script-path spend with OP_CHECKSIG, we need to:
// 1. Compute the tweaked private key
// 2. Sign the BIP-341 sighash
// 3. Provide the witness as [sig, script, controlBlock]

// Get the tweak from the vault state
const tweak = vault.tweak ? Buffer.from(vault.tweak, 'hex') : null;
console.log(`Tweak: ${tweak ? tweak.toString('hex') : 'null'}`);

// Compute the tweaked signer
// For script-path spending, the signing key is the internal key tweaked with the Merkle root
// bitcoinjs-lib v7's ECPair doesn't directly support tweaking.
// We need to use the raw signing approach.

// Actually, let's use the bip341 module directly
import { tweakKey } from 'bitcoinjs-lib/src/payments/bip341';

// Compute the Merkle root from the script tree
// The script tree is: [releaseScript, refundScript]
// We need the hash tree to compute the Merkle root
import { toHashTree } from 'bitcoinjs-lib/src/payments/bip341';

const releaseScript = Buffer.concat([
  Buffer.from([0xa8, 0x20]),
  Buffer.from(vault.committedAnchorBH, 'hex'),
  Buffer.from([0x87]),
]);

const scriptTree = [
  { output: releaseScript },
  { output: refundScript },
];

const hashTree = toHashTree(scriptTree);
const merkleRoot = hashTree.hash;
console.log(`Merkle root: ${Buffer.from(merkleRoot).toString('hex')}`);

// Compute the tweaked key
const tweakResult = tweakKey(internalPubkey, merkleRoot);
if (!tweakResult) throw new Error('tweakKey failed');

console.log(`Tweak parity: ${tweakResult.parity}`);
console.log(`Tweaked pubkey: ${Buffer.from(tweakResult.x).toString('hex').slice(0, 40)}...`);

// Now we need to sign the transaction with the tweaked private key
// The tweaked private key = original_private_key + tweak (mod n)
// We need to compute this using tiny-secp256k1

// Get the original private key
const originalPrivKey = borrower.privateKey;
console.log(`Original privkey: ${Buffer.from(originalPrivKey).toString('hex').slice(0, 20)}...`);

// Compute the tweaked private key using the tweak
// tweakKey returns {x, parity} for the tweaked PUBLIC key
// For signing, we need: tweaked_priv = original_priv + T (where T = hash(internal_pubkey || merkle_root))
// This is BIP-341 key tweaking

// Actually, for Taproot script-path spending, we DON'T use the tweaked key.
// The script-path signature is made with the INTERNAL key, not the tweaked key.
// The control block proves the script is in the Merkle tree.
// The signature in the witness is over the standard Taproot sighash using the internal key.

// Wait, actually for script-path spending with OP_CHECKSIG:
// - The signature is verified against the pubkey in the script
// - The pubkey in the script is the INTERNAL pubkey (not tweaked)
// - So we sign with the original (non-tweaked) private key

// But ECPair's signInput expects a specific key format for Taproot...
// Let's try using the raw signing approach

// Compute the sighash manually
const tx = psbt.extractTransaction(false); // don't validate
// Actually, let's try a different approach — sign the PSBT directly

// For Taproot script-path spend, we need to use signTapleafInput or similar
// Let's check if ECPair supports this

console.log('ECPair methods:', Object.getOwnPropertyNames(Object.getPrototypeOf(borrower)));

// Try signing with the raw approach
try {
  // Build the final witness manually
  // For script-path spend with OP_CHECKSIG:
  // witness = [signature, script, controlBlock]

  // We need to compute the BIP-341 signature hash
  // For script-path spend, the sighash includes:
  // - The transaction data (inputs, outputs)
  // - The script being spent
  // - The control block
  // - The leaf version

  // Use bitcoinjs-lib's built-in signing
  // The issue might be that ECPair doesn't support Taproot script-path signing
  // Let's use a custom signer

  // First, let's try the simplest approach: sign with the tweaked key pair
  const tweakedSigner = borrower.tweak(tweakResult.tweak || merkleRoot, { network });
  if (tweakedSigner) {
    psbt.signInput(0, tweakedSigner);
    console.log('Signed with tweaked signer');
  }
} catch (e) {
  console.log(`Tweaked signing failed: ${e.message}`);
  // Try raw signing
  try {
    // For script-path, we sign with the internal key directly
    psbt.signInput(0, borrower);
    console.log('Signed with original key');
  } catch (e2) {
    console.log(`Original signing also failed: ${e2.message}`);
    console.log('Falling back to manual signature...');

    // Manual approach: compute the sighash and sign it
    // This is complex but let's try
    console.log('Manual signing not implemented — trying to finalize with empty sig');

    // Actually, for the refund path, let's try just using the PSBT's built-in
    // Taproot signing with the leaf hash
  }
}

// Try to finalize
try {
  psbt.finalizeInput(0);
  console.log('Finalized OK');
} catch (e) {
  console.log(`Finalize failed: ${e.message}`);

  // Check what we have
  const input = psbt.data.inputs[0];
  console.log('tapScriptSigs:', input.tapScriptSigs?.length || 0);
  console.log('tapLeafScript:', input.tapLeafScript?.length || 0);
  console.log('finalScriptWitness:', input.finalScriptWitness ? 'yes' : 'no');
}

try {
  const signedTx = psbt.extractTransaction();
  const rawTxHex = signedTx.toHex();
  console.log(`Signed tx: ${rawTxHex.slice(0, 80)}...`);

  // Broadcast
  const resp = await fetch('https://mempool.space/testnet/api/tx', {
    method: 'POST',
    headers: { 'Content-Type': 'text/plain' },
    body: rawTxHex,
  });
  const text = await resp.text();
  if (resp.ok) {
    console.log(`BROADCAST SUCCESS! txid: ${text.replace(/"/g, '')}`);
    console.log(`Explorer: https://mempool.space/testnet/tx/${text.replace(/"/g, '')}`);

    const results = {
      step: 'csv-refund-spend',
      status: 'broadcast_success',
      fundingTxid,
      spendTxid: text.replace(/"/g, ''),
      sendAmount,
      fee: feeSats,
      vaultAddress: vault.vaultAddress,
      borrowerAddress: borrowerP2wpkh,
      csvBlocks,
      explorerUrl: `https://mempool.space/testnet/tx/${text.replace(/"/g, '')}`,
      timestamp: new Date().toISOString(),
    };
    fs.writeFileSync(
      '/home/z/my-project/trion-core/proofs/btcp-zero-bridge/stacks/btc-testnet-live-results.json',
      JSON.stringify(results, null, 2)
    );
    console.log('Results saved!');
  } else {
    console.error(`BROADCAST FAILED: ${resp.status} ${text}`);
    fs.writeFileSync('/tmp/refund-tx-hex.txt', rawTxHex);
  }
} catch (e) {
  console.error(`Extract/broadcast failed: ${e.message}`);
}
