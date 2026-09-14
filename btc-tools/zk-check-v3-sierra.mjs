const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}
const sampleAddr = '0x15569a4dae53e13da0b0f9332d88539c96db79858b14fb15e571a9f46b6c1be';
const cls = await rpc('starknet_getClassAt', ['latest', sampleAddr]);
const sp = cls.result?.sierra_program;
console.log('Sierra program entries:', sp?.length);
// Look for "call_contract_syscall" or "deploy_contract_syscall" in the program
if (sp) {
  const joined = sp.join(' ');
  console.log('Total chars:', joined.length);
  // Search for relevant syscalls
  const syscalls = ['call_contract', 'deploy_contract', 'library_call', 'replace_class', 'storage_read', 'storage_write', 'emit_event', 'get_caller_address', 'get_tx_info'];
  for (const s of syscalls) {
    if (joined.includes(s)) {
      console.log('  Found:', s);
    }
  }
  // Print first few entries
  console.log('\nFirst 3 entries:');
  for (let i = 0; i < Math.min(3, sp.length); i++) {
    console.log('  ', sp[i]?.slice(0, 200));
  }
}

// Also: try calling a function that should emit an event
// Use FRI.approve(NEW_ADDR, 100) — this should emit an Approval event
import { hash } from 'starknet';
const FRI = '0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d';
const NEW_ADDR = '0x06d58c2aa17312d090c27ac52b9f9e4a5d267675afee9dedf424b61655cc1854';

// Simulate approve call (view simulation)
const approveSel = hash.getSelectorFromName('approve');
const r = await rpc('starknet_call', [{
  contract_address: FRI,
  entry_point_selector: approveSel,
  calldata: [NEW_ADDR, '0x64', '0x0'], // approve 100
}, 'latest']);
console.log('\napprove simulation:', r.result || r.error?.message);

// Also check FRI's transfer selector name
const transferSel = hash.getSelectorFromName('transfer');
console.log('transfer selector:', transferSel);

// Check FRI's ABI
const friCls = await rpc('starknet_getClassAt', ['latest', FRI]);
if (friCls.result?.abi) {
  const abi = JSON.parse(friCls.result.abi);
  console.log('\nFRI functions:');
  for (const e of abi) {
    if (e.type === 'function') {
      const inputs = (e.inputs || []).map(i => i.name+':'+i.type).join(', ');
      console.log(`  ${e.name}(${inputs})`);
    }
  }
}
