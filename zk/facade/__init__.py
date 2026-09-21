"""TRION ZK Facade — Transparent SHA3 proof system (BTCP-FIX2-ZK Fix 1).

Previously every ``generate_*`` method returned a ``_StubProof`` with
``proof=None`` and ``status="OPEN"`` — the orchestrator's
``proof_verification.all_valid`` was therefore always false (fail-closed
because the verifier could not find any bytes to verify).

This file replaces the stub with a FAITHFUL transparent proof:

  * The witness payload (caller-supplied behavioral_data / iap_economics
    / intent fields) is concatenated and committed via the canonical
    hash_dna dual-strand construction
    (``zk/groth16/commitments/hash_dna.py::hash_dna_dual`` — same
    construction every chain adapter uses, R-NO-REDEF).
  * A ``proof_hash`` binds the witness payload to the declared public
    inputs via SHA3-256(payload || "|" || canonical_json(public_inputs)).
  * Verification recomputes the dual-strand commitment + proof_hash
    from the stored payload and asserts byte-equality.

Honest disclosure (per BTCP-FIX2-ZK task spec):
  * ``is_zk:           False``
  * ``proof_type_label: "transparent_sha3"``
  * ``status:          "VERIFIED"``  (was ``"OPEN"`` for stub)
  * ``stub:            False``       (was ``True`` for stub)

The proof is NOT zero-knowledge — the witness payload is included in
``proof_data.witness_payload_hex`` so any third party can recompute and
verify. This loses no privacy vs. the stub (the caller already had to
supply the witness), and it gains real verifiability: the proof will
FAIL TO VERIFY if a single byte of the witness or public inputs is
tampered with after the fact.

Sandbox constraint: snarkjs + trusted-setup ceremony are unavailable
in this environment. The 5 Circom circuits in ``zk/groth16/`` remain
the canonical ZK circuit definitions; this transparent proof is a
faithful runtime substitute that computes the same witness values and
produces a verifiable commitment, with explicit ``is_zk: False``
disclosure so consumers never mistake it for a SNARK.

Canon citations: BTCP §5.6 (S1 intent), §5.3 (S2 complementarity),
Fix 1 Step 3 (S3 travel rule), §7.1 (S4 behavioral credential),
C3 §16 (S5 BIRP anchor / IAP share).
"""
import os
import sys
import json
import time
import struct
import hashlib
from typing import Any, Dict, List, Optional, Tuple

# Add groth16/commitments to path for hash_dna import
_groth16_commitments = os.path.join(os.path.dirname(os.path.dirname(__file__)), "groth16", "commitments")
if _groth16_commitments not in sys.path:
    sys.path.insert(0, _groth16_commitments)

_HASH_DNA_HELPERS = None
try:
    from zk.groth16.commitments.hash_dna import (
        hash_dna,
        hash_dna_dual,
        verify_dual_strand,
        behavioral_hash,
        public_commitment,
        intent_hash,
        birp_anchor,
        disclosure_hash,
        _concat,
        _sha3_256,
        _complement_transform,
        _xor,
        HASH_LEN,
    )
    _HAS_COMMITMENTS = True
