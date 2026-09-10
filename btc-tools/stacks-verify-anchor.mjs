/**
 * stacks-verify-anchor.mjs — Run verify-anchor on-chain + 20 rounds.
 */
import * as crypto from "crypto";
import txPkg from '@stacks/transactions';
const { makeContractCall, broadcastTransaction, getAddressFromPrivateKey, uintCV, bufferCV, boolCV, listCV, PostConditionMode } = txPkg;
import netPkg from '@stacks/network';
const { STACKS_TESTNET, createNetwork } = netPkg;

const API = 'https://api.testnet.hiro.so';
const BTC_RPC = 'https://bitcoin-testnet.g.alchemy.com/v2/alch_s5FpWzSEKTzISMWu761j2';
const DEPLOYER_KEY = '940806a0a98e86df44835d7fb5d58a79d6259f413550ba11a858880a72e2e71901';
const DEPLOYER = 'ST969AZNDX2P7N1YJ0DNVGC8QEKT388DBMXGHR9Z';
const SPV = `${DEPLOYER}.btcspvverifier`;
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
      if (info.tx_status === 'abort_by_response') return { ok: false, error: info.raw_result || 'abort' };
    } catch {}
  }
  return { ok: false, error: 'timeout' };
}

async function send(fnName, args) {
  const nonce = await getNonce();
  try {
    const tx = await makeContractCall({
      contractAddress: DEPLOYER, contractName: 'btcspvverifier', functionName: fnName,
      functionArgs: args, senderKey: DEPLOYER_KEY, network, fee: 100000, nonce: BigInt(nonce),
      postConditionMode: PostConditionMode.Allow,
    });
    const resp = await broadcastTransaction({ transaction: tx, network });
    if (resp.txid) {
      const r = await waitForTx(`0x${resp.txid}`);
      return { ok: r.ok, txId: `0x${resp.txid}`, error: r.error };
    }
    return { ok: false, error: JSON.stringify(resp).slice(0, 100) };
  } catch (e) {
    return { ok: false, error: e.message.slice(0, 100) };
  }
}

function buffCV(hexStr) {
  const hex = hexStr.startsWith('0x') ? hexStr.slice(2) : hexStr;
  const bytes = Buffer.from(hex, 'hex');
  if (bytes.length < 32) {
    const padded = Buffer.alloc(32);
    bytes.copy(padded, 32 - bytes.length);
    return bufferCV(padded);
  }
  return bufferCV(bytes);
}

async function main() {
  // Fetch BTC data for tx 62bfe73f block 5128449
  const TXID = '62bfe73fab5ac18c64794493d3713c5eb3e92b839df401befecd68162ee1fcf7';
  const btc = async (m, p) => {
    const r = await fetch(BTC_RPC, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ jsonrpc: '2.0', method: m, params: p, id: 1 }) });
    const j = await r.json(); if (j.error) throw new Error(j.error.message); return j.result;
  };
  const tx = await btc('getrawtransaction', [TXID, true]);
  const blockHashLE = tx.blockhash;
  const block2 = await btc('getblock', [blockHashLE, 2]);
  const txids = block2.tx.map(t => t.txid);
  const txIndex = txids.indexOf(TXID);

  // Merkle proof (depth 2)
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

  // Anchor BH
  const BTC_ADDR = 'tb1q5d69fyxxxwdkr7pecmxyr245w5jqchm9zptkks';
  const v0 = tx.vout.find(v => v.n === 0);
  const amountSats = Math.round(v0.value * 1e8);
  const entityBuf = crypto.createHash('sha256').update(BTC_ADDR.toLowerCase()).digest();
  const headerHex = await btc('getblockheader', [blockHashLE, false]);
  const hb = Buffer.from(headerHex, 'hex');
  const blockTime = hb.readUInt32LE(68);
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
  const anchorBH = '0x' + sense.toString('hex');

  const blockHashU256 = '0x' + blockHashLE.padStart(64, '0');
  // Bitcoin uses LE internally; reverse display-order hex to LE for hashing
  const txidLE = '0x' + TXID.match(/../g).reverse().join('');
  const merklePathLE = merklePath.map(h => '0x' + h.slice(2).match(/../g).reverse().join(''));

  console.log('=== verify-anchor on-chain ===');
  console.log(`block: ${block2.height}, txIndex: ${txIndex}, depth: ${merklePath.length}`);
  console.log(`anchor_bh: ${anchorBH.slice(0, 18)}...`);

  // verify-anchor call
  const r1 = await send('verify-anchor', [buffCV(blockHashU256), buffCV(txidLE), listCV([buffCV(merklePathLE[0]), buffCV(merklePathLE[1])]), listCV([boolCV(merkleIsLeft[0]), boolCV(merkleIsLeft[1])]), buffCV(anchorBH)]);

  // 1 verify-anchor call
  console.log('\n--- verify-anchor #1 ---');
  // 20 verify-anchor rounds
  console.log('\n--- 20 verify-anchor rounds ---');
  let passed = 0;
  const roundTxs = [];
  for (let i = 1; i <= 20; i++) {
    const r = await send('verify-anchor', [buffCV(blockHashU256), buffCV(txidLE), listCV([buffCV(merklePathLE[0]), buffCV(merklePathLE[1])]), listCV([boolCV(merkleIsLeft[0]), boolCV(merkleIsLeft[1])]), buffCV(anchorBH)]);
    roundTxs.push({ round: i, ok: r.ok, txHash: r.txId });
    if (r.ok) { passed++; process.stdout.write(`R${i}:✓ `); }
    else { console.log(`\nR${i}: FAIL ${r.error}`); break; }
    if (i % 5 === 0) console.log('');
  }
  console.log(`\n=== ${passed}/20 rounds succeeded ===`);

  // Save results
  const results = {
    verifyAnchor: { ok: r1.ok, txHash: r1.txId, anchorBH, blockHash: blockHashLE, blockHeight: block2.height },
    rounds: { passed, total: 20, txs: roundTxs },
    invariant: 'assets_bridged=false',
    timestamp: new Date().toISOString(),
  };
  const fs = await import('fs');
  fs.writeFileSync('docs/proofs/stacks_verify_anchor_results.json', JSON.stringify(results, null, 2));
  console.log('\nResults saved to docs/proofs/stacks_verify_anchor_results.json');
}

main().catch(e => { console.error('FATAL:', e); process.exit(1); });
