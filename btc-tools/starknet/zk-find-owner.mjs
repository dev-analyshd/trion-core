import { hash } from 'starknet';
const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

const ZK = '0x0222c170d97af28d9cb964e81b9394be3bf9a4e1d96a85df1084a7667ef40029';
const deployTx = '0x01408e9cbd87bad551c515cdc232ba85d29a5d02ecfd939e9e13f5a3e2e4031b';

// Get deploy tx receipt
const r = await rpc('starknet_getTransactionReceipt', [deployTx]);
console.log('Deploy tx receipt:');
console.log('  status:', r.result?.execution_status);
console.log('  events:');
for (const e of (r.result?.events || [])) {
  console.log('  from:', e.from_address);
  console.log('  keys:', e.keys);
  console.log('  data:', e.data);
}

// Also try getTransactionByHash to see sender
const tx = await rpc('starknet_getTransactionByHash', [deployTx]);
console.log('\nDeploy tx:');
console.log('  type:', tx.result?.type);
console.log('  sender:', tx.result?.sender_address || tx.result?.contract_address || tx.result?.deployer);
console.log('  contract_address:', tx.result?.contract_address);
console.log('  class_hash:', tx.result?.class_hash);
console.log('  constructor_calldata:', tx.result?.constructor_calldata);

// Read storage at common slots
console.log('\n=== Read storage at common owner slots ===');
const slots = [
  '0x0',  // first slot
  // owner storage variable is often at SNIP-8 standard slot
  // For Cairo1 contracts: storage var address = pedersen(sn_keccak(var_name), keys)
  // For "owner" with no keys: just sn_keccak("owner")
  '0x' + hash.starknetKeccak('owner').toString(16),
  // For AccountOwner storage:
  '0x' + hash.starknetKeccak('AccountOwner').toString(16),
  // Common OpenZeppelin storage:
  '0x' + hash.starknetKeccak('owner').toString(16),
  '0x' + hash.starknetKeccak('_owner').toString(16),
];
for (const s of slots) {
  const r = await rpc('starknet_getStorageAt', [ZK, s, 'latest']);
  if (r.result && r.result !== '0x0') {
    console.log(`  slot ${s.slice(0,16)}...: ${r.result}`);
  } else {
    console.log(`  slot ${s.slice(0,16)}...: (empty)`);
  }
}
