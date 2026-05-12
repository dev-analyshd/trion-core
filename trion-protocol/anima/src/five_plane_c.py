"""
Five-Plane Full C(t) — TRION L9
C(t) = alpha*Phi_adj(t) + beta*M_adj(t) + gamma*Sigma(t) + delta*K(t) + epsilon*A(t)
Emergence verification: C(t) accuracy > max(any single plane)
"""
from dataclasses import dataclass
from typing import Tuple
from coherence_score import WEIGHT_PROFILES, dynamic_threshold, SignalType


@dataclass
class FivePlaneOutput:
    c_score:    float
    phi_adj:    float
    m_adj:      float
    sigma:      float
    k_score:    float
    a_score:    float
    weights_used:  dict
    asset_type:    str
    theta:         float
    ci_95:         Tuple[float, float]
    conf_genesis:  float
    tc_valid:      bool
    max_single_plane: float = 0.0
    emergence_detected: bool = False

    def signal_type(self) -> SignalType:
        if self.c_score >= self.theta and self.tc_valid:
            return SignalType.VALUATION
        return SignalType.SILENCE


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
    w = WEIGHT_PROFILES.get(asset_type, WEIGHT_PROFILES["MATURE_PROTOCOL"])

    c = (w["alpha"]   * phi_adj
       + w["beta"]    * m_adj
       + w["gamma"]   * sigma
       + w["delta"]   * k_score
       + w["epsilon"] * a_score)
    c = round(max(0.0, min(1.0, c)), 6)

    theta     = dynamic_threshold(volatility)
    max_plane = max(phi_adj, m_adj, sigma, k_score, a_score)
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
    )


def information_conservation_check(
    bh_generated: float,
    a_absorbed:   float,
    s_emitted:    float,
    e_lost:       float,
    prev_i_trion: float,
) -> dict:
    """
    I_TRION(t) = BH_generated + A_absorbed - S_emitted - E_lost
    dI_TRION/dt >= 0 ALWAYS — Thermodynamic Information Conservation
    """
    i_trion = prev_i_trion + bh_generated + a_absorbed - s_emitted - e_lost
    di_dt   = bh_generated + a_absorbed - s_emitted - e_lost
    conserved = di_dt >= 0
    return {
        "i_trion":   round(i_trion, 6),
        "di_dt":     round(di_dt, 6),
        "conserved": conserved,
        "violation": not conserved,
    }
