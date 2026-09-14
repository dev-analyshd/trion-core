import { hash } from 'starknet';
const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

// Get the entry_points_by_type for the v3 class
const sampleAddr = '0x15569a4dae53e13da0b0f9332d88539c96db79858b14fb15e571a9f46b6c1be';
const cls = await rpc('starknet_getClassAt', ['latest', sampleAddr]);

console.log('=== entry_points_by_type ===');
const ep = cls.result?.entry_points_by_type || {};
for (const [type, entries] of Object.entries(ep)) {
  console.log(`\n${type}:`);
  for (const e of entries) {
    console.log(`  selector: ${e.selector}  offset: ${e.offset}`);
  }
}

// Try to match the error selector 0x036fcbf06cd96843058359e1a75928beacfac10727dab22a3972f0af8aa92895
const errorSel = '0x036fcbf06cd96843058359e1a75928beacfac10727dab22a3972f0af8aa92895';

// Try many candidate names
const names = [
  '__validate__', '__validate_declare__', '__validate_deploy__', '__execute__',
  '__validate_invoke_v3__', '__validate_declare_v3__', '__validate_deploy_account_v3__',
  '__validate_invoke__', '__validate_deploy_account__', 'constructor',
  'deploy_contract', 'is_valid_signature',
  'is_valid_signature_for_v3',
  '__validate_deploy_v3__', '__validate_invoke_v3_b3__',
  // Different spec versions might use different naming
  'validate', 'execute',
];
console.log('\n=== Selector matches ===');
for (const n of names) {
  const sel = hash.getSelectorFromName(n);
  console.log(`  ${n}: ${sel} ${sel === errorSel ? '✓ MATCH' : ''}`);
}
