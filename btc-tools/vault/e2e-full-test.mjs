/**
 * e2e-full-test.mjs — Full end-to-end test across Bitcoin testnet + Stacks testnet.
 */

import { ECPairFactory } from 'ecpair';
import * as ecc from 'tiny-secp256k1';
import * as bitcoin from 'bitcoinjs-lib';
bitcoin.initEccLib(ecc);
import { toHashTree, findScriptPath, tapleafHash, tweakKey, LEAF_VERSION_TAPSCRIPT } from 'bitcoinjs-lib/src/payments/bip341';
import { witnessStackToScriptWitness } from 'bitcoinjs-lib/src/psbt/psbtutils';
import * as crypto from 'crypto';
import * as fs from 'fs';
import { sendContractCall, buffCV, hashStr, getAddressFromPrivateKey } from '../stacks/lib/helpers.mjs';
import txPkg from '@stacks/transactions';
const { uintCV } = txPkg;

const ECPair = ECPairFactory(ecc);
const network = bitcoin.networks.testnet;
const DEPLOYER_KEY = '940806a0a98e86df44835d7fb5d58a79d6259f413550ba11a858880a72e2e71901';
const DEPLOYER_ADDR = getAddressFromPrivateKey(DEPLOYER_KEY, 'testnet');
const STACKS_CONTRACT = { contractAddress: DEPLOYER_ADDR, contractName: 'trioncoherencevault-v5' };
const BTC_ADDR = 'tb1q5d69fyxxxwdkr7pecmxyr245w5jqchm9zptkks';
const btcBlockHash = '00000000000001a9562ec7227605f68ea1baf77dfa37d6794fcd55bca4a509f4';
const btcBlockTime = 1788718503;
const btcSats = 304527;

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
function log(msg) { console.log(`[${new Date().toISOString().slice(11,19)}] ${msg}`); }

// Phase 1: Generate vault
log('=== Phase 1: Generate vault ===');
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
log(`  Payload: ${payload.length} bytes, anchor_bh: ${committedAnchorBH}`);

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

const vault = {
  vaultAddress: p2tr.address, vaultOutputScript: Buffer.from(p2tr.output).toString('hex'),
  internalPubkey: internalPubkey.toString('hex'), committedAnchorBH, payloadHex, payloadLength: 80,
  csvBlocks, borrowerWif: borrower.toWIF(), lenderAddress: BTC_ADDR,
  releaseScript: releaseScript.toString('hex'), refundScript: refundScript.toString('hex'),
  releaseControlBlock: releaseCB.toString('hex'), refundControlBlock: refundCB.toString('hex'),
};
fs.writeFileSync('/tmp/vault-e2e.json', JSON.stringify(vault, null, 2));
log(`  Vault address: ${vault.vaultAddress}`);

// Phase 2: Wait for funding
log('\n=== Phase 2: Wait for vault funding ===');
log(`  >>> SEND TESTNET BTC TO: ${vault.vaultAddress} <<<`);
let utxo = null;
for (let i = 0; i < 120; i++) {
  try {
    const resp = await fetch(`https://mempool.space/testnet/api/address/${vault.vaultAddress}/utxo`);
    const utxos = await resp.json();
    if (utxos && utxos.length > 0) { utxo = utxos[0]; log(`  FUNDED! ${utxo.txid} ${utxo.value} sats`); break; }
  } catch {}
  process.stdout.write(`\r  Waiting... (${i*30}s)`);
  await sleep(30000);
}
if (!utxo) { log('\n  Not funded. Exiting.'); process.exit(0); }

if (!utxo.status.confirmed) {
  log('  Waiting for confirmation...');
  for (let i = 0; i < 60; i++) {
    await sleep(30000);
    const resp = await fetch(`https://mempool.space/testnet/api/address/${vault.vaultAddress}/utxo`);
    const updated = await resp.json();
    if (updated[0]?.status?.confirmed) { utxo = updated[0]; log(`  Confirmed block ${utxo.status.block_height}`); break; }
    process.stdout.write(`\r  Confirm... (${(i+1)*30}s)`);
  }
}
const fundingTxid = utxo.txid, fundingVout = utxo.vout, fundingAmount = utxo.value;
log(`  Funding: ${fundingTxid}:${fundingVout} = ${fundingAmount} sats`);

// Phase 3: Register vault on Stacks
log('\n=== Phase 3: Register vault on Stacks (v5 contract) ===');
const vaultId = '0x' + crypto.createHash('sha256').update(vault.vaultAddress + Date.now()).digest('hex');
const entityIdHex = payloadHex.slice(0, 40);
const regResult = await sendContractCall({
  ...STACKS_CONTRACT, functionName: 'register-vault',
  functionArgs: [buffCV(vaultId), buffCV('0x'+entityIdHex), buffCV('0x'+committedAnchorBH), buffCV(hashStr(BTC_ADDR)), uintCV(BigInt(fundingAmount)), uintCV(csvBlocks)],
  senderKey: DEPLOYER_KEY, fee: 100000,
});
log(`  register-vault: ${regResult.ok ? '✅ PASS' : '❌ FAIL'} tx=${regResult.txId || regResult.error}`);

