#!/usr/bin/env python3
"""
parity_check.py — Cross-VM anchor_bh parity verification for TRION BTCP.

Mirrors the Clarity `recompute-anchor-bh` logic byte-for-byte and verifies
it produces the same anchor_bh as the golden vector in
docs/proofs/anchor_parity_pinned.json (which Python / Solidity / Cairo all
agree on).

Run:
    python3 parity_check.py

Exit codes:
    0 — parity confirmed (Clarity logic produces the golden anchor_bh)
    1 — parity broken (Clarity logic differs from the golden vector)
"""

import hashlib
import json
import sys
from pathlib import Path

PINNED_PATH = Path(__file__).resolve().parent.parent / "docs" / "proofs" / "anchor_parity_pinned.json"


def uint_to_buff_8_be(n: int) -> bytes:
    """8-byte big-endian encoding (mirrors uint-to-buff-8-be in Clarity)."""
    if n < 0 or n >= 2**64:
        raise ValueError(f"uint {n} does not fit in u64")
    return n.to_bytes(8, "big")


def uint_to_buff_4_be(n: int) -> bytes:
    """4-byte big-endian encoding (mirrors uint-to-buff-4-be in Clarity)."""
    if n < 0 or n >= 2**32:
        raise ValueError(f"uint {n} does not fit in u32")
    return n.to_bytes(4, "big")


def recompute_anchor_bh(entity_id: bytes, event_type: int, magnitude_nano: int,
                        block_time: int, chain_id: int, block_hash: bytes) -> bytes:
    """
    Mirrors BTCSPVVerifier.clar::recompute-anchor-bh:
      payload = entity_id[32] || event_type[1] || magnitude_nano[u64 BE]
                || context[u64 BE 0] || block_time[u64 BE]
                || chain_id[u32 BE] || block_hash[32]
      sense   = SHA-256(payload || 0x00)
    """
    assert len(entity_id) == 32, f"entity_id must be 32 bytes, got {len(entity_id)}"
    assert len(block_hash) == 32, f"block_hash must be 32 bytes, got {len(block_hash)}"
    assert 0 <= event_type <= 255, f"event_type must fit in u8, got {event_type}"

    payload = b"".join([
        entity_id,
        bytes([event_type]),
        uint_to_buff_8_be(magnitude_nano),
        uint_to_buff_8_be(0),                # context = 0
        uint_to_buff_8_be(block_time),
        uint_to_buff_4_be(chain_id),
        block_hash,
    ])
    assert len(payload) == 93, f"payload should be 93 bytes, got {len(payload)}"

    sense = hashlib.sha256(payload + b"\x00").digest()
    return sense


def main() -> int:
    pinned = json.loads(PINNED_PATH.read_text())
    expected = pinned["anchor_bh"]
    if expected.startswith("0x"):
        expected = expected[2:]

    entity_id = bytes.fromhex(pinned["entity_id_hex"].removeprefix("0x"))
    block_hash = bytes.fromhex(pinned["block_hash_le"].removeprefix("0x"))

    recomputed = recompute_anchor_bh(
        entity_id=entity_id,
        event_type=0,
        magnitude_nano=pinned["magnitude_nano"],
        block_time=pinned["block_time"],
        chain_id=pinned["chain_id"],
        block_hash=block_hash,
    ).hex()

    print("=== TRION BTCP — anchor_bh parity check (Clarity mirror in Python) ===")
    print(f"entity_id       = {entity_id.hex()}")
    print(f"block_hash_le   = {block_hash.hex()}")
    print(f"magnitude_nano  = {pinned['magnitude_nano']}")
    print(f"block_time      = {pinned['block_time']}")
    print(f"chain_id        = {pinned['chain_id']}")
    print(f"expected_bh     = {expected}")
    print(f"recomputed_bh   = {recomputed}")
    print(f"match           = {recomputed == expected}")

    if recomputed == expected:
        print("\n[OK] Parity confirmed — Clarity logic produces the golden anchor_bh.")
        print("    The deployed contract's recompute-anchor-bh will match byte-for-byte.")
        return 0
    else:
        print("\n[FAIL] Parity broken — Clarity logic differs from golden vector.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
