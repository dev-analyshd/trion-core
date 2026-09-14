const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
const OLD_ADDR = '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';
const ETH = '0x049d36570d4e46f48e99674bd3fcc84644ddd6b96f7c741b1562b82f9e004dc7';
const STRK = '0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab0720188d6c1a4b6f';
const ZK = '0x0222c170d97af28d9cb964e81b9394be3bf9a4e1d96a85df1084a7667ef40029';

async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

// Spec 0_10 uses 'latest' instead of 'pending'
const balSel = '0x2e4263afad30923c891518314c3aae71e0f5b0170f6e21b84d97f4f0c4b3543';

// Block id in spec v0_10: {block_id: 'latest'} or {block_id: 'pending'}
console.log('=== Using "latest" block_id ===');
let r = await rpc('starknet_call', [{contract_address: ETH, entry_point_selector: balSel, calldata: [OLD_ADDR]}, 'latest']);
console.log('ETH balance:', r.result || r.error);

r = await rpc('starknet_call', [{contract_address: STRK, entry_point_selector: balSel, calldata: [OLD_ADDR]}, 'latest']);
console.log('STRK balance:', r.result || r.error);

r = await rpc('starknet_getClassHashAt', ['latest', ZK]);
console.log('ZKVerifier class hash:', r.result || r.error);

// Try is_awa_frozen selector (Cairo format)
import { hash } from 'starknet';
const sel = hash.getSelectorFromName('is_awa_frozen');
console.log('\nis_awa_frozen selector:', sel);

r = await rpc('starknet_call', [{contract_address: ZK, entry_point_selector: sel, calldata: []}, 'latest']);
console.log('is_awa_frozen():', r.result || r.error);

// Get the chain id
r = await rpc('starknet_chainId', []);
console.log('\nchainId:', r.result || r.error);

// Get spec version
r = await rpc('starknet_specVersion', []);
console.log('specVersion:', r.result || r.error);

// Also try with NEW_ADDR
const NEW_ADDR = '0x0417678126db3e4eb21ca3c4dfd1b1920eb5fd2fd1e2136cbd215905be4a434d';
r = await rpc('starknet_call', [{contract_address: ETH, entry_point_selector: balSel, calldata: [NEW_ADDR]}, 'latest']);
console.log('\nNEW wallet ETH balance:', r.result || r.error);
r = await rpc('starknet_call', [{contract_address: STRK, entry_point_selector: balSel, calldata: [NEW_ADDR]}, 'latest']);
console.log('NEW wallet STRK balance:', r.result || r.error);
r = await rpc('starknet_getClassHashAt', ['latest', NEW_ADDR]);
console.log('NEW wallet class hash:', r.result || r.error);
