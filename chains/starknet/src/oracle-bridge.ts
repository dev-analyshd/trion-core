/**
 * TRION Oracle Bridge
 * Run: pnpm --filter @workspace/starknet-trion bridge
 *
 * Continuously polls the TRION FAISS service for top active entities,
 * converts their scores to on-chain format, and pushes them to the
 * TRIONOracle contract on Starknet Sepolia.
 *
 * Score encoding:
 *   anima_score         → multiply by 10000, round to u64
 *   genesis_confidence  → multiply by 10000, round to u64
 *   akashic_depth       → integer part only, as u64
 *   trajectory_alert    → 0=CLEAR, 1=WARN, 2=MANIPULATION
 *   dormancy_type       → felt252 encoded short string
 */
import 'dotenv/config';
import axios from 'axios';
import { Contract, shortString, Provider } from 'starknet';
import { getWorkingProvider, getAccount } from './provider.js';
import { STARKNET_CONFIG, TRAJECTORY_ALERT } from './config.js';
import { TRION_ORACLE_ABI } from './abi/TRIONOracle.js';

const POLL_INTERVAL_MS = 60_000;
const KNOWN_ENTITIES   = [
  'NETWORK',
  '0x0000000000000000000000000000000000000001',
];

interface FAISSTrajectory {
  entity_id: string;
  alert: string;
  kl_divergence: number | null;
  archetype_id: number;
  genesis_locked: boolean;
  status: string;
}

interface FAISSResurrection {
  entity_id: string;
  beo_id: string;
  dormancy_type: string;
  is_resurrection: boolean;
  delta_score: number;
  confidence: number;
  status: string;
}

function encodeTrajectoryAlert(alert: string): number {
  if (alert === 'MANIPULATION_ALERT') return TRAJECTORY_ALERT.MANIPULATION;
  if (alert === 'WARN')               return TRAJECTORY_ALERT.WARN;
  return TRAJECTORY_ALERT.CLEAR;
}

function encodeDormancyType(dt: string): bigint {
  const safe = (dt ?? 'UNKNOWN').slice(0, 31);
  return BigInt(shortString.encodeShortString(safe));
}

function scaleScore(val: number | null | undefined, scale = 10000): bigint {
  if (val === null || val === undefined || isNaN(val)) return 0n;
  return BigInt(Math.round(Math.min(1, Math.max(0, val)) * scale));
}

async function fetchEntityScores(entityId: string) {
  const faissBase = STARKNET_CONFIG.trion.faissBaseUrl;

  const [trajRes, resRes] = await Promise.allSettled([
    axios.get<FAISSTrajectory>(`${faissBase}/api/v1/trajectory_anomaly/${entityId}`, { timeout: 8000 }),
    axios.get<FAISSResurrection>(`${faissBase}/api/v1/resurrection_status/${entityId}`, { timeout: 8000 }),
  ]);

  const traj = trajRes.status === 'fulfilled' ? trajRes.value.data : null;
  const res  = resRes.status  === 'fulfilled' ? resRes.value.data  : null;

  return { traj, res };
}

async function pushScore(
  contract: Contract,
  entityId: string,
  beoId: string,
  traj: FAISSTrajectory | null,
  res: FAISSResurrection | null,
) {
  const animaScore        = scaleScore(res?.confidence);
  const genesisConfidence = scaleScore(res?.delta_score);
  const trajectoryAlert   = encodeTrajectoryAlert(traj?.alert ?? 'CLEAR');
  const archetypeId       = BigInt(Math.max(0, Math.min(63, traj?.archetype_id ?? 0)));
  const akashicDepth      = scaleScore(res?.delta_score ?? 0, 1);
  const isResurrection    = res?.is_resurrection ?? false;
  const dormancyType      = encodeDormancyType(res?.dormancy_type ?? 'UNKNOWN');

  const beoBigInt = BigInt('0x' + beoId.slice(0, 31));

  console.log(`  Pushing score for ${entityId}:`);
  console.log(`    BEO:          0x${beoId.slice(0, 16)}...`);
  console.log(`    ANIMA:        ${animaScore} / 10000`);
  console.log(`    Genesis Conf: ${genesisConfidence} / 10000`);
  console.log(`    Alert:        ${trajectoryAlert} (${traj?.alert ?? 'CLEAR'})`);
  console.log(`    Archetype:    #${archetypeId}`);
  console.log(`    Resurrection: ${isResurrection}`);

  const tx = await contract.update_score(
    beoBigInt,
    animaScore,
    genesisConfidence,
    trajectoryAlert,
    archetypeId,
    akashicDepth,
    isResurrection,
    dormancyType,
  );

  console.log(`    ✓ Tx: ${tx.transaction_hash}`);
  console.log(`      ${STARKNET_CONFIG.explorer.voyager}/tx/${tx.transaction_hash}`);

  const provider = contract.providerOrAccount as Provider;
  if (provider && typeof (provider as any).waitForTransaction === 'function') {
    process.stdout.write('    Waiting for tx acceptance...');
    await (provider as any).waitForTransaction(tx.transaction_hash, { retryInterval: 3000 });
    process.stdout.write(' confirmed.\n');
  }
  return tx;
}

async function runBridgeCycle(contract: Contract) {
  console.log(`\n[${new Date().toISOString()}] Running bridge cycle — ${KNOWN_ENTITIES.length} entities`);

  for (const entityId of KNOWN_ENTITIES) {
    try {
      const { traj, res } = await fetchEntityScores(entityId);

      if (!res?.beo_id) {
        console.log(`  Skipping ${entityId}: no BEO ID`);
        continue;
      }

      await pushScore(contract, entityId, res.beo_id, traj, res);
    } catch (e) {
      console.error(`  ✗ Failed to push ${entityId}:`, (e as Error).message);
    }
  }
}

async function main() {
  console.log('═══════════════════════════════════════════════════════════');
  console.log('   TRION Oracle Bridge — Starknet Sepolia                  ');
  console.log('═══════════════════════════════════════════════════════════\n');

  const oracleAddress = STARKNET_CONFIG.contracts.TRIONOracle;
  if (!oracleAddress) {
    throw new Error(
      'TRION_ORACLE_ADDRESS not set.\n' +
      'Run deploy.ts first, then set the address as a Replit Secret.'
    );
  }

  const provider = await getWorkingProvider();
  const account  = getAccount(provider);

  console.log(`Oracle contract: ${oracleAddress}`);
  console.log(`Pusher account:  ${account.address}\n`);

  const contract = new Contract({ abi: TRION_ORACLE_ABI, address: oracleAddress, providerOrAccount: account });

  console.log('Checking current score count...');
  try {
    const count = await contract.get_score_count();
    console.log(`Scores on-chain: ${count}`);
  } catch (e) {
    console.warn('Could not read score count:', (e as Error).message);
  }

  await runBridgeCycle(contract);

  console.log(`\nStarting polling loop (every ${POLL_INTERVAL_MS / 1000}s)...`);
  setInterval(() => runBridgeCycle(contract), POLL_INTERVAL_MS);
}

main().catch(e => {
  console.error('\n✗ Bridge failed:', e.message);
  console.error(e.stack);
  process.exit(1);
});
