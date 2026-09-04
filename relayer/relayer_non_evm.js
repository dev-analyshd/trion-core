#!/usr/bin/env node
/**
 * TRION Unified Non-EVM Relayer
 * ==============================
 * Consolidates:
 *   - extended_chain_relayer.js (38 non-EVM chains: UTXO/Cosmos/Move/SUI/TRON/PI/etc.)
 *   - native_relayer.js (SVM/NEAR/TON/PVM/StarkNet — spawns chains/<vm>/execute.ts)
 *
 * This is the SINGLE non-EVM relayer. Together with relayer.js (EVM), it covers
 * all registry chains (config/chain_registry.json) across their VM families.
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
//
// CHAIN-ID NAMESPACE (canonical migration, PURGE-2 follow-up): every chain
// that exists in the canonical registry (config/chain_registry.json — single
// source of truth per P3-CONSOLIDATE, validated by
// core/generated_chain_bindings.py + tests) now uses its canonical chainId
// here: btc 21000 (was 2000), ltc 21004 (2010), doge 21003 (2020),
// dash 21005 (2030), cosmos-hub 10000 (4001), kava 10014 (4002),
// injective 10004 (4003), sei 10005 (4004), dydx 10006 (4005),
// initia 10015 (4006), osmosis 10001 (4007), neutron 10018 (4008),
// celestia 10003 (4009), terra 10009 (4010), aptos 20000 (5001),
// movement 20200 (5002), sui 20100 (6001), tron 26000 (7001),
// xrpl 31000 (8100), hedera 28000 (8300), vechain 29000 (8400),
// stellar 27000 (8800), multiversx 32000 (9000), waves 30000 (9200).
// algo 8200 and cardano 9400 already matched canonical. The NATIVE-VM half
// (NATIVE_VMS → chains/<vm>/execute.ts) always used canonical ids, so both
// code paths now agree and FAISS chain_id keys join the registry/rust
// indexers. Off-registry chains keep their local ids, documented below.
//
// Migration safety (reviewed before re-keying): this relayer persists no
// state keyed by chainId — the only state file (/tmp/trion_non_evm_relayer_
// latest.json) records per-chain results by chain KEY (name), the memo and
// signal hashes do not include the chainId, and previously pushed FAISS
// block-proof vectors are SYNTHETIC liveness attestations that naturally
// re-ingest under canonical ids on the next cycle (no dedup ledger to
// reset).
//
// ═══════════════════════════════════════════════════════════════════════════

const EXTENDED_CHAINS = [
  // UTXO chains (5) — canonical ids: 21000/21004/21003/21005
  { key: "btc",       name: "Bitcoin",      chainId: 21000, family: "UTXO",  rpc: "https://blockstream.info/api" },
  { key: "ltc",       name: "Litecoin",     chainId: 21004, family: "UTXO",  rpc: "https://litecoinblockexplorer.net/api" },
  { key: "doge",      name: "Dogecoin",     chainId: 21003, family: "UTXO",  rpc: "https://dogeblocks.com/api" },
  { key: "dash",      name: "Dash",         chainId: 21005, family: "UTXO",  rpc: "https://insight.dash.org/api" },
  // Cosmos chains (11) — canonical 10000-series ids
  { key: "cosmos-hub",name: "Cosmos Hub",   chainId: 10000, family: "COSMOS",rpc: "https://lcd.cosmos.network" },
  { key: "kava",      name: "Kava",         chainId: 10014, family: "COSMOS",rpc: "https://lcd.kava.io" },
  { key: "injective", name: "Injective",    chainId: 10004, family: "COSMOS",rpc: "https://lcd.injective.network" },
  { key: "sei",       name: "Sei Network",  chainId: 10005, family: "COSMOS",rpc: "https://lcd.sei-apis.com" },
  { key: "dydx",      name: "dYdX Chain",   chainId: 10006, family: "COSMOS",rpc: "https://lcd.dydx.exchange" },
  { key: "initia",    name: "Initia",       chainId: 10015, family: "COSMOS",rpc: "https://lcd.initia.xyz" },
  { key: "osmosis",   name: "Osmosis",      chainId: 10001, family: "COSMOS",rpc: "https://lcd.osmosis.zone" },
  { key: "neutron",   name: "Neutron",      chainId: 10018, family: "COSMOS",rpc: "https://lcd.neutron.org" },
  { key: "celestia",  name: "Celestia",     chainId: 10003, family: "COSMOS",rpc: "https://lcd.celestia.org" },
  { key: "terra",     name: "Terra Classic",chainId: 10009, family: "COSMOS",rpc: "https://lcd.terra.dev" },
  // provenance: NOT in the canonical 129-chain registry — legacy local id kept
  { key: "provenance",name: "Provenance",   chainId: 4011,  family: "COSMOS",rpc: "https://lcd.provenance.io" },
  // Move VM (2) — canonical 20000/20200
  { key: "aptos",     name: "Aptos",        chainId: 20000, family: "MOVE",  rpc: "https://fullnode.mainnet.aptoslabs.com" },
  { key: "movement",  name: "Movement",     chainId: 20200, family: "MOVE",  rpc: "https://mainnet.movementnetwork.xyz" },
  // Other L1s
  { key: "sui",       name: "Sui",          chainId: 20100, family: "SUI",   rpc: "https://fullnode.mainnet.sui.io" },
  { key: "tron",      name: "TRON",         chainId: 26000, family: "TVM",   rpc: "https://api.trongrid.io" },
  // pi: not in the canonical registry (trion-pi crate indexes Stellar as 27000) — local id kept
  { key: "pi",        name: "Pi Network",   chainId: 8001,  family: "MVM",   rpc: "https://horizon.stellar.org" },
  { key: "xrpl",      name: "XRP Ledger",   chainId: 31000, family: "XRPL",  rpc: "https://xrplcluster.com" },
  // algo 8200 / cardano 9400 already are the canonical registry ids
  { key: "algo",      name: "Algorand",     chainId: 8200,  family: "AVM",   rpc: "https://mainnet-api.algonode.cloud" },
  { key: "hedera",    name: "Hedera",       chainId: 28000, family: "HBAR",  rpc: "https://mainnet-public.mirrornode.hedera.com" },
  { key: "vechain",   name: "VeChain",      chainId: 29000, family: "VET",   rpc: "https://mainnet.vechain.org" },
  // kadena/icp/bittensor/flow/zilliqa/layerzero: not in the canonical 129-chain
  // registry (no genesis-walkable free API or not standalone L1s) — local ids kept
  { key: "kadena",    name: "Kadena",       chainId: 8500,  family: "CHAINWEB",rpc: "https://api.chainweb.com" },
  { key: "icp",       name: "Internet Computer",chainId: 8600, family: "WASM", rpc: "https://ic0.app" },
  { key: "bittensor", name: "Bittensor",    chainId: 8700,  family: "WASM",  rpc: "https://taostats.io/api" },
  { key: "stellar",   name: "Stellar",      chainId: 27000, family: "STELLAR",rpc: "https://horizon.stellar.org" },
  { key: "flow",      name: "Flow",         chainId: 8900,  family: "CADENCE",rpc: "https://rest-mainnet.onflow.org" },
  { key: "multiversx",name: "MultiversX",   chainId: 32000, family: "WASM",  rpc: "https://api.multiversx.com" },
  { key: "zilliqa",   name: "Zilliqa",      chainId: 9100,  family: "LLVM",  rpc: "https://api.zilliqa.com" },
  { key: "waves",     name: "Waves",        chainId: 30000, family: "WAVES", rpc: "https://nodes.wavesnodes.com" },
  { key: "layerzero", name: "LayerZero",    chainId: 9300,  family: "OMNI",  rpc: "https://api.layerzero.network" },
  { key: "cardano",   name: "Cardano",      chainId: 9400,  family: "EUTXO", rpc: "https://api.koios.rest" },
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
    if (!res.ok) {
      // audit fix (REL-1): was permissive (proceed on unreachable). relayer.js
      // correctly halts fail-closed in the same situation — if the relayer
      // cannot confirm the oracle's health, publishing on-chain risks
      // propagating signals from a degraded oracle. Both relayers now share
      // the same safety polarity.
      console.warn(`[SELF-HALT] /api/v1/self returned HTTP ${res.status} — HALTING this cycle (fail-closed)`);
      return true;
    }
    const data = await res.json();
    return data?.status === "SILENCED";
  } catch (e) {
    // audit fix (REL-1): unreachable oracle → halt (was: proceed).
    console.warn(`[SELF-HALT] could not reach /api/v1/self (${e?.message || e}) — HALTING this cycle (fail-closed)`);
    return true;
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
  // AUDIT FIX (REL-2) — HONEST PROVENANCE LABELING:
  // The 128-dim features below are SYNTHETIC: derived from sha256 of
  // (chain, blockInfo, time) — NOT from real on-chain behavioral data.
  // The block height/label IS real (fetchLatestBlock), and the vector shape
  // (9+9-complement+9-cross+4-stats+32 hash-derived) follows the BH feature
  // layout, but no transaction-level behavior is observed in this mode.
  // Downstream consumers MUST be able to filter these vectors — the payload
  // now carries data_provenance: "SYNTHETIC_BLOCK_PROOF" and each vector is
  // tagged synthetic=true. event_type stays 0 (TRANSFER) only as a schema
  // placeholder; these are liveness attestations, not behavioral events.
  //
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
    // audit fix (REL-2): provenance marker so synthetic block-proof vectors
    // are distinguishable from real behavioral-indexer vectors downstream.
    data_provenance: "SYNTHETIC_BLOCK_PROOF",
    synthetic: true,
    provenance_note: "features derived from sha256(chain:block:time) — block height is real, behavioral features are synthetic liveness attestations (no tx-level observation)",
    vectors: [{
      entity_id: entity,
      synthetic: true,             // per-vector marker for FAISS consumers
      data_provenance: "SYNTHETIC_BLOCK_PROOF",
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
      event_type: 0,               // placeholder — synthetic attestation, NOT a real TRANSFER event
      sense_hex: seedHash,
      antisense_hex: crypto.createHash("sha256").update(seed + ":antisense").digest("hex"),
      // NOTE: sense/antisense here do NOT satisfy the canonical dual-strand
      // invariant (sense XOR antisense == complement(sense)); they are seed
      // commitments for dedup only. Canonical BHs come from indexers/crates/*.
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
  // audit fix (REL-2): one honest startup disclosure — block-proof mode vectors
  // are synthetic liveness attestations (see pushBlockProof provenance labels).
  log(`Extended chain relayer started — ${EXTENDED_CHAINS.length} chains, poll=${EXTENDED_POLL}ms`);
  log(`  NOTE: chains without keys run in SYNTHETIC BLOCK-PROOF mode — features are`);
  log(`       hash-derived attestations tagged data_provenance=SYNTHETIC_BLOCK_PROOF,`);
  log(`       not transaction-level behavioral events (see audit fix REL-2).`);
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
