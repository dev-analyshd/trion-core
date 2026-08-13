"""
TRION Protocol — L2.3: Akashic Depth D(t)
D(t) = Σ_τ [BH_count(τ) × recency_weight(τ) × cross_chain_multiplier(τ)]

recency_weight(τ) = e^(-λ(t-τ))  λ=0.0001 per block
cross_chain_multiplier = 1 + 0.1 × (N_chains - 1)

The Depth Moat: cost to forge D(t) ≥ block_cost × N_blocks × N_chains
LSS grows as K(D(t)) ≥ Ω(t · N_chains · N_validators · H_env)
"""

import math
from typing import List
from dataclasses import dataclass


RECENCY_LAMBDA = 0.0001  # per-block decay


@dataclass
class BlockRecord:
    block_number:  int
    bh_count:      int       # behavioral events in this block
    chain_id:      int
    timestamp:     float


def recency_weight(block_number: int, current_block: int) -> float:
    """e^(-λ(t-τ)) — exponential recency weighting."""
    age = max(0, current_block - block_number)
    return math.exp(-RECENCY_LAMBDA * age)


def cross_chain_multiplier(n_chains: int) -> float:
    """1 + 0.1 × (N_chains - 1) — multi-chain depth bonus."""
    return 1.0 + 0.1 * max(0, n_chains - 1)


def compute_depth(
    records:       List[BlockRecord],
    current_block: int,
    n_chains:      int = 1,
) -> dict:
    """Full D(t) computation."""
    if not records:
        return {"depth": 0.0, "record_count": 0, "chains": n_chains}

    cc_mult = cross_chain_multiplier(n_chains)

    weighted_sum = sum(
        r.bh_count * recency_weight(r.block_number, current_block)
        for r in records
    )

    depth = weighted_sum * cc_mult

    oldest_block = min(r.block_number for r in records)
    newest_block = max(r.block_number for r in records)

    return {
        "depth":         depth,
        "record_count":  len(records),
        "chains":        n_chains,
        "cc_multiplier": cc_mult,
        "oldest_block":  oldest_block,
        "newest_block":  newest_block,
        "span_blocks":   newest_block - oldest_block,
    }


def dormancy_decay(depth: float, blocks_inactive: int) -> float:
    """
    Dormancy decay: depth decays if entity is inactive.
    D_decayed = D × e^(-λ × blocks_inactive)
    """
    return depth * math.exp(-RECENCY_LAMBDA * blocks_inactive)


if __name__ == "__main__":
    records = [
        BlockRecord(18000000 - i*100, bh_count=5 + i % 3, chain_id=1, timestamp=0.0)
        for i in range(100)
    ]
    result = compute_depth(records, current_block=18000000, n_chains=5)
    print(f"D(t) = {result['depth']:.2f}")
    print(f"  Records: {result['record_count']}, Chains: {result['chains']}")
    print(f"  CC multiplier: {result['cc_multiplier']:.2f}")
    decayed = dormancy_decay(result['depth'], blocks_inactive=50000)
    print(f"  After 50k blocks dormancy: {decayed:.2f} (decay={decayed/result['depth']:.2%})")
    assert result['depth'] > 0
    print("PHASE D PASS — Akashic Depth D(t) implemented")
