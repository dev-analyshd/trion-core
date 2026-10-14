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
const borrower = ECPair.fromWIF(vault.borrowerWif, network);
const internalPubkey = Buffer.from(vault.internalPubkey, 'hex');

const releaseScript = Buffer.from(vault.releaseScript.split(',').map(n => parseInt(n)));
const refundScript = Buffer.from(vault.refundScript.split(',').map(n => parseInt(n)));

const tree = [{ output: releaseScript }, { output: refundScript }];
const p2tr = bitcoin.payments.p2tr({ internalPubkey, scriptTree: tree, network });

console.log('=== Debug ===');
console.log('Vault address match:', p2tr.address === vault.vaultAddress);
console.log('p2tr.tweak:', p2tr.tweak ? Buffer.from(p2tr.tweak).toString('hex') : 'null');

// The key issue: for script-path spend, the signature is verified
// against the pubkey IN THE SCRIPT, which is the internal pubkey.
// But the PSBT's signInput fails because it tries to match the signer's
// pubkey against the TWEAKED pubkey (the output key), not the internal key.

// The PSBT's signInput for Taproot expects the signer's publicKey to match
// the tweaked output key. But for script-path spends, we need to sign with
// the INTERNAL key, not the tweaked key.

// The solution: use a custom signer that implements the Signer interface
// and provides the signature via the tapScriptSig mechanism.

// Let's compute everything manually:

// 1. Build the unsigned transaction
const psbt = new bitcoin.Psbt({ network });
psbt.addInput({
  hash: '688222635d1c86cae125ba4cf33b660b4d686e11ef15107a3547f7e724ab15d2',
  index: 0,
  witnessUtxo: {
    script: Buffer.from(vault.vaultOutputScript, 'hex'),
    value: BigInt(128310),
  },
  sequence: vault.csvBlocks,
  tapLeafScript: [{
    leafVersion: 0xc0,
    script: refundScript,
    controlBlock: Buffer.from(vault.refundControlBlock, 'hex'),
  }],
});

const borrowerP2wpkh = bitcoin.payments.p2wpkh({ pubkey: borrower.publicKey, network });
psbt.addOutput({ address: borrowerP2wpkh.address, value: BigInt(127310) });

// 2. Get the tapleaf hash
const tapleafHash = bitcoin.crypto.taggedHash('TapLeaf', Buffer.concat([
  Buffer.from([0xc0]),
  bitcoin.script.compile(refundScript),
]));

// 3. Try using PSBT's signTapleafInput or equivalent
// In bitcoinjs-lib v7, the PSBT's signInput for Taproot should handle script-path
// if the tapLeafScript is provided AND the signer's pubkey matches a key in the script

// The script has: OP_6 CSV OP_DROP <internalPubkey> OP_CHECKSIG
// The pubkey is the internal pubkey (x-only)
// The signer has: borrower.publicKey = 02<internalPubkey>

// The PSBT's signInput checks if the signer's publicKey (33 bytes compressed)
// matches any pubkey in the tapLeafScript. But the script uses x-only (32 bytes).
// This might be the mismatch!

// Let's try with a signer that has x-only pubkey
console.log('borrower.publicKey (33 bytes):', Buffer.from(borrower.publicKey).toString('hex'));
console.log('internal pubkey (32 bytes):  ', internalPubkey.toString('hex'));

// The PSBT signInput for Taproot script-path should work if we provide
// the signer with the right format. Let's check what signInput expects.

// Actually, looking at bitcoinjs-lib source, signInput for Taproot
// checks if the input has tapLeafScript, and if so, tries to sign
// using the leaf hash. It matches the signer's pubkey against
// the pubkeys found in the script.

// The issue might be that signInput can't find the pubkey in the script
// because the script uses x-only format (32 bytes) while the signer's
// publicKey is compressed (33 bytes).

// Let's create a signer with x-only pubkey
const xOnlySigner = {
  publicKey: Buffer.from(internalPubkey), // 32 bytes x-only
  signSchnorr: (hash) => {
    return Buffer.from(ecc.signSchnorr(hash, borrower.privateKey));
  },
  sign: (hash) => {
    return Buffer.from(ecc.sign(hash, borrower.privateKey));
  },
};

console.log('Trying x-only signer...');
try {
  psbt.signInput(0, xOnlySigner);
  console.log('signInput: OK');
  const input = psbt.data.inputs[0];
  console.log('tapScriptSigs:', input.tapScriptSigs?.length || 0);
  if (input.tapScriptSigs && input.tapScriptSigs.length > 0) {
    const sig = input.tapScriptSigs[0].signature;
    console.log('Signature:', Buffer.from(sig).toString('hex').slice(0, 40));
    console.log('Sig length:', sig.length);

    // Finalize and broadcast
    const witness = [sig, refundScript, Buffer.from(vault.refundControlBlock, 'hex')];
    psbt.finalizeInput(0, () => ({
      finalScriptWitness: witnessStackToScriptWitness(witness),
    }));

    const signedTx = psbt.extractTransaction();
    const rawTxHex = signedTx.toHex();
    console.log('txid:', signedTx.getId());
    console.log('raw:', rawTxHex.slice(0, 80));

    const resp = await fetch('https://mempool.space/testnet/api/tx', {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain' },
      body: rawTxHex,
    });
    const text = await resp.text();
    if (resp.ok) {
      console.log('BROADCAST SUCCESS! txid:', text.replace(/"/g, ''));
      console.log('Explorer: https://mempool.space/testnet/tx/' + text.replace(/"/g, ''));

      const results = {
        step: 'csv-refund-spend',
        status: 'broadcast_success',
        fundingTxid: '688222635d1c86cae125ba4cf33b660b4d686e11ef15107a3547f7e724ab15d2',
        spendTxid: text.replace(/"/g, ''),
        sendAmount: 127310,
        fee: 1000,
        vaultAddress: vault.vaultAddress,
        borrowerAddress: borrowerP2wpkh.address,
        csvBlocks: vault.csvBlocks,
        explorerUrl: 'https://mempool.space/testnet/tx/' + text.replace(/"/g, ''),
        timestamp: new Date().toISOString(),
      };
      fs.writeFileSync(
        '/home/z/my-project/trion-core/proofs/btcp-zero-bridge/stacks/btc-testnet-live-results.json',
        JSON.stringify(results, null, 2)
      );
      console.log('Results saved!');
    } else {
      console.error('FAILED:', resp.status, text);
    }
  }
} catch (e) {
  console.log('signInput failed:', e.message);
}
