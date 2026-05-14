"""
TRION Protocol — L3.4 Source Credibility Evolution
Chapter 8.2: ANIMA Data Architecture

CRED(source, t) = CRED(source, t-1) · α_decay + verification_events · β_update

α_decay  = 0.99 per day  (credibility decays if not reinforced)
β_update = 0.10         (verification event boost)

Source credibility is earned through verified correct predictions over time.
It is never assigned by authority — only by demonstrated accuracy.

CRED ∈ [0, 1]
CRED_initial = 0.30 (bootstrap — no prior data)
CRED_max     = 1.00 (asymptotic)
CRED_min     = 0.00 (floor — cannot go negative)

Source types (from ANIMA data architecture):
- SEC_EDGAR filings (structured, high initial credibility)
- Patent applications (structured)
- Developer repository (partially verifiable)
- Academic preprints (peer review = verification event)
- News/media (lowest initial credibility — most verification required)
- Regulatory filings (jurisdiction-tagged)

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class SourceType(Enum):
    SEC_EDGAR             = "SEC_EDGAR"           # CRED_initial = 0.65
    REGULATORY_FILING     = "REGULATORY_FILING"   # CRED_initial = 0.60
    PATENT_APPLICATION    = "PATENT_APPLICATION"  # CRED_initial = 0.55
    ACADEMIC_PREPRINT     = "ACADEMIC_PREPRINT"   # CRED_initial = 0.45
    DEV_REPOSITORY        = "DEV_REPOSITORY"      # CRED_initial = 0.40
    TECHNICAL_FORUM       = "TECHNICAL_FORUM"     # CRED_initial = 0.30
    NEWS_MEDIA            = "NEWS_MEDIA"          # CRED_initial = 0.25
    SOCIAL_MEDIA          = "SOCIAL_MEDIA"        # CRED_initial = 0.15


# Initial credibility by source type
CRED_INITIAL: Dict[SourceType, float] = {
    SourceType.SEC_EDGAR:         0.65,
    SourceType.REGULATORY_FILING: 0.60,
    SourceType.PATENT_APPLICATION: 0.55,
    SourceType.ACADEMIC_PREPRINT: 0.45,
    SourceType.DEV_REPOSITORY:    0.40,
    SourceType.TECHNICAL_FORUM:   0.30,
    SourceType.NEWS_MEDIA:        0.25,
    SourceType.SOCIAL_MEDIA:      0.15,
}

# Verification event values (by event type)
VERIFICATION_VALUES: Dict[str, float] = {
    "correct_prediction":          0.10,  # Source predicted outcome correctly
    "peer_review_accepted":        0.15,  # Academic peer review acceptance
    "sec_filing_verified":         0.12,  # SEC filing cross-verified
    "onchain_corroborated":        0.08,  # Off-chain claim verified on-chain
    "wrong_prediction":           -0.20,  # Source predicted incorrectly
    "misinformation_detected":    -0.35,  # Source published known false info
    "manipulation_detected":      -0.50,  # Source used for coordinated manipulation
    "sybil_identified":           -0.80,  # Source is a Sybil account
}

ALPHA_DECAY   = 0.99   # Per-day credibility decay
BETA_UPDATE   = 1.00   # Multiplier for verification event values
CRED_MIN      = 0.00
CRED_MAX      = 1.00


@dataclass
class SourceCredibility:
    """State of a single source's credibility at time t."""
    source_id:         str
    source_type:       SourceType
    cred:              float               # CRED(source, t)
    last_updated:      float               # Unix timestamp
    verification_count: int
    correct_count:     int
    wrong_count:       int
    manipulation_flag: bool
    jurisdiction:      Optional[str]       # For REGULATORY_FILING sources
    history:           List[float] = field(default_factory=list)


def initialize_source(
    source_id:    str,
    source_type:  SourceType,
    timestamp:    float,
    jurisdiction: Optional[str] = None,
) -> SourceCredibility:
    """Bootstrap a new source with type-appropriate initial credibility."""
    initial = CRED_INITIAL.get(source_type, 0.30)
    return SourceCredibility(
        source_id          = source_id,
        source_type        = source_type,
        cred               = initial,
        last_updated       = timestamp,
        verification_count = 0,
        correct_count      = 0,
        wrong_count        = 0,
        manipulation_flag  = False,
        jurisdiction       = jurisdiction,
        history            = [initial],
    )


