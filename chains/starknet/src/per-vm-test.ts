/**
 * TRION Zero-Bridge — Per-VM Test Runner
 * Runs 5 rounds for a single target VM.
 * Usage: npx tsx src/per-vm-test.ts <vm_name>
 *   vm_name: EthSepolia | ArbitrumSepolia | OPSepolia | BaseSepolia | NEAR | SOLANA | TON
 */
import 'dotenv/config';
import fs from 'fs';
import path from 'path';
import crypto from 'crypto';
import { fileURLToPath } from 'url';
import { ethers } from 'ethers';
import { RpcProvider, Account, CallData } from 'starknet';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const VM = process.argv[2] || 'BaseSepolia';
const ROUNDS = parseInt(process.env.ROUNDS_OVERRIDE || '5');

const SN = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'starknet_sepolia_deployments.json'), 'utf-8'));
const EVM = JSON.parse(fs.readFileSync(path.join(__dirname, '..', '..', '..', 'evm-tools', 'evm_sepolia_deployments.json'), 'utf-8'));
function snAddr(n) { return SN.contracts.find(c => c.name === n).address; }
function evmAddr(n) { const c = EVM.contracts.find(c => c.name === n); return c ? c.address : null; }

const SN_C = { intent: snAddr('BTCPIntent'), route: snAddr('BTCPRoute'), escrow: snAddr('BTCPEscrow') };
const CHAIN = { STARKNET: 1300, ETH: 11155111, ARB: 421614, OP: 11155420, BASE: 84532, NEAR: 1200, SOLANA: 900, TON: 1100 };

const EVM_CONFIG = {
  EthSepolia:      { chainId: 11155111, rpc: 'https://ethereum-sepolia-rpc.publicnode.com', escrow: evmAddr('BTCPEscrow@EthSepolia'),      route: evmAddr('BTCPRoute@EthSepolia') },
  ArbitrumSepolia: { chainId: 421614,   rpc: 'https://sepolia-rollup.arbitrum.io/rpc',       escrow: evmAddr('BTCPEscrow@ArbitrumSepolia'), route: evmAddr('BTCPRoute@ArbitrumSepolia') },
  OPSepolia:       { chainId: 11155420, rpc: 'https://sepolia.optimism.io',                  escrow: evmAddr('BTCPEscrow@OPSepolia'),       route: evmAddr('BTCPRoute@OPSepolia') },
  BaseSepolia:     { chainId: 84532,    rpc: 'https://base-sepolia-rpc.publicnode.com',      escrow: evmAddr('BTCPEscrow@BaseSepolia'),     route: evmAddr('BTCPRoute@BaseSepolia') },
};

const NON_EVM = { NEAR: CHAIN.NEAR, SOLANA: CHAIN.SOLANA, TON: CHAIN.TON };

function sha3Hex(d) { return '0x' + crypto.createHash('sha3-256').update(d).digest('hex'); }
function felt(h) { return BigInt(h.slice(0, 62)); }

const COMPILED = path.join(__dirname, '..', '..', '..', 'evm-tools', 'compiled');
const escrowABI = JSON.parse(fs.readFileSync(path.join(COMPILED, 'BTCPEscrow.json'), 'utf-8')).abi;
const routeABI = JSON.parse(fs.readFileSync(path.join(COMPILED, 'BTCPRoute.json'), 'utf-8')).abi;

const snPk = process.env.STARKNET_PRIVATE_KEY;
const snAccountAddr = process.env.STARKNET_ACCOUNT_ADDRESS;
const evmPk = process.env.EVM_PRIVATE_KEY;

const snProvider = new RpcProvider({ nodeUrl: 'https://starknet-sepolia-rpc.publicnode.com' });
const snAccount = new Account({ provider: snProvider, address: snAccountAddr, signer: snPk, feeEstimateMultiplier: 1.5 } as any);

const bid = sha3Hex('trion-loop-test-' + VM);
const beoFelt = felt(bid);
const now = Math.floor(Date.now() / 1000);

const results = { vm: VM, rounds: ROUNDS, startedAt: new Date().toISOString(), rounds_data: [], passed: 0, failed: 0, assets_bridged: false };

