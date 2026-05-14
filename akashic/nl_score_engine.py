"""
nl_score_engine.py — Network Liquidity Score Engine
Computes NL(asset, t) = LC(t) × LS(t) × volatility_damper(t)
Spec: BTCP Master Implementation Spec §7.1, completes stubs in anima_liquidity.py
"""

import math
import numpy as np
from typing import Optional

# ─── NL Score configuration ───────────────────────────────────────────────────
NL_FLOOR          = 0.0
NL_CEILING        = 1.0
VOLATILITY_WINDOW = 14   # days for volatility computation
MIN_DEPTH_USD     = 1_000  # minimum liquidity depth (USD) for NL > 0

# ─── LC(t): Liquidity Concentration ──────────────────────────────────────────
# LC(t) = Σ w_j × (depth_j / Σ depth_k) — weighted by pool diversity
# w_j = 1 - corr(pool_j, pool_mean) — same diversity principle as BTCP consensus
def compute_lc(
    pool_depths:   list[float],     # USD depth per pool/DEX
    pool_corrs:    list[float],     # correlation of each pool with market mean
) -> float:
    """
    LC(t): Liquidity Concentration score.
    High LC = liquidity spread across many diverse sources.
    Low LC = concentrated in single pool → fragile.
    """
    if not pool_depths or sum(pool_depths) == 0:
        return 0.0

    total_depth = sum(pool_depths)
    if total_depth < MIN_DEPTH_USD:
        return 0.0

    # Diversity weights: d_j = 1 - |corr_j|
    if pool_corrs and len(pool_corrs) == len(pool_depths):
        weights = [max(0.0, 1.0 - abs(c)) for c in pool_corrs]
    else:
        weights = [1.0] * len(pool_depths)  # equal weights if no correlation data

    total_weight = sum(weights)
    if total_weight == 0:
        return 0.0

    lc = sum(
        (w / total_weight) * (d / total_depth)
        for w, d in zip(weights, pool_depths)
    )

    # LC is bounded [0, 1] naturally since it's a weighted sum of fractions
    return max(NL_FLOOR, min(NL_CEILING, lc))


# ─── LS(t): Liquidity Stability ───────────────────────────────────────────────
# LS(t) = 1 - normalized_std_dev(depth_history)
# Measures how stable pool depths are over time.
def compute_ls(
    depth_history:  list[float],  # historical depth values (most recent last)
    window:         int = 14,
) -> float:
    """
    LS(t): Liquidity Stability score.
    High LS = stable depth → predictable routing environment.
    Low LS = volatile depth → increased routing risk.
    """
    if len(depth_history) < 2:
        return 0.5  # insufficient data — conservative default

    recent = depth_history[-window:]
    mean   = sum(recent) / len(recent)
    if mean == 0:
        return 0.0

    std = math.sqrt(sum((x - mean) ** 2 for x in recent) / len(recent))
    cv  = std / mean  # coefficient of variation

    # LS = 1 - tanh(2 × CV) — tanh normalizes to [0,1), penalizes high volatility
    ls = 1.0 - math.tanh(2.0 * cv)
    return max(NL_FLOOR, min(NL_CEILING, ls))


# ─── Volatility damper ────────────────────────────────────────────────────────
# vol_damper(t) = 1 - α × realized_vol(t)
# α calibrated so 50% vol → 25% damping
def compute_volatility_damper(
    price_history:  list[float],    # price observations (most recent last)
    alpha:          float = 0.5,
    window:         int   = VOLATILITY_WINDOW,
) -> float:
    if len(price_history) < 2:
        return 1.0

    recent = price_history[-window:]
    if len(recent) < 2:
        return 1.0

    log_returns = [
        math.log(recent[i] / recent[i - 1])
        for i in range(1, len(recent))
        if recent[i - 1] > 0 and recent[i] > 0
    ]

    if not log_returns:
        return 1.0

    realized_vol = math.sqrt(sum(r ** 2 for r in log_returns) / len(log_returns)) * math.sqrt(365)
    damper = 1.0 - alpha * min(realized_vol, 1.0)
    return max(0.0, min(1.0, damper))


# ─── Full NL score ────────────────────────────────────────────────────────────
def compute_nl_score(
    pool_depths:    list[float],
    pool_corrs:     list[float],
    depth_history:  list[float],
    price_history:  list[float],
    alpha:          float = 0.5,
) -> dict:
    """
    NL(asset, t) = LC(t) × LS(t) × vol_damper(t)

    Returns dict with nl_score and component breakdowns.
    """
    lc      = compute_lc(pool_depths, pool_corrs)
    ls      = compute_ls(depth_history)
    damper  = compute_volatility_damper(price_history, alpha)

    nl      = lc * ls * damper

    return {
        "nl_score":          round(nl, 6),
        "lc":                round(lc, 6),
        "ls":                round(ls, 6),
        "volatility_damper": round(damper, 6),
        "above_floor":       nl > 0.30,       # BTCP routing threshold
        "sufficient_depth":  sum(pool_depths) >= MIN_DEPTH_USD,
    }


# ─── Observer effect correction ──────────────────────────────────────────────
# Gap G: NL_adj(t) = NL_base(t) × (1 - OE_factor)
def apply_oe_correction(nl_score: float, oe_factor: float) -> float:
    """Apply Observer Effect correction to prevent circular reinforcement."""
    return max(0.0, nl_score * (1.0 - oe_factor))


# ─── Standalone CLI for testing ───────────────────────────────────────────────
if __name__ == "__main__":
    import json

    # Test: ETH-USDC on Arbitrum (simulated data)
    result = compute_nl_score(
        pool_depths   = [15_000_000, 8_000_000, 3_000_000, 1_200_000],
        pool_corrs    = [0.2, 0.4, 0.1, 0.6],
        depth_history = [14_500_000, 15_200_000, 14_800_000, 15_000_000, 15_100_000],
        price_history = [3400.0, 3420.0, 3380.0, 3410.0, 3405.0],
    )
    print(f"NL score: {json.dumps(result, indent=2)}")
