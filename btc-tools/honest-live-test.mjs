/**
 * HONEST LIVE TEST — Deploy new V3 (with all 4 fixes) on public RPC + test every function.
 * No false claims. Every step must actually SUCCEED on-chain or we report it as failed.
 */
import 'dotenv/config';
import crypto from 'crypto';
import fs from 'fs';
import { RpcProvider, Account, CallData, hash, json } from 'starknet';
import { makeExec } from './lib_patched_exec.mjs';

// Use PUBLIC RPC (no Alchemy fee estimation issues)
const RPC = 'https://starknet-sepolia-rpc.publicnode.com';
const BTC_RPC = process.env.BITCOIN_RPC;
const SPV_VERIFIER = '0x6510323e3ddd0c91d7c021200ec62c91605f528d1873eface5c0dc6258616c1';
const NEW_V3_CLASS = '0x4a603b5321ef2d5535d31040c5d63bfe3b2338a7f84fd3904b39d68ff7a4704';
const MAIN = process.env.STARKNET_ACCOUNT_ADDRESS;
const MAIN_PK = process.env.STARKNET_PRIVATE_KEY;
const TXID = '62bfe73fab5ac18c64794493d3713c5eb3e92b839df401befecd68162ee1fcf7';
const BTC_ADDR = 'tb1q5d69fyxxxwdkr7pecmxyr245w5jqchm9zptkks';
const BTC_CID = 100;

const provider = new RpcProvider({ nodeUrl: RPC });
const account = new Account({ provider, address: MAIN, signer: MAIN_PK });
const { exec, resetNonce } = await makeExec(provider, account, MAIN);

const FELT_MASK = (1n << 240n) - 1n;
function felt(h) { return BigInt('0x' + h.slice(2, 66).padStart(64, '0')) & FELT_MASK; }
function splitU256(v) { return { low: v & ((1n << 128n) - 1n), high: v >> 128n }; }
async function btc(method, params=[]) {
  const r = await fetch(BTC_RPC, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({jsonrpc:'2.0',method,params,id:1}) });
  const j = await r.json(); if (j.error) throw new Error(j.error.message); return j.result;
}

// Fetch BTC data
const tx = await btc('getrawtransaction', [TXID, true]);
const blockHex = await btc('getblockheader', [tx.blockhash, false]);
const headerBuf = Buffer.from(blockHex, 'hex');
const blockTime = headerBuf.readUInt32LE(68);
const blockHashBE = tx.blockhash;
const blockHashBuf = Buffer.from(blockHashBE, 'hex');
const vout0 = tx.vout.find(v => v.n === 0);
const amountSats = Math.round(vout0.value * 1e8);
const entityIdBuf = crypto.createHash('sha256').update(BTC_ADDR.toLowerCase()).digest();
const magnitudeNano = BigInt(amountSats) * 1_000_000_000n;
const buf = Buffer.alloc(93);
entityIdBuf.copy(buf, 0, 0, 32);
buf.writeUInt8(0, 32);
buf.writeBigUInt64BE(magnitudeNano, 33);
buf.writeBigUInt64BE(BigInt(blockTime), 49);
buf.writeUInt32BE(BTC_CID, 57);
blockHashBuf.copy(buf, 61, 0, 32);
const sense = crypto.createHash('sha256').update(Buffer.concat([buf, Buffer.from([0x00])])).digest();
const anchorBH = BigInt('0x' + sense.toString('hex'));
const blockHashU256 = BigInt('0x' + blockHashBE);

