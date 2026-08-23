/**
 * TRION Protocol — TRIONOracleV3 Multi-Chain Deployment Script
 * Usage: npx hardhat run scripts/deploy_oracle_v3.js --network <networkName>
 *
 * Supported networks (in hardhat.config.ts):
 *   arbitrumSepolia, ethSepolia, baseSepolia, optimismSepolia,
 *   hashkeyChain, bnbTestnet, zeroGTestnet,
 *   lineaMainnet, scrollMainnet, mantleMainnet,
 *   polygonMainnet, polygonAmoy
 */

const { ethers, network } = require("hardhat");
const fs = require("fs");
const path = require("path");

const CHAIN_META = {
  421614:  { name: "Arbitrum Sepolia",   explorer: "https://sepolia.arbiscan.io" },
  11155111:{ name: "Ethereum Sepolia",   explorer: "https://sepolia.etherscan.io" },
  84532:   { name: "Base Sepolia",       explorer: "https://sepolia.basescan.org" },
  11155420:{ name: "Optimism Sepolia",   explorer: "https://sepolia-optimism.etherscan.io" },
  177:     { name: "HashKey Mainnet",    explorer: "https://explorer.hsk.xyz" },
  97:      { name: "BNB Testnet",        explorer: "https://testnet.bscscan.com" },
  16602:   { name: "0G Galileo",         explorer: "https://chainscan-galileo.0g.ai" },
  59144:   { name: "Linea Mainnet",      explorer: "https://lineascan.build" },
  534352:  { name: "Scroll Mainnet",     explorer: "https://scrollscan.com" },
  5000:    { name: "Mantle Mainnet",     explorer: "https://mantlescan.xyz" },
  137:     { name: "Polygon Mainnet",    explorer: "https://polygonscan.com" },
  80002:   { name: "Polygon Amoy",       explorer: "https://amoy.polygonscan.com" },
};

async function main() {
  const [deployer] = await ethers.getSigners();
  const chainId = (await ethers.provider.getNetwork()).chainId;
  const meta = CHAIN_META[Number(chainId)] || { name: `Chain ${chainId}`, explorer: "" };

  console.log(`\n╔═══════════════════════════════════════════════════╗`);
  console.log(`║  TRION Protocol — TRIONOracleV3 Deployment        ║`);
  console.log(`╚═══════════════════════════════════════════════════╝`);
  console.log(`  Network:   ${meta.name} (chain ${chainId})`);
  console.log(`  Deployer:  ${deployer.address}`);

  const balance = await ethers.provider.getBalance(deployer.address);
  const balEth  = parseFloat(ethers.formatEther(balance));
  console.log(`  Balance:   ${balEth.toFixed(6)} ETH`);

  if (balEth < 0.001) {
    console.error(`  ❌ Insufficient balance. Need at least 0.001 ETH for deployment.`);
    process.exit(1);
  }

  // ── Deploy TRIONOracleV3 ──────────────────────────────────────────────────
  console.log(`\n  Deploying TRIONOracleV3...`);
  const Oracle = await ethers.getContractFactory("TRIONOracleV3");
  const oracle = await Oracle.deploy();
  await oracle.waitForDeployment();
  const oracleAddr = await oracle.getAddress();
  const oracleTx   = oracle.deploymentTransaction()?.hash ?? "unknown";
  console.log(`  ✅ TRIONOracleV3: ${oracleAddr}`);
  console.log(`     TX: ${oracleTx}`);
  if (meta.explorer) {
    console.log(`     Explorer: ${meta.explorer}/address/${oracleAddr}`);
  }

  const balAfter   = await ethers.provider.getBalance(deployer.address);
  const gasCost    = parseFloat(ethers.formatEther(balance - balAfter));
  console.log(`  Gas cost:  ${gasCost.toFixed(6)} ETH`);

  // ── Write proof-ledger record ─────────────────────────────────────────────
  const record = {
    network:       meta.name,
    chainId:       Number(chainId),
    explorer:      meta.explorer,
    deployer:      deployer.address,
    rpc:           network.config.url || "",
    timestamp:     new Date().toISOString(),
    balance_before: ethers.formatEther(balance),
    balance_after:  ethers.formatEther(balAfter),
    gas_cost_eth:  gasCost.toFixed(8),
    TRIONOracleV3: oracleAddr,
    oracle_tx:     oracleTx,
    status:        "live",
  };

  const slug     = meta.name.toLowerCase().replace(/\s+/g, "_").replace(/[^a-z0-9_]/g, "");
  const ledgerDir = path.resolve(__dirname, "../../proof-ledger");
  fs.mkdirSync(ledgerDir, { recursive: true });
  const ledgerPath = path.join(ledgerDir, `deploy_${slug}.json`);
  fs.writeFileSync(ledgerPath, JSON.stringify(record, null, 2));
  console.log(`\n  📝 Proof-ledger: proof-ledger/deploy_${slug}.json`);

  console.log(`\n  ════════════════════════════════════════════════════`);
  console.log(`  Deployment complete on ${meta.name}`);
  console.log(`  TRIONOracleV3: ${oracleAddr}`);
  console.log(`  ════════════════════════════════════════════════════\n`);

  return { chainId: Number(chainId), address: oracleAddr, tx: oracleTx };
}

main().catch((e) => { console.error(e); process.exit(1); });
