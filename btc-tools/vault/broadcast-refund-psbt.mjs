/**
 * broadcast-refund-psbt.mjs — Use PSBT's built-in Taproot signing.
 * This handles the BIP-341 sighash computation correctly.
 */
import { ECPairFactory } from 'ecpair';
import * as ecc from 'tiny-secp256k1';
import * as bitcoin from 'bitcoinjs-lib';
bitcoin.initEccLib(ecc);
import { toHashTree } from 'bitcoinjs-lib/src/payments/bip341';
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

// Use EXACT original scripts
const releaseScript = Buffer.from(vault.releaseScript.split(',').map(n => parseInt(n)));
const refundScript = Buffer.from(vault.refundScript.split(',').map(n => parseInt(n)));
const controlBlock = Buffer.from(vault.refundControlBlock, 'hex');

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

const borrowerP2wpkh = bitcoin.payments.p2wpkh({ pubkey: borrower.publicKey, network });
const feeSats = 1000;
const sendAmount = fundingAmount - feeSats;
psbt.addOutput({
  address: borrowerP2wpkh.address,
  value: BigInt(sendAmount),
});

console.log('=== PSBT Approach ===');
console.log(`Input: ${fundingTxid}:0 (${fundingAmount} sats)`);
console.log(`Output: ${sendAmount} sats -> ${borrowerP2wpkh.address}`);
console.log(`CSV: ${csvBlocks} blocks`);

// Sign using PSBT's signInput
// For Taproot script-path, we need to provide a custom signer
// that signs with the leaf hash

// The tapLeafScript is set, so PSBT should know which leaf to sign for
// Let's try signing with the borrower's key directly
try {
  psbt.signInput(0, borrower);
  console.log('PSBT signInput: OK');
} catch (e) {
  console.log(`PSBT signInput failed: ${e.message}`);

  // Try with a custom signer that provides the tapleaf signature
  console.log('Trying custom signer...');

  // Get the tapleaf hash from the PSBT input
  const input = psbt.data.inputs[0];
  const tapLeaf = input.tapLeafScript[0];

  // For Taproot script-path signing, we need to:
  // 1. Compute the tapleaf hash
  // 2. Compute the BIP-341 sighash with the leaf hash
  // 3. Sign with the internal private key

  // The PSBT signTapleafInput method handles this
  // But it might not be available in bitcoinjs-lib v7
  // Let's check
  console.log('PSBT methods:', Object.getOwnPropertyNames(Object.getPrototypeOf(psbt)).filter(m => m.includes('sign')));
}

// Check if we got a signature
const input = psbt.data.inputs[0];
console.log(`tapScriptSigs: ${input.tapScriptSigs?.length || 0}`);

if (input.tapScriptSigs && input.tapScriptSigs.length > 0) {
  const tapSig = input.tapScriptSigs[0];
  console.log(`Signature: ${Buffer.from(tapSig.signature).toString('hex').slice(0, 40)}...`);
  console.log(`Signature length: ${tapSig.signature.length}`);

  // Finalize
  const witness = [tapSig.signature, refundScript, controlBlock];
  psbt.finalizeInput(0, () => ({
    finalScriptWitness: witnessStackToScriptWitness(witness),
  }));

  const signedTx = psbt.extractTransaction();
  const rawTxHex = signedTx.toHex();
  const txid = signedTx.getId();
  console.log(`\ntxid: ${txid}`);
  console.log(`raw hex: ${rawTxHex}`);

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
      description: 'Real Bitcoin testnet transaction spending a TRION Coherence Vault UTXO via the CSV refund script path.',
    };
    fs.writeFileSync(
      '/home/z/my-project/trion-core/proofs/btcp-zero-bridge/stacks/btc-testnet-live-results.json',
      JSON.stringify(results, null, 2)
    );
    console.log('Results saved!');
  } else {
    console.error(`\nFAILED: ${resp.status} ${text}`);
  }
} else {
  console.log('No signature produced');

  // Last resort: try signing with the tweaked key
  const tree = [{ output: releaseScript }, { output: refundScript }];
  const hashTree = toHashTree(tree);
  const merkleRoot = hashTree.hash;
  const tweakHash = bitcoin.crypto.taggedHash('TapTweak', Buffer.concat([internalPubkey, merkleRoot]));
  const tweakedPrivKey = ecc.privateAdd(borrower.privateKey, tweakHash);

  // Create a tweaked ECPair
  const tweakedSigner = ECPair.fromPrivateKey(Buffer.from(tweakedPrivKey), { network, compressed: true });
  console.log('Trying with tweaked key...');
  try {
    psbt.signInput(0, tweakedSigner);
    console.log('Tweaked signInput: OK');
    const input2 = psbt.data.inputs[0];
    console.log(`tapScriptSigs: ${input2.tapScriptSigs?.length || 0}`);
    if (input2.tapScriptSigs && input2.tapScriptSigs.length > 0) {
      const witness = [input2.tapScriptSigs[0].signature, refundScript, controlBlock];
      psbt.finalizeInput(0, () => ({
        finalScriptWitness: witnessStackToScriptWitness(witness),
      }));
      const signedTx = psbt.extractTransaction();
      const rawTxHex = signedTx.toHex();
      console.log(`raw hex: ${rawTxHex}`);
      const resp = await fetch('https://mempool.space/testnet/api/tx', {
        method: 'POST',
        headers: { 'Content-Type': 'text/plain' },
        body: rawTxHex,
      });
      const text = await resp.text();
      if (resp.ok) {
        console.log(`SUCCESS! txid: ${text}`);
      } else {
        console.error(`FAILED: ${resp.status} ${text}`);
      }
    }
  } catch (e) {
    console.log(`Tweaked signInput failed: ${e.message}`);
  }
}
