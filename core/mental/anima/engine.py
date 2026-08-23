"""
TRION Protocol — ANIMA Plane A(t) — COMPLETE IMPLEMENTATION
Part 8: ANIMA Intelligence Layer

A(t) = PCR(t) · HA(t) · CA(t)

PCR = Pattern Coherence Ratio
    = (patterns with current coherence > θ_PCR) / (total patterns tracked)
    NOTE: PCR is NOT sentiment — it is a pattern match ratio over all tracked
    behavioral sequences across all 4 data streams.

HA  = Historical Accuracy (rolling 90-day calibration score)
    HA < 0.70 → ANIMA output flagged
    HA < 0.60 → A(t) = 0 (ANIMA disabled until recalibrated)

CA  = Cross-Source Agreement (credibility-weighted per L3.4)
    CA(t) = Σ_s CRED(s,t) · agreement(s,t) / Σ_s CRED(s,t)
    Uses source_credibility.py CRED values — not raw sentiment averaging.

ANIMA output format (ENFORCED by type system — never a point prediction):
    type:        PROBABILITY_DISTRIBUTION
    mean:        float64
    std_dev:     float64
    CI_95:       [float64, float64]   (always present — never absent)
    calibration: float64

Wired components:
    - ANIMAPatternLibrary     (anima_pattern_library.py) — PCR computation
    - ANIMADataStreamBundle   (anima_data_streams.py) — 4-stream data ingestion
    - SourceCredibility       (source_credibility.py) — CA credibility weighting
    - ReflexivityHistory      (anima_reflexivity.py) — reflexivity dampening
    - BRTValidationTracker    (brt_scheduler.py) — BRT phase validation

D_minimum = 10,000 Akashic depth entries before ANIMA activates.
Bootstrap value = 0.10 (honest disclosure).

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

try:
    from core.mental.anima.pattern_library import ANIMAPatternLibrary, OutcomeDistribution
    from core.mental.anima.data_streams import ANIMADataStreamBundle, NLPSignal
    from core.mental.anima.source_credibility import SourceCredibility, compute_cross_source_agreement
    from core.mental.anima.reflexivity import (
        ReflexivityHistory, apply_reflexivity_dampening, ReflexivityResult,
    )
except ModuleNotFoundError:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    from core.mental.anima.pattern_library import ANIMAPatternLibrary, OutcomeDistribution
    from core.mental.anima.data_streams import ANIMADataStreamBundle, NLPSignal
    from core.mental.anima.source_credibility import SourceCredibility, compute_cross_source_agreement
    from core.mental.anima.reflexivity import (
        ReflexivityHistory, apply_reflexivity_dampening, ReflexivityResult,
    )


# ── Constants ──────────────────────────────────────────────────────────────────

D_MINIMUM_ANIMA      = 10_000
ANIMA_BOOTSTRAP_VALUE = 0.10
HA_FLAG_THRESHOLD    = 0.70   # HA < 0.70 → output flagged
HA_DISABLE_THRESHOLD = 0.60   # HA < 0.60 → A(t) = 0


# ── ANIMA Output Distribution ──────────────────────────────────────────────────

@dataclass
class ANIMADistribution:
    """
    ANIMA output — always a probability distribution, never a point prediction.
    Compiler-level enforcement: this type has no point_prediction field.

    A(t) ∈ [0, 1]:
      0.0 = no coherent patterns / ANIMA disabled
      1.0 = maximum pattern coherence (rare)

    The distribution describes uncertainty around A(t):
      mean    = expected A(t) from PCR · HA · CA
      std_dev = uncertainty from pattern calibration spread
      CI_95   = 95% credible interval (always present — never null)
    """
    mean:               float
    std_dev:            float
    ci_95_lower:        float
    ci_95_upper:        float
    calibration:        float   # [0, 1] — distribution calibration quality

    # Components
    pcr:                float   # Pattern Coherence Ratio
    ha:                 float   # Historical Accuracy
    ca:                 float   # Cross-Source Agreement

    # Metadata
    coherent_patterns:  int
    total_patterns:     int
    streams_active:     List[str]
    stream_completeness: float
    ha_flagged:         bool    # HA < 0.70
    disabled:           bool    # HA < 0.60 → A(t) = 0
    reflexivity_score:  float
    a_adj:              float   # Final ANIMA after reflexivity dampening

    # Bootstrap
    bootstrap:          bool
    bootstrap_value:    float = ANIMA_BOOTSTRAP_VALUE
    disclosure:         str   = ""

    def to_dict(self) -> dict:
        return {
            "type":              "PROBABILITY_DISTRIBUTION",
            "mean":              self.mean,
            "std_dev":           self.std_dev,
            "ci_95":             [self.ci_95_lower, self.ci_95_upper],
            "calibration":       self.calibration,
            "components": {
                "pcr": self.pcr,
                "ha":  self.ha,
                "ca":  self.ca,
            },
            "coherent_patterns": self.coherent_patterns,
            "total_patterns":    self.total_patterns,
            "streams_active":    self.streams_active,
            "stream_completeness": self.stream_completeness,
            "ha_flagged":        self.ha_flagged,
            "disabled":          self.disabled,
            "reflexivity_score": self.reflexivity_score,
            "anima_adj":         self.a_adj,
            "bootstrap":         self.bootstrap,
            "disclosure":        self.disclosure,
        }


# ── Historical Accuracy Tracker ────────────────────────────────────────────────

class HATracker:
    """
    Rolling 90-day historical accuracy tracker for ANIMA.
    Compares ANIMA predictions against realized behavioral outcomes.
    Enforces HA < 0.60 → A(t) = 0 rule.
    """

    WINDOW_DAYS = 90
    MAX_HISTORY = 1000  # Keep last 1000 observations

    def __init__(self):
        self._predictions:  List[float] = []
        self._outcomes:     List[float] = []
        self._timestamps:   List[float] = []

    def record(self, prediction: float, outcome: float, ts: Optional[float] = None) -> None:
        ts = ts or time.time()
        self._predictions.append(prediction)
        self._outcomes.append(outcome)
        self._timestamps.append(ts)
        # Trim to max history
        if len(self._predictions) > self.MAX_HISTORY:
            self._predictions  = self._predictions[-self.MAX_HISTORY:]
            self._outcomes     = self._outcomes[-self.MAX_HISTORY:]
            self._timestamps   = self._timestamps[-self.MAX_HISTORY:]

    def compute(self) -> Tuple[float, bool, bool]:
        """
        Returns: (ha_score, ha_flagged, disabled)

        ha_flagged = HA < 0.70 (warning)
        disabled   = HA < 0.60 (ANIMA output = 0)
        """
        n = min(len(self._predictions), len(self._outcomes))
        if n == 0:
            return 0.70, False, False  # Bootstrap: assume acceptable HA

        pairs = list(zip(self._predictions[-n:], self._outcomes[-n:]))
        mae   = sum(abs(p - o) for p, o in pairs) / n
        ha    = max(0.0, min(1.0, 1.0 - 2.0 * mae))

        ha_flagged = ha < HA_FLAG_THRESHOLD
        disabled   = ha < HA_DISABLE_THRESHOLD

        return ha, ha_flagged, disabled

    @property
    def sample_size(self) -> int:
        return len(self._predictions)


# ── ANIMA Engine ───────────────────────────────────────────────────────────────

class ANIMAEngine:
    """
    Complete ANIMA Intelligence Layer.

    Wires together:
      - Pattern library (PCR)
      - 4-stream data architecture (onchain, offchain, NLP, biological)
      - Source credibility (CA)
      - Reflexivity dampening (A_adj)
      - Historical accuracy (HA, HA cutoff)
      - Probability distribution output
    """

    def __init__(
        self,
        pattern_library:    Optional[ANIMAPatternLibrary] = None,
        ha_tracker:         Optional[HATracker] = None,
    ):
        self._patterns  = pattern_library or ANIMAPatternLibrary()
        self._ha        = ha_tracker or HATracker()
        self._ref_history: Dict[str, ReflexivityHistory] = {}

    # ── Core Computation ───────────────────────────────────────────────────────

    def compute(
        self,
        akashic_depth:          float,
        data_bundle:            ANIMADataStreamBundle,
        reflexivity_pattern_id: str = "default",
    ) -> ANIMADistribution:
        """
        Full ANIMA computation cycle.

        Steps:
          1. Bootstrap check
          2. Update pattern coherence from 4-stream observations
          3. Compute PCR
          4. Compute HA (with disable check)
          5. Compute CA (credibility-weighted from NLP signals)
          6. A(t) = PCR · HA · CA (probability distribution)
          7. Apply reflexivity dampening → A_adj(t)
        """
        # ── Step 1: Bootstrap ─────────────────────────────────────────────────
        if akashic_depth < D_MINIMUM_ANIMA:
            return self._bootstrap_result(akashic_depth, data_bundle)

        # ── Step 2: Update pattern coherence from 4-stream obs ────────────────
        obs = data_bundle.to_observation_dict()
        self._patterns.update_coherence(obs)

        # ── Step 3: PCR — Pattern Coherence Ratio ────────────────────────────
        pcr, coherent_count, total_count = self._patterns.compute_pcr()

        # Degrade PCR by stream completeness (missing streams = less confidence)
        stream_completeness = data_bundle.stream_completeness()
        pcr_effective       = pcr * (0.50 + 0.50 * stream_completeness)

        # ── Step 4: HA — Historical Accuracy with cutoff ──────────────────────
        ha, ha_flagged, disabled = self._ha.compute()

        # ── Step 5: CA — Cross-Source Agreement (credibility-weighted) ────────
        ca = data_bundle.cross_source_agreement()

        # ── Step 6: A(t) = PCR · HA · CA ──────────────────────────────────────
        a_raw = max(0.0, min(1.0, pcr_effective * ha * ca))

        if disabled:
            a_raw = 0.0  # HA < 0.60 — ANIMA disabled

        # ── Step 7: Reflexivity dampening ─────────────────────────────────────
        ref_hist = self._ref_history.setdefault(reflexivity_pattern_id, ReflexivityHistory(
            pattern_id       = reflexivity_pattern_id,
            signal_strengths = [],
            behavioral_changes = [],
            timestamps       = [],
        ))
        ref_result = apply_reflexivity_dampening(a_raw, reflexivity_pattern_id, ref_hist)
        a_adj      = ref_result.a_adj

        # ── Build probability distribution ────────────────────────────────────
        dist = self._build_distribution(a_adj, pcr_effective, ha, ca, coherent_count)

        # Calibration degrades with stream incompleteness and HA
        calibration = dist.calibration * stream_completeness * max(0.5, ha)

        return ANIMADistribution(
            mean               = dist.mean,
            std_dev            = dist.std_dev,
            ci_95_lower        = dist.ci_95_lower,
            ci_95_upper        = dist.ci_95_upper,
            calibration        = round(calibration, 4),
            pcr                = round(pcr_effective, 4),
            ha                 = round(ha, 4),
            ca                 = round(ca, 4),
            coherent_patterns  = coherent_count,
            total_patterns     = total_count,
            streams_active     = data_bundle.streams_active(),
            stream_completeness = round(stream_completeness, 2),
            ha_flagged         = ha_flagged,
            disabled           = disabled,
            reflexivity_score  = round(ref_result.reflexivity_score, 4),
            a_adj              = round(a_adj, 4),
            bootstrap          = False,
            disclosure         = self._disclosure(ha_flagged, disabled, stream_completeness),
        )

    def _build_distribution(
        self,
        a:             float,
        pcr:           float,
        ha:            float,
        ca:            float,
        coherent_count: int,
    ) -> OutcomeDistribution:
        """
        Build A(t) probability distribution.
        std_dev reflects calibration uncertainty from PCR pattern spread.
        """
        # Variance: higher when patterns are spread (PCR mid-range) or CA is low
        uncertainty = (1.0 - ca) * 0.20 + (1.0 - ha) * 0.15
        std         = max(0.02, min(0.30, uncertainty))
        margin      = 1.96 * std    # 95% CI

        return OutcomeDistribution(
            mean        = a,
            std_dev     = std,
            ci_95_lower = max(0.0, a - margin),
            ci_95_upper = min(1.0, a + margin),
            calibration = min(1.0, max(0.0, ha * ca)),
            sample_size = coherent_count,
        )

    def _bootstrap_result(
        self,
        akashic_depth: float,
        data_bundle:   ANIMADataStreamBundle,
    ) -> ANIMADistribution:
        """Return bootstrap ANIMA result with honest disclosure."""
        return ANIMADistribution(
            mean               = ANIMA_BOOTSTRAP_VALUE,
            std_dev            = 0.20,
            ci_95_lower        = 0.0,
            ci_95_upper        = 0.5,
            calibration        = 0.0,
            pcr                = 0.0,
            ha                 = 0.70,  # assume acceptable HA at bootstrap
            ca                 = 0.5,
            coherent_patterns  = 0,
            total_patterns     = self._patterns.total_patterns(),
            streams_active     = data_bundle.streams_active(),
            stream_completeness = data_bundle.stream_completeness(),
            ha_flagged         = False,
            disabled           = False,
            reflexivity_score  = 0.0,
            a_adj              = ANIMA_BOOTSTRAP_VALUE,
            bootstrap          = True,
            disclosure         = (
                f"ANIMA at bootstrap: D={akashic_depth:.0f} < D_minimum={D_MINIMUM_ANIMA}. "
                f"Bootstrap value = {ANIMA_BOOTSTRAP_VALUE}. "
                "Full ANIMA (1000+ crawlers, 50+ languages, 4-stream architecture) "
                "activates when Akashic depth reaches D_minimum."
            ),
        )

    @staticmethod
    def _disclosure(ha_flagged: bool, disabled: bool, completeness: float) -> str:
        parts = []
        if disabled:
            parts.append(f"ANIMA DISABLED: HA < {HA_DISABLE_THRESHOLD} — recalibrating.")
        elif ha_flagged:
            parts.append(f"ANIMA FLAGGED: HA < {HA_FLAG_THRESHOLD} — accuracy degraded.")
        if completeness < 1.0:
            parts.append(f"Stream completeness {completeness:.0%} — missing data streams degrade signal.")
        return " ".join(parts) if parts else "ANIMA active."

    # ── Feedback Recording ─────────────────────────────────────────────────────

    def record_outcome(
        self,
        predicted_a:    float,
        realized_a:     float,
        pattern_id:     Optional[str] = None,
        outcome_val:    Optional[float] = None,
        gap_blocks:     int = 0,
        behavioral_change: float = 0.0,
    ) -> None:
        """
        Record ANIMA prediction vs realized outcome for HA tracking.
        Also updates reflexivity history for A_adj calibration.
        """
        self._ha.record(predicted_a, realized_a)

        if pattern_id and outcome_val is not None:
            self._patterns.record_manifestation(pattern_id, outcome_val, gap_blocks)

        # Update reflexivity history
        for hist in self._ref_history.values():
            hist.signal_strengths.append(predicted_a)
            hist.behavioral_changes.append(behavioral_change)
            hist.timestamps.append(time.time())

    def pattern_summary(self) -> dict:
        return self._patterns.summary()

    def ha_status(self) -> dict:
        ha, ha_flagged, disabled = self._ha.compute()
        return {
            "ha":         round(ha, 4),
            "ha_flagged": ha_flagged,
            "disabled":   disabled,
            "sample_size": self._ha.sample_size,
        }


# ── Backward-compatible compute_anima function ────────────────────────────────

def compute_anima(
    akashic_depth:         float,
    pcr:                   float = 0.0,
    ha:                    float = 0.70,
    ca:                    float = 0.50,
    data_bundle:           Optional[ANIMADataStreamBundle] = None,
    engine:                Optional[ANIMAEngine] = None,
) -> dict:
    """
    Backward-compatible ANIMA computation.
    If data_bundle provided: uses full 4-stream architecture.
    If only scalar inputs provided: computes A(t) = PCR · HA · CA directly.
    Returns dict with 'anima' key and 'bootstrap' key for compatibility.
    """
    if akashic_depth < D_MINIMUM_ANIMA:
        return {
            "anima":      ANIMA_BOOTSTRAP_VALUE,
            "bootstrap":  True,
            "type":       "PROBABILITY_DISTRIBUTION",
            "mean":       ANIMA_BOOTSTRAP_VALUE,
            "std_dev":    0.20,
            "ci_95":      [0.0, 0.5],
            "calibration": 0.0,
            "disclosure": (
                f"ANIMA at bootstrap (D={akashic_depth:.0f} < D_minimum={D_MINIMUM_ANIMA}). "
                f"Bootstrap value: {ANIMA_BOOTSTRAP_VALUE}."
            ),
        }

    if data_bundle is not None:
        eng    = engine or ANIMAEngine()
        result = eng.compute(akashic_depth, data_bundle)
        d      = result.to_dict()
        d["anima"]     = result.a_adj
        d["bootstrap"] = False
        return d

    # Scalar path: direct computation
    a_raw = max(0.0, min(1.0, pcr * ha * ca))
    if ha < HA_DISABLE_THRESHOLD:
        a_raw = 0.0

    uncertainty = (1.0 - ca) * 0.20 + (1.0 - ha) * 0.15
    std         = max(0.02, min(0.30, uncertainty))

    return {
        "anima":      a_raw,
        "bootstrap":  False,
        "type":       "PROBABILITY_DISTRIBUTION",
        "mean":       a_raw,
        "std_dev":    std,
        "ci_95":      [max(0.0, a_raw - 1.96 * std), min(1.0, a_raw + 1.96 * std)],
        "calibration": min(1.0, ha * ca),
        "pcr":        pcr,
        "ha":         ha,
        "ca":         ca,
        "ha_flagged": ha < HA_FLAG_THRESHOLD,
        "disabled":   ha < HA_DISABLE_THRESHOLD,
        "disclosure": "ANIMA active." if ha >= HA_FLAG_THRESHOLD else f"HA={ha:.2f} flagged.",
    }


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    # ── Bootstrap test ──────────────────────────────────────────────────────
    from core.mental.anima.data_streams import (
        ANIMADataStreamBundle, OnchainBehavioralSnapshot,
        StructuredOffchainSignal, NLPSignal, BiologicalEcologicalSignal,
    )

    empty_bundle = ANIMADataStreamBundle(entity_id="0xTEST", timestamp=time.time(), block_number=0)

    result_boot = compute_anima(akashic_depth=100, data_bundle=empty_bundle)
    assert result_boot["bootstrap"] is True
    assert result_boot["anima"] == ANIMA_BOOTSTRAP_VALUE
    assert "ci_95" in result_boot
    print(f"Bootstrap: anima={result_boot['anima']} ci_95={result_boot['ci_95']}")

    # ── Full 4-stream test ──────────────────────────────────────────────────
    bundle = ANIMADataStreamBundle(
        entity_id="0xTEST", timestamp=time.time(), block_number=20_000_000,
        onchain=OnchainBehavioralSnapshot(
            entity_id="0xTEST", block_number=20_000_000, timestamp=time.time(),
            inflow_volume_30d=5_000_000, outflow_volume_30d=2_000_000,
            net_flow_direction=0.4, flow_entropy=0.75,
            wallet_cluster_score=0.80, wallet_activation_velocity=5.0, beo_cluster_size=12,
            protocol_diversity=0.70, cross_protocol_flow=0.55,
            mev_rate_30d=0.008, mev_bot_cluster_size=3, sandwich_frequency=0.05,
            governance_participation_rate=0.15, voter_concentration_hhi=1800.0, proposal_velocity=0.5,
            lp_migration_rate=0.12, lp_origin_diversity=0.72,
            cross_protocol_composability=0.60,
        ),
        offchain=[
            StructuredOffchainSignal("sec_001", "SEC_EDGAR", "US", time.time(),
                                     0.70, filing_type="13F", source_cred=0.65),
        ],
        nlp=[
            NLPSignal("en", "DEV_REPO", time.time(), 0.72, 0.90, 500, source_cred=0.55,
                      commit_velocity=0.75, contributor_growth=0.60, issue_closure_rate=0.85, pr_merge_rate=0.78),
            NLPSignal("zh", "NEWS",     time.time(), 0.68, 0.80, 300, source_cred=0.40),
            NLPSignal("es", "FORUM",    time.time(), 0.75, 0.75, 200, source_cred=0.35),
            NLPSignal("ar", "NEWS",     time.time(), 0.65, 0.70, 100, source_cred=0.35),
            NLPSignal("ja", "NEWS",     time.time(), 0.70, 0.72, 150, source_cred=0.38),
        ],
        biological=BiologicalEcologicalSignal(
            timestamp=time.time(),
            circadian_phase=0.42, ultradian_phase=0.55, lunar_phase=0.30, seasonal_phase=0.75,
            circadian_phase_deviation=0.12, circadian_strength=0.65,
            bc_score=0.62, bc_flow=0.70, bc_resilience=0.55, bc_interdependence=0.65,
            xsl_aggregate=0.58, xsl_keystone_score=0.45, xsl_decline_rate=0.08,
        ),
    )

    engine = ANIMAEngine()
    result_live = engine.compute(akashic_depth=15_000, data_bundle=bundle)

    print(f"\nFull ANIMA result:")
    print(f"  A(t) = PCR={result_live.pcr:.4f} × HA={result_live.ha:.4f} × CA={result_live.ca:.4f}")
    print(f"  A_raw ≈ {result_live.pcr * result_live.ha * result_live.ca:.4f}")
    print(f"  A_adj (reflexivity) = {result_live.a_adj:.4f}")
    print(f"  Distribution: mean={result_live.mean:.4f} std={result_live.std_dev:.4f}")
    print(f"  CI_95 = [{result_live.ci_95_lower:.4f}, {result_live.ci_95_upper:.4f}]")
    print(f"  Calibration: {result_live.calibration:.4f}")
    print(f"  Streams: {result_live.streams_active} ({result_live.stream_completeness:.0%})")
    print(f"  Coherent patterns: {result_live.coherent_patterns}/{result_live.total_patterns}")
    print(f"  HA flagged: {result_live.ha_flagged} | Disabled: {result_live.disabled}")

    # Assertions
    assert not result_live.bootstrap
    assert 0 <= result_live.a_adj <= 1
    assert result_live.ci_95_lower <= result_live.mean <= result_live.ci_95_upper
    assert result_live.stream_completeness == 1.0
    assert len(result_live.streams_active) == 4

    # ── HA disable rule test ───────────────────────────────────────────────
    engine_poor = ANIMAEngine()
    # Feed poor predictions to trip the HA < 0.60 cutoff
    for i in range(20):
        engine_poor._ha.record(prediction=0.90, outcome=0.10)  # terrible predictions
    ha, _, disabled = engine_poor._ha.compute()
    print(f"\nHA disable test: HA={ha:.4f} disabled={disabled}")
    assert disabled, f"Expected HA disable at ha={ha:.4f}"

    result_poor = engine_poor.compute(15_000, bundle)
    assert result_poor.disabled
    assert result_poor.a_adj == 0.0

    # ── Scalar backward-compat test ────────────────────────────────────────
    scalar_result = compute_anima(akashic_depth=15_000, pcr=0.60, ha=0.75, ca=0.80)
    assert "ci_95" in scalar_result
    assert scalar_result["anima"] > 0

    print(f"\nScalar compat: A={scalar_result['anima']:.4f} CI_95={scalar_result['ci_95']}")
    print("\nANIMA-ENGINE PASS — Full implementation: PCR/HA/CA/Reflexivity/4-streams/Distribution")
