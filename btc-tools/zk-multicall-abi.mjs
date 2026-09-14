const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

const MULTICALL = '0x02ceed65a4bd731034c01113685c831b01c15d7d432f71afb1cf1634b53a2125';

// Print raw ABI
const cls = await rpc('starknet_getClassAt', ['latest', MULTICALL]);
console.log('Multicall class keys:', cls.result ? Object.keys(cls.result) : 'err');
if (cls.result?.abi) {
  console.log('ABI length:', cls.result.abi.length);
  console.log('ABI first 2000 chars:');
  console.log(cls.result.abi.slice(0, 2000));
}
