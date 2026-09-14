import { callView } from './zk-helpers.mjs';
import { hash } from 'starknet';

const V2_ZK = '0x70786a313eb52b0b8f4781c23c8e79adb13d42e54dbeb2f229199280c4536c6';

// Check the test commit done in deploy script
const testHIntent = '0x' + hash.starknetKeccak('TRION-V2-TEST-001').toString(16);
console.log('Test h_intent (from deploy script):', testHIntent);

const r = await callView(V2_ZK, 'intent_exists', [testHIntent]);
console.log('intent_exists(test):', r);

// Check if the hash_dna test intent also exists
const dnaEntityId = hash.starknetKeccak('TRION-DNA-test-entity');
const dnaSystemId = hash.starknetKeccak('TRION-DNA-test-system');
const bindingHash = await callView(V2_ZK, 'compute_hash_dna', ['0x' + dnaEntityId.toString(16), '0x' + dnaSystemId.toString(16)]);
console.log('DNA binding hash:', bindingHash);

const r2 = await callView(V2_ZK, 'intent_exists', [bindingHash[0]]);
console.log('intent_exists(DNA):', r2);

// Check S1-016 h_intent
const s1_16_intent = '0xfc287bc1f324b1034a61d6cfcb3bb1be188f0c9c21e50209555fc3edfbe8e2';
const r3 = await callView(V2_ZK, 'intent_exists', [s1_16_intent]);
console.log('intent_exists(S1-016):', r3);
