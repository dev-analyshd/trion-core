"""
TRION Protocol — L9.1: Cross-Species Liquidity (XSL)
Chapter 13: Biological-Digital Integration

XSL(entity, t) = TV(t) · FS(t) · RR(t) / (1 + TP(t))

Components:
  TV = Trade Volume continuity across behavioral species/chain families
       TV = 1 - |volume_change_vs_30d_avg| / max_observed_change
  FS = Functional Similarity score — how similar the entity's behavioral
       function is across different chain contexts
       FS = cos_sim(behavioral_vector_chain_A, behavioral_vector_chain_B)
  RR = Reciprocal Recognition Rate — fraction of cross-chain transactions
       that are mutually recognized (not just one-sided)
  TP = Trade Protocol Friction — normalized measure of cross-chain friction
       (high TP = poor interoperability, reduces XSL)

XSL ∈ [0, 1]
  ≥ 0.70  KEYSTONE_LIQUIDITY — entity is a cross-species connector
  0.40–0.70  BRIDGE_LIQUIDITY — partial cross-species function
  < 0.40  SPECIES_ISOLATED — entity confined to single behavioral niche

Biological analogy (whitepaper L9.1):
  In ecological systems, keystone species provide liquidity that benefits
  many other species. XSL measures the DeFi equivalent: entities that
  provide liquidity across protocol and chain "species" boundaries.

F6 Falsifiability: XSL decline detection must trigger 72h behavioral shift window.

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

XSL_KEYSTONE = 0.70
XSL_BRIDGE   = 0.40


@dataclass
class CrossChainBehavior:
    """Behavioral snapshot for one chain context."""
    chain_id:         str
    behavioral_vector: List[float]
    volume_30d:       float
    tx_count:         int
    unique_counterparties: int
    inbound_recognition: float
    outbound_recognition: float


def compute_tv(
    current_volume:      float,
    avg_volume_30d:      float,
    max_observed_change: float = 1.0,
) -> float:
    """
    TV = Trade Volume continuity.
    TV = 1 - |current - avg| / max_observed_change
    """
    if avg_volume_30d <= 0:
        return 0.50
    change = abs(current_volume - avg_volume_30d)
    norm_change = change / max(max_observed_change, avg_volume_30d)
    return max(0.0, min(1.0, 1.0 - norm_change))


def compute_fs(
    vec_a: List[float],
    vec_b: List[float],
) -> float:
    """
    FS = cosine_similarity(behavioral_vector_A, behavioral_vector_B).
    Measures functional similarity of entity across chain contexts.
    """
    if not vec_a or not vec_b:
        return 0.50
    n = min(len(vec_a), len(vec_b))
    a, b = vec_a[:n], vec_b[:n]
    dot   = sum(ai * bi for ai, bi in zip(a, b))
    na    = math.sqrt(sum(ai ** 2 for ai in a))
    nb    = math.sqrt(sum(bi ** 2 for bi in b))
    if na == 0 or nb == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))


def compute_rr(
    inbound_recognition_rate:  float,
    outbound_recognition_rate: float,
) -> float:
    """
    RR = Reciprocal Recognition Rate.
    RR = geometric mean of inbound and outbound recognition
    High RR: cross-chain transactions are mutually acknowledged.
    Low RR: one-sided flows that don't propagate behavioral context.
    """
    if inbound_recognition_rate <= 0 or outbound_recognition_rate <= 0:
        return 0.0
    return math.sqrt(inbound_recognition_rate * outbound_recognition_rate)


def compute_tp(
    bridge_latency_blocks: float,
    slippage_pct:          float,
    failure_rate:          float,
    max_latency_ref:       float = 100.0,
) -> float:
    """
    TP = Trade Protocol Friction ∈ [0, 1].
    Combines latency, slippage, and failure rate.
    Low TP = smooth cross-chain (good for XSL).
    High TP = heavy friction (suppresses XSL).
    """
    latency_norm  = min(1.0, bridge_latency_blocks / max_latency_ref)
    friction      = (latency_norm * 0.40 + slippage_pct * 0.40 + failure_rate * 0.20)
    return max(0.0, min(1.0, friction))


def compute_xsl(
    tv: float,
    fs: float,
    rr: float,
    tp: float,
) -> float:
    """
    XSL(entity, t) = TV · FS · RR / (1 + TP)
    """
    if tp < 0:
        tp = 0.0
    numerator   = tv * fs * rr
    denominator = 1.0 + tp
    return max(0.0, min(1.0, numerator / denominator))


def compute_xsl_full(
    entity_id:              str,
    chain_behaviors:        List[CrossChainBehavior],
    bridge_latency_blocks:  float = 10.0,
    slippage_pct:           float = 0.005,
    failure_rate:           float = 0.02,
) -> dict:
    """
    Full XSL computation from cross-chain behavioral snapshots.
    """
    if len(chain_behaviors) < 2:
        return {
            "entity_id":   entity_id,
            "xsl_score":   0.0,
            "tier":        "SPECIES_ISOLATED",
            "error":       "insufficient_cross_chain_data",
            "chain_count": len(chain_behaviors),
        }

    total_vol    = sum(cb.volume_30d for cb in chain_behaviors)
    avg_vol      = total_vol / len(chain_behaviors)
    max_vol      = max(cb.volume_30d for cb in chain_behaviors)

    tv = compute_tv(total_vol, avg_vol * len(chain_behaviors), max_vol)

    fs_scores = []
    for i in range(len(chain_behaviors)):
        for j in range(i + 1, len(chain_behaviors)):
            fs_ij = compute_fs(
                chain_behaviors[i].behavioral_vector,
                chain_behaviors[j].behavioral_vector,
            )
            fs_scores.append(fs_ij)
    fs = sum(fs_scores) / len(fs_scores) if fs_scores else 0.50

    avg_inbound  = sum(cb.inbound_recognition for cb in chain_behaviors) / len(chain_behaviors)
    avg_outbound = sum(cb.outbound_recognition for cb in chain_behaviors) / len(chain_behaviors)
    rr = compute_rr(avg_inbound, avg_outbound)

    tp = compute_tp(bridge_latency_blocks, slippage_pct, failure_rate)

    xsl = compute_xsl(tv, fs, rr, tp)

    tier = (
        "KEYSTONE_LIQUIDITY" if xsl >= XSL_KEYSTONE else
        "BRIDGE_LIQUIDITY"   if xsl >= XSL_BRIDGE   else
        "SPECIES_ISOLATED"
    )

    is_keystone = xsl >= XSL_KEYSTONE

    return {
        "entity_id":      entity_id,
        "xsl_score":      round(xsl, 6),
        "tier":           tier,
        "is_keystone":    is_keystone,
        "components": {
            "TV_volume_continuity":     round(tv, 4),
            "FS_functional_similarity": round(fs, 4),
            "RR_reciprocal_recognition": round(rr, 4),
            "TP_protocol_friction":     round(tp, 4),
        },
        "chain_count":    len(chain_behaviors),
        "chain_ids":      [cb.chain_id for cb in chain_behaviors],
        "total_volume":   round(total_vol, 2),
        "f6_monitoring":  True,
        "f6_note":        "XSL decline below BRIDGE threshold triggers 72h behavioral shift window (F6).",
        "disclosure": (
            f"XSL={xsl:.4f} [{tier}]. "
            f"{'Keystone species: cross-chain liquidity connector.' if is_keystone else 'Not keystone.'} "
            "Cross-species liquidity is a biological analogy — not a financial guarantee."
        ),
    }


if __name__ == "__main__":
    import random
    rng = random.Random(42)

    chains = [
        CrossChainBehavior(
            chain_id="ethereum",
            behavioral_vector=[rng.gauss(0.7, 0.1) for _ in range(9)],
            volume_30d=1_000_000,
            tx_count=500,
            unique_counterparties=120,
            inbound_recognition=0.85,
            outbound_recognition=0.82,
        ),
        CrossChainBehavior(
            chain_id="arbitrum",
            behavioral_vector=[rng.gauss(0.68, 0.1) for _ in range(9)],
            volume_30d=800_000,
            tx_count=400,
            unique_counterparties=95,
            inbound_recognition=0.80,
            outbound_recognition=0.78,
        ),
        CrossChainBehavior(
            chain_id="base",
            behavioral_vector=[rng.gauss(0.72, 0.1) for _ in range(9)],
            volume_30d=600_000,
            tx_count=300,
            unique_counterparties=80,
            inbound_recognition=0.75,
            outbound_recognition=0.77,
        ),
    ]

    result = compute_xsl_full("0xUNISWAP_POOL", chains, bridge_latency_blocks=5, slippage_pct=0.003)
    print(f"XSL = {result['xsl_score']:.4f} [{result['tier']}]")
    for k, v in result['components'].items():
        print(f"  {k}: {v:.4f}")
    assert 0 <= result['xsl_score'] <= 1
    print("L9.1 XSL Engine: PASS")
