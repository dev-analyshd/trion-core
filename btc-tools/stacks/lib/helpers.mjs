/**
 * lib/helpers.mjs — Shared Stacks testnet helpers for TRION deploys + verification.
 *
 * ESM only. Depends on @stacks/transactions v6.x and @stacks/network v6.x.
 * All HTTP calls target the Hiro testnet API (https://api.testnet.hiro.so).
 */
import * as crypto from 'crypto';
import txPkg from '@stacks/transactions';
const {
  makeContractCall,
  broadcastTransaction,
  bufferCV,
  getAddressFromPrivateKey,
  PostConditionMode,
  TransactionVersion,
} = txPkg;
import netPkg from '@stacks/network';
const { StacksTestnet } = netPkg;

export const API = 'https://api.testnet.hiro.so';
export const network = new StacksTestnet({ url: API });

/**
 * sleep(ms) — Promise-based delay.
 */
export function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

/**
 * getNonce(addr) — fetch the current account nonce from the Stacks testnet API.
 * Returns the integer nonce for the next outbound tx.
 */
export async function getNonce(addr) {
  const r = await fetch(`${API}/v2/accounts/${addr}?proof=0`);
  if (!r.ok) {
    throw new Error(`getNonce(${addr}): HTTP ${r.status} ${r.statusText}`);
  }
  const data = await r.json();
  return parseInt(data.nonce, 10);
}

/**
 * getBalance(addr) — fetch the STX balance from the Hiro extended API.
 * Returns balance in microSTX as a Number.
 */
export async function getBalance(addr) {
  const r = await fetch(`${API}/extended/v1/address/${addr}/balances`);
  if (!r.ok) {
    throw new Error(`getBalance(${addr}): HTTP ${r.status} ${r.statusText}`);
  }
  const data = await r.json();
  const microSTX = parseInt(data?.stx?.balance ?? '0', 10);
  return microSTX;
}

/**
 * waitForTx(txId, maxMs=180000) — poll the Stacks API until tx reaches a
 * terminal status (success | abort_by_response | abort_by_post_condition)
 * or until maxMs elapses. Resolves { ok, info?, error? }.
 */
export async function waitForTx(txId, maxMs = 180000) {
  const start = Date.now();
  while (Date.now() - start < maxMs) {
    await sleep(8000);
    try {
      const r = await fetch(`${API}/extended/v1/tx/${txId}`);
      const info = await r.json();
      if (info.tx_status === 'success') {
        return { ok: true, info };
      }
      if (
        info.tx_status === 'abort_by_response' ||
        info.tx_status === 'abort_by_post_condition'
      ) {
        return { ok: false, info, error: info.raw_result || info.tx_status };
      }
      // pending or not yet indexed — keep polling
    } catch (_e) {
      // transient fetch error — keep polling
    }
  }
  return { ok: false, error: 'timeout' };
}

/**
 * sendContractCall({...}) — wrap makeContractCall + broadcastTransaction + waitForTx.
 * Fetches the sender's nonce automatically, signs, broadcasts, and waits.
 * Returns { ok, txId, info?, error? }.
 *
 * postConditionMode defaults to Allow — override per-call if you need to
 * enforce specific post-conditions.
 */
export async function sendContractCall({
  contractAddress,
  contractName,
  functionName,
  functionArgs,
  senderKey,
  fee = 100000,
  postConditionMode = PostConditionMode.Allow,
}) {
  const senderAddr = getAddressFromPrivateKey(senderKey, TransactionVersion.Testnet);
  const nonce = await getNonce(senderAddr);
  const tx = await makeContractCall({
    contractAddress,
    contractName,
    functionName,
    functionArgs,
    senderKey,
    network,
    fee,
    nonce: BigInt(nonce),
    postConditionMode,
  });
  const resp = await broadcastTransaction(tx, network);
  if (!resp || !resp.txid) {
    return {
      ok: false,
      error: resp ? JSON.stringify(resp).slice(0, 200) : 'no broadcast response',
    };
  }
  const txId = `0x${resp.txid}`;
  const result = await waitForTx(txId);
  return {
    ok: !!result.ok,
    txId,
    info: result.info,
    error: result.error,
  };
}

/**
 * buffCV(hexStr) — convert a hex string (0x-prefixed or bare) into a Clarity
 * `bufferCV`. If the value is shorter than 32 bytes, it is left-padded with
 * zero bytes to 32 bytes (matching how on-chain hashes are typically passed).
 */
export function buffCV(hexStr) {
  const raw = hexStr == null ? '' : String(hexStr);
  const hex = raw.startsWith('0x') ? raw.slice(2) : raw;
  const bytes = Buffer.from(hex, 'hex');
  if (bytes.length < 32) {
    const padded = Buffer.alloc(32);
    bytes.copy(padded, 32 - bytes.length);
    return bufferCV(padded);
  }
  return bufferCV(bytes);
}

/**
 * hashStr(str) — sha256 of a UTF-8 string, returned as 0x-prefixed lowercase hex.
 */
export function hashStr(str) {
  const h = crypto.createHash('sha256').update(Buffer.from(str, 'utf-8')).digest('hex');
  return `0x${h}`;
}

/**
 * randomBuff32() — 32 random bytes, returned as 0x-prefixed lowercase hex.
 */
export function randomBuff32() {
  return `0x${crypto.randomBytes(32).toString('hex')}`;
}

export { getAddressFromPrivateKey, TransactionVersion };
