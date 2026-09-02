"""
Cross-language Behavioral Hash vector verification.

Verifies that Python produces the exact digest specified in bh_schema_v1.json.
Run after any change to the 93-byte payload layout or event-type enumeration to
confirm the canonical test vector is still correct.

Usage:
    uv run python tests/bh_cross_language_vector.py
"""
import hashlib
import json
import struct
import sys
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "bh_schema_v1.json"


def compute_bh(entity_id_hex: str, event_type: int, magnitude_norm: float,
               context: int, timestamp_secs: int, chain_id: int,
               block_hash_hex: str) -> tuple[str, str]:
    """Compute dual-strand BH per whitepaper L0.1 §3.1."""
    entity  = bytes.fromhex(entity_id_hex.lstrip("0x").zfill(64))[:32]
    blk     = bytes.fromhex(block_hash_hex.lstrip("0x").zfill(64))[:32]
    mag_nano = int(max(0.0, min(1.0, magnitude_norm)) * 1_000_000_000)

    payload = bytearray()
    payload += entity
    payload += bytes([event_type & 0xFF])
    payload += struct.pack(">Q", mag_nano)
    payload += struct.pack(">Q", context)
    payload += struct.pack(">Q", timestamp_secs)
    payload += struct.pack(">I", chain_id & 0xFFFF_FFFF)
    payload += blk

    assert len(payload) == 93, f"Expected 93-byte payload, got {len(payload)}"

    p0  = bytes(payload) + b"\x00"
    pff = bytes(payload) + b"\xff"

    sense    = hashlib.sha3_256(p0).digest()
    sha3ff   = hashlib.sha3_256(pff).digest()
    antisense = bytes(a ^ (~s & 0xFF) for a, s in zip(sha3ff, sense))

    return sense.hex(), antisense.hex()


def verify_invariant(sense_hex: str, antisense_hex: str,
                     payload: bytes) -> bool:
    """Verify: sense XOR antisense == NOT(SHA3-256(payload || 0xFF))."""
    pff    = payload + b"\xff"
    sha3ff = hashlib.sha3_256(pff).digest()
    sense  = bytes.fromhex(sense_hex)
    anti   = bytes.fromhex(antisense_hex)
    xor    = bytes(s ^ a for s, a in zip(sense, anti))
    not_ff = bytes(~b & 0xFF for b in sha3ff)
    return xor == not_ff


def main() -> int:
    schema = json.loads(SCHEMA_PATH.read_text())
    vec    = schema["test_vector"]

    sense, antisense = compute_bh(
        entity_id_hex  = vec["entity_id_hex"],
        event_type     = vec["event_type"],
        magnitude_norm = vec["magnitude_norm"],
        context        = vec["context"],
        timestamp_secs = vec["timestamp"],
        chain_id       = vec["chain_id"],
        block_hash_hex = vec["block_hash_hex"],
    )

    ok = True
    expected_sense     = vec["expected_sense"]
    expected_antisense = vec["expected_antisense"]

    if sense != expected_sense:
        print(f"FAIL  sense mismatch\n  got : {sense}\n  want: {expected_sense}")
        ok = False
    else:
        print(f"PASS  sense     = {sense}")

    if antisense != expected_antisense:
        print(f"FAIL  antisense mismatch\n  got : {antisense}\n  want: {expected_antisense}")
        ok = False
    else:
        print(f"PASS  antisense = {antisense}")

    # Also verify the dual-strand invariant
    entity  = bytes.fromhex(vec["entity_id_hex"].zfill(64))[:32]
    blk     = bytes.fromhex(vec["block_hash_hex"].zfill(64))[:32]
    mag_n   = int(max(0.0, min(1.0, vec["magnitude_norm"])) * 1_000_000_000)
    payload = bytearray()
    payload += entity
    payload += bytes([vec["event_type"]])
    payload += struct.pack(">Q", mag_n)
    payload += struct.pack(">Q", vec["context"])
    payload += struct.pack(">Q", vec["timestamp"])
    payload += struct.pack(">I", vec["chain_id"])
    payload += blk

    if verify_invariant(sense, antisense, bytes(payload)):
        print("PASS  dual-strand XOR invariant verified")
    else:
        print("FAIL  dual-strand XOR invariant broken")
        ok = False

    # Verify event_type value is a member of the canonical schema enum
    et_names = {e["id"]: e["name"] for e in schema["event_types"]}
    et_val   = vec["event_type"]
    et_name  = et_names.get(et_val)
    if et_name is not None:
        print(f"PASS  event_type {et_val} = {et_name} (canonical schema member)")
    else:
        print(f"FAIL  event_type {et_val} is NOT in the canonical schema enum")
        ok = False

    print()
    if ok:
        print("ALL CHECKS PASSED — canonical test vector is consistent")
    else:
        print("FAILURES DETECTED — update bh_schema_v1.json or fix the implementation")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
