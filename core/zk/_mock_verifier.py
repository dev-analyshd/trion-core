"""
TRION BZK Phase 5 — MockVerifier (testing twin).

Per mission Phase 5 (A-INT — integration engineer):

    "the prove/verify round-trip is `[OPEN]` (BLOCKER per Phase 3 — Groth16
    setup time exceeds sandbox timeout). Therefore your integration tests
    must use a `MockVerifier` that returns `true` for any well-formed proof
    and `false` for malformed ones. The MockVerifier is the testing twin;
    the real verifier.sol (exported via `snarkjs zkey export solidityverifier`)
    drops into the same `setVerifier(circuitId, address)` interface when the
    BLOCKER closes. This is R-LABELS compliant — label all integration tests
    as `SYNTHETIC-DEMO` per the mission's evidence labels."

This module provides the Python twin of:

  • contracts/zk/test/MockComplementarityGroth16Verifier.sol  (BZK Phase 4.3)
  • contracts/zk/test/MockTravelRuleVerifier.sol               (BZK Phase 4.1)

Both Solidity mocks return a configurable bool to enable positive / negative
proof verification tests without requiring a real Groth16 trusted setup
(per Phase 1 §1 BLOCKER: setup time >110s exceeds sandbox timeout). The Python
twins follow the same contract:

  • MockComplementarityVerifier.verify(proof, public_inputs) -> bool
      TRUE iff proof is well-formed (256 bytes — 8 Groth16 field elements,
      per BTCP §5.6 + Phase 1 MEASURED circuit, 5 public inputs) AND
      len(public_inputs) == 5.

  • MockTravelRuleVerifier.verify(proof, public_inputs) -> bool
      TRUE iff proof is well-formed (non-empty, ≥32 bytes — covers both
      Groth16 ~200 bytes and PLONK ~400-500 bytes per BTCP Fix 1 Step 3)
      AND len(public_inputs) == 3 (per BTCP Fix 1 Step 3 verbatim:
      `[transaction_hash, jurisdiction_id, disclosure_hash]`).

Malformed inputs (empty proof, wrong length, wrong public-inputs count)
return False — the testing twin mirrors the R-FAILCLOSED contract behavior
(revert TravelRuleProofInvalid / ComplementarityProofFailed becomes False).

R-LABELS: every test using these mocks MUST be labelled `SYNTHETIC-DEMO`
— the mocks are not cryptographic verifiers. The mocks assert that the
integration plumbing is correct; they do NOT assert that the underlying
SNARK is sound. SNARK soundness is a property of the Phase-3 MEASURED
circuits (zk_complementarity_proof 2,686 constraints; zk_travel_rule
1,179 constraints; zk_iap_share_proof 1,078 constraints — see
docs/zk/PHASE3_BENCHMARKS.md) and is gated `[OPEN]` per the BLOCKER
PROTOCOL until the Groth16/PLONK trusted setup runs in a non-sandbox
environment.
"""

from __future__ import annotations

from typing import Sequence

__all__ = [
    "WELL_FORMED_PROOF_BYTES_GROTH16",
    "WELL_FORMED_PROOF_MIN_BYTES",
    "COMPLEMENTARITY_PUBLIC_INPUTS_LEN",
    "TRAVEL_RULE_PUBLIC_INPUTS_LEN",
    "MockComplementarityVerifier",
    "MockTravelRuleVerifier",
    "MockIAPShareVerifier",
]


# ── Well-formed proof size constants ─────────────────────────────────────────
#
# Per BTCP §5.6 closing note verbatim: "Groth16 proof: ~200 bytes." The
# ComplementarityVerifier wrapper (Phase 4.3) accepts a 256-byte serialized
# proof (8 field elements × 32 bytes — see docs/zk/PHASE3_BENCHMARKS.md §3
# and contracts/zk/ComplementarityVerifier.sol::PROOF_LEN_BYTES).
WELL_FORMED_PROOF_BYTES_GROTH16 = 256  # 8 × 32 — Groth16 (a, b, c tuples)

# Per BTCP Fix 1 Step 3 verbatim: PLONK proofs are ~400-500 bytes; the
# TravelRuleCompliance.sol wrapper accepts either. We accept any non-empty
# proof ≥32 bytes as "well-formed" for the travel rule — the real verifier
# contract (snarkjs-exported) enforces the exact length at verify time.
WELL_FORMED_PROOF_MIN_BYTES = 32

# Per Phase 1 MEASURED circuit (docs/zk/FEASIBILITY_AND_SETUP.md §2):
#   zk_complementarity_proof:  5 public inputs
#   zk_travel_rule:            3 public inputs (BTCP Fix 1 Step 3 verbatim)
#   zk_iap_share_proof:        3 public inputs
COMPLEMENTARITY_PUBLIC_INPUTS_LEN = 5
TRAVEL_RULE_PUBLIC_INPUTS_LEN = 3
IAP_SHARE_PUBLIC_INPUTS_LEN = 3