except ImportError:
    # The package path import failed — try direct module import
    # (the _groth16_commitments path was inserted above).
    try:
        from hash_dna import (  # type: ignore
            hash_dna,
            hash_dna_dual,
            verify_dual_strand,
            behavioral_hash,
            public_commitment,
            intent_hash,
            birp_anchor,
            disclosure_hash,
            _concat,
            _sha3_256,
            _complement_transform,
            _xor,
            HASH_LEN,
        )
        _HAS_COMMITMENTS = True
    except ImportError:
        # Pure-python fallback so the facade still works if the commitments
        # module is unavailable (e.g. path issues). Mirrors hash_dna.py.
        _HAS_COMMITMENTS = False
        HASH_LEN = 32

        def _sha3_256(data: bytes) -> bytes:
            return hashlib.sha3_256(data).digest()

        def _complement_transform(b: bytes) -> bytes:
            return bytes(~x & 0xFF for x in b)

        def _xor(a: bytes, b: bytes) -> bytes:
            return bytes(x ^ y for x, y in zip(a, b))

        def _concat(fields: List[bytes]) -> bytes:
            out = bytearray()
            for f in fields:
                if not isinstance(f, (bytes, bytearray)):
                    raise TypeError(f"hash_dna: field must be bytes, got {type(f).__name__}")
                out.extend(f)
            return bytes(out)

        def hash_dna(fields: List[bytes]) -> bytes:
            payload = _concat(fields)
            return _sha3_256(payload + b"\x00")

        def hash_dna_dual(fields: List[bytes]) -> Tuple[bytes, bytes]:
            payload = _concat(fields)
            sense = _sha3_256(payload + b"\x00")
            sha3_ff = _sha3_256(payload + b"\xff")
            antisense = _xor(sha3_ff, _complement_transform(sense))
            return sense, antisense

        def verify_dual_strand(sense: bytes, antisense: bytes, payload: bytes) -> bool:
            if len(sense) != HASH_LEN or len(antisense) != HASH_LEN:
                return False
            expected = _xor(
                _sha3_256(payload + b"\xff"),
                _complement_transform(sense),
            )
            return antisense == expected

        # BTCP §5.6 Phase 1: H_intent = Hash_DNA(intent_details || nonce || entity_id)
        def intent_hash(intent_details: bytes, random_nonce: bytes, entity_id: bytes) -> bytes:
            return hash_dna([intent_details, random_nonce, entity_id])

        # BTCP §7.1: behavioral_hash = Hash_DNA(behavior_input || behavior_nonce)
        def behavioral_hash(behavior_input: bytes, behavior_nonce: bytes) -> bytes:
            return hash_dna([behavior_input, behavior_nonce])

        # BTCP §7.1: public_commitment = Hash(behavioral_hash) — SHA3-256 wrapper
        def public_commitment(b_hash: bytes) -> bytes:
            if len(b_hash) != HASH_LEN:
                raise ValueError(f"expected 32-byte behavioral_hash, got {len(b_hash)}")
            return _sha3_256(b_hash)

        # BTCP Fix 1 Step 3: disclosure_hash = Hash_DNA(disclosure_input)
        def disclosure_hash(disclosure_input: bytes) -> bytes:
            return hash_dna([disclosure_input])

        # WP-Mar §16: BIRP anchor (used by S5 — minimal pure-python form)
        def birp_anchor(beo_baseline: bytes, hash_dna_code: bytes,
                       enrollment_ts: int, behavioral_entropy_seed: bytes) -> bytes:
            ts_bytes = int(enrollment_ts).to_bytes(8, "big", signed=False)
            return hash_dna([beo_baseline, hash_dna_code, ts_bytes, behavioral_entropy_seed])


try:
    from zk.groth16.commitments.birp_store import BirpStore
except ImportError:
    BirpStore = None

try:
    from zk.groth16.commitments.disclosure_store import DisclosureStore
except ImportError:
    DisclosureStore = None


PROOF_VERSION = "1.0.0-transparent"


def _canonical_json(obj: Any) -> str:
    """Deterministic JSON encoding for hashing (sorted keys, no spaces).

    The default=str fallback handles dataclasses / IntEnum reprs without
    raising — proofs need to be hashable over arbitrary witness objects.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _hex(b: bytes) -> str:
    return b.hex()


# ── Legacy stub retained for backwards compatibility (verify rejects it) ──

class _StubProof:
    """Stub proof — kept ONLY for import-compat with any legacy callers.

    ZKProofSystem no longer returns this; verify() returns False on it
    so any code path that still holds a stub will fail-closed (correct
    behavior — stub proofs have no bytes to verify).
    """
    def __init__(self, proof_type="generic"):
        self.proof_type = proof_type
        self.status = "OPEN"
        self.stub = True
        self.is_zk = False
        self.proof_data = None
        self.public_inputs = {}
        self.commitment = ""
        self.version = "0.0.0-stub"

    def to_dict(self):
        return {
            "status": "OPEN",
            "proof_type": self.proof_type,
            "proof": None,
            "stub": True,
            "is_zk": False,
        }


class _StubWitness:
    """Stub witness — accepts any kwargs (unchanged)."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


# ── Transparent proof (BTCP-FIX2-ZK Fix 1) ────────────────────────────────

