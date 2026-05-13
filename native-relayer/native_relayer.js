#!/usr/bin/env node
/**
 * TRION Native VM Relayer
 * =======================
 * Periodically fires real, signed transactions on each non-EVM chain
 * (Solana Devnet, NEAR Testnet, TON Testnet, Polkadot Westend) using the
 * keys stored as Replit Secrets. Each cycle invokes the upstream
 * `execute.ts` script for one VM, which fires 5 real transactions, ingests
 * behavioral vectors into FAISS, and exits.
 *
 * Stored secret -> upstream env var mapping (with fallback to canonical names):
 *   SOLANA_RELAYER_PRIVATE_KEY  | SVM_PRIVATE_KEY_B58       -> SVM_PRIVATE_KEY_B58
 *   NEAR_RELAYER_PRIVATE_KEY    | NEAR_PRIVATE_KEY          -> NEAR_PRIVATE_KEY
 *   TON_RELAYER_PRIVATE_KEY     | TON_PRIVATE_KEY_HEX       -> TON_PRIVATE_KEY_HEX
 *   PVM_RELAYER_MNEMONIC        | DOT_MNEMONIC              -> DOT_MNEMONIC
 *   STARKNET_RELAYER_PRIVATE_KEY| STARKNET_PRIVATE_KEY      -> STARKNET_PRIVATE_KEY
 *
 * On testnet the same key signs both indexer ops and relayer ops, so the
 * canonical names are accepted as a fallback. If neither variant is set the
 * corresponding VM is skipped with a warning.
 */

// Resolve the first non-empty env var from a list of names.
function pickEnv(...names) {
  for (const n of names) {
    const v = process.env[n];
    if (v && v.trim()) return v;
  }
  return undefined;
}

import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT      = path.resolve(__dirname, "..");
const require   = createRequire(import.meta.url);

// Resolve tsx binary — prefer local node_modules, fall back to global npm install
function resolveTsx(cwd) {
  const local = path.join(ROOT, cwd, "node_modules", ".bin", "tsx");
  try {
    const { statSync } = require("fs");
    statSync(local);
    return local;
  } catch {
    // not found locally — use global
    const globalTsx = "/home/runner/workspace/.config/npm/node_global/bin/tsx";
    return globalTsx;
  }
}

const FAISS_URL        = process.env.FAISS_URL        || "http://127.0.0.1:8000";
const CYCLE_SLEEP_MS   = parseInt(process.env.NATIVE_CYCLE_SLEEP_MS || "600000", 10); // 10 min between cycles
const PER_VM_SLEEP_MS  = parseInt(process.env.NATIVE_PER_VM_SLEEP_MS || "30000", 10); // 30 s between VMs
const NEAR_ACCOUNT_ID  = process.env.NEAR_ACCOUNT_ID  || "trion.testnet";
const SOLANA_RPC       = process.env.SOLANA_RPC       || "https://api.devnet.solana.com";

// ── Key normalisation ────────────────────────────────────────────────────────
function svmKeyToBase58(raw) {
  if (!raw) return null;
  raw = raw.trim();
  // JSON byte array form: [12,34,...]
  if (raw.startsWith("[")) {
    try {
      const arr = JSON.parse(raw);
      if (!Array.isArray(arr) || arr.length !== 64)
        throw new Error(`expected 64-byte array, got len=${arr.length}`);
      // dynamic import to avoid hard dep at module load
      // (bs58 is installed in chains/svm; resolve from there)
      const bs58Mod = require(path.join(ROOT, "chains/svm/node_modules/bs58/index.js"));
      const bs58 = bs58Mod.default || bs58Mod;
      return bs58.encode(Uint8Array.from(arr));
    } catch (e) {
      console.error("[svm] failed to decode JSON key array:", e.message);
      return null;
    }
  }
  // already base58
  return raw;
}

function nearKey(raw) {
  if (!raw) return null;
  raw = raw.trim();
  // Accept both "ed25519:<key>" and bare "<key>"
  if (raw.startsWith("ed25519:")) return raw;
  return `ed25519:${raw}`;
}

function tonKey(raw) {
  if (!raw) return null;
  return raw.trim().replace(/^0x/, "");
}

function pvmMnemonic(raw) {
  if (!raw) return null;
  return raw.trim();
}

