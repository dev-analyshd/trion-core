import { hash } from 'starknet';
const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

const MULTICALL = '0x02ceed65a4bd731034c01113685c831b01c15d7d432f71afb1cf1634b53a2125';

// Get multicall ABI
const cls = await rpc('starknet_getClassAt', ['latest', MULTICALL]);
if (!cls.result?.abi) {
  console.log('No ABI:', cls.error);
} else {
  const abi = JSON.parse(cls.result.abi);
  console.log('Multicall ABI:');
  for (const e of abi) {
    if (e.type === 'function' || e.type === 'constructor') {
      const inputs = (e.inputs || []).map(i => i.name+':'+i.type).join(', ');
      console.log(`  [${e.type}] ${e.name}(${inputs})`);
    }
  }
}

// Try calling the multicall with a call to set_awa_state(false)
console.log('\n=== Simulate multicall(set_awa_state(false)) ===');
// Common multicall function names: 'multicall', 'aggregate', 'execute'
const setAwaSel = hash.getSelectorFromName('set_awa_state');
const ZK = '0x0222c170d97af28d9cb964e81b9394be3bf9a4e1d96a85df1084a7667ef40029';
for (const fnName of ['multicall', 'aggregate', 'execute', 'invoke']) {
  const sel = hash.getSelectorFromName(fnName);
  // Standard multicall format: [calls_len, to, selector, calldata_offset, calldata_len, ..., total_calldata_len, calldata...]
  const calldata = [
    1,         // 1 call
    BigInt(ZK),
    BigInt(setAwaSel),
    0,         // calldata_offset
    1,         // calldata_len
    1,         // total calldata length
    0,         // arg = false
  ].map(c => '0x' + BigInt(c).toString(16));
  
  const r = await rpc('starknet_call', [{
    contract_address: MULTICALL,
    entry_point_selector: sel,
    calldata,
  }, 'latest']);
  console.log(`  ${fnName}():`, r.result || r.error?.message?.slice(0, 200));
}
