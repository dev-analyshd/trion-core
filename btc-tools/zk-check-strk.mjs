const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
const NEW_ADDR = '0x0417678126db3e4eb21ca3c4dfd1b1920eb5fd2fd1e2136cbd215905be4a434d';
const OLD_ADDR = '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';
const STRK = '0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab0720188d6c1a4b6f';

async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

import { hash } from 'starknet';
const balSel = hash.getSelectorFromName('balanceOf');

// Verify STRK contract exists at this address
console.log('=== STRK contract verification ===');
const r = await rpc('starknet_getClassHashAt', ['latest', STRK]);
console.log('STRK class hash:', r.result || r.error?.message);

// Try the balanceOf selector with the right format
console.log('\n=== STRK balance ===');
const newR = await rpc('starknet_call', [{contract_address: STRK, entry_point_selector: balSel, calldata: [NEW_ADDR]}, 'latest']);
console.log('NEW wallet STRK balance:', newR.result || newR.error?.message);

const oldR = await rpc('starknet_call', [{contract_address: STRK, entry_point_selector: balSel, calldata: [OLD_ADDR]}, 'latest']);
console.log('OLD wallet STRK balance:', oldR.result || oldR.error?.message);

// Also check ETH balance
const ETH = '0x049d36570d4e46f48e99674bd3fcc84644ddd6b96f7c741b1562b82f9e004dc7';
const newEthR = await rpc('starknet_call', [{contract_address: ETH, entry_point_selector: balSel, calldata: [NEW_ADDR]}, 'latest']);
console.log('\nNEW wallet ETH balance:', newEthR.result || newEthR.error?.message);
const oldEthR = await rpc('starknet_call', [{contract_address: ETH, entry_point_selector: balSel, calldata: [OLD_ADDR]}, 'latest']);
console.log('OLD wallet ETH balance:', oldEthR.result || oldEthR.error?.message);

// Try STRK metadata
const symR = await rpc('starknet_call', [{contract_address: STRK, entry_point_selector: hash.getSelectorFromName('symbol'), calldata: []}, 'latest']);
console.log('\nSTRK symbol:', symR.result || symR.error?.message);
const nameR = await rpc('starknet_call', [{contract_address: STRK, entry_point_selector: hash.getSelectorFromName('name'), calldata: []}, 'latest']);
console.log('STRK name:', nameR.result || nameR.error?.message);
const decR = await rpc('starknet_call', [{contract_address: STRK, entry_point_selector: hash.getSelectorFromName('decimals'), calldata: []}, 'latest']);
console.log('STRK decimals:', decR.result || decR.error?.message);

// Decode the symbol/name if returned as felts
if (symR.result) {
  // STRK symbol is usually "STRK" or "FRI"
  const symHex = symR.result[1]; // second felt is the actual symbol bytes
  if (symHex) {
    const symStr = Buffer.from(symHex.replace('0x',''), 'hex').toString();
    console.log('Decoded symbol:', symStr);
  }
}
if (nameR.result) {
  const nameHex = nameR.result[1];
  if (nameHex) {
    const nameStr = Buffer.from(nameHex.replace('0x',''), 'hex').toString();
    console.log('Decoded name:', nameStr);
  }
}
