/**
 * TRION Hedera Family Relayer
 * ============================
 * VM family: HEDERA — Hedera, Hedera Testnet.
 *
 * Block-proof mode by default. Native signing via the Hedera SDK is not
 * wired through this module yet.
 *
 * Usage:
 *   node relayer/families/hedera.js --dry-run
 */

import { runFamily } from "./_template.js";

export const FAMILY = "HEDERA";

export function loadChains(reg) {
  return (reg.chains || []).filter(c => (c.vm || "").toUpperCase() === "HEDERA");
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
    console.error("hedera relayer fatal:", e);
    process.exit(1);
  });
}
