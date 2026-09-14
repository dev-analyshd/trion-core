const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}
const txHash = '0x54493ca83909a7d2357a62440e46faa316ea0b8c6d582be9d9c594e0bd9c9c';
const r = await rpc('starknet_getTransactionByHash', [txHash]);
console.log('Transaction:');
console.log('  type:', r.result?.type);
console.log('  version:', r.result?.version);
console.log('  sender:', r.result?.sender_address);
console.log('  nonce:', r.result?.nonce);
console.log('  calldata:', r.result?.calldata);
console.log('  signature:', r.result?.signature);
console.log('  resource_bounds:', JSON.stringify(r.result?.resource_bounds, null, 2));
