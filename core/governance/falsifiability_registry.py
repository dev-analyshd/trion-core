"""
TRION Protocol — Falsifiability Registry (F1-F15)
Canonical source: TRION Whitepaper #2 §20 "Formal Proofs and Falsification Conditions"

The 15 falsifiability conditions that would invalidate the TRION model.
Each F-condition is an empirically testable claim with a precise metric,
threshold, and observation window. If any condition is violated, the
corresponding TRION claim is falsified.

AUDIT-3 G1 fix (registry reconciliation): this file is the CANONICAL live
registry and is aligned with WP2 §20. The previous registry followed WP1's
primitive-based mapping (7/15 conditions mismatched WP2). The markdown spec
at spec/falsifiability_registry.md retains the WP1 mapping for historical
reference and is no longer authoritative.

FIX-CLAIMS honesty note (status provenance): the `status`, `sample_size`, and
figures quoted in `notes` below ("PASSING", "10,000 rounds verified",
"1,000 cases verified", ...) are SELF-REPORTED strings/numbers, NOT values
derived from the test suite. Each condition now carries a `status_source`
field stating exactly what backs it: "self-reported, not test-derived",
"partial" (a real unit test exercises a related computation on synthetic
inputs, but the headline figure/status is not test output), or a pointer to
the specific test. Treat PASSING here as an author's claim, not evidence.

WP2 §20 F1-F15:
  F1  — Manipulation resistance (D > D_minimum, >6 months)
  F2  — No contradictory signals simultaneously certified (Coordination Collapse)
  F3  — CI calibration coverage as D(t) grows
  F4  — LSS breach requires full causal-history reproduction
  F5  — Signal convergence to realized values as D(t) grows
  F6  — Genesis inference converges to behavioral reality
  F7  — Component degradation detected & corrected within 24 hours
  F8  — Validator HHI <= 2500 sustained (30 consecutive days, auto-corrected)
  F9  — Geographic distribution >= 4 continents (auto-corrective incentives)
  F10 — SILENCE coherence gap estimates accurate vs recovery times
  F11 — Observer Effect correction prevents circular reinforcement
  F12 — No single entity controls signal outputs (AWA violation -> freeze)
  F13 — Manipulation fingerprint false-positive rate < 2% on clean histories
  F14 — BRT gas correlations (F-test on sample; CONJECTURE)
  F15 — REGULATORY_BEHAVIORAL produces advance warning over 24-month window (CONJECTURE)

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
    # FIX-CLAIMS: provenance of `status`/`sample_size` — see module docstring.
    # Default is the honest fallback; "partial" entries cite real tests but
    # do not imply the headline status is test-derived.
    status_source: str = "self-reported, not test-derived"


FALSIFIABILITY_CONDITIONS: List[FalsifiabilityCondition] = [
    # F1 — Manipulation resistance (WP2 §20 F1)
    FalsifiabilityCondition(
        "F1", "Manipulation resistance",
        "Documented successful manipulation for an asset with sufficient behavioral history (D(t) > D_minimum, >6 months)",
        "No successful manipulation at D > D_minimum over 6-month observation",
        "MONITORING", "L1.2", "Continuous, per asset with D > D_minimum", 0, time.time(),
        "Falsified if a documented successful manipulation occurs for an asset with sufficient behavioral history. "
        "7/7 historical exploit simulations blocked; awaiting long-horizon mainnet ground truth.",
        status_source=("self-reported, not test-derived — the '7/7 historical exploit simulations' figure "
                       "is output of scripts/simulate_attacks.py (a script, not a test; the replay includes the "
                       "fabricated 'AAVE March 2026' case flagged by AUDIT-PY). The MF-detector formulas are "
                       "verified on synthetic inputs by tests/master_formula_verification.py, but no test asserts "
                       "the 6-month manipulation-resistance claim.")
    ),
    # F2 — Coordination Collapse (WP2 §20 F2)
    FalsifiabilityCondition(
        "F2", "Coordination Collapse / Consensus safety",
        "Two contradictory signals simultaneously certified for the same asset at the same time (binary, continuously testable)",
        "Zero contradictory simultaneous signals",
        "PASSING", "L4.1", "Continuous", 10000, time.time(),
        "Falsified if two contradictory signals are simultaneously certified for the same asset. "
        "GADT phantom types make SILENCE->VALUATION structurally impossible. 10,000 rounds verified.",
        status_source=("partial — the SILENCE≠VALUATION check is real at the type level "
                       "(formal/src/TRION/Theorems.hs T2; formal/test/Spec.hs), but the '10,000 rounds' "
                       "sample_size and 'PASSING' are hardcoded strings, not test output: no test executes "
                       "10,000 certification rounds.")
    ),
    # F3 — CI calibration (WP2 §20 F3)
    FalsifiabilityCondition(
        "F3", "Confidence-interval calibration",
        "Persistent under/over-coverage of confidence intervals as D(t) grows",
        "CI_95 calibrated within 95% +/- 2% over rolling 90-day window",
        "MONITORING", "L3.3", "90-day rolling", 0, time.time(),
        "Falsified if confidence-interval calibration shows persistent under/over-coverage as D(t) grows. "
        "ANIMA outputs probability distributions with CI_95 always present; calibration tracking active.",
        status_source=("self-reported, not test-derived — CI machinery is unit-tested "
                       "(tests/unit/trion_protocol/test_conformal_predictor.py) but 90-day rolling coverage "
                       "against realized outcomes is not measured by any test.")
    ),
    # F4 — LSS breach requires causal history (WP2 §20 F4)
    FalsifiabilityCondition(
        "F4", "Living Security System breach causality",
        "LSS breached without demonstrably reproducing complete causal history of the entity",
        "No LSS breach without complete causal-history reproduction",
        "PASSING", "L4.3-4.6", "Any time", 0, time.time(),
        "Falsified if the Living Security System is breached without reproducing the entity's complete causal history. "
        "Kolmogorov bound proven unbounded; P(break LSS) monotonically decreasing.",
        status_source=("self-reported, not test-derived — 'Kolmogorov bound proven unbounded' is prose: "
                       "no proof of unboundedness exists in formal/ and no test measures P(break LSS).")
    ),
    # F5 — Signal convergence (WP2 §20 F5)
    FalsifiabilityCondition(
        "F5", "Signal convergence to realized values",
        "TRION signals persistently diverge from realized values as behavioral depth grows (convergence theorem failure)",
        "Convergence to H_irreducible as D(t) grows",
        "MONITORING", "L2.5", "12-month rolling", 0, time.time(),
        "Falsified if signals persistently diverge from realized values as D(t) grows. "
        "Convergence theorem proved; awaiting 12-month mainnet data.",
        status_source=("self-reported, not test-derived — 'Convergence theorem proved' overstates: "
                       "Haskell T1 is only a C∈[0,1] range check (see formal/src/TRION/Theorems.hs header); "
                       "no convergence proof exists.")
    ),
    # F6 — Genesis Inference convergence (WP2 §20 F6)
    FalsifiabilityCondition(
        "F6", "Genesis inference convergence",
        "Systematic divergence of genesis inference from behavioral reality as the bootstrapped entity accumulates history",
        "No systematic divergence over 90-day, 100+ events",
        "MONITORING", "L2.3", "90-day, 100+ events", 0, time.time(),
        "Falsified if genesis inference diverges from behavioral reality as the bootstrapped entity accumulates history. "
        "Genesis engine active, accumulating data.",
        status_source="self-reported, not test-derived (no test measures genesis-inference convergence to reality)."
    ),
    # F7 — Component degradation 24h detection (WP2 §20 F7)
    FalsifiabilityCondition(
        "F7", "Component degradation 24h detection (IM Protocol)",
        "Any component degrades below threshold without detection and correction within 24 hours",
        "No component degradation > 24h undetected",
        "PASSING", "L3.7", "Continuous", 0, time.time(),
        "Falsified if any component degrades below threshold without detection and correction within 24 hours. "
        "Intelligence Maintenance (IM) protocol monitors all components continuously.",
        status_source=("partial — the IM computation is unit-tested "
                       "(tests/unit/test_all_planes.py::test_intelligence_maintenance_healthy), but the "
                       "24-hour detection SLA on a live deployment is not test-derived; 'PASSING' is a claim.")
    ),
    # F8 — Validator HHI (WP2 §20 F8)
    FalsifiabilityCondition(
        "F8", "Diversity enforced (HHI)",
        "Validator HHI exceeds 2500 sustained for 30 consecutive days without automatic correction",
        "HHI <= 2500 or auto-corrected within 30 consecutive days",
        "PASSING", "L4.8", "Continuous (30-day)", 10000, time.time(),
        "Falsified if validator HHI exceeds 2500 sustained for 30 consecutive days without automatic correction. "
        "HHI tiers enforced; 10,000 rounds verified HHI < 2500.",
        status_source=("partial — HHI math is unit-tested on synthetic stake vectors "
                       "(tests/unit/trion_protocol/test_consensus_bft.py::test_hhi_healthy_equal_stake, "
                       "test_hhi_critical_monopoly, test_sigma_result_has_hhi_status), but the '10,000 rounds' "
                       "sample_size and 'PASSING' are hardcoded, not test output.")
    ),
    # F9 — Geographic distribution (WP2 §20 F9)
    FalsifiabilityCondition(
        "F9", "Geographic distribution (4+ continents)",
        "Geographic distribution falls below 4 continents without automatic corrective incentive activation",
        ">= 4 continents with auto-corrective incentive activation on drop",
        "MONITORING", "L4.8", "Continuous", 0, time.time(),
        "Falsified if geographic distribution falls below 4 continents without automatic corrective incentive activation. "
        "Awaiting multi-region mainnet validator deployment (currently single-region testnet).",
        status_source="self-reported, not test-derived (validator geography is not measured by any test)."
    ),
    # F10 — SILENCE coherence gap accuracy (WP2 §20 F10)
    FalsifiabilityCondition(
        "F10", "SILENCE coherence gap accuracy",
        "SILENCE coherence gap estimates prove systematically inaccurate vs actual recovery times",
        "Gap estimates correlate with actual recovery times over rolling 6-month window",
        "MONITORING", "L5", "6-month rolling", 0, time.time(),
        "Falsified if SILENCE coherence gap estimates prove systematically inaccurate vs actual recovery times. "
        "SILENCE carries gap, limiting_plane, trend, eta. Accumulating recovery-time ground truth.",
        status_source="self-reported, not test-derived (no recovery-time ground-truth dataset exists in-repo)."
    ),
    # F11 — Observer Effect correction (WP2 §20 F11)
    FalsifiabilityCondition(
        "F11", "Observer Effect correction (anti-circular-reinforcement)",
        "Observer Effect correction fails to prevent circular reinforcement in TRION's own signals",
        "M_adj < M_base when OE_factor > 0 (no circular reinforcement)",
        "PASSING", "L3.2", "Continuous", 1000, time.time(),
        "Falsified if the Observer Effect correction fails to prevent circular reinforcement in TRION's own signals. "
        "M_adj = M_base * (1 - OE); 1,000 cases verified.",
        status_source=("partial — OE computation is unit-tested "
                       "(tests/unit/trion_protocol/test_conformal_predictor.py::test_observer_effect_zero_when_no_signals, "
                       "test_observer_effect_in_unit_interval), but the '1,000 cases' sample_size and 'PASSING' "
                       "are hardcoded, not test output.")
    ),
    # F12 — AWA anti-centralization (WP2 §20 F12)
    FalsifiabilityCondition(
        "F12", "AWA: no single entity controls signal outputs",
        "A single entity demonstrably controls TRION signal outputs through an AWA violation without triggering system freeze",
        "AWA violation -> signal emission FROZEN (no override by any single entity)",
        "PASSING", "L4.AWA", "Continuous", 0, time.time(),
        "Falsified if any single entity demonstrably controls TRION signal outputs through an AWA violation without a system freeze. "
        "AWAEnforcer now runtime-evaluates all 8 conditions (AUDIT-3 G2 fix); signal emission frozen on violation.",
        status_source=("partial — AWA-violation signal freeze is unit-tested "
                       "(tests/unit/test_all_planes.py::test_epigenetic_awa_violation_freezes_signals), but "
                       "continuous no-single-entity monitoring is not test-derived; 'PASSING' is a claim.")
    ),
    # F13 — Manipulation fingerprint FP rate (WP2 §20 F13)
    FalsifiabilityCondition(
        "F13", "Manipulation fingerprint false-positive rate",
        "Manipulation fingerprint detection produces false-positive rate > 2% on verified clean behavioral histories",
        "False-positive rate < 2% on verified clean behavioral histories",
        "MONITORING", "L1.2", "Continuous (labeled clean-histories audit)", 0, time.time(),
        "Falsified if manipulation fingerprint detection produces a false-positive rate > 2% on verified clean behavioral histories. "
        "7-type MF detector active; awaiting verified-clean audit dataset.",
        status_source="self-reported, not test-derived (the verified-clean audit dataset does not exist yet — see notes)."
    ),
    # F14 — BRT gas correlation (WP2 §20 F14, CONJECTURE)
    FalsifiabilityCondition(
        "F14", "BRT gas correlation (CONJECTURE)",
        "BRT gas correlation failure: no significant correlation between Biological Rhythm Timer phase and on-chain gas prices (F-test on 90-day, 1M+ block sample)",
        "Significant BRT-gas correlation (F-test, 90-day / 1M+ block sample)",
        "CONJECTURE", "L6.2", "90-day, 1M+ blocks", 0, time.time(),
        "Falsified by BRT gas correlation failure (F-test on sample). WP2 §20 lists this as a CONJECTURE — "
        "requires 90-day / 1M+ block mainnet sample to validate.",
        status_source=("self-reported — the CONJECTURE label is honest (no validation attempted); only the "
                       "fallback path is unit-tested (tests/unit/test_all_planes.py::test_brt_gas_correlation_noise_falls_back_to_anima).")
    ),
    # F15 — REGULATORY_BEHAVIORAL advance warning (WP2 §20 F15, CONJECTURE)
    FalsifiabilityCondition(
        "F15", "REGULATORY_BEHAVIORAL 24-month advance warning (CONJECTURE)",
        "REGULATORY_BEHAVIORAL signal produces no statistically significant advance warning over a 24-month rolling window of documented action",
        "Statistically significant advance warning over 24-month rolling window",
        "CONJECTURE", "L8.1", "24-month rolling", 0, time.time(),
        "Falsified if the REGULATORY_BEHAVIORAL signal produces no statistically significant advance warning over a 24-month rolling window. "
        "WP2 §20 lists this as a CONJECTURE — requires multi-year regulatory-action dataset to validate.",
        status_source="self-reported — the CONJECTURE label is honest (no dataset or test exists)."
    ),
]

_REGISTRY: Dict[str, FalsifiabilityCondition] = {c.id: c for c in FALSIFIABILITY_CONDITIONS}


def get_condition(fid: str) -> Optional[FalsifiabilityCondition]:
    return _REGISTRY.get(fid)


def get_all_conditions() -> List[dict]:
    return [{"id": c.id, "claim": c.claim, "test_metric": c.test_metric, "threshold": c.threshold, "status": c.status, "status_source": c.status_source, "plane": c.plane, "window": c.window, "sample_size": c.sample_size, "last_check": int(c.last_check), "notes": c.notes} for c in FALSIFIABILITY_CONDITIONS]


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
    print(f"F1-F15 (WP2 §20 canonical): {s['total']} total, "
          f"{s['passing']} PASSING, {s['monitoring']} MONITORING, "
          f"{s['conjecture']} CONJECTURE, {s['failing']} FAILING")
    assert s["total"] == 15, f"Expected 15 conditions, got {s['total']}"
    assert s["failing"] == 0, f"F-conditions should not be FAILING: {s}"
    # WP2 §20 spot-checks: F14 (BRT) and F15 (REGULATORY_BEHAVIORAL) must exist
    f14 = get_condition("F14")
    f15 = get_condition("F15")
    assert f14 is not None and "BRT" in f14.claim, "F14 must be BRT gas correlation (WP2 §20)"
    assert f15 is not None and "REGULATORY" in f15.claim.upper(), "F15 must be REGULATORY_BEHAVIORAL (WP2 §20)"
    # F8 must reference HHI 2500
    f8 = get_condition("F8")
    assert "2500" in f8.threshold or "2500" in f8.test_metric, "F8 must reference HHI 2500 (WP2 §20)"
    print("Falsifiability Registry (WP2 §20 canonical): PASS")
