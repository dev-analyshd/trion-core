import { hash } from 'starknet';
const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

const chainId = BigInt((await rpc('starknet_chainId', [])).result);

// My submitted tx
const myTxHash = '0x54493ca83909a7d2357a62440e46faa316ea0b8c6d582be9d9c594e0bd9c9c';
const myTx = (await rpc('starknet_getTransactionByHash', [myTxHash])).result;
console.log('My tx params:');
console.log('  sender:', myTx.sender_address);
console.log('  nonce:', myTx.nonce);
console.log('  calldata:', myTx.calldata);
console.log('  resource_bounds:', myTx.resource_bounds);
console.log('  tip:', myTx.tip);
console.log('  signature:', myTx.signature);

// Compute hash using starknet.js
const resourceBounds = {
  l2_gas: { max_amount: BigInt(myTx.resource_bounds.l2_gas.max_amount), max_price_per_unit: BigInt(myTx.resource_bounds.l2_gas.max_price_per_unit) },
  l1_gas: { max_amount: BigInt(myTx.resource_bounds.l1_gas.max_amount), max_price_per_unit: BigInt(myTx.resource_bounds.l1_gas.max_price_per_unit) },
  l1_data_gas: { max_amount: BigInt(myTx.resource_bounds.l1_data_gas.max_amount), max_price_per_unit: BigInt(myTx.resource_bounds.l1_data_gas.max_price_per_unit) },
};
const v3Hash = hash.calculateInvokeTransactionHash({
  senderAddress: BigInt(myTx.sender_address),
  version: '0x3',
  compiledCalldata: myTx.calldata.map(c => BigInt(c)),
  chainId,
  nonce: BigInt(myTx.nonce),
  accountDeploymentData: [],
  nonceDataAvailabilityMode: 0,
  feeDataAvailabilityMode: 0,
  resourceBounds,
  tip: BigInt(myTx.tip || '0x0'),
  paymasterData: [],
  proofFacts: undefined,
});
console.log('\nComputed hash:', v3Hash);
console.log('Actual hash  :', myTxHash);
console.log('Match:', v3Hash === myTxHash);

// If no match, check if hash with proofFacts=[] matches
const v3HashWithProofFacts = hash.calculateInvokeTransactionHash({
  senderAddress: BigInt(myTx.sender_address),
  version: '0x3',
  compiledCalldata: myTx.calldata.map(c => BigInt(c)),
  chainId,
  nonce: BigInt(myTx.nonce),
  accountDeploymentData: [],
  nonceDataAvailabilityMode: 0,
  feeDataAvailabilityMode: 0,
  resourceBounds,
  tip: BigInt(myTx.tip || '0x0'),
  paymasterData: [],
  proofFacts: [],
});
console.log('\nWith proofFacts=[]:', v3HashWithProofFacts, 'Match:', v3HashWithProofFacts === myTxHash);
