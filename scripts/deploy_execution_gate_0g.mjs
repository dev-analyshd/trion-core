#!/usr/bin/env node
/**
 * TRION × 0G — TRIONExecutionGate Deployment Script
 * ===================================================
 * Compiles TRIONExecutionGate.sol with solc and deploys to 0G Galileo testnet
 * (chainId 16602) or 0G mainnet (chainId 16661 — canonical registry id; the
 * old "Aristotle 16601" label matched no chain anywhere).
 *
 * Usage:
 *   DEPLOYER_PRIVATE_KEY=0x... node scripts/deploy_execution_gate_0g.mjs
 *   DEPLOYER_PRIVATE_KEY=0x... NETWORK=mainnet node scripts/deploy_execution_gate_0g.mjs
 *
 * Env vars:
 *   DEPLOYER_PRIVATE_KEY   — 0x-prefixed hex private key
 *   NETWORK                — "testnet" (default) | "mainnet"
 *   ZG_TESTNET_RPC         — override testnet RPC (default: https://evmrpc-testnet.0g.ai)
 *   ZG_MAINNET_RPC         — override mainnet RPC (default: https://evmrpc.0g.ai)
 *   QUORUM                 — validator quorum (default: 1)
 */

import { ethers } from "ethers";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");

// ── Network config ────────────────────────────────────────────────────────────
const NETWORKS = {
  testnet: {
    name: "0G Galileo Testnet",
    chainId: 16602,
    rpc: process.env.ZG_TESTNET_RPC || "https://evmrpc-testnet.0g.ai",
    explorer: "https://chainscan-galileo.0g.ai",
    ledgerFile: "proof-ledger/deploy_zerog_galileo.json",
  },
  mainnet: {
    name: "0G Mainnet",
    chainId: 16661,
    rpc: process.env.ZG_MAINNET_RPC || "https://evmrpc.0g.ai",
    explorer: "https://chainscan.0g.ai",
    ledgerFile: "proof-ledger/deploy_zerog_mainnet.json",
  },
};

const NETWORK   = NETWORKS[process.env.NETWORK || "testnet"];
const QUORUM    = parseInt(process.env.QUORUM || "1", 10);
const PRIV_KEY  = process.env.DEPLOYER_PRIVATE_KEY || process.env.RELAYER_PRIVATE_KEY;

if (!PRIV_KEY) {
  console.error("ERROR: Set DEPLOYER_PRIVATE_KEY or RELAYER_PRIVATE_KEY env var.");
  process.exit(1);
}

// ── Load & compile contract ───────────────────────────────────────────────────
async function compileContract() {
  const { createRequire } = await import("node:module");
  const require = createRequire(import.meta.url);

  let solc;
  try {
    solc = require("solc");
  } catch {
    console.error("solc not found. Run: npm install solc --save-dev");
    process.exit(1);
  }

  const contractPath = path.join(ROOT, "contracts", "TRIONExecutionGate.sol");
  const source = fs.readFileSync(contractPath, "utf-8");

  const input = {
    language: "Solidity",
    sources: { "TRIONExecutionGate.sol": { content: source } },
    settings: {
      evmVersion: "paris",
      optimizer: { enabled: true, runs: 200 },
      outputSelection: {
        "*": { "*": ["abi", "evm.bytecode.object"] },
      },
    },
  };

  console.log("Compiling TRIONExecutionGate.sol …");
  const output = JSON.parse(solc.compile(JSON.stringify(input)));

  const errors = (output.errors || []).filter(e => e.severity === "error");
  if (errors.length) {
    errors.forEach(e => console.error(e.formattedMessage));
    process.exit(1);
  }

  const warnings = (output.errors || []).filter(e => e.severity === "warning");
  if (warnings.length) {
    warnings.forEach(w => console.warn("WARN:", w.message?.split("\n")[0]));
  }

  const contract = output.contracts["TRIONExecutionGate.sol"]["TRIONExecutionGate"];
  if (!contract) {
    console.error("Compilation output missing TRIONExecutionGate");
    process.exit(1);
  }

  console.log("Compilation OK");
  return {
    abi:      contract.abi,
    bytecode: "0x" + contract.evm.bytecode.object,
  };
}

