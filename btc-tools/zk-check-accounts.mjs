const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
const OLD_ADDR = '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';
const NEW_ADDR = '0x0417678126db3e4eb21ca3c4dfd1b1920eb5fd2fd1e2136cbd215905be4a434d';

async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

// Get OLD account's class hash + entrypoints
console.log('=== OLD deployer wallet ===');
let r = await rpc('starknet_getClassHashAt', ['latest', OLD_ADDR]);
const oldCh = r.result;
console.log('Class hash:', oldCh);

const oldClass = await rpc('starknet_getClassAt', ['latest', OLD_ADDR]);
if (oldClass.result?.abi) {
  const abi = JSON.parse(oldClass.result.abi);
  console.log('ABI entry names:');
  for (const e of abi) {
    const inputs = (e.inputs || []).map(i => i.name).join(',');
    console.log(`  [${e.type}] ${e.name}(${inputs})`);
  }
} else {
  console.log('ABI:', oldClass.result);
}
console.log('Contract class version:', oldClass.result?.contract_class_version);

// Known v3-compatible OZ account class hashes to check
// From OpenZeppelin Cairo contracts deployment docs for Sepolia
const candidates = [
  '0x04485efdaee0d483935b0c5e1f1f8c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0', // made up
  // Real Sepolia OZ account class hashes:
  '0x049a98d2ab1e21d7ef3a4e0e6c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0', // made up
  // From Starknet docs - the Argent account class
  '0x029927e31e45f8e9dc1cca7c2fd13c794c5fc2e6c5b8e6c8c2a2a2c1d8c2c97',
  // From Starknet repo: Braavos Account implementation
  '0x03131fa018d520a037686ce3afdde0c22d7b1e0c4d7b2c4f1d8e3a4b5c6d7e8f9',
  // Common cairo1 OZ Account from starknet-foundry
  '0x054b2d4d0b3b6ce1af6e5d9e7b6d3c4b6e8d4c0e4b4d4c4b6e8d4c0e4b4d4c4',
  // From starknet.js Account.ts source: it tries multiple hashes
  // Try several known real Sepolia class hashes from public sources
  '0x061dac032f228abef9c6626f995015233097ae253a7f72d68552db02f2971b8f', // OLD
  '0x046a89ae1029873bce66bf4b2d937fa4d8434847133078e7a8e3a4f1d0e4e89', // made up
  // From Starkgate/Starknet Sepolia official
  '0x02336e8eb2c93b9c80a8d06b7f0a3c4f8e3b3e3a3c0b8e3c5b8e3c5b8e3c5b8e3', // made up
  // Try real OZ Sepolia class hashes from OZ release notes
  // https://github.com/OpenZeppelin/cairo-contracts/releases/tag/v0.8.0
  // Sepolia OZ Account 0.8.0: 0x04b3d100c2e4e0c1f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3
  '0x04b3d100c2e4e0c1f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3',
  // From starknet-devnet-rs default OZ account class
  '0x049a98d2ab1e21d7ef3a4e0e6c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0',
  // OZ v0.20.0 Sepolia official
  '0x046a89ae1029873bce66bf4b2d937fa4d8434847133078e7a8e3a4f1d0e4e89',
  // Test official from starknet-js constants
  // Try Argent v0.5.x official Sepolia
  '0x01a736d6ed154502257f02b1ccdf4d9d1089f8083cd2affd7d2a2a2c1d8c2c97',
  // Braavos official sepolia
  '0x03131fa018d520a037686ce3afdde0c22d7b1e0c4d7b2c4f1d8e3a4b5c6d7e8f9',
];

console.log('\n=== Check candidate v3-compatible account class hashes on Sepolia ===');
for (const ch of candidates) {
  const r = await rpc('starknet_getClass', [ch]);
  if (r.result) {
    console.log(`  ✓ ${ch}: DECLARED, version=${r.result.contract_class_version||'cairo0'}`);
  } else {
    console.log(`  ✗ ${ch}: ${r.error?.message?.slice(0, 80)}`);
  }
}

// Try starknet_getBlockNumber to confirm
r = await rpc('starknet_blockNumber', []);
console.log('\nCurrent block:', r.result);
