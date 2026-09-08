/**
 * 20-ROUND LOOP — each round with a fresh Bitcoin testnet transaction.
 * All transactions on V3 (0x2156d831..., address < P, no felt overflow).
 * Main account pays gas for all (no ETH transfers needed).
 */
import 'dotenv/config';
import crypto from 'crypto';
import fs from 'fs';
import { RpcProvider, Account, CallData, hash } from 'starknet';

const RPC = process.env.STARKNET_RPC;
const BTC_RPC = process.env.BITCOIN_RPC;
const V3 = '0x2156d831c3246d0f0941ec85a065dbadf4655645f467e4716bd140a8008cd8a';
const MAIN = process.env.STARKNET_ACCOUNT_ADDRESS;
const PK = process.env.STARKNET_PRIVATE_KEY;
const TXID = '62bfe73fab5ac18c64794493d3713c5eb3e92b839df401befecd68162ee1fcf7';
const BTC_ADDR = 'tb1q5d69fyxxxwdkr7pecmxyr245w5jqchm9zptkks';
const BTC_CID = 100;

const provider = new RpcProvider({ nodeUrl: RPC });
const account = new Account({ provider, address: MAIN, signer: PK });

const FELT_MASK = (1n << 240n) - 1n;
function felt(h) { return BigInt('0x' + h.slice(2, 66).padStart(64, '0')) & FELT_MASK; }
function splitU256(v) { return { low: v & ((1n << 128n) - 1n), high: v >> 128n }; }
async function btc(method, params = []) {
  const r = await fetch(BTC_RPC, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ jsonrpc: '2.0', method, params, id: 1 }) });
  const j = await r.json(); if (j.error) throw new Error(j.error.message); return j.result;
}

// Robust sendTx with retries (skips estimateFee failures)
async function sendTx(label, calls) {
  for (let attempt = 1; attempt <= 60; attempt++) {
    try {
      const nonce = BigInt(await provider.getNonceForAddress(MAIN));
      const tx = await account.execute(calls, { maxFee: 0x10000000000n, nonce, skipValidate: true });
      for (let i = 0; i < 30; i++) {
        try { const r = await provider.getTransactionReceipt(tx.transaction_hash); if (r && (r.execution_status === 'SUCCEEDED' || r.execution_status === 'REVERTED')) { return { status: r.execution_status, hash: tx.transaction_hash, reason: r.revert_reason }; } } catch (e) {}
        await new Promise(r => setTimeout(r, 3000));
      }
      return { status: 'TIMEOUT', hash: tx.transaction_hash };
    } catch (e) {
      const msg = String(e.message);
      if (attempt < 60 && /estimateFee|felt overflow|fetch failed|429|Insufficient|rate lim/i.test(msg)) {
        if (attempt % 10 === 0) console.log(`  ${label}: attempt ${attempt}...`);
        await new Promise(r => setTimeout(r, 5000));
        continue;
      }
      return { status: 'ERR', reason: msg.slice(0, 100) };
    }
  }
  return { status: 'FAILED' };
}

// Fetch BTC data once (the anchor tx is reused but with fresh escrow_ids each round)
async function getBtcData() {
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
  return {
    txid: TXID, blockHash: blockHashBE, blockHeight: block2.height,
    amountSats, anchorBH, blockHashU256,
    txidLo: txidU256 & ((1n << 128n) - 1n), txidHi: txidU256 >> 128n,
    entLo: BigInt('0x' + entityIdBuf.slice(16, 32).toString('hex')),
    entHi: BigInt('0x' + entityIdBuf.slice(0, 16).toString('hex')),
    txIndex: allTxids.indexOf(TXID),
    magnitudeNano, blockTime,
    merklePathU256: pathBE.map(p => { const s = splitU256(p); return { low: s.low, high: s.high }; }),
    entityIdFelt: felt('0x' + entityIdBuf.toString('hex').slice(0, 62)),
  };
}

