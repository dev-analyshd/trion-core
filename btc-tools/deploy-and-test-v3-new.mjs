import 'dotenv/config';
import crypto from 'crypto';
import { RpcProvider, Account, CallData, hash } from 'starknet';
import { makeExec } from './lib_patched_exec.mjs';

const RPC = process.env.STARKNET_RPC;
const BTC = process.env.BITCOIN_RPC;
const SPV_VERIFIER = '0x6510323e3ddd0c91d7c021200ec62c91605f528d1873eface5c0dc6258616c1';
const NEW_V3_CLASS = '0x4a603b5321ef2d5535d31040c5d63bfe3b2338a7f84fd3904b39d68ff7a4704';
const MAIN = process.env.STARKNET_ACCOUNT_ADDRESS;
const TXID = '62bfe73fab5ac18c64794493d3713c5eb3e92b839df401befecd68162ee1fcf7';
const BTC_ADDR = 'tb1q5d69fyxxxwdkr7pecmxyr245w5jqchm9zptkks';
const BTC_CID = 100;

const provider = new RpcProvider({ nodeUrl: RPC });
const account = new Account({ provider, address: MAIN, signer: process.env.STARKNET_PRIVATE_KEY });
const { exec, resetNonce } = await makeExec(provider, account, MAIN);

const FELT_MASK = (1n << 240n) - 1n;
function felt(h) { return BigInt('0x' + h.slice(2, 66).padStart(64, '0')) & FELT_MASK; }
function splitU256(v) { return { low: v & ((1n << 128n) - 1n), high: v >> 128n }; }
async function btc(method, params=[]) {
  const r = await fetch(BTC, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({jsonrpc:'2.0',method,params,id:1}) });
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

console.log('═══════════════════════════════════════════════════════════');
console.log('  DEPLOY NEW V3 (with all 4 fixes) + TEST');
console.log('═══════════════════════════════════════════════════════════\n');

// Deploy NEW V3 with the correct class hash
console.log('── Deploy NEW V3 (class hash with all 4 fixes) ──');
let v3Address;
for (let attempt = 1; attempt <= 5; attempt++) {
  try {
    const salt = '0x' + Math.floor(Math.random() * 1e9).toString(16);
    const deployRes = await account.deployContract({ classHash: NEW_V3_CLASS, constructorCalldata: CallData.compile({ owner: MAIN }), salt, unique: true });
    for (let i = 0; i < 60; i++) {
      try { const r = await provider.getTransactionReceipt(deployRes.transaction_hash); if (r && (r.execution_status === 'SUCCEEDED' || r.execution_status === 'REVERTED')) { console.log('  Deploy status:', r.execution_status); break; } } catch (e) {}
      await new Promise(r => setTimeout(r, 3000));
    }
    v3Address = deployRes.contract_address;
    console.log('  V3 deployed:', v3Address);
    break;
  } catch (e) { console.log(`  Attempt ${attempt} err: ${String(e.message).slice(0, 100)}`); await new Promise(r => setTimeout(r, 5000)); }
}

if (!v3Address) { console.log('FAILED to deploy V3'); process.exit(1); }

// Verify new functions exist
const code = await provider.getClassAt(v3Address);
const fns = (code.abi || []).filter(a => a.type === 'interface').flatMap(i => i.items || []).filter(i => i.type === 'function').map(f => f.name);
console.log('  report_spend_proof:', fns.includes('report_spend_proof') ? '✓' : '✗');
console.log('  verify_escrow_anchor:', fns.includes('verify_escrow_anchor') ? '✓' : '✗');
console.log('  set_btcp_score:', fns.includes('set_btcp_score') ? '✓' : '✗');
console.log('  get_btcp_score:', fns.includes('get_btcp_score') ? '✓' : '✗');

// Setup: set SPV, register validator, set quorum=1
await exec([{ contractAddress: v3Address, entrypoint: 'set_spv_verifier', calldata: CallData.compile({ spv: SPV_VERIFIER }) }], 'set-spv');
resetNonce();
await exec([{ contractAddress: v3Address, entrypoint: 'add_validator', calldata: CallData.compile({ validator: MAIN }) }], 'reg-val');
resetNonce();
await exec([{ contractAddress: v3Address, entrypoint: 'set_quorum_required', calldata: CallData.compile({ quorum: 1 }) }], 'set-q1');
resetNonce();
console.log('  SPV set, validator registered, quorum=1');

