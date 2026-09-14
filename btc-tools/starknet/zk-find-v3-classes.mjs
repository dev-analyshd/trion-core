const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';

async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

// Get latest block
const bn = await rpc('starknet_blockNumber', []);
console.log('Current block:', bn.result);

// Find recent v3 transactions by scanning the last few blocks
const classHashes = new Map(); // classHash → count

// Get the latest 10 blocks
for (let i = 0; i < 10; i++) {
  const blockNum = parseInt(bn.result, 16) - i;
  if (blockNum < 0) break;
  const blk = await rpc('starknet_getBlockWithTxs', [{ block_number: blockNum }]);
  if (!blk.result) continue;
  const txs = blk.result.transactions || [];
  for (const tx of txs) {
    if (tx.type === 'INVOKE' && tx.version === '0x3') {
      const sender = tx.sender_address;
      const ch = await rpc('starknet_getClassHashAt', ['latest', sender]);
      if (ch.result) {
        const key = ch.result;
        classHashes.set(key, (classHashes.get(key) || 0) + 1);
      }
    }
  }
}

console.log('\n=== v3 invoke class hashes seen in last 10 blocks ===');
for (const [ch, count] of classHashes.entries()) {
  console.log(`  ${ch}: ${count} txs`);
}

// Inspect the first one's ABI to confirm it has __validate_invoke_v3__
console.log('\n=== Inspect each class hash ABI for __validate_invoke_v3__ ===');
for (const ch of classHashes.keys()) {
  const r = await rpc('starknet_getClass', [ch]);
  if (!r.result) continue;
  let abi;
  try { abi = JSON.parse(r.result.abi); } catch { continue; }
  // Find __validate_invoke_v3__ function
  const allFns = [];
  function walk(items, prefix='') {
    if (!Array.isArray(items)) return;
    for (const e of items) {
      if (e.type === 'function') {
        const fullName = prefix + e.name;
        allFns.push(fullName);
        // Also check impl items
      }
      if (e.items) walk(e.items, prefix + (e.name||'') + '::');
      if (e.impls) walk(e.impls, prefix);
    }
  }
  walk(abi);
  const hasV3 = allFns.some(f => f.includes('__validate_invoke_v3') || f.includes('validate_v3'));
  console.log(`  ${ch.slice(0,20)}...: has_v3_validate=${hasV3?'✓':'✗'} version=${r.result.contract_class_version}`);
  if (hasV3) console.log(`    matching fns:`, allFns.filter(f => f.includes('v3')).slice(0,5));
}
