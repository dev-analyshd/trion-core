/**
 * TRION TRON Family Relayer
 * =========================
 * VM family: TRON — Tron Mainnet, Tron Shasta.
 *
 * Block-proof mode by default. Native signing via tronweb is in the
 * dependency tree but no chains/tron/execute.ts is wired through this
 * module yet.
 *
 * Usage:
 *   node relayer/families/tron.js --dry-run
 */

import { runFamily } from "./_template.js";

export const FAMILY = "TRON";

export function loadChains(reg) {
  return (reg.chains || []).filter(c => (c.vm || "").toUpperCase() === "TRON");
}

export const start = (opts) => runFamily({
  family: FAMILY,
  loadChains,
  nativeVmCwd: null,
  nativeEnvBuilder: null,
  pollMs: parseInt(process.env.EXTENDED_POLL_INTERVAL_MS || "90000", 10),
  opts,
});

const isMain = import.meta.url === `file://${process.argv[1]}`;
if (isMain) {
  start().catch(e => {
    console.error("tron relayer fatal:", e);
    process.exit(1);
  });
}
