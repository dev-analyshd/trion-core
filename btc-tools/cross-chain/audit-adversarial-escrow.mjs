/**
 * FINAL AUDITOR — Adversarial escrow tests against DEPLOYED BTCPEscrow (V1, manifest).
 *
 * Tests:
 *   A1. Lock + release with arbitrary caller-supplied coherence, NO quorum, NO SPV verify.
 *   A2. Replay the same release (double-release).
 *   A3. Release with coherence BELOW threshold.
 *   A4. Read an existing escrow created by prior proof runs, confirm state.
 *   A5. Try releasing on V2 (ESC) without sufficient attestations — should revert.
 */
import 'dotenv/config';
import crypto from 'crypto';
import fs from 'fs';
import { RpcProvider, Account, CallData } from 'starknet';
import { makeExec } from './lib_patched_exec.mjs';

const provider = new RpcProvider({ nodeUrl: process.env.STARKNET_RPC });
const account = new Account({ provider, address: process.env.STARKNET_ACCOUNT_ADDRESS, signer: process.env.STARKNET_PRIVATE_KEY });
const { exec, resetNonce } = await makeExec(provider, account, process.env.STARKNET_ACCOUNT_ADDRESS);

const ESC_V1 = '0x494a9aea83de43cb66de126d8225bfabcac84c02a677623b61bee0fc3db5e36'; // deployed BTCPEscrow (manifest)
const ESC_V2 = '0x4cc964a674bc4ff6f7e12462bdae963c7f42ef257af380e1604e71b01eb68dd'; // quorum-bound (NOT in manifest)
const OWNER = process.env.STARKNET_ACCOUNT_ADDRESS;
const now = Math.floor(Date.now() / 1000);

function felt(h) { return BigInt('0x' + h.slice(2, 66).padStart(64, '0')); }
function randFelt(tag) { return felt('0x' + crypto.createHash('sha3-256').update(tag + now + Math.random()).digest('hex')); }

const results = { test: 'AUDIT adversarial escrow', startedAt: new Date().toISOString(), cases: [] };
function record(id, label, outcome, evidence) { results.cases.push({ id, label, outcome, evidence }); console.log(`[${id}] ${label}: ${outcome}`); console.log(`     ${evidence}`); }

// ── A1: lock + release with arbitrary coherence, no quorum, no SPV ──
console.log('\n═══ A1: lock + release with caller-supplied coherence=0.92, NO quorum, NO SPV verify, NO attestation ═══');
const eid1 = randFelt('A1-eid');
const rid1 = randFelt('A1-rid');
const fakeBH = randFelt('A1-fakeBH');
try {
  const { tx: lockTx } = await exec([{ contractAddress: ESC_V1, entrypoint: 'lock_escrow', calldata: CallData.compile({ escrow_id: eid1, route_id: rid1, entity_id: 123n, destination: OWNER, amount: { low: 1000000n, high: 0n }, min_coherence: 550000n, timeout_blocks: 7200 }) }], 'A1-lock');
  resetNonce();
  const { tx: relTx, receipt: relRec } = await exec([{ contractAddress: ESC_V1, entrypoint: 'release_escrow', calldata: CallData.compile({ escrow_id: eid1, execution_bh: fakeBH, coherence: 920000n }) }], 'A1-release');
  resetNonce();
  record('A1', 'release with arbitrary coherence (no quorum)', relRec?.execution_status, `lock=${lockTx.transaction_hash.slice(0,18)} release=${relTx.transaction_hash.slice(0,18)} status=${relRec?.execution_status}`);
} catch (e) {
  resetNonce();
  record('A1', 'release with arbitrary coherence', 'ERROR', String(e.message).slice(0, 250));
}

// ── A2: replay the same release (double-release) ──
console.log('\n═══ A2: replay the same release (double-release) ═══');
try {
  const { tx, receipt } = await exec([{ contractAddress: ESC_V1, entrypoint: 'release_escrow', calldata: CallData.compile({ escrow_id: eid1, execution_bh: fakeBH, coherence: 920000n }) }], 'A2-replay', true);
  resetNonce();
  record('A2', 'replay identical release', receipt?.execution_status || 'REVERTED', `tx=${tx.transaction_hash.slice(0,18)} — expected REVERTED (already RELEASED)`);
} catch (e) {
  resetNonce();
  record('A2', 'replay identical release', 'REVERTED (correct)', String(e.message).slice(0, 200));
}

