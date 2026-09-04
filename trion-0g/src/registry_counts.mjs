/**
 * TRION × 0G — canonical chain-registry counts.
 *
 * Counts are read live from config/chain_registry.json (the repo's single
 * source of truth for chain/VM coverage — the same file the Python API and
 * both frontends derive from). Status output therefore reports the real
 * registry numbers instead of stale hard-coded marketing figures.
 *
 * Layout: trion-0g/src/ → ../../config/chain_registry.json (repo root).
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const REGISTRY_PATH = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
  "config",
  "chain_registry.json",
);

/**
 * Read the canonical registry and count:
 *   total_chains — every entry in the registry (catalog size)
 *   vm_families  — distinct VM families
 *   integrated   — chains with integrated=true (live indexer + oracle)
 *
 * Returns null when the registry is unreadable so callers report an explicit
 * unknown instead of falling back to a fabricated number.
 */
export function getRegistryCounts() {
  try {
    const reg = JSON.parse(readFileSync(REGISTRY_PATH, "utf8"));
    const chains = Array.isArray(reg.chains) ? reg.chains : [];
    return {
      total_chains: chains.length,
      vm_families: new Set(chains.map((c) => c.vm)).size,
      integrated: chains.filter((c) => c.integrated === true).length,
    };
  } catch {
    return null;
  }
}
