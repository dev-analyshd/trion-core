"""
Phase 4 — BIRP DNA_Code user-defined secret tests
=================================================
Verifies the whitepaper §16 "user-defined secret sequence with time-based
rotation" extension to the BIRP Phase 1 DNA verification.

The DNA_Code:
  - Is a user-chosen byte sequence (16–256 bytes)
  - Is stored only as a SHA3-256 commitment (never plaintext)
  - Rotates on a fixed schedule (default 90 days) via hash-chaining
  - Must be re-derived client-side and submitted during BIRP recovery
"""
import hashlib
import time
import pytest

from core.novel.birp import (
    BEHAVIORAL_PROOF_MIN_COVERAGE,
    CONSCIOUS_QUORUM_FRACTION,
    DNA_CODE_MAX_BYTES,
    DNA_CODE_MIN_BYTES,
    DNA_CODE_ROTATION_SECONDS,
    DNA_CODE_ROTATION_SECONDS as ROTATION,
    QUARANTINE_SECONDS,
    REJECTION_COOLDOWN,
    TEMPORAL_CLUSTER_MAX_DISTANCE,
    BIRPPhase,
    BIRPPhaseResult,
    BIRPOutcome,
    BIRPRequest,
    DNACodeRegistration,
    _complement,
    _dna_code_epoch,
    _hash_dna,
    _rotate_dna_code,
    _verify_xor_invariant,
    phase1_dna_verification,
    register_dna_code,
    rotate_dna_code_for_epoch,
    verify_dna_code,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def initial_dna_code():
    """A 32-byte user-defined secret (256 bits)."""
    return b"\x11\x22\x33\x44\x55\x66\x77\x88" * 4  # 32 bytes


@pytest.fixture
def registration_time():
    """Fixed registration timestamp: 2024-01-01 00:00:00 UTC."""
    return 1_704_067_200.0


@pytest.fixture
def registration(initial_dna_code, registration_time):
    return register_dna_code("entity_abc", initial_dna_code, registration_time)


@pytest.fixture
def valid_payload_hex():
    """Build a real dual-strand BH to use in Phase 1 tests."""
    payload = b"\xAB" * 32 + b"\x01" + b"\x00" * 60
    sense, antisense = _hash_dna(payload)
    return payload.hex(), sense.hex(), antisense.hex()


# ── Registration tests ─────────────────────────────────────────────────────────

class TestDNACodeRegistration:
    def test_register_returns_commitment_not_plaintext(self, registration, initial_dna_code):
        """The stored commitment must NOT be the raw code."""
        assert registration.code_commitment != initial_dna_code
        assert registration.code_commitment == hashlib.sha3_256(initial_dna_code).digest()

    def test_register_records_timestamp(self, registration, registration_time):
        assert registration.registered_at == registration_time
        assert registration.last_rotated_at == registration_time

    def test_register_starts_at_epoch_0(self, registration):
        assert registration.current_epoch == 0

    def test_rejects_short_code(self):
        with pytest.raises(ValueError, match="outside allowed range"):
            register_dna_code("e", b"\x00" * (DNA_CODE_MIN_BYTES - 1), time.time())

    def test_rejects_long_code(self):
        with pytest.raises(ValueError, match="outside allowed range"):
            register_dna_code("e", b"\x00" * (DNA_CODE_MAX_BYTES + 1), time.time())

    def test_accepts_minimum_length_code(self):
        reg = register_dna_code("e", b"\x00" * DNA_CODE_MIN_BYTES, time.time())
        assert reg.entity_id == "e"

    def test_accepts_maximum_length_code(self):
        reg = register_dna_code("e", b"\x42" * DNA_CODE_MAX_BYTES, time.time())
        assert reg.entity_id == "e"


# ── Rotation tests ─────────────────────────────────────────────────────────────

class TestDNACodeRotation:
    def test_epoch_0_at_registration_time(self, registration, registration_time):
        assert _dna_code_epoch(registration.registered_at, registration_time) == 0

    def test_epoch_0_shortly_after_registration(self, registration, registration_time):
        assert _dna_code_epoch(
            registration.registered_at, registration_time + ROTATION - 1
        ) == 0

    def test_epoch_1_after_one_rotation_period(self, registration, registration_time):
        assert _dna_code_epoch(
            registration.registered_at, registration_time + ROTATION
        ) == 1

    def test_epoch_2_after_two_rotation_periods(self, registration, registration_time):
        assert _dna_code_epoch(
            registration.registered_at, registration_time + 2 * ROTATION
        ) == 2

    def test_rotation_changes_the_code(self, initial_dna_code):
        epoch_0 = _rotate_dna_code(initial_dna_code, 0)
        epoch_1 = _rotate_dna_code(initial_dna_code, 1)
        epoch_2 = _rotate_dna_code(initial_dna_code, 2)
        assert epoch_0 == initial_dna_code
        assert epoch_1 != epoch_0
        assert epoch_2 != epoch_1
        assert epoch_2 != epoch_0

    def test_rotation_is_one_way_hash_chain(self, initial_dna_code):
        """An attacker with epoch N code cannot recover epoch N-1 code."""
        epoch_1 = _rotate_dna_code(initial_dna_code, 1)
        # The epoch-1 code is a SHA3-256 hash — there's no way to recover
        # the initial code from it.
        assert len(epoch_1) == 32  # SHA3-256 output size
        assert epoch_1 != initial_dna_code

    def test_rotate_for_epoch_helper(self, initial_dna_code, registration_time):
        """rotate_dna_code_for_epoch should match _rotate_dna_code."""
        now = registration_time + 3 * ROTATION
        derived = rotate_dna_code_for_epoch(initial_dna_code, registration_time, now)
        expected = _rotate_dna_code(initial_dna_code, 3)
        assert derived == expected


# ── Verification tests ─────────────────────────────────────────────────────────

class TestDNACodeVerification:
    def test_verify_at_epoch_0_with_initial_code(self, registration, initial_dna_code, registration_time):
        """At epoch 0, the submitted code IS the initial code."""
        ok, epoch, msg = verify_dna_code(registration, initial_dna_code, registration_time)
        assert ok
        assert epoch == 0
        assert "verified" in msg.lower()

    def test_verify_fails_with_wrong_code(self, registration, registration_time):
        wrong_code = b"\x99" * 32
        ok, epoch, msg = verify_dna_code(registration, wrong_code, registration_time)
        assert not ok

    def test_verify_fails_with_short_code(self, registration, registration_time):
        short_code = b"\x00" * 8
        ok, epoch, msg = verify_dna_code(registration, short_code, registration_time)
        assert not ok


# ── Phase 1 integration tests ──────────────────────────────────────────────────

class TestPhase1WithDNACode:
    def test_phase1_passes_without_dna_code(self, valid_payload_hex):
        """Phase 1 should still work when no DNA_Code is registered (backward compat)."""
        payload_hex, sense_hex, antisense_hex = valid_payload_hex
        result = phase1_dna_verification(
            entity_id="e1",
            sense_hex=sense_hex,
            antisense_hex=antisense_hex,
            canonical_payload_hex=payload_hex,
        )
        assert result.passed
        assert "dna_code_verified" not in result.evidence

    def test_phase1_passes_with_correct_dna_code(
        self, registration, initial_dna_code, registration_time, valid_payload_hex
    ):
        payload_hex, sense_hex, antisense_hex = valid_payload_hex
        result = phase1_dna_verification(
            entity_id="entity_abc",
            sense_hex=sense_hex,
            antisense_hex=antisense_hex,
            canonical_payload_hex=payload_hex,
            dna_code_registration=registration,
            submitted_dna_code=initial_dna_code,
            now=registration_time,
        )
        assert result.passed
        assert result.evidence["dna_code_verified"] is True
        assert result.evidence["dna_code_epoch"] == 0

    def test_phase1_fails_with_wrong_dna_code(
        self, registration, registration_time, valid_payload_hex
    ):
        payload_hex, sense_hex, antisense_hex = valid_payload_hex
        result = phase1_dna_verification(
            entity_id="entity_abc",
            sense_hex=sense_hex,
            antisense_hex=antisense_hex,
            canonical_payload_hex=payload_hex,
            dna_code_registration=registration,
            submitted_dna_code=b"\x99" * 32,  # wrong code
            now=registration_time,
        )
        assert not result.passed
        assert result.evidence["dna_code_verified"] is False

    def test_phase1_fails_when_dna_code_required_but_missing(
        self, registration, registration_time, valid_payload_hex
    ):
        payload_hex, sense_hex, antisense_hex = valid_payload_hex
        result = phase1_dna_verification(
            entity_id="entity_abc",
            sense_hex=sense_hex,
            antisense_hex=antisense_hex,
            canonical_payload_hex=payload_hex,
            dna_code_registration=registration,
            submitted_dna_code=None,  # missing
            now=registration_time,
        )
        assert not result.passed
        assert result.evidence["dna_code_verified"] is False
        assert "no code submitted" in result.evidence["dna_code_message"]


# ── Constants tests ────────────────────────────────────────────────────────────

class TestBIRPConstants:
    """Verify the whitepaper-mandated constants are unchanged."""

    def test_quarantine_is_7_days(self):
        assert QUARANTINE_SECONDS == 7 * 24 * 3600

    def test_rejection_cooldown_is_30_days(self):
        assert REJECTION_COOLDOWN == 30 * 24 * 3600

    def test_conscious_quorum_is_two_thirds(self):
        assert CONSCIOUS_QUORUM_FRACTION == 0.67

    def test_temporal_cluster_max_distance(self):
        assert TEMPORAL_CLUSTER_MAX_DISTANCE == 0.30

    def test_behavioral_proof_min_coverage(self):
        assert BEHAVIORAL_PROOF_MIN_COVERAGE == 0.70

    def test_dna_code_rotation_is_90_days(self):
        assert DNA_CODE_ROTATION_SECONDS == 90 * 24 * 3600

    def test_dna_code_min_is_128_bits(self):
        assert DNA_CODE_MIN_BYTES == 16

    def test_dna_code_max_is_2048_bits(self):
        assert DNA_CODE_MAX_BYTES == 256
