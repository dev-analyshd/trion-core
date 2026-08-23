"""
TRION Protocol — Love Protocol (Fitness Function Coefficient)
==============================================================

Whitepaper §20 specifies the "Love Protocol" — the F coefficient in the
master moat equation M_moat = D · Q · R · X · F · N.

F = 0 if Love = 0

"Love" here is operationalized as the protocol's commitment to:
  - Public Good Charter enforcement (≥15% revenue)
  - Indigenous Knowledge Interface respect
  - Right to Invisibility enforcement
  - Gratitude Protocol reciprocity
  - Elder Wisdom inclusion
  - Unknown-Unknown Provision (10% revenue reserve)

If ANY of these commitments is fully absent (score = 0), then F = 0
and the entire moat collapses to zero.  This is by design: a protocol
that fails its ethical commitments has no durable moat.

The Love coefficient is computed as the minimum of these six sub-scores
(not the average) — the weakest link determines the protocol's moral
authority, which is the whitepaper's intent.

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


# ── Sub-score identifiers ──────────────────────────────────────────────────────

# The six pillars of the Love coefficient
PILLARS = (
    "public_good_charter",     # ≥15% revenue to public goods
    "indigenous_knowledge",    # Indigenous Knowledge Interface
    "right_to_invisibility",   # Right to Invisibility enforcement
    "gratitude_protocol",      # Gratitude Protocol reciprocity
    "elder_wisdom",            # Elder Wisdom inclusion
    "unknown_unknown",         # 10% revenue reserve
)


# ── Data Model ─────────────────────────────────────────────────────────────────

@dataclass
class LoveInputs:
    """The six sub-scores that feed into the Love coefficient.

    Each sub-score ∈ [0, 1]:
      1.0 = fully embodied
      0.5 = partially implemented
      0.0 = absent / violated
    """
    public_good_charter:    float = 1.0
    indigenous_knowledge:   float = 1.0
    right_to_invisibility:  float = 1.0
    gratitude_protocol:     float = 1.0
    elder_wisdom:           float = 1.0
    unknown_unknown:        float = 1.0

    def to_dict(self) -> dict:
        return {
            "public_good_charter":   self.public_good_charter,
            "indigenous_knowledge":  self.indigenous_knowledge,
            "right_to_invisibility": self.right_to_invisibility,
            "gratitude_protocol":    self.gratitude_protocol,
            "elder_wisdom":          self.elder_wisdom,
            "unknown_unknown":       self.unknown_unknown,
        }


@dataclass
class LoveResult:
    """Output of the Love coefficient computation."""
    F_love:              float                  # final Love coefficient ∈ [0, 1]
    pillar_scores:       Dict[str, float]       # individual sub-scores
    weakest_pillar:      str                    # which pillar determined F
    moat_collapse:       bool                   # True iff F == 0
    rationale:           str

    def to_dict(self) -> dict:
        return {
            "F_love":          self.F_love,
            "pillar_scores":   self.pillar_scores,
            "weakest_pillar":  self.weakest_pillar,
            "moat_collapse":   self.moat_collapse,
            "rationale":       self.rationale,
        }


# ── Engine ─────────────────────────────────────────────────────────────────────

class LoveProtocol:
    """
    Computes the Love coefficient F for the master moat equation.

    F = min(public_good_charter, indigenous_knowledge, right_to_invisibility,
            gratitude_protocol, elder_wisdom, unknown_unknown)

    If any pillar is 0, F = 0 and the moat collapses.
    """

    @staticmethod
    def compute(inputs: LoveInputs) -> LoveResult:
        scores = {
            "public_good_charter":   inputs.public_good_charter,
            "indigenous_knowledge":  inputs.indigenous_knowledge,
            "right_to_invisibility": inputs.right_to_invisibility,
            "gratitude_protocol":    inputs.gratitude_protocol,
            "elder_wisdom":          inputs.elder_wisdom,
            "unknown_unknown":       inputs.unknown_unknown,
        }

        # Clamp each to [0, 1]
        clamped = {k: max(0.0, min(1.0, v)) for k, v in scores.items()}

        # Find the weakest pillar
        weakest_pillar = min(clamped, key=clamped.get)
        F = clamped[weakest_pillar]
        moat_collapse = (F == 0.0)

        if moat_collapse:
            rationale = (
                f"Moat collapse: pillar '{weakest_pillar}' score is 0. "
                f"Per whitepaper §20: F = 0 if Love = 0. "
                f"The entire moat M_moat collapses to 0."
            )
        else:
            rationale = (
                f"F = {F:.4f} determined by weakest pillar '{weakest_pillar}'. "
                f"All six pillars are non-zero — moat intact."
            )

        return LoveResult(
            F_love=F,
            pillar_scores=clamped,
            weakest_pillar=weakest_pillar,
            moat_collapse=moat_collapse,
            rationale=rationale,
        )

    @staticmethod
    def integrate_with_moat(
        moat_without_F: float,
        love_inputs:    LoveInputs,
    ) -> dict:
        """
        Integrate F into the master moat equation.

        M_moat = D · Q · R · X · F · N

        Args:
            moat_without_F: the product D · Q · R · X · N (without F)
            love_inputs:    the six Love sub-scores

        Returns:
            dict with M_moat, F, and collapse status
        """
        love_result = LoveProtocol.compute(love_inputs)
        M_moat = moat_without_F * love_result.F_love

        return {
            "M_moat":          M_moat,
            "F_love":          love_result.F_love,
            "moat_collapse":   love_result.moat_collapse,
            "pillar_scores":   love_result.pillar_scores,
            "weakest_pillar":  love_result.weakest_pillar,
            "rationale":       love_result.rationale,
            "formula":         "M_moat = D · Q · R · X · F · N  (F = min of 6 pillars)",
        }


# ── Self-test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Love Protocol Self-test ===\n")

    # Test 1: All pillars maxed → F = 1.0
    inputs_full = LoveInputs()
    result = LoveProtocol.compute(inputs_full)
    print(f"All pillars = 1.0: F = {result.F_love}")
    assert result.F_love == 1.0
    assert not result.moat_collapse

    # Test 2: One pillar at 0 → F = 0, moat collapse
    inputs_collapsed = LoveInputs(public_good_charter=0.0)
    result = LoveProtocol.compute(inputs_collapsed)
    print(f"Public Good Charter = 0: F = {result.F_love}, collapse = {result.moat_collapse}")
    assert result.F_love == 0.0
    assert result.moat_collapse
    assert result.weakest_pillar == "public_good_charter"

    # Test 3: Mixed scores → F = minimum
    inputs_mixed = LoveInputs(
        public_good_charter=0.9,
        indigenous_knowledge=0.7,
        right_to_invisibility=0.5,
        gratitude_protocol=0.8,
        elder_wisdom=0.6,
        unknown_unknown=0.4,
    )
    result = LoveProtocol.compute(inputs_mixed)
    print(f"Mixed scores: F = {result.F_love} (weakest: {result.weakest_pillar})")
    assert result.F_love == 0.4
    assert result.weakest_pillar == "unknown_unknown"
    assert not result.moat_collapse

    # Test 4: Integration with moat
    integration = LoveProtocol.integrate_with_moat(
        moat_without_F=0.75,  # D · Q · R · X · N
        love_inputs=inputs_mixed,
    )
    print(f"\nMoat integration:")
    print(f"  D·Q·R·X·N = 0.75")
    print(f"  F = {integration['F_love']}")
    print(f"  M_moat = {integration['M_moat']}")
    assert integration["M_moat"] == 0.75 * 0.4

    # Test 5: Collapse integration
    collapse = LoveProtocol.integrate_with_moat(
        moat_without_F=0.99,
        love_inputs=inputs_collapsed,
    )
    print(f"\nCollapse scenario:")
    print(f"  D·Q·R·X·N = 0.99")
    print(f"  F = {collapse['F_love']}")
    print(f"  M_moat = {collapse['M_moat']}")
    assert collapse["M_moat"] == 0.0
    assert collapse["moat_collapse"]

    print("\nPHASE 7 PASS — Love Protocol (F coefficient) implemented")
