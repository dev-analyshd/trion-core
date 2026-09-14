// P1 final — Try v1 invoke set_awa_state(false) via Alchemy, with raw JSON-RPC fallback
import { RpcProvider, Account, hash, CallData, constants, ec, num } from 'starknet';

const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
const OLD_ADDR = '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';
const OLD_PRIV = process.env.OLD_PRIV || '0x_REDACTED_OLD_PRIV';
const ZK = '0x0222c170d97af28d9cb964e81b9394be3bf9a4e1d96a85df1084a7667ef40029';

const provider = new RpcProvider({ nodeUrl: RPC });
const account = new Account({ provider, address: OLD_ADDR, signer: OLD_PRIV });

async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

// 1) Check current AWA state
const isFrSel = hash.getSelectorFromName('is_awa_frozen');
let r = await rpc('starknet_call', [{contract_address: ZK, entry_point_selector: isFrSel, calldata: []}, 'latest']);
console.log('Current is_awa_frozen():', r.result);

// 2) Build the call manually (avoid Contract class which can't parse string ABI)
const setAwaSel = hash.getSelectorFromName('set_awa_state');
const call = {
  contractAddress: ZK,
  entrypoint: 'set_awa_state',
  calldata: [0],  // false as felt252
};

// 3) Try v1 invoke via starknet.js Account.execute
console.log('\n=== Try v1 invoke via starknet.js ===');
try {
  const est = await account.estimateInvokeFee(call, { version: 1 });
  console.log('  v1 fee estimate:', est.suggestedMaxFee?.toString());
  const res = await account.execute(call, { version: 1, maxFee: est.suggestedMaxFee * 2n });
  console.log('  ✓ v1 tx submitted:', res.transaction_hash);
  const rcpt = await provider.waitForTransaction(res.transaction_hash);
  console.log('  Status:', rcpt.execution_status);
  if (rcpt.execution_status !== 'SUCCEEDED') {
    console.log('  Revert:', JSON.stringify(rcpt.revert_reason).slice(0,500));
  } else {
    console.log('  ✓ AWA UNFROZEN');
  }
} catch (e) {
  console.log('  ✗ v1 invoke err:', String(e.message).slice(0, 500));
  // Try v3
  console.log('\n=== Try v3 invoke (STRK gas) ===');
  try {
    const est = await account.estimateInvokeFee(call, { version: 3 });
    console.log('  v3 fee estimate:', est.suggestedMaxFee?.toString());
    const res = await account.execute(call, { version: 3, maxFee: est.suggestedMaxFee * 2n });
    console.log('  ✓ v3 tx submitted:', res.transaction_hash);
    const rcpt = await provider.waitForTransaction(res.transaction_hash);
    console.log('  Status:', rcpt.execution_status);
    if (rcpt.execution_status !== 'SUCCEEDED') {
      console.log('  Revert:', JSON.stringify(rcpt.revert_reason).slice(0,500));
    } else {
      console.log('  ✓ AWA UNFROZEN');
    }
  } catch (e2) {
    console.log('  ✗ v3 invoke err:', String(e2.message).slice(0, 500));
  }
}

// Re-check AWA state
r = await rpc('starknet_call', [{contract_address: ZK, entry_point_selector: isFrSel, calldata: []}, 'latest']);
console.log('\nis_awa_frozen() after:', r.result);
