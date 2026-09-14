const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

const bn = await rpc('starknet_blockNumber', []);
const curBlock = Number(BigInt(bn.result));
const blk = await rpc('starknet_getBlockWithTxs', [{ block_number: curBlock }]);
const v3Txs = (blk.result?.transactions || []).filter(t => t.version === '0x3');
const tx = v3Txs[0];
console.log('V3 tx:', tx.transaction_hash, 'sender:', tx.sender_address);

const rcpt = await rpc('starknet_getTransactionReceipt', [tx.transaction_hash]);
const events = rcpt.result?.events || [];
console.log(`\nTotal events: ${events.length}`);
console.log('\nAll events:');
for (let i = 0; i < Math.min(events.length, 20); i++) {
  const e = events[i];
  console.log(`  [${i}] from=${e.from_address?.slice(0,16)}... keys=[${(e.keys||[]).map(k=>k.slice(0,10)).join(',')}] data=[${(e.data||[]).map(d=>d.slice(0,16)).join(',')}]`);
}

// Find the fee payment event — typically emitted by the fee token contract
// and contains a Transfer event with sender → sequencer
console.log('\nLooking for fee token contract (transfer events from sender)...');
import { hash } from 'starknet';
const transferSel = hash.getSelectorFromName('Transfer');  // ERC20 Transfer event selector

// Search for Transfer events
for (const e of events) {
  if (e.keys && e.keys[0] === transferSel) {
    console.log(`  Transfer event from ${e.from_address?.slice(0,20)}...`);
    console.log(`    data: from=${e.data?.[0]?.slice(0,20)}... to=${e.data?.[1]?.slice(0,20)}... amount=${e.data?.[2]}`);
    if (e.data?.[0]?.toLowerCase() === tx.sender_address.toLowerCase() || e.data?.[1]?.toLowerCase() === tx.sender_address.toLowerCase()) {
      console.log(`    *** FEE TOKEN CONTRACT: ${e.from_address}`);
    }
  }
}

// Also try starknet_getEvents for the block
const ev = await rpc('starknet_getEvents', [{
  filter: { chunk_size: 50 },
  result_page_request: { limit: 50 }
}]);
console.log('\ngetEvents result:', JSON.stringify(ev).slice(0, 1000));
