"""
TRION BTCP — Modules 2.4-2.18: Proof Builder, BITP, Netting, Intent Aggregator,
OOA Anchor, Shadow Observer, State Capsule, Failure Classifier, Genesis
Commitment, BLO Scheduler, State Channel, Finality Normalizer, Version Handler,
Validator Fee Calculator, Sybil Resistance
================================================================================

Per BTCP Master Spec §Phase 2 Modules 2.4-2.18, these are the remaining
BTCP Rust modules implemented in Python.

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, List, Optional, Tuple, Any, Union


# ═══════════════════════════════════════════════════════════════════════════════
# Module 2.4: BTCP Proof Builder
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ValidatorSignature:
    validator_id:   bytes
    signature:      bytes
    diversity_weight: float


@dataclass
class ConsensusProof:
    validator_signatures: List[ValidatorSignature]
    diversity_certificate: List[float]  # all d_j values
    hhi_at_emission:      float
    coherence_score:      float
    threshold_margin:     float


@dataclass
class ConsensusAttestation:
    """Diversity-Weighted BFT attestation emitted by the spiritual plane.

    Bundles the outputs of `core.spiritual.consensus.compute_dw_bft_consensus`
    so the BTCP proof builder can call it once and pass the results through
    without re-running the diversity computation per proof.

    Closes AUDIT-1 gap #5: "DW-BFT consensus layer is disconnected from BTCP
    proof builder."
    """
    diversity_certificate:    List[float]    # all d_j values
    hhi:                      float          # HHI diversity concentration
    sigma:                    float          # Σ(t) ∈ [0,1] — coherence score
    threshold_margin:         float          # Σ_honest - (2/3)·Σ_total
    safety_holds:             bool           # L4.3 safety condition
    self_defeating_proof:     str            # formal statement
    consensus_value:          float          # v̄ stake-diversity-weighted mean
    validators_in_consensus:  int
    validator_count:          int
    hhi_health:               str            # HEALTHY / WARNING / CRITICAL


@dataclass
class BTCPProof:
    """BTCP_proof for cross-chain verification."""
    anchor_bh:             bytes  # HashDNA
    consensus_proof:       ConsensusProof
    intent_hash:           bytes
    route_type:            int
    certification_block:   int
    certification_expiry:  int
    validator_key_version: bytes


class BTCPProofBuilder:
    """
    Module 2.4: Constructs BTCP_proof for cross-chain verification.

    Verification on receiving chain:
    1. Check consensus_proof against known TRION validator set
    2. Check certification_block is within certification_expiry
    3. Check validator_key_version was valid at certification_block
    4. If valid: execute natively — no bridge contract, no wrapped token
    """

    # A3 Resolution: Certification validity windows by value tier
    CERT_WINDOWS = [
        (1_000,         10_000),    # <$1K → 10K blocks
        (100_000,       50_000),    # $1K-$100K → 50K blocks
        (10_000_000,    200_000),   # $100K-$10M → 200K blocks
        (float('inf'),  500_000),   # >$10M → 500K blocks
    ]

    def compute_cert_expiry(self, value_usd: float) -> int:
        """A3: Certification validity window based on route value."""
        for threshold, blocks in self.CERT_WINDOWS:
            if value_usd < threshold:
                return blocks
        return 500_000

    def build_proof(
        self,
        anchor_bh: bytes,
        intent_hash: bytes,
        route_type: int,
        certification_block: int,
        value_usd: float,
        validator_signatures: List[ValidatorSignature],
        diversity_weights: List[float],
        hhi: float,
        coherence: float,
        threshold: float,
        validator_key_version: bytes = b"\x00" * 4,
    ) -> BTCPProof:
        expiry = self.compute_cert_expiry(value_usd)
        consensus = ConsensusProof(
            validator_signatures=validator_signatures,
            diversity_certificate=diversity_weights,
            hhi_at_emission=hhi,
            coherence_score=coherence,
            threshold_margin=coherence - threshold,
        )
        return BTCPProof(
            anchor_bh=anchor_bh,
            consensus_proof=consensus,
            intent_hash=intent_hash,
            route_type=route_type,
            certification_block=certification_block,
            certification_expiry=certification_block + expiry,
            validator_key_version=validator_key_version,
        )

    # ── FIX-2: Consensus wiring (AUDIT-1 gap #5) ──────────────────────────────

    # Default threshold for Σ(t) — the BTCP proof is only valid if coherence
    # exceeds this. Whitepaper §4.3 specifies 2/3 BFT threshold; the
    # coherence form Σ(t) > 0.55 mirrors the spiritual plane default.
    DEFAULT_COHERENCE_THRESHOLD = 0.55

    def build_consensus_attestation(
        self,
        validators: List[Any],
        delta: float = 0.05,
    ) -> ConsensusAttestation:
        """Call the spiritual plane's DW-BFT consensus layer to produce a
        diversity certificate attestation.

        Resolves `core.spiritual.consensus.compute_dw_bft_consensus(validators)`
        and bundles the outputs into a `ConsensusAttestation` that the BTCP
        proof builder can attach to a BTCPProof.

        Args:
            validators: list of `core.spiritual.consensus.Validator` instances.
            delta: consensus agreement band width (default 0.05 = 5%).

        Returns:
            ConsensusAttestation with diversity_certificate, hhi, sigma,
            threshold_margin, safety_holds, self_defeating_proof, etc.
        """
        # Lazy import to avoid hard coupling at module load time. The
        # spiritual plane consensus module imports numpy via sigma_engine,
        # which may not be present in every consumer of the BTCP proof
        # builder. Failure to import degrades gracefully into a
        # bootstrap-mode attestation that the caller can inspect via
        # `safety_holds == False`.
        try:
            from core.spiritual.consensus import (
                compute_dw_bft_consensus,
                BFTConsensusResult,
            )
        except Exception as e:  # pragma: no cover — import-error path
            return ConsensusAttestation(
                diversity_certificate=[],
                hhi=10_000.0,
                sigma=0.0,
                threshold_margin=-1.0,
                safety_holds=False,
                self_defeating_proof=(
                    f"Spiritual plane consensus module unavailable: "
                    f"{type(e).__name__}: {e}. BTCP proof builder operating in "
                    f"bootstrap mode — diversity certificate empty, Σ(t)=0."
                ),
                consensus_value=0.0,
                validators_in_consensus=0,
                validator_count=0,
                hhi_health="CRITICAL",
            )

        result: BFTConsensusResult = compute_dw_bft_consensus(validators, delta=delta)
        return ConsensusAttestation(
            diversity_certificate=[
                r.diversity_weight for r in result.diversity_results
            ],
            hhi=result.hhi,
            sigma=result.sigma,
            threshold_margin=result.safety_margin,
            safety_holds=result.safety_holds,
            self_defeating_proof=result.self_defeating_proof,
            consensus_value=result.consensus_value,
            validators_in_consensus=result.validators_in_consensus,
            validator_count=result.validator_count,
            hhi_health=result.hhi_health,
        )

    def build_proof_from_validators(
        self,
        anchor_bh: bytes,
        intent_hash: bytes,
        route_type: int,
        certification_block: int,
        value_usd: float,
        validators: List[Any],
        validator_signatures: List[ValidatorSignature],
        delta: float = 0.05,
        coherence_threshold: Optional[float] = None,
        validator_key_version: bytes = b"\x00" * 4,
    ) -> Tuple[BTCPProof, ConsensusAttestation]:
        """Build a BTCPProof by calling the spiritual plane consensus layer
        to compute the diversity certificate, HHI, and Σ(t) coherence score.

        This is the canonical BTCP proof-construction entry point per
        AUDIT-1 gap #5 — previously the BTCP proof builder accepted diversity
        weights and HHI as opaque caller-supplied values with no live
        consensus call. Now the proof builder pulls them from the spiritual
        plane's DW-BFT consensus module.

        Args:
            anchor_bh: anchor-chain HashDNA (32 bytes).
            intent_hash: SHA3-256 of the BTCP intent (32 bytes).
            route_type: TRION route type code (see BTCPRoute.sol).
            certification_block: anchor block at which proof is emitted.
            value_usd: USD value of the route (controls cert expiry window).
            validators: list of `core.spiritual.consensus.Validator`.
            validator_signatures: BLS/Ed25519 signatures from the validator
                cohort (production) or mock signatures (dev).
            delta: consensus agreement band (default 5%).
            coherence_threshold: optional override (default 0.55).
            validator_key_version: 4-byte key version for ICA rotation.

        Returns:
            Tuple of (BTCPProof, ConsensusAttestation). The attestation is
            returned alongside the proof so the caller can attach the
            `self_defeating_proof` statement and `hhi_health` to the
            Akashic record for audit.
        """
        attestation = self.build_consensus_attestation(validators, delta=delta)
        # INV-010: the coherence threshold is protocol-owned. A caller
        # may TIGHTEN it (raise above the default floor) but never lower
        # it — previously coherence_threshold=0.0 produced a proof whose
        # threshold_margin was trivially non-negative and thus always
        # passed verify_proof.
        threshold = max(
            self.DEFAULT_COHERENCE_THRESHOLD,
            coherence_threshold if coherence_threshold is not None
            else self.DEFAULT_COHERENCE_THRESHOLD,
        )
        proof = self.build_proof(
            anchor_bh=anchor_bh,
            intent_hash=intent_hash,
            route_type=route_type,
            certification_block=certification_block,
            value_usd=value_usd,
            validator_signatures=validator_signatures,
            diversity_weights=attestation.diversity_certificate,
            hhi=attestation.hhi,
            coherence=attestation.sigma,
            threshold=threshold,
            validator_key_version=validator_key_version,
        )
        return proof, attestation

    def verify_proof(self, proof: BTCPProof, current_block: int) -> bool:
        """Verify a BTCP_proof on the receiving chain.

        Structural checks mirror rust/src/btcp_proof_builder.rs verify_proof
        so a proof accepted here is also accepted by the rust verifier (and
        vice versa) — the old python checks were strictly weaker (no HHI,
        no signer-count, no distinct-signer/shape checks), so a python-built
        proof could pass here and fail on the rust side:
          * certification window (expiry / anchor depth)
          * coherence above threshold
          * HHI not too concentrated — the python spiritual plane emits HHI on
            the 0-10000 scale, rust on 0-1; values > 1 are normalised before
            the shared > 0.5 rejection threshold
          * >= 3 validator signatures (rust: InsufficientSigners)
          * distinct signers, each signature exactly 65 bytes
            (secp256k1 ECDSA r[32] || s[32] || v[1]) — shape check only;
            cryptographic verification is the on-chain quorum's job
        """
        if current_block > proof.certification_expiry:
            return False  # certification expired
        sigs = proof.consensus_proof.validator_signatures
        if len(sigs) < 3:
            return False  # insufficient signers (rust parity)
        if proof.consensus_proof.coherence_score <= 0:
            return False
        if proof.consensus_proof.threshold_margin < 0:
            return False  # coherence below threshold
        hhi = float(proof.consensus_proof.hhi_at_emission)
        if hhi > 1.0:
            hhi = hhi / 10_000.0  # python 0-10000 scale → rust 0-1 scale
        if hhi > 0.5:
            return False  # too concentrated (rust parity)
        seen = set()
        for sig in sigs:
            vid = sig.validator_id if isinstance(sig.validator_id, bytes) else bytes(sig.validator_id)
            if vid in seen:
                return False  # duplicate signer (rust parity)
            seen.add(vid)
            s = sig.signature if isinstance(sig.signature, bytes) else bytes(sig.signature)
            if len(s) != 65:
                return False  # malformed signature shape (rust parity)
        return True

    # ── FIX-3: Real validator signature aggregation (gap-fill #2) ────────────────
    #
    # Replaces the SHA3-mock signatures used by the legacy ``build_proof`` path
    # with real Schnorr-multisig aggregation on secp256k1. The consensus proof
    # produced here is a self-contained dict that downstream consumers can
    # cryptographically verify without needing the spiritual plane consensus
    # module to be importable.

    DEFAULT_QUORUM_FRACTION = 2.0 / 3.0

    def build_consensus_proof(
        self,
        intent_hash: bytes,
        validator_keys: List[Tuple[bytes, bytes]],
        threshold: Optional[float] = None,
        quorum_fraction: Optional[float] = None,
        total_validators: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Build a real validator-signed consensus proof.

        Replaces the SHA3-mock signatures with real Schnorr-multisig (BLS-like)
        signatures from ``core.spiritual.signature_aggregation.ValidatorSignatureAggregator``.

        Args:
            intent_hash: 32-byte SHA3-256 of the BTCP intent being attested.
            validator_keys: list of ``(private_key, public_key)`` tuples for
                each signing validator. ``private_key`` is a 32-byte scalar,
                ``public_key`` is the 33-byte compressed curve point.
            threshold: optional override for the quorum fraction (default 2/3).
            quorum_fraction: alias for ``threshold`` (kept for clarity).
            total_validators: optional override for the total validator set
                size (defaults to ``len(validator_keys)``). Set this when
                only a subset of validators actually signed (e.g. 3 of 5).

        Returns:
            dict with keys:
              - validator_signatures: list of real sig dicts {r, s, v, public_key}
              - aggregate_signature:  real aggregated signature dict
              - signer_count:         int (number of signers)
              - total_validators:     int (size of full validator set)
              - threshold_met:        bool (signer_count/total >= quorum)
              - intent_hash:          hex of the attested intent hash
              - scheme:               "schnorr-musig-bls-like"
              - curve:                "secp256k1"
              - hash:                 "sha3-256"
        """
        from core.spiritual.signature_aggregation import ValidatorSignatureAggregator

        q = quorum_fraction if quorum_fraction is not None else (
            threshold if threshold is not None else self.DEFAULT_QUORUM_FRACTION
        )
        aggregator = ValidatorSignatureAggregator()
        if total_validators is None:
            total_validators = len(validator_keys)

        validator_signatures: List[Dict[str, Any]] = []
        messages: List[bytes] = []
        public_keys: List[bytes] = []
        for priv, pub in validator_keys:
            # Each validator signs (intent_hash || validator_pubkey) so the
            # signature binds both the intent and the signer's identity.
            msg = intent_hash + pub
            sig = aggregator.sign(msg, priv)
            validator_signatures.append(sig)
            messages.append(msg)
            public_keys.append(pub)

        agg_sig = aggregator.aggregate(validator_signatures, messages)
        signer_count = len(validator_signatures)
        threshold_met = aggregator.threshold_met(
            signer_count, total_validators, quorum_fraction=q,
        )

        return {
            "validator_signatures": validator_signatures,
            "aggregate_signature":  agg_sig,
            "signer_count":          signer_count,
            "total_validators":      total_validators,
            "threshold_met":         threshold_met,
            "quorum_fraction":       q,
            "intent_hash":           intent_hash.hex(),
            "scheme":                aggregator.PROOF_SYSTEM,
            "curve":                 aggregator.CURVE,
            "hash":                  aggregator.HASH,
            "version":                aggregator.VERSION,
        }

    def verify_consensus_proof(self, consensus_proof: Dict[str, Any]) -> bool:
        """Verify a real consensus proof produced by ``build_consensus_proof``.

        Performs real signature verification via the
        ``ValidatorSignatureAggregator``: reconstructs the per-signer messages,
        runs the aggregate verification equation
        ``s_agg · G == Σ R_i + Σ e_i · pk_i`` over secp256k1, and confirms
        that the quorum threshold was met.
        """
        try:
            from core.spiritual.signature_aggregation import ValidatorSignatureAggregator
            aggregator = ValidatorSignatureAggregator()

            validator_sigs = consensus_proof["validator_signatures"]
            agg_sig        = consensus_proof["aggregate_signature"]
            signer_count   = consensus_proof["signer_count"]
            total_validators = consensus_proof.get(
                "total_validators", signer_count,
            )
            threshold_met  = consensus_proof["threshold_met"]
            intent_hash_hex = consensus_proof["intent_hash"]
            intent_hash    = bytes.fromhex(intent_hash_hex)

            if signer_count != len(validator_sigs):
                return False
            if signer_count > total_validators:
                return False
            if not threshold_met:
                return False
            # INV-012: the quorum is RECOMPUTED here with the protocol
            # floor (DEFAULT_QUORUM_FRACTION = 2/3) — the proof dict's own
            # threshold_met / quorum_fraction fields are claims, not
            # authority. A forged {threshold_met: true, total_validators: 1}
            # alongside one real signature previously verified; now it
            # cannot. A builder that legitimately used a HIGHER quorum is
            # still honored (max of claimed and floor).
            claimed_quorum = consensus_proof.get(
                "quorum_fraction", self.DEFAULT_QUORUM_FRACTION,
            )
            effective_quorum = max(
                float(claimed_quorum), self.DEFAULT_QUORUM_FRACTION,
            )
            if total_validators <= 0:
                return False
            if signer_count / total_validators < effective_quorum:
                return False

            # Reconstruct (messages, public_keys) in the SAME order the prover
            # used:  msg_i = intent_hash || pub_i
            messages: List[bytes] = []
            public_keys: List[bytes] = []
            for sig in validator_sigs:
                pub = bytes.fromhex(sig["public_key"])
                messages.append(intent_hash + pub)
                public_keys.append(pub)

            return aggregator.verify_aggregate(agg_sig, messages, public_keys)
        except Exception:
            return False


