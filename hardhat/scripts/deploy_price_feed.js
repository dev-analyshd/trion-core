/**
 * deploy_price_feed.js — Deploy TRIONPriceFeed (Chainlink AggregatorV3-compatible)
 *
 * Deploys both the forward and inverse feed for a given pair.
 * Saves addresses to proof-ledger for the relayer to pick up.
 *
 * Usage:
 *   BASE=ETH QUOTE=USD npx hardhat run scripts/deploy_price_feed.js --network arbSepolia
 *   BASE=BTC QUOTE=USD npx hardhat run scripts/deploy_price_feed.js --network baseSepolia
 *   BASE=SOL QUOTE=USD npx hardhat run scripts/deploy_price_feed.js --network ethSepolia
 *
 * Defaults to ETH/USD if BASE/QUOTE not set.
 */

const hre    = require("hardhat");
const fs     = require("fs");
const path   = require("path");

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  const network    = hre.network.name;
  const chainId    = (await hre.ethers.provider.getNetwork()).chainId;

  const BASE  = (process.env.BASE  || "ETH").toUpperCase();
  const QUOTE = (process.env.QUOTE || "USD").toUpperCase();

  console.log("─".repeat(60));
  console.log(`TRIONPriceFeed Deployer`);
  console.log(`  Network  : ${network} (chain ${chainId})`);
  console.log(`  Pair     : ${BASE}/${QUOTE}`);
  console.log(`  Deployer : ${deployer.address}`);
  console.log("─".repeat(60));

  const balance = await hre.ethers.provider.getBalance(deployer.address);
  console.log(`  Balance  : ${hre.ethers.formatEther(balance)} ETH`);
  if (balance < hre.ethers.parseEther("0.001")) {
    throw new Error("Insufficient balance for deployment");
  }

  const Factory = await hre.ethers.getContractFactory("TRIONPriceFeed");
  const relayer  = deployer.address; // update to relayer address after deployment

  // ── Deploy forward feed: BASE/QUOTE ──────────────────────────────────────
  console.log(`\nDeploying ${BASE}/${QUOTE} (forward)...`);
  const forward = await Factory.deploy(BASE, QUOTE, false, relayer);
  await forward.waitForDeployment();
  const forwardAddr = await forward.getAddress();
  console.log(`  ✅ ${BASE}/${QUOTE} forward feed : ${forwardAddr}`);

  // ── Deploy inverse feed: QUOTE/BASE ──────────────────────────────────────
  console.log(`\nDeploying ${QUOTE}/${BASE} (inverse)...`);
  const inverse = await Factory.deploy(BASE, QUOTE, true, relayer);
  await inverse.waitForDeployment();
  const inverseAddr = await inverse.getAddress();
  console.log(`  ✅ ${QUOTE}/${BASE} inverse feed : ${inverseAddr}`);

  // ── Verify deployment fields ──────────────────────────────────────────────
  console.log(`\nVerifying deployments...`);
  console.log(`  forward.decimals()    = ${await forward.decimals()}`);
  console.log(`  forward.description() = ${await forward.description()}`);
  console.log(`  forward.isInverse()   = ${await forward.isInverse()}`);
  console.log(`  inverse.description() = ${await inverse.description()}`);
  console.log(`  inverse.isInverse()   = ${await inverse.isInverse()}`);

  // ── Write proof-ledger ────────────────────────────────────────────────────
  const ledgerPath = path.join(__dirname, "..", "deployed_price_feeds.json");
  let ledger = {};
  if (fs.existsSync(ledgerPath)) {
    try { ledger = JSON.parse(fs.readFileSync(ledgerPath, "utf8")); }
    catch (_) { ledger = {}; }
  }

  if (!ledger[network]) ledger[network] = {};
  const pairKey    = `${BASE}_${QUOTE}`;
  const invPairKey = `${QUOTE}_${BASE}`;

  ledger[network][pairKey] = {
    base:        BASE,
    quote:       QUOTE,
    isInverse:   false,
    address:     forwardAddr,
    chainId:     chainId.toString(),
    deployedAt:  new Date().toISOString(),
    deployer:    deployer.address,
    relayer:     relayer,
  };
  ledger[network][invPairKey] = {
    base:        QUOTE,
    quote:       BASE,
    isInverse:   true,
    address:     inverseAddr,
    chainId:     chainId.toString(),
    deployedAt:  new Date().toISOString(),
    deployer:    deployer.address,
    relayer:     relayer,
  };

  fs.writeFileSync(ledgerPath, JSON.stringify(ledger, null, 2));
  console.log(`\n✅ Proof ledger updated: hardhat/deployed_price_feeds.json`);

  // ── Print Chainlink-compatible usage ──────────────────────────────────────
  console.log("\n─".repeat(60));
  console.log("CHAINLINK DROP-IN USAGE (Solidity):");
  console.log("─".repeat(60));
  console.log(`
// Forward feed: ${BASE} priced in ${QUOTE}
ITRIONAggregatorV3 feed = ITRIONAggregatorV3(${forwardAddr});
(, int256 price, , uint256 updatedAt,) = feed.latestRoundData();
require(block.timestamp - updatedAt < 3600, "Stale");
// price has 8 decimals, identical to Chainlink

// Inverse feed: ${QUOTE} priced in ${BASE}
ITRIONAggregatorV3 inverseFeed = ITRIONAggregatorV3(${inverseAddr});
(, int256 inversePrice, , ,) = inverseFeed.latestRoundData();

// Behavioral circuit breaker (TRION-specific, beyond Chainlink):
TRIONPriceFeed trionFeed = TRIONPriceFeed(${forwardAddr});
require(!trionFeed.isManipulated(), "TRION: manipulation detected");
require(!trionFeed.isStale(),       "TRION: price stale");
`);

  console.log("─".repeat(60));
  console.log(`REST API equivalents:`);
  console.log(`  Forward : GET /api/v1/price/${BASE}/${QUOTE}`);
  console.log(`  Inverse : GET /api/v1/price/${BASE}/${QUOTE}/inverse`);
  console.log(`  Both    : GET /api/v1/price/${BASE}/${QUOTE}/aggregator`);
  console.log(`  Seed    : POST /api/v1/price/seed`);
  console.log("─".repeat(60));
}

main().catch((err) => { console.error(err); process.exit(1); });
