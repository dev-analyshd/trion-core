"""
TRION Protocol — L2.1: Manipulation Fingerprint (MF) Detector
Seven manipulation patterns:
1. ORACLE_ATTACK_ATTEMPT   (MF=1.0 immediate)
2. WASH_TRADING            (MF=0.25–0.95)
3. SYBIL_LIQUIDITY         (MF=0.40–0.80)
4. GOVERNANCE_CAPTURE      (MF=0.60–1.0)
5. MEV_EXTRACTION          (MF=0.20–0.70)
6. COORDINATED_PUMP        (MF=0.50–1.0)
7. FAKE_VOLUME             (MF=0.30–0.85)
"""

from dataclasses import dataclass, field
from typing import List, Optional
import math


@dataclass
class MFResult:
    pattern_type: str
    detected:     bool
    mf_score:     float         # 0–1 (1 = full manipulation)
    confidence:   float         # detection confidence
    description:  str
    evidence:     dict = field(default_factory=dict)


def detect_oracle_attack(
    spot_deviation_pct: float,   # price deviation from TWAP
    blocks_since_swap: int,       # blocks since suspicious large swap
    deviation_threshold: float = 0.15,
    block_window: int = 10,
) -> MFResult:
    """
    ORACLE_ATTACK_ATTEMPT: triggered by spot price deviation from TWAP.
    Flash loan oracle attacks deviate > 15% within 10 blocks.
    MF = 1.0 (immediate maximum — oracle attack = automatic SILENCE).
    """
    triggered = (
        spot_deviation_pct > deviation_threshold and
        blocks_since_swap <= block_window
    )
    if triggered:
        return MFResult(
            pattern_type="ORACLE_ATTACK_ATTEMPT",
            detected=True,
            mf_score=1.0,
            confidence=0.98,
            description=(
                f"Oracle attack signature: spot deviated {spot_deviation_pct:.1%} "
                f"from TWAP within {blocks_since_swap} blocks. Immediate SILENCE."
            ),
            evidence={
                "spot_deviation_pct": spot_deviation_pct,
                "blocks_since_swap": blocks_since_swap,
                "threshold_pct": deviation_threshold,
            }
        )
    return MFResult(
        pattern_type="ORACLE_ATTACK_ATTEMPT", detected=False,
        mf_score=0.0, confidence=0.95,
        description="No oracle attack pattern detected.",
        evidence={"spot_deviation_pct": spot_deviation_pct}
    )


def detect_wash_trading(
    self_trade_ratio: float,    # cyclic_flow_ratio — fraction of volume that is circular
    unique_counterparties: int, # unique addresses in trade set
    ratio_threshold: float = 0.60,
    min_counterparties: int = 5,
) -> MFResult:
    """
    WASH_TRADING (Whitepaper L2.1 TYPE 1):
    MF = 0.70 × cyclic_flow_ratio
    Threshold: cyclic_flow_ratio > 0.60 AND counterparty_count < 5
    """
    detected = (
        self_trade_ratio > ratio_threshold and
        unique_counterparties < min_counterparties
    )
    if detected:
        mf_score = min(0.95, 0.70 * self_trade_ratio)
        return MFResult(
            pattern_type="WASH_TRADING",
            detected=True,
            mf_score=mf_score,
            confidence=0.85,
            description=(
                f"Wash trading: cyclic_flow_ratio={self_trade_ratio:.2f} > 0.60 "
                f"AND counterparties={unique_counterparties} < 5. "
                f"MF = 0.70 × {self_trade_ratio:.2f} = {mf_score:.4f}."
            ),
            evidence={
                "cyclic_flow_ratio": self_trade_ratio,
                "unique_counterparties": unique_counterparties,
                "formula": "0.70 × cyclic_flow_ratio",
            }
        )
    return MFResult(
        pattern_type="WASH_TRADING", detected=False,
        mf_score=0.0, confidence=0.90,
        description=f"No wash trading: ratio={self_trade_ratio:.2f} (need >0.60 AND counterparties={unique_counterparties} < 5).",
        evidence={"cyclic_flow_ratio": self_trade_ratio, "unique_counterparties": unique_counterparties}
    )


