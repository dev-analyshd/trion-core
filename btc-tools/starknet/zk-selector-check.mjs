import { hash } from 'starknet';
const names = [
  '__execute__', '__validate__', '__validate_declare__', '__validate_deploy_account__',
  '__validate_invoke_v3__', '__validate_declare_v3__', '__validate_deploy_account_v3__',
  '__execute_invoke_v3__', '__execute_declare_v3__', '__execute_deploy_account_v3__',
  'is_valid_signature', 'getPublicKey', 'increase_nonce',
];
for (const n of names) {
  console.log(`  ${n}: ${hash.getSelectorFromName(n)}`);
}
