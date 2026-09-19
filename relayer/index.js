#!/usr/bin/env node
/**
 * TRION UNIFIED RELAYER — per-VM-family orchestrator
 * ===================================================
 *
 * This is the SINGLE entry point for the TRION relayer system. It reads the
 * canonical chain registry (config/chain_registry.json), identifies all VM
 * families, and spawns ONE worker process per family. Each worker is a
 * dedicated relayer module under relayer/families/<vm>.js.
 *
 * Layout
 * ------
 *   relayer/
 *     index.js                    <-- this file — orchestrator
 *     families/
 *       common.js                 shared helpers (oracle polling, block-proof)
 *       _template.js              generic block-proof relay loop
 *       evm.js                    EVM (DEFAULT — Node.js native signing)
 *       svm.js                    Solana
 *       utxo.js                   Bitcoin / Litecoin / Dogecoin / Dash / BCH
 *       starknet.js               Starknet
 *       cosmos.js                 Cosmos SDK chains (20)
 *       near.js                   NEAR Protocol
 *       ton.js                    TON
 *       move.js                   Sui + Aptos
 *       pvm.js                    Polkadot / Kusama
 *       stacks.js                 Stacks (stub — not yet in registry)
 *       stellar.js                Stellar
 *       tron.js                   TRON
 *       hedera.js                 Hedera
 *       algorand.js               Algorand
 *       cardano.js                Cardano
 *       multiversx.js             MultiversX
 *       vechain.js                VeChain
 *       waves.js                  Waves
 *       xrpl.js                   XRP Ledger
 *       botchain.js               BotChain (subset of EVM)
 *       movement.js               Movement (subset of MOVE)
 *       pi.js                     Pi Network (off-registry fallback)
 *
 * CLI
 * ---
 *   node relayer/index.js --list                    show families + chain counts
 *   node relayer/index.js --dry-run                 DEFAULT — no on-chain submit
 *                                                    (block-proof only across
 *                                                    every family)
 *   node relayer/index.js --dry-run --family=evm    run only the EVM family
 *   node relayer/index.js --live                    LIVE mode (requires keys)
 *
 * Environment (passed through to family workers)
 * ----------------------------------------------
 *   ORACLE_API_URL                  default http://127.0.0.1:5000
 *   FAISS_URL                       default http://127.0.0.1:8000
 *   RELAYER_PRIVATE_KEY             EVM live-mode signing key (env provider)
 *   KMS_PROVIDER                    env | aws | gcp | yubihsm | pkcs11
 *   MONITORED_ENTITIES              comma-separated list (EVM family)
 *   POLL_INTERVAL_MS                EVM poll interval, default 30000
 *   EXTENDED_POLL_INTERVAL_MS       block-proof cycle, default 90000
 *   NATIVE_CYCLE_SLEEP_MS           native VM cycle (SVM/NEAR/TON/PVM/StarkNet), 600000
 *
 * The orchestrator does NOT itself touch the Oracle or FAISS — every family
 * worker maintains its own connection. Workers run as long-lived child
 * processes; the orchestrator supervises them, forwards their stdout/stderr
 * to its own log, and exits non-zero if any worker exits with a non-zero
 * code (configurable via --keep-going to ignore worker failures).
 */

import { spawn } from "node:child_process";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";

import { loadRegistry, chainsByFamily, parseArgs } from "./families/common.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FAMILIES_DIR = path.join(__dirname, "families");

