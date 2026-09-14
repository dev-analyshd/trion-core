import { ec, hash, CallData } from 'starknet';

const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
const OLD_ADDR = '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';
const OLD_PRIV = '0x_REDACTED_OLD_PRIV';
const ZK = '0x0222c170d97af28d9cb964e81b9394be3bf9a4e1d96a85df1084a7667ef40029';

async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

const chainId = BigInt((await rpc('starknet_chainId', [])).result);
const nonce = BigInt((await rpc('starknet_getNonce', ['latest', OLD_ADDR])).result);

// Build cairo1 compiled calldata
const calls = [{
  contractAddress: ZK,
  entrypoint: 'set_awa_state',
  calldata: [0],
}];
const orderCalls = calls.map(c => ({
  contractAddress: c.contractAddress,
  entrypoint: c.entrypoint,
  calldata: CallData.compile(c.calldata || []),
}));
const compiledCalldata = CallData.compile({ orderCalls });
console.log('compiledCalldata:', compiledCalldata);

const resourceBounds = {
  l2_gas: { max_amount: 0x5f5e100n, max_price_per_unit: 0xba43b7400n },
  l1_gas: { max_amount: 0x11170n, max_price_per_unit: 0x8d79883d20000n },
  l1_data_gas: { max_amount: 0x2710n, max_price_per_unit: 0x62448724953354n },
};

// Compute v3 invoke hash via starknet.js
const v3Hash = hash.calculateInvokeTransactionHash({
  senderAddress: BigInt(OLD_ADDR),
  version: '0x3',
  compiledCalldata: compiledCalldata.map(c => BigInt(c)),
  chainId,
  nonce,
  accountDeploymentData: [],
  nonceDataAvailabilityMode: 0,
  feeDataAvailabilityMode: 0,
  resourceBounds,
  tip: 0n,
  paymasterData: [],
  proofFacts: undefined,
});
console.log('v3 hash (computed):', v3Hash);

// Sign
const sig = ec.starkCurve.sign(v3Hash, OLD_PRIV);
const sigArr = ['0x' + sig.r.toString(16), '0x' + sig.s.toString(16)];
console.log('signature:', sigArr);

// Now call is_valid_signature on the account contract
const isValidSel = hash.getSelectorFromName('is_valid_signature');
const r = await rpc('starknet_call', [{
  contract_address: OLD_ADDR,
  entry_point_selector: isValidSel,
  calldata: [v3Hash, '0x' + sigArr.length.toString(16), ...sigArr],
}, 'latest']);
console.log('\nis_valid_signature result:', r.result || r.error?.message);
