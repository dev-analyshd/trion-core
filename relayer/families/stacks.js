/**
 * TRION Stacks Family Relayer
 * ============================
 * VM family: STACKS — Stacks (canonical id 5800 — pending registry addition).
 *
 * NOTE: The canonical chain registry (config/chain_registry.json) does not
 * yet carry a STACKS entry. The family module is wired up so when a Stacks
 * chain is added to the registry it will be picked up automatically; until
 * then the family reports 0 chains and exits cleanly.
 *
 * Block-proof mode by default. No native signing executor wired yet.
 *
 * Usage:
 *   node relayer/families/stacks.js --dry-run
 */

import { runFamily } from "./_template.js";

export const FAMILY = "STACKS";

export function loadChains(reg) {
  return (reg.chains || []).filter(c => (c.vm || "").toUpperCase() === "STACKS");
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
    console.error("stacks relayer fatal:", e);
    process.exit(1);
  });
}
