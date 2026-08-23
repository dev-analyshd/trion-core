"""
TRION Protocol — L3.7: Intelligence Maintenance Protocol (IMP)
Whitepaper Chapter 8: ANIMA Intelligence Layer

The Intelligence Maintenance Protocol monitors ANIMA's ongoing accuracy
and triggers automatic retraining when performance degrades below threshold.

IM(t) = weighted_average_of_accuracy_metrics(t)

IM Threshold:
  IM < IM_THRESHOLD → trigger retraining cycle
  IM < IM_CRITICAL  → ANIMA output marked UNRELIABLE, signal degraded

Monitoring Metrics (whitepaper §8.4):
  1. Prediction Accuracy (PA):    HA tracker from anima_engine.py
  2. Calibration Score (CS):      Distribution calibration quality
  3. Pattern Coherence Ratio (PCR): Fraction of patterns with current coherence
  4. Stream Completeness (SC):    Active data streams / required streams
  5. Cross-Source Agreement (CA): Credibility-weighted cross-source agreement

IMP Actions:
  HEALTHY:     No action required
  FLAGGED:     Issue warning, increase monitoring frequency
  RETRAIN:     Trigger retraining cycle (pattern library reset + history retention)
  UNRELIABLE:  Mark ANIMA output as UNRELIABLE, reduce signal weight by 0.50
  DISABLED:    IM < 0.20 → ANIMA output = 0 (same as HA < 0.60 rule)

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


# ── Thresholds (whitepaper L3.7) ──────────────────────────────────────────────

IM_THRESHOLD  = 0.55    # IM < 0.55 → trigger retraining
IM_CRITICAL   = 0.40    # IM < 0.40 → ANIMA output marked UNRELIABLE
IM_DISABLED   = 0.20    # IM < 0.20 → ANIMA output = 0

# Component weights for IM(t) computation
IM_WEIGHTS = {
    "pa":  0.30,   # Prediction accuracy (most important)
    "cs":  0.20,   # Calibration score
    "pcr": 0.20,   # Pattern coherence ratio
    "sc":  0.15,   # Stream completeness
    "ca":  0.15,   # Cross-source agreement
}

assert abs(sum(IM_WEIGHTS.values()) - 1.0) < 1e-9, "IM weights must sum to 1.0"


class IMPStatus(str, Enum):
    HEALTHY     = "HEALTHY"
    FLAGGED     = "FLAGGED"
    RETRAIN     = "RETRAIN"
    UNRELIABLE  = "UNRELIABLE"
    DISABLED    = "DISABLED"


@dataclass
class IMPMetrics:
    """Current ANIMA metrics fed into the Intelligence Maintenance Protocol."""
    pa:                 float   # Prediction Accuracy [0,1]
    cs:                 float   # Calibration Score [0,1]
    pcr:                float   # Pattern Coherence Ratio [0,1]
    sc:                 float   # Stream Completeness [0,1]
    ca:                 float   # Cross-Source Agreement [0,1]
    sample_size:        int     # Number of predictions evaluated
    timestamp:          float


@dataclass
class IMPResult:
    """Intelligence Maintenance Protocol evaluation result."""
    im_score:           float           # IM(t) ∈ [0,1]
    status:             IMPStatus
    metrics:            IMPMetrics
    weights:            Dict[str, float]
    component_scores:   Dict[str, float]
    retrain_triggered:  bool
    signal_weight:      float           # Multiplier applied to ANIMA output [0,1]
    actions:            List[str]
    retraining_cycles:  int
    last_retrain_at:    Optional[float]
    disclosure:         str


@dataclass
class RetrainingCycle:
    """Record of a completed retraining cycle."""
    cycle_id:           int
    triggered_at:       float
    trigger_reason:     str
    im_score_before:    float
    im_score_after:     Optional[float]
    patterns_reset:     int
    history_retained:   bool
    completed_at:       Optional[float]


class IntelligenceMaintenanceProtocol:
    """
    L3.7 IMP — monitors ANIMA accuracy and triggers retraining.

    Plugs into ANIMAEngine's HA tracker and pattern library.
    Called after every ANIMA prediction cycle to assess health.
    """

    MONITORING_WINDOW_SIZE = 100    # Keep last N IM scores for trend analysis

    def __init__(self):
        self._history:     List[float] = []
        self._cycles:      List[RetrainingCycle] = []
        self._last_retrain: Optional[float] = None
        self._retrain_count: int = 0

    def evaluate(
        self,
        pa:              float,
        cs:              float,
        pcr:             float,
        sc:              float,
        ca:              float,
        sample_size:     int = 0,
        force_retrain:   bool = False,
    ) -> IMPResult:
        """
        IM(t) = 0.30·PA + 0.20·CS + 0.20·PCR + 0.15·SC + 0.15·CA

        Clamp all inputs to [0,1] before computation.
        """
        now = time.time()
        metrics = IMPMetrics(
            pa          = max(0.0, min(1.0, pa)),
            cs          = max(0.0, min(1.0, cs)),
            pcr         = max(0.0, min(1.0, pcr)),
            sc          = max(0.0, min(1.0, sc)),
            ca          = max(0.0, min(1.0, ca)),
            sample_size = sample_size,
            timestamp   = now,
        )

        component_scores = {
            "pa":  IM_WEIGHTS["pa"]  * metrics.pa,
            "cs":  IM_WEIGHTS["cs"]  * metrics.cs,
            "pcr": IM_WEIGHTS["pcr"] * metrics.pcr,
            "sc":  IM_WEIGHTS["sc"]  * metrics.sc,
            "ca":  IM_WEIGHTS["ca"]  * metrics.ca,
        }
        im_score = sum(component_scores.values())
        im_score = max(0.0, min(1.0, im_score))

        # Update rolling history
        self._history.append(im_score)
        if len(self._history) > self.MONITORING_WINDOW_SIZE:
            self._history = self._history[-self.MONITORING_WINDOW_SIZE:]

        # Determine status
        if im_score < IM_DISABLED:
            status = IMPStatus.DISABLED
        elif im_score < IM_CRITICAL:
            status = IMPStatus.UNRELIABLE
        elif im_score < IM_THRESHOLD or force_retrain:
            status = IMPStatus.RETRAIN
        elif im_score < 0.65:
            status = IMPStatus.FLAGGED
        else:
            status = IMPStatus.HEALTHY

        # Signal weight multiplier
        signal_weight = {
            IMPStatus.HEALTHY:    1.0,
            IMPStatus.FLAGGED:    0.85,
            IMPStatus.RETRAIN:    0.70,
            IMPStatus.UNRELIABLE: 0.50,
            IMPStatus.DISABLED:   0.0,
        }[status]

        # Build actions
        actions = []
        retrain_triggered = False

        if status == IMPStatus.DISABLED:
            actions.append("ANIMA_OUTPUT_ZEROED: IM below disabled threshold — A(t) = 0")
        if status == IMPStatus.UNRELIABLE:
            actions.append(f"SIGNAL_DEGRADED: ANIMA output weight reduced to {signal_weight:.2f}")
        if status in (IMPStatus.RETRAIN, IMPStatus.UNRELIABLE) or force_retrain:
            retrain_triggered = True
            cycle = self._trigger_retrain(im_score)
            actions.append(
                f"RETRAIN_CYCLE_{cycle.cycle_id}: pattern library reset, "
                f"history retained ({cycle.history_retained}), "
                f"patterns_reset={cycle.patterns_reset}"
            )
        if status == IMPStatus.FLAGGED:
            actions.append("MONITORING_INCREASED: IM in warning zone, frequency doubled")

        # Trend analysis from rolling history
        trend = self._compute_trend()
        if trend == "FALLING" and im_score < 0.65:
            actions.append(f"TREND_WARNING: IM falling ({trend}) — proactive review recommended")

        return IMPResult(
            im_score          = round(im_score, 6),
            status            = status,
            metrics           = metrics,
            weights           = IM_WEIGHTS.copy(),
            component_scores  = {k: round(v, 4) for k, v in component_scores.items()},
            retrain_triggered = retrain_triggered,
            signal_weight     = signal_weight,
            actions           = actions,
            retraining_cycles = self._retrain_count,
            last_retrain_at   = self._last_retrain,
            disclosure        = self._build_disclosure(im_score, status, signal_weight, trend),
        )

    def _trigger_retrain(self, im_before: float) -> RetrainingCycle:
        """
        Trigger a retraining cycle.
        Pattern library reset: archetypes re-derived from Akashic history.
        History is retained: prediction accuracy tracker not cleared.
        """
        self._retrain_count += 1
        self._last_retrain   = time.time()

        cycle = RetrainingCycle(
            cycle_id        = self._retrain_count,
            triggered_at    = self._last_retrain,
            trigger_reason  = f"IM={im_before:.4f} < threshold={IM_THRESHOLD}",
            im_score_before = im_before,
            im_score_after  = None,
            patterns_reset  = 64,   # All 64 archetypes re-derived
            history_retained = True,
            completed_at    = None,
        )
        self._cycles.append(cycle)
        return cycle

    def complete_retrain(self, im_score_after: float) -> None:
        """Call after retraining is complete to record IM improvement."""
        if self._cycles:
            last = self._cycles[-1]
            last.im_score_after = im_score_after
            last.completed_at   = time.time()

    def _compute_trend(self) -> str:
        """Compute IM(t) trend from rolling history."""
        n = len(self._history)
        if n < 5:
            return "STABLE"
        recent = self._history[-min(n, 10):]
        r = len(recent)
        x_mean = (r - 1) / 2.0
        y_mean = sum(recent) / r
        num   = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(recent))
        denom = sum((i - x_mean) ** 2 for i in range(r))
        slope = num / denom if denom > 0 else 0.0
        if slope > 0.01:
            return "RISING"
        if slope < -0.01:
            return "FALLING"
        return "STABLE"

    def _build_disclosure(
        self, im: float, status: IMPStatus, weight: float, trend: str
    ) -> str:
        parts = [
            f"IM(t)={im:.4f} [{status.value}] trend={trend}. "
            f"ANIMA signal_weight={weight:.2f}. "
        ]
        if status == IMPStatus.DISABLED:
            parts.append(f"ANIMA output zeroed (IM < {IM_DISABLED}). Retraining required.")
        elif status == IMPStatus.UNRELIABLE:
            parts.append(f"ANIMA output degraded 50% (IM < {IM_CRITICAL}). Retraining in progress.")
        elif status == IMPStatus.RETRAIN:
            parts.append(f"Retraining triggered (IM < {IM_THRESHOLD}). Pattern library rebuilding.")
        elif status == IMPStatus.FLAGGED:
            parts.append("IM in warning zone. Increased monitoring active.")
        else:
            parts.append("ANIMA intelligence healthy — no action required.")
        return "".join(parts)

    def get_cycles(self) -> List[dict]:
        return [
            {
                "cycle_id":        c.cycle_id,
                "triggered_at":    int(c.triggered_at),
                "trigger_reason":  c.trigger_reason,
                "im_before":       c.im_score_before,
                "im_after":        c.im_score_after,
                "patterns_reset":  c.patterns_reset,
                "history_retained": c.history_retained,
                "completed_at":    int(c.completed_at) if c.completed_at else None,
            }
            for c in self._cycles
        ]

    def status_dict(self) -> dict:
        trend = self._compute_trend()
        recent_im = self._history[-1] if self._history else 0.0
        return {
            "im_score":          round(recent_im, 4),
            "trend":             trend,
            "retraining_cycles": self._retrain_count,
            "last_retrain_at":   int(self._last_retrain) if self._last_retrain else None,
            "history_length":    len(self._history),
        }


# ── Module-level singleton ────────────────────────────────────────────────────

_imp = IntelligenceMaintenanceProtocol()

def get_imp() -> IntelligenceMaintenanceProtocol:
    return _imp


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    imp = IntelligenceMaintenanceProtocol()

    # Healthy ANIMA
    r = imp.evaluate(pa=0.85, cs=0.78, pcr=0.72, sc=1.0, ca=0.80, sample_size=500)
    print(f"HEALTHY: IM={r.im_score:.4f} [{r.status.value}] weight={r.signal_weight:.2f}")
    assert r.status == IMPStatus.HEALTHY
    assert r.signal_weight == 1.0
    assert not r.retrain_triggered

    # Flagged
    r2 = imp.evaluate(pa=0.62, cs=0.55, pcr=0.50, sc=0.70, ca=0.55, sample_size=200)
    print(f"FLAGGED: IM={r2.im_score:.4f} [{r2.status.value}] weight={r2.signal_weight:.2f}")
    assert r2.status == IMPStatus.FLAGGED

    # Retrain triggered
    r3 = imp.evaluate(pa=0.45, cs=0.42, pcr=0.38, sc=0.60, ca=0.40, sample_size=100)
    print(f"RETRAIN: IM={r3.im_score:.4f} [{r3.status.value}] triggered={r3.retrain_triggered}")
    assert r3.status == IMPStatus.RETRAIN
    assert r3.retrain_triggered
    assert r3.signal_weight == 0.70

    imp.complete_retrain(0.68)

    # Unreliable
    r4 = imp.evaluate(pa=0.25, cs=0.30, pcr=0.22, sc=0.40, ca=0.28, sample_size=30)
    print(f"UNRELIABLE: IM={r4.im_score:.4f} [{r4.status.value}] weight={r4.signal_weight:.2f}")
    assert r4.status == IMPStatus.UNRELIABLE
    assert r4.signal_weight == 0.50

    # Disabled
    r5 = imp.evaluate(pa=0.10, cs=0.08, pcr=0.05, sc=0.20, ca=0.12, sample_size=10)
    print(f"DISABLED: IM={r5.im_score:.4f} [{r5.status.value}] weight={r5.signal_weight:.2f}")
    assert r5.status == IMPStatus.DISABLED
    assert r5.signal_weight == 0.0

    cycles = imp.get_cycles()
    print(f"Retraining cycles: {len(cycles)}")

    print("\nL3.7 Intelligence Maintenance Protocol: ALL PASS")
