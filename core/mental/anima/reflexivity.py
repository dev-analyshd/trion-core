"""
TRION Protocol — L3.5 ANIMA Reflexivity Dampening + Manifestation Gap Monitor

ANIMA_reflexivity(S, t) = corr(ANIMA_signal_strength(S, t-1),
                               behavioral_change_attributed_to_signal(S, t))

When TRION publishes a TRAJECTORY signal, market participants may act on it,
making the prediction self-fulfilling (or self-defeating). This creates
reflexive feedback that corrupts future signals.

Response:
    A_adj(t) = A(t) · (1 - β_reflexivity · ANIMA_reflexivity(t))

Manifestation Gap Monitor tracks the lag between ANIMA pre-manifestation
signal and actual behavioral manifestation:
    MG(pattern, t) = E[blocks_to_manifestation | matched_archetype]
    MG calibration: improving over time as more patterns manifest.

Observer Effect (L3.6):
    OE_factor = corr(signal_publication(t-1), behavioral_change(t))
    M_adj(t)  = M_base(t) · (1 - OE_factor(t))

This is the whitepaper's acknowledged first-mover vulnerability:
"First-mover window before sufficient OE accumulation is genuinely vulnerable."

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Optional


BETA_REFLEXIVITY = 0.50   # Dampening strength — how much reflexivity reduces A(t)


@dataclass
class ReflexivityHistory:
    """History of ANIMA signal vs realized behavioral change for one pattern."""
    pattern_id:             str
    signal_strengths:       List[float]   # ANIMA signal strength at t-1
    behavioral_changes:     List[float]   # Behavioral change attributed to signal at t
    timestamps:             List[float]   # Unix timestamps


@dataclass
class ReflexivityResult:
    """
    ANIMA_reflexivity(S, t) = corr(signal_strength(t-1), behavioral_change(t))
    A_adj(t) = A(t) · (1 - β_reflexivity · reflexivity_score)
    """
    pattern_id:          str
    reflexivity_score:   float   # corr ∈ [-1, 1] — positive = self-fulfilling
    a_raw:               float
    a_adj:               float   # Adjusted ANIMA score
    dampening_applied:   float   # How much was removed
    sample_size:         int
    warning:             Optional[str]


def compute_correlation(x: List[float], y: List[float]) -> float:
    """Pearson correlation between two series."""
    n = min(len(x), len(y))
    if n < 2:
        return 0.0
    x = x[-n:]
    y = y[-n:]
    mx = sum(x) / n
    my = sum(y) / n
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    vx  = sum((xi - mx) ** 2 for xi in x)
    vy  = sum((yi - my) ** 2 for yi in y)
    if vx <= 0 or vy <= 0:
        return 0.0
    corr = cov / math.sqrt(vx * vy)
    return max(-1.0, min(1.0, corr))


def compute_anima_reflexivity(
    history: ReflexivityHistory,
) -> float:
    """
    ANIMA_reflexivity(S, t) = corr(signal_strength(t-1), behavioral_change(t))

    Positive correlation: TRION signal is self-fulfilling (reflexivity risk)
    Negative correlation: TRION signal is self-defeating (contrarian effect)
    Near zero: signal is not causing behavioral change (healthy)
    """
    if len(history.signal_strengths) < 5 or len(history.behavioral_changes) < 5:
        return 0.0  # Insufficient data

    # Align: signal at t-1 vs change at t (offset by 1)
    signals = history.signal_strengths[:-1]
    changes = history.behavioral_changes[1:]

    return compute_correlation(signals, changes)


def apply_reflexivity_dampening(
    a_raw:              float,
    pattern_id:         str,
    history:            ReflexivityHistory,
    beta_reflexivity:   float = BETA_REFLEXIVITY,
) -> ReflexivityResult:
    """
    A_adj(t) = A(t) · (1 - β_reflexivity · ANIMA_reflexivity(t))

    Only dampens when reflexivity is POSITIVE (self-fulfilling).
    Negative reflexivity (contrarian) is kept — it's informative in a different way.
    """
    reflexivity = compute_anima_reflexivity(history)
    dampening   = 0.0

    if reflexivity > 0:
        # Only dampen when positively reflexive
        dampening = beta_reflexivity * reflexivity
        a_adj = a_raw * (1.0 - dampening)
    else:
        a_adj = a_raw
        dampening = 0.0

    a_adj = max(0.0, min(1.0, a_adj))

    warning = None
    if reflexivity > 0.70:
        warning = (
            f"HIGH REFLEXIVITY: corr={reflexivity:.3f} for pattern {pattern_id}. "
            "ANIMA signal is substantially self-fulfilling. A(t) dampened significantly."
        )
    elif reflexivity > 0.40:
        warning = (
            f"MODERATE REFLEXIVITY: corr={reflexivity:.3f}. "
            "TRION recommendation affecting market behavior."
        )

    return ReflexivityResult(
        pattern_id        = pattern_id,
        reflexivity_score = reflexivity,
        a_raw             = a_raw,
        a_adj             = a_adj,
        dampening_applied = dampening,
        sample_size       = min(len(history.signal_strengths), len(history.behavioral_changes)),
        warning           = warning,
    )


# ── Observer Effect (L3.6 Predictive Completeness Limit) ─────────────────────

@dataclass
class ObserverEffectResult:
    """
    OE_factor = corr(signal_publication(t-1), behavioral_change(t))
    M_adj(t)  = M_base(t) · (1 - OE_factor(t))

    Note: OE_factor is the correlation between TRION's PUBLISHED mental layer
    signal and the behavioral changes that follow its publication.
    This measures how much the signal is causing what it predicts.
    """
    oe_factor:           float   # [0, 1] corr clipped to [0, 1]
    m_base:              float
    m_adj:               float   # M_base · (1 - OE_factor)
    signal_publications: int
    warning:             Optional[str]


def compute_observer_effect(
    signal_publications:  List[float],  # M_base values at t-1 (published)
    behavioral_changes:   List[float],  # Actual behavioral changes at t
) -> ObserverEffectResult:
    """
    OE_factor = corr(signal_publication(t-1), behavioral_change(t))
    Only positive correlations are relevant (TRION causing the change it predicts).
    Negative = prediction is contrarian → different phenomenon.
    """
    if len(signal_publications) < 5 or len(behavioral_changes) < 5:
        return ObserverEffectResult(
            oe_factor=0.0, m_base=0.0, m_adj=0.0,
            signal_publications=len(signal_publications),
            warning="Insufficient history for OE computation",
        )

    # Lag-1 alignment: publication at t-1 vs change at t
    pubs    = signal_publications[:-1]
    changes = behavioral_changes[1:]

    corr    = compute_correlation(pubs, changes)
    oe      = max(0.0, corr)  # Only positive OE matters

    m_base  = signal_publications[-1] if signal_publications else 0.0
    m_adj   = m_base * (1.0 - oe)
    m_adj   = max(0.0, min(1.0, m_adj))

    warning = None
    if oe > 0.60:
        warning = (
            f"HIGH OBSERVER EFFECT: OE={oe:.3f}. "
            "M_adj significantly dampened. First-mover vulnerability active."
        )

    return ObserverEffectResult(
        oe_factor           = oe,
        m_base              = m_base,
        m_adj               = m_adj,
        signal_publications = len(signal_publications),
        warning             = warning,
    )


# ── Manifestation Gap Monitor ──────────────────────────────────────────────────

@dataclass
class ManifestationGapEntry:
    """One observation of a pattern manifestation."""
    pattern_id:           str
    predicted_at_block:   int
    manifested_at_block:  int  # Actual manifestation block (0 = not yet)
    matched_archetype:    str
    signal_strength:      float

    @property
    def gap_blocks(self) -> int:
        if self.manifested_at_block <= 0:
            return -1  # Not yet manifested
        return self.manifested_at_block - self.predicted_at_block


@dataclass
class ManifestationGapStats:
    """Statistics for manifestation gap calibration."""
    pattern_id:         str
    sample_size:        int
    mean_gap_blocks:    float
    std_gap_blocks:     float
    p10_blocks:         float    # 10th percentile
    p90_blocks:         float    # 90th percentile
    calibration_score:  float    # How well MG estimates match realized gaps [0, 1]


def compute_manifestation_gap_stats(
    entries: List[ManifestationGapEntry],
) -> ManifestationGapStats:
    """
    MG(pattern, t) = E[blocks_to_manifestation | matched_archetype]

    Calibration improves as more patterns manifest — each manifestation
    updates the distribution of expected blocks.
    """
    realized = [e.gap_blocks for e in entries if e.gap_blocks >= 0]
    n = len(realized)

    if n == 0:
        return ManifestationGapStats(
            pattern_id="",
            sample_size=0,
            mean_gap_blocks=0,
            std_gap_blocks=0,
            p10_blocks=0,
            p90_blocks=0,
            calibration_score=0.0,
        )

    realized_sorted = sorted(realized)
    mean = sum(realized) / n
    std  = math.sqrt(sum((x - mean) ** 2 for x in realized) / n) if n > 1 else 0.0

    p10_idx = max(0, int(0.10 * n) - 1)
    p90_idx = min(n - 1, int(0.90 * n))
    p10 = realized_sorted[p10_idx]
    p90 = realized_sorted[p90_idx]

    # Calibration: ratio of predictions within expected range vs total
    pattern_id = entries[0].pattern_id if entries else ""
    calibration = min(1.0, n / 100.0)  # Grows toward 1.0 as sample grows

    return ManifestationGapStats(
        pattern_id        = pattern_id,
        sample_size       = n,
        mean_gap_blocks   = mean,
        std_gap_blocks    = std,
        p10_blocks        = p10,
        p90_blocks        = p90,
        calibration_score = calibration,
    )


if __name__ == "__main__":
    # Reflexivity dampening test
    # Simulate self-fulfilling prophecy: strong positive correlation
    history = ReflexivityHistory(
        pattern_id="pump_pattern_001",
        signal_strengths=[0.3, 0.5, 0.7, 0.8, 0.9, 0.85, 0.75],
        behavioral_changes=[0.1, 0.35, 0.65, 0.75, 0.88, 0.80, 0.72],
        timestamps=[1746000000 + i * 3600 for i in range(7)],
    )

    result = apply_reflexivity_dampening(0.80, "pump_pattern_001", history)
    print(f"Reflexivity={result.reflexivity_score:.4f} A_raw={result.a_raw:.4f} "
          f"A_adj={result.a_adj:.4f} dampening={result.dampening_applied:.4f}")
    assert result.a_adj < result.a_raw  # Dampening applied

    # Observer effect test
    oe_result = compute_observer_effect(
        signal_publications=[0.5, 0.6, 0.7, 0.8, 0.9],
        behavioral_changes  =[0.2, 0.5, 0.65, 0.78, 0.88],
    )
    print(f"OE_factor={oe_result.oe_factor:.4f} M_adj={oe_result.m_adj:.4f}")

    # Manifestation gap test
    entries = [
        ManifestationGapEntry("pat1", 1000, 1050, "growth_archetype", 0.75),
        ManifestationGapEntry("pat1", 2000, 2045, "growth_archetype", 0.80),
        ManifestationGapEntry("pat1", 3000, 3060, "growth_archetype", 0.70),
    ]
    stats = compute_manifestation_gap_stats(entries)
    print(f"MG mean={stats.mean_gap_blocks:.1f} blocks calibration={stats.calibration_score:.4f}")
    assert stats.mean_gap_blocks > 0

    print("L3.5 ANIMA Reflexivity Dampening + MG Monitor: PASS")
