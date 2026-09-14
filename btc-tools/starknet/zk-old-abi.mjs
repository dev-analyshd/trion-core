import { hash } from 'starknet';
const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

const OLD_ADDR = '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';
const cls = await rpc('starknet_getClassAt', ['latest', OLD_ADDR]);
const abi = JSON.parse(cls.result.abi);

console.log('=== Full ABI of OLD deployer ===');
for (const e of abi) {
  if (e.type === 'function' || e.type === 'constructor' || e.type === 'event' || e.type === 'impl' || e.type === 'interface') {
    const inputs = (e.inputs || []).map(i => i.name+':'+i.type).join(', ');
    console.log(`  [${e.type}] ${e.name}(${inputs})`);
    if (e.items) {
      for (const item of e.items) {
        if (item.type === 'function') {
          const ii = (item.inputs || []).map(i => i.name+':'+i.type).join(', ');
          console.log(`    - function ${item.name}(${ii})`);
        }
      }
    }
  }
}

// Test if we can call deploy_contract on OLD deployer (as view simulation, will fail since it's not view)
const deploySel = hash.getSelectorFromName('deploy_contract');
const r = await rpc('starknet_call', [{
  contract_address: OLD_ADDR,
  entry_point_selector: deploySel,
  calldata: ['0x05613dd22cb2c57584477da06fec45af657a82b487d1f475526d3eaf9b62b2c0', '0x42', '0x0', '0x0'],
}, 'latest']);
console.log('\nSimulate deploy_contract():', r.result || r.error?.message?.slice(0, 200));

// Try other function names
for (const fn of ['deployContract', 'deploy', '__declare_deploy__', 'declare_and_deploy']) {
  const sel = hash.getSelectorFromName(fn);
  const r = await rpc('starknet_call', [{
    contract_address: OLD_ADDR,
    entry_point_selector: sel,
    calldata: ['0x05613dd22cb2c57584477da06fec45af657a82b487d1f475526d3eaf9b62b2c0', '0x42', '0x0', '0x0'],
  }, 'latest']);
  console.log(`Simulate ${fn}():`, r.result || r.error?.message?.slice(0, 100));
}
