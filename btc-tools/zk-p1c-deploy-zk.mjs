// P1c + P1d — Deploy new ZKVerifier via NEW_ADDR's deploy_contract, then unfreeze AWA
import { submitV3Invoke, callView, NEW_ADDR, ZK_CLASS_HASH } from './zk-helpers.mjs';
import { hash as snHash } from 'starknet';

console.log('═══════════════════════════════════════════════════════════');
console.log('  P1c — Deploy new ZKVerifier via NEW_ADDR.deploy_contract');
console.log('═══════════════════════════════════════════════════════════\n');

// deploy_contract(class_hash, contract_address_salt, calldata: Array<felt252>, deploy_from_zero: bool)
// We call deploy_contract on NEW_ADDR (it's a function exposed via the v3 account class)
const salt = '0x' + BigInt(Date.now()).toString(16).padStart(8, '0').slice(-8);
console.log('Salt:', salt);

const deployCall = {
  contractAddress: NEW_ADDR,  // call self
  entrypoint: 'deploy_contract',
  calldata: [
    ZK_CLASS_HASH,    // class_hash
    salt,              // contract_address_salt
    0,                 // calldata length = 0 (constructor takes no args)
    0,                 // deploy_from_zero = false
  ],
};

const result = await submitV3Invoke([deployCall]);
console.log('Deploy result:', JSON.stringify(result, null, 2).slice(0, 800));

let newZkAddr = null;
if (result.success) {
  // Find ContractDeployed event to get the new address
  for (const ev of result.events) {
    // The event key for ContractDeployed is hash of "ContractDeployed"
    if (ev.keys && ev.keys.length > 0) {
      const evName = Buffer.from(ev.keys[0].replace('0x', '').padStart(64, '0'), 'hex').toString().replace(/\0/g, '').trim();
      console.log('Event:', ev.from_address?.slice(0,16), 'key:', ev.keys[0]?.slice(0,16));
    }
    // The deployed address is usually in event.data[0]
    if (ev.data && ev.data[0] && ev.from_address === NEW_ADDR) {
      newZkAddr = ev.data[0];
      console.log('Found new ZKVerifier address:', newZkAddr);
      break;
    }
  }
  if (!newZkAddr && result.events.length > 0) {
    // Try to find in any event
    for (const ev of result.events) {
      console.log('Event from:', ev.from_address, 'data:', ev.data);
      if (ev.data && ev.data[0] && BigInt(ev.data[0]) !== 0n && ev.from_address === NEW_ADDR) {
        newZkAddr = ev.data[0];
      }
    }
  }
}

if (!newZkAddr) {
  console.log('\nCould not extract new ZKVerifier address from events. Trying alternative method...');
  // Compute the address: hash.calculateContractAddressFromHash(salt, class_hash, [], deployer=NEW_ADDR)
  const computedAddr = snHash.calculateContractAddressFromHash(
    BigInt(salt),
    ZK_CLASS_HASH,
    [],
    BigInt(NEW_ADDR)
  );
  console.log('Computed address:', computedAddr);
  // Verify it's deployed
  const isFr = await callView(computedAddr, 'is_awa_frozen', []);
  console.log('is_awa_frozen() at computed addr:', isFr);
  if (isFr && !isFr.error) {
    newZkAddr = computedAddr;
  }
}

console.log('\nNew ZKVerifier address:', newZkAddr);

if (newZkAddr) {
  // Verify AWA state
  const isFr = await callView(newZkAddr, 'is_awa_frozen', []);
  console.log('is_awa_frozen() (initial):', isFr);

  // P1d — Call set_awa_state(false) to unfreeze AWA
  console.log('\n═══════════════════════════════════════════════════════════');
  console.log('  P1d — Call set_awa_state(false) to unfreeze AWA');
  console.log('═══════════════════════════════════════════════════════════\n');

  const unfreezeResult = await submitV3Invoke([{
    contractAddress: newZkAddr,
    entrypoint: 'set_awa_state',
    calldata: [0],  // false
  }]);
  console.log('Unfreeze result:', JSON.stringify({
    success: unfreezeResult.success,
    txHash: unfreezeResult.txHash,
    status: unfreezeResult.status,
    revert_reason: unfreezeResult.revert_reason?.slice(0, 200),
  }));

  // Verify AWA unfrozen
  const isFr2 = await callView(newZkAddr, 'is_awa_frozen', []);
  console.log('\nis_awa_frozen() after unfreeze:', isFr2);
  console.log('\n=== FINAL STATE ===');
  console.log('NEW_ADDR:', NEW_ADDR);
  console.log('New ZKVerifier:', newZkAddr);
  console.log('AWA frozen:', isFr2);
  console.log('Deploy tx:', result.txHash);
  console.log('Unfreeze tx:', unfreezeResult.txHash);
}

// Save to file
import { writeFileSync } from 'fs';
const state = {
  new_account: NEW_ADDR,
  new_account_priv: '0x_REDACTED_NEW_PRIV',
  new_zk_verifier: newZkAddr,
  deploy_tx: result.txHash,
  unfreeze_tx: unfreezeResult ? unfreezeResult.txHash : null,
  timestamp: new Date().toISOString(),
};
writeFileSync('/home/z/my-project/trion-core/docs/proofs/zk_p1_state.json', JSON.stringify(state, null, 2));
console.log('\nSaved state to docs/proofs/zk_p1_state.json');