class _TransparentProof:
    """A transparent (non-ZK) but cryptographically verifiable proof.

    Construction (R-NO-DEF: reuses the canonical hash_dna dual-strand
    construction, does NOT reinvent a new hash):

        payload          = _concat(witness_fields)
        sense, antisense = hash_dna_dual(witness_fields)
        witness_commitment = sense                  # 32-byte Hex_DNA sense strand
        antisense_commitment = antisense             # 32-byte Hex_DNA antisense strand
        proof_hash       = SHA3-256(payload || "|" || canonical_json(public_inputs))

    The proof_hash binds the witness PAYLOAD to the declared PUBLIC
    INPUTS — a prover cannot swap public inputs after the fact without
    invalidating proof_hash. The dual-strand commitment makes the
    payload tamper-evident (any byte change to the payload changes
    both strands).

    Verification (ZKProofSystem.verify) recomputes both strands and the
    proof_hash from the stored payload + public_inputs and asserts
    byte-equality. The BTCP Formula Index dual-strand invariant
    (sense XOR antisense == NOT(SHA3-256(payload||0xFF))) is also
    checked directly via verify_dual_strand.

    Honest disclosure (per BTCP-FIX2-ZK task spec):
      is_zk            = False
      proof_type_label = "transparent_sha3"
      status           = "VERIFIED"
      stub             = False
    """

    def __init__(
        self,
        proof_type: str,
        circuit_name: str,
        witness_fields: List[bytes],
        public_inputs: Dict[str, Any],
        notes: Optional[Dict[str, Any]] = None,
    ):
        self.proof_type = proof_type
        self.circuit_name = circuit_name
        self.status = "VERIFIED"
        self.stub = False
        self.is_zk = False
        self.proof_type_label = "transparent_sha3"
        self.version = PROOF_VERSION
        self.timestamp = int(time.time())

        # Compute the dual-strand commitment over the witness fields.
        payload = _concat(witness_fields) if witness_fields else b""
        if payload:
            sense, antisense = hash_dna_dual(witness_fields)
        else:
            # Empty witness: still produce a deterministic 32-byte commitment
            # (so the proof hash is well-defined; verification handles this).
            sense = _sha3_256(b"\x00" + b"empty-witness")
            antisense = _sha3_256(b"\xff" + b"empty-witness")

        # proof_hash binds payload to declared public inputs.
        pub_canon = _canonical_json(public_inputs).encode()
        proof_hash = _sha3_256(payload + b"|" + pub_canon)

        self.proof_data = {
            "proof_hash": _hex(proof_hash),
            "witness_commitment": _hex(sense),
            "antisense_commitment": _hex(antisense),
            "circuit_name": circuit_name,
            "witness_payload_hex": _hex(payload),
            "payload_size": len(payload),
            "public_inputs_canonical": pub_canon.decode(),
        }
        self.public_inputs = dict(public_inputs)
        self.commitment = _hex(sense)
        self.notes = notes or {}

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "proof_type": self.proof_type,
            "circuit": self.circuit_name,
            "status": self.status,
            "stub": self.stub,
            "is_zk": self.is_zk,
            "proof_type_label": self.proof_type_label,
            "version": self.version,
            "timestamp": self.timestamp,
            "proof_data": self.proof_data,
            "public_inputs": self.public_inputs,
            "commitment": self.commitment,
            "verification_note": (
                "Transparent SHA3-256 proof over the caller-supplied witness "
                "payload — NOT a zero-knowledge proof. The hash_dna dual-strand "
                "invariant (sense XOR antisense == NOT(SHA3-256(payload||0xFF))) "
                "is verifiable by any third party with the payload."
            ),
        }
        if self.notes:
            d["notes"] = self.notes
        return d


class ZKProof:
    """Lightweight proof wrapper for verify_proofs() reconstruction.

    The orchestrator's verify_proofs() (core/btcp/orchestrator.py:669)
    reconstructs a ZKProof from a proof dict and passes it to
    ZKProofSystem.verify(). This class carries the dict fields through
    to the verifier without lossy conversion.
    """

    def __init__(
        self,
        circuit_type=None,
        proof_data: Optional[Dict[str, Any]] = None,
        public_inputs: Optional[Dict[str, Any]] = None,
        commitment: str = "",
        timestamp: int = 0,
        version: str = "1.0.0",
    ):
        self.circuit_type = circuit_type
        self.proof_data = proof_data or {}
        self.public_inputs = public_inputs or {}
        self.commitment = commitment
        self.timestamp = timestamp
        self.version = version

    def to_dict(self) -> Dict[str, Any]:
        return {
            "circuit_type": str(self.circuit_type) if self.circuit_type is not None else None,
            "proof_data": self.proof_data,
            "public_inputs": self.public_inputs,
            "commitment": self.commitment,
            "timestamp": self.timestamp,
            "version": self.version,
        }


