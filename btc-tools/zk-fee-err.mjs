const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
const OLD_ADDR = '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';
const ZK = '0x0222c170d97af28d9cb964e81b9394be3bf9a4e1d96a85df1084a7667ef40029';

async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

// Call starknet_estimateFee directly with v3 invoke
const req = [{
  type: 'INVOKE',
  sender_address: OLD_ADDR,
  calldata: [
    '0x1',  // call_array_len
    '0x222c170d97af28d9cb964e81b9394be3bf9a4e1d96a85df1084a7667ef40029',
    '0x20100b40110464b25140f6a7a2b76cd44d72814cf433416e3d84893501515b7',
    '0x1', '0x0',
  ],
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
const r = await rpc('starknet_estimateFee', [{ block_id: 'latest' }, req]);
console.log('Result:', JSON.stringify(r, null, 2));