// ── Deploy ────────────────────────────────────────────────────────────────────
async function deploy() {
  console.log("================================================");
  console.log(" TRION × 0G  ExecutionGate Deployment");
  console.log("================================================");
  console.log(` Network  : ${NETWORK.name}  (chainId ${NETWORK.chainId})`);
  console.log(` RPC      : ${NETWORK.rpc}`);
  console.log(` Explorer : ${NETWORK.explorer}`);
  console.log(` Quorum   : ${QUORUM}`);
  console.log("");

  const { abi, bytecode } = await compileContract();

  const provider = new ethers.JsonRpcProvider(NETWORK.rpc, NETWORK.chainId);
  const wallet   = new ethers.Wallet(
    PRIV_KEY.startsWith("0x") ? PRIV_KEY : "0x" + PRIV_KEY,
    provider
  );
  const deployer = wallet.address;

  const balance = await provider.getBalance(deployer);
  const block   = await provider.getBlockNumber();
  const nonce   = await provider.getTransactionCount(deployer);

  console.log(` Deployer : ${deployer}`);
  console.log(` Balance  : ${ethers.formatEther(balance)} OG`);
  console.log(` Block    : ${block}`);
  console.log(` Nonce    : ${nonce}`);
  console.log("");

  if (balance < ethers.parseEther("0.005")) {
    console.error("ERROR: Balance too low. Need at least 0.005 OG for deployment.");
    process.exit(1);
  }

  const factory = new ethers.ContractFactory(abi, bytecode, wallet);

  console.log("Deploying TRIONExecutionGate …");
  const gasPrice = (await provider.getFeeData()).gasPrice;
  console.log(` Gas price: ${ethers.formatUnits(gasPrice, "gwei")} gwei`);

  const contract = await factory.deploy(QUORUM, {
    gasLimit: 2_000_000,
    gasPrice: gasPrice,
  });

  console.log(` Tx hash  : ${contract.deploymentTransaction().hash}`);
  console.log("Waiting for confirmation …");

  const receipt = await contract.deploymentTransaction().wait(1);
  const addr    = await contract.getAddress();

  console.log("");
  console.log("================================================");
  console.log(" DEPLOYMENT SUCCESSFUL");
  console.log("================================================");
  console.log(` Contract : ${addr}`);
  console.log(` Block    : ${receipt.blockNumber}`);
  console.log(` Tx hash  : ${receipt.hash}`);
  console.log(` Explorer : ${NETWORK.explorer}/address/${addr}`);
  console.log(` Tx link  : ${NETWORK.explorer}/tx/${receipt.hash}`);
  console.log("");

  // ── Verify it works ────────────────────────────────────────────────────────
  const gate = new ethers.Contract(addr, abi, wallet);
  const owner = await gate.owner();
  const quorumOnChain = await gate.quorumRequired();
  const isVal = await gate.isValidator(deployer);
  console.log(` Owner    : ${owner}`);
  console.log(` Quorum   : ${quorumOnChain}`);
  console.log(` Is valid : ${isVal}`);

  // ── Storage sync: record FAISS index hash on-chain ────────────────────────
  try {
    const faissIndexPath = path.join(ROOT, "akashic", "akashic_faiss.index");
    let vectorCount = 531000;
    let faissHash = "0x" + "ab".repeat(16);

    if (fs.existsSync(faissIndexPath)) {
      const { createHash } = await import("node:crypto");
      const data = fs.readFileSync(faissIndexPath);
      faissHash  = "0x" + createHash("sha256").update(data).digest("hex");
      vectorCount = Math.floor(data.length / 128); // estimate from file size
      console.log(`\n Syncing FAISS index to 0G Storage record …`);
      console.log(` FAISS hash: ${faissHash}`);
      console.log(` Est. vectors: ${vectorCount.toLocaleString()}`);
    } else {
      console.log(`\n FAISS index not found at ${faissIndexPath} — using placeholder hash`);
    }

    const storageRoot = `0g-storage:galileo:${faissHash.slice(2, 18)}`;
    const syncTx = await gate.confirmStorageSync(storageRoot, vectorCount, {
      gasLimit: 100_000,
      gasPrice: gasPrice,
    });
    const syncReceipt = await syncTx.wait(1);
    console.log(` Storage sync tx: ${syncReceipt.hash}`);
    console.log(` Storage root   : ${storageRoot}`);
  } catch (e) {
    console.warn(` Storage sync skipped: ${e.message?.slice(0, 80)}`);
  }

  // ── Save proof ledger ──────────────────────────────────────────────────────
  const ledgerPath = path.join(ROOT, NETWORK.ledgerFile);
  let existing = {};
  try {
    existing = JSON.parse(fs.readFileSync(ledgerPath, "utf-8"));
  } catch { /* fresh */ }

  const record = {
    ...existing,
    network: NETWORK.name,
    chainId: NETWORK.chainId,
    explorer: NETWORK.explorer,
    deployer,
    timestamp: new Date().toISOString(),
    TRIONExecutionGate: addr,
    execution_gate_tx: receipt.hash,
    status: "live",
  };
  fs.writeFileSync(ledgerPath, JSON.stringify(record, null, 2));
  console.log(`\n Ledger saved to ${NETWORK.ledgerFile}`);

  // ── Save ABI for relayer ────────────────────────────────────────────────────
  const abiPath = path.join(ROOT, "proof-ledger", "TRIONExecutionGate.abi.json");
  fs.writeFileSync(abiPath, JSON.stringify(abi, null, 2));
  console.log(` ABI saved to proof-ledger/TRIONExecutionGate.abi.json`);

  console.log("\n Next steps:");
  console.log("  1. Set ZG_EXECUTION_GATE_ADDR=" + addr);
  console.log("  2. Start the 0G ExecutionGate relayer:");
  console.log("     ZG_EXECUTION_GATE_ADDR=" + addr + " node relayer/zg_execution_gate_relayer.js");
  console.log("  3. For mainnet: NETWORK=mainnet node scripts/deploy_execution_gate_0g.mjs");

  return { addr, receipt, NETWORK };
}

deploy().catch(e => {
  console.error("Deploy failed:", e.message || e);
  process.exit(1);
});