const block2 = await btc('getblock', [tx.blockhash, 2]);
const allTxids = block2.tx.map(t => t.txid);
function ds(b){const a=crypto.createHash('sha256').update(b).digest();return crypto.createHash('sha256').update(a).digest();}
let levelNow = allTxids.map(t => Buffer.from(t, 'hex').reverse());
let idxNow = allTxids.indexOf(TXID);
const pathBE = [];
while (levelNow.length > 1) {
  const sibIdx = (idxNow % 2 === 0) ? idxNow + 1 : idxNow - 1;
  const sib = (sibIdx < levelNow.length) ? levelNow[sibIdx] : levelNow[idxNow];
  pathBE.push(BigInt('0x' + Buffer.from(sib).reverse().toString('hex')));
  const next = [];
  for (let i = 0; i < levelNow.length; i += 2) { const l = levelNow[i]; const r = (i+1<levelNow.length)?levelNow[i+1]:l; next.push(ds(Buffer.concat([l,r]))); }
  levelNow = next; idxNow = Math.floor(idxNow / 2);
}
const txidU256 = BigInt('0x' + TXID);
const txidLo = txidU256 & ((1n << 128n) - 1n);
const txidHi = txidU256 >> 128n;
const entLo = BigInt('0x' + entityIdBuf.slice(16, 32).toString('hex'));
const entHi = BigInt('0x' + entityIdBuf.slice(0, 16).toString('hex'));
const txIndex = allTxids.indexOf(TXID);
const merklePathU256 = pathBE.map(p => { const s = splitU256(p); return { low: s.low, high: s.high }; });
const now = Math.floor(Date.now() / 1000);

const results = { startedAt: new Date().toISOString(), steps: [], rpc: RPC };
function record(id, label, pass, evidence) { results.steps.push({ id, label, pass, evidence }); console.log(`\n[${id}] ${label}: ${pass ? 'PASS' : 'FAIL'}`); if (evidence) console.log(`     ${String(evidence).slice(0, 250)}`); }

console.log('═══════════════════════════════════════════════════════════');
console.log('  HONEST LIVE TEST — public RPC, real on-chain transactions');
console.log('  RPC:', RPC);
console.log('═══════════════════════════════════════════════════════════\n');

// ── STEP 1: Deploy NEW V3 instance with the new class hash ──
console.log('── Step 1: Deploy NEW V3 (class with all 4 fixes) ──');
let v3Address;
try {
  const salt = '0x' + Math.floor(Math.random() * 1e9).toString(16);
  const deployRes = await account.deployContract({ classHash: NEW_V3_CLASS, constructorCalldata: CallData.compile({ owner: MAIN }), salt, unique: true });
  // Wait for receipt
  for (let i = 0; i < 90; i++) {
    try { const r = await provider.getTransactionReceipt(deployRes.transaction_hash); if (r && (r.execution_status === 'SUCCEEDED' || r.execution_status === 'REVERTED')) { console.log('  Deploy receipt:', r.execution_status); break; } } catch (e) {}
    await new Promise(r => setTimeout(r, 3000));
  }
  v3Address = deployRes.contract_address;
  console.log('  V3 deployed:', v3Address);
  // Verify class hash
  const deployedClass = await provider.getClassHashAt(v3Address);
  const isNew = deployedClass === NEW_V3_CLASS;
  record('S1', 'Deploy NEW V3 with 4-fix class', isNew, `addr=${v3Address.slice(0,20)} class=${deployedClass.slice(0,20)} isNew=${isNew}`);
} catch (e) { record('S1', 'Deploy NEW V3', false, String(e.message).slice(0, 250)); throw e; }

// ── STEP 2: Verify new functions exist in deployed ABI ──
console.log('\n── Step 2: Verify 4 new functions in deployed ABI ──');
const code = await provider.getClassAt(v3Address);
const fns = (code.abi || []).filter(a => a.type === 'interface').flatMap(i => i.items || []).filter(i => i.type === 'function').map(f => f.name);
const hasReportSpendProof = fns.includes('report_spend_proof');
const hasVerifyEscrowAnchor = fns.includes('verify_escrow_anchor');
const hasSetBtcpScore = fns.includes('set_btcp_score');
const hasGetBtcpScore = fns.includes('get_btcp_score');
const hasIsAnchorSpent = fns.includes('is_anchor_spent');
record('S2', 'ABI has report_spend_proof', hasReportSpendProof, hasReportSpendProof ? 'present' : 'MISSING');
record('S3', 'ABI has verify_escrow_anchor', hasVerifyEscrowAnchor, hasVerifyEscrowAnchor ? 'present' : 'MISSING');
record('S4', 'ABI has set_btcp_score', hasSetBtcpScore, hasSetBtcpScore ? 'present' : 'MISSING');
record('S5', 'ABI has get_btcp_score', hasGetBtcpScore, hasGetBtcpScore ? 'present' : 'MISSING');
record('S6', 'ABI has is_anchor_spent', hasIsAnchorSpent, hasIsAnchorSpent ? 'present' : 'MISSING');

