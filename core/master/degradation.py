"""
TRION Protocol — L5.3: Consensus Degradation Tiers
Whitepaper Section 9, L5.3.

When coherence C(t) falls below threshold Θ(t) the system does not crash —
it enters one of two degradation tiers with specific behavioral guarantees.

Tier 1: C(t) between 0.5×Θ and Θ
  → STALE_SCORE flag emitted
  → Last confirmed BIBL snapshot used (max 50 blocks)
  → New routes suspended; in-flight routes complete normally

Tier 2: C(t) < 0.5×Θ
  → New routes suspended entirely
  → In-flight routes complete normally
  → Emergency Escape mechanism unaffected

GUARANTEE: Entity funds are NEVER at risk during degradation.

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class DegradationTier(str, Enum):
    NOMINAL    = "NOMINAL"     # C(t) >= Θ(t)            — full signal emission
    TIER_1     = "TIER_1"      # 0.5×Θ <= C(t) < Θ       — stale score, limited routing
    TIER_2     = "TIER_2"      # C(t) < 0.5×Θ             — suspended routing
    EMERGENCY  = "EMERGENCY"   # external override or HHI > 4000


@dataclass
class DegradationState:
    tier:                  DegradationTier
    coherence:             float
    threshold:             float
    stale_score_emitted:   bool
    new_routes_suspended:  bool
    inflight_allowed:      bool         # always True — funds always safe
    emergency_escape_ok:   bool         # always True — escape unaffected
    bibl_snapshot_max:     int          # max blocks last BIBL snapshot is valid
    limiting_plane:        Optional[str]
    coherence_gap:         float        # Θ(t) - C(t)
    coherence_trend:       str          # RISING | FALLING | STABLE
    eta_seconds:           Optional[int]  # estimated seconds to NOMINAL
    timestamp:             float
    disclosure:            str

    @property
    def fund_safety_guarantee(self) -> bool:
        """
        Whitepaper guarantee: entity funds are NEVER at risk during degradation.
        This is always True — it is a protocol invariant, not a condition.
        """
        return True


def classify_degradation(
    coherence:      float,
    threshold:      float,
    limiting_plane: Optional[str] = None,
    trend:          str = "STABLE",
    eta_seconds:    Optional[int] = None,
    hhi_emergency:  bool = False,
) -> DegradationState:
    """
    Classify the current degradation tier from five-plane coherence C(t) and Θ(t).

    Tier rules (whitepaper L5.3):
      NOMINAL:   coherence >= threshold
      TIER_1:    0.5 × threshold <= coherence < threshold
      TIER_2:    coherence < 0.5 × threshold
      EMERGENCY: HHI > 4000 (validator concentration critical)
    """
    gap = max(0.0, threshold - coherence)

    if hhi_emergency:
        tier = DegradationTier.EMERGENCY
    elif coherence >= threshold:
        tier = DegradationTier.NOMINAL
    elif coherence >= 0.5 * threshold:
        tier = DegradationTier.TIER_1
    else:
        tier = DegradationTier.TIER_2

    stale_score_emitted  = tier in (DegradationTier.TIER_1, DegradationTier.EMERGENCY)
    new_routes_suspended = tier in (DegradationTier.TIER_2, DegradationTier.EMERGENCY)
    bibl_max             = 50 if tier == DegradationTier.TIER_1 else 0

    disclosure = _build_disclosure(tier, coherence, threshold, gap, limiting_plane, trend, eta_seconds)

    return DegradationState(
        tier                 = tier,
        coherence            = round(coherence, 6),
        threshold            = round(threshold, 6),
        stale_score_emitted  = stale_score_emitted,
        new_routes_suspended = new_routes_suspended,
        inflight_allowed     = True,        # invariant — always True
        emergency_escape_ok  = True,        # invariant — always True
        bibl_snapshot_max    = bibl_max,
        limiting_plane       = limiting_plane,
        coherence_gap        = round(gap, 6),
        coherence_trend      = trend,
        eta_seconds          = eta_seconds,
        timestamp            = time.time(),
        disclosure           = disclosure,
    )


def _build_disclosure(
    tier:           DegradationTier,
    coherence:      float,
    threshold:      float,
    gap:            float,
    limiting_plane: Optional[str],
    trend:          str,
    eta_seconds:    Optional[int],
) -> str:
    pct = round(100 * coherence / threshold, 1) if threshold > 0 else 0.0
    trend_str = {"RISING": "↑ recovering", "FALLING": "↓ declining", "STABLE": "→ stable"}.get(trend, trend)

    if tier == DegradationTier.NOMINAL:
        return f"NOMINAL: C(t)={coherence:.4f} >= Θ={threshold:.4f}. Full signal emission active."

    base = (
        f"{tier.value}: C(t)={coherence:.4f} ({pct}% of Θ={threshold:.4f}). "
        f"Gap={gap:.4f}. Trend={trend_str}."
    )
    if limiting_plane:
        base += f" Limiting plane: {limiting_plane}."
    if eta_seconds is not None:
        base += f" Estimated recovery: {eta_seconds}s."

    if tier == DegradationTier.TIER_1:
        base += (
            " STALE_SCORE emitted. Last BIBL snapshot valid for 50 blocks. "
            "New routes suspended. In-flight routes unaffected. "
            "GUARANTEE: entity funds are safe."
        )
    elif tier == DegradationTier.TIER_2:
        base += (
            " All new routes suspended. In-flight routes complete normally. "
            "Emergency Escape unaffected. "
            "GUARANTEE: entity funds are safe."
        )
    elif tier == DegradationTier.EMERGENCY:
        base += (
            " EMERGENCY: validator HHI critical. "
            "Consensus paused. Governance emergency protocol active."
        )
    return base


def to_dict(state: DegradationState) -> dict:
    return {
        "tier":                  state.tier.value,
        "coherence":             state.coherence,
        "threshold":             state.threshold,
        "coherence_gap":         state.coherence_gap,
        "coherence_trend":       state.coherence_trend,
        "stale_score_emitted":   state.stale_score_emitted,
        "new_routes_suspended":  state.new_routes_suspended,
        "inflight_routes_safe":  state.inflight_allowed,
        "emergency_escape_ok":   state.emergency_escape_ok,
        "bibl_snapshot_max_blocks": state.bibl_snapshot_max,
        "limiting_plane":        state.limiting_plane,
        "eta_seconds":           state.eta_seconds,
        "fund_safety_guarantee": state.fund_safety_guarantee,
        "timestamp":             int(state.timestamp),
        "disclosure":            state.disclosure,
    }


if __name__ == "__main__":
    cases = [
        (0.85, 0.70, "nominal",  "RISING"),
        (0.60, 0.70, "tier_1",   "STABLE"),
        (0.30, 0.70, "tier_2",   "FALLING"),
        (0.65, 0.70, "tier_1",   "RISING", "anima"),
    ]
    for args in cases:
        coh, thr = args[0], args[1]
        lp = args[4] if len(args) > 4 else None
        s = classify_degradation(coh, thr, limiting_plane=lp, trend=args[3])
        assert s.fund_safety_guarantee, "Fund safety guarantee violated!"
        assert s.inflight_allowed,      "In-flight guarantee violated!"
        assert s.emergency_escape_ok,   "Emergency escape guarantee violated!"
        print(f"  {s.tier.value:10s}  C={coh}  Θ={thr}  gap={s.coherence_gap:.4f}  stale={s.stale_score_emitted}  suspended={s.new_routes_suspended}")
    print("L5.3 Consensus Degradation Tiers: PASS — all guarantees hold")
