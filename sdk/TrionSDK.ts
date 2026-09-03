/**
 * TRION Protocol — TypeScript SDK
 *
 * Provides helpers for:
 *  - Fetching and interpreting TRIONSignal responses from the Akashic Oracle
 *  - Packing / unpacking the 256-bit thermodynamic signal for gas-efficient on-chain storage
 *  - Signal classification utilities
 *  - Multi-chain entity ID helpers
 */

// ---------------------------------------------------------------------------
// Signal types
// ---------------------------------------------------------------------------

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

export type EntityType =
    | 'MATURE_PROTOCOL'
    | 'EMERGING_PROTOCOL'
    | 'GENESIS'
    | 'BOOTSTRAP'
    | 'UNKNOWN';

export type LimitingPlane =
    | 'PHYSICAL'
    | 'MENTAL'
    | 'SPIRITUAL'
    | 'CONSCIOUS'
    | 'ANIMA';

export type TrendDirection = 'RISING' | 'FALLING' | 'STABLE' | 'INSUFFICIENT_DATA';

export type ImmuneClearance = 'NOMINAL' | 'ALERT' | 'CRITICAL';

// ---------------------------------------------------------------------------
// Signal schema — mirrors TRIONSignal in akashic-oracle/src/oracle.rs
// ---------------------------------------------------------------------------

export interface PlaneBreakdown {
    physical: number;
    mental: number;
    spiritual: number;
    conscious: number;
    anima: number;
    limiting_plane: LimitingPlane;
}

export interface SilenceMetadata {
    gap: number;
    trend: TrendDirection;
    trend_rate: number;
    eta_blocks: number | null;
}

export interface BiologicalTime {
    circadian_phase: number;
    ultradian_phase: number;
    lunar_phase: number;
    seasonal_phase: number;
}

export interface LivingSecurity {
    sense_strand: string;
    antisense_strand: string;
    immune_clearance: ImmuneClearance;
    generation: number;
}

export interface TRIONSignal {
    signal_id: string;
    signal_type: SignalType;
    entity_id: string;
    entity_type: EntityType;
    coherence: number;
    threshold: number;
    margin: number;
    temporal_coherence: number;
    plane_breakdown: PlaneBreakdown;
    akashic_depth: number;
    entropy: number;
    manipulation_fingerprint: number;
    observer_effect: number;
    genesis_confidence: number;
    reflexivity_flag: boolean;
    signal_ttl_blocks: number;
    validator_hhi: number;
    silence_metadata?: SilenceMetadata;
    biological_time: BiologicalTime;
    living_security: LivingSecurity;
}

// ---------------------------------------------------------------------------
// Packed signal layout (256-bit uint256)
//
//   bits   0– 7   status     (8 bits)   1=SAFE 2=WARN 3=SILENCE
//   bits   8–39   coherence  (32 bits)  scaled ×1e6
//   bits  40–71   threshold  (32 bits)  scaled ×1e6
//   bits  72–135  blockNum   (64 bits)
//   bits 136–199  timestamp  (64 bits)  Unix seconds
// ---------------------------------------------------------------------------

export interface UnpackedSignal {
    status: number;
    coherence: number;
    threshold: number;
    blockNum: number;
    timestamp: number;
}

// ---------------------------------------------------------------------------
// TrionSDK
// ---------------------------------------------------------------------------

export class TrionSDK {

    // ── Fetch ────────────────────────────────────────────────────────────────

    /**
     * Fetch a live TRIONSignal from the Akashic Oracle for a given entity address.
     *
     * @param baseUrl  Oracle base URL, e.g. "http://localhost:3002"
     * @param entityId On-chain entity address (e.g. token contract or wallet)
     */
    static async fetchSignal(baseUrl: string, entityId: string): Promise<TRIONSignal> {
        const url = `${baseUrl.replace(/\/$/, '')}/api/v1/signal/${entityId}`;
        const res = await fetch(url);
        if (!res.ok) throw new Error(`TRION Oracle error ${res.status}: ${await res.text()}`);
        return res.json() as Promise<TRIONSignal>;
    }

    /**
     * Check oracle health.
     *
     * @param baseUrl Oracle base URL
     * @returns true if the oracle is healthy
     */
    static async checkHealth(baseUrl: string): Promise<boolean> {
        try {
            const res = await fetch(`${baseUrl.replace(/\/$/, '')}/api/v1/health`);
            return res.ok;
        } catch {
            return false;
        }
    }

