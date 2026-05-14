#!/usr/bin/env node
/**
 * TRION × 0G — Mainnet Deployment (Aristotle)
 * ==============================================
 * Deploys TRIONExecutionGate to 0G Aristotle mainnet (chainId 16601)
 * after testnet validation is complete.
 *
 * Usage:
 *   DEPLOYER_PRIVATE_KEY=0x... NETWORK=mainnet node scripts/deploy_execution_gate_0g.mjs
 *
 * Pre-flight checks this script enforces:
 *   1. Testnet deployment must exist in proof-ledger/deploy_zerog_galileo.json
 *   2. At least 0.01 OG mainnet balance required
 *   3. User must confirm before proceeding (--yes flag or CONFIRM=yes)
 *
 * After successful mainnet deploy:
 *   - Updates proof-ledger/deploy_zerog_mainnet.json
 *   - Prints the chainscan link
 *   - Prints env var to add to the ZG ExecutionGate relayer
 */

import { ethers } from "ethers";
import fs from "node:fs";
import path from "node:path";
import readline from "node:readline";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");

const PRIV_KEY    = process.env.DEPLOYER_PRIVATE_KEY || process.env.RELAYER_PRIVATE_KEY;
const CONFIRM     = process.env.CONFIRM === "yes" || process.argv.includes("--yes");
const ZG_MAINNET  = {
  name:       "0G Mainnet",
  chainId:    16661,
  rpc:        process.env.ZG_MAINNET_RPC || "https://evmrpc.0g.ai",
  explorer:   "https://chainscan.0g.ai",
  ledgerFile: "proof-ledger/deploy_zerog_mainnet.json",
};

async function confirm(msg) {
  if (CONFIRM) return true;
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise(resolve => {
    rl.question(`\n${msg} (yes/no): `, answer => {
      rl.close();
      resolve(answer.trim().toLowerCase() === "yes");
    });
  });
}

async function main() {
  console.log("================================================");
  console.log(" TRION × 0G  MAINNET Deployment (Aristotle)");
  console.log("================================================");

  if (!PRIV_KEY) {
    console.error("ERROR: Set DEPLOYER_PRIVATE_KEY env var.");
    process.exit(1);
  }

  // ── Pre-flight: testnet must be deployed ──────────────────────────────────
  const testnetLedger = path.join(ROOT, "proof-ledger", "deploy_zerog_galileo.json");
  if (!fs.existsSync(testnetLedger)) {
    console.error("ERROR: Testnet deployment not found. Run testnet deployment first:");
    console.error("  node scripts/deploy_execution_gate_0g.mjs");
    process.exit(1);
  }
  const testnet = JSON.parse(fs.readFileSync(testnetLedger, "utf-8"));
  if (!testnet.TRIONExecutionGate) {
    console.error("ERROR: TRIONExecutionGate not found in testnet ledger. Deploy testnet first.");
    console.error("  node scripts/deploy_execution_gate_0g.mjs");
    process.exit(1);
  }
  console.log(` ✓ Testnet gate   : ${testnet.TRIONExecutionGate}`);
  console.log(` ✓ Testnet oracle : ${testnet.TRIONOracleV3}`);
  console.log(` ✓ Testnet status : ${testnet.status}`);

  // ── Check mainnet balance ─────────────────────────────────────────────────
  const provider = new ethers.JsonRpcProvider(ZG_MAINNET.rpc, ZG_MAINNET.chainId);
  const wallet   = new ethers.Wallet(
    PRIV_KEY.startsWith("0x") ? PRIV_KEY : "0x" + PRIV_KEY,
    provider
  );

  let balance;
  try {
    balance = await provider.getBalance(wallet.address);
  } catch (e) {
    console.error(`ERROR: Cannot connect to mainnet RPC: ${e.message}`);
    console.error(`RPC: ${ZG_MAINNET.rpc}`);
    process.exit(1);
  }

  console.log(`\n Mainnet deployer  : ${wallet.address}`);
  console.log(` Mainnet balance   : ${ethers.formatEther(balance)} OG`);

  if (balance < ethers.parseEther("0.01")) {
    console.error("ERROR: Need at least 0.01 OG on mainnet.");
    console.error("Bridge OG tokens from testnet or purchase on an exchange.");
    process.exit(1);
  }

  console.log(`\n Network           : ${ZG_MAINNET.name}  (chainId ${ZG_MAINNET.chainId})`);
  console.log(` RPC               : ${ZG_MAINNET.rpc}`);
  console.log(` Explorer          : ${ZG_MAINNET.explorer}`);

  const ok = await confirm("Deploy TRIONExecutionGate to 0G Aristotle MAINNET?");
  if (!ok) {
    console.log("Deployment cancelled.");
    process.exit(0);
  }

  // ── Delegate to the shared deployment script with NETWORK=mainnet ─────────
  const { execSync } = await import("node:child_process");
  console.log("\n Running mainnet deployment …");
  execSync(
    `NETWORK=mainnet DEPLOYER_PRIVATE_KEY=${PRIV_KEY} node scripts/deploy_execution_gate_0g.mjs`,
    { stdio: "inherit", cwd: ROOT }
  );
}

main().catch(e => {
  console.error("Mainnet deploy failed:", e.message || e);
  process.exit(1);
});
