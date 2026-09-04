/**
 * TRION Protocol SDK
 * Complete TypeScript client for all TRION API endpoints
 * Type system enforces signal taxonomy at compile time.
 */
/**
 * ── DUPLICATE — NOT CANONICAL (W4-Q disposition) ──────────────────────────
 * This file is one of four overlapping TS SDK copies under sdk/src/ (index,
 * trion, trion-sdk, client). The canonical SDK is sdk/TrionSDK.ts (same
 * trust model: read/pack/classify — never sign, verify, or decide quorum).
 * Nothing in the repo imports this copy (grep-proven W4-Q); it is retained
 * only because two closed-wave battery tests pin it:
 * tests/unit/test_chain_registry_canonical.py (chain-id discipline) and
 * tests/unit/test_api_truth_boundaries.py (no-signing-surface check).
 * Do NOT add features here — extend sdk/TrionSDK.ts. Deletion is deferred to
 * a coordinated breaking-change window (W5-S) that updates those tests.
 * ──────────────────────────────────────────────────────────────────────────
 */


export type SignalType =
    | 'VALUATION'
    | 'SILENCE'
    | 'GENESIS'
    | 'BOOTSTRAP'
    | 'MANIPULATION_ALERT'
    | 'TEMPORAL_ANOMALY'
    | 'UNKNOWN'
    // ── BTCP Signal Types (April 2026) ────────────────────────────────────────
    | 'BTCP_ROUTE'              // BTCP route selected + executed (anchor_BH → exec_BH)
    | 'BEHAVIORAL_TRUTH'        // TRION truth signal consensus proof emitted
    | 'SHADOW_CHAIN'            // OOA shadow observation: non-integrated chain data
    | 'LIQUIDITY_OCEAN'         // Cross-chain NL aggregation signal
    | 'CONSENSUS_ADAPTATION'    // C(t) threshold adaptation event
    | 'CHAIN_RELIABILITY'       // Per-chain reliability score update
    | 'BTCP_ESCROW_EVENT'       // BTCP_ESCROW lock / release / revert event
    | 'BTCP_TIMEOUT'            // BTCP route timeout — escrow reverted
    | 'GENESIS_COMMITMENT'      // Null-state genesis commitment registered
    | 'RESURRECTION';           // Dormant entity resumed behavioral activity

// TAXONOMY UNIFICATION (GAP-PY): this union previously carried a THIRD,
// disjoint 19-type set that dropped 9 of the 10 BTCP-era names — it now
// matches sdk/TrionSDK.ts and sdk/src/index.ts exactly (the 17-literal set
// incl. the BTCP names above), so all three SDK surfaces agree.

export type AssetProfile =
  | "DEFAULT" | "NEW_TOKEN" | "MATURE_PROTOCOL"
  | "STABLECOIN" | "GOVERNANCE_TOKEN" | "BRIDGE_ASSET" | "WRAPPED_ASSET";

// ─── Trading Signal Layer Types ────────────────────────────────────────────

export type TradingSignalName =
  | "ACCUMULATION" | "DISTRIBUTION" | "MOMENTUM_LONG" | "MOMENTUM_SHORT"
  | "REVERSAL_LONG" | "REVERSAL_SHORT" | "NEUTRAL" | "MANIPULATION_ALERT"
  | "SILENCE";

export type AgentAction =
  | "STRONG_LONG" | "LONG" | "HOLD" | "SHORT" | "STRONG_SHORT" | "WAIT";

export type RiskLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" | "UNKNOWN";

export interface TradingSignalResponse {
  entity_id:    string;
  signal:       TradingSignalName;
  signal_id:    number;
  confidence:   number;
  tradeable:    boolean;
  risk:         RiskLevel;
  pattern:      string;
  explanation:  string;
  raw_phi:      number[];
  coherence:    number;
  akashic_depth: number;
}

