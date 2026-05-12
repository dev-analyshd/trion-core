"""
TRION Coherence Score C(t) — Phase 6: 3-plane version
C(t) = alpha*Phi_adj(t) + beta*M_adj(t) + gamma*Sigma(t)  [delta=0, epsilon=0 until Phase 9]
All 6 asset-type weight profiles from whitepaper.
Dynamic threshold Theta(t) = Theta_min + (Theta_max - Theta_min) * V(t)
Silence Signal emitted when C(t) < Theta(t) — never suppressed.
"""
from dataclasses import dataclass, field
from typing import Optional, Tuple
from enum import Enum


WEIGHT_PROFILES = {
    "NEW_TOKEN":        {"alpha": 0.40, "beta": 0.15, "gamma": 0.30, "delta": 0.10, "epsilon": 0.05},
    "MATURE_PROTOCOL":  {"alpha": 0.20, "beta": 0.30, "gamma": 0.20, "delta": 0.15, "epsilon": 0.15},
    "STABLECOIN":       {"alpha": 0.25, "beta": 0.35, "gamma": 0.25, "delta": 0.05, "epsilon": 0.10},
    "GOVERNANCE_TOKEN": {"alpha": 0.15, "beta": 0.20, "gamma": 0.25, "delta": 0.25, "epsilon": 0.15},
    "BRIDGE_ASSET":     {"alpha": 0.30, "beta": 0.25, "gamma": 0.30, "delta": 0.05, "epsilon": 0.10},
    "WRAPPED_ASSET":    {"alpha": 0.20, "beta": 0.25, "gamma": 0.35, "delta": 0.05, "epsilon": 0.15},
}

THETA_MIN = 0.55
THETA_MAX = 0.92

WEIGHT_MODES = {
    "BALANCED":     {"alpha": 0.20, "beta": 0.20, "gamma": 0.20, "delta": 0.20, "epsilon": 0.20},
    "SPEED":        {"alpha": 0.30, "beta": 0.20, "gamma": 0.30, "delta": 0.10, "epsilon": 0.10},
    "INTELLIGENCE": {"alpha": 0.15, "beta": 0.20, "gamma": 0.15, "delta": 0.15, "epsilon": 0.35},
    "CERTAINTY":    {"alpha": 0.15, "beta": 0.35, "gamma": 0.25, "delta": 0.15, "epsilon": 0.10},
    "FULL_SPECTRUM":{"alpha": 0.20, "beta": 0.20, "gamma": 0.20, "delta": 0.20, "epsilon": 0.20},
}


class SignalType(Enum):
    VALUATION               = "VALUATION"
    GENESIS_INFERENCE       = "GENESIS_INFERENCE"
    SILENCE                 = "SILENCE"
    MANIPULATION_ALERT      = "MANIPULATION_ALERT"
    LIQUIDITY_HEALTH        = "LIQUIDITY_HEALTH"
    ECOSYSTEM_HEALTH        = "ECOSYSTEM_HEALTH"
    GOVERNANCE_INTEGRITY    = "GOVERNANCE_INTEGRITY"
    SYSTEMIC_RISK           = "SYSTEMIC_RISK"
    RESURRECTION            = "RESURRECTION"
    FORK_DIVERGENCE         = "FORK_DIVERGENCE"
    DORMANCY_CLASSIFICATION = "DORMANCY_CLASSIFICATION"
    TRAJECTORY_ANOMALY      = "TRAJECTORY_ANOMALY"
    CROSS_CHAIN_CONTINUITY  = "CROSS_CHAIN_CONTINUITY"
    TEMPORAL_ANOMALY        = "TEMPORAL_ANOMALY"
    BEHAVIORAL_SHIFT        = "BEHAVIORAL_SHIFT"
    VALIDATOR_HEALTH        = "VALIDATOR_HEALTH"
    AKASHIC_MILESTONE       = "AKASHIC_MILESTONE"
    NEGATIVE_SPACE          = "NEGATIVE_SPACE"
    SOVEREIGN_ASSESSMENT    = "SOVEREIGN_ASSESSMENT"


