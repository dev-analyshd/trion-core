// P1 — Clean v3 invoke attempt with starknet.js defaults (let it auto-estimate)
import { RpcProvider, Account, hash, constants } from 'starknet';

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

const isFrSel = hash.getSelectorFromName('is_awa_frozen');
let r = await rpc('starknet_call', [{contract_address: ZK, entry_point_selector: isFrSel, calldata: []}, 'latest']);
console.log('is_awa_frozen() before:', r.result);

const call = {
  contractAddress: ZK,
  entrypoint: 'set_awa_state',
  calldata: [0],
};

// Try v3 invoke — let starknet.js auto-estimate
console.log('\n=== v3 invoke (auto-estimate) ===');
try {
  // Use the v3-specific estimateFee method
  const est = await account.estimateInvokeFee(call, { version: 3 });
  console.log('  v3 fee est:', {
    overall_fee: est.overall_fee?.toString(),
    l2_gas_consumed: est.l2_gas_consumed?.toString(),
    l2_gas_price: est.l2_gas_price?.toString(),
    suggestedMaxFee: est.suggestedMaxFee?.toString(),
  });
  // Execute the invoke using v3
  const res = await account.execute(call, undefined, {
    version: 3,
    resourceBounds: est.resourceBounds,
  });
  console.log('  ✓ v3 tx:', res.transaction_hash);
  const rcpt = await provider.waitForTransaction(res.transaction_hash);
  console.log('  Status:', rcpt.execution_status);
  if (rcpt.execution_status !== 'SUCCEEDED') {
    console.log('  Revert reason:', JSON.stringify(rcpt.revert_reason || '').slice(0, 500));
    console.log('  Execution info:', JSON.stringify(rcpt.execution_resources || '').slice(0, 500));
  } else {
    console.log('  ✓ AWA UNFROZEN');
  }
} catch (e) {
  console.log('  ✗ err:', String(e.message).slice(0, 500));
  if (e.response) console.log('  Response:', JSON.stringify(e.response).slice(0, 500));
}

r = await rpc('starknet_call', [{contract_address: ZK, entry_point_selector: isFrSel, calldata: []}, 'latest']);
console.log('\nis_awa_frozen() after:', r.result);

// Also check if v3 declare is supported by checking the version of starknet spec
console.log('\n=== Check starknet spec ===');
const sv = await rpc('starknet_specVersion', []);
console.log('Spec version:', sv.result);
const ci = await rpc('starknet_chainId', []);
console.log('Chain ID:', ci.result, '=>', Buffer.from(ci.result.replace('0x',''), 'hex').toString());
