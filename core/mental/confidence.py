"""
TRION Protocol — L3.1: Mental Plane M(t)

SPECIFICATION (L3_mental_anima.md §L3.1):
    M(t) = (1 - eta * O(t)) * (1 - gamma * PCL(t)) * B(t)

Where:
    O(t)     = observer effect magnitude  (L3.2; |corr(signal_pub, behavior_change)|)
    PCL(t)   = predictive completeness limit (L3.6; H(future) / (H(present)+H(future)))
    B(t)     = baseline empirical confidence from L1/L2 (archetype similarity,
                prediction-interval ratio, or other empirical prior).
    eta      = observer sensitivity (default 0.5)
    gamma    = predictive-debt sensitivity (default 0.3)

The original PI-based form `M = 1 - (PI_t / PI_baseline)` is preserved as a
legacy / backward-compatible derivation of B(t) for conformal-predictor callers.
"""

import numpy as np
from typing import List, Optional
from scipy import stats as scipy_stats


def compute_prediction_interval(
    predictions: List[float],
    alpha: float = 0.05
) -> tuple:
    if len(predictions) < 5:
        if predictions:
            center = np.mean(predictions)
            return center - 0.5, center + 0.5, 1.0
        return 0.0, 1.0, 1.0

    arr  = np.array(predictions)
    mean = float(np.mean(arr))
    std  = float(np.std(arr))
    n    = len(arr)

    t_crit = scipy_stats.t.ppf(1 - alpha/2, df=n-1)
    margin = t_crit * std * np.sqrt(1 + 1.0 / n)

    lower = mean - margin
    upper = mean + margin
    width = upper - lower

    return float(lower), float(upper), float(width)


def compute_b_baseline_from_pi(
    recent_predictions:   List[float],
    baseline_predictions: List[float],
) -> float:
    """Derive baseline empirical confidence B(t) from the conformal
    prediction-interval ratio:

        B(t) = 1 - (PI_t / PI_baseline)

    This is the legacy L3.1 derivation (kept for backward compatibility with
    the conformal-predictor tests). The spec L3.1 formula composes this B(t)
    with the observer-effect (O) and predictive-completeness-limit (PCL)
    dampening factors — see `compute_m_score`.

    Returns 0.5 (neutral prior) when the baseline PI is non-positive.
    """
    _, _, pi_t        = compute_prediction_interval(recent_predictions)
    _, _, pi_baseline = compute_prediction_interval(baseline_predictions)

    if pi_baseline <= 0:
        return 0.5

    b = 1.0 - (pi_t / pi_baseline)
    return max(0.0, min(1.0, b))


def compute_m_score(
    recent_predictions:   Optional[List[float]] = None,
    baseline_predictions: Optional[List[float]] = None,
    *,
    o_t:   Optional[float] = None,
    pcl_t: Optional[float] = None,
    b_t:   Optional[float] = None,
    eta:   float = 0.5,
    gamma: float = 0.3,
) -> float:
    """L3.1 Mental Confidence M(t) — spec-compliant.

    SPECIFICATION (spec/L3_mental_anima.md §L3.1):

        M(t) = (1 - eta * O(t)) * (1 - gamma * PCL(t)) * B(t)

    Parameters (spec form):
        o_t    — observer effect magnitude  ∈ [0, 1]   (L3.2)
        pcl_t  — predictive completeness limit ∈ [0, 1) (L3.6)
        b_t    — baseline empirical confidence  ∈ [0, 1] (L1/L2)
        eta    — observer sensitivity            (default 0.5 per spec)
        gamma  — predictive-debt sensitivity     (default 0.3 per spec)

    Legacy / backward-compatibility mode:
        If `b_t` is None and `recent_predictions` + `baseline_predictions`
        are supplied, B(t) is derived from the conformal prediction-interval
        ratio (`compute_b_baseline_from_pi`), and O(t)=PCL(t)=0 (no
        observer-effect or predictive-debt dampening available from a
        prediction list alone).  This preserves the old contract used by
        `tests/unit/trion_protocol/test_conformal_predictor.py`,
        `tests/unit/test_all_planes.py`, and `tests/master_formula_verification.py`.
    """
    # ── Spec form: caller supplies O(t), PCL(t), B(t) directly ───────────────
    if b_t is not None:
        O   = 0.0 if o_t   is None else max(0.0, min(1.0, float(o_t)))
        PCL = 0.0 if pcl_t is None else max(0.0, min(0.9999, float(pcl_t)))
        B   = max(0.0, min(1.0, float(b_t)))
        m = (1.0 - eta * O) * (1.0 - gamma * PCL) * B
        return max(0.0, min(1.0, m))

    # ── Legacy conformal form: derive B(t) from prediction lists ─────────────
    recent   = recent_predictions or []
    baseline = baseline_predictions or []
    B = compute_b_baseline_from_pi(recent, baseline)
    m = B
    return max(0.0, min(1.0, m))


