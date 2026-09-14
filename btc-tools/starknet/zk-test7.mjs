const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
const ZK = '0x0222c170d97af28d9cb964e81b9394be3bf9a4e1d96a85df1084a7667ef40029';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}
const r = await rpc('starknet_getClassAt', ['latest', ZK]);
const abi = JSON.parse(r.result.abi);
console.log('=== ZKVerifier ABI ===');
for (const e of abi) {
  if (e.type === 'function' || e.type === 'constructor' || e.type === 'event') {
    const inputs = (e.inputs || []).map(i => `${i.name}:${i.type}`).join(', ');
    console.log(`  [${e.type}] ${e.name}(${inputs})`);
  }
}
