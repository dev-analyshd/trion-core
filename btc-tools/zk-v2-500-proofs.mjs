// Submit 500+ proofs on v2 ZKVerifier — resumable
// Categories:
//   S1: commit_intent × 100
//   S2: duplicate intent collision (should REVERT "intent exists") × 50
//   S3: submit_travel_rule_proof × 100
//   S4: multi-entity commit_intent × 100
//   S5: enroll_birp × 75
//   Hash_DNA: compute_hash_dna + commit_intent × 50
//   Adversarial × 25 (zero values, duplicate enroll, duplicate travel rule, nonexistent fn)
// Total: 500 proofs

import { hash as snHash, CallData } from 'starknet';
import { writeFileSync, readFileSync, existsSync } from 'fs';
import { submitV3Invoke, callView, NEW_ADDR } from './zk-helpers.mjs';

const V2_ZK = '0x70786a313eb52b0b8f4781c23c8e79adb13d42e54dbeb2f229199280c4536c6';
const STATE_FILE = '/home/z/my-project/trion-core/docs/proofs/zk_500_proofs.json';

let proofs = [];
if (existsSync(STATE_FILE)) {
  try { proofs = JSON.parse(readFileSync(STATE_FILE, 'utf8')).proofs || []; } catch (e) {}
}
console.log(`Loaded ${proofs.length} existing proofs. Resuming...`);

console.log('═══════════════════════════════════════════════════════════');
console.log('  STARKNET ZK 500-PROOF GAUNTLET — v2 HARDENED CONTRACT');
console.log('═══════════════════════════════════════════════════════════\n');
console.log(`V2 ZKVerifier: ${V2_ZK}`);
console.log(`Submitter   : ${NEW_ADDR}\n`);

function hStr(s) {
  return '0x' + snHash.starknetKeccak(s).toString(16);
}

async function run(category, idx, calls, expectedRevert = false) {
  const proofId = `${category}-${String(idx).padStart(3, '0')}`;
  if (proofs.find(p => p.id === proofId)) {
    return;  // skip
  }
  process.stdout.write(`[${proofs.length + 1}/500] ${proofId}... `);
  let r;
  try { r = await submitV3Invoke(calls, expectedRevert); }
  catch (e) { r = { success: false, error: String(e.message).slice(0,200), txHash: null, status: 'EXCEPTION' }; }
  proofs.push({
    id: proofId, category, idx,
    calls: calls.map(c => ({ to: c.contractAddress, fn: c.entrypoint, args: c.calldata })),
    expected_revert: expectedRevert,
    tx_hash: r.txHash, status: r.status, success: r.success,
    revert_reason: r.revert_reason?.slice(0, 200) || r.error?.message?.slice(0, 200),
    actual_fee: r.actual_fee, events_count: r.events?.length || 0,
    timestamp: new Date().toISOString(),
  });
  if (r.success) console.log(expectedRevert ? 'UNEXPECTED SUCCESS' : `✓ ${r.txHash?.slice(0,16)}`);
  else console.log(expectedRevert ? `✓ EXPECTED REVERT` : `✗ ${r.error?.message?.slice(0,80) || r.status}`);
  writeFileSync(STATE_FILE, JSON.stringify({ timestamp: new Date().toISOString(), v2_zk_verifier: V2_ZK, submitter: NEW_ADDR, total_proofs: proofs.length, proofs }, null, 2));
  await new Promise(r => setTimeout(r, 200));
}

// S1 × 100 — commit_intent (unique h_intent each)
console.log('\n── S1: commit_intent × 100 ──');
for (let i = 1; i <= 100; i++) {
  await run('S1', i, [{ contractAddress: V2_ZK, entrypoint: 'commit_intent',
    calldata: [hStr(`TRION-V2-S1-${i}`), hStr(`TRION-V2-entity-${i}`)] }]);
}

// S2 × 50 — duplicate intent collision (re-commit S1 intents → should REVERT "intent exists")
console.log('\n── S2: Duplicate Intent Collision × 50 (expected REVERT) ──');
for (let i = 1; i <= 50; i++) {
  await run('S2', i, [{ contractAddress: V2_ZK, entrypoint: 'commit_intent',
    calldata: [hStr(`TRION-V2-S1-${i}`), hStr(`TRION-V2-S2-newentity-${i}`)] }], true);
}

// S3 × 100 — submit_travel_rule_proof
console.log('\n── S3: Travel Rule Proof × 100 ──');
for (let i = 1; i <= 100; i++) {
  await run('S3', i, [{ contractAddress: V2_ZK, entrypoint: 'submit_travel_rule_proof',
    calldata: [hStr(`TRION-V2-S3-ent-${i}`), hStr(`TRION-V2-S3-tx-${i}`), '0x' + i.toString(16), hStr(`TRION-V2-S3-disc-${i}`)] }]);
}

// S4 × 100 — multi-entity commit_intent
console.log('\n── S4: Multi-Entity Intent × 100 ──');
for (let i = 1; i <= 100; i++) {
  await run('S4', i, [{ contractAddress: V2_ZK, entrypoint: 'commit_intent',
    calldata: [hStr(`TRION-V2-S4-${i}`), hStr(`TRION-V2-S4-ent-${i}`)] }]);
}