    // ── Classification helpers ────────────────────────────────────────────────

    /** Returns true when C(t) >= Θ(t) and no manipulation alert is active. */
    static isSafe(signal: TRIONSignal): boolean {
        return signal.signal_type === 'VALUATION' || signal.signal_type === 'GENESIS';
    }

    /** Returns true when the oracle has triggered a SILENCE / revert primitive. */
    static isSilence(signal: TRIONSignal): boolean {
        return signal.signal_type === 'SILENCE';
    }

    /** Returns true when a wash-trade or manipulation fingerprint alert is active. */
    static isManipulationAlert(signal: TRIONSignal): boolean {
        return signal.signal_type === 'MANIPULATION_ALERT';
    }

    /** Returns true when the entity is in GENESIS or BOOTSTRAP mode. */
    static isGenesis(signal: TRIONSignal): boolean {
        return signal.signal_type === 'GENESIS' || signal.signal_type === 'BOOTSTRAP';
    }

    /**
     * Returns the coherence margin (positive = safe, negative = silence).
     * Equivalent to C(t) − Θ(t).
     */
    static coherenceMargin(signal: TRIONSignal): number {
        return signal.coherence - signal.threshold;
    }

    /**
     * Returns the weakest plane value and its label.
     */
    static limitingPlane(signal: TRIONSignal): { plane: LimitingPlane; value: number } {
        const p = signal.plane_breakdown;
        const entries: [LimitingPlane, number][] = [
            ['PHYSICAL',  p.physical],
            ['MENTAL',    p.mental],
            ['SPIRITUAL', p.spiritual],
            ['CONSCIOUS', p.conscious],
            ['ANIMA',     p.anima],
        ];
        const min = entries.reduce((a, b) => (a[1] < b[1] ? a : b));
        return { plane: min[0], value: min[1] };
    }

    /**
     * Returns a human-readable one-line summary of the signal.
     */
    static summarize(signal: TRIONSignal): string {
        const margin = TrionSDK.coherenceMargin(signal);
        const sign = margin >= 0 ? '+' : '';
        return `[${signal.signal_type}] ${signal.entity_id.slice(0, 10)}… `
             + `C(t)=${signal.coherence.toFixed(3)} Θ(t)=${signal.threshold.toFixed(3)} `
             + `margin=${sign}${margin.toFixed(3)} limiting=${signal.plane_breakdown.limiting_plane}`;
    }

    // ── 256-bit packing ───────────────────────────────────────────────────────

    /**
     * Packs thermodynamic data into a single 256-bit BigInt for gas-efficient
     * on-chain storage in TRIONOracleV3.
     *
     * @param status    1 = SAFE, 2 = WARN, 3 = SILENCE
     * @param coherence Scaled by 1e6  (e.g. 0.885 → 885000)
     * @param threshold Scaled by 1e6  (e.g. 0.750 → 750000)
     * @param blockNum  Current block number
     * @param timestamp Unix timestamp in seconds
     */
    static packSignal(
        status: number,
        coherence: number,
        threshold: number,
        blockNum: number,
        timestamp: number,
    ): bigint {
        let packed = BigInt(status) & BigInt(0xFF);
        packed |= (BigInt(coherence)  & BigInt(0xFFFFFFFF))           << BigInt(8);
        packed |= (BigInt(threshold)  & BigInt(0xFFFFFFFF))           << BigInt(40);
        packed |= (BigInt(blockNum)   & BigInt(0xFFFFFFFFFFFFFFFF))   << BigInt(72);
        packed |= (BigInt(timestamp)  & BigInt(0xFFFFFFFFFFFFFFFF))   << BigInt(136);
        return packed;
    }

    /**
     * Unpacks a 256-bit BigInt returned from TRIONOracleV3.getSignal().
     */
    static unpackSignal(packed: bigint): UnpackedSignal {
        return {
            status:    Number(packed & BigInt(0xFF)),
            coherence: Number((packed >> BigInt(8))   & BigInt(0xFFFFFFFF)),
            threshold: Number((packed >> BigInt(40))  & BigInt(0xFFFFFFFF)),
            blockNum:  Number((packed >> BigInt(72))  & BigInt(0xFFFFFFFFFFFFFFFF)),
            timestamp: Number((packed >> BigInt(136)) & BigInt(0xFFFFFFFFFFFFFFFF)),
        };
    }

