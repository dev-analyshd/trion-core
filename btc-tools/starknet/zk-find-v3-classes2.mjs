const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

const bn = await rpc('starknet_blockNumber', []);
const curBlock = parseInt(bn.result, 16);
console.log('Current block:', curBlock);

// Look at last 50 blocks
const classHashes = new Map();
for (let i = 0; i < 50; i++) {
  const blockNum = curBlock - i;
  if (blockNum < 0) break;
  const blk = await rpc('starknet_getBlockWithTxs', [{ block_number: blockNum }]);
  if (!blk.result) { console.log(`  block ${blockNum}: no result`); continue; }
  const txs = blk.result.transactions || [];
  let v3Count = 0;
  for (const tx of txs) {
    if (tx.version === '0x3' || tx.version === 3) {
      v3Count++;
      const sender = tx.sender_address;
      const ch = await rpc('starknet_getClassHashAt', ['latest', sender]);
      if (ch.result) {
        const key = ch.result;
        classHashes.set(key, (classHashes.get(key) || 0) + 1);
      }
    }
  }
  if (v3Count > 0) console.log(`  block ${blockNum}: ${txs.length} txs, ${v3Count} v3`);
}

console.log('\n=== v3 invoke class hashes ===');
for (const [ch, count] of classHashes.entries()) {
  console.log(`  ${ch}: ${count} txs`);
}
