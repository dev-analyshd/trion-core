/**
 * TRION UTXO Family Relayer
 * =========================
 * VM family: UTXO — Bitcoin, Bitcoin Testnet4, Bitcoin Cash, Dogecoin,
 * Litecoin, Dash (per config/chain_registry.json).
 *
 * Block-proof mode by default. There is no chains/utxo/execute.ts native
 * executor — these chains lack a stable JS signing SDK wired through the
 * relayer. Native signing for UTXO is handled by btc-tools/ (separate
 * pipeline).
 *
 * Usage:
 *   node relayer/families/utxo.js --dry-run         (default — block-proof only)
 */

import { runFamily } from "./_template.js";

export const FAMILY = "UTXO";

export function loadChains(reg) {
  return (reg.chains || []).filter(c => (c.vm || "").toUpperCase() === "UTXO");
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
    console.error("utxo relayer fatal:", e);
    process.exit(1);
  });
}
