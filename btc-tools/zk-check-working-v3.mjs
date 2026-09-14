const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

// Find a recent successful v3 invoke from another account using the v3 class
const bn = await rpc('starknet_blockNumber', []);
const curBlock = Number(BigInt(bn.result));

// Get the most recent successful v3 tx from sender 0x15569a4dae53e13da0b0f9332d88539c96db79858b14fb15e571a9f46b6c1be
const SAMPLE_ADDR = '0x15569a4dae53e13da0b0f9332d88539c96db79858b14fb15e571a9f46b6c1be';
for (let i = 0; i < 50; i++) {
  const blk = await rpc('starknet_getBlockWithTxs', [{ block_number: curBlock - i }]);
  if (!blk.result) continue;
  for (const tx of (blk.result.transactions || [])) {
    if (tx.version === '0x3' && tx.sender_address === SAMPLE_ADDR) {
      console.log('Found sample tx:', tx.transaction_hash);
      console.log('  calldata:', tx.calldata);
      const rcpt = await rpc('starknet_getTransactionReceipt', [tx.transaction_hash]);
      console.log('  status:', rcpt.result?.execution_status);
      console.log('  events count:', (rcpt.result?.events || []).length);
      for (const ev of (rcpt.result?.events || []).slice(0, 5)) {
        console.log('  event from:', ev.from_address?.slice(0,16));
        console.log('    keys[0]:', ev.keys?.[0]?.slice(0,16));
        console.log('    data:', ev.data?.slice(0, 4));
      }
      process.exit(0);
    }
  }
}
