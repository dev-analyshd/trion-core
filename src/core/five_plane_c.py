"""
Five-Plane Coherence Score C(t) — TRION L9
C(t) = alpha*Phi_adj + beta*M_adj + gamma*Sigma + delta*K + epsilon*A
Emergence verification: C(t) > max(any single plane).
Information conservation law: dI_TRION/dt >= 0.

All 6 whitepaper asset-type weight profiles included.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple, Dict, Optional
from enum import Enum


WEIGHT_PROFILES: Dict[str, Dict[str, float]] = {
    "NEW_TOKEN":        {"alpha": 0.40, "beta": 0.15, "gamma": 0.30, "delta": 0.10, "epsilon": 0.05},
    "MATURE_PROTOCOL":  {"alpha": 0.20, "beta": 0.30, "gamma": 0.20, "delta": 0.15, "epsilon": 0.15},
    "STABLECOIN":       {"alpha": 0.25, "beta": 0.35, "gamma": 0.25, "delta": 0.05, "epsilon": 0.10},
    "GOVERNANCE_TOKEN": {"alpha": 0.15, "beta": 0.20, "gamma": 0.25, "delta": 0.25, "epsilon": 0.15},
    "BRIDGE_ASSET":     {"alpha": 0.30, "beta": 0.25, "gamma": 0.30, "delta": 0.05, "epsilon": 0.10},
    "WRAPPED_ASSET":    {"alpha": 0.20, "beta": 0.25, "gamma": 0.35, "delta": 0.05, "epsilon": 0.15},
}

THETA_MIN = 0.55
THETA_MAX = 0.92


class SignalType(Enum):
    VALUATION            = "VALUATION"
    SILENCE              = "SILENCE"
    MANIPULATION_ALERT   = "MANIPULATION_ALERT"
    GENESIS_INFERENCE    = "GENESIS_INFERENCE"
    LIQUIDITY_HEALTH     = "LIQUIDITY_HEALTH"
    ECOSYSTEM_HEALTH     = "ECOSYSTEM_HEALTH"
    GOVERNANCE_INTEGRITY = "GOVERNANCE_INTEGRITY"
    SYSTEMIC_RISK        = "SYSTEMIC_RISK"
    RESURRECTION         = "RESURRECTION"
    FORK_DIVERGENCE      = "FORK_DIVERGENCE"
    DORMANCY             = "DORMANCY_CLASSIFICATION"
    TRAJECTORY_ANOMALY   = "TRAJECTORY_ANOMALY"
    CROSS_CHAIN          = "CROSS_CHAIN_CONTINUITY"
    TEMPORAL_ANOMALY     = "TEMPORAL_ANOMALY"
    BEHAVIORAL_SHIFT     = "BEHAVIORAL_SHIFT"
    VALIDATOR_HEALTH     = "VALIDATOR_HEALTH"
    AKASHIC_MILESTONE    = "AKASHIC_MILESTONE"
    NEGATIVE_SPACE       = "NEGATIVE_SPACE"
    SOVEREIGN_ASSESSMENT = "SOVEREIGN_ASSESSMENT"


@dataclass
class FivePlaneOutput:
    c_score:            float
    phi_adj:            float
    m_adj:              float
    sigma:              float
    k_score:            float
    a_score:            float
    weights_used:       Dict[str, float]
    asset_type:         str
    theta:              float
    ci_95:              Tuple[float, float]
    conf_genesis:       float
    tc_valid:           bool
    max_single_plane:   float = 0.0
    emergence_detected: bool  = False
    limiting_plane:     str   = "UNKNOWN"

    def signal_type(self) -> SignalType:
        if self.c_score >= self.theta and self.tc_valid:
            return SignalType.VALUATION
        return SignalType.SILENCE

    def to_dict(self) -> dict:
        return {
            "c_score":            self.c_score,
            "signal_type":        self.signal_type().value,
            "phi_adj":            self.phi_adj,
            "m_adj":              self.m_adj,
            "sigma":              self.sigma,
            "k_score":            self.k_score,
            "a_score":            self.a_score,
            "weights_used":       self.weights_used,
            "asset_type":         self.asset_type,
            "theta":              self.theta,
            "ci_95":              list(self.ci_95),
            "conf_genesis":       self.conf_genesis,
            "tc_valid":           self.tc_valid,
            "max_single_plane":   self.max_single_plane,
            "emergence_detected": self.emergence_detected,
            "limiting_plane":     self.limiting_plane,
        }


def dynamic_threshold(volatility: float) -> float:
    """Theta(t) = Theta_min + (Theta_max - Theta_min) * V(t)"""
    v = max(0.0, min(1.0, volatility))
    return THETA_MIN + (THETA_MAX - THETA_MIN) * v


def compute_five_plane_c(
    phi_adj:      float,
    m_adj:        float,
    sigma:        float,
    k_score:      float,
    a_score:      float,
    asset_type:   str   = "MATURE_PROTOCOL",
    volatility:   float = 0.10,
    conf_genesis: float = 0.5,
    ci_95:        Tuple[float, float] = (0.0, 1.0),
    tc_valid:     bool  = True,
) -> FivePlaneOutput:
    """
    Full five-plane C(t) computation with emergence verification.
    All weights from whitepaper asset-type profiles.
    """
    w = WEIGHT_PROFILES.get(asset_type, WEIGHT_PROFILES["MATURE_PROTOCOL"])

    c = (w["alpha"]   * phi_adj
       + w["beta"]    * m_adj
       + w["gamma"]   * sigma
       + w["delta"]   * k_score
       + w["epsilon"] * a_score)
    c = round(max(0.0, min(1.0, c)), 6)

    theta     = dynamic_threshold(volatility)
    planes    = {"Phi_adj": phi_adj, "M_adj": m_adj, "Sigma": sigma,
                 "K": k_score, "A": a_score}
    max_plane = max(planes.values())
    limiting  = min(planes, key=planes.get)
    emergence = c > max_plane

    return FivePlaneOutput(
        c_score=c,
        phi_adj=phi_adj, m_adj=m_adj, sigma=sigma,
        k_score=k_score, a_score=a_score,
        weights_used=w, asset_type=asset_type,
        theta=theta, ci_95=ci_95,
        conf_genesis=conf_genesis, tc_valid=tc_valid,
        max_single_plane=round(max_plane, 6),
        emergence_detected=emergence,
        limiting_plane=limiting,
    )


def information_conservation_check(
    bh_generated: float,
    a_absorbed:   float,
    s_emitted:    float,
    e_lost:       float,
    prev_i_trion: float,
) -> dict:
    """
    I_TRION(t) = I_TRION(t-1) + BH_generated + A_absorbed - S_emitted - E_lost
    Thermodynamic constraint: dI_TRION/dt >= 0 ALWAYS.
    Returns conservation status and violation flag.
    """
    di_dt   = bh_generated + a_absorbed - s_emitted - e_lost
    i_trion = prev_i_trion + di_dt
    return {
        "i_trion":   round(i_trion, 6),
        "di_dt":     round(di_dt, 6),
        "conserved": di_dt >= 0,
        "violation": di_dt < 0,
    }
