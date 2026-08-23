"""
TRION Protocol — L2.4 Resurrection Inference
Chapter 7.2: Dormancy Taxonomy and Resurrection

Five dormancy types with κ (decay coefficient) values:

ABANDONED       κ = 0.008   >365 days, team absent, no governance.
                             High probability of hostile takeover if resurrected.

HIBERNATION     κ = 0.003   30–365 days, team still signing.
                             Moderate resurrection probability.

MIGRATION       κ = 0.000   Activity stops on chain A, equivalent activity
                             starts on chain B. Not truly dormant.

REGULATORY_PAUSE κ = 0.001  Sudden cessation following known regulatory event.
                             External force, not internal failure.

EXPLOIT_RECOVERY κ = 0.005  Sharp cessation following exploit.
                             Probability depends on exploit severity + team response.

Δ_resurrection = w_d · e^(-κ·T) · w_c · sim(S_pre, S_react) · w_x · g(C)

T         = dormancy duration (days)
sim(·,·)  = behavioral similarity between pre-dormancy and reactive patterns
g(C)      = context quality function [0, 1]

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class DormancyType(Enum):
    ABANDONED         = "ABANDONED"
    HIBERNATION       = "HIBERNATION"
    MIGRATION         = "MIGRATION"
    REGULATORY_PAUSE  = "REGULATORY_PAUSE"
    EXPLOIT_RECOVERY  = "EXPLOIT_RECOVERY"


# κ values per dormancy type (decay coefficient)
KAPPA: dict[DormancyType, float] = {
    DormancyType.ABANDONED:         0.008,
    DormancyType.HIBERNATION:       0.003,
    DormancyType.MIGRATION:         0.000,  # Not truly dormant — κ=0
    DormancyType.REGULATORY_PAUSE:  0.001,
    DormancyType.EXPLOIT_RECOVERY:  0.005,
}

# Component weights for Δ_resurrection
W_DECAY       = 0.40   # w_d — dormancy decay component
W_CONTINUITY  = 0.35   # w_c — behavioral continuity component
W_CONTEXT     = 0.25   # w_x — external context component


@dataclass
class DormancyProfile:
    """Complete dormancy characterization for an asset."""
    entity_id:          str
    dormancy_type:      DormancyType
    dormancy_days:      float       # T — total days dormant
    team_activity:      bool        # Team signing activity during dormancy
    governance_active:  bool
    exploit_severity:   float       # [0, 1] — 0 = none, 1 = total loss
    team_response_quality: float    # [0, 1] for EXPLOIT_RECOVERY
    known_regulatory:   bool        # True if regulatory event preceded cessation
    chain_b_activity:   float       # [0, 1] activity on alternative chain


@dataclass
class ResurrectionScore:
    """Output of resurrection inference."""
    entity_id:                str
    dormancy_type:            DormancyType
    kappa:                    float
    delta_resurrection:       float   # [0, 1] overall resurrection health score
    decay_component:          float   # e^(-κ·T)
    continuity_component:     float   # sim(S_pre, S_react)
    context_component:        float   # g(C)
    hostile_takeover_risk:    float   # [0, 1] — ABANDONED type especially
    dormancy_days:            float
    signal_type:              str     # "RESURRECTION" or "MIGRATION"
    warning:                  Optional[str]


def classify_dormancy(profile: DormancyProfile) -> DormancyType:
    """
    Classify dormancy type from behavioral evidence.
    Classification order matters — check MIGRATION first (κ=0 means no decay).
    """
    if profile.chain_b_activity > 0.60:
        return DormancyType.MIGRATION

    if profile.known_regulatory and profile.dormancy_days < 365:
        return DormancyType.REGULATORY_PAUSE

    if profile.exploit_severity > 0.10 and not profile.team_activity:
        return DormancyType.EXPLOIT_RECOVERY

    if profile.team_activity and profile.dormancy_days < 365:
        return DormancyType.HIBERNATION

    return DormancyType.ABANDONED


def compute_decay_component(kappa: float, dormancy_days: float) -> float:
    """
    Decay component: e^(-κ·T)
    κ = 0.000 (MIGRATION) → e^0 = 1.0 (no decay)
    κ = 0.008 (ABANDONED) at T=365 → e^{-2.92} ≈ 0.054
    """
    return math.exp(-kappa * dormancy_days)


def compute_continuity_component(
    pre_dormancy_features:  list[float],
    reactive_features:      list[float],
) -> float:
    """
    sim(S_pre, S_react) — cosine similarity of behavioral feature vectors.
    S_pre  = behavioral feature vector in last 90 days before dormancy
    S_react = behavioral feature vector in first 30 days after reactivation
    """
    if not pre_dormancy_features or not reactive_features:
        return 0.50  # Neutral when no data

    n = min(len(pre_dormancy_features), len(reactive_features))
    if n == 0:
        return 0.50

    pre  = pre_dormancy_features[:n]
    reac = reactive_features[:n]

    dot   = sum(a * b for a, b in zip(pre, reac))
    mag_a = sum(a ** 2 for a in pre) ** 0.5
    mag_b = sum(b ** 2 for b in reac) ** 0.5

    if mag_a <= 0 or mag_b <= 0:
        return 0.0

    similarity = dot / (mag_a * mag_b)
    return max(0.0, min(1.0, (similarity + 1.0) / 2.0))  # Map [-1,1] → [0,1]


def compute_context_component(profile: DormancyProfile) -> float:
    """
    g(C) — external context quality [0, 1]
    Factors: regulatory clarity, exploit resolution, market conditions
    """
    if profile.dormancy_type == DormancyType.MIGRATION:
        return 0.90  # Migration is intentional — context is strong

    if profile.dormancy_type == DormancyType.REGULATORY_PAUSE:
        # Context quality depends on regulatory clarity at reactivation
        return 0.70 if profile.known_regulatory else 0.40

    if profile.dormancy_type == DormancyType.EXPLOIT_RECOVERY:
        # Context depends on how well team addressed the exploit
        return max(0.0, profile.team_response_quality * (1.0 - profile.exploit_severity * 0.5))

    if profile.dormancy_type == DormancyType.HIBERNATION:
        return 0.75 if profile.team_activity else 0.50

    # ABANDONED — very low context quality
    return max(0.0, 0.30 * profile.governance_active)


def compute_resurrection(
    profile:                 DormancyProfile,
    pre_dormancy_features:   list[float],
    reactive_features:       list[float],
) -> ResurrectionScore:
    """
    Δ_resurrection = w_d · e^(-κ·T) · w_c · sim(S_pre, S_react) · w_x · g(C)

    Note: This is a WEIGHTED SUM (not product) of the three components.
    Each component is multiplied by its weight and summed.
    """
    dormancy_type = profile.dormancy_type
    kappa         = KAPPA[dormancy_type]

    decay       = compute_decay_component(kappa, profile.dormancy_days)
    continuity  = compute_continuity_component(pre_dormancy_features, reactive_features)
    context     = compute_context_component(profile)

    delta = (W_DECAY * decay) + (W_CONTINUITY * continuity) + (W_CONTEXT * context)
    delta = max(0.0, min(1.0, delta))

    # Hostile takeover risk — especially high for ABANDONED assets
    hostile_risk = 0.0
    if dormancy_type == DormancyType.ABANDONED:
        hostile_risk = max(0.0, 1.0 - decay)  # Higher as decay progresses
    elif dormancy_type == DormancyType.EXPLOIT_RECOVERY:
        hostile_risk = profile.exploit_severity * 0.50

    warning = None
    if dormancy_type == DormancyType.ABANDONED:
        warning = (
            f"ABANDONED asset reactivated after {profile.dormancy_days:.0f} days. "
            f"Hostile takeover risk={hostile_risk:.2f}. Full behavioral audit required."
        )
    elif dormancy_type == DormancyType.EXPLOIT_RECOVERY:
        warning = (
            f"EXPLOIT_RECOVERY: severity={profile.exploit_severity:.2f}. "
            f"Team response quality={profile.team_response_quality:.2f}."
        )

    signal_type = "MIGRATION" if dormancy_type == DormancyType.MIGRATION else "RESURRECTION"

    return ResurrectionScore(
        entity_id              = profile.entity_id,
        dormancy_type          = dormancy_type,
        kappa                  = kappa,
        delta_resurrection     = delta,
        decay_component        = decay,
        continuity_component   = continuity,
        context_component      = context,
        hostile_takeover_risk  = hostile_risk,
        dormancy_days          = profile.dormancy_days,
        signal_type            = signal_type,
        warning                = warning,
    )


if __name__ == "__main__":
    # ABANDONED asset test
    profile = DormancyProfile(
        entity_id="abandoned_token",
        dormancy_type=DormancyType.ABANDONED,
        dormancy_days=500.0,
        team_activity=False,
        governance_active=False,
        exploit_severity=0.0,
        team_response_quality=0.0,
        known_regulatory=False,
        chain_b_activity=0.0,
    )
    pre  = [0.8, 0.6, 0.4, 0.9, 0.7]
    reac = [0.3, 0.2, 0.8, 0.1, 0.9]  # Very different behavior
    result = compute_resurrection(profile, pre, reac)
    print(f"ABANDONED: Δ_res={result.delta_resurrection:.4f} κ={result.kappa} "
          f"hostile_risk={result.hostile_takeover_risk:.4f}")
    assert result.delta_resurrection < 0.5  # Low resurrection score

    # HIBERNATION test
    profile_h = DormancyProfile(
        entity_id="hibernating_protocol",
        dormancy_type=DormancyType.HIBERNATION,
        dormancy_days=60.0,
        team_activity=True,
        governance_active=True,
        exploit_severity=0.0,
        team_response_quality=1.0,
        known_regulatory=False,
        chain_b_activity=0.0,
    )
    pre_h  = [0.8, 0.6, 0.4, 0.9, 0.7]
    reac_h = [0.8, 0.6, 0.4, 0.9, 0.7]  # Similar behavior — healthy resurrection
    result_h = compute_resurrection(profile_h, pre_h, reac_h)
    print(f"HIBERNATION: Δ_res={result_h.delta_resurrection:.4f} κ={result_h.kappa}")
    assert result_h.delta_resurrection > 0.5

    print("L2.4 Resurrection Inference: PASS")
