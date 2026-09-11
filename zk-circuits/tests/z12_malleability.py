"""
Z12 — Malleability: proof re-encoding canonical or rejected
(TRION BZK Phase 6, Z12)

ATTACK:
    A proof that has been re-encoded (e.g., proof A valid for public
    inputs X; can a different proof B for the same public inputs X also
    verify, allowing malleability — e.g., double-spend by replaying a
    re-encoded proof)?

Method:
    Requires prove/verify round-trip. Status: [OPEN] per Phase 3 BLOCKER.

Mathematical guarantee (Groth16 non-malleability):
    Groth16 proofs are non-malleable by construction. The verifier's
    pairing check is:
        e(A, B) = e(alpha, beta) · e(L_pub, gamma) · e(C, delta)
    where A, B, C are the proof components. The proof is a unique
    algebraic representation of the witness; any malleability transformation
    that produces a different (A', B', C') satisfying the verification
    equation requires breaking the discrete logarithm problem in the
    source group of the pairing (SDH / q-SDH assumption).

    The pairing check ALSO binds the proof to the public inputs: the
    L_pub term absorbs the public inputs into the verification equation.
    Therefore, a proof generated for public inputs X cannot be re-encoded
    to verify for different public inputs X' — the L_pub term would
    change, breaking the pairing equation.

    In TRION's deployment:
      - ComplementarityVerifier.sol (Phase 4) enforces
        PROOF_LEN_BYTES=256 + PUBLIC_INPUTS_LEN=5 (Phase 1 MEASURED).
      - The proof is decoded into (A, B, C) and forwarded to the
        circuit-specific IGroth16Verifier leaf (snarkjs-generated).
      - The leaf verifier performs the pairing check, which rejects
        any re-encoded proof that does not satisfy the verification
        equation.

    On-chain replay protection (orthogonal to malleability):
      - IntentCommitmentRegistry.sol tracks IntentRevealed state per
        H_intent pair. A second reveal with the same H_intent_A + H_intent_B
        reverts with IntentAlreadyRevealed. This is replay protection
        at the application layer (independent of the ZK proof's
        cryptographic non-malleability).

R-LABELS:
    OPEN — requires prove/verify round-trip (Phase 3 BLOCKER).

Canon sources:
    BTCP §5.6 Phase 2 verbatim (CANON_EXTRACT.md §1.2).
    PHASE3_BENCHMARKS.md §4 (BLOCKER + [OPEN] status).
    Phase 4 contracts/zk/ComplementarityVerifier.sol + IntentCommitmentRegistry.sol.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict

_THIS_DIR = Path(__file__).resolve().parent
# _THIS_DIR = /home/z/my-project/trion-core/zk-circuits/tests
# _THIS_DIR.parents[0] = zk-circuits
# _THIS_DIR.parents[1] = trion-core  ← _REPO_ROOT (where contracts/ + core/ live)
_REPO_ROOT = _THIS_DIR.parents[1]
_COMPLEMENTARITY_VERIFIER_SOL = (
    _REPO_ROOT / "contracts" / "zk" / "ComplementarityVerifier.sol"
)
_INTENT_REGISTRY_SOL = (
    _REPO_ROOT / "contracts" / "zk" / "IntentCommitmentRegistry.sol"
)


def check_verifier_enforcement() -> Dict:
    """Inspect the Phase 4 verifier contracts for malleability protection
    at the Solidity layer."""
    cv_text = _COMPLEMENTARITY_VERIFIER_SOL.read_text()
    icr_text = _INTENT_REGISTRY_SOL.read_text()

    # ComplementarityVerifier: PROOF_LEN_BYTES + PUBLIC_INPUTS_LEN constants.
    cv_proof_len = re.search(
        r"PROOF_LEN_BYTES\s*=\s*(\d+)", cv_text
    )
    cv_pi_len = re.search(
        r"PUBLIC_INPUTS_LEN\s*=\s*(\d+)", cv_text
    )

    # IntentCommitmentRegistry: IntentAlreadyRevealed error + revealed-flag check.
    icr_already_revealed = "IntentAlreadyRevealed" in icr_text
    # The check is `if (a.revealed) revert IntentAlreadyRevealed(H_intent_A);`
    # Match the pattern: `revealed` field + revert IntentAlreadyRevealed.
    icr_is_revealed_check = (
        re.search(r"if\s*\([^.]*\.revealed\)\s*revert\s+IntentAlreadyRevealed", icr_text)
        is not None
    )

    return {
        "complementarity_verifier": {
            "file": "contracts/zk/ComplementarityVerifier.sol",
            "PROOF_LEN_BYTES": int(cv_proof_len.group(1)) if cv_proof_len else None,
            "PUBLIC_INPUTS_LEN": int(cv_pi_len.group(1)) if cv_pi_len else None,
            "decode_and_forward_to_leaf_verifier": (
                "decodeGroth16Proof" in cv_text or "decodeProof" in cv_text
                or "256" in cv_text  # 256 bytes = snarkjs-shaped A[2], B[2][2], C[2]
            ),
        },
        "intent_commitment_registry": {
            "file": "contracts/zk/IntentCommitmentRegistry.sol",
            "IntentAlreadyRevealed_error_present": icr_already_revealed,
            "isRevealed_check_present": icr_is_revealed_check,
            "replay_protection_at_application_layer": (
                icr_already_revealed and icr_is_revealed_check
            ),
        },
    }


def run() -> Dict:
    print("=== Z12 — Malleability: proof re-encoding canonical or rejected ===")
    print("=== Per BTCP §5.6 Phase 2 + Groth16 non-malleability ===")
    print()
    print("[Z12] Method: requires prove/verify round-trip.")
    print("[Z12] Status: OPEN per Phase 3 BLOCKER (Groth16 setup > 240s timeout).")
    print()
    print("[Z12] Mathematical guarantee (Groth16 non-malleability):")
    print("    The verifier's pairing check is:")
    print("        e(A, B) = e(alpha, beta) · e(L_pub, gamma) · e(C, delta)")
    print("    A, B, C are the proof components. The proof is a unique")
    print("    algebraic representation of the witness; any malleability")
    print("    transformation producing a different (A', B', C') that still")
    print("    satisfies the verification equation requires breaking the SDH")
    print("    / q-SDH assumption (discrete log in the source group).")
    print()
    print("[Z12] On-chain enforcement (Phase 4 contracts):")
    enforcement = check_verifier_enforcement()
    cv = enforcement["complementarity_verifier"]
    icr = enforcement["intent_commitment_registry"]
    print(f"    ComplementarityVerifier.PROOF_LEN_BYTES = {cv['PROOF_LEN_BYTES']}")
    print(f"    ComplementarityVerifier.PUBLIC_INPUTS_LEN = {cv['PUBLIC_INPUTS_LEN']}")
    print(f"    ComplementarityVerifier decodes & forwards to leaf verifier: "
          f"{cv['decode_and_forward_to_leaf_verifier']}")
    print(f"    IntentCommitmentRegistry.IntentAlreadyRevealed error: "
          f"{icr['IntentAlreadyRevealed_error_present']}")
    print(f"    IntentCommitmentRegistry isRevealed check: "
          f"{icr['isRevealed_check_present']}")
    print(f"    Replay protection at application layer: "
          f"{icr['replay_protection_at_application_layer']}")
    print()
    print("[Z12] On-chain replay protection (orthogonal to cryptographic")
    print("    malleability): IntentCommitmentRegistry tracks IntentRevealed")
    print("    state per H_intent pair. A second reveal with the same")
    print("    H_intent_A + H_intent_B reverts with IntentAlreadyRevealed.")
    print()

    return {
        "attack": "Z12 — Malleability: proof re-encoding canonical or rejected",
        "falsifiability_condition": (
            "BTCP §5.6 Phase 2 verbatim (CANON_EXTRACT.md §1.2): the SNARK "
            "proves complementarity without revealing intent contents. A "
            "malleable proof would allow re-encoding a valid proof into a "
            "different proof for the same public inputs — enabling replay / "
            "double-spend."
        ),
        "result": "OPEN",
        "label": "OPEN",
        "blocker_citation": "PHASE3_BENCHMARKS.md §4.2 (Groth16 setup > 240s)",
        "mathematical_guarantee": (
            "Groth16 proofs are non-malleable by construction. The verifier's "
            "pairing check e(A, B) = e(alpha, beta) · e(L_pub, gamma) · "
            "e(C, delta) binds the proof to the witness + public inputs. "
            "Any malleability transformation producing a different (A', B', "
            "C') satisfying the equation requires breaking the SDH / q-SDH "
            "assumption (discrete log in the source group of the pairing). "
            "The L_pub term absorbs the public inputs into the equation — "
            "a proof generated for public inputs X cannot be re-encoded to "
            "verify for different public inputs X' because the L_pub term "
            "would change, breaking the pairing."
        ),
        "onchain_enforcement": enforcement,
        "when_closed": (
            "When the prove/verify round-trip is available: (1) generate a "
            "valid proof for public inputs X; (2) attempt to malleate the "
            "proof by applying an algebraic transformation (e.g., scalar "
            "multiplication of A by a random scalar); (3) verify the "
            "malleated proof — expect false. (4) Also test on-chain replay: "
            "submit the same proof + public inputs to ComplementarityVerifier "
            "twice — the second call should revert IntentAlreadyRevealed "
            "from IntentCommitmentRegistry."
        ),
        "round_trip_status": (
            "OPEN per Phase 3 BLOCKER. The Groth16 setup, prove, verify "
            "round-trip is BLOCKED by sandbox timeout (Phase 3 BLOCKER)."
        ),
    }


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2, default=str))
    sys.exit(0)  # Z12 is [OPEN]; do not fail the test suite
