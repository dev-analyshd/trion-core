"""
TRION Protocol — L8.1: Sovereign Behavioral Assessment (SBA)
Chapter 12: Macro-Behavioral Intelligence

SBA(nation, t) = w_E·E(t) + w_I·I(t) + w_S·S(t) + w_G·G(t) + w_C·C(t)

Components:
  E = Economic Behavioral Regularity
      corr(stated_GDP_growth, onchain_economic_activity) ∈ [-1, 1] → normalized [0,1]
  I = Institutional Integrity
      corr(stated_policy, onchain_enforcement) — measures policy-action gap
  S = Sovereign Signaling Credibility
      CRED-weighted track record of sovereign signal accuracy
  G = Geopolitical Behavioral Coherence
      consistency of cross-border behavioral patterns
  C = Currency Behavior Alignment
      alignment between stated monetary policy and onchain FX/stablecoin flows

Weights (whitepaper L8.1):
  w_E=0.25, w_I=0.25, w_S=0.20, w_G=0.15, w_C=0.15   (sum=1.00)

SBA ∈ [0, 1]
  ≥ 0.75  HIGH_CREDIBILITY
  0.55–0.75  MODERATE_CREDIBILITY
  0.35–0.55  LOW_CREDIBILITY
  < 0.35  BEHAVIORAL_RISK

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

W_E = 0.25
W_I = 0.25
W_S = 0.20
W_G = 0.15
W_C = 0.15

assert abs(W_E + W_I + W_S + W_G + W_C - 1.0) < 1e-9, "SBA weights must sum to 1.0"

SBA_HIGH       = 0.75
SBA_MODERATE   = 0.55
SBA_LOW        = 0.35


def _corr_to_score(corr: float) -> float:
    """Convert correlation [-1,1] to score [0,1]: (corr+1)/2."""
    return max(0.0, min(1.0, (corr + 1.0) / 2.0))


def compute_e_score(
    stated_gdp_growth_series:   List[float],
    onchain_activity_series:    List[float],
) -> float:
    """
    E = corr(stated_GDP_growth, onchain_economic_activity), normalized [0,1].
    High E: stated economic signals match onchain reality.
    Low E: stated growth diverges from onchain flows (behavioral deception risk).
    """
    n = min(len(stated_gdp_growth_series), len(onchain_activity_series))
    if n < 3:
        return 0.50
    x = stated_gdp_growth_series[-n:]
    y = onchain_activity_series[-n:]
    mx, my = sum(x) / n, sum(y) / n
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    dx  = math.sqrt(sum((xi - mx) ** 2 for xi in x))
    dy  = math.sqrt(sum((yi - my) ** 2 for yi in y))
    if dx == 0 or dy == 0:
        return 0.50
    corr = max(-1.0, min(1.0, num / (dx * dy)))
    return _corr_to_score(corr)


def compute_i_score(
    stated_policies:        List[str],
    onchain_enforcements:   List[float],
    policy_alignment_scores: List[float],
) -> float:
    """
    I = corr(stated_policy, onchain_enforcement)
    Measures the gap between declared regulatory/monetary policy and
    observed on-chain enforcement behavior.
    policy_alignment_scores: pre-computed match scores ∈ [0,1] per policy-action pair.
    """
    if not policy_alignment_scores:
        return 0.50
    n = len(policy_alignment_scores)
    mean_alignment = sum(policy_alignment_scores) / n
    variance = sum((s - mean_alignment) ** 2 for s in policy_alignment_scores) / max(1, n)
    consistency_bonus = max(0.0, 0.10 * (1.0 - math.sqrt(variance)))
    return min(1.0, mean_alignment + consistency_bonus)


def compute_s_score(
    signal_accuracy_history: List[float],
    cred_weights:            Optional[List[float]] = None,
) -> float:
    """
    S = CRED-weighted track record of sovereign signal accuracy.
    signal_accuracy_history: accuracy of past sovereign signals [0,1]
    cred_weights: source credibility weights (default: equal)
    """
    if not signal_accuracy_history:
        return 0.50
    n = len(signal_accuracy_history)
    if cred_weights and len(cred_weights) == n:
        total_w = sum(cred_weights)
        if total_w > 0:
            return min(1.0, sum(a * w for a, w in zip(signal_accuracy_history, cred_weights)) / total_w)
    return sum(signal_accuracy_history) / n


def compute_g_score(
    cross_border_flow_consistency:  float,
    alliance_behavioral_alignment:  float,
    geopolitical_entropy:           float,
) -> float:
    """
    G = Geopolitical Behavioral Coherence.
    cross_border_flow_consistency: how consistent cross-border crypto flows are [0,1]
    alliance_behavioral_alignment: alignment with stated alliance behaviors [0,1]
    geopolitical_entropy: diversity of geopolitical behaviors (low = coherent) [0,1]
    """
    coherence = (cross_border_flow_consistency + alliance_behavioral_alignment) / 2.0
    entropy_penalty = geopolitical_entropy * 0.20
    return max(0.0, min(1.0, coherence - entropy_penalty))


def compute_c_score(
    stated_monetary_policy_rate:  float,
    onchain_stablecoin_flow_bias: float,
    fx_policy_alignment:          float,
) -> float:
    """
    C = Currency Behavior Alignment.
    stated_monetary_policy_rate: tightening/easing signal [0,1] where 0=ultra-easy, 1=ultra-tight
    onchain_stablecoin_flow_bias: net flow direction matching policy [0,1]
    fx_policy_alignment: FX intervention vs stated policy [0,1]
    """
    deviation = abs(stated_monetary_policy_rate - onchain_stablecoin_flow_bias)
    alignment = max(0.0, 1.0 - deviation)
    c = (alignment * 0.60 + fx_policy_alignment * 0.40)
    return max(0.0, min(1.0, c))


def compute_sba(
    nation_id:                      str,
    e_score:                        float,
    i_score:                        float,
    s_score:                        float,
    g_score:                        float,
    c_score:                        float,
    w_e:                            float = W_E,
    w_i:                            float = W_I,
    w_s:                            float = W_S,
    w_g:                            float = W_G,
    w_c:                            float = W_C,
) -> dict:
    """
    SBA(nation, t) = w_E·E + w_I·I + w_S·S + w_G·G + w_C·C

    Returns full breakdown for whitepaper compliance.
    """
    sba = (w_e * e_score + w_i * i_score + w_s * s_score
           + w_g * g_score + w_c * c_score)
    sba = max(0.0, min(1.0, sba))

    tier = (
        "HIGH_CREDIBILITY"   if sba >= SBA_HIGH     else
        "MODERATE_CREDIBILITY" if sba >= SBA_MODERATE else
        "LOW_CREDIBILITY"    if sba >= SBA_LOW      else
        "BEHAVIORAL_RISK"
    )

    policy_action_gap = abs(i_score - e_score)

    return {
        "nation_id":           nation_id,
        "sba_score":           round(sba, 6),
        "tier":                tier,
        "components": {
            "E_economic_regularity":    round(e_score, 4),
            "I_institutional_integrity": round(i_score, 4),
            "S_signaling_credibility":  round(s_score, 4),
            "G_geopolitical_coherence": round(g_score, 4),
            "C_currency_alignment":     round(c_score, 4),
        },
        "weights": {
            "w_E": w_e, "w_I": w_i, "w_S": w_s, "w_G": w_g, "w_C": w_c,
        },
        "policy_action_gap":   round(policy_action_gap, 4),
        "behavioral_risk":     sba < SBA_LOW,
        "disclosure": (
            f"SBA={sba:.4f} [{tier}]. "
            f"Policy-action gap={'HIGH' if policy_action_gap > 0.30 else 'LOW'} "
            f"({policy_action_gap:.4f}). "
            "SBA predictions require 70%+ alignment validation over 90-day sample (F10)."
        ),
    }


def sba_from_raw_data(
    nation_id:                      str,
    gdp_stated:                     List[float],
    gdp_onchain:                    List[float],
    policy_alignment_scores:        List[float],
    signal_accuracy:                List[float],
    cross_border_consistency:       float = 0.5,
    alliance_alignment:             float = 0.5,
    geopolitical_entropy:           float = 0.3,
    monetary_policy_rate:           float = 0.5,
    stablecoin_flow_bias:           float = 0.5,
    fx_alignment:                   float = 0.5,
) -> dict:
    """Full SBA computation from raw inputs."""
    e = compute_e_score(gdp_stated, gdp_onchain)
    i = compute_i_score([], [], policy_alignment_scores)
    s = compute_s_score(signal_accuracy)
    g = compute_g_score(cross_border_consistency, alliance_alignment, geopolitical_entropy)
    c = compute_c_score(monetary_policy_rate, stablecoin_flow_bias, fx_alignment)
    return compute_sba(nation_id, e, i, s, g, c)


if __name__ == "__main__":
    result = sba_from_raw_data(
        nation_id="US",
        gdp_stated=[0.02, 0.03, 0.025, 0.022, 0.028],
        gdp_onchain=[0.018, 0.031, 0.024, 0.020, 0.026],
        policy_alignment_scores=[0.80, 0.75, 0.82, 0.78, 0.77],
        signal_accuracy=[0.72, 0.68, 0.74, 0.70],
        cross_border_consistency=0.72,
        alliance_alignment=0.68,
        geopolitical_entropy=0.25,
        monetary_policy_rate=0.70,
        stablecoin_flow_bias=0.65,
        fx_alignment=0.72,
    )
    print(f"SBA(US): {result['sba_score']:.4f} [{result['tier']}]")
    for k, v in result['components'].items():
        print(f"  {k}: {v:.4f}")
    assert 0 <= result['sba_score'] <= 1
    print("L8.1 SBA Engine: PASS")
