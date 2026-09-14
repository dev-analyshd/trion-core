// Minimal memory-efficient script for 100 proofs — no helper imports, single account instance
import { ec, hash, CallData, RpcProvider, Account } from 'starknet';
import { writeFileSync, readFileSync, existsSync } from 'fs';

const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
const NEW_ADDR = '0x06d58c2aa17312d090c27ac52b9f9e4a5d267675afee9dedf424b61655cc1854';
const NEW_PRIV = '0x_REDACTED_NEW_PRIV';
const NEW_ZK = '0x69457ea628e4816beb44eeda55b84a2b0cd3169aebebbea43ab10792138e54a';
const STATE_FILE = '/home/z/my-project/trion-core/docs/proofs/zk_100_proofs.json';

const L2_MAX_AMOUNT = 0x989680n, L2_MAX_PRICE = 0xba43b7400n;
const L1_MAX_AMOUNT = 0xc8n, L1_MAX_PRICE = 0x8d79883d20000n;
const L1D_MAX_AMOUNT = 0x3e8n, L1D_MAX_PRICE = 0x62448724953354n;

// Reuse single provider + account instance
const provider = new RpcProvider({ nodeUrl: RPC });
const account = new Account({ provider, address: NEW_ADDR, signer: NEW_PRIV });

// Fetch chainId + initial nonce ONCE
const chainId = BigInt((await (await fetch(RPC, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'starknet_chainId', params: [] }) })).json()).result);
let _nonce = BigInt((await (await fetch(RPC, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'starknet_getNonce', params: ['latest', NEW_ADDR] }) })).json()).result);

console.log(`chain: 0x${chainId.toString(16)}  initial nonce: ${_nonce}`);

async function rawRpc(method, params) {
  const r = await fetch(RPC, { method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ jsonrpc: '2.0', id: 1, method, params }) });
  return await r.json();
}

async function submitProof(calls, expectedRevert = false) {
  const nonce = _nonce;
  const orderCalls = calls.map(c => ({
    contractAddress: c.contractAddress,
    entrypoint: c.entrypoint,
    calldata: CallData.compile(c.calldata || []),
  }));
  const compiledCalldata = CallData.compile({ orderCalls });

  const resourceBounds = {
    l2_gas: { max_amount: L2_MAX_AMOUNT, max_price_per_unit: L2_MAX_PRICE },
    l1_gas: { max_amount: L1_MAX_AMOUNT, max_price_per_unit: L1_MAX_PRICE },
    l1_data_gas: { max_amount: L1D_MAX_AMOUNT, max_price_per_unit: L1D_MAX_PRICE },
  };

  const details = {
    version: '0x3', walletAddress: NEW_ADDR, nonce, maxFee: 0n, chainId,
    cairoVersion: '1', resourceBounds, tip: 0n, paymasterData: [], accountDeploymentData: [],
    nonceDataAvailabilityMode: 'L1', feeDataAvailabilityMode: 'L1', proofFacts: undefined,
  };
  const sig = await account.signer.signTransaction(calls, details);

  const invokeReq = {
    type: 'INVOKE', sender_address: NEW_ADDR,
    calldata: compiledCalldata.map(c => '0x' + BigInt(c).toString(16)),
    version: '0x3',
    signature: ['0x' + sig.r.toString(16), '0x' + sig.s.toString(16)],
    nonce: '0x' + nonce.toString(16),
    resource_bounds: {
      l2_gas: { max_amount: '0x' + L2_MAX_AMOUNT.toString(16), max_price_per_unit: '0x' + L2_MAX_PRICE.toString(16) },
      l1_gas: { max_amount: '0x' + L1_MAX_AMOUNT.toString(16), max_price_per_unit: '0x' + L1_MAX_PRICE.toString(16) },
      l1_data_gas: { max_amount: '0x' + L1D_MAX_AMOUNT.toString(16), max_price_per_unit: '0x' + L1D_MAX_PRICE.toString(16) },
    },
    tip: '0x0', paymaster_data: [],
    nonce_data_availability_mode: 'L1', fee_data_availability_mode: 'L1',
    account_deployment_data: [],
  };

  const r = await rawRpc('starknet_addInvokeTransaction', [invokeReq]);
  if (r.error) return { success: false, error: r.error.message, txHash: null, status: 'RPC_ERROR' };
  const txHash = r.result.transaction_hash;
  _nonce += 1n;  // increment local nonce
  // Wait for receipt (max 30s)
  for (let i = 0; i < 15; i++) {
    const rcpt = await rawRpc('starknet_getTransactionReceipt', [txHash]);
    if (rcpt.result) {
      return {
        success: rcpt.result.execution_status === 'SUCCEEDED',
        expectedRevert,
        txHash,
        status: rcpt.result.execution_status,
        revert_reason: rcpt.result.revert_reason || null,
        events_count: (rcpt.result.events || []).length,
        actual_fee: rcpt.result.actual_fee,
      };
    }
    await new Promise(r => setTimeout(r, 2000));
  }
  return { success: false, error: 'receipt_timeout', txHash, status: 'PENDING' };
}