def update_credibility(
    source:             SourceCredibility,
    current_timestamp:  float,
    verification_type:  str,
    multiplier:         float = 1.0,
) -> SourceCredibility:
    """
    CRED(source, t) = CRED(source, t-1) · α_decay^Δdays + verification · β_update

    Applies time-based decay first, then verification event update.
    """
    # Time decay: α^days elapsed
    days_elapsed = (current_timestamp - source.last_updated) / 86400.0
    decayed = source.cred * (ALPHA_DECAY ** days_elapsed)

    # Verification event
    event_value = VERIFICATION_VALUES.get(verification_type, 0.0) * multiplier
    new_cred = decayed + event_value * BETA_UPDATE

    # Clamp to [0, 1]
    new_cred = max(CRED_MIN, min(CRED_MAX, new_cred))

    # Track statistics
    new_correct = source.correct_count + (1 if "correct" in verification_type else 0)
    new_wrong   = source.wrong_count   + (1 if "wrong" in verification_type or "misinformation" in verification_type else 0)
    manip_flag  = source.manipulation_flag or (
        "manipulation" in verification_type or "sybil" in verification_type
    )

    updated = SourceCredibility(
        source_id          = source.source_id,
        source_type        = source.source_type,
        cred               = new_cred,
        last_updated       = current_timestamp,
        verification_count = source.verification_count + 1,
        correct_count      = new_correct,
        wrong_count        = new_wrong,
        manipulation_flag  = manip_flag,
        jurisdiction       = source.jurisdiction,
        history            = source.history + [new_cred],
    )
    return updated


def apply_time_decay_only(
    source:             SourceCredibility,
    current_timestamp:  float,
) -> SourceCredibility:
    """Apply only time decay — no verification event. Used for daily updates."""
    days_elapsed = (current_timestamp - source.last_updated) / 86400.0
    new_cred = max(CRED_MIN, source.cred * (ALPHA_DECAY ** days_elapsed))
    return SourceCredibility(
        source_id          = source.source_id,
        source_type        = source.source_type,
        cred               = new_cred,
        last_updated       = current_timestamp,
        verification_count = source.verification_count,
        correct_count      = source.correct_count,
        wrong_count        = source.wrong_count,
        manipulation_flag  = source.manipulation_flag,
        jurisdiction       = source.jurisdiction,
        history            = source.history + [new_cred],
    )


def credibility_weighted_signal(
    signals:    List[float],
    sources:    List[SourceCredibility],
) -> float:
    """
    Credibility-weighted aggregate of ANIMA source signals.
    signal_agg = Σ_s CRED(s,t) · signal_s / Σ_s CRED(s,t)
    Used for CA (Cross-Source Agreement) in ANIMA.
    """
    if not signals or not sources or len(signals) != len(sources):
        return 0.0

    total_weight = sum(s.cred for s in sources)
    if total_weight <= 0:
        return sum(signals) / len(signals)

    weighted_sum = sum(sig * src.cred for sig, src in zip(signals, sources))
    return weighted_sum / total_weight


def compute_cross_source_agreement(
    signals: List[float],
    sources: List[SourceCredibility],
) -> float:
    """
    CA (Cross-Source Agreement) = 1 - credibility-weighted standard deviation

    High agreement (low std) → CA near 1.0
    High disagreement (high std) → CA near 0.0
    """
    if not signals or not sources:
        return 0.5

    weighted_mean = credibility_weighted_signal(signals, sources)
    total_weight  = sum(s.cred for s in sources)

    if total_weight <= 0:
        return 0.5

    weighted_var = sum(
        src.cred * (sig - weighted_mean) ** 2
        for sig, src in zip(signals, sources)
    ) / total_weight

    weighted_std = weighted_var ** 0.5

    # Normalize: std of 0 → CA=1.0, std of 0.5 → CA≈0.0
    ca = max(0.0, 1.0 - weighted_std * 4.0)
    return min(1.0, ca)


if __name__ == "__main__":
    import time
    now = time.time()

    # Create an SEC EDGAR source
    sec_source = initialize_source("sec_edgar_001", SourceType.SEC_EDGAR, now)
    print(f"Initial CRED: {sec_source.cred:.4f}")
    assert sec_source.cred == 0.65

    # Correct prediction
    updated = update_credibility(sec_source, now + 86400 * 30, "correct_prediction")
    print(f"After 30d + correct: {updated.cred:.4f}")

    # Apply decay only
    decayed = apply_time_decay_only(sec_source, now + 86400 * 90)
    print(f"After 90d decay only: {decayed.cred:.4f}")
    assert decayed.cred < sec_source.cred

    # Social media with manipulation
    social = initialize_source("twitter_bot", SourceType.SOCIAL_MEDIA, now)
    manipulated = update_credibility(social, now + 3600, "manipulation_detected")
    print(f"Social media manipulation: CRED={manipulated.cred:.4f} flag={manipulated.manipulation_flag}")
    assert manipulated.cred < 0.15
    assert manipulated.manipulation_flag

    # Cross-source agreement
    signals = [0.72, 0.70, 0.68, 0.74, 0.30]  # 4 agree, 1 outlier
    sources = [
        initialize_source(f"s{i}", SourceType.NEWS_MEDIA, now) for i in range(4)
    ] + [initialize_source("outlier", SourceType.SOCIAL_MEDIA, now)]
    ca = compute_cross_source_agreement(signals, sources)
    print(f"Cross-source agreement (outlier present): CA={ca:.4f}")

    print("L3.4 Source Credibility Evolution: PASS")