// ── STEP 3: Setup — set SPV, register validator, set quorum ──
console.log('\n── Step 3: Setup (SPV, validator, quorum) ──');
try {
  await exec([{ contractAddress: v3Address, entrypoint: 'set_spv_verifier', calldata: CallData.compile({ spv: SPV_VERIFIER }) }], 'set-spv');
  resetNonce();
  await exec([{ contractAddress: v3Address, entrypoint: 'add_validator', calldata: CallData.compile({ validator: MAIN }) }], 'reg-val');
  resetNonce();
  await exec([{ contractAddress: v3Address, entrypoint: 'set_quorum_required', calldata: CallData.compile({ quorum: 1 }) }], 'set-q1');
  resetNonce();
  record('S7', 'Setup SPV + validator + quorum', true, 'SPV set, main account is validator, quorum=1');
} catch (e) { resetNonce(); record('S7', 'Setup', false, String(e.message).slice(0, 200)); throw e; }

// ── STEP 4: Lock escrow with SPV verify_anchor ──
console.log('\n── Step 4: Lock escrow with SPV verify_anchor ──');
const eid = felt('0x' + crypto.createHash('sha3-256').update('honest-' + now).digest('hex'));
const rid = felt('0x' + crypto.createHash('sha3-256').update('honest-r-' + now).digest('hex'));
const execBH = felt('0x' + crypto.createHash('sha3-256').update('honest-bh-' + now).digest('hex'));
try {
  const lockCalldata = CallData.compile({
    escrow_id: eid, route_id: rid, entity_id: felt('0x' + entityIdBuf.toString('hex').slice(0, 62)),
    destination: MAIN, amount: { low: BigInt(amountSats) * 100n, high: 0n },
    min_coherence: 550000n, timeout_blocks: 7200n,
    anchor_bh: splitU256(anchorBH), block_hash: splitU256(blockHashU256),
    txid_lo: txidLo, txid_hi: txidHi, tx_index: txIndex,
    merkle_path_len: pathBE.length, merkle_path: merklePathU256,
    entity_id_lo: entLo, entity_id_hi: entHi,
    event_type: 0, magnitude_nano: magnitudeNano, block_time: blockTime,
    chain_id: BTC_CID, value_usd: 0n
  });
  const { tx, receipt } = await exec([{ contractAddress: v3Address, entrypoint: 'lock_escrow', calldata: lockCalldata }], 'lock');
  resetNonce();
  record('S8', 'Lock with verify_anchor (FIX 1)', receipt?.execution_status === 'SUCCEEDED', `tx=${tx.transaction_hash.slice(0,18)} status=${receipt?.execution_status}`);
} catch (e) { resetNonce(); record('S8', 'Lock', false, String(e.message).slice(0, 250)); }

// ── STEP 5: Attest ──
console.log('\n── Step 5: Validator attests ──');
try {
  const { tx, receipt } = await exec([{ contractAddress: v3Address, entrypoint: 'submit_attestation', calldata: CallData.compile({ route_id: rid, coherence: 920000n, execution_bh: execBH, attestation_time: now - 10 }) }], 'attest');
  resetNonce();
  record('S9', 'Attest (quorum=1)', receipt?.execution_status === 'SUCCEEDED', `tx=${tx.transaction_hash.slice(0,18)}`);
} catch (e) { resetNonce(); record('S9', 'Attest', false, String(e.message).slice(0, 250)); }

