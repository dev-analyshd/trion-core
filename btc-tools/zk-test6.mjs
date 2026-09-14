const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
const ZK = '0x0222c170d97af28d9cb964e81b9394be3bf9a4e1d96a85df1084a7667ef40029';

async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}
const r = await rpc('starknet_getClassHashAt', ['latest', ZK]);
const ch = r.result;
console.log('class hash:', ch);

// Try starknet_getClass (legacy format for cairo0)
const cls = await rpc('starknet_getClass', [ch]);
console.log('Result keys:', Object.keys(cls.result || {}));
console.log('ABI present:', !!cls.result?.abi, ' Program present:', !!cls.result?.program);
console.log('ABI type:', typeof cls.result?.abi);
if (typeof cls.result?.abi === 'string') {
  console.log('ABI string first 500 chars:', cls.result.abi.slice(0, 500));
}
if (Array.isArray(cls.result?.abi)) {
  console.log('ABI[0]:', JSON.stringify(cls.result.abi[0]).slice(0, 300));
}

// Try starknet_getClassAt which may use a different format
const cls2 = await rpc('starknet_getClassAt', ['latest', ZK]);
console.log('\ngetClassAt result keys:', Object.keys(cls2.result || {}));
console.log('getClassAt ABI present:', !!cls2.result?.abi);
console.log('getClassAt ABI type:', typeof cls2.result?.abi);
if (typeof cls2.result?.abi === 'string') {
  console.log('getClassAt ABI first 500 chars:', cls2.result.abi.slice(0, 500));
}
