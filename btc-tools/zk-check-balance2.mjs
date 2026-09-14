import { hash } from 'starknet';
const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

const NEW_ADDR = '0x06d58c2aa17312d090c27ac52b9f9e4a5d267675afee9dedf424b61655cc1854';
const OLD_ADDR = '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';
const FRI = '0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d';
const balSel = hash.getSelectorFromName('balanceOf');

const newR = await rpc('starknet_call', [{contract_address: FRI, entry_point_selector: balSel, calldata: [NEW_ADDR]}, 'latest']);
console.log('NEW_ADDR balance (raw):', newR.result);
if (newR.result) {
  const bal = BigInt(newR.result[0]) + (BigInt(newR.result[1]) << 128n);
  console.log('NEW_ADDR STRK:', (Number(bal) / 1e18).toFixed(6));
}

const oldR = await rpc('starknet_call', [{contract_address: FRI, entry_point_selector: balSel, calldata: [OLD_ADDR]}, 'latest']);
console.log('OLD_ADDR balance (raw):', oldR.result);
if (oldR.result) {
  const bal = BigInt(oldR.result[0]) + (BigInt(oldR.result[1]) << 128n);
  console.log('OLD_ADDR STRK:', (Number(bal) / 1e18).toFixed(6));
}

// Also check the user-provided NEW wallet address
const userNewAddr = '0x0417678126db3e4eb21ca3c4dfd1b1920eb5fd2fd1e2136cbd215905be4a434d';
const userR = await rpc('starknet_call', [{contract_address: FRI, entry_point_selector: balSel, calldata: [userNewAddr]}, 'latest']);
console.log('User NEW_ADDR balance (raw):', userR.result);
if (userR.result) {
  const bal = BigInt(userR.result[0]) + (BigInt(userR.result[1]) << 128n);
  console.log('User NEW_ADDR STRK:', (Number(bal) / 1e18).toFixed(6));
}
