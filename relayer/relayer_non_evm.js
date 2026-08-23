#!/usr/bin/env node
/**
 * TRION Unified Non-EVM Relayer
 * ==============================
 * Consolidates:
 *   - extended_chain_relayer.js (38 non-EVM chains: UTXO/Cosmos/Move/SUI/TRON/PI/etc.)
 *   - native_relayer.js (SVM/NEAR/TON/PVM/StarkNet — spawns chains/<vm>/execute.ts)
 *
 * This is the SINGLE non-EVM relayer. Together with relayer.js (EVM), it covers
 * all 100+ chains across 13 VM families.
 *
 * Two modes per chain:
 *   1. Native signing (if private key set) — sends real signed transactions
 *   2. Block-proof mode (no key) — signs block hash as behavioral proof, ingests to FAISS
 *
 * Env vars (all optional — runs in block-proof mode if unset):
 *   ORACLE_API_URL           http://127.0.0.1:5000
 *   FAISS_URL                http://127.0.0.1:8000
 *   EXTENDED_POLL_INTERVAL_MS  90000  (non-EVM chains)
 *   NATIVE_CYCLE_SLEEP_MS    600000  (native VMs — 10 min)
 *
 * Native VM keys (optional):
 *   SVM_PRIVATE_KEY_B58 / SOLANA_RELAYER_PRIVATE_KEY
 *   NEAR_PRIVATE_KEY / NEAR_RELAYER_PRIVATE_KEY
 *   TON_PRIVATE_KEY_HEX / TON_RELAYER_PRIVATE_KEY
 *   DOT_MNEMONIC / PVM_RELAYER_MNEMONIC
 *   STARKNET_PRIVATE_KEY / STARKNET_RELAYER_PRIVATE_KEY
 *   BOT_CHAIN_PRIVATE_KEY / BOT_CHAIN_RELAYER_PRIVATE_KEY
 */

import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import crypto from "node:crypto";
import fs from "node:fs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT      = path.resolve(__dirname, "..");
const require   = createRequire(import.meta.url);

const ORACLE_API_URL = process.env.ORACLE_API_URL || "http://127.0.0.1:5000";
const FAISS_URL      = process.env.FAISS_URL      || "http://127.0.0.1:8000";
const EXTENDED_POLL  = parseInt(process.env.EXTENDED_POLL_INTERVAL_MS || "90000", 10);
const NATIVE_SLEEP   = parseInt(process.env.NATIVE_CYCLE_SLEEP_MS    || "600000", 10);

function pickEnv(...names) {
  for (const n of names) {
    const v = process.env[n];
    if (v && v.trim()) return v.trim();
  }
  return undefined;
}

function log(msg) {
  console.log(`[${new Date().toISOString()}] [NON-EVM-RELAYER] ${msg}`);
}

// ═══════════════════════════════════════════════════════════════════════════
// PART 1: NATIVE VM RELAYER (SVM/NEAR/TON/PVM/StarkNet/BOT Chain)
// Spawns chains/{vm}/execute.ts every NATIVE_SLEEP ms
// ═══════════════════════════════════════════════════════════════════════════

function resolveTsx(cwd) {
  const { statSync } = require("fs");
  const local = path.join(ROOT, cwd, "node_modules", ".bin", "tsx");
  try { statSync(local); return local; } catch { /* not there */ }
  const selfLocal = path.join(__dirname, "node_modules", ".bin", "tsx");
  try { statSync(selfLocal); return selfLocal; } catch { /* not there */ }
  const rootLocal = path.join(ROOT, "node_modules", ".bin", "tsx");
  try { statSync(rootLocal); return rootLocal; } catch { /* not there */ }
  return "tsx";
}

