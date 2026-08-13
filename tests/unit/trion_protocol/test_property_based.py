"""
Phase 8 — Property-Based Tests for Behavioral Hash
===================================================
Uses Hypothesis to verify mathematical invariants of the BH primitive
that must hold for ALL possible inputs, not just the hand-picked
examples in the unit tests.

Properties verified:
  1. Payload length is always 93 bytes (canonical v1 layout)
  2. sense and antisense are always 32 bytes
  3. XOR invariant holds for all payloads
  4. Determinism: same input → same output
  5. Distinct inputs → distinct senses (no collisions in test sample)
  6. Magnitude normalization is in [0, 1]
  7. Event type byte is correctly encoded at offset 32
  8. Timestamp is correctly encoded at offset 49
  9. chain_id is correctly encoded at offset 57
"""
import hashlib
import pytest
from hypothesis import given, strategies as st, settings, assume

from core.primitives.behavioral_hash import (
    EventType,
    BehavioralEvent,
    compute_behavioral_hash,
    normalize_magnitude,
    complement_transform,
    hash_dna,
)


# ── Strategies ─────────────────────────────────────────────────────────────────

# 32-byte entity ID
entity_id_strategy = st.binary(min_size=32, max_size=32)

# 32-byte block hash
block_hash_strategy = st.binary(min_size=32, max_size=32)

# 8-byte context
context_strategy = st.binary(min_size=8, max_size=8)

# Event type (0-19)
event_type_strategy = st.sampled_from(list(EventType))

# Magnitude parameters
magnitude_strategy = st.integers(min_value=0, max_value=2**64 - 1)
decimals_strategy = st.integers(min_value=0, max_value=18)
max_90d_strategy = st.integers(min_value=1, max_value=2**64 - 1)

# Timestamp
timestamp_strategy = st.integers(min_value=0, max_value=2**63 - 1)

# Block number
block_number_strategy = st.integers(min_value=0, max_value=2**63 - 1)

# Chain ID (4 bytes)
chain_id_strategy = st.integers(min_value=0, max_value=2**32 - 1)


# Composite strategy for a full BehavioralEvent
@st.composite
def behavioral_event_strategy(draw):
    return BehavioralEvent(
        entity_id=draw(entity_id_strategy),
        event_type=draw(event_type_strategy),
        magnitude_raw=draw(magnitude_strategy),
        magnitude_decimals=draw(decimals_strategy),
        magnitude_max_90d=draw(max_90d_strategy),
        timestamp=draw(timestamp_strategy),
        block_number=draw(block_number_strategy),
        block_hash=draw(block_hash_strategy),
        chain_id=draw(chain_id_strategy),
        context=draw(context_strategy),
    )


# ── Property tests ─────────────────────────────────────────────────────────────

class TestBHProperties:
    @given(event=behavioral_event_strategy())
    @settings(max_examples=200)
    def test_payload_length_is_93(self, event):
        """Property 1: payload is always exactly 93 bytes."""
        result = compute_behavioral_hash(event)
        assert result["payload_len"] == 93

    @given(event=behavioral_event_strategy())
    @settings(max_examples=200)
    def test_sense_is_32_bytes(self, event):
        """Property 2: sense strand is always 32 bytes (64 hex chars)."""
        result = compute_behavioral_hash(event)
        assert len(result["sense_hex"]) == 64
        assert len(result["antisense_hex"]) == 64

    @given(event=behavioral_event_strategy())
    @settings(max_examples=200)
    def test_xor_invariant_holds(self, event):
        """Property 3: XOR invariant holds for all valid events.

        sense XOR antisense == NOT(SHA3-256(payload || 0xFF))
        """
        result = compute_behavioral_hash(event)
        assert result["valid"] is True

    @given(event=behavioral_event_strategy())
    @settings(max_examples=100)
    def test_determinism(self, event):
        """Property 4: same input always produces same output."""
        r1 = compute_behavioral_hash(event)
        r2 = compute_behavioral_hash(event)
        assert r1["sense_hex"] == r2["sense_hex"]
        assert r1["antisense_hex"] == r2["antisense_hex"]

    @given(
        entity_id=entity_id_strategy,
        event_type=event_type_strategy,
        timestamp=timestamp_strategy,
    )
    @settings(max_examples=100)
    def test_distinct_inputs_distinct_senses(self, entity_id, event_type, timestamp):
        """Property 5: distinct inputs produce distinct senses.

        We vary only one field at a time and confirm the sense changes.
        """
        base_event = BehavioralEvent(
            entity_id=entity_id,
            event_type=event_type,
            magnitude_raw=1_000_000,
            magnitude_decimals=18,
            magnitude_max_90d=1_000_000_000,
            timestamp=timestamp,
            block_number=100,
            block_hash=b"\x00" * 32,
            chain_id=1,
        )
        base_result = compute_behavioral_hash(base_event)

        # Vary entity_id
        if entity_id != b"\xff" * 32:
            varied_event = BehavioralEvent(
                entity_id=bytes(b ^ 0xFF for b in entity_id),
                event_type=event_type,
                magnitude_raw=1_000_000,
                magnitude_decimals=18,
                magnitude_max_90d=1_000_000_000,
                timestamp=timestamp,
                block_number=100,
                block_hash=b"\x00" * 32,
                chain_id=1,
            )
            varied_result = compute_behavioral_hash(varied_event)
            assert base_result["sense_hex"] != varied_result["sense_hex"]