// ── VM definitions ───────────────────────────────────────────────────────────
const VMS = [
  {
    label: "SVM (Solana Devnet)",
    cwd:   "chains/svm",
    cmd:   [resolveTsx("chains/svm"), "execute.ts"],
    envBuilder: () => {
      const k = svmKeyToBase58(pickEnv("SOLANA_RELAYER_PRIVATE_KEY", "SVM_PRIVATE_KEY_B58"));
      if (!k) return null;
      return { SVM_PRIVATE_KEY_B58: k, SOLANA_RPC, FAISS_URL };
    },
  },
  {
    label: "NEAR Testnet",
    cwd:   "chains/near",
    cmd:   [resolveTsx("chains/near"), "execute.ts"],
    envBuilder: () => {
      const k = nearKey(pickEnv("NEAR_RELAYER_PRIVATE_KEY", "NEAR_PRIVATE_KEY"));
      if (!k) return null;
      return { NEAR_PRIVATE_KEY: k, NEAR_ACCOUNT_ID, FAISS_URL };
    },
  },
  {
    label: "TON Testnet",
    cwd:   "chains/ton",
    cmd:   [resolveTsx("chains/ton"), "execute.ts"],
    envBuilder: () => {
      const k = tonKey(pickEnv("TON_RELAYER_PRIVATE_KEY", "TON_PRIVATE_KEY_HEX"));
      if (!k) return null;
      return { TON_PRIVATE_KEY_HEX: k, TON_TESTNET: "true", FAISS_URL };
    },
  },
  {
    label: "PVM (Polkadot Westend)",
    cwd:   "chains/pvm",
    cmd:   [resolveTsx("chains/pvm"), "execute.ts"],
    envBuilder: () => {
      const m = pvmMnemonic(pickEnv("PVM_RELAYER_MNEMONIC", "DOT_MNEMONIC"));
      if (!m) return null;
      return { DOT_MNEMONIC: m, FAISS_URL };
    },
  },
  {
    label: "StarkNet Sepolia",
    cwd:   "chains/starknet",
    cmd:   [resolveTsx("chains/starknet"), "execute.ts"],
    envBuilder: () => {
      const k = (pickEnv("STARKNET_RELAYER_PRIVATE_KEY", "STARKNET_PRIVATE_KEY") ?? "").trim();
      if (!k) return null;
      const env = { STARKNET_PRIVATE_KEY: k, FAISS_URL };
      if (process.env.STARKNET_ACCOUNT_ADDRESS) env.STARKNET_ACCOUNT_ADDRESS = process.env.STARKNET_ACCOUNT_ADDRESS;
      return env;
    },
  },
];

// ── Runner ───────────────────────────────────────────────────────────────────
function runOnce(vm) {
  return new Promise((resolve) => {
    const env = vm.envBuilder();
    if (!env) {
      console.warn(`[${vm.label}] SKIP — required secret not set`);
      return resolve({ skipped: true });
    }
    const cwd = path.join(ROOT, vm.cwd);
    const child = spawn(vm.cmd[0], vm.cmd.slice(1), {
      cwd,
      env: { ...process.env, ...env, PATH: process.env.PATH },
      stdio: ["ignore", "pipe", "pipe"],
    });
    const tag = `[${vm.label}]`;
    child.stdout.on("data", d => process.stdout.write(`${tag} ${d}`));
    child.stderr.on("data", d => process.stderr.write(`${tag} ${d}`));
    child.on("exit", (code) => {
      console.log(`${tag} exit code ${code}`);
      resolve({ skipped: false, code });
    });
    child.on("error", (e) => {
      console.error(`${tag} spawn error: ${e.message}`);
      resolve({ skipped: false, code: -1, error: e.message });
    });
  });
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function main() {
  console.log("════════════════════════════════════════════════════════");
  console.log(" TRION Native VM Relayer — live signing every cycle");
  console.log("════════════════════════════════════════════════════════");
  console.log(` FAISS               : ${FAISS_URL}`);
  console.log(` Cycle sleep         : ${CYCLE_SLEEP_MS} ms`);
  console.log(` Per-VM stagger      : ${PER_VM_SLEEP_MS} ms`);
  console.log(` Configured VMs      : ${VMS.map(v => v.label).join(", ")}`);
  console.log(" Secrets present     :");
  console.log(`   SVM   : ${pickEnv("SOLANA_RELAYER_PRIVATE_KEY",  "SVM_PRIVATE_KEY_B58")   ? "yes" : "no"}`);
  console.log(`   NEAR  : ${pickEnv("NEAR_RELAYER_PRIVATE_KEY",    "NEAR_PRIVATE_KEY")      ? "yes" : "no"}`);
  console.log(`   TON   : ${pickEnv("TON_RELAYER_PRIVATE_KEY",     "TON_PRIVATE_KEY_HEX")   ? "yes" : "no"}`);
  console.log(`   PVM   : ${pickEnv("PVM_RELAYER_MNEMONIC",        "DOT_MNEMONIC")          ? "yes" : "no"}`);
  console.log(`   STK   : ${pickEnv("STARKNET_RELAYER_PRIVATE_KEY","STARKNET_PRIVATE_KEY")  ? "yes" : "no"}`);
  console.log("");

  let cycle = 0;
  while (true) {
    cycle += 1;
    console.log(`\n──── Cycle ${cycle} @ ${new Date().toISOString()} ────`);
    for (const vm of VMS) {
      await runOnce(vm);
      await sleep(PER_VM_SLEEP_MS);
    }
    console.log(`──── Cycle ${cycle} complete; sleeping ${CYCLE_SLEEP_MS / 1000}s ────`);
    await sleep(CYCLE_SLEEP_MS);
  }
}

main().catch(e => { console.error("native_relayer fatal:", e); process.exit(1); });