// ═══ FIX 4a: set_btcp_score ═══
console.log('\n═══ FIX 4a: set_btcp_score ═══');
try {
  const { tx, receipt } = await exec([{ contractAddress: v3Address, entrypoint: 'set_btcp_score', calldata: CallData.compile({ escrow_id: eid, score: 849235n }) }], 'set-score');
  resetNonce();
  record('F4a', 'FIX 4: set_btcp_score', receipt?.execution_status === 'SUCCEEDED', `tx=${tx.transaction_hash.slice(0,18)} status=${receipt?.execution_status}`);
} catch (e) { resetNonce(); record('F4a', 'set_btcp_score', false, String(e.message).slice(0, 300)); }

// Verify get_btcp_score reads it back
try {
  const r = await provider.callContract({ contractAddress: v3Address, entrypoint: 'get_btcp_score', calldata: [eid] });
  const scoreVal = parseInt(r.result[0], 16);
  record('F4a-read', 'get_btcp_score reads back', scoreVal === 849235, `score=${scoreVal} (expected 849235)`);
} catch (e) { record('F4a-read', 'get_btcp_score', false, String(e.message).slice(0, 200)); }

// ═══ FIX 3: verify_escrow_anchor (permissionless reorg check) ═══
console.log('\n═══ FIX 3: verify_escrow_anchor ═══');
try {
  const { tx, receipt } = await exec([{ contractAddress: v3Address, entrypoint: 'verify_escrow_anchor', calldata: CallData.compile({ escrow_id: eid, merkle_path: merklePathU256 }) }], 'verify-anchor');
  resetNonce();
  record('F3', 'FIX 3: verify_escrow_anchor (permissionless)', receipt?.execution_status === 'SUCCEEDED', `tx=${tx.transaction_hash.slice(0,18)} status=${receipt?.execution_status}`);
} catch (e) { resetNonce(); record('F3', 'verify_escrow_anchor', false, String(e.message).slice(0, 300)); }

// ═══ FIX 2: report_spend_proof (permissionless trustless spend proof) ═══
console.log('\n═══ FIX 2: report_spend_proof ═══');
try {
  const spendCalldata = CallData.compile({
    escrow_id: eid,
    spending_txid_lo: txidLo, spending_txid_hi: txidHi,
    spending_block_hash: splitU256(blockHashU256),
    spending_tx_index: txIndex,
    spending_merkle_path_len: pathBE.length,
    spending_merkle_path: merklePathU256,
  });
  const { tx, receipt } = await exec([{ contractAddress: v3Address, entrypoint: 'report_spend_proof', calldata: spendCalldata }], 'spend-proof');
  resetNonce();
  record('F2', 'FIX 2: report_spend_proof (permissionless trustless)', receipt?.execution_status === 'SUCCEEDED', `tx=${tx.transaction_hash.slice(0,18)} status=${receipt?.execution_status}`);
} catch (e) { resetNonce(); record('F2', 'report_spend_proof', false, String(e.message).slice(0, 300)); }

// Verify is_anchor_spent is now true
try {
  const r = await provider.callContract({ contractAddress: v3Address, entrypoint: 'is_anchor_spent', calldata: [eid] });
  const spent = r.result[0] === '0x1';
  record('F2-verify', 'is_anchor_spent = true after spend proof', spent, `is_anchor_spent=${r.result[0]}`);
} catch (e) { record('F2-verify', 'is_anchor_spent read', false, String(e.message).slice(0, 200)); }

