/**
 * TRION Relayer — shared helpers for per-VM-family modules
 * =======================================================
 *
 * Every per-VM-family relayer module (evm.js, svm.js, cosmos.js, ...) imports
 * from this file so that:
 *
 *   - Oracle polling + self-halt semantics are identical across families.
 *   - Signal validation is fail-closed everywhere (W3-M: no defaults).
 *   - Block-proof ingestion (the FAISS liveness attestation path) is shared
 *     by every family that does not yet have a native signing SDK wired up.
 *   - The retry helper and logging tag follow the same format.
 *
 * The intent is that this file is the SINGLE source of behavioural truth for
 * cross-cutting concerns; per-family modules only supply:
 *
 *     FAMILY           string  — VM family label (e.g. "EVM", "SVM")
 *     loadChains(reg) array   — list of chain descriptors for this family
 *     start(opts)     Promise — the family-specific relay loop
 *
 * This module is intentionally dependency-free at import time — fetchers,
 * validators, and FAISS pushers are exported as plain functions so family
 * modules can compose them however they like (solo dry-run, native signing,
 * block-proof mode, ...).
 *
 * Provenance — every block-proof vector pushed by this module is tagged:
 *   data_provenance: "SYNTHETIC_BLOCK_PROOF"
 *   synthetic:        true
 * See audit fix REL-2 in relayer_non_evm.js — these are liveness
 * attestations, NOT behavioural indexer events.
 */

import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";
import { createRequire } from "node:module";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..", "..");
const REGISTRY_PATH = path.join(ROOT, "config", "chain_registry.json");
const _require = createRequire(import.meta.url);

// ── Environment ──────────────────────────────────────────────────────────────
export const ORACLE_API_URL = process.env.ORACLE_API_URL || "http://127.0.0.1:5000";
export const FAISS_URL = process.env.FAISS_URL || "http://127.0.0.1:8000";
export const POLL_INTERVAL_MS = parseInt(process.env.POLL_INTERVAL_MS || "30000", 10);
export const EXTENDED_POLL_MS = parseInt(process.env.EXTENDED_POLL_INTERVAL_MS || "90000", 10);

// ── Logging ──────────────────────────────────────────────────────────────────
export function log(family, msg) {
  console.log(`[${new Date().toISOString()}] [${family}] ${msg}`);
}

// ── Registry loader ──────────────────────────────────────────────────────────
let _registryCache = null;
export function loadRegistry() {
  if (_registryCache) return _registryCache;
  try {
    _registryCache = JSON.parse(fs.readFileSync(REGISTRY_PATH, "utf-8"));
  } catch (e) {
    throw new Error(`common: cannot read chain registry at ${REGISTRY_PATH}: ${e.message}`);
  }
  return _registryCache;
}

/**
 * Group the canonical chain registry by VM family. Returns a map
 *   { EVM: [...chains], SVM: [...], COSMOS: [...], ... }
 * Each chain entry is augmented with a `family` field for convenience.
 */
export function chainsByFamily() {
  const reg = loadRegistry();
  const map = {};
  for (const c of reg.chains) {
    const vm = (c.vm || "UNKNOWN").toUpperCase();
    if (!map[vm]) map[vm] = [];
    map[vm].push({ ...c, family: vm });
  }
  return map;
}

/**
 * Resolve the canonical registry chains for a single VM family.
 * Optional `filter(chain)` lets a family module narrow further (e.g. the
 * botchain family cherry-picks the BotChain entry out of EVM).
 */
export function chainsForFamily(vmFamily, filter) {
  const all = chainsByFamily()[vmFamily.toUpperCase()] || [];
  return filter ? all.filter(filter) : all;
}

// ── CLI parsing ──────────────────────────────────────────────────────────────
export function parseArgs(argv = process.argv.slice(2)) {
  const opts = {
    dryRun: true,       // DEFAULT: dry-run (no on-chain submission)
    family: null,       // null = run all
    list: false,
    help: false,
  };
  for (const a of argv) {
    if (a === "--help" || a === "-h") opts.help = true;
    else if (a === "--list") opts.list = true;
    else if (a === "--dry-run") opts.dryRun = true;
    else if (a === "--live" || a === "--no-dry-run") opts.dryRun = false;
    else if (a.startsWith("--family=")) opts.family = a.slice("--family=".length).toLowerCase();
    else if (a.startsWith("--families=")) opts.family = a.slice("--families=".length).toLowerCase();
  }
  return opts;
}

