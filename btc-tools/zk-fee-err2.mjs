const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
const OLD_ADDR = '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';
const ZK = '0x0222c170d97af28d9cb964e81b9394be3bf9a4e1d96a85df1084a7667ef40029';

async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

// Try estimateFee WITHOUT block_id (spec v0_10 format)
const req = [{
  type: 'INVOKE',
  sender_address: OLD_ADDR,
  calldata: ['0x1', ZK, '0x20100b40110464b25140f6a7a2b76cd44d72814cf433416e3d84893501515b7', '0x1', '0x0'],
  signature: [],
  nonce: '0x61f',
  resource_bounds: {
    l2_gas: { max_amount: '0xf4240', max_price_per_unit: '0x5af3107a4000' },
    l1_gas: { max_amount: '0x0', max_price_per_unit: '0x0' },
    l1_data_gas: { max_amount: '0x400', max_price_per_unit: '0x5af3107a4000' },
  },
  tip: '0x0',
  paymaster_data: [],
  nonce_data_availability_mode: 'L1',
  fee_data_availability_mode: 'L1',
  account_deployment_data: [],
}];

// Try variant 1: params = [block_id, request]
let r = await rpc('starknet_estimateFee', ['latest', req]);
console.log('Variant 1 [latest, [req]]:', JSON.stringify(r).slice(0, 500));

// Variant 2: params = { request: [...], block_id: 'latest' }
r = await rpc('starknet_estimateFee', { block_id: 'latest', request: req });
console.log('\nVariant 2 {block_id, request:[req]}:', JSON.stringify(r).slice(0, 500));

// Variant 3: just [request] without block_id
r = await rpc('starknet_estimateFee', [req]);
console.log('\nVariant 3 [req]:', JSON.stringify(r).slice(0, 500));

// Variant 4: array as the top-level param
r = await rpc('starknet_estimateFee', req);
console.log('\nVariant 4 req (array):', JSON.stringify(r).slice(0, 500));
