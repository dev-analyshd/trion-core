// Try raw v3 invoke via raw JSON-RPC with manually-computed v3 transaction hash
import { ec, hash, num, CallData } from 'starknet';

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
console.log('chain:', '0x' + chainId.toString(16), ' nonce:', nonce);

const setAwaSel = hash.getSelectorFromName('set_awa_state');
// Invoke v3 calldata format (Cairo1): [call_array_len, contract, selector, calldata_len, ...args]
const callCalldata = [
  1n,
  BigInt(ZK),
  BigInt(setAwaSel),
  1n,
  0n,
];

// Compute v3 invoke tx hash using starknet.js's calculateInvokeTransactionHash
// For v3, version = 3, and resourceBounds + tip + paymasterData are needed
const resourceBounds = {
  l2_gas: { max_amount: 1_000_000n, max_price_per_unit: 1_000_000_000_000n }, // 10^12
  l1_gas: { max_amount: 100_000n, max_price_per_unit: 1_000_000_000_000_000n }, // 10^15
  l1_data_gas: { max_amount: 1_000n, max_price_per_unit: 1_000_000_000_000_000n }, // 10^15
};
const tip = 0n;
const paymasterData = [];
const accountDeploymentData = [];
const compiledCalldata = callCalldata; // already a list of bigints

const v3Hash = hash.calculateInvokeTransactionHash({
  senderAddress: BigInt(OLD_ADDR),
  version: '0x3', // V3
  compiledCalldata,
  chainId,
  nonce,
  accountDeploymentData,
  nonceDataAvailabilityMode: 0, // L1
  feeDataAvailabilityMode: 0, // L1
  resourceBounds,
  tip,
  paymasterData,
  proofFacts: undefined,
});
console.log('v3 invoke hash:', v3Hash);

// Sign with priv key
const sig = ec.starkCurve.sign(v3Hash, OLD_PRIV);
console.log('signature r:', '0x' + sig.r.toString(16));
console.log('signature s:', '0x' + sig.s.toString(16));

// Submit v3 invoke via raw JSON-RPC
console.log('\n=== Submit v3 invoke via raw JSON-RPC ===');
const invokeReq = {
  type: 'INVOKE',
  sender_address: OLD_ADDR,
  calldata: callCalldata.map(c => '0x' + c.toString(16)),
  version: '0x3',
  signature: ['0x' + sig.r.toString(16), '0x' + sig.s.toString(16)],
  nonce: '0x' + nonce.toString(16),
  resource_bounds: {
    l2_gas: { max_amount: '0xf4240', max_price_per_unit: '0xe8d4a51000' },
    l1_gas: { max_amount: '0x186a0', max_price_per_unit: '0x38d7ea4c68000' },
    l1_data_gas: { max_amount: '0x400', max_price_per_unit: '0x38d7ea4c68000' },
  },
  tip: '0x0',
  paymaster_data: [],
  nonce_data_availability_mode: 'L1',
  fee_data_availability_mode: 'L1',
  account_deployment_data: [],
};
const r = await rpc('starknet_addInvokeTransaction', [invokeReq]);
console.log('Result:', JSON.stringify(r).slice(0, 800));

if (r.result?.transaction_hash) {
  console.log('\n✓ v3 tx submitted:', r.result.transaction_hash);
  // Wait for receipt
  for (let i = 0; i < 30; i++) {
    const rcpt = await rpc('starknet_getTransactionReceipt', [r.result.transaction_hash]);
    if (rcpt.result) {
      console.log('Receipt:');
      console.log('  status:', rcpt.result.execution_status);
      console.log('  revert_reason:', rcpt.result.revert_reason);
      console.log('  actual_fee:', rcpt.result.actual_fee);
      break;
    }
    await new Promise(r => setTimeout(r, 2000));
  }
} else if (r.error) {
  console.log('\nv3 invoke failed:', r.error.message);
  console.log('  code:', r.error.code);
  console.log('  data:', JSON.stringify(r.error.data).slice(0, 500));
}

// Re-check AWA state
const isFrSel = hash.getSelectorFromName('is_awa_frozen');
const r2 = await rpc('starknet_call', [{contract_address: ZK, entry_point_selector: isFrSel, calldata: []}, 'latest']);
console.log('\nis_awa_frozen() after:', r2.result);
