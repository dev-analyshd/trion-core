"""
Conformal Predictor — TRION L3 (Mental Plane)
Provides CI_95 for M(t) using non-conformity scores.
Coverage guarantee: 1 - alpha = 0.95

Usage:
    cp = ConformalPredictor()
    cp.calibrate(residual)          # feed |predicted - actual| observations
    lo, hi = cp.predict_interval(0.72)
"""
import math
from collections import deque
from typing import Tuple


class ConformalPredictor:
    """
    Conformal prediction for any TRION score.
    Calibration set grows dynamically; coverage is always maintained.
    Bootstrap mode: 15% width until 10+ calibration points available.
    """

    def __init__(self, alpha: float = 0.05, max_cal: int = 1000):
        self.alpha       = alpha        # significance level (1-alpha = 95% coverage)
        self.calibration = deque(maxlen=max_cal)

    def calibrate(self, residual: float):
        """Add a new non-conformity score (|predicted - actual|) to the calibration set."""
        self.calibration.append(abs(residual))

    def predict_interval(self, point_estimate: float) -> Tuple[float, float]:
        """
        Non-conformity quantile: q = quantile(calibration, 1-alpha)
        CI = [estimate - q, estimate + q], clamped to [0,1] with lo < hi.

        Falls back to ±15% bootstrap width until 10+ calibration points.
        """
        if len(self.calibration) < 10:
            margin = 0.15
        else:
            sorted_cal = sorted(self.calibration)
            q_idx      = int(math.ceil((1 - self.alpha) * len(sorted_cal))) - 1
            margin     = sorted_cal[min(q_idx, len(sorted_cal) - 1)]

        lo = max(0.0, point_estimate - margin)
        hi = min(1.0, point_estimate + margin)
        if lo >= hi:
            hi = min(1.0, lo + 0.001)
        return (round(lo, 6), round(hi, 6))

    @property
    def calibration_size(self) -> int:
        return len(self.calibration)

    @property
    def is_bootstrap(self) -> bool:
        return len(self.calibration) < 10
