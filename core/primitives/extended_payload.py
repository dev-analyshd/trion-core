"""
TRION Protocol — L0.1 Extended Behavioral Hash Payload (v2)
============================================================

Whitepaper "Protocol Whitepaper" specifies an OPTIONAL extended payload
format with replay protection and cross-chain domain separation:

    DOMAIN_SEPARATOR || entity_id || event_type_id || magnitude_normalized ||
    magnitude_currency_id || timestamp || block_number || block_hash ||
    chain_id || counterparty_id || protocol_id || context_hash ||
    btcp_version || nonce

This module implements that extended format. The 93-byte canonical payload
(see `core/primitives/behavioral_hash.py` and `config/bh_schema_v1.json`)
remains the DEFAULT for backward compatibility and cross-component hash
verification. The extended format is opt-in per chain/protocol that needs
the additional replay-protection and counterparty-tracking fields.

Layout (big-endian throughout):
    DOMAIN_SEPARATOR     4 bytes   — magic 0x54524F4E ("TRON") + version byte
    entity_id           32 bytes   — canonical BEO identifier
    event_type_id        1 byte    — 0..19 (matches L0.1 EventType)
    magnitude_norm       8 bytes   — uint64, normalized × 1e9
    magnitude_currency_id 2 bytes  — ISO 4217-like numeric code (0=USD, 1=ETH, …)
    timestamp            8 bytes   — uint64, unix seconds
    block_number         8 bytes   — uint64
    block_hash          32 bytes   — from chain header
    chain_id             4 bytes   — TRION internal chain ID
    counterparty_id     32 bytes   — BEO identifier of the other side (or 0×32)
    protocol_id          4 bytes   — TRION-registered protocol ID
    context_hash        32 bytes   — SHA3-256 of arbitrary context (calldata, etc.)
    btcp_version         1 byte    — BTCP protocol version (1..255)
    nonce                8 bytes   — uint64, replay-protection nonce
    ────────────────────────────────────────────────────────────────────────
    Total:             144 bytes

The dual-strand hash construction is identical to the 93-byte payload:
    sense     = SHA3-256(payload || 0x00)
    antisense = SHA3-256(payload || 0xFF) XOR complement(sense)

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import hashlib
import math
import os
import struct
from dataclasses import dataclass, field
from typing import Optional

from core.primitives.behavioral_hash import (
    EventType,
    complement_transform,
    normalize_magnitude,
)


# ── Constants ──────────────────────────────────────────────────────────────────

# Magic 4 bytes "TRON" (0x54 0x52 0x4F 0x4E) — domain separator that
# distinguishes TRION BH payloads from any other SHA3-256 input.  This
# prevents hash collisions across protocols that might use a similar
# payload layout.
DOMAIN_MAGIC: bytes = b"TRON"

# BTCP version byte (currently 1).  Increment when the BTCP transport
# format changes — consumers MUST reject payloads with versions they
# don't understand.
BTCP_VERSION: int = 1

# Total length of the extended payload.
#   DOMAIN_MAGIC(4) + entity_id(32) + event_type(1) + magnitude_norm(8) +
#   magnitude_currency_id(2) + timestamp(8) + block_number(8) + block_hash(32) +
#   chain_id(4) + counterparty_id(32) + protocol_id(4) + context_hash(32) +
#   btcp_version(1) + nonce(8) = 176 bytes
EXTENDED_PAYLOAD_LEN: int = 176

# Magic prefix is DOMAIN_MAGIC (4 bytes) only; the BTCP version is encoded
# as a separate 1-byte field near the end of the payload.
_HEADER_LEN: int = 4  # DOMAIN_MAGIC only


# ── Data Model ─────────────────────────────────────────────────────────────────

@dataclass
class ExtendedBehavioralEvent:
    """
    Fields required for the extended 144-byte BH payload.

    All multi-byte integer fields are encoded big-endian.  `counterparty_id`
    MAY be all-zero bytes when no counterparty applies (e.g. MINT/BURN with
    no recipient); consumers MUST treat 0×32 as "no counterparty".
    """
    entity_id:            bytes       # 32 bytes — BEO ID
    event_type:           EventType
    magnitude_raw:        int
    magnitude_decimals:   int
    magnitude_max_90d:    int
    magnitude_currency_id: int        # 2 bytes — ISO 4217-like numeric
    timestamp:            int
    block_number:         int
    block_hash:           bytes       # 32 bytes
    chain_id:             int
    counterparty_id:      bytes = field(default_factory=lambda: b"\x00" * 32)
    protocol_id:          int = 0
    context:              bytes = field(default_factory=lambda: b"\x00" * 8)
    btcp_version:         int = BTCP_VERSION
    nonce:                int = 0
    usd_value:            Optional[float] = None
    usd_max_90d:          Optional[float] = None


# ── Payload Construction ──────────────────────────────────────────────────────

def _ctx_hash(context: bytes) -> bytes:
    """Hash arbitrary context bytes into a 32-byte field.

    If the caller already passes a 32-byte value, it is used as-is (this
    allows pre-computed context commitments).  Otherwise SHA3-256 is
    applied.  The 8-byte `context` field from the v1 schema is implicitly
    supported by hashing it; the result is stored in `context_hash`.
    """
    if len(context) == 32:
        return context
    return hashlib.sha3_256(context or b"\x00").digest()


def build_extended_payload(event: ExtendedBehavioralEvent) -> bytes:
    """
    Construct the 144-byte extended BH payload.

    The payload is laid out exactly as documented in the module docstring.
    All integer fields are big-endian.  Magnitude is normalized using the
    same log10 formula as the v1 payload (see `normalize_magnitude`).
    """
    if len(event.entity_id) != 32:
        raise ValueError(f"entity_id must be 32 bytes, got {len(event.entity_id)}")
    if len(event.block_hash) != 32:
        raise ValueError(f"block_hash must be 32 bytes, got {len(event.block_hash)}")
    if len(event.counterparty_id) != 32:
        raise ValueError(
            f"counterparty_id must be 32 bytes (use b'\\x00'*32 if none), got "
            f"{len(event.counterparty_id)}"
        )

    mag_norm = normalize_magnitude(
        event.magnitude_raw,
        event.magnitude_decimals,
        event.magnitude_max_90d,
        event.usd_value,
        event.usd_max_90d,
    )

    ctx_hash = _ctx_hash(event.context)

    payload = (
        DOMAIN_MAGIC                                            #  4 bytes
        + event.entity_id                                       # 32 bytes
        + event.event_type.to_bytes(1, "big")                   #  1 byte
        + int(mag_norm * 1e9).to_bytes(8, "big")                #  8 bytes
        + int(event.magnitude_currency_id).to_bytes(2, "big")   #  2 bytes
        + int(event.timestamp).to_bytes(8, "big")               #  8 bytes
        + int(event.block_number).to_bytes(8, "big")            #  8 bytes
        + event.block_hash                                      # 32 bytes
        + int(event.chain_id).to_bytes(4, "big")                #  4 bytes
        + event.counterparty_id                                 # 32 bytes
        + int(event.protocol_id).to_bytes(4, "big")             #  4 bytes
        + ctx_hash                                              # 32 bytes
        + int(event.btcp_version).to_bytes(1, "big")            #  1 byte
        + int(event.nonce).to_bytes(8, "big")                   #  8 bytes
    )

    if len(payload) != EXTENDED_PAYLOAD_LEN:
        raise RuntimeError(
            f"Internal error: extended payload is {len(payload)} bytes, "
            f"expected {EXTENDED_PAYLOAD_LEN}"
        )
    return payload


def hash_dna_extended(payload: bytes) -> tuple[bytes, bytes]:
    """
    Dual-strand hash construction for the extended payload.

    Identical to the v1 construction:
        sense     = SHA3-256(payload || 0x00)
        antisense = SHA3-256(payload || 0xFF) XOR complement(sense)
    """
    sense     = hashlib.sha3_256(payload + b"\x00").digest()
    antisense = bytes(
        a ^ b for a, b in zip(
            hashlib.sha3_256(payload + b"\xFF").digest(),
            complement_transform(sense),
        )
    )
    return sense, antisense


def verify_xor_invariant(payload: bytes, sense: bytes, antisense: bytes) -> bool:
    """
    Verify the dual-strand XOR invariant.

    Returns True iff `antisense XOR complement(sense) == SHA3-256(payload || 0xFF)`.
    """
    expected_inner = hashlib.sha3_256(payload + b"\xFF").digest()
    recovered      = bytes(a ^ b for a, b in zip(antisense, complement_transform(sense)))
    return recovered == expected_inner


# ── Public API ─────────────────────────────────────────────────────────────────

def compute_extended_bh(event: ExtendedBehavioralEvent) -> dict:
    """
    Compute the extended 144-byte BH for an event.

    Returns a dict with the same key shape as `compute_behavioral_hash`
    plus the extended fields (counterparty_id, protocol_id, btcp_version,
    nonce, magnitude_currency_id, context_hash, payload_version).
    """
    payload = build_extended_payload(event)
    sense, antisense = hash_dna_extended(payload)
    valid = verify_xor_invariant(payload, sense, antisense)

    # Field offsets (see layout table in module docstring):
    #   DOMAIN_MAGIC[0:4] entity_id[4:36] event_type[36:37] mag_norm[37:45]
    #   mag_currency[45:47] timestamp[47:55] block_number[55:63] block_hash[63:95]
    #   chain_id[95:99] counterparty_id[99:131] protocol_id[131:135]
    #   context_hash[135:167] btcp_version[167:168] nonce[168:176]
    mag_norm = int.from_bytes(payload[37:45], "big") / 1e9

    return {
        "payload_version":         "v2_extended",
        "payload_len":             EXTENDED_PAYLOAD_LEN,
        "sense_hex":               sense.hex(),
        "antisense_hex":           antisense.hex(),
        "valid":                   valid,
        "magnitude_normalized":    mag_norm,
        "magnitude_currency_id":   int.from_bytes(payload[45:47], "big"),
        "event_type":              event.event_type.name,
        "event_type_id":           int(event.event_type),
        "timestamp":               int.from_bytes(payload[47:55], "big"),
        "block_number":            int.from_bytes(payload[55:63], "big"),
        "chain_id":                int.from_bytes(payload[95:99], "big"),
        "counterparty_id_hex":     payload[99:131].hex(),
        "protocol_id":             int.from_bytes(payload[131:135], "big"),
        "context_hash_hex":        payload[135:167].hex(),
        "btcp_version":            payload[167],
        "nonce":                   int.from_bytes(payload[168:176], "big"),
        "domain_separator":        payload[0:4].hex(),
    }


def generate_nonce() -> int:
    """
    Generate a cryptographically-random 8-byte nonce.

    Used when the caller does not have a deterministic nonce source (e.g.
    sequential per-block counter).  Uses `os.urandom` for CSPRNG quality.
    """
    return int.from_bytes(os.urandom(8), "big")


# ── Self-test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Extended BH Payload v2 Self-test ===")

    evt = ExtendedBehavioralEvent(
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
        nonce=generate_nonce(),
        usd_value=500.0,
        usd_max_90d=50_000.0,
    )

    result = compute_extended_bh(evt)
    assert result["valid"], "XOR invariant verification FAILED"
    assert result["payload_len"] == EXTENDED_PAYLOAD_LEN
    assert result["domain_separator"] == DOMAIN_MAGIC.hex()

    # Every event type should hash cleanly
    for et in EventType:
        e2 = ExtendedBehavioralEvent(
            entity_id=b"\x01" * 32,
            event_type=et,
            magnitude_raw=int(1e15),
            magnitude_decimals=18,
            magnitude_max_90d=int(1e18),
            magnitude_currency_id=1,
            timestamp=1_700_000_000,
            block_number=100,
            block_hash=b"\x00" * 32,
            chain_id=137,
            counterparty_id=b"\x00" * 32,
            protocol_id=1,
            context=b"\x00" * 8,
            nonce=generate_nonce(),
        )
        r = compute_extended_bh(e2)
        assert r["valid"], f"XOR invariant failed for {et.name}"

    # Replay protection: same payload with different nonce produces different hash
    base_nonce = generate_nonce()
    e_a = ExtendedBehavioralEvent(
        entity_id=b"\x11" * 32, event_type=EventType.TRANSFER,
        magnitude_raw=int(1e18), magnitude_decimals=18, magnitude_max_90d=int(1e19),
        magnitude_currency_id=0, timestamp=1_700_000_000, block_number=100,
        block_hash=b"\x22" * 32, chain_id=1, counterparty_id=b"\x33" * 32,
        protocol_id=1, context=b"\x00" * 8, nonce=base_nonce,
    )
    e_b = ExtendedBehavioralEvent(
        entity_id=b"\x11" * 32, event_type=EventType.TRANSFER,
        magnitude_raw=int(1e18), magnitude_decimals=18, magnitude_max_90d=int(1e19),
        magnitude_currency_id=0, timestamp=1_700_000_000, block_number=100,
        block_hash=b"\x22" * 32, chain_id=1, counterparty_id=b"\x33" * 32,
        protocol_id=1, context=b"\x00" * 8, nonce=base_nonce + 1,
    )
    r_a = compute_extended_bh(e_a)
    r_b = compute_extended_bh(e_b)
    assert r_a["sense_hex"] != r_b["sense_hex"], "Nonce did not change the hash!"

    # Cross-chain domain separation: same entity/event on different chains
    # produces different hashes (chain_id field is part of the payload).
    e_chain_a = ExtendedBehavioralEvent(
        entity_id=b"\x44" * 32, event_type=EventType.BRIDGE,
        magnitude_raw=int(1e18), magnitude_decimals=18, magnitude_max_90d=int(1e19),
        magnitude_currency_id=0, timestamp=1_700_000_000, block_number=100,
        block_hash=b"\x55" * 32, chain_id=1, counterparty_id=b"\x66" * 32,
        protocol_id=1, context=b"\x00" * 8, nonce=1,
    )
    e_chain_b = ExtendedBehavioralEvent(
        entity_id=b"\x44" * 32, event_type=EventType.BRIDGE,
        magnitude_raw=int(1e18), magnitude_decimals=18, magnitude_max_90d=int(1e19),
        magnitude_currency_id=0, timestamp=1_700_000_000, block_number=100,
        block_hash=b"\x55" * 32, chain_id=137, counterparty_id=b"\x66" * 32,
        protocol_id=1, context=b"\x00" * 8, nonce=1,
    )
    r_ca = compute_extended_bh(e_chain_a)
    r_cb = compute_extended_bh(e_chain_b)
    assert r_ca["sense_hex"] != r_cb["sense_hex"], "Chain ID did not change the hash!"

    print(f"  payload_len:    {result['payload_len']} bytes (extended v2)")
    print(f"  domain_sep:     {result['domain_separator']}")
    print(f"  sense:          {result['sense_hex'][:16]}...")
    print(f"  XOR invariant:  {result['valid']}")
    print(f"  All 20 EventTypes verified")
    print(f"  Replay protection: nonce sensitivity verified")
    print(f"  Cross-chain domain separation: chain_id sensitivity verified")
    print("PHASE 3 PASS — Extended v2 BH payload with replay protection & domain separation")
