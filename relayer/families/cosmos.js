/**
 * TRION Cosmos Family Relayer
 * ===========================
 * VM family: COSMOS — 20 chains: Cosmos Hub, Osmosis, Juno, Celestia,
 * Injective, Sei, dYdX, Kujira, Stargaze, Terra Classic, Terra Phoenix,
 * Persistence, Comdex, Chihuahua, Kava, Initia, Saga, Noble, Neutron,
 * Axelar (per config/chain_registry.json).
 *
 * Block-proof mode by default. Native Cosmos signing via @cosmjs/stargate
 * is in the relayer dependency tree but no per-chain signing executor is
 * wired through this module yet — chains/cosmos/* is the indexing side.
 *
 * Usage:
 *   node relayer/families/cosmos.js --dry-run
 */

import { runFamily } from "./_template.js";

export const FAMILY = "COSMOS";

export function loadChains(reg) {
  return (reg.chains || []).filter(c => (c.vm || "").toUpperCase() === "COSMOS");
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
    console.error("cosmos relayer fatal:", e);
    process.exit(1);
  });
}
