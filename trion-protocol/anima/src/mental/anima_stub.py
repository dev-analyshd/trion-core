"""
ANIMA Stub — TRION L3 Phase 4
Full ANIMA is Phase 7. This stub satisfies the interface contract.
PCR * HA * CA formula implemented — but data sources are synthetic.
is_stub = True until Phase 7 replaces this.
"""
from dataclasses import dataclass
from typing import Tuple, Optional


HA_FLAG_THRESHOLD    = 0.60   # flag warning below this
HA_DISABLE_THRESHOLD = 0.40   # disable ANIMA output below this


@dataclass
class AnimaOutput:
    distribution_mean: float
    distribution_std:  float
    ci_95:             Tuple[float, float]
    pcr:               float
    ha_90d:            float
    ca:                float
    a_score:           float
    is_stub:           bool = True
    confidence_warning: bool = False


class AnimaStub:
    """
    Minimal ANIMA stub satisfying Phase 4 interface.
    Returns synthetic but structurally correct output.
    """

    def compute(
        self,
        phi_adj: float,
        m_score: float = 0.5,
        source_count: int = 3,
    ) -> AnimaOutput:
        # Stub PCR: proportion of sources above 0.60 threshold
        pcr = 0.65  # synthetic

        # Stub HA: historical accuracy (warm-up period)
        ha = 0.70

        # Stub CA: cross-source agreement
        ca = 0.75

        a_score = pcr * ha * ca
        std     = 0.15 * (1.0 - a_score)
        ci_lo   = max(0.0, a_score - 1.96 * std)
        ci_hi   = min(1.0, a_score + 1.96 * std)

        return AnimaOutput(
            distribution_mean=round(a_score, 6),
            distribution_std=round(std, 6),
            ci_95=(round(ci_lo, 6), round(ci_hi, 6)),
            pcr=round(pcr, 6),
            ha_90d=round(ha, 6),
            ca=round(ca, 6),
            a_score=round(a_score, 6),
            is_stub=True,
        )
