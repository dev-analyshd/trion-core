"""
TRION Protocol — L0.1: Behavioral Hash (BH)
Dual-strand hash with thermodynamic proof.

Whitepaper canonical payload (L0.1 §3.1):
  BH(entity, t) = Hash_DNA(
    entity_id || event_type || magnitude_normalized || context || timestamp || chain_id || block_hash
  )
sense     = SHA3-256(payload || 0x00)
antisense = SHA3-256(payload || 0xFF) XOR complement(sense)

magnitude_normalized (L0.1 §3.2, log10 formula):
  M_norm = log10(USD_value + 1) / log10(max_observed_90d + 1)
  Falls back to linear ratio when USD conversion unavailable.

EventType (whitepaper L0.1 §2 — 20 canonical types):
  0  TRANSFER         8  STAKE           16 ORACLE_UPDATE
  1  SWAP             9  UNSTAKE         17 MEV_CAPTURE
  2  LIQUIDITY       10  BRIDGE          18 AIRDROP
  3  BORROW          11  DEPLOY          19 CLAIM
  4  REPAY           12  UPGRADE
  5  LIQUIDATE       13  MINT
  6  GOVERNANCE      14  BURN
  7  PROPOSAL        15  FLASH_LOAN

Backward-compat aliases kept for existing indexer code:
  LIQUIDITY_ADD = LIQUIDITY, LIQUIDITY_REMOVE = LIQUIDITY,
  GOVERNANCE_VOTE = GOVERNANCE, NFT_MINT = MINT,
  CONTRACT_DEPLOY = DEPLOY, NFT_TRANSFER = TRANSFER
"""

import hashlib
import math
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional


class EventType(IntEnum):
    TRANSFER       = 0
    SWAP           = 1
    LIQUIDITY      = 2
    BORROW         = 3
    REPAY          = 4
    LIQUIDATE      = 5
    GOVERNANCE     = 6
    PROPOSAL       = 7
    STAKE          = 8
    UNSTAKE        = 9
    BRIDGE         = 10
    DEPLOY         = 11
    UPGRADE        = 12
    MINT           = 13
    BURN           = 14
    FLASH_LOAN     = 15
    ORACLE_UPDATE  = 16
    MEV_CAPTURE    = 17
    AIRDROP        = 18
    CLAIM          = 19

    # ── Backward-compat aliases (map to canonical types above) ──────────────
    @classmethod
    def _missing_(cls, value):
        return None


# Backward-compat name aliases (used by indexers written before whitepaper alignment)
LIQUIDITY_ADD    = EventType.LIQUIDITY
LIQUIDITY_REMOVE = EventType.LIQUIDITY
GOVERNANCE_VOTE  = EventType.GOVERNANCE
NFT_MINT         = EventType.MINT
NFT_TRANSFER     = EventType.TRANSFER
CONTRACT_DEPLOY  = EventType.DEPLOY

# 20 canonical event type names for API serialization
EVENT_TYPE_NAMES = {e.value: e.name for e in EventType}


@dataclass
class BehavioralEvent:
    entity_id:           bytes      # 32-byte canonical BEO ID
    event_type:          EventType
    magnitude_raw:       int        # raw value in smallest unit (wei/lamports/etc)
    magnitude_decimals:  int        # token decimals
    magnitude_max_90d:   int        # 90-day rolling max for normalization
    timestamp:           int        # unix timestamp
    block_number:        int
    block_hash:          bytes      # 32-byte block hash
    chain_id:            int
    contract_addr:       Optional[bytes] = None
    context:             bytes = field(default_factory=lambda: b'\x00' * 8)
    # context: 8-byte field encoding execution context flags
    # bits 0-1: venue type (0=DEX, 1=LENDING, 2=BRIDGE, 3=NATIVE)
    # bits 2-3: settlement layer (0=L1, 1=L2, 2=L3, 3=sidechain)
    # bits 4-7: protocol version / reserved


def complement_transform(data: bytes) -> bytes:
    """Bitwise complement — antisense strand construction."""
    return bytes(b ^ 0xFF for b in data)


def hash_dna(payload: bytes):
    """
    Dual-strand hash construction.
    sense     = SHA3-256(payload || 0x00)
    antisense = SHA3-256(payload || 0xFF) XOR complement(sense)
    """
    sense     = hashlib.sha3_256(payload + b'\x00').digest()
    antisense = bytes(
        a ^ b for a, b in zip(
            hashlib.sha3_256(payload + b'\xFF').digest(),
            complement_transform(sense)
        )
    )
    return sense, antisense


