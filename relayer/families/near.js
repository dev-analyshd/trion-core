/**
 * TRION NEAR Family Relayer
 * =========================
 * VM family: NEAR — NEAR Mainnet, NEAR Testnet.
 *
 * Two paths:
 *   1. Native signing (chains/near/execute.ts) — requires NEAR_RELAYER_PRIVATE_KEY
 *      or NEAR_PRIVATE_KEY.
 *   2. Block-proof fallback.
 *
 * Usage:
 *   node relayer/families/near.js --dry-run
 *   NEAR_RELAYER_PRIVATE_KEY=... node relayer/families/near.js --live
 */

import { runFamily } from "./_template.js";

export const FAMILY = "NEAR";

export function loadChains(reg) {
  return (reg.chains || []).filter(c => (c.vm || "").toUpperCase() === "NEAR");
}

export const start = (opts) => runFamily({
  family: FAMILY,
  loadChains,
  nativeVmCwd: "chains/near",
  nativeEnvBuilder: () => {
    const k = process.env.NEAR_RELAYER_PRIVATE_KEY || process.env.NEAR_PRIVATE_KEY;
    if (!k) return null;
    return { NEAR_PRIVATE_KEY: k };
  },
  pollMs: parseInt(process.env.NATIVE_CYCLE_SLEEP_MS || "600000", 10),
  opts,
});

const isMain = import.meta.url === `file://${process.argv[1]}`;
if (isMain) {
  start().catch(e => {
    console.error("near relayer fatal:", e);
    process.exit(1);
  });
}
