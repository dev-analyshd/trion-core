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


# ─── Wash Trading Defense (MD L1.1/L1.2, Wave 3 D — R-EC-03) ──────────────────
#
# MD "Wash Trading Defense" (verbatim):
#     D_effective = D × (1 - HHI(counterparty_distribution))
#
# Washed volume inflates apparent depth; the HHI of the counterparty
# distribution measures how concentrated the "activity" is (a wash ring
# cycling through the same few counterparties ⇒ HHI → 1 ⇒ D_effective → 0).
# The discount is multiplicative and monotone: more concentrated ⇒ less
# effective depth, exactly as specified.

def compute_counterparty_hhi(counterparty_distribution) -> float:
    """HHI over a {counterparty_id: volume/weight} distribution, ∈ [0, 1].

    Normalized HHI = Σ (share_i)² over total — the same construction as
    core/spiritual/sigma_engine.compute_hhi, expressed on the 0-1 scale
    (1.0 = a single counterparty took all volume; ~0 = perfectly spread).
    An empty distribution returns 0.0 (no observed counterparties — no
    concentration evidence, depth passes through undiscounted; honest
    data-pending, never a fabricated penalty).
    """
    if not counterparty_distribution:
        return 0.0
    vals = [float(v) for v in counterparty_distribution.values()
            if v is not None and v > 0]
    total = sum(vals)
    if total <= 0:
        return 0.0
    return sum((v / total) ** 2 for v in vals)


def wash_trading_depth_discount(
    D: float,
    counterparty_distribution,
) -> float:
    """MD L1.1 Wash Trading Defense: D_effective = D·(1 − HHI(cp_dist)).

    Args:
        D: raw Akashic depth accumulated for the entity/asset.
        counterparty_distribution: {counterparty_id: volume-or-weight}
            mapping of the entity's observed counterparties. ``None``/empty
            → HHI 0 → no discount (unmeasured, not penalized).

    Returns:
        D_effective ∈ [0, D] — the wash-adjusted depth.
    """
    if D <= 0:
        return 0.0
    hhi = compute_counterparty_hhi(counterparty_distribution)
    return max(0.0, D * (1.0 - min(1.0, hhi)))


def effective_depth(
    D: float,
    counterparty_distribution=None,
) -> dict:
    """Depth-engine entry: raw depth + wash-trading discount (R-EC-03).

    Returns {D, D_effective, counterparty_hhi, discount_applied} — the
    single place the depth engine applies the MD wash-trading defense so
    consumers (D(t) feeds, moat D factor, routing) read D_effective.
    """
    hhi = compute_counterparty_hhi(counterparty_distribution)
    d_eff = wash_trading_depth_discount(D, counterparty_distribution)
    return {
        "D":                 float(D),
        "D_effective":       d_eff,
        "counterparty_hhi":  round(hhi, 6),
        "discount_applied":  bool(counterparty_distribution) and hhi > 0.0,
        "formula":           "D_effective = D × (1 − HHI(counterparty_distribution)) [MD L1.1]",
    }


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

    # Wash Trading Defense (MD L1.1, R-EC-03): D_eff = D × (1 − HHI(cp))
    cp_wash_ring = {"ring_a": 90.0, "ring_b": 10.0}     # HHI = 0.82
    cp_healthy   = {f"cp_{i}": 1.0 for i in range(10)}  # HHI = 0.10
    eff = effective_depth(D, cp_wash_ring)
    hhi = compute_counterparty_hhi(cp_wash_ring)
    assert abs(eff["D_effective"] - D * (1 - hhi)) < 1e-9
    assert eff["D_effective"] < effective_depth(D, cp_healthy)["D_effective"]
    assert effective_depth(D, None)["D_effective"] == D   # unmeasured → no penalty
    print(f"Wash defense: D={D:.1f} → D_eff={eff['D_effective']:.1f} "
          f"(ring HHI={hhi:.2f})")
    print("PHASE 9 PASS — Akashic Depth D(t) integral form implemented")
