#!/usr/bin/env node
/**
 * TRION Master Indexer — chain indexing orchestrator
 * ==================================================
 *
 * Single entry point for "index every chain, every VM" (BTCP Master Spec §2).
 *
 * Two indexing backends are orchestrated:
 *
 *   1. Rust indexer workspace (indexers/crates/trion-*) — continuous block
 *      streaming + canonical BH batching + FAISS ingest for 21 VM families.
 *      Built with `cargo build --release` inside indexers/.
 *
 *   2. Python genesis backfills (anima-service/genesis_backfill_*.py) —
 *      historical bootstrap from genesis for each chain family.
 *
 * Usage:
 *   node scripts/trion_master_indexer.mjs                 # start all Rust indexers
 *   node scripts/trion_master_indexer.mjs --list          # list indexed chains
 *   node scripts/trion_master_indexer.mjs --backfill      # run genesis backfills
 *   node scripts/trion_master_indexer.mjs --family svm    # single VM family
 *
 * Environment:
 *   TRION_INDEXER_BIN_DIR   — directory of compiled indexer binaries
 *                             (default: indexers/target/release)
 *   FAISS_URL               — FAISS ANIMA ingest endpoint
 *                             (default: http://127.0.0.1:8000)
 *   TRION_FAMILIES          — comma-separated family filter
 *
 * Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
 * License: CC0
 */

