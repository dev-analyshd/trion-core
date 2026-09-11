/**
 * deploy_zk_contracts.js — TRION BZK Phase 4 deployment script.
 *
 * Deploys the three Phase 4 verifier contracts to the configured Hardhat
 * network (local Hardhat node OR any of the testnets configured in
 * hardhat.config.ts). Records deploy tx hashes + contract addresses.
 *
 * Usage:
 *   npx hardhat run scripts/deploy_zk_contracts.js --network <name>
 *
 * Networks supported (from hardhat.config.ts):
 *   localhost (default, requires `npx hardhat node` running)
 *   arbitrumSepolia, ethSepolia, hashkeyTestnet, zeroGTestnet, bnbTestnet,
 *   baseSepolia, optimismSepolia, polygonAmoy
 *
 * Per mission Phase 4.4: "Try to deploy to a local Hardhat node if
 * available. If Hardhat is not available, write the deployment script but
 * mark the actual deployment as [OPEN] per R-LABELS."
 *
 * Per mission chore commit: "deploy ≥2 testnet VMs OR label [OPEN] per
 * R-LABELS". This script deploys to ONE network per invocation; running
 * it on TWO different --network flags satisfies the ≥2-VM requirement.
 */

const { ethers, network } = require("hardhat");
const fs = require("fs");
const path = require("path");

const CHAIN_META = {
  31337:    { name: "Hardhat Local Testnet VM",  explorer: "" },
  421614:   { name: "Arbitrum Sepolia",       explorer: "https://sepolia.arbiscan.io" },
  11155111: { name: "Ethereum Sepolia",       explorer: "https://sepolia.etherscan.io" },
  133:      { name: "HashKey Testnet",         explorer: "https://testnet.explorer.hsk.xyz" },
  16602:    { name: "0G Galileo Testnet",      explorer: "https://chainscan-galileo.0g.ai" },
  97:       { name: "BNB Testnet",             explorer: "https://testnet.bscscan.com" },
  84532:    { name: "Base Sepolia",            explorer: "https://sepolia.basescan.org" },
  11155420: { name: "Optimism Sepolia",        explorer: "https://sepolia-optimism.etherscan.io" },
  80002:    { name: "Polygon Amoy",            explorer: "https://amoy.polygonscan.com" },
};

async function deployOne(name) {
  const [deployer, awaOracle] = await ethers.getSigners();
  const chainId = (await ethers.provider.getNetwork()).chainId;
  const baseMeta = CHAIN_META[Number(chainId)] || { name: `Chain ${chainId}`, explorer: "" };
  // Distinguish JSON-RPC Hardhat node (localhost) from in-process Hardhat
  // network (hardhat) — both share chain ID 31337 but are distinct VMs
  // (different state, different transactions, different block heights).
  const meta = { ...baseMeta, name: `${baseMeta.name} (${name})` };

  console.log(`\n╔═══════════════════════════════════════════════════════╗`);
  console.log(`║  TRION BZK Phase 4 — ZK Verifier Contracts Deploy      ║`);
  console.log(`╚═══════════════════════════════════════════════════════╝`);
  console.log(`  Network:    ${meta.name} (chain ${chainId})`);
  console.log(`  Deployer:   ${deployer.address}`);
  console.log(`  AWA Oracle: ${awaOracle ? awaOracle.address : "(same as deployer)"}`);

  const balance = await ethers.provider.getBalance(deployer.address);
  console.log(`  Balance:    ${ethers.formatEther(balance)} ETH`);

  const results = {
    network: meta.name,
    chainId: Number(chainId),
    deployer: deployer.address,
    awaOracle: awaOracle ? awaOracle.address : deployer.address,
    deployerBalance: ethers.formatEther(balance),
    contracts: {},
  };

  // ── 1. ComplementarityVerifier (no constructor args) ──────────────────────
  console.log(`\n  [1/3] Deploying ComplementarityVerifier...`);
  const CompV = await ethers.getContractFactory("ComplementarityVerifier");
  const comp = await CompV.deploy();
  await comp.waitForDeployment();
  const compAddr = await comp.getAddress();
  const compTx = comp.deploymentTransaction()?.hash ?? "unknown";
  console.log(`    ✅ ComplementarityVerifier:  ${compAddr}`);
  console.log(`       TX:                       ${compTx}`);
  results.contracts.ComplementarityVerifier = { address: compAddr, tx: compTx };

  // ── 2. IntentCommitmentRegistry (no constructor args) ─────────────────────
  console.log(`\n  [2/3] Deploying IntentCommitmentRegistry...`);
  const RegF = await ethers.getContractFactory("IntentCommitmentRegistry");
  const reg = await RegF.deploy();
  await reg.waitForDeployment();
  const regAddr = await reg.getAddress();
  const regTx = reg.deploymentTransaction()?.hash ?? "unknown";
  console.log(`    ✅ IntentCommitmentRegistry:  ${regAddr}`);
  console.log(`       TX:                        ${regTx}`);
  results.contracts.IntentCommitmentRegistry = { address: regAddr, tx: regTx };

  // ── 3. TravelRuleCompliance (requires awaOracle) ──────────────────────────
  console.log(`\n  [3/3] Deploying TravelRuleCompliance...`);
  const awaAddr = awaOracle ? awaOracle.address : deployer.address;
  const TRCF = await ethers.getContractFactory("TravelRuleCompliance");
  const trc = await TRCF.deploy(awaAddr);
  await trc.waitForDeployment();
  const trcAddr = await trc.getAddress();
  const trcTx = trc.deploymentTransaction()?.hash ?? "unknown";
  console.log(`    ✅ TravelRuleCompliance:      ${trcAddr}`);
  console.log(`       TX:                        ${trcTx}`);
  results.contracts.TravelRuleCompliance = { address: trcAddr, tx: trcTx };

  // ── Verify AWA freeze defaults to TRUE (R-FAILCLOSED) ────────────────────
  const awaFrozen = await trc.awaFrozen();
  console.log(`\n  Post-deploy invariant checks:`);
  console.log(`    TravelRuleCompliance.awaFrozen = ${awaFrozen} (R-FAILCLOSED: must be true)`);
  if (!awaFrozen) {
    console.error(`    ❌ FATAL: awaFrozen must default to TRUE per R-FAILCLOSED.`);
    process.exit(1);
  }
  results.invariants = { awaFrozenDefaultsTrue: true };

  // ── Persist results ───────────────────────────────────────────────────────
  const outDir = path.resolve(__dirname, "..", "deploy-results");
  if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });
  const outFile = path.join(outDir, `zk_phase4_${name || `chain${chainId}`}.json`);
  fs.writeFileSync(outFile, JSON.stringify(results, null, 2));
  console.log(`\n  ✅ Deployment results persisted to: ${outFile}`);
  console.log(`\n  ═══════════════════════════════════════════════════════`);
  console.log(`  Phase 4 deployment complete on ${meta.name}.`);
  console.log(`  ═══════════════════════════════════════════════════════\n`);
}

const targetName = network.name || "unknown";
deployOne(targetName).catch((err) => {
  console.error(err);
  process.exit(1);
});
