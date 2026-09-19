/**
 * TRION Cardano Family Relayer
 * =============================
 * VM family: CARDANO — Cardano, Cardano Preprod.
 *
 * Block-proof mode by default. Native signing via cardano-serialization-lib
 * is not wired through this module yet.
 *
 * Usage:
 *   node relayer/families/cardano.js --dry-run
 */

import { runFamily } from "./_template.js";

export const FAMILY = "CARDANO";

export function loadChains(reg) {
  return (reg.chains || []).filter(c => (c.vm || "").toUpperCase() === "CARDANO");
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
    console.error("cardano relayer fatal:", e);
    process.exit(1);
  });
}
