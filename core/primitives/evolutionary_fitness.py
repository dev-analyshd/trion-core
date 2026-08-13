"""
TRION Protocol — L0.6 Evolutionary Fitness Function
Channel 13: Biological Communication (Fitness)

F(component, t) = PA(c,t) · ICE(c,t) · AS(c,t) · Love(c,t)

Critical: F = 0 if Love = 0. Always. No exceptions.
This is the architectural constraint that ensures TRION never becomes
a tool for harm. Love Protocol: Love = 0 is the kill-switch.

PA  = Performance Accuracy — how well the component predicts/measures
ICE = Information Contribution Efficiency — signal/noise ratio
AS  = Adaptation Speed — how fast the component responds to new patterns
Love = Does this component contribute to life flourishing?

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class FitnessComponents:
    """
    Full fitness evaluation for a TRION component.
    """
    component_id:    str
    pa:              float  # Performance Accuracy [0, 1]
    ice:             float  # Information Contribution Efficiency [0, 1]
    as_score:        float  # Adaptation Speed [0, 1]   (field named as_score to avoid Python keyword)
    love:            float  # Love Protocol score [0, 1]
    fitness:         float  # F(c, t) = PA · ICE · AS · Love
    love_killed:     bool   # True iff Love = 0 triggered F = 0
    description:     str


def compute_fitness(
    component_id:     str,
    pa:               float,
    ice:              float,
    adaptation_speed: float,
    love:             float,
) -> FitnessComponents:
    """
    Evolutionary Fitness Function:
        F(component, t) = PA(c,t) · ICE(c,t) · AS(c,t) · Love(c,t)
        F = 0 if Love = 0. No exceptions.

    PA  ∈ [0, 1] — measured against realized outcomes
    ICE ∈ [0, 1] — computed from signal contribution vs. noise added
    AS  ∈ [0, 1] — inverse of lag from pattern change to detection
    Love∈ [0, 1] — protocol contribution to life flourishing

    Love = 0 conditions (AWA-related):
        - Component weaponized against individuals
        - Component violates Right_to_Invisibility
        - Component serves to concentrate power in one entity
        - Gratitude(t) < 1 sustained > 30 days
    """
    pa_c   = max(0.0, min(1.0, pa))
    ice_c  = max(0.0, min(1.0, ice))
    as_c   = max(0.0, min(1.0, adaptation_speed))
    love_c = max(0.0, min(1.0, love))

    if love_c == 0.0:
        return FitnessComponents(
            component_id = component_id,
            pa           = pa_c,
            ice          = ice_c,
            as_score     = as_c,
            love         = 0.0,
            fitness      = 0.0,
            love_killed  = True,
            description  = (
                f"F=0: Love=0 for component '{component_id}'. "
                "Component violates the Love Protocol — AWA enforced."
            ),
        )

    fitness = pa_c * ice_c * as_c * love_c

    tier = (
        "THRIVING" if fitness >= 0.70 else
        "HEALTHY"  if fitness >= 0.50 else
        "DEGRADED" if fitness >= 0.30 else
        "CRITICAL"
    )

    return FitnessComponents(
        component_id = component_id,
        pa           = pa_c,
        ice          = ice_c,
        as_score     = as_c,
        love         = love_c,
        fitness      = fitness,
        love_killed  = False,
        description  = (
            f"F({component_id})={fitness:.4f} [{tier}] "
            f"PA={pa_c:.2f} ICE={ice_c:.2f} AS={as_c:.2f} Love={love_c:.2f}"
        ),
    )


def compute_pa(
    predicted_values:  list[float],
    realized_values:   list[float],
) -> float:
    """
    Performance Accuracy = 1 - mean_absolute_error / baseline_variance
    Normalized so PA=1 is perfect, PA=0 is no better than baseline.
    """
    n = min(len(predicted_values), len(realized_values))
    if n == 0:
        return 0.0

    pairs  = list(zip(predicted_values[:n], realized_values[:n]))
    mae    = sum(abs(p - r) for p, r in pairs) / n
    mean_r = sum(r for _, r in pairs) / n
    var_r  = sum((r - mean_r) ** 2 for _, r in pairs) / max(1, n - 1)
    baseline_mae = var_r ** 0.5

    if baseline_mae <= 0:
        return 1.0 if mae < 1e-9 else 0.0

    pa = max(0.0, 1.0 - mae / baseline_mae)
    return min(1.0, pa)


def compute_ice(
    signal_variance:  float,
    noise_variance:   float,
) -> float:
    """
    Information Contribution Efficiency = signal_variance / (signal_variance + noise_variance)
    Based on signal-to-noise ratio. ICE=1 is pure signal, ICE=0 is pure noise.
    """
    total = signal_variance + noise_variance
    if total <= 0:
        return 0.0
    return signal_variance / total


def compute_adaptation_speed(
    detection_lag_blocks:  int,
    reference_lag_blocks:  int = 100,
) -> float:
    """
    Adaptation Speed = 1 - (detection_lag / reference_lag)
    detection_lag: blocks from pattern change to detection
    reference_lag: baseline acceptable lag (100 blocks default)
    """
    if reference_lag_blocks <= 0:
        return 0.0
    ratio = detection_lag_blocks / reference_lag_blocks
    return max(0.0, 1.0 - ratio)


def compute_love(
    right_to_invisibility_enforced: bool,
    awa_conditions_met:             bool,
    public_good_contribution:       float,  # Fraction [0, 1]
    gratitude_score:                float,  # Gratitude(t) = value_given / value_received
    sovereignty_dignity_active:     bool,
) -> float:
    """
    Love Protocol score — not a soft metric.
    Love = 0 activates F = 0 kill-switch.

    Love > 0 requires ALL of:
    - Right_to_Invisibility enforced
    - AWA conditions met
    - public_good_contribution >= 0.15 (15% minimum per charter)
    - gratitude_score >= 1.0 (giving more than taking)
    - Sovereignty_Dignity_Protocol active
    """
    if not right_to_invisibility_enforced:
        return 0.0
    if not awa_conditions_met:
        return 0.0
    if not sovereignty_dignity_active:
        return 0.0
    if gratitude_score < 1.0:
        return 0.0
    if public_good_contribution < 0.15:
        return 0.0

    # If all conditions met, score based on quality of contribution
    love = min(1.0, (
        0.30 * min(1.0, public_good_contribution / 0.30) +
        0.30 * min(1.0, gratitude_score / 2.0) +
        0.20 * (1.0 if right_to_invisibility_enforced else 0.0) +
        0.20 * (1.0 if sovereignty_dignity_active else 0.0)
    ))
    return max(0.01, love)  # > 0 iff conditions met


if __name__ == "__main__":
    # Self-test
    fit = compute_fitness(
        "nl_engine",
        pa=0.85, ice=0.78, adaptation_speed=0.92, love=0.80
    )
    print(fit.description)
    assert fit.fitness > 0
    assert not fit.love_killed

    fit_zero = compute_fitness(
        "weaponized_component",
        pa=0.99, ice=0.99, adaptation_speed=0.99, love=0.0
    )
    print(fit_zero.description)
    assert fit_zero.fitness == 0.0
    assert fit_zero.love_killed

    print("L0.6 Evolutionary Fitness: PASS")
