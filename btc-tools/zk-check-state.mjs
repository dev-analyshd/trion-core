import { callView, NEW_ADDR, FRI } from './zk-helpers.mjs';
const newB = await callView(FRI, 'balanceOf', [NEW_ADDR]);
console.log('NEW_ADDR STRK:', Number(BigInt(newB[0]) + (BigInt(newB[1])<<128n)) / 1e18);
const r = await (await fetch('https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY', {
  method:'POST', headers:{'Content-Type':'application/json'},
  body: JSON.stringify({jsonrpc:'2.0',id:1,method:'starknet_getNonce',params:['latest', NEW_ADDR]})
})).json();
console.log('NEW_ADDR nonce:', r.result);
