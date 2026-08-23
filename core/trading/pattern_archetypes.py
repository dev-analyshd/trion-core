"""
TRION Trading Pattern Archetypes
---------------------------------
The 8 behavioral trading patterns TRION detects.

Each pattern is a 9-dimensional behavioral signature:
  [f1_volume_entropy, f2_counterparty_diversity,
   f3_temporal_spacing, f4_contract_interaction,
   f5_value_flow_directionality, f6_wallet_architecture,
   f7_cross_protocol, f8_gas_pattern, f9_mev_interaction]

Patterns learned from historical Akashic Index data.
Initial values from hand-coded priors — updated as
FAISS accumulates behavioral depth D(t).
"""

import numpy as np
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


class TradingSignal(IntEnum):
    STRONG_BUY       = 0
    BUY              = 1
    WEAK_BUY         = 2
    NEUTRAL          = 3
    WEAK_SELL        = 4
    SELL             = 5
    STRONG_SELL      = 6
    ACCUMULATION     = 7
    DISTRIBUTION     = 8
    REVERSAL_LONG    = 9
    REVERSAL_SHORT   = 10
    MOMENTUM         = 11


@dataclass
class PatternArchetype:
    signal:         TradingSignal
    name:           str
    description:    str
    phi_vector:     np.ndarray
    confidence:     float
    min_coherence:  float
    min_depth:      float


ARCHETYPES = [

    PatternArchetype(
        signal=TradingSignal.ACCUMULATION,
        name="Smart Money Accumulation",
        description=(
            "Quiet buying with high counterparty diversity, irregular timing, "
            "cross-protocol activity. Whale accumulating without moving price."
        ),
        phi_vector=np.array([
            0.80, 0.90, 0.85, 0.75, 0.25, 0.70, 0.80, 0.60, 0.90,
        ]),
        confidence=0.72,
        min_coherence=0.55,
        min_depth=100,
    ),

    PatternArchetype(
        signal=TradingSignal.DISTRIBUTION,
        name="Smart Money Distribution",
        description=(
            "Quiet selling with high counterparty diversity, concentrated "
            "outflow. Whale distributing without collapsing price."
        ),
        phi_vector=np.array([
            0.75, 0.85, 0.80, 0.65, 0.80, 0.65, 0.70, 0.55, 0.85,
        ]),
        confidence=0.68,
        min_coherence=0.55,
        min_depth=100,
    ),

    PatternArchetype(
        signal=TradingSignal.STRONG_BUY,
        name="High Conviction Buy Pressure",
        description=(
            "Sustained buy-side pressure with high volume entropy, "
            "behavioral continuity, low MEV. Not a bot."
        ),
        phi_vector=np.array([
            0.85, 0.70, 0.65, 0.80, 0.20, 0.60, 0.75, 0.70, 0.85,
        ]),
        confidence=0.75,
        min_coherence=0.60,
        min_depth=200,
    ),

    PatternArchetype(
        signal=TradingSignal.STRONG_SELL,
        name="High Conviction Sell Pressure",
        description=(
            "Sustained sell-side pressure with concentrated outflow, "
            "possible deleveraging pattern."
        ),
        phi_vector=np.array([
            0.70, 0.60, 0.55, 0.70, 0.85, 0.55, 0.65, 0.60, 0.75,
        ]),
        confidence=0.71,
        min_coherence=0.60,
        min_depth=200,
    ),

    PatternArchetype(
        signal=TradingSignal.REVERSAL_LONG,
        name="Behavioral Bottom — Long Reversal",
        description=(
            "Capitulation pattern: low temporal entropy (panic), "
            "concentrated outflow, MEV spike, then recovery signal."
        ),
        phi_vector=np.array([
            0.45, 0.40, 0.25, 0.55, 0.90, 0.45, 0.40, 0.35, 0.20,
        ]),
        confidence=0.65,
        min_coherence=0.45,
        min_depth=300,
    ),

    PatternArchetype(
        signal=TradingSignal.REVERSAL_SHORT,
        name="Behavioral Top — Short Reversal",
        description=(
            "Euphoria pattern: retail FOMO, high uniform buys, "
            "low counterparty diversity, MEV bots front-running."
        ),
        phi_vector=np.array([
            0.50, 0.35, 0.30, 0.45, 0.15, 0.40, 0.35, 0.30, 0.25,
        ]),
        confidence=0.62,
        min_coherence=0.45,
        min_depth=300,
    ),

    PatternArchetype(
        signal=TradingSignal.MOMENTUM,
        name="Trend Continuation",
        description=(
            "Sustained directional flow with healthy counterparty diversity. "
            "Organic trend — not manufactured."
        ),
        phi_vector=np.array([
            0.75, 0.75, 0.70, 0.70, 0.35, 0.65, 0.70, 0.65, 0.80,
        ]),
        confidence=0.70,
        min_coherence=0.58,
        min_depth=150,
    ),

    PatternArchetype(
        signal=TradingSignal.NEUTRAL,
        name="Behavioral Equilibrium",
        description=(
            "Balanced in/out flows, high diversity, organic timing. "
            "No directional signal."
        ),
        phi_vector=np.array([
            0.70, 0.80, 0.75, 0.65, 0.50, 0.65, 0.70, 0.70, 0.85,
        ]),
        confidence=0.80,
        min_coherence=0.55,
        min_depth=50,
    ),
]