# ═══════════════════════════════════════════════════════════════════════════════
# Module 2.5: BITP Matcher
# ═══════════════════════════════════════════════════════════════════════════════

# BTCP Master Spec §4.1 — Intent object enumerations (BITPIntent values)
INTENT_ACTIONS      = frozenset({"SWAP", "TRANSFER", "LIQUIDITY", "STAKE", "BORROW"})
MIN_FINALITY_LEVELS = frozenset({"FAST", "STANDARD", "SECURE"})
PRIVACY_LEVELS      = frozenset({"PUBLIC", "ZK_CREDENTIAL", "INVISIBLE"})
CHAIN_PREF_MODES    = frozenset({"OPTIMAL", "SINGLE_CHAIN"})


def _canonical_intent_field(value: Any) -> str:
    """Deterministic string encoding of one BITPIntent field for hashing.

    bytes → hex, str → as-is, list/tuple → comma-joined recursively,
    None → "none", floats via repr() (stable across runs/processes).
    Mirrors the append-only hash policy of ``rust/src/types.rs``
    ``Intent::hash()`` (the Python and Rust intents carry different
    legacy field sets, so the byte streams differ by construction; the
    encoding policy — canonical per-field text, colon-joined — is
    identical).
    """
    if value is None:
        return "none"
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).hex()
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_canonical_intent_field(v) for v in value) + "]"
    if isinstance(value, float):
        return repr(value)
    return str(value)


