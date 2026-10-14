/**
 * broadcast-refund-v3.mjs — Build + sign + broadcast the CSV refund spend.
 * Uses raw transaction construction with manual signature computation.
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
const csvBlocks = vault.csvBlocks;

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
const tweakResult = tweakKey(internalPubkey, merkleRoot);

console.log('=== CSV Refund (raw signing) ===');
console.log(`Merkle root: ${Buffer.from(merkleRoot).toString('hex')}`);
console.log(`Tweak parity: ${tweakResult.parity}`);

// Build PSBT
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

const borrowerP2wpkh = bitcoin.payments.p2wpkh({ pubkey: borrower.publicKey, network }).address;
const feeSats = 1000;
const sendAmount = fundingAmount - feeSats;

psbt.addOutput({
  address: borrowerP2wpkh,
  value: BigInt(sendAmount),
});

// For Taproot script-path spend, the signature is made with the TWEAKED key.
// The tweaked private key = original_private_key + hash(internal_pubkey || merkle_root) mod n
// The signature is a Schnorr signature over the BIP-341 sighash.

// bitcoinjs-lib v7's Psbt.signInput handles this automatically if the signer
// supports tweaking. ECPair supports `.tweak()`.

// Compute the tweak value
const tweakHash = bitcoin.crypto.taggedHash('TapTweak', Buffer.concat([
  internalPubkey,
  merkleRoot,
]));
console.log(`Tweak hash: ${tweakHash.toString('hex')}`);

// Create a tweaked signer
const tweakedSigner = borrower.tweak(tweakHash, { network });
if (tweakedSigner) {
  console.log(`Tweaked signer created`);
  try {
    psbt.signInput(0, tweakedSigner);
    console.log('Signed OK');
  } catch (e) {
    console.log(`Sign failed: ${e.message}`);
  }
} else {
  console.log('Tweak failed, trying direct sign');
  try {
    psbt.signInput(0, borrower);
    console.log('Direct sign OK');
  } catch (e) {
    console.log(`Direct sign failed: ${e.message}`);
  }
}

// Check if we have a signature
const input = psbt.data.inputs[0];
console.log(`tapScriptSigs: ${input.tapScriptSigs?.length || 0}`);

if (input.tapScriptSigs && input.tapScriptSigs.length > 0) {
  // We have a signature — finalize manually
  const sig = input.tapScriptSigs[0].signature;
  console.log(`Signature: ${sig.toString('hex').slice(0, 40)}...`);

  const witness = [sig, refundScript, controlBlock];
  psbt.finalizeInput(0, () => ({
    finalScriptWitness: witnessStackToScriptWitness(witness),
  }));
  console.log('Finalized OK');

  const signedTx = psbt.extractTransaction();
  const rawTxHex = signedTx.toHex();
  const txid = signedTx.getId();
  console.log(`txid: ${txid}`);
  console.log(`raw hex: ${rawTxHex.slice(0, 80)}...`);

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
    console.log(`BROADCAST SUCCESS!`);
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
    console.error(`FAILED: ${resp.status} ${text}`);
    fs.writeFileSync('/tmp/refund-tx-hex.txt', rawTxHex);
  }
} else {
  console.log('No signature produced — cannot finalize');
  console.log('Trying alternative approach...');

  // Alternative: compute the signature manually using the BIP-341 sighash
  // This is the most reliable approach for Taproot script-path spending

  // The BIP-341 sighash for script-path spend includes:
  // - Transaction data
  // - The script being spent
  // - The control block (which contains the Merkle path)

  // Get the raw transaction for sighash computation
  // We need to build the transaction without extracting (it's not finalized)
  // Use the PSBT's internal transaction hash computation

  // For Taproot script-path spend, the sighash is BIP-341 compliant
  // hashForWitnessV1 computes this correctly
  // BUT we need to pass the leaf hash for script-path spends

  // Compute the tapleaf hash
  const tapleafHash = bitcoin.crypto.taggedHash('TapLeaf', Buffer.concat([
    Buffer.from([0xc0]), // leaf version
    bitcoin.script.compile(refundScript),
  ]));
  console.log(`Tapleaf hash: ${Buffer.from(tapleafHash).toString('hex')}`);

  // Compute the BIP-341 sighash for script-path spend
  // hashForWitnessV1(inputIndex, prevoutScripts, prevoutValues, hashType, leafHash)
  const sighash = psbt.data.inputs[0].witnessUtxo
    ? bitcoin.Transaction.fromBuffer(psbt.data.globalMap.unsignedTx.toBuffer()).hashForWitnessV1(
        0,
        [Buffer.from(vault.vaultOutputScript, 'hex')],
        [BigInt(fundingAmount)],
        bitcoin.Transaction.SIGHASH_DEFAULT,
        tapleafHash, // leaf hash for script-path spend
        0xc0, // leaf version
      )
    : null;

  if (!sighash) {
    // Fallback: compute manually
    console.log('Manual sighash computation...');
    // Build a temp transaction for sighash
    const unsignedTx = new bitcoin.Transaction();
    unsignedTx.version = 2;
    unsignedTx.addInput(Buffer.from(fundingTxid, 'hex').reverse(), fundingVout, csvBlocks);
    unsignedTx.addOutput(bitcoin.address.toOutputScript(borrowerP2wpkh, network), BigInt(sendAmount));

    const sighash2 = unsignedTx.hashForWitnessV1(
      0,
      [Buffer.from(vault.vaultOutputScript, 'hex')],
      [BigInt(fundingAmount)],
      bitcoin.Transaction.SIGHASH_DEFAULT,
      tapleafHash,
      0xc0,
    );
    console.log(`Sighash (manual): ${Buffer.from(sighash2).toString('hex')}`);

    // Compute the tweaked private key
    const tweakedPrivKey = ecc.privateAdd(borrower.privateKey, tweakHash);
    console.log(`Tweaked privkey: ${Buffer.from(tweakedPrivKey).toString('hex').slice(0, 20)}...`);

    // Sign with Schnorr
    const sig = ecc.signSchnorr(sighash2, tweakedPrivKey);
    console.log(`Schnorr sig: ${Buffer.from(sig).toString('hex').slice(0, 40)}... (${sig.length} bytes)`);

    // Add SIGHASH_DEFAULT byte
    const sigWithHashType = Buffer.concat([Buffer.from(sig), Buffer.from([0x00])]);
    console.log(`Final sig: ${sigWithHashType.toString('hex').slice(0, 40)}... (${sigWithHashType.length} bytes)`);

    const witness = [sigWithHashType, refundScript, controlBlock];
    psbt.finalizeInput(0, () => ({
      finalScriptWitness: witnessStackToScriptWitness(witness),
    }));

    const signedTx = psbt.extractTransaction();
    const rawTxHex = signedTx.toHex();
    const txid = signedTx.getId();
    console.log(`txid: ${txid}`);
    console.log(`raw hex: ${rawTxHex}`);
    console.log(`length: ${rawTxHex.length / 2} bytes`);

    console.log('Broadcasting...');
    const resp = await fetch('https://mempool.space/testnet/api/tx', {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain' },
      body: rawTxHex,
    });
    const text = await resp.text();
    if (resp.ok) {
      const broadcastTxid = text.replace(/"/g, '').trim();
      console.log(`BROADCAST SUCCESS!`);
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
      console.error(`FAILED: ${resp.status} ${text}`);
      fs.writeFileSync('/tmp/refund-tx-hex.txt', rawTxHex);
    }
  } else {
    console.log('Sighash computation failed - no signature produced');
    console.log('tiny-secp256k1 exports:', Object.keys(ecc));
  }
}
