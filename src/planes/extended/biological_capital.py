"""
TRION Protocol — L6.1 Biological Capital Index (BC)

BC(ecosystem, t) = Flow · Resilience · Uniqueness · Interdependence

Flow          = net primary productivity rate × biomass density
                Measures energy/material flow through the ecosystem.
                High flow = productive, active ecosystem.

Resilience    = recovery_speed_after_disturbance / disturbance_magnitude
                How fast the ecosystem recovers relative to the size of the shock.
                Healthy ecosystems recover quickly. Brittle ones do not.

Uniqueness    = endemic_species_count / (comparable_ecosystem_baseline + 1)
                Irreplaceable ecological value.
                Uniqueness = 0 if species are globally common.
                Uniqueness → high if species exist ONLY here.

Interdependence = keystone_species_presence_weighted_connectivity
                Network of species dependencies — how connected is the web?
                Loss of keystone species → cascade collapse.

BC maps to financial protocol health:
    Flow          = value throughput and velocity
    Resilience    = protocol resilience to stress events
    Uniqueness    = protocol's unique value proposition (non-substitutability)
    Interdependence = composability and ecosystem integration depth

XSL(species, t) = TerritoryViability · FoodSecurity · ReproductionRate / (1 + ThreatPressure)
→ see xsl.py

Falsification: F9 (BC scores must not systematically diverge from
peer-reviewed ecosystem valuations over 12-month rolling window)

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class EcosystemProfile:
    """
    Input data for Biological Capital computation.
    Sourced from: IUCN Red List, GBIF, peer-reviewed ecological databases.
    Calibrated by computational biologists (critical non-obvious hire).
    """
    ecosystem_id:                 str
    # Flow components
    net_primary_productivity:     float   # gC/m²/year — carbon fixed by photosynthesis
    biomass_density:              float   # tonnes/hectare
    # Resilience components
    recovery_speed:               float   # [0, 1] — fraction recovered per year post-disturbance
    disturbance_magnitude:        float   # [0, 1] — size of reference disturbance
    # Uniqueness components
    endemic_species_count:        int
    comparable_baseline_count:    int     # Same type ecosystem elsewhere
    # Interdependence components
    keystone_species_present:     bool
    network_connectivity:         float   # [0, 1] — ecological network connectivity
    trophic_levels:               int     # Number of trophic levels


@dataclass
class BiologicalCapitalResult:
    """
    BC(ecosystem, t) = Flow · Resilience · Uniqueness · Interdependence
    """
    ecosystem_id:      str
    bc:                float     # [0, 1] — biological capital score
    flow:              float     # Net primary productivity × biomass (normalized)
    resilience:        float     # Recovery speed / disturbance magnitude
    uniqueness:        float     # Endemic / comparable baseline
    interdependence:   float     # Keystone × connectivity
    label:             str       # THRIVING / HEALTHY / STRESSED / CRITICAL / COLLAPSED
    warning:           Optional[str]


# Calibration constants (from peer-reviewed ecology literature)
# These must be validated against real ecological data by computational biologists
NPP_MAX_REFERENCE     = 2500.0   # gC/m²/year — tropical rainforest reference
BIOMASS_MAX_REFERENCE = 300.0    # tonnes/hectare — old-growth forest reference


def compute_flow(
    net_primary_productivity: float,
    biomass_density:          float,
) -> float:
    """
    Flow = (NPP / NPP_reference) × (biomass / biomass_reference)
    Normalized to [0, 1] using reference maxima.
    """
    npp_norm     = min(1.0, net_primary_productivity / NPP_MAX_REFERENCE)
    biomass_norm = min(1.0, biomass_density / BIOMASS_MAX_REFERENCE)
    return npp_norm * biomass_norm


def compute_resilience(
    recovery_speed:      float,
    disturbance_magnitude: float,
) -> float:
    """
    Resilience = recovery_speed / disturbance_magnitude

    If disturbance is near zero, resilience is defined by recovery speed alone.
    Normalized to [0, 1].
    """
    if disturbance_magnitude <= 0:
        return min(1.0, recovery_speed)
    raw = recovery_speed / max(disturbance_magnitude, 0.001)
    return min(1.0, max(0.0, raw))


def compute_uniqueness(
    endemic_species_count:     int,
    comparable_baseline_count: int,
) -> float:
    """
    Uniqueness = endemic_species_count / (comparable_baseline_count + 1)

    +1 prevents division by zero.
    High endemic count relative to baseline = highly unique = high conservation value.
    Normalized to [0, 1] with logistic capping.
    """
    raw = endemic_species_count / (comparable_baseline_count + 1)
    # Logistic normalization: caps high values smoothly
    import math
    return 1.0 - math.exp(-raw)


def compute_interdependence(
    keystone_species_present: bool,
    network_connectivity:     float,
    trophic_levels:           int,
) -> float:
    """
    Interdependence = keystone_presence_weight × connectivity × trophic_complexity

    Keystone species: if absent, interdependence is halved regardless of connectivity.
    Trophic levels: more levels = more complex web = higher interdependence.
    """
    keystone_weight   = 1.0 if keystone_species_present else 0.5
    trophic_factor    = min(1.0, trophic_levels / 6.0)  # Normalize 6 trophic levels = 1.0
    raw               = keystone_weight * network_connectivity * trophic_factor
    return min(1.0, max(0.0, raw))


def compute_bc(profile: EcosystemProfile) -> BiologicalCapitalResult:
    """
    BC(ecosystem, t) = Flow · Resilience · Uniqueness · Interdependence
    """
    flow   = compute_flow(profile.net_primary_productivity, profile.biomass_density)
    resil  = compute_resilience(profile.recovery_speed, profile.disturbance_magnitude)
    unique = compute_uniqueness(profile.endemic_species_count, profile.comparable_baseline_count)
    inter  = compute_interdependence(
        profile.keystone_species_present, profile.network_connectivity, profile.trophic_levels
    )

    bc = flow * resil * unique * inter

    if bc >= 0.70:
        label = "THRIVING"
    elif bc >= 0.50:
        label = "HEALTHY"
    elif bc >= 0.30:
        label = "STRESSED"
    elif bc >= 0.10:
        label = "CRITICAL"
    else:
        label = "COLLAPSED"

    warning = None
    if bc < 0.10:
        warning = (
            f"ECOSYSTEM COLLAPSE: BC={bc:.4f}. "
            "XSL(species) signals will show systemic extinction risk. "
            "Correlated asset (ECOSYSTEM_HEALTH signal) affected."
        )
    elif bc < 0.30:
        warning = f"CRITICAL ecosystem: BC={bc:.4f}. Stress signals active."

    return BiologicalCapitalResult(
        ecosystem_id  = profile.ecosystem_id,
        bc            = bc,
        flow          = flow,
        resilience    = resil,
        uniqueness    = unique,
        interdependence = inter,
        label         = label,
        warning       = warning,
    )


def bc_to_ecosystem_health_signal(bc_result: BiologicalCapitalResult) -> dict:
    """
    Build ECOSYSTEM_HEALTH signal from BC computation.
    BC and EP components included per whitepaper signal specification.
    """
    return {
        "signal_type":    "ECOSYSTEM_HEALTH",
        "ecosystem_id":   bc_result.ecosystem_id,
        "bc_score":       bc_result.bc,
        "bc_components": {
            "flow":           bc_result.flow,
            "resilience":     bc_result.resilience,
            "uniqueness":     bc_result.uniqueness,
            "interdependence": bc_result.interdependence,
        },
        "label":          bc_result.label,
        "warning":        bc_result.warning,
        "data_sources":   [
            "IUCN Red List", "GBIF", "peer-reviewed ecological databases",
        ],
        "calibration_note": (
            "HONEST DISCLOSURE: BC calibration requires computational biologist validation "
            "against peer-reviewed ecosystem valuations (F9 falsification condition). "
            "Current values are initial estimates pending expert calibration."
        ),
    }


if __name__ == "__main__":
    # Amazon rainforest approximation
    amazon = EcosystemProfile(
        ecosystem_id                 = "amazon_basin",
        net_primary_productivity     = 2100.0,
        biomass_density              = 250.0,
        recovery_speed               = 0.60,
        disturbance_magnitude        = 0.30,
        endemic_species_count        = 40000,
        comparable_baseline_count    = 5000,
        keystone_species_present     = True,
        network_connectivity         = 0.88,
        trophic_levels               = 5,
    )

    result = compute_bc(amazon)
    print(f"Amazon BC: {result.bc:.4f} [{result.label}]")
    print(f"  Flow={result.flow:.4f} Resilience={result.resilience:.4f} "
          f"Uniqueness={result.uniqueness:.4f} Interdependence={result.interdependence:.4f}")
    assert result.bc > 0.30  # Amazon should be healthy

    # Degraded ecosystem
    degraded = EcosystemProfile(
        ecosystem_id                 = "degraded_monoculture",
        net_primary_productivity     = 300.0,
        biomass_density              = 20.0,
        recovery_speed               = 0.10,
        disturbance_magnitude        = 0.80,
        endemic_species_count        = 5,
        comparable_baseline_count    = 1000,
        keystone_species_present     = False,
        network_connectivity         = 0.15,
        trophic_levels               = 2,
    )
    result_d = compute_bc(degraded)
    print(f"Degraded BC: {result_d.bc:.4f} [{result_d.label}]")
    assert result_d.bc < 0.30

    print("L6.1 Biological Capital Index: PASS")
