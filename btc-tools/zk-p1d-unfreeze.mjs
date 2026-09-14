// Continue P1d: new ZKVerifier already deployed, just set_awa_state(false)
import * as lib from './zk-gauntlet-lib.mjs';
import { promises as fs } from 'node:fs';
import path from 'node:path';

const newZkAddr = '0x22f72b5b445e787889ca7bbb0047851e9816e85ce422043d6fc9e16f27b69be';
const deployTxHash = '0x3f3441dfb5a9fb3dc988fba9024c8a89c1e98a947e9f37653d277b01dd8b549';

console.log('=== P1c verify + P1d unfreeze ===');
console.log('New ZKVerifier address:', newZkAddr);

// Verify class hash
const ch = await lib.rpc('starknet_getClassHashAt', ['latest', newZkAddr]);
console.log('Class hash at new addr:', ch.result || ch.error);

// Check is_awa_frozen (should be true initially per constructor)
const fr1 = await lib.callView(newZkAddr, 'is_awa_frozen', []);
console.log('is_awa_frozen() initial:', fr1);

// Call set_awa_state(false) from NEW_ADDR (which is the owner)
console.log('\n=== P1d: Submit set_awa_state(false) ===');
const call = {
  contractAddress: newZkAddr,
  entrypoint: 'set_awa_state',
  calldata: [0], // false
};
const r = await lib.submitV3Invoke(call, { maxAttempts: 90, interval: 2000 });
console.log('Result:', JSON.stringify(r, (k, v) => typeof v === 'bigint' ? '0x' + v.toString(16) : v).slice(0, 600));

if (r.error || !r.txHash) {
  console.error('FATAL: set_awa_state invoke failed');
  process.exit(1);
}

// Wait a moment for state to settle
await lib.sleep(1500);
const fr2 = await lib.callView(newZkAddr, 'is_awa_frozen', []);
console.log('\nis_awa_frozen() after unfreeze:', fr2);

const deployInfo = {
  task: 'P1c+P1d — Deploy new ZKVerifier + unfreeze AWA',
  deployed_at: new Date().toISOString(),
  new_zk_verifier_address: newZkAddr,
  new_zk_verifier_class_hash: lib.ZK_VERIFIER_CLASS,
  deploy_tx_hash: deployTxHash,
  deploy_tx_status: 'SUCCEEDED',
  deployer: lib.NEW_ADDR,
  deployer_class_hash: lib.V3_ACCT_CLASS,
  initial_awa_frozen: fr1,
  set_awa_state_tx_hash: r.txHash,
  set_awa_state_tx_status: r.status,
  set_awa_state_revert_reason: r.revert_reason || null,
  awa_frozen_after_unfreeze: fr2,
  rpc: lib.RPC,
};

const outDir = '/home/z/my-project/trion-core/docs/proofs';
const deployInfoPath = path.join(outDir, 'zk_gauntlet_deployment.json');
await fs.writeFile(deployInfoPath, JSON.stringify(deployInfo, null, 2));
console.log('\nSaved to:', deployInfoPath);

if (fr2 && fr2[0] === '0x0') {
  console.log('\n✓✓✓ AWA UNFROZEN — ready for 100-proof gauntlet');
} else {
  console.error('\n✗ AWA still FROZEN');
  process.exit(1);
}
