"""
TRION Protocol — L4.8 HHI + Geographic Enforcement

HHI(t) = Σ_j (s_j · d_j / Σ_k s_k·d_k)² × 10000

Where s_j · d_j = effective stake of validator j (stake × diversity weight)

HHI Tiers (diversity enforcement):
    <1500:       HEALTHY — no action
    1500-2500:   WARNING — 2× reward multiplier for underrepresented validators
    2500-4000:   DANGER  — weight cap: no cluster > 15% effective stake
    >4000:       CRITICAL — consensus paused, governance emergency

Geographic constraints (separate from HHI, continuous):
    max single region:         < 40% of effective stake
    max single jurisdiction:   < 30% of effective stake
    minimum continents:        >= 4

Falsification conditions:
    F8: Falsified if HHI > 2500 sustained for 30 consecutive days without correction
    F9: Falsified if geographic coverage < 4 continents without automatic incentive

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class HHITier(Enum):
    HEALTHY  = "HEALTHY"
    WARNING  = "WARNING"
    DANGER   = "DANGER"
    CRITICAL = "CRITICAL"


HHI_THRESHOLDS = {
    HHITier.HEALTHY:  1500,
    HHITier.WARNING:  2500,
    HHITier.DANGER:   4000,
}

MAX_SINGLE_REGION     = 0.40  # 40%
MAX_SINGLE_JURISDICTION = 0.30  # 30%
MIN_CONTINENTS        = 4
MAX_CLUSTER_SHARE     = 0.15  # 15% cap per cluster in DANGER tier


@dataclass
class ValidatorStake:
    """Effective stake for one validator."""
    validator_id:   str
    stake:          float
    diversity_score: float  # d_j
    effective_stake: float  # s_j · d_j
    geographic_region: str
    jurisdiction:   str
    continent:      str


@dataclass
class HHIResult:
    """Full HHI computation with geographic enforcement."""
    hhi:                    float
    tier:                   HHITier
    total_effective_stake:  float
    validator_count:        int
    region_shares:          Dict[str, float]    # region → share of effective stake
    jurisdiction_shares:    Dict[str, float]
    continent_count:        int
    continents:             List[str]

    # Enforcement actions
    reward_multiplier_regions: List[str]        # Regions eligible for 2× reward
    weight_capped_validators:  List[str]        # Validators weight-capped
    consensus_paused:          bool             # CRITICAL tier
    governance_emergency:      bool

    # F8/F9 checks
    hhi_days_above_2500:       int             # Days sustained above WARNING
    f8_violation:              bool            # HHI > 2500 for 30+ days
    f9_violation:              bool            # < 4 continents, no incentive

    geographic_violations:     List[str]       # Regions exceeding max share
    auto_response:             str


def compute_hhi(validators: List[ValidatorStake]) -> tuple[float, Dict[str, float]]:
    """
    HHI(t) = Σ_j (w_j_eff / Σ_k w_k_eff)² × 10000
    where w_j_eff = s_j · d_j
    """
    total = sum(v.effective_stake for v in validators)
    if total <= 0:
        return 0.0, {}

    weights = {}
    hhi = 0.0
    for v in validators:
        share = v.effective_stake / total
        weights[v.validator_id] = share
        hhi += share ** 2

    return hhi * 10000, weights


def compute_geographic_distribution(
    validators: List[ValidatorStake],
    total_effective_stake: float,
) -> tuple[Dict[str, float], Dict[str, float], int, List[str]]:
    """Compute regional, jurisdictional, and continental distribution."""
    region_stake: Dict[str, float] = {}
    juris_stake:  Dict[str, float] = {}
    continents:   set[str]         = set()

    for v in validators:
        region_stake[v.geographic_region] = region_stake.get(v.geographic_region, 0) + v.effective_stake
        juris_stake[v.jurisdiction]       = juris_stake.get(v.jurisdiction, 0) + v.effective_stake
        continents.add(v.continent)

    if total_effective_stake > 0:
        region_shares = {r: s / total_effective_stake for r, s in region_stake.items()}
        juris_shares  = {j: s / total_effective_stake for j, s in juris_stake.items()}
    else:
        region_shares = {}
        juris_shares  = {}

    return region_shares, juris_shares, len(continents), sorted(continents)


def compute_hhi_enforcement(
    validators:              List[ValidatorStake],
    hhi_days_above_2500:     int = 0,
    continents_have_incentive: bool = True,
) -> HHIResult:
    """
    Full HHI computation with enforcement tiers and geographic checks.
    """
    if not validators:
        return HHIResult(
            hhi=0, tier=HHITier.HEALTHY,
            total_effective_stake=0, validator_count=0,
            region_shares={}, jurisdiction_shares={},
            continent_count=0, continents=[],
            reward_multiplier_regions=[], weight_capped_validators=[],
            consensus_paused=False, governance_emergency=False,
            hhi_days_above_2500=0, f8_violation=False, f9_violation=False,
            geographic_violations=[], auto_response="no_validators",
        )

    total_eff = sum(v.effective_stake for v in validators)
    hhi, weights = compute_hhi(validators)
    region_shares, juris_shares, continent_count, continents = compute_geographic_distribution(
        validators, total_eff
    )

    # Classify tier — whitepaper L4.8 four response tiers:
    #   HHI < 1500 HEALTHY | 1500–2500 WARNING | 2500–4000 DANGER | > 4000 CRITICAL
    if hhi > 4000:
        tier = HHITier.CRITICAL
    elif hhi > 2500:
        tier = HHITier.DANGER
    elif hhi > 1500:
        tier = HHITier.WARNING
    else:
        tier = HHITier.HEALTHY

    # Geographic violations
    geo_violations = []
    for region, share in region_shares.items():
        if share > MAX_SINGLE_REGION:
            geo_violations.append(f"region:{region}:{share:.3f}>{MAX_SINGLE_REGION}")
    for juris, share in juris_shares.items():
        if share > MAX_SINGLE_JURISDICTION:
            geo_violations.append(f"juris:{juris}:{share:.3f}>{MAX_SINGLE_JURISDICTION}")

    # Enforcement actions per tier
    reward_multiplier_regions = []
    weight_capped_validators  = []
    consensus_paused          = False
    governance_emergency      = False
    auto_response             = "no_action"

    if tier == HHITier.CRITICAL:
        consensus_paused     = True
        governance_emergency = True
        auto_response        = "CONSENSUS_PAUSED_GOVERNANCE_EMERGENCY"

    elif tier == HHITier.DANGER:
        # Cap: no cluster > 15% effective stake
        for v in validators:
            if weights.get(v.validator_id, 0) > MAX_CLUSTER_SHARE:
                weight_capped_validators.append(v.validator_id)
        auto_response = f"WEIGHT_CAP_{MAX_CLUSTER_SHARE*100:.0f}pct"

    elif tier == HHITier.WARNING:
        # 2× reward multiplier for underrepresented regions
        avg_share = 1.0 / len(region_shares) if region_shares else 0
        for region, share in region_shares.items():
            if share < avg_share * 0.5:  # Significantly underrepresented
                reward_multiplier_regions.append(region)
        auto_response = "REWARD_MULTIPLIER_UNDERREPRESENTED"

    # F8: HHI > 2500 for 30+ consecutive days
    f8_violation = (hhi > 2500) and (hhi_days_above_2500 >= 30)

    # F9: < 4 continents without automatic corrective incentive
    f9_violation = (continent_count < MIN_CONTINENTS) and not continents_have_incentive

    return HHIResult(
        hhi                      = hhi,
        tier                     = tier,
        total_effective_stake    = total_eff,
        validator_count          = len(validators),
        region_shares            = region_shares,
        jurisdiction_shares      = juris_shares,
        continent_count          = continent_count,
        continents               = continents,
        reward_multiplier_regions = reward_multiplier_regions,
        weight_capped_validators  = weight_capped_validators,
        consensus_paused         = consensus_paused,
        governance_emergency     = governance_emergency,
        hhi_days_above_2500      = hhi_days_above_2500,
        f8_violation             = f8_violation,
        f9_violation             = f9_violation,
        geographic_violations    = geo_violations,
        auto_response            = auto_response,
    )


if __name__ == "__main__":
    # Diverse validator set (HEALTHY)
    validators = [
        ValidatorStake(f"v{i}", 100.0, 0.80, 80.0,
                       f"region_{i % 8}", f"juris_{i % 6}", f"continent_{i % 5}")
        for i in range(100)
    ]
    result = compute_hhi_enforcement(validators)
    print(f"Diverse: HHI={result.hhi:.1f} tier={result.tier.value} continents={result.continent_count}")
    assert result.tier == HHITier.HEALTHY
    assert result.continent_count >= 4
    assert not result.f8_violation

    # Concentrated validator set (CRITICAL)
    concentrated = [
        ValidatorStake(f"v{i}", 1000.0 if i < 5 else 1.0, 0.80,
                       800.0 if i < 5 else 0.8,
                       "single_region", "single_juris", "single_continent")
        for i in range(20)
    ]
    result_c = compute_hhi_enforcement(concentrated)
    print(f"Concentrated: HHI={result_c.hhi:.1f} tier={result_c.tier.value} paused={result_c.consensus_paused}")
    assert result_c.hhi > 2500

    print("L4.8 HHI + Geographic Enforcement: PASS")
