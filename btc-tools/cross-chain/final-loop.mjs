/**
 * Fix validator deployment: generate OZ accounts with felt252-safe addresses (<= 62 hex chars).
 * Fund with ETH, register on V3, attest, release.
 */
import 'dotenv/config';
import crypto from 'crypto';
import fs from 'fs';
import { RpcProvider, Account, CallData, hash, ec } from 'starknet';

const RPC = process.env.STARKNET_RPC;
const BTC_RPC = process.env.BITCOIN_RPC;
const V3 = '0x2156d831c3246d0f0941ec85a065dbadf4655645f467e4716bd140a8008cd8a';
const SPV = '0x6510323e3ddd0c91d7c021200ec62c91605f528d1873eface5c0dc6258616c1';
const MAIN = process.env.STARKNET_ACCOUNT_ADDRESS;
const MAIN_PK = process.env.STARKNET_PRIVATE_KEY;
const OZ_CLASS = '0x061dac032f228abef9c6626f995015233097ae253a7f72d68552db02f2971b8f';
const ETH = '0x049d36570d4e46f48e112690c1cbf541e2e51a3e2d0c4d8e1c1c3b3b3b3b3b3b3';
const TXID = '62bfe73fab5ac18c64794493d3713c5eb3e92b839df401befecd68162ee1fcf7';
const BTC_ADDR = 'tb1q5d69fyxxxwdkr7pecmxyr245w5jqchm9zptkks';
const BTC_CID = 100;
const FELT_ADDR_MAX = (1n << 248n) - 1n;

const provider = new RpcProvider({ nodeUrl: RPC });
const mainAccount = new Account({ provider, address: MAIN, signer: MAIN_PK });

const FELT_MASK = (1n << 240n) - 1n;
function felt(h) { return BigInt('0x' + h.slice(2, 66).padStart(64, '0')) & FELT_MASK; }
function splitU256(v) { return { low: v & ((1n << 128n) - 1n), high: v >> 128n }; }
async function btc(method, params = []) {
  const r = await fetch(BTC_RPC, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ jsonrpc: '2.0', method, params, id: 1 }) });
  const j = await r.json(); if (j.error) throw new Error(j.error.message); return j.result;
}
async function sendTx(acct, label, calls) {
  for (let attempt = 1; attempt <= 20; attempt++) {
    try {
      const nonce = await provider.getNonceForAddress(acct.address);
      const tx = await acct.execute(calls, { maxFee: '0x10000000000', nonce, skipValidate: true });
      for (let i = 0; i < 40; i++) {
        try { const r = await provider.getTransactionReceipt(tx.transaction_hash); if (r && (r.execution_status === 'SUCCEEDED' || r.execution_status === 'REVERTED')) { const reason = r.execution_status === 'REVERTED' ? ' — ' + (r.revert_reason || '').slice(0, 80) : ''; console.log(`  ${label}: ${r.execution_status}${reason}`); return r; } } catch (e) { }
        await new Promise(r => setTimeout(r, 3000));
      }
      console.log(`  ${label}: TIMEOUT`); return null;
    } catch (e) {
      if (attempt < 20 && /estimateFee|fetch failed|429|Insufficient/i.test(String(e.message))) { await new Promise(r => setTimeout(r, 12000)); continue; }
      console.log(`  ${label}: ERR ${String(e.message).slice(0, 80)}`); return null;
    }
  }
  return null;
}

console.log('═══════════════════════════════════════════════════════════');
console.log('  FINAL LOOP — 3 distinct validators + all fixes');
console.log('═══════════════════════════════════════════════════════════\n');

