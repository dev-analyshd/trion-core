/**
 * TRION TON Family Relayer
 * ========================
 * VM family: TON — TON Mainnet, TON Testnet.
 *
 * Two paths:
 *   1. Native signing (chains/ton/execute.ts) — requires TON_RELAYER_PRIVATE_KEY
 *      or TON_PRIVATE_KEY_HEX.
 *   2. Block-proof fallback.
 *
 * Usage:
 *   node relayer/families/ton.js --dry-run
 *   TON_RELAYER_PRIVATE_KEY=... node relayer/families/ton.js --live
 */

import { runFamily } from "./_template.js";

export const FAMILY = "TON";

export function loadChains(reg) {
  return (reg.chains || []).filter(c => (c.vm || "").toUpperCase() === "TON");
}

export const start = (opts) => runFamily({
  family: FAMILY,
  loadChains,
  nativeVmCwd: "chains/ton",
  nativeEnvBuilder: () => {
    const k = process.env.TON_RELAYER_PRIVATE_KEY || process.env.TON_PRIVATE_KEY_HEX;
    if (!k) return null;
    return { TON_PRIVATE_KEY_HEX: k };
  },
  pollMs: parseInt(process.env.NATIVE_CYCLE_SLEEP_MS || "600000", 10),
  opts,
});

const isMain = import.meta.url === `file://${process.argv[1]}`;
if (isMain) {
  start().catch(e => {
    console.error("ton relayer fatal:", e);
    process.exit(1);
  });
}
