import { submitV3Invoke, callView, NEW_ADDR } from './zk-helpers.mjs';
import { hash } from 'starknet';

const NEW_ZK = '0x69457ea628e4816beb44eeda55b84a2b0cd3169aebebbea43ab10792138e54a';

console.log('=== Test: commit_intent on new ZKVerifier ===');
const hIntent = '0x' + hash.starknetKeccak('TRION-S1-test-001').toString(16);
const entityId = '0x' + hash.starknetKeccak('entity-test-001').toString(16);
console.log('h_intent:', hIntent);
console.log('entity_id:', entityId);

const r = await submitV3Invoke([{
  contractAddress: NEW_ZK,
  entrypoint: 'commit_intent',
  calldata: [hIntent, entityId],
}]);
console.log('Result:', JSON.stringify({
  success: r.success,
  txHash: r.txHash,
  status: r.status,
  revert_reason: r.revert_reason?.slice(0, 300),
  events_count: r.events?.length,
  events_from: r.events?.map(e => e.from_address?.slice(0,16)),
}));

// Verify the intent was committed
const r2 = await callView(NEW_ZK, 'get_intent', [hIntent]);
console.log('\nget_intent result:', r2);
