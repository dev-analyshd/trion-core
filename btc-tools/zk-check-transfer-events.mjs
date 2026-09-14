const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

// Get the latest v3 tx from NEW_ADDR
const NEW_ADDR = '0x06d58c2aa17312d090c27ac52b9f9e4a5d267675afee9dedf424b61655cc1854';
const bn = await rpc('starknet_blockNumber', []);
const curBlock = Number(BigInt(bn.result));

// Search recent blocks for txs from NEW_ADDR
console.log('Looking for txs from NEW_ADDR...');
for (let i = 0; i < 30; i++) {
  const blk = await rpc('starknet_getBlockWithTxs', [{ block_number: curBlock - i }]);
  if (!blk.result) continue;
  for (const tx of (blk.result.transactions || [])) {
    if (tx.sender_address === NEW_ADDR) {
      console.log(`\nFound tx ${tx.transaction_hash.slice(0,16)}... in block ${curBlock - i}`);
      console.log('  type:', tx.type, ' version:', tx.version);
      console.log('  calldata:', tx.calldata);
      const rcpt = await rpc('starknet_getTransactionReceipt', [tx.transaction_hash]);
      console.log('  status:', rcpt.result?.execution_status);
      console.log('  events count:', (rcpt.result?.events || []).length);
      for (const ev of (rcpt.result?.events || [])) {
        console.log('  event from:', ev.from_address);
        console.log('    keys:', ev.keys);
        console.log('    data:', ev.data);
      }
      console.log('  revert_reason:', rcpt.result?.revert_reason?.slice(0, 300));
      console.log('  actual_fee:', rcpt.result?.actual_fee);
    }
  }
}
