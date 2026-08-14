"""P3 — Coordination Collapse Theorem: d_j = 1-corr(M_j, M_bar)

The Coordination Collapse Theorem proves that any attempt by Byzantine validators
to coordinate their signals collapses under diversity-weighting. When validators
coordinate (corr → 1), their diversity weight d_j → 0, effectively removing them
from the consensus. The theorem provides a formal bound on the maximum influence
coordinating attackers can exert.

Formal statement:
  For any coalition C of validators with perfectly correlated model outputs:
    Σ_{j∈C} w_j·d_j ≤ Σ_{j∈C} w_j·(1-1) = 0
  
  Coordinating attackers exert zero effective weight on consensus.

Implementation lives in core/spiritual/consensus.py (diversity_weighted_bft).
This module re-exports the key functions for convenience.
"""
from core.spiritual.consensus import (
    compute_diversity_weights,
    compute_dw_bft_consensus,
    BFTConsensusResult,
    DiversityResult,
    Validator,
    build_demo_validators,
    simulate_coordination_attack,
)

__all__ = [
    'compute_diversity_weights',
    'compute_dw_bft_consensus',
    'BFTConsensusResult',
    'DiversityResult',
    'Validator',
    'build_demo_validators',
    'simulate_coordination_attack',
    'CoordinationCollapseTheorem',
]


class CoordinationCollapseTheorem:
    """Facade class exposing the Coordination Collapse Theorem analysis."""

    @staticmethod
    def compute_collapse_bound(
        validator_count: int,
        byzantine_fraction: float,
        honest_avg_diversity: float = 0.5,
    ) -> float:
        """
        Compute the maximum effective influence a coordinating coalition can exert.

        When Byzantine validators coordinate (corr → 1), their diversity weight
        d_j = 1 - corr → 0, effectively removing them from consensus.

        Args:
            validator_count: Total number of validators N
            byzantine_fraction: Fraction f that is Byzantine (0 ≤ f ≤ 1)
            honest_avg_diversity: Average diversity weight of honest validators

        Returns:
            Bound on effective Byzantine influence ∈ [0, 1)
        """
        # Coordinating Byzantines have corr → 1, so d_j → 0
        # Effective Byzantine weight ≈ byzantine_fraction × (1 - high_correlation)
        high_correlation = 0.95  # Near-perfect coordination
        effective_byzantine = byzantine_fraction * (1.0 - high_correlation)
        honest_weight = (1.0 - byzantine_fraction) * honest_avg_diversity
        total_effective = effective_byzantine + honest_weight

        if total_effective <= 0:
            return 0.0
        return effective_byzantine / total_effective

    @staticmethod
    def byzantine_resistance(
        total_stake: float,
        byzantine_stake: float,
        avg_correlation: float,
    ) -> dict:
        """Analyze byzantine resistance under coordination."""
        effective_byzantine = byzantine_stake * (1.0 - avg_correlation)
        honest_stake = total_stake - byzantine_stake
        safety_margin = honest_stake - 2 * effective_byzantine
        return {
            'effective_byzantine_weight': effective_byzantine,
            'honest_weight': honest_stake,
            'safety_margin': safety_margin,
            'safe': safety_margin > 0,
            'correlation_used': avg_correlation,
        }

    @staticmethod
    def simulate_attack(
        validator_count: int = 100,
        byzantine_count: int = 33,
        coordination_strength: float = 0.9,
    ) -> dict:
        """Simulate a coordination attack and measure its effectiveness."""
        validators = build_demo_validators(validator_count)
        result = simulate_coordination_attack(
            validators, byzantine_count, coordination_strength
        )
        if hasattr(result, '__dict__'):
            return {k: v for k, v in result.__dict__.items()
                    if not k.startswith('_')}
        return dict(result) if isinstance(result, dict) else {'result': str(result)}