@dataclass
class BITPIntent:
    """Behavioral intent object — BTCP Master Spec §4.1.

    The legacy BITP fields keep their positional order (entity_id,
    asset_in, asset_out, magnitude, chain_id, deadline) so every existing
    6-argument construction keeps working. The §4.1 field set is appended
    with the spec defaults:

    ==============  =================================================
    action           SWAP | TRANSFER | LIQUIDITY | STAKE | BORROW
    value            uint256 behavioral magnitude units
    max_total_gas    uint128 USD equivalent across all chains (None =
                     unbounded)
    min_finality     FAST | STANDARD | SECURE
    min_nl_score     uint16 ×1000 liquidity-health floor (spec name
                     min_NL_score; 300 = 0.30 — naming follows the repo's
                     ``nl_score`` convention, see core/akashic/bibl.py)
    chain_pref       OPTIMAL | [chain_list] | SINGLE_CHAIN
    privacy          PUBLIC | ZK_CREDENTIAL | INVISIBLE
    btcp_version     semver string (spec encodes as bytes12)
    nonce            per-entity monotonic counter (uint64)
    ==============  =================================================

    ``value`` stays ``None`` when unset (the legacy ``magnitude`` float
    carries the same information for BITP matching).
    """
    # legacy BITP fields — positional order frozen (backwards compatible)
    entity_id:    bytes
    asset_in:     bytes
    asset_out:    bytes
    magnitude:    float
    chain_id:     int
    deadline:     int
    # BTCP Master Spec §4.1 fields (defaults per spec)
    action:        str = "SWAP"
    value:         Optional[int] = None
    max_total_gas: Optional[int] = None
    min_finality:  str = "STANDARD"
    min_nl_score:  int = 300            # ×1000 → default 0.30 NL floor
    chain_pref:    Union[str, List[int]] = "OPTIMAL"
    privacy:       str = "PUBLIC"
    btcp_version:  str = "1.0.0"        # semver (spec encodes as bytes12)
    nonce:         int = 0              # per-entity monotonic counter

    def hash(self) -> bytes:
        """SHA3-256 over the §4.1 field set (legacy fields first).

        Legacy BITP fields in their original order with the §4.1 fields
        appended after them, colon-joined, SHA3-256 — the same
        append-only extension policy as ``rust/src/types.rs``
        ``Intent::hash()``. No pinned vectors existed for this object
        before (BITPIntent had no hash), so the format is defined here
        once and stays stable going forward.
        """
        parts = [
            _canonical_intent_field(self.entity_id),
            _canonical_intent_field(self.asset_in),
            _canonical_intent_field(self.asset_out),
            _canonical_intent_field(self.magnitude),
            _canonical_intent_field(self.chain_id),
            _canonical_intent_field(self.deadline),
            # BTCP Master Spec §4.1 fields
            _canonical_intent_field(self.action),
            _canonical_intent_field(self.value),
            _canonical_intent_field(self.max_total_gas),
            _canonical_intent_field(self.min_finality),
            _canonical_intent_field(self.min_nl_score),
            _canonical_intent_field(self.chain_pref),
            _canonical_intent_field(self.privacy),
            _canonical_intent_field(self.btcp_version),
            _canonical_intent_field(self.nonce),
        ]
        return hashlib.sha3_256(":".join(parts).encode()).digest()