// Lock escrow
const eid = felt('0x' + crypto.createHash('sha3-256').update('final-' + now).digest('hex'));
const rid = felt('0x' + crypto.createHash('sha3-256').update('final-r-' + now).digest('hex'));
const execBH = felt('0x' + crypto.createHash('sha3-256').update('final-bh-' + now).digest('hex'));
console.log('\n── Lock escrow with SPV verify_anchor ──');
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
  const { receipt } = await exec([{ contractAddress: v3Address, entrypoint: 'lock_escrow', calldata: lockCalldata }], 'lock');
  resetNonce();
  console.log('  Lock:', receipt?.execution_status);
} catch (e) { resetNonce(); console.log('  Lock err:', String(e.message).slice(0, 150)); }

// Attest
try {
  await exec([{ contractAddress: v3Address, entrypoint: 'submit_attestation', calldata: CallData.compile({ route_id: rid, coherence: 920000n, execution_bh: execBH, attestation_time: now - 10 }) }], 'attest');
  resetNonce();
  console.log('  Attest: OK');
} catch (e) { resetNonce(); console.log('  Attest err:', String(e.message).slice(0, 100)); }

// FIX 4a: set_btcp_score
console.log('\n=== FIX 4a: set_btcp_score ===');
try {
  const { tx, receipt } = await exec([{ contractAddress: v3Address, entrypoint: 'set_btcp_score', calldata: CallData.compile({ escrow_id: eid, score: 849235n }) }], 'set-score');
  resetNonce();
  console.log('  PASS:', receipt?.execution_status, 'tx:', tx.transaction_hash.slice(0, 18));
} catch (e) { resetNonce(); console.log('  FAIL:', String(e.message).slice(0, 200)); }

// FIX 3: verify_escrow_anchor
console.log('\n=== FIX 3: verify_escrow_anchor (permissionless reorg check) ===');
try {
  const { tx, receipt } = await exec([{ contractAddress: v3Address, entrypoint: 'verify_escrow_anchor', calldata: CallData.compile({ escrow_id: eid, merkle_path: merklePathU256 }) }], 'verify-anchor');
  resetNonce();
  console.log('  PASS:', receipt?.execution_status, 'tx:', tx.transaction_hash.slice(0, 18));
} catch (e) { resetNonce(); console.log('  FAIL:', String(e.message).slice(0, 200)); }

// FIX 2: report_spend_proof
console.log('\n=== FIX 2: report_spend_proof (permissionless trustless spend proof) ===');
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
  console.log('  PASS:', receipt?.execution_status, 'tx:', tx.transaction_hash.slice(0, 18));
} catch (e) { resetNonce(); console.log('  FAIL:', String(e.message).slice(0, 300)); }

// FIX 4b: verify is_anchor_spent
console.log('\n=== FIX 4b: verify is_anchor_spent ===');
try {
  const r = await provider.callContract({ contractAddress: v3Address, entrypoint: 'is_anchor_spent', calldata: [eid] });
  console.log('  is_anchor_spent:', r.result[0], '(0x1 = spent/invalidated)');
} catch (e) { console.log('  FAIL:', String(e.message).slice(0, 150)); }

// FIX 4c: verify get_btcp_score
console.log('\n=== FIX 4c: verify get_btcp_score ===');
try {
  const r = await provider.callContract({ contractAddress: v3Address, entrypoint: 'get_btcp_score', calldata: [eid] });
  console.log('  btcp_score:', r.result[0], `(decimal: ${parseInt(r.result[0], 16)})`);
} catch (e) { console.log('  FAIL:', String(e.message).slice(0, 150)); }

console.log('\n═══════════════════════════════════════════════════════════');
console.log('  NEW V3 Address:', v3Address);
console.log('═══════════════════════════════════════════════════════════');
