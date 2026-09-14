import { hash } from 'starknet';
const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

const ZK = '0x0222c170d97af28d9cb964e81b9394be3bf9a4e1d96a85df1084a7667ef40029';
const OLD_ADDR = '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';
const NEW_ADDR = '0x0417678126db3e4eb21ca3c4dfd1b1920eb5fd2fd1e2136cbd215905be4a434d';

// Read storage at various slots — try Cairo1 Ownable component storage names
const slotNames = [
  'owner',
  'Owner',
  '_owner',
  'Ownable_owner',
  'Ownable_Ownable_owner',
  'admin',
  'Admin',
  'authority',
  'Authority',
  'awa_owner',
  'zk_owner',
];

console.log('=== Storage slot scan ===');
for (const name of slotNames) {
  const slotHash = '0x' + hash.starknetKeccak(name).toString(16).padStart(64, '0');
  const r = await rpc('starknet_getStorageAt', [ZK, slotHash, 'latest']);
  if (r.result && r.result !== '0x0') {
    console.log(`  ${name}: ${r.result}`);
  }
}

// Also try with the contract address as part of the slot
console.log('\n=== Try with addresses as keys ===');
for (const name of ['owner']) {
  for (const key of [OLD_ADDR, NEW_ADDR, ZK, '0x0', '0x1']) {
    // Cairo1 storage: pedersen(sn_keccak(var_name), keys)
    const baseSlot = hash.starknetKeccak(name);
    // For 1 key: pedersen(baseSlot, key)
    // Note: starknet.js's pedersen takes [a, b]
    const slot1 = hash.computePedersenHashOnElements([baseSlot, BigInt(key)]);
    const slotHex = '0x' + slot1.toString(16).padStart(64, '0');
    const r = await rpc('starknet_getStorageAt', [ZK, slotHex, 'latest']);
    if (r.result && r.result !== '0x0') {
      console.log(`  ${name}[${key.slice(0,16)}...]: ${r.result}`);
    }
  }
}

// Also check the contract's compiled Sierra to find storage variable names
console.log('\n=== Check compiled Sierra for storage vars ===');
const cls = await rpc('starknet_getClassAt', ['latest', ZK]);
if (cls.result?.abi) {
  const abi = JSON.parse(cls.result.abi);
  // Find storage-related items
  for (const e of abi) {
    if (e.type === 'struct' || e.type === 'impl') {
      console.log(`  [${e.type}] ${e.name}`);
    }
  }
}
