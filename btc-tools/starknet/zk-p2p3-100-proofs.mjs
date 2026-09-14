// P2+P3 — Generate 100 proofs with progress saving + resumption
import { submitV3Invoke, callView, NEW_ADDR, getNonce } from './zk-helpers.mjs';
import { writeFileSync, readFileSync, existsSync } from 'fs';
import { hash as snHash } from 'starknet';

const NEW_ZK = '0x69457ea628e4816beb44eeda55b84a2b0cd3169aebebbea43ab10792138e54a';
const STATE_FILE = '/home/z/my-project/trion-core/docs/proofs/zk_100_proofs.json';

// Load existing state if available
let proofs = [];
if (existsSync(STATE_FILE)) {
  try {
    const saved = JSON.parse(readFileSync(STATE_FILE, 'utf8'));
    if (saved.proofs) proofs = saved.proofs;
    console.log(`Loaded ${proofs.length} existing proofs from state file.`);
  } catch (e) { console.log('Could not load state:', e.message); }
}

console.log('═══════════════════════════════════════════════════════════');
console.log('  STARKNET ZK 100-PROOF GAUNTLET — P2+P3 (resumable)');
console.log('═══════════════════════════════════════════════════════════\n');
console.log(`New ZKVerifier: ${NEW_ZK}`);
console.log(`Submitter: ${NEW_ADDR}`);
console.log(`Resuming from: ${proofs.length} proofs\n`);

function hStr(s) {
  return '0x' + snHash.starknetKeccak(s).toString(16);
}

async function submitProof(category, idx, calls, expectedRevert = false) {
  const proofId = `${category}-${String(idx).padStart(3, '0')}`;
  // Check if already done
  const existing = proofs.find(p => p.id === proofId);
  if (existing) {
    console.log(`[SKIP] ${proofId} (already done: ${existing.status})`);
    return existing;
  }
  process.stdout.write(`[${proofs.length + 1}/100] ${proofId}... `);
  let r;
  try {
    r = await submitV3Invoke(calls, expectedRevert);
  } catch (e) {
    r = { success: false, error: { message: String(e.message).slice(0, 200) }, txHash: null, status: 'EXCEPTION' };
  }
  const proof = {
    id: proofId,
    category,
    idx,
    calls: calls.map(c => ({ to: c.contractAddress, fn: c.entrypoint, args: c.calldata })),
    expected_revert: expectedRevert,
    tx_hash: r.txHash,
    status: r.status,
    success: r.success,
    revert_reason: r.revert_reason?.slice(0, 200) || r.error?.message?.slice(0, 200),
    actual_fee: r.actual_fee,
    events_count: r.events?.length || 0,
    timestamp: new Date().toISOString(),
  };
  proofs.push(proof);
  // Save state after each proof
  saveState();
  if (r.success) {
    console.log(expectedRevert ? `UNEXPECTED SUCCESS` : `✓ SUCCEEDED tx=${r.txHash?.slice(0,16)}...`);
  } else {
    console.log(expectedRevert ? `✓ EXPECTED REVERT: ${(r.revert_reason || r.error?.message || '').slice(0,80)}` : `✗ FAILED: ${(r.revert_reason || r.error?.message || '').slice(0,80)}`);
  }
  // Small delay between submissions to allow RPC to settle
  await new Promise(r => setTimeout(r, 500));
  return proof;
}

function saveState() {
  const byCategory = {};
  for (const p of proofs) {
    if (!byCategory[p.category]) byCategory[p.category] = { succeeded: 0, reverted: 0, failed: 0, total: 0 };
    byCategory[p.category].total++;
    if (p.success && !p.expected_revert) byCategory[p.category].succeeded++;
    else if (!p.success && p.expected_revert) byCategory[p.category].reverted++;
    else byCategory[p.category].failed++;
  }
  const result = {
    timestamp: new Date().toISOString(),
    new_zk_verifier: NEW_ZK,
    submitter: NEW_ADDR,
    total_proofs: proofs.length,
    by_category: byCategory,
    proofs,
  };
  writeFileSync(STATE_FILE, JSON.stringify(result, null, 2));
}

// ════════════════════════════════════════════════════════════
// S1: commit_intent × 20
// ════════════════════════════════════════════════════════════
console.log('\n── S1: Intent Commitment × 20 ──');
const S1_INTENTS = [];  // save h_intent values for S2 reuse
for (let i = 1; i <= 20; i++) {
  const hIntent = hStr(`TRION-S1-intent-${i}-fixed`);
  S1_INTENTS.push(hIntent);
  const entityId = hStr(`TRION-entity-${i}`);
  await submitProof('S1', i, [{
    contractAddress: NEW_ZK, entrypoint: 'commit_intent',
    calldata: [hIntent, entityId],
  }]);
}

// ════════════════════════════════════════════════════════════
// S2: Duplicate intent (re-commit) × 15
// ════════════════════════════════════════════════════════════
console.log('\n── S2: Duplicate Intent (re-commit) × 15 ──');
for (let i = 1; i <= 15; i++) {
  const hIntent = S1_INTENTS[i - 1] || hStr(`TRION-S2-intent-${i}`);
  const newEntityId = hStr(`TRION-S2-newentity-${i}`);
  await submitProof('S2', i, [{
    contractAddress: NEW_ZK, entrypoint: 'commit_intent',
    calldata: [hIntent, newEntityId],
  }]);
}