// Phase 4: Publish preimage on Stacks
log('\n=== Phase 4: Publish preimage on Stacks ===');
const pubResult = await sendContractCall({
  ...STACKS_CONTRACT, functionName: 'publish-preimage',
  functionArgs: [buffCV(vaultId), buffCV('0x'+payloadHex)],
  senderKey: DEPLOYER_KEY, fee: 100000,
});
log(`  publish-preimage: ${pubResult.ok ? '✅ PASS' : '❌ FAIL'} tx=${pubResult.txId || pubResult.error}`);
if (!pubResult.ok && pubResult.info) { log(`  result: ${pubResult.info?.tx_result?.repr || ''}`); log(`  vm_error: ${pubResult.info?.vm_error || ''}`); }

// Phase 5: Build + broadcast BTC preimage-reveal spend
log('\n=== Phase 5: BTC preimage-reveal spend ===');
const tx = new bitcoin.Transaction();
tx.version = 2;
tx.addInput(Buffer.from(fundingTxid, 'hex').reverse(), fundingVout, 0xfffffffe);
const feeSats = 1000, sendAmount = fundingAmount - feeSats;
tx.addOutput(bitcoin.address.toOutputScript(BTC_ADDR, network), BigInt(sendAmount));
tx.setWitness(0, [payload, releaseScript, releaseCB]);
const rawTxHex = tx.toHex(), btcTxid = tx.getId();
log(`  txid: ${btcTxid}`);
log(`  Input: ${fundingAmount} sats -> Output: ${sendAmount} sats to lender`);
log(`  Witness: [${payload.length}B preimage, ${releaseScript.length}B script, ${releaseCB.length}B CB]`);

log('  Broadcasting...');
const bresp = await fetch('https://mempool.space/testnet/api/tx', { method: 'POST', headers: {'Content-Type':'text/plain'}, body: rawTxHex });
const btext = await bresp.text();
if (!bresp.ok) { log(`  ❌ BROADCAST FAILED: ${bresp.status} ${btext}`); process.exit(1); }
const broadcastTxid = btext.replace(/"/g,'').trim();
log(`  ✅ BROADCAST SUCCESS! txid: ${broadcastTxid}`);
log(`  Explorer: https://mempool.space/testnet/tx/${broadcastTxid}`);

// Phase 6: Wait for confirmation
log('\n=== Phase 6: Wait for BTC confirmation ===');
let confirmed = false, blockHeight = null;
for (let i = 0; i < 120; i++) {
  await sleep(30000);
  try {
    const sr = await fetch(`https://mempool.space/testnet/api/tx/${broadcastTxid}`);
    const sd = await sr.json();
    if (sd.status?.confirmed) { confirmed = true; blockHeight = sd.status.block_height; log(`  ✅ CONFIRMED block ${blockHeight}!`); break; }
  } catch {}
  process.stdout.write(`\r  Waiting... (${(i+1)*30}s)`);
}

// Phase 7: Final report
log('\n=== Phase 7: Final report ===');
const results = {
  test: 'TRION Coherence Vault E2E (BTC + Stacks)', timestamp: new Date().toISOString(),
  vault: { address: vault.vaultAddress, committedAnchorBH, payloadLength: 80, releaseScript: vault.releaseScript },
  bitcoin: {
    fundingTxid, fundingVout, fundingAmount, fundingConfirmed: utxo.status.confirmed, fundingBlock: utxo.status.block_height,
    spendTxid: broadcastTxid, spendAmount: sendAmount, fee: feeSats, spendConfirmed: confirmed, spendBlock: blockHeight,
    spendType: 'preimage-reveal (NO SIGNATURE)', explorerUrl: `https://mempool.space/testnet/tx/${broadcastTxid}`,
    witness: { item0: '80-byte HashDNA preimage (NOT a signature)', item1: '35-byte OP_SHA256 <hash> OP_EQUAL', item2: '65-byte controlBlock' },
  },
  stacks: {
    contract: 'ST969AZNDX2P7N1YJ0DNVGC8QEKT388DBMXGHR9Z.trioncoherencevault-v5',
    registerVaultTx: regResult.txId, registerVaultOk: regResult.ok,
    publishPreimageTx: pubResult.txId, publishPreimageOk: pubResult.ok,
  },
  summary: {
    btcFundingConfirmed: utxo.status.confirmed, btcPreimageSpendConfirmed: confirmed,
    stacksRegisterOk: regResult.ok, stacksPublishOk: pubResult.ok,
    assetsBridged: false, novelPrimitiveProven: confirmed && regResult.ok && pubResult.ok,
  },
};
fs.writeFileSync('/home/z/my-project/trion-core/proofs/btcp-zero-bridge/stacks/e2e-full-results.json', JSON.stringify(results, null, 2));
log('');
log('=========================================================');
log('  FINAL STATUS');
log('=========================================================');
log(`  BTC funding:     ${utxo.status.confirmed ? '✅' : '❌'} (block ${utxo.status.block_height})`);
log(`  BTC preimage:    ${confirmed ? '✅' : '❌'} (block ${blockHeight})`);
log(`  Stacks register: ${regResult.ok ? '✅' : '❌'} (${regResult.txId?.slice(0,20)}...)`);
log(`  Stacks publish:  ${pubResult.ok ? '✅' : '❌'} (${pubResult.txId?.slice(0,20)}...)`);
log(`  assets_bridged:  false`);
log(`  Novel primitive: ${confirmed && regResult.ok && pubResult.ok ? '✅ PROVEN' : '❌ INCOMPLETE'}`);
log('=========================================================');
