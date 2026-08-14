"""L5.4 — Master Equation: T(t) = [C≥Θ] · C(t) · e^(M_moat)

The Master Equation combines coherence, threshold, and moat into a single
output signal strength T(t). This is the final output of the TRION engine
that gets published on-chain via the oracle contracts.

Formula (whitepaper L5.4):
  T(t) = [C(t) ≥ Θ(t)] · C(t) · e^(M_moat(t))

Where:
  [C≥Θ] = 1 if coherent, 0 if silent (Heaviside step function)
  C(t)  = five-plane coherence score
  M_moat = economic moat factor (D·Q·R·X·F·N)

When C(t) < Θ(t), the system emits SILENCE — T(t) = 0.
When C(t) ≥ Θ(t), the signal strength is amplified by the economic moat.

The coherence computation lives in core/master/coherence.py.
This module provides the MasterEquation class that combines all components.
"""
import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class MasterEquationResult:
    t: float                # T(t) — final signal strength
    c: float                # C(t) — coherence score
    theta: float            # Θ(t) — dynamic threshold
    emits: bool             # [C≥Θ]
    moat_factor: float      # M_moat — economic moat multiplier
    margin: float           # C(t) - Θ(t)
    limiting_plane: str     # Which plane is constraining the score
    trend: str              # RISING / FALLING / STABLE
    silence_reason: Optional[str] = None


class MasterEquation:
    """
    L5.4 Master Equation: combines coherence, threshold, and moat.
    
    This is the final assembly point of the TRION engine. It takes the
    five-plane coherence score from CoherenceEngine, applies the dynamic
    threshold, and amplifies the result with the economic moat factor.
    """

    def compute(
        self,
        coherence_result: dict,
    ) -> MasterEquationResult:
        """
        Compute T(t) from a coherence engine result.

        Args:
            coherence_result: Output from CoherenceEngine.compute_coherence()

        Returns:
            MasterEquationResult with T(t) and all component values
        """
        C = coherence_result['C']
        theta = coherence_result['theta']
        emits = coherence_result['emits']
        margin = coherence_result['margin']
        moat = coherence_result.get('moat_factor', 1.0)
        limiting_plane = coherence_result.get('limiting_plane', 'unknown')
        trend = coherence_result.get('trend', 'STABLE')

        # T(t) = [C≥Θ] · C(t) · e^(M_moat)
        if emits:
            # Clamp moat exponent to prevent numerical explosion
            moat_exp = min(moat, 10.0)  # e^10 ≈ 22026 — reasonable upper bound
            T = C * math.exp(moat_exp)
            silence_reason = None
        else:
            T = 0.0
            silence_reason = (
                f"C={C:.4f} < Θ={theta:.4f}; "
                f"limiting_plane={limiting_plane}; "
                f"gap={abs(margin):.4f}"
            )

        return MasterEquationResult(
            t=T,
            c=C,
            theta=theta,
            emits=emits,
            moat_factor=moat,
            margin=margin,
            limiting_plane=limiting_plane,
            trend=trend,
            silence_reason=silence_reason,
        )

    def compute_from_planes(
        self,
        phi_adj: float,
        m_adj: float,
        sigma: float,
        k_plane: float,
        anima: float,
        volatility: float,
        akashic_depth: float,
        moat_time: float,
        profile: str = 'DEFAULT',
    ) -> MasterEquationResult:
        """Convenience: compute coherence first, then master equation."""
        from core.master.coherence import CoherenceEngine, CoherenceInput, AssetProfile
        
        profile_enum = AssetProfile(profile.upper()) if isinstance(profile, str) else profile
        engine = CoherenceEngine()
        coh_input = CoherenceInput(
            phi_adj=phi_adj,
            m_adj=m_adj,
            sigma=sigma,
            k_plane=k_plane,
            anima=anima,
            volatility=volatility,
            akashic_depth=akashic_depth,
            moat_time=moat_time,
            profile=profile_enum,
        )
        coh = engine.compute_coherence(coh_input)
        return self.compute(coh)


__all__ = ['MasterEquation', 'MasterEquationResult']