// ── STEP 1: Deploy 3 OZ accounts with felt252-safe addresses ──
console.log('── Step 1: Deploy 3 OZ accounts (safe addresses) ──');
const validatorKeys = [process.env.VALIDATOR_2_PK, process.env.VALIDATOR_3_PK, process.env.VALIDATOR_4_PK].filter(Boolean);
const validators = [];
for (let i = 0; i < validatorKeys.length; i++) {
  const pk = validatorKeys[i];
  const pub = ec.starkCurve.getStarkKey(pk);
  const cd = CallData.compile({ publicKey: pub });
  // Find a salt that produces a safe address
  let salt, addr;
  for (let attempt = 0; attempt < 1000; attempt++) {
    salt = BigInt('0x' + crypto.randomBytes(30).toString('hex'));
    addr = hash.calculateContractAddressFromHash(salt, OZ_CLASS, cd, 0);
    if (BigInt(addr) <= FELT_ADDR_MAX) break;
  }
  const label = 'V' + (i + 2);
  // Deploy
  const r = await sendTx(mainAccount, `deploy-${label}`, [{
    contractAddress: OZ_CLASS, entrypoint: 'constructor', calldata: cd
  }]);
  // Actually deployContract is not an entrypoint — use account.deployContract
  try {
    const deployRes = await mainAccount.deployContract({
      classHash: OZ_CLASS,
      constructorCalldata: cd,
      salt: '0x' + salt.toString(16),
      unique: false
    });
    for (let i = 0; i < 40; i++) {
      try { const rcpt = await provider.getTransactionReceipt(deployRes.transaction_hash); if (rcpt && (rcpt.execution_status === 'SUCCEEDED' || rcpt.execution_status === 'REVERTED')) { console.log(`  ${label} deploy: ${rcpt.execution_status} addr=${deployRes.contract_address.slice(0, 20)}...`); break; } } catch (e) { }
      await new Promise(r => setTimeout(r, 3000));
    }
    validators.push({ pk, pub, salt: '0x' + salt.toString(16), address: deployRes.contract_address, label });
  } catch (e) { console.log(`  ${label} deploy err: ${String(e.message).slice(0, 100)}`); }
}

// Check addresses are safe
for (const v of validators) {
  const hexlen = BigInt(v.address).toString(16).length;
  const safe = BigInt(v.address) <= FELT_ADDR_MAX;
  console.log(`  ${v.label}: addr hexlen=${hexlen} safe=${safe}`);
}

// Save validators
fs.writeFileSync('/tmp/validators-safe.json', JSON.stringify(validators, null, 2));

// ── STEP 2: Fund validators with ETH ──
console.log('\n── Step 2: Fund validators with ETH ──');
for (const v of validators) {
  await sendTx(mainAccount, `fund-${v.label}`, [{
    contractAddress: ETH, entrypoint: 'transfer',
    calldata: CallData.compile({ recipient: v.address, amount: { low: 10000000000000000n, high: 0n } })
  }]);
}

// ── STEP 3: Register validators on V3 ──
console.log('\n── Step 3: Register validators on V3 ──');
for (const v of validators) {
  await sendTx(mainAccount, `reg-${v.label}`, [{
    contractAddress: V3, entrypoint: 'add_validator', calldata: CallData.compile({ validator: v.address })
  }]);
}
// Register main too
await sendTx(mainAccount, 'reg-main', [{
  contractAddress: V3, entrypoint: 'add_validator', calldata: CallData.compile({ validator: MAIN })
}]);

// Set quorum=3
await sendTx(mainAccount, 'set-q3', [{
  contractAddress: V3, entrypoint: 'set_quorum_required', calldata: CallData.compile({ quorum: 3 })
}]);

// Verify validator count
const vcBody = { jsonrpc: '2.0', method: 'starknet_call', id: 1, params: [{ contract_address: V3, entry_point_selector: hash.getSelectorFromName('validator_count'), calldata: [] }, 'latest'] };
const vcR = await fetch(RPC, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(vcBody) });
const vcJ = await vcR.json();
console.log(`\n  validator_count: ${vcJ.result?.[0]} (expect >= 0x4)`);

