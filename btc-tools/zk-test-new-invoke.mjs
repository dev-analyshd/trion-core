import { submitV3Invoke, NEW_ADDR, FRI } from './zk-helpers.mjs';
import { hash } from 'starknet';

console.log('=== Test: transfer 1 wei STRK from NEW_ADDR to OLD_ADDR ===');
const OLD_ADDR = '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';

const r = await submitV3Invoke([{
  contractAddress: FRI,
  entrypoint: 'transfer',
  calldata: [OLD_ADDR, '0x1', '0x0'], // 1 wei
}]);
console.log('Result:', JSON.stringify(r, null, 2).slice(0, 600));

// Check balances
import { callView } from './zk-helpers.mjs';
const balSel = hash.getSelectorFromName('balanceOf');
const newBal = await callView(FRI, 'balanceOf', [NEW_ADDR]);
const oldBal = await callView(FRI, 'balanceOf', [OLD_ADDR]);
console.log('\nNEW_ADDR STRK:', newBal ? (Number(BigInt(newBal[0]) + (BigInt(newBal[1])<<128n))/1e18).toFixed(6) : 'err');
console.log('OLD_ADDR STRK:', oldBal ? (Number(BigInt(oldBal[0]) + (BigInt(oldBal[1])<<128n))/1e18).toFixed(6) : 'err');

// Test calling set_awa_state on the EXISTING ZKVerifier (will revert with "Not owner")
const ZK_EXISTING = '0x0222c170d97af28d9cb964e81b9394be3bf9a4e1d96a85df1084a7667ef40029';
console.log('\n=== Test: call set_awa_state(false) on EXISTING ZKVerifier ===');
const r2 = await submitV3Invoke([{
  contractAddress: ZK_EXISTING,
  entrypoint: 'set_awa_state',
  calldata: [0],
}]);
console.log('Result:', JSON.stringify(r2, null, 2).slice(0, 600));
