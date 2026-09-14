import { hash } from 'starknet';
const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

const bn = await rpc('starknet_blockNumber', []);
const curBlock = Number(BigInt(bn.result));
console.log('Block:', curBlock);

const blk = await rpc('starknet_getBlockWithTxs', [{ block_number: curBlock }]);
const v3Txs = (blk.result?.transactions || []).filter(t => t.version === '0x3');
const tx = v3Txs[0];
console.log('V3 tx:', tx.transaction_hash, 'sender:', tx.sender_address);

const rcpt = await rpc('starknet_getTransactionReceipt', [tx.transaction_hash]);
const events = rcpt.result?.events || [];
console.log(`\nEvents (${events.length}):`);
for (let i = 0; i < events.length; i++) {
  const e = events[i];
  console.log(`  [${i}] from_address = ${e.from_address}`);
  console.log(`      keys: ${JSON.stringify(e.keys)}`);
  console.log(`      data: ${JSON.stringify(e.data)}`);
}

// Try every unique from_address with symbol()
const uniqueFrom = new Set();
for (let i = 0; i < 3; i++) {
  const blk2 = await rpc('starknet_getBlockWithTxs', [{ block_number: curBlock - i }]);
  for (const tx2 of (blk2.result?.transactions || [])) {
    if (tx2.version !== '0x3') continue;
    const rcpt2 = await rpc('starknet_getTransactionReceipt', [tx2.transaction_hash]);
    for (const e of (rcpt2.result?.events || [])) uniqueFrom.add(e.from_address);
  }
}

const symSel = hash.getSelectorFromName('symbol');
const balSel = hash.getSelectorFromName('balanceOf');
console.log('\nUnique from_address across last 3 blocks:');
for (const a of uniqueFrom) {
  // Pad to 64 chars
  const padded = '0x' + a.replace('0x','').padStart(64, '0');
  const r2 = await rpc('starknet_call', [{contract_address: padded, entry_point_selector: symSel, calldata: []}, 'latest']);
  let sym = '';
  if (r2.result) {
    try {
      // Some tokens return symbol as ShortString (felt) directly
      sym = Buffer.from(r2.result[0].replace('0x','').padStart(64,'0'), 'hex').toString().replace(/\0/g, '').trim();
    } catch { sym = '?'; }
  } else {
    sym = r2.error?.message?.slice(0,40);
  }
  console.log(`  ${padded}: ${sym}`);
}
