// P1c + P1d: Deploy NEW ZKVerifier instance via NEW_ADDR.deploy_contract(), then set_awa_state(false)
//
// Owner of new ZKVerifier = NEW_ADDR (because deploy_contract_syscall's caller is NEW_ADDR's
// __execute__ which is NEW_ADDR itself).
//
// After this script:
//   - new ZKVerifier address recorded to /home/z/my-project/trion-core/docs/proofs/zk_gauntlet_deployment.json
//   - awa_frozen = false (unfrozen, ready for proof submission)
//
import * as lib from './zk-gauntlet-lib.mjs';
import { promises as fs } from 'node:fs';
import path from 'node:path';

const NEW_ADDR = lib.NEW_ADDR;
const ZK_CLASS = lib.ZK_VERIFIER_CLASS;

console.log('=== P1c: Deploy new ZKVerifier via NEW_ADDR.deploy_contract() ===');
console.log('NEW_ADDR:', NEW_ADDR);
console.log('ZK_VERIFIER_CLASS:', ZK_CLASS);

// Predict the deployed contract address BEFORE submitting the tx
// deploy_contract(class_hash, contract_address_salt, calldata, deploy_from_zero)
// constructor takes no args -> calldata = []
const salt = lib.sha256Felt('TRION-ZKVerifier-Gauntlet-salt-v1');
console.log('deploy salt:', '0x' + salt.toString(16));

const constructorCalldata = []; // empty ctor
const predictedAddr = lib.computeDeployAddress(NEW_ADDR, ZK_CLASS, salt, constructorCalldata, false);
console.log('PREDICTED new ZKVerifier address:', predictedAddr);

// Build the v3 invoke call
// Note: deploy_contract is an entrypoint on the account contract itself (NEW_ADDR).
const call = {
  contractAddress: NEW_ADDR, // self-call
  entrypoint: 'deploy_contract',
  calldata: [ZK_CLASS, '0x' + salt.toString(16), 0, 0], // [class_hash, salt, calldata_len=0, deploy_from_zero=false]
  // calldata array layout: [class_hash, salt, calldata_len, ...calldata, deploy_from_zero]
  // Since calldata=[] (length 0), the array is [class_hash, salt, 0, 0]
};

console.log('\nSubmitting v3 invoke (deploy_contract)...');
const r1 = await lib.submitV3Invoke(call, { maxAttempts: 90, interval: 2000 });
console.log('Deploy tx result:', JSON.stringify(r1, (k, v) => typeof v === 'bigint' ? '0x' + v.toString(16) : v).slice(0, 800));

if (r1.error || !r1.txHash) {
  console.error('FATAL: deploy_contract invoke failed');
  process.exit(1);
}

console.log('\n✓ deploy_contract tx:', r1.txHash);
console.log('  status:', r1.status);

// Verify the deployed address matches prediction
const chAtPred = await lib.rpc('starknet_getClassHashAt', ['latest', predictedAddr]);
console.log('\ngetClassHashAt predicted addr:', chAtPred.result || chAtPred.error);

let newZkAddr;
if (chAtPred.result) {
  newZkAddr = predictedAddr;
} else {
  // Try extracting from events
  console.log('Predicted addr has no class hash — inspecting receipt events...');
  const tx = await lib.rpc('starknet_getTransactionReceipt', [r1.txHash]);
  if (tx.result?.events) {
    for (const ev of tx.result.events) {
      if (ev.from_address === NEW_ADDR) {
        console.log('  ev:', JSON.stringify(ev));
      }
    }
  }
  throw new Error('Could not determine deployed ZKVerifier address');
}

// Sanity check: is_awa_frozen() should return true initially (constructor sets it)
const fr = await lib.callView(newZkAddr, 'is_awa_frozen', []);
console.log('\nis_awa_frozen() on new ZKVerifier (initial):', fr);

// Save deployment info
const deployInfo = {
  task: 'P1c — Deploy new ZKVerifier via NEW_ADDR.deploy_contract()',
  deployed_at: new Date().toISOString(),
  new_zk_verifier_address: newZkAddr,
  new_zk_verifier_class_hash: ZK_CLASS,
  deploy_tx_hash: r1.txHash,
  deploy_tx_status: r1.status,
  deployer: NEW_ADDR,
  deployer_class_hash: lib.V3_ACCT_CLASS,
  deploy_salt: '0x' + salt.toString(16),
  initial_awa_frozen: fr,
  owner_expected: NEW_ADDR,
  rpc: lib.RPC,
};

const outDir = '/home/z/my-project/trion-core/docs/proofs';
const deployInfoPath = path.join(outDir, 'zk_gauntlet_deployment.json');
await fs.mkdir(outDir, { recursive: true });
await fs.writeFile(deployInfoPath, JSON.stringify(deployInfo, null, 2));
console.log('\nSaved deployment info to:', deployInfoPath);

if (r1.status !== 'SUCCEEDED') {
  console.error('FATAL: deploy tx did not SUCCEED — aborting P1d');
  process.exit(1);
}

// === P1d: set_awa_state(false) to unfreeze AWA ===
console.log('\n=== P1d: set_awa_state(false) on new ZKVerifier ===');

const call2 = {
  contractAddress: newZkAddr,
  entrypoint: 'set_awa_state',
  calldata: [0], // false
};

const r2 = await lib.submitV3Invoke(call2, { maxAttempts: 90, interval: 2000 });
console.log('set_awa_state tx result:', JSON.stringify(r2, (k, v) => typeof v === 'bigint' ? '0x' + v.toString(16) : v).slice(0, 800));

if (r2.error || !r2.txHash) {
  console.error('FATAL: set_awa_state invoke failed');
  process.exit(1);
}

console.log('\n✓ set_awa_state(false) tx:', r2.txHash);
console.log('  status:', r2.status);
if (r2.revert_reason) console.log('  revert_reason:', r2.revert_reason);

// Verify is_awa_frozen() now returns false
const fr2 = await lib.callView(newZkAddr, 'is_awa_frozen', []);
console.log('\nis_awa_frozen() after set_awa_state(false):', fr2);

deployInfo.set_awa_state_tx_hash = r2.txHash;
deployInfo.set_awa_state_tx_status = r2.status;
deployInfo.set_awa_state_revert_reason = r2.revert_reason || null;
deployInfo.awa_frozen_after_unfreeze = fr2;
await fs.writeFile(deployInfoPath, JSON.stringify(deployInfo, null, 2));

console.log('\n=== P1c + P1d COMPLETE ===');
console.log('New ZKVerifier:', newZkAddr);
console.log('Deploy tx:', r1.txHash);
console.log('Unfreeze tx:', r2.txHash);
console.log('AWA frozen after:', fr2);
if (fr2 && fr2[0] === '0x0') {
  console.log('✓ AWA successfully UNFROZEN — ready for proof submission');
} else {
  console.error('✗ AWA still FROZEN — proofs will revert');
  process.exit(1);
}
