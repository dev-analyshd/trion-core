/**
 * TRION Protocol — BTCFi Guard Deployer
 * Run: pnpm --filter @workspace/starknet-trion deploy:btcfi
 *
 * Deploys BTCFiGuard.cairo — composable anti-Sybil risk module for BTCFi protocols.
 * Requires TRION_ORACLE_ADDRESS to be set (already deployed TRIONOracle contract).
 */
import 'dotenv/config';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { json, DeclareContractPayload, CallData, hash } from 'starknet';
import { getWorkingProvider, getAccount } from './provider.js';
import { STARKNET_CONFIG } from './config.js';

const __dirname    = path.dirname(fileURLToPath(import.meta.url));
const ARTIFACTS_DIR = path.join(__dirname, '..', 'target', 'dev');

function loadArtifact(contractName: string) {
  const sierraPath = path.join(ARTIFACTS_DIR, `trion_oracle_${contractName}.contract_class.json`);
  const casmPath   = path.join(ARTIFACTS_DIR, `trion_oracle_${contractName}.compiled_contract_class.json`);
  if (!fs.existsSync(sierraPath)) throw new Error(`Artifact not found: ${sierraPath}\nRun: cd starknet-trion && scarb build`);
  return {
    sierra: json.parse(fs.readFileSync(sierraPath, 'utf-8')),
    casm:   json.parse(fs.readFileSync(casmPath,   'utf-8')),
  };
}

async function main() {
  console.log('═══════════════════════════════════════════════════════════');
  console.log('   TRION Protocol × Starknet — BTCFi Guard Deployer       ');
  console.log('═══════════════════════════════════════════════════════════\n');

  const oracleAddress = STARKNET_CONFIG.contracts.TRIONOracle;
  if (!oracleAddress) throw new Error('TRION_ORACLE_ADDRESS not set. Deploy TRIONOracle first.');

  const provider = await getWorkingProvider();
  const account  = getAccount(provider);

  console.log(`Deployer:       ${account.address}`);
  console.log(`Oracle address: ${oracleAddress}\n`);

  const { sierra, casm } = loadArtifact('BTCFiGuard');

  // Declare
  console.log('── Declaring BTCFiGuard ──────────────────────────────────');
  let classHash: string;
  try {
    const declarePayload: DeclareContractPayload = { contract: sierra, casm };
    const declareRes = await account.declare(declarePayload);
    await account.waitForTransaction(declareRes.transaction_hash);
    classHash = declareRes.class_hash;
    console.log(`✓ Declared — class hash: ${classHash}`);
  } catch (e: any) {
    if (e.message?.includes('already declared') || e.message?.includes('ContractClassAlreadyDeclared')) {
      classHash = hash.computeContractClassHash(sierra);
      console.log(`✓ Already declared — class hash: ${classHash}`);
    } else {
      throw e;
    }
  }

  // Deploy
  console.log('\n── Deploying BTCFiGuard ──────────────────────────────────');
  const deployRes = await account.deployContract({
    classHash,
    constructorCalldata: CallData.compile({ owner: account.address, oracle: oracleAddress }),
    salt: '0x' + Date.now().toString(16),
    unique: true,
  });
  await account.waitForTransaction(deployRes.transaction_hash);
  const contractAddress = deployRes.contract_address;

  console.log(`\n✓ BTCFiGuard deployed!`);
  console.log(`  Address: ${contractAddress}`);
  console.log(`  Voyager: ${STARKNET_CONFIG.explorer.voyager}/contract/${contractAddress}`);
  console.log(`  Tx:      ${STARKNET_CONFIG.explorer.voyager}/tx/${deployRes.transaction_hash}`);

  console.log('\n═══════════════════════════════════════════════════════════');
  console.log('   Save as Replit Secret:                                  ');
  console.log(`   BTCFI_GUARD_ADDRESS = ${contractAddress}`);
  console.log('═══════════════════════════════════════════════════════════\n');
}

main().catch(e => {
  console.error('\n✗ Deployment failed:', e.message);
  process.exit(1);
});
