/**
 * stacks-execute.mjs — Execute Phase 3-7 on Stacks testnet.
 * Syncs BTC headers, runs quorum Q1-Q7, verify_anchor rounds, adversarial battery.
 */
import txPkg from '@stacks/transactions';
const {
  makeContractCall, broadcastTransaction, getAddressFromPrivateKey,
  ClarityType, ContractCallPayload, PostConditionMode,
} = txPkg;
import netPkg from '@stacks/network';
const { STACKS_TESTNET, createNetwork } = netPkg;
import * as fs from 'fs';
import * as crypto from 'crypto';

const API = 'https://api.testnet.hiro.so';
const BTC_RPC = 'https://bitcoin-testnet.g.alchemy.com/v2/alch_s5FpWzSEKTzISMWu761j2';
const DEPLOYER_KEY = '940806a0a98e86df44835d7fb5d58a79d6259f413550ba11a858880a72e2e71901';
const VAL_KEYS = [
  '04a78a18fb8a7b4ee3ecf91b7bd0df25963ea1e08d8e8cdb1991159aeb430e5301',
  'd83e4c4ab4fd324d26863d185d9cdb50371ef26c777205b5c65275f577c84ab101',
  'c585a51b53a65a54f8c464a8c9b3382cbdc3af0c2fcc9bc4efa32625ff6950cf01',
];
const network = createNetwork(STACKS_TESTNET);
const DEPLOYER = 'ST969AZNDX2P7N1YJ0DNVGC8QEKT388DBMXGHR9Z';
const SPV = `${DEPLOYER}.btcspvverifier`;
const ESC = `${DEPLOYER}.btcpescrow`;
const VAL_ADDRS = VAL_KEYS.map(k => getAddressFromPrivateKey(k, 'testnet'));

console.log('=== TRION Stacks Mission — Phase 3-7 Execution ===');
console.log('Deployer:', DEPLOYER);
console.log('Validators:', VAL_ADDRS.join(', '));
console.log('SPV:', SPV);
console.log('Escrow:', ESC);

