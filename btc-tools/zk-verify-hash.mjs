import { hash, CallData } from 'starknet';
const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

const chainId = BigInt((await rpc('starknet_chainId', [])).result);

// Get a recent successful v3 tx and verify hash
const bn = await rpc('starknet_blockNumber', []);
const curBlock = Number(BigInt(bn.result));
const blk = await rpc('starknet_getBlockWithTxs', [{ block_number: curBlock }]);
const v3Txs = (blk.result?.transactions || []).filter(t => t.version === '0x3' && t.type === 'INVOKE');
const tx = v3Txs[0];
console.log('Test tx:', tx.transaction_hash);

// Compute v3 hash using starknet.js
const resourceBounds = {
  l2_gas: { max_amount: BigInt(tx.resource_bounds.l2_gas.max_amount), max_price_per_unit: BigInt(tx.resource_bounds.l2_gas.max_price_per_unit) },
  l1_gas: { max_amount: BigInt(tx.resource_bounds.l1_gas.max_amount), max_price_per_unit: BigInt(tx.resource_bounds.l1_gas.max_price_per_unit) },
  l1_data_gas: { max_amount: BigInt(tx.resource_bounds.l1_data_gas.max_amount), max_price_per_unit: BigInt(tx.resource_bounds.l1_data_gas.max_price_per_unit) },
};
const nonce = BigInt(tx.nonce);
const sender = BigInt(tx.sender_address);
const compiledCalldata = tx.calldata.map(c => BigInt(c));

const v3Hash = hash.calculateInvokeTransactionHash({
  senderAddress: sender,
  version: '0x3',
  compiledCalldata,
  chainId,
  nonce,
  accountDeploymentData: [],
  nonceDataAvailabilityMode: 0,
  feeDataAvailabilityMode: 0,
  resourceBounds,
  tip: BigInt(tx.tip || '0x0'),
  paymasterData: [],
  proofFacts: undefined,
});
console.log('Computed hash:', v3Hash);
console.log('Actual hash  :', tx.transaction_hash);
console.log('Match:', v3Hash === tx.transaction_hash);