// ── Signal validation (W3-M fail-closed) ─────────────────────────────────────
export function _num(v) {
  return typeof v === "number" && Number.isFinite(v);
}

export function validateSignal(signal) {
  if (!signal || typeof signal !== "object") return "oracle response is not an object";
  const coh = signal.coherence_score ?? signal.coherence ?? signal.signal_value;
  const thr = signal.threshold;
  if (!_num(coh)) return "coherence_score/coherence/signal_value missing or not a finite number";
  if (coh < 0 || coh > 1) return `coherence ${coh} out of range [0,1]`;
  if (!_num(thr)) return "threshold missing or not a finite number";
  if (thr <= 0 || thr > 1) return `threshold ${thr} out of range (0,1]`;
  return null;
}

export function signalFields(signal) {
  const coh = signal.coherence_score ?? signal.coherence ?? signal.signal_value;
  const thr = signal.threshold;
  return { coh, thr };
}

// ── Oracle polling ───────────────────────────────────────────────────────────
export async function fetchSignal(entity, timeoutMs = 8000) {
  try {
    const res = await fetch(
      `${ORACLE_API_URL}/api/v1/signal/${encodeURIComponent(entity)}`,
      { signal: AbortSignal.timeout(timeoutMs) },
    );
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

/**
 * Reflexive self-halt — every family consults the oracle's own /api/v1/self
 * before publishing. If TRION's own coherence has dropped below the SILENCE
 * threshold OR the oracle is unreachable, the family halts this cycle
 * (fail-closed — same polarity as relayer.js).
 */
export async function checkSelfHalt(family) {
  try {
    const res = await fetch(`${ORACLE_API_URL}/api/v1/self`, {
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) {
      log(family, `SELF-HALT: /api/v1/self returned HTTP ${res.status} — halting cycle (fail-closed)`);
      return true;
    }
    const data = await res.json();
    if (data?.status === "SILENCED") {
      log(family, `SELF-HALT: oracle status=SILENCED coherence=${data.coherence} threshold=${data.threshold} — halting cycle`);
      return true;
    }
    return false;
  } catch (e) {
    log(family, `SELF-HALT: cannot reach /api/v1/self (${e?.message || e}) — halting cycle (fail-closed)`);
    return true;
  }
}

// ── Retry helper (network/5xx only — never contract reverts) ──────────────────
const MAX_RETRIES = parseInt(process.env.RELAYER_MAX_RETRIES || "3", 10);
const RETRY_BASE_MS = parseInt(process.env.RELAYER_RETRY_BASE_MS || "500", 10);

function isRetryableError(err) {
  if (!err) return false;
  if (err.code === "ECONNABORTED" || err.code === "ETIMEDOUT" ||
      err.code === "ENOTFOUND" || err.code === "ECONNRESET") return true;
  const status = err.response?.status;
  if (status && status >= 500 && status < 600) return true;
  if (status === 429) return true;
  return false;
}

export async function withRetry(label, fn) {
  let lastErr = null;
  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    try {
      return await fn(attempt);
    } catch (e) {
      lastErr = e;
      if (!isRetryableError(e) || attempt === MAX_RETRIES) {
        if (attempt > 0) {
          console.warn(`  [${label}] giving up after ${attempt + 1} attempt(s): ${(e?.shortMessage || e?.message || String(e)).slice(0, 100)}`);
        }
        throw e;
      }
      const delay = RETRY_BASE_MS * Math.pow(2, attempt) + Math.floor(Math.random() * 200);
      console.warn(`  [${label}] attempt ${attempt + 1} failed (${(e?.shortMessage || e?.message || String(e)).slice(0, 80)}); retrying in ${delay}ms`);
      await new Promise(r => setTimeout(r, delay));
    }
  }
  throw lastErr;
}

// ── Block fetcher (best-effort — different chain RPCs return JSON differently) ─
export async function fetchLatestBlock(chain) {
  try {
    const res = await fetch(chain.rpc, { signal: AbortSignal.timeout(8000) });
    if (!res.ok) return null;
    const text = await res.text();
    try {
      const json = JSON.parse(text);
      return json?.height || json?.block_height || json?.latest_block_height ||
             json?.ledger?.sequence || json?.data?.height || json?.block?.header?.height || null;
    } catch {
      return text.slice(0, 64);
    }
  } catch {
    return null;
  }
}

// ── Block-proof FAISS ingestion ─────────────────────────────────────────────
/**
 * Build a 128-dim SYNTHETIC block-proof vector and push it to the FAISS
 * service. Used by every family that does not yet have a native signing
 * SDK wired up (UTXO, Cosmos, Move, Stellar, Hedera, Algorand, Cardano,
 * MultiversX, VeChain, Waves, XRPL, Tron, Pi, Stacks, PVM, NEAR, TON, SVM
 * block-proof fallback, etc.).
 *
 * Provenance — see header. Every vector is explicitly tagged:
 *   data_provenance: "SYNTHETIC_BLOCK_PROOF"
 *   synthetic:        true
 */
export async function pushBlockProof(family, chain, blockInfo, signal) {
  const entity = `${family.toLowerCase()}:${chain.key || chain.name}`;
  const seed = `${chain.key || chain.name}:${blockInfo}:${Date.now()}`;
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

  const chainId = chain.chainId ?? chain.chain_id ?? 0;
  const payload = {
    data_provenance: "SYNTHETIC_BLOCK_PROOF",
    synthetic: true,
    provenance_note: "features derived from sha256(chain:block:time) — block height is real, behavioural features are synthetic liveness attestations (no tx-level observation)",
    vectors: [{
      entity_id: entity,
      synthetic: true,
      data_provenance: "SYNTHETIC_BLOCK_PROOF",
      vector: features,
      magnitude: signal?.coherence ?? mean,
      entropy: mean,
      timestamp: Math.floor(Date.now() / 1000),
      bh_id: seedHash,
      block_num: parseInt(blockInfo) || 0,
      chain_id: chainId,
      chain_label: (chain.key || chain.name || family).toUpperCase(),
      vm_type: family.toUpperCase(),
      block_hash_hex: seedHash,
      event_type: 0,
      sense_hex: seedHash,
      antisense_hex: crypto.createHash("sha256").update(seed + ":antisense").digest("hex"),
    }],
    block_num: parseInt(blockInfo) || 0,
    block_features: features.slice(0, 9),
    block_phi: mean,
    chain_id: chainId,
    chain_label: (chain.key || chain.name || family).toUpperCase(),
    vm_type: family.toUpperCase(),
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

// ── State persistence ────────────────────────────────────────────────────────
export function persistState(family, state) {
  const file = path.join("/tmp", `trion_${family.toLowerCase()}_relayer_latest.json`);
  try {
    fs.writeFileSync(file, JSON.stringify({
      ...state,
      generated_at: new Date().toISOString(),
    }, null, 2));
  } catch { /* non-fatal */ }
}

// ── Native VM executor (for families that wrap chains/<vm>/execute.ts) ───────
export function resolveTsx() {
  const { statSync } = _require("fs");
  const candidates = [
    path.join(ROOT, "node_modules", ".bin", "tsx"),
    path.join(__dirname, "..", "node_modules", ".bin", "tsx"),
    path.join(__dirname, "node_modules", ".bin", "tsx"),
  ];
  for (const p of candidates) {
    try { statSync(p); return p; } catch { /* not there */ }
  }
  return "tsx";
}

/**
 * Spawn a single run of chains/<vm>/execute.ts. Returns the exit code.
 * If the cwd does not exist, returns -1 (treated as SKIP — non-fatal).
 */
export function runNativeVM(family, vmCwd, envOverrides = {}) {
  return new Promise((resolve) => {
    const cwd = path.join(ROOT, vmCwd);
    try { fs.statSync(cwd); } catch {
      log(family, `native VM dir missing: ${vmCwd} — SKIPPING (block-proof fallback may still run)`);
      return resolve({ skipped: true, code: -1 });
    }
    const tsx = resolveTsx();
    const child = spawn(tsx, ["execute.ts"], {
      cwd,
      env: { ...process.env, ...envOverrides },
      stdio: ["ignore", "pipe", "pipe"],
    });
    const tag = `[${family}]`;
    child.stdout?.on("data", (d) => d.toString().split("\n").forEach((l) => l.trim() && console.log(`${tag} ${l}`)));
    child.stderr?.on("data", (d) => d.toString().split("\n").forEach((l) => l.trim() && console.error(`${tag} ${l}`)));
    child.on("close", (code) => {
      log(family, `native VM exited code=${code}`);
      resolve({ skipped: false, code });
    });
    child.on("error", (err) => {
      log(family, `native VM spawn error: ${err.message}`);
      resolve({ skipped: false, error: err.message });
    });
  });
}