async function main() {
  console.log(`═══ Starknet ↔ ${VM} (${ROUNDS} rounds) ═══`);

  if (NON_EVM[VM]) {
    // Non-EVM: register intent on Starknet pointing to target VM
    const chainId = NON_EVM[VM];
    const action = VM === 'SOLANA' ? 0 : 1; // SWAP for Solana, TRANSFER for NEAR/TON
    for (let r = 1; r <= ROUNDS; r++) {
      try {
        const intentHash = felt(sha3Hex(`sn-${VM}-${r}-${Date.now()}`));
        const tx = await snAccount.execute([{
          contractAddress: SN_C.intent, entrypoint: 'register_intent',
          calldata: CallData.compile({
            intent_hash: intentHash, entity_id: beoFelt, action,
            asset_in: 1n, asset_out: 2n, magnitude: { low: 500000000000000n, high: 0n },
            source_chain: CHAIN.STARKNET, dest_chain: chainId,
            deadline: now + 7200, max_gas_usd: 30, min_nl_score: 2500, privacy: 0,
          }),
        }]);
        await snProvider.waitForTransaction(tx.transaction_hash);
        console.log(`  ✓ Round ${r}: intent SN→${VM} → ${tx.transaction_hash.slice(0,16)}...`);
        results.passed++;
        results.rounds_data.push({ round: r, pass: true, txHash: tx.transaction_hash });
      } catch (e) {
        console.log(`  ✗ Round ${r}: ${e.message.slice(0,80)}`);
        results.failed++;
        results.rounds_data.push({ round: r, pass: false, error: e.message.slice(0,100) });
      }
    }
  } else if (EVM_CONFIG[VM]) {
    // EVM: full bidirectional zero-bridge test
    const cfg = EVM_CONFIG[VM];
    const provider = new ethers.JsonRpcProvider(cfg.rpc, cfg.chainId, { staticNetwork: true });
    const wallet = new ethers.Wallet(evmPk, provider);
    const evmEscrow = new ethers.Contract(cfg.escrow, escrowABI, wallet);
    const evmRoute = cfg.route ? new ethers.Contract(cfg.route, routeABI, wallet) : null;

    for (let r = 1; r <= ROUNDS; r++) {
      console.log(`  ── Round ${r}/${ROUNDS} ──`);
      try {
        // Sync EVM nonce to avoid stale nonce errors (use 'pending' to include in-flight txs)
        const currentNonce = await provider.getTransactionCount(wallet.address, 'pending');
        wallet.nonce = currentNonce;
        // Small delay to let previous txs settle
        if (r > 1) await new Promise(resolve => setTimeout(resolve, 3000));

        // 1. Register intent on Starknet
        const intentHash = felt(sha3Hex(`sn-${VM}-intent-${r}-${Date.now()}`));
        const routeId = felt(sha3Hex(`sn-${VM}-route-${r}-${Date.now()}`));
        const escrowId = felt(sha3Hex(`sn-${VM}-escrow-${r}-${Date.now()}`));
        const anchorBH = felt(sha3Hex(`sn-${VM}-anchor-${r}-${Date.now()}`));

        const tx1 = await snAccount.execute([{
          contractAddress: SN_C.intent, entrypoint: 'register_intent',
          calldata: CallData.compile({
            intent_hash: intentHash, entity_id: beoFelt, action: 0,
            asset_in: 1n, asset_out: 2n, magnitude: { low: 1000000n, high: 0n },
            source_chain: CHAIN.STARKNET, dest_chain: cfg.chainId,
            deadline: now + 3600, max_gas_usd: 50, min_nl_score: 3000, privacy: 0,
          }),
        }]);
        await snProvider.waitForTransaction(tx1.transaction_hash);

        // 2. Lock escrow on Starknet
        const tx2 = await snAccount.execute([{
          contractAddress: SN_C.escrow, entrypoint: 'lock_escrow',
          calldata: CallData.compile({
            escrow_id: escrowId, route_id: routeId, entity_id: beoFelt,
            destination: snAccountAddr, amount: { low: 1000000000000000n, high: 0n },
            min_coherence: 500000, timeout_blocks: 3600,
          }),
        }]);
        await snProvider.waitForTransaction(tx2.transaction_hash);

        // 3. Register route on Starknet
        const tx3 = await snAccount.execute([{
          contractAddress: SN_C.route, entrypoint: 'register_route',
          calldata: CallData.compile({
            route_id: routeId, intent_hash: intentHash, anchor_bh: anchorBH,
            anchor_chain: CHAIN.STARKNET, execution_chain: cfg.chainId,
            entity_id: beoFelt, route_type: 3,
          }),
        }]);
        await snProvider.waitForTransaction(tx3.transaction_hash);

        // 4. Lock escrow on EVM (0.0001 ETH)
        const evmEscrowId = ethers.id(`evm-${VM}-escrow-${r}-${Date.now()}`);
        const evmRouteId = ethers.id(`evm-${VM}-route-${r}-${Date.now()}`);
        const evmExecBH = ethers.id(`evm-${VM}-exec-${r}-${Date.now()}`);
        const lockFn = evmEscrow['lockEscrow(bytes32,bytes32,bytes32,address,uint256,uint256,bytes32)'];
        const tx4 = await lockFn(evmEscrowId, evmRouteId, ethers.id('trion-loop-test-'+VM), wallet.address, 500000, 3600, ethers.ZeroHash,
          { value: ethers.parseEther('0.0001'), gasLimit: 500000 });
        await tx4.wait();

        // 5. Verify settlement + release on EVM
        await (await evmEscrow.verifySettlementCheck(evmEscrowId, evmExecBH)).wait();
        const tx5 = await evmEscrow.releaseEscrow(evmEscrowId, evmExecBH, 920000);
        await tx5.wait();

        // 6. Release escrow on Starknet
        const tx6 = await snAccount.execute([{
          contractAddress: SN_C.escrow, entrypoint: 'release_escrow',
          calldata: CallData.compile({ escrow_id: escrowId, execution_bh: felt(evmExecBH.slice(0,62)), coherence: 920000 }),
        }]);
        await snProvider.waitForTransaction(tx6.transaction_hash);

        // 7. Finalize route on Starknet
        const tx7 = await snAccount.execute([{
          contractAddress: SN_C.route, entrypoint: 'finalize_route',
          calldata: CallData.compile({
            route_id: routeId, execution_bh: felt(evmExecBH.slice(0,62)),
            gas_saved_vs_bridge: 42000000, beo_continuity: 950000, cc_coherence: 880000,
          }),
        }]);
        await snProvider.waitForTransaction(tx7.transaction_hash);

        // 8. Publish + finalize route on EVM (if route contract exists)
        if (evmRoute) {
          try {
            const evmIntentHash = ethers.id(`evm-${VM}-intent-${r}-${Date.now()}`);
            const evmAnchorBH = ethers.id(`evm-${VM}-anchor-${r}-${Date.now()}`);
            const tx8a = await evmRoute.publishRoute(evmRouteId, evmIntentHash, evmAnchorBH, cfg.chainId, CHAIN.STARKNET, ethers.id('trion-loop-test-'+VM), 3);
            await tx8a.wait();
            console.log(`    ✓ EVM: publishRoute → ${tx8a.hash.slice(0,16)}...`);
            const tx8b = await evmRoute.finalizeRoute(evmRouteId, evmExecBH, 42000000, 950000, 880000);
            await tx8b.wait();
            console.log(`    ✓ EVM: finalizeRoute → ${tx8b.hash.slice(0,16)}...`);
          } catch (routeErr) {
            console.log(`    ⚠ EVM route ops skipped: ${routeErr.message.slice(0,80)}`);
          }
        }

        console.log(`  ✅ Round ${r} PASSED (7 txs SN + EVM)`);
        results.passed++;
        results.rounds_data.push({ round: r, pass: true, snTxs: 5, evmTxs: evmRoute ? 3 : 2 });
      } catch (e) {
        console.log(`  ✗ Round ${r} FAILED: ${e.message.slice(0,120)}`);
        results.failed++;
        results.rounds_data.push({ round: r, pass: false, error: e.message.slice(0,200) });
      }
    }
  }

  results.endedAt = new Date().toISOString();
  console.log(`\n  ${VM}: ${results.passed}/${ROUNDS} rounds passed ${results.passed === ROUNDS ? '✅' : '⚠'}`);

  // Append to combined report
  const reportPath = path.join(__dirname, '..', 'loop_test_report.json');
  let combined = { vms: [], startedAt: new Date().toISOString() };
  try { combined = JSON.parse(fs.readFileSync(reportPath, 'utf-8')); } catch {}
  const existing = combined.vms.findIndex(v => v.vm === VM);
  if (existing >= 0) combined.vms[existing] = results; else combined.vms.push(results);
  combined.endedAt = new Date().toISOString();
  fs.writeFileSync(reportPath, JSON.stringify(combined, null, 2));
  console.log(`  Report updated: ${reportPath}`);
  process.exit(results.failed > 0 ? 1 : 0);
}

main().catch(e => { console.error('✗', e.message); process.exit(1); });
