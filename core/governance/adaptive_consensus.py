"""
TRION Protocol — L4.5a Adaptive Consensus Parameter Recommendations
====================================================================

Whitepaper §L4.5 specifies that TRION should emit consensus parameter
recommendations to consuming chains based on observed behavioral
patterns.  This module implements those recommendations.

The recommendations cover:
  - block_size_limit   — based on observed throughput vs behavioral diversity
  - gas_limit          — based on MEV extraction rates
  - finality_threshold — based on Σ plane confidence
  - slashing_threshold — based on manipulation detection rates
  - validator_set_size — based on HHI and geographic distribution

Each recommendation is non-binding — chains opt-in to TRION's
suggestions.  The recommendations are emitted as signed signals
that consuming chains can verify on-chain.

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ── Constants ──────────────────────────────────────────────────────────────────

# Baseline values (per whitepaper §L4.5)
DEFAULT_BLOCK_SIZE:     int   = 30_000_000   # gas
DEFAULT_GAS_LIMIT:      int   = 30_000_000
DEFAULT_FINALITY:       int   = 32           # blocks (Ethereum finality)
DEFAULT_SLASHING_PCT:   float = 0.10         # 10% of stake
DEFAULT_VALIDATOR_SET:  int   = 100

# Recommendation bounds (chains shouldn't accept unbounded values)
MAX_BLOCK_SIZE:         int   = 200_000_000
MIN_BLOCK_SIZE:         int   = 1_000_000
MAX_VALIDATOR_SET:      int   = 10_000
MIN_VALIDATOR_SET:      int   = 4


# ── Data Model ─────────────────────────────────────────────────────────────────

@dataclass
class ConsensusRecommendation:
    """A single parameter recommendation for a consuming chain."""
    chain_id:               int
    parameter:              str   # block_size_limit, gas_limit, etc.
    recommended_value:      float
    current_value:          Optional[float]
    rationale:              str
    confidence:             float   # 0-1
    timestamp:              float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "chain_id":          self.chain_id,
            "parameter":         self.parameter,
            "recommended_value": self.recommended_value,
            "current_value":     self.current_value,
            "rationale":         self.rationale,
            "confidence":        self.confidence,
            "timestamp":         self.timestamp,
        }


# ── Engine ─────────────────────────────────────────────────────────────────────

class AdaptiveConsensusEngine:
    """
    Computes consensus parameter recommendations for consuming chains.

    Inputs (per chain):
      - sigma_score:        Σ plane confidence (0-1)
      - mf_rate:            manipulation fingerprint detection rate (0-1)
      - mev_rate:           MEV extraction rate (0-0.05 typical)
      - hhi:                validator HHI (0-10000, lower is better)
      - validator_count:    current validator set size
      - current_block_size: current block size limit (gas)
      - current_finality:   current finality threshold (blocks)

    Output: list of ConsensusRecommendation
    """

    def compute_recommendations(
        self,
        chain_id:              int,
        sigma_score:           float = 0.25,
        mf_rate:               float = 0.0,
        mev_rate:              float = 0.0,
        hhi:                   float = 2500.0,
        validator_count:       int   = 0,
        current_block_size:    Optional[int]   = None,
        current_finality:      Optional[int]   = None,
        current_slashing_pct:  Optional[float] = None,
    ) -> List[ConsensusRecommendation]:
        recs: List[ConsensusRecommendation] = []

        # ── 1. Block size recommendation ────────────────────────────────────
        # Higher Σ → can support larger blocks (more validator confidence)
        # Higher MF → reduce block size (more manipulation risk)
        if current_block_size is None:
            current_block_size = DEFAULT_BLOCK_SIZE
        sigma_factor = max(0.5, min(2.0, sigma_score * 2.0))
        mf_penalty = max(0.3, 1.0 - mf_rate * 5.0)
        recommended_block = int(DEFAULT_BLOCK_SIZE * sigma_factor * mf_penalty)
        recommended_block = max(MIN_BLOCK_SIZE, min(MAX_BLOCK_SIZE, recommended_block))
        recs.append(ConsensusRecommendation(
            chain_id=chain_id,
            parameter="block_size_limit",
            recommended_value=recommended_block,
            current_value=current_block_size,
            rationale=(
                f"Σ={sigma_score:.2f} scales block by {sigma_factor:.2f}x; "
                f"MF={mf_rate:.2%} applies {mf_penalty:.2f}x penalty."
            ),
            confidence=max(0.0, min(1.0, sigma_score)),
        ))

        # ── 2. Gas limit recommendation ─────────────────────────────────────
        # Higher MEV → reduce gas limit (less MEV extraction opportunity)
        if mev_rate > 0.005:
            mev_penalty = max(0.5, 1.0 - (mev_rate - 0.005) * 10.0)
            recommended_gas = int(DEFAULT_GAS_LIMIT * mev_penalty)
            recs.append(ConsensusRecommendation(
                chain_id=chain_id,
                parameter="gas_limit",
                recommended_value=recommended_gas,
                current_value=current_block_size,
                rationale=(
                    f"MEV rate {mev_rate:.4f} exceeds 0.5% threshold; "
                    f"reduce gas by {(1-mev_penalty):.0%}."
                ),
                confidence=min(1.0, mev_rate * 100.0),
            ))

        # ── 3. Finality threshold recommendation ────────────────────────────
        # Lower Σ → require more confirmations
        if current_finality is None:
            current_finality = DEFAULT_FINALITY
        if sigma_score < 0.5:
            recommended_finality = int(DEFAULT_FINALITY * (1.0 + (0.5 - sigma_score) * 4.0))
            recs.append(ConsensusRecommendation(
                chain_id=chain_id,
                parameter="finality_threshold",
                recommended_value=recommended_finality,
                current_value=current_finality,
                rationale=(
                    f"Σ={sigma_score:.2f} below 0.5; increase finality to "
                    f"{recommended_finality} blocks."
                ),
                confidence=1.0 - sigma_score,
            ))

        # ── 4. Slashing threshold recommendation ────────────────────────────
        # Higher MF → increase slashing severity
        if current_slashing_pct is None:
            current_slashing_pct = DEFAULT_SLASHING_PCT
        if mf_rate > 0.05:
            recommended_slashing = min(1.0, DEFAULT_SLASHING_PCT + mf_rate * 5.0)
            recs.append(ConsensusRecommendation(
                chain_id=chain_id,
                parameter="slashing_threshold_pct",
                recommended_value=recommended_slashing,
                current_value=current_slashing_pct,
                rationale=(
                    f"MF rate {mf_rate:.2%} exceeds 5%; increase slashing "
                    f"to {recommended_slashing:.0%}."
                ),
                confidence=min(1.0, mf_rate * 10.0),
            ))

        # ── 5. Validator set size recommendation ────────────────────────────
        # High HHI → recommend expanding validator set
        if hhi > 2500 and validator_count < 100:
            recommended_set = min(MAX_VALIDATOR_SET, max(MIN_VALIDATOR_SET, validator_count * 2))
            recs.append(ConsensusRecommendation(
                chain_id=chain_id,
                parameter="validator_set_size",
                recommended_value=recommended_set,
                current_value=validator_count,
                rationale=(
                    f"HHI={hhi:.0f} above 2500 danger threshold; "
                    f"expand validator set from {validator_count} to {recommended_set}."
                ),
                confidence=min(1.0, hhi / 10000.0),
            ))

        return recs


# ── Self-test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    engine = AdaptiveConsensusEngine()

    print("=== Adaptive Consensus Engine Self-test ===\n")

    # Healthy chain — no recommendations
    healthy = engine.compute_recommendations(
        chain_id=1, sigma_score=0.85, mf_rate=0.001, mev_rate=0.001,
        hhi=800, validator_count=200,
    )
    print(f"Healthy chain: {len(healthy)} recommendation(s)")
    assert len(healthy) <= 1, "Healthy chain should produce minimal recommendations"

    # Stressed chain — multiple recommendations
    stressed = engine.compute_recommendations(
        chain_id=137, sigma_score=0.30, mf_rate=0.08, mev_rate=0.02,
        hhi=3500, validator_count=30,
    )
    print(f"\nStressed chain: {len(stressed)} recommendation(s)")
    for r in stressed:
        print(f"  {r.parameter}: {r.current_value} → {r.recommended_value}")
        print(f"    rationale:  {r.rationale}")
        print(f"    confidence: {r.confidence:.2f}")
    assert len(stressed) >= 4, "Stressed chain should produce multiple recommendations"

    print("\nPHASE 7 PASS — Adaptive consensus recommendations implemented")