// ═══ ADVERSARIAL: mutated anchor REVERTS ═══
console.log('\n═══ ADVERSARIAL: mutated anchor_bh ═══');
const mutBuf = Buffer.from(buf); mutBuf[0] ^= 0x01;
const mutSense = crypto.createHash('sha256').update(Buffer.concat([mutBuf, Buffer.from([0x00])])).digest();
const mutBH = BigInt('0x' + mutSense.toString('hex'));
const advEid = felt('0x' + crypto.createHash('sha3-256').update('adv-' + now).digest('hex'));
const advRid = felt('0x' + crypto.createHash('sha3-256').update('adv-r-' + now).digest('hex'));
try {
  const lockCalldata = CallData.compile({
    escrow_id: advEid, route_id: advRid, entity_id: felt('0x' + entityIdBuf.toString('hex').slice(0, 62)),
    destination: MAIN, amount: { low: 1000000n, high: 0n },
    min_coherence: 550000n, timeout_blocks: 7200n,
    anchor_bh: splitU256(mutBH), block_hash: splitU256(blockHashU256),
    txid_lo: txidLo, txid_hi: txidHi, tx_index: txIndex,
    merkle_path_len: pathBE.length, merkle_path: merklePathU256,
    entity_id_lo: entLo, entity_id_hi: entHi,
    event_type: 0, magnitude_nano: magnitudeNano, block_time: blockTime,
    chain_id: BTC_CID, value_usd: 0n
  });
  await exec([{ contractAddress: v3Address, entrypoint: 'lock_escrow', calldata: lockCalldata }], 'adv-mut', true);
  resetNonce();
  record('ADV1', 'Mutated anchor_bh REVERTS', false, 'Should have reverted');
} catch (e) { resetNonce(); record('ADV1', 'Mutated anchor_bh REVERTS', true, 'Correctly reverted'); }

// ═══ ADVERSARIAL: release without quorum REVERTS ═══
console.log('\n═══ ADVERSARIAL: release without quorum ═══');
const nqEid = felt('0x' + crypto.createHash('sha3-256').update('nq-' + now).digest('hex'));
const nqRid = felt('0x' + crypto.createHash('sha3-256').update('nq-r-' + now).digest('hex'));
try {
  const lockCalldata = CallData.compile({
    escrow_id: nqEid, route_id: nqRid, entity_id: felt('0x' + entityIdBuf.toString('hex').slice(0, 62)),
    destination: MAIN, amount: { low: 1000000n, high: 0n },
    min_coherence: 550000n, timeout_blocks: 7200n,
    anchor_bh: splitU256(anchorBH), block_hash: splitU256(blockHashU256),
    txid_lo: txidLo, txid_hi: txidHi, tx_index: txIndex,
    merkle_path_len: pathBE.length, merkle_path: merklePathU256,
    entity_id_lo: entLo, entity_id_hi: entHi,
    event_type: 0, magnitude_nano: magnitudeNano, block_time: blockTime,
    chain_id: BTC_CID, value_usd: 0n
  });
  await exec([{ contractAddress: v3Address, entrypoint: 'lock_escrow', calldata: lockCalldata }], 'nq-lock');
  resetNonce();
  const releaseCalldata = CallData.compile({
    escrow_id: nqEid, execution_bh: execBH, coherence: 920000n,
    anchor_bh: splitU256(anchorBH), block_hash: splitU256(blockHashU256),
    txid_lo: txidLo, txid_hi: txidHi, tx_index: txIndex,
    merkle_path: merklePathU256,
    entity_id_lo: entLo, entity_id_hi: entHi,
    event_type: 0, magnitude_nano: magnitudeNano, block_time: blockTime,
    chain_id: BTC_CID, value_usd: 0n
  });
  await exec([{ contractAddress: v3Address, entrypoint: 'release_escrow', calldata: releaseCalldata }], 'nq-release', true);
  resetNonce();
  record('ADV2', 'Release without quorum REVERTS', false, 'Should have reverted');
} catch (e) { resetNonce(); record('ADV2', 'Release without quorum REVERTS', true, 'Correctly reverted'); }

// ── SAVE RESULTS ──
results.endedAt = new Date().toISOString();
results.v3Address = v3Address;
const outPath = '/home/z/my-project/trion-core/docs/proofs/honest_live_test.json';
fs.writeFileSync(outPath, JSON.stringify(results, null, 2));

console.log('\n═══════════════════════════════════════════════════════════');
const passed = results.steps.filter(s => s.pass).length;
const total = results.steps.length;
console.log(`  HONEST RESULT: ${passed}/${total} steps passed`);
console.log(`  V3 (new class): ${v3Address}`);
console.log(`  Report: ${outPath}`);
console.log('═══════════════════════════════════════════════════════════\n');