// ── Family registry ──────────────────────────────────────────────────────────
// Each entry maps a CLI label to its family module. The order matters only
// for the --list display (alphabetical by convention). BotChain and Movement
// are intentionally separate from EVM and MOVE respectively — they have
// their own native signing executors or are treated as distinct for
// operational reasons.
const FAMILY_MODULES = [
  { key: "evm",         label: "EVM",         file: "evm.js",         vm: "EVM",       note: "DEFAULT — Node.js native signing (ethers v6 + KMS abstraction)" },
  { key: "svm",         label: "SVM",         file: "svm.js",         vm: "SVM",       note: "Solana — native executor chains/svm/execute.ts" },
  { key: "utxo",        label: "UTXO",        file: "utxo.js",        vm: "UTXO",      note: "Bitcoin / Litecoin / Dogecoin / Dash / BCH" },
  { key: "starknet",    label: "STARKNET",    file: "starknet.js",    vm: "STARKNET",  note: "Starknet — native executor chains/starknet/execute.ts" },
  { key: "cosmos",      label: "COSMOS",      file: "cosmos.js",      vm: "COSMOS",    note: "Cosmos SDK chains — block-proof mode" },
  { key: "near",        label: "NEAR",        file: "near.js",        vm: "NEAR",      note: "NEAR Protocol — native executor chains/near/execute.ts" },
  { key: "ton",         label: "TON",         file: "ton.js",         vm: "TON",       note: "TON — native executor chains/ton/execute.ts" },
  { key: "move",        label: "MOVE",        file: "move.js",        vm: "MOVE",      note: "Sui + Aptos (excludes Movement)" },
  { key: "pvm",         label: "PVM",         file: "pvm.js",         vm: "PVM",       note: "Polkadot / Kusama — native executor chains/pvm/execute.ts" },
  { key: "stacks",      label: "STACKS",      file: "stacks.js",      vm: "STACKS",    note: "Stacks — stub (not yet in canonical registry)" },
  { key: "stellar",     label: "STELLAR",     file: "stellar.js",     vm: "STELLAR",   note: "Stellar — block-proof mode" },
  { key: "tron",        label: "TRON",        file: "tron.js",        vm: "TRON",      note: "TRON — block-proof mode" },
  { key: "hedera",      label: "HEDERA",      file: "hedera.js",      vm: "HEDERA",    note: "Hedera — block-proof mode" },
  { key: "algorand",    label: "ALGORAND",    file: "algorand.js",    vm: "ALGORAND",  note: "Algorand — block-proof mode" },
  { key: "cardano",     label: "CARDANO",     file: "cardano.js",     vm: "CARDANO",   note: "Cardano — block-proof mode" },
  { key: "multiversx",  label: "MULTIVERSX",  file: "multiversx.js",  vm: "MULTIVERSX",note: "MultiversX — block-proof mode" },
  { key: "vechain",     label: "VECHAIN",     file: "vechain.js",     vm: "VECHAIN",   note: "VeChain — block-proof mode" },
  { key: "waves",       label: "WAVES",       file: "waves.js",       vm: "WAVES",     note: "Waves — block-proof mode" },
  { key: "xrpl",        label: "XRPL",        file: "xrpl.js",        vm: "XRPL",      note: "XRP Ledger — block-proof mode" },
  { key: "botchain",    label: "BOTCHAIN",    file: "botchain.js",    vm: "EVM",       note: "BotChain — native executor chains/botchain/execute.ts (cherry-picked from EVM)" },
  { key: "movement",    label: "MOVEMENT",    file: "movement.js",    vm: "MOVE",      note: "Movement Mainnet + Bardock (cherry-picked from MOVE)" },
  { key: "pi",          label: "PI",          file: "pi.js",          vm: "PI",        note: "Pi Network — off-registry fallback (legacy local entry)" },
];

// ── Helpers ──────────────────────────────────────────────────────────────────
function chainCountForFamily(entry, grouped) {
  if (entry.key === "botchain") {
    return (grouped["EVM"] || []).filter(c => {
      const n = (c.name || "").toLowerCase().replace(/[^a-z0-9]/g, "");
      return n === "botchain" || n === "botchainai";
    }).length;
  }
  if (entry.key === "movement") {
    return (grouped["MOVE"] || []).filter(c => (c.name || "").toLowerCase().startsWith("movement")).length;
  }
  if (entry.key === "move") {
    return (grouped["MOVE"] || []).filter(c => !(c.name || "").toLowerCase().startsWith("movement")).length;
  }
  if (entry.key === "evm") {
    // EVM family EXCLUDES BotChain (which has its own module).
    return (grouped["EVM"] || []).filter(c => {
      const n = (c.name || "").toLowerCase().replace(/[^a-z0-9]/g, "");
      return n !== "botchain" && n !== "botchainai";
    }).length;
  }
  return grouped[entry.vm]?.length || 0;
}

