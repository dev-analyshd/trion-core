import { hash } from 'starknet';
const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

// Use a deployed account that uses this class hash
const sampleAddr = '0x15569a4dae53e13da0b0f9332d88539c96db79858b14fb15e571a9f46b6c1be';
const cls = await rpc('starknet_getClassAt', ['latest', sampleAddr]);
const abi = JSON.parse(cls.result.abi);

console.log('=== V3 class full ABI ===');
for (const e of abi) {
  console.log(`[${e.type}] ${e.name}`);
  if (e.items) {
    for (const i of e.items) {
      if (i.type === 'function') {
        const inputs = (i.inputs || []).map(j => j.name+':'+j.type).join(', ');
        console.log(`  - function ${i.name}(${inputs})`);
      }
    }
  }
  if (e.type === 'function' || e.type === 'constructor') {
    const inputs = (e.inputs || []).map(i => i.name+':'+i.type).join(', ');
    console.log(`  inputs: ${inputs}`);
  }
}

// Compute selectors for the error selector we saw
const errorSel = '0x036fcbf06cd96843058359e1a75928beacfac10727dab22a3972f0af8aa92895';
console.log('\nError selector:', errorSel);

// Try various deploy-related names
for (const n of ['__validate_deploy__', '__validate_deploy_account__', '__validate_deploy_v3__', '__validate_deploy_account_v3__', '__validate_declare_v3__', '__validate_declare__', '__validate_invoke_v3__', '__validate__', 'validate_deploy', 'validate']) {
  const sel = hash.getSelectorFromName(n);
  if (sel === errorSel) {
    console.log(`  MATCH: ${n} = ${sel}`);
  }
}
