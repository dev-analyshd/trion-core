// Use starknet.js's account.signer.signTransaction to compute proper sig, then submit raw
import { RpcProvider, Account, hash, CallData, constants } from 'starknet';

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

const chainId = BigInt((await rpc('starknet_chainId', [])).result);
const nonce = BigInt((await rpc('starknet_getNonce', ['latest', OLD_ADDR])).result);
console.log('chain:', '0x' + chainId.toString(16), ' nonce:', nonce);

// Build call
const calls = [{
  contractAddress: ZK,
  entrypoint: 'set_awa_state',
  calldata: [0],  // false
}];

// Set v3 transaction details with explicit resource_bounds (matching a recent successful tx)
const details = {
  version: '0x3',
  walletAddress: OLD_ADDR,
  nonce,
  maxFee: 0n, // ignored for v3
  chainId,
  cairoVersion: '1', // cairo1
  resourceBounds: {
    l2_gas: { max_amount: 0x5f5e100n, max_price_per_unit: 0xba43b7400n }, // match recent successful tx (bigints)
    l1_gas: { max_amount: 0x11170n, max_price_per_unit: 0x8d79883d20000n },
    l1_data_gas: { max_amount: 0x2710n, max_price_per_unit: 0x62448724953354n },
  },
  tip: 0n,
  paymasterData: [],
  accountDeploymentData: [],
  nonceDataAvailabilityMode: 'L1',
  feeDataAvailabilityMode: 'L1',
  proofFacts: undefined,
};

// Sign the transaction using starknet.js's signer
const sig = await account.signer.signTransaction(calls, details);
console.log('Signature:', sig);

// Also get the compiledCalldata starknet.js produced
// Recreate it manually
const callArr = calls.map((call) => ({
  contractAddress: call.contractAddress,
  entrypoint: call.entrypoint,
  calldata: CallData.compile(call.calldata || []),
}));
const compiledCalldata = CallData.compile({ orderCalls: callArr });
console.log('Compiled calldata (cairo1):', compiledCalldata);

// Submit v3 invoke via raw JSON-RPC with starknet.js's signature
console.log('\n=== Submit v3 invoke via raw JSON-RPC with starknet.js sig ===');
const invokeReq = {
  type: 'INVOKE',
  sender_address: OLD_ADDR,
  calldata: compiledCalldata.map(c => '0x' + BigInt(c).toString(16)),
  version: '0x3',
  signature: ['0x' + sig.r.toString(16), '0x' + sig.s.toString(16)],
  nonce: '0x' + nonce.toString(16),
  resource_bounds: {
    l2_gas: { max_amount: '0x5f5e100', max_price_per_unit: '0xba43b7400' },
    l1_gas: { max_amount: '0x11170', max_price_per_unit: '0x8d79883d20000' },
    l1_data_gas: { max_amount: '0x2710', max_price_per_unit: '0x62448724953354' },
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
