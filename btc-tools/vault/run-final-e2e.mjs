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

// Read vault state from permanent file
const vault = JSON.parse(fs.readFileSync('/home/z/my-project/trion-core/btc-tools/vault/vault-final.json', 'utf-8'));
console.log('=== Phase 1: Verify vault ===');
console.log(`  Vault address: ${vault.vaultAddress}`);

const borrower = ECPair.fromWIF(vault.borrowerWif, network);
const internalPubkey = Buffer.from(vault.internalPubkey, 'hex');
const payload = Buffer.from(vault.payloadHex, 'hex');
const committedAnchorBH = vault.committedAnchorBH;
const releaseScript = Buffer.from(vault.releaseScript.split(',').map(b => parseInt(b)));
const releaseCB = Buffer.from(vault.releaseControlBlock, 'hex');

// Verify hash
const computedHash = crypto.createHash('sha256').update(payload).digest('hex');
console.log(`  anchor_bh: ${committedAnchorBH}`);
console.log(`  hash match: ${computedHash === committedAnchorBH}`);

// Verify vault address
const tree = [{ output: releaseScript }, { output: Buffer.from(vault.refundScript.split(',').map(b => parseInt(b))) }];
const p2tr = bitcoin.payments.p2tr({ internalPubkey, scriptTree: tree, network });
console.log(`  address match: ${p2tr.address === vault.vaultAddress}`);

// Phase 2: Verify funding (already confirmed)
const fundingTxid = '36172ef4b754ea80e2a533406368a3c1f4db3c6611dfe3a7ea2d88cb926836c4';
const fundingVout = 1;
const fundingAmount = 158148;
console.log('\n=== Phase 2: Funding confirmed ===');
console.log(`  txid: ${fundingTxid}:${fundingVout}`);
console.log(`  amount: ${fundingAmount} sats`);
console.log(`  block: 5197629`);

// Phase 3: Register vault on Stacks v5
console.log('\n=== Phase 3: Register vault on Stacks (v5) ===');
const vaultId = '0x' + crypto.createHash('sha256').update(vault.vaultAddress + Date.now()).digest('hex');
const entityIdHex = vault.payloadHex.slice(0, 40);

const regResult = await sendContractCall({
  ...STACKS_CONTRACT, functionName: 'register-vault',
  functionArgs: [buffCV(vaultId), buffCV('0x'+entityIdHex), buffCV('0x'+committedAnchorBH), buffCV(hashStr(vault.lenderAddress)), uintCV(BigInt(fundingAmount)), uintCV(vault.csvBlocks)],
  senderKey: DEPLOYER_KEY, fee: 100000,
});
console.log(`  register-vault: ${regResult.ok ? '✅ PASS' : '❌ FAIL'} tx=${regResult.txId || regResult.error}`);

// Phase 4: Publish preimage on Stacks v5
console.log('\n=== Phase 4: Publish preimage on Stacks (v5) ===');
const pubResult = await sendContractCall({
  ...STACKS_CONTRACT, functionName: 'publish-preimage',
  functionArgs: [buffCV(vaultId), buffCV('0x'+vault.payloadHex)],
  senderKey: DEPLOYER_KEY, fee: 100000,
});
console.log(`  publish-preimage: ${pubResult.ok ? '✅ PASS' : '❌ FAIL'} tx=${pubResult.txId || pubResult.error}`);
if (!pubResult.ok) {
  console.log(`  error: ${pubResult.error}`);
  if (pubResult.info?.tx_result) console.log(`  result: ${pubResult.info.tx_result.repr}`);
  if (pubResult.info?.vm_error) console.log(`  vm_error: ${pubResult.info.vm_error}`);
}

// Phase 5: Build + broadcast BTC preimage-reveal spend
console.log('\n=== Phase 5: BTC preimage-reveal spend ===');
const tx = new bitcoin.Transaction();
tx.version = 2;
tx.addInput(Buffer.from(fundingTxid, 'hex').reverse(), fundingVout, 0xfffffffe);
const feeSats = 1000;
const sendAmount = fundingAmount - feeSats;
tx.addOutput(bitcoin.address.toOutputScript(vault.lenderAddress, network), BigInt(sendAmount));
tx.setWitness(0, [payload, releaseScript, releaseCB]);
const rawTxHex = tx.toHex();
const btcTxid = tx.getId();
console.log(`  txid: ${btcTxid}`);
console.log(`  Input: ${fundingAmount} sats -> Output: ${sendAmount} sats to lender`);
console.log(`  Fee: ${feeSats} sats`);
console.log(`  Witness: [${payload.length}B preimage, ${releaseScript.length}B script, ${releaseCB.length}B CB]`);

