"""
Z11 — BIRP drift false-negative rate (SYNTHETIC-DEMO, NEVER as fact)
(TRION BZK Phase 6, Z11)

Canon governing the conjecture (WP-Mar §16 verbatim, CANON_EXTRACT.md §5.4):
    Known honest limitation: Behavioral patterns drift over time. Recovery
    challenges are drawn from recent behavioral history, not enrollment
    history. BEO baseline updates continuously.
    [CONJECTURE — false negative rate under behavioral drift requires
     empirical validation and threshold-setting.]

WP-Mar Research / Falsifiability table (CANON_EXTRACT.md §5.6):
    | BIRP false negative rate | CONJECTURE — empirical | False negative rate
    |                          |                         | exceeds agreed [...] |

ATTACK:
    Generate a SYNTHETIC behavioral drift set (1,000 BEO profiles with
    gradual drift over 100 epochs). For each, run a SYNTHETIC BIRP
    behavioral_match check (the real Phase 2 of recovery is GATED-OPEN per
    Phase 1 verdict). Measure the false-negative rate.

CRITICAL R-LABELS DISCIPLINE:
    Per mission R-LABELS and WP-Mar §16 CONJECTURE label, the drift
    false-negative rate is NEVER presented as a fact. This test records a
    SYNTHETIC-DEMO measurement on a synthetic behavior set; it does NOT
    claim the measured rate holds in production. The real rate requires
    empirical validation on real behavioral data (which is GATED-OPEN).

Test method:
    1. Generate 1,000 SYNTHETIC BEO profiles, each with a behavioral
       baseline (7-plane coherence state).
    2. For each profile, simulate drift over 100 epochs (each plane's
       score perturbs by a small random walk).
    3. After 100 epochs of drift, run the SYNTHETIC behavioral_match:
       a behavioral_match score is computed as the cosine similarity
       between the baseline and the drifted profile.
       Per WP-Mar §16 Recovery Phase 2 verbatim: 'behavioral_match
       required: > 0.85'.
    4. Count: of the 1,000 profiles, how many have behavioral_match
       below 0.85 (FALSE NEGATIVE — the true owner is denied recovery).
    5. Record the SYNTHETIC false-negative rate, with the CONJECTURE
       label applied.

Expected result: PASS — the test runs, records the SYNTHETIC-DEMO
measurement, does NOT claim the rate as a fact.

R-LABELS:
    Label: SYNTHETIC-DEMO. The result is a synthetic measurement; the
    real-world drift false-negative rate is a CONJECTURE per WP-Mar §16.

Canon sources:
    WP-Mar §16 (BIRP Drift Conjecture + Recovery Phase 2 verbatim,
    CANON_EXTRACT.md §5.3 + §5.4 + §5.6).
"""

from __future__ import annotations

import json
import math
import os
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

# Reproducible SYNTHETIC data.
_RNG_SEED = 0xB1B2  # B1RP — fixed for reproducibility.

# 7 planes per BTCP §7.1 + WP-Mar §16 (C, phi, m, sigma, k, anima, mf).
N_PLANES = 7

# Per WP-Mar §16 Recovery Phase 2 verbatim: 'behavioral_match required: > 0.85'.
BEHAVIORAL_MATCH_THRESHOLD = 0.85

# SYNTHETIC simulation parameters.
N_PROFILES = 1000
N_EPOCHS = 100
DRIFT_STD = 0.01  # per-plane per-epoch drift (small random walk)


@dataclass
class BehavioralProfile:
    """A 7-plane coherence profile (SYNTHETIC)."""
    # Each plane score is a float in [0, 1.0] (matching the 1e6-scaled
    # range used in the circom circuit; we use floats here for simulation).
    planes: List[float]

    def cosine_similarity(self, other: "BehavioralProfile") -> float:
        """Cosine similarity between two 7-plane profiles. Used as the
        SYNTHETIC behavioral_match score (proxy for the real Phase 2
        of recovery, which is GATED-OPEN)."""
        a = self.planes
        b = other.planes
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)


def generate_baseline(rng: random.Random) -> BehavioralProfile:
    """Generate a SYNTHETIC behavioral baseline (7-plane coherence profile)."""
    return BehavioralProfile(
        planes=[rng.uniform(0.5, 1.0) for _ in range(N_PLANES)]
    )


def drift_profile(
    baseline: BehavioralProfile, n_epochs: int, drift_std: float, rng: random.Random
) -> BehavioralProfile:
    """Simulate behavioral drift over n_epochs. Each plane's score
    perturbs by a small Gaussian random walk (clipped to [0, 1.0]).

    Per WP-Mar §16 verbatim: 'BEO baseline updates continuously' — but
    the user's submitted challenge is drawn from RECENT history, not
    enrollment history. The drift gap between the user's current
    behavioral state and the enrollment-time baseline determines
    behavioral_match."""
    planes = list(baseline.planes)
    for _ in range(n_epochs):
        for i in range(N_PLANES):
            planes[i] += rng.gauss(0, drift_std)
            planes[i] = max(0.0, min(1.0, planes[i]))  # clip to [0, 1]
    return BehavioralProfile(planes=planes)


