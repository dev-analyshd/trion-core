import { hash } from 'starknet';
const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

const ZK = '0x0222c170d97af28d9cb964e81b9394be3bf9a4e1d96a85df1084a7667ef40029';

const setAwaSel = hash.getSelectorFromName('set_awa_state');
// Use 0x0 (hex) instead of 0 (number)
const r = await rpc('starknet_call', [{
  contract_address: ZK,
  entry_point_selector: setAwaSel,
  calldata: ['0x0'],  // false as hex
}, 'latest']);
console.log('set_awa_state(0x0):', r.result || r.error);

// Try set_awa_state(true)
const r2 = await rpc('starknet_call', [{
  contract_address: ZK,
  entry_point_selector: setAwaSel,
  calldata: ['0x1'],  // true
}, 'latest']);
console.log('set_awa_state(0x1):', r2.result || r2.error);

// Check the storage via get_intent (to verify contract is reachable)
const getIntentSel = hash.getSelectorFromName('get_intent');
const r3 = await rpc('starknet_call', [{
  contract_address: ZK,
  entry_point_selector: getIntentSel,
  calldata: ['0x1'],
}, 'latest']);
console.log('get_intent(1):', r3.result || r3.error);
