import { ECPairFactory } from 'ecpair';
import * as ecc from 'tiny-secp256k1';
import * as bitcoin from 'bitcoinjs-lib';
bitcoin.initEccLib(ecc);
import { toHashTree, tweakKey } from 'bitcoinjs-lib/src/payments/bip341';
import * as fs from 'fs';

const ECPair = ECPairFactory(ecc);
const network = bitcoin.networks.testnet;

const vault = JSON.parse(fs.readFileSync('/tmp/vault-state-live.json', 'utf-8'));
const borrower = ECPair.fromWIF(vault.borrowerWif, network);
const internalPubkey = Buffer.from(vault.internalPubkey, 'hex');

const releaseScript = Buffer.concat([
  Buffer.from([0xa8, 0x20]),
  Buffer.from(vault.committedAnchorBH, 'hex'),
  Buffer.from([0x87]),
]);
const csvNum = bitcoin.script.number.encode(vault.csvBlocks);
const refundScript = Buffer.concat([
  csvNum, Buffer.from([0xb2, 0x75]), internalPubkey, Buffer.from([0xac]),
]);

const tree = [{ output: releaseScript }, { output: refundScript }];
const hashTree = toHashTree(tree);
const merkleRoot = hashTree.hash;

// Compute the tweaked key
const tweakResult = tweakKey(internalPubkey, merkleRoot);
console.log('Tweak result:');
console.log('  parity:', tweakResult.parity);
console.log('  x (tweaked pubkey):', Buffer.from(tweakResult.x).toString('hex'));
console.log();

// Re-derive the vault address
const p2tr = bitcoin.payments.p2tr({ internalPubkey, scriptTree: tree, network });
console.log('Re-derived vault address:', p2tr.address);
console.log('Original vault address:  ', vault.vaultAddress);
console.log('Match:', p2tr.address === vault.vaultAddress);
console.log();

// Check output script
const expectedOutput = p2tr.output;
console.log('Expected output script:', Buffer.from(expectedOutput).toString('hex'));
console.log('Actual vault output:  ', vault.vaultOutputScript);
console.log('Match:', Buffer.from(expectedOutput).toString('hex') === vault.vaultOutputScript);
console.log();

// Compute the tweaked private key
const tweakHash = bitcoin.crypto.taggedHash('TapTweak', Buffer.concat([internalPubkey, merkleRoot]));
const tweakedPrivKey = ecc.privateAdd(borrower.privateKey, tweakHash);
const tweakedPubkey = ecc.pointFromScalar(tweakedPrivKey, true);
console.log('Tweaked pubkey from private key (compressed):', Buffer.from(tweakedPubkey).toString('hex'));
const tweakedXOnly = Buffer.from(tweakedPubkey).slice(1, 33);
console.log('X-only from private:', tweakedXOnly.toString('hex'));
console.log('X-only from tweakKey:', Buffer.from(tweakResult.x).toString('hex'));
console.log('Match:', tweakedXOnly.toString('hex') === Buffer.from(tweakResult.x).toString('hex'));
console.log();

// For Taproot script-path spend:
// The signature is verified against the INTERNAL pubkey (in the script)
// NOT the tweaked pubkey
// So we should sign with the INTERNAL private key, not the tweaked one

// Actually wait — in BIP-341 script-path spend:
// The script has OP_CHECKSIG with the internal pubkey
// The signature is verified against the internal pubkey
// So we need to sign with the INTERNAL key, not the tweaked key!

console.log('=== Key insight ===');
console.log('Script-path spend: signature verified against INTERNAL pubkey');
console.log('So we should sign with the ORIGINAL (non-tweaked) private key!');
console.log();

// Verify: does the internal pubkey match what's in the refund script?
console.log('Internal pubkey in script:', internalPubkey.toString('hex'));
console.log('Borrower pubkey (compressed):', Buffer.from(borrower.publicKey).toString('hex'));
const borrowerXOnly = Buffer.from(borrower.publicKey).slice(1, 33);
console.log('Borrower x-only:', borrowerXOnly.toString('hex'));
console.log('Match:', internalPubkey.toString('hex') === borrowerXOnly.toString('hex'));
