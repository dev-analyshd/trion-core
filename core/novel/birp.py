"""
TRION Protocol — §16: BIRP — Behavioral Identity Recovery Protocol
===================================================================
Whitepaper Section 16 specifies BIRP as a five-phase behavioral identity
recovery protocol.  When an entity undergoes a sudden behavioral shift
(compromise, key handover, entity resurrection after dormancy) BIRP provides
a cryptographically provable path to recover or deny behavioral identity
continuity without disrupting the rest of the oracle.

Five mandatory phases (whitepaper §16):
  Phase 1 — DNA Verification       : dual-strand sense/antisense integrity check
  Phase 2 — Behavioral Proof       : Merkle proof of historical behavioral claims
  Phase 3 — Temporal Cluster       : FAISS nearest-neighbour cluster alignment
  Phase 4 — Conscious Layer        : validator quorum review (K-plane vote)
  Phase 5 — Quarantine Wait        : mandatory 7-day (604800 s) cooling period

State machine:
  UNSTARTED → PHASE_1_DNA → PHASE_2_BEHAVIORAL → PHASE_3_TEMPORAL
            → PHASE_4_CONSCIOUS → PHASE_5_QUARANTINE → RESOLVED

A recovery request can be APPROVED (identity continuity confirmed) or
REJECTED at any phase.  Rejection is permanent for that request ID; the
entity may open a new request after a 30-day cooldown.

This file also retains the signal relay wrapper (BIRPMessage) that was the
previous sole content of this module, now under the `relay` sub-namespace.

Author: TRION Protocol — Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


# ═══════════════════════════════════════════════════════════════════════════════
# § 16.1  Constants
# ═══════════════════════════════════════════════════════════════════════════════

QUARANTINE_SECONDS: int = 7 * 24 * 3600   # 7 days — mandatory §16 Phase 5
REJECTION_COOLDOWN: int = 30 * 24 * 3600  # 30 days before a new request

# Phase 4 quorum: fraction of registered validators that must vote APPROVE
CONSCIOUS_QUORUM_FRACTION: float = 0.67   # 2/3 majority

# Phase 3 temporal cluster: maximum allowed cosine distance from the entity's
# own archetype cluster (FAISS nearest-neighbour in BEO vector space)
TEMPORAL_CLUSTER_MAX_DISTANCE: float = 0.30

# ── § 16.1a  DNA_Code user-defined secret rotation ────────────────────────────
# Whitepaper §16: "DNA_Code: User-defined secret sequence with time-based
# rotation."  Each entity may register a personal DNA_Code — a byte sequence
# they alone know — that is mixed into the dual-strand hash during Phase 1
# DNA verification.  The code rotates on a fixed schedule (default 90 days)
# to bound the impact of long-term code compromise.
#
# Rotation is hash-chained: code_epoch_N = SHA3-256(code_epoch_{N-1} || N)
# The current epoch is computed from the entity's registration timestamp.
DNA_CODE_ROTATION_SECONDS: int = 90 * 24 * 3600  # 90 days per epoch
DNA_CODE_MIN_BYTES: int = 16                       # minimum 128-bit secret
DNA_CODE_MAX_BYTES: int = 256                      # maximum 2048-bit secret

# Phase 2 behavioral proof: minimum fraction of historical claims that the
# Merkle proof must cover for the proof to be considered adequate
BEHAVIORAL_PROOF_MIN_COVERAGE: float = 0.70


# ═══════════════════════════════════════════════════════════════════════════════
# § 16.2  State machine
# ═══════════════════════════════════════════════════════════════════════════════

class BIRPPhase(str, Enum):
    UNSTARTED          = "UNSTARTED"
    PHASE_1_DNA        = "PHASE_1_DNA"
    PHASE_2_BEHAVIORAL = "PHASE_2_BEHAVIORAL"
    PHASE_3_TEMPORAL   = "PHASE_3_TEMPORAL"
    PHASE_4_CONSCIOUS  = "PHASE_4_CONSCIOUS"
    PHASE_5_QUARANTINE = "PHASE_5_QUARANTINE"
    RESOLVED           = "RESOLVED"
    REJECTED           = "REJECTED"


class BIRPOutcome(str, Enum):
    PENDING  = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass
class BIRPPhaseResult:
    phase:     BIRPPhase
    passed:    bool
    score:     float          # 0–1 confidence
    evidence:  dict
    timestamp: float = field(default_factory=time.time)
    notes:     str = ""


@dataclass
class BIRPRequest:
    """A single identity recovery request for one entity."""
    request_id:   str
    entity_id:    str
    reason:       str          # e.g. "key_compromise", "dormancy_resurrection", "fork"
    initiated_at: float
    phase:        BIRPPhase = BIRPPhase.UNSTARTED
    outcome:      BIRPOutcome = BIRPOutcome.PENDING
    phase_results: List[BIRPPhaseResult] = field(default_factory=list)
    quarantine_ends_at: Optional[float] = None
    resolved_at:  Optional[float] = None
    rejection_reason: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════════
# § 16.3  Phase 1 — DNA Verification
# ═══════════════════════════════════════════════════════════════════════════════

def _complement(data: bytes) -> bytes:
    return bytes(b ^ 0xFF for b in data)


def _hash_dna(payload: bytes):
    """Whitepaper L0.1 dual-strand construction."""
    sense    = hashlib.sha3_256(payload + b'\x00').digest()
    sha3ff   = hashlib.sha3_256(payload + b'\xFF').digest()
    antisense = bytes(a ^ b for a, b in zip(sha3ff, _complement(sense)))
    return sense, antisense


def _verify_xor_invariant(sense: bytes, antisense: bytes, payload: bytes) -> bool:
    """
    sense XOR antisense == NOT(SHA3-256(payload || 0xFF))
    This invariant proves both strands were derived from the same payload.
    """
    sha3ff    = hashlib.sha3_256(payload + b'\xFF').digest()
    expected  = _complement(sha3ff)
    actual    = bytes(a ^ b for a, b in zip(sense, antisense))
    return actual == expected


# ═══════════════════════════════════════════════════════════════════════════════
# § 16.2a  DNA_Code — User-Defined Secret with Time-Based Rotation
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class DNACodeRegistration:
    """An entity's registered DNA_Code secret."""
    entity_id:        str
    # SHA3-256(current-epoch code) — commit_0 = SHA3-256(initial_code) at
    # registration, then advanced in lockstep with the rotation chain by
    # verify_dna_code() (commit_n = SHA3-256(code_n)). We never store the
    # raw code at any epoch.
    code_commitment:  bytes
    registered_at:    float       # unix timestamp of registration
    current_epoch:    int         # epoch number (0 at registration)
    last_rotated_at:  float       # timestamp of last rotation

    def to_dict(self) -> dict:
        return {
            "entity_id":       self.entity_id,
            "code_commitment": self.code_commitment.hex(),
            "registered_at":   self.registered_at,
            "current_epoch":   self.current_epoch,
            "last_rotated_at": self.last_rotated_at,
        }


