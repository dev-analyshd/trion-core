const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

// My latest transfer test tx
const tx1 = '0x1940ba00216844cbddcc0cdd7618ab8429c7888ddde070e2da5c32726b6c066';
const r1 = await rpc('starknet_getTransactionReceipt', [tx1]);
console.log('NEW_ADDR transfer tx events:');
for (const ev of (r1.result?.events || [])) {
  console.log('  from:', ev.from_address);
  console.log('  keys:', ev.keys);
  console.log('  data:', ev.data);
  console.log();
}

// Compare with OLD deployer's transfer (which worked)
const tx2 = '0x10a8f24d555debb18c9851736f4f8b85998d400d17f06253065788cd664344a';
const r2 = await rpc('starknet_getTransactionReceipt', [tx2]);
console.log('\nOLD deployer transfer tx events (this one worked):');
for (const ev of (r2.result?.events || [])) {
  console.log('  from:', ev.from_address);
  console.log('  keys:', ev.keys);
  console.log('  data:', ev.data);
  console.log();
}
