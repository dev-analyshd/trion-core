/**
 * TRION PVM Family Relayer (Polkadot / Kusama)
 * ============================================
 * VM family: PVM — Polkadot, Polkadot Westend, Kusama.
 *
 * Two paths:
 *   1. Native signing (chains/pvm/execute.ts) — requires PVM_RELAYER_MNEMONIC
 *      or DOT_MNEMONIC.
 *   2. Block-proof fallback.
 *
 * Usage:
 *   node relayer/families/pvm.js --dry-run
 *   PVM_RELAYER_MNEMONIC="..." node relayer/families/pvm.js --live
 */

import { runFamily } from "./_template.js";

export const FAMILY = "PVM";

export function loadChains(reg) {
  return (reg.chains || []).filter(c => (c.vm || "").toUpperCase() === "PVM");
}

export const start = (opts) => runFamily({
  family: FAMILY,
  loadChains,
  nativeVmCwd: "chains/pvm",
  nativeEnvBuilder: () => {
    const m = process.env.PVM_RELAYER_MNEMONIC || process.env.DOT_MNEMONIC;
    if (!m) return null;
    return { DOT_MNEMONIC: m };
  },
  pollMs: parseInt(process.env.NATIVE_CYCLE_SLEEP_MS || "600000", 10),
  opts,
});

const isMain = import.meta.url === `file://${process.argv[1]}`;
if (isMain) {
  start().catch(e => {
    console.error("pvm relayer fatal:", e);
    process.exit(1);
  });
}
