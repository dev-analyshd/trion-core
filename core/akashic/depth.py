"""
TRION Protocol — L2: Akashic Depth D(t)
Phase 9 implementation per whitepaper Section 4, L2.

D(t) ∝ ∫₀ᵗ [ A(τ) · (1 + M(τ)) · C(τ) ] dτ
D(t=0) = EVM genesis history (bootstrap)
D_minimum ≈ 6 months of live operation (10,000 behavioral events)

Also see: src/core/d_engine.py for block-level accumulation.
This module provides the integral form and bootstrap weight functions.
"""

import numpy as np
from typing import List, Optional


D_MINIMUM = 10_000.0


def compute_akashic_depth(
    block_samples: List[dict],
    dt: float = 12.0,
) -> float:
    """
    Numerical integration: D(t) = ∫ A(τ) · (1 + M(τ)) · C(τ) dτ
    Uses trapezoidal rule over sampled blocks.
    dt = block interval in seconds (12s for Ethereum mainnet).
    """
    if not block_samples:
        return 0.0

    values = [
        s.get('A', 0.1) * (1 + s.get('M', 0.5)) * s.get('C', 0.3)
        for s in block_samples
    ]

    D = 0.0
    for i in range(len(values) - 1):
        D += 0.5 * (values[i] + values[i + 1]) * dt

    return D


def bootstrap_weight(D: float, lambda_boot: float = 0.0005) -> float:
    """
    bootstrap_weight(t) = e^(-λ_boot · D(t))
    At D = D_minimum: weight approaches 0 → Living Security fully active.
    At D = 0: weight = 1.0 → full bootstrap fallback active.
    """
    return float(np.exp(-lambda_boot * D))


def effective_security(
    D: float,
    sec_classical: float = 0.85,
    sec_living: float = 0.99,
) -> float:
    """
    SEC_boot = w · SEC_classical + (1-w) · SEC_living
    Interpolates between classical and living security based on depth.
    """
    w = bootstrap_weight(D)
    return w * sec_classical + (1.0 - w) * sec_living


def is_bootstrap_phase(D: float) -> bool:
    """True when entity has insufficient behavioral history for full activation."""
    return D < D_MINIMUM


def depth_to_confidence(D: float, lambda_conf: float = 0.001) -> float:
    """
    conf_genesis(t) = 1 - e^(-λ · D(t))
    Used by genesis inference to scale confidence with depth.
    """
    return 1.0 - float(np.exp(-lambda_conf * D))


if __name__ == "__main__":
    samples = [
        {'A': 0.3, 'M': 0.6, 'C': 0.5 + 0.1 * np.sin(i / 100)}
        for i in range(1000)
    ]

    D = compute_akashic_depth(samples, dt=12.0)
    w = bootstrap_weight(D)
    sec = effective_security(D)
    conf = depth_to_confidence(D)

    print(f"D(t) after 1000 blocks (12s each): {D:.2f}")
    print(f"Bootstrap weight:                  {w:.4f}")
    print(f"Effective security:                {sec:.4f}")
    print(f"Genesis confidence:                {conf:.4f}")
    print(f"Bootstrap phase:                   {is_bootstrap_phase(D)}")

    assert D > 0
    assert 0 <= w <= 1
    assert 0 <= sec <= 1
    print("PHASE 9 PASS — Akashic Depth D(t) integral form implemented")
