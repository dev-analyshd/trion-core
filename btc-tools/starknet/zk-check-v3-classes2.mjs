const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

// Try multiple forms of the class hash
const hashes = [
  '0xd632f69c8e02ea43f1d8a7c3eb441c67eb935f460c02e3860f7c410115d10f',     // as-returned
  '0x0d632f69c8e02ea43f1d8a7c3eb441c67eb935f460c02e3860f7c410115d10f',     // 1 leading 0
  '0x00d632f69c8e02ea43f1d8a7c3eb441c67eb935f460c02e3860f7c410115d10f',    // 2 leading 0s
];

for (const ch of hashes) {
  console.log(`\nTrying: ${ch} (len=${ch.length})`);
  const r = await rpc('starknet_getClass', [ch]);
  if (r.error) { console.log('  err:', r.error.message); continue; }
  console.log('  ✓ declared');
  console.log('  version:', r.result?.contract_class_version);
  let abi;
  try { abi = JSON.parse(r.result?.abi || '[]'); } catch(e) { console.log('  abi parse err:', e.message); continue; }
  console.log('  abi entries:', abi.length);
  // Find all functions
  const fns = [];
  function walk(items, prefix='') {
    if (!Array.isArray(items)) return;
    for (const e of items) {
      if (e.type === 'function') fns.push(prefix + e.name);
      if (e.items) walk(e.items, prefix + (e.name||'') + '.');
      if (e.impls) walk(e.impls, prefix);
    }
  }
  walk(abi);
  console.log('  fns:', fns.length);
  const v3Fns = fns.filter(f => f.includes('v3') || f.includes('__validate'));
  console.log('  v3/validate fns:', v3Fns.slice(0,10));
  const ctor = abi.find(e => e.type === 'constructor');
  console.log('  constructor inputs:', ctor?.inputs?.map(i=>i.name+':'+i.type).join(', '));
}