def detect_sybil_liquidity(
    top_k_lp_share: float,      # funding_concentration — top-K LP share
    lp_beo_count: int,          # unique BEO identities (not just addresses)
    k: int = 5,
    share_threshold: float = 0.80,
) -> MFResult:
    """
    SYBIL_LIQUIDITY (Whitepaper L2.1 TYPE 4):
    MF = 0.60 × funding_concentration
    Threshold: top_k_lp_share > 0.80 AND lp_beo_count < 20
    """
    funding_concentration = top_k_lp_share
    detected = top_k_lp_share > share_threshold and lp_beo_count < 20
    if detected:
        mf_score = min(0.80, 0.60 * funding_concentration)
        return MFResult(
            pattern_type="SYBIL_LIQUIDITY",
            detected=True,
            mf_score=mf_score,
            confidence=0.80,
            description=(
                f"Sybil liquidity: top-{k} LPs hold {top_k_lp_share:.1%} "
                f"with only {lp_beo_count} distinct BEO identities. "
                f"MF = 0.60 × {funding_concentration:.2f} = {mf_score:.4f}."
            ),
            evidence={
                "top_k_lp_share": top_k_lp_share,
                "lp_beo_count": lp_beo_count,
                "funding_concentration": funding_concentration,
                "formula": "0.60 × funding_concentration",
            }
        )
    return MFResult(
        pattern_type="SYBIL_LIQUIDITY", detected=False,
        mf_score=0.0, confidence=0.85,
        description="No sybil liquidity pattern.",
        evidence={"top_k_lp_share": top_k_lp_share, "lp_beo_count": lp_beo_count}
    )


def detect_governance_capture(
    vote_hhi: float,             # Herfindahl-Hirschman Index of vote distribution (0–10000)
    proposal_age_hours: float,   # time between proposal and vote execution
    hhi_threshold: float = 2500,
    min_proposal_age_hours: float = 48.0,
) -> MFResult:
    """
    GOVERNANCE_CAPTURE (Whitepaper L2.1 TYPE 5):
    MF = 0.50 × (vote_HHI - 2500) / 7500
    Threshold: vote_HHI > 2500 AND proposal_age < 48h
    Beanstalk scenario: same-block governance execution (HHI → 10000).
    """
    detected = vote_hhi > hhi_threshold and proposal_age_hours < min_proposal_age_hours
    if detected:
        mf_score = min(1.0, max(0.0, 0.50 * (vote_hhi - 2500) / 7500))
        return MFResult(
            pattern_type="GOVERNANCE_CAPTURE",
            detected=True,
            mf_score=mf_score,
            confidence=0.92,
            description=(
                f"Governance capture: HHI={vote_hhi:.0f} > 2500, "
                f"proposal age={proposal_age_hours:.1f}h < 48h. "
                f"MF = 0.50 × ({vote_hhi:.0f} - 2500) / 7500 = {mf_score:.4f}."
            ),
            evidence={
                "vote_hhi": vote_hhi,
                "proposal_age_hours": proposal_age_hours,
                "formula": "0.50 × (vote_HHI - 2500) / 7500",
            }
        )
    return MFResult(
        pattern_type="GOVERNANCE_CAPTURE", detected=False,
        mf_score=0.0, confidence=0.88,
        description=f"No governance capture: HHI={vote_hhi:.0f} (need >2500) age={proposal_age_hours:.1f}h.",
        evidence={"vote_hhi": vote_hhi}
    )


