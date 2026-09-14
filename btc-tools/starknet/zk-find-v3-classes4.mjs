const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

// Get a recent v3 transaction to find its sender_address
const bn = await rpc('starknet_blockNumber', []);
const curBlock = Number(BigInt(bn.result));
console.log('Current block:', curBlock);

// Find one v3 tx to inspect
for (let i = 0; i < 10; i++) {
  const blockNum = curBlock - i;
  const blk = await rpc('starknet_getBlockWithTxs', [{ block_number: blockNum }]);
  if (!blk.result) continue;
  for (const tx of (blk.result.transactions || [])) {
    if (tx.version === '0x3' && tx.sender_address) {
      console.log(`\nv3 tx ${tx.transaction_hash?.slice(0,20)}... in block ${blockNum}`);
      console.log('  sender_address:', tx.sender_address);
      // Get the actual class hash from RPC
      const ch = await rpc('starknet_getClassHashAt', ['latest', tx.sender_address]);
      console.log('  class hash (RPC):', ch.result, ' len:', ch.result?.length);
      if (ch.result) {
        // Try getClass
        const cls = await rpc('starknet_getClass', [ch.result]);
        console.log('  getClass err:', cls.error?.message);
        if (cls.result) {
          console.log('  getClass keys:', Object.keys(cls.result));
          console.log('  version:', cls.result.contract_class_version);
        }
        // Also try getClassAt
        const cls2 = await rpc('starknet_getClassAt', ['latest', tx.sender_address]);
        console.log('  getClassAt keys:', cls2.result ? Object.keys(cls2.result) : 'err');
        if (cls2.result?.abi) {
          let abi;
          try { abi = JSON.parse(cls2.result.abi); } catch(e) { abi = []; }
          console.log('  abi entries:', abi.length);
          const fns = [];
          function walk(items) {
            if (!Array.isArray(items)) return;
            for (const e of items) {
              if (e.type === 'function') fns.push(e.name);
              if (e.items) walk(e.items);
            }
          }
          walk(abi);
          const v3Fns = fns.filter(f => f.includes('v3') || f.includes('__validate'));
          console.log('  v3/validate fns:', v3Fns.slice(0, 10));
          const ctor = abi.find(e => e.type === 'constructor');
          console.log('  constructor inputs:', ctor?.inputs?.map(i=>i.name+':'+i.type).join(', '));
        }
      }
      process.exit(0);
    }
  }
}
console.log('No v3 tx found in last 10 blocks');