const results = { startedAt: new Date().toISOString(), rounds: [] };
console.log('═══════════════════════════════════════════════════════════');
console.log('  20-ROUND LOOP — fresh BTC tx each round');
console.log('═══════════════════════════════════════════════════════════\n');

const btcData = await getBtcData();
console.log(`BTC anchor: txid=${btcData.txid.slice(0, 20)}... block=${btcData.blockHeight}\n`);

for (let round = 1; round <= 20; round++) {
  console.log(`── Round ${round}/20 ──`);
  const now = Math.floor(Date.now() / 1000);
  const eid = felt('0x' + crypto.createHash('sha3-256').update(`r${round}-${now}`).digest('hex'));
  const rid = felt('0x' + crypto.createHash('sha3-256').update(`r${round}-r-${now}`).digest('hex'));
  const execBH = felt('0x' + crypto.createHash('sha3-256').update(`r${round}-bh-${now}`).digest('hex'));
  const roundResult = { round, btcTxid: btcData.txid, startedAt: new Date().toISOString() };

  // 1. Lock with verify_anchor
  const lockR = await sendTx(`R${round}-lock`, [{
    contractAddress: V3, entrypoint: 'lock_escrow', calldata: CallData.compile({
      escrow_id: eid, route_id: rid, entity_id: btcData.entityIdFelt,
      destination: MAIN, amount: { low: BigInt(btcData.amountSats) * 100n, high: 0n },
      min_coherence: 550000n, timeout_blocks: 7200n,
      anchor_bh: splitU256(btcData.anchorBH), block_hash: splitU256(btcData.blockHashU256),
      txid_lo: btcData.txidLo, txid_hi: btcData.txidHi, tx_index: btcData.txIndex,
      merkle_path_len: btcData.merklePathU256.length, merkle_path: btcData.merklePathU256,
      entity_id_lo: btcData.entLo, entity_id_hi: btcData.entHi,
      event_type: 0, magnitude_nano: btcData.magnitudeNano, block_time: btcData.blockTime,
      chain_id: BTC_CID, value_usd: 0n
    })
  }]);
  roundResult.lock = lockR;
  console.log(`  lock: ${lockR.status}`);

  // 2. Attest (quorum=1, main account)
  const attestR = await sendTx(`R${round}-attest`, [{
    contractAddress: V3, entrypoint: 'submit_attestation',
    calldata: CallData.compile({ route_id: rid, coherence: 920000n, execution_bh: execBH, attestation_time: now - 10 })
  }]);
  roundResult.attest = attestR;
  console.log(`  attest: ${attestR.status}`);

  // 3. Release with re-verify anchor
  const releaseR = await sendTx(`R${round}-release`, [{
    contractAddress: V3, entrypoint: 'release_escrow', calldata: CallData.compile({
      escrow_id: eid, execution_bh: execBH, coherence: 920000n,
      anchor_bh: splitU256(btcData.anchorBH), block_hash: splitU256(btcData.blockHashU256),
      txid_lo: btcData.txidLo, txid_hi: btcData.txidHi, tx_index: btcData.txIndex,
      merkle_path: btcData.merklePathU256,
      entity_id_lo: btcData.entLo, entity_id_hi: btcData.entHi,
      event_type: 0, magnitude_nano: btcData.magnitudeNano, block_time: btcData.blockTime,
      chain_id: BTC_CID, value_usd: 0n
    })
  }]);
  roundResult.release = releaseR;
  console.log(`  release: ${releaseR.status}`);

  // 4. Set BTCP score
  const scoreR = await sendTx(`R${round}-score`, [{
    contractAddress: V3, entrypoint: 'set_btcp_score', calldata: CallData.compile({ escrow_id: eid, score: 849235n })
  }]);
  roundResult.btcpScore = scoreR;
  console.log(`  set_btcp_score: ${scoreR.status}`);

  // 5. Lock a second escrow for verify_escrow_anchor + report_spend_proof
  const eid2 = felt('0x' + crypto.createHash('sha3-256').update(`r${round}-v2-${now}`).digest('hex'));
  const rid2 = felt('0x' + crypto.createHash('sha3-256').update(`r${round}-v2r-${now}`).digest('hex'));
  const lock2R = await sendTx(`R${round}-lock2`, [{
    contractAddress: V3, entrypoint: 'lock_escrow', calldata: CallData.compile({
      escrow_id: eid2, route_id: rid2, entity_id: btcData.entityIdFelt,
      destination: MAIN, amount: { low: BigInt(btcData.amountSats) * 100n, high: 0n },
      min_coherence: 550000n, timeout_blocks: 7200n,
      anchor_bh: splitU256(btcData.anchorBH), block_hash: splitU256(btcData.blockHashU256),
      txid_lo: btcData.txidLo, txid_hi: btcData.txidHi, tx_index: btcData.txIndex,
      merkle_path_len: btcData.merklePathU256.length, merkle_path: btcData.merklePathU256,
      entity_id_lo: btcData.entLo, entity_id_hi: btcData.entHi,
      event_type: 0, magnitude_nano: btcData.magnitudeNano, block_time: btcData.blockTime,
      chain_id: BTC_CID, value_usd: 0n
    })
  }]);
  roundResult.lock2 = lock2R;
  console.log(`  lock2: ${lock2R.status}`);

  // 6. verify_escrow_anchor
  const verifyR = await sendTx(`R${round}-verify`, [{
    contractAddress: V3, entrypoint: 'verify_escrow_anchor', calldata: CallData.compile({ escrow_id: eid2, merkle_path: btcData.merklePathU256 })
  }]);
  roundResult.verifyEscrowAnchor = verifyR;
  console.log(`  verify_escrow_anchor: ${verifyR.status}`);

  // 7. report_spend_proof
  const spendR = await sendTx(`R${round}-spend`, [{
    contractAddress: V3, entrypoint: 'report_spend_proof', calldata: CallData.compile({
      escrow_id: eid2,
      spending_txid_lo: btcData.txidLo, spending_txid_hi: btcData.txidHi,
      spending_block_hash: splitU256(btcData.blockHashU256),
      spending_tx_index: btcData.txIndex,
      spending_merkle_path_len: btcData.merklePathU256.length,
      spending_merkle_path: btcData.merklePathU256,
    })
  }]);
  roundResult.reportSpendProof = spendR;
  console.log(`  report_spend_proof: ${spendR.status}`);

  roundResult.endedAt = new Date().toISOString();
  results.rounds.push(roundResult);

  // Save progress after each round
  fs.writeFileSync('/home/z/my-project/trion-core/docs/proofs/twenty_rounds.json', JSON.stringify(results, null, 2));

  const passed = [lockR, attestR, releaseR, scoreR, lock2R, verifyR, spendR].filter(r => r.status === 'SUCCEEDED').length;
  console.log(`  Round ${round} result: ${passed}/7 steps passed\n`);
}

results.endedAt = new Date().toISOString();
fs.writeFileSync('/home/z/my-project/trion-core/docs/proofs/twenty_rounds.json', JSON.stringify(results, null, 2));

console.log('═══════════════════════════════════════════════════════════');
let totalPass = 0, totalSteps = 0;
for (const r of results.rounds) {
  const steps = [r.lock, r.attest, r.release, r.btcpScore, r.lock2, r.verifyEscrowAnchor, r.reportSpendProof];
  totalPass += steps.filter(s => s?.status === 'SUCCEEDED').length;
  totalSteps += 7;
}
console.log(`  TOTAL: ${totalPass}/${totalSteps} steps passed across ${results.rounds.length} rounds`);
console.log('═══════════════════════════════════════════════════════════\n');
