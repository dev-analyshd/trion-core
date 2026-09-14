const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}
const deployTxHash = '0x7bb6d44af2a1b3a530002724ebacc9d97f5387c639e636ab1b97306615152dc';
const r = await rpc('starknet_getTransactionReceipt', [deployTxHash]);
console.log('Status:', r.result?.execution_status);
console.log('Events:');
for (const ev of (r.result?.events || [])) {
  console.log('  from:', ev.from_address);
  console.log('  keys:', ev.keys);
  console.log('  data:', ev.data);
  console.log();
}
console.log('Messages sent:', r.result?.messages_sent);
console.log('Execution resources:', r.result?.execution_resources);