function hStr(s) {
  return '0x' + hash.starknetKeccak(s).toString(16);
}

// Load state
let proofs = [];
if (existsSync(STATE_FILE)) {
  try {
    const saved = JSON.parse(readFileSync(STATE_FILE, 'utf8'));
    if (saved.proofs) proofs = saved.proofs;
  } catch (e) {}
}
console.log(`Loaded ${proofs.length} existing proofs. Resuming...`);

async function run(category, idx, calls, expectedRevert = false) {
  const proofId = `${category}-${String(idx).padStart(3, '0')}`;
  if (proofs.find(p => p.id === proofId)) {
    process.stdout.write(`[SKIP] ${proofId} `);
    return;
  }
  process.stdout.write(`[${proofs.length + 1}/100] ${proofId}... `);
  let r;
  try { r = await submitProof(calls, expectedRevert); }
  catch (e) { r = { success: false, error: String(e.message).slice(0,200), txHash: null, status: 'EXCEPTION' }; }
  proofs.push({
    id: proofId, category, idx,
    calls: calls.map(c => ({ to: c.contractAddress, fn: c.entrypoint, args: c.calldata })),
    expected_revert: expectedRevert,
    tx_hash: r.txHash, status: r.status, success: r.success,
    revert_reason: r.revert_reason?.slice(0, 200) || r.error?.slice(0, 200),
    actual_fee: r.actual_fee, events_count: r.events_count,
    timestamp: new Date().toISOString(),
  });
  if (r.success) console.log(expectedRevert ? 'UNEXPECTED SUCCESS' : `✓ SUCCEEDED ${r.txHash?.slice(0,16)}...`);
  else console.log(expectedRevert ? `✓ EXPECTED REVERT` : `✗ ${r.error?.slice(0,80) || r.status}`);
  // Save state
  writeFileSync(STATE_FILE, JSON.stringify({ timestamp: new Date().toISOString(), new_zk_verifier: NEW_ZK, submitter: NEW_ADDR, total_proofs: proofs.length, proofs }, null, 2));
  await new Promise(r => setTimeout(r, 300));
}

