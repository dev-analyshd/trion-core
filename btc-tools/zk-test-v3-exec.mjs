import { submitV3Invoke, callView, NEW_ADDR, FRI } from './zk-helpers.mjs';
import { hash } from 'starknet';

const OLD_ADDR = '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';

// Check balances before
const newBefore = await callView(FRI, 'balanceOf', [NEW_ADDR]);
const oldBefore = await callView(FRI, 'balanceOf', [OLD_ADDR]);
console.log('Before:');
console.log('  NEW_ADDR:', Number(BigInt(newBefore[0]) + (BigInt(newBefore[1])<<128n)) / 1e18, 'STRK');
console.log('  OLD_ADDR:', Number(BigInt(oldBefore[0]) + (BigInt(oldBefore[1])<<128n)) / 1e18, 'STRK');

// Transfer 0.001 STRK (10^15 wei) from NEW to OLD
const amount = 1n * 10n**15n; // 0.001 STRK
const amountLow = amount & ((1n << 128n) - 1n);
const amountHigh = amount >> 128n;
console.log(`\nTransferring 0.001 STRK (${amount} wei) from NEW to OLD...`);

const r = await submitV3Invoke([{
  contractAddress: FRI,
  entrypoint: 'transfer',
  calldata: [OLD_ADDR, '0x' + amountLow.toString(16), '0x' + amountHigh.toString(16)],
}]);
console.log('Result:', JSON.stringify({
  success: r.success,
  txHash: r.txHash,
  status: r.status,
  revert_reason: r.revert_reason?.slice(0, 200),
  events_count: r.events?.length,
  events_from: r.events?.map(e => e.from_address?.slice(0,16)),
}));

// Check balances after
const newAfter = await callView(FRI, 'balanceOf', [NEW_ADDR]);
const oldAfter = await callView(FRI, 'balanceOf', [OLD_ADDR]);
console.log('\nAfter:');
console.log('  NEW_ADDR:', Number(BigInt(newAfter[0]) + (BigInt(newAfter[1])<<128n)) / 1e18, 'STRK');
console.log('  OLD_ADDR:', Number(BigInt(oldAfter[0]) + (BigInt(oldAfter[1])<<128n)) / 1e18, 'STRK');
const diff = BigInt(oldAfter[0]) - BigInt(oldBefore[0]);
console.log('  OLD_ADDR diff:', Number(diff) / 1e18, 'STRK');
