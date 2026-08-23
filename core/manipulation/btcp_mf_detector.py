"""
TRION BTCP — 7 Manipulation Fingerprint Types (BTCP_15 Gap 3 Resolution)
=========================================================================

Per the BTCP Master Implementation Spec §Phase 0 Task 0.3, BTCP defines 7
distinct manipulation fingerprint types — different from TRION's existing
7 MF types (oracle_attack, wash_trading, etc.). The BTCP MF types are
specialized for cross-chain routing detection:

| Type | Pattern                                           | Weight |
|------|---------------------------------------------------|--------|
| T1   | Sandwich: Intent A → victim_tx → Intent B         | 0.20   |
| T2   | Wash Trading: self-trading for false volume       | 0.15   |
| T3   | Oracle Manipulation: large trade → oracle exploit | 0.25   |
| T4   | Layering: many orders never intended to fill      | 0.15   |
| T5   | Behavioral Spoofing: mimics high-trust entity     | 0.10   |
| T6   | Cross-Protocol Coordination                       | 0.10   |
| T7   | Statistical Anomaly: catch-all                    | 0.05   |

Combination Rule:
    MF_score = weighted_max(fingerprint_1..7 scores)  // range 0.0 to 1.0
    If Type 7 detected: hold at 0.5 pending Conscious Layer review
    Chain-level MF: aggregated across all entities in rolling window W

Used as multiplicative penalty in BTCP_score: × (1 - MF_score)

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import IntEnum


class MFType(IntEnum):
    """7 BTCP manipulation fingerprint types."""
    T1_SANDWICH          = 1
    T2_WASH_TRADING      = 2
    T3_ORACLE_MANIP      = 3
    T4_LAYERING          = 4
    T5_SPOOFING          = 5
    T6_CROSS_PROTOCOL    = 6
    T7_STATISTICAL       = 7


# Whitepaper-mandated weights (sum to 1.0)
MF_WEIGHTS: Dict[MFType, float] = {
    MFType.T1_SANDWICH:        0.20,
    MFType.T2_WASH_TRADING:    0.15,
    MFType.T3_ORACLE_MANIP:    0.25,
    MFType.T4_LAYERING:        0.15,
    MFType.T5_SPOOFING:        0.10,
    MFType.T6_CROSS_PROTOCOL:  0.10,
    MFType.T7_STATISTICAL:     0.05,
}


@dataclass
class MFResult:
    """Result of one MF fingerprint check."""
    mf_type: MFType
    detected: bool
    score: float                # 0.0 to 1.0 (1.0 = definitively manipulation)
    evidence: Dict[str, float] = field(default_factory=dict)


@dataclass
class MFInput:
    """Inputs for the 7 MF fingerprint detectors."""
    # T1 — Sandwich
    intent_a_side: Optional[str] = None      # "BUY" or "SELL"
    intent_b_side: Optional[str] = None
    victim_tx_between: bool = False
    intent_a_magnitude: float = 0.0
    intent_b_magnitude: float = 0.0
    magnitude_similarity: float = 0.0       # cosine sim of A and B magnitudes

    # T2 — Wash Trading
    self_trade_ratio: float = 0.0           # fraction of trades with self
    counterparty_diversity: float = 1.0     # 0=monopoly, 1=perfect diversity
    trade_frequency: float = 0.0            # trades per block

    # T3 — Oracle Manipulation
    large_swap_deviation: float = 0.0       # price impact of large swap
    oracle_update_deviation: float = 0.0    # oracle price change after swap
    borrow_liquidate_within_10_blocks: bool = False

    # T4 — Layering
    order_submission_rate: float = 0.0      # orders per block
    order_cancellation_rate: float = 0.0    # fraction cancelled

    # T5 — Spoofing
    behavioral_similarity_to_high_D: float = 0.0  # cosine sim to high-D entity
    own_D: float = 0.0                       # entity's own depth
    high_D_threshold: float = 1000.0         # what counts as "high D"

    # T6 — Cross-Protocol Coordination
    correlated_timing_score: float = 0.0    # 0-1, how correlated across protocols
    protocol_overlap_count: int = 0          # # of protocols with correlated timing

    # T7 — Statistical Anomaly
    kc_complexity_delta: float = 0.0        # KC(recent) - KC(historical)
    historical_kc: float = 0.0


# ── T1: Sandwich Detection ─────────────────────────────────────────────────────

def detect_t1_sandwich(inp: MFInput) -> MFResult:
    """
    T1 — Sandwich: Intent A → victim_tx → Intent B bracketing.
    Pattern: SWAP_BUY → victim → SWAP_SELL with similar magnitude.

    Detection logic:
      - intent_a_side and intent_b_side must be opposite (BUY/SELL)
      - victim_tx_between must be True
      - magnitude_similarity > 0.8 (same size bracketing)
    """
    if not inp.intent_a_side or not inp.intent_b_side:
        return MFResult(MFType.T1_SANDWICH, False, 0.0)

    opposite_sides = (
        {inp.intent_a_side, inp.intent_b_side} == {"BUY", "SELL"}
    )
    if not opposite_sides or not inp.victim_tx_between:
        return MFResult(MFType.T1_SANDWICH, False, 0.0)

    # Score based on magnitude similarity
    score = inp.magnitude_similarity if inp.magnitude_similarity > 0.8 else 0.0
    detected = score > 0.8

    return MFResult(
        mf_type=MFType.T1_SANDWICH,
        detected=detected,
        score=score,
        evidence={
            "intent_a_side": hash(inp.intent_a_side) % 100,
            "intent_b_side": hash(inp.intent_b_side) % 100,
            "victim_between": 1.0 if inp.victim_tx_between else 0.0,
            "magnitude_similarity": inp.magnitude_similarity,
            "intent_a_mag": inp.intent_a_magnitude,
            "intent_b_mag": inp.intent_b_magnitude,
        },
    )


# ── T2: Wash Trading Detection ────────────────────────────────────────────────

def detect_t2_wash(inp: MFInput) -> MFResult:
    """
    T2 — Wash Trading: self-trading for false volume.
    Pattern: High frequency + low counterparty diversity.

    Score = self_trade_ratio × (1 - counterparty_diversity) × frequency_factor
    """
    if inp.self_trade_ratio <= 0:
        return MFResult(MFType.T2_WASH_TRADING, False, 0.0)

    # High self-trade ratio + low diversity = strong wash signal
    diversity_penalty = 1.0 - inp.counterparty_diversity
    # Frequency factor: trades/block normalized to [0, 1]
    freq_factor = min(1.0, inp.trade_frequency / 10.0)

    score = inp.self_trade_ratio * diversity_penalty * (0.5 + 0.5 * freq_factor)
    detected = score > 0.5

    return MFResult(
        mf_type=MFType.T2_WASH_TRADING,
        detected=detected,
        score=min(1.0, score),
        evidence={
            "self_trade_ratio": inp.self_trade_ratio,
            "counterparty_diversity": inp.counterparty_diversity,
            "trade_frequency": inp.trade_frequency,
        },
    )


# ── T3: Oracle Manipulation Detection ─────────────────────────────────────────

def detect_t3_oracle(inp: MFInput) -> MFResult:
    """
    T3 — Oracle Manipulation: large trade → exploit on another protocol.
    Pattern: Anomalous SWAP → ORACLE_UPDATE deviation → BORROW/LIQUIDATE within 10 blocks.

    Score = base_deviation × exploit_amplifier
    where:
      base_deviation = max(swap_deviation, oracle_deviation) scaled to [0, 1]
      exploit_amplifier = 5.0 if borrow_liquidate confirmed (smoking gun) else 1.0
    """
    if inp.large_swap_deviation <= 0 and inp.oracle_update_deviation <= 0:
        return MFResult(MFType.T3_ORACLE_MANIP, False, 0.0)

    max_dev = max(inp.large_swap_deviation, inp.oracle_update_deviation)
    # Scale: a 5% deviation is significant; a 20% deviation is max signal
    base = min(1.0, max_dev / 0.20)
    # borrow/liquidate within 10 blocks is the smoking gun — 5x amplifier
    exploit_amplifier = 5.0 if inp.borrow_liquidate_within_10_blocks else 1.0

    score = min(1.0, base * exploit_amplifier)
    # Detection requires the borrow/liquidate exploit window — without it, even
    # a large deviation is just a big trade, not oracle manipulation.
    detected = inp.borrow_liquidate_within_10_blocks and base > 0.25

    return MFResult(
        mf_type=MFType.T3_ORACLE_MANIP,
        detected=detected,
        score=score,
        evidence={
            "swap_deviation": inp.large_swap_deviation,
            "oracle_deviation": inp.oracle_update_deviation,
            "borrow_liquidate_window": 1.0 if inp.borrow_liquidate_within_10_blocks else 0.0,
            "base_deviation": base,
            "exploit_amplifier": exploit_amplifier,
        },
    )


# ── T4: Layering Detection ────────────────────────────────────────────────────

def detect_t4_layering(inp: MFInput) -> MFResult:
    """
    T4 — Layering: many orders never intended to fill, withdrawn before execution.
    Pattern: High order submission + very high cancellation rate.
    """
    if inp.order_submission_rate <= 0:
        return MFResult(MFType.T4_LAYERING, False, 0.0)

    # High submission rate AND high cancellation rate = layering
    submission_factor = min(1.0, inp.order_submission_rate / 20.0)  # 20+ orders/block = max
    cancellation_factor = inp.order_cancellation_rate  # already 0-1

    score = submission_factor * cancellation_factor
    detected = score > 0.6

    return MFResult(
        mf_type=MFType.T4_LAYERING,
        detected=detected,
        score=score,
        evidence={
            "submission_rate": inp.order_submission_rate,
            "cancellation_rate": inp.order_cancellation_rate,
        },
    )


# ── T5: Behavioral Spoofing Detection ─────────────────────────────────────────

def detect_t5_spoofing(inp: MFInput) -> MFResult:
    """
    T5 — Behavioral Spoofing: mimics high-trust entity to gain routing preference.
    Pattern: Sudden behavioral similarity to high-D(t) entity.

    Detection: behavioral_similarity_to_high_D > 0.85 AND own_D << high_D_threshold
    """
    if inp.behavioral_similarity_to_high_D <= 0:
        return MFResult(MFType.T5_SPOOFING, False, 0.0)

    # If entity is itself high-D, no spoofing
    if inp.own_D >= inp.high_D_threshold:
        return MFResult(MFType.T5_SPOOFING, False, 0.0,
                       {"own_D": inp.own_D, "reason": "entity_is_high_D"})

    # Sudden similarity to high-D entity is suspicious
    score = inp.behavioral_similarity_to_high_D if inp.behavioral_similarity_to_high_D > 0.85 else 0.0
    detected = score > 0.85

    return MFResult(
        mf_type=MFType.T5_SPOOFING,
        detected=detected,
        score=score,
        evidence={
            "similarity_to_high_D": inp.behavioral_similarity_to_high_D,
            "own_D": inp.own_D,
            "high_D_threshold": inp.high_D_threshold,
        },
    )


# ── T6: Cross-Protocol Coordination Detection ─────────────────────────────────

def detect_t6_cross_protocol(inp: MFInput) -> MFResult:
    """
    T6 — Cross-Protocol Coordination: coordinated behavior across protocols
    for value extraction. Correlated timing across BORROW/SWAP/LIQUIDATE events.
    """
    if inp.correlated_timing_score <= 0:
        return MFResult(MFType.T6_CROSS_PROTOCOL, False, 0.0)

    # Multiple protocols with correlated timing = coordination
    protocol_factor = min(1.0, inp.protocol_overlap_count / 3.0)  # 3+ protocols = max
    score = inp.correlated_timing_score * (0.5 + 0.5 * protocol_factor)
    detected = score > 0.5 and inp.protocol_overlap_count >= 2

    return MFResult(
        mf_type=MFType.T6_CROSS_PROTOCOL,
        detected=detected,
        score=score,
        evidence={
            "correlated_timing": inp.correlated_timing_score,
            "protocol_overlap": inp.protocol_overlap_count,
        },
    )


# ── T7: Statistical Anomaly (catch-all) ──────────────────────────────────────

def detect_t7_statistical(inp: MFInput) -> MFResult:
    """
    T7 — Statistical Anomaly: catch-all — doesn't fit T1-T6 but statistically improbable.
    Sharp KC complexity increase, unpredictable from own history.

    If T7 detected: MF_score held at 0.5 pending Conscious Layer review.
    """
    if inp.historical_kc <= 0:
        return MFResult(MFType.T7_STATISTICAL, False, 0.0,
                       {"reason": "no_baseline"})

    rel_delta = abs(inp.kc_complexity_delta) / inp.historical_kc
    # Sharp increase (>30% relative) = anomaly
    score = min(1.0, rel_delta / 0.30)
    detected = rel_delta > 0.30

    return MFResult(
        mf_type=MFType.T7_STATISTICAL,
        detected=detected,
        score=score,
        evidence={
            "kc_delta": inp.kc_complexity_delta,
            "historical_kc": inp.historical_kc,
            "relative_delta": rel_delta,
        },
    )


# ── Weighted Max Combination ───────────────────────────────────────────────────

def compute_mf_score(inp: MFInput) -> Tuple[float, List[MFResult], bool]:
    """
    Compute the combined MF score using weighted_max.

    MF_score = weighted_max(T1×0.20, T2×0.15, T3×0.25, T4×0.15, T5×0.10, T6×0.10, T7×0.05)

    "weighted_max" means: find the type with the highest weighted score
    (weight × score), and return that weighted score. This is different
    from a simple weighted average — it emphasizes the most-likely
    manipulation type.

    Special case: If Type 7 is detected, hold the final MF_score at 0.5
    pending Conscious Layer review.

    Returns:
        (mf_score, list_of_results, needs_conscious_review)
    """
    results = [
        detect_t1_sandwich(inp),
        detect_t2_wash(inp),
        detect_t3_oracle(inp),
        detect_t4_layering(inp),
        detect_t5_spoofing(inp),
        detect_t6_cross_protocol(inp),
        detect_t7_statistical(inp),
    ]

    # Compute weighted scores
    weighted_scores = [
        MF_WEIGHTS[r.mf_type] * r.score for r in results
    ]
    max_weighted = max(weighted_scores) if weighted_scores else 0.0

    # Normalize by the max possible weighted score (which is the weight itself,
    # since score ≤ 1.0). This gives a final MF_score in [0, 1].
    # However, the spec says "range 0.0 to 1.0" without normalization, so we
    # interpret weighted_max as: the max of (weight × score), but if any type
    # is detected (score > threshold), boost to at least the weight.
    detected_any = any(r.detected for r in results)
    if detected_any:
        # Find the highest-weighted detected type
        max_detected_weight = max(
            MF_WEIGHTS[r.mf_type] for r in results if r.detected
        )
        mf_score = max(max_weighted, max_detected_weight)
    else:
        mf_score = max_weighted

    # T7 special case: hold at 0.5 pending Conscious review
    t7_detected = results[6].detected
    needs_review = t7_detected
    if t7_detected:
        mf_score = max(mf_score, 0.5)

    # Clamp to [0, 1]
    mf_score = max(0.0, min(1.0, mf_score))

    return mf_score, results, needs_review


def aggregate_chain_mf(entity_mf_scores: List[float], window_size: int = 100) -> float:
    """
    Chain-level MF aggregation across all entities in rolling window W.

    Uses the max entity MF score within the window, with a small boost
    based on the fraction of entities with elevated MF (to capture
    coordinated chain-wide manipulation).
    """
    if not entity_mf_scores:
        return 0.0

    max_mf = max(entity_mf_scores)
    elevated_count = sum(1 for s in entity_mf_scores if s > 0.3)
    elevated_fraction = elevated_count / len(entity_mf_scores)

    # Boost: if >20% of entities have elevated MF, boost chain MF by 10%
    boost = 0.1 if elevated_fraction > 0.2 else 0.0
    return min(1.0, max_mf + boost)


# ── Self-test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== 7 MF Fingerprint Types Self-test ===\n")

    # Test 1: Clean entity — no manipulation
    clean = MFInput(
        self_trade_ratio=0.0,
        counterparty_diversity=1.0,
        trade_frequency=1.0,
        order_submission_rate=1.0,
        order_cancellation_rate=0.1,
        own_D=500.0,
        high_D_threshold=1000.0,
        historical_kc=0.5,
        kc_complexity_delta=0.02,
    )
    score, results, review = compute_mf_score(clean)
    print(f"Clean entity: MF_score={score:.4f}, review={review}")
    for r in results:
        print(f"  T{r.mf_type}: detected={r.detected} score={r.score:.3f}")
    assert score < 0.1, f"Clean entity should have low MF, got {score}"

    # Test 2: Sandwich attack
    sandwich = MFInput(
        intent_a_side="BUY",
        intent_b_side="SELL",
        victim_tx_between=True,
        intent_a_magnitude=1000.0,
        intent_b_magnitude=990.0,
        magnitude_similarity=0.95,
    )
    score, results, review = compute_mf_score(sandwich)
    print(f"\nSandwich attack: MF_score={score:.4f}")
    assert results[0].detected, "T1 should detect sandwich"
    assert score >= 0.20  # at least T1 weight

    # Test 3: Wash trading
    wash = MFInput(
        self_trade_ratio=0.8,
        counterparty_diversity=0.2,
        trade_frequency=8.0,
    )
    score, results, review = compute_mf_score(wash)
    print(f"Wash trading: MF_score={score:.4f}")
    assert results[1].detected, "T2 should detect wash trading"

    # Test 4: Oracle manipulation
    oracle = MFInput(
        large_swap_deviation=0.15,
        oracle_update_deviation=0.20,
        borrow_liquidate_within_10_blocks=True,
    )
    score, results, review = compute_mf_score(oracle)
    print(f"Oracle manipulation: MF_score={score:.4f}")
    assert results[2].detected, "T3 should detect oracle manipulation"

    # Test 5: Layering
    layering = MFInput(
        order_submission_rate=25.0,
        order_cancellation_rate=0.9,
    )
    score, results, review = compute_mf_score(layering)
    print(f"Layering: MF_score={score:.4f}")
    assert results[3].detected, "T4 should detect layering"

    # Test 6: Spoofing
    spoofing = MFInput(
        behavioral_similarity_to_high_D=0.92,
        own_D=50.0,
        high_D_threshold=1000.0,
    )
    score, results, review = compute_mf_score(spoofing)
    print(f"Spoofing: MF_score={score:.4f}")
    assert results[4].detected, "T5 should detect spoofing"

    # Test 7: Cross-protocol coordination
    cross_proto = MFInput(
        correlated_timing_score=0.85,
        protocol_overlap_count=4,
    )
    score, results, review = compute_mf_score(cross_proto)
    print(f"Cross-protocol: MF_score={score:.4f}")
    assert results[5].detected, "T6 should detect cross-protocol coordination"

    # Test 8: Statistical anomaly → Conscious review
    stat = MFInput(
        historical_kc=0.5,
        kc_complexity_delta=0.25,  # 50% relative increase
    )
    score, results, review = compute_mf_score(stat)
    print(f"Statistical anomaly: MF_score={score:.4f} review={review}")
    assert results[6].detected, "T7 should detect statistical anomaly"
    assert review, "T7 should flag conscious review"
    assert score >= 0.5, "T7 detection should hold MF at >= 0.5"

    # Test 9: Weighted max — multiple types detected, highest weight wins
    multi = MFInput(
        # T3 (weight 0.25) detected
        large_swap_deviation=0.2,
        oracle_update_deviation=0.25,
        borrow_liquidate_within_10_blocks=True,
        # T1 (weight 0.20) also detected
        intent_a_side="BUY",
        intent_b_side="SELL",
        victim_tx_between=True,
        magnitude_similarity=0.95,
    )
    score, results, review = compute_mf_score(multi)
    print(f"\nMulti-attack: MF_score={score:.4f}")
    print(f"  Detected types: {[r.mf_type for r in results if r.detected]}")
    # T3 has highest weight (0.25), so MF_score should be at least 0.25
    assert score >= 0.25, f"Multi-attack with T3 should score >= 0.25, got {score}"

    # Test 10: Chain-level aggregation
    entity_scores = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    chain_mf = aggregate_chain_mf(entity_scores)
    print(f"\nChain MF (max={max(entity_scores)}): {chain_mf:.4f}")
    assert chain_mf >= 1.0 - 0.01  # max entity + possible boost

    # Test 11: Weights sum to 1.0
    total_weight = sum(MF_WEIGHTS.values())
    print(f"\nWeight sum: {total_weight}")
    assert abs(total_weight - 1.0) < 1e-9, "MF weights must sum to 1.0"

    print("\nPHASE 0.3 PASS — 7 MF fingerprint types implemented")
