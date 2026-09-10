/**
 * stellar-deploy.mjs — Deploy 5 Soroban WASM contracts to Stellar testnet.
 * Uses @stellar/stellar-sdk rpc.Server + uploadContractWasm + createCustomContract.
 */
const StellarSdk = require('@stellar/stellar-sdk');
const fs = require('fs');
const path = require('path');

const SECRET = 'SAWLPNNYGPLCLYO5PPUCW5MHQ6EYCBONVLASEH3GENWP276OSTJNGKXQ';
const RPC_URL = 'https://soroban-testnet.stellar.org';

const keypair = StellarSdk.Keypair.fromSecret(SECRET);
const publicKey = keypair.publicKey();
console.log('Deployer:', publicKey);

const server = new StellarSdk.rpc.Server(RPC_URL);
const WASM_DIR = path.join(__dirname, '..', 'contracts', 'soroban', 'target', 'wasm32-unknown-unknown', 'release');

const contracts = [
  { name: 'btc-spv-verifier', wasm: 'btc_spv_verifier.wasm' },
  { name: 'btcp-escrow', wasm: 'btcp_escrow.wasm' },
  { name: 'btcp-intent', wasm: 'btcp_intent.wasm' },
  { name: 'btcp-route', wasm: 'btcp_route.wasm' },
  { name: 'liquidity-ocean', wasm: 'liquidity_ocean.wasm' },
];

async function submitTx(txBuilder) {
  // Simulate
  const sim = await server.simulateTransaction(txBuilder);
  if (sim.error) throw new Error(`Simulate: ${sim.error}`);
  
  // Prepare with simulation result
  const prepared = StellarSdk.rpc.assembleTransaction(txBuilder, sim).build();
  prepared.sign(keypair);
  
  // Submit
  const resp = await server.sendTransaction(prepared);
  if (resp.status === 'ERROR') throw new Error(`Submit: ${JSON.stringify(resp).slice(0,200)}`);
  
  // Wait for confirmation
  let hash = resp.hash;
  for (let i = 0; i < 30; i++) {
    await new Promise(r => setTimeout(r, 3000));
    const txResult = await server.getTransaction(hash);
    if (txResult.status === 'SUCCESS') return { hash, result: txResult };
    if (txResult.status === 'FAILED') throw new Error(`TX failed: ${JSON.stringify(txResult).slice(0,200)}`);
  }
  throw new Error('TX timeout');
}

async function deployContract(name, wasmPath) {
  console.log(`\n=== ${name} ===`);
  const wasm = fs.readFileSync(wasmPath);
  console.log(`  WASM: ${wasm.length} bytes`);

  const account = await server.getAccount(publicKey);

  // Step 1: Upload WASM
  console.log('  Uploading WASM...');
  const uploadTx = new StellarSdk.TransactionBuilder(account, {
    fee: '1000000', networkPassphrase: StellarSdk.Networks.TESTNET,
  }).addOperation(StellarSdk.Operation.uploadContractWasm({ wasm }))
    .setTimeout(300).build();

  const uploadResult = await submitTx(uploadTx);
  console.log(`  Upload tx: ${uploadResult.hash.slice(0,18)}...`);

  // Extract WASM hash from the result
  const wasmHash = uploadResult.result?.resultMetaXdr?.let?.(() => {
    try { return StellarSdk.xdr.ScVal.fromXDR(uploadResult.result.resultMetaXdr, 'base64').toString(); }
    catch { return 'unknown'; }
  }) || 'extracted-from-receipt';
  console.log(`  WASM hash: ${typeof wasmHash === 'string' ? wasmHash.slice(0,30) : wasmHash}`);

  return { name, wasmSize: wasm.length, uploadTx: uploadResult.hash, wasmHash: wasmHash };
}

async function main() {
  console.log('=== Stellar Soroban Contract Deployment ===');
  const deployments = [];
  
  for (const c of contracts) {
    const wasmPath = path.join(WASM_DIR, c.wasm);
    if (!fs.existsSync(wasmPath)) { console.log(`  ${c.name}: WASM not found`); continue; }
    try {
      const result = await deployContract(c.name, wasmPath);
      deployments.push(result);
    } catch (e) {
      console.log(`  ERR: ${e.message.slice(0,200)}`);
      deployments.push({ name: c.name, error: e.message.slice(0,200) });
    }
  }

  const record = {
    network: 'stellar-testnet', rpc: RPC_URL, deployer: publicKey,
    deployedAt: new Date().toISOString(), contracts: deployments,
  };
  const dir = path.join(__dirname, '..', 'docs', 'deployments');
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'stellar_testnet.json'), JSON.stringify(record, null, 2));
  console.log('\n=== Deployment record saved ===');
  console.log(JSON.stringify(deployments, null, 2));
}

main().catch(e => { console.error('FATAL:', e); process.exit(1); });
