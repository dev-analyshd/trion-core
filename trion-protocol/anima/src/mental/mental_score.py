"""
Mental Coherence Score M(t) — TRION L3
M(t) = ANIMA(t) * (1 - OE_factor) * IM_protocol_weight
Conformal prediction for CI_95.
Observer Effect dampening when signal impacts behavior.
"""
import math
from dataclasses import dataclass
from typing import Tuple, Optional, List
from collections import deque

from mental.source_credibility import CredibilityRegistry
from mental.anima_stub import AnimaOutput, AnimaStub


# Observer Effect dampening coefficient
OE_DAMPENING = 0.15   # 15% reduction per unit of signal impact

# IM Protocol: information market weights
IM_VALID_THRESHOLD = 0.60


@dataclass
class MentalScoreOutput:
    m_adj:       float
    m_raw:       float
    oe_factor:   float
    ci_95:       Tuple[float, float]
    anima:       AnimaOutput
    im_weight:   float
    tc_valid:    bool


class ConformalPredictor:
    """
    Conformal prediction for CI_95 of M(t).
    Calibration set grows with new observations.
    Coverage: 1 - alpha = 0.95
    """

    def __init__(self, alpha: float = 0.05):
        self.alpha       = alpha
        self.calibration = deque(maxlen=1000)

    def calibrate(self, residual: float):
        """Add a new residual (|predicted - actual|) to calibration set."""
        self.calibration.append(abs(residual))

    def predict_interval(self, point_estimate: float) -> Tuple[float, float]:
        """
        Non-conformity score: q = quantile(calibration, 1-alpha)
        CI_95 = [estimate - q, estimate + q]
        Falls back to ±1.96*std_dev if calibration set is small.
        """
        if len(self.calibration) < 10:
            # Bootstrap: use 15% width
            margin = 0.15
        else:
            sorted_cal = sorted(self.calibration)
            q_idx      = int(math.ceil((1 - self.alpha) * len(sorted_cal))) - 1
            margin     = sorted_cal[min(q_idx, len(sorted_cal) - 1)]

        lo = max(0.0, point_estimate - margin)
        hi = min(1.0, point_estimate + margin)
        # ensure lo < hi while keeping both in [0,1]
        if lo >= hi:
            hi = min(1.0, lo + 0.001)
        return (round(lo, 6), round(hi, 6))


class InformationMarketProtocol:
    """
    IM Protocol: prediction markets that weight ANIMA sources.
    im_weight = weighted market consensus / number of markets.
    """

    def __init__(self):
        self._market_scores: List[float] = []

    def submit_market_score(self, score: float):
        """Add a market consensus score (0-1)."""
        self._market_scores.append(max(0.0, min(1.0, score)))

    def compute_weight(self) -> float:
        if not self._market_scores:
            return 1.0  # no market data: full weight to ANIMA
        avg = sum(self._market_scores) / len(self._market_scores)
        return max(0.0, min(1.0, avg))


def compute_observer_effect(
    signal_impact: float,
    history_count: int,
) -> float:
    """
    OE_factor = dampening if signal strongly impacts market behavior.
    Reflexivity: when our signal moves the market, M(t) must be dampened.
    OE_factor -> 0 as history_count grows (empirical calibration).
    """
    if signal_impact <= 0.0:
        return 0.0
    maturity_factor = 1.0 / (1.0 + history_count / 1000.0)
    return min(1.0, OE_DAMPENING * signal_impact * maturity_factor)


def compute_mental_score(
    phi_adj:       float,
    signal_impact: float  = 0.0,
    history_count: int    = 0,
    im_weight:     float  = 1.0,
    predictor:     Optional[ConformalPredictor] = None,
) -> MentalScoreOutput:
    """
    M(t) = ANIMA(t) * (1 - OE_factor) * im_weight
    """
    if predictor is None:
        predictor = ConformalPredictor()

    anima_stub  = AnimaStub()
    anima_out   = anima_stub.compute(phi_adj)
    oe_factor   = compute_observer_effect(signal_impact, history_count)

    m_raw = anima_out.a_score
    m_adj = m_raw * (1.0 - oe_factor) * im_weight
    m_adj = max(0.0, min(1.0, m_adj))

    ci_95 = predictor.predict_interval(m_adj)
    tc_valid = abs(m_adj - m_raw) < 0.30  # TC valid if OE hasn't distorted too much

    return MentalScoreOutput(
        m_adj=round(m_adj, 6),
        m_raw=round(m_raw, 6),
        oe_factor=round(oe_factor, 6),
        ci_95=ci_95,
        anima=anima_out,
        im_weight=round(im_weight, 6),
        tc_valid=tc_valid,
    )
