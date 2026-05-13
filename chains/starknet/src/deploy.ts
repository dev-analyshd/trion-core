/**
 * TRION Protocol — Starknet Sepolia Contract Deployer
 * Run: pnpm --filter @workspace/starknet-trion deploy
 *
 * Deploys:
 *  1. TRIONOracle.cairo   — stores BEO behavioral scores on-chain
 *  2. BEOAttestation.cairo — binds wallets to BEO identities
 *
 * Contract artifacts are compiled by Scarb before this runs.
 * After deploy, addresses are printed and should be saved as env vars:
 *   TRION_ORACLE_ADDRESS
 *   BEO_ATTESTATION_ADDRESS
 */
import 'dotenv/config';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { json, DeclareContractPayload, CallData, hash } from 'starknet';
import { getWorkingProvider, getAccount, printAccountInfo, ensureAccountDeployed } from './provider.js';
import { STARKNET_CONFIG } from './config.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ARTIFACTS_DIR = path.join(__dirname, '..', 'target', 'dev');

function loadArtifact(contractName: string): { sierra: any; casm: any } {
  const sierraPath = path.join(ARTIFACTS_DIR, `trion_oracle_${contractName}.contract_class.json`);
  const casmPath   = path.join(ARTIFACTS_DIR, `trion_oracle_${contractName}.compiled_contract_class.json`);

  if (!fs.existsSync(sierraPath)) {
    throw new Error(
      `Artifact not found: ${sierraPath}\n` +
      'Run: cd starknet-trion && scarb build'
    );
  }

  return {
    sierra: json.parse(fs.readFileSync(sierraPath, 'utf-8')),
    casm:   json.parse(fs.readFileSync(casmPath,   'utf-8')),
  };
}

async function declareAndDeploy(
  account: any,
  contractName: string,
  constructorCalldata: string[],
  label: string,
): Promise<string> {
  console.log(`\n── Deploying ${label} ────────────────────────────`);

  const { sierra, casm } = loadArtifact(contractName);

  // Declare
  console.log('  Declaring contract...');
  let classHash: string;
  try {
    const declarePayload: DeclareContractPayload = {
      contract: sierra,
      casm,
    };
    const declareRes = await account.declare(declarePayload);
    await account.waitForTransaction(declareRes.transaction_hash);
    classHash = declareRes.class_hash;
    console.log(`  ✓ Declared — class hash: ${classHash}`);
  } catch (e: any) {
    if (e.message?.includes('already declared') || e.message?.includes('ContractClassAlreadyDeclared')) {
      classHash = hash.computeContractClassHash(sierra);
      console.log(`  ✓ Already declared — class hash: ${classHash}`);
    } else {
      throw e;
    }
  }

  // Deploy (UDC)
  console.log('  Deploying instance...');
  const deployRes = await account.deployContract({
    classHash,
    constructorCalldata,
    salt: '0x' + Date.now().toString(16),
    unique: true,
  });
  await account.waitForTransaction(deployRes.transaction_hash);
  const contractAddress = deployRes.contract_address;

  console.log(`  ✓ Deployed — address: ${contractAddress}`);
  console.log(`    Voyager: ${STARKNET_CONFIG.explorer.voyager}/contract/${contractAddress}`);
  console.log(`    Tx:      ${STARKNET_CONFIG.explorer.voyager}/tx/${deployRes.transaction_hash}`);

  return contractAddress;
}

async function main() {
  console.log('═══════════════════════════════════════════════════════════');
  console.log('   TRION Protocol × Starknet — Contract Deployer           ');
  console.log('═══════════════════════════════════════════════════════════');

  const provider = await getWorkingProvider();
  const account  = getAccount(provider);

  console.log('\n── Deployer Account ──────────────────────────────────────');
  await printAccountInfo(account, provider);

  await ensureAccountDeployed(account, provider);

  // Deploy TRIONOracle (owner = deployer account)
  const oracleAddress = await declareAndDeploy(
    account,
    'TRIONOracle',
    CallData.compile({ owner: account.address }),
    'TRIONOracle'
  );

  // Deploy BEOAttestation (attester = deployer account)
  const attestationAddress = await declareAndDeploy(
    account,
    'BEOAttestation',
    CallData.compile({ attester: account.address }),
    'BEOAttestation'
  );

  console.log('\n═══════════════════════════════════════════════════════════');
  console.log('   Deployment Complete — Save these as Replit Secrets:     ');
  console.log('═══════════════════════════════════════════════════════════');
  console.log(`   TRION_ORACLE_ADDRESS    = ${oracleAddress}`);
  console.log(`   BEO_ATTESTATION_ADDRESS = ${attestationAddress}`);
  console.log('═══════════════════════════════════════════════════════════\n');
}

main().catch(e => {
  console.error('\n✗ Deployment failed:', e.message);
  if (e.message?.includes('scarb build')) {
    console.error('\nFix: run "cd starknet-trion && scarb build" first');
  }
  process.exit(1);
});