export interface AgentDecideRequest {
  entity_id:    string;
  phi_vector:   number[];           // 9-dimensional Φ vector
  coherence:    number;
  threshold:    number;
  akashic_depth: number;
  nl_score?:    number;             // optional NL agreement score
  mf_score?:    number;             // optional manipulation fingerprint
  market_price?: number;
  portfolio_exposure?: number;
  max_position_pct?: number;
}

export interface AgentDecideResponse {
  entity_id:    string;
  action:       AgentAction;
  size_pct:     number;
  stop_loss_pct: number;
  pattern:      string;
  trion_signal: TradingSignalName;
  trion_conf:   number;
  agreement:    number;
  weighted_conf: number;
  timestamp:    string;
}

export interface TradingArchetype {
  name:         string;
  signal:       TradingSignalName;
  confidence:   number;
  min_coherence: number;
  min_depth:    number;
  phi_vector:   number[];
}

export interface TradingPatternsResponse {
  archetypes:   TradingArchetype[];
  count:        number;
}

export interface ChainScanResult {
  entity_id:    string;
  signal:       TradingSignalName;
  confidence:   number;
  tradeable:    boolean;
  pattern:      string;
}

export interface ChainScanResponse {
  chain_id:     number;
  signals:      ChainScanResult[];
  count:        number;
  scanned_at:   string;
}

export interface PlanBreakdown {
  phi_adj:  number;
  m_adj:    number;
  sigma:    number;
  k_plane:  number;
  anima:    number;
}

export interface TRIONSignal {
  signal_id:       string;
  signal_type:     SignalType;
  entity_id:       string;
  signal_value:    number | null;   // null on SILENCE
  ci_95:           [number, number]; // NEVER null — enforced by type
  coherence:       number;
  threshold:       number;
  margin:          number;
  plane_breakdown: PlanBreakdown;
  limiting_plane:  string;
  silence:         boolean;
  silence_gap:     number;          // Θ(t) - C(t) when silent
  coherence_trend: "RISING" | "FALLING" | "STABLE";
  eta_blocks:      number;
  akashic_depth:   number;
  observer_effect: number;
  bootstrap_phase: boolean;
  biological_time: {
    circadian_phase: number;
    ultradian_phase: number;
    lunar_phase:     number;
    seasonal_phase:  number;
  };
  timestamp:       number;
}

// Type safety: ValuationSignal always has signal_value
export interface ValuationSignal extends TRIONSignal {
  signal_type:  "VALUATION";
  signal_value: number;  // NOT null
}

// Type safety: SilenceSignal never has usable signal_value
export interface SilenceSignal extends TRIONSignal {
  signal_type:     "SILENCE";
  silence:         true;
  silence_gap:     number;
  coherence_trend: "RISING" | "FALLING" | "STABLE";
  eta_blocks:      number;
}

export interface NLScore {
  nl_score:    number;
  ld_score:    number;
  lo_score:    number;
  lc_score:    number;
  ls_score:    number;
  alert:       boolean;
  recommendation: "DO_NOT_ROUTE" | "CAUTION" | "CLEAR";
}

export interface BTCPScore {
  btcp_score:  number;
  is_safe:     boolean;
  components:  Record<string, number>;
  mf_discount: number;
}

export interface PreExecCheck {
  would_block:  boolean;
  reason:       string | null;
  signal_value: number;
  threshold:    number;
  explanation:  string;
}

export class TRIONClient {
  private readonly baseUrl: string;
  private readonly headers: Record<string, string>;

  constructor(baseUrl: string = "https://trion-protocol.onrender.com") {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.headers = { "Content-Type": "application/json" };
  }

  private async get<T>(path: string): Promise<T> {
    const res = await fetch(`${this.baseUrl}${path}`, { headers: this.headers });
    if (!res.ok) throw new Error(`TRION API error ${res.status}: ${await res.text()}`);
    return res.json();
  }