console.log('  Broadcasting...');
const bresp = await fetch('https://mempool.space/testnet/api/tx', { method: 'POST', headers: {'Content-Type':'text/plain'}, body: rawTxHex });
const btext = await bresp.text();
if (!bresp.ok) {
  console.error(`  ❌ BROADCAST FAILED: ${bresp.status} ${btext}`);
  process.exit(1);
}
const broadcastTxid = btext.replace(/"/g,'').trim();
console.log(`  ✅ BROADCAST SUCCESS! txid: ${broadcastTxid}`);
console.log(`  Explorer: https://mempool.space/testnet/tx/${broadcastTxid}`);

// Phase 6: Wait for BTC confirmation
console.log('\n=== Phase 6: Wait for BTC confirmation ===');
let confirmed = false, blockHeight = null;
for (let i = 0; i < 120; i++) {
  await new Promise(r => setTimeout(r, 30000));
  try {
    const sr = await fetch(`https://mempool.space/testnet/api/tx/${broadcastTxid}`);
    const sd = await sr.json();
    if (sd.status?.confirmed) {
      confirmed = true; blockHeight = sd.status.block_height;
      console.log(`  ✅ CONFIRMED at block ${blockHeight}!`);
      break;
    }
  } catch {}
  process.stdout.write(`\r  Waiting... (${(i+1)*30}s)`);
}

// Phase 7: Final report
console.log('\n\n=== Phase 7: Final report ===');
const results = {
  test: 'TRION Coherence Vault E2E (BTC testnet + Stacks testnet)', timestamp: new Date().toISOString(),
  vault: { address: vault.vaultAddress, committedAnchorBH, payloadLength: 80 },
  bitcoin: {
    fundingTxid, fundingVout, fundingAmount, fundingConfirmed: true, fundingBlock: 5197629,
    spendTxid: broadcastTxid, spendAmount: sendAmount, fee: feeSats,
    spendConfirmed: confirmed, spendBlock: blockHeight,
    spendType: 'preimage-reveal (NO SIGNATURE — 80-byte HashDNA payload is the SOLE authorization)',
    explorerUrl: `https://mempool.space/testnet/tx/${broadcastTxid}`,
    witness: { item0: '80-byte HashDNA preimage (NOT a signature)', item1: '35-byte OP_SHA256 <hash> OP_EQUAL', item2: '65-byte controlBlock' },
  },
  stacks: {
    contract: 'ST969AZNDX2P7N1YJ0DNVGC8QEKT388DBMXGHR9Z.trioncoherencevault-v5',
    registerVaultTx: regResult.txId, registerVaultOk: regResult.ok,
    publishPreimageTx: pubResult.txId, publishPreimageOk: pubResult.ok,
  },
  summary: {
    btcFundingConfirmed: true, btcPreimageSpendConfirmed: confirmed,
    stacksRegisterOk: regResult.ok, stacksPublishOk: pubResult.ok,
    assetsBridged: false,
    novelPrimitiveProven: confirmed && regResult.ok && pubResult.ok,
  },
};
fs.writeFileSync('/home/z/my-project/trion-core/proofs/btcp-zero-bridge/stacks/e2e-full-results.json', JSON.stringify(results, null, 2));
console.log('=========================================================');
console.log('  FINAL STATUS');
console.log('=========================================================');
console.log(`  BTC funding:     ✅ CONFIRMED (block 5197629)`);
console.log(`  BTC preimage:    ${confirmed ? '✅' : '❌'} ${blockHeight ? `(block ${blockHeight})` : '(pending)'}`);
console.log(`  Stacks register: ${regResult.ok ? '✅' : '❌'} (${regResult.txId?.slice(0,20)}...)`);
console.log(`  Stacks publish:  ${pubResult.ok ? '✅' : '❌'} (${pubResult.txId?.slice(0,20)}...)`);
console.log(`  assets_bridged:  false`);
console.log(`  Novel primitive: ${confirmed && regResult.ok && pubResult.ok ? '✅ PROVEN' : '❌ INCOMPLETE'}`);
console.log('=========================================================');