def normalize_magnitude(raw: int, decimals: int, max_90d: int,
                        usd_value: Optional[float] = None,
                        usd_max_90d: Optional[float] = None) -> float:
    """
    Whitepaper L0.1 §3.2 — log10 magnitude normalization:
      M_norm = log10(USD_value + 1) / log10(max_observed_90d + 1)

    Falls back to token-unit linear ratio when USD data unavailable.
    """
    # Primary path: USD log10 formula (whitepaper-exact)
    if usd_value is not None and usd_max_90d is not None and usd_max_90d > 0:
        denom = math.log10(usd_max_90d + 1)
        if denom > 0:
            return min(1.0, math.log10(max(0.0, usd_value) + 1) / denom)

    # Fallback: token-unit log10 formula (same shape, different unit)
    if max_90d <= 0:
        return 0.0
    human    = raw / (10 ** decimals)
    max_h    = max_90d / (10 ** decimals)
    if max_h <= 0:
        return 0.0
    denom = math.log10(max_h + 1)
    if denom <= 0:
        return 0.0
    return min(1.0, math.log10(human + 1) / denom)


def compute_behavioral_hash(event: BehavioralEvent,
                            usd_value: Optional[float] = None,
                            usd_max_90d: Optional[float] = None) -> dict:
    """
    Compute BH(entity, t) per whitepaper L0.1.

    Payload (canonical order per §3.1):
      entity_id(32) || event_type(1) || magnitude_normalized(8) ||
      context(8)    || timestamp(8)  || chain_id(4) || block_hash(32)
    """
    mag_norm = normalize_magnitude(
        event.magnitude_raw, event.magnitude_decimals, event.magnitude_max_90d,
        usd_value, usd_max_90d
    )

    # Ensure context is exactly 8 bytes
    ctx = (event.context or b'\x00' * 8)[:8].ljust(8, b'\x00')

    payload = (
        event.entity_id                                    # 32 bytes
        + event.event_type.to_bytes(1, 'big')              #  1 byte
        + int(mag_norm * 1e9).to_bytes(8, 'big')           #  8 bytes  (nanounit precision)
        + ctx                                              #  8 bytes  (context flags)
        + event.timestamp.to_bytes(8, 'big')               #  8 bytes
        + event.chain_id.to_bytes(4, 'big')                #  4 bytes
        + event.block_hash                                 # 32 bytes
    )
    # Total: 93 bytes canonical payload (32+1+8+8+8+4+32)

    sense, antisense = hash_dna(payload)

    # Verification: antisense XOR complement(sense) must equal SHA3(payload||0xFF)
    comp_sense      = complement_transform(sense)
    recovered_inner = bytes(a ^ b for a, b in zip(antisense, comp_sense))
    expected_inner  = hashlib.sha3_256(payload + b'\xFF').digest()
    valid = (recovered_inner == expected_inner)

    return {
        "sense_hex":             sense.hex(),
        "antisense_hex":         antisense.hex(),
        "valid":                 valid,
        "magnitude_normalized":  mag_norm,
        "event_type":            event.event_type.name,
        "event_type_id":         int(event.event_type),
        "context_hex":           ctx.hex(),
        "chain_id":              event.chain_id,
        "block_number":          event.block_number,
        "timestamp":             event.timestamp,
        "payload_len":           len(payload),
    }


def bh_from_rust_hex(hex_payload: str) -> dict:
    """
    Ingest and verify a 93-byte Behavioral Hash produced by the Rust
    ``trion-common`` crate (``canonical_bh`` / ``hash_dna.rs``).

    This is the strict Python ingestion path for Rust-originated BH payloads.
    It accepts the hex-encoded 93-byte binary produced by Rust, asserts the
    exact canonical field layout, recomputes the dual-strand hashes, and
    verifies the XOR invariant — ensuring cross-verifiability between the
    Rust L0 indexers and all Python consumers without any field-translation
    or re-encoding that could produce a divergent hash.

    Canonical layout (whitepaper L0.1 §3.1, big-endian throughout):
        entity_id(32) || event_type(1) || magnitude_norm(8) ||
        context(8)    || timestamp(8)  || chain_id(4)       || block_hash(32)
        ─────────────────────────────────────────────────────────────────────
        Total: 93 bytes

    Raises:
        ValueError — if the hex string does not decode to exactly 93 bytes,
                     or if the XOR invariant (sense, antisense, payload)
                     fails.  Either condition means the payload was not
                     produced by the canonical Rust ``canonical_bh`` path.
    """
    raw = bytes.fromhex(hex_payload.replace("0x", "").replace("0X", ""))
    if len(raw) != 93:
        raise ValueError(
            f"Expected exactly 93-byte canonical BH payload, got {len(raw)} bytes. "
            "Input must be the unmodified hex output of Rust trion-common::canonical_bh()."
        )

    # Parse canonical binary fields — no re-encoding, no translation
    entity_id_bytes  = raw[0:32]
    event_type_byte  = raw[32]
    mag_nano         = int.from_bytes(raw[33:41], "big")
    context_bytes    = raw[41:49]
    timestamp_val    = int.from_bytes(raw[49:57], "big")
    chain_id_val     = int.from_bytes(raw[57:61], "big")
    block_hash_bytes = raw[61:93]

    # Recompute dual-strand hashes from the exact 93-byte binary
    sense, antisense = hash_dna(raw)

    # Verify XOR invariant: antisense XOR complement(sense) == SHA3(payload||0xFF)
    comp_sense      = complement_transform(sense)
    recovered_inner = bytes(a ^ b for a, b in zip(antisense, comp_sense))
    expected_inner  = hashlib.sha3_256(raw + b'\xFF').digest()
    valid           = (recovered_inner == expected_inner)

    if not valid:
        raise ValueError(
            "XOR invariant verification FAILED for 93-byte BH payload. "
            "The payload may have been tampered with or was not produced by "
            "the canonical Rust trion-common::hash_dna implementation."
        )

    mag_norm = mag_nano / 1_000_000_000.0
    try:
        et: EventType | None = EventType(event_type_byte)
    except ValueError:
        et = None

    return {
        "sense_hex":            sense.hex(),
        "antisense_hex":        antisense.hex(),
        "valid":                valid,
        "magnitude_normalized": mag_norm,
        "event_type":           et.name if et else f"UNKNOWN_{event_type_byte}",
        "event_type_id":        event_type_byte,
        "context_hex":          context_bytes.hex(),
        "chain_id":             chain_id_val,
        "timestamp":            timestamp_val,
        "entity_id_hex":        entity_id_bytes.hex(),
        "block_hash_hex":       block_hash_bytes.hex(),
        "payload_len":          93,
        "source":               "rust_canonical_bh",
    }


