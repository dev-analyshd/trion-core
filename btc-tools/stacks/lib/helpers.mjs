import * as crypto from 'crypto';
import txPkg from '@stacks/transactions';
const { makeContractCall, broadcastTransaction, bufferCV, getAddressFromPrivateKey: _getAddr, PostConditionMode } = txPkg;
import netPkg from '@stacks/network';
const { STACKS_TESTNET } = netPkg;

export const API = 'https://api.testnet.hiro.so';
export const network = STACKS_TESTNET;

export function getAddressFromPrivateKey(privateKey, network = 'testnet') {
  return _getAddr(privateKey, network);
}

export function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

export async function getNonce(addr) {
  const r = await fetch(`${API}/v2/accounts/${addr}?proof=0`);
  if (!r.ok) throw new Error(`getNonce(${addr}): HTTP ${r.status}`);
  const data = await r.json();
  return parseInt(data.nonce, 10);
}

export async function getBalance(addr) {
  const r = await fetch(`${API}/extended/v1/address/${addr}/balances`);
  if (!r.ok) throw new Error(`getBalance(${addr}): HTTP ${r.status}`);
  const data = await r.json();
  return parseInt(data?.stx?.balance ?? '0', 10);
}

export async function waitForTx(txId, maxMs = 180000) {
  const start = Date.now();
  while (Date.now() - start < maxMs) {
    await sleep(8000);
    try {
      const r = await fetch(`${API}/extended/v1/tx/${txId}`);
      const info = await r.json();
      if (info.tx_status === 'success') return { ok: true, info };
      if (info.tx_status === 'abort_by_response' || info.tx_status === 'abort_by_post_condition') {
        return { ok: false, info, error: info.raw_result || info.tx_status };
      }
    } catch (_e) {}
  }
  return { ok: false, error: 'timeout' };
}

export async function sendContractCall({ contractAddress, contractName, functionName, functionArgs, senderKey, fee = 100000, postConditionMode = PostConditionMode.Allow }) {
  const senderAddr = getAddressFromPrivateKey(senderKey, 'testnet');
  const nonce = await getNonce(senderAddr);
  const tx = await makeContractCall({ contractAddress, contractName, functionName, functionArgs, senderKey, network, fee, nonce: BigInt(nonce), postConditionMode });
  const resp = await broadcastTransaction({ transaction: tx, network });
  if (!resp || !resp.txid) return { ok: false, error: resp ? JSON.stringify(resp).slice(0, 200) : 'no broadcast response' };
  const txId = `0x${resp.txid}`;
  const result = await waitForTx(txId);
  return { ok: !!result.ok, txId, info: result.info, error: result.error };
}

export function buffCV(hexStr) {
  const raw = hexStr == null ? '' : String(hexStr);
  const hex = raw.startsWith('0x') ? raw.slice(2) : raw;
  const bytes = Buffer.from(hex, 'hex');
  if (bytes.length < 32) { const padded = Buffer.alloc(32); bytes.copy(padded, 32 - bytes.length); return bufferCV(padded); }
  return bufferCV(bytes);
}

export function hashStr(str) {
  const h = crypto.createHash('sha256').update(Buffer.from(str, 'utf-8')).digest('hex');
  return `0x${h}`;
}

export function randomBuff32() { return `0x${crypto.randomBytes(32).toString('hex')}`; }