// ════════════════════════════════════════════════════════════
// S3: submit_travel_rule_proof × 15
// ════════════════════════════════════════════════════════════
console.log('\n── S3: Travel Rule Proof × 15 ──');
for (let i = 1; i <= 15; i++) {
  const entityId = hStr(`TRION-S3-entity-${i}`);
  const txHash = hStr(`TRION-S3-tx-${i}`);
  const jurisdictionId = i;
  const disclosureHash = hStr(`TRION-S3-disc-${i}`);
  await submitProof('S3', i, [{
    contractAddress: NEW_ZK, entrypoint: 'submit_travel_rule_proof',
    calldata: [entityId, txHash, '0x' + jurisdictionId.toString(16), disclosureHash],
  }]);
}

// ════════════════════════════════════════════════════════════
// S4: Multi-entity commit_intent × 20
// ════════════════════════════════════════════════════════════
console.log('\n── S4: Multi-Entity Intent × 20 ──');
for (let i = 1; i <= 20; i++) {
  const hIntent = hStr(`TRION-S4-intent-${i}-fixed`);
  const entityId = hStr(`TRION-S4-entity-${i}`);
  await submitProof('S4', i, [{
    contractAddress: NEW_ZK, entrypoint: 'commit_intent',
    calldata: [hIntent, entityId],
  }]);
}

// ════════════════════════════════════════════════════════════
// S5: enroll_birp × 15
// ════════════════════════════════════════════════════════════
console.log('\n── S5: BIRP Enrollment × 15 ──');
for (let i = 1; i <= 15; i++) {
  const entityId = hStr(`TRION-S5-entity-${i}`);
  const birpAnchor = hStr(`TRION-S5-birp-${i}`);
  await submitProof('S5', i, [{
    contractAddress: NEW_ZK, entrypoint: 'enroll_birp',
    calldata: [entityId, birpAnchor],
  }]);
}

// ════════════════════════════════════════════════════════════
// Hash_DNA × 10 — Pedersen hash for cross-system binding
// ════════════════════════════════════════════════════════════
console.log('\n── Hash_DNA: Cross-System Identity Binding × 10 ──');
const hashDnaBindings = [];
for (let i = 1; i <= 10; i++) {
  const entityId = BigInt(hStr(`TRION-DNA-entity-${i}`));
  const systemId = BigInt(hStr(`TRION-DNA-system-${i}`));
  const bindingHash = snHash.computePedersenHashOnElements([entityId, systemId]);
  const bindingHashHex = '0x' + bindingHash.toString(16);
  hashDnaBindings.push({ idx: i, entity_id: '0x' + entityId.toString(16), system_id: '0x' + systemId.toString(16), binding_hash: bindingHashHex });
  await submitProof('Hash_DNA', i, [{
    contractAddress: NEW_ZK, entrypoint: 'commit_intent',
    calldata: [bindingHashHex, '0x' + entityId.toString(16)],
  }]);
}

// ════════════════════════════════════════════════════════════
// Adversarial negation × 5 (expected to REVERT)
// ════════════════════════════════════════════════════════════
console.log('\n── Adversarial Negation × 5 (expected to REVERT) ──');
await submitProof('ADV', 1, [{
  contractAddress: NEW_ZK, entrypoint: 'commit_intent',
  calldata: ['0x0', hStr('ADV-entity-1')],
}], true);
await submitProof('ADV', 2, [{
  contractAddress: NEW_ZK, entrypoint: 'commit_intent',
  calldata: [hStr('ADV-intent-2'), '0x0'],
}], true);
await submitProof('ADV', 3, [{
  contractAddress: NEW_ZK, entrypoint: 'submit_travel_rule_proof',
  calldata: [hStr('ADV-entity-3'), '0x0', '0x1', hStr('ADV-disc-3')],
}], true);
await submitProof('ADV', 4, [{
  contractAddress: NEW_ZK, entrypoint: 'enroll_birp',
  calldata: [hStr('ADV-entity-4'), '0x0'],
}], true);
await submitProof('ADV', 5, [{
  contractAddress: NEW_ZK, entrypoint: 'nonexistent_adversarial_fn',
  calldata: ['0x0', '0x0'],
}], true);

// ════════════════════════════════════════════════════════════
// Final summary
// ════════════════════════════════════════════════════════════
console.log('\n═══════════════════════════════════════════════════════════');
console.log('  100-PROOF GAUNTLET — FINAL SUMMARY');
console.log('═══════════════════════════════════════════════════════════\n');

const byCategory = {};
let totalSucceeded = 0, totalReverted = 0, totalFailed = 0;
for (const p of proofs) {
  if (!byCategory[p.category]) byCategory[p.category] = { succeeded: 0, reverted: 0, failed: 0, total: 0 };
  byCategory[p.category].total++;
  if (p.success && !p.expected_revert) { byCategory[p.category].succeeded++; totalSucceeded++; }
  else if (!p.success && p.expected_revert) { byCategory[p.category].reverted++; totalReverted++; }
  else { byCategory[p.category].failed++; totalFailed++; }
}

for (const [cat, counts] of Object.entries(byCategory)) {
  console.log(`  ${cat}: ${counts.succeeded} succeeded, ${counts.reverted} reverted (expected), ${counts.failed} failed / ${counts.total} total`);
}
console.log(`\n  TOTAL: ${totalSucceeded} succeeded + ${totalReverted} reverted (expected adversarial) + ${totalFailed} failed`);
console.log(`  Submitted: ${proofs.length} / 100 proofs`);

// Save hash_dna_bindings
const result = {
  timestamp: new Date().toISOString(),
  new_zk_verifier: NEW_ZK,
  submitter: NEW_ADDR,
  total_proofs: proofs.length,
  succeeded: totalSucceeded,
  reverted_expected: totalReverted,
  failed: totalFailed,
  by_category: byCategory,
  proofs,
  hash_dna_bindings: hashDnaBindings,
};
writeFileSync(STATE_FILE, JSON.stringify(result, null, 2));
console.log('\n✓ Saved to', STATE_FILE);
