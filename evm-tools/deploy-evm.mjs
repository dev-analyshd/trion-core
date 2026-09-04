// Deploy TRION BTCP contracts on EVM Base Sepolia.
//
// S3/C2 fix — consensus-gated escrow BY DEFAULT:
//   1. TRIONOracleV3 is deployed FIRST (the deployer/relayer is auto-registered
//      as bootstrap validator #1); additional validators are registered from
//      VALIDATOR_ADDRESSES (comma-separated) — route verdicts need
//      N = max(2, ceil(2/3 · validatorCount)) distinct ECDSA attestations.
//   2. BTCPEscrow is deployed and BOUND to the oracle via setTRIONOracle()
//      in the same flow — releases then require the oracle's
//      signature-quorum route verdict (submitRouteAttestation), not the
//      relayer's word alone. Binding is one-way (cannot be undone on-chain).
//   3. TRUSTED_RELAYER_MODE=1 skips the binding — LOCAL DEV ONLY (escrow
//      releases then trust the relayer-supplied coherence; see BTCPEscrow
//      natspec "TRUSTED-RELAYER MODE").
//
// Env: EVM_PRIVATE_KEY | PRIVATE_KEY (deployer/relayer), VALIDATOR_ADDRESSES
//      (extra validator addresses, csv), TRUSTED_RELAYER_MODE=1 (skip bind).
import fs from 'fs';
import path from 'path';
import { ethers } from 'ethers';
import { fileURLToPath } from 'url';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const COMPILED = path.join(__dirname, 'compiled');
const PK = process.env.EVM_PRIVATE_KEY || process.env.PRIVATE_KEY;
const RPC = 'https://base-sepolia-rpc.publicnode.com';
const CHAIN_ID = 84532;
const TRUSTED_RELAYER_MODE = process.env.TRUSTED_RELAYER_MODE === '1';
const provider = new ethers.JsonRpcProvider(RPC, CHAIN_ID, { staticNetwork: true });
const wallet = new ethers.Wallet(PK, provider);
function loadArt(name) { return JSON.parse(fs.readFileSync(path.join(COMPILED, `${name}.json`), 'utf-8')); }
async function deploy(name) {
  const art = loadArt(name);
  const factory = new ethers.ContractFactory(art.abi, art.bytecode, wallet);
  const c = await factory.deploy();
  await c.waitForDeployment();
  return await c.getAddress();
}
async function main() {
  console.log('═══ TRION × EVM Base Sepolia — BTCP Contract Deploy ═══');
  console.log(`  Deployer/Relayer: ${wallet.address}`);
  console.log(`  Balance:  ${ethers.formatEther(await provider.getBalance(wallet.address))} ETH\n`);
  const results = [];

  // ── 1) Consensus oracle (S3/C2): deployer is bootstrap validator #1 ──────
  const oracleAddr = await deploy('TRIONOracleV3');
  const oracle = new ethers.Contract(oracleAddr, loadArt('TRIONOracleV3').abi, wallet);
  console.log(`  ✓ TRIONOracleV3: ${oracleAddr}`);
  results.push({ name: 'TRIONOracleV3@BaseSepolia', address: oracleAddr });

  // Register additional validators from env (owner-gated, event-logged).
  const extraValidators = (process.env.VALIDATOR_ADDRESSES || '')
    .split(',').map(s => s.trim()).filter(s => s.length > 0);
  for (const v of extraValidators) {
    await oracle.addValidator(v);
    console.log(`  ✓ validator registered: ${v}`);
  }
  const validatorCount = await oracle.validatorCount();
  const minRouteAttestations = await oracle.minRouteAttestations();
  console.log(`  · validators=${validatorCount} → route quorum N=${minRouteAttestations} (max(2, ⌈2/3·N⌉))`);
  if (validatorCount < 2) {
    console.warn('  ⚠ WARNING: fewer than 2 validators registered — route verdicts can NEVER');
    console.warn('    reach quorum, so bound escrows FAIL CLOSED (no consensus release; the');
    console.warn('    timeout/emergency revert paths remain). Set VALIDATOR_ADDRESSES=a,b,c');
    console.warn('    for a real deployment.');
  }

  // ── 2) Escrow, bound to the oracle by default (S3/C2) ────────────────────
  const escrowAddr = await deploy('BTCPEscrow');
  const escrow = new ethers.Contract(escrowAddr, loadArt('BTCPEscrow').abi, wallet);
  console.log(`  ✓ BTCPEscrow: ${escrowAddr}`);
  results.push({ name: 'BTCPEscrow@BaseSepolia', address: escrowAddr });
  if (!TRUSTED_RELAYER_MODE) {
    await escrow.setTRIONOracle(oracleAddr); // one-way bind — consensus-gated release
    console.log(`  ✓ escrow BOUND to oracle ${oracleAddr} (signature-quorum release)`);
    results.push({ name: 'BTCPEscrowOracleBinding@BaseSepolia', escrow: escrowAddr, oracle: oracleAddr, mode: 'consensus-gated' });
  } else {
    console.warn('  ⚠ TRUSTED_RELAYER_MODE=1 — escrow NOT bound to the oracle.');
    console.warn('    Trusted-relayer mode is for LOCAL DEV ONLY (DD S3/C2).');
    results.push({ name: 'BTCPEscrowOracleBinding@BaseSepolia', escrow: escrowAddr, mode: 'trusted-relayer (dev only)' });
  }

  // ── 3) Remaining BTCP contracts (unchanged flow) ──────────────────────────
  for (const name of ['BTCPIntent', 'BTCPRoute', 'LiquidityOcean']) {
    const addr = await deploy(name);
    console.log(`  ✓ ${name}: ${addr}`);
    results.push({ name: `${name}@BaseSepolia`, address: addr });
  }

  const record = {
    network: 'evm-sepolia-multi-chain',
    deployer: wallet.address,
    trionOracle: oracleAddr,
    escrowOracleBinding: TRUSTED_RELAYER_MODE ? 'none (trusted-relayer dev mode)' : oracleAddr,
    contracts: results,
  };
  fs.writeFileSync(path.join(__dirname, 'evm_sepolia_deployments.json'), JSON.stringify(record, null, 2));
  console.log('\n  ✅ Deployment complete — escrow releases require validator');
  console.log('     signature quorum (submitRouteAttestation) unless TRUSTED_RELAYER_MODE=1.');
}
main().catch(e => { console.error('✗', e.message); process.exit(1); });
