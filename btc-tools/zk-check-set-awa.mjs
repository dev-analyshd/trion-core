import { hash } from 'starknet';
const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

const ZK = '0x0222c170d97af28d9cb964e81b9394be3bf9a4e1d96a85df1084a7667ef40029';
const OLD_ADDR = '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';

// Call set_awa_state(false) as a simulation
const setAwaSel = hash.getSelectorFromName('set_awa_state');
const r = await rpc('starknet_call', [{
  contract_address: ZK,
  entry_point_selector: setAwaSel,
  calldata: [0],  // false
}, 'latest']);
console.log('set_awa_state(false) call:', r.result || r.error);

// Get ZKVerifier ABI and check for owner functions
const cls = await rpc('starknet_getClassAt', ['latest', ZK]);
const abi = JSON.parse(cls.result.abi);
console.log('\n=== ZKVerifier full ABI ===');
for (const e of abi) {
  if (e.type === 'function' || e.type === 'constructor' || e.type === 'event') {
    const inputs = (e.inputs || []).map(i => i.name+':'+i.type).join(', ');
    console.log(`  [${e.type}] ${e.name}(${inputs})`);
  }
}

// Check owner / access control via get_owner or owner()
const ownerSel = hash.getSelectorFromName('owner');
const r2 = await rpc('starknet_call', [{
  contract_address: ZK,
  entry_point_selector: ownerSel,
  calldata: [],
}, 'latest']);
console.log('\nowner():', r2.result || r2.error?.message);

const getOwnerSel = hash.getSelectorFromName('get_owner');
const r3 = await rpc('starknet_call', [{
  contract_address: ZK,
  entry_point_selector: getOwnerSel,
  calldata: [],
}, 'latest']);
console.log('get_owner():', r3.result || r3.error?.message);

// Check if there's a get_admin or similar
for (const sel of ['admin', 'admin_address', 'get_admin']) {
  const s = hash.getSelectorFromName(sel);
  const r = await rpc('starknet_call', [{contract_address: ZK, entry_point_selector: s, calldata: []}, 'latest']);
  if (r.result) console.log(`${sel}():`, r.result);
}
