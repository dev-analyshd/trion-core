"""Tests for src/planes/mental/conformal_predictor.py — Conformal CI_95."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import random
from src.planes.mental.conformal_predictor import ConformalPredictor


def test_bootstrap_mode_before_calibration():
    cp = ConformalPredictor()
    assert cp.is_bootstrap
    lo, hi = cp.predict_interval(0.5)
    assert lo < hi, "CI must be ordered"
    assert 0.0 <= lo and hi <= 1.0
    print(f"[PASS] Bootstrap CI=[{lo},{hi}]")


def test_ci_always_ordered_in_unit_interval():
    cp = ConformalPredictor()
    rng = random.Random(42)
    for _ in range(50):
        for _ in range(20):
            cp.calibrate(rng.uniform(0, 0.5))
        est = rng.random()
        lo, hi = cp.predict_interval(est)
        assert lo < hi, f"CI not ordered: [{lo},{hi}]"
        assert 0.0 <= lo <= 1.0 and 0.0 <= hi <= 1.0
    print(f"[PASS] CI always ordered and in [0,1]")


def test_tight_calibration_gives_narrow_ci():
    cp = ConformalPredictor()
    for _ in range(100):
        cp.calibrate(0.01)
    lo, hi = cp.predict_interval(0.5)
    assert (hi - lo) < 0.10, f"Tight calibration should give narrow CI: [{lo},{hi}]"
    print(f"[PASS] Tight calibration: CI width={hi-lo:.4f}")


def test_wide_calibration_gives_wide_ci():
    cp = ConformalPredictor()
    for _ in range(100):
        cp.calibrate(0.40)
    lo, hi = cp.predict_interval(0.5)
    assert (hi - lo) > 0.30, f"Wide calibration should give wide CI: [{lo},{hi}]"
    print(f"[PASS] Wide calibration: CI width={hi-lo:.4f}")


def test_ci_at_boundary_does_not_exceed_unit():
    cp = ConformalPredictor()
    for _ in range(100):
        cp.calibrate(0.30)
    for extreme in [0.0, 0.01, 0.99, 1.0]:
        lo, hi = cp.predict_interval(extreme)
        assert 0.0 <= lo <= 1.0 and 0.0 <= hi <= 1.0
        assert lo < hi
    print(f"[PASS] Boundary predictions stay in [0,1] with ordered CI")


def test_calibration_size_grows():
    cp = ConformalPredictor(max_cal=500)
    assert cp.calibration_size == 0
    for i in range(20):
        cp.calibrate(0.1)
    assert cp.calibration_size == 20
    assert not cp.is_bootstrap
    print(f"[PASS] Calibration size grows and exits bootstrap mode")


if __name__ == "__main__":
    test_bootstrap_mode_before_calibration()
    test_ci_always_ordered_in_unit_interval()
    test_tight_calibration_gives_narrow_ci()
    test_wide_calibration_gives_wide_ci()
    test_ci_at_boundary_does_not_exceed_unit()
    test_calibration_size_grows()
    print("\n[PASS] All conformal predictor tests passed")
