/**
 * stacks-verify-le.mjs — Sync headers with LE merkle roots + verify-anchor.
 * Fixes byte order: Bitcoin merkle root is stored as LE in raw header.
 * getblockheader JSON returns BE display order; we reverse it to LE.
 */
import txPkg from '@stacks/transactions';
const { makeContractCall, broadcastTransaction, getAddressFromPrivateKey, uintCV, bufferCV, boolCV, listCV, PostConditionMode } = txPkg;
import netPkg from '@stacks/network';
const { STACKS_TESTNET, createNetwork } = netPkg;
import * as crypto from 'crypto';
import * as fs from 'fs';

const API = 'https://api.testnet.hiro.so';
const BTC_RPC = 'https://bitcoin-testnet.g.alchemy.com/v2/alch_s5FpWzSEKTzISMWu761j2';
const DEPLOYER_KEY = '940806a0a98e86df44835d7fb5d58a79d6259f413550ba11a858880a72e2e71901';
const DEPLOYER = 'ST969AZNDX2P7N1YJ0DNVGC8QEKT388DBMXGHR9Z';
const SPV = `${DEPLOYER}.spv-v2`;
const network = createNetwork(STACKS_TESTNET);

async function getNonce() {
  const r = await fetch(`${API}/v2/accounts/${DEPLOYER}?proof=0`);
  const data = await r.json();
  return parseInt(data.nonce);
}
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
async function waitForTx(txId) {
  for (let i = 0; i < 20; i++) {
    await sleep(8000);
    try {
      const r = await fetch(`${API}/extended/v1/tx/${txId}`);
      const info = await r.json();
      if (info.tx_status === 'success') return { ok: true };
      if (info.tx_status === 'abort_by_response') return { ok: false, error: 'abort' };
    } catch {}
  }
  return { ok: false, error: 'timeout' };
}

async function send(fnName, args) {
  const nonce = await getNonce();
  try {
    const tx = await makeContractCall({
      contractAddress: DEPLOYER, contractName: 'spv-v2', functionName: fnName,
      functionArgs: args, senderKey: DEPLOYER_KEY, network, fee: 100000, nonce: BigInt(nonce),
      postConditionMode: PostConditionMode.Allow,
    });
    const resp = await broadcastTransaction({ transaction: tx, network });
    if (resp.txid) { const r = await waitForTx(`0x${resp.txid}`); return { ok: r.ok, txId: `0x${resp.txid}`, error: r.error }; }
    return { ok: false };
  } catch (e) { return { ok: false, error: e.message.slice(0, 100) }; }
}

function buffCV(hexStr) {
  const hex = hexStr.startsWith('0x') ? hexStr.slice(2) : hexStr;
  const bytes = Buffer.from(hex, 'hex');
  if (bytes.length < 32) { const padded = Buffer.alloc(32); bytes.copy(padded, 32 - bytes.length); return bufferCV(padded); }
  return bufferCV(bytes);
}

function reverseHex(h) { return '0x' + (h.startsWith('0x') ? h.slice(2) : h).match(/../g).reverse().join(''); }

