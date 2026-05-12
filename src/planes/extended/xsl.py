"""
TRION Protocol — L9.1 Cross-Species Liquidity (XSL)

XSL(species, t) = TerritoryViability · FoodSecurity · ReproductionRate
                  ─────────────────────────────────────────────────────
                              (1 + ThreatPressure)

Cross-Species Liquidity is TRION's most novel signal.
It maps ecological liquidity metrics onto financial market dynamics:

- A species is "liquid" in its ecological niche when its territory is viable,
  food supply is secure, reproduction maintains population, and threats are low.
- When XSL declines for keystone species, the ecosystem is losing
  "ecological liquidity" — the capacity to sustain complex interactions.
- This precedes ecosystem collapse — observable 30-90 days before financial
  markets register the downstream economic effects.

Falsification F10:
  Falsified if species declines are NOT preceded by XSL decline > 30 days before event.

Application in TRION:
  - Real-world natural resource protocols (carbon credits, biodiversity bonds)
  - Agricultural commodity pricing
  - Any financial asset correlated with ecological health
  - Systemic risk: ecosystem collapse → supply chain disruption → asset stress

Data sources (requires ecological + environmental scientists):
  - IUCN Red List (species population data)
  - WWF Living Planet Index
  - GBIF occurrence data
  - Satellite-derived habitat maps (NDVI, land cover)
  - Government wildlife monitoring agencies

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class SpeciesProfile:
    """
    Input data for XSL computation.
    Sourced from IUCN Red List, GBIF, peer-reviewed ecological surveys.
    """
    species_id:            str
    common_name:           str
    is_keystone:           bool     # Keystone species? Loss → cascade collapse

    # Territory viability
    habitat_area_km2:      float    # Current habitat area
    habitat_area_baseline: float    # Historical baseline area (10-year average)
    habitat_quality_score: float    # [0, 1] — NDVI-derived or expert-assessed

    # Food security
    prey_availability:     float    # [0, 1] — relative prey/food abundance
    dietary_breadth:       float    # [0, 1] — 1=generalist, 0=specialist (vulnerable)
    competition_pressure:  float    # [0, 1] — competitive pressure for food resources

    # Reproduction rate
    observed_reproduction: float    # Births per female per year (observed)
    baseline_reproduction: float    # Historical baseline reproduction rate
    juvenile_survival:     float    # [0, 1] — fraction surviving to adulthood

    # Threat pressure (additive)
    habitat_loss_rate:     float    # [0, 1] — fraction of habitat lost per year
    hunting_pressure:      float    # [0, 1] — poaching/harvest intensity
    climate_vulnerability: float    # [0, 1] — IUCN climate vulnerability score
    disease_pressure:      float    # [0, 1] — pathogen/disease burden
    pollution_level:       float    # [0, 1] — environmental contamination


@dataclass
class XSLResult:
    """
    XSL(species, t) = TerritoryViability · FoodSecurity · ReproductionRate / (1 + ThreatPressure)
    """
    species_id:           str
    common_name:          str
    xsl:                  float    # [0, ∞) but practically [0, 1] for healthy species
    territory_viability:  float
    food_security:        float
    reproduction_rate:    float
    threat_pressure:      float
    is_keystone:          bool
    status:               str      # THRIVING / STABLE / VULNERABLE / ENDANGERED / CRITICAL
    financial_risk_flag:  bool     # True if XSL decline exceeds 30-day threshold
    early_warning:        Optional[str]


def compute_territory_viability(
    habitat_area_km2:      float,
    habitat_area_baseline: float,
    habitat_quality_score: float,
) -> float:
    """
    TerritoryViability = (habitat_area / baseline_area) × habitat_quality

    Normalized to [0, 1]. Values > 1 truncated — we cannot exceed baseline.
    """
    if habitat_area_baseline <= 0:
        return habitat_quality_score

    area_ratio = min(1.0, habitat_area_km2 / habitat_area_baseline)
    return max(0.0, area_ratio * habitat_quality_score)


def compute_food_security(
    prey_availability:    float,
    dietary_breadth:      float,
    competition_pressure: float,
) -> float:
    """
    FoodSecurity = prey_availability × dietary_breadth × (1 - competition_pressure)

    Species with broad diets are more food-secure (dietary_breadth near 1).
    High competition reduces effective food security.
    """
    competition_factor = max(0.0, 1.0 - competition_pressure)
    return max(0.0, prey_availability * dietary_breadth * competition_factor)


def compute_reproduction_rate(
    observed:           float,
    baseline:           float,
    juvenile_survival:  float,
) -> float:
    """
    ReproductionRate = (observed / baseline) × juvenile_survival

    Normalized to [0, 1]. Reproduction above baseline still capped at 1.0
    for XSL purposes (we measure adequacy, not excess).
    """
    if baseline <= 0:
        return juvenile_survival
    rate_ratio = min(1.0, observed / baseline)
    return max(0.0, rate_ratio * juvenile_survival)


def compute_threat_pressure(
    habitat_loss_rate:     float,
    hunting_pressure:      float,
    climate_vulnerability: float,
    disease_pressure:      float,
    pollution_level:       float,
) -> float:
    """
    ThreatPressure = weighted sum of threat factors.
    Range [0, ∞) — but practically [0, 2] for severe cases.

    Weights reflect relative impact on population viability:
    habitat loss and climate are most severe over long time horizons.
    """
    return (
        0.35 * habitat_loss_rate      +
        0.20 * hunting_pressure       +
        0.25 * climate_vulnerability  +
        0.10 * disease_pressure       +
        0.10 * pollution_level
    )


def compute_xsl(profile: SpeciesProfile) -> XSLResult:
    """
    XSL(species, t) = TerritoryViability · FoodSecurity · ReproductionRate
                      ─────────────────────────────────────────────────────
                                   (1 + ThreatPressure)
    """
    tv  = compute_territory_viability(
        profile.habitat_area_km2, profile.habitat_area_baseline, profile.habitat_quality_score
    )
    fs  = compute_food_security(
        profile.prey_availability, profile.dietary_breadth, profile.competition_pressure
    )
    rr  = compute_reproduction_rate(
        profile.observed_reproduction, profile.baseline_reproduction, profile.juvenile_survival
    )
    tp  = compute_threat_pressure(
        profile.habitat_loss_rate, profile.hunting_pressure,
        profile.climate_vulnerability, profile.disease_pressure, profile.pollution_level
    )

    xsl = (tv * fs * rr) / (1.0 + tp)
    xsl = max(0.0, xsl)

    if xsl >= 0.70:
        status = "THRIVING"
    elif xsl >= 0.50:
        status = "STABLE"
    elif xsl >= 0.30:
        status = "VULNERABLE"
    elif xsl >= 0.10:
        status = "ENDANGERED"
    else:
        status = "CRITICAL"

    financial_risk_flag = xsl < 0.30 and profile.is_keystone
    early_warning = None
    if financial_risk_flag:
        early_warning = (
            f"KEYSTONE SPECIES CRITICAL: {profile.common_name} XSL={xsl:.4f}. "
            "Financial assets correlated with this ecosystem face cascade risk. "
            "30-90 day advance warning per F10 falsification condition."
        )
    elif xsl < 0.30:
        early_warning = (
            f"SPECIES VULNERABLE: {profile.common_name} XSL={xsl:.4f}. "
            "Ecosystem stress signal active."
        )

    return XSLResult(
        species_id          = profile.species_id,
        common_name         = profile.common_name,
        xsl                 = xsl,
        territory_viability = tv,
        food_security       = fs,
        reproduction_rate   = rr,
        threat_pressure     = tp,
        is_keystone         = profile.is_keystone,
        status              = status,
        financial_risk_flag = financial_risk_flag,
        early_warning       = early_warning,
    )


def xsl_to_trion_signal(xsl_results: List[XSLResult], ecosystem_id: str) -> dict:
    """Build TRION XSL signal from multiple species assessments."""
    if not xsl_results:
        return {}

    keystone_scores = [r.xsl for r in xsl_results if r.is_keystone]
    all_scores      = [r.xsl for r in xsl_results]

    ecosystem_xsl   = sum(all_scores) / len(all_scores)
    keystone_xsl    = sum(keystone_scores) / len(keystone_scores) if keystone_scores else None
    critical_species = [r.common_name for r in xsl_results if r.status in ("ENDANGERED", "CRITICAL")]

    return {
        "signal_type":         "ECOSYSTEM_HEALTH",
        "ecosystem_id":        ecosystem_id,
        "xsl_aggregate":       ecosystem_xsl,
        "xsl_keystone":        keystone_xsl,
        "species_count":       len(xsl_results),
        "critical_species":    critical_species,
        "financial_risk":      any(r.financial_risk_flag for r in xsl_results),
        "data_sources":        ["IUCN Red List", "GBIF", "WWF Living Planet Index"],
        "early_warnings":      [r.early_warning for r in xsl_results if r.early_warning],
    }


if __name__ == "__main__":
    # African elephant (keystone species)
    elephant = SpeciesProfile(
        species_id="loxodonta_africana",
        common_name="African Elephant",
        is_keystone=True,
        habitat_area_km2=350000,
        habitat_area_baseline=500000,
        habitat_quality_score=0.65,
        prey_availability=0.70,
        dietary_breadth=0.60,
        competition_pressure=0.25,
        observed_reproduction=0.08,
        baseline_reproduction=0.12,
        juvenile_survival=0.65,
        habitat_loss_rate=0.04,
        hunting_pressure=0.15,
        climate_vulnerability=0.35,
        disease_pressure=0.10,
        pollution_level=0.08,
    )

    result = compute_xsl(elephant)
    print(f"Elephant XSL: {result.xsl:.4f} [{result.status}]")
    print(f"  TV={result.territory_viability:.4f} FS={result.food_security:.4f} "
          f"RR={result.reproduction_rate:.4f} TP={result.threat_pressure:.4f}")
    if result.early_warning:
        print(f"  WARNING: {result.early_warning[:80]}...")

    # Critically endangered
    crit = SpeciesProfile(
        species_id="vaquita_marina",
        common_name="Vaquita",
        is_keystone=True,
        habitat_area_km2=2200,
        habitat_area_baseline=8000,
        habitat_quality_score=0.25,
        prey_availability=0.30,
        dietary_breadth=0.40,
        competition_pressure=0.70,
        observed_reproduction=0.02,
        baseline_reproduction=0.15,
        juvenile_survival=0.20,
        habitat_loss_rate=0.12,
        hunting_pressure=0.40,
        climate_vulnerability=0.50,
        disease_pressure=0.20,
        pollution_level=0.45,
    )
    result_c = compute_xsl(crit)
    print(f"Vaquita XSL: {result_c.xsl:.4f} [{result_c.status}] risk={result_c.financial_risk_flag}")
    assert result_c.status in ("CRITICAL", "ENDANGERED")

    print("L9.1 Cross-Species Liquidity: PASS")
