/**
 * TRION per-VM-family relayer template
 * ====================================
 *
 * Generic relay loop used by every NON-EVM family module. Each family
 * supplies:
 *
 *   family           string    VM label (e.g. "SVM", "COSMOS")
 *   loadChains(reg) array     chains for this VM (filtered from the registry)
 *   nativeVmCwd      string?   path to chains/<vm>/ if a native executor exists
 *   nativeEnvBuilder ()       env overrides for the native executor; return
 *                              null to skip native execution this cycle
 *   pollMs           number    cycle sleep in milliseconds
 *   opts             object    parsed CLI args (see common.parseArgs)
 *
 * Cycle semantics:
 *   1. Check self-halt — fail-closed if /api/v1/self is unreachable or SILENCED
 *   2. Pull latest oracle signal for the TRION_PROTOCOL entity
 *   3. If a native executor is configured AND keys are present, run it once
 *      (chains/<vm>/execute.ts via tsx). Streams stdout/stderr into our log.
 *   4. Block-proof fallback (always runs alongside native executor): for
 *      every chain in the family, fetch latest block from the registry RPC,
 *      push a SYNTHETIC liveness attestation to FAISS.
 *
 * Provenance: every block-proof vector is tagged
 *   data_provenance: "SYNTHETIC_BLOCK_PROOF", synthetic: true
 *
 * See audit fix REL-2 in relayer_non_evm.js.
 */

import {
  ORACLE_API_URL, FAISS_URL,
  log, loadRegistry, validateSignal, signalFields,
  fetchSignal, checkSelfHalt,
  fetchLatestBlock, pushBlockProof, persistState,
  runNativeVM,
} from "./common.js";

export const FAMILY_TAG = "TEMPLATE"; // exported for parity with family modules

export async function runFamily({
  family, loadChains, nativeVmCwd, nativeEnvBuilder, pollMs,
  opts = { dryRun: true },
}) {
  const DRY_RUN = opts.dryRun;
  const monitored = (process.env.MONITORED_ENTITIES || "TRION_PROTOCOL")
    .split(",").map(s => s.trim()).filter(Boolean);

  const reg = loadRegistry();
  const chains = loadChains(reg);

  log(family, "═══════════════════════════════════════════════════════════════");
  log(family, `TRION ${family} FAMILY RELAYER`);
  log(family, `Oracle API: ${ORACLE_API_URL}`);
  log(family, `FAISS:      ${FAISS_URL}`);
  log(family, `Mode:       ${DRY_RUN ? "DRY_RUN (block-proof only, no native signing)" : "LIVE"}`);
  log(family, `Chains:     ${chains.length} (from canonical chain_registry.json)`);
  if (nativeVmCwd) {
    log(family, `Native VM:  ${nativeVmCwd}/execute.ts (spawned if keys present)`);
  } else {
    log(family, `Native VM:  none — block-proof mode only`);
  }
  log(family, `Poll cycle: ${pollMs}ms`);
  log(family, "═══════════════════════════════════════════════════════════════");

  // Boot-time disclosure: block-proof vectors are SYNTHETIC liveness attestations.
  log(family, `NOTE: chains without native keys run in SYNTHETIC BLOCK-PROOF mode — features`);
  log(family, `     are hash-derived attestations tagged data_provenance=SYNTHETIC_BLOCK_PROOF,`);
  log(family, `     not transaction-level behavioral events (see audit fix REL-2).`);

  const state = { chains_total: chains.length, last_cycle: null, chains: [] };

  while (true) {
    const cycleStartedAt = new Date().toISOString();

    // ── Self-halt ───────────────────────────────────────────────────────────
    if (await checkSelfHalt(family)) {
      await new Promise(r => setTimeout(r, pollMs));
      continue;
    }

    // ── Oracle signal ───────────────────────────────────────────────────────
    let signal = null;
    for (const entity of monitored) {
      signal = await fetchSignal(entity);
      if (signal) break;
    }
    const verr = signal ? validateSignal(signal) : "oracle returned no signal";
    if (verr) {
      log(family, `oracle signal invalid — running block-proof cycle without signal (verr: ${verr})`);
    } else {
      const { coh, thr } = signalFields(signal);
      log(family, `oracle signal φ=${coh.toFixed(4)} θ=${thr.toFixed(4)} → ${coh >= thr ? "SAFE" : "INTERCEPT"}`);
    }

    // ── Native VM executor (optional) ──────────────────────────────────────
    let nativeResult = null;
    if (nativeVmCwd && nativeEnvBuilder) {
      const env = nativeEnvBuilder();
      if (env) {
        log(family, `native VM cycle start (${nativeVmCwd})`);
        nativeResult = await runNativeVM(family, nativeVmCwd, env);
      } else {
        log(family, `native VM SKIP — required key not set (will fall through to block-proof)`);
      }
    }

    // ── Block-proof fallback (always runs — even after native) ─────────────
    log(family, `── ${family} block-proof cycle — ${chains.length} chains ──`);
    const results = await Promise.allSettled(
      chains.map(async (chain) => {
        const blockInfo = await fetchLatestBlock(chain);
        if (!blockInfo) {
          return { chain: chain.name, status: "BLOCK_FAIL" };
        }
        const pushed = await pushBlockProof(family, chain, blockInfo, signal);
        return { chain: chain.name, status: pushed ? "OK" : "FAISS_FAIL", block: blockInfo };
      })
    );
    let ok = 0, fail = 0;
    for (const r of results) {
      if (r.status === "fulfilled" && r.value.status === "OK") ok++;
      else fail++;
    }
    log(family, `── ${family} cycle complete — ${ok} OK, ${fail} fail ──`);

    state.last_cycle = cycleStartedAt;
    state.chains_ok = ok;
    state.chains_fail = fail;
    state.native = nativeResult;
    state.results = results.map(r => r.status === "fulfilled" ? r.value : { error: r.reason?.message });
    persistState(family, state);

    await new Promise(r => setTimeout(r, pollMs));
  }
}

// ── Standalone CLI ───────────────────────────────────────────────────────────
const isMain = import.meta.url === `file://${process.argv[1]}`;
if (isMain) {
  // The template is never run directly — family modules import runFamily.
  console.error("This module is a template, not directly runnable.");
  process.exit(1);
}