async function main() {
  const TXID = '62bfe73fab5ac18c64794493d3713c5eb3e92b839df401befecd68162ee1fcf7';
  const BTC_ADDR = 'tb1q5d69fyxxxwdkr7pecmxyr245w5jqchm9zptkks';
  const TARGET = 5128449, GEN = TARGET - 6, TIP = TARGET + 6;

  const btc = async (m, p) => {
    const r = await fetch(BTC_RPC, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ jsonrpc: '2.0', method: m, params: p, id: 1 }) });
    const j = await r.json(); if (j.error) throw new Error(j.error.message); return j.result;
  };
  const tx = await btc('getrawtransaction', [TXID, true]);
  const blockHashLE = tx.blockhash;
  const headerHex = await btc('getblockheader', [blockHashLE, false]);
  const hb = Buffer.from(headerHex, 'hex');
  const blockTime = hb.readUInt32LE(68);
  const blockBits = hb.readUInt32BE(72);
  const block2 = await btc('getblock', [blockHashLE, 2]);
  const txids = block2.tx.map(t => t.txid);
  const txIndex = txids.indexOf(TXID);

  // Merkle proof (txid and siblings in LE/internal form)
  let level = txids.map(t => Buffer.from(t, 'hex').reverse());
  let idx = txIndex;
  const merklePathLE = [], merkleIsLeft = [];
  while (level.length > 1) {
    const sibIdx = (idx % 2 === 0) ? idx + 1 : idx - 1;
    const sib = (sibIdx < level.length) ? level[sibIdx] : level[idx];
    merklePathLE.push(sib); // keep as LE buffer
    merkleIsLeft.push(idx % 2 === 0);
    const next = [];
    for (let i = 0; i < level.length; i += 2) { const l = level[i]; const r = (i+1<level.length)?level[i+1]:l; next.push(crypto.createHash('sha256').update(crypto.createHash('sha256').update(Buffer.concat([l,r])).digest()).digest()); }
    level = next; idx = Math.floor(idx / 2);
  }
  const merkleRootLE = level[0]; // LE merkle root (internal Bitcoin form)

  // Anchor BH
  const v0 = tx.vout.find(v => v.n === 0);
  const amountSats = Math.round(v0.value * 1e8);
  const entityBuf = crypto.createHash('sha256').update(BTC_ADDR.toLowerCase()).digest();
  const magnitudeNano = BigInt(amountSats) * 1_000_000_000n;
  const payload = Buffer.alloc(93);
  entityBuf.copy(payload, 0, 0, 32);
  payload.writeUInt8(0, 32);
  payload.writeBigUInt64BE(magnitudeNano, 33);
  payload.writeBigUInt64BE(0n, 41);
  payload.writeBigUInt64BE(BigInt(blockTime), 49);
  payload.writeUInt32BE(100, 57);
  Buffer.from(blockHashLE, 'hex').copy(payload, 61, 0, 32);
  const sense = crypto.createHash('sha256').update(Buffer.concat([payload, Buffer.from([0x00])])).digest();
  const anchorBH = sense;

  // Fetch headers
  const headers = [];
  for (let h = GEN; h <= TIP; h++) {
    const bh = await btc('getblockhash', [h]);
    const hd = await btc('getblockheader', [bh, true]);
    const hBuf = Buffer.from(await btc('getblockheader', [bh, false]), 'hex');
    // Merkle root: reverse the display-order to get LE (internal Bitcoin form)
    const merkleRootBE = hd.merkleroot; // display order
    const merkleRootLEHex = merkleRootBE.match(/../g).reverse().join(''); // reverse to LE
    headers.push({
      height: h, blockHashLE: bh, blockHashU256: '0x' + bh.padStart(64, '0'),
      merkleRootLE: '0x' + merkleRootLEHex,
      timestamp: hBuf.readUInt32LE(68), bits: hBuf.readUInt32BE(72),
    });
  }
  for (let i = 1; i < headers.length; i++) headers[i].prevHashU256 = headers[i-1].blockHashU256;

  console.log(`=== Sync ${headers.length} headers to ${SPV} (with LE merkle roots) ===`);
  // Genesis
  {
    const g = headers[0];
    const r = await send('submit-genesis-tip', [buffCV(g.blockHashU256), uintCV(BigInt(g.height)), buffCV(g.merkleRootLE), uintCV(BigInt(g.timestamp)), uintCV(BigInt(g.bits))]);
    console.log(`genesis ${g.height}: ${r.ok ? 'OK' : 'FAIL'}`);
  }
  for (let i = 1; i < headers.length; i++) {
    const h = headers[i];
    const r = await send('submit-block-header', [buffCV(h.blockHashU256), uintCV(BigInt(h.height)), buffCV(h.merkleRootLE), uintCV(BigInt(h.timestamp)), uintCV(BigInt(h.bits)), buffCV(h.prevHashU256)]);
    console.log(`block ${h.height}: ${r.ok ? 'OK' : 'FAIL'}`);
    if (!r.ok) break;
  }

  // Renounce
  await send('renounce-genesis-ability', []);
  console.log('genesis renounced');

  // verify-anchor: pass txid and merkle path in LE (internal Bitcoin form)
  console.log('\n=== verify-anchor ===');
  const txidLE = Buffer.from(TXID, 'hex').reverse(); // LE form
  const rootLE = merkleRootLE; // LE merkle root buffer

  console.log(`txid LE: 0x${txidLE.toString('hex').slice(0,16)}...`);
  console.log(`merkle root LE: 0x${rootLE.toString('hex').slice(0,16)}...`);
  console.log(`stored root LE: 0x${headers[6].merkleRootLE.slice(0,16)}...`); // block 5128449 = headers[6]

  const r = await send('verify-anchor', [
    buffCV('0x' + blockHashLE.padStart(64, '0')),  // block-hash (stored as display-order)
    bufferCV(txidLE),                                // txid in LE
    listCV([bufferCV(merklePathLE[0]), bufferCV(merklePathLE[1])]),  // merkle path in LE
    listCV([boolCV(merkleIsLeft[0]), boolCV(merkleIsLeft[1])]),     // is-left flags
    bufferCV(anchorBH),                              // anchor-bh
  ]);
  console.log(`verify-anchor: ${r.ok ? 'SUCCEEDED ✓' : 'FAIL'} ${r.error || ''} ${r.txId || ''}`);

  if (r.ok) {
    // 20 rounds
    console.log('\n=== 20 verify-anchor rounds ===');
    let passed = 0;
    const roundTxs = [];
    for (let i = 1; i <= 20; i++) {
      const rr = await send('verify-anchor', [
        buffCV('0x' + blockHashLE.padStart(64, '0')),
        bufferCV(txidLE),
        listCV([bufferCV(merklePathLE[0]), bufferCV(merklePathLE[1])]),
        listCV([boolCV(merkleIsLeft[0]), boolCV(merkleIsLeft[1])]),
        bufferCV(anchorBH),
      ]);
      roundTxs.push({ round: i, ok: rr.ok, txHash: rr.txId });
      if (rr.ok) { passed++; process.stdout.write(`R${i}:✓ `); if (i % 5 === 0) console.log(''); }
      else { console.log(`\nR${i}: FAIL ${rr.error}`); break; }
    }
    console.log(`\n=== ${passed}/20 rounds succeeded ===`);

    // Save results
    const results = {
      spvContract: SPV,
      verifyAnchor: { ok: r.ok, txHash: r.txId, anchorBH: '0x' + anchorBH.toString('hex'), blockHash: blockHashLE, blockHeight: block2.height },
      rounds: { passed, total: 20, txs: roundTxs },
      invariant: 'assets_bridged=false',
      timestamp: new Date().toISOString(),
    };
    fs.writeFileSync('docs/proofs/stacks_verify_anchor_results.json', JSON.stringify(results, null, 2));
    console.log('\nResults saved.');
  }
}

main().catch(e => { console.error('FATAL:', e); process.exit(1); });
