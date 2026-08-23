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
from dataclasses import dataclass
from typing import Optional


# Default anomaly threshold — KL divergence above this triggers alert
THETA_ANOMALY_DEFAULT: float = 0.50


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
    entity_id:      str,
    p_actual:       TrajectoryDistribution,
    p_expected:     TrajectoryDistribution,
    theta_anomaly:  float = THETA_ANOMALY_DEFAULT,
    in_genesis:     bool  = True,
    reflexivity_oe: float = 0.0,  # Observer Effect factor [0, 1]
) -> TrajectoryAnomalyResult:
    """
    Compute KL(P_actual || P_expected) and determine if anomaly threshold exceeded.

    If TRAJ_ANOMALY > theta_anomaly AND in_genesis:
        - Genesis signal invalidated (conf_genesis locked)
        - MANIPULATION_ALERT raised

    reflexivity_oe: if high, anomaly may be caused by TRION's own prediction
    (reflexivity attack) rather than manipulation.
    """
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
    reflexivity_flag included per whitepaper spec.
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

    print("L2.7 Trajectory Anomaly Monitor: PASS")
