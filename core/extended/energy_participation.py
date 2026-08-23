"""
TRION Protocol — L7.2 Energy Participation Index (EP)

EP = VC · PA · DC

VC = Value Concentration ratio
     VC = value_flowing_to_protocol_purpose / (value_extracted_as_MEV + fees)
     Measures what fraction of value goes to the protocol's stated purpose
     vs what is extracted by intermediaries.
     VC near 1.0: protocol fulfills its purpose efficiently
     VC near 0.0: most value captured by MEV bots and fee extraction

PA = Participation Alignment — entropy of interaction type distribution
     PA = H(interaction_type_distribution)
     Healthy protocols have diverse interaction patterns (high entropy).
     Manipulated or extractive protocols show narrow interaction patterns.

DC = Developer Commitment
     DC = (active_core_contributors × median_commit_tenure_days)
          / (total_contributor_count × reference_tenure_days)
     Long-tenured committed core team = high DC.
     High turnover or few contributors = low DC.

EP used in:
  - ECOSYSTEM_HEALTH signal
  - BIBL (Behavioral Inter-Block Layer) guidance
  - MEV_EXPOSURE signal calibration
  - Protocol health assessment for lending protocol collateral

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Dict, List, Optional


REFERENCE_TENURE_DAYS = 365.0   # 1 year = reference for DC computation


@dataclass
class ProtocolEconomics:
    """
    Economic flow data for EP computation.
    Sourced from: on-chain analysis, protocol transparency reports.
    """
    protocol_id:                  str
    value_to_protocol_purpose:    float   # USD value serving stated purpose
    value_mev_extracted:          float   # USD value captured by MEV
    value_fees_extracted:         float   # Total protocol fees not serving purpose
    interaction_type_counts:      Dict[str, int]  # {interaction_type: count}


@dataclass
class DeveloperData:
    """Developer activity for DC computation."""
    protocol_id:                  str
    active_core_contributors:     int     # Contributors with commits in last 90 days
    median_commit_tenure_days:    float   # Median tenure of core contributors
    total_contributor_count:      int     # All contributors ever
    commit_velocity:              float   # Commits per week (recent)
    issue_resolution_rate:        float   # [0, 1] — issues closed / opened ratio


@dataclass
class EPResult:
    """
    EP = VC · PA · DC
    """
    protocol_id:   str
    ep:            float    # [0, 1] Energy Participation Index
    vc:            float    # Value Concentration [0, 1]
    pa:            float    # Participation Alignment (normalized entropy) [0, 1]
    dc:            float    # Developer Commitment [0, 1]
    label:         str      # THRIVING / ALIGNED / EXTRACTIVE / PARASITIC
    mev_fraction:  float    # Fraction of value captured by MEV
    warning:       Optional[str]


def compute_vc(econ: ProtocolEconomics) -> float:
    """
    VC = value_flowing_to_protocol_purpose / (value_extracted_as_MEV + fees)

    Interpretation:
    - VC > 1.0: more value to purpose than extracted → capped at 1.0
    - VC ≈ 1.0: balanced (protocol serves purpose efficiently)
    - VC < 0.5: extractive (more taken than given to purpose)
    - VC ≈ 0.0: parasitic (almost all value extracted by MEV/fees)

    Edge case: if total extraction is 0, VC = 1.0 (pure public good).
    """
    total_extraction = econ.value_mev_extracted + econ.value_fees_extracted
    if total_extraction <= 0:
        return 1.0  # No extraction at all — fully purpose-aligned

    vc_raw = econ.value_to_protocol_purpose / total_extraction
    return min(1.0, max(0.0, vc_raw))


def compute_pa(interaction_type_counts: Dict[str, int]) -> float:
    """
    PA = normalized_shannon_entropy(interaction_type_distribution)

    H(X) = -Σ p_i · log₂(p_i)
    PA   = H(X) / log₂(n_types)   [normalized to [0, 1]]

    Diverse interaction patterns → high entropy → high PA → healthy protocol
    Concentrated patterns → low entropy → extractive focus
    """
    if not interaction_type_counts:
        return 0.0

    total = sum(interaction_type_counts.values())
    if total <= 0:
        return 0.0

    n_types = len(interaction_type_counts)
    if n_types == 1:
        return 0.0  # Only one type = zero diversity

    h = 0.0
    for count in interaction_type_counts.values():
        if count > 0:
            p = count / total
            h -= p * math.log2(p)

    h_max = math.log2(n_types)
    return h / h_max if h_max > 0 else 0.0


def compute_dc(dev: DeveloperData) -> float:
    """
    DC = (active_core_contributors × median_commit_tenure_days)
         / (total_contributor_count × REFERENCE_TENURE_DAYS)

    A protocol with 10 core contributors averaging 2 years of tenure,
    out of 100 total ever, has:
    DC = (10 × 730) / (100 × 365) = 7300 / 36500 ≈ 0.20

    High DC: few deeply committed contributors.
    Low DC: many contributors but shallow tenure → instability risk.
    """
    if dev.total_contributor_count <= 0:
        return 0.0

    numerator   = dev.active_core_contributors * dev.median_commit_tenure_days
    denominator = dev.total_contributor_count * REFERENCE_TENURE_DAYS

    dc = numerator / denominator if denominator > 0 else 0.0
    return min(1.0, max(0.0, dc))


def compute_ep(econ: ProtocolEconomics, dev: DeveloperData) -> EPResult:
    """
    EP = VC · PA · DC
    """
    vc = compute_vc(econ)
    pa = compute_pa(econ.interaction_type_counts)
    dc = compute_dc(dev)
    ep = vc * pa * dc

    total_value  = econ.value_to_protocol_purpose + econ.value_mev_extracted + econ.value_fees_extracted
    mev_fraction = (econ.value_mev_extracted / total_value) if total_value > 0 else 0.0

    if ep >= 0.60:
        label = "THRIVING"
    elif ep >= 0.40:
        label = "ALIGNED"
    elif ep >= 0.20:
        label = "EXTRACTIVE"
    else:
        label = "PARASITIC"

    warning = None
    if mev_fraction > 0.50:
        warning = (
            f"HIGH MEV EXTRACTION: {mev_fraction*100:.1f}% of value captured by MEV. "
            f"EP={ep:.4f} [{label}]. MEV_EXPOSURE signal warranted."
        )
    elif label == "PARASITIC":
        warning = f"PARASITIC protocol: EP={ep:.4f}. VC={vc:.4f} PA={pa:.4f} DC={dc:.4f}."

    # NOTE: A prior implementation referenced an undefined `econ.renewable_energy_fraction`
    # attribute and an undefined `ep_score` variable here, then attempted to construct
    # EPResult with a non-existent `ep_score=` kwarg. That code was dead-code-by-bug
    # (AttributeError + NameError + TypeError on every call) and has been removed.
    # The whitepaper L7.2 formula is strictly EP = VC * PA * DC (no green-energy
    # multiplier); the real value is returned below.

    return EPResult(
        protocol_id  = econ.protocol_id,
        ep           = ep,
        vc           = vc,
        pa           = pa,
        dc           = dc,
        label        = label,
        mev_fraction = mev_fraction,
        warning      = warning,
    )


if __name__ == "__main__":
    # Healthy protocol (Uniswap-like)
    econ_healthy = ProtocolEconomics(
        protocol_id                  = "healthy_dex",
        value_to_protocol_purpose    = 5_000_000.0,
        value_mev_extracted          = 200_000.0,
        value_fees_extracted         = 800_000.0,
        interaction_type_counts      = {
            "SWAP": 150000, "LIQUIDITY_ADD": 5000, "LIQUIDITY_REMOVE": 4800,
            "GOVERNANCE_VOTE": 200, "REWARD_CLAIM": 8000,
        }
    )
    dev_healthy = DeveloperData(
        protocol_id               = "healthy_dex",
        active_core_contributors  = 20,     # 20 active core contributors
        median_commit_tenure_days = 730.0,  # 2 years median tenure
        total_contributor_count   = 40,     # Tight committed team
        commit_velocity           = 35.0,
        issue_resolution_rate     = 0.88,
    )
    result = compute_ep(econ_healthy, dev_healthy)
    print(f"Healthy DEX: EP={result.ep:.4f} [{result.label}] "
          f"VC={result.vc:.4f} PA={result.pa:.4f} DC={result.dc:.4f}")
    assert result.ep > 0.20

    # Parasitic protocol (MEV extraction dominant)
    econ_mev = ProtocolEconomics(
        protocol_id                  = "mev_extractor",
        value_to_protocol_purpose    = 100_000.0,
        value_mev_extracted          = 8_000_000.0,
        value_fees_extracted         = 2_000_000.0,
        interaction_type_counts      = {"MEV_SANDWICH": 90000, "SWAP": 5000, "OTHER": 500}
    )
    dev_mev = DeveloperData(
        protocol_id              = "mev_extractor",
        active_core_contributors = 2,
        median_commit_tenure_days = 45.0,
        total_contributor_count  = 200,
        commit_velocity          = 3.0,
        issue_resolution_rate    = 0.20,
    )
    result_mev = compute_ep(econ_mev, dev_mev)
    print(f"MEV extractor: EP={result_mev.ep:.4f} [{result_mev.label}] "
          f"MEV_frac={result_mev.mev_fraction:.4f}")
    assert result_mev.label in ("EXTRACTIVE", "PARASITIC")
    assert result_mev.warning is not None

    print("L7.2 Energy Participation Index: PASS")
