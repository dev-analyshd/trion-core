/**
 * TRION Protocol — Starknet Sepolia Contract Verification
 * =======================================================
 * Reads back the on-chain state of all 7 deployed contracts
 * to verify they are correctly deployed and functioning.
 *
 * For each contract, we:
 *   1. Check the class hash matches deployment record
 *   2. Call read functions to verify storage state
 *   3. Verify access control parameters (owner/relayer)
 *   4. Check counters and key state variables
 *
 * Run: npx tsx src/verify-all.ts
 */
import 'dotenv/config';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { RpcProvider, CallData } from 'starknet';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Load deployment record
const SN = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'starknet_sepolia_deployments.json'), 'utf-8'));
function addr(name) { return SN.contracts.find(c => c.name === name).address; }
function classHash(name) { return SN.contracts.find(c => c.name === name).classHash; }

const provider = new RpcProvider({ nodeUrl: 'https://starknet-sepolia-rpc.publicnode.com' });

const results = {
  network: 'starknet-sepolia',
  chainId: 'SN_SEPOLIA',
  verifiedAt: new Date().toISOString(),
  contracts: [],
  summary: { total: 0, verified: 0, failed: 0 },
};

async function call(contractAddress, entrypoint, calldata = []) {
  try {
    const res = await provider.callContract({ contractAddress, entrypoint, calldata });
    return { success: true, result: res };
  } catch (e) {
    return { success: false, error: e.message.slice(0, 150) };
  }
}

async function getClassHashAt(address) {
  try {
    const ch = await provider.getClassHashAt(address);
    return { success: true, classHash: ch };
  } catch (e) {
    return { success: false, error: e.message.slice(0, 150) };
  }
}

async function getNonce(address) {
  try {
    const n = await provider.getNonceForAddress(address);
    return { success: true, nonce: n };
  } catch (e) {
    return { success: false, error: e.message.slice(0, 100) };
  }
}