import { spawn } from "node:child_process";
import { existsSync, readdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const BIN_DIR =
  process.env.TRION_INDEXER_BIN_DIR || join(ROOT, "indexers", "target", "release");
const FAISS_URL = process.env.FAISS_URL || "http://127.0.0.1:8000";

// Canonical VM-family → indexer binary map (mirrors indexers/crates/*)
const FAMILIES = {
  evm:         { bin: "trion-evm",         chains: 55, note: "Ethereum + L2s + alt-EVM (EIP-155 IDs)" },
  svm:         { bin: "trion-svm",         chains: 1,  note: "Solana mainnet/devnet (chain 900/901)" },
  starknet:    { bin: "trion-starknet",    chains: 1,  note: "Cairo VM (chain 24000)" },
  sui:         { bin: "trion-sui",         chains: 1,  note: "Move VM — Sui (chain 20100)" },
  aptos:       { bin: "trion-aptos",       chains: 1,  note: "Move VM — Aptos (chain 20000)" },
  movement:    { bin: "trion-movement",    chains: 1,  note: "Move VM — Movement (chain 20200)" },
  near:        { bin: "trion-near",        chains: 1,  note: "WASM — NEAR (chain 23000)" },
  ton:         { bin: "trion-ton",         chains: 1,  note: "TVM — TON (chain 22000)" },
  tron:        { bin: "trion-tron",        chains: 1,  note: "TVM — TRON (chain 26000)" },
  utxo:        { bin: "trion-utxo",        chains: 4,  note: "BTC/LTC/DOGE/DASH (21000-series)" },
  cosmos:      { bin: "trion-cosmos",      chains: 6,  note: "Cosmos SDK (10000-series)" },
  pvm:         { bin: "trion-pvm",         chains: 1,  note: "Substrate — Polkadot (chain 25000)" },
  multiversx:  { bin: "trion-multiversx",  chains: 1,  note: "WASM — MultiversX (chain 32000)" },
  algorand:    { bin: "trion-algorand",    chains: 1,  note: "AVM — Algorand (chain 8200)" },
  cardano:     { bin: "trion-cardano",     chains: 1,  note: "eUTXO — Cardano (chain 9400)" },
  hedera:      { bin: "trion-hedera",      chains: 1,  note: "Hashgraph (chain 28000)" },
  stellar:     { bin: "trion-pi",          chains: 1,  note: "Stellar MVM (chain 27000)" },
  vechain:     { bin: "trion-vechain",     chains: 1,  note: "VeChainThor EVM (chain 29000)" },
  waves:       { bin: "trion-waves",       chains: 1,  note: "Waves RIDE (chain 30000)" },
  xrpl:        { bin: "trion-xrpl",        chains: 1,  note: "XRPL (chain 31000)" },
  botchain:    { bin: "trion-botchain",    chains: 1,  note: "TRION BOT Chain (chain 677)" },
};

// Python genesis backfills (historical bootstrap)
const BACKFILLS = [
  "genesis_backfill.py",            // EVM (Arbitrum)
  "genesis_backfill_utxo.py",       // BTC/LTC/DOGE/DASH
  "genesis_backfill_solana.py",
  "genesis_backfill_cosmos.py",
  "genesis_backfill_move.py",
  "genesis_backfill_near.py",
  "genesis_backfill_starknet.py",
  "genesis_backfill_polkadot.py",
  "genesis_backfill_ton.py",
  "genesis_backfill_sui.py",
  "genesis_backfill_tron.py",
  "genesis_backfill_xrpl.py",
  "genesis_backfill_algorand.py",
  "genesis_backfill_cardano.py",
  "genesis_backfill_hedera.py",
  "genesis_backfill_stellar.py",
  "genesis_backfill_vechain.py",
  "genesis_backfill_multiversx.py",
  "genesis_backfill_waves.py",
];

const args = process.argv.slice(2);
const flag = (name) => args.includes(name);
const familyFilter =
  (args.find((a) => a.startsWith("--family=")) || "").split("=")[1] ||
  process.env.TRION_FAMILIES ||
  null;

function listFamilies() {
  console.log("\nTRION Master Indexer — canonical chain coverage\n");
  console.log("  family        chains  indexer binary      note");
  console.log("  ────────────  ──────  ──────────────────  ─────────────────────────────");
  let total = 0;
  for (const [name, f] of Object.entries(FAMILIES)) {
    total += f.chains;
    const built = existsSync(join(BIN_DIR, f.bin));
    console.log(
      `  ${name.padEnd(13)} ${String(f.chains).padStart(4)}   ${(f.bin + (built ? " ✓" : " ✗")).padEnd(19)}  ${f.note}`
    );
  }
  console.log("  ────────────  ──────");
  console.log(`  ${Object.keys(FAMILIES).length} VM families, ${total} chains total`);
  console.log(`\n  Indexer binaries: ${BIN_DIR}`);
  console.log("  Build with: cd indexers && cargo build --release\n");
}

function startFamily(name) {
  const f = FAMILIES[name];
  const bin = join(BIN_DIR, f.bin);
  if (!existsSync(bin)) {
    console.error(`✗ ${name}: indexer binary not found at ${bin}`);
    console.error(`  Build first:  cd indexers && cargo build --release`);
    process.exitCode = 1;
    return null;
  }
  console.log(`→ starting ${name} indexer (${f.bin}) — ${f.note}`);
  const child = spawn(bin, [], {
    env: { ...process.env, FAISS_URL },
    stdio: ["ignore", "inherit", "inherit"],
  });
  child.on("exit", (code) =>
    console.log(`  ${name} indexer exited with code ${code}`)
  );
  return child;
}

function runBackfills() {
  const svc = join(ROOT, "anima-service");
  for (const script of BACKFILLS) {
    const path = join(svc, script);
    if (!existsSync(path)) {
      console.warn(`  ! missing backfill script: ${path}`);
      continue;
    }
    console.log(`→ backfill ${script}`);
    const child = spawn(process.executable || "python3", [path], {
      cwd: svc,
      stdio: "inherit",
    });
    child.on("exit", (code) => {
      if (code !== 0) console.warn(`  ! ${script} exited with code ${code}`);
    });
  }
}

// ── Main ─────────────────────────────────────────────────────────────────────
if (flag("--list")) {
  listFamilies();
} else if (flag("--backfill")) {
  runBackfills();
} else {
  const selected = familyFilter
    ? familyFilter.split(",").filter((f) => FAMILIES[f])
    : Object.keys(FAMILIES);
  if (familyFilter) {
    const missing = familyFilter.split(",").filter((f) => !FAMILIES[f]);
    if (missing.length) console.warn(`! unknown families ignored: ${missing}`);
  }
  console.log(`TRION Master Indexer — starting ${selected.length} indexer families`);
  console.log(`  FAISS ingest: ${FAISS_URL}\n`);
  const children = selected.map(startFamily).filter(Boolean);
  if (children.length === 0) {
    console.error("No indexers started — build the Rust workspace first.");
    process.exit(1);
  }
  const shutdown = () => {
    console.log("\nShutting down indexers…");
    for (const c of children) c.kill("SIGTERM");
    process.exit(0);
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}
