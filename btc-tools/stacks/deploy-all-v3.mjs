/**
 * deploy-all-v3.mjs — Deploy 10 Clarity contracts (9 TRION protocol contracts
 * + 1 SIP-010 test token) to the Stacks testnet.
 *
 * Each contract name is suffixed with `-v3` (configurable via CONTRACT_SUFFIX)
 * because v1 / v2 names are already taken on chain by previous deploys.
 *
 * Deploy order is the dependency order listed in the TRION task spec:
 *   1. btcspvverifier-v3        ← BTCSPVVerifier.clar
 *   2. btcpversionregistry-v3   ← BTCPVersionRegistry.clar
 *   3. travelrulecompliance-v3  ← TravelRuleCompliance.clar
 *   4. genesiscommitment-v3     ← GenesisCommitment.clar
 *   5. btcpintent-v3            ← BTCPIntent.clar
 *   6. btcproute-v3             ← BTCPRoute.clar
 *   7. btcpescrow-v3            ← BTCPEscrow.clar
 *   8. liquidityocean-v3        ← LiquidityOcean.clar
 *   9. behaviorallimitorder-v3  ← BehavioralLimitOrder.clar
 *  10. triontesttoken-v3        ← trion-test-token.clar  (SIP-010 token, created by Task 4)
 *
 * Output: /home/z/my-project/trion-core/proofs/btcp-zero-bridge/stacks/v3-deployments.json
 *   — JSON array of { name, contractId, txId, status, blockHeight, error? }
 *
 * Run from any cwd; paths are resolved relative to this script.
 * Usage:
 *   node deploy-all-v3.mjs
 *   DEPLOYER_KEY=... CONTRACT_SUFFIX=v3 node deploy-all-v3.mjs
 */
import { fileURLToPath } from 'url';
import * as fs from 'fs';
import * as path from 'path';

import txPkg from '@stacks/transactions';
const { makeContractDeploy, broadcastTransaction, getAddressFromPrivateKey } = txPkg;

import { API, network, getNonce, getBalance, waitForTx, sleep } from './lib/helpers.mjs';

// ----------------------------------------------------------------------------- config
const DEPLOYER_KEY =
  process.env.DEPLOYER_KEY ||
  '940806a0a98e86df44835d7fb5d58a79d6259f413550ba11a858880a72e2e71901';
const CONTRACT_SUFFIX = process.env.CONTRACT_SUFFIX || 'v3';
const FEE = 100000; // 0.1 STX per deploy (microSTX)

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, '..', '..');
const CONTRACTS_DIR =
  process.env.CONTRACTS_DIR || path.resolve(REPO_ROOT, 'contracts', 'clarity');
const PROOFS_FILE =
  process.env.PROOFS_FILE ||
  path.resolve(REPO_ROOT, 'proofs', 'btcp-zero-bridge', 'stacks', 'v3-deployments.json');

const DEPLOYER_ADDR = getAddressFromPrivateKey(DEPLOYER_KEY, 'testnet');

// ----------------------------------------------------------------------------- contracts
const CONTRACTS = [
  { name: 'btcspvverifier',       file: 'BTCSPVVerifier.clar' },
  { name: 'btcpversionregistry',  file: 'BTCPVersionRegistry.clar' },
  { name: 'travelrulecompliance', file: 'TravelRuleCompliance.clar' },
  { name: 'genesiscommitment',    file: 'GenesisCommitment.clar' },
  { name: 'btcpintent',           file: 'BTCPIntent.clar' },
  { name: 'btcproute',            file: 'BTCPRoute.clar' },
  { name: 'btcpescrow',           file: 'BTCPEscrow.clar' },
  { name: 'liquidityocean',       file: 'LiquidityOcean.clar' },
  { name: 'behaviorallimitorder', file: 'BehavioralLimitOrder.clar' },
  { name: 'triontesttoken',       file: 'trion-test-token.clar' }, // SIP-010 token (Task 4)
];