# ── MockComplementarityVerifier ───────────────────────────────────────────────
#
# Twin of contracts/zk/test/MockComplementarityGroth16Verifier.sol.
# Returns True for any well-formed Groth16 proof (256 bytes) with 5 public
# inputs — i.e. the positive path. Returns False for malformed inputs
# (empty proof, wrong length, wrong public-inputs count) — i.e. the
# negative path that mirrors R-FAILCLOSED `ComplementarityProofFailed`.

class MockComplementarityVerifier:
    """Testing twin of the snarkjs-generated Groth16 verifier for the
    zk_complementarity_proof circuit (BTCP §5.6 Phase 2).

    verify(proof, public_inputs) -> True iff:
      • len(proof) == 256 (8 Groth16 field elements × 32 bytes)
      • len(public_inputs) == 5 (per Phase 1 MEASURED circuit)

    R-LABELS: SYNTHETIC-DEMO. NOT a cryptographic verifier — asserts only
    that the integration plumbing is correct, not that the SNARK is sound.
    SNARK soundness is a property of the Phase-3 MEASURED circuit (2,686
    constraints) and is gated `[OPEN]` per the BLOCKER PROTOCOL.
    """

    circuit_id_label = "zk_complementarity_proof/v1"  # for log lines only
    expected_proof_len = WELL_FORMED_PROOF_BYTES_GROTH16
    expected_public_inputs_len = COMPLEMENTARITY_PUBLIC_INPUTS_LEN

    def __init__(self, *, return_value: bool | None = None) -> None:
        # If return_value is None (default), the verifier applies the
        # well-formedness check (True for well-formed, False for malformed).
        # If set explicitly, the verifier returns that value unconditionally
        # (matching the Solidity mock's constructor bool flag).
        self._override = return_value

    def verify(self, proof: bytes, public_inputs: Sequence[int]) -> bool:
        if self._override is not None:
            return bool(self._override)
        if not isinstance(proof, (bytes, bytearray)):
            return False
        if len(proof) != self.expected_proof_len:
            return False
        try:
            _ = list(public_inputs)
        except TypeError:
            return False
        if len(public_inputs) != self.expected_public_inputs_len:
            return False
        return True


# ── MockTravelRuleVerifier ───────────────────────────────────────────────────
#
# Twin of contracts/zk/test/MockTravelRuleVerifier.sol. Returns True for
# any well-formed proof (non-empty, ≥32 bytes — accepts both Groth16 and
# PLONK per BTCP Fix 1 Step 3) with exactly 3 public inputs
# (transaction_hash, jurisdiction_id, disclosure_hash).

class MockTravelRuleVerifier:
    """Testing twin of the snarkjs-generated verifier for the zk_travel_rule
    circuit (BTCP Fix 1 Step 3).

    verify(proof, public_inputs) -> True iff:
      • len(proof) >= 32 (well-formed — accepts Groth16 ~200 bytes or
        PLONK ~400-500 bytes per BTCP Fix 1 Step 3 + Phase 1 §3 decision)
      • len(public_inputs) == 3 per BTCP Fix 1 Step 3 verbatim:
        [transaction_hash, jurisdiction_id, disclosure_hash]

    R-LABELS: SYNTHETIC-DEMO. NOT a cryptographic verifier.
    """

    circuit_id_label = "zk_travel_rule/v1"  # for log lines only
    expected_proof_min_len = WELL_FORMED_PROOF_MIN_BYTES
    expected_public_inputs_len = TRAVEL_RULE_PUBLIC_INPUTS_LEN

    def __init__(self, *, return_value: bool | None = None) -> None:
        self._override = return_value

    def verify(self, proof: bytes, public_inputs: Sequence[int]) -> bool:
        if self._override is not None:
            return bool(self._override)
        if not isinstance(proof, (bytes, bytearray)):
            return False
        if len(proof) < self.expected_proof_min_len:
            return False
        try:
            _ = list(public_inputs)
        except TypeError:
            return False
        if len(public_inputs) != self.expected_public_inputs_len:
            return False
        return True


# ── MockIAPShareVerifier ──────────────────────────────────────────────────────
#
# Python twin for the snarkjs-generated verifier for the zk_iap_share_proof
# circuit (BTCP §5.3). Used by the IAP transparent module's `[OPEN]` ZK
# share-proof path placeholder (see iap_transparent.py). The transparent
# path is the live default per R-ORDER; the ZK path is gated `[OPEN]`.

