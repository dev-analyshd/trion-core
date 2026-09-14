const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

// Use getBlockWithReceipts to be faster, look at last 100 blocks in parallel
const bn = await rpc('starknet_blockNumber', []);
const curBlock = Number(BigInt(bn.result));
console.log('Current block:', curBlock);

const classHashes = new Map();
let totalV3 = 0, totalChecked = 0;
// Parallel fetch 20 blocks at a time
async function fetchBlock(num) {
  const blk = await rpc('starknet_getBlockWithTxs', [{ block_number: num }]);
  if (!blk.result) return [];
  return (blk.result.transactions || []).filter(t => t.version === '0x3' && t.sender_address);
}

const blocksToScan = 100;
for (let batch = 0; batch < blocksToScan / 20; batch++) {
  const promises = [];
  for (let i = 0; i < 20; i++) {
    const num = curBlock - (batch * 20 + i);
    if (num < 0) break;
    promises.push(fetchBlock(num));
  }
  const results = await Promise.all(promises);
  for (const v3Txs of results) {
    for (const tx of v3Txs) {
      totalV3++;
      const ch = await rpc('starknet_getClassHashAt', ['latest', tx.sender_address]);
      if (ch.result) classHashes.set(ch.result, (classHashes.get(ch.result) || 0) + 1);
    }
  }
}

console.log(`v3: ${totalV3}`);
console.log('\n=== All v3 class hashes ===');
const sorted = [...classHashes.entries()].sort((a,b) => b[1]-a[1]);
for (const [ch, count] of sorted) {
  console.log(`  ${ch}: ${count} txs (len=${ch.length})`);
}
