"""
Tests for src/planes/mental/m_engine.py — TRION L3 M(t).
Actual module imported by api/app.py at line 267.
M(t) = 1 - (PI_t / PI_baseline) — prediction interval reduction score.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.planes.mental.m_engine import (
    compute_m_score, compute_prediction_interval, compute_observer_effect,
)


def test_prediction_interval_with_single_sample():
    lo, hi, width = compute_prediction_interval([0.5])
    assert lo <= hi, "PI must be ordered"
    assert width > 0
    print(f"[PASS] PI with 1 sample: [{lo:.3f}, {hi:.3f}], width={width:.3f}")


def test_prediction_interval_narrows_with_consistent_data():
    consistent = [0.70, 0.71, 0.70, 0.71, 0.70, 0.71, 0.70, 0.71, 0.70, 0.71]
    noisy      = [0.0, 0.5, 1.0, 0.2, 0.8, 0.1, 0.9, 0.3, 0.7, 0.4]
    _, _, w_consistent = compute_prediction_interval(consistent)
    _, _, w_noisy      = compute_prediction_interval(noisy)
    assert w_consistent < w_noisy, "Consistent data must give narrower PI"
    print(f"[PASS] PI width: consistent={w_consistent:.4f} < noisy={w_noisy:.4f}")


def test_m_score_in_unit_interval():
    recent   = [0.70, 0.71, 0.70, 0.71, 0.70, 0.71, 0.70, 0.71, 0.70, 0.71]
    baseline = [0.50, 0.80, 0.40, 0.90, 0.30, 0.70, 0.20, 0.60, 0.10, 0.95]
    m = compute_m_score(recent, baseline)
    assert 0.0 <= m <= 1.0
    print(f"[PASS] M(t) in [0,1]: {m:.4f}")


def test_m_score_higher_when_more_predictable():
    predictable = [0.70, 0.70, 0.70, 0.70, 0.70, 0.70, 0.70, 0.70, 0.70, 0.70]
    chaotic     = [0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0]
    baseline    = [0.5, 0.6, 0.4, 0.7, 0.3, 0.8, 0.2, 0.9, 0.1, 0.95]
    m_pred  = compute_m_score(predictable, baseline)
    m_chaos = compute_m_score(chaotic, baseline)
    assert m_pred > m_chaos, f"Predictable M(t)={m_pred:.4f} should > chaotic M(t)={m_chaos:.4f}"
    print(f"[PASS] M(t) higher for predictable: {m_pred:.4f} > {m_chaos:.4f}")


def test_observer_effect_zero_when_no_signals():
    oe = compute_observer_effect([0.0, 0.0, 0.0, 0.0, 0.0],
                                  [0.0, 0.0, 0.0, 0.0, 0.0])
    assert oe == 0.0
    print(f"[PASS] OE=0 when no signal impact")


def test_observer_effect_in_unit_interval():
    signals = [0.8, 0.9, 0.7, 0.85, 0.75, 0.8, 0.9, 0.7, 0.85, 0.75]
    changes = [0.3, 0.4, 0.2, 0.35, 0.25, 0.3, 0.4, 0.2, 0.35, 0.25]
    oe = compute_observer_effect(signals, changes)
    assert 0.0 <= oe <= 1.0, f"OE factor out of [0,1]: {oe}"
    print(f"[PASS] OE factor in [0,1]: {oe:.4f}")


def test_m_score_empty_baseline_falls_back():
    m = compute_m_score([0.5] * 10, [])
    assert isinstance(m, float)
    assert 0.0 <= m <= 1.0
    print(f"[PASS] M(t) empty baseline fallback = {m:.4f} (valid float in [0,1])")


def test_m_score_too_few_samples_handled():
    m = compute_m_score([0.7, 0.8], [0.6, 0.9])
    assert isinstance(m, float)
    assert 0.0 <= m <= 1.0
    print(f"[PASS] M(t) < 5 samples handled gracefully: {m:.4f}")


if __name__ == "__main__":
    test_prediction_interval_with_single_sample()
    test_prediction_interval_narrows_with_consistent_data()
    test_m_score_in_unit_interval()
    test_m_score_higher_when_more_predictable()
    test_observer_effect_zero_when_no_signals()
    test_observer_effect_in_unit_interval()
    test_m_score_empty_baseline_falls_back()
    test_m_score_too_few_samples_handled()
    print("\n[PASS] All m_engine (L3 M(t)) tests passed")
