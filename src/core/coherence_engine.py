"""
TRION Protocol — L5: Five-Plane Coherence C(t)
The Master Equation

C(t) = α·Φ_adj(t) + β·M_adj(t) + γ·Σ(t) + δ·K(t) + ε·A(t)

Dynamic threshold:
Θ(t) = Θ_min + (Θ_max - Θ_min) × V(t)
Θ_min = 0.55, Θ_max = 0.92

WEIGHT PROFILES (per whitepaper L5.2):
DEFAULT_BALANCED:    α=0.25, β=0.30, γ=0.25, δ=0.10, ε=0.10
NEW_TOKEN (<90d):    α=0.40, β=0.15, γ=0.30, δ=0.10, ε=0.05
MATURE_PROTOCOL:     α=0.20, β=0.30, γ=0.20, δ=0.15, ε=0.15
STABLECOIN:          α=0.25, β=0.35, γ=0.25, δ=0.05, ε=0.10
GOVERNANCE_TOKEN:    α=0.15, β=0.20, γ=0.25, δ=0.25, ε=0.15
BRIDGE_ASSET:        α=0.30, β=0.25, γ=0.30, δ=0.05, ε=0.10
WRAPPED_ASSET:       α=0.20, β=0.25, γ=0.35, δ=0.05, ε=0.15
"""

import math
from enum import Enum
from dataclasses import dataclass


THETA_MIN = 0.55
THETA_MAX = 0.92


class AssetProfile(str, Enum):
    DEFAULT    = "DEFAULT"
    NEW_TOKEN  = "NEW_TOKEN"
    MATURE     = "MATURE_PROTOCOL"
    STABLECOIN = "STABLECOIN"
    GOVERNANCE = "GOVERNANCE_TOKEN"
    BRIDGE     = "BRIDGE_ASSET"
    WRAPPED    = "WRAPPED_ASSET"


WEIGHT_PROFILES = {
    AssetProfile.DEFAULT:    {"alpha":0.25,"beta":0.30,"gamma":0.25,"delta":0.10,"epsilon":0.10},
    AssetProfile.NEW_TOKEN:  {"alpha":0.40,"beta":0.15,"gamma":0.30,"delta":0.10,"epsilon":0.05},
    AssetProfile.MATURE:     {"alpha":0.20,"beta":0.30,"gamma":0.20,"delta":0.15,"epsilon":0.15},
    AssetProfile.STABLECOIN: {"alpha":0.25,"beta":0.35,"gamma":0.25,"delta":0.05,"epsilon":0.10},
    AssetProfile.GOVERNANCE: {"alpha":0.15,"beta":0.20,"gamma":0.25,"delta":0.25,"epsilon":0.15},
    AssetProfile.BRIDGE:     {"alpha":0.30,"beta":0.25,"gamma":0.30,"delta":0.05,"epsilon":0.10},
    AssetProfile.WRAPPED:    {"alpha":0.20,"beta":0.25,"gamma":0.35,"delta":0.05,"epsilon":0.15},
}


@dataclass
class CoherenceInput:
    phi_adj:      float
    m_adj:        float
    sigma:        float
    k_plane:      float
    anima:        float
    volatility:   float
    akashic_depth: float
    moat_time:    float
    profile:      AssetProfile = AssetProfile.DEFAULT


