// Deploy a NEW ZKVerifier instance via the OLD deployer's deploy_contract function
// This makes the OLD deployer the owner of the new instance
import { ec, hash, CallData, RpcProvider, Account } from 'starknet';

const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
const OLD_ADDR = '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';
const OLD_PRIV = '0x_REDACTED_OLD_PRIV';
const ZK_CLASS_HASH = '0x05613dd22cb2c57584477da06fec45af657a82b487d1f475526d3eaf9b62b2c0';

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

// Build call: deploy_contract(class_hash, salt, unique, calldata) on the OLD deployer itself
// IDeployable.deploy_contract(class_hash: felt252, salt: felt252, unique: bool, calldata: Span<felt252>)
const deploySel = hash.getSelectorFromName('deploy_contract');
const calls = [{
  contractAddress: OLD_ADDR,  // call self
  entrypoint: 'deploy_contract',
  calldata: [
    ZK_CLASS_HASH,  // class_hash
    '0x' + (Date.now() % 1000000).toString(16).padStart(8, '0'),  // salt
    0,  // unique = false
    0,  // calldata length = 0 (constructor takes no args)
  ],
}];

// Build cairo1 compiled calldata
const orderCalls = calls.map(c => ({
  contractAddress: c.contractAddress,
  entrypoint: c.entrypoint,
  calldata: CallData.compile(c.calldata || []),
}));
const compiledCalldata = CallData.compile({ orderCalls });
console.log('compiledCalldata:', compiledCalldata);

// Set resource_bounds (matching recent successful txs)
const resourceBounds = {
  l2_gas: { max_amount: 0x5f5e100n, max_price_per_unit: 0xba43b7400n },
  l1_gas: { max_amount: 0x11170n, max_price_per_unit: 0x8d79883d20000n },
  l1_data_gas: { max_amount: 0x2710n, max_price_per_unit: 0x62448724953354n },
};

// Sign using starknet.js signer
const details = {
  version: '0x3',
  walletAddress: OLD_ADDR,
  nonce,
  maxFee: 0n,
  chainId,
  cairoVersion: '1',
  resourceBounds,
  tip: 0n,
  paymasterData: [],
  accountDeploymentData: [],
  nonceDataAvailabilityMode: 'L1',
  feeDataAvailabilityMode: 'L1',
  proofFacts: undefined,
};
const sig = await account.signer.signTransaction(calls, details);
console.log('Signature r:', '0x' + sig.r.toString(16));

// Submit v3 invoke
console.log('\n=== Submit v3 invoke: deploy_contract(ZK_CLASS_HASH) ===');
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
console.log('Result:', JSON.stringify(r).slice(0, 600));

if (r.result?.transaction_hash) {
  console.log('\n✓ v3 tx submitted:', r.result.transaction_hash);
  for (let i = 0; i < 60; i++) {
    const rcpt = await rpc('starknet_getTransactionReceipt', [r.result.transaction_hash]);
    if (rcpt.result) {
      console.log('Receipt:');
      console.log('  status:', rcpt.result.execution_status);
      console.log('  actual_fee:', rcpt.result.actual_fee);
      if (rcpt.result.execution_status !== 'SUCCEEDED') {
        console.log('  revert_reason:', (rcpt.result.revert_reason || '').slice(0, 500));
      } else {
        console.log('  ✓ Deploy succeeded!');
        // Look for ContractDeployed event to get the new address
        for (const ev of (rcpt.result.events || [])) {
          console.log('  Event from:', ev.from_address, ' keys:', ev.keys?.[0]?.slice(0,10));
          console.log('    data:', ev.data);
        }
      }
      break;
    }
    await new Promise(r => setTimeout(r, 2000));
  }
} else if (r.error) {
  console.log('v3 invoke failed:', r.error.message);
  console.log('  data:', JSON.stringify(r.error.data).slice(0, 500));
}
