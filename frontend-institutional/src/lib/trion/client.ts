/**
 * TRION Protocol — typed API client for the institutional dashboard.
 *
 * All requests go through the Next.js catch-all proxy at /api/trion/*
 * which forwards them to the TRION Sensing Oracle (Flask, port 5000).
 */

/* ── Chain registry coverage ──────────────────────────────────────────────
 * Source: config/chain_registry.json (canonical chain registry). 129 chains
 * across 18 VM families; 41 integrated (live indexer + oracle). All chain/VM
 * counts in the dashboard must come from these constants — re-read the
 * registry when it changes instead of hand-editing literals at call sites.
 * ──────────────────────────────────────────────────────────────────────── */
export const CHAIN_COUNT = 129;
export const VM_FAMILY_COUNT = 18;
export const INTEGRATED_CHAIN_COUNT = 41;

export interface TrionHealth {
  oracle: string;
  status: string;
  network: string;
  chain_id: number;
  chain_connected: boolean;
  contract: string;
  vault: string;
  block_number: number;
  dynamic_threshold: number;
  market_volatility: number;
  total_signals_onchain: number;
  timestamp: number;
}

export interface BhStats {
  total_bhs?: number;
  total?: number;
  [k: string]: unknown;
}

export interface BhRecord {
  bh_id?: string;
  entity_id?: string;
  chain_id?: number;
  chain_label?: string;
  event_type_name?: string;
  magnitude_norm?: number;
  sense_hex?: string;
  antisense_hex?: string;
  ts?: number;
  [k: string]: unknown;
}

export interface MoatFactors {
  D?: number;
  Q?: number;
  R?: number;
  X?: number;
  F?: number;
  N?: number;
  [k: string]: unknown;
}

export interface PlaneProfile {
  alpha: number;
  beta: number;
  gamma: number;
  delta: number;
  epsilon: number;
  description?: string;
}

export interface CoherenceProfiles {
  asset_type_profiles: Record<string, PlaneProfile>;
  [k: string]: unknown;
}

export interface DwBft {
  consensus_value?: number;
  byzantine_effective_weight?: number;
  consensus_window_delta?: number;
  bft_safety_proof?: string;
  coordination_attack_simulation?: Array<Record<string, number>>;
  [k: string]: unknown;
}

export interface HhiStatus {
  hhi?: number;
  tier?: string;
  [k: string]: unknown;
}

export interface ChainEntry {
  id: string;
  name: string;
  chain_id: number;
  vm: string;
  status: string;
  indexer: string;
  color?: string;
  note?: string;
  bh_label?: string;
}

export interface ChainsResponse {
  chains: ChainEntry[];
  [k: string]: unknown;
}

export interface BtcpRouteResult {
  route: {
    route_id: string;
    route_type: string;
    anchor_chain: number;
    execution_chain: number;
    gas_total: number;
    finality_confidence: number;
    beo_continuity: number;
    cc_coherence: number;
  } | null;
  btcp_score: number;
  reason?: string;
  whitepaper?: string;
  [k: string]: unknown;
}

export interface FeedItem {
  [k: string]: unknown;
}

/** GET a TRION API path (without the /api/v1 prefix). */
export async function trionGet<T>(path: string): Promise<T> {
  const res = await fetch(`/api/trion/${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`TRION API ${path} -> HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

/** POST a JSON body to a TRION API path. */
export async function trionPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`/api/trion/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`TRION API ${path} -> HTTP ${res.status} ${detail.slice(0, 200)}`);
  }
  return res.json() as Promise<T>;
}
