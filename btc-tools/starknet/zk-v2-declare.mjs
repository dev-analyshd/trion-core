// Declare the new ZKVerifier v2 class on Starknet Sepolia
// Uses the new v3 account's __execute__ → declare_syscall path
import { readFileSync } from 'fs';
import { ec, hash, CallData, RpcProvider, Account, json } from 'starknet';

const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
const NEW_ADDR = '0x06d58c2aa17312d090c27ac52b9f9e4a5d267675afee9dedf424b61655cc1854';
const NEW_PRIV = '0x_REDACTED_NEW_PRIV';

const provider = new RpcProvider({ nodeUrl: RPC });
const account = new Account({ provider, address: NEW_ADDR, signer: NEW_PRIV });

async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

console.log('═══════════════════════════════════════════════════════════');
console.log('  DECLARE ZKVerifier v2 (HARDENED) class on Starknet Sepolia');
console.log('═══════════════════════════════════════════════════════════\n');

// Load the compiled Sierra (contract_class.json)
const sierraPath = '/home/z/my-project/trion-core/zk/stark/contract/target/dev/zk_verifier_contract_ZKVerifier.contract_class.json';
const casmPath = '/home/z/my-project/trion-core/zk/stark/contract/target/dev/zk_verifier_contract_ZKVerifier.compiled_contract_class.json';

const sierraJson = JSON.parse(readFileSync(sierraPath, 'utf-8'));
const casmJson = JSON.parse(readFileSync(casmPath, 'utf-8'));

// Compute the class hash locally first (for reference)
let classHash;
try {
  classHash = hash.computeSierraContractClassHash(sierraJson);
  console.log('Computed class hash:', classHash);
} catch (e) {
  console.log('computeSierraContractClassHash err:', String(e.message).slice(0, 200));
}

// Check if class is already declared
const r0 = await rpc('starknet_getClass', [classHash]);
if (r0.result) {
  console.log('✓ Class already declared on Sepolia:', classHash);
  console.log('Skipping declare...');
  // Save and exit
  const result = { class_hash: classHash, already_declared: true };
  console.log('\nFinal result:', JSON.stringify(result, null, 2));
  process.exit(0);
}

console.log('\nClass not yet declared. Submitting declare tx...');

// Get nonce + chainId
const chainId = BigInt((await rpc('starknet_chainId', [])).result);
const nonce = BigInt((await rpc('starknet_getNonce', ['latest', NEW_ADDR])).result);
console.log('nonce:', nonce);

// Build the declare transaction using starknet.js's signer.signDeclare
// For v3 declare, we need: class_hash, compiled_class_hash, sender_address, nonce, etc.
const compiledClassHash = hash.computeCompiledClassHash(casmJson);
console.log('compiled_class_hash:', compiledClassHash);

const resourceBounds = {
  l2_gas: { max_amount: 0x989680n, max_price_per_unit: 0xba43b7400n },
  l1_gas: { max_amount: 0xc8n, max_price_per_unit: 0x8d79883d20000n },
  l1_data_gas: { max_amount: 0x3e8n, max_price_per_unit: 0x62448724953354n },
};

const details = {
  version: '0x3',
  walletAddress: NEW_ADDR,
  senderAddress: NEW_ADDR,  // alias
  nonce,
  maxFee: 0n,
  chainId,
  cairoVersion: '1',
  resourceBounds,
  tip: 0n,
  paymasterData: [],
  accountDeploymentData: [],
  nonceDataAvailabilityMode: 'L1',
  feeDataAvailabilityMode: 'L1',
  proofFacts: undefined,
  classHash,
  compiledClassHash,
};

// Use starknet.js's account.signer.signDeclareTransaction to compute the sig
let sig;
try {
  sig = await account.signer.signDeclareTransaction(details);
  console.log('sig r:', '0x' + sig.r.toString(16));
} catch (e) {
  console.log('signDeclareTransaction err:', String(e.message).slice(0, 500));
  // Print full stack
  console.log(e.stack);
  process.exit(1);
}

// Submit declare via raw JSON-RPC
// starknet_addDeclareTransaction expects contract_class as a JSON STRING (not an object)
const declareReq = {
  type: 'DECLARE',
  sender_address: NEW_ADDR,
  contract_class: json.stringify(sierraJson),  // serialize to string
  compiled_class_hash: '0x' + compiledClassHash.toString(16).padStart(64, '0'),
  version: '0x3',
  signature: ['0x' + sig.r.toString(16).padStart(64, '0'), '0x' + sig.s.toString(16).padStart(64, '0')],
  nonce: '0x' + nonce.toString(16),
  resource_bounds: {
    l2_gas: { max_amount: '0x989680', max_price_per_unit: '0xba43b7400' },
    l1_gas: { max_amount: '0xc8', max_price_per_unit: '0x8d79883d20000' },
    l1_data_gas: { max_amount: '0x3e8', max_price_per_unit: '0x62448724953354' },
  },
  tip: '0x0',
  paymaster_data: [],
  nonce_data_availability_mode: 'L1',
  fee_data_availability_mode: 'L1',
  account_deployment_data: [],
};

console.log('\nSubmitting declare tx...');
const r = await rpc('starknet_addDeclareTransaction', [declareReq]);
console.log('Result:', JSON.stringify(r).slice(0, 500));

if (r.result?.transaction_hash) {
  console.log('\n✓ declare tx submitted:', r.result.transaction_hash);
  console.log('  class_hash:', r.result.class_hash);
  // Wait for receipt
  for (let i = 0; i < 60; i++) {
    const rcpt = await rpc('starknet_getTransactionReceipt', [r.result.transaction_hash]);
    if (rcpt.result) {
      console.log('Receipt:');
      console.log('  status:', rcpt.result.execution_status);
      console.log('  actual_fee:', rcpt.result.actual_fee);
      if (rcpt.result.execution_status !== 'SUCCEEDED') {
        console.log('  revert_reason:', (rcpt.result.revert_reason || '').slice(0, 500));
      } else {
        console.log('  ✓ Class declared successfully!');
      }
      break;
    }
    await new Promise(r => setTimeout(r, 2000));
  }
} else if (r.error) {
  console.log('declare failed:', r.error.message);
  console.log('  data:', JSON.stringify(r.error.data).slice(0, 500));
}

// Save state
import { writeFileSync } from 'fs';
writeFileSync('/home/z/my-project/trion-core/docs/proofs/zk_v2_declare.json', JSON.stringify({
  class_hash: classHash,
  declare_tx: r.result?.transaction_hash,
  timestamp: new Date().toISOString(),
}, null, 2));
console.log('\nSaved to docs/proofs/zk_v2_declare.json');