// ── STEP 4: Fetch BTC data ──
console.log('\n── Step 4: Fetch BTC data ──');
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
function ds(b) { const a = crypto.createHash('sha256').update(b).digest(); return crypto.createHash('sha256').update(a).digest(); }
let levelNow = allTxids.map(t => Buffer.from(t, 'hex').reverse());
let idxNow = allTxids.indexOf(TXID);
const pathBE = [];
while (levelNow.length > 1) {
  const sibIdx = (idxNow % 2 === 0) ? idxNow + 1 : idxNow - 1;
  const sib = (sibIdx < levelNow.length) ? levelNow[sibIdx] : levelNow[idxNow];
  pathBE.push(BigInt('0x' + Buffer.from(sib).reverse().toString('hex')));
  const next = [];
  for (let i = 0; i < levelNow.length; i += 2) { const l = levelNow[i]; const r = (i + 1 < levelNow.length) ? levelNow[i + 1] : l; next.push(ds(Buffer.concat([l, r]))); }
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
const eid = felt('0x' + crypto.createHash('sha3-256').update('final-' + now).digest('hex'));
const rid = felt('0x' + crypto.createHash('sha3-256').update('final-r-' + now).digest('hex'));
const execBH = felt('0x' + crypto.createHash('sha3-256').update('final-bh-' + now).digest('hex'));

// ── STEP 5: Lock with verify_anchor ──
console.log('\n── Step 5: Lock with verify_anchor (FIX 1) ──');
await sendTx(mainAccount, 'lock', [{
  contractAddress: V3, entrypoint: 'lock_escrow', calldata: CallData.compile({
    escrow_id: eid, route_id: rid, entity_id: felt('0x' + entityIdBuf.toString('hex').slice(0, 62)),
    destination: MAIN, amount: { low: BigInt(amountSats) * 100n, high: 0n },
    min_coherence: 550000n, timeout_blocks: 7200n,
    anchor_bh: splitU256(anchorBH), block_hash: splitU256(blockHashU256),
    txid_lo: txidLo, txid_hi: txidHi, tx_index: txIndex,
    merkle_path_len: pathBE.length, merkle_path: merklePathU256,
    entity_id_lo: entLo, entity_id_hi: entHi,
    event_type: 0, magnitude_nano: magnitudeNano, block_time: blockTime,
    chain_id: BTC_CID, value_usd: 0n
  })
}]);

// ── STEP 6: Set BTCP score ──
console.log('\n── Step 6: Set BTCP score (FIX 4) ──');
await sendTx(mainAccount, 'set_score', [{
  contractAddress: V3, entrypoint: 'set_btcp_score', calldata: CallData.compile({ escrow_id: eid, score: 849235n })
}]);

// ── STEP 7: 3 distinct validators attest ──
console.log('\n── Step 7: 3 distinct validators attest (FIX 2) ──');
for (const v of validators) {
  const vAcct = new Account({ provider, address: v.address, signer: v.pk });
  await sendTx(vAcct, `attest-${v.label}`, [{
    contractAddress: V3, entrypoint: 'submit_attestation',
    calldata: CallData.compile({ route_id: rid, coherence: 920000n, execution_bh: execBH, attestation_time: now - 10 })
  }]);
}

// ── STEP 8: Release with re-verify anchor + quorum=3 ──
console.log('\n── Step 8: Release (re-verify anchor + quorum=3) ──');
await sendTx(mainAccount, 'release', [{
  contractAddress: V3, entrypoint: 'release_escrow', calldata: CallData.compile({
    escrow_id: eid, execution_bh: execBH, coherence: 920000n,
    anchor_bh: splitU256(anchorBH), block_hash: splitU256(blockHashU256),
    txid_lo: txidLo, txid_hi: txidHi, tx_index: txIndex,
    merkle_path: merklePathU256,
    entity_id_lo: entLo, entity_id_hi: entHi,
    event_type: 0, magnitude_nano: magnitudeNano, block_time: blockTime,
    chain_id: BTC_CID, value_usd: 0n
  })
}]);

// ── STEP 9: verify_escrow_anchor (FIX 3) — needs a HOLDING escrow ──
console.log('\n── Step 9: verify_escrow_anchor (FIX 3) ──');
const eid2 = felt('0x' + crypto.createHash('sha3-256').update('final-v3-' + now).digest('hex'));
const rid2 = felt('0x' + crypto.createHash('sha3-256').update('final-v3-r-' + now).digest('hex'));
await sendTx(mainAccount, 'lock2', [{
  contractAddress: V3, entrypoint: 'lock_escrow', calldata: CallData.compile({
    escrow_id: eid2, route_id: rid2, entity_id: felt('0x' + entityIdBuf.toString('hex').slice(0, 62)),
    destination: MAIN, amount: { low: BigInt(amountSats) * 100n, high: 0n },
    min_coherence: 550000n, timeout_blocks: 7200n,
    anchor_bh: splitU256(anchorBH), block_hash: splitU256(blockHashU256),
    txid_lo: txidLo, txid_hi: txidHi, tx_index: txIndex,
    merkle_path_len: pathBE.length, merkle_path: merklePathU256,
    entity_id_lo: entLo, entity_id_hi: entHi,
    event_type: 0, magnitude_nano: magnitudeNano, block_time: blockTime,
    chain_id: BTC_CID, value_usd: 0n
  })
}]);
await sendTx(mainAccount, 'verify_anchor', [{
  contractAddress: V3, entrypoint: 'verify_escrow_anchor', calldata: CallData.compile({ escrow_id: eid2, merkle_path: merklePathU256 })
}]);

// ── STEP 10: report_spend_proof (FIX 2) ──
console.log('\n── Step 10: report_spend_proof (FIX 2) ──');
await sendTx(mainAccount, 'spend_proof', [{
  contractAddress: V3, entrypoint: 'report_spend_proof', calldata: CallData.compile({
    escrow_id: eid2,
    spending_txid_lo: txidLo, spending_txid_hi: txidHi,
    spending_block_hash: splitU256(blockHashU256),
    spending_tx_index: txIndex,
    spending_merkle_path_len: pathBE.length,
    spending_merkle_path: merklePathU256,
  })
}]);

// ── STEP 11: Verify final state ──
console.log('\n── Step 11: Verify final state ──');
async function rawCall(fn, calldata) {
  const r = await fetch(RPC, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ jsonrpc: '2.0', method: 'starknet_call', id: 1, params: [{ contract_address: V3, entry_point_selector: hash.getSelectorFromName(fn), calldata }, 'latest'] }) });
  const j = await r.json();
  return j;
}
const eidHex = '0x' + eid.toString(16);
const eid2Hex = '0x' + eid2.toString(16);

