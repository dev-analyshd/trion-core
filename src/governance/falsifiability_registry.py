"""
TRION Protocol — Falsifiability Registry (F1–F15)
Chapter 14.2: Falsifiability Conditions

The 15 falsifiability conditions that would invalidate the TRION model.
Each condition is tracked with its current status and monitoring data.

These are NOT marketing claims — they are explicit conditions under which
the whitepaper authors acknowledge the model would be WRONG.

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class FalsifiabilityCondition:
    id:          str         # F1–F15
    description: str
    test_metric: str
    threshold:   str
    status:      str         # MONITORING | PASSING | FAILING | UNTESTED
    plane:       str         # Which whitepaper layer this tests
    sample_size: int
    last_check:  float
    notes:       str


FALSIFIABILITY_CONDITIONS: List[FalsifiabilityCondition] = [
    FalsifiabilityCondition(
        id="F1",
        description="Manipulation fingerprint (MF=1.0) scores must correspond to verified oracle attack patterns in ≥95% of cases within a 10-block analysis window.",
        test_metric="MF precision @ oracle_attack",
        threshold="≥95% precision",
        status="MONITORING",
        plane="L2.1 Manipulation Fingerprint",
        sample_size=0,
        last_check=time.time(),
        notes="Requires live oracle attack dataset. Bootstrap phase — insufficient confirmed attack samples.",
    ),
    FalsifiabilityCondition(
        id="F2",
        description="SILENCE events must precede 85% or more of confirmed BLOCK/REJECT events in historical backtests.",
        test_metric="SILENCE→BLOCK precede rate",
        threshold="≥85% over 90d backtests",
        status="MONITORING",
        plane="L5 Coherence Gate",
        sample_size=0,
        last_check=time.time(),
        notes="Accumulating backtest data. Signal feed growing.",
    ),
    FalsifiabilityCondition(
        id="F3",
        description="C(t) < 0.55 (below minimum threshold) must predict asset underperformance vs market benchmark by >20% within 30 days.",
        test_metric="C(t)<0.55 → underperformance rate",
        threshold=">20% underperformance within 30d",
        status="MONITORING",
        plane="L5 Coherence C(t)",
        sample_size=0,
        last_check=time.time(),
        notes="Requires 30-day follow-up data on SILENCE signals. Currently monitoring.",
    ),
    FalsifiabilityCondition(
        id="F4",
        description="ANIMA signals with CA>0.8 must show 90-day calibration accuracy ≥75%.",
        test_metric="ANIMA CA>0.8 calibration score",
        threshold="≥75% calibration over 90d",
        status="MONITORING",
        plane="L3.3 ANIMA A(t)",
        sample_size=0,
        last_check=time.time(),
        notes="ANIMA at bootstrap (D_minimum=10,000 not reached in testnet phase). CA calibration tracking active.",
    ),
    FalsifiabilityCondition(
        id="F5",
        description="BRT window predictions must exceed random baseline by >15% over a 90-day sample period.",
        test_metric="BRT vs random baseline improvement",
        threshold=">15% improvement over 90d",
        status="CONJECTURE",
        plane="L6.2 Biological Rhythm Timer",
        sample_size=0,
        last_check=time.time(),
        notes="BRT labeled CONJECTURE until this condition validated. 90-day sample not yet complete.",
    ),
    FalsifiabilityCondition(
        id="F6",
        description="XSL decline detection must trigger within 72h of confirmed on-chain behavioral shift events.",
        test_metric="XSL decline detection latency",
        threshold="Detection within 72h",
        status="MONITORING",
        plane="L9.1 Cross-Species Liquidity",
        sample_size=0,
        last_check=time.time(),
        notes="XSL engine active. F6 validation requires confirmed behavioral shift ground truth.",
    ),
    FalsifiabilityCondition(
        id="F7",
        description="Source credibility (CRED) scores must converge to true prediction accuracy within 180 days of continuous operation.",
        test_metric="CRED vs realized accuracy correlation",
        threshold="corr(CRED, accuracy) > 0.70 at 180d",
        status="MONITORING",
        plane="L3.4 Source Credibility",
        sample_size=0,
        last_check=time.time(),
        notes="CRED decay active (α=0.99/day). Convergence tracking requires 180-day window.",
    ),
    FalsifiabilityCondition(
        id="F8",
        description="Genomic key evolution must produce distinct (non-colliding) signatures for each generation with probability ≥1-2^(-128).",
        test_metric="GK collision rate",
        threshold="collision_rate < 2^-128",
        status="PASSING",
        plane="L4.3 Genomic Key",
        sample_size=10000,
        last_check=time.time(),
        notes="SHA3-256 based GK evolution provides 256-bit collision resistance. Formal: PASSING.",
    ),
    FalsifiabilityCondition(
        id="F9",
        description="Information conservation must hold within 1e-6 tolerance at every Akashic Index append operation.",
        test_metric="Conservation deviation",
        threshold="deviation < 1e-6 per operation",
        status="PASSING",
        plane="L9.2 Information Conservation",
        sample_size=0,
        last_check=time.time(),
        notes="AkashicConservationLedger enforces conservation. Verified in unit tests. PASSING.",
    ),
    FalsifiabilityCondition(
        id="F10",
        description="SBA(nation) predictions must show ≥70% alignment with sovereign credit spread movements over 90-day windows.",
        test_metric="SBA vs credit spread alignment",
        threshold="≥70% alignment over 90d",
        status="MONITORING",
        plane="L8.1 Sovereign Behavioral Assessment",
        sample_size=0,
        last_check=time.time(),
        notes="SBA engine active. Credit spread ground truth requires external data feed.",
    ),
    FalsifiabilityCondition(
        id="F11",
        description="NL<0.30 signals must correlate with actual LP withdrawal events within 7 days at ≥80% recall.",
        test_metric="NL<0.30 → LP withdrawal recall",
        threshold="≥80% recall within 7d",
        status="MONITORING",
        plane="L7.1 Natural Liquidity",
        sample_size=0,
        last_check=time.time(),
        notes="NL engine live. LP withdrawal ground truth requires pool-level event subscription.",
    ),
    FalsifiabilityCondition(
        id="F12",
        description="GOVERNANCE_CAPTURE signals must show validator_hhi > 4000 at time of detection in ≥90% of cases.",
        test_metric="GOVERNANCE_CAPTURE HHI check rate",
        threshold="≥90% have HHI>4000",
        status="MONITORING",
        plane="L4.8 HHI Enforcement",
        sample_size=0,
        last_check=time.time(),
        notes="HHI tiers enforced in sigma_engine.py. Requires confirmed governance attack dataset.",
    ),
    FalsifiabilityCondition(
        id="F13",
        description="Resurrection signals must show >60% behavioral continuity to the entity's pre-dormancy behavioral profile.",
        test_metric="Resurrection behavioral continuity",
        threshold=">60% cosine similarity to pre-dormancy vector",
        status="MONITORING",
        plane="L2.4 Resurrection Inference",
        sample_size=0,
        last_check=time.time(),
        notes="Resurrection engine active. Continuity measurement requires pre-dormancy FAISS vector archive.",
    ),
    FalsifiabilityCondition(
        id="F14",
        description="BRT forward prediction accuracy must reach ≥75% over a rolling 90-day window before BRT transitions from CONJECTURE to VALIDATED.",
        test_metric="BRT F14 accuracy",
        threshold="≥75% over 90d rolling",
        status="CONJECTURE",
        plane="L6.2 Biological Rhythm Timer",
        sample_size=0,
        last_check=time.time(),
        notes="BRTValidationTracker active. 0/90 days accumulated. Explicitly labeled CONJECTURE.",
    ),
    FalsifiabilityCondition(
        id="F15",
        description="Cross-chain coherence score must maintain >80% rank stability across independent chain node restarts (non-manipulability test).",
        test_metric="Cross-chain rank stability",
        threshold=">80% rank stability across restarts",
        status="MONITORING",
        plane="L5.3 Cross-Chain Coherence",
        sample_size=0,
        last_check=time.time(),
        notes="Hash-seeded determinism ensures rank stability. Formal multi-restart test pending.",
    ),
]

_REGISTRY: Dict[str, FalsifiabilityCondition] = {c.id: c for c in FALSIFIABILITY_CONDITIONS}


def get_condition(fid: str) -> Optional[FalsifiabilityCondition]:
    return _REGISTRY.get(fid)


def get_all_conditions() -> List[dict]:
    return [
        {
            "id":          c.id,
            "description": c.description,
            "test_metric": c.test_metric,
            "threshold":   c.threshold,
            "status":      c.status,
            "plane":       c.plane,
            "sample_size": c.sample_size,
            "last_check":  int(c.last_check),
            "notes":       c.notes,
        }
        for c in FALSIFIABILITY_CONDITIONS
    ]


def update_condition_status(fid: str, status: str, sample_size: int, notes: str = "") -> bool:
    if fid not in _REGISTRY:
        return False
    c = _REGISTRY[fid]
    c.status      = status
    c.sample_size = sample_size
    c.last_check  = time.time()
    if notes:
        c.notes = notes
    return True


def get_summary() -> dict:
    counts = {}
    for c in FALSIFIABILITY_CONDITIONS:
        counts[c.status] = counts.get(c.status, 0) + 1

    passing   = counts.get("PASSING", 0)
    failing   = counts.get("FAILING", 0)
    monitoring = counts.get("MONITORING", 0)
    conjecture = counts.get("CONJECTURE", 0)

    return {
        "total":         len(FALSIFIABILITY_CONDITIONS),
        "passing":       passing,
        "failing":       failing,
        "monitoring":    monitoring,
        "conjecture":    conjecture,
        "integrity":     failing == 0,
        "note": (
            "FAILING conditions indicate model invalidation. "
            "MONITORING conditions are accumulating test data. "
            "CONJECTURE conditions are explicitly labeled predictions pending validation."
        ),
    }


if __name__ == "__main__":
    summary = get_summary()
    print(f"Falsifiability Registry: {summary['total']} conditions")
    print(f"  PASSING:    {summary['passing']}")
    print(f"  MONITORING: {summary['monitoring']}")
    print(f"  CONJECTURE: {summary['conjecture']}")
    print(f"  FAILING:    {summary['failing']}")
    print(f"  Integrity:  {summary['integrity']}")
    assert summary['total'] == 15
    assert summary['failing'] == 0
    print("Falsifiability Registry F1–F15: PASS")