def detect_mev_extraction(
    mev_ratio_30d: float,     # fraction of value extracted by MEV bots
    sandwich_count: int,      # number of sandwich attacks detected
    threshold_ratio: float = 0.005,
    max_ratio: float = 0.05,
) -> MFResult:
    """
    MEV_EXTRACTION_SUSTAINED (Whitepaper L2.1 TYPE 6):
    MF = 0.40 × (mev_rate - 0.005) / 0.045
    Threshold: mev_rate > 0.005 (0.5% MEV extraction rate)
    """
    detected = mev_ratio_30d > threshold_ratio or (sandwich_count > 10 and mev_ratio_30d > 0)
    if detected:
        mf_score = min(0.40, max(0.0, 0.40 * (mev_ratio_30d - 0.005) / 0.045))
        return MFResult(
            pattern_type="MEV_EXTRACTION_SUSTAINED",
            detected=True,
            mf_score=mf_score,
            confidence=0.75,
            description=(
                f"MEV extraction: rate={mev_ratio_30d:.4f} > 0.005, "
                f"sandwich_count={sandwich_count}. "
                f"MF = 0.40 × ({mev_ratio_30d:.4f} - 0.005) / 0.045 = {mf_score:.4f}."
            ),
            evidence={
                "mev_rate_30d": mev_ratio_30d,
                "sandwich_count": sandwich_count,
                "formula": "0.40 × (mev_rate - 0.005) / 0.045",
            }
        )
    return MFResult(
        pattern_type="MEV_EXTRACTION_SUSTAINED", detected=False,
        mf_score=0.0, confidence=0.80,
        description=f"MEV rate {mev_ratio_30d:.4f} within normal range (< 0.005).",
        evidence={"mev_rate_30d": mev_ratio_30d}
    )


def detect_coordinated_pump(
    sync_buy_ratios: List[float],  # synchronized buy ratios across wallets
    entity_count: int,
    sync_threshold: float = 0.85,
    min_entities: int = 3,
) -> MFResult:
    """
    COORDINATED_PUMP (Whitepaper L2.1 TYPE 2):
    MF = 0.85 × sync_buy_ratio
    Threshold: high_sync_entities >= 3 AND avg_sync_buy_ratio > 0.85
    Mango Markets scenario: correlated buying across 4 wallets.
    """
    high_sync = sum(1 for r in sync_buy_ratios if r > sync_threshold)
    detected = high_sync >= min_entities and entity_count >= min_entities
    if detected:
        high_sync_ratios = [r for r in sync_buy_ratios if r > sync_threshold]
        avg_sync = sum(high_sync_ratios) / len(high_sync_ratios) if high_sync_ratios else 0
        mf_score = min(1.0, 0.85 * avg_sync)
        return MFResult(
            pattern_type="COORDINATED_PUMP",
            detected=True,
            mf_score=mf_score,
            confidence=0.88,
            description=(
                f"Coordinated pump: {high_sync}/{entity_count} entities "
                f"with sync_buy_ratio={avg_sync:.3f}. "
                f"MF = 0.85 × {avg_sync:.3f} = {mf_score:.4f}."
            ),
            evidence={
                "high_sync_entities": high_sync,
                "total_entities": entity_count,
                "avg_sync_ratio": avg_sync,
                "formula": "0.85 × sync_buy_ratio",
            }
        )
    return MFResult(
        pattern_type="COORDINATED_PUMP", detected=False,
        mf_score=0.0, confidence=0.85,
        description=f"No coordinated pump: {high_sync}/{entity_count} synced (need ≥{min_entities}).",
        evidence={"entity_count": entity_count}
    )