class BITPMatcher:
    """
    Module 2.5: Behavioral Information Transfer Protocol matching engine.
    Finds complements for illiquid pairs without lock/mint bridging.

    BITP Flow:
    1. Entity A on Chain A posts intent to Akashic clipboard
    2. TRION searches for complement(intent_A) across ALL chains
    3. If found → proceed to PASTE
    4. If not found → intent becomes BLO stored in Akashic Index
    5. PASTE: TRION pastes complementary commitment to both chains
    6. Both native transfers execute — no bridge, no wrapped token
    """

    def find_complement(
        self,
        intent_a: BITPIntent,
        candidate_intents: List[BITPIntent],
        price_tolerance: float = 0.02,
        current_time: Optional[float] = None,
    ) -> Optional[BITPIntent]:
        """Find a complement intent (opposite direction, same assets).

        Spec §5.1 MATCH-phase conditions (INV-007,
        docs/security/CANONICAL_INVARIANTS.md):

        * ``candidate.entity_id != intent_a.entity_id`` — a match must be
          between two DISTINCT entities (anti-wash: the same entity
          filling both sides of its own commitment would fabricate a
          behavioral price discovery). Unconditional — mirrors the rust
          reference (rust/src/bitp_matcher.rs find_complement).
        * expiry: when ``current_time`` is supplied, both the seeking
          intent and every candidate must be unexpired
          (``deadline > current_time``); an expired seeking intent
          returns None outright. Mirrors rust, where ``now`` is a
          required argument; here it stays optional so legacy
          pure-function callers (tests with fixed past deadlines) keep
          working — the Akashic clipboard tier enforces expiry
          unconditionally before serving candidates.
        """
        if current_time is not None and current_time >= intent_a.deadline:
            return None  # expired seeking intent cannot be matched
        for candidate in candidate_intents:
            # Spec §5.1: entity == counterparty (self-match) is rejected
            if candidate.entity_id == intent_a.entity_id:
                continue
            # Expired commitments never match
            if current_time is not None and current_time >= candidate.deadline:
                continue
            # Complement: B wants what A has, and has what A wants
            if (candidate.asset_in == intent_a.asset_out and
                candidate.asset_out == intent_a.asset_in and
                candidate.chain_id != intent_a.chain_id):
                # Magnitude must be within price tolerance
                if abs(candidate.magnitude - intent_a.magnitude) / max(intent_a.magnitude, 1) <= price_tolerance:
                    return candidate
        return None

    def execute_paste(
        self,
        intent_a: BITPIntent,
        intent_b: BITPIntent,
    ) -> Dict:
        """Execute the PASTE phase: paste complementary commitments."""
        return {
            "chain_a": intent_a.chain_id,
            "chain_b": intent_b.chain_id,
            "entity_a": intent_a.entity_id.hex(),
            "entity_b": intent_b.entity_id.hex(),
            "asset_x_stays_on_chain_a": True,  # asset never leaves chain A
            "asset_y_stays_on_chain_b": True,  # asset never leaves chain B
            "cross_chain_movement": 0,         # ZERO
            "bridge": "NONE",
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Module 2.6: Netting Engine
# ═══════════════════════════════════════════════════════════════════════════════

class NettingEngine:
    """
    Module 2.6: Finds counterparties with opposite intents simultaneously.
    Pure NETTING routes with zero asset movement.

    Economics: $10K USDC→ETH swap
      - ETH only: $31.00 gas, BTCP_score 0.41
      - ETH anchor → Base execute: $0.98 gas, BTCP_score 0.94
      - NETTING (counterparty found): $0.05 gas, BTCP_score 0.98 ← OPTIMAL
    """

    def find_netting_pair(
        self,
        intent_a: BITPIntent,
        candidates: List[BITPIntent],
        tolerance: float = 0.01,
    ) -> Optional[BITPIntent]:
        """Find exact opposite intent for netting."""
        for c in candidates:
            if (c.asset_in == intent_a.asset_out and
                c.asset_out == intent_a.asset_in and
                c.chain_id == intent_a.chain_id and
                c.entity_id != intent_a.entity_id):
                if abs(c.magnitude - intent_a.magnitude) / max(intent_a.magnitude, 1) <= tolerance:
                    return c
        return None

    def netting_gas_cost(self) -> float:
        """Netting has minimal gas — just state update."""
        return 0.05  # $0.05


# ═══════════════════════════════════════════════════════════════════════════════
# Module 2.7: Intent Aggregator
# ═══════════════════════════════════════════════════════════════════════════════

class IntentAggregator:
    """
    Module 2.7: Intent Aggregation Protocol.
    Pools N≥3 same-direction intents within window W for massive gas savings.

    Economics: 100 users each want $100 ETH→SOL swap
      - Individual: $0.80 gas each = $80 total
      - Aggregated: $0.80 for pool = $0.008 per user (100× cheaper)

    Privacy: Each entity's amount hidden from other participants via ZK proof
    of correct share calculation.
    """

    MIN_INTENTS = 3

    def find_aggregation_pool(
        self,
        intents: List[BITPIntent],
        window_blocks: int = 10,
    ) -> List[BITPIntent]:
        """Find N≥3 same-direction intents within window."""
        if len(intents) < self.MIN_INTENTS:
            return []
        # Group by (asset_in, asset_out, chain_id)
        groups: Dict[Tuple, List[BITPIntent]] = {}
        for intent in intents:
            key = (intent.asset_in, intent.asset_out, intent.chain_id)
            groups.setdefault(key, []).append(intent)
        # Return first group with ≥3 intents
        for group in groups.values():
            if len(group) >= self.MIN_INTENTS:
                return group[:100]  # cap at 100
        return []

    def compute_per_user_gas(self, total_gas: float, num_users: int) -> float:
        """Per-user gas after aggregation — equal split.

        This is the uniform-value special case of the spec formula (all
        participants hold equal value); use compute_per_user_gas_weighted
        for the general case."""
        if num_users <= 0:
            return total_gas
        return total_gas / num_users

    def compute_per_user_gas_weighted(self, total_gas: float, user_value: float, total_value: float) -> float:
        """Per-user gas, VALUE-WEIGHTED per BTCP spec §5.3:

            user_gas = G_total × (value_user / total_value)

        Mirrors rust/src/intent_aggregator.rs compute_per_user_gas_weighted.
        When every participant's value is equal this reduces to the equal
        split above (which is why the 100×-savings claim holds for uniform
        pools)."""
        if total_value <= 0:
            return total_gas
        return total_gas * user_value / total_value


# ═══════════════════════════════════════════════════════════════════════════════
# Module 2.8: OOA Anchor (Observation-Only Anchoring)
# ═══════════════════════════════════════════════════════════════════════════════

class OOAAnchor:
    """
    Module 2.8: Observation-Only Anchoring for non-integrated chains.
    Reads via Channel 6 direct indexing (no permission needed).

    Spec (BTCP Master Spec §5.2):
        OOA_conf(depth) = conf_max × (1 - e^(-k × depth))
        conf_max = 0.85  (approaches but does not reach integrated (1.0))
        k        = 0.001 (growth rate, calibrated)

    OOA_conf < integrated_conf at all depths.
    Θ_OOA(t) = Θ_base(t) × OOA_penalty_factor (higher threshold, harder to emit)
    """

    OOA_PENALTY_FACTOR = 1.5  # 50% higher threshold for OOA chains
    OOA_CONF_MAX = 0.85        # spec constant — asymptote below integrated (1.0)
    OOA_K = 0.001              # spec growth rate

    def compute_ooa_confidence(
        self,
        observation_depth: int,
        integrated_confidence: float = 1.0,
    ) -> float:
        """
        OOA_conf(depth) = conf_max × (1 - e^(-k·depth))   [spec §5.2]

        conf_max = 0.85 per spec: OOA approaches but never reaches integrated
        confidence. If the caller supplies an integrated_confidence below the
        spec asymptote (a low-confidence integrated chain), the lower value
        is respected — OOA can never out-confidence integration.
        """
        if observation_depth <= 0:
            return 0.0
        # Spec asymptote: min(0.85, caller's integrated confidence)
        conf_max = min(self.OOA_CONF_MAX, integrated_confidence)
        factor = 1.0 - math.exp(-self.OOA_K * observation_depth)
        return conf_max * factor

    def compute_ooa_threshold(self, base_threshold: float) -> float:
        """Θ_OOA = Θ_base × penalty_factor."""
        return min(0.99, base_threshold * self.OOA_PENALTY_FACTOR)


# ═══════════════════════════════════════════════════════════════════════════════
# Module 2.9: Shadow Observer
# ═══════════════════════════════════════════════════════════════════════════════

class ShadowObserver:
    """
    Module 2.9: Shadow Observation Protocol for hostile chains.
    Reads effects on OTHER chains to reconstruct hostile chain's behavioral state.

    Shadow Sources:
    - TRANSFER events on integrated chains referencing known hostile-chain addresses
    - ORACLE_UPDATE citing hostile-chain native assets
    - BRIDGE events from/to hostile chain
    - DEX trades of hostile chain native token
    - GOVERNANCE referencing hostile chain protocols

    Each source becomes shadow_source with confidence weight.
    shadow_BH reconstructed from weighted sum.
    """

    def reconstruct_shadow_bh(
        self,
        shadow_sources: List[Dict],
    ) -> Tuple[bytes, float]:
        """Reconstruct shadow BH from weighted sum of shadow sources."""
        if not shadow_sources:
            return b"\x00" * 32, 0.0
        total_weight = sum(s.get("weight", 0.0) for s in shadow_sources)
        if total_weight <= 0:
            return b"\x00" * 32, 0.0
        # Hash all source data together, weighted by confidence
        h = hashlib.sha3_256()
        for src in sorted(shadow_sources, key=lambda s: s.get("weight", 0), reverse=True):
            h.update(src.get("data", b"").encode())
            h.update(str(src.get("weight", 0)).encode())
        confidence = min(1.0, total_weight / 10.0)  # 10+ sources = max confidence
        return h.digest(), confidence


# ═══════════════════════════════════════════════════════════════════════════════
# Module 2.10: State Capsule
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class StateCapsule:
    """
    Module 2.10: Behavioral State Capsule — cross-chain state reads at anchor time.

    Chain B reads from capsule, not from live Chain A.
    Chain boundary does not stop state from flowing.
    """
    price_at_anchor:      float
    balance_X:            float
    governance_snapshot:  bytes
    block_hash_A:         bytes
    staleness_CI_95:      float  # confidence interval on staleness


class StateCapsuleBuilder:
    def build_capsule(
        self,
        price: float,
        balance: float,
        governance: bytes,
        block_hash: bytes,
        staleness: float,
    ) -> StateCapsule:
        return StateCapsule(
            price_at_anchor=price,
            balance_X=balance,
            governance_snapshot=governance,
            block_hash_A=block_hash,
            staleness_CI_95=staleness,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Module 2.11: Failure Classifier
# ═══════════════════════════════════════════════════════════════════════════════

class FailureClassifier:
    """
    Module 2.11: Classifies route failures as EXTERNAL_CAUSE vs ENTITY_CAUSE.

    EXTERNAL_CAUSE indicators:
    - chain_outage(execution_chain) = TRUE at failure time
    - NL(execution_chain) dropped below 0.10 during execution
    - reorg_depth > safe_confirmation_count on anchor chain
    - MF_score spike on execution chain (external attack)

    ENTITY_CAUSE indicators:
    - Entity submitted invalid proof
    - Entity withdrew collateral before BTCP_ESCROW released
    - Entity submitted conflicting intents simultaneously
    - Systematic repeated timeout pattern

    Impact:
    - EXTERNAL_CAUSE: BEO impact = ZERO, entity not penalized
    - ENTITY_CAUSE: graduated penalties
    - AMBIGUOUS: first two = EXTERNAL benefit of doubt; third within 90 days = ENTITY
    """

    def classify(
        self,
        chain_outage: bool,
        nl_dropped_below_0_10: bool,
        reorg_depth_exceeded: bool,
        mf_spike: bool,
        invalid_proof: bool,
        collateral_withdrawn: bool,
        conflicting_intents: bool,
        systematic_timeout: bool,
        prior_ambiguous_count: int = 0,
    ) -> str:
        external_indicators = sum([chain_outage, nl_dropped_below_0_10, reorg_depth_exceeded, mf_spike])
        entity_indicators = sum([invalid_proof, collateral_withdrawn, conflicting_intents, systematic_timeout])

        if entity_indicators >= 2:
            return "ENTITY_CAUSE"
        if external_indicators >= 2:
            return "EXTERNAL_CAUSE"
        if external_indicators >= 1 and entity_indicators == 0:
            return "EXTERNAL_CAUSE"
        if entity_indicators >= 1 and external_indicators == 0:
            return "ENTITY_CAUSE"
        # AMBIGUOUS: first two = EXTERNAL benefit of doubt; third = ENTITY
        if prior_ambiguous_count >= 2:
            return "ENTITY_CAUSE"
        return "EXTERNAL_CAUSE"  # benefit of doubt


# ═══════════════════════════════════════════════════════════════════════════════
# Module 2.12: Genesis Commitment (Rust side — Python equivalent)
# ═══════════════════════════════════════════════════════════════════════════════

class GenesisCommitmentProcessor:
    """
    Module 2.12: Genesis commitment processing.

    Null-State Theorem: Any decentralized routing system without explicit genesis
    mechanism fails at scale with probability 1.

    Genesis Commitments ensure:
        ∀ entity e: ∃ genesis pathway → History(e) can be initialized
        ∀ asset a: ∃ genesis pathway → Liquidity_Ocean(a) can be initialized
    """

    GENESIS_PATHWAYS = ["stake", "signature", "social_proof"]

    def initiate_genesis(
        self,
        entity_id: bytes,
        pathway: str,
        stake_amount: float = 0.0,
    ) -> Dict:
        if pathway not in self.GENESIS_PATHWAYS:
            raise ValueError(f"Invalid pathway: {pathway}")
        return {
            "entity_id": entity_id.hex(),
            "pathway": pathway,
            "stake_amount": stake_amount,
            "conf_genesis": 0.01,  # minimal initial confidence
            "timestamp": time.time(),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Module 2.13: BLO Scheduler
# ═══════════════════════════════════════════════════════════════════════════════

class BLOScheduler:
    """
    Module 2.13: BRT Intent Scheduling — finds optimal execution window.

    OPTIMAL_WINDOW = circadian_low ∩ NL_peak ∩ MEV_valley
    Predicted savings: 78%.
    """

    def find_optimal_window(
        self,
        circadian_low_hours: List[int],    # hours of day with low gas
        nl_peak_hours: List[int],          # hours with high NL
        mev_valley_hours: List[int],       # hours with low MEV
    ) -> List[int]:
        """Find hours that are in all three windows simultaneously."""
        return sorted(set(circadian_low_hours) & set(nl_peak_hours) & set(mev_valley_hours))


# ═══════════════════════════════════════════════════════════════════════════════
# Module 2.14: Behavioral State Channel
# ═══════════════════════════════════════════════════════════════════════════════

class BehavioralStateChannel:
    """
    Module 2.14: Behavioral State Channels for high-frequency interaction.

    Lifecycle:
    1. OPEN: single BTCP_proof anchors channel, both sides lock collateral
    2. OPERATE: unlimited interactions in BIBL space — no on-chain cost per interaction
    3. CLOSE: final state submitted to both chains

    Economics: 50 interactions → 2 on-chain transactions. 50× cheaper per interaction.
    """

    def __init__(self):
        self._channels: Dict[str, Dict] = {}

    def open_channel(
        self, channel_id: str, entity_a: bytes, entity_b: bytes,
        collateral_a: float, collateral_b: float, proof: bytes,
    ) -> Dict:
        self._channels[channel_id] = {
            "entity_a": entity_a, "entity_b": entity_b,
            "collateral_a": collateral_a, "collateral_b": collateral_b,
            "proof": proof, "state": "OPEN",
            "interaction_count": 0,
            "opened_at": time.time(),
        }
        return self._channels[channel_id]

    def operate(self, channel_id: str, interaction: Dict) -> bool:
        ch = self._channels.get(channel_id)
        if not ch or ch["state"] != "OPEN":
            return False
        ch["interaction_count"] += 1
        return True

    def close_channel(self, channel_id: str, final_state: Dict) -> bool:
        ch = self._channels.get(channel_id)
        if not ch or ch["state"] != "OPEN":
            return False
        ch["state"] = "CLOSED"
        ch["final_state"] = final_state
        ch["closed_at"] = time.time()
        return True


# ═══════════════════════════════════════════════════════════════════════════════
# Module 2.15: Finality Normalizer
# ═══════════════════════════════════════════════════════════════════════════════

class FinalityNormalizer:
    """
    Module 2.15: Finality Normalization Layer.
    BTCP_ESCROW waits max(A_finality, B_finality), not sum.

    BIBL operates in parallel with block production, not sequentially after.
    - Effective latency = max(A finality, B finality)
    - ETH→Base: max(12s, 2s) = 12 seconds (not 14s)
    """

    def effective_latency(self, a_finality_sec: float, b_finality_sec: float) -> float:
        """max(A, B), not sum."""
        return max(a_finality_sec, b_finality_sec)


# ═══════════════════════════════════════════════════════════════════════════════
# Module 2.16: Version Handler
# ═══════════════════════════════════════════════════════════════════════════════

class VersionHandler:
    """
    Module 2.16: Semver compatibility, min_verifier_version routing,
    adapter version bonus incentives.

    Compatibility Rules:
    - route_valid = verifier_version >= min_verifier_version
    - Major (v1→v2): breaking, 6-month transition
    - Minor (v2.0→v2.1): non-breaking, new features optional
    - Patch: always backward compatible
    - ADAPTER_VERSION_BONUS: routing preference for latest adapters
    """

    ADAPTER_VERSION_BONUS = 0.03  # +3% bonus to BTCP_score for latest version

    def parse_semver(self, version: str) -> Tuple[int, int, int]:
        parts = version.split(".")
        return (int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)

    def is_compatible(self, verifier_version: str, min_version: str) -> bool:
        v = self.parse_semver(verifier_version)
        m = self.parse_semver(min_version)
        return v >= m

    def is_breaking_change(self, old_version: str, new_version: str) -> bool:
        """Major version change = breaking."""
        return self.parse_semver(new_version)[0] > self.parse_semver(old_version)[0]


# ═══════════════════════════════════════════════════════════════════════════════
# Module 2.17: Validator Fee Calculator
# ═══════════════════════════════════════════════════════════════════════════════

class ValidatorFeeCalculator:
    """
    Module 2.17: Validator fee structure per Fix 4.

    total_reward(validator_j, period_T) =
          BASE_SIGNAL_REWARD(j, T)
        + COVERAGE_BONUS(j, T)
        + BTCP_ROUTE_REWARD(j, T)
        - COVERAGE_COST_OFFSET(j, T)

    COVERAGE_BONUS(j, T) = Σ_chains [
        BASE_RATE × rarity_factor(c) × volume_factor(c,T) × uptime_factor(j,c,T)
    ]

    rarity_factor(c) = 1 / (validators_covering_c / total_validators)

    BTCP_ROUTE_REWARD: split 60% anchor chain validators / 40% execution chain validators
    """

    BASE_RATE = 100.0  # base reward rate per chain
    BTCP_ROUTE_SPLIT_ANCHOR = 0.60
    BTCP_ROUTE_SPLIT_EXEC = 0.40

    def compute_rarity_factor(
        self, validators_covering_chain: int, total_validators: int,
    ) -> float:
        """rarity_factor = 1 / (validators_covering / total_validators)."""
        if validators_covering_chain <= 0:
            return float('inf')
        return total_validators / validators_covering_chain

    def compute_coverage_bonus(
        self,
        chains_covered: List[int],
        validators_per_chain: Dict[int, int],
        total_validators: int,
        volume_per_chain: Dict[int, float],
        uptime_per_chain: Dict[int, float],
    ) -> float:
        """COVERAGE_BONUS = Σ_chains [BASE_RATE × rarity × volume × uptime]."""
        bonus = 0.0
        for c in chains_covered:
            rarity = self.compute_rarity_factor(validators_per_chain.get(c, 1), total_validators)
            volume = volume_per_chain.get(c, 0.0)
            uptime = uptime_per_chain.get(c, 0.0)
            bonus += self.BASE_RATE * rarity * volume * uptime
        return bonus

    def compute_btcp_route_reward(
        self, total_route_reward: float, is_anchor: bool,
    ) -> float:
        """Split: 60% anchor / 40% execution."""
        if is_anchor:
            return total_route_reward * self.BTCP_ROUTE_SPLIT_ANCHOR
        return total_route_reward * self.BTCP_ROUTE_SPLIT_EXEC


# ═══════════════════════════════════════════════════════════════════════════════
# Module 2.18: Sybil Resistance
# ═══════════════════════════════════════════════════════════════════════════════

class SybilResistance:
    """
    Module 2.18: Sponsored Genesis sybil resistance enforcement.
    All 5 layers:
    1. Logarithmic sponsorship cap
    2. Reputation decay scrutiny
    3. BEO vector similarity detection (>0.85 = alert)
    4. Quadratic temporal spacing
    5. Sponsor network graph analysis
    """

    BASE_SPONSOR_CAP = 10
    MIN_SPACING_BASE_DAYS = 7
    SIMILARITY_THRESHOLD = 0.85

    def layer1_max_sponsored(self, d: float, d_min: float) -> int:
        """MAX_SPONSORED = floor(log2(D/D_min) × BASE_SPONSOR_CAP)."""
        if d <= d_min or d_min <= 0:
            return 0
        return int(math.log2(d / d_min) * self.BASE_SPONSOR_CAP)

    def layer2_scrutiny_multiplier(self, n_sponsored: int) -> float:
        """scrutiny_multiplier = 1 + (n × 0.2)."""
        return 1.0 + n_sponsored * 0.2

    def layer3_is_sockpuppet(self, cosine_similarity: float) -> bool:
        """cosine_similarity > 0.85 → SOCKPUPPET_ALERT."""
        return cosine_similarity > self.SIMILARITY_THRESHOLD

    def layer4_min_spacing_days(self, n_sponsored: int) -> float:
        """MIN_SPACING(n) = BASE_SPACING × n²."""
        return self.MIN_SPACING_BASE_DAYS * (n_sponsored ** 2)

    def layer5_detect_star_pattern(
        self, sponsor_graph: Dict[bytes, List[bytes]],
    ) -> List[bytes]:
        """
        Star pattern: one sponsor sponsoring many unrelated entities.
        Returns list of suspicious sponsor IDs.
        """
        suspicious = []
        for sponsor, sponsored in sponsor_graph.items():
            if len(sponsored) > 20:  # star pattern threshold
                suspicious.append(sponsor)
        return suspicious


# ── Self-test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== BTCP Modules 2.4-2.18 Self-test ===\n")

    # Module 2.4: Proof Builder
    pb = BTCPProofBuilder()
    # 3 distinct signers with well-formed 65-byte signatures — verify_proof
    # enforces the rust-parity structural contract (≥3 signers, distinct,
    # 65B shape); the old single-signer fixture predated that check and
    # failed the self-test.
    proof = pb.build_proof(
        anchor_bh=b"\x01" * 32, intent_hash=b"\x02" * 32,
        route_type=1, certification_block=18000000, value_usd=5000.0,
        validator_signatures=[
            ValidatorSignature(b"\x03" * 32, b"\x04" * 65, 0.8),
            ValidatorSignature(b"\x13" * 32, b"\x14" * 65, 0.7),
            ValidatorSignature(b"\x23" * 32, b"\x24" * 65, 0.6),
        ],
        diversity_weights=[0.8, 0.7, 0.6], hhi=1500.0,
        coherence=0.85, threshold=0.55,
    )
    assert pb.verify_proof(proof, current_block=18000001)
    assert not pb.verify_proof(proof, current_block=18000001 + 100000)  # expired
    print(f"✓ Module 2.4: BTCPProofBuilder")

    # FIX-2: BTCPProofBuilder consensus wiring (AUDIT-1 gap #5)
    try:
        from core.spiritual.consensus import build_demo_validators
        demo_validators = build_demo_validators(12)
        proof2, attestation = pb.build_proof_from_validators(
            anchor_bh=b"\x05" * 32, intent_hash=b"\x06" * 32,
            route_type=1, certification_block=18000000, value_usd=5000.0,
            validators=demo_validators,
            validator_signatures=[
                ValidatorSignature(b"\x07" * 32, b"\x08" * 65, 0.8)
            ],
        )
        assert isinstance(attestation, ConsensusAttestation)
        assert len(attestation.diversity_certificate) == 12
        assert attestation.hhi > 0
        assert attestation.sigma >= 0.0
        assert pb.verify_proof(proof2, current_block=18000001) or not attestation.safety_holds
        print(f"✓ Module 2.4 (FIX-2): BTCPProofBuilder.build_proof_from_validators — Σ(t)={attestation.sigma:.4f}, HHI={attestation.hhi:.0f} [{attestation.hhi_health}]")
    except ImportError:
        print(f"✓ Module 2.4 (FIX-2): consensus module not installed — skipping wiring test")

    # Module 2.5: BITP Matcher
    bm = BITPMatcher()
    intent_a = BITPIntent(b"\x01"*32, b"\xAA"*32, b"\xBB"*32, 1000.0, 1, 1000)
    intent_b = BITPIntent(b"\x02"*32, b"\xBB"*32, b"\xAA"*32, 1000.0, 137, 1000)
    match = bm.find_complement(intent_a, [intent_b])
    assert match is not None
    paste_result = bm.execute_paste(intent_a, intent_b)
    assert paste_result["cross_chain_movement"] == 0
    print(f"✓ Module 2.5: BITPMatcher")

    # Module 2.6: Netting Engine
    ne = NettingEngine()
    intent_c = BITPIntent(b"\x03"*32, b"\xBB"*32, b"\xAA"*32, 1000.0, 1, 1000)
    pair = ne.find_netting_pair(intent_a, [intent_c])
    assert pair is not None
    assert ne.netting_gas_cost() == 0.05
    print(f"✓ Module 2.6: NettingEngine")

    # Module 2.7: Intent Aggregator
    ia = IntentAggregator()
    intents = [
        BITPIntent(b"\x01"*32, b"\xAA"*32, b"\xBB"*32, 100.0, 1, 1000),
        BITPIntent(b"\x02"*32, b"\xAA"*32, b"\xBB"*32, 200.0, 1, 1000),
        BITPIntent(b"\x03"*32, b"\xAA"*32, b"\xBB"*32, 150.0, 1, 1000),
    ]
    pool = ia.find_aggregation_pool(intents)
    assert len(pool) >= 3
    assert ia.compute_per_user_gas(0.80, 100) == 0.008
    assert abs(ia.compute_per_user_gas_weighted(0.80, 1.0, 100.0) - 0.008) < 1e-12
    assert abs(ia.compute_per_user_gas_weighted(0.80, 30.0, 100.0) - 0.24) < 1e-9
    print(f"✓ Module 2.7: IntentAggregator")

    # Module 2.8: OOA Anchor
    ooa = OOAAnchor()
    conf = ooa.compute_ooa_confidence(500, 0.85)
    assert 0 < conf < 0.85
    assert ooa.compute_ooa_threshold(0.55) > 0.55
    print(f"✓ Module 2.8: OOAAnchor")

    # Module 2.9: Shadow Observer
    so = ShadowObserver()
    sources = [
        {"data": "transfer1", "weight": 0.8},
        {"data": "oracle1", "weight": 0.6},
        {"data": "bridge1", "weight": 0.5},
    ]
    bh, conf = so.reconstruct_shadow_bh(sources)
    assert len(bh) == 32
    assert conf > 0
    print(f"✓ Module 2.9: ShadowObserver")

    # Module 2.10: State Capsule
    scb = StateCapsuleBuilder()
    cap = scb.build_capsule(2000.0, 5.0, b"\x01"*32, b"\x02"*32, 0.95)
    assert cap.price_at_anchor == 2000.0
    print(f"✓ Module 2.10: StateCapsuleBuilder")

    # Module 2.11: Failure Classifier
    fc = FailureClassifier()
    assert fc.classify(True, True, False, False, False, False, False, False) == "EXTERNAL_CAUSE"
    assert fc.classify(False, False, False, False, True, True, False, False) == "ENTITY_CAUSE"
    assert fc.classify(False, False, False, False, False, False, False, False) == "EXTERNAL_CAUSE"
    print(f"✓ Module 2.11: FailureClassifier")

    # Module 2.12: Genesis Commitment
    gc = GenesisCommitmentProcessor()
    result = gc.initiate_genesis(b"\x01"*32, "stake", 1000.0)
    assert result["conf_genesis"] == 0.01
    print(f"✓ Module 2.12: GenesisCommitmentProcessor")

    # Module 2.13: BLO Scheduler
    bs = BLOScheduler()
    window = bs.find_optimal_window([2, 3, 4], [3, 4, 5], [4, 5, 6])
    assert window == [4]
    print(f"✓ Module 2.13: BLOScheduler")

    # Module 2.14: State Channel
    bsc = BehavioralStateChannel()
    bsc.open_channel("ch1", b"\x01"*32, b"\x02"*32, 1000.0, 1000.0, b"\x03"*32)
    for _ in range(50):
        bsc.operate("ch1", {"action": "swap"})
    assert bsc.close_channel("ch1", {"final_balance_a": 1100.0})
    assert bsc._channels["ch1"]["interaction_count"] == 50
    print(f"✓ Module 2.14: BehavioralStateChannel (50× cheaper)")

    # Module 2.15: Finality Normalizer
    fn = FinalityNormalizer()
    assert fn.effective_latency(12.0, 2.0) == 12.0  # max, not sum (14)
    print(f"✓ Module 2.15: FinalityNormalizer (max not sum)")

    # Module 2.16: Version Handler
    vh = VersionHandler()
    assert vh.is_compatible("2.1.0", "2.0.0")
    assert not vh.is_compatible("1.5.0", "2.0.0")
    assert vh.is_breaking_change("1.0.0", "2.0.0")
    assert not vh.is_breaking_change("2.0.0", "2.1.0")
    print(f"✓ Module 2.16: VersionHandler")

    # Module 2.17: Validator Fee Calculator
    vfc = ValidatorFeeCalculator()
    assert vfc.compute_rarity_factor(5, 100) == 20.0  # 5% coverage → 20x rarity
    bonus = vfc.compute_coverage_bonus(
        chains_covered=[1, 137],
        validators_per_chain={1: 50, 137: 10},
        total_validators=100,
        volume_per_chain={1: 0.8, 137: 0.5},
        uptime_per_chain={1: 0.99, 137: 0.95},
    )
    assert bonus > 0
    assert vfc.compute_btcp_route_reward(100.0, is_anchor=True) == 60.0
    assert vfc.compute_btcp_route_reward(100.0, is_anchor=False) == 40.0
    print(f"✓ Module 2.17: ValidatorFeeCalculator")

    # Module 2.18: Sybil Resistance
    sr = SybilResistance()
    assert sr.layer1_max_sponsored(10000, 100) > 0
    assert sr.layer2_scrutiny_multiplier(5) == 2.0
    assert sr.layer3_is_sockpuppet(0.90)
    assert not sr.layer3_is_sockpuppet(0.80)
    assert sr.layer4_min_spacing_days(3) == 63  # 7 × 9
    suspicious = sr.layer5_detect_star_pattern({b"\x01"*32: [b"\x02"*32] * 25})
    assert len(suspicious) == 1
    print(f"✓ Module 2.18: SybilResistance (5 layers)")

    print("\nPHASE 2.3-2.18 PASS — All BTCP modules implemented")
