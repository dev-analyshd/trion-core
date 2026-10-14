import { ECPairFactory } from 'ecpair';
import * as ecc from 'tiny-secp256k1';
import * as bitcoin from 'bitcoinjs-lib';
bitcoin.initEccLib(ecc);
import { toHashTree, findScriptPath, tapleafHash, tweakKey, LEAF_VERSION_TAPSCRIPT } from 'bitcoinjs-lib/src/payments/bip341';
import * as crypto from 'crypto';
import * as fs from 'fs';

const ECPair = ECPairFactory(ecc);
const network = bitcoin.networks.testnet;

// Generate borrower key
const borrower = ECPair.makeRandom({ network });
const wif = borrower.toWIF();
const pubkey = Buffer.from(borrower.publicKey);
const internalPubkey = pubkey.slice(1, 33);

// Compute anchor_bh from a real BTC testnet tx
const BTC_ADDR = 'tb1q5d69fyxxxwdkr7pecmxyr245w5jqchm9zptkks';
const btcBlockHash = '00000000000001a9562ec7227605f68ea1baf77dfa37d6794fcd55bca4a509f4';
const btcBlockTime = 1788718503;
const btcSats = 304527;

const entityId = crypto.createHash('sha256').update(BTC_ADDR.toLowerCase()).digest();
const magnitudeNano = BigInt(btcSats) * 1_000_000_000n;
const payload = Buffer.alloc(93);
entityId.copy(payload, 0, 0, 32);
payload.writeUInt8(0, 32);
payload.writeBigUInt64BE(magnitudeNano, 33);
payload.writeBigUInt64BE(0n, 41);
payload.writeBigUInt64BE(BigInt(btcBlockTime), 49);
payload.writeUInt32BE(100, 57);
Buffer.from(btcBlockHash, 'hex').copy(payload, 61, 0, 32);

const senseData = Buffer.concat([payload, Buffer.from([0x00])]);
const anchorBH = crypto.createHash('sha256').update(senseData).digest('hex');

// Build vault
const releaseScript = bitcoin.script.compile([
  Buffer.from(anchorBH, 'hex'),
  bitcoin.opcodes.OP_SHA256,
  bitcoin.opcodes.OP_EQUAL,
]);
const refundScript = bitcoin.script.compile([
  bitcoin.script.number.encode(6),
  bitcoin.opcodes.OP_CHECKSEQUENCEVERIFY,
  bitcoin.opcodes.OP_DROP,
  internalPubkey,
  bitcoin.opcodes.OP_CHECKSIG,
]);

const tree = [{ output: releaseScript }, { output: refundScript }];
const p2tr = bitcoin.payments.p2tr({ internalPubkey, scriptTree: tree, network });

// Compute control blocks
function computeCB(scriptTree, targetScript) {
  const hashTree = toHashTree(scriptTree);
  const leafHash = tapleafHash({ output: targetScript, version: LEAF_VERSION_TAPSCRIPT });
  const path = findScriptPath(hashTree, leafHash) ?? [];
  const tweak = tweakKey(internalPubkey, hashTree.hash);
  if (!tweak) throw new Error('tweakKey failed');
  const firstByte = (LEAF_VERSION_TAPSCRIPT & 0xfe) | (tweak.parity & 0x01);
  return Buffer.concat([Buffer.from([firstByte]), Buffer.from(internalPubkey), ...path.map(h => Buffer.from(h))]);
}

const releaseCB = computeCB(tree, releaseScript);
const refundCB = computeCB(tree, refundScript);

console.log('=== VAULT CREATED ===');
console.log('Borrower WIF:', wif);
console.log('Vault address:', p2tr.address);
console.log('anchor_bh:', anchorBH);
console.log('payload_hex:', payload.toString('hex'));
console.log('release_script:', releaseScript.toString('hex'));
console.log('refund_script:', refundScript.toString('hex'));
console.log('release_control_block:', releaseCB.toString('hex'));
console.log('refund_control_block:', refundCB.toString('hex'));
console.log('vault_output_script:', Buffer.from(p2tr.output).toString('hex'));
console.log('internal_pubkey:', internalPubkey.toString('hex'));

// Save to file
fs.writeFileSync('/tmp/vault-state-live.json', JSON.stringify({
  vaultAddress: p2tr.address,
  vaultOutputScript: Buffer.from(p2tr.output).toString('hex'),
  internalPubkey: internalPubkey.toString('hex'),
  tweak: p2tr.tweak ? Buffer.from(p2tr.tweak).toString('hex') : null,
  releaseScript: releaseScript.toString('hex'),
  refundScript: refundScript.toString('hex'),
  releaseControlBlock: releaseCB.toString('hex'),
  refundControlBlock: refundCB.toString('hex'),
  committedAnchorBH: anchorBH,
  payloadHex: payload.toString('hex'),
  csvBlocks: 6,
  borrowerWif: wif,
  borrowerPubkey: pubkey.toString('hex'),
  lenderAddress: BTC_ADDR,
}, null, 2));
console.log('\nState saved to /tmp/vault-state-live.json');
console.log('\nSEND TESTNET BTC TO:', p2tr.address);