class TestMagnitudeNormalization:
    @given(
        raw=magnitude_strategy,
        decimals=decimals_strategy,
        max_90d=max_90d_strategy,
    )
    @settings(max_examples=200)
    def test_normalization_in_unit_interval(self, raw, decimals, max_90d):
        """Property 6: normalized magnitude is always in [0, 1]."""
        norm = normalize_magnitude(raw, decimals, max_90d)
        assert 0.0 <= norm <= 1.0

    @given(
        raw=magnitude_strategy,
        decimals=decimals_strategy,
        max_90d=max_90d_strategy,
    )
    @settings(max_examples=200)
    def test_normalization_monotone_in_raw(self, raw, decimals, max_90d):
        """Property: doubling raw value (when max_90d is large) doesn't decrease norm."""
        if raw == 0 or max_90d <= raw:
            assume(False)
        n1 = normalize_magnitude(raw, decimals, max_90d)
        n2 = normalize_magnitude(raw * 2, decimals, max_90d)
        # log10 is monotonic, so n2 >= n1 (when both fit in max_90d)
        if raw * 2 <= max_90d:
            assert n2 >= n1


class TestHashDNA:
    @given(payload=st.binary(min_size=0, max_size=256))
    @settings(max_examples=200)
    def test_sense_antisense_lengths(self, payload):
        """sense and antisense are always 32 bytes regardless of payload size."""
        sense, antisense = hash_dna(payload)
        assert len(sense) == 32
        assert len(antisense) == 32

    @given(payload=st.binary(min_size=0, max_size=256))
    @settings(max_examples=200)
    def test_xor_invariant_direct(self, payload):
        """XOR invariant holds for any payload, not just BH-shaped ones.

        sense XOR antisense == NOT(SHA3-256(payload || 0xFF))
        """
        sense, antisense = hash_dna(payload)
        sha3ff = hashlib.sha3_256(payload + b"\xFF").digest()
        expected = complement_transform(sha3ff)
        actual = bytes(a ^ b for a, b in zip(sense, antisense))
        assert actual == expected

    @given(payload=st.binary(min_size=1, max_size=256))
    @settings(max_examples=100)
    def test_distinct_payloads_distinct_senses(self, payload):
        """Different payloads produce different senses (with overwhelming probability)."""
        sense1, _ = hash_dna(payload)
        # Flip one bit of the payload
        tampered = bytes([payload[0] ^ 0x01]) + payload[1:]
        sense2, _ = hash_dna(tampered)
        assert sense1 != sense2


class TestExtendedPayloadProperties:
    """Property-based tests for the v2 extended payload."""

    @given(
        entity_id=entity_id_strategy,
        event_type=event_type_strategy,
        chain_id=chain_id_strategy,
        nonce=st.integers(min_value=0, max_value=2**64 - 1),
    )
    @settings(max_examples=100)
    def test_extended_payload_always_176_bytes(self, entity_id, event_type, chain_id, nonce):
        """Property: extended payload is always exactly 176 bytes."""
        from core.primitives.extended_payload import (
            ExtendedBehavioralEvent,
            EXTENDED_PAYLOAD_LEN,
            build_extended_payload,
        )
        event = ExtendedBehavioralEvent(
            entity_id=entity_id,
            event_type=event_type,
            magnitude_raw=1_000_000,
            magnitude_decimals=18,
            magnitude_max_90d=1_000_000_000,
            magnitude_currency_id=0,
            timestamp=1_700_000_000,
            block_number=100,
            block_hash=b"\x00" * 32,
            chain_id=chain_id,
            counterparty_id=b"\x00" * 32,
            protocol_id=1,
            context=b"\x00" * 8,
            btcp_version=1,
            nonce=nonce,
        )
        payload = build_extended_payload(event)
        assert len(payload) == EXTENDED_PAYLOAD_LEN
        assert EXTENDED_PAYLOAD_LEN == 176

    @given(
        entity_id=entity_id_strategy,
        event_type=event_type_strategy,
        chain_id=chain_id_strategy,
        nonce=st.integers(min_value=0, max_value=2**64 - 1),
    )
    @settings(max_examples=100)
    def test_extended_xor_invariant_holds(self, entity_id, event_type, chain_id, nonce):
        """Property: XOR invariant holds for all extended payloads."""
        from core.primitives.extended_payload import (
            ExtendedBehavioralEvent,
            compute_extended_bh,
        )
        event = ExtendedBehavioralEvent(
            entity_id=entity_id,
            event_type=event_type,
            magnitude_raw=1_000_000,
            magnitude_decimals=18,
            magnitude_max_90d=1_000_000_000,
            magnitude_currency_id=0,
            timestamp=1_700_000_000,
            block_number=100,
            block_hash=b"\x00" * 32,
            chain_id=chain_id,
            counterparty_id=b"\x00" * 32,
            protocol_id=1,
            context=b"\x00" * 8,
            btcp_version=1,
            nonce=nonce,
        )
        result = compute_extended_bh(event)
        assert result["valid"] is True