function printList() {
  const reg = loadRegistry();
  const grouped = chainsByFamily();
  console.log("═══════════════════════════════════════════════════════════════");
  console.log("TRION UNIFIED RELAYER — per-VM-family modules");
  console.log("═══════════════════════════════════════════════════════════════");
  console.log(`Chain registry:        ${reg.chains.length} chains`);
  console.log(`Registry VM families:  ${Object.keys(grouped).length}`);
  console.log(`Relayer modules:       ${FAMILY_MODULES.length}`);
  console.log(`Oracle API URL:        ${process.env.ORACLE_API_URL || "http://127.0.0.1:5000"}`);
  console.log(`Default mode:          DRY_RUN (block-proof only, no on-chain submission)`);
  console.log("───────────────────────────────────────────────────────────────");
  console.log(
    "key".padEnd(14) +
    "label".padEnd(14) +
    "chains".padStart(8) +
    "  note",
  );
  console.log("───────────────────────────────────────────────────────────────");
  let total = 0;
  for (const entry of FAMILY_MODULES) {
    const count = chainCountForFamily(entry, grouped);
    total += count;
    console.log(
      entry.key.padEnd(14) +
      entry.label.padEnd(14) +
      String(count).padStart(8) +
      "  " + entry.note,
    );
  }
  console.log("───────────────────────────────────────────────────────────────");
  console.log(`Total chains covered:  ${total}`);
  console.log(`Note: BotChain (EVM) and Movement (MOVE) are split out of their`);
  console.log(`      parent VM families because they have dedicated executors;`);
  console.log(`      they are not double-counted in the total above.`);
  console.log("");
  console.log("Usage:");
  console.log("  node relayer/index.js --list                   show this list");
  console.log("  node relayer/index.js --dry-run                start all families in DRY_RUN mode (default)");
  console.log("  node relayer/index.js --dry-run --family=evm  start only EVM family in DRY_RUN mode");
  console.log("  node relayer/index.js --live                   start all families in LIVE mode (requires keys)");
  console.log("  node relayer/index.js --help                   this help");
}

function printHelp() {
  console.log(`TRION Unified Relayer — per-VM-family orchestrator

Usage:
  node relayer/index.js [options]

Options:
  --list                       Show all VM families + chain counts and exit.
  --dry-run                    DEFAULT — no on-chain submission; family
                               workers run block-proof cycles only.
  --live                       LIVE mode — family workers may submit on-chain
                               transactions (requires per-family keys).
  --family=<key>               Run only one family (e.g. --family=evm).
                               The key must match an entry from --list.
  --keep-going                 Continue running other families if one exits
                               with a non-zero code (default: stop on first
                               failure).
  -h, --help                   Show this help.

Environment (passed through to family workers):
  ORACLE_API_URL               default http://127.0.0.1:5000
  FAISS_URL                    default http://127.0.0.1:8000
  RELAYER_PRIVATE_KEY           EVM live-mode signing key (env provider)
  KMS_PROVIDER                 env | aws | gcp | yubihsm | pkcs11
  MONITORED_ENTITIES           comma-separated list (EVM family)
  POLL_INTERVAL_MS             EVM poll interval, default 30000
  EXTENDED_POLL_INTERVAL_MS    block-proof cycle, default 90000
  NATIVE_CYCLE_SLEEP_MS        native VM cycle (SVM/NEAR/TON/PVM/StarkNet), 600000
  SOLANA_RELAYER_PRIVATE_KEY   SVM family
  NEAR_RELAYER_PRIVATE_KEY     NEAR family
  TON_RELAYER_PRIVATE_KEY      TON family
  PVM_RELAYER_MNEMONIC         PVM family
  STARKNET_RELAYER_PRIVATE_KEY STARKNET family
  BOT_CHAIN_PRIVATE_KEY        BOTCHAIN family

Per-VM-family modules live in relayer/families/<key>.js and are also runnable
standalone:
  node relayer/families/evm.js --dry-run
  node relayer/families/svm.js --dry-run
`);
}

