/**
 * TRION BotChain Family Relayer
 * ==============================
 * VM family: BOTCHAIN (subset — BotChain, the AI-agent EVM L1).
 *
 * BotChain is registered in the canonical chain registry as an EVM chain
 * (chainId 677 — see config/chain_registry.json). It is treated as a
 * distinct family here because it has its own native signing pipeline
 * (chains/botchain/execute.ts) and a separate behavioural indexer.
 *
 * Two paths:
 *   1. Native signing (chains/botchain/execute.ts) — runs in block-proof
 *      mode if no key; produces BH vectors.
 *   2. Block-proof fallback (always runs alongside native) — pushes a
 *      SYNTHETIC liveness attestation to FAISS.
 *
 * Usage:
 *   node relayer/families/botchain.js --dry-run
 *   BOT_CHAIN_PRIVATE_KEY=... node relayer/families/botchain.js --live
 */

import { runFamily } from "./_template.js";

export const FAMILY = "BOTCHAIN";

export function loadChains(reg) {
  // Cherry-pick BotChain out of the EVM family — it gets its own module
  // because chains/botchain/execute.ts is the native signing path.
  return (reg.chains || []).filter(c => {
    if ((c.vm || "").toUpperCase() !== "EVM") return false;
    const name = (c.name || "").toLowerCase().replace(/[^a-z0-9]/g, "");
    return name === "botchain" || name === "botchainai";
  });
}

export const start = (opts) => runFamily({
  family: FAMILY,
  loadChains,
  nativeVmCwd: "chains/botchain",
  nativeEnvBuilder: () => {
    const k = (process.env.BOT_CHAIN_PRIVATE_KEY ||
               process.env.BOT_CHAIN_RELAYER_PRIVATE_KEY ||
               process.env.RELAYER_PRIVATE_KEY || "").trim();
    const env = {
      BOT_CHAIN_RPC_URL: process.env.BOT_CHAIN_RPC_URL || "https://rpc.botchain.ai",
    };
    if (k) env.BOT_CHAIN_PRIVATE_KEY = k;
    return env;
  },
  pollMs: parseInt(process.env.NATIVE_CYCLE_SLEEP_MS || "600000", 10),
  opts,
});

const isMain = import.meta.url === `file://${process.argv[1]}`;
if (isMain) {
  start().catch(e => {
    console.error("botchain relayer fatal:", e);
    process.exit(1);
  });
}