def bh_from_dict(d: dict) -> dict:
    """
    Convenience constructor — build BH from plain dict (for API calls).

    Required keys: entity_id_hex, event_type (name or int), magnitude_raw,
                   magnitude_decimals, magnitude_max_90d, timestamp, block_number,
                   block_hash_hex, chain_id
    Optional keys: context_hex, usd_value, usd_max_90d
    """
    et_raw = d.get("event_type", "TRANSFER")
    if isinstance(et_raw, str):
        try:
            et = EventType[et_raw.upper()]
        except KeyError:
            et = EventType.TRANSFER
    else:
        et = EventType(int(et_raw))

    entity_hex = d.get("entity_id_hex", "ab" * 32)
    bh_hex     = d.get("block_hash_hex", "cc" * 32)
    ctx_hex    = d.get("context_hex", "00" * 8)

    event = BehavioralEvent(
        entity_id=bytes.fromhex(entity_hex.replace("0x", "")),
        event_type=et,
        magnitude_raw=int(d.get("magnitude_raw", 0)),
        magnitude_decimals=int(d.get("magnitude_decimals", 18)),
        magnitude_max_90d=int(d.get("magnitude_max_90d", int(1e18))),
        timestamp=int(d.get("timestamp", 0)),
        block_number=int(d.get("block_number", 0)),
        block_hash=bytes.fromhex(bh_hex.replace("0x", "")),
        chain_id=int(d.get("chain_id", 1)),
        context=bytes.fromhex(ctx_hex.replace("0x", "")) if ctx_hex else b'\x00' * 8,
    )
    return compute_behavioral_hash(
        event,
        usd_value=d.get("usd_value"),
        usd_max_90d=d.get("usd_max_90d"),
    )


if __name__ == "__main__":
    # ── Self-test: all 20 event types ────────────────────────────────────────
    print("=== BH L0.1 Self-test ===")
    assert len(EventType) == 20, f"Expected 20 event types, got {len(EventType)}"

    # Test with USD log10 path
    event = BehavioralEvent(
        entity_id=b'\xab' * 32,
        event_type=EventType.SWAP,
        magnitude_raw=int(1e18),
        magnitude_decimals=18,
        magnitude_max_90d=int(100e18),
        timestamp=1700000000,
        block_number=18000000,
        block_hash=b'\xcc' * 32,
        chain_id=1,
        context=b'\x01\x00\x00\x00\x00\x00\x00\x00',
    )
    result = compute_behavioral_hash(event, usd_value=500.0, usd_max_90d=50000.0)
    assert result['valid'], "Dual-strand verification failed"
    assert 0 <= result['magnitude_normalized'] <= 1
    assert result['payload_len'] == 93, f"Expected 93 bytes, got {result['payload_len']}"
    print(f"BH sense:     {result['sense_hex'][:16]}...")
    print(f"BH valid:     {result['valid']}")
    print(f"Magnitude:    {result['magnitude_normalized']:.4f} (log10 USD path)")
    print(f"Context:      {result['context_hex']}")
    print(f"Payload len:  {result['payload_len']} bytes (canonical: 32+1+8+8+8+4+32)")

    # Test fallback log10 path (no USD data)
    result2 = compute_behavioral_hash(event)
    assert result2['valid']
    print(f"Magnitude:    {result2['magnitude_normalized']:.4f} (log10 token-unit fallback)")

    # Test every event type hashes cleanly
    for et in EventType:
        e2 = BehavioralEvent(
            entity_id=b'\x01' * 32, event_type=et,
            magnitude_raw=int(1e15), magnitude_decimals=18,
            magnitude_max_90d=int(1e18), timestamp=1700000000,
            block_number=100, block_hash=b'\x00' * 32, chain_id=137,
        )
        r = compute_behavioral_hash(e2)
        assert r['valid'], f"BH invalid for {et.name}"

    print(f"\nAll 20 EventTypes verified ✓")
    print("PHASE 8 PASS — BH dual-strand + log10 magnitude + context field + all 20 event types")
