/**
 * TRION Algorand Family Relayer
 * ==============================
 * VM family: ALGORAND — Algorand, Algorand Testnet.
 *
 * Block-proof mode by default. Native signing via algosdk is not wired
 * through this module yet.
 *
 * Usage:
 *   node relayer/families/algorand.js --dry-run
 */

import { runFamily } from "./_template.js";

export const FAMILY = "ALGORAND";

export function loadChains(reg) {
  return (reg.chains || []).filter(c => (c.vm || "").toUpperCase() === "ALGORAND");
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
    console.error("algorand relayer fatal:", e);
    process.exit(1);
  });
}
