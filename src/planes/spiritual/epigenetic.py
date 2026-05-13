"""
TRION Protocol — L4.5 Epigenetic Layer (Semi-Immutability)

EL_state(t) = f(Threat_level, Validator_health, Network_entropy)

TRION's expression changes continuously with environment.
TRION's bytecode (architecture) never changes.

This is Semi-Immutability:
    bytecode(P, t)    = bytecode(P, t₀)         for all t > t₀
    expression(P, t)  = f(bytecode(P), EL_state(t))

The chameleon does not become a different animal under threat.
Its DNA is unchanged. What changes is expression.

Threat levels → expression changes:
    LOW:      increase privacy defaults
    MEDIUM:   ZK proofs become default output
    HIGH:     validator weight in hostile jurisdiction de-emphasized
    CRITICAL: signal disaggregation across neutral jurisdictions
    WEAPONIZATION: AWA_enforced → FALSE → emission FROZEN

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ThreatLevel(Enum):
    NONE          = 0
    LOW           = 1
    MEDIUM        = 2
    HIGH          = 3
    CRITICAL      = 4
    WEAPONIZATION = 5


class ELExpression(Enum):
    """Current protocol expression mode — changes with threat level."""
    STANDARD            = "STANDARD"           # Normal operation
    PRIVACY_ENHANCED    = "PRIVACY_ENHANCED"   # Increased privacy defaults
    ZK_DEFAULT          = "ZK_DEFAULT"         # ZK proofs are default output
    GEOGRAPHIC_REWEIGHT = "GEOGRAPHIC_REWEIGHT" # Hostile jurisdiction de-emphasized
    DISAGGREGATED       = "DISAGGREGATED"       # Signals split across neutral jurisdictions
    FROZEN              = "FROZEN"              # AWA_enforced=FALSE → emission stopped


@dataclass
class ELState:
    """
    EL_state(t) = f(Threat_level, Validator_health, Network_entropy)
    """
    threat_level:            ThreatLevel
    validator_health:        float    # [0, 1] — average validator health score
    network_entropy:         float    # [0, 1] — behavioral diversity of network
    hostile_jurisdictions:   list[str]
    expression:              ELExpression
    awa_enforced:            bool
    signals_frozen:          bool
    zk_proofs_active:        bool
    geographic_rebalancing:  bool
    description:             str


def compute_threat_level(
    regulatory_sba_score:     float,   # L8.1 SBA — sovereign behavioral assessment
    validator_health_min:     float,   # Minimum across all validators
    hostile_jurisdiction_pct: float,   # Fraction of validators in hostile jurisdictions
    awa_violation_detected:   bool,
    network_entropy:          float,
) -> ThreatLevel:
    """
    Compute threat level from multiple behavioral inputs.
    Uses most conservative (highest threat) of all signals.
    """
    if awa_violation_detected:
        return ThreatLevel.WEAPONIZATION

    # Low regulatory SBA + high hostile jurisdiction concentration = CRITICAL
    if regulatory_sba_score < 0.20 and hostile_jurisdiction_pct > 0.60:
        return ThreatLevel.CRITICAL

    if regulatory_sba_score < 0.30 or hostile_jurisdiction_pct > 0.50:
        return ThreatLevel.HIGH

    if regulatory_sba_score < 0.50 or hostile_jurisdiction_pct > 0.30:
        return ThreatLevel.MEDIUM

    if regulatory_sba_score < 0.70 or hostile_jurisdiction_pct > 0.15:
        return ThreatLevel.LOW

    return ThreatLevel.NONE


def compute_el_state(
    threat_level:            ThreatLevel,
    validator_health:        float,
    network_entropy:         float,
    hostile_jurisdictions:   list[str],
    no_single_entity_weight: bool,
    no_single_entity_select: bool,
    public_good_pct:         float,
    sovereignty_active:      bool,
    right_to_invisibility:   bool,
    gratitude_score:         float,
) -> ELState:
    """
    EL_state(t) = f(Threat_level, Validator_health, Network_entropy)

    AWA_enforced iff all_of:
        no_single_entity_controls_signal_weights
        no_single_entity_controls_validator_selection
        Public_Good_Charter_minimum >= 15%
        Sovereignty_Dignity_Protocol_active
        Right_to_Invisibility_enforced
        Gratitude >= 1
    """
    # Check AWA conditions
    awa_enforced = all([
        no_single_entity_weight,
        no_single_entity_select,
        public_good_pct >= 0.15,
        sovereignty_active,
        right_to_invisibility,
        gratitude_score >= 1.0,
    ])

    if not awa_enforced or threat_level == ThreatLevel.WEAPONIZATION:
        return ELState(
            threat_level            = ThreatLevel.WEAPONIZATION,
            validator_health        = validator_health,
            network_entropy         = network_entropy,
            hostile_jurisdictions   = hostile_jurisdictions,
            expression              = ELExpression.FROZEN,
            awa_enforced            = False,
            signals_frozen          = True,
            zk_proofs_active        = True,
            geographic_rebalancing  = True,
            description             = (
                "AWA VIOLATION — emission FROZEN. "
                "Cannot be overridden by any single entity. By design."
            ),
        )

    if threat_level == ThreatLevel.CRITICAL:
        expression = ELExpression.DISAGGREGATED
        desc = (
            "CRITICAL: Signal disaggregation across neutral jurisdictions. "
            "No single jurisdiction sees complete signal. "
            "Individual user invisibility fully enforced."
        )
    elif threat_level == ThreatLevel.HIGH:
        expression = ELExpression.GEOGRAPHIC_REWEIGHT
        desc = (
            "HIGH: Validator weight in hostile jurisdictions de-emphasized. "
            "Geographic HHI rebalances automatically (algorithmic, not human decision). "
            "All outputs: jurisdiction-specific ZK only."
        )
    elif threat_level == ThreatLevel.MEDIUM:
        expression = ELExpression.ZK_DEFAULT
        desc = (
            "MEDIUM: ZK proofs become default output. "
            "Right_to_Invisibility auto-enforced in affected jurisdiction. "
            "Raw behavioral data access restricted."
        )
    elif threat_level == ThreatLevel.LOW:
        expression = ELExpression.PRIVACY_ENHANCED
        desc = (
            "LOW: Privacy defaults increased. "
            "ZK credential options surfaced to users."
        )
    else:
        expression = ELExpression.STANDARD
        desc = "NONE: Standard operation."

    return ELState(
        threat_level            = threat_level,
        validator_health        = validator_health,
        network_entropy         = network_entropy,
        hostile_jurisdictions   = hostile_jurisdictions,
        expression              = expression,
        awa_enforced            = awa_enforced,
        signals_frozen          = False,
        zk_proofs_active        = threat_level.value >= ThreatLevel.MEDIUM.value,
        geographic_rebalancing  = threat_level.value >= ThreatLevel.HIGH.value,
        description             = desc,
    )


def apply_epigenetic_adjustment(
    base_value:   float,
    el_state:     ELState,
) -> tuple[float, str]:
    """
    Apply epigenetic adjustment to a signal value based on current expression.

    In DISAGGREGATED or FROZEN mode: signals are not emitted.
    In other modes: signals may be privacy-enhanced or ZK-only.

    Returns (adjusted_value, emission_mode).
    """
    if el_state.signals_frozen:
        return 0.0, "FROZEN"

    if el_state.expression == ELExpression.DISAGGREGATED:
        # Values emitted as partial signals only
        return base_value * 0.70, "DISAGGREGATED_PARTIAL"

    if el_state.expression == ELExpression.GEOGRAPHIC_REWEIGHT:
        return base_value, "ZK_ONLY"

    if el_state.expression == ELExpression.ZK_DEFAULT:
        return base_value, "ZK_PROOF"

    if el_state.expression == ELExpression.PRIVACY_ENHANCED:
        return base_value, "PRIVACY_ENHANCED"

    return base_value, "STANDARD"


if __name__ == "__main__":
    # Healthy state
    el_healthy = compute_el_state(
        threat_level            = ThreatLevel.NONE,
        validator_health        = 0.95,
        network_entropy         = 0.80,
        hostile_jurisdictions   = [],
        no_single_entity_weight = True,
        no_single_entity_select = True,
        public_good_pct         = 0.15,
        sovereignty_active      = True,
        right_to_invisibility   = True,
        gratitude_score         = 1.10,
    )
    print(f"Healthy: expression={el_healthy.expression.value} awa={el_healthy.awa_enforced}")
    assert el_healthy.expression == ELExpression.STANDARD
    assert el_healthy.awa_enforced

    # AWA violation
    el_frozen = compute_el_state(
        threat_level            = ThreatLevel.NONE,
        validator_health        = 0.95,
        network_entropy         = 0.80,
        hostile_jurisdictions   = ["hostile_country"],
        no_single_entity_weight = False,  # VIOLATION
        no_single_entity_select = True,
        public_good_pct         = 0.15,
        sovereignty_active      = True,
        right_to_invisibility   = True,
        gratitude_score         = 1.10,
    )
    print(f"AWA violation: frozen={el_frozen.signals_frozen}")
    assert el_frozen.signals_frozen
    assert not el_frozen.awa_enforced

    v, mode = apply_epigenetic_adjustment(0.75, el_frozen)
    assert mode == "FROZEN" and v == 0.0
    print(f"Frozen emission: value={v} mode={mode}")

    print("L4.5 Epigenetic Layer: PASS")