def detect_fake_volume(
    round_trip_ratio: float,    # fraction of volume that returns to origin (proxy for vol_entropy)
    zero_sum_trades: int,       # trades with zero net value change
    volume_spike_ratio: float,  # volume relative to 90d average
    vol_entropy: float = 0.0,   # Shannon entropy of volume distribution
    h_baseline: float = 1.0,   # baseline entropy (max observed)
    threshold_ratio: float = 0.40,
) -> MFResult:
    """
    FAKE_VOLUME_PROTOCOL (Whitepaper L2.1 TYPE 7):
    MF = 0.80 × (1 - vol_entropy / H_baseline)
    Threshold: (1 - vol_entropy/H_baseline) > 0.40 OR volume_spike > 5x
    When vol_entropy not available, use round_trip_ratio as proxy.
    """
    if h_baseline > 0 and vol_entropy > 0:
        entropy_deficit = max(0.0, 1.0 - vol_entropy / h_baseline)
    else:
        entropy_deficit = round_trip_ratio

    detected = (
        entropy_deficit > threshold_ratio or
        (volume_spike_ratio > 5.0 and round_trip_ratio > 0.20)
    )
    if detected:
        mf_score = min(0.85, 0.80 * entropy_deficit)
        return MFResult(
            pattern_type="FAKE_VOLUME_PROTOCOL",
            detected=True,
            mf_score=mf_score,
            confidence=0.82,
            description=(
                f"Fake volume: entropy_deficit={entropy_deficit:.3f} "
                f"(vol_entropy={vol_entropy:.3f}/H_baseline={h_baseline:.3f}), "
                f"spike={volume_spike_ratio:.1f}x. "
                f"MF = 0.80 × {entropy_deficit:.3f} = {mf_score:.4f}."
            ),
            evidence={
                "entropy_deficit": entropy_deficit,
                "vol_entropy": vol_entropy,
                "h_baseline": h_baseline,
                "round_trip_ratio": round_trip_ratio,
                "volume_spike_ratio": volume_spike_ratio,
                "formula": "0.80 × (1 - vol_entropy / H_baseline)",
            }
        )
    return MFResult(
        pattern_type="FAKE_VOLUME_PROTOCOL", detected=False,
        mf_score=0.0, confidence=0.80,
        description=f"No fake volume: entropy_deficit={entropy_deficit:.3f} < 0.40.",
        evidence={"entropy_deficit": entropy_deficit, "round_trip_ratio": round_trip_ratio}
    )


def compute_mf_score(results: List[MFResult]) -> dict:
    """
    Aggregate MF score from multiple pattern detectors.
    ORACLE_ATTACK_ATTEMPT = immediate 1.0 (hard rule).
    Otherwise: max of detected scores.
    """
    detected = [r for r in results if r.detected]

    # Oracle attack: immediate maximum
    oracle = [r for r in detected if r.pattern_type == "ORACLE_ATTACK_ATTEMPT"]
    if oracle:
        return {
            "mf_score": 1.0,
            "primary_type": "ORACLE_ATTACK_ATTEMPT",
            "detected_types": [r.pattern_type for r in detected],
            "components": {r.pattern_type: r.mf_score for r in results},
            "action": "IMMEDIATE_SILENCE",
        }

    if not detected:
        return {
            "mf_score": 0.0,
            "primary_type": None,
            "detected_types": [],
            "components": {r.pattern_type: r.mf_score for r in results},
            "action": "PASS",
        }

    max_result = max(detected, key=lambda r: r.mf_score)
    return {
        "mf_score": max_result.mf_score,
        "primary_type": max_result.pattern_type,
        "detected_types": [r.pattern_type for r in detected],
        "components": {r.pattern_type: r.mf_score for r in results},
        "action": "DISCOUNT_PHI" if max_result.mf_score < 0.70 else "SILENCE",
    }


def apply_mf_discount(phi_raw: float, mf_score: float) -> float:
    """Φ_adj = Φ_raw × (1 - MF_score)"""
    return max(0.0, phi_raw * (1.0 - mf_score))


if __name__ == "__main__":
    r1 = detect_oracle_attack(0.22, 5)
    r2 = detect_wash_trading(0.75, 3)
    r3 = detect_governance_capture(5500, 10)
    r4 = detect_wash_trading(0.10, 100)

    assert r1.detected and r1.mf_score == 1.0, "Oracle attack should give MF=1.0"
    assert r2.detected, "High wash trading should be detected"
    assert r3.detected, "Governance capture should be detected"
    assert not r4.detected, "Low wash trading should not trigger"

    final = compute_mf_score([r1, r2, r3, r4])
    assert final['mf_score'] == 1.0, "Oracle attack collapses to 1.0"

    phi_adj = apply_mf_discount(0.80, 1.0)
    assert phi_adj == 0.0, "Oracle attack collapses phi"

    print(f"Oracle attack MF:       {r1.mf_score}")
    print(f"Wash trading MF:        {r2.mf_score:.4f}")
    print(f"Governance capture MF:  {r3.mf_score:.4f}")
    print(f"Aggregate MF:           {final['mf_score']}")
    print(f"Φ_adj after oracle:     {phi_adj}")
    print("PHASE 11 PASS — MF detector verified")
