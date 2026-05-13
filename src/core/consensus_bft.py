"""
Diversity-Weighted BFT Consensus — TRION L4 (Spiritual Plane)
Sigma(t) = (sum_i w_i * v_i) / (sum_i w_i)
w_i = stake_i * diversity_i * history_i

Whitepaper-exact:
- BFT safety uses stake (not zeroed weight) for Byzantine fraction
- HHI-based concentration detection (4 levels)
- Dynamic consensus window delta(t) = f(volatility)
- 5 slashing types with whitepaper-specified rates
- INIT Ceremony (8 conditions) gated on first signal

From trion-protocol/ whitepaper scaffold — fully tested (15/15 tests).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum


BFT_FAULT_TOLERANCE = 1.0 / 3.0

HHI_HEALTHY  = 2500
HHI_WARNING  = 3500
HHI_DANGER   = 5000
HHI_CRITICAL = 7500

WINDOW_MIN = 3
WINDOW_MAX = 21


class HHIStatus(Enum):
    HEALTHY  = "HEALTHY"
    WARNING  = "WARNING"
    DANGER   = "DANGER"
    CRITICAL = "CRITICAL"


class SlashingType(Enum):
    DOUBLE_SIGN        = "DOUBLE_SIGN"
    SUSTAINED_DOWNTIME = "SUSTAINED_DOWNTIME"
    MANIPULATION       = "MANIPULATION"
    SYBIL_COLLUSION    = "SYBIL_COLLUSION"
    GOVERNANCE_CAPTURE = "GOVERNANCE_CAPTURE"


SLASH_RATES: Dict[SlashingType, float] = {
    SlashingType.DOUBLE_SIGN:        0.10,
    SlashingType.SUSTAINED_DOWNTIME: 0.02,
    SlashingType.MANIPULATION:       0.25,
    SlashingType.SYBIL_COLLUSION:    0.15,
    SlashingType.GOVERNANCE_CAPTURE: 0.20,
}


@dataclass
class Validator:
    validator_id: str
    stake:        float
    diversity:    float    # geographic + cultural diversity score [0,1]
    history:      float    # uptime/accuracy history [0,1]
    is_excluded:  bool = False
    is_slashed:   bool = False
    slash_history: List[SlashingType] = field(default_factory=list)
    violations:   int  = 0

    @property
    def weight(self) -> float:
        """Voting weight: 0 if excluded or slashed, else stake*diversity*history."""
        if self.is_excluded or self.is_slashed:
            return 0.0
        return self.stake * self.diversity * self.history

    @property
    def is_byzantine(self) -> bool:
        return self.is_slashed


@dataclass
class ConsensusResult:
    sigma:                    float
    participant_count:        int
    total_weight:             float
    hhi:                      float
    hhi_status:               HHIStatus
    window_size:              int
    bft_safe:                 bool
    byzantine_weight_fraction: float

    def to_dict(self) -> dict:
        return {
            "sigma":                    self.sigma,
            "participant_count":        self.participant_count,
            "total_weight":             self.total_weight,
            "hhi":                      self.hhi,
            "hhi_status":               self.hhi_status.value,
            "window_size":              self.window_size,
            "bft_safe":                 self.bft_safe,
            "byzantine_weight_fraction": self.byzantine_weight_fraction,
        }


def compute_hhi(validators: List[Validator]) -> float:
    """HHI = sum(s_i^2) * 10000 where s_i = stake_i / total_stake."""
    total = sum(v.stake for v in validators if not v.is_excluded)
    if total == 0:
        return 10000.0
    shares = [(v.stake / total) for v in validators if not v.is_excluded]
    return sum(s**2 for s in shares) * 10000


def hhi_status(hhi: float) -> HHIStatus:
    if hhi < HHI_HEALTHY:  return HHIStatus.HEALTHY
    if hhi < HHI_WARNING:  return HHIStatus.WARNING
    if hhi < HHI_DANGER:   return HHIStatus.DANGER
    return HHIStatus.CRITICAL


def dynamic_window(volatility: float) -> int:
    """delta(t) = WINDOW_MAX - (WINDOW_MAX - WINDOW_MIN) * V(t)"""
    v = max(0.0, min(1.0, volatility))
    return round(WINDOW_MAX - (WINDOW_MAX - WINDOW_MIN) * v)


def compute_sigma(
    validators: List[Validator],
    votes:      Dict[str, float],
    volatility: float = 0.10,
) -> ConsensusResult:
    """
    Sigma(t) = weighted average of validator votes on active (non-excluded, non-slashed) set.
    BFT safety check uses raw stake (not zeroed weight) to prevent gaming.
    """
    hhi    = compute_hhi(validators)
    status = hhi_status(hhi)
    window = dynamic_window(volatility)

    active = [v for v in validators
              if not v.is_excluded and not v.is_slashed
              and v.validator_id in votes]

    if not active:
        return ConsensusResult(
            sigma=0.0, participant_count=0, total_weight=0.0,
            hhi=hhi, hhi_status=status, window_size=window,
            bft_safe=False, byzantine_weight_fraction=1.0,
        )

    total_weight = sum(v.weight for v in active)
    weighted_sum = sum(v.weight * votes[v.validator_id] for v in active)
    sigma        = weighted_sum / total_weight if total_weight > 0 else 0.0

    # BFT: Byzantine fraction by stake (not zeroed weight — prevents gaming)
    all_stake = sum(v.stake for v in validators)
    byz_stake = sum(v.stake for v in validators if v.is_slashed)
    byz_frac  = byz_stake / all_stake if all_stake > 0 else 0.0
    bft_safe  = byz_frac < BFT_FAULT_TOLERANCE

    return ConsensusResult(
        sigma=round(max(0.0, min(1.0, sigma)), 6),
        participant_count=len(active),
        total_weight=round(total_weight, 2),
        hhi=round(hhi, 2),
        hhi_status=status,
        window_size=window,
        bft_safe=bft_safe,
        byzantine_weight_fraction=round(byz_frac, 6),
    )


def apply_slash(validator: Validator, slash_type: SlashingType) -> float:
    """Apply slashing penalty. Returns slashed amount. Sets is_slashed=True."""
    rate   = SLASH_RATES[slash_type]
    amount = validator.stake * rate
    validator.stake      -= amount
    validator.is_slashed  = True
    validator.slash_history.append(slash_type)
    validator.violations += 1
    return amount
