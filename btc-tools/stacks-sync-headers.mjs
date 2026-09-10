/**
 * stacks-sync-headers.mjs — Sync 13 BTC block headers to the SPV verifier.
 */
import txPkg from '@stacks/transactions';
const { makeContractCall, broadcastTransaction, getAddressFromPrivateKey, uintCV, bufferCV, PostConditionMode } = txPkg;
import netPkg from '@stacks/network';
const { STACKS_TESTNET, createNetwork } = netPkg;
import * as crypto from 'crypto';

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

async function waitForTx(txId, maxWaitMs = 120000) {
  const start = Date.now();
  while (Date.now() - start < maxWaitMs) {
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
      console.log(`  ${fnName}: ${r.ok ? 'OK' : 'FAIL'} ${r.error || ''}`);
      return r;
    }
    console.log(`  ${fnName}: broadcast failed: ${JSON.stringify(resp).slice(0,100)}`);
    return { ok: false };
  } catch (e) {
    console.log(`  ${fnName}: ERR ${e.message.slice(0,100)}`);
    return { ok: false };
  }
}

function buffCV(hexStr) {
  const hex = hexStr.startsWith('0x') ? hexStr.slice(2) : hexStr;
  const bytes = Buffer.from(hex, 'hex');
  // Pad to 32 bytes if shorter
  if (bytes.length < 32) {
    const padded = Buffer.alloc(32);
    bytes.copy(padded, 32 - bytes.length);
    return bufferCV(padded);
  }
  return bufferCV(bytes);
}

async function main() {
  // Fetch BTC headers
  const TARGET = 5128449, GEN = TARGET - 6, TIP = TARGET + 6;
  const btc = async (m, p) => {
    const r = await fetch(BTC_RPC, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ jsonrpc: '2.0', method: m, params: p, id: 1 }) });
    const j = await r.json(); if (j.error) throw new Error(j.error.message); return j.result;
  };

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

  console.log(`=== Sync ${headers.length} BTC headers (blocks ${GEN} to ${TIP}) ===`);

  // Genesis
  const g = headers[0];
  await send('submit-genesis-tip', [buffCV(g.blockHashU256), uintCV(BigInt(g.height)), buffCV(g.merkleRoot), uintCV(BigInt(g.timestamp)), uintCV(BigInt(g.bits))]);

  // Blocks GEN+1 to TIP
  for (let i = 1; i < headers.length; i++) {
    const h = headers[i];
    await send('submit-block-header', [buffCV(h.blockHashU256), uintCV(BigInt(h.height)), buffCV(h.merkleRoot), uintCV(BigInt(h.timestamp)), uintCV(BigInt(h.bits)), buffCV(h.prevHashU256)]);
  }

  // Renounce
  await send('renounce-genesis-ability', []);

  // Verify state
  const r = await fetch(`${API}/v2/contracts/call-read-only/${DEPLOYER}/btcspvverifier/get-chain-tip`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sender: DEPLOYER, arguments: [] }),
  });
  const data = await r.json();
  console.log('\n=== Chain tip ===');
  console.log(JSON.stringify(data, null, 2).slice(0, 400));
}

main().catch(e => { console.error('FATAL:', e); process.exit(1); });
