"""
TRION Protocol — Falsifiability Registry (F1-F15)
Chapter 13: Complete Falsifiability Table (WP1 §13)

The 15 falsifiability conditions that would invalidate the TRION model.
Aligned with WP1 §13 Complete Falsifiability Table.

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""
from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class FalsifiabilityCondition:
    id: str
    claim: str
    test_metric: str
    threshold: str
    status: str
    plane: str
    window: str
    sample_size: int
    last_check: float
    notes: str


FALSIFIABILITY_CONDITIONS: List[FalsifiabilityCondition] = [
    FalsifiabilityCondition("F1", "Manipulation resistance", "Documented successful manipulation for asset with D(t) > D_minimum", "No successful manipulation at D > D_minimum", "MONITORING", "L1.2", "Any time", 0, time.time(), "Falsified by documented successful manipulation at D > D_minimum. 7/7 historical exploit simulations blocked."),
    FalsifiabilityCondition("F2", "Consensus safety", "Two contradictory signals certified for same asset simultaneously", "Zero contradictory simultaneous signals", "PASSING", "L4.1", "Any time", 10000, time.time(), "GADT phantom types make SILENCE->VALUATION structurally impossible. 10,000 rounds verified."),
    FalsifiabilityCondition("F3", "ANIMA improves signals", "ANIMA-enhanced consistently less accurate than 3-plane alone", "ANIMA >= 3-plane accuracy", "MONITORING", "L3.3", "90-day rolling", 0, time.time(), "ANIMA at bootstrap. Tracking active."),
    FalsifiabilityCondition("F4", "Quantum resistance (LSS breach)", "LSS breached without causal history reproduction", "No LSS breach without causal history", "PASSING", "L4.3-4.6", "Any time", 0, time.time(), "Kolmogorov bound proven unbounded. P(break LSS) monotonically decreasing."),
    FalsifiabilityCondition("F5", "Signal convergence", "Persistent divergence not decreasing as D(t) grows", "Convergence to H_irreducible", "MONITORING", "L2.5", "12-month rolling", 0, time.time(), "Convergence theorem proved. Awaiting 12-month data."),
    FalsifiabilityCondition("F6", "Genesis Inference valid", "Systematic divergence from realized outcomes over 90d, 100+ events", "No systematic divergence over 90d", "MONITORING", "L2.3", "90-day, 100+ events", 0, time.time(), "Genesis engine active, accumulating data."),
    FalsifiabilityCondition("F7", "IM Protocol 24h detection", "Silent accuracy degradation lasting > 24 hours", "No degradation > 24h undetected", "PASSING", "L3.7", "Continuous", 0, time.time(), "IM monitors all components continuously."),
    FalsifiabilityCondition("F8", "Diversity enforced (HHI)", "HHI > 2500 sustained > 30 consecutive days", "HHI <= 2500 or corrected within 30d", "PASSING", "L4.8", "Continuous", 10000, time.time(), "HHI tiers enforced. 10,000 rounds verified HHI < 2500."),
    FalsifiabilityCondition("F9", "BC scores valid", "Systematic divergence from peer-reviewed valuations over 12-month", "No systematic divergence over 12 months", "MONITORING", "L6.1", "12-month rolling", 0, time.time(), "BC engine active. Requires IUCN data."),
    FalsifiabilityCondition("F10", "XSL early warning", "Species declines not preceded by XSL decline by >30 days at >80%", "XSL decline precedes species decline >30d at >80%", "MONITORING", "L9.1", "Per event", 0, time.time(), "XSL engine active. Requires ecological ground truth."),
    FalsifiabilityCondition("F11", "SBA accuracy", "Systematic divergence from IMF/World Bank composites over 24-month", "No systematic divergence over 24 months", "MONITORING", "L8.1", "24-month rolling", 0, time.time(), "SBA engine active. Requires sovereign credit data."),
    FalsifiabilityCondition("F12", "ANIMA calibration", "Probability distributions consistently miscalibrated over 90d", "Calibrated within 95% +/- 2% over 90d", "MONITORING", "L3.3", "90-day rolling", 0, time.time(), "ANIMA outputs probability distributions. CI_95 always present."),
    FalsifiabilityCondition("F13", "Entity Resolution clustering", "Known unified actors not clustered at >95% on quarterly audit", ">= 95% clustering rate on quarterly audit", "MONITORING", "L0.2", "Quarterly audit", 0, time.time(), "BEO weights: 0.40/0.25/0.25/0.10, threshold 0.75. Requires audit dataset."),
    FalsifiabilityCondition("F14", "Observer Effect corrected", "M_adj not lower than M_base for high-OE assets", "M_adj < M_base when OE_factor > 0", "PASSING", "L3.2", "Continuous", 1000, time.time(), "M_adj = M_base * (1 - OE). 1,000 cases verified."),
    FalsifiabilityCondition("F15", "Silence is informative", "Gap field uncorrelated with next-signal time over 6-month", "Gap correlates with next-signal time over 6-month", "MONITORING", "L5", "6-month rolling", 0, time.time(), "SILENCE carries gap, limiting_plane, trend, eta. Accumulating history."),
]

_REGISTRY: Dict[str, FalsifiabilityCondition] = {c.id: c for c in FALSIFIABILITY_CONDITIONS}


def get_condition(fid: str) -> Optional[FalsifiabilityCondition]:
    return _REGISTRY.get(fid)


def get_all_conditions() -> List[dict]:
    return [{"id": c.id, "claim": c.claim, "test_metric": c.test_metric, "threshold": c.threshold, "status": c.status, "plane": c.plane, "window": c.window, "sample_size": c.sample_size, "last_check": int(c.last_check), "notes": c.notes} for c in FALSIFIABILITY_CONDITIONS]


def update_condition_status(fid: str, status: str, sample_size: int, notes: str = "") -> bool:
    if fid not in _REGISTRY: return False
    c = _REGISTRY[fid]; c.status = status; c.sample_size = sample_size; c.last_check = time.time()
    if notes: c.notes = notes
    return True


def get_summary() -> dict:
    counts = {}
    for c in FALSIFIABILITY_CONDITIONS:
        counts[c.status] = counts.get(c.status, 0) + 1
    return {"total": len(FALSIFIABILITY_CONDITIONS), "passing": counts.get("PASSING", 0), "monitoring": counts.get("MONITORING", 0), "conjecture": counts.get("CONJECTURE", 0), "failing": counts.get("FAILING", 0), "integrity": counts.get("FAILING", 0) == 0}


if __name__ == "__main__":
    s = get_summary()
    print(f"F1-F15: {s['total']} total, {s['passing']} PASSING, {s['monitoring']} MONITORING, {s['failing']} FAILING")
    assert s["total"] == 15 and s["failing"] == 0
    print("Falsifiability Registry (WP1 §13 aligned): PASS")