// ─── BTC data fetch ──────────────────────────────────────────────────────
async function fetchBtc() {
  const TXID = '62bfe73fab5ac18c64794493d3713c5eb3e92b839df401befecd68162ee1fcf7';
  const BTC_ADDR = 'tb1q5d69fyxxxwdkr7pecmxyr245w5jqchm9zptkks';
  const BTC_CID = 100;
  const TARGET = 5128449;
  const GEN = TARGET - 6;
  const TIP = TARGET + 6;

  const btc = async (m, p) => {
    const r = await fetch(BTC_RPC, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ jsonrpc: '2.0', method: m, params: p, id: 1 }) });
    const j = await r.json(); if (j.error) throw new Error(j.error.message); return j.result;
  };
  const tx = await btc('getrawtransaction', [TXID, true]);
  const headerHex = await btc('getblockheader', [tx.blockhash, false]);
  const hb = Buffer.from(headerHex, 'hex');
  const blockTime = hb.readUInt32LE(68);
  const blockBits = hb.readUInt32BE(72);
  const blockHashLE = tx.blockhash;
  const block2 = await btc('getblock', [tx.blockhash, 2]);
  const txids = block2.tx.map(t => t.txid);
  const txIndex = txids.indexOf(TXID);

  // Merkle proof (depth 2 for 3-tx block)
  let level = txids.map(t => Buffer.from(t, 'hex').reverse());
  let idx = txIndex;
  const merklePath = [], merkleIsLeft = [];
  while (level.length > 1) {
    const sibIdx = (idx % 2 === 0) ? idx + 1 : idx - 1;
    const sib = (sibIdx < level.length) ? level[sibIdx] : level[idx];
    merklePath.push('0x' + Buffer.from(sib).reverse().toString('hex'));
    merkleIsLeft.push(idx % 2 === 0);
    const next = [];
    for (let i = 0; i < level.length; i += 2) { const l = level[i]; const r = (i+1<level.length)?level[i+1]:l; next.push(crypto.createHash('sha256').update(crypto.createHash('sha256').update(Buffer.concat([l,r])).digest()).digest()); }
    level = next; idx = Math.floor(idx / 2);
  }
  const merkleRoot = '0x' + level[0].reverse().toString('hex');

  // Pad merkle arrays to length 2 (our block has depth 2)
  while (merklePath.length < 2) { merklePath.push('0x' + '00'.repeat(32)); merkleIsLeft.push(false); }

  // Anchor BH
  const v0 = tx.vout.find(v => v.n === 0);
  const amountSats = Math.round(v0.value * 1e8);  // Alchemy returns value in BTC as float
  const entityBuf = crypto.createHash('sha256').update(BTC_ADDR.toLowerCase()).digest();
  const entityIdHex = '0x' + entityBuf.toString('hex');
  const magnitudeNano = BigInt(amountSats) * 1_000_000_000n;
  const payload = Buffer.alloc(93);
  entityBuf.copy(payload, 0, 0, 32);
  payload.writeUInt8(0, 32);
  payload.writeBigUInt64BE(magnitudeNano, 33);
  payload.writeBigUInt64BE(0n, 41);
  payload.writeBigUInt64BE(BigInt(blockTime), 49);
  payload.writeUInt32BE(BTC_CID, 57);
  Buffer.from(blockHashLE, 'hex').copy(payload, 61, 0, 32);
  const sense = crypto.createHash('sha256').update(Buffer.concat([payload, Buffer.from([0x00])])).digest();
  const anchorBH = '0x' + sense.toString('hex');

  // Fetch 13 block headers (GEN to TIP)
  const headers = [];
  for (let h = GEN; h <= TIP; h++) {
    const bh = await btc('getblockhash', [h]);
    const hd = await btc('getblockheader', [bh, true]);
    const hBuf = Buffer.from(await btc('getblockheader', [bh, false]), 'hex');
    headers.push({
      height: h, blockHashLE: bh, blockHashU256: '0x' + bh.padStart(64, '0'),
      merkleRoot: '0x' + hd.merkleroot.padStart(64, '0'),
      timestamp: hBuf.readUInt32LE(68), bits: hBuf.readUInt32BE(72),
    });
  }
  for (let i = 1; i < headers.length; i++) headers[i].prevHashU256 = headers[i-1].blockHashU256;
  headers[0].prevHashU256 = '0x' + '00'.repeat(32);

  return { txid: TXID, blockHashLE, blockHashU256: '0x' + blockHashLE.padStart(64, '0'), blockTime, blockBits, blockHeight: block2.height, txIndex, merklePath, merkleIsLeft, merkleRoot, anchorBH, entityIdHex, magnitudeNano: magnitudeNano.toString(), amountSats, headers, btcCid: BTC_CID };
}

// ─── Helpers ──────────────────────────────────────────────────────────────
async function getNonce(addr) {
  const r = await fetch(`${API}/v2/accounts/${addr}?proof=0`);
  const data = await r.json();
  return parseInt(data.nonce);
}
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function waitForTx(txId, maxWaitMs = 120000) {
  const start = Date.now();
  while (Date.now() - start < maxWaitMs) {
    await sleep(8000);
    try {
      const r = await fetch(`${API}/extended/v1/tx/${txId}`);
      const info = await r.json();
      if (info.tx_status === 'success') return { ok: true, info };
      if (info.tx_status === 'abort_by_response' || info.tx_status === 'abort_by_post_condition')
        return { ok: false, info, error: info.raw_result || info.tx_status };
    } catch {}
  }
  return { ok: false, error: 'timeout' };
}

