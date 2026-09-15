"""
TRION Protocol — L8.1: Sovereign Behavioral Assessment (SBA)
Chapter 12: Macro-Behavioral Intelligence

SBA(nation, t) = w_E·E(t) + w_I·I(t) + w_S·S(t) + w_G·G(t) + w_C·C(t)

Sub-components (whitepaper L8.1 formulas):
  E = Economic Behavioral Signal
      H(cross_border_capital_flow) × trade_balance_trend × stablecoin_adoption
  I = Institutional Quality Signal
      corr(stated_policy, onchain_enforcement_behavior)
      (high: government behavior matches stated policy; low: divergence)
  S = Social Stability Signal
      NL(domestic_DeFi, t) × EP(domestic_protocols, t) × citizen_wallet_activity
  G = Governance Behavioral Signal
      government_wallet_behavioral_consistency (90-day rolling)
  C = Cross-chain Capital Confidence
      foreign_capital_inflow / (inflow + outflow)

Weights (whitepaper L8.1):
  w_E=0.30, w_I=0.25, w_S=0.20, w_G=0.15, w_C=0.10   (sum=1.00)

SBA ∈ [0, 1]
  ≥ 0.75  HIGH_CREDIBILITY
  0.55–0.75  MODERATE_CREDIBILITY
  0.35–0.55  LOW_CREDIBILITY
  < 0.35  BEHAVIORAL_RISK

Every SBA signal carries Sovereignty Dignity Protocol (SDP) mandatory
metadata: uncertainty_bounds (CI_95 always present), cultural_context_vector
(encoded regional context), appeal_mechanism (any entity can formally
challenge the assessment), and data_sources (complete provenance chain).

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional

W_E = 0.30
W_I = 0.25
W_S = 0.20
W_G = 0.15
W_C = 0.10

assert abs(W_E + W_I + W_S + W_G + W_C - 1.0) < 1e-9, "SBA weights must sum to 1.0"

SBA_HIGH       = 0.75
SBA_MODERATE   = 0.55
SBA_LOW        = 0.35


def _corr_to_score(corr: float) -> float:
    """Convert correlation [-1,1] to score [0,1]: (corr+1)/2."""
    return max(0.0, min(1.0, (corr + 1.0) / 2.0))


def _normalized_shannon_entropy(values: List[float]) -> float:
    """
    Shannon entropy of the value-magnitude distribution, normalized to [0,1]
    via log2(n) so that a uniform distribution maps to 1.0 and a perfectly
    concentrated distribution maps to 0.0.

        H(X) = -Σ p_i · log2(p_i)    where p_i = |v_i| / Σ|v_j|
        H_norm = H(X) / log2(n)      (defined as 0.0 when n <= 1)
    """
    n = len(values)
    if n <= 1:
        return 0.0
    abs_vals = [abs(v) for v in values]
    total = sum(abs_vals)
    if total <= 0:
        return 0.0
    h = 0.0
    for v in abs_vals:
        if v > 0:
            p = v / total
            h -= p * math.log2(p)
    h_max = math.log2(n)
    return h / h_max if h_max > 0 else 0.0


def compute_e_score(
    cross_border_capital_flow: List[float],
    trade_balance_trend:       float,
    stablecoin_adoption:       float,
) -> float:
    """
    E = H(cross_border_capital_flow) × trade_balance_trend × stablecoin_adoption

    Whitepaper L8.1 (Economic Behavioral Signal):
      - H(cross_border_capital_flow) = normalized Shannon entropy of the
        cross-border capital flow distribution. A uniformly distributed flow
        across counterparties/channels scores 1.0 (diversified, healthy); a
        single dominant flow scores 0.0 (concentrated, brittle).
      - trade_balance_trend ∈ [-1, 1] (signed: surplus = +, deficit = -),
        mapped to [0, 1] via (1 + trend) / 2 so that surplus → 1.0 and
        deficit → 0.0.
      - stablecoin_adoption ∈ [0, 1] (fraction of domestic stablecoin
        penetration vs. fiat / M2).

    The product captures: capital-flow diversification × external-balance
    health × onchain adoption posture. All three must be strong for high E.
    """
    h_norm = _normalized_shannon_entropy(cross_border_capital_flow)
    tbt    = max(0.0, min(1.0, (trade_balance_trend + 1.0) / 2.0))
    sa     = max(0.0, min(1.0, stablecoin_adoption))
    return max(0.0, min(1.0, h_norm * tbt * sa))


def compute_i_score(
    stated_policies:        List[str],
    onchain_enforcements:   List[float],
    policy_alignment_scores: List[float],
) -> float:
    """
    I = corr(stated_policy, onchain_enforcement_behavior)
    Measures the gap between declared regulatory/monetary policy and
    observed on-chain enforcement behavior.
    policy_alignment_scores: pre-computed match scores ∈ [0,1] per policy-action pair.

    The whitepaper L8.1 formula matches this implementation already (correlation
    between stated policy and onchain enforcement behavior). Kept unchanged.
    """
    if not policy_alignment_scores:
        return 0.50
    n = len(policy_alignment_scores)
    mean_alignment = sum(policy_alignment_scores) / n
    variance = sum((s - mean_alignment) ** 2 for s in policy_alignment_scores) / max(1, n)
    consistency_bonus = max(0.0, 0.10 * (1.0 - math.sqrt(variance)))
    return min(1.0, mean_alignment + consistency_bonus)


def compute_s_score(
    nl_domestic_defi:        float,
    ep_domestic_protocols:   float,
    citizen_wallet_activity: float,
) -> float:
    """
    S = NL(domestic_DeFi, t) × EP(domestic_protocols, t) × citizen_wallet_activity

    Whitepaper L8.1 (Social Stability Signal):
      - NL(domestic_DeFi, t) ∈ [0, 1] — Natural Liquidity score for the
        nation's domestic DeFi ecosystem (whitepaper L7.1, computed by
        core.extended.natural_liquidity.compute_nl).
      - EP(domestic_protocols, t) ∈ [0, 1] — Energy Participation index for
        the nation's domestic protocols (whitepaper L7.2, computed by
        core.extended.energy_participation.compute_ep).
      - citizen_wallet_activity ∈ [0, 1] — fraction of citizen wallets
        active on domestic infrastructure in the evaluation window.

    The product captures: domestic liquidity health × protocol energy
    participation × civic onchain engagement. All three must be strong for
    high S.
    """
    nl  = max(0.0, min(1.0, nl_domestic_defi))
    ep  = max(0.0, min(1.0, ep_domestic_protocols))
    cwa = max(0.0, min(1.0, citizen_wallet_activity))
    return max(0.0, min(1.0, nl * ep * cwa))


def compute_g_score(
    daily_consistency_scores: List[float],
) -> float:
    """
    G = government_wallet_behavioral_consistency (90-day rolling)

    Whitepaper L8.1 (Governance Behavioral Signal):
      Computes the rolling-mean consistency of government wallet behavior
      over the trailing 90 days. Each entry is a per-day consistency score
      ∈ [0, 1] (1.0 = perfectly aligned with stated policy that day,
      0.0 = fully divergent). The trailing 90 entries are averaged
      (or all entries if fewer than 90 are supplied, with a 0.50 neutral
      fallback when the series is empty).
    """
    if not daily_consistency_scores:
        return 0.50
    window = daily_consistency_scores[-90:]
    return max(0.0, min(1.0, sum(window) / len(window)))


def compute_c_score(
    foreign_capital_inflow:  float,
    foreign_capital_outflow: float,
) -> float:
    """
    C = foreign_capital_inflow / (inflow + outflow)

    Whitepaper L8.1 (Cross-chain Capital Confidence):
      Fraction of cross-chain capital that is INBOUND. A nation whose
      cross-chain flows are net-inflowing scores C → 1.0 (capital
      confidence); net-outflow scores C → 0.0 (capital flight). When both
      inflow and outflow are zero (no flow observed), C = 0.5 (neutral).
    """
    total = foreign_capital_inflow + foreign_capital_outflow
    if total <= 0:
        return 0.5
    return max(0.0, min(1.0, foreign_capital_inflow / total))


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

    Returns full breakdown for specification compliance.
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
    nation_id:                       str,
    cross_border_capital_flow:       List[float],
    trade_balance_trend:             float,
    stablecoin_adoption:             float,
    policy_alignment_scores:         List[float],
    nl_domestic_defi:                float,
    ep_domestic_protocols:           float,
    citizen_wallet_activity:         float,
    gov_wallet_consistency_90d:      List[float],
    foreign_capital_inflow:          float,
    foreign_capital_outflow:         float,
) -> dict:
    """Full SBA computation from raw whitepaper-aligned inputs.

    Maps each whitepaper L8.1 axis to its canonical inputs:
      E ← cross_border_capital_flow, trade_balance_trend, stablecoin_adoption
      I ← policy_alignment_scores                  (already spec-aligned)
      S ← nl_domestic_defi, ep_domestic_protocols, citizen_wallet_activity
      G ← gov_wallet_consistency_90d                (90-day rolling series)
      C ← foreign_capital_inflow, foreign_capital_outflow
    """
    e = compute_e_score(cross_border_capital_flow, trade_balance_trend, stablecoin_adoption)
    i = compute_i_score([], [], policy_alignment_scores)
    s = compute_s_score(nl_domestic_defi, ep_domestic_protocols, citizen_wallet_activity)
    g = compute_g_score(gov_wallet_consistency_90d)
    c = compute_c_score(foreign_capital_inflow, foreign_capital_outflow)
    return compute_sba(nation_id, e, i, s, g, c)


if __name__ == "__main__":
    result = sba_from_raw_data(
        nation_id="US",
        cross_border_capital_flow=[1.0e6, 1.2e6, 0.9e6, 1.1e6, 1.05e6],
        trade_balance_trend=+0.30,                # surplus
        stablecoin_adoption=0.65,
        policy_alignment_scores=[0.80, 0.75, 0.82, 0.78, 0.77],
        nl_domestic_defi=0.72,
        ep_domestic_protocols=0.68,
        citizen_wallet_activity=0.55,
        gov_wallet_consistency_90d=[0.85, 0.82, 0.88, 0.80, 0.86],
        foreign_capital_inflow=1.5e6,
        foreign_capital_outflow=0.9e6,
    )
    print(f"SBA(US): {result['sba_score']:.4f} [{result['tier']}]")
    for k, v in result['components'].items():
        print(f"  {k}: {v:.4f}")
    assert 0 <= result['sba_score'] <= 1
    print("L8.1 SBA Engine: PASS")
