"""
Diversity-Weighted BFT Consensus — TRION L4
Sigma(t) = (sum_i w_i * v_i) / (sum_i w_i)
w_i = stake_i * diversity_i * history_i
Dynamic consensus window delta(t).
HHI-based concentration detection.
"""
import math
from dataclasses import dataclass, field
from typing import List, Optional, Dict
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


SLASH_RATES = {
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
    diversity:    float
    history:      float
    is_excluded:  bool = False
    is_slashed:   bool = False
    slash_history: List[SlashingType] = field(default_factory=list)
    violations:   int = 0

    @property
    def weight(self) -> float:
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


def compute_hhi(validators: List[Validator]) -> float:
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
    v = max(0.0, min(1.0, volatility))
    return round(WINDOW_MAX - (WINDOW_MAX - WINDOW_MIN) * v)


def compute_sigma(
    validators: List[Validator],
    votes:      Dict[str, float],
    volatility: float = 0.10,
) -> ConsensusResult:
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
    sigma = weighted_sum / total_weight if total_weight > 0 else 0.0

    # BFT safety: Byzantine fraction by stake (not zeroed weight)
    all_stake  = sum(v.stake for v in validators)
    byz_stake  = sum(v.stake for v in validators if v.is_slashed)
    byz_frac   = byz_stake / all_stake if all_stake > 0 else 0.0
    bft_safe   = byz_frac < BFT_FAULT_TOLERANCE

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
    rate   = SLASH_RATES[slash_type]
    amount = validator.stake * rate
    validator.stake       -= amount
    validator.is_slashed   = True
    validator.slash_history.append(slash_type)
    validator.violations  += 1
    return amount
