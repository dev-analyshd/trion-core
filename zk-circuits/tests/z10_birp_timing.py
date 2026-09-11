"""
Z10 — BIRP timing/length exactness
(TRION BZK Phase 6, Z10)

Canon governing BIRP Recovery Phase 1 (WP-Mar §16 verbatim,
CANON_EXTRACT.md §5.3):
    Phase 1: DNA_Code verification
        timing_window: exact — zero tolerance
        length_check:    exact — partial submission silently rejected
        hash_check:      dual-strand verification

ATTACK:
    Test the BIRP anchor store (Phase 2.4, completed by A-REG).
    Submit a BIRP enrollment with correct timing/length → succeeds.
    Submit with off-by-one timing → silently rejected.
    Submit with partial length → silently rejected.

IMPORTANT — scope nuance (per Phase 1 verdict, FEASIBILITY_AND_SETUP.md §3 S5):
    The Phase 2.4 birp_store implements the ENROLLMENT layer (BIRP_Enrollment
    per WP-Mar §16). The timing/length EXACTNESS checks described in WP-Mar
    §16 Recovery Phase 1 belong to the RECOVERY path, which is GATED-OPEN
    per Phase 1 verdict (drift false-negative rate conjecture unresolved —
    see CW-2 + §3 S5 in FEASIBILITY_AND_SETUP.md).

    So this test exercises BOTH:
      (a) the ENROLLMENT store's round-trip (VERIFIED — actual Phase 2.4 code):
            enroll() → get_anchor() → expected anchor.
      (b) the RECOVERY Phase 1 timing/length checks (SYNTHETIC-DEMO — a
          stubbed recovery-verification function that demonstrates what
          the GATED-OPEN recovery path WOULD enforce per WP-Mar §16
          Recovery Phase 1 verbatim).

Test method:
    Part A — ENROLLMENT round-trip (VERIFIED, real Phase 2.4 code):
      1. Enroll an entity with valid inputs.
      2. Verify the stored anchor matches hash_dna.birp_anchor(...) for the
         same inputs.
      3. Verify re-enrollment with different timestamp produces different
         anchor (parameter sensitivity).
    Part B — RECOVERY Phase 1 timing/length exactness (SYNTHETIC-DEMO):
      1. Correct timing_window + correct length → ACCEPTED.
      2. Off-by-one timing_window (early) → SILENTLY REJECTED.
      3. Off-by-one timing_window (late)  → SILENTLY REJECTED.
      4. Partial length                  → SILENTLY REJECTED.
      5. Off-by-one length                → SILENTLY REJECTED.

R-LABELS:
    Part A: VERIFIED (real Phase 2.4 code at commitments/birp_store.py).
    Part B: SYNTHETIC-DEMO (stubbed recovery check; real recovery path is
            GATED-OPEN per Phase 1 verdict).

Canon sources:
    WP-Mar §16 (BIRP Enrollment + Recovery Phase 1 verbatim, CANON_EXTRACT.md
    §5.2 + §5.3).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

# Make the Phase 2 commitment helpers importable.
_THIS_DIR = Path(__file__).resolve().parent
_COMMITMENTS_DIR = _THIS_DIR.parent / "commitments"
sys.path.insert(0, str(_COMMITMENTS_DIR))

import hash_dna  # noqa: E402  (Phase 2.1 helper — birp_anchor())
import birp_store  # noqa: E402  (Phase 2.4 store — the layer under test)


# ── Part A: ENROLLMENT round-trip (VERIFIED, real Phase 2.4 code) ────────────

def test_enrollment_round_trip() -> Dict:
    """Test the BIRP anchor store's enrollment round-trip on the actual
    Phase 2.4 code (commitments/birp_store.py)."""
    print("[Z10-A] ENROLLMENT round-trip test on real Phase 2.4 code...")

    results: Dict = {"tests": [], "passed": 0, "failed": 0}

    def record(name: str, passed: bool, detail: str) -> None:
        results["tests"].append({"test": name, "passed": passed, "detail": detail})
        if passed:
            results["passed"] += 1
        else:
            results["failed"] += 1
        print(f"  [{('PASS' if passed else 'FAIL')}] {name}: {detail}")

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_birp_z10.db"
        store = birp_store.BirpStore(db_path)

        # Test 1: enroll + get_anchor round-trip.
        eid = "entity_z10_test"
        beo = b"\x11" * 32
        hdna_code = b"\x22" * 32  # Hash(user-secret) — already hashed
        ts = 1_700_000_000
        seed = b"\x33" * 32
        anchor = store.enroll(eid, beo, hdna_code, ts, seed)
        retrieved = store.get_anchor(eid)
        ok = (retrieved == anchor)
        record(
            "enroll + get_anchor round-trip",
            ok,
            f"retrieved={retrieved.hex()[:16] if retrieved else 'None'}... vs "
            f"anchor={anchor.hex()[:16]}..."
        )

        # Test 2: stored anchor matches hash_dna.birp_anchor(...)
        expected_anchor = hash_dna.birp_anchor(beo, hdna_code, ts, seed)
        ok = (anchor == expected_anchor)
        record(
            "stored anchor matches hash_dna.birp_anchor(...)",
            ok,
            f"anchor={anchor.hex()[:16]}... vs expected={expected_anchor.hex()[:16]}..."
        )

        # Test 3: re-enrollment with different timestamp → different anchor.
        anchor2 = store.enroll(eid, beo, hdna_code, ts + 1, seed)
        ok = (anchor2 != anchor)
        record(
            "re-enrollment with different ts → different anchor",
            ok,
            f"anchor2={anchor2.hex()[:16]}... vs anchor={anchor.hex()[:16]}..."
        )

        # Test 4: R-FAILCLOSED — schema drift causes refusal.
        with store._connect() as conn:
            conn.execute("ALTER TABLE birp_anchors ADD COLUMN leak TEXT")
            conn.commit()
        try:
            store.enroll("e2", beo, hdna_code, ts, seed)
            record(
                "R-FAILCLOSED: schema drift → enroll refuses",
                False,
                "expected SchemaMismatchError, got NO ERROR (R-FAILCLOSED broken)"
            )
        except birp_store.SchemaMismatchError:
            record(
                "R-FAILCLOSED: schema drift → enroll refuses",
                True,
                "SchemaMismatchError raised (R-FAILCLOSED holds)"
            )

    print(f"[Z10-A] ENROLLMENT round-trip: {results['passed']} passed, "
          f"{results['failed']} failed.")
    return results


# ── Part B: RECOVERY Phase 1 timing/length exactness (SYNTHETIC-DEMO) ────────

@dataclass
class RecoverySubmission:
    """A simulated BIRP recovery Phase 1 submission. The user submits their
    DNA_Code content + their claimed timing window + length."""
    submitted_content: bytes        # the user's claimed DNA_Code content
    submitted_length: int           # the user's claimed length
    submitted_timing_window: int    # the user's claimed timing window (seconds since enrollment)
    actual_length: int              # the TRUE length (enrollment-time)
    actual_timing_window: int        # the TRUE timing window (enrollment-time)


@dataclass
class RecoveryVerifier:
    """A SYNTHETIC-DEMO stub of the WP-Mar §16 Recovery Phase 1 verifier.

    The real recovery path is GATED-OPEN per Phase 1 verdict (drift
    false-negative conjecture unresolved). This stub demonstrates what
    the recovery path WOULD enforce per WP-Mar §16 Recovery Phase 1
    verbatim:
        timing_window: exact — zero tolerance
        length_check:    exact — partial submission silently rejected
        hash_check:      dual-strand verification
    """
    expected_length: int            # the TRUE length enrolled
    expected_timing_window: int     # the TRUE timing window enrolled

    def verify(self, sub: RecoverySubmission) -> bool:
        """Returns True if the submission matches both timing AND length
        EXACTLY (zero tolerance per WP-Mar §16 verbatim). Returns False
        (silently rejected) on ANY deviation.

        Per WP-Mar §16 verbatim: 'partial submission silently rejected'
        (no error message — silent rejection).
        """
        # Timing check: EXACT, zero tolerance.
        if sub.submitted_timing_window != self.expected_timing_window:
            return False  # silently rejected
        # Length check: EXACT, zero tolerance.
        if sub.submitted_length != self.expected_length:
            return False  # silently rejected (partial or off-by-one)
        # Hash check: dual-strand verification (synthetic — assume passes
        # if length + timing match exactly, since the user knows the content).
        return True


def test_recovery_timing_length() -> Dict:
    """Test the WP-Mar §16 Recovery Phase 1 timing/length exactness via
    a SYNTHETIC-DEMO stub verifier."""
    print("[Z10-B] RECOVERY Phase 1 timing/length exactness (SYNTHETIC-DEMO)...")

    # The enrollment established:
    #   - DNA_Code length: 64 bytes (user-defined, kept secret per WP-Mar §16)
    #   - timing_window: 3600 seconds (user-defined change schedule, secret)
    expected_length = 64
    expected_timing_window = 3600  # 1 hour

    verifier = RecoveryVerifier(
        expected_length=expected_length,
        expected_timing_window=expected_timing_window,
    )

    results: Dict = {"tests": [], "passed": 0, "failed": 0}

    def record(name: str, expected_accept: bool, actual_accept: bool) -> None:
        ok = (expected_accept == actual_accept)
        results["tests"].append({
            "test": name,
            "expected": "ACCEPT" if expected_accept else "REJECT",
            "actual": "ACCEPT" if actual_accept else "REJECT",
            "passed": ok,
        })
        if ok:
            results["passed"] += 1
        else:
            results["failed"] += 1
        print(f"  [{('PASS' if ok else 'FAIL')}] {name}: "
              f"expected={'ACCEPT' if expected_accept else 'REJECT'}, "
              f"actual={'ACCEPT' if actual_accept else 'REJECT'}")

    # Test 1: correct timing + correct length → ACCEPTED.
    sub_correct = RecoverySubmission(
        submitted_content=b"x" * 64,
        submitted_length=64,
        submitted_timing_window=3600,
        actual_length=64,
        actual_timing_window=3600,
    )
    record(
        "correct timing + correct length → ACCEPTED",
        expected_accept=True,
        actual_accept=verifier.verify(sub_correct),
    )

    # Test 2: off-by-one timing (early) → SILENTLY REJECTED.
    sub_early = RecoverySubmission(
        submitted_content=b"x" * 64,
        submitted_length=64,
        submitted_timing_window=3599,  # 1 second early
        actual_length=64,
        actual_timing_window=3600,
    )
    record(
        "off-by-one timing (early, 3599 vs 3600) → SILENTLY REJECTED",
        expected_accept=False,
        actual_accept=verifier.verify(sub_early),
    )

    # Test 3: off-by-one timing (late) → SILENTLY REJECTED.
    sub_late = RecoverySubmission(
        submitted_content=b"x" * 64,
        submitted_length=64,
        submitted_timing_window=3601,  # 1 second late
        actual_length=64,
        actual_timing_window=3600,
    )
    record(
        "off-by-one timing (late, 3601 vs 3600) → SILENTLY REJECTED",
        expected_accept=False,
        actual_accept=verifier.verify(sub_late),
    )

    # Test 4: partial length → SILENTLY REJECTED.
    sub_partial = RecoverySubmission(
        submitted_content=b"x" * 63,  # 1 byte short
        submitted_length=63,           # partial
        submitted_timing_window=3600,
        actual_length=64,
        actual_timing_window=3600,
    )
    record(
        "partial length (63 vs 64) → SILENTLY REJECTED",
        expected_accept=False,
        actual_accept=verifier.verify(sub_partial),
    )

    # Test 5: off-by-one length → SILENTLY REJECTED.
    sub_off = RecoverySubmission(
        submitted_content=b"x" * 65,  # 1 byte over
        submitted_length=65,
        submitted_timing_window=3600,
        actual_length=64,
        actual_timing_window=3600,
    )
    record(
        "off-by-one length (65 vs 64) → SILENTLY REJECTED",
        expected_accept=False,
        actual_accept=verifier.verify(sub_off),
    )

    print(f"[Z10-B] RECOVERY Phase 1 timing/length: {results['passed']} passed, "
          f"{results['failed']} failed.")
    return results


def run() -> Dict:
    print("=== Z10 — BIRP timing/length exactness ===")
    print("=== Per WP-Mar §16 Recovery Phase 1 verbatim ===")
    print()
    print("[Z10] Part A — ENROLLMENT round-trip (VERIFIED, real Phase 2.4 code):")
    part_a = test_enrollment_round_trip()
    print()
    print("[Z10] Part B — RECOVERY Phase 1 timing/length (SYNTHETIC-DEMO stub):")
    part_b = test_recovery_timing_length()
    print()

    expected = (part_a["failed"] == 0) and (part_b["failed"] == 0)
    print(f"[Z10] Overall: {'PASS' if expected else 'FAIL'}")
    print(f"[Z10] Labels:")
    print(f"       Part A (ENROLLMENT round-trip): VERIFIED")
    print(f"       Part B (RECOVERY Phase 1 timing/length): SYNTHETIC-DEMO")

    return {
        "attack": "Z10 — BIRP timing/length exactness",
        "falsifiability_condition": "WP-Mar §16 Recovery Phase 1 verbatim "
                                    "(CANON_EXTRACT.md §5.3): "
                                    "'timing_window: exact — zero tolerance; "
                                    "length_check: exact — partial submission "
                                    "silently rejected'",
        "part_a_enrollment_round_trip": {
            "label": "VERIFIED",
            "label_justification": (
                "Tests the actual Phase 2.4 birp_store at "
                "zk-circuits/commitments/birp_store.py — enroll() + get_anchor() "
                "+ R-FAILCLOSED schema-drift refusal. Real code path, real SQLite "
                "DB, real Hash_DNA output."
            ),
            "results": part_a,
        },
        "part_b_recovery_timing_length": {
            "label": "SYNTHETIC-DEMO",
            "label_justification": (
                "Tests a stubbed RecoveryVerifier that demonstrates what the "
                "GATED-OPEN recovery path WOULD enforce per WP-Mar §16 Recovery "
                "Phase 1 verbatim. The real recovery path is GATED-OPEN per "
                "Phase 1 verdict (drift false-negative conjecture unresolved — "
                "see FEASIBILITY_AND_SETUP.md §3 S5 + CANON_EXTRACT.md §5.4)."
            ),
            "results": part_b,
        },
        "result": "PASS" if expected else "FAIL",
        "scope_nuance": (
            "The Phase 2.4 birp_store implements the ENROLLMENT layer "
            "(BIRP_Enrollment per WP-Mar §16). The timing/length exactness "
            "checks described in WP-Mar §16 Recovery Phase 1 belong to the "
            "RECOVERY path, which is GATED-OPEN per Phase 1 verdict. This "
            "test exercises both: (A) the real enrollment round-trip "
            "(VERIFIED) and (B) the recovery timing/length checks via a "
            "synthetic stub (SYNTHETIC-DEMO, real recovery path GATED-OPEN)."
        ),
        "round_trip_status": (
            "Z10 does NOT require the prove/verify round-trip — BIRP is hash-"
            "only per WP-Mar §16 (BIRP_Enrollment stores BIRP_anchor = "
            "Hash_DNA(...)). There is no ZK circuit for S5 enrollment; the "
            "recovery path (when activated) would use multi-factor verification, "
            "not a single SNARK."
        ),
    }


if __name__ == "__main__":
    result = run()
    print()
    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result["result"] == "PASS" else 1)
