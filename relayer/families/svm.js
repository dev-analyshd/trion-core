/**
 * TRION SVM Family Relayer (Solana)
 * =================================
 *
 * VM family: SVM — Solana Mainnet, Solana Devnet, Solana Testnet
 * (per config/chain_registry.json).
 *
 * Two paths, picked per cycle:
 *   1. Native signing path (chains/svm/execute.ts) — if SOLANA_RELAYER_PRIVATE_KEY
 *      or SVM_PRIVATE_KEY_B58 is set, spawn the native executor which sends
 *      real signed Solana transactions.
 *   2. Block-proof fallback — pushes a SYNTHETIC liveness attestation vector
 *      to FAISS (see common.pushBlockProof provenance labels).
 *
 * Usage:
 *   node relayer/families/svm.js --dry-run         (default — block-proof only)
 *   SOLANA_RELAYER_PRIVATE_KEY=... node relayer/families/svm.js --live
 */

import { runFamily } from "./_template.js";

export const FAMILY = "SVM";

export function loadChains(reg) {
  return (reg.chains || []).filter(c => (c.vm || "").toUpperCase() === "SVM");
}

export const start = (opts) => runFamily({
  family: FAMILY,
  loadChains,
  nativeVmCwd: "chains/svm",
  nativeEnvBuilder: () => {
    const k = process.env.SOLANA_RELAYER_PRIVATE_KEY || process.env.SVM_PRIVATE_KEY_B58;
    if (!k) return null;
    return { SVM_PRIVATE_KEY_B58: k };
  },
  pollMs: parseInt(process.env.NATIVE_CYCLE_SLEEP_MS || "600000", 10),
  opts,
});

const isMain = import.meta.url === `file://${process.argv[1]}`;
if (isMain) {
  start().catch(e => {
    console.error("svm relayer fatal:", e);
    process.exit(1);
  });
}
