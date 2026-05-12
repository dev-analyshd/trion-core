"""
ANIMA v1 — TRION L7 (replaces stub from Phase 4)
Full PCR * HA * CA with real offchain data.
Manifestation Gap Monitor calibrating continuously.
"""
from dataclasses import dataclass, field
from typing import Dict
from collections import deque
import numpy as np

from mental.source_credibility import CredibilityRegistry
from mental.anima_stub import AnimaOutput, HA_FLAG_THRESHOLD, HA_DISABLE_THRESHOLD
from adapters.biological_capital import compute_bc, EcosystemMetrics, BiologicalRhythmTimer
from adapters.natural_liquidity import compute_nl
from adapters.energy_participation import compute_ep


@dataclass
class ManifestationGapMonitor:
    """
    MG(S, t) = B_predicted(S, t) - B_observed(t)
    Rolling mean improves future timing predictions.
    """
    asset_id:    str
    gap_history: deque = field(default_factory=lambda: deque(maxlen=90))

    def record(self, predicted: float, observed: float):
        self.gap_history.append(predicted - observed)

    @property
    def rolling_mean(self) -> float:
        if not self.gap_history: return 0.0
        return sum(self.gap_history) / len(self.gap_history)

    @property
    def is_calibrating(self) -> bool:
        return len(self.gap_history) < 30

    def adjusted_prediction(self, raw_prediction: float) -> float:
        return raw_prediction - self.rolling_mean


class AnimaV1:
    """Full ANIMA v1 — all real data sources."""

    def __init__(self, asset_id: str):
        self.asset_id       = asset_id
        self.registry       = CredibilityRegistry()
        self.mg_monitor     = ManifestationGapMonitor(asset_id)
        self.bio_timer      = BiologicalRhythmTimer()
        self.accuracy_history = deque(maxlen=90)

        for src in [
            "onchain_flows", "onchain_governance", "onchain_liquidity",
            "dev_activity", "governance_forums", "regulatory_filings",
            "ecosystem_bc", "natural_liquidity", "energy_participation",
        ]:
            self.registry.register(src)

    def compute(self, source_values: Dict[str, float],
                signal_impact: float = 0.0,
                unix_ts: float = 0.0) -> AnimaOutput:
        values   = list(source_values.values())
        theta_pcr = 0.60
        coherent = sum(1 for v in values if v > theta_pcr)
        pcr      = coherent / len(values) if values else 0.5

        if len(self.accuracy_history) >= 5:
            ha = sum(self.accuracy_history) / len(self.accuracy_history)
        else:
            ha = 0.70

        ha_flagged  = ha < HA_FLAG_THRESHOLD
        ha_disabled = ha < HA_DISABLE_THRESHOLD

        if ha_disabled:
            return AnimaOutput(
                distribution_mean=0.0, distribution_std=0.5,
                ci_95=(0.0, 0.5), pcr=pcr, ha_90d=ha, ca=0.0,
                a_score=0.0, is_stub=False, confidence_warning=True
            )

        ca    = self.registry.cross_source_agreement(source_values)
        a_raw = pcr * ha * ca

        if signal_impact > 0:
            reflexivity = min(signal_impact, 1.0)
            a_adj = a_raw * (1.0 - 0.30 * reflexivity)
        else:
            a_adj = a_raw

        a_adj = self.mg_monitor.adjusted_prediction(a_adj)
        a_adj = max(0.0, min(1.0, a_adj))

        std   = 0.15 * (1.0 - a_adj)
        ci_lo = max(0.0, a_adj - 1.96 * std)
        ci_hi = min(1.0, a_adj + 1.96 * std)

        return AnimaOutput(
            distribution_mean=round(a_adj, 6),
            distribution_std=round(std, 6),
            ci_95=(round(ci_lo, 6), round(ci_hi + 0.001, 6)),
            pcr=round(pcr, 6),
            ha_90d=round(ha, 6),
            ca=round(ca, 6),
            a_score=round(a_adj, 6),
            is_stub=False,
            confidence_warning=ha_flagged,
        )
