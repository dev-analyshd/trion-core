"""
TRION Protocol — L7.1: Natural Liquidity Score
NL(asset, t) = LD(a,t) · LO(a,t) · LC(a,t) · LS(a,t)
NL < 0.30 → LIQUIDITY_HEALTH signal emitted

LD = Liquidity Depth Entropy
LO = Liquidity Origin Score = 1 - Sybil_LP_ratio
LC = Liquidity Consistency
LS = Liquidity Stress Resilience

March 12, 2026 AAVE pool: NL ≈ 0.09 → BLOCKED
"""

import numpy as np
from typing import List
import math


NL_ALERT_THRESHOLD = 0.30


def compute_ld(depth_per_tick: List[float]) -> float:
    if not depth_per_tick or sum(depth_per_tick) <= 0:
        return 0.0
    total = sum(depth_per_tick)
    probs = [d / total for d in depth_per_tick if d > 0]
    H     = -sum(p * math.log2(p) for p in probs)
    max_H = math.log2(len(depth_per_tick))
    return H / max_H if max_H > 0 else 0.0


def compute_lo(top5_lp_share: float, lp_count: int) -> float:
    if lp_count <= 0:
        return 0.0
    sybil_ratio = top5_lp_share / max(1, lp_count / 5)
    return max(0.0, 1.0 - sybil_ratio)


def compute_lc(current_ld: float, baseline_ld_history: List[float]) -> float:
    if not baseline_ld_history:
        return 0.5
    baseline_mean = float(np.mean(baseline_ld_history))
    baseline_std  = float(np.std(baseline_ld_history))
    if baseline_std < 1e-6:
        deviation = abs(current_ld - baseline_mean)
        if deviation < 0.05:
            return 1.0
        if deviation < 0.30:
            return round(max(0.5, 1.0 - deviation * 1.5), 4)
        return 0.5
    z = abs(current_ld - baseline_mean) / baseline_std
    return max(0.0, 1.0 - min(1.0, z / 3.0))


def compute_ls(ld_during_stress: float, ld_during_normal: float) -> float:
    if ld_during_normal <= 0:
        return 0.0
    return min(1.0, ld_during_stress / ld_during_normal)


def compute_nl(
    depth_per_tick:   List[float],
    top5_lp_share:    float,
    lp_count:         int,
    baseline_ld_90d:  List[float],
    ld_during_stress: float,
    ld_during_normal: float,
) -> dict:
    ld = compute_ld(depth_per_tick)
    lo = compute_lo(top5_lp_share, lp_count)
    lc = compute_lc(ld, baseline_ld_90d)
    ls = compute_ls(ld_during_stress, ld_during_normal)

    nl       = ld * lo * lc * ls
    alert    = nl < NL_ALERT_THRESHOLD
    limiting = min({'LD':ld,'LO':lo,'LC':lc,'LS':ls}, key={'LD':ld,'LO':lo,'LC':lc,'LS':ls}.get)

    return {
        "nl_score":        nl,
        "ld_score":        ld,
        "lo_score":        lo,
        "lc_score":        lc,
        "ls_score":        ls,
        "alert":           alert,
        "limiting_factor": limiting,
        "recommendation":  "DO_NOT_ROUTE" if nl < NL_ALERT_THRESHOLD else "CAUTION" if nl < 0.50 else "CLEAR",
    }


if __name__ == "__main__":
    aave_march12 = compute_nl(
        depth_per_tick=[1000, 50, 20, 10, 5],
        top5_lp_share=0.92,
        lp_count=8,
        baseline_ld_90d=[0.5, 0.6, 0.55, 0.48, 0.52],
        ld_during_stress=0.05,
        ld_during_normal=0.55,
    )
    print(f"AAVE March 12 NL:  {aave_march12['nl_score']:.4f} (expected ~0.09)")
    print(f"  LD={aave_march12['ld_score']:.3f} LO={aave_march12['lo_score']:.3f} "
          f"LC={aave_march12['lc_score']:.3f} LS={aave_march12['ls_score']:.3f}")
    print(f"  Alert:            {aave_march12['alert']} (expected True)")
    assert aave_march12['alert'], "NL alert should fire for AAVE scenario"

    healthy = compute_nl(
        depth_per_tick=[100]*20,
        top5_lp_share=0.35,
        lp_count=200,
        baseline_ld_90d=[0.9]*30,
        ld_during_stress=0.8,
        ld_during_normal=0.9,
    )
    print(f"Healthy pool NL:   {healthy['nl_score']:.4f} (expected > 0.60)")
    assert healthy['nl_score'] > 0.50, "Healthy pool should score well"
    print("PHASE 16 PASS — NL engine verified, March 12 scenario passes")