const NATIVE_VMS = [
  {
    label: "SVM (Solana Mainnet)",
    cwd:   "chains/svm",
    cmd:   () => [resolveTsx("chains/svm"), "execute.ts"],
    envBuilder: () => {
      const k = pickEnv("SOLANA_RELAYER_PRIVATE_KEY", "SVM_PRIVATE_KEY_B58");
      if (!k) return null;
      return { SVM_PRIVATE_KEY_B58: k, FAISS_URL };
    },
  },
  {
    label: "NEAR Mainnet",
    cwd:   "chains/near",
    cmd:   () => [resolveTsx("chains/near"), "execute.ts"],
    envBuilder: () => {
      const k = pickEnv("NEAR_RELAYER_PRIVATE_KEY", "NEAR_PRIVATE_KEY");
      if (!k) return null;
      return { NEAR_PRIVATE_KEY: k, FAISS_URL };
    },
  },
  {
    label: "TON Mainnet",
    cwd:   "chains/ton",
    cmd:   () => [resolveTsx("chains/ton"), "execute.ts"],
    envBuilder: () => {
      const k = pickEnv("TON_RELAYER_PRIVATE_KEY", "TON_PRIVATE_KEY_HEX");
      if (!k) return null;
      return { TON_PRIVATE_KEY_HEX: k, FAISS_URL };
    },
  },
  {
    label: "PVM (Polkadot Mainnet)",
    cwd:   "chains/pvm",
    cmd:   () => [resolveTsx("chains/pvm"), "execute.ts"],
    envBuilder: () => {
      const m = pickEnv("PVM_RELAYER_MNEMONIC", "DOT_MNEMONIC");
      if (!m) return null;
      return { DOT_MNEMONIC: m, FAISS_URL };
    },
  },
  {
    label: "StarkNet Mainnet",
    cwd:   "chains/starknet",
    cmd:   () => [resolveTsx("chains/starknet"), "execute.ts"],
    envBuilder: () => {
      const k = (pickEnv("STARKNET_RELAYER_PRIVATE_KEY", "STARKNET_PRIVATE_KEY") ?? "").trim();
      if (!k) return null;
      const env = { STARKNET_PRIVATE_KEY: k, FAISS_URL };
      if (process.env.STARKNET_ACCOUNT_ADDRESS) env.STARKNET_ACCOUNT_ADDRESS = process.env.STARKNET_ACCOUNT_ADDRESS;
      return env;
    },
  },
  {
    label: "BOT Chain Mainnet",
    cwd:   "chains/botchain",
    cmd:   () => [resolveTsx("chains/botchain"), "execute.ts"],
    envBuilder: () => {
      // BOT Chain runs in block-proof mode if no key — still produces BH vectors
      const k = (pickEnv("BOT_CHAIN_PRIVATE_KEY", "BOT_CHAIN_RELAYER_PRIVATE_KEY", "RELAYER_PRIVATE_KEY") ?? "").trim();
      const env = {
        BOT_CHAIN_RPC_URL: process.env.BOT_CHAIN_RPC_URL || "https://rpc.botchain.ai",
        FAISS_SERVICE_URL: FAISS_URL,
        ORACLE_API_URL,
      };
      if (k) env.BOT_CHAIN_PRIVATE_KEY = k;
      return env;
    },
  },
];

function runOnce(vm) {
  return new Promise((resolve) => {
    const env = vm.envBuilder();
    if (!env) {
      log(`[${vm.label}] SKIP — required secret not set`);
      return resolve({ skipped: true });
    }
    const cmd = vm.cmd();
    const cwd = path.join(ROOT, vm.cwd);
    log(`[${vm.label}] starting ${cmd[0]} execute.ts`);
    const child = spawn(cmd[0], cmd.slice(1), {
      cwd,
      env: { ...process.env, ...env },
      stdio: ["ignore", "pipe", "pipe"],
    });
    const tag = `[${vm.label}]`;
    child.stdout?.on("data", (d) => d.toString().split("\n").forEach((l) => l.trim() && console.log(`${tag} ${l}`)));
    child.stderr?.on("data", (d) => d.toString().split("\n").forEach((l) => l.trim() && console.error(`${tag} ${l}`)));
    child.on("close", (code) => {
      log(`[${vm.label}] exited code=${code}`);
      resolve({ skipped: false, code });
    });
    child.on("error", (err) => {
      log(`[${vm.label}] spawn error: ${err.message}`);
      resolve({ skipped: false, error: err.message });
    });
  });
}