def compute_observer_effect(
    signal_strengths:   List[float],
    behavioral_changes: List[float],
) -> float:
    if len(signal_strengths) < 3 or len(behavioral_changes) < 3:
        return 0.0

    min_len = min(len(signal_strengths), len(behavioral_changes))
    s = np.array(signal_strengths[-min_len:])
    b = np.array(behavioral_changes[-min_len:])

    if s.std() == 0 or b.std() == 0:
        return 0.0

    corr = float(np.corrcoef(s, b)[0, 1])
    # Use abs(corr): both positive and negative correlations indicate observer effect.
    # A negative correlation (inverse response to signal publication) is still reflexivity.
    return abs(corr) if not np.isnan(corr) else 0.0


def compute_m_adj(m_base: float, oe_factor: float) -> float:
    """Legacy dampening helper: M_adj(t) = M(t) · (1 - OE_factor).

    Equivalent to the spec form `M(t) = (1 - eta·O(t))·B(t)` with eta=1.0
    and PCL=0.  Preserved for callers that apply observer-effect dampening
    as a post-hoc multiplier (e.g. ANIMA runtime).
    """
    return max(0.0, m_base * (1.0 - oe_factor))


if __name__ == "__main__":
    np.random.seed(42)

    baseline     = list(np.random.normal(0.5, 0.3, 100))
    recent_good  = list(np.random.normal(0.72, 0.05, 50))
    recent_poor  = list(np.random.normal(0.50, 0.40, 50))

    m_good = compute_m_score(recent_good, baseline)
    m_poor = compute_m_score(recent_poor, baseline)

    signals = list(np.random.normal(0.7, 0.1, 50))
    changes = [s * 0.8 + np.random.normal(0, 0.05) for s in signals]
    oe      = compute_observer_effect(signals, changes)
    m_adj   = compute_m_adj(m_good, oe)

    print(f"M (high confidence):  {m_good:.4f}")
    print(f"M (low confidence):   {m_poor:.4f}")
    print(f"Observer Effect:      {oe:.4f}")
    print(f"M_adj:                {m_adj:.4f}")
    assert m_good > m_poor, "Confidence ordering wrong"

    # ── Spec form ────────────────────────────────────────────────────────────
    # M(t) = (1 - eta·O(t)) · (1 - gamma·PCL(t)) · B(t)
    m_spec = compute_m_score(o_t=0.20, pcl_t=0.10, b_t=m_good, eta=0.5, gamma=0.3)
    # Sanity: dampening by O and PCL must reduce M below the un-dampened B.
    assert 0.0 <= m_spec <= m_good, "Spec M(t) must be ≤ B(t)"
    print(f"M (spec form):        {m_spec:.4f}  "
          f"= (1-0.5·0.20)·(1-0.3·0.10)·{m_good:.4f}")
    print("PHASE 13 PASS — M(t) mental plane implemented (spec + legacy forms)")
