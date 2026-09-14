const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
const OLD_ADDR = '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';
const NEW_ADDR = '0x0417678126db3e4eb21ca3c4dfd1b1920eb5fd2fd1e2136cbd215905be4a434d';
const ZK = '0x0222c170d97af28d9cb964e81b9394be3bf9a4e1d96a85df1084a7667ef40029';

import { hash, RpcProvider, Account, Contract, CallData } from 'starknet';
const provider = new RpcProvider({ nodeUrl: RPC });

// 1. Check the actual STRK address on Sepolia (try multiple candidates)
const strkCandidates = [
  '0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab0720188d6c1a4b6f',  // mainnet
  '0x049d36570d4e46f48e99674bd3fcc84644ddd6b96f7c741b1562b82f9e004dc7',  // ETH
  // From Starkgate docs Sepolia STRK:
  '0x045f8eb8d2e1f7c4f5a3b6e7d8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7',
  // Some other common testnet STRK
  '0x00b08b4ffd8d9d7c1b6c5a3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f',
];

async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}
const balSel = hash.getSelectorFromName('balanceOf');

console.log('=== Search for STRK contract on Sepolia ===');
for (const addr of strkCandidates) {
  const r = await rpc('starknet_getClassHashAt', ['latest', addr]);
  console.log(`  ${addr.slice(0,16)}...:`, r.result ? `✓ class=${r.result.slice(0,20)}...` : r.error?.message);
}

// 2. Get ZKVerifier ABI properly
console.log('\n=== ZKVerifier ABI ===');
const cls = await provider.getClassAt(ZK, 'latest');
console.log('ABI entries:', (cls.abi||[]).length, 'class version:', cls.version);
const fns = (cls.abi || []).filter(a => a.type === 'interface').flatMap(i => (i.items || [])).filter(i => i.type === 'function');
console.log('Functions:', fns.map(f => `${f.name}(${(f.inputs||[]).map(i=>i.name).join(',')})`).join('\n  '));

// 3. Test v1 invoke via Alchemy (sanity check) — just get the v1 transaction type accepted
console.log('\n=== Test v1 invoke via raw JSON-RPC ===');
// First get the account's current nonce
const nonceR = await rpc('starknet_getNonce', ['latest', OLD_ADDR]);
console.log('OLD nonce:', nonceR.result || nonceR.error);

// 4. Try to declare a NEW v3-compatible OpenZeppelin account class
// Use starknet.js Account.declareIfNot
const OLD_PRIV = process.env.OLD_PRIV || '0x_REDACTED_OLD_PRIV';
const account = new Account({ provider, address: OLD_ADDR, signer: OLD_PRIV });

// Try the set_awa_state(false) call with v1
const zkContract = new Contract(cls.abi, ZK, account);
console.log('\n=== Try v1 invoke set_awa_state(false) ===');
try {
  const call = zkContract.populate('set_awa_state', [false]);
  console.log('Call:', JSON.stringify(call));
  const est = await account.estimateInvokeFee(call, { version: 1 });
  console.log('  v1 fee estimate:', est.suggestedMaxFee?.toString());
  const { transaction_hash } = await account.execute(call, { version: 1, maxFee: est.suggestedMaxFee * 2n });
  console.log('  ✓ v1 tx:', transaction_hash);
  const rcpt = await provider.waitForTransaction(transaction_hash);
  console.log('  Status:', rcpt.execution_status);
  if (rcpt.execution_status !== 'SUCCEEDED') {
    console.log('  Revert:', JSON.stringify(rcpt.revert_reason).slice(0,300));
  }
} catch (e) {
  console.log('  ✗ err:', String(e.message).slice(0, 400));
}

// Re-check is_awa_frozen
const isFrozenSel = hash.getSelectorFromName('is_awa_frozen');
const r = await rpc('starknet_call', [{contract_address: ZK, entry_point_selector: isFrozenSel, calldata: []}, 'latest']);
console.log('\nis_awa_frozen() after:', r.result);
