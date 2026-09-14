const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

const bn = await rpc('starknet_blockNumber', []);
const curBlock = Number(BigInt(bn.result));
console.log('Current block:', curBlock, '(hex:', bn.result, ')');

const classHashes = new Map();
// Look at last 20 blocks
for (let i = 0; i < 20; i++) {
  const blockNum = curBlock - i;
  if (blockNum < 0) break;
  const blk = await rpc('starknet_getBlockWithTxs', [{ block_number: blockNum }]);
  if (!blk.result) { console.log(`  block ${blockNum}: no result`, blk.error?.message); continue; }
  const txs = blk.result.transactions || [];
  let v3Count = 0;
  for (const tx of txs) {
    if (tx.version === '0x3' || tx.version === 3 || (tx.type === 'INVOKE' && tx.version && Number(BigInt(tx.version)) === 3)) {
      v3Count++;
      const sender = tx.sender_address;
      if (!sender) continue;
      const ch = await rpc('starknet_getClassHashAt', ['latest', sender]);
      if (ch.result) {
        classHashes.set(ch.result, (classHashes.get(ch.result) || 0) + 1);
      }
    }
  }
  if (v3Count > 0) console.log(`  block ${blockNum}: ${txs.length} txs, ${v3Count} v3`);
}

console.log('\n=== v3 invoke class hashes ===');
for (const [ch, count] of classHashes.entries()) {
  console.log(`  ${ch}: ${count} txs`);
}

// For each class hash, check if __validate_invoke_v3__ works by inspecting the ABI
console.log('\n=== Inspect each class ABI for v3 entrypoints ===');
for (const ch of classHashes.keys()) {
  const r = await rpc('starknet_getClass', [ch]);
  if (!r.result) continue;
  let abi;
  try { abi = JSON.parse(r.result.abi); } catch { continue; }
  const allNames = [];
  function walk(items) {
    if (!Array.isArray(items)) return;
    for (const e of items) {
      if (e.type === 'function' || e.type === 'impl') allNames.push(e.name);
      if (e.items) walk(e.items);
      if (e.impls) walk(e.impls);
      if (e.functions) walk(e.functions);
    }
  }
  walk(abi);
  const v3Fns = allNames.filter(f => f && (f.includes('v3') || f.includes('V3')));
  console.log(`  ${ch.slice(0,20)}...: v3 fns:`, v3Fns.slice(0,8).join(', '));
}
