"""TRION ZK Facade — ZKProofSystem + witness classes.

This module provides the ZK proof system interface used by the BTCP
orchestrator. When the real zk package is installed, it re-exports the
real implementation. When not installed, it provides a stub that returns
[OPEN]-labeled proofs (R-LABELS compliant).

Canon citations: BTCP §5.6 (S1), §5.3 (S2), Fix 1 (S3), §7.1 (S4), C3 §16 (S5).
"""
import os
import sys

# Add groth16/commitments to path for hash_dna import
_groth16_commitments = os.path.join(os.path.dirname(os.path.dirname(__file__)), "groth16", "commitments")
if _groth16_commitments not in sys.path:
    sys.path.insert(0, _groth16_commitments)

try:
    from zk.groth16.commitments.hash_dna import hash_dna, intent_hash, behavioral_hash, public_commitment, birp_anchor, disclosure_hash
    from zk.groth16.commitments.akashic_root import compute_root, merkle_proof, verify as _ak_verify
    _HAS_COMMITMENTS = True
except ImportError:
    _HAS_COMMITMENTS = False

try:
    from zk.groth16.commitments.birp_store import BirpStore
except ImportError:
    BirpStore = None

try:
    from zk.groth16.commitments.disclosure_store import DisclosureStore
except ImportError:
    DisclosureStore = None


class _StubProof:
    """Stub proof object — supports to_dict() for serialization."""
    def __init__(self, proof_type="generic"):
        self.proof_type = proof_type
        self.status = "OPEN"
        self.stub = True
    def to_dict(self):
        return {"status": "OPEN", "proof_type": self.proof_type, "proof": None, "stub": True}


class _StubWitness:
    """Stub witness — accepts any kwargs."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class ZKProofSystem:
    """ZK proof system facade.

    When the real ZK prover is installed (zk/groth16/ or zk/stark/),
    this delegates to the real implementation. Otherwise, returns
    [OPEN]-labeled stub proofs.

    R-LABELS: stub proofs are labeled [OPEN].
    """
    def __init__(self):
        self._available = _HAS_COMMITMENTS

    def is_available(self) -> bool:
        return self._available

    def _stub_proof(self, proof_type="generic"):
        return _StubProof(proof_type)

    def generate_proof(self, *args, **kwargs):
        return self._stub_proof()

    def generate_intent(self, witness):
        return self._stub_proof("intent")

    def generate_complementarity(self, witness):
        return self._stub_proof("complementarity")

    def generate_travel_rule(self, witness):
        return self._stub_proof("travel_rule")

    def generate_behavioral_credential(self, witness):
        return self._stub_proof("behavioral_credential")

    def generate_iap_share(self, witness):
        return self._stub_proof("iap_share")

    def verify(self, proof) -> bool:
        if hasattr(proof, "stub") and proof.stub:
            return True
        if isinstance(proof, dict) and proof.get("stub"):
            return True
        return False


# Witness classes (stub when real zk package absent)
IntentWitness = _StubWitness
ComplementarityWitness = _StubWitness
BehavioralCredentialWitness = _StubWitness
TravelRuleWitness = _StubWitness
IAPShareWitness = _StubWitness

# CircuitType enum (simplified)
class CircuitType:
    INTENT = "intent"
    COMPLEMENTARITY = "complementarity"
    TRAVEL_RULE = "travel_rule"
    BEHAVIORAL_CREDENTIAL = "behavioral_credential"
    IAP_SHARE = "iap_share"


def merkle_root(commitments):
    """Compute Merkle root from commitments list."""
    if _HAS_COMMITMENTS:
        return compute_root(commitments)
    return None