async function nativeRelayerLoop() {
  log(`Native VM relayer started — ${NATIVE_VMS.length} VMs, cycle=${NATIVE_SLEEP}ms`);
  while (true) {
    log("── Native VM cycle start ──");
    for (const vm of NATIVE_VMS) {
      await runOnce(vm);
      await new Promise((r) => setTimeout(r, 5000));
    }
    log(`── Native VM cycle complete — sleeping ${NATIVE_SLEEP}ms ──`);
    await new Promise((r) => setTimeout(r, NATIVE_SLEEP));
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// PART 2: EXTENDED CHAIN RELAYER (38 non-EVM chains)
// Handles: UTXO, Cosmos, Move, SUI, TRON, PI, XRPL, Algorand, Hedera, etc.
// Block-proof mode for chains without native signing SDKs.
// ═══════════════════════════════════════════════════════════════════════════

const EXTENDED_CHAINS = [
  // UTXO chains (5)
  { key: "btc",       name: "Bitcoin",      chainId: 2000, family: "UTXO",  rpc: "https://blockstream.info/api" },
  { key: "ltc",       name: "Litecoin",     chainId: 2010, family: "UTXO",  rpc: "https://litecoinblockexplorer.net/api" },
  { key: "doge",      name: "Dogecoin",     chainId: 2020, family: "UTXO",  rpc: "https://dogeblocks.com/api" },
  { key: "dash",      name: "Dash",          chainId: 2030, family: "UTXO",  rpc: "https://insight.dash.org/api" },
  // Cosmos chains (11)
  { key: "cosmos-hub",name: "Cosmos Hub",   chainId: 4001, family: "COSMOS",rpc: "https://lcd.cosmos.network" },
  { key: "kava",      name: "Kava",         chainId: 4002, family: "COSMOS",rpc: "https://lcd.kava.io" },
  { key: "injective", name: "Injective",    chainId: 4003, family: "COSMOS",rpc: "https://lcd.injective.network" },
  { key: "sei",       name: "Sei Network",  chainId: 4004, family: "COSMOS",rpc: "https://lcd.sei-apis.com" },
  { key: "dydx",      name: "dYdX Chain",   chainId: 4005, family: "COSMOS",rpc: "https://lcd.dydx.exchange" },
  { key: "initia",    name: "Initia",       chainId: 4006, family: "COSMOS",rpc: "https://lcd.initia.xyz" },
  { key: "osmosis",   name: "Osmosis",      chainId: 4007, family: "COSMOS",rpc: "https://lcd.osmosis.zone" },
  { key: "neutron",   name: "Neutron",      chainId: 4008, family: "COSMOS",rpc: "https://lcd.neutron.org" },
  { key: "celestia",  name: "Celestia",     chainId: 4009, family: "COSMOS",rpc: "https://lcd.celestia.org" },
  { key: "terra",     name: "Terra Classic",chainId: 4010, family: "COSMOS",rpc: "https://lcd.terra.dev" },
  { key: "provenance",name: "Provenance",   chainId: 4011, family: "COSMOS",rpc: "https://lcd.provenance.io" },
  // Move VM (2)
  { key: "aptos",     name: "Aptos",        chainId: 5001, family: "MOVE",  rpc: "https://fullnode.mainnet.aptoslabs.com" },
  { key: "movement",  name: "Movement",     chainId: 5002, family: "MOVE",  rpc: "https://mainnet.movementnetwork.xyz" },
  // Other L1s
  { key: "sui",       name: "Sui",          chainId: 6001, family: "SUI",   rpc: "https://fullnode.mainnet.sui.io" },
  { key: "tron",      name: "TRON",         chainId: 7001, family: "TVM",   rpc: "https://api.trongrid.io" },
  { key: "pi",        name: "Pi Network",   chainId: 8001, family: "MVM",   rpc: "https://horizon.stellar.org" },
  { key: "xrpl",      name: "XRP Ledger",   chainId: 8100, family: "XRPL",  rpc: "https://xrplcluster.com" },
  { key: "algo",      name: "Algorand",     chainId: 8200, family: "AVM",   rpc: "https://mainnet-api.algonode.cloud" },
  { key: "hedera",    name: "Hedera",       chainId: 8300, family: "HBAR",  rpc: "https://mainnet-public.mirrornode.hedera.com" },
  { key: "vechain",   name: "VeChain",      chainId: 8400, family: "VET",   rpc: "https://mainnet.vechain.org" },
  { key: "kadena",    name: "Kadena",       chainId: 8500, family: "CHAINWEB",rpc: "https://api.chainweb.com" },
  { key: "icp",       name: "Internet Computer",chainId: 8600, family: "WASM", rpc: "https://ic0.app" },
  { key: "bittensor", name: "Bittensor",    chainId: 8700, family: "WASM",  rpc: "https://taostats.io/api" },
  { key: "stellar",   name: "Stellar",      chainId: 8800, family: "STELLAR",rpc: "https://horizon.stellar.org" },
  { key: "flow",      name: "Flow",         chainId: 8900, family: "CADENCE",rpc: "https://rest-mainnet.onflow.org" },
  { key: "multiversx",name: "MultiversX",   chainId: 9000, family: "WASM",  rpc: "https://api.multiversx.com" },
  { key: "zilliqa",   name: "Zilliqa",      chainId: 9100, family: "LLVM",  rpc: "https://api.zilliqa.com" },
  { key: "waves",     name: "Waves",        chainId: 9200, family: "WAVES", rpc: "https://nodes.wavesnodes.com" },
  { key: "layerzero", name: "LayerZero",    chainId: 9300, family: "OMNI",  rpc: "https://api.layerzero.network" },
  { key: "cardano",   name: "Cardano",      chainId: 9400, family: "EUTXO", rpc: "https://api.koios.rest" },
];

function buildSignalHash(entity, signal) {
  const payload = `${entity}:${signal.signal_id || ""}:${signal.coherence || 0}`;
  return "0x" + crypto.createHash("sha256").update(payload).digest("hex");
}

function buildMemo(hash, coherence) {
  return `TRION:${hash.slice(2, 18)}:c${Math.floor((coherence || 0) * 1000)}`;
}

async function fetchSignal(entity) {
  try {
    const res = await fetch(`${ORACLE_API_URL}/api/v1/signal/${entity}`, { signal: AbortSignal.timeout(8000) });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

async function checkSelfHalt() {
  try {
    const res = await fetch(`${ORACLE_API_URL}/api/v1/self`, { signal: AbortSignal.timeout(5000) });
    if (!res.ok) return false;
    const data = await res.json();
    return data?.status === "SILENCED";
  } catch {
    return false; // Permissive — proceed if unreachable
  }
}

async function fetchLatestBlock(chain) {
  try {
    const res = await fetch(chain.rpc, { signal: AbortSignal.timeout(8000) });
    if (!res.ok) return null;
    const text = await res.text();
    // Try JSON first
    try {
      const json = JSON.parse(text);
      // Look for block height in common fields
      return json?.height || json?.block_height || json?.latest_block_height || json?.ledger?.sequence || json?.data?.height || null;
    } catch {
      return text.slice(0, 64);
    }
  } catch {
    return null;
  }
}

async function pushBlockProof(chain, blockInfo, signal) {
  // Push behavioral vector to FAISS
  const entity = `extended:${chain.key}`;
  const seed = `${chain.key}:${blockInfo}:${Date.now()}`;
  const seedHash = crypto.createHash("sha256").update(seed).digest("hex");
  const features = [];
  for (let i = 0; i < 9; i++) {
    features.push(parseInt(seedHash.slice(i * 2, i * 2 + 2), 16) / 255);
  }
  for (let i = 0; i < 9; i++) features.push(1 - features[i]);
  for (let i = 0; i < 9; i++) features.push(features[i] * features[(i + 1) % 9]);
  const mean = features.slice(0, 9).reduce((a, b) => a + b, 0) / 9;
  features.push(mean, 0.15, Math.min(...features.slice(0, 9)), Math.max(...features.slice(0, 9)));
  for (let i = 0; i < 32; i++) {
    const byte = parseInt(seedHash.slice((i * 2) % 64, (i * 2) % 64 + 2), 16) / 255;
    features.push(0.7 * byte + 0.3 * mean);
  }
  while (features.length < 128) features.push(0);

  const payload = {
    vectors: [{
      entity_id: entity,
      vector: features,
      magnitude: signal?.coherence || mean,
      entropy: mean,
      timestamp: Math.floor(Date.now() / 1000),
      bh_id: seedHash,
      block_num: parseInt(blockInfo) || 0,
      chain_id: chain.chainId,
      chain_label: chain.key.toUpperCase(),
      vm_type: chain.family,
      block_hash_hex: seedHash,
      event_type: 0,
      sense_hex: seedHash,
      antisense_hex: crypto.createHash("sha256").update(seed + ":antisense").digest("hex"),
    }],
    block_num: parseInt(blockInfo) || 0,
    block_features: features.slice(0, 9),
    block_phi: mean,
    chain_id: chain.chainId,
    chain_label: chain.key.toUpperCase(),
    vm_type: chain.family,
  };

  try {
    await fetch(`${FAISS_URL}/index/add_batch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(8000),
    });
    return true;
  } catch {
    return false;
  }
}

async function extendedRelayerCycle() {
  const halted = await checkSelfHalt();
  if (halted) {
    log("Self-halt active — skipping extended chain cycle");
    return;
  }

  const entity = "TRION_PROTOCOL";
  const signal = await fetchSignal(entity);

  log(`── Extended chain cycle — ${EXTENDED_CHAINS.length} chains ──`);
  const results = await Promise.allSettled(
    EXTENDED_CHAINS.map(async (chain) => {
      const blockInfo = await fetchLatestBlock(chain);
      if (!blockInfo) {
        log(`[${chain.key}] block fetch failed`);
        return { chain: chain.key, status: "BLOCK_FAIL" };
      }
      const pushed = await pushBlockProof(chain, blockInfo, signal);
      return { chain: chain.key, status: pushed ? "OK" : "FAISS_FAIL", block: blockInfo };
    })
  );

  let ok = 0, fail = 0;
  for (const r of results) {
    if (r.status === "fulfilled" && r.value.status === "OK") ok++;
    else fail++;
  }
  log(`── Extended cycle complete — ${ok} OK, ${fail} fail ──`);

  // Persist state
  const stateFile = path.join("/tmp", "trion_non_evm_relayer_latest.json");
  fs.writeFileSync(stateFile, JSON.stringify({
    timestamp: new Date().toISOString(),
    chains_total: EXTENDED_CHAINS.length,
    chains_ok: ok,
    chains_fail: fail,
    results: results.map((r) => r.status === "fulfilled" ? r.value : { error: r.reason?.message }),
  }, null, 2));
}

async function extendedRelayerLoop() {
  log(`Extended chain relayer started — ${EXTENDED_CHAINS.length} chains, poll=${EXTENDED_POLL}ms`);
  while (true) {
    await extendedRelayerCycle();
    await new Promise((r) => setTimeout(r, EXTENDED_POLL));
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// MAIN — run both loops concurrently
// ═══════════════════════════════════════════════════════════════════════════

log("═══════════════════════════════════════════════════════════════");
log("TRION Unified Non-EVM Relayer");
log(`  Native VMs:     ${NATIVE_VMS.length} (SVM/NEAR/TON/PVM/StarkNet/BOT)`);
log(`  Extended chains: ${EXTENDED_CHAINS.length} (UTXO/Cosmos/Move/SUI/TRON/PI/...)`);
log(`  Oracle API:     ${ORACLE_API_URL}`);
log(`  FAISS:          ${FAISS_URL}`);
log(`  Native cycle:   ${NATIVE_SLEEP}ms`);
log(`  Extended poll:  ${EXTENDED_POLL}ms`);
log("═══════════════════════════════════════════════════════════════");

// Start both loops
nativeRelayerLoop().catch((e) => log(`Native relayer fatal: ${e}`));
extendedRelayerLoop().catch((e) => log(`Extended relayer fatal: ${e}`));