class CoherenceEngine:

    def __init__(self):
        self._history: list = []   # Rolling window of recent C(t) values
        self._HISTORY_MAX = 20

    def compute_threshold(self, volatility: float) -> float:
        """Θ(t) = Θ_min + (Θ_max - Θ_min) × V(t)"""
        return THETA_MIN + (THETA_MAX - THETA_MIN) * min(1.0, max(0.0, volatility))

    def _compute_trend(self, C: float) -> str:
        """
        Compute C(t) trend from rolling history.
        RISING:  C is increasing over recent window (slope > +0.02)
        FALLING: C is declining over recent window (slope < -0.02)
        STABLE:  C is roughly flat (|slope| <= 0.02)
        """
        self._history.append(C)
        if len(self._history) > self._HISTORY_MAX:
            self._history = self._history[-self._HISTORY_MAX:]

        n = len(self._history)
        if n < 3:
            return "STABLE"

        recent = self._history[-min(n, 5):]
        r = len(recent)
        if r < 2:
            return "STABLE"

        x_mean = (r - 1) / 2.0
        y_mean = sum(recent) / r
        num    = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(recent))
        denom  = sum((i - x_mean) ** 2 for i in range(r))
        slope  = num / denom if denom > 0 else 0.0

        if slope > 0.02:
            return "RISING"
        if slope < -0.02:
            return "FALLING"
        return "STABLE"

    def compute_coherence(self, inp: CoherenceInput) -> dict:
        w = WEIGHT_PROFILES[inp.profile]

        weight_sum = sum(w.values())
        assert abs(weight_sum - 1.0) < 1e-9, f"Weights sum to {weight_sum}"

        C = (
            w["alpha"]   * inp.phi_adj  +
            w["beta"]    * inp.m_adj    +
            w["gamma"]   * inp.sigma    +
            w["delta"]   * inp.k_plane  +
            w["epsilon"] * inp.anima
        )
        C = max(0.0, min(1.0, C))

        theta  = self.compute_threshold(inp.volatility)
        emits  = C >= theta
        margin = C - theta
        trend  = self._compute_trend(C)

        plane_values = {
            "physical":  inp.phi_adj * w["alpha"],
            "mental":    inp.m_adj   * w["beta"],
            "spiritual": inp.sigma   * w["gamma"],
            "conscious": inp.k_plane * w["delta"],
            "anima":     inp.anima   * w["epsilon"],
        }
        limiting_plane = min(plane_values, key=plane_values.get)

        if not emits and margin < 0:
            gap        = abs(margin)
            eta_blocks = int(gap * 1000)
        else:
            eta_blocks = 0

        # Whitepaper L0.5: M_moat(t) = D(t) · Q(t) · R(t) · X(t) · F(t) · N(t)
        # Six multiplicative factors — each in (0, 1]:
        #   D = Akashic depth factor  (data moat)
        #   Q = Quality factor        (signal quality from validator diversity)
        #   R = Reflexivity factor    (observer-effect resistance)
        #   X = Cross-chain factor    (multi-chain coverage breadth)
        #   F = Falsifiability factor (15-condition falsifiability registry)
        #   N = Network factor        (moat durability over time)
        D_factor = min(1.0, math.log(1 + inp.akashic_depth / 1000) / math.log(1 + 10.0))
        Q_factor = min(1.0, inp.k_plane + 0.15)          # k-plane (conscious) as quality proxy
        R_factor = min(1.0, 1.0 - 0.30 * (inp.m_adj - 0.5) ** 2) if inp.m_adj >= 0 else 0.7
        X_factor = min(1.0, math.log(1 + inp.akashic_depth / 5000) / math.log(3))   # chain breadth
        F_factor = 0.90  # falsifiability registry baseline (updated by governance votes)
        N_factor = math.exp(-inp.moat_time / 1e8) if inp.moat_time > 0 else 1.0      # decay over time
        moat_factor = D_factor * Q_factor * R_factor * X_factor * F_factor * N_factor
        moat_factor = min(1.0, max(0.0, moat_factor))
        # Also expose legacy scalar
        M_moat = math.log(1 + inp.akashic_depth / 10000)

        return {
            "C":               C,
            "theta":           theta,
            "margin":          margin,
            "emits":           emits,
            "silence":         not emits,
            "coherence_gap":   max(0, theta - C),
            "limiting_plane":  limiting_plane,
            "trend":           trend,
            "eta_blocks":      eta_blocks,
            "moat_factor":     moat_factor,
            "moat_components": {
                "D_data":          round(D_factor, 6),
                "Q_quality":       round(Q_factor, 6),
                "R_reflexivity":   round(R_factor, 6),
                "X_crosschain":    round(X_factor, 6),
                "F_falsifiability": F_factor,
                "N_network":       round(N_factor, 6),
            },
            "plane_breakdown": {
                "phi_adj":  inp.phi_adj,
                "m_adj":    inp.m_adj,
                "sigma":    inp.sigma,
                "k_plane":  inp.k_plane,
                "anima":    inp.anima,
            },
            "weights":         w,
            "profile":         inp.profile.value,
            "bootstrap_planes": {
                "sigma_bootstrap": inp.sigma   <= 0.26,
                "k_bootstrap":     inp.k_plane <= 0.11,
                "anima_bootstrap": inp.anima   <= 0.11,
            },
            "akashic_depth":   inp.akashic_depth,
        }

    def apply_mf_to_phi(self, phi_raw: float, mf_score: float) -> float:
        return phi_raw * (1.0 - mf_score)

    def apply_oe_to_m(self, m_base: float, oe_factor: float) -> float:
        return max(0.0, m_base * (1.0 - oe_factor))


if __name__ == "__main__":
    engine = CoherenceEngine()

    normal = CoherenceInput(
        phi_adj=0.72, m_adj=0.68, sigma=0.25,
        k_plane=0.10, anima=0.10,
        volatility=0.30, akashic_depth=500,
        moat_time=1000000, profile=AssetProfile.MATURE,
    )
    result = engine.compute_coherence(normal)
    print(f"Normal C(t)={result['C']:.4f} Θ={result['theta']:.4f} emits={result['emits']}")

    attack = CoherenceInput(
        phi_adj=0.05, m_adj=0.40, sigma=0.25,
        k_plane=0.10, anima=0.10,
        volatility=0.80, akashic_depth=500,
        moat_time=1000000, profile=AssetProfile.MATURE,
    )
    result_attack = engine.compute_coherence(attack)
    print(f"Attack C(t)={result_attack['C']:.4f} Θ={result_attack['theta']:.4f} SILENCE={result_attack['silence']}")
    assert result_attack['silence'], "Attack should produce SILENCE"
    print(f"  Limiting plane: {result_attack['limiting_plane']}")
    print("PHASE 14 PASS — C(t) master equation implemented")