// S1 × 20
console.log('\n── S1: Intent Commitment × 20 ──');
const S1_INTENTS = [];
for (let i = 1; i <= 20; i++) {
  const hIntent = hStr(`TRION-S1-intent-${i}-fixed`);
  S1_INTENTS.push(hIntent);
  await run('S1', i, [{ contractAddress: NEW_ZK, entrypoint: 'commit_intent', calldata: [hIntent, hStr(`TRION-entity-${i}`)] }]);
}
// S2 × 15
console.log('\n── S2: Duplicate Intent × 15 ──');
for (let i = 1; i <= 15; i++) {
  const hIntent = S1_INTENTS[i - 1] || hStr(`TRION-S2-intent-${i}`);
  await run('S2', i, [{ contractAddress: NEW_ZK, entrypoint: 'commit_intent', calldata: [hIntent, hStr(`TRION-S2-newentity-${i}`)] }]);
}
// S3 × 15
console.log('\n── S3: Travel Rule Proof × 15 ──');
for (let i = 1; i <= 15; i++) {
  await run('S3', i, [{ contractAddress: NEW_ZK, entrypoint: 'submit_travel_rule_proof',
    calldata: [hStr(`TRION-S3-entity-${i}`), hStr(`TRION-S3-tx-${i}`), '0x' + i.toString(16), hStr(`TRION-S3-disc-${i}`)] }]);
}
// S4 × 20
console.log('\n── S4: Multi-Entity Intent × 20 ──');
for (let i = 1; i <= 20; i++) {
  await run('S4', i, [{ contractAddress: NEW_ZK, entrypoint: 'commit_intent',
    calldata: [hStr(`TRION-S4-intent-${i}-fixed`), hStr(`TRION-S4-entity-${i}`)] }]);
}
// S5 × 15
console.log('\n── S5: BIRP Enrollment × 15 ──');
for (let i = 1; i <= 15; i++) {
  await run('S5', i, [{ contractAddress: NEW_ZK, entrypoint: 'enroll_birp',
    calldata: [hStr(`TRION-S5-entity-${i}`), hStr(`TRION-S5-birp-${i}`)] }]);
}
// Hash_DNA × 10
console.log('\n── Hash_DNA: Cross-System Identity Binding × 10 ──');
const hashDnaBindings = [];
for (let i = 1; i <= 10; i++) {
  const entityId = BigInt(hStr(`TRION-DNA-entity-${i}`));
  const systemId = BigInt(hStr(`TRION-DNA-system-${i}`));
  const bindingHash = hash.computePedersenHashOnElements([entityId, systemId]);
  const bindingHashHex = '0x' + bindingHash.toString(16);
  hashDnaBindings.push({ idx: i, entity_id: '0x' + entityId.toString(16), system_id: '0x' + systemId.toString(16), binding_hash: bindingHashHex });
  await run('Hash_DNA', i, [{ contractAddress: NEW_ZK, entrypoint: 'commit_intent',
    calldata: [bindingHashHex, '0x' + entityId.toString(16)] }]);
}
// Adversarial × 5
console.log('\n── Adversarial Negation × 5 (expected REVERT) ──');
await run('ADV', 1, [{ contractAddress: NEW_ZK, entrypoint: 'commit_intent', calldata: ['0x0', hStr('ADV-entity-1')] }], true);
await run('ADV', 2, [{ contractAddress: NEW_ZK, entrypoint: 'commit_intent', calldata: [hStr('ADV-intent-2'), '0x0'] }], true);
await run('ADV', 3, [{ contractAddress: NEW_ZK, entrypoint: 'submit_travel_rule_proof', calldata: [hStr('ADV-entity-3'), '0x0', '0x1', hStr('ADV-disc-3')] }], true);
await run('ADV', 4, [{ contractAddress: NEW_ZK, entrypoint: 'enroll_birp', calldata: [hStr('ADV-entity-4'), '0x0'] }], true);
await run('ADV', 5, [{ contractAddress: NEW_ZK, entrypoint: 'nonexistent_adversarial_fn', calldata: ['0x0', '0x0'] }], true);

// Final summary
console.log('\n═══════════════════════════════════════════════════════════');
console.log('  100-PROOF GAUNTLET — FINAL SUMMARY');
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
console.log(`\n  TOTAL: ${succeeded} succeeded + ${reverted} reverted (expected) + ${failed} failed = ${proofs.length}/100`);

// Save final state with summary
const byCatFinal = {};
for (const [c, n] of Object.entries(byCategory)) {
  byCatFinal[c] = { succeeded: n.s, reverted: n.r, failed: n.f, total: n.t };
}
writeFileSync(STATE_FILE, JSON.stringify({
  timestamp: new Date().toISOString(),
  new_zk_verifier: NEW_ZK, submitter: NEW_ADDR,
  total_proofs: proofs.length, succeeded, reverted_expected: reverted, failed,
  by_category: byCatFinal, proofs, hash_dna_bindings: hashDnaBindings,
}, null, 2));
console.log('\n✓ Final state saved to', STATE_FILE);
process.exit(0);