    /**
     * Converts a packed signal into a human-readable object with float coherence values.
     */
    static interpretPacked(packed: bigint): {
        status: 'SAFE' | 'WARN' | 'SILENCE' | 'UNKNOWN';
        coherence: number;
        threshold: number;
        blockNum: number;
        timestamp: Date;
    } {
        const u = TrionSDK.unpackSignal(packed);
        const statusMap: Record<number, 'SAFE' | 'WARN' | 'SILENCE' | 'UNKNOWN'> = {
            1: 'SAFE',
            2: 'WARN',
            3: 'SILENCE',
        };
        return {
            status:    statusMap[u.status] ?? 'UNKNOWN',
            coherence: u.coherence / 1e6,
            threshold: u.threshold / 1e6,
            blockNum:  u.blockNum,
            timestamp: new Date(u.timestamp * 1000),
        };
    }

    /**
     * Converts a TRIONSignal into the packed format ready for on-chain submission.
     *
     * @param signal   Full signal from fetchSignal()
     * @param blockNum Current block number
     */
    static signalToPacked(signal: TRIONSignal, blockNum: number): bigint {
        const statusMap: Record<SignalType, number> = {
            VALUATION:            1,
            GENESIS:              1,
            BOOTSTRAP:            1,
            SILENCE:              3,
            MANIPULATION_ALERT:   3,
            TEMPORAL_ANOMALY:     2,
            UNKNOWN:              2,
            // BTCP signal status codes
            BTCP_ROUTE:           1,   // safe — route confirmed
            BEHAVIORAL_TRUTH:     1,   // safe — consensus proof valid
            SHADOW_CHAIN:         2,   // advisory — OOA confidence below integrated
            LIQUIDITY_OCEAN:      1,   // safe — ocean coherence above threshold
            CONSENSUS_ADAPTATION: 2,   // advisory — threshold adapted
            CHAIN_RELIABILITY:    2,   // advisory — reliability update
            BTCP_ESCROW_EVENT:    1,   // safe — escrow event recorded
            BTCP_TIMEOUT:         3,   // unsafe — escrow timed out
            GENESIS_COMMITMENT:   1,   // safe — genesis registered
            RESURRECTION:         2,   // advisory — dormant entity resumed
        };
        const status    = statusMap[signal.signal_type] ?? 2;
        const coherence = Math.round(signal.coherence  * 1e6);
        const threshold = Math.round(signal.threshold  * 1e6);
        const timestamp = Math.floor(Date.now() / 1000);
        return TrionSDK.packSignal(status, coherence, threshold, blockNum, timestamp);
    }

    // ── Biological Rhythm helpers ─────────────────────────────────────────────

    /**
     * Returns which biological rhythm phase is currently dominant (closest to peak).
     */
    static dominantRhythm(bt: BiologicalTime): keyof BiologicalTime {
        const entries = Object.entries(bt) as [keyof BiologicalTime, number][];
        return entries.reduce((a, b) => (Math.abs(a[1] - 0.5) > Math.abs(b[1] - 0.5) ? a : b))[0];
    }

    // ── Multi-chain entity helpers ────────────────────────────────────────────

    /**
     * Normalises an entity ID for use with the oracle.
     * Lowercases and zero-pads to a full 42-char hex address if needed.
     */
    static normalizeEntityId(id: string): string {
        const hex = id.startsWith('0x') ? id : `0x${id}`;
        return hex.toLowerCase().padEnd(42, '0');
    }

    /**
     * Returns the supported chain IDs in the TRION multi-chain gateway.
     */
    static supportedChains(): { name: string; chainId: number }[] {
        return [
            { name: 'Arbitrum',        chainId: 42161 },
            { name: 'BNB Smart Chain', chainId: 56 },
            { name: 'Ethereum',        chainId: 1 },
            { name: 'Base',            chainId: 8453 },
            { name: 'Polygon',         chainId: 137 },
            { name: 'Avalanche',       chainId: 43114 },
            { name: 'Optimism',        chainId: 10 },
            { name: 'Arb Sepolia',     chainId: 421614 },
        ];
    }

    // ── BTCP helpers ──────────────────────────────────────────────────────────

    /** Returns true when a signal type indicates a live BTCP route execution. */
    static isBTCPRoute(signal: TRIONSignal): boolean {
        return signal.signal_type === 'BTCP_ROUTE';
    }

    /** Returns true when a BTCP route has timed out (escrow reverted). */
    static isBTCPTimeout(signal: TRIONSignal): boolean {
        return signal.signal_type === 'BTCP_TIMEOUT';
    }

