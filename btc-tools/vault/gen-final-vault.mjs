import { ECPairFactory } from 'ecpair';
import * as ecc from 'tiny-secp256k1';
import * as bitcoin from 'bitcoinjs-lib';
bitcoin.initEccLib(ecc);
import { toHashTree, findScriptPath, tapleafHash, tweakKey, LEAF_VERSION_TAPSCRIPT } from 'bitcoinjs-lib/src/payments/bip341';
import * as crypto from 'crypto';
import * as fs from 'fs';

const ECPair = ECPairFactory(ecc);
const network = bitcoin.networks.testnet;

const BTC_ADDR = 'tb1q5d69fyxxxwdkr7pecmxyr245w5jqchm9zptkks';
const btcBlockHash = '00000000000001a9562ec7227605f68ea1baf77dfa37d6794fcd55bca4a509f4';
const btcBlockTime = 1788718503;
const btcSats = 304527;

const borrower = ECPair.makeRandom({ network });
const internalPubkey = Buffer.from(borrower.publicKey).subarray(1, 33);

const entityIdFull = crypto.createHash('sha256').update(BTC_ADDR.toLowerCase()).digest();
const entityId = entityIdFull.subarray(0, 20);
const magnitudeNano = BigInt(btcSats) * 1_000_000_000n;
const payload = Buffer.alloc(80);
entityId.copy(payload, 0);
payload.writeUInt8(0, 20);
payload.writeBigUInt64BE(magnitudeNano, 21);
payload.writeBigUInt64BE(BigInt(btcBlockTime), 29);
payload.writeUInt32BE(100, 37);
Buffer.from(btcBlockHash, 'hex').copy(payload, 41);
const payloadHex = payload.toString('hex');
const committedAnchorBH = crypto.createHash('sha256').update(payload).digest('hex');

const releaseScript = bitcoin.script.compile([
  bitcoin.opcodes.OP_SHA256, Buffer.from(committedAnchorBH, 'hex'), bitcoin.opcodes.OP_EQUAL,
]);
const csvBlocks = 6;
const refundScript = bitcoin.script.compile([
  bitcoin.script.number.encode(csvBlocks), bitcoin.opcodes.OP_CHECKSEQUENCEVERIFY, bitcoin.opcodes.OP_DROP,
  internalPubkey, bitcoin.opcodes.OP_CHECKSIG,
]);
const tree = [{ output: releaseScript }, { output: refundScript }];
const p2tr = bitcoin.payments.p2tr({ internalPubkey, scriptTree: tree, network });

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

const vaultState = {
  vaultAddress: p2tr.address,
  vaultOutputScript: Buffer.from(p2tr.output).toString('hex'),
  internalPubkey: internalPubkey.toString('hex'),
  committedAnchorBH,
  payloadHex,
  payloadLength: 80,
  csvBlocks,
  borrowerWif: borrower.toWIF(),
  borrowerPubkey: Buffer.from(borrower.publicKey).toString('hex'),
  lenderAddress: BTC_ADDR,
  releaseScript: releaseScript.toString('hex'),
  refundScript: refundScript.toString('hex'),
  releaseControlBlock: releaseCB.toString('hex'),
  refundControlBlock: refundCB.toString('hex'),
};

// Save to BOTH /tmp AND the repo (permanent — survives cron resets)
fs.writeFileSync('/tmp/vault-final.json', JSON.stringify(vaultState, null, 2));
fs.writeFileSync('/home/z/my-project/trion-core/btc-tools/vault/vault-final.json', JSON.stringify(vaultState, null, 2));

console.log('=== NEW VAULT GENERATED ===');
console.log('Vault address:', p2tr.address);
console.log('Borrower WIF:', borrower.toWIF());
console.log('anchor_bh:', committedAnchorBH);
console.log('Payload:', payloadHex.slice(0, 40) + '...');
console.log('');
console.log('>>> FUND THIS ADDRESS: ' + p2tr.address + ' <<<');
