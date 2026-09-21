"""
TRION Protocol — Falsifiability Registry (F1-F15)
=================================================================
Canonical source: TRION Whitepaper PART 13 — "Formal Proofs and
Falsifiability", "Complete Falsifiability Table" (lines ~2445-2591 of
spec/WHITEPAPER_MD.txt / /tmp/whitepaper_full.txt).

The 15 falsifiability conditions that would invalidate the TRION model.
Each F-condition is an empirically testable claim with a precise metric,
threshold, and observation window. If any condition is violated, the
corresponding TRION claim is falsified.

FIX-E (Gap 18) consolidation: TRION previously carried THREE divergent
F1-F15 registries:
  1. Whitepaper PART 13 "Complete Falsifiability Table" (canonical)
  2. API endpoint /api/v1/falsifiability (this module — used to follow WP2 §20)
  3. Markdown registry spec/falsifiability_registry.md (used to follow WP1
     primitive-based per-layer mapping — F1=BH collision, F2=BEO monotonic,
     F3=Resonance AUC, ... F15=XSL bounding)

Per Gap 18, this file and the markdown registry now mirror the whitepaper
PART 13 table VERBATIM. The previous WP2 §20 mapping (which elevated
BRT-gas-correlation to F14 and REGULATORY_BEHAVIORAL-24-month to F15 as
CONJECTUREs) has been retired — those two long-horizon conjectures are
documented in spec/open_research_questions.md, NOT in the canonical
Part 13 falsifiability table.

FIX-CLAIMS honesty note (status provenance): the `status`, `sample_size`,
and figures quoted in `notes` below ("PASSING", "10,000 rounds verified",
"1,000 cases verified", ...) are SELF-REPORTED strings/numbers, NOT values
derived from the test suite. Each condition carries a `status_source`
field stating exactly what backs it: "self-reported, not test-derived",
"partial" (a real unit test exercises a related computation on synthetic
inputs, but the headline figure/status is not test output), or a pointer
to the specific test. Treat PASSING here as an author's claim, not evidence.

Whitepaper Part 13 F1-F15 canonical table:
  F1  — Manipulation resistance
        Falsified by documented successful manipulation for asset with
        D(t) > D_minimum.                                  Window: Any time
  F2  — Consensus safety
        Falsified by two contradictory signals simultaneously certified
        for same asset at same time.                      Window: Any time
  F3  — ANIMA improves signals
        Falsified if ANIMA-enhanced consistently less accurate than
        3-plane alone.                                     Window: 90-day rolling
  F4  — Quantum resistance
        Falsified if LSS breached without demonstrably reproducing
        causal history.                                    Window: Any time
  F5  — Signal convergence
        Falsified by persistent divergence from realized values that
        does not decrease as D(t) grows.                   Window: 12-month rolling
  F6  — Genesis Inference valid
        Falsified by systematic divergence from realized outcomes.
                                                          Window: 90-day, 100+ events
  F7  — IM Protocol operational
        Falsified by silent accuracy degradation lasting > 24 hours.
                                                          Window: Continuous
  F8  — Diversity enforced
        Falsified if HHI > 2500 sustained > 30 consecutive days.
                                                          Window: Continuous
  F9  — BC scores valid
        Falsified by systematic divergence from peer-reviewed ecosystem
        valuations.                                       Window: 12-month rolling
  F10 — XSL early warning
        Falsified if species declines not preceded by XSL decline >30 days.
                                                          Window: Per event
  F11 — SBA accuracy
        Falsified by systematic divergence from IMF/World Bank composites.
                                                          Window: 24-month rolling
  F12 — ANIMA calibration
        Falsified if probability distributions consistently miscalibrated.
                                                          Window: 90-day rolling
  F13 — Entity Resolution
        Falsified if known unified actors not clustered at >95% rate.
                                                          Window: Quarterly audit
  F14 — Observer Effect corrected
        Falsified if M_adj not lower than M_base for high-OE assets.
                                                          Window: Continuous
  F15 — Silence is informative
        Falsified if gap field in Silence Signals uncorrelated with
        next-signal time.                                  Window: 6-month rolling

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field
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
    # FIX-CLAIMS: provenance of `status`/`sample_size` — see module docstring.
    # Default is the honest fallback; "partial" entries cite real tests but
    # do not imply the headline status is test-derived.
    status_source: str = "self-reported, not test-derived"
    # FIX-E (Gap 18): canonical Part 13 reference for each F-condition.
    # The whitepaper Part 13 "Complete Falsifiability Table" lists F1-F15 as
    # flat entries (no §13.x.y sub-sections exist in the source). The
    # `part_13_section` field now carries the canonical "Part 13 F<n> —
    # <claim>" string for cross-reference with the markdown registry.
    part_13_section: str = ""


# ── FIX-E (Gap 18) — Canonical Part 13 reference table ───────────────────────
# Verbatim citations of the whitepaper Part 13 "Complete Falsifiability
# Table". Per the whitepaper, Part 13 has flat F1-F15 entries (NO §13.x.y
# sub-section structure — the previous registry's invented sub-section
# numbers have been removed).
PART_13_MAPPING: Dict[str, str] = {
    "F1":  "Part 13 F1 — Manipulation resistance",
    "F2":  "Part 13 F2 — Consensus safety",
    "F3":  "Part 13 F3 — ANIMA improves signals",
    "F4":  "Part 13 F4 — Quantum resistance",
    "F5":  "Part 13 F5 — Signal convergence",
    "F6":  "Part 13 F6 — Genesis Inference valid",
    "F7":  "Part 13 F7 — IM Protocol operational",
    "F8":  "Part 13 F8 — Diversity enforced",
    "F9":  "Part 13 F9 — BC scores valid",
    "F10": "Part 13 F10 — XSL early warning",
    "F11": "Part 13 F11 — SBA accuracy",
    "F12": "Part 13 F12 — ANIMA calibration",
    "F13": "Part 13 F13 — Entity Resolution",
    "F14": "Part 13 F14 — Observer Effect corrected",
    "F15": "Part 13 F15 — Silence is informative",
}


FALSIFIABILITY_CONDITIONS: List[FalsifiabilityCondition] = [
    # F1 — Manipulation resistance (Part 13 F1)
    FalsifiabilityCondition(
        "F1", "Manipulation resistance",
        "Documented successful manipulation for an asset with sufficient behavioral history (D(t) > D_minimum, >6 months)",
        "No successful manipulation at D > D_minimum (any time, continuous)",
        "MONITORING", "L1.2", "Any time", 0, time.time(),
        "Falsified by documented successful manipulation for asset with D(t) > D_minimum. "
        "7/7 historical exploit simulations blocked; awaiting long-horizon mainnet ground truth.",
        status_source=("self-reported, not test-derived — the '7/7 historical exploit simulations' figure "
                       "is output of scripts/simulate_attacks.py (a script, not a test; the replay includes the "
                       "fabricated 'AAVE March 2026' case flagged by AUDIT-PY). The MF-detector formulas are "
                       "verified on synthetic inputs by tests/master_formula_verification.py, but no test asserts "
                       "the manipulation-resistance claim."),
        part_13_section=PART_13_MAPPING["F1"],
    ),
    # F2 — Consensus safety (Part 13 F2)
    FalsifiabilityCondition(
        "F2", "Consensus safety",
        "Two contradictory signals simultaneously certified for the same asset at the same time (binary, continuously testable)",
        "Zero contradictory simultaneous signals (any time, continuous)",
        "PASSING", "L4.1", "Any time", 10000, time.time(),
        "Falsified by two contradictory signals simultaneously certified for same asset at same time. "
        "GADT phantom types make SILENCE→VALUATION structurally impossible. 10,000 rounds verified.",
        status_source=("partial — the SILENCE≠VALUATION check is real at the type level "
                       "(formal/src/TRION/Theorems.hs T2; formal/test/Spec.hs), but the '10,000 rounds' "
                       "sample_size and 'PASSING' are hardcoded strings, not test output: no test executes "
                       "10,000 certification rounds."),
        part_13_section=PART_13_MAPPING["F2"],
    ),
    # F3 — ANIMA improves signals (Part 13 F3)
    FalsifiabilityCondition(
        "F3", "ANIMA improves signals",
        "ANIMA-enhanced signals consistently less accurate than 3-plane-alone baseline on identical assets",
        "ANIMA-enhanced signals strictly more accurate than 3-plane-alone (90-day rolling)",
        "MONITORING", "L3.3", "90-day rolling", 0, time.time(),
        "Falsified if ANIMA-enhanced signals are consistently less accurate than the 3-plane-alone baseline. "
        "ANIMA layer (PCR×HA×CA) is active; awaiting mainnet comparative-accuracy corpus.",
        status_source=("self-reported, not test-derived — the ANIMA scoring is unit-tested "
                       "(tests/unit/trion_protocol/test_conformal_predictor.py) but no test measures "
                       "ANIMA-vs-3-plane-alone out-of-sample accuracy on a 90-day rolling window."),
        part_13_section=PART_13_MAPPING["F3"],
    ),
    # F4 — Quantum resistance (Part 13 F4)
    FalsifiabilityCondition(
        "F4", "Quantum resistance",
        "LSS breached without demonstrably reproducing complete causal history of the entity",
        "No LSS breach without complete causal-history reproduction (any time)",
        "PASSING", "L4.3-4.6", "Any time", 0, time.time(),
        "Falsified if LSS breached without demonstrably reproducing causal history. "
        "Kolmogorov bound proven unbounded; P(break LSS) monotonically decreasing.",
        status_source=("self-reported, not test-derived — 'Kolmogorov bound proven unbounded' is prose: "
                       "no proof of unboundedness exists in formal/ and no test measures P(break LSS)."),
        part_13_section=PART_13_MAPPING["F4"],
    ),
    # F5 — Signal convergence (Part 13 F5)
    FalsifiabilityCondition(
        "F5", "Signal convergence",
        "Persistent divergence from realized values that does not decrease as D(t) grows (convergence theorem failure)",
        "Convergence to H_irreducible as D(t) grows (12-month rolling)",
        "MONITORING", "L2.5", "12-month rolling", 0, time.time(),
        "Falsified by persistent divergence from realized values that does not decrease as D(t) grows. "
        "Convergence theorem proved; awaiting 12-month mainnet data.",
        status_source=("self-reported, not test-derived — 'Convergence theorem proved' overstates: "
                       "Haskell T1 is only a C∈[0,1] range check (see formal/src/TRION/Theorems.hs header); "
                       "no convergence proof exists."),
        part_13_section=PART_13_MAPPING["F5"],
    ),
    # F6 — Genesis Inference valid (Part 13 F6)
    FalsifiabilityCondition(
        "F6", "Genesis Inference valid",
        "Systematic divergence of genesis inference from realized outcomes as the bootstrapped entity accumulates history",
        "No systematic divergence over 90-day, 100+ events",
        "MONITORING", "L2.3", "90-day, 100+ events", 0, time.time(),
        "Falsified by systematic divergence from realized outcomes. "
        "Genesis engine active, accumulating data.",
        status_source="self-reported, not test-derived (no test measures genesis-inference convergence to reality).",
        part_13_section=PART_13_MAPPING["F6"],
    ),
    # F7 — IM Protocol operational (Part 13 F7)
    FalsifiabilityCondition(
        "F7", "IM Protocol operational",
        "Silent accuracy degradation lasting > 24 hours without detection and correction",
        "No silent accuracy degradation > 24 hours undetected (continuous)",
        "PASSING", "L3.7", "Continuous", 0, time.time(),
        "Falsified by silent accuracy degradation lasting > 24 hours. "
        "Intelligence Maintenance (IM) protocol monitors all components continuously.",
        status_source=("partial — the IM computation is unit-tested "
                       "(tests/unit/test_all_planes.py::test_intelligence_maintenance_healthy), but the "
                       "24-hour detection SLA on a live deployment is not test-derived; 'PASSING' is a claim."),
        part_13_section=PART_13_MAPPING["F7"],
    ),
    # F8 — Diversity enforced (Part 13 F8)
    FalsifiabilityCondition(
        "F8", "Diversity enforced",
        "Validator HHI exceeds 2500 sustained for > 30 consecutive days without automatic correction",
        "HHI ≤ 2500 or auto-corrected within 30 consecutive days (continuous)",
        "PASSING", "L4.8", "Continuous", 10000, time.time(),
        "Falsified if HHI > 2500 sustained > 30 consecutive days. "
        "HHI tiers enforced; 10,000 rounds verified HHI < 2500.",
        status_source=("partial — HHI math is unit-tested on synthetic stake vectors "
                       "(tests/unit/trion_protocol/test_consensus_bft.py::test_hhi_healthy_equal_stake, "
                       "test_hhi_critical_monopoly, test_sigma_result_has_hhi_status), but the '10,000 rounds' "
                       "sample_size and 'PASSING' are hardcoded, not test output."),
        part_13_section=PART_13_MAPPING["F8"],
    ),
    # F9 — BC scores valid (Part 13 F9)
    FalsifiabilityCondition(
        "F9", "BC scores valid",
        "Systematic divergence of Biological Capital (BC) scores from peer-reviewed ecosystem valuations",
        "No systematic divergence from peer-reviewed ecosystem valuations (12-month rolling)",
        "MONITORING", "L6.1", "12-month rolling", 0, time.time(),
        "Falsified by systematic divergence from peer-reviewed ecosystem valuations over 12-month rolling window. "
        "BC Index (L6.1) currently uses (D·H·R)^(1/3) formula (see audit gap #11: formula divergence vs spec 4-factor); "
        "awaiting mainnet BC-vs-valuation corpus.",
        status_source="self-reported, not test-derived (no peer-reviewed valuation corpus is wired to test BC).",
        part_13_section=PART_13_MAPPING["F9"],
    ),
    # F10 — XSL early warning (Part 13 F10)
    FalsifiabilityCondition(
        "F10", "XSL early warning",
        "Species declines not preceded by XSL signal decline > 30 days at > 80% rate (per documented event)",
        "Species declines preceded by XSL decline > 30 days at > 80% rate (per event)",
        "MONITORING", "L9.1", "Per event", 0, time.time(),
        "Falsified if species declines are not preceded by XSL signal decline by > 30 days at > 80% rate over "
        "documented events. XSL engine (L9.1) computes TV·FS·RR/(1+TP); awaiting cross-species corpus.",
        status_source="self-reported, not test-derived (no documented cross-species decline-event corpus is wired).",
        part_13_section=PART_13_MAPPING["F10"],
    ),
    # F11 — SBA accuracy (Part 13 F11)
    FalsifiabilityCondition(
        "F11", "SBA accuracy",
        "Systematic divergence of Sovereign Behavioral Accuracy (SBA) scores from IMF/World Bank composite behavioral indicators",
        "No systematic divergence from IMF/World Bank composites (24-month rolling)",
        "MONITORING", "L8.1", "24-month rolling", 0, time.time(),
        "Falsified by systematic divergence from IMF/World Bank composite behavioral indicators over 24-month "
        "rolling window. SBA engine active with 5 components (0.30/0.25/0.20/0.15/0.10 weights); currently uses "
        "synthetic inputs (audit gap #4); awaiting real IMF/WorldBank DataMapper feed.",
        status_source=("self-reported, not test-derived — SBA computation is unit-tested but 24-month rolling "
                       "divergence vs IMF/World Bank composites is not measured by any test."),
        part_13_section=PART_13_MAPPING["F11"],
    ),
    # F12 — ANIMA calibration (Part 13 F12)
    FalsifiabilityCondition(
        "F12", "ANIMA calibration",
        "Probability distributions consistently miscalibrated (under/over-coverage persists as D(t) grows)",
        "CI_95 calibrated within 95% ± 2% over rolling 90-day window",
        "MONITORING", "L3.3", "90-day rolling", 0, time.time(),
        "Falsified if probability distributions are consistently miscalibrated. "
        "ANIMA outputs probability distributions with CI_95 always present; calibration tracking active.",
        status_source=("self-reported, not test-derived — CI machinery is unit-tested "
                       "(tests/unit/trion_protocol/test_conformal_predictor.py) but 90-day rolling coverage "
                       "against realized outcomes is not measured by any test."),
        part_13_section=PART_13_MAPPING["F12"],
    ),
    # F13 — Entity Resolution (Part 13 F13)
    FalsifiabilityCondition(
        "F13", "Entity Resolution",
        "Known unified actors not clustered at > 95% rate (quarterly audit on labeled actor set)",
        "Known unified actors clustered at > 95% rate (quarterly audit)",
        "MONITORING", "L0.2", "Quarterly audit", 0, time.time(),
        "Falsified if known unified actors are not clustered at > 95% rate. "
        "BEO entity-resolution pipeline active; awaiting labeled unified-actor ground-truth set.",
        status_source=("self-reported, not test-derived (no labeled unified-actor ground-truth set exists in-repo "
                       "for the quarterly audit)."),
        part_13_section=PART_13_MAPPING["F13"],
    ),
    # F14 — Observer Effect corrected (Part 13 F14)
    FalsifiabilityCondition(
        "F14", "Observer Effect corrected",
        "M_adj not lower than M_base for high-OE assets (circular reinforcement not prevented)",
        "M_adj < M_base when OE_factor > 0 (continuous)",
        "PASSING", "L3.2", "Continuous", 1000, time.time(),
        "Falsified if M_adj not lower than M_base for high-OE assets. "
        "M_adj = M_base * (1 - OE); 1,000 cases verified.",
        status_source=("partial — OE computation is unit-tested "
                       "(tests/unit/trion_protocol/test_conformal_predictor.py::test_observer_effect_zero_when_no_signals, "
                       "test_observer_effect_in_unit_interval), but the '1,000 cases' sample_size and 'PASSING' "
                       "are hardcoded, not test output."),
        part_13_section=PART_13_MAPPING["F14"],
    ),
    # F15 — Silence is informative (Part 13 F15)
    FalsifiabilityCondition(
        "F15", "Silence is informative",
        "Gap field in SILENCE signals uncorrelated with next-signal time (6-month rolling)",
        "Gap field in SILENCE signals correlated with next-signal time (6-month rolling window)",
        "MONITORING", "L5", "6-month rolling", 0, time.time(),
        "Falsified if gap field in Silence Signals is uncorrelated with next-signal time. "
        "SILENCE carries gap, limiting_plane, trend, eta. Accumulating recovery-time ground truth.",
        status_source="self-reported, not test-derived (no recovery-time ground-truth dataset exists in-repo).",
        part_13_section=PART_13_MAPPING["F15"],
    ),
]

_REGISTRY: Dict[str, FalsifiabilityCondition] = {c.id: c for c in FALSIFIABILITY_CONDITIONS}


def get_condition(fid: str) -> Optional[FalsifiabilityCondition]:
    return _REGISTRY.get(fid)


def get_all_conditions() -> List[dict]:
    return [{"id": c.id, "claim": c.claim, "test_metric": c.test_metric, "threshold": c.threshold, "status": c.status, "status_source": c.status_source, "plane": c.plane, "window": c.window, "sample_size": c.sample_size, "last_check": int(c.last_check), "notes": c.notes, "part_13_section": c.part_13_section} for c in FALSIFIABILITY_CONDITIONS]


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
    print(f"F1-F15 (Whitepaper Part 13 canonical): {s['total']} total, "
          f"{s['passing']} PASSING, {s['monitoring']} MONITORING, "
          f"{s['conjecture']} CONJECTURE, {s['failing']} FAILING")
    assert s["total"] == 15, f"Expected 15 conditions, got {s['total']}"
    assert s["failing"] == 0, f"F-conditions should not be FAILING: {s}"
    # Part 13 spot-checks: F8 must reference HHI 2500; F15 must be "Silence is informative"
    f8 = get_condition("F8")
    f15 = get_condition("F15")
    assert f8 is not None and ("2500" in f8.threshold or "HHI" in f8.claim), \
        "F8 must reference HHI 2500 (Part 13 F8 Diversity enforced)"
    assert f15 is not None and "silence" in f15.claim.lower(), \
        "F15 must be 'Silence is informative' (Part 13 F15)"
    # Ensure all conditions carry a non-empty part_13_section reference
    for c in FALSIFIABILITY_CONDITIONS:
        assert c.part_13_section.startswith("Part 13 F"), \
            f"{c.id} part_13_section must be canonical Part 13 reference"
    print("Falsifiability Registry (Whitepaper Part 13 canonical): PASS")
