const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
const OLD_ADDR = '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';
const NEW_ADDR = '0x0417678126db3e4eb21ca3c4dfd1b1920eb5fd2fd1e2136cbd215905be4a434d';
const ETH = '0x049d36570d4e46f48e99674bd3fcc84644ddd6b96f7c741b1562b82f9e004dc7';
const STRK = '0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab0720188d6c1a4b6f';
const ZK = '0x0222c170d97af28d9cb964e81b9394be3bf9a4e1d96a85df1084a7667ef40029';

import { hash } from 'starknet';
const balSel = hash.getSelectorFromName('balanceOf');
const decSel = hash.getSelectorFromName('decimals');
const symSel = hash.getSelectorFromName('symbol');
const nameSel = hash.getSelectorFromName('name');
console.log('balanceOf selector:', balSel);

async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

// Check ETH contract metadata
console.log('\n=== ETH contract ===');
let r = await rpc('starknet_call', [{contract_address: ETH, entry_point_selector: nameSel, calldata: []}, 'latest']);
console.log('name:', r.result || r.error?.message);
r = await rpc('starknet_call', [{contract_address: ETH, entry_point_selector: symSel, calldata: []}, 'latest']);
console.log('symbol:', r.result || r.error?.message);
r = await rpc('starknet_call', [{contract_address: ETH, entry_point_selector: decSel, calldata: []}, 'latest']);
console.log('decimals:', r.result || r.error?.message);
r = await rpc('starknet_call', [{contract_address: ETH, entry_point_selector: balSel, calldata: [OLD_ADDR]}, 'latest']);
console.log('OLD ETH balance:', r.result || r.error?.message);
r = await rpc('starknet_call', [{contract_address: ETH, entry_point_selector: balSel, calldata: [NEW_ADDR]}, 'latest']);
console.log('NEW ETH balance:', r.result || r.error?.message);

// Check STRK
console.log('\n=== STRK contract ===');
r = await rpc('starknet_getClassHashAt', ['latest', STRK]);
console.log('STRK class hash:', r.result || r.error?.message);
r = await rpc('starknet_call', [{contract_address: STRK, entry_point_selector: balSel, calldata: [OLD_ADDR]}, 'latest']);
console.log('OLD STRK balance:', r.result || r.error?.message);
r = await rpc('starknet_call', [{contract_address: STRK, entry_point_selector: balSel, calldata: [NEW_ADDR]}, 'latest']);
console.log('NEW STRK balance:', r.result || r.error?.message);

// Check ZKVerifier AWA state + try to call set_awa_state(false) via raw JSON-RPC
console.log('\n=== ZKVerifier state ===');
const isFrSel = hash.getSelectorFromName('is_awa_frozen');
r = await rpc('starknet_call', [{contract_address: ZK, entry_point_selector: isFrSel, calldata: []}, 'latest']);
console.log('is_awa_frozen (OLD):', r.result || r.error?.message);

// List all entrypoints in ZKVerifier
const ch = (await rpc('starknet_getClassHashAt', ['latest', ZK])).result;
const cls = (await rpc('starknet_getClass', [ch])).result;
console.log('\nZK class:', ch, 'abi entries:', (cls.abi||[]).length);
const fns = (cls.abi || []).filter(a => a.type === 'interface').flatMap(i => (i.items || [])).filter(i => i.type === 'function');
console.log('Functions:', fns.map(f => `${f.name}/${(f.inputs||[]).length}`).join(', '));

// Try set_awa_state selector
const setSel = hash.getSelectorFromName('set_awa_state');
console.log('\nset_awa_state selector:', setSel);
