import { hash } from 'starknet';
const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

const chainId = BigInt((await rpc('starknet_chainId', [])).result);

// Get my submitted tx (reverted)
const myTxHash = '0x54493ca83909a7d2357a62440e46faa316ea0b8c6d582be9d9c594e0bd9c9c';
const myTx = (await rpc('starknet_getTransactionByHash', [myTxHash])).result;

// Compute the actual tx hash (matches the receipt hash)
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
console.log('Computed hash:', v3Hash);
console.log('Actual hash  :', myTxHash);

// Now call is_valid_signature on the account contract with the ACTUAL sig + ACTUAL hash
const isValidSel = hash.getSelectorFromName('is_valid_signature');
const sigArr = myTx.signature;  // [r, s]
const r = await rpc('starknet_call', [{
  contract_address: myTx.sender_address,
  entry_point_selector: isValidSel,
  calldata: [v3Hash, '0x' + sigArr.length.toString(16), ...sigArr],
}, 'latest']);
console.log('\nis_valid_signature(tx_hash, tx_sig):', r.result || r.error?.message);

// Decode the result
if (r.result) {
  const result = r.result[0];
  const decoded = Buffer.from(result.replace('0x','').padStart(64,'0'), 'hex').toString().replace(/\0/g, '').trim();
  console.log('Decoded:', decoded);
}

// Also try with the sender_address in the call (so the call comes from itself, simulating __execute__)
console.log('\n=== Try calling from the account itself (using get_tx_info simulation) ===');
// starknet_call doesn't simulate get_tx_info, so we can't fully test __execute__ via call.
// But we can verify the sig is valid.