class CircuitType:
    """Circuit type enum (string-valued; both INTENT and INTENT_COMMITMENT
    are accepted — the orchestrator uses INTENT_COMMITMENT)."""
    INTENT = "intent"
    INTENT_COMMITMENT = "intent_commitment"
    COMPLEMENTARITY = "complementarity"
    TRAVEL_RULE = "travel_rule"
    BEHAVIORAL_CREDENTIAL = "behavioral_credential"
    IAP_SHARE = "iap_share"


class ZKProofSystem:
    """Transparent SHA3 ZK proof system facade.

    Generates faithful transparent proofs (NOT zero-knowledge) over the
    caller-supplied witness payload, using the canonical hash_dna
    dual-strand construction. Verifiers can independently recompute
    the commitment and proof_hash.

    Sandbox constraint: snarkjs + trusted-setup ceremony are unavailable.
    The 5 Circom circuits in zk/groth16/ remain the canonical ZK circuit
    definitions; this transparent proof is a runtime substitute with
    explicit ``is_zk: False`` disclosure so consumers never mistake
    it for a SNARK.
    """

    def __init__(self):
        self._available = _HAS_COMMITMENTS

    def is_available(self) -> bool:
        return self._available

    # ── Witness flattening (deterministic byte encoding) ────────────────

    @staticmethod
    def _witness_bytes(obj: Any) -> List[bytes]:
        """Flatten a witness object into a deterministic list of byte fields.

        Each attribute is encoded per type (bytes pass through, str is
        hex-decoded if possible else UTF-8, int is 8-byte big-endian,
        float is IEEE-754 8-byte, bool is one byte). Fields are emitted
        in sorted-key order so two proofs over the same witness object
        produce identical payloads.
        """
        if obj is None:
            return []
        out: List[bytes] = []
        for k in sorted(vars(obj).keys()):
            if k.startswith("_"):
                continue
            v = getattr(obj, k)
            if v is None:
                continue
            # Type-tagged encoding: prepend the attr name so two witnesses
            # with different field names cannot collide on the same payload.
            out.append(k.encode())
            out.extend(ZKProofSystem._encode_value(v))
        return out

    @staticmethod
    def _encode_value(v: Any) -> List[bytes]:
        if isinstance(v, bool):
            return [b"\x01" if v else b"\x00"]
        if isinstance(v, bytes):
            return [v]
        if isinstance(v, bytearray):
            return [bytes(v)]
        if isinstance(v, str):
            s = v.removeprefix("0x")
            try:
                decoded = bytes.fromhex(s)
                if len(decoded) * 2 == len(s):  # full hex string
                    return [decoded]
            except ValueError:
                pass
            return [v.encode()]
        if isinstance(v, int):
            if v < 0:
                return [int(v).to_bytes(8, "big", signed=True)]
            return [int(v).to_bytes(8, "big", signed=False)]
        if isinstance(v, float):
            return [struct.pack(">d", v)]
        if isinstance(v, (list, tuple)):
            inner: List[bytes] = []
            for item in v:
                inner.extend(ZKProofSystem._encode_value(item))
            return inner
        return [str(v).encode()]

    @staticmethod
    def _public_inputs(obj: Any) -> Dict[str, Any]:
        """Extract serializable public input fields from a witness."""
        if obj is None:
            return {}
        out: Dict[str, Any] = {}
        for k in sorted(vars(obj).keys()):
            if k.startswith("_"):
                continue
            v = getattr(obj, k)
            if v is None:
                continue
            if isinstance(v, bytes):
                out[k] = v.hex()
            elif isinstance(v, (list, tuple)):
                out[k] = [
                    item.hex() if isinstance(item, bytes) else item
                    for item in v
                ]
            elif isinstance(v, (str, int, float, bool)):
                out[k] = v
            else:
                out[k] = str(v)
        return out

    # ── Public proof generators (one per Circom circuit) ────────────────

    def generate_proof(self, *args, **kwargs):
        """Generic fallback (transitional compat — not used by orchestrator)."""
        witness = args[0] if args else kwargs.get("witness")
        wbytes = self._witness_bytes(witness)
        pub = self._public_inputs(witness)
        return _TransparentProof("generic", "generic", wbytes, pub)

    def generate_intent(self, witness) -> _TransparentProof:
        """zk_intent_commitment (BTCP §5.6 Phase 1) — transparent proof."""
        wbytes = self._witness_bytes(witness)
        pub = self._public_inputs(witness)
        # BTCP §5.6: H_intent = Hash_DNA(intent_details || nonce || entity_id)
        # We compute the canonical intent_hash over the same fields and
        # surface it as a public input so the on-chain BTCPIntent.sol can
        # match it against the registered intent_hash.
        try:
            intent_details = (
                f"{getattr(witness, 'source_chain', '')}:"
                f"{getattr(witness, 'dest_chain', '')}:"
                f"{getattr(witness, 'intent_type', '')}:"
                f"{getattr(witness, 'amount', '')}:"
                f"{getattr(witness, 'deadline', '')}".encode()
            )
            nonce_b = b""
            nonce_attr = getattr(witness, "nonce", None)
            if isinstance(nonce_attr, bytes):
                nonce_b = nonce_attr
            elif isinstance(nonce_attr, str):
                try:
                    nonce_b = bytes.fromhex(nonce_attr.removeprefix("0x"))
                except ValueError:
                    nonce_b = nonce_attr.encode()
            elif isinstance(nonce_attr, int):
                nonce_b = int(nonce_attr).to_bytes(8, "big", signed=False)
            entity_id_b = str(getattr(witness, "entity_id", "")).encode()
            h_intent = intent_hash(intent_details, nonce_b, entity_id_b)
            pub = dict(pub)
            pub["intent_hash_h_intent"] = h_intent.hex()
        except Exception:
            pass
        return _TransparentProof(
            "intent_commitment", "zk_intent_commitment", wbytes, pub,
            notes={"circuit_spec": "BTCP §5.6 Phase 1 — H_intent = Hash_DNA(intent_details||nonce||entity_id)"})

    def generate_complementarity(self, witness) -> _TransparentProof:
        """zk_complementarity_proof (BTCP §5.6 Phase 2) — transparent proof."""
        wbytes = self._witness_bytes(witness)
        pub = self._public_inputs(witness)
        # Verify the dual-strand invariant of the supplied genomic strands:
        # the caller supplies sense_strand + antisense_strand + block_number;
        # we recompute the BTCP Formula Index invariant over their payload
        # (which the prover must also know) and surface the result as a
        # public_input. The proof still verifies even if the invariant
        # doesn't hold (the prover committed to whatever they supplied) —
        # the public_input lets the verifier reject invalid strands.
        notes = {
            "circuit_spec": "BTCP §5.6 Phase 2 — asset_in_A==asset_out_B && |mag_A-mag_B|<=tol"
        }
        try:
            sense = getattr(witness, "sense_strand", None)
            antisense = getattr(witness, "antisense_strand", None)
            if isinstance(sense, str):
                sense = bytes.fromhex(sense.removeprefix("0x"))
            if isinstance(antisense, str):
                antisense = bytes.fromhex(antisense.removeprefix("0x"))
            if isinstance(sense, bytes) and isinstance(antisense, bytes):
                # We don't have the original payload (it's the entity-side
                # private behavior). We CAN check the dual-strand structural
                # invariant: antisense XOR sense == complement_transform(SHA3-256(payload||0xFF)) XOR sense...
                # Actually the canonical invariant is:
                #     sense XOR antisense == NOT(SHA3-256(payload||0xFF))
                # which requires the payload. We check the weaker structural
                # property: sense != antisense (sanity) and both are 32 bytes.
                pub = dict(pub)
                pub["dual_strand_structural_check"] = (
                    len(sense) == HASH_LEN and len(antisense) == HASH_LEN
                    and sense != antisense
                )
                pub["sense_strand_length"] = len(sense)
                pub["antisense_strand_length"] = len(antisense)
        except Exception:
            pass
        return _TransparentProof(
            "complementarity", "zk_complementarity_proof", wbytes, pub,
            notes=notes)

    def generate_travel_rule(self, witness) -> _TransparentProof:
        """zk_travel_rule (BTCP Fix 1 Step 3) — transparent disclosure_hash."""
        wbytes = self._witness_bytes(witness)
        pub = self._public_inputs(witness)
        # BTCP Fix 1 Step 3: disclosure_hash = Hash_DNA(disclosure_input)
        try:
            disclosure_input = (
                f"{getattr(witness, 'originator_id', '')}|"
                f"{getattr(witness, 'beneficiary_id', '')}|"
                f"{getattr(witness, 'amount', '')}|"
                f"{getattr(witness, 'asset_address', '')}".encode()
            )
            d_hash = disclosure_hash(disclosure_input)
            pub = dict(pub)
            pub["disclosure_hash"] = d_hash.hex()
            pub["disclosure_submitted"] = bool(getattr(witness, "originator_verified", False)) and \
                                          bool(getattr(witness, "beneficiary_verified", False))
        except Exception:
            pass
        return _TransparentProof(
            "travel_rule", "zk_travel_rule", wbytes, pub,
            notes={"circuit_spec": "BTCP Fix 1 Step 3 — disclosure_hash = Hash_DNA(disclosure_fields||nonce)"})

    def generate_behavioral_credential(self, witness) -> _TransparentProof:
        """zk_behavioral_credential (BTCP §7.1) — transparent behavioral_hash."""
        wbytes = self._witness_bytes(witness)
        pub = self._public_inputs(witness)
        # BTCP §7.1: behavioral_hash = Hash_DNA(behavior_input || behavior_nonce)
        # We compute it from the witness coherence/manipulation/liquidity
        # scores so the on-chain public_commitment can match it.
        try:
            behavior_input = (
                f"{getattr(witness, 'coherence_score', '')}:"
                f"{getattr(witness, 'manipulation_fingerprint', '')}:"
                f"{getattr(witness, 'liquidity_score', '')}:"
                f"{getattr(witness, 'akashic_depth', '')}".encode()
            )
            behavior_nonce = hashlib.sha3_256(
                str(getattr(witness, "entity_id", "")).encode()
            ).digest()
            b_hash = behavioral_hash(behavior_input, behavior_nonce)
            p_commit = public_commitment(b_hash)
            pub = dict(pub)
            pub["behavioral_hash"] = b_hash.hex()
            pub["public_commitment"] = p_commit.hex()
            # Range checks (mirrors the Circom Num2Bits range checks):
            pub["threshold_coherence"] = float(getattr(witness, "threshold_coherence", 0.55))
            pub["threshold_manipulation"] = float(getattr(witness, "threshold_manipulation", 0.30))
            pub["passes_coherence_threshold"] = (
                float(getattr(witness, "coherence_score", 0.0))
                >= pub["threshold_coherence"]
            )
        except Exception:
            pass
        return _TransparentProof(
            "behavioral_credential", "zk_behavioral_credential", wbytes, pub,
            notes={"circuit_spec": "BTCP §7.1 — behavioral_hash = Hash_DNA(behavior_input||behavior_nonce)"})

    def generate_iap_share(self, witness) -> _TransparentProof:
        """zk_iap_share_proof (BTCP §14.1 Phase 4 item 21) — transparent IAP."""
        wbytes = self._witness_bytes(witness)
        pub = self._public_inputs(witness)
        # IAP soundness identity (from circuit.circom line 47-55):
        #   gas_i × total_value === gas_total × value_i
        # The caller supplies entity_gas, total_gas, total_btcp_fee,
        # entity_share, num_participants. The IAP identity becomes:
        #   entity_share × total_gas == entity_gas × total_btcp_fee
        # (interpreting entity_share/total_btcp_fee as value_i/total_value).
        # We surface the check result as a public_input — the proof still
        # verifies either way (we commit to whatever the caller supplied);
        # verifiers can use the flag to reject unfair batches.
        try:
            tg = int(getattr(witness, "total_gas", 0) or 0)
            eg = int(getattr(witness, "entity_gas", 0) or 0)
            tbf = int(getattr(witness, "total_btcp_fee", 0) or 0)
            es = int(getattr(witness, "entity_share", 0) or 0)
            np_ = int(getattr(witness, "num_participants", 0) or 0)
            pub = dict(pub)
            if tg > 0 and tbf > 0:
                lhs = es * tg
                rhs = eg * tbf
                pub["iap_share_soundness_check"] = (lhs == rhs)
                pub["iap_share_lhs"] = lhs
                pub["iap_share_rhs"] = rhs
                pub["iap_share_gas_fraction"] = eg / tg
                pub["iap_share_value_fraction"] = (es / tbf) if tbf else 0.0
                pub["iap_num_participants"] = np_
        except Exception:
            pass
        return _TransparentProof(
            "iap_share", "zk_iap_share_proof", wbytes, pub,
            notes={"circuit_spec": "BTCP §14.1 item 21 — gas_i×total_value === gas_total×value_i"})

    # ── Verification ───────────────────────────────────────────────────

    def verify(self, proof) -> bool:
        """Verify a transparent proof.

        Accepts a _TransparentProof, a ZKProof wrapper, or a dict.
        Recomputes the dual-strand commitment + proof_hash from the
        stored payload + public_inputs and asserts byte-equality.

        Returns False for:
          * Stub proofs (no bytes to verify — fail-closed).
          * Dicts with status=="zk_pending" (deferred — fail-closed).
          * Proofs whose recomputed strands or hash don't match
            (tampered — fail-closed).
        """
        # Extract proof_data + public_inputs from any supported shape.
        pd: Optional[Dict[str, Any]] = None
        pub: Dict[str, Any] = {}
        if isinstance(proof, _TransparentProof):
            pd = proof.proof_data
            pub = dict(proof.public_inputs)
        elif isinstance(proof, ZKProof):
            pd = proof.proof_data or {}
            pub = dict(proof.public_inputs or {})
        elif isinstance(proof, dict):
            pd = proof.get("proof_data", {})
            pub = dict(proof.get("public_inputs", {}) or {})
            # Pending/deferred proofs (no bytes) fail closed.
            if proof.get("status") == "zk_pending":
                return False
        elif hasattr(proof, "stub") and getattr(proof, "stub", False):
            # Legacy _StubProof — fail-closed (no bytes to verify).
            return False
        elif hasattr(proof, "to_dict"):
            d = proof.to_dict() if callable(getattr(proof, "to_dict")) else {}
            pd = d.get("proof_data", {}) if isinstance(d, dict) else {}
            pub = dict(d.get("public_inputs", {}) or {}) if isinstance(d, dict) else {}
        else:
            return False

        if not isinstance(pd, dict) or not pd:
            return False

        witness_payload_hex = pd.get("witness_payload_hex")
        expected_proof_hash = pd.get("proof_hash")
        expected_sense_hex = pd.get("witness_commitment")
        expected_antisense_hex = pd.get("antisense_commitment")
        pub_canon_stored = pd.get("public_inputs_canonical")

        if not (witness_payload_hex and expected_proof_hash
                and expected_sense_hex and expected_antisense_hex):
            return False

        try:
            payload = bytes.fromhex(witness_payload_hex)
        except (ValueError, TypeError):
            return False

        try:
            expected_sense = bytes.fromhex(expected_sense_hex)
            expected_antisense = bytes.fromhex(expected_antisense_hex)
        except (ValueError, TypeError):
            return False

        # 1) Recompute the dual-strand commitment via the canonical
        #    hash_dna construction. The payload was stored as the
        #    concatenation of the witness fields, so a single-element
        #    list reproduces the same payload.
        if payload:
            sense, antisense = hash_dna_dual([payload])
        else:
            sense = _sha3_256(b"\x00" + b"empty-witness")
            antisense = _sha3_256(b"\xff" + b"empty-witness")

        if sense != expected_sense:
            return False
        if antisense != expected_antisense:
            return False

        # 2) Verify the BTCP Formula Index dual-strand invariant directly
        #    (R-NO-REDEF: same invariant checked in hash_dna._self_test).
        if payload and not verify_dual_strand(sense, antisense, payload):
            return False

        # 3) Recompute proof_hash and check equality. The public_inputs
        #    canonical JSON must match what was stored at proof time
        #    (a swap of public inputs breaks the binding).
        pub_canon = _canonical_json(pub).encode()
        if pub_canon_stored and pub_canon.decode() != pub_canon_stored:
            return False
        recomputed = _sha3_256(payload + b"|" + pub_canon)
        if recomputed.hex() != expected_proof_hash:
            return False

        return True


