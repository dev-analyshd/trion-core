/**
 * TRION VeChain Family Relayer
 * ============================
 * VM family: VECHAIN — Vechain (single chain).
 *
 * Block-proof mode by default. Native signing via @vechain/ethers is not
 * wired through this module yet (VeChain is EVM-compatible at the JSON-RPC
 * level — see chains/vechain/ for the indexer).
 *
 * Usage:
 *   node relayer/families/vechain.js --dry-run
 */

import { runFamily } from "./_template.js";

export const FAMILY = "VECHAIN";

export function loadChains(reg) {
  return (reg.chains || []).filter(c => (c.vm || "").toUpperCase() === "VECHAIN");
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
    console.error("vechain relayer fatal:", e);
    process.exit(1);
  });
}
