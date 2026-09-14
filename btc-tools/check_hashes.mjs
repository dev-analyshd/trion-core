import { hash } from 'starknet';
const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}
const V2_ZK = '0x70786a313eb52b0b8f4781c23c8e79adb13d42e54dbeb2f229199280c4536c6';

// Compute S1-016's h_intent and check the contract directly
const s1_16_h = '0x' + hash.starknetKeccak('TRION-V2-S1-16').toString(16);
console.log('Computed S1-016 h_intent:', s1_16_h);
// Compare with stored value
console.log('Stored S1-016 h_intent:', '0xfc287bc1f324b1034a61d6cfcb3bb1be188f0c9c21e50209555fc3edfbe8e2');
console.log('Match:', s1_16_h === '0xfc287bc1f324b1034a61d6cfcb3bb1be188f0c9c21e50209555fc3edfbe8e2');

// Check S1-001 — it succeeded
const s1_1_h = '0x' + hash.starknetKeccak('TRION-V2-S1-1').toString(16);
console.log('\nComputed S1-001 h_intent:', s1_1_h);
const r1 = await rpc('starknet_call', [{contract_address: V2_ZK, entry_point_selector: hash.getSelectorFromName('intent_exists'), calldata: [s1_1_h]}, 'latest']);
console.log('intent_exists(S1-001):', r1.result);

// Check the actual stored value for S1-016's h_intent
const r2 = await rpc('starknet_call', [{contract_address: V2_ZK, entry_point_selector: hash.getSelectorFromName('intent_exists'), calldata: [s1_16_h]}, 'latest']);
console.log('intent_exists(S1-016 computed):', r2.result || r2.error);

// Maybe the script computed wrong hashes — check S1-001's stored value
const r3 = await rpc('starknet_call', [{contract_address: V2_ZK, entry_point_selector: hash.getSelectorFromName('get_intent'), calldata: [s1_1_h]}, 'latest']);
console.log('get_intent(S1-001):', r3.result || r3.error);
