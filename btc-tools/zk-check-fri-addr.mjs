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

// Print full from_address of every event
for (let i = 0; i < events.length; i++) {
  const e = events[i];
  console.log(`  [${i}] full from_address = ${e.from_address}`);
  console.log(`      keys (${e.keys?.length}): ${JSON.stringify(e.keys)}`);
  console.log(`      data (${e.data?.length}): ${JSON.stringify(e.data)}`);
}

// The fee_token_address can be fetched from starknet_getBlockHashStrByNumber's events
// Actually let's check several common addresses by querying their class hashes
// STRK is on Sepolia, just maybe at a different address

// Search the latest 5 blocks for v3 txs with from_address not equal to anything we know
// and identify unique from_addresses in events
const uniqueFrom = new Set();
for (let i = 0; i < 5; i++) {
  const blk2 = await rpc('starknet_getBlockWithTxs', [{ block_number: curBlock - i }]);
  const txs = (blk2.result?.transactions || []).filter(t => t.version === '0x3');
  for (const tx2 of txs) {
    const rcpt2 = await rpc('starknet_getTransactionReceipt', [tx2.transaction_hash]);
    for (const e of (rcpt2.result?.events || [])) {
      uniqueFrom.add(e.from_address);
    }
  }
}

console.log('\nUnique from_address across last 5 blocks events:');
for (const a of uniqueFrom) {
  console.log(`  ${a}`);
  // Check if this is the STRK token by calling symbol
  const symR = await rpc('starknet_call', [{contract_address: a, entry_point_selector: '0x2e4263afad30923c891518314c3aae71e0f5b0170f6e21b84d97f4f0c4b3543', calldata: []}, 'latest']);
  // Wait — let me use the correct balanceOf selector
  // Try common selectors
  import { hash } from 'starknet';
  const balSel = hash.getSelectorFromName('balanceOf');
  const symSel = hash.getSelectorFromName('symbol');
  const r2 = await rpc('starknet_call', [{contract_address: a, entry_point_selector: symSel, calldata: []}, 'latest']);
  if (r2.result) {
    // Symbol is a shortstring (felt)
    const symHex = r2.result[0];
    if (symHex && symHex !== '0x0') {
      const symStr = Buffer.from(symHex.replace('0x','').padStart(64,'0'), 'hex').toString().replace(/\0/g, '');
      console.log(`    symbol: '${symStr}'`);
    }
  }
}
