const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

// Get the most recent v3 tx
const bn = await rpc('starknet_blockNumber', []);
const curBlock = Number(BigInt(bn.result));
const blk = await rpc('starknet_getBlockWithTxs', [{ block_number: curBlock }]);
const v3Txs = (blk.result?.transactions || []).filter(t => t.version === '0x3');
const tx = v3Txs[0];
console.log('V3 tx:', tx.transaction_hash, 'sender:', tx.sender_address);

const rcpt = await rpc('starknet_getTransactionReceipt', [tx.transaction_hash]);
console.log('\nEvents from receipt:');
const events = rcpt.result?.events || [];
const senderAddr = tx.sender_address.toLowerCase();
for (const e of events) {
  // Look for events emitted by the fee token (transfer from sender to sequencer)
  const from = '0x' + BigInt(e.data?.[0] || 0).toString(16).padStart(64, '0');
  const to = '0x' + BigInt(e.data?.[1] || 0).toString(16).padStart(64, '0');
  if (from.toLowerCase() === senderAddr.toLowerCase() || to.toLowerCase() === senderAddr.toLowerCase()) {
    console.log(`  from_addr=${from.slice(0,16)}... to_addr=${to.slice(0,16)}... amount=${e.data?.[2]} (emitted by ${e.from_address?.slice(0,16)}...)`);
  }
}

// Also: starknet getEvents API to query token transfers
const ev = await rpc('starknet_getEvents', [{
  filter: { from_address: tx.sender_address, chunk_size: 5, keys: [] },
  result_page_request: { limit: 5 }
}]);
console.log('\nSender events:', JSON.stringify(ev).slice(0, 800));

// Try common Sepolia FRI addresses
// The Sepolia FRI token is typically deployed by the Starknet team
// Let me check what tokens have recent transfer events to the sequencer
const feeAmount = BigInt(rcpt.result?.actual_fee?.amount || 0);
console.log('\nFee amount:', '0x' + feeAmount.toString(16));

// Now: the fee payment must come from the sender's ETH balance (since v3 on Sepolia pays in ETH-equivalent?)
// Or it pays in FRI token. Let me check the ETH balance of the sender before/after this tx
import { hash } from 'starknet';
const balSel = hash.getSelectorFromName('balanceOf');
const ETH = '0x049d36570d4e46f48e99674bd3fcc84644ddd6b96f7c741b1562b82f9e004dc7';

// Balance at the block before the tx
const beforeR = await rpc('starknet_call', [{contract_address: ETH, entry_point_selector: balSel, calldata: [tx.sender_address]}, {block_number: curBlock - 1}]);
console.log('\nSender ETH balance before tx:', beforeR.result || beforeR.error?.message);
const afterR = await rpc('starknet_call', [{contract_address: ETH, entry_point_selector: balSel, calldata: [tx.sender_address]}, {block_number: curBlock}]);
console.log('Sender ETH balance after tx:', afterR.result || afterR.error?.message);

// Difference
if (beforeR.result && afterR.result) {
  const before = BigInt(beforeR.result[0]);
  const after = BigInt(afterR.result[0]);
  console.log('Difference:', (before - after).toString());
}

// Also check known Sepolia FRI token addresses
// The official Sepolia FRI token might be at one of these addresses
const friCandidates = [
  '0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab0720188d6c1a4b6f',
  '0x049d36570d4e46f48e99674bd3fcc84644ddd6b96f7c741b1562b82f9e004dc7',  // ETH on Sepolia
  // From starknet-foundry docs - Sepolia STRK
  '0x049d36570d4e46f48e99674bd3fcc84644ddd6b96f7c741b1562b82f9e004dc7',
];
for (const a of friCandidates) {
  const r = await rpc('starknet_call', [{contract_address: a, entry_point_selector: hash.getSelectorFromName('symbol'), calldata: []}, 'latest']);
  console.log(`\n  symbol of ${a.slice(0,16)}...:`, r.result || r.error?.message);
  const r2 = await rpc('starknet_call', [{contract_address: a, entry_point_selector: hash.getSelectorFromName('name'), calldata: []}, 'latest']);
  console.log(`  name of ${a.slice(0,16)}...:`, r2.result || r2.error?.message);
}
