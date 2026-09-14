// Try raw v1 invoke via raw JSON-RPC — manually sign the transaction
import { ec, hash, num } from 'starknet';

const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
const OLD_ADDR = '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';
const OLD_PRIV = '0x_REDACTED_OLD_PRIV';
const ZK = '0x0222c170d97af28d9cb964e81b9394be3bf9a4e1d96a85df1084a7667ef40029';

async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

// Build the v1 invoke transaction hash manually
// v1 invoke hash = pedersen([
//   "invoke", sender_address, entry_point_selector (0x0 for invoke),
//   zero,  // no arguments hashing
//   hash(calldata: [call_array_len, contract_addr, selector, calldata_len, ...args]),
//   max_fee, chain_id, nonce
// ])
// (Actually v1 invoke uses the simpler format: hash(prefix, address, 0, h(calldata), max_fee, chain_id, nonce))

const chainIdR = await rpc('starknet_chainId', []);
const chainId = BigInt(chainIdR.result);
console.log('chain id:', chainIdR.result);

const nonce = BigInt((await rpc('starknet_getNonce', ['latest', OLD_ADDR])).result);
console.log('nonce:', nonce);

// Build calldata for the call: set_awa_state(false)
const setAwaSel = hash.getSelectorFromName('set_awa_state');
const callArrayLen = 1n;
const calldataLen = 1n; // 1 arg (false=0)
// Calldata: [call_array_len, contract_addr, selector, calldata_offset, calldata_len, ...args]
// For Cairo1 invoke v1, calldata = [1, contract, selector, calldata_len, ...args]
const callCalldata = [
  callArrayLen,        // 1
  BigInt(ZK),          // contract address
  BigInt(setAwaSel),   // entry point selector
  calldataLen,         // calldata length
  0n,                  // false as felt252
];
console.log('Calldata:', callCalldata.map(c => '0x' + c.toString(16)));

// v1 invoke tx hash
// Reference: starknet spec — invoke v1 hash uses:
// hash = pedersen([INVOKE, sender, 0, hash(calldata), max_fee, chain_id, nonce])
// where INVOKE = "invoke"
const maxFee = 1000000000000000n;  // 0.001 ETH
const invokePrefix = BigInt(hash.starknetKeccak('invoke'));
const calldataHash = hash.computeHashOnElements(callCalldata);
const v1Hash = hash.computePedersenHashOnElements([
  invokePrefix,
  BigInt(OLD_ADDR),
  0n,
  calldataHash,
  maxFee,
  chainId,
  nonce,
]);
console.log('v1 invoke hash:', '0x' + v1Hash.toString(16));

// Sign with priv key using Stark curve
const hashHex = '0x' + v1Hash.toString(16).replace(/^0x/, '').replace(/^0x/, '');
console.log('hashHex (clean):', hashHex);
const sig = ec.starkCurve.sign(hashHex, OLD_PRIV);
console.log('signature r:', sig.r, ' s:', sig.s);

// Submit v1 invoke via raw JSON-RPC starknet_addInvokeTransaction
console.log('\n=== Submit v1 invoke via raw JSON-RPC ===');
const invokeReq = {
  type: 'INVOKE',
  max_fee: '0x' + maxFee.toString(16),
  version: '0x1',
  signature: ['0x' + sig.r.toString(16), '0x' + sig.s.toString(16)],
  nonce: '0x' + nonce.toString(16),
  sender_address: OLD_ADDR,
  calldata: callCalldata.map(c => '0x' + c.toString(16)),
};
const r = await rpc('starknet_addInvokeTransaction', [invokeReq]);
console.log('Result:', JSON.stringify(r).slice(0, 600));

if (r.result?.transaction_hash) {
  console.log('\n✓ v1 tx submitted:', r.result.transaction_hash);
  // Wait for receipt
  const receipt = await (async () => {
    for (let i = 0; i < 30; i++) {
      try {
        const rcpt = await rpc('starknet_getTransactionReceipt', [r.result.transaction_hash]);
        if (rcpt.result) return rcpt.result;
      } catch (e) {}
      await new Promise(r => setTimeout(r, 2000));
    }
    return null;
  })();
  console.log('Receipt:', JSON.stringify(receipt, null, 2).slice(0, 800));
} else {
  console.log('v1 invoke failed:', r.error?.message);
  // Try v3 manually with raw JSON-RPC
  console.log('\n=== Try v3 invoke via raw JSON-RPC (manual sign) ===');
  const v3Hash = hash.calculateInvokeTransactionHash(
    BigInt(OLD_ADDR),
    callCalldata,
    3, // version
    { nonce, chainId, tip: 0n, resourceBounds: {
      l2_gas: { max_amount: 1000000n, max_price_per_unit: 1000000000n },
      l1_gas: { max_amount: 0n, max_price_per_unit: 0n },
      l1_data_gas: { max_amount: 1000n, max_price_per_unit: 1000000000n },
    }, paymasterData: [], accountDeploymentData: [], nonceDataAvailabilityMode: 'L1', feeDataAvailabilityMode: 'L1' },
  );
  console.log('v3 invoke hash:', '0x' + v3Hash.toString(16));
  const sig3 = ec.starkCurve.sign('0x' + v3Hash.toString(16), OLD_PRIV);
  const invokeV3 = {
    type: 'INVOKE',
    sender_address: OLD_ADDR,
    calldata: callCalldata.map(c => '0x' + c.toString(16)),
    version: '0x3',
    signature: [sig3.r, sig3.s],
    nonce: '0x' + nonce.toString(16),
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
  };
  const r3 = await rpc('starknet_addInvokeTransaction', [invokeV3]);
  console.log('v3 result:', JSON.stringify(r3).slice(0, 600));
}
