"""
TRION Protocol — Section 18: Behavioral Inter-Block Layer (BIBL)
The space between block N confirmation and block N+1 production.

Fills inter-block window with behavioral intelligence:
- Current mempool behavioral distribution (15 archetypes, calibrated from history)
- BRT phase derived from actual observed transaction timing
- ANIMA pre-manifestation signals
- Cross-chain behavioral health comparison
- Active MEV patterns with batch opportunity detection
- Real historical match counts from BIBLPatternStore

Primitive 5: BIBL — pattern library upgraded from 5 → 15 archetypes.
Historical matches backed by SQLite pattern store (not hardcoded).

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum

try:
    from src.core.bibl_pattern_store import (
        ARCHETYPES,
        BIBLPatternStore,
        MempoolArchetype,
        PatternObservation,
        classify_mempool_archetype,
    )
except ModuleNotFoundError:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from src.core.bibl_pattern_store import (
        ARCHETYPES,
        BIBLPatternStore,
        MempoolArchetype,
        PatternObservation,
        classify_mempool_archetype,
    )


class ChainMemoryChoice(str, Enum):
    ACCEPT  = "ACCEPT"
    REJECT  = "REJECT"
    PARTIAL = "PARTIAL"
    DEFER   = "DEFER"


@dataclass
class BIBLState:
    current_block:   int
    block_time_ms:   int
    mempool_size:    int
    mempool_fee_p50: float
    mempool_fee_p95: float
    volatility:      float
    nl_scores:       Dict[str, float]
    mev_rate_30d:    float
    # Circadian rhythm score derived from historical block-timing patterns (0–1)
    brt_circadian:   float = 0.5
    # Observed timing series for BRT derivation (unix timestamps of recent txns)
    recent_tx_timestamps: List[float] = field(default_factory=list)
    chain_id:        int = 1


@dataclass
class ChainMemorySignal:
    target_chain:         str
    current_pattern:      str
    pattern_label:        str
    historical_matches:   int           # real count from pattern store
    calibrated_confidence: float        # Bayesian-updated confidence
    recommended_base_fee: float
    direction:            str
    fee_adj_factor:       float
    choice:               ChainMemoryChoice = ChainMemoryChoice.DEFER
    pattern_description:  str = ""


@dataclass
class BRTPhase:
    """
    Behavioral Rhythm Theory phase derived from observed transaction timing.
    Replaces time.time() % 86400 with actual observed circadian patterns.
    """
    circadian_phase:    float    # [0, 1] — position in 24h cycle
    ultradian_phase:    float    # [0, 1] — position in 90-min cycle
    lunar_phase:        float    # [0, 1] — position in 29.5-day cycle
    seasonal_phase:     float    # [0, 1] — position in annual cycle
    circadian_strength: float    # [0, 1] — how strong is the 24h autocorrelation
    ultradian_strength: float    # [0, 1] — how strong is the 90-min autocorrelation
    brt_data_source:    str      # "OBSERVED" or "CLOCK_FALLBACK"
    observation_count:  int


@dataclass
class BIBLOutput:
    signal_type:        str
    timestamp:          float
    brt:                BRTPhase
    chain_memory:       Optional[ChainMemorySignal]
    mev_warning:        Optional[dict]
    liquidity_routing:  Optional[dict]
    batch_opportunity:  Optional[dict]
    block_window_ms:    int
    archetype_code:     str
    archetype_label:    str
    cross_chain_health: Optional[dict]


# ── BRT Derivation from Observed Timing ───────────────────────────────────────

def derive_brt_from_observations(
    tx_timestamps: List[float],
) -> BRTPhase:
    """
    Derive BRT phase from actual observed transaction timestamps.
    Falls back to wall-clock if insufficient observations.
    """
    now = time.time()

    # Wall-clock fallback phases
    circ_fallback  = (now % 86400)    / 86400
    ultr_fallback  = (now % 5400)     / 5400
    lunar_fallback = (now % 2551442)  / 2551442
    seas_fallback  = (now % 31557600) / 31557600

    if len(tx_timestamps) < 48:
        return BRTPhase(
            circadian_phase    = circ_fallback,
            ultradian_phase    = ultr_fallback,
            lunar_phase        = lunar_fallback,
            seasonal_phase     = seas_fallback,
            circadian_strength = 0.0,
            ultradian_strength = 0.0,
            brt_data_source    = "CLOCK_FALLBACK",
            observation_count  = len(tx_timestamps),
        )

    # Compute directional statistics for circadian phase (24h)
    circ_angles  = [(t % 86400) / 86400 * 2 * math.pi for t in tx_timestamps]
    ultr_angles  = [(t % 5400)  / 5400  * 2 * math.pi for t in tx_timestamps]

    circ_peak, circ_str = _circular_mean_and_strength(circ_angles)
    ultr_peak, ultr_str = _circular_mean_and_strength(ultr_angles)

    # Use observed peak phase if strength is meaningful, else clock fallback
    circ_phase = circ_peak if circ_str > 0.20 else circ_fallback
    ultr_phase = ultr_peak if ultr_str > 0.20 else ultr_fallback

    return BRTPhase(
        circadian_phase    = circ_phase,
        ultradian_phase    = ultr_phase,
        lunar_phase        = lunar_fallback,    # lunar needs multi-week data
        seasonal_phase     = seas_fallback,
        circadian_strength = circ_str,
        ultradian_strength = ultr_str,
        brt_data_source    = "OBSERVED",
        observation_count  = len(tx_timestamps),
    )


def _circular_mean_and_strength(angles: List[float]) -> Tuple[float, float]:
    """Circular mean and resultant length (strength) for a set of angles."""
    n = len(angles)
    if n == 0:
        return 0.0, 0.0
    sin_m = sum(math.sin(a) for a in angles) / n
    cos_m = sum(math.cos(a) for a in angles) / n
    mean  = (math.atan2(sin_m, cos_m) % (2 * math.pi)) / (2 * math.pi)
    strength = min(1.0, math.sqrt(sin_m ** 2 + cos_m ** 2))
    return mean, strength


# ── BIBL Engine ───────────────────────────────────────────────────────────────

class BIBLEngine:
    """
    Behavioral Inter-Block Intelligence Engine.

    Upgrade from previous version:
    - 15 archetypes (was 5)
    - historical_matches from real pattern store (was hardcoded 100)
    - BRT phase from observed transaction timing (was wall-clock only)
    - Batch opportunity detector
    - Cross-chain health comparison
    """

    def __init__(self, pattern_store: Optional[BIBLPatternStore] = None):
        self._store = pattern_store or BIBLPatternStore()

    def classify_mempool_pattern(
        self,
        state: BIBLState,
    ) -> Tuple[MempoolArchetype, float]:
        """Classify mempool state into one of 15 behavioral archetypes."""
        return classify_mempool_archetype(
            state.mempool_size,
            state.mev_rate_30d,
            state.volatility,
        )

    def compute_chain_memory_signal(
        self,
        state:   BIBLState,
        chain_id: str,
    ) -> ChainMemorySignal:
        """
        Chain memory signal with real historical match count and
        Bayesian-calibrated confidence from the pattern store.
        """
        archetype, match_score = self.classify_mempool_pattern(state)

        # Real historical match count from pattern store
        historical_matches = self._store.match_count(archetype.code)
        cal                = self._store.get_calibration(archetype.code)
        confidence         = (
            cal.calibrated_confidence
            if cal and cal.sample_size >= 10
            else archetype.confidence_base
        )
        fee_adj = (
            cal.mean_fee_adj
            if cal and cal.sample_size >= 10
            else archetype.base_fee_adj
        )

        recommended_fee = state.mempool_fee_p50 * (1.0 + fee_adj)
        direction       = "TIGHTEN" if fee_adj > 0 else "RELAX" if fee_adj < 0 else "HOLD"

        choice = self._decide_chain_memory_choice(archetype, state)

        return ChainMemorySignal(
            target_chain         = chain_id,
            current_pattern      = archetype.code,
            pattern_label        = archetype.label,
            historical_matches   = historical_matches,
            calibrated_confidence = confidence,
            recommended_base_fee = recommended_fee,
            direction            = direction,
            fee_adj_factor       = fee_adj,
            choice               = choice,
            pattern_description  = archetype.description,
        )

    def _decide_chain_memory_choice(
        self,
        archetype: MempoolArchetype,
        state: BIBLState,
    ) -> ChainMemoryChoice:
        """Decide ACCEPT / REJECT / PARTIAL / DEFER based on archetype and conditions."""
        if archetype.code in ("FULL_CONGESTION", "STRESS_EVENT", "LIQUIDATION_STORM"):
            if state.volatility > 0.70:
                return ChainMemoryChoice.DEFER
            return ChainMemoryChoice.PARTIAL
        if archetype.code in ("MEV_SURGE", "NFT_MINT_STORM", "AIRDROP_WAVE"):
            return ChainMemoryChoice.PARTIAL
        if archetype.code in ("DEEP_CALM", "LOW_ACTIVITY", "GOVERNANCE_VOTE_WINDOW"):
            return ChainMemoryChoice.ACCEPT
        return ChainMemoryChoice.ACCEPT

    def detect_mev_opportunity(self, state: BIBLState) -> Optional[dict]:
        """MEV exposure detection with batch opportunity sizing."""
        if state.mev_rate_30d > 0.005:
            exposure  = "HIGH" if state.mev_rate_30d > 0.02 else "MEDIUM"
            save_pct  = min(0.90, state.mev_rate_30d * 10)
            # Estimate minimum batch size to beat MEV overhead
            min_batch = max(2, int(1 / max(state.mev_rate_30d, 0.001)))
            return {
                "warning":            True,
                "mev_rate":           state.mev_rate_30d,
                "exposure":           exposure,
                "protection":         "BATCH_TRANSACTIONS",
                "estimated_save_pct": save_pct,
                "min_batch_size":     min_batch,
                "private_mempool":    state.mev_rate_30d > 0.03,
            }
        return None

    def detect_batch_opportunity(self, state: BIBLState) -> Optional[dict]:
        """
        Detect if inter-block window has a batching opportunity.
        Batching is beneficial when: fee_p95/fee_p50 > 1.5 (bimodal gas distribution)
        indicating that large transactions are paying a premium that batch routing avoids.
        """
        if state.mempool_fee_p50 <= 0:
            return None
        fee_ratio = state.mempool_fee_p95 / state.mempool_fee_p50
        if fee_ratio < 1.5:
            return None

        estimated_batch_savings = min(0.40, (fee_ratio - 1.0) * 0.20)
        optimal_batch_size      = max(2, min(50, int(fee_ratio * 5)))

        return {
            "opportunity":          True,
            "fee_ratio_p95_p50":    round(fee_ratio, 3),
            "estimated_savings_pct": round(estimated_batch_savings, 4),
            "optimal_batch_size":   optimal_batch_size,
            "reason": (
                f"Gas distribution bimodal: P95/P50={fee_ratio:.2f}x — "
                "batching avoids priority fee premium"
            ),
        }

    def compute_cross_chain_health(
        self,
        nl_scores:   Dict[str, float],
        state:       BIBLState,
    ) -> Optional[dict]:
        """Cross-chain behavioral health comparison."""
        if not nl_scores or len(nl_scores) < 2:
            return None

        sorted_chains = sorted(nl_scores.items(), key=lambda x: x[1], reverse=True)
        best_chain    = sorted_chains[0]
        worst_chain   = sorted_chains[-1]

        at_risk = [c for c, score in nl_scores.items() if score < 0.30]
        mean_nl = sum(nl_scores.values()) / len(nl_scores)
        spread  = best_chain[1] - worst_chain[1]

        return {
            "recommended_chain":  best_chain[0],
            "recommended_nl":     best_chain[1],
            "weakest_chain":      worst_chain[0],
            "weakest_nl":         worst_chain[1],
            "at_risk_chains":     at_risk,
            "mean_nl_score":      round(mean_nl, 4),
            "nl_spread":          round(spread, 4),
            "routing_premium":    round(spread * 0.5, 4),  # expected improvement
            "all_scores":         nl_scores,
        }

    def record_outcome(
        self,
        archetype_code:    str,
        recommended_fee:   float,
        actual_fee:        float,
        mempool_size:      int,
        mev_rate:          float,
        volatility:        float,
        chain_id:          int,
    ) -> None:
        """
        Record actual fee outcome vs recommendation for pattern calibration.
        Call this after each block settles to continuously improve accuracy.
        """
        base_fee     = recommended_fee / max(1, 1 + ARCHETYPES[archetype_code].base_fee_adj
                                             if archetype_code in ARCHETYPES else 1)
        rec_adj      = recommended_fee / max(base_fee, 1e-9) - 1
        actual_adj   = actual_fee      / max(base_fee, 1e-9) - 1
        pred_error   = abs(rec_adj - actual_adj)

        obs = PatternObservation(
            archetype_code      = archetype_code,
            observed_at         = time.time(),
            mempool_size        = mempool_size,
            mev_rate            = mev_rate,
            volatility          = volatility,
            recommended_fee_adj = rec_adj,
            actual_fee_adj      = actual_adj,
            prediction_error    = pred_error,
            chain_id            = chain_id,
        )
        self._store.record_observation(obs)

    def run_cycle(self, state: BIBLState, chain_id: str) -> BIBLOutput:
        """
        Run one BIBL inter-block cycle.
        Called once per block (or on mempool update events).
        """
        # BRT from observed timing (not wall-clock)
        brt          = derive_brt_from_observations(state.recent_tx_timestamps)
        chain_memory = self.compute_chain_memory_signal(state, chain_id)
        mev_warning  = self.detect_mev_opportunity(state)
        batch_opp    = self.detect_batch_opportunity(state)
        cross_health = self.compute_cross_chain_health(state.nl_scores, state)

        # Liquidity routing recommendation
        routing = None
        if state.nl_scores:
            best   = max(state.nl_scores.items(), key=lambda x: x[1])
            worst  = min(state.nl_scores.items(), key=lambda x: x[1])
            routing = {
                "recommended_chain": best[0],
                "nl_score":          best[1],
                "avoid_chain":       worst[0] if worst[1] < 0.30 else None,
                "reason":            "Behavioral liquidity quality differential detected",
            }

        archetype, _ = self.classify_mempool_pattern(state)

        return BIBLOutput(
            signal_type        = "BIBL",
            timestamp          = time.time(),
            brt                = brt,
            chain_memory       = chain_memory,
            mev_warning        = mev_warning,
            liquidity_routing  = routing,
            batch_opportunity  = batch_opp,
            block_window_ms    = state.block_time_ms,
            archetype_code     = archetype.code,
            archetype_label    = archetype.label,
            cross_chain_health = cross_health,
        )


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    store  = BIBLPatternStore(db_path=db_path)
    engine = BIBLEngine(pattern_store=store)

    # Simulate observed timing: 200 tx spread over last 7 days
    import random
    rng = random.Random(42)
    base_ts = time.time() - 7 * 86400
    tx_timestamps = [base_ts + rng.uniform(0, 7 * 86400) for _ in range(200)]

    state = BIBLState(
        current_block=20_000_000,
        block_time_ms=12000,
        mempool_size=65000,
        mempool_fee_p50=15e9,
        mempool_fee_p95=45e9,
        volatility=0.55,
        nl_scores={"ethereum": 0.75, "arbitrum": 0.60, "aave_pool": 0.09},
        mev_rate_30d=0.025,
        recent_tx_timestamps=tx_timestamps,
        chain_id=1,
    )

    output = engine.run_cycle(state, "ethereum")
    cm     = output.chain_memory

    print(f"BIBL cycle output:")
    print(f"  Archetype:    {output.archetype_code} — {output.archetype_label}")
    print(f"  Description:  {cm.pattern_description}")
    print(f"  History:      {cm.historical_matches} matches (real count)")
    print(f"  Confidence:   {cm.calibrated_confidence:.4f}")
    print(f"  Fee adj:      {cm.fee_adj_factor:+.2%} ({cm.direction})")
    print(f"  Choice:       {cm.choice}")
    print(f"  MEV warning:  {output.mev_warning is not None}")
    print(f"  Batch:        {output.batch_opportunity}")
    print(f"  BRT source:   {output.brt.brt_data_source}")
    print(f"  BRT circ:     {output.brt.circadian_phase:.4f} (strength={output.brt.circadian_strength:.4f})")
    print(f"  Cross-chain:  {output.cross_chain_health['recommended_chain'] if output.cross_chain_health else None}")
    print(f"  Avoid:        {output.cross_chain_health['at_risk_chains'] if output.cross_chain_health else None}")

    assert output.archetype_code != "MEDIUM_ACTIVITY", "Should classify as congestion/MEV"
    assert output.brt.brt_data_source == "OBSERVED"
    assert output.mev_warning is not None
    assert output.batch_opportunity is not None

    os.unlink(db_path)
    print("PRIMITIVE-5 PASS — BIBL upgraded: 15 archetypes + real history + observed BRT")
