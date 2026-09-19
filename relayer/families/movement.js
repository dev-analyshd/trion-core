/**
 * TRION Movement Family Relayer
 * ==============================
 * VM family: MOVE (subset — Movement Mainnet + Movement Bardock).
 *
 * These chains share the Move VM with Sui + Aptos but are treated as a
 * distinct family for relayer purposes because they have their own
 * indexer/signing pipeline (chains/movement/* — pending). Block-proof mode
 * by default.
 *
 * Usage:
 *   node relayer/families/movement.js --dry-run
 */

import { runFamily } from "./_template.js";

export const FAMILY = "MOVEMENT";

export function loadChains(reg) {
  return (reg.chains || []).filter(c => {
    if ((c.vm || "").toUpperCase() !== "MOVE") return false;
    return (c.name || "").toLowerCase().startsWith("movement");
  });
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
    console.error("movement relayer fatal:", e);
    process.exit(1);
  });
}
