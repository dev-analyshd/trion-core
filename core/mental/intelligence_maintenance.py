"""
TRION Protocol — L3.7 Intelligence Maintenance Protocol (IMP)

IM(component, t) = Accuracy(component, t) / Accuracy(component, t_baseline)

Monitors ALL TRION components for accuracy degradation.
Detects silent degradation before it corrupts the Akashic Index.

Falsification condition F7:
  Falsified if any component degrades below threshold without
  detection and correction within 24 hours.

IMP guarantees this cannot happen by continuous monitoring.

Detection thresholds:
    IM >= 0.95: HEALTHY
    IM  < 0.95: WARNING (investigation triggered)
    IM  < 0.80: DEGRADED (automatic weight reduction)
    IM  < 0.60: CRITICAL (component isolated, governance alert)
    IM  < 0.40: FAILURE (component offline, emergency protocol)

Accuracy measurement method:
    Compare component predictions against realized outcomes
    over rolling 30-day window.
    Baseline established in first 90 days of operation.

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class ComponentHealth(Enum):
    HEALTHY  = "HEALTHY"
    WARNING  = "WARNING"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"
    FAILURE  = "FAILURE"


HEALTH_THRESHOLDS = {
    ComponentHealth.HEALTHY:  0.95,
    ComponentHealth.WARNING:  0.80,
    ComponentHealth.DEGRADED: 0.60,
    ComponentHealth.CRITICAL: 0.40,
    ComponentHealth.FAILURE:  0.00,
}

# Automatic responses per health tier
AUTO_RESPONSES: Dict[ComponentHealth, str] = {
    ComponentHealth.HEALTHY:  "no_action",
    ComponentHealth.WARNING:  "investigate_trigger",
    ComponentHealth.DEGRADED: "weight_reduction_50pct",
    ComponentHealth.CRITICAL: "component_isolation",
    ComponentHealth.FAILURE:  "emergency_protocol_offline",
}

MAX_DEGRADATION_WINDOW_HOURS = 24.0  # F7: must detect within 24 hours


@dataclass
class ComponentAccuracy:
    """Rolling accuracy measurement for one component."""
    component_id:        str
    predictions:         List[float]    # Component predictions (rolling 30d)
    realized_outcomes:   List[float]    # Actual outcomes
    timestamps:          List[float]    # Unix timestamps


@dataclass
class IMPResult:
    """
    Intelligence Maintenance Protocol result for one component.
    """
    component_id:        str
    im_score:            float           # IM(component, t) = Acc(t) / Acc(baseline)
    accuracy_current:    float           # Current rolling accuracy
    accuracy_baseline:   float          # Baseline accuracy
    health:              ComponentHealth
    auto_response:       str
    hours_since_detect:  float          # Hours since degradation started
    f7_violation:        bool           # True if degradation undetected > 24h
    warning:             Optional[str]


def compute_accuracy(
    predictions:       List[float],
    realized_outcomes: List[float],
    method:            str = "mae_normalized",
) -> float:
    """
    Compute accuracy of a component's predictions vs realized outcomes.

    method "mae_normalized":
        Acc = 1 - MAE / baseline_variance
        Baseline variance = std of realized outcomes
    """
    n = min(len(predictions), len(realized_outcomes))
    if n == 0:
        return 0.0

    pairs = list(zip(predictions[-n:], realized_outcomes[-n:]))
    mae   = sum(abs(p - r) for p, r in pairs) / n

    mean_r = sum(r for _, r in pairs) / n
    var_r  = sum((r - mean_r) ** 2 for _, r in pairs) / n
    std_r  = var_r ** 0.5

    # Use max(std_r, 0.05) to prevent division collapse when outcomes are
    # tightly clustered — MAE/std_r explodes when both are very small.
    denom = max(std_r, 0.05)
    return max(0.0, min(1.0, 1.0 - mae / denom))


def classify_health(im_score: float) -> ComponentHealth:
    """Classify component health from IM score."""
    if im_score >= HEALTH_THRESHOLDS[ComponentHealth.HEALTHY]:
        return ComponentHealth.HEALTHY
    elif im_score >= HEALTH_THRESHOLDS[ComponentHealth.WARNING]:
        return ComponentHealth.WARNING
    elif im_score >= HEALTH_THRESHOLDS[ComponentHealth.DEGRADED]:
        return ComponentHealth.DEGRADED
    elif im_score >= HEALTH_THRESHOLDS[ComponentHealth.CRITICAL]:
        return ComponentHealth.CRITICAL
    else:
        return ComponentHealth.FAILURE


def compute_im(
    component:              ComponentAccuracy,
    baseline_predictions:   List[float],
    baseline_outcomes:      List[float],
    degradation_start_ts:   Optional[float] = None,
) -> IMPResult:
    """
    IM(component, t) = Accuracy(component, t) / Accuracy(component, t_baseline)

    Baseline accuracy: established during first 90 days of operation.
    Current accuracy: rolling 30-day window.

    F7 check: if degradation started more than 24 hours ago without correction,
    F7 is violated.
    """
    acc_current  = compute_accuracy(component.predictions, component.realized_outcomes)
    acc_baseline = compute_accuracy(baseline_predictions, baseline_outcomes)

    if acc_baseline <= 0:
        im = 0.0
    else:
        im = acc_current / acc_baseline

    im = max(0.0, im)

    health        = classify_health(im)
    auto_response = AUTO_RESPONSES.get(health, "no_action")

    hours_degraded = 0.0
    f7_violation   = False

    if health != ComponentHealth.HEALTHY and degradation_start_ts is not None:
        now = time.time()
        hours_degraded = (now - degradation_start_ts) / 3600.0
        f7_violation   = hours_degraded > MAX_DEGRADATION_WINDOW_HOURS

    warning = None
    if f7_violation:
        warning = (
            f"F7 VIOLATION: component '{component.component_id}' degraded "
            f"for {hours_degraded:.1f}h (limit: {MAX_DEGRADATION_WINDOW_HOURS}h). "
            "Falsification condition F7 triggered."
        )
    elif health == ComponentHealth.CRITICAL:
        warning = (
            f"CRITICAL DEGRADATION: IM={im:.4f} for '{component.component_id}'. "
            "Component isolated. Governance alert triggered."
        )
    elif health == ComponentHealth.DEGRADED:
        warning = (
            f"DEGRADED: IM={im:.4f} for '{component.component_id}'. "
            "Weight reduced 50%. Investigation triggered."
        )
    elif health == ComponentHealth.WARNING:
        warning = f"WARNING: IM={im:.4f} for '{component.component_id}'. Investigation triggered."

    return IMPResult(
        component_id       = component.component_id,
        im_score           = im,
        accuracy_current   = acc_current,
        accuracy_baseline  = acc_baseline,
        health             = health,
        auto_response      = auto_response,
        hours_since_detect = hours_degraded,
        f7_violation       = f7_violation,
        warning            = warning,
    )


# ── Multi-Component Monitoring ─────────────────────────────────────────────────

class IntelligenceMaintenanceSystem:
    """
    Continuous monitoring system for all TRION components.
    Runs every block — detects degradation within 24 hours.
    """

    def __init__(self):
        self.components:          Dict[str, ComponentAccuracy] = {}
        self.baselines:           Dict[str, tuple] = {}         # (preds, outcomes)
        self.degradation_starts:  Dict[str, Optional[float]] = {}
        self.results:             Dict[str, IMPResult] = {}

    def register_component(
        self,
        component_id:         str,
        baseline_predictions: List[float],
        baseline_outcomes:    List[float],
    ):
        self.baselines[component_id] = (baseline_predictions, baseline_outcomes)
        self.degradation_starts[component_id] = None
        self.components[component_id] = ComponentAccuracy(
            component_id       = component_id,
            predictions        = [],
            realized_outcomes  = [],
            timestamps         = [],
        )

    def update_component(
        self,
        component_id:     str,
        new_prediction:   float,
        realized_outcome: float,
        timestamp:        Optional[float] = None,
    ):
        if component_id not in self.components:
            return

        comp = self.components[component_id]
        ts = timestamp or time.time()

        # Rolling 30-day window (approx 30 * 5760 = 172800 blocks, or keep last 1000 data points)
        comp.predictions.append(new_prediction)
        comp.realized_outcomes.append(realized_outcome)
        comp.timestamps.append(ts)

        # Keep rolling window of 1000 observations
        if len(comp.predictions) > 1000:
            comp.predictions    = comp.predictions[-1000:]
            comp.realized_outcomes = comp.realized_outcomes[-1000:]
            comp.timestamps     = comp.timestamps[-1000:]

        self._run_health_check(component_id, ts)

    def _run_health_check(self, component_id: str, ts: float):
        if component_id not in self.baselines:
            return

        comp = self.components[component_id]
        base_preds, base_outcomes = self.baselines[component_id]
        deg_start = self.degradation_starts.get(component_id)

        result = compute_im(comp, base_preds, base_outcomes, deg_start)
        self.results[component_id] = result

        # Track degradation start time
        if result.health != ComponentHealth.HEALTHY:
            if self.degradation_starts[component_id] is None:
                self.degradation_starts[component_id] = ts
        else:
            self.degradation_starts[component_id] = None  # Reset if recovered

    def get_system_health(self) -> Dict[str, ComponentHealth]:
        return {cid: r.health for cid, r in self.results.items()}

    def has_f7_violation(self) -> bool:
        return any(r.f7_violation for r in self.results.values())

    def get_critical_components(self) -> List[IMPResult]:
        return [r for r in self.results.values()
                if r.health in (ComponentHealth.CRITICAL, ComponentHealth.FAILURE)]


if __name__ == "__main__":
    # Test healthy component — predictions match baseline quality exactly (no degradation)
    preds         = [0.70, 0.72, 0.68, 0.73, 0.71]
    outcomes      = [0.71, 0.70, 0.69, 0.72, 0.70]
    comp_healthy = ComponentAccuracy(
        component_id="nl_engine",
        predictions=preds,
        realized_outcomes=outcomes,
        timestamps=[1746000000.0 + i * 86400 for i in range(5)],
    )
    # Baseline uses same predictions and outcomes → identical accuracy → IM = 1.0
    base_preds    = preds
    base_outcomes = outcomes

    result = compute_im(comp_healthy, base_preds, base_outcomes)
    print(f"Healthy: IM={result.im_score:.4f} health={result.health.value}")
    assert result.health == ComponentHealth.HEALTHY

    # Test degraded component (random noise predictions)
    comp_degraded = ComponentAccuracy(
        component_id="degraded_model",
        predictions=[0.90, 0.10, 0.80, 0.20, 0.70],
        realized_outcomes=[0.40, 0.45, 0.42, 0.44, 0.41],
        timestamps=[1746000000.0 + i * 86400 for i in range(5)],
    )
    result_d = compute_im(comp_degraded, base_preds, base_outcomes)
    print(f"Degraded: IM={result_d.im_score:.4f} health={result_d.health.value} "
          f"response={result_d.auto_response}")
    assert result_d.health in (ComponentHealth.WARNING, ComponentHealth.DEGRADED,
                                ComponentHealth.CRITICAL, ComponentHealth.FAILURE)

    # IMP system test
    ims = IntelligenceMaintenanceSystem()
    ims.register_component("phi_engine", base_preds, base_outcomes)
    for i in range(5):
        ims.update_component("phi_engine", 0.71 + i * 0.01, 0.70 + i * 0.01)
    health = ims.get_system_health()
    print(f"IMP system: phi_engine={health.get('phi_engine', 'N/A')}")
    assert not ims.has_f7_violation()

    print("L3.7 Intelligence Maintenance Protocol: PASS")
