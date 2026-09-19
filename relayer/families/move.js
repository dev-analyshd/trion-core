/**
 * TRION Move Family Relayer (Sui, Aptos)
 * ======================================
 * VM family: MOVE — 4 chains: Aptos Mainnet, Aptos Testnet, Sui Mainnet,
 * Sui Testnet. (Movement Mainnet + Movement Bardock are handled by the
 * separate movement.js family module — they are MOVE VM but treated as a
 * distinct family for relayer purposes since they have a separate indexer.)
 *
 * Block-proof mode by default. Native signing paths exist for Sui
 * (@mysten/sui) and Aptos (@aptos-labs/ts-sdk) but no chains/move/execute.ts
 * is wired through this module — chains/sui/ and chains/aptos/ hold the
 * indexers.
 *
 * Usage:
 *   node relayer/families/move.js --dry-run
 */

import { runFamily } from "./_template.js";

export const FAMILY = "MOVE";

export function loadChains(reg) {
  // MOVE chains EXCLUDING Movement Mainnet + Movement Bardock (those go to
  // movement.js). This split is documented in the task spec — move.js
  // covers only Sui + Aptos.
  return (reg.chains || []).filter(c => {
    if ((c.vm || "").toUpperCase() !== "MOVE") return false;
    const name = (c.name || "").toLowerCase();
    return !name.startsWith("movement");
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
    console.error("move relayer fatal:", e);
    process.exit(1);
  });
}
