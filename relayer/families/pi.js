/**
 * TRION Pi Network Family Relayer
 * ================================
 * VM family: PI — Pi Network.
 *
 * NOTE: Pi Network is NOT in the canonical chain registry
 * (config/chain_registry.json). The legacy non-EVM relayer carried a local
 * chain entry for Pi (chainId 8001, family MVM, RPC pointing at the
 * Stellar horizon — see relayer_non_evm.js line 247). That local entry
 * is preserved here as a fallback so the pi family module can still run
 * block-proof cycles until a canonical PI entry is added to the registry.
 *
 * When a PI entry is added to the registry, this module will pick it up
 * automatically (the fallback is only used if no PI chain is found).
 *
 * Usage:
 *   node relayer/families/pi.js --dry-run
 */

import { runFamily } from "./_template.js";

export const FAMILY = "PI";

export function loadChains(reg) {
  const fromRegistry = (reg.chains || []).filter(c => (c.vm || "").toUpperCase() === "PI");
  if (fromRegistry.length > 0) return fromRegistry;
  // Fallback — legacy local entry (documented off-registry):
  return [{
    name: "Pi Network",
    vm: "PI",
    chainId: 8001,
    rpc: "https://horizon.stellar.org",
    finalitySec: 5,
    gasUsd: 0.001,
    integrated: false,
    explorer: "https://blockexplorer.minepi.com",
    nativeToken: "PI",
    decimals: 7,
    notes: "off-registry — Pi Network not yet in canonical registry; legacy local entry from relayer_non_evm.js",
  }];
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
    console.error("pi relayer fatal:", e);
    process.exit(1);
  });
}
