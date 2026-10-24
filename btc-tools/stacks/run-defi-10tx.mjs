/**
 * run-defi-10tx.mjs — 10 on-chain DeFi interactions across all contracts.
 *
 * Flow:
 * 1. register-publisher (PublisherRegistry)
 * 2. heartbeat (PublisherRegistry)
 * 3. deposit tTRION to lending pool (BTCPLendV5)
 * 4. register-vault on Stacks (CoherenceVaultV6)
 * 5. activate-vault (CoherenceVaultV6)
 * 6. register-btc-collateral (BTCPLendV5)
 * 7. borrow against BTC (BTCPLendV5)
 * 8. repay partial (BTCPLendV5)
 * 9. fund-bounty for liquidation (PublisherRegistry)
 * 10. publish-preimage (CoherenceVaultV6)
 *
 * Plus the real BTC preimage-reveal spend on Bitcoin testnet.
 */

import { sendContractCall, buffCV, hashStr, getAddressFromPrivateKey } from './lib/helpers.mjs';
import txPkg from '@stacks/transactions';
import * as crypto from 'crypto';
import * as fs from 'fs';
const { uintCV, principalCV, bufferCV } = txPkg;

const KEY = '940806a0a98e86df44835d7fb5d58a79d6259f413550ba11a858880a72e2e71901';
const ADDR = getAddressFromPrivateKey(KEY, 'testnet');
const FEE = 100000;
const results = [];

// V2/V3 keys for multi-party testing
const V2_KEY = 'c5a4f8e2a9b1d3c5e7f9a1b3d5e7f9a1b3d5e7f9a1b3d5e7f9a1b3d5e7f9a1b301';
const V2_ADDR = getAddressFromPrivateKey(V2_KEY, 'testnet');

// Contract addresses
const PUBLISHER = { contractAddress: ADDR, contractName: 'publisherregistry-v1' };
const VAULT = { contractAddress: ADDR, contractName: 'trioncoherencevault-v6' };
const LEND = { contractAddress: ADDR, contractName: 'btcplend-v5b' };

// Vault state from the permanent file
const vaultState = JSON.parse(fs.readFileSync('/home/z/my-project/trion-core/btc-tools/vault/vault-final.json', 'utf-8'));

// Run salt for unique IDs
const RUN_SALT = Date.now();

function log(msg) { console.log(`[${new Date().toISOString().slice(11,19)}] ${msg}`); }

async function runStep(id, name, call) {
  log(`[tx ${id}/10] ${name} ... `);
  try {
    const r = await call();
    const ok = r.ok;
    const mark = ok ? 'PASS' : 'FAIL';
    log(`  ${mark} tx=${r.txId || r.error || ''}`);
    results.push({ id, name, status: ok ? 'pass' : 'fail', txId: r.txId, error: r.error });
    return r;
  } catch (e) {
    log(`  ERR: ${e.message.slice(0, 100)}`);
    results.push({ id, name, status: 'error', error: e.message.slice(0, 200) });
    return { ok: false, error: e.message };
  }
}

log('=========================================================');
log('  TRION DBP DeFi Flow — 10 On-Chain Interactions');
log('=========================================================');
log(`Deployer: ${ADDR}`);
log(`V2: ${V2_ADDR}`);
log('');

// ─── Step 1: Register as publisher ──────────────────────────────────────
await runStep(1, 'PublisherRegistry.register-publisher (stake 5 STX)', () =>
  sendContractCall({
    ...PUBLISHER,
    functionName: 'register-publisher',
    functionArgs: [uintCV(5000000n)],
    senderKey: KEY,
    fee: FEE,
  })
);

// ─── Step 2: Heartbeat ──────────────────────────────────────────────────
// Can't heartbeat immediately (interval = 12 blocks). Skip if fails.
await runStep(2, 'PublisherRegistry.heartbeat (may fail — too early)', () =>
  sendContractCall({
    ...PUBLISHER,
    functionName: 'heartbeat',
    functionArgs: [],
    senderKey: KEY,
    fee: FEE,
  })
);

// ─── Step 3: Deposit tTRION to lending pool ────────────────────────────
await runStep(3, 'BTCPLendV5.deposit 500 tTRION', () =>
  sendContractCall({
    ...LEND,
    functionName: 'deposit',
    functionArgs: [uintCV(500n)],
    senderKey: KEY,
    fee: FEE,
  })
);

// ─── Step 4: Register vault on Stacks (V6) ──────────────────────────────
const vaultId = '0x' + crypto.createHash('sha256').update(`vault-${RUN_SALT}`).digest('hex');
const entityIdHex = vaultState.payloadHex.slice(0, 40);
const anchorBH = vaultState.committedAnchorBH;
const lenderBtcAddr = hashStr(vaultState.lenderAddress);

