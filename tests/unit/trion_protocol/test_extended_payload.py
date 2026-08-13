"""
Phase 3 — Extended BH Payload v2 Tests
=======================================
Verifies the optional 176-byte extended BH payload (whitepaper "Protocol
Whitepaper" format) with:
  - DOMAIN_SEPARATOR ("TRON" magic) for cross-protocol domain separation
  - counterparty_id for bilateral behavioral tracking
  - protocol_id for protocol-level identification
  - btcp_version for transport version negotiation
  - nonce for replay protection
  - context_hash for arbitrary context commitment

The 93-byte canonical v1 payload remains the default; v2 is opt-in.
"""
import hashlib
import pytest

from core.primitives.behavioral_hash import EventType, complement_transform
from core.primitives.extended_payload import (
    BTCP_VERSION,
    DOMAIN_MAGIC,
    EXTENDED_PAYLOAD_LEN,
    ExtendedBehavioralEvent,
    build_extended_payload,
    compute_extended_bh,
    generate_nonce,
    hash_dna_extended,
    verify_xor_invariant,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def base_event():
    return ExtendedBehavioralEvent(
        entity_id=b"\xab" * 32,
        event_type=EventType.SWAP,
        magnitude_raw=int(1e18),
        magnitude_decimals=18,
        magnitude_max_90d=int(100e18),
        magnitude_currency_id=0,        # USD
        timestamp=1_700_000_000,
        block_number=18_000_000,
        block_hash=b"\xcc" * 32,
        chain_id=1,
        counterparty_id=b"\xdd" * 32,
        protocol_id=42,
        context=b"\x01\x00\x00\x00\x00\x00\x00\x00",
        btcp_version=BTCP_VERSION,
        nonce=0xDEADBEEFCAFEBABE,
        usd_value=500.0,
        usd_max_90d=50_000.0,
    )


# ── Layout tests ───────────────────────────────────────────────────────────────

class TestExtendedPayloadLayout:
    def test_payload_is_exactly_176_bytes(self, base_event):
        payload = build_extended_payload(base_event)
        assert len(payload) == EXTENDED_PAYLOAD_LEN
        assert EXTENDED_PAYLOAD_LEN == 176

    def test_domain_separator_is_tron_magic(self, base_event):
        payload = build_extended_payload(base_event)
        assert payload[0:4] == DOMAIN_MAGIC
        assert DOMAIN_MAGIC == b"TRON"

    def test_entity_id_at_offset_4(self, base_event):
        payload = build_extended_payload(base_event)
        assert payload[4:36] == base_event.entity_id

    def test_event_type_at_offset_36(self, base_event):
        payload = build_extended_payload(base_event)
        assert payload[36] == int(base_event.event_type)

    def test_magnitude_currency_id_at_offset_45(self, base_event):
        payload = build_extended_payload(base_event)
        cid = int.from_bytes(payload[45:47], "big")
        assert cid == base_event.magnitude_currency_id

    def test_counterparty_id_at_offset_99(self, base_event):
        payload = build_extended_payload(base_event)
        assert payload[99:131] == base_event.counterparty_id

    def test_protocol_id_at_offset_131(self, base_event):
        payload = build_extended_payload(base_event)
        pid = int.from_bytes(payload[131:135], "big")
        assert pid == base_event.protocol_id

    def test_context_hash_at_offset_135(self, base_event):
        payload = build_extended_payload(base_event)
        # context_hash = SHA3-256(context) when context is not already 32 bytes
        expected = hashlib.sha3_256(base_event.context).digest()
        assert payload[135:167] == expected

    def test_btcp_version_at_offset_167(self, base_event):
        payload = build_extended_payload(base_event)
        assert payload[167] == BTCP_VERSION

    def test_nonce_at_offset_168(self, base_event):
        payload = build_extended_payload(base_event)
        nonce = int.from_bytes(payload[168:176], "big")
        assert nonce == 0xDEADBEEFCAFEBABE


# ── XOR invariant tests ────────────────────────────────────────────────────────

class TestXORInvariant:
    def test_invariant_holds_for_valid_payload(self, base_event):
        payload = build_extended_payload(base_event)
        sense, antisense = hash_dna_extended(payload)
        assert verify_xor_invariant(payload, sense, antisense)

    def test_invariant_breaks_on_tampered_sense(self, base_event):
        payload = build_extended_payload(base_event)
        sense, antisense = hash_dna_extended(payload)
        # Flip one bit of sense
        tampered_sense = bytes([sense[0] ^ 0x01]) + sense[1:]
        assert not verify_xor_invariant(payload, tampered_sense, antisense)

    def test_invariant_breaks_on_tampered_antisense(self, base_event):
        payload = build_extended_payload(base_event)
        sense, antisense = hash_dna_extended(payload)
        tampered_antisense = bytes([antisense[0] ^ 0x01]) + antisense[1:]
        assert not verify_xor_invariant(payload, sense, tampered_antisense)

    def test_invariant_breaks_on_tampered_payload(self, base_event):
        payload = build_extended_payload(base_event)
        sense, antisense = hash_dna_extended(payload)
        # Tamper with one byte of the payload
        tampered_payload = bytes([payload[0] ^ 0x01]) + payload[1:]
        # The original sense/antisense were for the original payload — they
        # should NOT verify against the tampered payload.
        assert not verify_xor_invariant(tampered_payload, sense, antisense)


# ── Domain separation tests ────────────────────────────────────────────────────

class TestDomainSeparation:
    def test_different_chains_produce_different_hashes(self, base_event):
        e_a = ExtendedBehavioralEvent(**{**base_event.__dict__, "chain_id": 1})
        e_b = ExtendedBehavioralEvent(**{**base_event.__dict__, "chain_id": 137})
        r_a = compute_extended_bh(e_a)
        r_b = compute_extended_bh(e_b)
        assert r_a["sense_hex"] != r_b["sense_hex"]

    def test_different_counterparties_produce_different_hashes(self, base_event):
        e_a = ExtendedBehavioralEvent(**{
            **base_event.__dict__,
            "counterparty_id": b"\x11" * 32,
        })
        e_b = ExtendedBehavioralEvent(**{
            **base_event.__dict__,
            "counterparty_id": b"\x22" * 32,
        })
        r_a = compute_extended_bh(e_a)
        r_b = compute_extended_bh(e_b)
        assert r_a["sense_hex"] != r_b["sense_hex"]

    def test_different_protocols_produce_different_hashes(self, base_event):
        e_a = ExtendedBehavioralEvent(**{**base_event.__dict__, "protocol_id": 1})
        e_b = ExtendedBehavioralEvent(**{**base_event.__dict__, "protocol_id": 2})
        r_a = compute_extended_bh(e_a)
        r_b = compute_extended_bh(e_b)
        assert r_a["sense_hex"] != r_b["sense_hex"]


# ── Replay protection tests ────────────────────────────────────────────────────

class TestReplayProtection:
    def test_different_nonces_produce_different_hashes(self, base_event):
        e_a = ExtendedBehavioralEvent(**{**base_event.__dict__, "nonce": 1})
        e_b = ExtendedBehavioralEvent(**{**base_event.__dict__, "nonce": 2})
        r_a = compute_extended_bh(e_a)
        r_b = compute_extended_bh(e_b)
        assert r_a["sense_hex"] != r_b["sense_hex"]

    def test_generate_nonce_returns_8_byte_value(self):
        n = generate_nonce()
        assert isinstance(n, int)
        assert 0 <= n < 2**64

    def test_generate_nonce_is_cryptographically_random(self):
        # Two consecutive calls should almost certainly differ
        n1 = generate_nonce()
        n2 = generate_nonce()
        assert n1 != n2


# ── All 20 event types ─────────────────────────────────────────────────────────

class TestAllEventTypes:
    @pytest.mark.parametrize("et", list(EventType))
    def test_event_type_hashes_cleanly(self, et, base_event):
        e = ExtendedBehavioralEvent(**{**base_event.__dict__, "event_type": et})
        r = compute_extended_bh(e)
        assert r["valid"]
        assert r["event_type_id"] == int(et)


# ── Validation tests ───────────────────────────────────────────────────────────

class TestValidation:
    def test_rejects_wrong_entity_id_length(self, base_event):
        e = ExtendedBehavioralEvent(**{**base_event.__dict__, "entity_id": b"\x00" * 31})
        with pytest.raises(ValueError, match="entity_id must be 32 bytes"):
            build_extended_payload(e)

    def test_rejects_wrong_block_hash_length(self, base_event):
        e = ExtendedBehavioralEvent(**{**base_event.__dict__, "block_hash": b"\x00" * 31})
        with pytest.raises(ValueError, match="block_hash must be 32 bytes"):
            build_extended_payload(e)

    def test_rejects_wrong_counterparty_id_length(self, base_event):
        e = ExtendedBehavioralEvent(**{
            **base_event.__dict__,
            "counterparty_id": b"\x00" * 31,
        })
        with pytest.raises(ValueError, match="counterparty_id must be 32 bytes"):
            build_extended_payload(e)

    def test_zero_counterparty_id_is_allowed(self, base_event):
        """0×32 counterparty_id is the canonical "no counterparty" marker."""
        e = ExtendedBehavioralEvent(**{
            **base_event.__dict__,
            "counterparty_id": b"\x00" * 32,
        })
        payload = build_extended_payload(e)
        assert payload[99:131] == b"\x00" * 32
