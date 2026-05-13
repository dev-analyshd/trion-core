"""
Sovereign Behavioral Assessment (SBA) — TRION L8
SBA(nation, t) = 0.30*E + 0.25*I + 0.20*S + 0.15*G + 0.10*C
Sovereignty Dignity Protocol MANDATORY on every SBA signal.
"""
from dataclasses import dataclass
from typing import Dict, Tuple


SBA_WEIGHTS = {
    "economic":      0.30,
    "institutional": 0.25,
    "social":        0.20,
    "governance":    0.15,
    "cross_chain":   0.10,
}


@dataclass
class SBASignal:
    nation_id:                  str
    sba_score:                  float
    ci_95:                      Tuple[float, float]
    cultural_context_vector:    Dict
    data_sources:               Dict[str, str]
    appeal_mechanism_url:       str
    uncertainty_bounds_displayed: bool
    calibration_source:         str


def compute_sba(
    nation_id:    str,
    economic:     float,
    institutional: float,
    social:       float,
    governance:   float,
    cross_chain:  float,
    ci_width:     float = 0.15,
) -> SBASignal:
    for name, val in [("E", economic), ("I", institutional), ("S", social),
                      ("G", governance), ("C", cross_chain)]:
        if not 0 <= val <= 1:
            raise ValueError(f"SBA component {name} must be in [0,1], got {val}")

    score = (SBA_WEIGHTS["economic"]      * economic
           + SBA_WEIGHTS["institutional"] * institutional
           + SBA_WEIGHTS["social"]        * social
           + SBA_WEIGHTS["governance"]    * governance
           + SBA_WEIGHTS["cross_chain"]   * cross_chain)

    score = round(max(0.0, min(1.0, score)), 6)
    ci_lo = max(0.0, score - ci_width / 2)
    ci_hi = min(1.0, score + ci_width / 2)

    return SBASignal(
        nation_id=nation_id,
        sba_score=score,
        ci_95=(round(ci_lo, 6), round(ci_hi, 6)),
        cultural_context_vector={"nation": nation_id, "encoding": "ISO-3166"},
        data_sources={
            "economic":      "World Bank WDI",
            "institutional": "World Governance Indicators",
            "social":        "UNDP HDI",
            "governance":    "V-Dem Electoral Integrity",
            "cross_chain":   "TRION Akashic Index",
        },
        appeal_mechanism_url=f"https://trion.protocol/sba/appeal/{nation_id}",
        uncertainty_bounds_displayed=True,
        calibration_source="IMF World Economic Outlook + World Bank composites",
    )
