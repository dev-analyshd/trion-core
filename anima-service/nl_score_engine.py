"""
nl_score_engine.py — Natural Liquidity Score Engine (legacy entry point)

CANONICAL FORMULA (whitepaper L7.1):
    NL(asset, t) = LD(a,t) · LO(a,t) · LC(a,t) · LS(a,t)

    LD = Liquidity Depth Entropy      — Shannon entropy of depth across price ticks
    LO = Liquidity Origin Score       — 1 - Sybil_LP_ratio
    LC = Liquidity Consistency        — deviation of current LD from 90d baseline
    LS = Liquidity Stress Resilience  — LD(during_stress) / LD(normal_conditions)

    NL < 0.30 → LIQUIDITY_HEALTH signal emitted (see the simulated March 12, 2026
    AAVE scenario — a synthetic test vector, NOT a real historical event)

This module previously implemented a non-spec two-factor approximation
(LC × LS × volatility_damper) that omitted LD and LO entirely. It has been
corrected to delegate to the canonical, whitepaper-verified implementation in
src.planes.physical.nl_engine, which is the same engine the live FAISS
service (anima-service/faiss_service.py) uses. Kept as a thin compatibility layer
for any callers (e.g. akashic/liquidity_ocean.py) still importing this path.
"""

import math
import sys
import os
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.extended.natural_liquidity import (  # noqa: E402
    compute_nl,
    compute_ld,
    compute_lo,
    compute_lc as _spec_compute_lc,
    compute_ls as _spec_compute_ls,
    NL_ALERT_THRESHOLD,
)

NL_FLOOR   = 0.0
NL_CEILING = 1.0
MIN_DEPTH_USD = 1_000


def compute_lc(pool_depths: list, pool_corrs: Optional[list] = None) -> float:
    """
    Legacy-signature shim → spec-correct LD entropy used as the "current"
    depth-distribution signal, compared against itself as baseline when no
    historical series is supplied by the caller.
    Prefer src.planes.physical.nl_engine.compute_lc(current_ld, baseline_history)
    directly for spec-accurate results.
    """
    ld = compute_ld(pool_depths or [])
    return ld


def compute_ls(depth_history: list, window: int = 14) -> float:
    """
    Legacy-signature shim → approximates LS (stress resilience) using the
    ratio of the most recent depth reading to the historical mean.
    Prefer src.planes.physical.nl_engine.compute_ls(stress, normal) directly.
    """
    if len(depth_history) < 2:
        return 0.5
    recent = depth_history[-window:]
    mean = sum(recent) / len(recent)
    if mean <= 0:
        return 0.0
    return max(NL_FLOOR, min(NL_CEILING, recent[-1] / mean))


def compute_nl_score(
    pool_depths: list,
    pool_corrs: Optional[list] = None,
    depth_history: Optional[list] = None,
    price_history: Optional[list] = None,
    alpha: float = 0.5,
    top5_lp_share: Optional[float] = None,
    lp_count: Optional[int] = None,
) -> dict:
    """
    NL(asset, t) = LD(a,t) · LO(a,t) · LC(a,t) · LS(a,t)   [whitepaper L7.1]

    Backward-compatible wrapper: accepts the legacy call shape (pool depths +
    correlations + depth/price history) and maps it onto the four spec
    components. Sybil/LP-origin inputs are optional; when absent, LO defaults
    to a neutral 1.0 (unknown origin diversity, not penalized).
    """
    depth_per_tick = pool_depths or []

    # `depth_history` in the legacy call shape is a raw-dollar depth series,
    # not an LD-entropy series ([0,1]) as `nl_engine.compute_lc`/`compute_ls`
    # expect. Normalize by the series max so the values become a bounded
    # depth-ratio proxy for LD before handing them to the spec functions —
    # this preserves the *shape* of the legacy signal (stable vs volatile,
    # stressed vs normal) without collapsing healthy inputs toward zero.
    if depth_history and len(depth_history) > 1:
        hist_max = max(depth_history) or 1.0
        norm_history = [d / hist_max for d in depth_history]
        baseline_ld_90d  = norm_history[:-1]
        ld_during_normal = norm_history[-2]
        ld_during_stress = norm_history[-1]
    else:
        baseline_ld_90d  = []
        ld_during_normal = 1.0
        ld_during_stress = 1.0

    if top5_lp_share is not None and lp_count:
        result = compute_nl(
            depth_per_tick=depth_per_tick,
            top5_lp_share=top5_lp_share,
            lp_count=lp_count,
            baseline_ld_90d=baseline_ld_90d,
            ld_during_stress=ld_during_stress,
            ld_during_normal=ld_during_normal,
        )
    else:
        ld = compute_ld(depth_per_tick)
        lo = 1.0  # unknown LP origin distribution — neutral, not penalized
        lc = _spec_compute_lc(ld, baseline_ld_90d) if baseline_ld_90d else 1.0
        ls = _spec_compute_ls(ld_during_stress, ld_during_normal)
        nl = ld * lo * lc * ls
        result = {
            "nl_score": nl,
            "ld_score": ld,
            "lo_score": lo,
            "lc_score": lc,
            "ls_score": ls,
            "alert": nl < NL_ALERT_THRESHOLD,
            "recommendation": "DO_NOT_ROUTE" if nl < NL_ALERT_THRESHOLD else ("CAUTION" if nl < 0.50 else "CLEAR"),
        }

    return {
        "nl_score":          round(result["nl_score"], 6),
        "ld":                round(result["ld_score"], 6),
        "lo":                round(result["lo_score"], 6),
        "lc":                round(result["lc_score"], 6),
        "ls":                round(result["ls_score"], 6),
        "above_floor":       result["nl_score"] > NL_ALERT_THRESHOLD,
        "sufficient_depth":  sum(depth_per_tick) >= MIN_DEPTH_USD,
        "recommendation":    result.get("recommendation"),
    }


def apply_oe_correction(nl_score: float, oe_factor: float) -> float:
    """Apply Observer Effect correction to prevent circular reinforcement."""
    return max(0.0, nl_score * (1.0 - oe_factor))


if __name__ == "__main__":
    import json

    result = compute_nl_score(
        pool_depths   = [15_000_000, 8_000_000, 3_000_000, 1_200_000],
        pool_corrs    = [0.2, 0.4, 0.1, 0.6],
        depth_history = [14_500_000, 15_200_000, 14_800_000, 15_000_000, 15_100_000],
        price_history = [3400.0, 3420.0, 3380.0, 3410.0, 3405.0],
        top5_lp_share = 0.55,
        lp_count      = 40,
    )
    print(f"NL score: {json.dumps(result, indent=2)}")
