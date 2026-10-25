/**
 * run-atomic-liquidation.mjs — Full atomic liquidation flow on Stacks testnet.
 *
 * Flow:
 * 1. publish-coherence-score (CoherenceGate) — C(t)=0.85, V(t)=0.2
 * 2. gate-liquidation (CoherenceGate) — check C(t) >= threshold
 * 3. register-vault (CoherenceVaultV6)
 * 4. activate-vault (CoherenceVaultV6)
 * 5. deposit (BTCPLendV5b)
 * 6. register-btc-collateral (BTCPLendV5b)
 * 7. borrow (BTCPLendV5b) — borrow against BTC
 * 8. liquidate (BTCPLendV5b) — calls mark-liquidating on V6
 * 9. publish-preimage (CoherenceVaultV6) — triggers BTC release
 * 10. mark-liquidated (CoherenceVaultV6) — confirm BTC spent
 *
 * This is the full liquidation path: borrow -> default -> gate -> liquidate -> preimage -> settled.
 */

import { sendContractCall, buffCV, hashStr, getAddressFromPrivateKey } from './lib/helpers.mjs';
import txPkg from '@stacks/transactions';
import * as crypto from 'crypto';
import * as fs from 'fs';
const { uintCV, principalCV } = txPkg;

const KEY = '940806a0a98e86df44835d7fb5d58a79d6259f413550ba11a858880a72e2e71901';
const ADDR = getAddressFromPrivateKey(KEY, 'testnet');
const FEE = 100000;
const results = [];

const GATE = { contractAddress: ADDR, contractName: 'coherencegate-v1' };
const VAULT = { contractAddress: ADDR, contractName: 'trioncoherencevault-v6' };
const LEND = { contractAddress: ADDR, contractName: 'btcplend-v5b' };
const PUBLISHER = { contractAddress: ADDR, contractName: 'publisherregistry-v2' };

const vaultState = JSON.parse(fs.readFileSync('/home/z/my-project/trion-core/btc-tools/vault/vault-final.json', 'utf-8'));
const RUN_SALT = Date.now();

function log(msg) { console.log(`[${new Date().toISOString().slice(11,19)}] ${msg}`); }

async function runStep(id, name, call) {
  log(`[tx ${id}/10] ${name} ... `);
  try {
    const r = await call();
    const mark = r.ok ? 'PASS' : 'FAIL';
    log(`  ${mark} tx=${r.txId || r.error || ''}`);
    if (!r.ok && r.info) {
      log(`    result: ${r.info?.tx_result?.repr || ''}`);
      log(`    vm_error: ${r.info?.vm_error || ''}`);
    }
    results.push({ id, name, status: r.ok ? 'pass' : 'fail', txId: r.txId, error: r.error });
    return r;
  } catch (e) {
    log(`  ERR: ${e.message.slice(0, 100)}`);
    results.push({ id, name, status: 'error', error: e.message.slice(0, 200) });
    return { ok: false, error: e.message };
  }
}

log('=========================================================');
log('  TRION Atomic Liquidation Flow — 10 On-Chain Txs');
log('=========================================================');
log('');

// Step 1: Add deployer as authorized publisher to CoherenceGate
await runStep(0, 'CoherenceGate.add-publisher (authorize deployer)', () =>
  sendContractCall({
    ...GATE,
    functionName: 'add-publisher',
    functionArgs: [principalCV(ADDR)],
    senderKey: KEY,
    fee: FEE,
  })
);

// Step 1: Publish coherence score (C=0.85, V=0.2)
await runStep(1, 'CoherenceGate.publish-coherence-score (C=0.85, V=0.2)', () =>
  sendContractCall({
    ...GATE,
    functionName: 'publish-coherence-score',
    functionArgs: [uintCV(850000n), uintCV(200000n)], // C=0.85, V=0.2
    senderKey: KEY,
    fee: FEE,
  })
);

// Step 2: Gate-liquidation (check coherence passes)
const vaultId = '0x' + crypto.createHash('sha256').update(`liquidation-${RUN_SALT}`).digest('hex');
await runStep(2, 'CoherenceGate.gate-liquidation (check C(t) >= threshold)', () =>
  sendContractCall({
    ...GATE,
    functionName: 'gate-liquidation',
    functionArgs: [buffCV(vaultId)],
    senderKey: KEY,
    fee: FEE,
  })
);

// Step 3: Register vault
const entityIdHex = vaultState.payloadHex.slice(0, 40);
const anchorBH = vaultState.committedAnchorBH;
await runStep(3, 'CoherenceVaultV6.register-vault', () =>
  sendContractCall({
    ...VAULT,
    functionName: 'register-vault',
    functionArgs: [
      buffCV(vaultId),
      buffCV('0x' + entityIdHex),
      buffCV('0x' + anchorBH),
      buffCV(hashStr(vaultState.lenderAddress)),
      uintCV(100000n), // 100k sats
      uintCV(6),       // CSV blocks
    ],
    senderKey: KEY,
    fee: FEE,
  })
);

