const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

const bn = await rpc('starknet_blockNumber', []);
const curBlock = Number(BigInt(bn.result));
console.log('Block:', curBlock);

// Get the most recent v3 INVOKE tx (we know there are many) and check its resource_bounds
// Then estimate the deploy account cost based on that
const blk = await rpc('starknet_getBlockWithTxs', [{ block_number: curBlock }]);
const txs = blk.result?.transactions || [];
console.log(`Total txs in latest block: ${txs.length}`);
for (const t of txs) {
  if (t.version === '0x3') {
    console.log(`\nTx ${t.transaction_hash?.slice(0,16)}... (${t.type}):`);
    console.log('  resource_bounds:', JSON.stringify(t.resource_bounds, null, 2));
    const rcpt = await rpc('starknet_getTransactionReceipt', [t.transaction_hash]);
    console.log('  actual_fee:', rcpt.result?.actual_fee);
    console.log('  execution_resources:', rcpt.result?.execution_resources);
    break;
  }
}

// Calculate what bounds we can afford with 50 STRK
console.log('\n=== Affordability calc for 50 STRK balance ===');
const balance = 50n * 10n**18n;
console.log('Balance:', balance.toString(), 'wei (50 STRK)');
// With low bounds that should fit
// l2_gas: 10M * 5*10^10 = 5*10^17 = 0.5 STRK
// l1_gas: 0 (skip)
// l1_data_gas: 1000 * 2.77*10^16 = 2.77*10^19 = 27.7 STRK  <-- too much
// l1_data_gas: 100 * 2.77*10^16 = 2.77*10^18 = 2.77 STRK <-- fits
const rb = {
  l2_gas: { max_amount: 10_000_000n, max_price_per_unit: 50_000_000_000n },
  l1_gas: { max_amount: 0n, max_price_per_unit: 0n },
  l1_data_gas: { max_amount: 100n, max_price_per_unit: 27_659_894_942_675_796n },
};
const total = rb.l2_gas.max_amount * rb.l2_gas.max_price_per_unit +
              rb.l1_gas.max_amount * rb.l1_gas.max_price_per_unit +
              rb.l1_data_gas.max_amount * rb.l1_data_gas.max_price_per_unit;
console.log('Total max fee (affordable):', total.toString(), '=', (Number(total) / 1e18).toFixed(4), 'STRK');