  private async post<T>(path: string, body: unknown): Promise<T> {
    const res = await fetch(`${this.baseUrl}${path}`, {
      method: "POST", headers: this.headers, body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`TRION API error ${res.status}: ${await res.text()}`);
    return res.json();
  }

  // ─── Core Signal ──────────────────────────────────────────────

  /** Get TRION signal for an entity. Signal or SILENCE, never undefined. */
  async getSignal(entityId: string, profile: AssetProfile = "DEFAULT"): Promise<TRIONSignal> {
    return this.get(`/api/v1/signal/${entityId}?profile=${profile}`);
  }

  /** Type-safe: get valuation signal, throws if SILENCE */
  async getValuation(entityId: string): Promise<ValuationSignal> {
    const sig = await this.getSignal(entityId);
    if (sig.silence) throw new Error(`TRION SILENCE: ${sig.silence_gap} gap, ${sig.eta_blocks} blocks ETA`);
    return sig as ValuationSignal;
  }

  /** Type-safe: get silence details */
  async getSilence(entityId: string): Promise<SilenceSignal | null> {
    const sig = await this.getSignal(entityId);
    return sig.silence ? sig as SilenceSignal : null;
  }

  // ─── Planes ────────────────────────────────────────────────────

  async getAllPlanes(entityId: string): Promise<Record<string, unknown>> {
    return this.get(`/api/v1/planes/${entityId}/all`);
  }

  async getPhysicalPlane(entityId: string): Promise<Record<string, unknown>> {
    return this.get(`/api/v1/planes/${entityId}/physical`);
  }

  // ─── Security ──────────────────────────────────────────────────

  /** Pre-execution check — the software equivalent of TRIONFirewall.gate() */
  async preExecCheck(params: {
    entity_id:     string;
    asset_address: string;
    amount:        number;
    is_flash_loan?: boolean;
  }): Promise<PreExecCheck> {
    return this.post("/api/v1/security/check", params);
  }

  // ─── Liquidity ─────────────────────────────────────────────────

  async getNLScore(assetAddress: string): Promise<NLScore> {
    return this.get(`/api/v1/liquidity/${assetAddress}`);
  }

  // ─── BTCP ──────────────────────────────────────────────────────

  async getBTCPScore(params: {
    nl_score:            number;
    gas_total_usd:       number;
    gas_99th_usd:        number;
    finality_confidence: number;
    cc_coherence:        number;
    beo_continuity:      number;
    mf_score:            number;
  }): Promise<BTCPScore> {
    return this.post("/api/v1/btcp/score", params);
  }

  // ─── System ────────────────────────────────────────────────────

  async health(): Promise<{ status: string }> {
    return this.get("/health");
  }

  async getBootstrapStatus(): Promise<Record<string, unknown>> {
    return this.get("/api/v1/system/bootstrap");
  }

  async getFalsifiability(): Promise<Record<string, unknown>> {
    return this.get("/api/v1/system/falsifiability");
  }

  async getVMStatus(): Promise<Record<string, unknown>> {
    return this.get("/api/v1/index/vm-status");
  }

  // ─── Trading Signal Layer ───────────────────────────────────────

  async getTradingSignal(entityId: string): Promise<TradingSignalResponse> {
    return this.get(`/api/v1/trading/signal/${encodeURIComponent(entityId)}`);
  }

  async agentDecide(req: AgentDecideRequest): Promise<AgentDecideResponse> {
    return this.post("/api/v1/trading/agent/decide", req);
  }

  async getTradingPatterns(): Promise<TradingPatternsResponse> {
    return this.get("/api/v1/trading/patterns");
  }

  async scanChain(chainId: number): Promise<ChainScanResponse> {
    return this.get(`/api/v1/trading/scan/${chainId}`);
  }
}

// Solidity integration helper
export const TRION_MODIFIER = `
// Add to any DeFi protocol function that moves value:
modifier onlyWhenCoherent(bytes32 txId) {
    (bool isSafe,,) = ITRIONOracle(TRION_ORACLE).verifyExecution(txId);
    require(isSafe, "TRION: Behavioral coherence insufficient");
    _;
}
`;

export default TRIONClient;
