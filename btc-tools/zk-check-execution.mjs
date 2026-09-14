const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

// Get the deploy_contract tx receipt (tx 0x7bb6d44af2a1b3a530002724ebacc9d97f5387c639e636ab1b97306615152dc)
const txHash1 = '0x7bb6d44af2a1b3a530002724ebacc9d97f5387c639e636ab1b97306615152dc';
const r1 = await rpc('starknet_getTransactionReceipt', [txHash1]);
console.log('Deploy_contract tx:');
console.log('  status:', r1.result?.execution_status);
console.log('  execution_resources:', r1.result?.execution_resources);
console.log('  events count:', (r1.result?.events || []).length);
console.log('  actual_fee:', r1.result?.actual_fee);

// Sample tx from another account using v3 class
const txHash2 = '0x78869f58ce7ffd70a74bcab23896e92b3106cbf1287e19d53e67fc917f76906';
const r2 = await rpc('starknet_getTransactionReceipt', [txHash2]);
console.log('\nSample v3 tx:');
console.log('  status:', r2.result?.execution_status);
console.log('  execution_resources:', r2.result?.execution_resources);
console.log('  events count:', (r2.result?.events || []).length);

// My OLD deployer's STRK transfer (which worked)
const txHash3 = '0x10a8f24d555debb18c9851736f4f8b85998d400d17f06253065788cd664344a';
const r3 = await rpc('starknet_getTransactionReceipt', [txHash3]);
console.log('\nOLD deployer STRK transfer tx:');
console.log('  status:', r3.result?.execution_status);
console.log('  execution_resources:', r3.result?.execution_resources);
console.log('  events count:', (r3.result?.events || []).length);
for (const ev of (r3.result?.events || [])) {
  console.log('  event from:', ev.from_address?.slice(0,16), 'keys:', ev.keys?.[0]?.slice(0,16));
}
