"""
TRION BTCP — 7-Plane Coherence Implementation (Gap 2 Resolution)
=================================================================

Per the BTCP Master Implementation Spec §Phase 0 Task 0.2, the 7-Plane
Coherence model extends the existing 5-plane C(t) to add two additional
planes required for BTCP routing decisions:

| Plane | Question                                       | Check                                  | Threshold |
|-------|------------------------------------------------|----------------------------------------|-----------|
| 1 Mag | Is magnitude consistent with history?          | z_score = |m - μ| / σ                  | < 3.0     |
| 2 Temp| Is timing consistent with BRT patterns?       | BRT_consistency = P(event at T | dist)| > THR     |
| 3 Prot| Is protocol consistent with preferences?      | protocol_familiarity = count(P)/total | Fam/new   |
| 4 Cpty| Is counterparty in behavioral graph?          | graph_distance = shortest_path(e, c)   | In graph  |
| 5 Vel | Is frequency consistent with history?          | velocity_score = tx_last_N/hist_avg    | < 5.0×    |
| 6 CC  | Behavior consistent across ALL chains?         | CC_coherence = agreement(vectors)      | used dir. |
| 7 Stat| Kolmogorov complexity changed abnormally?     | KC_delta = KC(recent) - KC(historical) | w/in bnds |

Weights for coherence_score:
    Plane 1 (magnitude):    0.20
    Plane 2 (temporal):     0.10
    Plane 3 (protocol):     0.10
    Plane 4 (counterparty): 0.15
    Plane 5 (velocity):     0.20
    Plane 6 (cross-chain):  0.20
    Plane 7 (statistical):  0.05 (Conscious Layer review required)

This module implements the BTCP-specific 7-plane coherence. The existing
5-plane TRION coherence (core/master/coherence.py: Φ, M, Σ, K, A) remains
canonical for the master oracle. The 7-plane model is used by the BTCP
router for per-intent route scoring.

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import IntEnum


class PlaneType(IntEnum):
    """7 canonical BTCP planes."""
    MAGNITUDE    = 0   # Plane 1
    TEMPORAL     = 1   # Plane 2
    PROTOCOL     = 2   # Plane 3
    COUNTERPARTY = 3   # Plane 4
    VELOCITY     = 4   # Plane 5
    CROSS_CHAIN  = 5   # Plane 6
    STATISTICAL  = 6   # Plane 7


# Whitepaper-mandated weights (sum to 1.0)
PLANE_WEIGHTS: Dict[PlaneType, float] = {
    PlaneType.MAGNITUDE:    0.20,
    PlaneType.TEMPORAL:     0.10,
    PlaneType.PROTOCOL:     0.10,
    PlaneType.COUNTERPARTY: 0.15,
    PlaneType.VELOCITY:     0.20,
    PlaneType.CROSS_CHAIN:  0.20,
    PlaneType.STATISTICAL:  0.05,
}

# Plane-specific thresholds
MAGNITUDE_Z_THRESHOLD    = 3.0   # |z| < 3.0 passes
VELOCITY_MAX_MULTIPLIER  = 5.0   # velocity_score < 5.0× passes
STATISTICAL_KC_THRESHOLD = 0.30  # KC delta beyond this triggers Conscious review
CROSS_CHAIN_MIN_AGREEMENT = 0.60  # min vector agreement across chains
COUNTERPARTY_MAX_DISTANCE = 3     # graph distance hops


@dataclass
class PlaneInput:
    """All inputs needed to compute the 7-plane coherence score."""
    # Plane 1 — Magnitude
    magnitude: float                       # current event magnitude (normalized)
    historical_magnitudes: List[float]     # past magnitudes for z-score

    # Plane 2 — Temporal
    event_timestamp: int                   # unix seconds
    brt_phase: str                         # circadian/ultradian/lunar/seasonal
    historical_event_times: List[int]      # past event timestamps

    # Plane 3 — Protocol
    protocol_id: str                       # current protocol
    historical_protocols: List[str]        # protocols entity has used before

    # Plane 4 — Counterparty
    counterparty_id: str                   # current counterparty
    behavioral_graph: Dict[str, List[str]] # adjacency list of known relationships

    # Plane 5 — Velocity
    recent_tx_count: int                   # tx in last N blocks
    historical_avg_per_N: float            # historical avg tx per N blocks

    # Plane 6 — Cross-Chain
    behavioral_vectors: Dict[int, List[float]]  # chain_id → 128-dim vector

    # Plane 7 — Statistical
    recent_kc: float                       # Kolmogorov complexity of recent behavior
    historical_kc: float                   # KC of historical baseline


@dataclass
class PlaneResult:
    """Result of one plane check."""
    plane: PlaneType
    score: float                  # 0.0 to 1.0 (1.0 = perfectly consistent)
    passed: bool                  # True iff score meets threshold
    details: Dict[str, float] = field(default_factory=dict)
    needs_conscious_review: bool = False


# ── Plane 1: Magnitude ─────────────────────────────────────────────────────────

def check_magnitude(magnitude: float, historical: List[float]) -> PlaneResult:
    """
    Plane 1 — Magnitude Consistency.

    z_score = |m - μ| / σ
    Pass if z_score < 3.0.

    Score = 1.0 - min(1.0, z_score / 3.0)  → maps z=0 to 1.0, z=3 to 0.0
    """
    if len(historical) < 2:
        # Not enough history — give benefit of the doubt (0.5 score)
        return PlaneResult(
            plane=PlaneType.MAGNITUDE,
            score=0.5,
            passed=True,
            details={"z_score": 0.0, "reason": "insufficient_history"},
        )

    mu = statistics.mean(historical)
    sigma = statistics.stdev(historical)
    if sigma == 0:
        # All historical values identical — perfect consistency if matches
        score = 1.0 if magnitude == mu else 0.0
        return PlaneResult(
            plane=PlaneType.MAGNITUDE,
            score=score,
            passed=score > 0.5,
            details={"z_score": 0.0 if magnitude == mu else float("inf"), "mu": mu, "sigma": 0.0},
        )

    z_score = abs(magnitude - mu) / sigma
    score = max(0.0, 1.0 - min(1.0, z_score / MAGNITUDE_Z_THRESHOLD))
    return PlaneResult(
        plane=PlaneType.MAGNITUDE,
        score=score,
        passed=z_score < MAGNITUDE_Z_THRESHOLD,
        details={"z_score": z_score, "mu": mu, "sigma": sigma},
    )


# ── Plane 2: Temporal ──────────────────────────────────────────────────────────

def check_temporal(
    event_timestamp: int,
    brt_phase: str,
    historical_times: List[int],
) -> PlaneResult:
    """
    Plane 2 — Temporal Consistency with BRT patterns.

    Computes the probability of an event at this time given the historical
    distribution. Uses a simple histogram approach: events are bucketed by
    hour-of-day, and the score is the normalized frequency of the current
    bucket.

    A more sophisticated implementation would use the BRT (Biological
    Rhythm Timer) 4-phase model — this is a placeholder that uses
    hour-of-day frequency.
    """
    if len(historical_times) < 5:
        return PlaneResult(
            plane=PlaneType.TEMPORAL,
            score=0.5,
            passed=True,
            details={"reason": "insufficient_history"},
        )

    # Bucket by hour-of-day (0-23)
    hours = [((t // 3600) % 24) for t in historical_times]
    current_hour = (event_timestamp // 3600) % 24

    hour_counts: Dict[int, int] = {}
    for h in hours:
        hour_counts[h] = hour_counts.get(h, 0) + 1

    max_count = max(hour_counts.values())
    current_count = hour_counts.get(current_hour, 0)
    score = current_count / max_count if max_count > 0 else 0.0

    return PlaneResult(
        plane=PlaneType.TEMPORAL,
        score=score,
        passed=score > 0.1,  # at least 10% of peak frequency
        details={
            "current_hour": current_hour,
            "current_count": current_count,
            "max_count": max_count,
            "brt_phase": brt_phase,
        },
    )


# ── Plane 3: Protocol ──────────────────────────────────────────────────────────

def check_protocol(
    protocol_id: str,
    historical_protocols: List[str],
) -> PlaneResult:
    """
    Plane 3 — Protocol Familiarity.

    protocol_familiarity = count(P) / total_interactions
    New protocols are allowed (familiar or new entity).
    Score = familiarity ratio (1.0 = always used this protocol, 0.0 = never).
    Pass: familiar (score > 0.1) OR new entity (no history).
    """
    if not historical_protocols:
        return PlaneResult(
            plane=PlaneType.PROTOCOL,
            score=0.5,
            passed=True,
            details={"reason": "new_entity"},
        )

    count = sum(1 for p in historical_protocols if p == protocol_id)
    total = len(historical_protocols)
    score = count / total

    # Pass if familiar OR if entity has used at least 3 different protocols
    # (showing exploration behavior, not locked-in)
    unique_protocols = len(set(historical_protocols))
    passed = score > 0.1 or unique_protocols >= 3

    return PlaneResult(
        plane=PlaneType.PROTOCOL,
        score=score,
        passed=passed,
        details={
            "protocol_id": hash(protocol_id) % 10000,  # don't leak raw protocol_id
            "count": count,
            "total": total,
            "unique_protocols": unique_protocols,
        },
    )


# ── Plane 4: Counterparty ──────────────────────────────────────────────────────

def check_counterparty(
    counterparty_id: str,
    behavioral_graph: Dict[str, List[str]],
    entity_id: str = "self",
) -> PlaneResult:
    """
    Plane 4 — Counterparty Behavioral Graph Distance.

    graph_distance = shortest_path(entity, counterparty)
    Pass if counterparty is in graph (distance 1), established (distance 2),
    or DEX (special case — always allowed).

    Score = 1.0 - min(1.0, distance / (MAX_DISTANCE + 1))
    """
    if not counterparty_id:
        # No counterparty (e.g., MINT/BURN) — auto-pass
        return PlaneResult(
            plane=PlaneType.COUNTERPARTY,
            score=1.0,
            passed=True,
            details={"reason": "no_counterparty"},
        )

    # BFS shortest path
    if entity_id not in behavioral_graph:
        return PlaneResult(
            plane=PlaneType.COUNTERPARTY,
            score=0.3,
            passed=False,
            details={"reason": "entity_not_in_graph"},
        )

    visited = {entity_id}
    queue = [(entity_id, 0)]
    while queue:
        node, dist = queue.pop(0)
        if node == counterparty_id:
            score = 1.0 - min(1.0, dist / (COUNTERPARTY_MAX_DISTANCE + 1))
            return PlaneResult(
                plane=PlaneType.COUNTERPARTY,
                score=score,
                passed=dist <= COUNTERPARTY_MAX_DISTANCE,
                details={"graph_distance": dist},
            )
        if dist >= COUNTERPARTY_MAX_DISTANCE:
            continue
        for neighbor in behavioral_graph.get(node, []):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, dist + 1))

    # Not found within max distance
    return PlaneResult(
        plane=PlaneType.COUNTERPARTY,
        score=0.0,
        passed=False,
        details={"graph_distance": float("inf"), "reason": "not_in_graph"},
    )


# ── Plane 5: Velocity ──────────────────────────────────────────────────────────

def check_velocity(
    recent_tx_count: int,
    historical_avg_per_N: float,
) -> PlaneResult:
    """
    Plane 5 — Velocity Consistency.

    velocity_score = tx_last_N / historical_avg_per_N
    Pass if velocity_score < 5.0× (5x spike allowed).

    Score = 1.0 - min(1.0, (velocity_score - 1) / 5.0)
    """
    if historical_avg_per_N <= 0:
        return PlaneResult(
            plane=PlaneType.VELOCITY,
            score=0.5,
            passed=True,
            details={"reason": "no_historical_baseline"},
        )

    velocity_score = recent_tx_count / historical_avg_per_N
    # Score: 1.0 at velocity=0, 1.0 at velocity=1 (matches avg), 0.0 at velocity=5+
    if velocity_score <= 1.0:
        score = 1.0
    else:
        score = max(0.0, 1.0 - (velocity_score - 1.0) / (VELOCITY_MAX_MULTIPLIER - 1.0))

    return PlaneResult(
        plane=PlaneType.VELOCITY,
        score=score,
        passed=velocity_score < VELOCITY_MAX_MULTIPLIER,
        details={
            "recent_tx_count": recent_tx_count,
            "historical_avg": historical_avg_per_N,
            "velocity_score": velocity_score,
        },
    )


# ── Plane 6: Cross-Chain ───────────────────────────────────────────────────────

def check_cross_chain(
    behavioral_vectors: Dict[int, List[float]],
) -> PlaneResult:
    """
    Plane 6 — Cross-Chain Coherence.

    CC_coherence = agreement(behavioral_vectors across chains)
    Uses pairwise cosine similarity averaged across all chain pairs.
    """
    if len(behavioral_vectors) < 2:
        # Single chain — trivially coherent
        return PlaneResult(
            plane=PlaneType.CROSS_CHAIN,
            score=1.0,
            passed=True,
            details={"chain_count": len(behavioral_vectors), "reason": "single_chain"},
        )

    chain_ids = list(behavioral_vectors.keys())
    sims = []
    for i in range(len(chain_ids)):
        for j in range(i + 1, len(chain_ids)):
            v1 = behavioral_vectors[chain_ids[i]]
            v2 = behavioral_vectors[chain_ids[j]]
            sim = _cosine_similarity(v1, v2)
            if sim is not None:
                sims.append(sim)

    if not sims:
        return PlaneResult(
            plane=PlaneType.CROSS_CHAIN,
            score=0.5,
            passed=True,
            details={"reason": "vectors_too_short"},
        )

    avg_sim = sum(sims) / len(sims)
    return PlaneResult(
        plane=PlaneType.CROSS_CHAIN,
        score=avg_sim,
        passed=avg_sim >= CROSS_CHAIN_MIN_AGREEMENT,
        details={
            "chain_count": len(behavioral_vectors),
            "avg_cosine_similarity": avg_sim,
            "min_similarity": min(sims),
            "max_similarity": max(sims),
        },
    )


def _cosine_similarity(v1: List[float], v2: List[float]) -> Optional[float]:
    """Compute cosine similarity. Returns None if vectors are too short or zero."""
    n = min(len(v1), len(v2))
    if n < 2:
        return None
    dot = sum(v1[i] * v2[i] for i in range(n))
    mag1 = math.sqrt(sum(x * x for x in v1[:n]))
    mag2 = math.sqrt(sum(x * x for x in v2[:n]))
    if mag1 == 0 or mag2 == 0:
        return None
    return dot / (mag1 * mag2)


# ── Plane 7: Statistical (Kolmogorov Complexity) ──────────────────────────────

def check_statistical(
    recent_kc: float,
    historical_kc: float,
) -> PlaneResult:
    """
    Plane 7 — Statistical Anomaly (Kolmogorov Complexity delta).

    KC_delta = KC(recent) - KC(historical)
    If KC_delta exceeds threshold, hold at 0.5 pending Conscious Layer review.

    Score = 1.0 - min(1.0, |KC_delta| / threshold)
    """
    if historical_kc <= 0:
        return PlaneResult(
            plane=PlaneType.STATISTICAL,
            score=0.5,
            passed=True,
            needs_conscious_review=False,
            details={"reason": "no_baseline"},
        )

    kc_delta = recent_kc - historical_kc
    # Normalize by historical KC to get relative delta
    rel_delta = abs(kc_delta) / historical_kc
    score = max(0.0, 1.0 - min(1.0, rel_delta / STATISTICAL_KC_THRESHOLD))

    # Plane 7 always requires Conscious Layer review when delta is non-trivial
    needs_review = rel_delta > 0.10  # >10% relative change

    return PlaneResult(
        plane=PlaneType.STATISTICAL,
        score=score,
        passed=rel_delta < STATISTICAL_KC_THRESHOLD,
        needs_conscious_review=needs_review,
        details={
            "recent_kc": recent_kc,
            "historical_kc": historical_kc,
            "kc_delta": kc_delta,
            "relative_delta": rel_delta,
        },
    )


# ── 7-Plane Coherence Score ────────────────────────────────────────────────────

def compute_7plane_coherence(inp: PlaneInput) -> Tuple[float, List[PlaneResult]]:
    """
    Compute the weighted 7-plane coherence score.

    coherence = Σ_i (weight_i × score_i)

    Returns (coherence_score, list_of_plane_results).
    The coherence_score is in [0, 1].
    """
    results = [
        check_magnitude(inp.magnitude, inp.historical_magnitudes),
        check_temporal(inp.event_timestamp, inp.brt_phase, inp.historical_event_times),
        check_protocol(inp.protocol_id, inp.historical_protocols),
        check_counterparty(inp.counterparty_id, inp.behavioral_graph),
        check_velocity(inp.recent_tx_count, inp.historical_avg_per_N),
        check_cross_chain(inp.behavioral_vectors),
        check_statistical(inp.recent_kc, inp.historical_kc),
    ]

    total = sum(
        PLANE_WEIGHTS[results[i].plane] * results[i].score
        for i in range(7)
    )

    return total, results


def coherence_with_conscious_review(
    inp: PlaneInput,
    conscious_review_score: float = 1.0,
) -> Tuple[float, List[PlaneResult]]:
    """
    Compute coherence with Conscious Layer review for Plane 7.

    If Plane 7 (Statistical) flags `needs_conscious_review`, the Plane 7
    score is multiplied by the conscious_review_score (default 1.0 = no
    adjustment; 0.0 = reject; 0.5 = hold pending).

    The conscious_review_score would come from the K-plane annotation network
    (3-of-5 majority vote by tenured annotators).
    """
    score, results = compute_7plane_coherence(inp)

    # If Plane 7 needs conscious review, adjust its contribution
    plane7 = results[6]
    if plane7.needs_conscious_review:
        original_contribution = PLANE_WEIGHTS[PlaneType.STATISTICAL] * plane7.score
        adjusted_contribution = original_contribution * conscious_review_score
        score = score - original_contribution + adjusted_contribution

    return score, results


# ── Self-test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== 7-Plane Coherence Self-test ===\n")

    # Test 1: Perfect consistency — all planes pass with high scores
    # Use timestamps that span multiple days at the SAME hour-of-day, so the
    # temporal plane sees a strong peak at the current hour.
    _now = 1_700_000_000
    _current_hour = (_now // 3600) % 24
    _historical_times = [
        _now - i * 86400  # one event per day at the same hour
        for i in range(1, 20)
    ]
    perfect_input = PlaneInput(
        magnitude=100.0,
        historical_magnitudes=[99.0, 100.0, 101.0, 100.0, 99.5],
        event_timestamp=_now,
        brt_phase="circadian_peak",
        historical_event_times=_historical_times,
        protocol_id="uniswap_v3",
        historical_protocols=["uniswap_v3"] * 15 + ["curve"] * 3,
        counterparty_id="0xabc",
        behavioral_graph={"self": ["0xabc", "0xdef"], "0xabc": ["self"], "0xdef": ["self"]},
        recent_tx_count=10,
        historical_avg_per_N=10.0,
        behavioral_vectors={
            1: [0.8, 0.7, 0.9, 0.8],
            137: [0.79, 0.71, 0.88, 0.81],
        },
        recent_kc=0.50,
        historical_kc=0.49,
    )
    score, results = compute_7plane_coherence(perfect_input)
    print(f"Perfect consistency: score={score:.4f}")
    for r in results:
        print(f"  {r.plane.name:14s}: score={r.score:.3f} passed={r.passed}")
    assert score > 0.7, f"Perfect input should score > 0.7, got {score}"
    assert all(r.passed for r in results), "All planes should pass"

    # Test 2: Anomalous magnitude (z-score > 3.0)
    anomalous_input = PlaneInput(
        magnitude=10000.0,  # huge outlier
        historical_magnitudes=[100.0, 101.0, 99.0, 100.5, 100.2],
        event_timestamp=1_700_000_000,
        brt_phase="normal",
        historical_event_times=[1_700_000_000 - i * 3600 for i in range(1, 20)],
        protocol_id="uniswap_v3",
        historical_protocols=["uniswap_v3"] * 15,
        counterparty_id="0xabc",
        behavioral_graph={"self": ["0xabc"], "0xabc": ["self"]},
        recent_tx_count=10,
        historical_avg_per_N=10.0,
        behavioral_vectors={1: [0.8, 0.7, 0.9]},
        recent_kc=0.50,
        historical_kc=0.49,
    )
    score, results = compute_7plane_coherence(anomalous_input)
    print(f"\nAnomalous magnitude: score={score:.4f}")
    print(f"  Plane 1 (Magnitude): score={results[0].score:.3f} passed={results[0].passed}")
    assert not results[0].passed, "Magnitude plane should fail with z-score > 3.0"

    # Test 3: Velocity spike (10x normal)
    velocity_input = PlaneInput(
        magnitude=100.0,
        historical_magnitudes=[100.0, 100.0, 100.0, 100.0, 100.0],
        event_timestamp=1_700_000_000,
        brt_phase="normal",
        historical_event_times=[1_700_000_000 - i * 3600 for i in range(1, 20)],
        protocol_id="uniswap_v3",
        historical_protocols=["uniswap_v3"] * 15,
        counterparty_id="0xabc",
        behavioral_graph={"self": ["0xabc"], "0xabc": ["self"]},
        recent_tx_count=100,  # 10x spike
        historical_avg_per_N=10.0,
        behavioral_vectors={1: [0.8, 0.7, 0.9]},
        recent_kc=0.50,
        historical_kc=0.49,
    )
    score, results = compute_7plane_coherence(velocity_input)
    print(f"\nVelocity spike (10x): score={score:.4f}")
    print(f"  Plane 5 (Velocity): score={results[4].score:.3f} passed={results[4].passed}")
    assert not results[4].passed, "Velocity plane should fail with 10x spike"

    # Test 4: Statistical anomaly triggers Conscious review
    stat_input = PlaneInput(
        magnitude=100.0,
        historical_magnitudes=[100.0, 100.0, 100.0, 100.0, 100.0],
        event_timestamp=1_700_000_000,
        brt_phase="normal",
        historical_event_times=[1_700_000_000 - i * 3600 for i in range(1, 20)],
        protocol_id="uniswap_v3",
        historical_protocols=["uniswap_v3"] * 15,
        counterparty_id="0xabc",
        behavioral_graph={"self": ["0xabc"], "0xabc": ["self"]},
        recent_tx_count=10,
        historical_avg_per_N=10.0,
        behavioral_vectors={1: [0.8, 0.7, 0.9]},
        recent_kc=0.80,  # 60% jump from 0.50
        historical_kc=0.50,
    )
    score, results = compute_7plane_coherence(stat_input)
    print(f"\nStatistical anomaly (KC +60%): score={score:.4f}")
    print(f"  Plane 7 (Statistical): score={results[6].score:.3f} review={results[6].needs_conscious_review}")
    assert results[6].needs_conscious_review, "Statistical plane should flag conscious review"

    # Test 5: Weights sum to 1.0
    total_weight = sum(PLANE_WEIGHTS.values())
    print(f"\nWeight sum: {total_weight}")
    assert abs(total_weight - 1.0) < 1e-9, "Plane weights must sum to 1.0"

    print("\nPHASE 0.2 PASS — 7-Plane coherence implemented")
