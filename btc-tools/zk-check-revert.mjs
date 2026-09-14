const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}
const txHash = '0x238ff60ac7f645f1648f70b0e93ac841cdc014212cd56e33d67243ad03d4f74';
const r = await rpc('starknet_getTransactionReceipt', [txHash]);
console.log('Full receipt:');
console.log(JSON.stringify(r.result, null, 2));