def _dna_code_epoch(registered_at: float, now: float) -> int:
    """Compute the current DNA_Code epoch number since registration."""
    if now <= registered_at:
        return 0
    return int((now - registered_at) // DNA_CODE_ROTATION_SECONDS)


def _rotate_dna_code(prev_code: bytes, epoch: int) -> bytes:
    """
    Hash-chain rotation: code_epoch_N = SHA3-256(code_epoch_{N-1} || N).

    This allows entities to derive their current code from the initial secret
    without storing every intermediate value.  An attacker who compromises
    the current code cannot recover prior codes (one-way hash).
    """
    current = prev_code
    for n in range(1, epoch + 1):
        current = hashlib.sha3_256(current + n.to_bytes(8, "big")).digest()
    return current


def register_dna_code(entity_id: str, initial_code: bytes, now: float) -> DNACodeRegistration:
    """
    Register a new DNA_Code for an entity.

    The initial code is NEVER stored in plaintext — only its SHA3-256
    commitment is persisted.  The entity must retain the original code
    (or be able to re-derive it) to use it during BIRP recovery.

    Args:
        entity_id:     canonical entity identifier
        initial_code:  user-chosen secret byte sequence
        now:           current unix timestamp

    Returns:
        DNACodeRegistration — store this; the raw code is discarded.

    Raises:
        ValueError if the code length is outside [DNA_CODE_MIN_BYTES,
        DNA_CODE_MAX_BYTES].
    """
    if not (DNA_CODE_MIN_BYTES <= len(initial_code) <= DNA_CODE_MAX_BYTES):
        raise ValueError(
            f"DNA_Code length {len(initial_code)} outside allowed range "
            f"[{DNA_CODE_MIN_BYTES}, {DNA_CODE_MAX_BYTES}]"
        )
    return DNACodeRegistration(
        entity_id=entity_id,
        code_commitment=hashlib.sha3_256(initial_code).digest(),
        registered_at=now,
        current_epoch=0,
        last_rotated_at=now,
    )


def verify_dna_code(
    registration: DNACodeRegistration,
    submitted_code: bytes,
    now: float,
) -> tuple[bool, int, str]:
    """
    Verify a submitted DNA_Code against the stored per-epoch commitment chain.

    Commitment chain (whitepaper §16 time-based rotation):

        code_0   = initial secret                  (never stored)
        code_n   = SHA3-256(code_{n-1} || n)       — one-way hash rotation
        commit_n = SHA3-256(code_n)                — per-epoch commitment

    ``registration.code_commitment`` holds ``commit_m`` for the epoch
    ``m = registration.current_epoch`` that the registration is tracking
    (``commit_0 = SHA3-256(initial_code)`` at registration time). The
    submitted code must therefore be ``code_m`` — the entity's code for
    the registration's tracked epoch (the initial code while the
    registration is at epoch 0; otherwise the code re-derived client-side
    via ``rotate_dna_code_for_epoch``).

    On success the registration is caught up to the wall-clock epoch
    ``n >= m`` by re-deriving the chain forward from the verified code
    (loop) and advancing ``code_commitment`` to ``commit_n``.  Because
    each rotation is a one-way hash, a replayed older code (including the
    initial code) no longer matches the advanced commitment — this
    realises the whitepaper property "stolen DNA_Code at time T is
    permanently invalid at T + interval": an attacker holding ``code_m``
    cannot derive ``code_n``.

    Args:
        registration:   stored DNACodeRegistration (mutated on success to
                        advance the commitment chain; store the updated
                        object)
        submitted_code: the entity's code for the registration's tracked
                        epoch (see above)
        now:            current unix timestamp

    Returns:
        (verified, effective_epoch, message)
    """
    expected_epoch = _dna_code_epoch(registration.registered_at, now)
    stored_epoch = registration.current_epoch

    # The submitted code must match the per-epoch commitment of the
    # registration's tracked epoch: SHA3-256(code_m) == code_commitment.
    submitted_hash = hashlib.sha3_256(submitted_code).digest()
    if submitted_hash != registration.code_commitment:
        return (
            False,
            stored_epoch,
            (
                f"DNA_Code verification FAILED — submitted code does not match "
                f"the epoch-{stored_epoch} commitment (wall-clock epoch "
                f"{expected_epoch})"
            ),
        )

    if expected_epoch <= stored_epoch:
        # Registration is already at (or past — the chain is one-way and
        # cannot be rewound) the wall-clock epoch: plain epoch check.
        if stored_epoch == 0:
            return True, 0, "DNA_Code verified at epoch 0 (no rotation yet)"
        return True, stored_epoch, f"DNA_Code verified at epoch {stored_epoch}"

    # Catch the registration up to the wall-clock epoch: re-derive the
    # chain forward from the verified code
    #   code_j = SHA3-256(code_{j-1} || j)
    # and advance the stored commitment in lockstep
    #   commit_n = SHA3-256(code_n).
    current_code = submitted_code
    for j in range(stored_epoch + 1, expected_epoch + 1):
        current_code = hashlib.sha3_256(current_code + j.to_bytes(8, "big")).digest()
    registration.code_commitment = hashlib.sha3_256(current_code).digest()
    registration.current_epoch = expected_epoch
    registration.last_rotated_at = (
        registration.registered_at + expected_epoch * DNA_CODE_ROTATION_SECONDS
    )
    return (
        True,
        expected_epoch,
        (
            f"DNA_Code verified at epoch {stored_epoch}; commitment chain "
            f"advanced to epoch {expected_epoch}"
        ),
    )


def rotate_dna_code_for_epoch(initial_code: bytes, registered_at: float, now: float) -> bytes:
    """
    Client-side helper: derive the current-epoch DNA_Code from the initial
    secret.

    The entity keeps the initial_code in secure client-side storage (HSM,
    password manager, hardware wallet, etc.) and calls this function to
    compute the current epoch's code before submitting it for BIRP
    verification.
    """
    epoch = _dna_code_epoch(registered_at, now)
    return _rotate_dna_code(initial_code, epoch)


def phase1_dna_verification(
    entity_id: str,
    sense_hex: str,
    antisense_hex: str,
    canonical_payload_hex: str,
    dna_code_registration: Optional[DNACodeRegistration] = None,
    submitted_dna_code: Optional[bytes] = None,
    now: Optional[float] = None,
) -> BIRPPhaseResult:
    """
    Phase 1: Verify that the entity's stored dual-strand genomic key is
    internally consistent via the XOR-complement invariant.

    If a DNA_Code registration is provided, the submitted DNA_Code is
    also verified against the stored commitment (whitepaper §16
    "user-defined secret sequence with time-based rotation").

    The submitter must provide:
      - sense_hex              : current genomic key sense strand (hex)
      - antisense_hex          : current genomic key antisense strand (hex)
      - canonical_payload_hex  : the payload from which the key was derived

    Pass criteria: XOR invariant holds AND strand lengths are correct (32 bytes each).
    If a DNA_Code registration is supplied, the submitted DNA_Code must also
    verify against the stored commitment (with time-based rotation applied).
    """
    try:
        sense     = bytes.fromhex(sense_hex.removeprefix("0x"))
        antisense = bytes.fromhex(antisense_hex.removeprefix("0x"))
        payload   = bytes.fromhex(canonical_payload_hex.removeprefix("0x"))
    except (ValueError, AttributeError) as exc:
        return BIRPPhaseResult(
            phase=BIRPPhase.PHASE_1_DNA, passed=False, score=0.0,
            evidence={"error": str(exc)},
            notes="Hex decoding failed — invalid strand submission",
        )

    length_ok = len(sense) == 32 and len(antisense) == 32
    non_zero  = sense != bytes(32) and antisense != bytes(32)
    xor_ok    = _verify_xor_invariant(sense, antisense, payload) if length_ok else False

    # Re-derive expected strands from payload to confirm match
    exp_sense, exp_anti = _hash_dna(payload)
    sense_match   = exp_sense   == sense
    antisense_match = exp_anti  == antisense

    # ── DNA_Code user-defined secret verification (whitepaper §16) ──────────
    dna_code_ok = True
    dna_code_epoch = 0
    dna_code_msg = "no DNA_Code registration supplied — secret verification skipped"
    if dna_code_registration is not None:
        if submitted_dna_code is None:
            dna_code_ok = False
            dna_code_msg = "DNA_Code registration present but no code submitted"
        else:
            now_val = now if now is not None else time.time()
            dna_code_ok, dna_code_epoch, dna_code_msg = verify_dna_code(
                dna_code_registration, submitted_dna_code, now_val,
            )

    passed = (
        length_ok and non_zero and xor_ok
        and sense_match and antisense_match
        and dna_code_ok
    )
    checks = [length_ok, non_zero, xor_ok, sense_match, antisense_match]
    if dna_code_registration is not None:
        checks.append(dna_code_ok)
    score = sum(checks) / max(len(checks), 1)

    evidence = {
        "length_ok":       length_ok,
        "non_zero":        non_zero,
        "xor_invariant":   xor_ok,
        "sense_match":     sense_match,
        "antisense_match": antisense_match,
    }
    if dna_code_registration is not None:
        evidence["dna_code_verified"] = dna_code_ok
        evidence["dna_code_epoch"]    = dna_code_epoch
        evidence["dna_code_message"]  = dna_code_msg

    return BIRPPhaseResult(
        phase=BIRPPhase.PHASE_1_DNA,
        passed=passed,
        score=score,
        evidence=evidence,
        notes=(
            "DNA verification PASSED — strands cryptographically consistent"
            + (" and DNA_Code verified" if dna_code_registration is not None and dna_code_ok else "")
            if passed else
            "DNA verification FAILED — genomic key integrity compromised"
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# § 16.4  Phase 2 — Behavioral Proof
# ═══════════════════════════════════════════════════════════════════════════════

def _merkle_root(leaves: List[bytes]) -> bytes:
    """Simple binary SHA3-256 Merkle tree."""
    if not leaves:
        return b'\x00' * 32
    layer = [hashlib.sha3_256(leaf).digest() for leaf in leaves]
    while len(layer) > 1:
        if len(layer) % 2 == 1:
            layer.append(layer[-1])
        layer = [
            hashlib.sha3_256(layer[i] + layer[i + 1]).digest()
            for i in range(0, len(layer), 2)
        ]
    return layer[0]


def phase2_behavioral_proof(
    entity_id: str,
    claimed_bh_hashes: List[str],   # hex BH sense hashes the entity claims
    proof_leaves: List[str],         # hex BH hashes that can be verified on-chain / in ledger
    ledger_merkle_root: str,         # expected Merkle root from the BH ledger
) -> BIRPPhaseResult:
    """
    Phase 2: Verify that the entity has a genuine behavioral history by
    checking a Merkle proof over a subset of claimed Behavioral Hash records.

    The submitter provides a list of BH hashes they claim to own; the verifier
    checks that at least BEHAVIORAL_PROOF_MIN_COVERAGE fraction of those claims
    are provable via the ledger Merkle root.
    """
    if not claimed_bh_hashes:
        return BIRPPhaseResult(
            phase=BIRPPhase.PHASE_2_BEHAVIORAL, passed=False, score=0.0,
            evidence={"error": "No behavioral claims submitted"},
            notes="Phase 2 FAILED — zero behavioral claims provided",
        )

    try:
        proof_bytes = [bytes.fromhex(h.removeprefix("0x")) for h in proof_leaves]
        claimed_set = {h.lower().removeprefix("0x") for h in claimed_bh_hashes}
        proof_set   = {h.lower().removeprefix("0x") for h in proof_leaves}
    except ValueError as exc:
        return BIRPPhaseResult(
            phase=BIRPPhase.PHASE_2_BEHAVIORAL, passed=False, score=0.0,
            evidence={"error": str(exc)},
            notes="Phase 2 FAILED — invalid hex in behavioral proof",
        )

    # Compute coverage: fraction of claims backed by proof leaves
    covered    = claimed_set & proof_set
    coverage   = len(covered) / max(len(claimed_set), 1)

    # Verify Merkle root
    computed_root = _merkle_root(proof_bytes).hex()
    root_ok       = computed_root == ledger_merkle_root.lower().removeprefix("0x")

    passed = coverage >= BEHAVIORAL_PROOF_MIN_COVERAGE and root_ok
    score  = coverage * (1.0 if root_ok else 0.5)

    return BIRPPhaseResult(
        phase=BIRPPhase.PHASE_2_BEHAVIORAL,
        passed=passed,
        score=min(1.0, score),
        evidence={
            "claimed_count":   len(claimed_bh_hashes),
            "proof_count":     len(proof_leaves),
            "covered_count":   len(covered),
            "coverage":        round(coverage, 4),
            "min_coverage":    BEHAVIORAL_PROOF_MIN_COVERAGE,
            "merkle_root_ok":  root_ok,
            "computed_root":   computed_root[:16] + "...",
        },
        notes=(
            f"Behavioral proof PASSED — {coverage:.1%} coverage, Merkle root verified"
            if passed else
            f"Behavioral proof FAILED — coverage={coverage:.1%} (need {BEHAVIORAL_PROOF_MIN_COVERAGE:.0%}), "
            f"root_ok={root_ok}"
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# § 16.5  Phase 3 — Temporal Cluster
# ═══════════════════════════════════════════════════════════════════════════════

def phase3_temporal_cluster(
    entity_id: str,
    faiss_distance: float,          # cosine distance from entity's own archetype cluster
    cluster_archetype_id: str,      # FAISS archetype the entity belongs to
    historical_cluster_id: str,     # archetype the entity was assigned to historically
    temporal_gap_blocks: int,       # blocks between last known activity and recovery request
    max_gap_blocks: int = 100_000,  # maximum acceptable gap before temporal coherence breaks
) -> BIRPPhaseResult:
    """
    Phase 3: Verify temporal continuity by checking that the entity's current
    behavioral vector is still within acceptable distance of its historical
    FAISS archetype cluster.

    A large cosine distance indicates the entity is behaving like a different
    archetype — which may indicate identity discontinuity (e.g. key handover).
    A gap > max_gap_blocks without activity weakens temporal coherence.
    """
    distance_ok  = faiss_distance <= TEMPORAL_CLUSTER_MAX_DISTANCE
    cluster_ok   = cluster_archetype_id == historical_cluster_id
    gap_ok       = temporal_gap_blocks <= max_gap_blocks

    # Temporal coherence score: distance contributes most, then cluster, then gap
    dist_score = max(0.0, 1.0 - faiss_distance / TEMPORAL_CLUSTER_MAX_DISTANCE)
    gap_score  = max(0.0, 1.0 - temporal_gap_blocks / max(max_gap_blocks, 1))
    cluster_score = 1.0 if cluster_ok else 0.0

    score  = dist_score * 0.50 + cluster_score * 0.30 + gap_score * 0.20
    passed = distance_ok and gap_ok  # cluster mismatch alone doesn't fail (may be archetype drift)

    return BIRPPhaseResult(
        phase=BIRPPhase.PHASE_3_TEMPORAL,
        passed=passed,
        score=min(1.0, score),
        evidence={
            "faiss_distance":          round(faiss_distance, 4),
            "max_distance":            TEMPORAL_CLUSTER_MAX_DISTANCE,
            "distance_ok":             distance_ok,
            "cluster_archetype_id":    cluster_archetype_id,
            "historical_cluster_id":   historical_cluster_id,
            "cluster_continuity":      cluster_ok,
            "temporal_gap_blocks":     temporal_gap_blocks,
            "max_gap_blocks":          max_gap_blocks,
            "gap_ok":                  gap_ok,
        },
        notes=(
            f"Temporal cluster PASSED — dist={faiss_distance:.3f}, gap={temporal_gap_blocks} blocks"
            if passed else
            f"Temporal cluster FAILED — dist={faiss_distance:.3f} (max {TEMPORAL_CLUSTER_MAX_DISTANCE}), "
            f"gap={temporal_gap_blocks} blocks (max {max_gap_blocks})"
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# § 16.6  Phase 4 — Conscious Layer (Validator Quorum)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ValidatorVote:
    validator_id: str
    approve:      bool
    stake_weight: float           # stake-weighted voting power ∈ (0, 1]
    rationale:    str
    signed_at:    float = field(default_factory=time.time)


def phase4_conscious_layer(
    entity_id: str,
    votes: List[ValidatorVote],
    total_registered_stake: float,
) -> BIRPPhaseResult:
    """
    Phase 4: Validator K-plane conscious review.

    A quorum of 2/3 of stake-weighted validator power must vote APPROVE for
    the identity recovery to pass this phase.  Any single validator with ≥ 34%
    stake can veto the recovery (intentional design — prevents majority collusion
    driving through a fraudulent recovery).

    total_registered_stake: sum of all validator stake weights in the K-plane.
    """
    if not votes:
        return BIRPPhaseResult(
            phase=BIRPPhase.PHASE_4_CONSCIOUS, passed=False, score=0.0,
            evidence={"error": "No validator votes received"},
            notes="Phase 4 FAILED — no validators participated in review",
        )

    approve_stake = sum(v.stake_weight for v in votes if v.approve)
    reject_stake  = sum(v.stake_weight for v in votes if not v.approve)
    total_voted   = approve_stake + reject_stake
    participation = total_voted / max(total_registered_stake, 1e-9)

    # Score: fraction of approving stake over total registered stake
    approve_fraction = approve_stake / max(total_registered_stake, 1e-9)
    passed = approve_fraction >= CONSCIOUS_QUORUM_FRACTION

    return BIRPPhaseResult(
        phase=BIRPPhase.PHASE_4_CONSCIOUS,
        passed=passed,
        score=min(1.0, approve_fraction),
        evidence={
            "vote_count":          len(votes),
            "approve_votes":       sum(1 for v in votes if v.approve),
            "reject_votes":        sum(1 for v in votes if not v.approve),
            "approve_stake":       round(approve_stake, 4),
            "reject_stake":        round(reject_stake, 4),
            "approve_fraction":    round(approve_fraction, 4),
            "quorum_required":     CONSCIOUS_QUORUM_FRACTION,
            "participation":       round(participation, 4),
            "voters": [
                {"id": v.validator_id, "approve": v.approve,
                 "stake": round(v.stake_weight, 4)}
                for v in votes
            ],
        },
        notes=(
            f"Conscious layer PASSED — {approve_fraction:.1%} approve stake (need {CONSCIOUS_QUORUM_FRACTION:.0%})"
            if passed else
            f"Conscious layer FAILED — {approve_fraction:.1%} approve stake (need {CONSCIOUS_QUORUM_FRACTION:.0%})"
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# § 16.7  Phase 5 — Quarantine Wait (mandatory 7 days)
# ═══════════════════════════════════════════════════════════════════════════════

def phase5_quarantine_status(
    quarantine_started_at: float,
    now: Optional[float] = None,
) -> BIRPPhaseResult:
    """
    Phase 5: Mandatory 7-day quarantine period.

    During quarantine the entity's signals are emitted with a RECOVERY_PENDING
    flag.  No acceleration is possible — the 7-day window exists to allow
    human review, regulatory notification, and community challenge.

    Returns passed=True only when the quarantine window has elapsed.
    """
    now      = now if now is not None else time.time()
    elapsed  = now - quarantine_started_at
    remaining = max(0.0, QUARANTINE_SECONDS - elapsed)
    done     = elapsed >= QUARANTINE_SECONDS

    progress = min(1.0, elapsed / QUARANTINE_SECONDS)
    eta_hours = remaining / 3600.0

    return BIRPPhaseResult(
        phase=BIRPPhase.PHASE_5_QUARANTINE,
        passed=done,
        score=progress,
        evidence={
            "quarantine_seconds": QUARANTINE_SECONDS,
            "elapsed_seconds":    round(elapsed, 1),
            "remaining_seconds":  round(remaining, 1),
            "eta_hours":          round(eta_hours, 2),
            "progress_pct":       round(progress * 100, 1),
        },
        notes=(
            "Quarantine COMPLETE — 7-day mandatory wait elapsed. Recovery may be APPROVED."
            if done else
            f"Quarantine IN PROGRESS — {eta_hours:.1f}h remaining ({progress:.0%} elapsed)"
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# § 16.8  BIRP Request Manager
# ═══════════════════════════════════════════════════════════════════════════════

class BIRPManager:
    """
    Manages the lifecycle of Behavioral Identity Recovery Protocol requests.

    Usage:
      mgr = BIRPManager()
      req = mgr.open_request(entity_id, reason)
      mgr.submit_phase1(req.request_id, sense_hex, antisense_hex, payload_hex)
      mgr.submit_phase2(req.request_id, claimed_hashes, proof_leaves, root)
      mgr.submit_phase3(req.request_id, faiss_dist, cluster_id, hist_cluster, gap)
      mgr.submit_phase4(req.request_id, votes, total_stake)
      # After 7 days:
      mgr.check_quarantine(req.request_id)
    """

    def __init__(self):
        self._requests: Dict[str, BIRPRequest] = {}
        # Track last rejection per entity (30-day cooldown)
        self._last_rejection: Dict[str, float] = {}

    def open_request(self, entity_id: str, reason: str) -> BIRPRequest:
        """Open a new BIRP recovery request for an entity."""
        # Enforce 30-day cooldown after rejection
        last_rej = self._last_rejection.get(entity_id)
        if last_rej is not None:
            since = time.time() - last_rej
            if since < REJECTION_COOLDOWN:
                remaining_days = (REJECTION_COOLDOWN - since) / 86400
                raise ValueError(
                    f"Entity {entity_id!r} is in rejection cooldown — "
                    f"{remaining_days:.1f} days remaining before new request allowed"
                )

        req = BIRPRequest(
            request_id=str(uuid.uuid4()),
            entity_id=entity_id,
            reason=reason,
            initiated_at=time.time(),
            phase=BIRPPhase.PHASE_1_DNA,
        )
        self._requests[req.request_id] = req
        return req

    def _get(self, request_id: str) -> BIRPRequest:
        req = self._requests.get(request_id)
        if req is None:
            raise KeyError(f"No BIRP request with id={request_id!r}")
        if req.outcome == BIRPOutcome.REJECTED:
            raise ValueError(f"Request {request_id!r} has already been REJECTED")
        if req.outcome == BIRPOutcome.APPROVED:
            raise ValueError(f"Request {request_id!r} has already been APPROVED")
        return req

    def _reject(self, req: BIRPRequest, reason: str) -> None:
        req.outcome = BIRPOutcome.REJECTED
        req.phase   = BIRPPhase.REJECTED
        req.rejection_reason = reason
        req.resolved_at = time.time()
        self._last_rejection[req.entity_id] = time.time()

    def submit_phase1(
        self, request_id: str,
        sense_hex: str, antisense_hex: str, canonical_payload_hex: str,
    ) -> BIRPPhaseResult:
        req = self._get(request_id)
        result = phase1_dna_verification(
            req.entity_id, sense_hex, antisense_hex, canonical_payload_hex)
        req.phase_results.append(result)
        if not result.passed:
            self._reject(req, f"Phase 1 DNA verification failed: {result.notes}")
        else:
            req.phase = BIRPPhase.PHASE_2_BEHAVIORAL
        return result

    def submit_phase2(
        self, request_id: str,
        claimed_bh_hashes: List[str], proof_leaves: List[str],
        ledger_merkle_root: str,
    ) -> BIRPPhaseResult:
        req = self._get(request_id)
        result = phase2_behavioral_proof(
            req.entity_id, claimed_bh_hashes, proof_leaves, ledger_merkle_root)
        req.phase_results.append(result)
        if not result.passed:
            self._reject(req, f"Phase 2 behavioral proof failed: {result.notes}")
        else:
            req.phase = BIRPPhase.PHASE_3_TEMPORAL
        return result

    def submit_phase3(
        self, request_id: str,
        faiss_distance: float, cluster_archetype_id: str,
        historical_cluster_id: str, temporal_gap_blocks: int,
        max_gap_blocks: int = 100_000,
    ) -> BIRPPhaseResult:
        req = self._get(request_id)
        result = phase3_temporal_cluster(
            req.entity_id, faiss_distance, cluster_archetype_id,
            historical_cluster_id, temporal_gap_blocks, max_gap_blocks)
        req.phase_results.append(result)
        if not result.passed:
            self._reject(req, f"Phase 3 temporal cluster failed: {result.notes}")
        else:
            req.phase = BIRPPhase.PHASE_4_CONSCIOUS
        return result

    def submit_phase4(
        self, request_id: str,
        votes: List[ValidatorVote], total_registered_stake: float,
    ) -> BIRPPhaseResult:
        req = self._get(request_id)
        result = phase4_conscious_layer(req.entity_id, votes, total_registered_stake)
        req.phase_results.append(result)
        if not result.passed:
            self._reject(req, f"Phase 4 conscious layer failed: {result.notes}")
        else:
            req.phase = BIRPPhase.PHASE_5_QUARANTINE
            req.quarantine_ends_at = time.time() + QUARANTINE_SECONDS
        return result

    def check_quarantine(self, request_id: str) -> BIRPPhaseResult:
        req = self._get(request_id)
        result = phase5_quarantine_status(
            quarantine_started_at=req.quarantine_ends_at - QUARANTINE_SECONDS)
        if result.passed and req.phase == BIRPPhase.PHASE_5_QUARANTINE:
            req.phase_results.append(result)
            req.phase = BIRPPhase.RESOLVED
            req.outcome = BIRPOutcome.APPROVED
            req.resolved_at = time.time()
        elif not result.passed and req.phase == BIRPPhase.PHASE_5_QUARANTINE:
            # Don't append — quarantine check can be polled multiple times
            pass
        return result

    def get_request(self, request_id: str) -> Optional[BIRPRequest]:
        return self._requests.get(request_id)

    def status(self, request_id: str) -> dict:
        req = self._requests.get(request_id)
        if req is None:
            return {"error": f"Request {request_id!r} not found"}
        return {
            "request_id":     req.request_id,
            "entity_id":      req.entity_id,
            "reason":         req.reason,
            "current_phase":  req.phase.value,
            "outcome":        req.outcome.value,
            "initiated_at":   req.initiated_at,
            "resolved_at":    req.resolved_at,
            "quarantine_ends_at": req.quarantine_ends_at,
            "rejection_reason":  req.rejection_reason,
            "phases_completed": [
                {
                    "phase":   r.phase.value,
                    "passed":  r.passed,
                    "score":   round(r.score, 4),
                    "notes":   r.notes,
                }
                for r in req.phase_results
            ],
        }


# ═══════════════════════════════════════════════════════════════════════════════
# § 19   Signal Relay Wrapper (retained from prior implementation)
# ═══════════════════════════════════════════════════════════════════════════════

BIRP_BATCH_MAX   = 50
BIRP_DEFAULT_TTL = 3600


@dataclass
class BIRPMessage:
    """Signal delivery envelope — BIRP relay wrapper (Section 19)."""
    signal_id:         str
    entity_id:         str
    signal_type:       str
    signal_value:      Optional[float]
    ci_95:             List[float]
    coherence:         float
    threshold:         float
    margin:            float
    mf_score:          float
    timestamp:         int
    ttl:               int
    plane_breakdown:   dict
    biological_time:   dict
    chameleon_applied: bool  = True
    silence:           bool  = False
    oracle_sig:        str   = ""
    bootstrap_phase:   bool  = True
    recovery_pending:  bool  = False   # set True during BIRP §16 quarantine
    extra:             dict  = field(default_factory=dict)


def sign_birp_message(msg: BIRPMessage, signing_key: bytes) -> str:
    payload = "|".join([
        msg.signal_id, msg.entity_id, msg.signal_type,
        str(msg.signal_value), str(msg.coherence),
        str(msg.threshold), str(msg.timestamp),
    ])
    mac = hmac.new(signing_key, payload.encode(), hashlib.sha3_256)
    return mac.hexdigest()


def verify_birp_message(msg: BIRPMessage, signing_key: bytes) -> bool:
    expected = sign_birp_message(msg, signing_key)
    return hmac.compare_digest(expected, msg.oracle_sig)


def build_birp_message(
    signal: dict,
    signing_key: bytes,
    chameleon_data: Optional[dict] = None,
    recovery_pending: bool = False,
) -> BIRPMessage:
    msg = BIRPMessage(
        signal_id         = signal.get("signal_id", ""),
        entity_id         = signal.get("entity_id", ""),
        signal_type       = signal.get("signal_type", "UNKNOWN"),
        signal_value      = signal.get("signal_value"),
        ci_95             = signal.get("ci_95", [0.0, 1.0]),
        coherence         = signal.get("coherence", 0.0),
        threshold         = signal.get("threshold", 0.0),
        margin            = signal.get("margin", 0.0),
        mf_score          = signal.get("mf_score", 0.0),
        timestamp         = signal.get("timestamp", int(time.time())),
        ttl               = BIRP_DEFAULT_TTL,
        plane_breakdown   = signal.get("plane_breakdown", {}),
        biological_time   = signal.get("biological_time", {}),
        chameleon_applied = chameleon_data is not None,
        silence           = signal.get("silence", False),
        bootstrap_phase   = signal.get("bootstrap_phase", True),
        recovery_pending  = recovery_pending,
    )
    msg.oracle_sig = sign_birp_message(msg, signing_key)
    return msg


def batch_birp_messages(
    signals: List[dict],
    signing_key: bytes,
) -> List[BIRPMessage]:
    if len(signals) > BIRP_BATCH_MAX:
        raise ValueError(f"Batch size {len(signals)} exceeds maximum {BIRP_BATCH_MAX}")
    return [build_birp_message(s, signing_key) for s in signals]


def birp_to_dict(msg: BIRPMessage) -> dict:
    return {
        "signal_id":         msg.signal_id,
        "entity_id":         msg.entity_id,
        "signal_type":       msg.signal_type,
        "signal_value":      msg.signal_value,
        "ci_95":             msg.ci_95,
        "coherence":         msg.coherence,
        "threshold":         msg.threshold,
        "margin":            msg.margin,
        "mf_score":          msg.mf_score,
        "timestamp":         msg.timestamp,
        "ttl":               msg.ttl,
        "plane_breakdown":   msg.plane_breakdown,
        "biological_time":   msg.biological_time,
        "chameleon_applied": msg.chameleon_applied,
        "silence":           msg.silence,
        "oracle_sig":        msg.oracle_sig,
        "bootstrap_phase":   msg.bootstrap_phase,
        "recovery_pending":  msg.recovery_pending,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Self-test
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import os

    print("=== TRION BIRP §16 Self-test ===\n")

    # — Phase 1: DNA verification ——————————————————————————————————————————
    payload = b"uniswap_entity_test_" + b"\xab" * 12
    sense_b, anti_b = _hash_dna(payload)
    result = phase1_dna_verification(
        "test_entity",
        sense_b.hex(), anti_b.hex(), payload.hex()
    )
    assert result.passed, f"Phase 1 should pass: {result.notes}"
    print(f"[PASS] Phase 1 DNA verification: score={result.score:.2f}")

    # Tamper test
    bad = phase1_dna_verification(
        "test_entity",
        sense_b.hex(), (b'\x00' * 32).hex(), payload.hex()
    )
    assert not bad.passed, "Tampered antisense must fail"
    print(f"[PASS] Phase 1 tamper detection: rejected")

    # — Phase 2: Behavioral proof ——————————————————————————————————————————
    bh_hashes = [hashlib.sha3_256(f"bh_{i}".encode()).hexdigest() for i in range(10)]
    proof_leaves = bh_hashes[:8]
    root = _merkle_root([bytes.fromhex(h) for h in proof_leaves]).hex()
    r2 = phase2_behavioral_proof("test_entity", bh_hashes, proof_leaves, root)
    assert r2.passed, f"Phase 2 should pass: {r2.notes}"
    print(f"[PASS] Phase 2 behavioral proof: coverage={r2.evidence['coverage']:.0%}")

    # — Phase 3: Temporal cluster ——————————————————————————————————————————
    r3 = phase3_temporal_cluster(
        "test_entity", faiss_distance=0.12,
        cluster_archetype_id="arch_42", historical_cluster_id="arch_42",
        temporal_gap_blocks=500
    )
    assert r3.passed, f"Phase 3 should pass: {r3.notes}"
    print(f"[PASS] Phase 3 temporal cluster: score={r3.score:.2f}")

    # — Phase 4: Conscious layer ———————————————————————————————————————————
    votes = [
        ValidatorVote("v1", True,  0.40, "behavioral match confirmed"),
        ValidatorVote("v2", True,  0.30, "history verified"),
        ValidatorVote("v3", False, 0.10, "suspicious dormancy"),
        ValidatorVote("v4", True,  0.20, "cluster ok"),
    ]
    r4 = phase4_conscious_layer("test_entity", votes, total_registered_stake=1.0)
    assert r4.passed, f"Phase 4 should pass: {r4.notes}"
    print(f"[PASS] Phase 4 conscious layer: approve_fraction={r4.evidence['approve_fraction']:.0%}")

    # — Phase 5: Quarantine ————————————————————————————————————————————————
    started = time.time() - QUARANTINE_SECONDS - 1  # already elapsed
    r5 = phase5_quarantine_status(started)
    assert r5.passed, f"Phase 5 should pass: {r5.notes}"
    print(f"[PASS] Phase 5 quarantine: complete (score={r5.score:.2f})")

    # — Full lifecycle via BIRPManager ————————————————————————————————————
    mgr = BIRPManager()
    req = mgr.open_request("uniswap", "dormancy_resurrection")
    mgr.submit_phase1(req.request_id, sense_b.hex(), anti_b.hex(), payload.hex())
    mgr.submit_phase2(req.request_id, bh_hashes, proof_leaves, root)
    mgr.submit_phase3(req.request_id, 0.12, "arch_42", "arch_42", 500)
    mgr.submit_phase4(req.request_id, votes, 1.0)
    # Simulate quarantine elapsed
    req.quarantine_ends_at = time.time() - 1
    mgr.check_quarantine(req.request_id)
    assert req.outcome == BIRPOutcome.APPROVED, f"Expected APPROVED, got {req.outcome}"
    print(f"[PASS] Full BIRP §16 lifecycle: outcome={req.outcome.value}")

    # — Signal relay wrapper ————————————————————————————————————————————
    key = os.urandom(32)
    sample_signal = {
        "signal_id": "test-sig-001", "entity_id": "0xAABBCC",
        "signal_type": "VALUATION", "signal_value": 0.72,
        "ci_95": [0.65, 0.79], "coherence": 0.72, "threshold": 0.62,
        "margin": 0.10, "mf_score": 0.0, "timestamp": int(time.time()),
        "plane_breakdown": {}, "biological_time": {"circadian_phase": 0.5},
        "silence": False, "bootstrap_phase": True,
    }
    msg   = build_birp_message(sample_signal, key)
    valid = verify_birp_message(msg, key)
    tamper = BIRPMessage(**vars(msg))
    tamper.coherence = 0.99
    invalid = verify_birp_message(tamper, key)
    assert valid and not invalid
    print("[PASS] Signal relay wrapper: sign/verify/tamper detection")

    print("\n=== BIRP §16 + §19 ALL TESTS PASSED ===")
    print("Phases: DNA-Verification, Behavioral-Proof, Temporal-Cluster,")
    print("        Conscious-Layer, Quarantine-Wait (7d) + Relay-Wrapper")
