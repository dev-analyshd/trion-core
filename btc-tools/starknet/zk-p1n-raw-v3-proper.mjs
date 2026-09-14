// Use starknet.js's built-in calldata compiler for proper v3 invoke
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
console.log('chain:', '0x' + chainId.toString(16), ' nonce:', nonce);

// Build the call using starknet.js's transformCallsToMulticallArrays internally
// We can call fromCallsToExecuteCalldata via CallData's compiler
// The cairo0 invoke format (used by OZ Cairo1 0.1.0):
// [call_array_len, to_1, selector_1, data_offset_1, data_len_1, ..., total_len, calldata_1, ..., calldata_K]
const call = {
  contractAddress: ZK,
  entrypoint: 'set_awa_state',
  calldata: [0],  // false
};
const callArr = [call];
// Use CallData.compile directly via fromCallsToExecuteCalldata (cairo0 format)
// Since this function isn't exported, replicate it
const transformed = callArr.map((c) => {
  const data = CallData.compile(c.calldata || []);
  return {
    to: BigInt(c.contractAddress),
    selector: BigInt(hash.getSelectorFromName(c.entrypoint)),
    data_offset: 0, // will fix below
    data_len: data.length,
    data,
  };
});
// Compute offsets
let offset = 0;
for (const t of transformed) { t.data_offset = offset; offset += t.data_len; }
const allCalldata = transformed.flatMap(t => t.data);

// cairo0 format: [N, to_1, sel_1, off_1, len_1, ..., to_N, sel_N, off_N, len_N, total_len, ...args]
const compiledCalldata = [
  BigInt(transformed.length),
  ...transformed.flatMap(t => [t.to, t.selector, BigInt(t.data_offset), BigInt(t.data_len)]),
  BigInt(allCalldata.length),
  ...allCalldata,
].map(v => typeof v === 'bigint' ? v : BigInt(v));
console.log('Compiled calldata:', compiledCalldata.map(c => '0x' + c.toString(16)));

// Resource bounds (with sufficient L1_gas price)
const resourceBounds = {
  l2_gas: { max_amount: 1_000_000n, max_price_per_unit: 1_000_000_000_000n },
  l1_gas: { max_amount: 100_000n, max_price_per_unit: 1_000_000_000_000_000n },
  l1_data_gas: { max_amount: 1_000n, max_price_per_unit: 1_000_000_000_000_000n },
};
const tip = 0n;
const paymasterData = [];
const accountDeploymentData = [];

// Compute v3 invoke tx hash
const v3Hash = hash.calculateInvokeTransactionHash({
  senderAddress: BigInt(OLD_ADDR),
  version: '0x3',
  compiledCalldata,
  chainId,
  nonce,
  accountDeploymentData,
  nonceDataAvailabilityMode: 0,
  feeDataAvailabilityMode: 0,
  resourceBounds,
  tip,
  paymasterData,
  proofFacts: undefined,
});
console.log('v3 invoke hash:', v3Hash);

// Sign
const sig = ec.starkCurve.sign(v3Hash, OLD_PRIV);
console.log('signature:', 'r=0x' + sig.r.toString(16), 's=0x' + sig.s.toString(16));

// Submit v3 invoke
console.log('\n=== Submit v3 invoke via raw JSON-RPC ===');
const invokeReq = {
  type: 'INVOKE',
  sender_address: OLD_ADDR,
  calldata: compiledCalldata.map(c => '0x' + c.toString(16)),
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
  for (let i = 0; i < 60; i++) {
    const rcpt = await rpc('starknet_getTransactionReceipt', [r.result.transaction_hash]);
    if (rcpt.result) {
      console.log('Receipt:');
      console.log('  status:', rcpt.result.execution_status);
      console.log('  actual_fee:', rcpt.result.actual_fee);
      if (rcpt.result.execution_status !== 'SUCCEEDED') {
        console.log('  revert_reason:', rcpt.result.revert_reason);
      } else {
        console.log('  ✓ AWA UNFROZEN!');
      }
      break;
    }
    await new Promise(r => setTimeout(r, 2000));
  }
} else if (r.error) {
  console.log('v3 invoke failed:', r.error.message);
  console.log('  data:', JSON.stringify(r.error.data).slice(0, 500));
}

// Re-check AWA
const isFrSel = hash.getSelectorFromName('is_awa_frozen');
const r2 = await rpc('starknet_call', [{contract_address: ZK, entry_point_selector: isFrSel, calldata: []}, 'latest']);
console.log('\nis_awa_frozen() after:', r2.result);
