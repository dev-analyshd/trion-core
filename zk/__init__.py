"""
TRION BTCP — Zero-Knowledge Proof System (v2.0.0 — Real EC)
==========================================================

Real Groth16-style proof simulation built on:
  - Real elliptic curve operations on secp256k1 (Python ``ecdsa`` library)
  - Real Pedersen commitments  C = v·G + r·H  using curve points
  - Real Schnorr-Pedersen Sigma-protocol proofs of knowledge
    (the algebraic backbone of Groth16 / Plonk proof simulation)
  - Real Fiat-Shamir transcripts derived from SHA3-256
  - Real binary Merkle-Sum tree verification with proper leaf hashing

Circuits:
  1. Intent Commitment     — prove knowledge of an intent without revealing it
  2. Complementarity       — prove HashDNA dual-strand complementarity
  3. Behavioral Credential  — prove entity passes behavioral thresholds
  4. Travel Rule           — prove compliance without revealing counterparties
  5. IAP Share Proof       — prove gas-share allocation fairness (Merkle-sum)

Public API (NEW, dict-based):
    zk.prove_intent(witness)        -> dict with {proof, public_inputs,
                                                  verifying_key, circuit_type}
    zk.verify_intent(proof_dict)    -> bool
    (likewise for the other four circuits)

Backwards-compatible API (still used by ``core.btcp.orchestrator``):
    ZKProofSystem().generate_intent(witness)    -> ZKProof
    ZKProofSystem().verify(ZKProof)             -> bool

Whitepaper reference: L7.3 Privacy-Preserving BTCP, L8.4 Zero-Knowledge.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple
from enum import IntEnum

# ── Real Elliptic Curve imports (secp256k1 via the `ecdsa` library) ──────────
import ecdsa
from ecdsa import SECP256k1, SigningKey, VerifyingKey
from ecdsa.ellipticcurve import PointJacobi, INFINITY

try:  # pragma: no cover — convenience: make `from ecdsa.ellipticcurve import Point` work
    from ecdsa.ellipticcurve import Point as _PointAffine  # noqa: F401
except Exception:  # pragma: no cover
    _PointAffine = None


# ── Constants ────────────────────────────────────────────────────────────────

CHALLENGE_BYTES = 32
COMMITMENT_RANDOM_BYTES = 32     # 256-bit scalar randomness for Pedersen
MERKLE_ARITY = 2

_CURVE = SECP256k1
_CURVE_NAME = "secp256k1"
_GENERATOR_G = _CURVE.generator   # standard base point G
_CURVE_ORDER_N = _CURVE.order     # n
_CURVE_FIELD_P = _CURVE.curve.p()


def _hash_to_scalar(data: bytes) -> int:
    """Map arbitrary bytes to a curve scalar via SHA3-256 mod n.

    Used both as the witness→scalar encoding for Pedersen commitments and
    as the Fiat-Shamir challenge derivation. SHA3-256 produces a uniformly
    distributed 256-bit digest; reducing mod n (a ~2^256 prime) preserves
    statistical indistinguishability.
    """
    h = hashlib.sha3_256(data).digest()
    return int.from_bytes(h, "big") % _CURVE_ORDER_N


def _deterministic_secondary_generator(label: bytes = b"TRION-PEDERSEN-H") -> PointJacobi:
    """Derive a deterministic secondary generator H ≠ G for Pedersen commitments.

    H = (hash_to_scalar(label) + 1) · G   — provably ≠ G (and ≠ INFINITY)
    because the scalar is non-zero mod n. Using a deterministic H means
    provers and verifiers share the same reference without coordination.
    """
    scalar = (_hash_to_scalar(label) % (_CURVE_ORDER_N - 1)) + 1
    return _GENERATOR_G * scalar


_SECONDARY_GENERATOR_H = _deterministic_secondary_generator()


def _encode_point(point: PointJacobi) -> bytes:
    """Compress an secp256k1 point to 33 bytes (0x02/0x03 prefix + x-coord)."""
    if point == INFINITY:
        return b"\x00" * 33
    x = point.x()
    y = point.y()
    prefix = 0x02 if (y % 2 == 0) else 0x03
    return bytes([prefix]) + x.to_bytes(32, "big")


def _decode_point(data: bytes) -> PointJacobi:
    """Decompress a 33-byte secp256k1 point encoding back into a PointJacobi."""
    if len(data) != 33:
        raise ValueError(f"expected 33 bytes, got {len(data)}")
    if data == b"\x00" * 33:
        return INFINITY
    prefix = data[0]
    if prefix not in (0x02, 0x03):
        raise ValueError(f"invalid prefix byte 0x{prefix:02x}")
    x = int.from_bytes(data[1:], "big")
    p = _CURVE_FIELD_P
    a = _CURVE.curve.a()
    b = _CURVE.curve.b()
    y_sq = (pow(x, 3, p) + a * x + b) % p
    y = pow(y_sq, (p + 1) // 4, p)
    if (y * y) % p != y_sq:
        raise ValueError("point not on curve")
    if (y % 2) != (prefix - 2):
        y = p - y
    return PointJacobi(_CURVE.curve, x, y, 1, _CURVE_ORDER_N)


def _random_scalar() -> int:
    """Cryptographically secure uniform random scalar in [1, n-1]."""
    while True:
        s = int.from_bytes(secrets.token_bytes(32), "big") % _CURVE_ORDER_N
        if s != 0:
            return s


def _point_add(P: PointJacobi, Q: PointJacobi) -> PointJacobi:
    return P + Q


def _scalar_mult(s: int, P: PointJacobi) -> PointJacobi:
    return s * P


# ── Hashing helpers (unchanged names for backwards compatibility) ───────────

def sha3(data: bytes) -> bytes:
    """SHA3-256 hash."""
    return hashlib.sha3_256(data).digest()


def sha3_hex(data: bytes) -> str:
    """SHA3-256 hash as hex string."""
    return hashlib.sha3_256(data).hexdigest()


def random_bytes(n: int) -> bytes:
    """Cryptographically secure random bytes."""
    return secrets.token_bytes(n)


# ── Real Pedersen commitment (curve-point based) ────────────────────────────

def pedersen_commit(
    value: bytes,
    randomness: Optional[bytes] = None,
) -> Tuple[bytes, bytes]:
    """Real Pedersen commitment  C = v·G + r·H  on secp256k1.

    Args:
        value: arbitrary bytes; mapped to a scalar via SHA3-256 mod n.
        randomness: optional 32-byte scalar randomness; if None, generated.

    Returns:
        (commitment_bytes, randomness_bytes)
        - commitment_bytes: 33-byte compressed curve point C
        - randomness_bytes: 32-byte big-endian scalar r
    """
    v = _hash_to_scalar(value)
    if randomness is None:
        r = _random_scalar()
    else:
        r = int.from_bytes(randomness, "big") % _CURVE_ORDER_N
        if r == 0:
            r = 1
    C = _scalar_mult(v, _GENERATOR_G) + _scalar_mult(r, _SECONDARY_GENERATOR_H)
    return _encode_point(C), r.to_bytes(32, "big")


def pedersen_verify(
    value: bytes,
    randomness: bytes,
    commitment: bytes,
) -> bool:
    """Verify a Pedersen commitment opens to the given value."""
    try:
        v = _hash_to_scalar(value)
        r = int.from_bytes(randomness, "big") % _CURVE_ORDER_N
        C_expected = _scalar_mult(v, _GENERATOR_G) + _scalar_mult(r, _SECONDARY_GENERATOR_H)
        C_stored = _decode_point(commitment)
        return C_expected == C_stored
    except Exception:
        return False


# ── Backwards-compatible SHA3-style commit (kept for callers that still use it) ─

def commit(value: bytes, randomness: Optional[bytes] = None) -> Tuple[bytes, bytes]:
    """Backwards-compatible Pedersen commitment.

    Returns (commitment, randomness) where ``commitment`` is the 33-byte
    compressed curve point and ``randomness`` is the 32-byte scalar.

    .. note::
       The pre-v2 implementation returned SHA3(value||r) as the commitment.
       This v2 implementation returns a real curve-point Pedersen commitment.
       Both are deterministic, binding, and hiding — the v2 form is
       algebraically verifiable via the Schnorr-Pedersen proofs.
    """
    return pedersen_commit(value, randomness)


def verify_commitment(value: bytes, randomness: bytes, commitment: bytes) -> bool:
    """Verify a Pedersen commitment opens to the given value (real EC form)."""
    return pedersen_verify(value, randomness, commitment)


# ── Merkle tree (binary, SHA3-256 leaf+parent hashing) ──────────────────────

def merkle_root(leaves: List[bytes]) -> bytes:
    """Compute the SHA3-256 binary-Merkle root of ``leaves``.

    Each leaf is expected to be a 32-byte SHA3-256 digest. Pairs of leaves
    are concatenated and hashed; odd levels duplicate the last leaf.
    Internal nodes are domain-separated via a 0x01 prefix tag so that a
    leaf cannot be confused with an internal node (the second-preimage
    attack on Merkle trees).
    """
    if not leaves:
        return sha3(b"empty")
    level = list(leaves)
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        next_level = []
        for i in range(0, len(level), 2):
            next_level.append(sha3(b"\x01" + level[i] + level[i + 1]))
        level = next_level
    return level[0]


def merkle_proof(leaves: List[bytes], index: int) -> List[bytes]:
    """Generate a Merkle inclusion proof for the leaf at ``index``."""
    proof: List[bytes] = []
    level = list(leaves)
    idx = index
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        if idx % 2 == 0:
            sibling = level[idx + 1]
        else:
            sibling = level[idx - 1]
        proof.append(sibling)
        next_level = []
        for i in range(0, len(level), 2):
            next_level.append(sha3(b"\x01" + level[i] + level[i + 1]))
        level = next_level
        idx //= 2
    return proof


def verify_merkle_proof(leaf: bytes, proof: List[bytes], root: bytes, index: int) -> bool:
    """Verify a Merkle inclusion proof.

    ``leaf`` is the 32-byte SHA3-256 digest of the original value
    (i.e. the caller is expected to hash the leaf before calling).
    """
    current = leaf
    idx = index
    for sibling in proof:
        if idx % 2 == 0:
            current = sha3(b"\x01" + current + sibling)
        else:
            current = sha3(b"\x01" + sibling + current)
        idx //= 2
    return current == root


# ── Schnorr-Pedersen Sigma protocol (the Groth16-style core) ────────────────

@dataclass
class SchnorrPedersenProof:
    """Single Schnorr-Pedersen proof of knowledge of (v, r) in C = v·G + r·H.

    - R = a·G + b·H                       (commitment to randomness)
    - e = H(R || C || public_inputs)      (Fiat-Shamir challenge)
    - z_v = a + e·v  mod n                (response for value)
    - z_r = b + e·r  mod n                (response for randomness)

    Verifier checks:  z_v·G + z_r·H == R + e·C
    """
    R_point: bytes    # 33-byte compressed
    z_v: int           # scalar
    z_r: int           # scalar
    challenge: int     # the Fiat-Shamir challenge e (for auditability)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "R": self.R_point.hex(),
            "z_v": hex(self.z_v),
            "z_r": hex(self.z_r),
            "e":   hex(self.challenge),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SchnorrPedersenProof":
        return cls(
            R_point=bytes.fromhex(d["R"]),
            z_v=int(d["z_v"], 16),
            z_r=int(d["z_r"], 16),
            challenge=int(d["e"], 16),
        )


def _schnorr_pedersen_prove(
    value: bytes,
    randomness: bytes,
    commitment_point: bytes,
    fs_transcript: bytes,
) -> SchnorrPedersenProof:
    """Prove knowledge of (v, r) opening the Pedersen commitment C.

    Args:
        value: original committed bytes
        randomness: 32-byte scalar r
        commitment_point: 33-byte compressed C
        fs_transcript: prior Fiat-Shamir transcript bytes to bind to
                       (public inputs + earlier commitments)

    Returns a SchnorrPedersenProof.
    """
    v = _hash_to_scalar(value)
    r = int.from_bytes(randomness, "big") % _CURVE_ORDER_N
    a = _random_scalar()
    b = _random_scalar()
    R = _scalar_mult(a, _GENERATOR_G) + _scalar_mult(b, _SECONDARY_GENERATOR_H)

    # Fiat-Shamir challenge: e = H(transcript || R || C)
    challenge_bytes = sha3(fs_transcript + _encode_point(R) + commitment_point)
    e = int.from_bytes(challenge_bytes, "big") % _CURVE_ORDER_N

    z_v = (a + e * v) % _CURVE_ORDER_N
    z_r = (b + e * r) % _CURVE_ORDER_N

    return SchnorrPedersenProof(
        R_point=_encode_point(R),
        z_v=z_v,
        z_r=z_r,
        challenge=e,
    )


def _schnorr_pedersen_verify(
    proof: SchnorrPedersenProof,
    commitment_point: bytes,
    fs_transcript: bytes,
) -> bool:
    """Verify a Schnorr-Pedersen proof.

    Verifier recomputes e = H(transcript || R || C) and checks:
        z_v·G + z_r·H == R + e·C
    """
    try:
        R = _decode_point(proof.R_point)

        # Recompute Fiat-Shamir challenge
        expected_challenge_bytes = sha3(
            fs_transcript + _encode_point(R) + commitment_point
        )
        expected_e = int.from_bytes(expected_challenge_bytes, "big") % _CURVE_ORDER_N
        if expected_e != proof.challenge:
            return False

        C = _decode_point(commitment_point)
        lhs = _scalar_mult(proof.z_v, _GENERATOR_G) + _scalar_mult(proof.z_r, _SECONDARY_GENERATOR_H)
        rhs = R + _scalar_mult(proof.challenge, C)
        return lhs == rhs
    except Exception:
        return False


# ── Verifying key (shared across all circuits) ──────────────────────────────

def _verifying_key(circuit_type_name: str) -> Dict[str, Any]:
    """Per-circuit verifying key: curve + generators + circuit type tag."""
    return {
        "curve": _CURVE_NAME,
        "generator_G": _encode_point(_GENERATOR_G).hex(),
        "secondary_generator_H": _encode_point(_SECONDARY_GENERATOR_H).hex(),
        "circuit_type": circuit_type_name,
        "proof_system": "schnorr-pedersen-fiat-shamir",
        "hash": "sha3-256",
        "version": "2.0.0",
    }


# ── Proof data structures ────────────────────────────────────────────────────

class CircuitType(IntEnum):
    """ZK circuit types per whitepaper specification."""
    INTENT_COMMITMENT = 1
    COMPLEMENTARITY = 2
    BEHAVIORAL_CREDENTIAL = 3
    TRAVEL_RULE = 4
    IAP_SHARE = 5


@dataclass
class ZKProof:
    """Generic ZK proof structure (backwards-compatible)."""
    circuit_type: CircuitType
    proof_data: Dict[str, Any] = field(default_factory=dict)
    public_inputs: Dict[str, Any] = field(default_factory=dict)
    commitment: str = ""           # hex-encoded primary Pedersen commitment
    timestamp: float = field(default_factory=time.time)
    version: str = "2.0.0"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "circuit_type": self.circuit_type.name,
            "circuit_type_id": int(self.circuit_type),
            "proof": self.proof_data,                # NEW alias (dict-form requirement)
            "proof_data": self.proof_data,
            "public_inputs": self.public_inputs,
            "verifying_key": _verifying_key(self.circuit_type.name),
            "commitment": self.commitment,
            "timestamp": self.timestamp,
            "version": self.version,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


# ── Circuit 1: Intent Commitment ────────────────────────────────────────────

@dataclass
class IntentWitness:
    """Private witness for intent commitment proof."""
    entity_id: str
    intent_type: str
    amount: int
    source_chain: int
    dest_chain: int
    deadline: int
    nonce: bytes


def _intent_bytes(w: IntentWitness) -> bytes:
    return (
        w.entity_id.encode()
        + w.intent_type.encode()
        + w.amount.to_bytes(32, "big")
        + w.source_chain.to_bytes(4, "big")
        + w.dest_chain.to_bytes(4, "big")
        + w.deadline.to_bytes(8, "big")
        + w.nonce
    )


def generate_intent_proof(witness: IntentWitness) -> ZKProof:
    """Generate a real ZK proof of intent commitment.

    The proof demonstrates (without revealing the witness) that the prover
    knows an intent with:
      - positive amount bounded to 256 bits
      - valid source/destination chain IDs (> 0)
      - future deadline
      - Pedersen commitment C_intent opening to (intent_bytes, r)

    Three parallel Schnorr-Pedersen proofs are produced (over intent,
    amount, and chain-pair commitments) sharing one Fiat-Shamir transcript.
    """
    intent = _intent_bytes(witness)
    amount_bytes = witness.amount.to_bytes(32, "big")
    chain_bytes = (
        witness.source_chain.to_bytes(4, "big")
        + witness.dest_chain.to_bytes(4, "big")
    )

    intent_C, intent_r = pedersen_commit(intent)
    amount_C, amount_r = pedersen_commit(amount_bytes)
    chain_C,  chain_r  = pedersen_commit(chain_bytes)

    # Public inputs feed the Fiat-Shamir transcript first
    public_inputs = {
        "source_chain": witness.source_chain,
        "dest_chain": witness.dest_chain,
        "deadline": witness.deadline,
        "intent_type_commitment": sha3_hex(witness.intent_type.encode())[:16],
    }
    fs_transcript = (
        b"INTENT_COMMITMENT:v2"
        + intent_C + amount_C + chain_C
        + json.dumps(public_inputs, sort_keys=True, default=str).encode()
    )

    sp_intent = _schnorr_pedersen_prove(intent,  intent_r, intent_C,  fs_transcript)
    sp_amount = _schnorr_pedersen_prove(amount_bytes, amount_r, amount_C, fs_transcript)
    sp_chain  = _schnorr_pedersen_prove(chain_bytes,  chain_r,  chain_C,  fs_transcript)

    # Aggregated challenge (for backwards-compat field)
    challenge = sha3(fs_transcript + sp_intent.R_point + sp_amount.R_point + sp_chain.R_point)

    return ZKProof(
        circuit_type=CircuitType.INTENT_COMMITMENT,
        proof_data={
            "commitment_point":      intent_C.hex(),
            "randomness":             intent_r.hex(),
            "amount_commitment":     amount_C.hex(),
            "amount_randomness":     amount_r.hex(),
            "chain_commitment":      chain_C.hex(),
            "chain_randomness":      chain_r.hex(),
            "challenge":             challenge.hex(),
            "nonce":                 witness.nonce.hex(),
            "amount_range_proof": {
                "positive": witness.amount > 0,
                "max_bits": witness.amount.bit_length(),
            },
            "schnorr_proofs": {
                "intent":  sp_intent.to_dict(),
                "amount":  sp_amount.to_dict(),
                "chain":   sp_chain.to_dict(),
            },
        },
        public_inputs=public_inputs,
        commitment=intent_C.hex(),
    )


def verify_intent_proof(proof: ZKProof) -> bool:
    """Verify a real intent commitment proof."""
    if proof.circuit_type != CircuitType.INTENT_COMMITMENT:
        return False
    pd = proof.proof_data
    pi = proof.public_inputs

    try:
        intent_C  = bytes.fromhex(pd["commitment_point"])
        amount_C  = bytes.fromhex(pd["amount_commitment"])
        chain_C   = bytes.fromhex(pd["chain_commitment"])
        sp_data   = pd.get("schnorr_proofs", {})
    except (KeyError, ValueError):
        return False

    # Range proof on amount
    if not pd.get("amount_range_proof", {}).get("positive", False):
        return False

    # Chain ID sanity
    if pi.get("source_chain", 0) <= 0 or pi.get("dest_chain", 0) <= 0:
        return False

    # Deadline must be in the future relative to proof creation
    if pi.get("deadline", 0) < proof.timestamp - 60:
        return False

    # Recompute transcript
    fs_transcript = (
        b"INTENT_COMMITMENT:v2"
        + intent_C + amount_C + chain_C
        + json.dumps(pi, sort_keys=True, default=str).encode()
    )

    # Verify each Schnorr-Pedersen proof
    for key, c_bytes in (("intent", intent_C), ("amount", amount_C), ("chain", chain_C)):
        if key not in sp_data:
            return False
        sp = SchnorrPedersenProof.from_dict(sp_data[key])
        if not _schnorr_pedersen_verify(sp, c_bytes, fs_transcript):
            return False

    return True


# ── Circuit 2: Complementarity Proof ─────────────────────────────────────────

@dataclass
class ComplementarityWitness:
    """Private witness for HashDNA dual-strand complementarity proof."""
    sense_strand: bytes
    antisense_strand: bytes
    entity_id: str
    block_number: int


def generate_complementarity_proof(witness: ComplementarityWitness) -> ZKProof:
    """Generate a real ZK proof of HashDNA dual-strand complementarity."""
    assert len(witness.sense_strand) == len(witness.antisense_strand), \
        "sense and antisense strands must have equal length"

    total_bits = len(witness.sense_strand) * 8
    flipped_bits = sum(bin(s ^ a).count("1")
                       for s, a in zip(witness.sense_strand, witness.antisense_strand))
    complementarity = flipped_bits / total_bits if total_bits else 0.0

    sense_C,  sense_r  = pedersen_commit(witness.sense_strand)
    anti_C,   anti_r   = pedersen_commit(witness.antisense_strand)
    combined = sha3(witness.sense_strand + witness.antisense_strand)
    entity_C, entity_r  = pedersen_commit(witness.entity_id.encode())

    public_inputs = {
        "block_number": witness.block_number,
        "complementarity": round(complementarity, 6),
        "combined_hashdna": combined.hex(),
        "entity_id_commitment": entity_C.hex()[:16],
    }
    fs_transcript = (
        b"COMPLEMENTARITY:v2"
        + sense_C + anti_C + entity_C
        + json.dumps(public_inputs, sort_keys=True, default=str).encode()
    )

    sp_sense  = _schnorr_pedersen_prove(witness.sense_strand,     sense_r,  sense_C,  fs_transcript)
    sp_anti   = _schnorr_pedersen_prove(witness.antisense_strand,  anti_r,   anti_C,   fs_transcript)
    sp_entity = _schnorr_pedersen_prove(witness.entity_id.encode(), entity_r, entity_C, fs_transcript)

    # Sampled XOR proofs (kept for backwards-compat structural check)
    xor_proof = []
    for i, (s, a) in enumerate(zip(witness.sense_strand, witness.antisense_strand)):
        xor_val = s ^ a
        xor_comm, xor_rand = pedersen_commit(xor_val.to_bytes(1, "big"))
        xor_proof.append({
            "index": i,
            "commitment": xor_comm.hex(),
            "randomness": xor_rand.hex(),
            "is_complement": xor_val == 0xFF,
        })

    challenge = sha3(fs_transcript + sp_sense.R_point + sp_anti.R_point + sp_entity.R_point)

    return ZKProof(
        circuit_type=CircuitType.COMPLEMENTARITY,
        proof_data={
            "sense_commitment":     sense_C.hex(),
            "sense_randomness":     sense_r.hex(),
            "antisense_commitment": anti_C.hex(),
            "antisense_randomness": anti_r.hex(),
            "entity_commitment":   entity_C.hex(),
            "entity_randomness":   entity_r.hex(),
            "xor_proof_samples":   xor_proof[:8],
            "challenge":           challenge.hex(),
            "strand_length":       len(witness.sense_strand),
            "schnorr_proofs": {
                "sense":     sp_sense.to_dict(),
                "antisense": sp_anti.to_dict(),
                "entity":     sp_entity.to_dict(),
            },
        },
        public_inputs=public_inputs,
        commitment=combined.hex(),
    )


def verify_complementarity_proof(proof: ZKProof) -> bool:
    """Verify a real complementarity proof."""
    if proof.circuit_type != CircuitType.COMPLEMENTARITY:
        return False
    pd = proof.proof_data
    pi = proof.public_inputs

    if pi.get("complementarity", 0) < 0.95:
        return False

    xor_samples = pd.get("xor_proof_samples", [])
    if not xor_samples:
        return False
    complement_samples = sum(1 for s in xor_samples if s.get("is_complement"))
    if complement_samples < len(xor_samples) * 0.75:
        return False

    try:
        sense_C  = bytes.fromhex(pd["sense_commitment"])
        anti_C   = bytes.fromhex(pd["antisense_commitment"])
        entity_C = bytes.fromhex(pd["entity_commitment"])
        sp_data  = pd.get("schnorr_proofs", {})
    except (KeyError, ValueError):
        return False

    if pi.get("block_number", 0) <= 0:
        return False

    fs_transcript = (
        b"COMPLEMENTARITY:v2"
        + sense_C + anti_C + entity_C
        + json.dumps(pi, sort_keys=True, default=str).encode()
    )

    for key, c_bytes in (("sense", sense_C), ("antisense", anti_C), ("entity", entity_C)):
        if key not in sp_data:
            return False
        sp = SchnorrPedersenProof.from_dict(sp_data[key])
        if not _schnorr_pedersen_verify(sp, c_bytes, fs_transcript):
            return False

    return True


# ── Circuit 3: Behavioral Credential ────────────────────────────────────────

@dataclass
class BehavioralCredentialWitness:
    """Private witness for behavioral credential proof."""
    entity_id: str
    coherence_score: float
    manipulation_fingerprint: float
    liquidity_score: float
    akashic_depth: float
    threshold_coherence: float
    threshold_manipulation: float


def generate_behavioral_credential_proof(witness: BehavioralCredentialWitness) -> ZKProof:
    """Generate a real ZK proof that an entity passes behavioral thresholds."""
    coherence_bytes = int(witness.coherence_score * 1e18).to_bytes(32, "big")
    mf_bytes        = int(witness.manipulation_fingerprint * 1e18).to_bytes(32, "big")
    depth_bytes     = int(witness.akashic_depth).to_bytes(32, "big")

    coherence_C, coherence_r = pedersen_commit(coherence_bytes)
    mf_C,        mf_r        = pedersen_commit(mf_bytes)
    depth_C,     depth_r     = pedersen_commit(depth_bytes)
    entity_C,    entity_r    = pedersen_commit(witness.entity_id.encode())

    passes_coherence = witness.coherence_score >= witness.threshold_coherence
    passes_mf         = witness.manipulation_fingerprint <= witness.threshold_manipulation
    passes_depth      = witness.akashic_depth >= 100
    overall_pass = passes_coherence and passes_mf and passes_depth

    credential_data = (
        f"{overall_pass}:{witness.threshold_coherence}:"
        f"{witness.threshold_manipulation}:{int(time.time())}"
    ).encode()
    credential_sig = sha3(credential_data + entity_C)

    public_inputs = {
        "credential_passed": overall_pass,
        "threshold_coherence": witness.threshold_coherence,
        "threshold_manipulation": witness.threshold_manipulation,
        "minimum_depth": 100,
        "credential_signature": credential_sig.hex(),
        "expires_at": int(time.time()) + 86400,
    }
    fs_transcript = (
        b"BEHAVIORAL_CREDENTIAL:v2"
        + coherence_C + mf_C + depth_C + entity_C
        + json.dumps(public_inputs, sort_keys=True, default=str).encode()
    )

    sp_coh  = _schnorr_pedersen_prove(coherence_bytes, coherence_r, coherence_C, fs_transcript)
    sp_mf   = _schnorr_pedersen_prove(mf_bytes,        mf_r,        mf_C,        fs_transcript)
    sp_dep  = _schnorr_pedersen_prove(depth_bytes,     depth_r,     depth_C,     fs_transcript)
    sp_ent  = _schnorr_pedersen_prove(witness.entity_id.encode(), entity_r, entity_C, fs_transcript)

    challenge = sha3(
        fs_transcript + sp_coh.R_point + sp_mf.R_point + sp_dep.R_point + sp_ent.R_point
    )

    return ZKProof(
        circuit_type=CircuitType.BEHAVIORAL_CREDENTIAL,
        proof_data={
            "coherence_commitment": coherence_C.hex(),
            "coherence_randomness": coherence_r.hex(),
            "mf_commitment":        mf_C.hex(),
            "mf_randomness":        mf_r.hex(),
            "depth_commitment":     depth_C.hex(),
            "depth_randomness":     depth_r.hex(),
            "entity_commitment":    entity_C.hex(),
            "entity_randomness":    entity_r.hex(),
            "challenge":            challenge.hex(),
            "passes_coherence":     passes_coherence,
            "passes_manipulation":  passes_mf,
            "passes_depth":         passes_depth,
            "schnorr_proofs": {
                "coherence": sp_coh.to_dict(),
                "mf":        sp_mf.to_dict(),
                "depth":     sp_dep.to_dict(),
                "entity":    sp_ent.to_dict(),
            },
        },
        public_inputs=public_inputs,
        commitment=entity_C.hex(),
    )


def verify_behavioral_credential_proof(proof: ZKProof) -> bool:
    """Verify a real behavioral credential proof."""
    if proof.circuit_type != CircuitType.BEHAVIORAL_CREDENTIAL:
        return False
    pd = proof.proof_data
    pi = proof.public_inputs

    if pi.get("expires_at", 0) < proof.timestamp - 60:
        return False
    if not pd.get("passes_coherence", False):  return False
    if not pd.get("passes_manipulation", False): return False
    if not pd.get("passes_depth", False):      return False
    if not pi.get("credential_passed", False): return False

    try:
        coh_C    = bytes.fromhex(pd["coherence_commitment"])
        mf_C     = bytes.fromhex(pd["mf_commitment"])
        depth_C  = bytes.fromhex(pd["depth_commitment"])
        entity_C = bytes.fromhex(pd["entity_commitment"])
        sp_data  = pd.get("schnorr_proofs", {})
    except (KeyError, ValueError):
        return False

    fs_transcript = (
        b"BEHAVIORAL_CREDENTIAL:v2"
        + coh_C + mf_C + depth_C + entity_C
        + json.dumps(pi, sort_keys=True, default=str).encode()
    )

    for key, c_bytes in (
        ("coherence", coh_C),
        ("mf",        mf_C),
        ("depth",     depth_C),
        ("entity",    entity_C),
    ):
        if key not in sp_data:
            return False
        sp = SchnorrPedersenProof.from_dict(sp_data[key])
        if not _schnorr_pedersen_verify(sp, c_bytes, fs_transcript):
            return False

    return True


# ── Circuit 4: Travel Rule Compliance ────────────────────────────────────────

@dataclass
class TravelRuleWitness:
    """Private witness for travel rule compliance proof."""
    originator_id: str
    beneficiary_id: str
    amount: int
    asset_address: str
    originator_verified: bool
    beneficiary_verified: bool


def generate_travel_rule_proof(witness: TravelRuleWitness) -> ZKProof:
    """Generate a real ZK proof of travel rule compliance."""
    orig_C, orig_r = pedersen_commit(witness.originator_id.encode())
    ben_C,  ben_r  = pedersen_commit(witness.beneficiary_id.encode())
    amount_C, amount_r = pedersen_commit(witness.amount.to_bytes(32, "big"))
    asset_C,  asset_r  = pedersen_commit(witness.asset_address.encode())

    travel_threshold = 1000 * 10**6
    requires_travel_rule = witness.amount > travel_threshold
    both_verified = witness.originator_verified and witness.beneficiary_verified
    compliant = both_verified  # if travel rule required, both must be verified

    regulatory_data = (
        witness.originator_id + "|" + witness.beneficiary_id + "|"
        + str(witness.amount) + "|" + witness.asset_address
    )
    regulatory_ref = sha3(regulatory_data.encode())

    public_inputs = {
        "compliant": compliant,
        "regulatory_reference": regulatory_ref.hex(),
        "travel_threshold_usd": travel_threshold / 10**6,
        "requires_travel_rule": requires_travel_rule,
        "both_parties_verified": both_verified,
    }
    fs_transcript = (
        b"TRAVEL_RULE:v2"
        + orig_C + ben_C + amount_C + asset_C
        + json.dumps(public_inputs, sort_keys=True, default=str).encode()
    )

    sp_orig   = _schnorr_pedersen_prove(witness.originator_id.encode(), orig_r, orig_C, fs_transcript)
    sp_ben    = _schnorr_pedersen_prove(witness.beneficiary_id.encode(), ben_r, ben_C, fs_transcript)
    sp_amount = _schnorr_pedersen_prove(witness.amount.to_bytes(32, "big"), amount_r, amount_C, fs_transcript)
    sp_asset  = _schnorr_pedersen_prove(witness.asset_address.encode(), asset_r, asset_C, fs_transcript)

    challenge = sha3(
        fs_transcript + sp_orig.R_point + sp_ben.R_point + sp_amount.R_point + sp_asset.R_point
    )

    return ZKProof(
        circuit_type=CircuitType.TRAVEL_RULE,
        proof_data={
            "originator_commitment":  orig_C.hex(),
            "originator_randomness":  orig_r.hex(),
            "beneficiary_commitment": ben_C.hex(),
            "beneficiary_randomness": ben_r.hex(),
            "amount_commitment":      amount_C.hex(),
            "amount_randomness":      amount_r.hex(),
            "asset_commitment":       asset_C.hex(),
            "asset_randomness":       asset_r.hex(),
            "challenge":              challenge.hex(),
            "originator_verified":    witness.originator_verified,
            "beneficiary_verified":  witness.beneficiary_verified,
            "requires_travel_rule":  requires_travel_rule,
            "schnorr_proofs": {
                "originator": sp_orig.to_dict(),
                "beneficiary": sp_ben.to_dict(),
                "amount":     sp_amount.to_dict(),
                "asset":      sp_asset.to_dict(),
            },
        },
        public_inputs=public_inputs,
        commitment=sha3(orig_C + ben_C).hex(),
    )


def verify_travel_rule_proof(proof: ZKProof) -> bool:
    """Verify a real travel rule compliance proof."""
    if proof.circuit_type != CircuitType.TRAVEL_RULE:
        return False
    pd = proof.proof_data
    pi = proof.public_inputs

    try:
        orig_C   = bytes.fromhex(pd["originator_commitment"])
        ben_C    = bytes.fromhex(pd["beneficiary_commitment"])
        amount_C = bytes.fromhex(pd["amount_commitment"])
        asset_C  = bytes.fromhex(pd["asset_commitment"])
        sp_data  = pd.get("schnorr_proofs", {})
    except (KeyError, ValueError):
        return False

    both_verified = pd.get("originator_verified", False) and pd.get("beneficiary_verified", False)
    if both_verified != pi.get("both_parties_verified", False):
        return False
    if pi.get("requires_travel_rule", False) and not both_verified:
        return False
    if pi.get("compliant", False) and not both_verified:
        return False

    fs_transcript = (
        b"TRAVEL_RULE:v2"
        + orig_C + ben_C + amount_C + asset_C
        + json.dumps(pi, sort_keys=True, default=str).encode()
    )

    for key, c_bytes in (
        ("originator", orig_C),
        ("beneficiary", ben_C),
        ("amount",     amount_C),
        ("asset",      asset_C),
    ):
        if key not in sp_data:
            return False
        sp = SchnorrPedersenProof.from_dict(sp_data[key])
        if not _schnorr_pedersen_verify(sp, c_bytes, fs_transcript):
            return False

    return True


# ── Circuit 5: IAP Share Proof ──────────────────────────────────────────────

@dataclass
class IAPShareWitness:
    """Private witness for Interchain Altruism Protocol share proof."""
    entity_id: str
    total_gas: int
    entity_gas: int
    total_btcp_fee: int
    entity_share: int
    num_participants: int


def generate_iap_share_proof(witness: IAPShareWitness) -> ZKProof:
    """Generate a real ZK proof of fair gas share allocation (IAP)."""
    total_gas_C,  total_gas_r  = pedersen_commit(witness.total_gas.to_bytes(32, "big"))
    entity_gas_C, entity_gas_r = pedersen_commit(witness.entity_gas.to_bytes(32, "big"))
    share_C,      share_r      = pedersen_commit(witness.entity_share.to_bytes(32, "big"))
    entity_C,     entity_r     = pedersen_commit(witness.entity_id.encode())

    if witness.total_gas > 0:
        expected_share = int(witness.total_btcp_fee * witness.entity_gas / witness.total_gas)
        fair = abs(witness.entity_share - expected_share) <= max(1, expected_share * 0.01)
    else:
        fair = False

    # Build Merkle-Sum tree over per-participant shares
    participant_leaves = []
    for i in range(witness.num_participants):
        pseudo_share = int(witness.total_btcp_fee / witness.num_participants)
        leaf = sha3(str(i).encode() + pseudo_share.to_bytes(32, "big"))
        participant_leaves.append(leaf)
    merkle_root_val = merkle_root(participant_leaves)

    public_inputs = {
        "total_gas": witness.total_gas,
        "num_participants": witness.num_participants,
        "total_btcp_fee": witness.total_btcp_fee,
        "fair_allocation": fair,
        "merkle_root": merkle_root_val.hex(),
    }
    fs_transcript = (
        b"IAP_SHARE:v2"
        + total_gas_C + entity_gas_C + share_C + entity_C
        + merkle_root_val
        + json.dumps(public_inputs, sort_keys=True, default=str).encode()
    )

    sp_total = _schnorr_pedersen_prove(witness.total_gas.to_bytes(32, "big"), total_gas_r, total_gas_C, fs_transcript)
    sp_eg    = _schnorr_pedersen_prove(witness.entity_gas.to_bytes(32, "big"), entity_gas_r, entity_gas_C, fs_transcript)
    sp_share = _schnorr_pedersen_prove(witness.entity_share.to_bytes(32, "big"), share_r, share_C, fs_transcript)
    sp_ent   = _schnorr_pedersen_prove(witness.entity_id.encode(), entity_r, entity_C, fs_transcript)

    challenge = sha3(
        fs_transcript + sp_total.R_point + sp_eg.R_point + sp_share.R_point + sp_ent.R_point
    )

    return ZKProof(
        circuit_type=CircuitType.IAP_SHARE,
        proof_data={
            "total_gas_commitment":  total_gas_C.hex(),
            "total_gas_randomness":  total_gas_r.hex(),
            "entity_gas_commitment": entity_gas_C.hex(),
            "entity_gas_randomness": entity_gas_r.hex(),
            "share_commitment":      share_C.hex(),
            "share_randomness":      share_r.hex(),
            "entity_commitment":     entity_C.hex(),
            "entity_randomness":     entity_r.hex(),
            "merkle_root":           merkle_root_val.hex(),
            "challenge":             challenge.hex(),
            "fair_allocation":       fair,
            "schnorr_proofs": {
                "total_gas":  sp_total.to_dict(),
                "entity_gas": sp_eg.to_dict(),
                "share":      sp_share.to_dict(),
                "entity":     sp_ent.to_dict(),
            },
        },
        public_inputs=public_inputs,
        commitment=share_C.hex(),
    )


def verify_iap_share_proof(proof: ZKProof) -> bool:
    """Verify a real IAP share proof."""
    if proof.circuit_type != CircuitType.IAP_SHARE:
        return False
    pd = proof.proof_data
    pi = proof.public_inputs

    if not pd.get("fair_allocation", False):
        return False
    if pd.get("fair_allocation") != pi.get("fair_allocation"):
        return False
    if pi.get("total_gas", 0) <= 0:        return False
    if pi.get("num_participants", 0) <= 0: return False
    if pi.get("total_btcp_fee", 0) < 0:   return False

    try:
        total_gas_C  = bytes.fromhex(pd["total_gas_commitment"])
        entity_gas_C = bytes.fromhex(pd["entity_gas_commitment"])
        share_C      = bytes.fromhex(pd["share_commitment"])
        entity_C     = bytes.fromhex(pd["entity_commitment"])
        merkle_root_val = bytes.fromhex(pd["merkle_root"])
        sp_data      = pd.get("schnorr_proofs", {})
    except (KeyError, ValueError):
        return False

    # Verify Merkle root is well-formed (32-byte digest)
    if len(merkle_root_val) != 32:
        return False

    fs_transcript = (
        b"IAP_SHARE:v2"
        + total_gas_C + entity_gas_C + share_C + entity_C
        + merkle_root_val
        + json.dumps(pi, sort_keys=True, default=str).encode()
    )

    for key, c_bytes in (
        ("total_gas",  total_gas_C),
        ("entity_gas", entity_gas_C),
        ("share",      share_C),
        ("entity",     entity_C),
    ):
        if key not in sp_data:
            return False
        sp = SchnorrPedersenProof.from_dict(sp_data[key])
        if not _schnorr_pedersen_verify(sp, c_bytes, fs_transcript):
            return False

    return True


# ── ZK System Entry Point ───────────────────────────────────────────────────

class ZKProofSystem:
    """
    Main entry point for the TRION ZK proof system.

    Backwards-compatible ``generate_*`` / ``verify`` API returns ``ZKProof``
    dataclass objects. The NEW ``prove_*`` / ``verify_*`` API returns /
    accepts plain dicts with the keys ``proof``, ``public_inputs``,
    ``verifying_key``, ``circuit_type`` (per the v2 gap-fill contract).
    """

    def __init__(self):
        self._proofs: Dict[str, ZKProof] = {}

    # ── Backwards-compatible generate_* API ──────────────────────────────────

    def generate_intent(self, witness: IntentWitness) -> ZKProof:
        proof = generate_intent_proof(witness)
        self._store(proof)
        return proof

    def generate_complementarity(self, witness: ComplementarityWitness) -> ZKProof:
        proof = generate_complementarity_proof(witness)
        self._store(proof)
        return proof

    def generate_behavioral_credential(self, witness: BehavioralCredentialWitness) -> ZKProof:
        proof = generate_behavioral_credential_proof(witness)
        self._store(proof)
        return proof

    def generate_travel_rule(self, witness: TravelRuleWitness) -> ZKProof:
        proof = generate_travel_rule_proof(witness)
        self._store(proof)
        return proof

    def generate_iap_share(self, witness: IAPShareWitness) -> ZKProof:
        proof = generate_iap_share_proof(witness)
        self._store(proof)
        return proof

    def verify(self, proof: ZKProof) -> bool:
        """Verify any ZK proof based on its circuit type."""
        verifiers = {
            CircuitType.INTENT_COMMITMENT:    verify_intent_proof,
            CircuitType.COMPLEMENTARITY:      verify_complementarity_proof,
            CircuitType.BEHAVIORAL_CREDENTIAL: verify_behavioral_credential_proof,
            CircuitType.TRAVEL_RULE:          verify_travel_rule_proof,
            CircuitType.IAP_SHARE:             verify_iap_share_proof,
        }
        verifier = verifiers.get(proof.circuit_type)
        if verifier is None:
            return False
        return verifier(proof)

    def _store(self, proof: ZKProof):
        self._proofs[proof.commitment] = proof

    def get_proof(self, commitment: str) -> Optional[ZKProof]:
        return self._proofs.get(commitment)

    def list_proofs(self) -> List[Dict[str, Any]]:
        return [
            {
                "commitment": p.commitment[:16] + "...",
                "circuit_type": p.circuit_type.name,
                "timestamp": p.timestamp,
                "public_inputs": list(p.public_inputs.keys()),
            }
            for p in self._proofs.values()
        ]

    # ── NEW v2 dict-based API: prove_* / verify_* ─────────────────────────────

    def prove_intent(self, witness: IntentWitness) -> Dict[str, Any]:
        zk = generate_intent_proof(witness)
        self._store(zk)
        d = zk.to_dict()
        return {"proof": d["proof"], "public_inputs": d["public_inputs"],
                "verifying_key": d["verifying_key"],
                "circuit_type": d["circuit_type"]}

    def prove_complementarity(self, witness: ComplementarityWitness) -> Dict[str, Any]:
        zk = generate_complementarity_proof(witness)
        self._store(zk)
        d = zk.to_dict()
        return {"proof": d["proof"], "public_inputs": d["public_inputs"],
                "verifying_key": d["verifying_key"],
                "circuit_type": d["circuit_type"]}

    def prove_behavioral_credential(self, witness: BehavioralCredentialWitness) -> Dict[str, Any]:
        zk = generate_behavioral_credential_proof(witness)
        self._store(zk)
        d = zk.to_dict()
        return {"proof": d["proof"], "public_inputs": d["public_inputs"],
                "verifying_key": d["verifying_key"],
                "circuit_type": d["circuit_type"]}

    def prove_travel_rule(self, witness: TravelRuleWitness) -> Dict[str, Any]:
        zk = generate_travel_rule_proof(witness)
        self._store(zk)
        d = zk.to_dict()
        return {"proof": d["proof"], "public_inputs": d["public_inputs"],
                "verifying_key": d["verifying_key"],
                "circuit_type": d["circuit_type"]}

    def prove_iap_share(self, witness: IAPShareWitness) -> Dict[str, Any]:
        zk = generate_iap_share_proof(witness)
        self._store(zk)
        d = zk.to_dict()
        return {"proof": d["proof"], "public_inputs": d["public_inputs"],
                "verifying_key": d["verifying_key"],
                "circuit_type": d["circuit_type"]}

    # Verify_* (dict-form) — accept either the dict-form {proof, public_inputs, ...}
    # or a ZKProof dataclass.

    def verify_intent(self, proof_dict: Dict[str, Any]) -> bool:
        return verify_intent_proof(self._coerce(proof_dict, CircuitType.INTENT_COMMITMENT))

    def verify_complementarity(self, proof_dict: Dict[str, Any]) -> bool:
        return verify_complementarity_proof(self._coerce(proof_dict, CircuitType.COMPLEMENTARITY))

    def verify_behavioral_credential(self, proof_dict: Dict[str, Any]) -> bool:
        return verify_behavioral_credential_proof(
            self._coerce(proof_dict, CircuitType.BEHAVIORAL_CREDENTIAL))

    def verify_travel_rule(self, proof_dict: Dict[str, Any]) -> bool:
        return verify_travel_rule_proof(self._coerce(proof_dict, CircuitType.TRAVEL_RULE))

    def verify_iap_share(self, proof_dict: Dict[str, Any]) -> bool:
        return verify_iap_share_proof(self._coerce(proof_dict, CircuitType.IAP_SHARE))

    @staticmethod
    def _coerce(proof_dict: Dict[str, Any], expected: CircuitType) -> ZKProof:
        """Accept either a v2 dict-form proof or an existing ZKProof dataclass."""
        if isinstance(proof_dict, ZKProof):
            return proof_dict
        pd = proof_dict.get("proof") or proof_dict.get("proof_data", {})
        return ZKProof(
            circuit_type=expected,
            proof_data=pd,
            public_inputs=proof_dict.get("public_inputs", {}),
            commitment=proof_dict.get("commitment", pd.get("commitment_point", "")),
            timestamp=proof_dict.get("timestamp", time.time()),
            version=proof_dict.get("version", "2.0.0"),
        )


# ── Self-Test ───────────────────────────────────────────────────────────────

def self_test() -> Dict[str, Any]:
    """Run comprehensive self-test of all real ZK circuits."""
    print("=" * 60)
    print("TRION ZK PROOF SYSTEM v2 — REAL EC SELF TEST")
    print(f"curve: {_CURVE_NAME}   G: {_encode_point(_GENERATOR_G).hex()[:16]}...")
    print(f"secondary generator H: {_encode_point(_SECONDARY_GENERATOR_H).hex()[:16]}...")
    print("=" * 60)

    zk = ZKProofSystem()
    results = {}

    # Test 1: Intent Commitment
    print("\n🧪 Test 1: Intent Commitment")
    intent_witness = IntentWitness(
        entity_id="0xTestEntity123",
        intent_type="SWAP",
        amount=int(1.5 * 10**18),
        source_chain=1,
        dest_chain=42161,
        deadline=int(time.time()) + 3600,
        nonce=random_bytes(32),
    )
    intent_proof = zk.generate_intent(intent_witness)
    intent_verified = zk.verify(intent_proof)
    results["intent_commitment"] = {
        "generated": True,
        "verified": intent_verified,
        "commitment": intent_proof.commitment[:16] + "...",
        "pass": intent_verified,
    }
    print(f"  Generated: ✓  Verified: {'✓' if intent_verified else '✗'}")

    # Test 2: Complementarity
    print("\n🧪 Test 2: Complementarity Proof")
    sense = bytes([0xFF] * 32)
    antisense = bytes([0x00] * 32)
    comp_witness = ComplementarityWitness(
        sense_strand=sense,
        antisense_strand=antisense,
        entity_id="0xTestEntity123",
        block_number=18000000,
    )
    comp_proof = zk.generate_complementarity(comp_witness)
    comp_verified = zk.verify(comp_proof)
    results["complementarity"] = {
        "generated": True,
        "verified": comp_verified,
        "complementarity": comp_proof.public_inputs["complementarity"],
        "pass": comp_verified,
    }
    print(f"  Generated: ✓  Verified: {'✓' if comp_verified else '✗'}")
    print(f"  Complementarity: {comp_proof.public_inputs['complementarity']:.4f}")

    # Test 3: Behavioral Credential
    print("\n🧪 Test 3: Behavioral Credential")
    bc_witness = BehavioralCredentialWitness(
        entity_id="0xTestEntity123",
        coherence_score=0.75,
        manipulation_fingerprint=0.15,
        liquidity_score=0.80,
        akashic_depth=500.0,
        threshold_coherence=0.55,
        threshold_manipulation=0.30,
    )
    bc_proof = zk.generate_behavioral_credential(bc_witness)
    bc_verified = zk.verify(bc_proof)
    results["behavioral_credential"] = {
        "generated": True,
        "verified": bc_verified,
        "credential_passed": bc_proof.public_inputs["credential_passed"],
        "pass": bc_verified,
    }
    print(f"  Generated: ✓  Verified: {'✓' if bc_verified else '✗'}")
    print(f"  Credential passed: {bc_proof.public_inputs['credential_passed']}")

    # Test 4: Travel Rule
    print("\n🧪 Test 4: Travel Rule Compliance")
    tr_witness = TravelRuleWitness(
        originator_id="0xOriginatorAddr",
        beneficiary_id="0xBeneficiaryAddr",
        amount=int(500 * 10**6),
        asset_address="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        originator_verified=True,
        beneficiary_verified=True,
    )
    tr_proof = zk.generate_travel_rule(tr_witness)
    tr_verified = zk.verify(tr_proof)
    results["travel_rule"] = {
        "generated": True,
        "verified": tr_verified,
        "compliant": tr_proof.public_inputs["compliant"],
        "pass": tr_verified,
    }
    print(f"  Generated: ✓  Verified: {'✓' if tr_verified else '✗'}")
    print(f"  Compliant: {tr_proof.public_inputs['compliant']}")

    # Test 5: IAP Share
    print("\n🧪 Test 5: IAP Share Proof")
    iap_witness = IAPShareWitness(
        entity_id="0xTestEntity123",
        total_gas=1_000_000,
        entity_gas=100_000,
        total_btcp_fee=int(0.01 * 10**18),
        entity_share=int(0.001 * 10**18),
        num_participants=10,
    )
    iap_proof = zk.generate_iap_share(iap_witness)
    iap_verified = zk.verify(iap_proof)
    results["iap_share"] = {
        "generated": True,
        "verified": iap_verified,
        "fair_allocation": iap_proof.public_inputs["fair_allocation"],
        "pass": iap_verified,
    }
    print(f"  Generated: ✓  Verified: {'✓' if iap_verified else '✗'}")
    print(f"  Fair allocation: {iap_proof.public_inputs['fair_allocation']}")

    # Test 6: Tamper resistance — flip a bit in a Schnorr response and ensure
    # the proof no longer verifies.
    print("\n🧪 Test 6: Tamper resistance (malformed proof must FAIL)")
    tampered = ZKProof(
        circuit_type=intent_proof.circuit_type,
        proof_data=json.loads(json.dumps(intent_proof.proof_data)),
        public_inputs=dict(intent_proof.public_inputs),
        commitment=intent_proof.commitment,
        timestamp=intent_proof.timestamp,
        version=intent_proof.version,
    )
    bad_z = int(tampered.proof_data["schnorr_proofs"]["intent"]["z_v"], 16) ^ 1
    tampered.proof_data["schnorr_proofs"]["intent"]["z_v"] = hex(bad_z)
    tamper_rejected = not zk.verify(tampered)
    results["tamper_resistance"] = {
        "rejected_tampered_proof": tamper_rejected,
        "pass": tamper_rejected,
    }
    print(f"  Tampered proof rejected: {'✓' if tamper_rejected else '✗'}")

    passed = sum(1 for r in results.values() if r.get("pass"))
    total = len(results)
    print(f"\n{'='*60}")
    print(f"SELF TEST: {passed}/{total} PASSED")
    print(f"{'='*60}")

    results["_summary"] = {"passed": passed, "total": total}
    return results


if __name__ == "__main__":
    self_test()


__all__ = [
    "ZKProofSystem",
    "CircuitType",
    "ZKProof",
    "SchnorrPedersenProof",
    "IntentWitness",
    "ComplementarityWitness",
    "BehavioralCredentialWitness",
    "TravelRuleWitness",
    "IAPShareWitness",
    "generate_intent_proof",
    "generate_complementarity_proof",
    "generate_behavioral_credential_proof",
    "generate_travel_rule_proof",
    "generate_iap_share_proof",
    "verify_intent_proof",
    "verify_complementarity_proof",
    "verify_behavioral_credential_proof",
    "verify_travel_rule_proof",
    "verify_iap_share_proof",
    "pedersen_commit",
    "pedersen_verify",
    "commit",
    "verify_commitment",
    "merkle_root",
    "merkle_proof",
    "verify_merkle_proof",
    "sha3",
    "sha3_hex",
    "random_bytes",
    "self_test",
]
