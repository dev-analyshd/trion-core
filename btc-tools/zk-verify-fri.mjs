import { hash } from 'starknet';
const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

// The FRI token address (fee token) discovered from events
const FRI = '0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d';
const MAIN_STRK = '0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab0720188d6c1a4b6f';  // mainnet STRK
const ETH = '0x049d36570d4e46f48e99674bd3fcc84644ddd6b96f7c741b1562b82f9e004dc7';  // ETH (mainnet+sepolia)

const NEW_ADDR = '0x0417678126db3e4eb21ca3c4dfd1b1920eb5fd2fd1e2136cbd215905be4a434d';
const OLD_ADDR = '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';

console.log('=== Verify FRI contract ===');
const r1 = await rpc('starknet_getClassHashAt', ['latest', FRI]);
console.log('FRI class hash:', r1.result || r1.error);

// Try with no leading 0
const FRI2 = '0x4718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d';
const r1b = await rpc('starknet_getClassHashAt', ['latest', FRI2]);
console.log('FRI (no-leading-0) class hash:', r1b.result || r1b.error);

// Get ABI to find right selector for symbol/balanceOf
const cls = await rpc('starknet_getClassAt', ['latest', FRI]);
console.log('\nFRI getClassAt keys:', cls.result ? Object.keys(cls.result) : cls.error?.message);
if (cls.result?.abi) {
  let abi;
  try { abi = JSON.parse(cls.result.abi); } catch(e) { abi = []; }
  console.log('ABI entries:', abi.length);
  for (const e of abi) {
    if (e.type === 'function' || e.type === 'constructor') {
      console.log(`  [${e.type}] ${e.name}(${(e.inputs||[]).map(i=>i.name+':'+i.type).join(', ')})`);
    }
  }
}

const balSel = hash.getSelectorFromName('balanceOf');
const symSel = hash.getSelectorFromName('symbol');

console.log('\n=== Check balances on FRI ===');
const newBal = await rpc('starknet_call', [{contract_address: FRI, entry_point_selector: balSel, calldata: [NEW_ADDR]}, 'latest']);
console.log('NEW wallet FRI balance:', newBal.result || newBal.error);
const oldBal = await rpc('starknet_call', [{contract_address: FRI, entry_point_selector: balSel, calldata: [OLD_ADDR]}, 'latest']);
console.log('OLD wallet FRI balance:', oldBal.result || oldBal.error);

console.log('\n=== Symbol ===');
const symR = await rpc('starknet_call', [{contract_address: FRI, entry_point_selector: symSel, calldata: []}, 'latest']);
console.log('FRI symbol:', symR.result || symR.error);
if (symR.result) {
  // Decode shortstring (felt) → string
  const feltHex = symR.result[0];
  if (feltHex) {
    const decoded = Buffer.from(feltHex.replace('0x','').padStart(64,'0'), 'hex').toString().replace(/\0/g, '').trim();
    console.log('Decoded symbol:', decoded);
  }
}

// Also check the main STRK address for comparison
console.log('\n=== Compare with main STRK address ===');
const mainR = await rpc('starknet_getClassHashAt', ['latest', MAIN_STRK]);
console.log('Mainnet STRK class hash:', mainR.result || mainR.error);

const mainBal = await rpc('starknet_call', [{contract_address: MAIN_STRK, entry_point_selector: balSel, calldata: [NEW_ADDR]}, 'latest']);
console.log('NEW wallet Mainnet-STRK balance:', mainBal.result || mainBal.error);
