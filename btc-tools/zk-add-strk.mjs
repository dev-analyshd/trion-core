// Transfer 200 more STRK from OLD to NEW_ADDR
import { ec, hash, CallData, RpcProvider, Account } from 'starknet';

const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
const OLD_ADDR = '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';
const OLD_PRIV = '0x_REDACTED_OLD_PRIV';
const FRI = '0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d';
const NEW_ADDR = '0x06d58c2aa17312d090c27ac52b9f9e4a5d267675afee9dedf424b61655cc1854';

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

// Transfer 200 STRK
const amount = 200n * 10n**18n;
const amountLow = amount & ((1n << 128n) - 1n);
const amountHigh = amount >> 128n;
console.log('Transferring', Number(amount) / 1e18, 'STRK...');

const calls = [{
  contractAddress: FRI, entrypoint: 'transfer',
  calldata: [NEW_ADDR, '0x' + amountLow.toString(16), '0x' + amountHigh.toString(16)],
}];
const orderCalls = calls.map(c => ({ contractAddress: c.contractAddress, entrypoint: c.entrypoint, calldata: CallData.compile(c.calldata || []) }));
const compiledCalldata = CallData.compile({ orderCalls });

const resourceBounds = {
  l2_gas: { max_amount: 0x5f5e100n, max_price_per_unit: 0xba43b7400n },
  l1_gas: { max_amount: 0x11170n, max_price_per_unit: 0x8d79883d20000n },
  l1_data_gas: { max_amount: 0x2710n, max_price_per_unit: 0x62448724953354n },
};
const details = {
  version: '0x3', walletAddress: OLD_ADDR, nonce, maxFee: 0n, chainId, cairoVersion: '1',
  resourceBounds, tip: 0n, paymasterData: [], accountDeploymentData: [],
  nonceDataAvailabilityMode: 'L1', feeDataAvailabilityMode: 'L1', proofFacts: undefined,
};
const sig = await account.signer.signTransaction(calls, details);

const invokeReq = {
  type: 'INVOKE', sender_address: OLD_ADDR,
  calldata: compiledCalldata.map(c => '0x' + BigInt(c).toString(16)),
  version: '0x3',
  signature: ['0x' + sig.r.toString(16), '0x' + sig.s.toString(16)],
  nonce: '0x' + nonce.toString(16),
  resource_bounds: {
    l2_gas: { max_amount: '0x5f5e100', max_price_per_unit: '0xba43b7400' },
    l1_gas: { max_amount: '0x11170', max_price_per_unit: '0x8d79883d20000' },
    l1_data_gas: { max_amount: '0x2710', max_price_per_unit: '0x62448724953354' },
  },
  tip: '0x0', paymaster_data: [],
  nonce_data_availability_mode: 'L1', fee_data_availability_mode: 'L1',
  account_deployment_data: [],
};
const r = await rpc('starknet_addInvokeTransaction', [invokeReq]);
console.log('Result:', JSON.stringify(r).slice(0, 400));
if (r.result?.transaction_hash) {
  console.log('\n✓ tx submitted:', r.result.transaction_hash);
  for (let i = 0; i < 60; i++) {
    const rcpt = await rpc('starknet_getTransactionReceipt', [r.result.transaction_hash]);
    if (rcpt.result) {
      console.log('  status:', rcpt.result.execution_status);
      if (rcpt.result.execution_status !== 'SUCCEEDED') console.log('  revert:', rcpt.result.revert_reason?.slice(0, 200));
      else {
        // Check new balance
        const balSel = hash.getSelectorFromName('balanceOf');
        const balR = await rpc('starknet_call', [{contract_address: FRI, entry_point_selector: balSel, calldata: [NEW_ADDR]}, 'latest']);
        const bal = BigInt(balR.result[0]) + (BigInt(balR.result[1]) << 128n);
        console.log('  NEW_ADDR STRK balance:', Number(bal) / 1e18);
      }
      break;
    }
    await new Promise(r => setTimeout(r, 2000));
  }
} else if (r.error) {
  console.log('failed:', r.error.message);
}