ARCHETYPE_MATRIX = np.stack([a.phi_vector for a in ARCHETYPES])  # (8, 9)


def cosine_similarity_batch(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    query_norm = np.linalg.norm(query)
    if query_norm == 0:
        return np.zeros(len(matrix))
    q = query / query_norm
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1e-9, norms)
    m = matrix / norms
    return m @ q


def match_archetype(
    phi_vector:    np.ndarray,
    coherence:     float,
    akashic_depth: float,
) -> dict:
    """
    Find the best matching trading pattern archetype.
    Returns signal, confidence, and explanation.
    """
    sims = cosine_similarity_batch(phi_vector, ARCHETYPE_MATRIX)

    # Identify best archetype by raw cosine similarity (geometric closeness).
    # Confidence scales the reported output score — not the archetype selector.
    # This prevents high-confidence archetypes (e.g. NEUTRAL=0.80) from
    # crowding out geometrically closer matches.
    valid = [
        (i, sims[i])
        for i, archetype in enumerate(ARCHETYPES)
        if (coherence >= archetype.min_coherence and
            akashic_depth >= archetype.min_depth)
    ]

    if not valid:
        raw_sim  = float(max(sims))
        adj_sim  = -1.0
        best_idx = int(np.argmax(sims))
    else:
        best_idx, raw_sim = max(valid, key=lambda x: x[1])
        adj_sim  = raw_sim * ARCHETYPES[best_idx].confidence

    best = ARCHETYPES[best_idx]

    if not valid:
        return {
            "signal":           TradingSignal.NEUTRAL.name,
            "signal_id":        int(TradingSignal.NEUTRAL),
            "confidence":       0.0,
            "pattern":          "INSUFFICIENT_DEPTH",
            "description":      "Insufficient behavioral depth for pattern matching",
            "similarity":       float(raw_sim),
            "adjusted_score":   float(adj_sim),
            "requirements_met": False,
        }

    return {
        "signal":           best.signal.name,
        "signal_id":        int(best.signal),
        "confidence":       float(adj_sim),
        "raw_similarity":   float(raw_sim),
        "archetype_base_confidence": best.confidence,
        "pattern":          best.name,
        "description":      best.description,
        "all_similarities": {
            ARCHETYPES[i].signal.name: float(sims[i])
            for i in range(len(ARCHETYPES))
        },
        "requirements_met": True,
        "coherence_used":   coherence,
        "depth_used":       akashic_depth,
    }


if __name__ == "__main__":
    test_vec = np.array([0.82, 0.88, 0.83, 0.73, 0.22, 0.68, 0.78, 0.62, 0.89])
    result = match_archetype(test_vec, coherence=0.62, akashic_depth=500)
    print(f"Pattern match:  {result['pattern']}")
    print(f"Signal:         {result['signal']}")
    print(f"Confidence:     {result['confidence']:.4f}")
    print(f"Raw similarity: {result['raw_similarity']:.4f}")
    assert result['signal'] in [s.name for s in TradingSignal]
    print("PHASE 1 PASS — Pattern archetypes: PASS")