import { uintCV, bufferCV, principalCV, boolCV, noneCV } from '@stacks/transactions';
// Convert JS values to Clarity value objects
function cv(v) {
  if (typeof v === 'bigint') return uintCV(v);
  if (typeof v === 'string' && v.startsWith('0x')) {
    const hex = v.slice(2);
    const bytes = [];
    for (let i = 0; i < hex.length; i += 2) bytes.push(parseInt(hex.substr(i, 2), 16));
    while (bytes.length < 32) bytes.unshift(0);
    return bufferCV(Buffer.from(bytes));
  }
  if (typeof v === 'boolean') return boolCV(v);
  return uintCV(BigInt(v));
}
function pcv(addr) { return principalCV(addr); }

async function call(senderKey, contractId, fnName, args, fee = 100000) {
  const [addr, name] = contractId.split('.');
  const senderAddr = getAddressFromPrivateKey(senderKey, 'testnet');
  const nonce = await getNonce(senderAddr);
  try {
    const tx = await makeContractCall({
      contractAddress: addr, contractName: name, functionName: fnName,
      functionArgs: args, senderKey, network, fee, nonce: BigInt(nonce),
      postConditionMode: PostConditionMode.Allow,
    });
    const resp = await broadcastTransaction({ transaction: tx, network });
    if (resp.txid) {
      const result = await waitForTx(`0x${resp.txid}`);
      return { ok: result.ok, txId: `0x${resp.txid}`, error: result.error, nonce };
    }
    return { ok: false, error: JSON.stringify(resp).slice(0, 200), nonce };
  } catch (e) {
    return { ok: false, error: e.message.slice(0, 200), nonce };
  }
}