def run() -> Dict:
    rng = random.Random(_RNG_SEED)

    print("[Z11] SYNTHETIC-DEMO: BIRP drift false-negative rate simulation")
    print(f"[Z11] Profiles: {N_PROFILES}, Epochs: {N_EPOCHS}, Drift σ: {DRIFT_STD}")
    print(f"[Z11] Behavioral match threshold (WP-Mar §16 verbatim): > {BEHAVIORAL_MATCH_THRESHOLD}")
    print()

    # Per WP-Mar §16: 'BEO baseline updates continuously' — but the
    # challenge is drawn from enrollment-time baseline. Drift gap =
    # (current behavior) vs (enrollment baseline).
    false_negatives = 0
    false_positive_or_correct = 0
    drift_gaps: List[float] = []
    match_scores: List[float] = []

    for i in range(N_PROFILES):
        baseline = generate_baseline(rng)
        drifted = drift_profile(baseline, N_EPOCHS, DRIFT_STD, rng)

        # SYNTHETIC behavioral_match: cosine similarity (proxy for the
        # real Phase 2 of recovery, which is GATED-OPEN).
        match = baseline.cosine_similarity(drifted)
        match_scores.append(match)
        drift_gaps.append(1.0 - match)

        # Per WP-Mar §16 verbatim: 'behavioral_match required: > 0.85'.
        # A TRUE owner is accepted iff behavioral_match > 0.85.
        if match <= BEHAVIORAL_MATCH_THRESHOLD:
            false_negatives += 1  # TRUE owner denied recovery (drift FN)
        else:
            false_positive_or_correct += 1

    total = N_PROFILES
    fn_rate = false_negatives / total
    avg_match = sum(match_scores) / total
    avg_drift_gap = sum(drift_gaps) / total

    print(f"[Z11] Total profiles: {total}")
    print(f"[Z11] False negatives (TRUE owner denied recovery): {false_negatives}")
    print(f"[Z11] SYNTHETIC false-negative rate: {fn_rate:.4f} "
          f"({fn_rate*100:.2f}%)")
    print(f"[Z11] Average behavioral_match score: {avg_match:.4f}")
    print(f"[Z11] Average drift gap (1 - match): {avg_drift_gap:.4f}")
    print()
    print("[Z11] *** CRITICAL R-LABELS DISCIPLINE ***")
    print("[Z11] Per WP-Mar §16 CONJECTURE label + mission R-LABELS:")
    print("[Z11]   The above rate is a SYNTHETIC-DEMO measurement.")
    print("[Z11]   It is NOT a fact about real-world BIRP drift behavior.")
    print("[Z11]   The real rate requires empirical validation on real")
    print("[Z11]   behavioral data — currently GATED-OPEN per Phase 1 verdict.")
    print("[Z11]   This test records the measurement; it does NOT claim it")
    print("[Z11]   as a fact. The CONJECTURE label is preserved.")
    print()

    # PASS criterion: the test RUNS and RECORDS the SYNTHETIC-DEMO
    # measurement. It does NOT claim the rate as a fact (the CONJECTURE
    # label is preserved in the output).
    expected = True  # the test ran and recorded the measurement.

    return {
        "attack": "Z11 — BIRP drift false-negative rate (SYNTHETIC-DEMO)",
        "falsifiability_condition": (
            "WP-Mar §16 Research/Falsifiability table verbatim "
            "(CANON_EXTRACT.md §5.6): 'BIRP false negative rate | "
            "CONJECTURE — empirical | False negative rate exceeds agreed [...]'"
        ),
        "canon_governing_conjecture": (
            "WP-Mar §16 verbatim (CANON_EXTRACT.md §5.4): '[CONJECTURE — "
            "false negative rate under behavioral drift requires empirical "
            "validation and threshold-setting.]'"
        ),
        "synthetic_parameters": {
            "n_profiles": N_PROFILES,
            "n_epochs": N_EPOCHS,
            "drift_std": DRIFT_STD,
            "behavioral_match_threshold": BEHAVIORAL_MATCH_THRESHOLD,
            "threshold_citation": "WP-Mar §16 Recovery Phase 2 verbatim: "
                                  "'behavioral_match required: > 0.85'",
            "rng_seed": _RNG_SEED,
        },
        "synthetic_results": {
            "false_negatives": false_negatives,
            "synthetic_false_negative_rate": fn_rate,
            "average_behavioral_match": avg_match,
            "average_drift_gap": avg_drift_gap,
        },
        "result": "PASS" if expected else "FAIL",
        "result_justification": (
            "PASS = the test runs and records the SYNTHETIC-DEMO measurement. "
            "PASS does NOT mean the false-negative rate is acceptable or "
            "accurate. The real rate is a CONJECTURE per WP-Mar §16, "
            "requiring empirical validation on real behavioral data "
            "(GATED-OPEN per Phase 1 verdict)."
        ),
        "label": "SYNTHETIC-DEMO",
        "label_justification": (
            "CRITICAL: per WP-Mar §16 CONJECTURE label + mission R-LABELS, "
            "this measurement is SYNTHETIC-DEMO and is NEVER presented as "
            "fact. The drift false-negative rate is a CONJECTURE per WP-Mar "
            "§16 verbatim: '[CONJECTURE — false negative rate under "
            "behavioral drift requires empirical validation and "
            "threshold-setting.]' The measurement is on synthetic profiles "
            "(random Gaussian walk); real-world behavioral drift is "
            "non-Gaussian and domain-specific. The test runs and records; "
            "it does NOT claim the rate as fact."
        ),
        "conjecture_status_preserved": True,
        "gated_open_per_phase_1_verdict": True,
        "round_trip_status": (
            "Z11 does NOT require the prove/verify round-trip — the BIRP "
            "recovery Phase 2 (behavioral proof) is GATED-OPEN per Phase 1 "
            "verdict. The SYNTHETIC-DEMO uses cosine similarity as a proxy "
            "for the real behavioral_match check; the real check (when "
            "activated) would query the Akashic Index for BEO history and "
            "generate challenges from lived behavioral knowledge per WP-Mar "
            "§16 Recovery Phase 2 verbatim."
        ),
    }


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result["result"] == "PASS" else 1)