@dataclass
class TRIONSignal:
    signal_type:  SignalType
    asset_id:     str
    c_score:      Optional[float]

    phi_adj:  float = 0.0
    m_adj:    float = 0.0
    sigma:    float = 0.0
    k_score:  float = 0.0   # zero until Phase 8
    a_score:  float = 0.0   # zero until Phase 7 full

    ci_95:        Tuple[float, float] = (0.0, 0.0)
    conf_genesis: float = 0.0
    tc_valid:     bool  = False
    asset_type:   str   = "MATURE_PROTOCOL"
    weight_mode:  str   = "BALANCED"
    theta:        float = THETA_MIN

    c_gap:          Optional[float] = None
    limiting_plane: Optional[str]   = None
    eta_hours:      Optional[float] = None

    def is_silence(self) -> bool:
        return self.signal_type == SignalType.SILENCE

    def validate(self) -> list:
        errors = []
        if self.ci_95 is None:
            errors.append("CI_95 must never be null")
        elif self.ci_95[0] >= self.ci_95[1]:
            errors.append(f"CI_95 must be ordered: {self.ci_95}")
        if self.conf_genesis is None:
            errors.append("conf_genesis must never be null")
        if not self.tc_valid and self.signal_type == SignalType.VALUATION:
            errors.append("Temporal coherence must be valid for VALUATION signal")
        return errors


def compute_c_score(
    phi_adj:    float,
    m_adj:      float,
    sigma:      float,
    k_score:    float = 0.0,
    a_score:    float = 0.0,
    asset_type: str   = "MATURE_PROTOCOL",
    mode:       str   = "BALANCED",
) -> Tuple[float, dict]:
    """
    C(t) = alpha*Phi_adj + beta*M_adj + gamma*Sigma + delta*K + epsilon*A
    Weights from asset_type profile, normalized to active planes.
    """
    weights = dict(WEIGHT_PROFILES.get(asset_type, WEIGHT_PROFILES["MATURE_PROTOCOL"]))

    active = {}
    active["alpha"] = weights["alpha"]
    active["beta"]  = weights["beta"]
    active["gamma"] = weights["gamma"]
    if k_score > 0: active["delta"]   = weights["delta"]
    if a_score > 0: active["epsilon"] = weights["epsilon"]

    total_weight = sum(active.values())
    if total_weight == 0:
        return 0.0, weights

    norm_alpha   = weights["alpha"]   / total_weight
    norm_beta    = weights["beta"]    / total_weight
    norm_gamma   = weights["gamma"]   / total_weight
    norm_delta   = weights.get("delta",   0.0) / total_weight
    norm_epsilon = weights.get("epsilon", 0.0) / total_weight

    c = (norm_alpha * phi_adj + norm_beta * m_adj + norm_gamma * sigma
         + norm_delta * k_score + norm_epsilon * a_score)

    return round(max(0.0, min(1.0, c)), 6), weights


def dynamic_threshold(volatility: float) -> float:
    """Theta(t) = Theta_min + (Theta_max - Theta_min) * V(t)"""
    return THETA_MIN + (THETA_MAX - THETA_MIN) * max(0.0, min(1.0, volatility))


def emit_signal(
    asset_id:     str,
    phi_adj:      float,
    m_adj:        float,
    sigma:        float,
    conf_genesis: float,
    ci_95:        Tuple[float, float],
    tc_valid:     bool,
    volatility:   float = 0.10,
    asset_type:   str   = "MATURE_PROTOCOL",
    k_score:      float = 0.0,
    a_score:      float = 0.0,
) -> TRIONSignal:
    c_score, weights = compute_c_score(phi_adj, m_adj, sigma, k_score, a_score, asset_type)
    theta = dynamic_threshold(volatility)

    planes   = {"Phi_adj": phi_adj, "M_adj": m_adj, "Sigma": sigma}
    limiting = min(planes, key=planes.get)

    c_gap     = theta - c_score
    eta_hours = max(0.0, c_gap / 0.01) if c_gap > 0 else 0.0

    if c_score >= theta and tc_valid:
        return TRIONSignal(
            signal_type=SignalType.VALUATION,
            asset_id=asset_id,
            c_score=c_score,
            phi_adj=phi_adj, m_adj=m_adj, sigma=sigma,
            k_score=k_score, a_score=a_score,
            ci_95=ci_95, conf_genesis=conf_genesis,
            tc_valid=tc_valid, asset_type=asset_type,
            theta=theta,
        )
    else:
        return TRIONSignal(
            signal_type=SignalType.SILENCE,
            asset_id=asset_id,
            c_score=c_score,
            phi_adj=phi_adj, m_adj=m_adj, sigma=sigma,
            k_score=k_score, a_score=a_score,
            ci_95=ci_95, conf_genesis=conf_genesis,
            tc_valid=tc_valid, asset_type=asset_type,
            theta=theta,
            c_gap=round(c_gap, 6),
            limiting_plane=limiting,
            eta_hours=round(eta_hours, 1),
        )
