"""
TRION Protocol — L3.1: Mental Plane M(t)
M(t) = 1 - (PI_t / PI_baseline)
PI_t = current prediction interval width
PI_baseline = baseline from historical calibration

Observer Effect Correction:
M_adj(t) = M_base(t) · (1 - OE_factor(t))
OE_factor = corr(signal_publication(t-1), behavioral_change(t))
"""

import numpy as np
from typing import List
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
    margin = t_crit * std / np.sqrt(n)

    lower = mean - margin
    upper = mean + margin
    width = upper - lower

    return float(lower), float(upper), float(width)


def compute_m_score(
    recent_predictions:   List[float],
    baseline_predictions: List[float],
) -> float:
    _, _, pi_t        = compute_prediction_interval(recent_predictions)
    _, _, pi_baseline = compute_prediction_interval(baseline_predictions)

    if pi_baseline <= 0:
        return 0.5

    m = 1.0 - (pi_t / pi_baseline)
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
    return max(0.0, corr) if not np.isnan(corr) else 0.0


def compute_m_adj(m_base: float, oe_factor: float) -> float:
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
    print("PHASE 13 PASS — M(t) mental plane implemented")
