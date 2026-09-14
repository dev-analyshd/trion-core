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
const cls = await rpc('starknet_getClass', [ch]);
console.log('class keys:', Object.keys(cls.result || {}));
console.log('class abi type:', Array.isArray(cls.result?.abi) ? 'array' : typeof cls.result?.abi);
console.log('class abi[0]:', JSON.stringify(cls.result?.abi?.[0]).slice(0, 300));
console.log('class abi[1]:', JSON.stringify(cls.result?.abi?.[1]).slice(0, 300));
console.log('class abi[2]:', JSON.stringify(cls.result?.abi?.[2]).slice(0, 300));

// Print all entry names + types
console.log('\nAll ABI entries:');
for (const e of (cls.result?.abi || [])) {
  console.log(`  [${e.type || 'unknown'}]:`, JSON.stringify(e).slice(0, 200));
}

// Print program entry_points
console.log('\nProgram entry points:');
const progs = cls.result?.program?.entry_points_by_type || {};
for (const [t, eps] of Object.entries(progs)) {
  for (const ep of eps) {
    console.log(`  ${t}: ${ep.selector} (offset ${ep.offset})`);
  }
}