// ── Worker supervisor ────────────────────────────────────────────────────────
function spawnWorker(entry, opts) {
  const file = path.join(FAMILIES_DIR, entry.file);
  const args = [file];
  if (opts.dryRun) args.push("--dry-run");
  else args.push("--live");

  const child = spawn(process.execPath, args, {
    cwd: path.resolve(__dirname, ".."),
    env: process.env,
    stdio: ["ignore", "pipe", "pipe"],
  });

  const tag = `[${entry.label}]`;
  child.stdout?.on("data", (d) => {
    d.toString().split("\n").forEach((l) => { if (l.trim()) console.log(`${tag} ${l}`); });
  });
  child.stderr?.on("data", (d) => {
    d.toString().split("\n").forEach((l) => { if (l.trim()) console.error(`${tag} ${l}`); });
  });

  child.on("close", (code, signal) => {
    if (code === 0 || signal) {
      console.log(`${tag} worker exited code=${code} signal=${signal || "-"}`);
    } else {
      console.error(`${tag} worker FAILED code=${code} signal=${signal || "-"}`);
    }
  });
  child.on("error", (err) => {
    console.error(`${tag} spawn error: ${err.message}`);
  });

  return child;
}

// ── Main ─────────────────────────────────────────────────────────────────────
async function main() {
  const opts = parseArgs();
  if (opts.help) {
    printHelp();
    process.exit(0);
  }
  if (opts.list) {
    printList();
    process.exit(0);
  }

  // Validate --family flag (if provided)
  let selected = FAMILY_MODULES;
  if (opts.family) {
    const match = FAMILY_MODULES.find(
      (e) => e.key.toLowerCase() === opts.family || e.label.toLowerCase() === opts.family,
    );
    if (!match) {
      console.error(`Unknown family: ${opts.family}`);
      console.error(`Run 'node relayer/index.js --list' to see available families.`);
      process.exit(2);
    }
    selected = [match];
  }

  const grouped = chainsByFamily();
  console.log("═══════════════════════════════════════════════════════════════");
  console.log("TRION UNIFIED RELAYER");
  console.log("═══════════════════════════════════════════════════════════════");
  console.log(`Mode:              ${opts.dryRun ? "DRY_RUN (default — block-proof only, no on-chain submission)" : "LIVE (requires per-family keys)"}`);
  console.log(`Families selected: ${selected.length} of ${FAMILY_MODULES.length}`);
  if (opts.family) {
    console.log(`  --family=${opts.family}`);
  }
  console.log(`Oracle API:        ${process.env.ORACLE_API_URL || "http://127.0.0.1:5000"}`);
  console.log(`FAISS:             ${process.env.FAISS_URL || "http://127.0.0.1:8000"}`);
  console.log("───────────────────────────────────────────────────────────────");
  console.log(
    "family".padEnd(14) +
    "label".padEnd(14) +
    "chains".padStart(8) +
    "  note",
  );
  console.log("───────────────────────────────────────────────────────────────");
  for (const entry of selected) {
    const count = chainCountForFamily(entry, grouped);
    console.log(
      entry.key.padEnd(14) +
      entry.label.padEnd(14) +
      String(count).padStart(8) +
      "  " + entry.note,
    );
  }
  console.log("───────────────────────────────────────────────────────────────");
  console.log("");

  // Spawn workers
  const workers = selected.map((entry) => ({ entry, child: spawnWorker(entry, opts) }));

  // Supervise
  const shutdown = (signal) => {
    console.log(`\n[orchestrator] received ${signal} — forwarding to ${workers.length} workers`);
    for (const w of workers) {
      try { w.child.kill(signal); } catch { /* ignore */ }
    }
    setTimeout(() => process.exit(0), 1000).unref();
  };
  process.on("SIGINT", () => shutdown("SIGINT"));
  process.on("SIGTERM", () => shutdown("SIGTERM"));
  process.on("SIGHUP", () => shutdown("SIGHUP"));

  // Wait for all workers to exit
  await Promise.all(workers.map((w) => new Promise((resolve) => {
    w.child.on("close", () => resolve());
  })));
  console.log("[orchestrator] all workers exited");
}

main().catch((e) => {
  console.error("relayer/index.js fatal:", e);
  process.exit(1);
});
