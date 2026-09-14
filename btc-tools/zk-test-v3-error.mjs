import { submitV3Invoke, NEW_ADDR, FRI } from './zk-helpers.mjs';

// Try to transfer WAY more than the balance (should revert with "insufficient balance")
const hugeAmount = 1_000_000n * 10n**18n; // 1 million STRK
const amountLow = hugeAmount & ((1n << 128n) - 1n);
const amountHigh = hugeAmount >> 128n;
const OLD_ADDR = '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';

console.log('Attempting to transfer 1M STRK (more than balance)...');
const r = await submitV3Invoke([{
  contractAddress: FRI,
  entrypoint: 'transfer',
  calldata: [OLD_ADDR, '0x' + amountLow.toString(16), '0x' + amountHigh.toString(16)],
}]);
console.log('Result:', JSON.stringify({
  success: r.success,
  txHash: r.txHash,
  status: r.status,
  revert_reason: r.revert_reason?.slice(0, 300),
  events_count: r.events?.length,
}));

// Also try calling a non-existent function
console.log('\nAttempting to call non-existent function...');
const r2 = await submitV3Invoke([{
  contractAddress: FRI,
  entrypoint: 'nonexistent_function',
  calldata: [0, 0, 0],
}]);
console.log('Result:', JSON.stringify({
  success: r2.success,
  txHash: r2.txHash,
  status: r2.status,
  revert_reason: r2.revert_reason?.slice(0, 300),
}));
