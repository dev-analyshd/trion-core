// Declare ZKVerifier v2 using starknet.js's account.declareIfNot
import { readFileSync, writeFileSync } from 'fs';
import { RpcProvider, Account, hash, json, ec } from 'starknet';

const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
const NEW_ADDR = '0x06d58c2aa17312d090c27ac52b9f9e4a5d267675afee9dedf424b61655cc1854';
const NEW_PRIV = '0x_REDACTED_NEW_PRIV';

const provider = new RpcProvider({ nodeUrl: RPC });
const account = new Account({ provider, address: NEW_ADDR, signer: NEW_PRIV });

console.log('═══════════════════════════════════════════════════════════');
console.log('  DECLARE ZKVerifier v2 via starknet.js account.declareIfNot');
console.log('═══════════════════════════════════════════════════════════\n');

const sierraPath = '/home/z/my-project/trion-core/zk/stark/contract/target/dev/zk_verifier_contract_ZKVerifier.contract_class.json';
const casmPath = '/home/z/my-project/trion-core/zk/stark/contract/target/dev/zk_verifier_contract_ZKVerifier.compiled_contract_class.json';

const sierraJson = JSON.parse(readFileSync(sierraPath, 'utf-8'));
const casmJson = JSON.parse(readFileSync(casmPath, 'utf-8'));

let classHash;
try {
  classHash = hash.computeSierraContractClassHash(sierraJson);
  console.log('Computed class hash:', classHash);
} catch (e) {
  console.log('computeSierraContractClassHash err:', String(e.message).slice(0, 500));
  process.exit(1);
}

// Check if already declared
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}
const r0 = await rpc('starknet_getClass', [classHash]);
if (r0.result) {
  console.log('✓ Class already declared on Sepolia:', classHash);
  writeFileSync('/home/z/my-project/trion-core/docs/proofs/zk_v2_declare.json', JSON.stringify({
    class_hash: classHash,
    already_declared: true,
    timestamp: new Date().toISOString(),
  }, null, 2));
  process.exit(0);
}

console.log('\nClass not yet declared. Calling account.declareIfNot()...');

// Use starknet.js's account.declareIfNot (which uses Cairo1 declare)
// Set resource bounds manually
const L2_MAX_AMOUNT = 0x40000000n, L2_MAX_PRICE = 0xba43b7400n;  // 1B l2 gas
const L1_MAX_AMOUNT = 0x400n, L1_MAX_PRICE = 0x8d79883d20000n;
const L1D_MAX_AMOUNT = 0x800n, L1D_MAX_PRICE = 0x62448724953354n;
// Max fee = 1B * 5e10 + 1024 * 4e16 + 2048 * 2.77e16 = 5e19 + 4.1e19 + 5.66e19 = ~14.7 STRK max

try {
  const declareResult = await account.declareIfNot({
    contract: sierraJson,
    casm: casmJson,
  }, {
    version: '0x3',
    resourceBounds: {
      l2_gas: { max_amount: L2_MAX_AMOUNT, max_price_per_unit: L2_MAX_PRICE },
      l1_gas: { max_amount: L1_MAX_AMOUNT, max_price_per_unit: L1_MAX_PRICE },
      l1_data_gas: { max_amount: L1D_MAX_AMOUNT, max_price_per_unit: L1D_MAX_PRICE },
    },
  });
  console.log('\n✓ declare submitted:', declareResult.transaction_hash);
  console.log('  class_hash:', declareResult.class_hash);
  // Wait for receipt
  console.log('Waiting for receipt...');
  const receipt = await provider.waitForTransaction(declareResult.transaction_hash);
  console.log('  status:', receipt.execution_status);
  if (receipt.execution_status !== 'SUCCEEDED') {
    console.log('  revert_reason:', (receipt.revert_reason || '').slice(0, 500));
  } else {
    console.log('  ✓ Class declared successfully!');
  }
  writeFileSync('/home/z/my-project/trion-core/docs/proofs/zk_v2_declare.json', JSON.stringify({
    class_hash: declareResult.class_hash,
    declare_tx: declareResult.transaction_hash,
    status: receipt.execution_status,
    timestamp: new Date().toISOString(),
  }, null, 2));
  console.log('\nSaved to docs/proofs/zk_v2_declare.json');
} catch (e) {
  console.log('declareIfNot err:', String(e.message).slice(0, 500));
  console.log(e.stack);
  // Try alternative: account.declare
  console.log('\nTrying account.declare...');
  try {
    const declareResult = await account.declare({
      contract: sierraJson,
      casm: casmJson,
    }, {
      version: '0x3',
      resourceBounds: {
        l2_gas: { max_amount: L2_MAX_AMOUNT, max_price_per_unit: L2_MAX_PRICE },
        l1_gas: { max_amount: L1_MAX_AMOUNT, max_price_per_unit: L1_MAX_PRICE },
        l1_data_gas: { max_amount: L1D_MAX_AMOUNT, max_price_per_unit: L1D_MAX_PRICE },
      },
    });
    console.log('declare submitted:', declareResult.transaction_hash);
    const receipt = await provider.waitForTransaction(declareResult.transaction_hash);
    console.log('status:', receipt.execution_status);
    if (receipt.execution_status !== 'SUCCEEDED') {
      console.log('revert_reason:', (receipt.revert_reason || '').slice(0, 500));
    }
    writeFileSync('/home/z/my-project/trion-core/docs/proofs/zk_v2_declare.json', JSON.stringify({
      class_hash: declareResult.class_hash,
      declare_tx: declareResult.transaction_hash,
      status: receipt.execution_status,
      timestamp: new Date().toISOString(),
    }, null, 2));
  } catch (e2) {
    console.log('declare err:', String(e2.message).slice(0, 500));
    console.log(e2.stack);
  }
}
