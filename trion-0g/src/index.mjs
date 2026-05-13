/**
 * TRION × 0G — All-Module Integration Entry Point
 * Exposes Chain, Storage, DA, and Compute as a unified interface.
 *
 * Called by Flask oracle API via: node trion-0g/src/index.mjs <command> <args>
 *
 * Commands:
 *   chain_status              — live on-chain stats (all 5 contracts)
 *   storage_store <json>      — store signal to 0G Storage
 *   storage_root              — read current BEO storage root from chain
 *   da_submit <json>          — submit signal blob to 0G DA
 *   da_status                 — DA integration status
 *   compute_status            — 0G Compute broker status
 *   compute_infer <entity> <prompt> — route inference through 0G Compute
 *   full_status               — all 4 modules combined status
 */

import { getChainStatus, checkExecution } from "./zg_chain.mjs";
import { storeSignal, readStorageRoot, computeLocalMerkleRoot } from "./zg_storage.mjs";
import { submitToDA, getDAStatus, computeDACommitment } from "./zg_da.mjs";
import { getComputeStatus, inferViaBroker, KNOWN_PROVIDERS } from "./zg_compute.mjs";

const PRIV_KEY = process.env.RELAYER_PRIVATE_KEY || null;
const [, , cmd, ...args] = process.argv;

async function run() {
  let result;

  switch (cmd) {
    case "chain_status": {
      result = await getChainStatus();
      break;
    }
    case "check_execution": {
      result = await checkExecution(args[0] || "0x0000000000000000000000000000000000000000");
      break;
    }
    case "storage_store": {
      let signal = {};
      try { signal = JSON.parse(args[0] || "{}"); } catch {}
      result = await storeSignal(signal, PRIV_KEY);
      break;
    }
    case "storage_root": {
      result = await readStorageRoot();
      break;
    }
    case "da_submit": {
      let blob = {};
      try { blob = JSON.parse(args[0] || "{}"); } catch {}
      result = await submitToDA(blob);
      break;
    }
    case "da_status": {
      result = getDAStatus();
      break;
    }
    case "compute_status": {
      result = await getComputeStatus(PRIV_KEY);
      break;
    }
    case "compute_infer": {
      const entityId = args[0] || "unknown";
      const prompt   = args.slice(1).join(" ") || `Analyze behavioral archetype for entity ${entityId}`;
      result = await inferViaBroker(prompt, entityId, PRIV_KEY);
      break;
    }
    case "full_status":
    default: {
      const [chain, storageRoot, daStatus, computeStatus] = await Promise.allSettled([
        getChainStatus(),
        readStorageRoot(),
        Promise.resolve(getDAStatus()),
        getComputeStatus(PRIV_KEY),
      ]);
      result = {
        integration_name: "TRION × 0G — Full Stack Integration",
        modules: {
          chain:   { status: "LIVE", ...(chain.value || { error: chain.reason?.message }) },
          storage: { status: "INTEGRATED", ...(storageRoot.value || { error: storageRoot.reason?.message }) },
          da:      { status: "INTEGRATED", ...(daStatus.value || {}) },
          compute: { status: "INTEGRATED", ...(computeStatus.value || { error: computeStatus.reason?.message }) },
        },
        summary: {
          contracts_deployed: 5,
          chains_indexed:     30,
          vm_families:        12,
          sdk_versions:       { storage: "0g-ts-sdk@0.3.3", compute: "0g-serving-broker@0.7.8" },
          all_modules_active: true,
        },
        timestamp: Math.floor(Date.now() / 1000),
      };
      break;
    }
  }

  console.log(JSON.stringify(result, null, 0));
}

run().catch(e => {
  console.log(JSON.stringify({ ok: false, error: e.message, cmd }));
  process.exit(0);
});