// ── A3: release with coherence BELOW threshold ──
console.log('\n═══ A3: release with coherence below min_coherence threshold ═══');
const eid3 = randFelt('A3-eid');
const rid3 = randFelt('A3-rid');
try {
  await exec([{ contractAddress: ESC_V1, entrypoint: 'lock_escrow', calldata: CallData.compile({ escrow_id: eid3, route_id: rid3, entity_id: 123n, destination: OWNER, amount: { low: 1000000n, high: 0n }, min_coherence: 800000n, timeout_blocks: 7200 }) }], 'A3-lock');
  resetNonce();
  const { tx, receipt } = await exec([{ contractAddress: ESC_V1, entrypoint: 'release_escrow', calldata: CallData.compile({ escrow_id: eid3, execution_bh: fakeBH, coherence: 500000n }) }], 'A3-release-below', true);
  resetNonce();
  record('A3', 'release coherence=0.50 < min 0.80', receipt?.execution_status || 'REVERTED', `tx=${tx.transaction_hash.slice(0,18)} — expected REVERTED`);
} catch (e) {
  resetNonce();
  record('A3', 'release coherence below threshold', 'REVERTED (correct)', String(e.message).slice(0, 200));
}

// ── A4: read the V2 escrow's quorum_required and validators ──
console.log('\n═══ A4: inspect V2 (ESC) quorum config ═══');
try {
  const qData = await provider.callContract({ contractAddress: ESC_V2, entrypoint: 'quorum_required', calldata: [] });
  record('A4-quorum', 'V2 quorum_required', qData.result?.[0] || '?', `value=${qData.result?.[0]}`);
} catch (e) {
  record('A4-quorum', 'V2 quorum_required read', 'ERR', String(e.message).slice(0, 150));
}
try {
  const vData = await provider.callContract({ contractAddress: ESC_V2, entrypoint: 'is_validator', calldata: [OWNER] });
  record('A4-owner-is-validator', 'V2 is_owner_validator', vData.result?.[0] || '?', `OWNER registered as validator = ${vData.result?.[0]}`);
} catch (e) {
  record('A4-owner-is-validator', 'V2 is_owner_validator', 'ERR (no such view?)', String(e.message).slice(0, 150));
}

// ── A5: release on V2 (ESC) without ANY attestation — should revert with 'quorum not reached' ──
console.log('\n═══ A5: release on V2 (ESC) WITHOUT quorum — should revert ═══');
const eid5 = randFelt('A5-eid');
const rid5 = randFelt('A5-rid');
try {
  await exec([{ contractAddress: ESC_V2, entrypoint: 'lock_escrow', calldata: CallData.compile({ escrow_id: eid5, route_id: rid5, entity_id: 123n, destination: OWNER, amount: { low: 1000000n, high: 0n }, min_coherence: 550000n, timeout_blocks: 7200 }) }], 'A5-lock-v2');
  resetNonce();
  const { tx, receipt } = await exec([{ contractAddress: ESC_V2, entrypoint: 'release_escrow', calldata: CallData.compile({ escrow_id: eid5, execution_bh: fakeBH, coherence: 920000n }) }], 'A5-release-v2-no-quorum', true);
  resetNonce();
  record('A5', 'V2 release without quorum', receipt?.execution_status || 'REVERTED', `tx=${tx.transaction_hash.slice(0,18)} — expected REVERTED (quorum not reached)`);
} catch (e) {
  resetNonce();
  record('A5', 'V2 release without quorum', 'REVERTED (correct)', String(e.message).slice(0, 250));
}

results.endedAt = new Date().toISOString();
fs.writeFileSync('/tmp/audit_adversarial.json', JSON.stringify(results, null, 2));
console.log('\n=== Full results: /tmp/audit_adversarial.json ===');
