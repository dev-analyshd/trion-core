/**
 * TRION Starknet Verifier
 * Run: pnpm --filter @workspace/starknet-trion verify
 *
 * Checks:
 *  - RPC connectivity and chain ID
 *  - Account address and balance
 *  - Latest block info
 *  - TRION API connectivity
 *  - FAISS service connectivity
 */
import 'dotenv/config';
import axios from 'axios';
import { getWorkingProvider, getAccount, printAccountInfo } from './provider.js';
import { STARKNET_CONFIG } from './config.js';

async function checkTrionServices() {
  console.log('\n── TRION Services ────────────────────────────────────────');

  try {
    const r = await axios.get(`${STARKNET_CONFIG.trion.apiBaseUrl}/health`, { timeout: 4000 });
    console.log('✓ API Server:', r.data?.status ?? 'ok');
  } catch {
    try {
      const r = await axios.get(`${STARKNET_CONFIG.trion.apiBaseUrl}/api/trion/trajectory_anomaly/NETWORK`, { timeout: 4000 });
      console.log('✓ API Server: responding', r.status);
    } catch (e2) {
      console.warn('✗ API Server: unreachable');
    }
  }

  try {
    const r = await axios.get(`${STARKNET_CONFIG.trion.faissBaseUrl}/api/v1/trajectory_anomaly/NETWORK`, { timeout: 4000 });
    console.log('✓ FAISS Engine:', r.data?.status ?? r.status);
  } catch {
    console.warn('✗ FAISS Engine: unreachable');
  }
}

async function main() {
  console.log('═══════════════════════════════════════════════════════════');
  console.log('   TRION Protocol × Starknet — Environment Verification    ');
  console.log('═══════════════════════════════════════════════════════════');

  // 1. RPC + chain
  console.log('\n── Starknet Sepolia RPC ──────────────────────────────────');
  const provider = await getWorkingProvider();

  // 2. Latest block
  try {
    const block = await provider.getBlockWithTxHashes('latest');
    console.log(`  Latest block : ${'block_number' in block ? block.block_number : 'pending'}`);
    console.log(`  Block hash   : ${'block_hash' in block ? String(block.block_hash).slice(0, 18) + '...' : 'N/A'}`);
  } catch (e) {
    console.warn('  Could not fetch block:', (e as Error).message);
  }

  // 3. Account
  console.log('\n── Account ───────────────────────────────────────────────');
  const account = getAccount(provider);
  await printAccountInfo(account, provider);

  // 4. Deployed contracts
  console.log('\n── Deployed Contracts ────────────────────────────────────');
  if (STARKNET_CONFIG.contracts.TRIONOracle) {
    console.log(`  TRIONOracle     : ${STARKNET_CONFIG.contracts.TRIONOracle}`);
    console.log(`    Voyager       : ${STARKNET_CONFIG.explorer.voyager}/contract/${STARKNET_CONFIG.contracts.TRIONOracle}`);
  } else {
    console.log('  TRIONOracle     : not yet deployed (run deploy.ts)');
  }
  if (STARKNET_CONFIG.contracts.BEOAttestation) {
    console.log(`  BEOAttestation  : ${STARKNET_CONFIG.contracts.BEOAttestation}`);
  } else {
    console.log('  BEOAttestation  : not yet deployed (run deploy.ts)');
  }

  // 5. TRION services
  await checkTrionServices();

  console.log('\n═══════════════════════════════════════════════════════════');
  console.log('   Verification complete');
  console.log('═══════════════════════════════════════════════════════════\n');
}

main().catch(e => {
  console.error('\n✗ Verification failed:', e.message);
  process.exit(1);
});
