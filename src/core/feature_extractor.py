"""
Physical Feature Extractor — TRION L1
Computes 9 behavioral entropy features per asset per time window.
All outputs normalized to [0,1]. Invariant enforced at runtime.

Features:
  f1 — Transaction volume entropy (Shannon)
  f2 — Counterparty diversity ratio
  f3 — Temporal spacing entropy
  f4 — Smart contract interaction breadth
  f5 — Value flow directionality (bidirectional = healthy)
  f6 — Wallet architecture diversity (prefix entropy)
  f7 — Cross-protocol breadth
  f8 — Gas usage pattern entropy
  f9 — MEV interaction (inverted: high MEV → lower f9)
"""
import math
from typing import List, Dict
from dataclasses import dataclass


def shannon_entropy_normalized(values: List[float]) -> float:
    """H_norm = H / log(n) — normalized to [0,1]."""
    total = sum(values)
    if total == 0:
        return 0.0
    probs = [v / total for v in values if v > 0]
    raw_h = -sum(p * math.log(p) for p in probs)
    max_h = math.log(len(values)) if len(values) > 1 else 1.0
    return raw_h / max_h if max_h > 0 else 0.0


@dataclass
class FeatureWindow:
    volumes:           List[float]
    counterparties:    List[str]
    timestamps:        List[float]
    contracts_touched: List[str]
    inflow:            float
    outflow:           float
    protocol_ids:      List[str]
    gas_prices:        List[float]
    mev_tx_count:      int
    total_tx_count:    int


def extract_features(window: FeatureWindow) -> Dict[str, float]:
    """
    Returns f1–f9 as a dict, all values in [0,1].
    Raises AssertionError if any feature violates the invariant.
    """
    if window.total_tx_count == 0:
        return {f"f{i}": 0.0 for i in range(1, 10)}

    # f1: Transaction volume entropy
    f1 = shannon_entropy_normalized(window.volumes) if window.volumes else 0.0

    # f2: Counterparty diversity
    unique_cp = len(set(window.counterparties))
    f2 = unique_cp / max(len(window.counterparties), 1)

    # f3: Temporal spacing entropy
    if len(window.timestamps) > 1:
        gaps = [max(0.0, window.timestamps[i+1] - window.timestamps[i])
                for i in range(len(window.timestamps) - 1)]
        f3 = shannon_entropy_normalized(gaps) if any(g > 0 for g in gaps) else 0.0
    else:
        f3 = 0.0

    # f4: Smart contract interaction breadth
    unique_contracts = len(set(window.contracts_touched))
    f4 = min(unique_contracts / max(window.total_tx_count, 1), 1.0)

    # f5: Value flow directionality (balanced = healthy = 1.0)
    gross = window.inflow + window.outflow
    f5 = (1.0 - abs(window.inflow - window.outflow) / gross) if gross > 0 else 0.0

    # f6: Wallet architecture diversity (prefix entropy proxy)
    prefixes = [cp[:4] for cp in window.counterparties if len(cp) >= 4]
    counts: Dict[str, int] = {}
    for p in prefixes:
        counts[p] = counts.get(p, 0) + 1
    f6 = shannon_entropy_normalized(list(counts.values())) if counts else 0.0

    # f7: Cross-protocol breadth
    f7 = min(len(set(window.protocol_ids)) / 10.0, 1.0)

    # f8: Gas usage pattern entropy
    f8 = shannon_entropy_normalized(window.gas_prices) if window.gas_prices else 0.0

    # f9: MEV interaction (inverted — high MEV = lower f9)
    f9 = 1.0 - min(window.mev_tx_count / max(window.total_tx_count, 1), 1.0)

    result = {
        "f1": round(f1, 6), "f2": round(f2, 6), "f3": round(f3, 6),
        "f4": round(f4, 6), "f5": round(f5, 6), "f6": round(f6, 6),
        "f7": round(f7, 6), "f8": round(f8, 6), "f9": round(f9, 6),
    }

    for k, v in result.items():
        assert 0.0 <= v <= 1.0, f"Feature {k} out of [0,1]: {v}"

    return result