async function main() {
  console.log('═══════════════════════════════════════════════════════════');
  console.log('  TRION Protocol — Starknet Sepolia Contract Verification ');
  console.log('  7 contracts · full on-chain state read-back           ');
  console.log('═══════════════════════════════════════════════════════════\n');

  // Get chain info
  const chainId = await provider.getChainId();
  const blockNum = await provider.getBlockNumber();
  console.log(`  Network: Starknet Sepolia (${chainId})`);
  console.log(`  Latest block: ${blockNum}\n`);

  const deployerExpected = '0x7cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';

  // ═══════════════════════════════════════════════════════════
  // 1. TRIONOracle
  // ═══════════════════════════════════════════════════════════
  console.log('── 1. TRIONOracle ────────────────────────────────────────');
  const oracleAddr = addr('TRIONOracle');
  const oracleCH = classHash('TRIONOracle');
  {
    const onChainCH = await getClassHashAt(oracleAddr);
    const owner = await call(oracleAddr, 'get_owner');
    const scoreCount = await call(oracleAddr, 'get_score_count');
    const nonce = await getNonce(oracleAddr);

    console.log(`  Address:     ${oracleAddr}`);
    console.log(`  Class Hash:  ${oracleCH}`);
    console.log(`  On-chain CH: ${onChainCH.success ? onChainCH.classHash : 'ERROR: ' + onChainCH.error}`);
    console.log(`  CH Match:    ${onChainCH.success && onChainCH.classHash === oracleCH ? '✅ YES' : '❌ MISMATCH'}`);
    console.log(`  get_owner:   ${owner.success ? owner.result[0] : '❌ ' + owner.error}`);
    console.log(`  Owner Match: ${owner.success && owner.result[0] === deployerExpected ? '✅ YES (deployer)' : '⚠ check'}`);
    console.log(`  score_count: ${scoreCount.success ? scoreCount.result[0] : '❌ ' + scoreCount.error}`);
    console.log(`  Nonce:       ${nonce.success ? nonce.nonce : 'N/A (no account)'}`);

    const checks = [
      { name: 'Contract deployed (class hash exists)', pass: onChainCH.success },
      { name: 'Class hash matches deployment record', pass: onChainCH.success && onChainCH.classHash === oracleCH },
      { name: 'Owner is deployer', pass: owner.success && owner.result[0] === deployerExpected },
      { name: 'get_score_count callable', pass: scoreCount.success },
    ];
    const passed = checks.filter(c => c.pass).length;
    results.contracts.push({ name: 'TRIONOracle', address: oracleAddr, classHash: oracleCH, onChainClassHash: onChainCH.classHash, checks, passed: `${passed}/${checks.length}` });
    results.summary.total += checks.length;
    results.summary.verified += passed;
    results.summary.failed += checks.length - passed;
  }

  // ═══════════════════════════════════════════════════════════
  // 2. BEOAttestation
  // ═══════════════════════════════════════════════════════════
  console.log('\n── 2. BEOAttestation ─────────────────────────────────────');
  const beoAddr = addr('BEOAttestation');
  const beoCH = classHash('BEOAttestation');
  {
    const onChainCH = await getClassHashAt(beoAddr);
    const attester = await call(beoAddr, 'get_attester');
    const total = await call(beoAddr, 'total_attestations');

    console.log(`  Address:     ${beoAddr}`);
    console.log(`  Class Hash:  ${beoCH}`);
    console.log(`  On-chain CH: ${onChainCH.success ? onChainCH.classHash : 'ERROR'}`);
    console.log(`  CH Match:    ${onChainCH.success && onChainCH.classHash === beoCH ? '✅ YES' : '❌ MISMATCH'}`);
    console.log(`  get_attester: ${attester.success ? attester.result[0] : '❌'}`);
    console.log(`  Attester Match: ${attester.success && attester.result[0] === deployerExpected ? '✅ YES (deployer)' : '⚠'}`);
    console.log(`  total_attestations: ${total.success ? total.result[0] : '❌'}`);

    const checks = [
      { name: 'Contract deployed', pass: onChainCH.success },
      { name: 'Class hash matches', pass: onChainCH.success && onChainCH.classHash === beoCH },
      { name: 'Attester is deployer', pass: attester.success && attester.result[0] === deployerExpected },
      { name: 'total_attestations callable', pass: total.success },
    ];
    const passed = checks.filter(c => c.pass).length;
    results.contracts.push({ name: 'BEOAttestation', address: beoAddr, classHash: beoCH, checks, passed: `${passed}/${checks.length}` });
    results.summary.total += checks.length;
    results.summary.verified += passed;
    results.summary.failed += checks.length - passed;
  }

  // ═══════════════════════════════════════════════════════════
  // 3. BTCFiGuard
  // ═══════════════════════════════════════════════════════════
  console.log('\n── 3. BTCFiGuard ─────────────────────────────────────────');
  const btcfiAddr = addr('BTCFiGuard');
  const btcfiCH = classHash('BTCFiGuard');
  {
    const onChainCH = await getClassHashAt(btcfiAddr);
    const owner = await call(btcfiAddr, 'get_owner');
    const oracle = await call(btcfiAddr, 'get_oracle');
    const threshold = await call(btcfiAddr, 'get_safe_threshold');

    console.log(`  Address:     ${btcfiAddr}`);
    console.log(`  Class Hash:  ${btcfiCH}`);
    console.log(`  On-chain CH: ${onChainCH.success ? onChainCH.classHash : 'ERROR'}`);
    console.log(`  CH Match:    ${onChainCH.success && onChainCH.classHash === btcfiCH ? '✅ YES' : '❌ MISMATCH'}`);
    console.log(`  get_owner:   ${owner.success ? owner.result[0] : '❌'}`);
    console.log(`  get_oracle:  ${oracle.success ? oracle.result[0] : '❌'}`);
    console.log(`  Oracle Link: ${oracle.success && oracle.result[0] === oracleAddr ? '✅ Points to TRIONOracle' : '⚠'}`);
    console.log(`  get_safe_threshold: ${threshold.success ? threshold.result[0] + ' (1=CAUTION)' : '❌'}`);

    const checks = [
      { name: 'Contract deployed', pass: onChainCH.success },
      { name: 'Class hash matches', pass: onChainCH.success && onChainCH.classHash === btcfiCH },
      { name: 'Owner is deployer', pass: owner.success && owner.result[0] === deployerExpected },
      { name: 'Oracle linked to TRIONOracle', pass: oracle.success && oracle.result[0] === oracleAddr },
      { name: 'Safe threshold set (CAUTION=1)', pass: threshold.success && threshold.result[0] === '0x1' },
    ];
    const passed = checks.filter(c => c.pass).length;
    results.contracts.push({ name: 'BTCFiGuard', address: btcfiAddr, classHash: btcfiCH, checks, passed: `${passed}/${checks.length}` });
    results.summary.total += checks.length;
    results.summary.verified += passed;
    results.summary.failed += checks.length - passed;
  }

  // ═══════════════════════════════════════════════════════════
  // 4. BTCPIntent
  // ═══════════════════════════════════════════════════════════
  console.log('\n── 4. BTCPIntent ─────────────────────────────────────────');
  const intentAddr = addr('BTCPIntent');
  const intentCH = classHash('BTCPIntent');
  {
    const onChainCH = await getClassHashAt(intentAddr);
    const count = await call(intentAddr, 'intent_count');

    console.log(`  Address:     ${intentAddr}`);
    console.log(`  Class Hash:  ${intentCH}`);
    console.log(`  On-chain CH: ${onChainCH.success ? onChainCH.classHash : 'ERROR'}`);
    console.log(`  CH Match:    ${onChainCH.success && onChainCH.classHash === intentCH ? '✅ YES' : '❌ MISMATCH'}`);
    console.log(`  intent_count: ${count.success ? count.result[0] + ' (' + parseInt(count.result[0], 16) + ' intents registered)' : '❌'}`);

    const checks = [
      { name: 'Contract deployed', pass: onChainCH.success },
      { name: 'Class hash matches', pass: onChainCH.success && onChainCH.classHash === intentCH },
      { name: 'intent_count callable', pass: count.success },
      { name: 'Intents registered (>0)', pass: count.success && parseInt(count.result[0], 16) > 0 },
    ];
    const passed = checks.filter(c => c.pass).length;
    results.contracts.push({ name: 'BTCPIntent', address: intentAddr, classHash: intentCH, intentCount: count.success ? parseInt(count.result[0], 16) : 0, checks, passed: `${passed}/${checks.length}` });
    results.summary.total += checks.length;
    results.summary.verified += passed;
    results.summary.failed += checks.length - passed;
  }

  // ═══════════════════════════════════════════════════════════
  // 5. BTCPRoute
  // ═══════════════════════════════════════════════════════════
  console.log('\n── 5. BTCPRoute ──────────────────────────────────────────');
  const routeAddr = addr('BTCPRoute');
  const routeCH = classHash('BTCPRoute');
  {
    const onChainCH = await getClassHashAt(routeAddr);
    const count = await call(routeAddr, 'route_count');

    console.log(`  Address:     ${routeAddr}`);
    console.log(`  Class Hash:  ${routeCH}`);
    console.log(`  On-chain CH: ${onChainCH.success ? onChainCH.classHash : 'ERROR'}`);
    console.log(`  CH Match:    ${onChainCH.success && onChainCH.classHash === routeCH ? '✅ YES' : '❌ MISMATCH'}`);
    console.log(`  route_count: ${count.success ? count.result[0] + ' (' + parseInt(count.result[0], 16) + ' routes registered)' : '❌'}`);

    const checks = [
      { name: 'Contract deployed', pass: onChainCH.success },
      { name: 'Class hash matches', pass: onChainCH.success && onChainCH.classHash === routeCH },
      { name: 'route_count callable', pass: count.success },
      { name: 'Routes registered (>0)', pass: count.success && parseInt(count.result[0], 16) > 0 },
    ];
    const passed = checks.filter(c => c.pass).length;
    results.contracts.push({ name: 'BTCPRoute', address: routeAddr, classHash: routeCH, routeCount: count.success ? parseInt(count.result[0], 16) : 0, checks, passed: `${passed}/${checks.length}` });
    results.summary.total += checks.length;
    results.summary.verified += passed;
    results.summary.failed += checks.length - passed;
  }

  // ═══════════════════════════════════════════════════════════
  // 6. BTCPEscrow
  // ═══════════════════════════════════════════════════════════
  console.log('\n── 6. BTCPEscrow ──────────────────────────────────────────');
  const escrowAddr = addr('BTCPEscrow');
  const escrowCH = classHash('BTCPEscrow');
  {
    const onChainCH = await getClassHashAt(escrowAddr);
    const count = await call(escrowAddr, 'escrow_count');

    console.log(`  Address:     ${escrowAddr}`);
    console.log(`  Class Hash:  ${escrowCH}`);
    console.log(`  On-chain CH: ${onChainCH.success ? onChainCH.classHash : 'ERROR'}`);
    console.log(`  CH Match:    ${onChainCH.success && onChainCH.classHash === escrowCH ? '✅ YES' : '❌ MISMATCH'}`);
    console.log(`  escrow_count: ${count.success ? count.result[0] + ' (' + parseInt(count.result[0], 16) + ' escrows processed)' : '❌'}`);

    const checks = [
      { name: 'Contract deployed', pass: onChainCH.success },
      { name: 'Class hash matches', pass: onChainCH.success && onChainCH.classHash === escrowCH },
      { name: 'escrow_count callable', pass: count.success },
      { name: 'Escrows processed (>0)', pass: count.success && parseInt(count.result[0], 16) > 0 },
    ];
    const passed = checks.filter(c => c.pass).length;
    results.contracts.push({ name: 'BTCPEscrow', address: escrowAddr, classHash: escrowCH, escrowCount: count.success ? parseInt(count.result[0], 16) : 0, checks, passed: `${passed}/${checks.length}` });
    results.summary.total += checks.length;
    results.summary.verified += passed;
    results.summary.failed += checks.length - passed;
  }

  // ═══════════════════════════════════════════════════════════
  // 7. LiquidityOcean
  // ═══════════════════════════════════════════════════════════
  console.log('\n── 7. LiquidityOcean ─────────────────────────────────────');
  const oceanAddr = addr('LiquidityOcean');
  const oceanCH = classHash('LiquidityOcean');
  {
    const onChainCH = await getClassHashAt(oceanAddr);
    const owner = await call(oceanAddr, 'get_owner');
    const threshold = await call(oceanAddr, 'get_routing_threshold');
    const chainCount = await call(oceanAddr, 'get_chain_count');
    const oceanScore = await call(oceanAddr, 'get_ocean_score');
    const relayer = await call(oceanAddr, 'get_relayer');

    console.log(`  Address:     ${oceanAddr}`);
    console.log(`  Class Hash:  ${oceanCH}`);
    console.log(`  On-chain CH: ${onChainCH.success ? onChainCH.classHash : 'ERROR'}`);
    console.log(`  CH Match:    ${onChainCH.success && onChainCH.classHash === oceanCH ? '✅ YES' : '❌ MISMATCH'}`);
    console.log(`  get_owner:   ${owner.success ? owner.result[0] : '❌'}`);
    console.log(`  Owner Match: ${owner.success && owner.result[0] === deployerExpected ? '✅ YES (deployer)' : '⚠'}`);
    console.log(`  get_relayer: ${relayer.success ? relayer.result[0] : '❌'}`);
    console.log(`  routing_threshold: ${threshold.success ? threshold.result[0] + ' (' + parseInt(threshold.result[0], 16) + ' = 0.' + (parseInt(threshold.result[0], 16)/10000) + '×1e6)' : '❌'}`);
    console.log(`  chain_count: ${chainCount.success ? chainCount.result[0] : '❌'}`);
    console.log(`  ocean_score: ${oceanScore.success ? oceanScore.result[0] : '❌'}`);

    const checks = [
      { name: 'Contract deployed', pass: onChainCH.success },
      { name: 'Class hash matches', pass: onChainCH.success && onChainCH.classHash === oceanCH },
      { name: 'Owner is deployer', pass: owner.success && owner.result[0] === deployerExpected },
      { name: 'Relayer is deployer', pass: relayer.success && relayer.result[0] === deployerExpected },
      { name: 'Routing threshold = 300000 (0.30×1e6, L7.1)', pass: threshold.success && parseInt(threshold.result[0], 16) === 300000 },
      { name: 'get_chain_count callable', pass: chainCount.success },
      { name: 'get_ocean_score callable', pass: oceanScore.success },
    ];
    const passed = checks.filter(c => c.pass).length;
    results.contracts.push({ name: 'LiquidityOcean', address: oceanAddr, classHash: oceanCH, routingThreshold: threshold.success ? parseInt(threshold.result[0], 16) : 0, checks, passed: `${passed}/${checks.length}` });
    results.summary.total += checks.length;
    results.summary.verified += passed;
    results.summary.failed += checks.length - passed;
  }

  // ═══════════════════════════════════════════════════════════
  // SUMMARY
  // ═══════════════════════════════════════════════════════════
  console.log('\n═══════════════════════════════════════════════════════════');
  console.log('  VERIFICATION SUMMARY                                    ');
  console.log('═══════════════════════════════════════════════════════════');
  for (const c of results.contracts) {
    console.log(`  ${c.name.padEnd(18)} ${c.passed.padEnd(8)} ${c.checks.every(x=>x.pass) ? '✅ ALL CHECKS PASS' : '⚠ HAS FAILURES'}`);
  }
  console.log(`\n  Total checks:   ${results.summary.total}`);
  console.log(`  Passed:         ${results.summary.verified}`);
  console.log(`  Failed:         ${results.summary.failed}`);
  console.log(`  Success rate:   ${(results.summary.verified / results.summary.total * 100).toFixed(1)}%`);
  console.log(`  Deployer:       ${deployerExpected}`);
  console.log(`  Block:          ${blockNum}`);
  console.log('═══════════════════════════════════════════════════════════\n');

  // Save verification report
  results.blockNumber = blockNum;
  results.deployer = deployerExpected;
  const reportPath = path.join(__dirname, '..', 'starknet_verification_report.json');
  fs.writeFileSync(reportPath, JSON.stringify(results, null, 2));
  console.log(`  Verification report: ${reportPath}`);

  process.exit(results.summary.failed > 0 ? 1 : 0);
}

main().catch(e => {
  console.error('\n✗ Verification failed:', e.message);
  if (e.stack) console.error(e.stack.split('\n').slice(0, 5).join('\n'));
  process.exit(1);
});