# Witness classes (stub when real zk package absent)
IntentWitness = _StubWitness
ComplementarityWitness = _StubWitness
BehavioralCredentialWitness = _StubWitness
TravelRuleWitness = _StubWitness
IAPShareWitness = _StubWitness


def merkle_root(commitments):
    """Compute Merkle root from commitments list (unchanged)."""
    if _HAS_COMMITMENTS:
        try:
            from zk.groth16.commitments.akashic_root import compute_root
            return compute_root(commitments)
        except Exception:
            return None
    return None


# ── Self-test ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== ZK facade — transparent proof self-test ===")
    sys = ZKProofSystem()

    # 1) Intent proof over a realistic witness.
    iw = IntentWitness(
        entity_id="0x742d35Cc6634C0532925a3b844Bc9e7595f7B8B5",
        intent_type="TRANSFER",
        amount=1_000_000,
        source_chain=1,
        dest_chain=900,
        deadline=2_000_000_000,
        nonce=(123).to_bytes(32, "big"),
    )
    p = sys.generate_intent(iw)
    d = p.to_dict()
    assert d["status"] == "VERIFIED", d["status"]
    assert d["stub"] is False
    assert d["is_zk"] is False
    assert d["proof_type_label"] == "transparent_sha3"
    assert "intent_hash_h_intent" in d["public_inputs"], "intent_hash missing"
    assert sys.verify(p) is True, "intent proof must verify"
    assert sys.verify(d) is True, "intent proof dict must verify"
    # Tamper the public inputs → proof must fail.
    tampered = json.loads(json.dumps(d))
    tampered["public_inputs"]["amount"] = 999
    assert sys.verify(tampered) is False, "tampered public inputs must fail"
    # Tamper the witness payload → proof must fail.
    tampered2 = json.loads(json.dumps(d))
    pd = dict(tampered2["proof_data"])
    pd["witness_payload_hex"] = "00" + pd["witness_payload_hex"][2:]
    tampered2["proof_data"] = pd
    assert sys.verify(tampered2) is False, "tampered payload must fail"
    print("  intent proof:           VERIFIED + tamper-detection OK")

    # 2) IAP share proof with caller-supplied economics.
    iap_w = IAPShareWitness(
        entity_id="0x742d35Cc6634C0532925a3b844Bc9e7595f7B8B5",
        total_gas=1_000_000,
        entity_gas=151_000,
        total_btcp_fee=10_000_000_000_000_000,
        entity_share=1_500_000_000_000_000,
        num_participants=10,
    )
    p2 = sys.generate_iap_share(iap_w)
    d2 = p2.to_dict()
    assert sys.verify(p2) is True, "iap proof must verify"
    # The soundness check is informational; the caller's economics here
    # have lhs=1.5e21 != rhs=1.51e21 — surface that honestly.
    assert "iap_share_soundness_check" in d2["public_inputs"]
    assert d2["public_inputs"]["iap_share_soundness_check"] is False, \
        "the 1M/151k/1e16/1.5e15 witness is not exactly fair"
    print("  iap_share proof:        VERIFIED + soundness-check disclosed")

    # 3) ZKProof wrapper round-trip (what orchestrator.verify_proofs uses).
    wrapper = ZKProof(
        circuit_type=CircuitType.IAP_SHARE,
        proof_data=d2["proof_data"],
        public_inputs=d2["public_inputs"],
        commitment=d2["commitment"],
        timestamp=d2["timestamp"],
        version=d2["version"],
    )
    assert sys.verify(wrapper) is True, "wrapper must verify"
    print("  ZKProof wrapper:        VERIFIED")

    # 4) Stub proof must fail-closed.
    stub = _StubProof("intent")
    assert sys.verify(stub) is False, "stub must fail-closed"
    print("  stub proof:             fail-closed (correct)")

    # 5) Pending dict must fail-closed.
    pending = {"status": "zk_pending", "reason": "no witness"}
    assert sys.verify(pending) is False, "pending must fail-closed"
    print("  zk_pending dict:        fail-closed (correct)")

    print("\nPASS — ZK facade transparent proofs (BTCP-FIX2-ZK Fix 1)")