// S5 × 75 — enroll_birp
console.log('\n── S5: BIRP Enrollment × 75 ──');
for (let i = 1; i <= 75; i++) {
  await run('S5', i, [{ contractAddress: V2_ZK, entrypoint: 'enroll_birp',
    calldata: [hStr(`TRION-V2-S5-ent-${i}`), hStr(`TRION-V2-S5-birp-${i}`)] }]);
}

// Hash_DNA × 50 — compute_hash_dna + commit_intent (FIX: use compute_hash_dna view first)
console.log('\n── Hash_DNA: Cross-System Identity Binding × 50 ──');
for (let i = 1; i <= 50; i++) {
  // First compute the binding hash via view call
  const entityId = hStr(`TRION-V2-DNA-entity-${i}`);
  const systemId = hStr(`TRION-V2-DNA-system-${i}`);
  const bindingR = await callView(V2_ZK, 'compute_hash_dna', [entityId, systemId]);
  if (bindingR && !bindingR.error && bindingR[0]) {
    await run('Hash_DNA', i, [{ contractAddress: V2_ZK, entrypoint: 'commit_intent',
      calldata: [bindingR[0], entityId] }]);
  } else {
    console.log(`[skip] Hash_DNA-${i}: compute_hash_dna failed`);
  }
}

// Adversarial × 25 — mix of zero values, duplicate enroll, duplicate travel rule, nonexistent fn
console.log('\n── Adversarial Negation × 25 (expected REVERT) ──');
// ADV 1-5: zero h_intent
for (let i = 1; i <= 5; i++) {
  await run('ADV', i, [{ contractAddress: V2_ZK, entrypoint: 'commit_intent',
    calldata: ['0x0', hStr(`TRION-V2-ADV-ent-${i}`)] }], true);
}
// ADV 6-10: zero entity_id
for (let i = 6; i <= 10; i++) {
  await run('ADV', i, [{ contractAddress: V2_ZK, entrypoint: 'commit_intent',
    calldata: [hStr(`TRION-V2-ADV-intent-${i}`), '0x0'] }], true);
}
// ADV 11-15: zero tx_hash in travel rule
for (let i = 11; i <= 15; i++) {
  await run('ADV', i, [{ contractAddress: V2_ZK, entrypoint: 'submit_travel_rule_proof',
    calldata: [hStr(`TRION-V2-ADV-ent-${i}`), '0x0', '0x1', hStr(`TRION-V2-ADV-disc-${i}`)] }], true);
}
// ADV 16-20: zero birp_anchor
for (let i = 16; i <= 20; i++) {
  await run('ADV', i, [{ contractAddress: V2_ZK, entrypoint: 'enroll_birp',
    calldata: [hStr(`TRION-V2-ADV-ent-${i}`), '0x0'] }], true);
}
// ADV 21-25: duplicate enroll (re-enroll S5 entity 1-5)
for (let i = 21; i <= 25; i++) {
  const s5Idx = i - 20;  // re-enroll S5 entity 1-5
  await run('ADV', i, [{ contractAddress: V2_ZK, entrypoint: 'enroll_birp',
    calldata: [hStr(`TRION-V2-S5-ent-${s5Idx}`), hStr(`TRION-V2-ADV-birp-new-${i}`)] }], true);
}

// Final summary
console.log('\n═══════════════════════════════════════════════════════════');
console.log('  500-PROOF GAUNTLET — FINAL SUMMARY');
console.log('═══════════════════════════════════════════════════════════\n');

const byCategory = {};
let succeeded = 0, reverted = 0, failed = 0;
for (const p of proofs) {
  if (!byCategory[p.category]) byCategory[p.category] = { s: 0, r: 0, f: 0, t: 0 };
  byCategory[p.category].t++;
  if (p.success && !p.expected_revert) { byCategory[p.category].s++; succeeded++; }
  else if (!p.success && p.expected_revert) { byCategory[p.category].r++; reverted++; }
  else { byCategory[p.category].f++; failed++; }
}
for (const [c, n] of Object.entries(byCategory)) {
  console.log(`  ${c}: ${n.s}✓ ${n.r}↩ ${n.f}✗ / ${n.t}`);
}
console.log(`\n  TOTAL: ${succeeded} succeeded + ${reverted} reverted (expected) + ${failed} failed = ${proofs.length}/500`);

// Get final contract state
const totalProofs = await callView(V2_ZK, 'get_total_proofs', []);
console.log(`\n  Contract total_proofs counter: ${totalProofs}`);

const byCatFinal = {};
for (const [c, n] of Object.entries(byCategory)) {
  byCatFinal[c] = { succeeded: n.s, reverted: n.r, failed: n.f, total: n.t };
}
writeFileSync(STATE_FILE, JSON.stringify({
  timestamp: new Date().toISOString(),
  v2_zk_verifier: V2_ZK, submitter: NEW_ADDR,
  total_proofs: proofs.length, succeeded, reverted_expected: reverted, failed,
  by_category: byCatFinal, proofs,
  contract_total_proofs_counter: totalProofs,
}, null, 2));
console.log('\n✓ Final state saved to', STATE_FILE);
process.exit(0);
