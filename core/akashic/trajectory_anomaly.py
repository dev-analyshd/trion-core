"""
TRION Protocol — L2.7 Trajectory Anomaly Monitor
Chapter 7.1: Genesis Inference — Adversarial Protection

TRAJ_ANOMALY(asset, t) = KL_divergence(P_actual, P_expected(matched_archetype))

When TRAJ_ANOMALY > θ_anomaly:
    - Genesis Signal invalidated
    - MANIPULATION_ALERT raised
    - conf_genesis locked (stops growing)

KL divergence measures how much P_actual (observed behavior) differs
from P_expected (what the matched archetype predicts). High KL = behavioral
divergence from archetype expectation = anomaly.

KL(P || Q) = Σ_i P(i) · log(P(i) / Q(i))

Also used for ANIMA pre-manifestation signals:
    TRAJECTORY signal contains full probability distribution of expected behavioral
    sequences, not point predictions.

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations
import math
import statistics
from dataclasses import dataclass
from typing import Optional


# Default anomaly threshold — KL divergence above this triggers alert.
# Used as a fallback when no historical KL data is available (per whitepaper
# L2.7 spec: "If insufficient history exists, fall back to 0.50").
THETA_ANOMALY_DEFAULT: float = 0.50

# Per whitepaper L2.7 spec: "If TRAJ_ANOMALY > θ_anomaly (> 2 standard
# deviations)". The statistical threshold is computed as
#     θ_anomaly = mean(historical_KL) + THETA_STD_MULTIPLIER · stdev(historical_KL)
THETA_STD_MULTIPLIER: float = 2.0

# Minimum number of historical KL observations required to estimate a
# meaningful mean and standard deviation. Below this we fall back to the
# fixed default threshold (0.50). statistics.stdev requires at least 2
# data points; we use a slightly higher bar to get a stable estimate.
MIN_HISTORY_FOR_STATISTICAL_THRESHOLD: int = 5


def compute_dynamic_theta(
    historical_kl_values: Optional[list[float]] = None,
    std_multiplier: float = THETA_STD_MULTIPLIER,
    fallback: float = THETA_ANOMALY_DEFAULT,
) -> float:
    """
    Compute the dynamic anomaly threshold θ_anomaly per whitepaper L2.7 spec:
    "If TRAJ_ANOMALY > θ_anomaly (> 2 standard deviations)".

        θ_anomaly = mean(historical_KL) + std_multiplier · stdev(historical_KL)

    If insufficient history exists (fewer than
    MIN_HISTORY_FOR_STATISTICAL_THRESHOLD observations), fall back to
    THETA_ANOMALY_DEFAULT = 0.50.

    Args:
        historical_kl_values: prior KL divergence observations for the same
            entity (or archetype baseline). Each entry is a single
            KL(P_actual || P_expected) measurement from a prior window.
        std_multiplier: how many standard deviations above the mean
            constitutes an anomaly (whitepaper default: 2.0).
        fallback: threshold used when historical data is insufficient.

    Returns:
        θ_anomaly — KL divergence above this triggers MANIPULATION_ALERT.
    """
    if not historical_kl_values:
        return fallback
    if len(historical_kl_values) < MIN_HISTORY_FOR_STATISTICAL_THRESHOLD:
        return fallback
    try:
        mean_kl = statistics.fmean(historical_kl_values)
        stdev_kl = statistics.stdev(historical_kl_values)
    except statistics.StatisticsError:
        # Defensive: stdev requires ≥2 data points; we already checked above,
        # but guard against degenerate inputs (e.g. all values equal → stdev=0).
        return fallback
    return mean_kl + std_multiplier * stdev_kl


@dataclass
class TrajectoryDistribution:
    """
    Probability distribution over behavioral outcomes.
    P_actual: what we observe.
    P_expected: what the matched archetype predicts.

    Both must sum to 1.0. Same support (outcome categories).
    """
    outcomes:  list[str]    # Outcome category labels
    probs:     list[float]  # Probability for each outcome


@dataclass
class TrajectoryAnomalyResult:
    """
    TRAJ_ANOMALY output with full diagnostic information.
    """
    entity_id:           str
    kl_divergence:       float   # KL(P_actual || P_expected)
    theta_anomaly:       float   # Threshold for alert
    anomaly_detected:    bool    # kl_divergence > theta_anomaly
    genesis_invalidated: bool    # Genesis signal locked
    alert_type:          Optional[str]
    dominant_deviation:  Optional[str]  # Outcome with largest deviation
    p_actual:            list[float]
    p_expected:          list[float]
    reflexivity_flag:    bool    # True if anomaly may be self-caused by TRION signal


def kl_divergence(p_actual: list[float], p_expected: list[float], epsilon: float = 1e-10) -> float:
    """
    KL(P || Q) = Σ_i P(i) · log(P(i) / Q(i))

    epsilon prevents log(0). P and Q must have same length.
    Result is always >= 0 (Gibbs inequality). KL = 0 iff P = Q.
    """
    n = min(len(p_actual), len(p_expected))
    if n == 0:
        return 0.0

    # Normalize to ensure valid distributions
    sum_p = sum(p_actual[:n])
    sum_q = sum(p_expected[:n])

    p = [max(epsilon, x / sum_p) for x in p_actual[:n]] if sum_p > 0 else [epsilon] * n
    q = [max(epsilon, x / sum_q) for x in p_expected[:n]] if sum_q > 0 else [epsilon] * n

    return sum(p[i] * math.log(p[i] / q[i]) for i in range(n))


def compute_trajectory_anomaly(
    entity_id:              str,
    p_actual:               TrajectoryDistribution,
    p_expected:             TrajectoryDistribution,
    theta_anomaly:          float = THETA_ANOMALY_DEFAULT,
    in_genesis:             bool  = True,
    reflexivity_oe:         float = 0.0,  # Observer Effect factor [0, 1]
    historical_kl_values:   Optional[list[float]] = None,
) -> TrajectoryAnomalyResult:
    """
    Compute KL(P_actual || P_expected) and determine if anomaly threshold exceeded.

    Per whitepaper L2.7 spec: "If TRAJ_ANOMALY > θ_anomaly (> 2 standard
    deviations)". When `historical_kl_values` is provided (≥ MIN_HISTORY
    observations), θ_anomaly is computed dynamically as
        θ_anomaly = mean(historical_KL) + 2 · stdev(historical_KL)
    via compute_dynamic_theta(). If historical data is insufficient or
    absent, the threshold falls back to THETA_ANOMALY_DEFAULT = 0.50.

    If TRAJ_ANOMALY > theta_anomaly AND in_genesis:
        - Genesis signal invalidated (conf_genesis locked)
        - MANIPULATION_ALERT raised

    Args:
        historical_kl_values: optional prior KL divergence observations for
            the same entity/archetype baseline. When provided with sufficient
            history, overrides `theta_anomaly` with the dynamic 2-std threshold.

    reflexivity_oe: if high, anomaly may be caused by TRION's own prediction
    (reflexivity attack) rather than manipulation.
    """
    # Dynamic statistical threshold (whitepaper L2.7 spec: 2 std above mean).
    # If historical KL data is provided, this overrides the static `theta_anomaly`
    # parameter; otherwise we use whatever the caller passed (default 0.50).
    if historical_kl_values is not None:
        theta_anomaly = compute_dynamic_theta(historical_kl_values)

    if len(p_actual.probs) != len(p_expected.probs):
        # Truncate to shorter — different outcome spaces
        n = min(len(p_actual.probs), len(p_expected.probs))
        p_act = p_actual.probs[:n]
        p_exp = p_expected.probs[:n]
    else:
        p_act = p_actual.probs
        p_exp = p_expected.probs

    kl = kl_divergence(p_act, p_exp)

    anomaly = kl > theta_anomaly

    # Identify dominant deviation
    dominant_deviation = None
    if anomaly and p_actual.outcomes:
        n = min(len(p_actual.outcomes), len(p_act), len(p_exp))
        eps = 1e-10
        sum_p = sum(p_act) or 1.0
        sum_q = sum(p_exp) or 1.0
        deviations = []
        for i in range(n):
            pi = max(eps, p_act[i] / sum_p)
            qi = max(eps, p_exp[i] / sum_q)
            deviations.append((pi * math.log(pi / qi), p_actual.outcomes[i]))
        deviations.sort(reverse=True)
        dominant_deviation = deviations[0][1] if deviations else None

    # Reflexivity check: TRION's own signals may cause the anomaly
    reflexivity_flag = (reflexivity_oe > 0.50) and anomaly

    alert_type = None
    genesis_invalidated = False

    if anomaly:
        if reflexivity_flag:
            alert_type = "REFLEXIVITY_ANOMALY"  # May be self-caused
        elif kl > theta_anomaly * 3:
            alert_type = "SEVERE_MANIPULATION_ALERT"
            genesis_invalidated = in_genesis
        else:
            alert_type = "TRAJECTORY_ANOMALY"
            genesis_invalidated = in_genesis

    return TrajectoryAnomalyResult(
        entity_id          = entity_id,
        kl_divergence      = kl,
        theta_anomaly      = theta_anomaly,
        anomaly_detected   = anomaly,
        genesis_invalidated = genesis_invalidated,
        alert_type         = alert_type,
        dominant_deviation = dominant_deviation,
        p_actual           = p_act,
        p_expected         = p_exp,
        reflexivity_flag   = reflexivity_flag,
    )


def build_trajectory_signal(
    entity_id:         str,
    p_expected:        TrajectoryDistribution,
    manifestation_window_blocks: int,
    historical_matches: int,
    reflexivity_oe:    float = 0.0,
) -> dict:
    """
    Build a TRAJECTORY signal payload.
    Contains full probability distribution — NOT a point prediction.
    reflexivity_flag included per specification spec.
    """
    return {
        "signal_type":              "TRAJECTORY",
        "entity_id":                entity_id,
        "probability_distribution": dict(zip(p_expected.outcomes, p_expected.probs)),
        "manifestation_window_blocks": manifestation_window_blocks,
        "historical_match_count":   historical_matches,
        "reflexivity_flag":         reflexivity_oe > 0.30,
        "oe_factor":                reflexivity_oe,
        "note": (
            "ANIMA pre-manifestation signal. "
            "Full probability distribution, not point prediction. "
            "reflexivity_flag=True → OE_factor dampening applied."
        ),
    }


if __name__ == "__main__":
    # Test 1: Healthy trajectory (P_actual ≈ P_expected)
    outcomes = ["GROWTH", "STABLE", "DECLINE", "CRASH"]
    p_expected = TrajectoryDistribution(outcomes, [0.50, 0.30, 0.15, 0.05])
    p_actual_healthy = TrajectoryDistribution(outcomes, [0.48, 0.31, 0.16, 0.05])
    r_healthy = compute_trajectory_anomaly("healthy_token", p_actual_healthy, p_expected)
    print(f"Healthy: KL={r_healthy.kl_divergence:.6f} anomaly={r_healthy.anomaly_detected}")
    assert not r_healthy.anomaly_detected

    # Test 2: Manipulated trajectory (P_actual very different from P_expected)
    p_actual_manip = TrajectoryDistribution(outcomes, [0.02, 0.03, 0.05, 0.90])
    r_manip = compute_trajectory_anomaly("manipulated_token", p_actual_manip, p_expected, in_genesis=True)
    print(f"Manipulated: KL={r_manip.kl_divergence:.6f} anomaly={r_manip.anomaly_detected} "
          f"genesis_locked={r_manip.genesis_invalidated} dominant={r_manip.dominant_deviation}")
    assert r_manip.anomaly_detected
    assert r_manip.genesis_invalidated

    # Test 3: Build TRAJECTORY signal
    sig = build_trajectory_signal("entity_X", p_expected, 1000, 47, reflexivity_oe=0.25)
    print(f"TRAJECTORY signal: type={sig['signal_type']} matches={sig['historical_match_count']}")

    # Test 4: Dynamic 2-std threshold (whitepaper L2.7 spec)
    # Baseline healthy behavior with very low KL — fixed 0.50 threshold would
    # miss subtle anomalies, but mean + 2·std catches them.
    healthy_baseline = [0.001, 0.002, 0.001, 0.003, 0.002, 0.001, 0.002, 0.001]
    dynamic_theta = compute_dynamic_theta(healthy_baseline)
    import statistics as _st
    expected_theta = _st.fmean(healthy_baseline) + 2.0 * _st.stdev(healthy_baseline)
    print(f"Dynamic θ_anomaly = mean + 2·std = {dynamic_theta:.6f} "
          f"(expected {expected_theta:.6f})")
    assert abs(dynamic_theta - expected_theta) < 1e-9
    # A KL of 0.01 is below the fixed 0.50 threshold but ABOVE the dynamic
    # 2-std threshold — should trigger anomaly under dynamic threshold.
    p_actual_subtle = TrajectoryDistribution(outcomes, [0.42, 0.34, 0.18, 0.06])
    r_subtle = compute_trajectory_anomaly(
        "subtle_anomaly_token", p_actual_subtle, p_expected,
        historical_kl_values=healthy_baseline,
    )
    print(f"Subtle anomaly: KL={r_subtle.kl_divergence:.6f} "
          f"θ_dynamic={r_subtle.theta_anomaly:.6f} anomaly={r_subtle.anomaly_detected}")
    assert r_subtle.theta_anomaly < THETA_ANOMALY_DEFAULT  # dynamic < default
    assert r_subtle.anomaly_detected                      # caught by 2-std rule

    # Test 5: Insufficient history → fallback to 0.50
    theta_fallback = compute_dynamic_theta([0.01, 0.02])  # only 2 points
    assert theta_fallback == THETA_ANOMALY_DEFAULT
    theta_empty = compute_dynamic_theta(None)
    assert theta_empty == THETA_ANOMALY_DEFAULT
    print(f"Insufficient history fallback: θ={theta_fallback} (== {THETA_ANOMALY_DEFAULT})")

    print("L2.7 Trajectory Anomaly Monitor: PASS")