    /**
     * Interprets a BTCP_score value (0→1) into a human-readable tier.
     * Scores: > 0.85 = Excellent, 0.70–0.85 = Good, 0.50–0.70 = Fair, < 0.50 = Poor
     */
    static btcpScoreTier(score: number): BTCPScoreTier {
        if (score >= 0.85) return 'EXCELLENT';
        if (score >= 0.70) return 'GOOD';
        if (score >= 0.50) return 'FAIR';
        return 'POOR';
    }

    /**
     * Returns the minimum number of validators required for a route.
     * C1: min_validators = 3 + floor(log10(value_usd/1000)) + illiquid_supplement
     */
    static minValidators(valueUsd: number, isIlliquid = false): number {
        const valueFactor = valueUsd >= 1000
            ? Math.floor(Math.log10(valueUsd / 1000))
            : 0;
        const illiquidBonus = isIlliquid ? 1 : 0;
        return Math.min(10, 3 + valueFactor + illiquidBonus);
    }

    /**
     * Computes coverage emergency multiplier per C2 spec.
     * 30%+ drop → 5×; 50%+ drop → 10×
     */
    static coverageMultiplier(currentWeight: number, targetWeight: number): number {
        if (targetWeight <= 0) return 1;
        const dropPct = 1 - (currentWeight / targetWeight);
        if (dropPct >= 0.50) return 10;
        if (dropPct >= 0.30) return 5;
        return 1;
    }

    /**
     * Checks BITP price tolerance between two entity rates.
     * Returns true if divergence is within the 2% behavioral price tolerance.
     */
    static checkBITPTolerance(rateA: number, rateB: number, tolerance = 0.02): BITPToleranceResult {
        if (rateA <= 0 || rateB <= 0) {
            return { valid: false, divergencePct: 0, reason: 'Invalid rates' };
        }
        const divergence = Math.abs(rateA - rateB) / rateA;
        return {
            valid:         divergence <= tolerance,
            divergencePct: divergence * 100,
            rateA,
            rateB,
            tolerancePct:  tolerance * 100,
        };
    }

    /**
     * Returns MF score classification.
     * Per GAP 3: 7 manipulation types weighted into composite score.
     */
    static mfScoreLevel(mfScore: number): MFScoreLevel {
        if (mfScore < 0.05) return 'CLEAN';
        if (mfScore < 0.20) return 'LOW';
        if (mfScore < 0.50) return 'MEDIUM';
        if (mfScore < 0.80) return 'HIGH';
        return 'CRITICAL';
    }

    /**
     * Fetches BTCP route data from the API server.
     */
    static async fetchBTCPRoute(
        apiBaseUrl: string,
        intentHash: string,
    ): Promise<BTCPRouteData | null> {
        try {
            const url = `${apiBaseUrl.replace(/\/$/, '')}/api/btcp/route/${intentHash}`;
            const res = await fetch(url);
            if (!res.ok) return null;
            return res.json() as Promise<BTCPRouteData>;
        } catch {
            return null;
        }
    }

    /**
     * Fetches BITP clipboard entries for a specific asset pair.
     */
    static async fetchBITPClipboard(
        apiBaseUrl: string,
        assetX: string,
        assetY: string,
    ): Promise<BITPClipboardEntry[]> {
        try {
            const url = `${apiBaseUrl.replace(/\/$/, '')}/api/btcp/bitp/clipboard?assetX=${assetX}&assetY=${assetY}`;
            const res = await fetch(url);
            if (!res.ok) return [];
            return res.json() as Promise<BITPClipboardEntry[]>;
        } catch {
            return [];
        }
    }

    /**
     * Checks if an entity is sanctioned via the TRION sanctions oracle (J1).
     *
     * Fail-closed: if the oracle cannot be reached we return sanctioned=true
     * with the SCREENING_UNAVAILABLE marker list, so callers block the
     * entity instead of waving it through. confidence=0 signals an
     * unverified result, not a confirmed hit.
     */
    static async checkSanctions(
        apiBaseUrl: string,
        address: string,
    ): Promise<SanctionsResult> {
        try {
            const url = `${apiBaseUrl.replace(/\/$/, '')}/api/v1/btcp/sanctions/${address}`;
            const res = await fetch(url);
            if (!res.ok) {
                return { sanctioned: true, lists: ['SCREENING_UNAVAILABLE'], confidence: 0 };
            }
            return res.json() as Promise<SanctionsResult>;
        } catch {
            return { sanctioned: true, lists: ['SCREENING_UNAVAILABLE'], confidence: 0 };
        }
    }
}