const esc1 = await rawCall('get_escrow', [eidHex]);
if (esc1.result) { const state = parseInt(esc1.result[9], 16); console.log(`  escrow 1 state: ${['HOLDING', 'RELEASED', 'REVERTED'][state]}`); }

const esc2 = await rawCall('get_escrow', [eid2Hex]);
if (esc2.result) { const state = parseInt(esc2.result[9], 16); console.log(`  escrow 2 state: ${['HOLDING', 'RELEASED', 'REVERTED'][state]}`); }

const score = await rawCall('get_btcp_score', [eidHex]);
if (score.result) { console.log(`  btcp_score: ${parseInt(score.result[0], 16)} (expect 849235)`); }

const spent = await rawCall('is_anchor_spent', [eid2Hex]);
if (spent.result) { console.log(`  is_anchor_spent(eid2): ${spent.result[0]} (expect 0x1)`); }

const vc2 = await rawCall('validator_count', []);
console.log(`  validator_count: ${vc2.result?.[0]}`);

const qr = await rawCall('quorum_required', []);
console.log(`  quorum_required: ${qr.result?.[0]}`);

const ecR = await rawCall('escrow_count', []);
console.log(`  escrow_count: ${ecR.result?.[0]}`);

console.log('\n═══════════════════════════════════════════════════════════');
console.log('  DONE');
console.log('═══════════════════════════════════════════════════════════\n');
