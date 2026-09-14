const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

// Look at last 200 blocks
const bn = await rpc('starknet_blockNumber', []);
const curBlock = Number(BigInt(bn.result));
console.log('Current block:', curBlock);

const classHashes = new Map();
let totalV3 = 0, totalChecked = 0;
for (let i = 0; i < 200; i++) {
  const blockNum = curBlock - i;
  if (blockNum < 0) break;
  const blk = await rpc('starknet_getBlockWithTxs', [{ block_number: blockNum }]);
  if (!blk.result) continue;
  for (const tx of (blk.result.transactions || [])) {
    totalChecked++;
    if (tx.version === '0x3' && tx.sender_address) {
      totalV3++;
      const ch = await rpc('starknet_getClassHashAt', ['latest', tx.sender_address]);
      if (ch.result) {
        classHashes.set(ch.result, (classHashes.get(ch.result) || 0) + 1);
      }
    }
  }
}

console.log(`Total txs checked: ${totalChecked}, v3: ${totalV3}`);
console.log('\n=== All v3 invoke class hashes (last 200 blocks) ===');
const sorted = [...classHashes.entries()].sort((a,b) => b[1]-a[1]);
for (const [ch, count] of sorted) {
  console.log(`  ${ch}: ${count} txs (len=${ch.length})`);
}