class MockIAPShareVerifier:
    """Testing twin of the snarkjs-generated verifier for the
    zk_iap_share_proof circuit (BTCP §5.3).

    R-ORDER: the ZK IAP share-proof path is `[OPEN]` per Phase 3 BLOCKER.
    This mock is provided so the integration plumbing can be tested now;
    it does NOT assert that the underlying SNARK is sound.

    verify(proof, public_inputs) -> True iff:
      • len(proof) >= 32 (well-formed)
      • len(public_inputs) == 3 (per BTCP §5.3 + Phase 1 MEASURED circuit:
        total_value, pool_direction_hash, merkle_root)
    """

    circuit_id_label = "zk_iap_share_proof/v1"  # for log lines only
    expected_proof_min_len = WELL_FORMED_PROOF_MIN_BYTES
    expected_public_inputs_len = IAP_SHARE_PUBLIC_INPUTS_LEN

    def __init__(self, *, return_value: bool | None = None) -> None:
        self._override = return_value

    def verify(self, proof: bytes, public_inputs: Sequence[int]) -> bool:
        if self._override is not None:
            return bool(self._override)
        if not isinstance(proof, (bytes, bytearray)):
            return False
        if len(proof) < self.expected_proof_min_len:
            return False
        try:
            _ = list(public_inputs)
        except TypeError:
            return False
        if len(public_inputs) != self.expected_public_inputs_len:
            return False
        return True


# ── Self-test ────────────────────────────────────────────────────────────────

def _self_test() -> dict:
    """Deterministic self-test of the MockVerifier twins.

    Verifies:
      1. MockComplementarityVerifier: well-formed (256 bytes, 5 PI) → True.
      2. MockComplementarityVerifier: malformed (empty / wrong len / wrong PI count) → False.
      3. MockTravelRuleVerifier: well-formed (≥32 bytes, 3 PI) → True.
      4. MockTravelRuleVerifier: malformed (empty / wrong PI count) → False.
      5. MockIAPShareVerifier: well-formed (≥32 bytes, 3 PI) → True.
      6. Explicit override (return_value=True / False) returns that value
         unconditionally, matching the Solidity mock constructor flag.
    """
    out: dict = {}

    # 1. MockComplementarityVerifier well-formed → True.
    cv = MockComplementarityVerifier()
    ok = cv.verify(b"\x01" * 256, [1, 2, 3, 4, 5])
    assert ok is True, "well-formed complementarity proof must verify True"

    # 2. Malformed → False.
    assert cv.verify(b"", [1, 2, 3, 4, 5]) is False, "empty proof must fail"
    assert cv.verify(b"\x01" * 128, [1, 2, 3, 4, 5]) is False, "wrong-length proof must fail"
    assert cv.verify(b"\x01" * 256, [1, 2, 3]) is False, "wrong PI count must fail"
    assert cv.verify(b"\x01" * 256, "not-a-list") is False, "non-sequence PI must fail"

    # 3. MockTravelRuleVerifier well-formed → True.
    tv = MockTravelRuleVerifier()
    assert tv.verify(b"\x01" * 200, [1, 2, 3]) is True, "Groth16-shaped travel rule proof must verify"
    assert tv.verify(b"\x01" * 450, [1, 2, 3]) is True, "PLONK-shaped travel rule proof must verify"

    # 4. Malformed → False.
    assert tv.verify(b"", [1, 2, 3]) is False, "empty proof must fail"
    assert tv.verify(b"\x01" * 16, [1, 2, 3]) is False, "too-short proof must fail"
    assert tv.verify(b"\x01" * 200, [1, 2]) is False, "wrong PI count must fail"

    # 5. MockIAPShareVerifier well-formed → True.
    iv = MockIAPShareVerifier()
    assert iv.verify(b"\x01" * 200, [1, 2, 3]) is True, "well-formed IAP proof must verify"
    assert iv.verify(b"", [1, 2, 3]) is False, "empty IAP proof must fail"
    assert iv.verify(b"\x01" * 200, [1, 2]) is False, "wrong IAP PI count must fail"

    # 6. Explicit override.
    cv_true = MockComplementarityVerifier(return_value=True)
    cv_false = MockComplementarityVerifier(return_value=False)
    assert cv_true.verify(b"", []) is True, "override=True must return True unconditionally"
    assert cv_false.verify(b"\x01" * 256, [1, 2, 3, 4, 5]) is False, "override=False must return False unconditionally"

    out["all_passed"] = True
    return out


if __name__ == "__main__":
    import json
    print("=== MockVerifier (testing twin) — self-test ===")
    res = _self_test()
    print(json.dumps(res, indent=2))
    assert res.get("all_passed"), "self-test FAILED"
    print("PASS — MockVerifier twins (R-LABELS: SYNTHETIC-DEMO)")