// ----------------------------------------------------------------------------- deploy
async function deployContract(name, source) {
  const nonce = await getNonce(DEPLOYER_ADDR);
  console.log(`  [nonce=${nonce}] deploying ${name} (${source.length} bytes)...`);
  try {
    const tx = await makeContractDeploy({
      contractName: name,
      codeBody: source,
      senderKey: DEPLOYER_KEY,
      network,
      fee: FEE,
      nonce: BigInt(nonce),
    });
    const resp = await broadcastTransaction({ transaction: tx, network });
    if (!resp || !resp.txid) {
      const err = resp ? JSON.stringify(resp).slice(0, 200) : 'no broadcast response';
      console.log(`    ✗ broadcast_failed: ${err}`);
      return {
        name,
        contractId: `${DEPLOYER_ADDR}.${name}`,
        status: 'failed',
        error: `broadcast_failed: ${err}`,
      };
    }
    const txId = `0x${resp.txid}`;
    console.log(`    broadcast: ${txId}`);
    const result = await waitForTx(txId, 180000);
    if (result.ok) {
      const blockHeight = result.info?.block_height ?? null;
      console.log(`    ✓ SUCCESS at block ${blockHeight}`);
      return {
        name,
        contractId: `${DEPLOYER_ADDR}.${name}`,
        txId,
        status: 'deployed',
        blockHeight,
      };
    }
    // Failed: abort_by_response / abort_by_post_condition / timeout
    const raw =
      result.info?.raw_result || result.error || result.info?.tx_status || 'unknown';
    console.log(`    ✗ FAILED: ${String(raw).slice(0, 300)}`);
    if (result.info?.raw_result) {
      console.log(`    raw_result: ${String(result.info.raw_result).slice(0, 300)}`);
    }
    return {
      name,
      contractId: `${DEPLOYER_ADDR}.${name}`,
      txId,
      status: 'failed',
      error: String(raw).slice(0, 300),
      blockHeight: result.info?.block_height ?? null,
    };
  } catch (e) {
    const msg = (e && e.message) ? e.message : String(e);
    console.log(`    ERR: ${msg.slice(0, 300)}`);
    return {
      name,
      contractId: `${DEPLOYER_ADDR}.${name}`,
      status: 'failed',
      error: msg.slice(0, 300),
    };
  }
}

// ----------------------------------------------------------------------------- main
async function main() {
  console.log('=== deploy-all-v3.mjs — Stacks testnet deploy ===');
  console.log(`API:         ${API}`);
  console.log(`Deployer:    ${DEPLOYER_ADDR}`);
  const balance = await getBalance(DEPLOYER_ADDR);
  console.log(
    `Balance:     ${balance} microSTX (${(balance / 1e6).toFixed(6)} STX)`
  );
  const startNonce = await getNonce(DEPLOYER_ADDR);
  console.log(`Nonce:       ${startNonce}`);
  console.log(`Suffix:      -${CONTRACT_SUFFIX}`);
  console.log(`Fee:         ${FEE} microSTX (0.1 STX) per deploy`);
  console.log(`Sources dir: ${CONTRACTS_DIR}`);
  console.log(`Proofs file: ${PROOFS_FILE}`);
  console.log(`Contracts:   ${CONTRACTS.length} (in dependency order)`);
  console.log('');

  const deployments = [];
  for (const c of CONTRACTS) {
    const contractName = `${c.name}-${CONTRACT_SUFFIX}`;
    const sourcePath = path.join(CONTRACTS_DIR, c.file);
    console.log(`\n--- ${contractName}  ←  ${c.file} ---`);

    if (!fs.existsSync(sourcePath)) {
      const msg = `source not found: ${sourcePath}`;
      console.log(`  ✗ ${msg}`);
      deployments.push({
        name: contractName,
        contractId: `${DEPLOYER_ADDR}.${contractName}`,
        status: 'failed',
        error: msg,
      });
      continue; // don't break — continue to next contract
    }

    const source = fs.readFileSync(sourcePath, 'utf-8');
    const result = await deployContract(contractName, source);
    deployments.push(result);

    // small pacing between deploys; do not break on failure
    await sleep(2000);
  }

  // ----------------------------------------------------------------- write proofs
  fs.mkdirSync(path.dirname(PROOFS_FILE), { recursive: true });
  fs.writeFileSync(PROOFS_FILE, JSON.stringify(deployments, null, 2));

  // ----------------------------------------------------------------- summary
  const ok = deployments.filter(d => d.status === 'deployed').length;
  const fail = deployments.length - ok;
  console.log('\n=== Summary ===');
  console.log(`Deployed: ${ok}/${deployments.length}    Failed: ${fail}`);
  console.log(`Results saved to: ${PROOFS_FILE}`);
  console.log('');
  console.log(JSON.stringify(deployments, null, 2));
}

main().catch(e => {
  console.error('FATAL:', e);
  process.exit(1);
});
