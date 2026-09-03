/**
 * TRION Protocol — Starknet Sepolia FULL Contract Suite Deployer
 * Deploys all 7 contracts on Starknet Sepolia using STRK for gas fees.
 *
 * Contracts: TRIONOracle, BEOAttestation, BTCFiGuard, BTCPIntent, BTCPRoute, BTCPEscrow, LiquidityOcean
 *
 * Run: npx tsx src/deploy-all.ts
 */
import 'dotenv/config';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { json, DeclareContractPayload, CallData, hash } from 'starknet';
import { getWorkingProvider, getAccount, printAccountInfo, ensureAccountDeployed } from './provider.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ARTIFACTS_DIR = path.join(__dirname, '..', 'target', 'dev');

interface DeployResult { name: string; address: string; classHash: string; txHash: string; }

function loadArtifact(contractName: string): { sierra: any; casm: any } {
  const sierraPath = path.join(ARTIFACTS_DIR, `trion_oracle_${contractName}.contract_class.json`);
  const casmPath   = path.join(ARTIFACTS_DIR, `trion_oracle_${contractName}.compiled_contract_class.json`);
  if (!fs.existsSync(sierraPath)) throw new Error(`Artifact not found: ${sierraPath}\nRun: scarb build`);
  return { sierra: json.parse(fs.readFileSync(sierraPath, 'utf-8')), casm: json.parse(fs.readFileSync(casmPath, 'utf-8')) };
}

const declaredClasses = new Map<string, string>();

async function declareAndDeploy(account: any, contractName: string, constructorCalldata: any, label: string): Promise<DeployResult> {
  console.log(`\n── Deploying ${label} ────────────────────────────`);
  const { sierra, casm } = loadArtifact(contractName);
  let classHash: string;
  const cacheKey = hash.computeSierraContractClassHash(sierra);
  if (declaredClasses.has(cacheKey)) {
    classHash = declaredClasses.get(cacheKey)!;
    console.log(`  ✓ Already declared — class hash: ${classHash}`);
  } else {
    try {
      const declarePayload: DeclareContractPayload = { contract: sierra, casm };
      const declareRes = await account.declare(declarePayload);
      await account.waitForTransaction(declareRes.transaction_hash);
      classHash = declareRes.class_hash;
      console.log(`  ✓ Declared — class hash: ${classHash}`);
    } catch (e: any) {
      const msg = e?.message ?? String(e);
      if (msg.includes('already declared') || msg.includes('ContractClassAlreadyDeclared')) {
        classHash = hash.computeContractClassHash(sierra);
        console.log(`  ✓ Already declared on-chain — class hash: ${classHash}`);
      } else throw e;
    }
    declaredClasses.set(cacheKey, classHash);
  }
  const deployRes = await account.deployContract({ classHash, constructorCalldata, salt: '0x' + Math.floor(Date.now() + Math.random() * 1e6).toString(16), unique: true });
  await account.waitForTransaction(deployRes.transaction_hash);
  const contractAddress = deployRes.contract_address;
  console.log(`  ✓ Deployed — address: ${contractAddress}`);
  return { name: contractName, address: contractAddress, classHash, txHash: deployRes.transaction_hash };
}

async function main() {
  console.log('═══════════════════════════════════════════════════════════');
  console.log('  TRION Protocol × Starknet SEPOLIA — Full Suite Deployer   ');
  console.log('  7 contracts · STRK gas fees · SN_SEPOLIA                ');
  console.log('═══════════════════════════════════════════════════════════');
  const provider = await getWorkingProvider();
  const account  = getAccount(provider);
  await printAccountInfo(account, provider);
  await ensureAccountDeployed(account, provider);
  const owner = account.address;
  const results: DeployResult[] = [];

  // 1. TRIONOracle
  results.push(await declareAndDeploy(account, 'TRIONOracle', CallData.compile({ owner }), 'TRIONOracle'));
  const oracleAddress = results[0].address;
  // 2. BEOAttestation
  results.push(await declareAndDeploy(account, 'BEOAttestation', CallData.compile({ attester: owner }), 'BEOAttestation'));
  // 3. BTCFiGuard
  results.push(await declareAndDeploy(account, 'BTCFiGuard', CallData.compile({ owner, oracle: oracleAddress }), 'BTCFiGuard'));
  // 4. BTCPIntent
  results.push(await declareAndDeploy(account, 'BTCPIntent', CallData.compile({ owner }), 'BTCPIntent'));
  // 5. BTCPRoute
  results.push(await declareAndDeploy(account, 'BTCPRoute', CallData.compile({ owner }), 'BTCPRoute'));
  // 6. BTCPEscrow
  results.push(await declareAndDeploy(account, 'BTCPEscrow', CallData.compile({ owner }), 'BTCPEscrow'));
  // 7. LiquidityOcean
  results.push(await declareAndDeploy(account, 'LiquidityOcean', CallData.compile({ owner }), 'LiquidityOcean'));

  console.log('\n═══════════════════════════════════════════════════════════');
  console.log('  ✅ DEPLOYMENT COMPLETE — Starknet Sepolia              ');
  console.log('═══════════════════════════════════════════════════════════\n');
  for (const r of results) console.log(`  ${r.name.padEnd(18)} ${r.address}`);
  const deployRecord = { network: 'starknet-sepolia', chainId: 'SN_SEPOLIA', deployedAt: new Date().toISOString(), deployer: owner, contracts: results.map(r => ({ name: r.name, address: r.address, classHash: r.classHash, txHash: r.txHash })) };
  fs.writeFileSync(path.join(__dirname, '..', 'starknet_sepolia_deployments.json'), JSON.stringify(deployRecord, null, 2));
  console.log(`\n  Deployment record saved.`);
}
main().catch(e => { console.error('\n✗ Deployment failed:', e.message); process.exit(1); });