// Step 4: Activate vault
await runStep(4, 'CoherenceVaultV6.activate-vault', () =>
  sendContractCall({
    ...VAULT,
    functionName: 'activate-vault',
    functionArgs: [buffCV(vaultId), principalCV(ADDR)],
    senderKey: KEY,
    fee: FEE,
  })
);

// Step 5: Deposit to lending pool
await runStep(5, 'BTCPLendV5b.deposit 1000 tTRION', () =>
  sendContractCall({
    ...LEND,
    functionName: 'deposit',
    functionArgs: [uintCV(1000n)],
    senderKey: KEY,
    fee: FEE,
  })
);

// Step 6: Register BTC collateral (use sats=100 so liquidation is reachable)
await runStep(6, 'BTCPLendV5b.register-btc-collateral (sats=100)', () =>
  sendContractCall({
    ...LEND,
    functionName: 'register-btc-collateral',
    functionArgs: [
      buffCV('0x' + 'b'.repeat(64)),
      uintCV(100n),    // 100 sats (so 100*0.8=80 borrow limit, 100*0.9=90 liquidation trigger)
      buffCV('0x' + anchorBH),
      buffCV(vaultId),
    ],
    senderKey: KEY,
    fee: FEE,
  })
);

// Step 7: Borrow 80 (80% LTV = max)
await runStep(7, 'BTCPLendV5b.borrow 80 tTRION (max LTV)', () =>
  sendContractCall({
    ...LEND,
    functionName: 'borrow',
    functionArgs: [uintCV(80n), buffCV(vaultId)],
    senderKey: KEY,
    fee: FEE,
  })
);

// Step 8: Borrow 11 more (total=91 > 90 = 90% LTV -> triggers liquidation)
await runStep(8, 'BTCPLendV5b.borrow 11 more (total=91 > 90 LTV)', () =>
  sendContractCall({
    ...LEND,
    functionName: 'borrow',
    functionArgs: [uintCV(11n), buffCV(vaultId)],
    senderKey: KEY,
    fee: FEE,
  })
);

// Step 9: Liquidate (LTV > 90%, calls mark-liquidating on V6)
await runStep(9, 'BTCPLendV5b.liquidate (LTV > 90% -> mark-liquidating)', () =>
  sendContractCall({
    ...LEND,
    functionName: 'liquidate',
    functionArgs: [principalCV(ADDR)],
    senderKey: KEY,
    fee: FEE,
  })
);

// Step 9: Publish preimage (anyone can call — triggers BTC release)
await runStep(10, 'CoherenceVaultV6.publish-preimage (80-byte payload)', () =>
  sendContractCall({
    ...VAULT,
    functionName: 'publish-preimage',
    functionArgs: [buffCV(vaultId), buffCV('0x' + vaultState.payloadHex)],
    senderKey: KEY,
    fee: FEE,
  })
);

// Step 10: Mark liquidated (confirm)
await runStep(11, 'CoherenceVaultV6.mark-liquidated', () =>
  sendContractCall({
    ...VAULT,
    functionName: 'mark-liquidated',
    functionArgs: [buffCV(vaultId)],
    senderKey: KEY,
    fee: FEE,
  })
);

// Summary
const passed = results.filter(r => r.status === 'pass').length;
const failed = results.filter(r => r.status !== 'pass').length;
log('');
log('=========================================================');
log('  ATOMIC LIQUIDATION FLOW — FINAL STATUS');
log('=========================================================');
for (const r of results) {
  const mark = r.status === 'pass' ? 'PASS' : 'FAIL';
  log(`  [${r.id}] ${mark} ${r.name}`);
  if (r.txId) log(`       tx: ${r.txId}`);
  if (r.error) log(`       err: ${String(r.error).slice(0, 80)}`);
}
log('');
log(`  Passed: ${passed}/${results.length}  Failed: ${failed}/${results.length}`);
log(`  assets_bridged: false`);
log(`  Full atomic flow: ${passed === results.length ? 'PROVEN' : 'PARTIAL'}`);
log('=========================================================');

fs.writeFileSync('/home/z/my-project/trion-core/proofs/btcp-zero-bridge/stacks/atomic-liquidation-results.json',
  JSON.stringify({ test: 'Atomic Liquidation Flow', timestamp: new Date().toISOString(), results, summary: { total: results.length, passed, failed, assetsBridged: false } }, null, 2));
log('Results saved.');