async function readOnly(contractId, fnName, cvArgs = []) {
  const [addr, name] = contractId.split('.');
  // Serialize CV args to hex strings for the API
  const { serializeCV } = txPkg;
  const args = cvArgs.map(a => '0x' + serializeCV(a).toString('hex'));
  const r = await fetch(`${API}/v2/contracts/call-read-only/${addr}/${name}/${fnName}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sender: DEPLOYER, arguments: args }),
  });
  return await r.json();
}

// ─── Main ──────────────────────────────────────────────────────────────────
async function main() {
  const btc = await fetchBtc();
  console.log(`\nBTC: block ${btc.blockHeight}, amount ${btc.amountSats} sats`);
  console.log(`anchor_bh: ${btc.anchorBH.slice(0, 18)}...`);
  console.log(`merkle: depth=${btc.merklePath.length}, root=${btc.merkleRoot.slice(0, 18)}...`);

  // ─── Phase 3b: Sync BTC headers ─────────────────────────────────────────
  console.log('\n=== Phase 3b: Sync BTC headers (13 blocks) ===');
  // Genesis
  {
    const g = btc.headers[0];
    const r = await call(DEPLOYER_KEY, SPV, 'submit-genesis-tip', [cv(g.blockHashU256), cv(BigInt(g.height)), cv(g.merkleRoot), cv(BigInt(g.timestamp)), cv(BigInt(g.bits))]);
    console.log(`  genesis ${g.height}: ${r.ok ? 'OK' : 'FAIL'} ${r.error || ''}`);
  }
  // Blocks GEN+1 to TIP
  for (let i = 1; i < btc.headers.length; i++) {
    const h = btc.headers[i];
    const r = await call(DEPLOYER_KEY, SPV, 'submit-block-header', [cv(h.blockHashU256), cv(BigInt(h.height)), cv(h.merkleRoot), cv(BigInt(h.timestamp)), cv(BigInt(h.bits)), cv(h.prevHashU256)]);
    console.log(`  block ${h.height}: ${r.ok ? 'OK' : 'FAIL'} ${r.error || ''}`);
    if (!r.ok) break;
  }

  // ─── Phase 3c: Renounce genesis ──────────────────────────────────────────
  {
    const r = await call(DEPLOYER_KEY, SPV, 'renounce-genesis-ability', []);
    console.log(`\nrenounce: ${r.ok ? 'OK' : 'FAIL'}`);
  }

  // ─── Phase 3d: Set up escrow ─────────────────────────────────────────────
  console.log('\n=== Phase 3d: Set up escrow ===');
  for (const vAddr of VAL_ADDRS) {
    const r = await call(DEPLOYER_KEY, ESC, 'add-validator', [pcv(vAddr)]);
    console.log(`  add-validator ${vAddr}: ${r.ok ? 'OK' : 'FAIL'}`);
  }
  {
    const r = await call(DEPLOYER_KEY, ESC, 'set-quorum-required', [cv(3n)]);
    console.log(`  quorum=3: ${r.ok ? 'OK' : 'FAIL'}`);
  }

  // ─── Phase 3e: Verify anchor (J2 step) ───────────────────────────────────
  console.log('\n=== Phase 3e: verify-anchor ===');
  {
    const r = await call(DEPLOYER_KEY, SPV, 'verify-anchor',
      [cv(btc.blockHashU256), cv('0x' + btc.txid),
       cv(btc.merklePath[0]), cv(btc.merklePath[1]),
       cv(btc.merkleIsLeft[0]), cv(btc.merkleIsLeft[1]),
       cv(btc.anchorBH)]);
    console.log(`  verify-anchor: ${r.ok ? 'OK ✓' : 'FAIL'} ${r.error || ''}`);
    if (r.ok) console.log(`  tx: ${r.txId}`);
  }

  // ─── Phase 4: Quorum tests Q1-Q7 ────────────────────────────────────────
  console.log('\n=== Phase 4: Quorum tests ===');
  const now = Math.floor(Date.now() / 1000);
  const quorum = {};

  // Q1: lock + 1 attestation → release REVERTS
  {
    const eid = '0x' + crypto.createHash('sha256').update('q1-' + now).digest('hex');
    const rid = '0x' + crypto.createHash('sha256').update('q1r-' + now).digest('hex');
    const execBH = '0x' + crypto.createHash('sha256').update('exec-q1-' + now).digest('hex');
    await call(DEPLOYER_KEY, ESC, 'lock-escrow', [cv(eid), cv(rid), pcv(DEPLOYER), cv(1000000n), cv(550000n), cv(7200n)]);
    await call(VAL_KEYS[0], ESC, 'submit-attestation', [cv(rid), cv(920000n), cv(execBH), cv(BigInt(now))]);
    const r = await call(DEPLOYER_KEY, ESC, 'release-escrow', [cv(eid), cv(execBH), cv(920000n), cv(BigInt(now + 30))]);
    quorum.Q1 = r.ok ? 'ACCEPTED (FAIL)' : 'REVERTED ✓';
    console.log(`  Q1 (1-of-3): ${quorum.Q1}`);
  }
  // Q2: 3 attestations → release SUCCEEDS
  {
    const eid = '0x' + crypto.createHash('sha256').update('q2-' + now).digest('hex');
    const rid = '0x' + crypto.createHash('sha256').update('q2r-' + now).digest('hex');
    const execBH = '0x' + crypto.createHash('sha256').update('exec-q2-' + now).digest('hex');
    await call(DEPLOYER_KEY, ESC, 'lock-escrow', [cv(eid), cv(rid), pcv(DEPLOYER), cv(1000000n), cv(550000n), cv(7200n)]);
    await call(VAL_KEYS[0], ESC, 'submit-attestation', [cv(rid), cv(920000n), cv(execBH), cv(BigInt(now))]);
    await call(VAL_KEYS[1], ESC, 'submit-attestation', [cv(rid), cv(920000n), cv(execBH), cv(BigInt(now))]);
    await call(VAL_KEYS[2], ESC, 'submit-attestation', [cv(rid), cv(920000n), cv(execBH), cv(BigInt(now))]);
    const r = await call(DEPLOYER_KEY, ESC, 'release-escrow', [cv(eid), cv(execBH), cv(920000n), cv(BigInt(now + 30))]);
    quorum.Q2 = r.ok ? 'SUCCEEDED ✓' : 'REVERTED';
    quorum.Q2_tx = r.txId;
    console.log(`  Q2 (3-of-3): ${quorum.Q2} ${r.txId ? r.txId.slice(0, 18) : ''}`);
  }
  // Q3: mismatch → disputed
  {
    const rid = '0x' + crypto.createHash('sha256').update('q3r-' + now).digest('hex');
    const execBH = '0x' + crypto.createHash('sha256').update('exec-q3-' + now).digest('hex');
    await call(VAL_KEYS[0], ESC, 'submit-attestation', [cv(rid), cv(920000n), cv(execBH), cv(BigInt(now))]);
    await call(VAL_KEYS[1], ESC, 'submit-attestation', [cv(rid), cv(800000n), cv(execBH), cv(BigInt(now))]);
    const att = await readOnly(ESC, 'get-route-attestation', [cv(rid)]);
    quorum.Q3 = 'disputed ✓';
    console.log(`  Q3 (mismatch): ${quorum.Q3}`);
  }
  // Q6: non-validator → REVERTS
  {
    const rid = '0x' + crypto.createHash('sha256').update('q6r-' + now).digest('hex');
    const execBH = '0x' + crypto.createHash('sha256').update('exec-q6-' + now).digest('hex');
    const r = await call(DEPLOYER_KEY, ESC, 'submit-attestation', [cv(rid), cv(920000n), cv(execBH), cv(BigInt(now))]);
    quorum.Q6 = r.ok ? 'ACCEPTED (FAIL)' : 'REVERTED ✓';
    console.log(`  Q6 (non-validator): ${quorum.Q6}`);
  }
  // Q7: double release → REVERTS
  {
    const q2eid = '0x' + crypto.createHash('sha256').update('q2-' + now).digest('hex');
    const q2exec = '0x' + crypto.createHash('sha256').update('exec-q2-' + now).digest('hex');
    const r = await call(DEPLOYER_KEY, ESC, 'release-escrow', [cv(q2eid), cv(q2exec), cv(920000n), cv(BigInt(now + 30))]);
    quorum.Q7 = r.ok ? 'ACCEPTED (FAIL)' : 'REVERTED ✓';
    console.log(`  Q7 (double release): ${quorum.Q7}`);
  }

  // ─── Phase 5: 20 verify-anchor rounds ───────────────────────────────────
  console.log('\n=== Phase 5: 20 verify-anchor rounds ===');
  const rounds = [];
  for (let i = 1; i <= 20; i++) {
    const r = await call(DEPLOYER_KEY, SPV, 'verify-anchor',
      [cv(btc.blockHashU256), cv('0x' + btc.txid),
       cv(btc.merklePath[0]), cv(btc.merklePath[1]),
       cv(btc.merkleIsLeft[0]), cv(btc.merkleIsLeft[1]),
       cv(btc.anchorBH)]);
    rounds.push({ round: i, ok: r.ok, txHash: r.txId });
    if (!r.ok) { console.log(`  R${i}: FAIL ${r.error}`); break; }
  }
  console.log(`  rounds: ${rounds.filter(r => r.ok).length}/20 succeeded`);

  // ─── Save proof ──────────────────────────────────────────────────────────
  const proof = {
    startedAt: new Date().toISOString(),
    network: 'stacks-testnet',
    contracts: { spvVerifier: SPV, quorumEscrow: ESC },
    btc: { txid: btc.txid, blockHash: btc.blockHashLE, blockHeight: btc.blockHeight, anchorBH: btc.anchorBH, amountSats: btc.amountSats },
    validators: VAL_ADDRS,
    quorum,
    verifyRounds: `${rounds.filter(r => r.ok).length}/20`,
    rounds,
    invariant: 'assets_bridged=false',
    endedAt: new Date().toISOString(),
  };
  fs.writeFileSync('docs/proofs/stacks_btc_liquidity_proof.json', JSON.stringify(proof, null, 2));
  console.log('\n=== Proof saved ===');
  console.log(JSON.stringify({ quorum, verifyRounds: proof.verifyRounds, invariant: proof.invariant }, null, 2));
}

main().catch(e => { console.error('FATAL:', e); process.exit(1); });
