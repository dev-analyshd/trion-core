// P1 — Submit v3 invoke with manual fee bounds, no estimate
import { RpcProvider, Account, hash, CallData, constants, num, ec, stark, v3hash } from 'starknet';

const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
const OLD_ADDR = '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';
const OLD_PRIV = '0x_REDACTED_OLD_PRIV';
const ZK = '0x0222c170d97af28d9cb964e81b9394be3bf9a4e1d96a85df1084a7667ef40029';

const provider = new RpcProvider({ nodeUrl: RPC });
const account = new Account({ provider, address: OLD_ADDR, signer: OLD_PRIV });

async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

// 1. Check AWA frozen state
const isFrSel = hash.getSelectorFromName('is_awa_frozen');
let r = await rpc('starknet_call', [{contract_address: ZK, entry_point_selector: isFrSel, calldata: []}, 'latest']);
console.log('is_awa_frozen() before:', r.result);

// 2. Try v3 invoke set_awa_state(false) with manual fee
console.log('\n=== Submit v3 invoke set_awa_state(false) ===');

// Build the invoke v3 calldata manually
// Invoke v3 calldata format:
//   [call_array_len, contract_address, entrypoint_selector, calldata_len, ...calldata]
const call = {
  contractAddress: ZK,
  entrypoint: 'set_awa_state',
  calldata: [0],  // false as felt252
};

// Get nonce
const nonce = await account.getNonce();

// Use resource bounds: l2_gas = 1M, l1_data_gas = 0
// Use v3 invoke with STRK token as gas
const v3Invoke = {
  type: 'INVOKE',
  sender_address: OLD_ADDR,
  compiled_data_version: 1,
  nonce: nonce,
  calls: [call],
  signature: [],
  resource_bounds: {
    l2_gas: { max_amount: '0x100000', max_price_per_unit: '0x1000000000' }, // 1M gas, 1 gwei
    l1_data_gas: { max_amount: '0x100', max_price_per_unit: '0x100000000' },
  },
  tip: '0x0',
  paymaster_data: [],
  nonce_data_availability_mode: 'L1',
  fee_data_availability_mode: 'L1',
  account_deployment_data: [],
};

// Use starknet.js to sign and submit
try {
  // Build the call
  const calls = [call];
  
  // Let starknet.js do the signing, but specify v3 + resource_bounds explicitly
  // Actually use estimateInvokeFee with v3 first to get a fee
  console.log('Trying v3 estimate...');
  const est = await account.estimateInvokeFee(calls, {
    version: 3,
    nonce,
    resourceBounds: {
      l2_gas: { max_amount: '0xf4240', max_price_per_unit: '0x5af3107a4000' },
      l1_data_gas: { max_amount: '0x400', max_price_per_unit: '0x5af3107a4000' },
    },
  });
  console.log('  v3 estimate result:', est);

  // Execute
  console.log('Submitting v3 invoke...');
  const res = await account.execute(calls, {
    version: 3,
    nonce,
    maxFee: 0n, // ignored for v3
    resourceBounds: {
      l2_gas: { max_amount: '0xf4240', max_price_per_unit: '0x5af3107a4000' },
      l1_data_gas: { max_amount: '0x400', max_price_per_unit: '0x5af3107a4000' },
    },
  });
  console.log('  ✓ v3 tx:', res.transaction_hash);
  const rcpt = await provider.waitForTransaction(res.transaction_hash);
  console.log('  Status:', rcpt.execution_status);
  if (rcpt.execution_status !== 'SUCCEEDED') {
    console.log('  Revert:', JSON.stringify(rcpt.revert_reason).slice(0, 500));
    console.log('  Full receipt:', JSON.stringify(rcpt).slice(0, 1000));
  } else {
    console.log('  ✓ AWA UNFROZEN!');
  }
} catch (e) {
  console.log('  ✗ err:', String(e.message).slice(0, 600));
  // Get more detail
  if (e.error) {
    console.log('  Error detail:', JSON.stringify(e.error).slice(0, 600));
  }
}

// Re-check AWA state
r = await rpc('starknet_call', [{contract_address: ZK, entry_point_selector: isFrSel, calldata: []}, 'latest']);
console.log('\nis_awa_frozen() after:', r.result);
