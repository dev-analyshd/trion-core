/**
 * TRION Stellar Family Relayer
 * ============================
 * VM family: STELLAR — Stellar Mainnet, Stellar Testnet.
 *
 * Block-proof mode by default. Native signing via stellar-sdk is in the
 * dependency tree but no chains/stellar/execute.ts is wired through this
 * module yet.
 *
 * Usage:
 *   node relayer/families/stellar.js --dry-run
 */

import { runFamily } from "./_template.js";

export const FAMILY = "STELLAR";

export function loadChains(reg) {
  return (reg.chains || []).filter(c => (c.vm || "").toUpperCase() === "STELLAR");
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
    console.error("stellar relayer fatal:", e);
    process.exit(1);
  });
}
