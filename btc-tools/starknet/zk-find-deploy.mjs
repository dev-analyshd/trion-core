const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

// Get last 50 blocks and find deployAccount v3 txs
const bn = await rpc('starknet_blockNumber', []);
const curBlock = Number(BigInt(bn.result));

async function findDeployAccountInBlock(num) {
  const blk = await rpc('starknet_getBlockWithTxs', [{ block_number: num }]);
  return (blk.result?.transactions || []).filter(t => t.type === 'DEPLOY_ACCOUNT' && t.version === '0x3');
}

let found = null;
for (let i = 0; i < 30; i++) {
  const txs = await findDeployAccountInBlock(curBlock - i);
  if (txs.length > 0) {
    found = txs[0];
    console.log(`Found deployAccount in block ${curBlock - i}:`, found.transaction_hash);
    break;
  }
}

if (found) {
  console.log('resource_bounds:', JSON.stringify(found.resource_bounds, null, 2));
  console.log('contract_address_salt:', found.contract_address_salt);
  console.log('class_hash:', found.class_hash);
  console.log('constructor_calldata:', found.constructor_calldata);
  // Get receipt for actual_fee and balance check
  const rcpt = await rpc('starknet_getTransactionReceipt', [found.transaction_hash]);
  console.log('actual_fee:', rcpt.result?.actual_fee);
  console.log('execution_resources:', rcpt.result?.execution_resources);
}