export default TrionSDK;

// ---------------------------------------------------------------------------
// BTCP-specific types (April 2026)
// ---------------------------------------------------------------------------

/** Route priority ladder per spec: NETTING > SINGLE_CHAIN > SPLIT > PARALLEL > BITP > DEFERRED */
export type BTCPRouteType =
    | 'NETTING'       // zero-movement native transfer with counterparty
    | 'SINGLE_CHAIN'  // same chain — optimal liquidity available
    | 'SPLIT'         // anchor on A, execute on B
    | 'PARALLEL'      // split value across multiple chains simultaneously
    | 'BITP'          // behavioral commitment transfer — no bridge
    | 'DEFERRED'      // wait for better conditions
    | 'MULTI_HOP';    // route via intermediate chain

export type BTCPScoreTier = 'EXCELLENT' | 'GOOD' | 'FAIR' | 'POOR';

/** 7 manipulation fingerprint types per GAP 3 §6.2 */
export type MFType =
    | 'CLEAN'
    | 'SANDWICH'
    | 'WASH_TRADING'
    | 'ORACLE_MANIPULATION'
    | 'LAYERING'
    | 'BEHAVIORAL_SPOOFING'
    | 'CROSS_PROTOCOL_COORDINATION'
    | 'STATISTICAL_ANOMALY';

export type MFScoreLevel = 'CLEAN' | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

/** Coverage emergency state per C2 spec */
export type CoverageState = 'NOMINAL' | 'ALERT' | 'CRITICAL';

export interface BTCPRouteData {
    route_id:              string;
    intent_hash:           string;
    route_type:            BTCPRouteType;
    anchor_chain:          number;
    exec_chain:            number;
    btcp_score:            number;
    btcp_score_tier:       BTCPScoreTier;
    beo_continuity_score:  number;
    nl_score:              number;
    gas_total_usd:         number;
    gas_saved_vs_bridge:   number;
    mf_score:              number;
    mf_level:              MFScoreLevel;
    consensus_hhi:         number;
    d_effective:           number;
    status:                string;
    failure_cause?:        'EXTERNAL' | 'ENTITY' | 'AMBIGUOUS';
    counterparty_entity_id?: string;  // set for NETTING routes
    created_at:            string;
    finalized_at?:         string;
}

export interface MFEvidence {
    sandwich_score:     number;
    wash_score:         number;
    oracle_score:       number;
    layering_score:     number;
    spoofing_score:     number;
    cross_proto_score:  number;
    stat_anomaly_score: number;
}

export interface MFBreakdown {
    total_score:    number;
    dominant_type:  MFType;
    level:          MFScoreLevel;
    evidence:       MFEvidence;
    alerts:         MFAlert[];
    hhi:            number;   // counterparty HHI (A5)
    d_effective:    number;   // 1 - HHI
}

export interface MFAlert {
    mf_type:     MFType;
    score:       number;
    description: string;
    chain_id:    number;
    entity_id:   string;
}

export interface BITPClipboardEntry {
    commitment_hash:        string;
    entity_id:              string;
    asset_x:                string;
    asset_y:                string;
    chain_a:                number;
    chain_b:                number;
    magnitude:              string;   // big number as string
    valuation_x:            number;
    valuation_y:            number;
    price_tolerance:        number;   // default 0.02 (2%)
    status:                 'POSTED' | 'MATCHED' | 'FILLED' | 'EXPIRED';
    posted_timestamp:       number;
    expiry_blocks:          number;
}

export interface BITPToleranceResult {
    valid:          boolean;
    divergencePct:  number;
    rateA?:         number;
    rateB?:         number;
    tolerancePct?:  number;
    reason?:        string;
}

export interface SanctionsResult {
    sanctioned:   boolean;
    lists:        string[];   // ['OFAC_SDN', 'EU_CONSOLIDATED', ...]
    confidence:   number;     // 0→1
    flagged_at?:  number;     // Unix timestamp
}

export interface BTCPRouteSignalMetadata {
    route_id:              string;
    route_type:            BTCPRouteType;
    anchor_bh:             string;
    execution_bh:          string;
    anchor_chain:          number;
    execution_chain:       number;
    btcp_score:            number;
    gas_saved_vs_bridge:   number;
    gas_saved_vs_single:   number;
    beo_continuity_score:  number;
    cc_coherence:          number;
    travel_rule_proof?:    string;
    min_validators_required: number;
    validators_signed:     number;
    coverage_state:        CoverageState;
}


