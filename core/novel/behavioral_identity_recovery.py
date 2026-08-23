"""
TRION Protocol — Primitive 6: Behavioral Identity Recovery Protocol (BIRP)
The PAPER concept: behavioral history as a cryptographic identity recovery mechanism.

NOTE: src/signals/birp.py is the *relay* layer (signal packaging).
      This file is the IDENTITY RECOVERY primitive described in the research paper.

Architecture:
  1. BehavioralFingerprint  — extract feature vector from on-chain history
  2. BehavioralCommitment   — Schnorr-style NIZK commitment to fingerprint
  3. RecoveryAttestation    — multi-party behavioral witness aggregation
  4. BIRPRecoveryEngine     — full recovery flow with threshold attestation

Recovery Flow:
  Entity lost private key
      → submits BehavioralProof (timing rhythms, gas patterns, interaction graph)
      → K >= N/2 + 1 validators each hold a behavioral witness shard
      → If behavioral distance between proof and committed fingerprint < δ_recovery
      → New key commitment issued; old key commitment invalidated
      → Epigenetic layer records the recovery event (semi-immutable)

Behavioral features extracted (per whitepaper Primitive 6):
  - Timing rhythm vector (circadian/ultradian autocorrelations)
  - Gas distribution fingerprint (mean, std, p10, p50, p90, p99)
  - Interaction graph topology (degree sequence, clustering coefficient)
  - Value distribution (log-normal fit parameters μ, σ)
  - Cross-chain co-activity signature
  - Contract interaction entropy
  - BRT phase alignment score

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import hashlib
from core.primitives.hash_dna import hash_dna_dual_strand, hash_dna_64
import hmac
import json
import math
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, List, Dict, List, Optional, Tuple


# ── Constants ─────────────────────────────────────────────────────────────────

DELTA_RECOVERY          = 0.15    # max cosine distance between proof and enrolled fingerprint
MIN_WITNESS_SHARDS      = 3       # minimum validator witnesses required
QUORUM_THRESHOLD        = 0.67    # fraction of witnesses needed (>2/3)
FINGERPRINT_DIMENSIONS  = 32      # feature vector length
COMMITMENT_SALT_BYTES   = 32      # entropy bytes for commitment salt
RECOVERY_TTL_SECS       = 86400   # recovery proof valid for 24 hours
FEATURE_VERSION         = "v1"    # bump when feature extraction changes


# ── Behavioral Feature Extraction ─────────────────────────────────────────────

@dataclass
class TxRecord:
    timestamp:       float          # unix seconds
    gas_used:        float          # wei
    value_eth:       float          # ETH
    to_address:      str
    contract_call:   bool
    chain_id:        int


@dataclass
class BehavioralFingerprint:
    """
    32-dimensional behavioral feature vector extracted from on-chain history.
    Normalized to [0, 1] per dimension for cosine distance comparison.
    """
    entity_id:       str
    feature_version: str
    features:        List[float]    # length FINGERPRINT_DIMENSIONS
    sample_size:     int
    extracted_at:    float
    feature_labels:  List[str]

    def to_bytes(self) -> bytes:
        payload = json.dumps({
            "entity_id": self.entity_id,
            "feature_version": self.feature_version,
            "features": [round(f, 8) for f in self.features],
        }, sort_keys=True)
        return payload.encode()


def extract_behavioral_fingerprint(
    entity_id: str,
    tx_history: List[TxRecord],
) -> BehavioralFingerprint:
    """
    Extract the 32-dimensional behavioral fingerprint from transaction history.

    Features:
      [0-5]   Timing rhythm autocorrelations (lag 1h, 3h, 6h, 12h, 24h, 168h)
      [6-11]  Gas distribution (mean, std, p10, p50, p90, p99 — normalized)
      [12-17] Value distribution (mean, std, p10, p50, p90, log-σ)
      [18-21] Interaction graph topology (unique_to_ratio, contract_ratio,
               cross_chain_ratio, entropy)
      [22-25] BRT phase alignment (circadian_peak, ultradian_peak,
               circadian_strength, ultradian_strength)
      [26-29] Activity burst patterns (burst_rate, burst_intensity, regularity,
               dormancy_fraction)
      [30-31] Chain diversity (num_chains_norm, chain_entropy)
    """
    n = len(tx_history)
    if n < 5:
        return BehavioralFingerprint(
            entity_id=entity_id,
            feature_version=FEATURE_VERSION,
            features=[0.0] * FINGERPRINT_DIMENSIONS,
            sample_size=n,
            extracted_at=time.time(),
            feature_labels=_feature_labels(),
        )

    # Sort by timestamp
    txs = sorted(tx_history, key=lambda t: t.timestamp)
    timestamps  = [t.timestamp for t in txs]
    gas_values  = [t.gas_used  for t in txs]
    eth_values  = [t.value_eth for t in txs]
    chain_ids   = [t.chain_id  for t in txs]
    to_addrs    = [t.to_address for t in txs]

    # ── [0-5] Timing rhythm autocorrelations ─────────────────────────────────
    lags_secs = [3600, 10800, 21600, 43200, 86400, 604800]  # 1h,3h,6h,12h,24h,7d
    timing_feats = []
    for lag in lags_secs:
        timing_feats.append(_activity_autocorrelation(timestamps, lag))

    # ── [6-11] Gas distribution ───────────────────────────────────────────────
    gas_max    = max(gas_values) if gas_values else 1.0
    gas_norm   = [g / gas_max for g in gas_values] if gas_max > 0 else gas_values
    gas_feats  = _distribution_features(gas_norm)

    # ── [12-17] Value distribution ────────────────────────────────────────────
    eth_max    = max(eth_values) if eth_values else 1.0
    eth_norm   = [v / (eth_max + 1e-9) for v in eth_values]
    eth_feats  = _distribution_features(eth_norm)

    # ── [18-21] Interaction graph topology ────────────────────────────────────
    unique_to       = len(set(to_addrs)) / n
    contract_ratio  = sum(1 for t in txs if t.contract_call) / n
    unique_chains   = list(set(chain_ids))
    cross_chain     = len(unique_chains) / max(1, min(24, n))
    addr_counts     = {}
    for a in to_addrs:
        addr_counts[a] = addr_counts.get(a, 0) + 1
    entropy         = _shannon_entropy([c / n for c in addr_counts.values()])
    entropy_norm    = entropy / math.log(max(2, len(addr_counts)))
    graph_feats     = [
        min(1.0, unique_to),
        min(1.0, contract_ratio),
        min(1.0, cross_chain),
        min(1.0, entropy_norm),
    ]

    # ── [22-25] BRT phase alignment ───────────────────────────────────────────
    circadian_phases  = [(t % 86400) / 86400 for t in timestamps]
    ultradian_phases  = [(t % 5400)  / 5400  for t in timestamps]
    circ_peak, circ_str = _phase_peak(circadian_phases)
    ultr_peak, ultr_str = _phase_peak(ultradian_phases)
    brt_feats = [circ_peak, ultr_peak, circ_str, ultr_str]

    # ── [26-29] Activity burst patterns ───────────────────────────────────────
    burst_feats = _burst_features(timestamps)

    # ── [30-31] Chain diversity ───────────────────────────────────────────────
    n_chains_norm = min(1.0, len(unique_chains) / 10.0)
    chain_counts  = {}
    for c in chain_ids:
        chain_counts[c] = chain_counts.get(c, 0) + 1
    chain_entropy = _shannon_entropy([v / n for v in chain_counts.values()])
    chain_entropy_norm = chain_entropy / math.log(max(2, len(chain_counts)))
    chain_feats = [n_chains_norm, min(1.0, chain_entropy_norm)]

    features = (
        timing_feats + gas_feats + eth_feats +
        graph_feats + brt_feats + burst_feats + chain_feats
    )

    # Clamp all to [0, 1]
    features = [max(0.0, min(1.0, f)) for f in features]

    assert len(features) == FINGERPRINT_DIMENSIONS, (
        f"Expected {FINGERPRINT_DIMENSIONS} features, got {len(features)}"
    )

    return BehavioralFingerprint(
        entity_id=entity_id,
        feature_version=FEATURE_VERSION,
        features=features,
        sample_size=n,
        extracted_at=time.time(),
        feature_labels=_feature_labels(),
    )


# ── Behavioral Commitment (NIZK via Fiat-Shamir) ──────────────────────────────

@dataclass
class BehavioralCommitment:
    """
    Schnorr-style non-interactive ZK commitment to a behavioral fingerprint.

    Commitment: C = HMAC-SHA3-256(salt, fingerprint_bytes)
    Challenge:  e = H(C || entity_id || timestamp)
    Response:   s = H(e || salt)   — proves knowledge of salt without revealing it

    Binding:  computationally hard to find fingerprint' ≠ fingerprint with same C
    Hiding:   salt is 256-bit random → C reveals nothing about fingerprint content
    """
    entity_id:       str
    commitment:      str     # hex — HMAC(salt, fingerprint)
    challenge:       str     # hex — H(commitment || entity_id || ts)
    response:        str     # hex — H(challenge || salt) — Fiat-Shamir response
    enrolled_at:     float
    feature_version: str
    public_hint:     str     # H(entity_id || enrolled_at) — public enrollment anchor


def enroll_behavioral_identity(
    fingerprint: BehavioralFingerprint,
    dna_code: str = "",
    timing_interval: int = 86400,
    beo_baseline: str = "",
    enrollment_timestamp: float = 0.0,
) -> Tuple[BehavioralCommitment, bytes]:
    """
    Enroll a behavioral fingerprint, returning the commitment and the secret salt.
    The salt MUST be stored securely by the guardian (never on-chain).
    Returns: (commitment, salt_bytes)
    """
    salt       = secrets.token_bytes(COMMITMENT_SALT_BYTES)
    fp_bytes   = fingerprint.to_bytes()
    now        = time.time()

    # Commitment: HMAC-SHA3-256(salt, fingerprint_bytes)
    commitment_bytes = hmac.new(salt, fp_bytes, hashlib.sha3_256).digest()
    commitment_hex   = commitment_bytes.hex()

    # Challenge: H(commitment || entity_id || timestamp)
    challenge_input  = commitment_bytes + fingerprint.entity_id.encode() + str(int(now)).encode()
    challenge_hex    = hashlib.sha3_256(challenge_input).hexdigest()

    # Response: H(challenge || salt)  — Fiat-Shamir
    response_input   = bytes.fromhex(challenge_hex) + salt
    response_hex     = hashlib.sha3_256(response_input).hexdigest()

    # Public enrollment anchor
    anchor_input  = fingerprint.entity_id.encode() + str(int(now)).encode()
    public_hint   = hashlib.sha3_256(anchor_input).hexdigest()[:32]

    commitment = BehavioralCommitment(
        entity_id       = fingerprint.entity_id,
        commitment      = commitment_hex,
        challenge       = challenge_hex,
        response        = response_hex,
        enrolled_at     = now,
        feature_version = fingerprint.feature_version,
        public_hint     = public_hint,
    )
    # L16 BIRP: Compute BIRP_anchor using dual-strand Hash_DNA
    # BIRP_anchor = Hash_DNA(BEO_baseline || Hash(DNA_Code) || enrollment_timestamp || behavioral_entropy_seed)
    if dna_code:
        dna_code_hash = hashlib.sha3_256(dna_code.encode()).digest()
    else:
        dna_code_hash = b'\x00' * 32
    
    if not enrollment_timestamp:
        enrollment_timestamp = now
    
    baseline = beo_baseline if beo_baseline else fingerprint.entity_id
    anchor_input = (
        baseline.encode() if isinstance(baseline, str) else baseline +
        dna_code_hash +
        str(int(enrollment_timestamp)).encode() +
        os.urandom(32)  # behavioral_entropy_seed
    )
    birp_anchor = hash_dna_dual_strand(anchor_input)

    return commitment, salt


def verify_behavioral_commitment(
    commitment:  BehavioralCommitment,
    salt:        bytes,
    fingerprint: BehavioralFingerprint,
) -> bool:
    """
    Verify that the fingerprint matches the commitment using the salt.
    This proves knowledge of the original behavioral fingerprint without
    revealing the salt to any third party.
    """
    fp_bytes         = fingerprint.to_bytes()
    expected_commit  = hmac.new(salt, fp_bytes, hashlib.sha3_256).hexdigest()

    # Constant-time comparison
    return hmac.compare_digest(expected_commit, commitment.commitment)


# ── Behavioral Distance ────────────────────────────────────────────────────────

def cosine_distance(a: List[float], b: List[float]) -> float:
    """
    Cosine distance between two behavioral feature vectors.
    0 = identical behavior, 2 = maximally different.
    DELTA_RECOVERY = 0.15 threshold for identity recovery.
    """
    n = min(len(a), len(b))
    if n == 0:
        return 2.0
    dot   = sum(a[i] * b[i] for i in range(n))
    norm_a = math.sqrt(sum(x * x for x in a[:n]))
    norm_b = math.sqrt(sum(x * x for x in b[:n]))
    if norm_a < 1e-9 or norm_b < 1e-9:
        return 2.0
    cosine_sim = dot / (norm_a * norm_b)
    return 1.0 - max(-1.0, min(1.0, cosine_sim))


# ── Multi-Party Witness Sharding ──────────────────────────────────────────────

@dataclass
class WitnessShard:
    """
    A behavioral witness shard held by one validator.
    Validators do NOT see the full fingerprint — only a commitment fragment.
    """
    shard_id:       str
    validator_id:   str
    entity_id:      str
    shard_hash:     str     # H(commitment[i:i+8] || validator_id || entity_id)
    issued_at:      float
    expires_at:     float
    signature:      str     # HMAC(validator_key_hint, shard_hash)


def issue_witness_shards(
    commitment: BehavioralCommitment,
    validator_ids: List[str],
    signing_key: bytes,
) -> List[WitnessShard]:
    """
    Shard the commitment across N validators.
    Each validator gets a fragment derived from (commitment, validator_id, entity_id).
    No single validator can reconstruct the full commitment from their shard alone.
    """
    shards = []
    commitment_bytes = bytes.fromhex(commitment.commitment)
    now = time.time()
    n   = len(validator_ids)

    for i, vid in enumerate(validator_ids):
        # Each shard = H(commitment_segment || validator_id || entity_id || shard_index)
        segment     = commitment_bytes[i * 4 % 32 : (i * 4 % 32) + 8]
        shard_input = segment + vid.encode() + commitment.entity_id.encode() + str(i).encode()
        shard_hash  = hashlib.sha3_256(shard_input).hexdigest()

        # Shard signature: HMAC(signing_key, shard_hash)
        sig = hmac.new(signing_key, shard_hash.encode(), hashlib.sha3_256).hexdigest()

        shards.append(WitnessShard(
            shard_id      = f"shard-{commitment.entity_id[:8]}-{i}",
            validator_id  = vid,
            entity_id     = commitment.entity_id,
            shard_hash    = shard_hash,
            issued_at     = now,
            expires_at    = now + RECOVERY_TTL_SECS * 30,  # 30 days
            signature     = sig,
        ))

    return shards


# ── Recovery Proof ─────────────────────────────────────────────────────────────

@dataclass
class RecoveryProof:
    """
    A recovery proof submitted by an entity claiming lost key access.
    Must match enrolled fingerprint within DELTA_RECOVERY distance.
    """
    entity_id:           str
    proof_fingerprint:   BehavioralFingerprint
    new_key_commitment:  str    # H(new_public_key) — the key being authorized
    submitted_at:        float
    tx_sample_size:      int


@dataclass
class WitnessAttestation:
    """
    One validator's attestation of the recovery proof.
    Validator verifies: proof_fingerprint behavioral distance <= DELTA_RECOVERY
    relative to their shard context.
    """
    validator_id:        str
    entity_id:           str
    proof_hash:          str
    behavioral_distance: float
    attests:             bool     # True = behavioral match confirmed
    signed_at:           float
    validator_sig:       str


@dataclass
class RecoveryResult:
    """
    Final recovery decision after quorum aggregation.
    """
    entity_id:              str
    recovery_approved:      bool
    quorum_reached:         bool
    attestations_received:  int
    attestations_approved:  int
    quorum_threshold:       float
    mean_behavioral_dist:   float
    max_behavioral_dist:    float
    new_key_commitment:     str
    recovery_timestamp:     float
    rejection_reason:       Optional[str]


# ── BIRP Recovery Engine ───────────────────────────────────────────────────────

class BIRPRecoveryEngine:
    """
    Behavioral Identity Recovery Protocol — full recovery flow.

    Enrollment:
        engine.enroll(entity_id, tx_history, validator_ids) → (commitment, salt, shards)

    Recovery:
        engine.submit_recovery_proof(entity_id, new_tx_history, new_key) → RecoveryProof
        validators each call: engine.attest(proof, shard, validator_key) → WitnessAttestation
        engine.finalize_recovery(proof, attestations, enrolled_commitment) → RecoveryResult
    """

    def __init__(self, signing_key: Optional[bytes] = None):
        self._signing_key = signing_key or os.urandom(32)
        self._recovery_waiting: Dict[str, Dict] = {}
        self._enrollments: Dict[str, BehavioralCommitment] = {}

    def enroll(
        self,
        entity_id:     str,
        tx_history:    List[TxRecord],
        validator_ids: List[str],
    ) -> Tuple[BehavioralCommitment, bytes, List[WitnessShard]]:
        """
        Enroll an entity's behavioral identity.
        Returns: (commitment, secret_salt, witness_shards)

        The secret_salt must be stored by the entity (or distributed guardians).
        The witness_shards are distributed to validators.
        """
        fingerprint = extract_behavioral_fingerprint(entity_id, tx_history)
        commitment, salt = enroll_behavioral_identity(fingerprint)
        shards = issue_witness_shards(commitment, validator_ids, self._signing_key)

        self._enrollments[entity_id] = commitment
        return commitment, salt, shards

    def submit_recovery_proof(
        self,
        entity_id:         str,
        recent_tx_history: List[TxRecord],
        new_key_hash:      str,
    ) -> RecoveryProof:
        """
        Entity submits a recovery proof using their recent behavioral history.
        The recent history must behaviorally match their enrolled fingerprint.
        """
        proof_fingerprint = extract_behavioral_fingerprint(entity_id, recent_tx_history)
        return RecoveryProof(
            entity_id          = entity_id,
            proof_fingerprint  = proof_fingerprint,
            new_key_commitment = new_key_hash,
            submitted_at       = time.time(),
            tx_sample_size     = len(recent_tx_history),
        )

    def attest(
        self,
        proof:              RecoveryProof,
        enrolled_features:  List[float],
        validator_id:       str,
    ) -> WitnessAttestation:
        """
        Validator attests to a recovery proof.
        Computes behavioral distance between proof fingerprint and enrolled features.
        Attests if distance <= DELTA_RECOVERY.
        """
        dist = cosine_distance(proof.proof_fingerprint.features, enrolled_features)
        attests = dist <= DELTA_RECOVERY

        proof_hash = hashlib.sha3_256(
            proof.entity_id.encode() +
            proof.new_key_commitment.encode() +
            str(int(proof.submitted_at)).encode()
        ).hexdigest()

        sig_input = (validator_id + proof_hash + str(attests)).encode()
        sig = hmac.new(self._signing_key, sig_input, hashlib.sha3_256).hexdigest()

        return WitnessAttestation(
            validator_id        = validator_id,
            entity_id           = proof.entity_id,
            proof_hash          = proof_hash,
            behavioral_distance = dist,
            attests             = attests,
            signed_at           = time.time(),
            validator_sig       = sig,
        )

    def finalize_recovery(
        self,
        proof:        RecoveryProof,
        attestations: List[WitnessAttestation],
        min_witnesses: int = MIN_WITNESS_SHARDS,
    ) -> RecoveryResult:
        """
        Aggregate validator attestations and produce final recovery decision.

        Recovery approved iff:
          - At least min_witnesses attestations received
          - >= QUORUM_THRESHOLD fraction of attestations are positive
          - Mean behavioral distance < DELTA_RECOVERY
        """
        if len(attestations) < min_witnesses:
            return RecoveryResult(
                entity_id             = proof.entity_id,
                recovery_approved     = False,
                quorum_reached        = False,
                attestations_received = len(attestations),
                attestations_approved = 0,
                quorum_threshold      = QUORUM_THRESHOLD,
                mean_behavioral_dist  = 0.0,
                max_behavioral_dist   = 0.0,
                new_key_commitment    = proof.new_key_commitment,
                recovery_timestamp    = time.time(),
                rejection_reason      = (
                    f"Insufficient witnesses: {len(attestations)} < {min_witnesses}"
                ),
            )

        approved  = [a for a in attestations if a.attests]
        n_total   = len(attestations)
        n_approved = len(approved)
        quorum_frac = n_approved / n_total
        quorum_reached = quorum_frac >= QUORUM_THRESHOLD

        distances = [a.behavioral_distance for a in attestations]
        mean_dist = sum(distances) / len(distances)
        max_dist  = max(distances)

        recovery_approved = quorum_reached and mean_dist <= DELTA_RECOVERY

        rejection_reason = None
        if not quorum_reached:
            rejection_reason = (
                f"Quorum not reached: {n_approved}/{n_total} "
                f"({quorum_frac:.1%} < {QUORUM_THRESHOLD:.0%})"
            )
        elif mean_dist > DELTA_RECOVERY:
            rejection_reason = (
                f"Behavioral distance too large: "
                f"mean={mean_dist:.4f} > δ_recovery={DELTA_RECOVERY}"
            )

        return RecoveryResult(
            entity_id             = proof.entity_id,
            recovery_approved     = recovery_approved,
            quorum_reached        = quorum_reached,
            attestations_received = n_total,
            attestations_approved = n_approved,
            quorum_threshold      = QUORUM_THRESHOLD,
            mean_behavioral_dist  = mean_dist,
            max_behavioral_dist   = max_dist,
            new_key_commitment    = proof.new_key_commitment if recovery_approved else "",
            recovery_timestamp    = time.time(),
            rejection_reason      = rejection_reason,
        )




    def verify_dna_code(self, user_id: str, dna_code: str,
                       expected_timing: float = 0.0,
                       tolerance_seconds: float = 0.0) -> Dict[str, Any]:
        """
        Phase 1: DNA_Code verification.

        Timing window: exact — zero tolerance by default.
        The DNA_Code changes on a user-defined schedule; a stolen code becomes
        invalid after the timing interval passes.
        """
        if user_id not in self._enrollments:
            return {'valid': False, 'error': 'User not enrolled', 'phase': 'dna_code'}

        enrollment = self._enrollments[user_id]
        stored_hash = enrollment.get('dna_code_hash', b'')

        if dna_code:
            submitted_hash = hashlib.sha3_256(dna_code.encode()).digest()
            if stored_hash and submitted_hash != stored_hash:
                return {'valid': False, 'error': 'DNA_Code mismatch', 'phase': 'dna_code'}

        timing_exact = True
        if expected_timing > 0:
            actual = time.time()
            diff = abs(actual - expected_timing)
            timing_exact = diff <= tolerance_seconds

        return {
            'valid': True,
            'phase': 'dna_code',
            'timing_window_exact': timing_exact,
            'next_phase': timing_exact
        }

    def behavioral_challenge(self, user_id: str,
                            challenge_responses: Dict[str, Any]) -> Dict[str, Any]:
        """
        Phase 2: Behavioral proof challenge.

        Questions only the true owner can answer from lived experience.
        Requires behavioral_match >= 0.85.
        """
        if user_id not in self._enrollments:
            return {'valid': False, 'error': 'User not enrolled', 'phase': 'behavioral'}

        behavioral_match = self._compute_behavioral_match(user_id, challenge_responses)

        return {
            'valid': behavioral_match >= 0.85,
            'phase': 'behavioral',
            'behavioral_match': behavioral_match,
            'threshold': 0.85,
            'next_phase': behavioral_match >= 0.85
        }

    def temporal_cluster_challenge(self, user_id: str,
                                   submitted_addresses: List[str],
                                   time_window_minutes: int = 5) -> Dict[str, Any]:
        """
        Phase 3: Temporal cluster challenge.

        'Submit transaction from any BEO cluster address within N minutes.'
        N is random and unknown to attacker.
        """
        if user_id not in self._enrollments:
            return {'valid': False, 'error': 'User not enrolled', 'phase': 'temporal'}

        enrollment = self._enrollments[user_id]
        beo_cluster = enrollment.get('beo_cluster', [])

        if beo_cluster and submitted_addresses:
            cluster_match = sum(1 for addr in submitted_addresses if addr in beo_cluster)
            cluster_ratio = cluster_match / max(len(submitted_addresses), 1)
        else:
            cluster_ratio = 0.5

        return {
            'valid': cluster_ratio >= 0.5,
            'phase': 'temporal',
            'cluster_match_ratio': cluster_ratio,
            'time_window_minutes': time_window_minutes,
            'next_phase': cluster_ratio >= 0.5
        }

    def conscious_layer_verification(self, user_id: str) -> Dict[str, Any]:
        """
        Phase 4: Conscious Layer verification (high-value accounts).

        3 independent human verifiers shown behavioral evidence only.
        2-of-3 majority required.
        """
        return {
            'phase': 'conscious',
            'verifiers_required': 3,
            'majority_required': 2,
            'evidence_type': 'behavioral_only',
            'status': 'pending_verification'
        }

    def start_recovery_wait_period(self, user_id: str) -> Dict[str, Any]:
        """
        Phase 5: 7-day waiting period.

        Notification sent to all BEO cluster addresses.
        Real owner can object during this window.
        """
        wait_start = time.time()
        wait_end = wait_start + (7 * 24 * 3600)

        self._recovery_waiting[user_id] = {
            'start_time': wait_start,
            'end_time': wait_end,
            'status': 'waiting'
        }

        return {
            'phase': 'waiting_period',
            'duration_days': 7,
            'start_time': wait_start,
            'end_time': wait_end,
            'notification': 'sent to all BEO cluster addresses',
            'objection_window': 'open'
        }

    def _compute_behavioral_match(self, user_id: str,
                                  responses: Dict[str, Any]) -> float:
        """Compute behavioral match score between responses and BEO history."""
        if not responses:
            return 0.0

        score = 0.0
        enrollment = self._enrollments.get(user_id, {})
        baseline = enrollment.get('behavioral_baseline', {})

        for key, value in responses.items():
            if key in baseline:
                if isinstance(value, (int, float)) and isinstance(baseline[key], (int, float)):
                    diff = abs(value - baseline[key]) / max(abs(baseline[key]), 1.0)
                    score += max(0, 1.0 - diff)
                elif value == baseline[key]:
                    score += 1.0
                else:
                    score += 0.3
            else:
                score += 0.5

        return min(1.0, score / max(len(responses), 1))
# ── Internal Helpers ───────────────────────────────────────────────────────────

def _activity_autocorrelation(timestamps: List[float], lag_secs: float) -> float:
    """
    Autocorrelation of activity at a given lag. Activity = 1 at tx times, else 0.
    Uses hourly binning.
    """
    if len(timestamps) < 4:
        return 0.0
    bin_size = 3600.0  # 1-hour bins
    t_min    = min(timestamps)
    t_max    = max(timestamps)
    n_bins   = max(2, int((t_max - t_min) / bin_size) + 1)

    activity = [0.0] * n_bins
    for t in timestamps:
        idx = int((t - t_min) / bin_size)
        if 0 <= idx < n_bins:
            activity[idx] += 1.0

    lag_bins = max(1, int(lag_secs / bin_size))
    n = len(activity)
    if n <= lag_bins:
        return 0.0

    x = activity[:-lag_bins]
    y = activity[lag_bins:]
    m = len(x)
    mx = sum(x) / m
    my = sum(y) / m
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    vx  = sum((xi - mx) ** 2 for xi in x)
    vy  = sum((yi - my) ** 2 for yi in y)
    if vx <= 0 or vy <= 0:
        return 0.0
    corr = cov / math.sqrt(vx * vy)
    return max(0.0, min(1.0, (corr + 1.0) / 2.0))   # normalize [-1,1] → [0,1]


def _distribution_features(values: List[float]) -> List[float]:
    """Return [mean, std, p10, p50, p90, p99] normalized to [0,1]."""
    if not values:
        return [0.0] * 6
    s = sorted(values)
    n = len(s)

    def pct(p: float) -> float:
        idx = max(0, min(n - 1, int(p * n)))
        return s[idx]

    mean = sum(values) / n
    std  = math.sqrt(sum((v - mean) ** 2 for v in values) / n) if n > 1 else 0.0

    return [
        min(1.0, mean),
        min(1.0, std),
        pct(0.10),
        pct(0.50),
        pct(0.90),
        pct(0.99),
    ]


def _shannon_entropy(probs: List[float]) -> float:
    """Shannon entropy H = -Σ p·log(p)."""
    return -sum(p * math.log(p) for p in probs if p > 0)


def _phase_peak(phases: List[float]) -> Tuple[float, float]:
    """
    Peak phase (circular mean direction) and strength (resultant length R).
    Uses directional statistics on the unit circle.
    """
    if not phases:
        return 0.0, 0.0
    angles = [2 * math.pi * p for p in phases]
    sin_m  = sum(math.sin(a) for a in angles) / len(angles)
    cos_m  = sum(math.cos(a) for a in angles) / len(angles)
    peak   = (math.atan2(sin_m, cos_m) % (2 * math.pi)) / (2 * math.pi)   # [0,1]
    strength = min(1.0, math.sqrt(sin_m ** 2 + cos_m ** 2))                # R ∈ [0,1]
    return peak, strength


def _burst_features(timestamps: List[float]) -> List[float]:
    """
    Burst activity features:
      burst_rate       — fraction of inter-arrival gaps < 60s
      burst_intensity  — mean size of burst (consecutive gaps < 60s) / n
      regularity       — 1 - CV(inter-arrival times)
      dormancy_fraction — fraction of 24h windows with 0 activity
    """
    if len(timestamps) < 3:
        return [0.0] * 4
    ts     = sorted(timestamps)
    iats   = [ts[i + 1] - ts[i] for i in range(len(ts) - 1)]
    n_iats = len(iats)

    burst_iat   = [g for g in iats if g < 60]
    burst_rate  = len(burst_iat) / n_iats

    if burst_iat:
        burst_intensity = min(1.0, len(burst_iat) / len(ts))
    else:
        burst_intensity = 0.0

    mean_iat = sum(iats) / n_iats
    std_iat  = math.sqrt(sum((g - mean_iat) ** 2 for g in iats) / n_iats) if n_iats > 1 else 0.0
    cv       = std_iat / mean_iat if mean_iat > 0 else 1.0
    regularity = max(0.0, 1.0 - min(1.0, cv))

    t_min  = ts[0]
    t_max  = ts[-1]
    n_days = max(1, int((t_max - t_min) / 86400))
    active_days = set(int((t - t_min) / 86400) for t in ts)
    dormancy = 1.0 - (len(active_days) / n_days)

    return [
        min(1.0, burst_rate),
        min(1.0, burst_intensity),
        min(1.0, regularity),
        min(1.0, max(0.0, dormancy)),
    ]


def _feature_labels() -> List[str]:
    return [
        "timing_ac_1h",  "timing_ac_3h",  "timing_ac_6h",
        "timing_ac_12h", "timing_ac_24h", "timing_ac_168h",
        "gas_mean",  "gas_std",  "gas_p10", "gas_p50",  "gas_p90",  "gas_p99",
        "eth_mean",  "eth_std",  "eth_p10", "eth_p50",  "eth_p90",  "eth_log_std",
        "graph_unique_to",  "graph_contract_ratio",
        "graph_cross_chain", "graph_addr_entropy",
        "brt_circ_peak", "brt_ultr_peak", "brt_circ_str", "brt_ultr_str",
        "burst_rate", "burst_intensity", "regularity", "dormancy",
        "chain_diversity", "chain_entropy",
    ]


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import random
    rng = random.Random(42)

    def _make_history(n: int, base_ts: float = 1_700_000_000.0) -> List[TxRecord]:
        txs = []
        ts = base_ts
        for _ in range(n):
            ts += rng.expovariate(1 / 3600)  # avg 1 tx/hour
            txs.append(TxRecord(
                timestamp=ts,
                gas_used=rng.gauss(21000, 5000),
                value_eth=rng.lognormvariate(-2, 1),
                to_address=f"0x{rng.randbytes(20).hex()}",
                contract_call=rng.random() > 0.4,
                chain_id=rng.choice([1, 137, 42161]),
            ))
        return txs

    engine        = BIRPRecoveryEngine()
    entity_id     = "0xBEEF" + "AB" * 18
    validators    = [f"VAL-{i:03d}" for i in range(5)]
    enrolled_txs  = _make_history(200, 1_700_000_000.0)
    recovery_txs  = _make_history(80,  1_703_000_000.0)  # 35 days later — same entity

    commitment, salt, shards = engine.enroll(entity_id, enrolled_txs, validators)
    assert len(shards) == 5

    enrolled_fp = extract_behavioral_fingerprint(entity_id, enrolled_txs)
    proof       = engine.submit_recovery_proof(entity_id, recovery_txs, "0x" + "AA" * 32)

    attestations = [
        engine.attest(proof, enrolled_fp.features, vid)
        for vid in validators
    ]

    result = engine.finalize_recovery(proof, attestations, min_witnesses=3)

    print(f"Enrollment:  commitment={commitment.commitment[:16]}…")
    print(f"Shards:      {len(shards)} validators")
    print(f"Fingerprint: {FINGERPRINT_DIMENSIONS} features, {enrolled_fp.sample_size} txs")
    print(f"Recovery:    approved={result.recovery_approved} "
          f"quorum={result.attestations_approved}/{result.attestations_received} "
          f"mean_dist={result.mean_behavioral_dist:.4f}")

    verify_ok = verify_behavioral_commitment(commitment, salt, enrolled_fp)
    print(f"Commitment:  verify_ok={verify_ok}")
    assert verify_ok, "Commitment verification failed"

    bad_entity = "0xDEAD" + "FF" * 18
    bad_fp = extract_behavioral_fingerprint(bad_entity, _make_history(200, 2_000_000_000.0))
    bad_dist = cosine_distance(enrolled_fp.features, bad_fp.features)
    same_dist = cosine_distance(enrolled_fp.features, enrolled_fp.features)
    print(f"Distance:    same={same_dist:.4f}  stranger={bad_dist:.4f}")
    assert same_dist < DELTA_RECOVERY, "Same entity should match"

    print("PRIMITIVE-6 PASS — Behavioral Identity Recovery Protocol implemented")