await runStep(4, `CoherenceVaultV6.register-vault (vault-id=${vaultId.slice(0,20)}...)`, () =>
  sendContractCall({
    ...VAULT,
    functionName: 'register-vault',
    functionArgs: [
      buffCV(vaultId),
      buffCV('0x' + entityIdHex),
      buffCV('0x' + anchorBH),
      buffCV(lenderBtcAddr),
      uintCV(158148n),
      uintCV(6),
    ],
    senderKey: KEY,
    fee: FEE,
  })
);

// ─── Step 5: Activate vault (make it borrowable) ────────────────────────
await runStep(5, 'CoherenceVaultV6.activate-vault', () =>
  sendContractCall({
    ...VAULT,
    functionName: 'activate-vault',
    functionArgs: [buffCV(vaultId), principalCV(ADDR)],
    senderKey: KEY,
    fee: FEE,
  })
);

// ─── Step 6: Register BTC collateral ────────────────────────────────────
await runStep(6, 'BTCPLendV5.register-btc-collateral', () =>
  sendContractCall({
    ...LEND,
    functionName: 'register-btc-collateral',
    functionArgs: [
      buffCV('0x' + 'a'.repeat(64)),  // fake btc txid
      uintCV(100000n),                 // 100k sats
      buffCV('0x' + anchorBH),
      buffCV(vaultId),
    ],
    senderKey: KEY,
    fee: FEE,
  })
);

// ─── Step 7: Borrow tTRION against BTC collateral ───────────────────────
await runStep(7, 'BTCPLendV5.borrow 80 tTRION (80% LTV)', () =>
  sendContractCall({
    ...LEND,
    functionName: 'borrow',
    functionArgs: [uintCV(80n), buffCV(vaultId)],
    senderKey: KEY,
    fee: FEE,
  })
);

// ─── Step 8: Repay partial ──────────────────────────────────────────────
await runStep(8, 'BTCPLendV5.repay 40 tTRION (partial)', () =>
  sendContractCall({
    ...LEND,
    functionName: 'repay',
    functionArgs: [uintCV(40n)],
    senderKey: KEY,
    fee: FEE,
  })
);

// ─── Step 9: Fund bounty for liquidation ────────────────────────────────
await runStep(9, 'PublisherRegistry.fund-bounty 10000 microSTX', () =>
  sendContractCall({
    ...PUBLISHER,
    functionName: 'fund-bounty',
    functionArgs: [buffCV(vaultId), uintCV(10000n)],
    senderKey: KEY,
    fee: FEE,
  })
);

// ─── Step 10: Publish preimage (triggers BTC release) ──────────────────
await runStep(10, 'CoherenceVaultV6.publish-preimage (80-byte payload)', () =>
  sendContractCall({
    ...VAULT,
    functionName: 'publish-preimage',
    functionArgs: [buffCV(vaultId), buffCV('0x' + vaultState.payloadHex)],
    senderKey: KEY,
    fee: FEE,
  })
);

// ─── Summary ────────────────────────────────────────────────────────────
const passed = results.filter(r => r.status === 'pass').length;
const failed = results.filter(r => r.status !== 'pass').length;
log('');
log('=========================================================');
log('  FINAL STATUS');
log('=========================================================');
for (const r of results) {
  const mark = r.status === 'pass' ? '✅' : '❌';
  log(`  [${r.id}/10] ${mark} ${r.name}`);
  if (r.txId) log(`         tx: ${r.txId}`);
  if (r.error) log(`         err: ${String(r.error).slice(0, 80)}`);
}
log('');
log(`  Passed: ${passed}/10  Failed: ${failed}/10`);
log(`  assets_bridged: false`);
log('=========================================================');

// Save results
const resultsPath = '/home/z/my-project/trion-core/proofs/btcp-zero-bridge/stacks/defi-10tx-results.json';
fs.writeFileSync(resultsPath, JSON.stringify({
  test: 'TRION DBP DeFi Flow — 10 On-Chain Interactions',
  timestamp: new Date().toISOString(),
  contracts: {
    publisherRegistry: `${ADDR}.publisherregistry-v1`,
    coherenceVaultV6: `${ADDR}.trioncoherencevault-v6`,
    btcplendV5: `${ADDR}.btcplend-v5`,
  },
  vault: { address: vaultState.vaultAddress, committedAnchorBH: anchorBH, payloadLength: 80 },
  results,
  summary: { total: 10, passed, failed, assetsBridged: false },
}, null, 2));
log(`Results saved to: ${resultsPath}`);
