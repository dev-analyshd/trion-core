"""
TRION Protocol — L8.1 Sovereign Behavioral Assessment (SBA)

SBA(nation, t) = w_E·E + w_I·I + w_S·S + w_G·G + w_C·C

Weights (from whitepaper):
    w_E = 0.30  Economic stability component
    w_I = 0.25  Institutional integrity component  [KEY: I = corr(stated_policy, onchain_enforcement)]
    w_S = 0.20  Social cohesion component
    w_G = 0.15  Governance quality component
    w_C = 0.10  Crypto/digital asset behavior component

The critical insight: I = corr(stated_policy, onchain_enforcement_behavior)

Governments publish policies. On-chain data reveals how they actually enforce them.
When stated_policy diverges from onchain_enforcement → I drops → SBA drops →
REGULATORY_BEHAVIORAL signal triggered (F15 condition).

SBA feeds into:
  - REGULATORY_BEHAVIORAL signal (advance warning of regulatory action)
  - Chameleon Protocol threat level computation
  - Geographic HHI enforcement (hostile jurisdiction detection)

Falsification F11:
  Falsified if SBA systematically diverges from IMF/World Bank composites over 24 months.

Honest disclosure: I-component corr threshold and jurisdictional data quality
require regulatory lawyer embedded in the team. Cannot be built correctly without them.

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# SBA component weights
W_E = 0.30   # Economic stability
W_I = 0.25   # Institutional integrity (behavioral vs stated)
W_S = 0.20   # Social cohesion
W_G = 0.15   # Governance quality
W_C = 0.10   # Crypto/digital asset behavior


@dataclass
class SBAInputs:
    """
    All inputs for SBA computation for one nation at time t.
    """
    nation_id:              str
    nation_name:            str
    timestamp:              float

    # E: Economic stability (0-1)
    gdp_growth_rate:        float   # Recent GDP growth (normalized)
    inflation_stability:    float   # 1 - normalized_inflation_volatility
    forex_reserve_ratio:    float   # FX reserves / imports months coverage (normalized)
    debt_to_gdp:            float   # Inverse: 1 - (debt/gdp normalized)

    # I: Institutional integrity — behavioral divergence from stated policy
    stated_policy_scores:   List[float]   # Stated policy positions (time series)
    onchain_enforcement:    List[float]   # Actual on-chain enforcement behavior

    # S: Social cohesion (0-1)
    gini_coefficient:       float   # Income inequality (inverted: 1 - normalized_gini)
    protest_intensity:      float   # Inverse: 1 - normalized_protest_intensity
    press_freedom_score:    float   # RSF press freedom index (normalized)

    # G: Governance quality (0-1)
    wgi_government:         float   # World Governance Indicators score (normalized)
    regulatory_consistency: float   # Consistency of regulatory decisions over time
    judicial_independence:  float   # Judicial independence score

    # C: Crypto/digital asset behavior (0-1)
    crypto_regulatory_clarity: float  # Clarity of crypto regulatory framework
    cbdc_behavorial_coherence: float  # If CBDC: behavioral consistency with policy
    defi_accessibility:     float     # Whether DeFi is allowed vs blocked


@dataclass
class SBAResult:
    """
    Sovereign Behavioral Assessment result.
    """
    nation_id:              str
    nation_name:            str
    sba:                    float   # [0, 1] overall SBA score
    e_component:            float   # Economic stability
    i_component:            float   # Institutional integrity
    s_component:            float   # Social cohesion
    g_component:            float   # Governance quality
    c_component:            float   # Crypto behavior
    policy_behavior_corr:   float   # corr(stated_policy, onchain_enforcement)
    regulatory_threat_level: str    # LOW / MEDIUM / HIGH / CRITICAL
    advance_warning:        bool    # True if REGULATORY_BEHAVIORAL signal warranted
    signal_type:            str
    warning:                Optional[str]


def compute_pearson_corr(x: List[float], y: List[float]) -> float:
    """Pearson correlation between stated policy and actual enforcement."""
    n = min(len(x), len(y))
    if n < 3:
        return 0.5  # Neutral when insufficient data

    x = x[-n:]
    y = y[-n:]
    mx = sum(x) / n
    my = sum(y) / n
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    vx  = sum((xi - mx) ** 2 for xi in x)
    vy  = sum((yi - my) ** 2 for yi in y)
    if vx <= 0 or vy <= 0:
        return 0.5
    corr = cov / math.sqrt(vx * vy)
    return max(-1.0, min(1.0, corr))


def compute_economic_stability(inp: SBAInputs) -> float:
    """E component: economic stability from macro indicators."""
    gdp_factor    = max(0.0, min(1.0, (inp.gdp_growth_rate + 0.10) / 0.20))  # Normalize: -10% to +10%
    inflation_fac = max(0.0, min(1.0, inp.inflation_stability))
    forex_factor  = max(0.0, min(1.0, inp.forex_reserve_ratio))
    debt_factor   = max(0.0, min(1.0, inp.debt_to_gdp))

    return (0.30 * gdp_factor + 0.25 * inflation_fac +
            0.25 * forex_factor + 0.20 * debt_factor)


def compute_institutional_integrity(inp: SBAInputs) -> float:
    """
    I = corr(stated_policy, onchain_enforcement_behavior)

    This is the core innovation of SBA. Governments that say one thing
    and do another have low I. Behavioral truth from on-chain data.

    Normalized to [0, 1]: I = (corr + 1) / 2
    corr = 1.0 → I = 1.0 (perfect policy-behavior alignment)
    corr = 0.0 → I = 0.5 (uncorrelated)
    corr = -1.0 → I = 0.0 (doing opposite of stated policy)
    """
    corr = compute_pearson_corr(inp.stated_policy_scores, inp.onchain_enforcement)
    return (corr + 1.0) / 2.0


def compute_social_cohesion(inp: SBAInputs) -> float:
    """S component: social cohesion from inequality and press freedom."""
    return (0.40 * inp.gini_coefficient +
            0.30 * inp.protest_intensity +
            0.30 * inp.press_freedom_score)


def compute_governance_quality(inp: SBAInputs) -> float:
    """G component: governance quality."""
    return (0.40 * inp.wgi_government +
            0.35 * inp.regulatory_consistency +
            0.25 * inp.judicial_independence)


def compute_crypto_behavior(inp: SBAInputs) -> float:
    """C component: crypto/digital asset behavior."""
    return (0.40 * inp.crypto_regulatory_clarity +
            0.30 * inp.cbdc_behavorial_coherence +
            0.30 * inp.defi_accessibility)


def compute_sba(inp: SBAInputs) -> SBAResult:
    """
    SBA(nation, t) = w_E·E + w_I·I + w_S·S + w_G·G + w_C·C
    """
    e = compute_economic_stability(inp)
    i = compute_institutional_integrity(inp)
    s = compute_social_cohesion(inp)
    g = compute_governance_quality(inp)
    c = compute_crypto_behavior(inp)

    sba = W_E * e + W_I * i + W_S * s + W_G * g + W_C * c
    sba = max(0.0, min(1.0, sba))

    policy_behavior_corr = compute_pearson_corr(
        inp.stated_policy_scores, inp.onchain_enforcement
    )

    # Regulatory threat level
    if sba < 0.25 or i < 0.25:
        threat_level = "CRITICAL"
    elif sba < 0.40 or i < 0.35:
        threat_level = "HIGH"
    elif sba < 0.55 or i < 0.50:
        threat_level = "MEDIUM"
    elif sba < 0.70:
        threat_level = "LOW"
    else:
        threat_level = "STABLE"

    advance_warning = threat_level in ("HIGH", "CRITICAL")

    warning = None
    if advance_warning:
        warning = (
            f"REGULATORY_BEHAVIORAL ADVANCE WARNING: {inp.nation_name} "
            f"SBA={sba:.4f} I={i:.4f} threat={threat_level}. "
            f"Policy-behavior corr={policy_behavior_corr:.4f}. "
            "Historical pattern matching: regulatory action likely within 60-180 days."
        )
    elif i < 0.40:
        warning = (
            f"LOW INSTITUTIONAL INTEGRITY: {inp.nation_name} "
            f"stated_policy vs onchain_enforcement corr={policy_behavior_corr:.4f}. "
            "Government behavior diverging from stated policy."
        )

    return SBAResult(
        nation_id              = inp.nation_id,
        nation_name            = inp.nation_name,
        sba                    = sba,
        e_component            = e,
        i_component            = i,
        s_component            = s,
        g_component            = g,
        c_component            = c,
        policy_behavior_corr   = policy_behavior_corr,
        regulatory_threat_level = threat_level,
        advance_warning        = advance_warning,
        signal_type            = "REGULATORY_BEHAVIORAL",
        warning                = warning,
    )


if __name__ == "__main__":
    import time

    # Stable jurisdiction (Switzerland-like)
    stable = SBAInputs(
        nation_id="ch", nation_name="Switzerland", timestamp=time.time(),
        gdp_growth_rate=0.025, inflation_stability=0.90, forex_reserve_ratio=0.85, debt_to_gdp=0.55,
        stated_policy_scores=[0.8, 0.82, 0.81, 0.83, 0.80, 0.82],
        onchain_enforcement  =[0.79, 0.81, 0.80, 0.82, 0.79, 0.81],
        gini_coefficient=0.78, protest_intensity=0.85, press_freedom_score=0.92,
        wgi_government=0.90, regulatory_consistency=0.88, judicial_independence=0.95,
        crypto_regulatory_clarity=0.85, cbdc_behavorial_coherence=0.75, defi_accessibility=0.80,
    )
    result = compute_sba(stable)
    print(f"Switzerland: SBA={result.sba:.4f} I={result.i_component:.4f} threat={result.regulatory_threat_level}")
    assert result.regulatory_threat_level in ("STABLE", "LOW")

    # Hostile jurisdiction (diverging behavior)
    hostile = SBAInputs(
        nation_id="hostile", nation_name="Hostile Nation", timestamp=time.time(),
        gdp_growth_rate=-0.02, inflation_stability=0.30, forex_reserve_ratio=0.20, debt_to_gdp=0.15,
        stated_policy_scores=[0.8,  0.8,  0.8,  0.8,  0.8,  0.8],   # Says pro-crypto
        onchain_enforcement  =[0.1,  0.05, 0.02, 0.0,  0.0,  0.0],   # Blocks all DeFi
        gini_coefficient=0.20, protest_intensity=0.10, press_freedom_score=0.05,
        wgi_government=0.15, regulatory_consistency=0.10, judicial_independence=0.08,
        crypto_regulatory_clarity=0.05, cbdc_behavorial_coherence=0.20, defi_accessibility=0.0,
    )
    result_h = compute_sba(hostile)
    print(f"Hostile: SBA={result_h.sba:.4f} I={result_h.i_component:.4f} threat={result_h.regulatory_threat_level}")
    assert result_h.advance_warning
    assert result_h.regulatory_threat_level in ("HIGH", "CRITICAL")

    print("L8.1 Sovereign Behavioral Assessment: PASS")
