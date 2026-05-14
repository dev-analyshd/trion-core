"""
TRION Protocol — L5.3 Consensus Degradation Tiers

When validator count or diversity drops below thresholds,
consensus degrades through defined tiers before halting.

Degradation tiers:
    FULL:      100+ validators, HHI < 1500, 4+ continents
    REDUCED:   33-99 validators OR HHI 1500-2500 OR 3 continents
    DEGRADED:  10-32 validators OR HHI 2500-4000 OR 2 continents
    MINIMAL:   3-9 validators (Byzantine threshold barely preserved)
    HALTED:    < 3 validators OR HHI > 4000 OR < 2 continents

Safety guarantee: 33% Byzantine threshold must always be maintained.
At MINIMAL tier: signals emitted with HONEST DISCLOSURE of degradation.
At HALTED: no signal emission. SILENCE only with explanation.

Living Security SEC(t) = LSS(t) · PQC(t) · CC(t)
    LSS = Living Security Score (BCK + immune system + genomic key)
    PQC = Post-Quantum Cryptography (CRYSTALS-Kyber + Dilithium + SPHINCS+)
    CC  = Coherence Continuity (anti-fragmentation)

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ConsensusState(Enum):
    FULL     = "FULL"      # 100+ validators, full diversity
    REDUCED  = "REDUCED"   # 33-99 validators
    DEGRADED = "DEGRADED"  # 10-32 validators
    MINIMAL  = "MINIMAL"   # 3-9 validators
    HALTED   = "HALTED"    # < 3 validators


VALIDATOR_THRESHOLDS = {
    ConsensusState.FULL:     100,
    ConsensusState.REDUCED:  33,
    ConsensusState.DEGRADED: 10,
    ConsensusState.MINIMAL:  3,
    ConsensusState.HALTED:   0,
}

# Signal confidence multipliers per tier
CONFIDENCE_MULTIPLIERS = {
    ConsensusState.FULL:     1.00,
    ConsensusState.REDUCED:  0.85,
    ConsensusState.DEGRADED: 0.60,
    ConsensusState.MINIMAL:  0.35,
    ConsensusState.HALTED:   0.00,
}


@dataclass
class ConsensusDegradationResult:
    state:                   ConsensusState
    validator_count:         int
    byzantine_threshold:     float     # 33% of effective stake — must be preserved
    byzantine_safe:          bool      # True iff no single Byzantine actor > 33%
    hhi:                     float
    continent_count:         int
    confidence_multiplier:   float
    signals_allowed:         bool
    honest_disclosure:       str
    living_security_score:   float     # SEC(t)
    f8_approaching:          bool      # HHI > 1500 and growing


def classify_consensus_state(
    validator_count:  int,
    hhi:             float,
    continent_count: int,
) -> ConsensusState:
    """
    Classify current consensus state.
    Most conservative tier from all three criteria.
    """
    # HHI-based tier
    if hhi > 4000:
        hhi_state = ConsensusState.HALTED
    elif hhi > 2500:
        hhi_state = ConsensusState.DEGRADED
    elif hhi > 1500:
        hhi_state = ConsensusState.REDUCED
    else:
        hhi_state = ConsensusState.FULL

    # Count-based tier
    if validator_count < 3:
        count_state = ConsensusState.HALTED
    elif validator_count < 10:
        count_state = ConsensusState.MINIMAL
    elif validator_count < 33:
        count_state = ConsensusState.DEGRADED
    elif validator_count < 100:
        count_state = ConsensusState.REDUCED
    else:
        count_state = ConsensusState.FULL

    # Geography-based tier
    if continent_count < 2:
        geo_state = ConsensusState.HALTED
    elif continent_count < 3:
        geo_state = ConsensusState.MINIMAL
    elif continent_count < 4:
        geo_state = ConsensusState.DEGRADED
    else:
        geo_state = ConsensusState.FULL

    # Use most degraded tier
    tier_order = [
        ConsensusState.FULL, ConsensusState.REDUCED,
        ConsensusState.DEGRADED, ConsensusState.MINIMAL, ConsensusState.HALTED
    ]
    states = [hhi_state, count_state, geo_state]
    worst = max(states, key=lambda s: tier_order.index(s))
    return worst


def compute_living_security(
    lss: float,  # Living Security Score [0, 1]
    pqc: float,  # Post-Quantum Cryptography [0, 1]
    cc:  float,  # Coherence Continuity [0, 1]
) -> float:
    """
    SEC(t) = LSS(t) · PQC(t) · CC(t)
    All components must be healthy for SEC to be healthy.
    """
    return max(0.0, min(1.0, lss * pqc * cc))


def compute_consensus_degradation(
    validator_count:  int,
    hhi:             float,
    continent_count: int,
    effective_stakes: list[float],  # Effective stake per validator
    lss:             float = 0.90,
    pqc:             float = 0.95,
    cc:              float = 0.88,
) -> ConsensusDegradationResult:
    """
    Full consensus degradation assessment with safety checks.
    """
    state = classify_consensus_state(validator_count, hhi, continent_count)

    # Byzantine safety: no single actor should exceed 33% of effective stake
    total_eff = sum(effective_stakes)
    byzantine_safe = True
    if total_eff > 0 and effective_stakes:
        max_share = max(effective_stakes) / total_eff
        byzantine_safe = max_share < 0.33
    byzantine_threshold = 0.33 * total_eff

    confidence = CONFIDENCE_MULTIPLIERS[state]
    signals_allowed = state != ConsensusState.HALTED and byzantine_safe

    # Build honest disclosure
    if state == ConsensusState.HALTED:
        disclosure = (
            f"HALTED: consensus impossible. "
            f"validators={validator_count} HHI={hhi:.0f} continents={continent_count}. "
            "SILENCE signal only — no valuation possible."
        )
    elif state == ConsensusState.MINIMAL:
        disclosure = (
            f"MINIMAL consensus: {validator_count} validators. "
            f"Byzantine safety {'MAINTAINED' if byzantine_safe else 'VIOLATED'}. "
            f"Signal confidence reduced to {confidence*100:.0f}%."
        )
    elif state == ConsensusState.DEGRADED:
        disclosure = (
            f"DEGRADED consensus: {validator_count} validators, HHI={hhi:.0f}. "
            f"Signal confidence {confidence*100:.0f}% of normal."
        )
    elif state == ConsensusState.REDUCED:
        disclosure = (
            f"REDUCED consensus: {validator_count} validators. "
            f"Signal confidence {confidence*100:.0f}%."
        )
    else:
        disclosure = (
            f"FULL consensus: {validator_count} validators, HHI={hhi:.0f}, "
            f"{continent_count} continents. Full signal confidence."
        )

    sec = compute_living_security(lss, pqc, cc)

    return ConsensusDegradationResult(
        state                 = state,
        validator_count       = validator_count,
        byzantine_threshold   = byzantine_threshold,
        byzantine_safe        = byzantine_safe,
        hhi                   = hhi,
        continent_count       = continent_count,
        confidence_multiplier = confidence,
        signals_allowed       = signals_allowed,
        honest_disclosure     = disclosure,
        living_security_score = sec,
        f8_approaching        = hhi > 1200,
    )


if __name__ == "__main__":
    # Full consensus
    result = compute_consensus_degradation(
        validator_count=150, hhi=800.0, continent_count=5,
        effective_stakes=[100.0] * 150,
    )
    print(f"Full: {result.state.value} confidence={result.confidence_multiplier}")
    assert result.state == ConsensusState.FULL
    assert result.signals_allowed

    # HALTED
    result_halt = compute_consensus_degradation(
        validator_count=2, hhi=5000.0, continent_count=1,
        effective_stakes=[1000.0, 1000.0],
    )
    print(f"Halted: {result_halt.state.value} signals={result_halt.signals_allowed}")
    assert result_halt.state == ConsensusState.HALTED
    assert not result_halt.signals_allowed

    # Living security
    sec = compute_living_security(0.90, 0.95, 0.88)
    print(f"SEC(t) = {sec:.4f}")
    assert 0 < sec < 1

    print("L5.3 Consensus Degradation Tiers + Living Security: PASS")
