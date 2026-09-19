/**
 * TRION XRPL Family Relayer
 * ==========================
 * VM family: XRPL — XRP Ledger (single chain).
 *
 * Block-proof mode by default. Native signing via xrpl.js is not wired
 * through this module yet.
 *
 * Usage:
 *   node relayer/families/xrpl.js --dry-run
 */

import { runFamily } from "./_template.js";

export const FAMILY = "XRPL";

export function loadChains(reg) {
  return (reg.chains || []).filter(c => (c.vm || "").toUpperCase() === "XRPL");
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
    console.error("xrpl relayer fatal:", e);
    process.exit(1);
  });
}
