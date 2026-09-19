/**
 * TRION StarkNet Family Relayer
 * =============================
 * VM family: STARKNET — Starknet Mainnet, Starknet Sepolia.
 *
 * Two paths:
 *   1. Native signing (chains/starknet/execute.ts) — requires
 *      STARKNET_RELAYER_PRIVATE_KEY (or STARKNET_PRIVATE_KEY) and optionally
 *      STARKNET_ACCOUNT_ADDRESS.
 *   2. Block-proof fallback — pushes SYNTHETIC liveness attestation to FAISS.
 *
 * Usage:
 *   node relayer/families/starknet.js --dry-run
 *   STARKNET_RELAYER_PRIVATE_KEY=0x... node relayer/families/starknet.js --live
 */

import { runFamily } from "./_template.js";

export const FAMILY = "STARKNET";

export function loadChains(reg) {
  return (reg.chains || []).filter(c => (c.vm || "").toUpperCase() === "STARKNET");
}

export const start = (opts) => runFamily({
  family: FAMILY,
  loadChains,
  nativeVmCwd: "chains/starknet",
  nativeEnvBuilder: () => {
    const k = (process.env.STARKNET_RELAYER_PRIVATE_KEY || process.env.STARKNET_PRIVATE_KEY || "").trim();
    if (!k) return null;
    const env = { STARKNET_PRIVATE_KEY: k };
    if (process.env.STARKNET_ACCOUNT_ADDRESS) env.STARKNET_ACCOUNT_ADDRESS = process.env.STARKNET_ACCOUNT_ADDRESS;
    return env;
  },
  pollMs: parseInt(process.env.NATIVE_CYCLE_SLEEP_MS || "600000", 10),
  opts,
});

const isMain = import.meta.url === `file://${process.argv[1]}`;
if (isMain) {
  start().catch(e => {
    console.error("starknet relayer fatal:", e);
    process.exit(1);
  });
}
