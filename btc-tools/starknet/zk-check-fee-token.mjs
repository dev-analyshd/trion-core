const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

// Get the most recent v3 tx
const bn = await rpc('starknet_blockNumber', []);
const curBlock = Number(BigInt(bn.result));
console.log('Block:', curBlock);

const blk = await rpc('starknet_getBlockWithTxs', [{ block_number: curBlock }]);
const v3Txs = (blk.result?.transactions || []).filter(t => t.version === '0x3');
console.log('V3 txs in latest block:', v3Txs.length);

if (v3Txs.length > 0) {
  const tx = v3Txs[0];
  console.log('\nV3 tx:', tx.transaction_hash);
  console.log('  sender:', tx.sender_address);
  console.log('  resource_bounds:', JSON.stringify(tx.resource_bounds));
  console.log('  paymaster_data:', tx.paymaster_data);
  console.log('  nonce_data_availability_mode:', tx.nonce_data_availability_mode);
  console.log('  fee_data_availability_mode:', tx.fee_data_availability_mode);

  // Get receipt to see fee_token
  const rcpt = await rpc('starknet_getTransactionReceipt', [tx.transaction_hash]);
  console.log('\nReceipt:');
  console.log('  execution_status:', rcpt.result?.execution_status);
  console.log('  actual_fee:', rcpt.result?.actual_fee);
  console.log('  actual_fee object:', JSON.stringify(rcpt.result?.actual_fee));
  console.log('  fee_token_address:', rcpt.result?.actual_fee?.token_address);
  console.log('  full receipt keys:', Object.keys(rcpt.result || {}));
}

// Also check if STRK contract is deployed anywhere on Sepolia by looking at common addresses
const STRK = '0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab0720188d6c1a4b6f';
const ETH = '0x049d36570d4e46f48e99674bd3fcc84644ddd6b96f7c741b1562b82f9e004dc7';
console.log('\n=== Fee tokens ===');
let r = await rpc('starknet_getClassHashAt', ['latest', ETH]);
console.log('ETH class hash:', r.result || r.error?.message);
r = await rpc('starknet_getClassHashAt', ['latest', STRK]);
console.log('STRK class hash:', r.result || r.error?.message);

// Also try common STRK addresses for Sepolia
const strkCandidates = [
  '0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab0720188d6c1a4b6f', // mainnet
  // Other possible Sepolia STRK addresses
  '0x045f8eb8d2e1f7c4f5a3b6e7d8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7',
];
for (const a of strkCandidates) {
  r = await rpc('starknet_getClassHashAt', ['latest', a]);
  console.log(`  ${a.slice(0,16)}...:`, r.result || r.error?.message);
}
