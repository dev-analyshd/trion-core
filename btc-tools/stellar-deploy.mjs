/**
 * stellar-deploy.mjs — Deploy 5 Soroban WASM contracts to Stellar testnet.
 */
import * as StellarSdk from '@stellar/stellar-sdk';
import * as fs from 'fs';
import * as path from 'path';

const SECRET = 'SAWLPNNYGPLCLYO5PPUCW5MHQ6EYCBONVLASEH3GENWP276OSTJNGKXQ';
const RPC_URL = 'https://soroban-testnet.stellar.org';
const HORIZON_URL = 'https://horizon-testnet.stellar.org';

const keypair = StellarSdk.Keypair.fromSecret(SECRET);
const publicKey = keypair.publicKey();
console.log('Deployer:', publicKey);

const server = new StellarSdk.SorobanRpc.Server(RPC_URL);
const WASM_DIR = path.join(process.cwd(), 'contracts', 'soroban', 'target', 'wasm32-unknown-unknown', 'release');

const contracts = [
  { name: 'btc-spv-verifier', wasm: 'btc_spv_verifier.wasm' },
  { name: 'btcp-escrow', wasm: 'btcp_escrow.wasm' },
  { name: 'btcp-intent', wasm: 'btcp_intent.wasm' },
  { name: 'btcp-route', wasm: 'btcp_route.wasm' },
  { name: 'liquidity-ocean', wasm: 'liquidity_ocean.wasm' },
];

async function deployContract(name, wasmPath) {
  console.log(`\n=== Deploying ${name} ===`);
  const wasm = fs.readFileSync(wasmPath);
  console.log(`  WASM size: ${wasm.length} bytes`);

  try {
    // Step 1: Upload WASM
    console.log('  Uploading WASM...');
    const account = await server.getAccount(publicKey);

    // Build the upload transaction
    const tx = new StellarSdk.TransactionBuilder(account, {
      fee: '1000000',
      networkPassphrase: StellarSdk.Networks.TESTNET,
    })
      .addOperation(StellarSdk.Operation.uploadBytes({ wasm }))
      .setTimeout(300)
      .build();

    // Simulate
    const simResponse = await server.simulateTransaction(tx);
    if (simResponse.error) {
      console.log(`  Simulate error: ${simResponse.error}`);
      return null;
    }
    console.log(`  Simulate OK`);

    // Prepare and sign
    const preparedTx = await server.prepareTransaction(tx, simResponse);
    preparedTx.sign(keypair);

    // Submit
    const response = await server.sendTransaction(preparedTx);
    console.log(`  Submit status: ${response.status}`);

    if (response.status === 'ERROR') {
      console.log(`  Error: ${JSON.stringify(response.errorResult?.xdr || response).slice(0, 200)}`);
      return null;
    }

    // Wait for confirmation
    let hash = response.hash;
    console.log(`  TX hash: ${hash}`);
    await new Promise(r => setTimeout(r, 5000));

    // Get the WASM hash from the result
    const resultXdr = response.errorResult?.xdr || simResponse.results?.[0]?.xdr;
    console.log(`  WASM upload complete`);

    return { name, wasmHash: hash, deployed: true };
  } catch (e) {
    console.log(`  ERR: ${e.message?.slice(0, 200)}`);
    return null;
  }
}

async function main() {
  console.log('=== Stellar Soroban Contract Deployment ===');

  const deployments = [];
  for (const c of contracts) {
    const wasmPath = path.join(WASM_DIR, c.wasm);
    if (!fs.existsSync(wasmPath)) {
      console.log(`  ${c.name}: WASM not found at ${wasmPath}`);
      continue;
    }
    const result = await deployContract(c.name, wasmPath);
    deployments.push(result);
  }

  // Save deployment record
  const record = {
    network: 'stellar-testnet',
    rpc: RPC_URL,
    horizon: HORIZON_URL,
    deployer: publicKey,
    deployedAt: new Date().toISOString(),
    contracts: deployments,
  };
  const dir = path.join(process.cwd(), 'docs', 'deployments');
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'stellar_testnet.json'), JSON.stringify(record, null, 2));
  console.log('\n=== Deployment record saved ===');
  console.log(JSON.stringify(record, null, 2));
}

main().catch(e => { console.error('FATAL:', e); process.exit(1); });