// ---------------------------------------------------------------------------
// WebAssembly Signal Processor
// ---------------------------------------------------------------------------
//
// The TRION WASM module provides browser-side signal processing for:
//   - Fast coherence score verification
//   - Lightweight entropy computation
//   - Signal classification without round-trip to API
//
// Built from Rust/C sources, compiled to WASM for zero-dependency execution.
// ---------------------------------------------------------------------------

/**
 * WASM signal processor instance. Lazy-loaded on first use.
 */
let wasmInstance: WebAssembly.Instance | null = null;
let wasmLoadPromise: Promise<WebAssembly.Instance> | null = null;

/**
 * Load the TRION WASM signal processor.
 * @param wasmUrl Optional URL to the .wasm file. Defaults to bundled path.
 */
export async function loadWasmProcessor(wasmUrl?: string): Promise<WebAssembly.Instance> {
    if (wasmInstance) return wasmInstance;
    if (wasmLoadPromise) return wasmLoadPromise;

    wasmLoadPromise = (async () => {
        const url = wasmUrl || (typeof window !== 'undefined'
            ? new URL('./wasm/signal_processor.wasm', import.meta.url).href
            : './wasm/signal_processor.wasm');

        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`Failed to load WASM processor: ${response.status} ${response.statusText}`);
        }

        const bytes = await response.arrayBuffer();
        const { instance } = await WebAssembly.instantiate(bytes, {
            env: {
                memory: new WebAssembly.Memory({ initial: 2 }),
                abort: (_msg: number, _file: number, line: number, col: number) => {
                    throw new Error(`WASM abort at ${line}:${col}`);
                }
            }
        });

        wasmInstance = instance;
        return instance;
    })();

    return wasmLoadPromise;
}

/**
 * Verify a coherence score client-side using the WASM processor.
 * Returns true if the locally computed value matches the provided score
 * within tolerance (catches trivial data tampering).
 */
export async function verifyCoherenceWasm(
    phi: number,
    mental: number,
    sigma: number,
    conscious: number,
    anima: number,
    expectedCoherence: number,
    tolerance = 0.001
): Promise<{ valid: boolean; computed: number }> {
    const wasm = await loadWasmProcessor();
    const computeFn = wasm.exports.compute_coherence as (
        p: number, m: number, s: number, k: number, a: number
    ) => number | undefined;

    if (typeof computeFn !== "function") {
        throw new Error(
            "signal_processor.wasm does not export compute_coherence — " +
            "rebuild the module from signal_processor.wat (see sdk/src/wasm/)."
        );
    }

    const computed = computeFn(phi, mental, sigma, conscious, anima);
    const valid = Math.abs(computed - expectedCoherence) <= tolerance;
    return { valid, computed };
}

/**
 * Compute Shannon entropy of a value distribution using WASM.
 * Faster than pure JS for large datasets.
 *
 * H = -Σ p·log2(p), p = v_i / Σv (positive values only) — mirrors
 * core/physical/phi_engine.py shannon_entropy().
 */
export async function computeEntropyWasm(values: Float64Array): Promise<number> {
    const wasm = await loadWasmProcessor();
    const mem = wasm.exports.memory as WebAssembly.Memory | undefined;
    const entropyFn = wasm.exports.shannon_entropy as
        ((ptr: number, len: number) => number) | undefined;

    if (typeof entropyFn !== "function" || !(mem instanceof WebAssembly.Memory)) {
        throw new Error(
            "signal_processor.wasm does not export shannon_entropy/memory — " +
            "rebuild the module from signal_processor.wat (see sdk/src/wasm/)."
        );
    }

    if (values.length === 0) return 0;

    // Copy values into WASM memory (offset 0, 8 bytes per f64).
    // The module declares one 64 KiB page — guard against overflow.
    const maxValues = mem.buffer.byteLength / 8;
    if (values.length > maxValues) {
        throw new Error(
            `values.length ${values.length} exceeds wasm memory capacity ${maxValues}`
        );
    }
    const offset = 0;
    const view = new Float64Array(mem.buffer, offset, values.length);
    view.set(values);

    return entropyFn(offset, values.length);
}

/**
 * Check if WASM processor is loaded and ready.
 */
export function isWasmLoaded(): boolean {
    return wasmInstance !== null;
}

/**
 * Unload the WASM processor (free memory).
 */
export function unloadWasmProcessor(): void {
    wasmInstance = null;
    wasmLoadPromise = null;
}
