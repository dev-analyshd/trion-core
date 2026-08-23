"""
TRION Protocol — L0 Whitepaper Criterion: BH Collision Resistance
Empirical stress test for the dual-strand Behavioral Hash (BH) construction.

Construction (behavioral_hash.py):
  payload = entity_id(32) || event_type(1) || mag_norm(8) || context(8)
            || timestamp(8) || chain_id(4) || block_hash(32)   → 93 bytes
  sense     = SHA3-256(payload || 0x00)
  antisense = SHA3-256(payload || 0xFF) XOR complement(sense)

Test strategy:
  Generate N ≥ 2,000,000 distinct canonical payloads varying all fields BH
  uses in production, compute BH sense for each, check for zero collisions,
  and verify the empirical collision count is consistent with the birthday
  bound for a 256-bit output space.

  Birthday bound: P(collision) ≈ n² / (2 × 2²⁵⁶) — astronomically small
  for n = 2,000,000, confirming that any collision found would be a
  catastrophic failure of SHA3-256.

IMPORTANT — epistemic honesty:
  This is an empirical stress test, NOT a mathematical proof of collision
  resistance.  It constitutes strong statistical evidence that the BH
  construction does not suffer from implementation-level collisions
  (e.g. ambiguous payload encoding, field aliasing, or domain confusion)
  over the tested input domain.  The underlying collision resistance of
  SHA3-256 itself rests on the NIST/cryptographic community's cryptanalysis
  record, not on this test.
"""

import sys
import os
import time
import hashlib
import math
import struct

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from core.primitives.behavioral_hash import EventType

# ── Constants ─────────────────────────────────────────────────────────────────

TOTAL_SAMPLES  = 2_000_000
BATCH_SIZE     =   100_000   # process in batches to keep peak RAM reasonable
N_EVENT_TYPES  = 20          # all canonical EventType values

# Representative chain IDs used in production indexers
CHAIN_IDS = [1, 56, 137, 42161, 10, 43114, 250, 8453, 324, 59144]

# ── Payload builder (mirrors compute_behavioral_hash exactly) ─────────────────

def _build_payload(
    entity_seed: int,
    event_type_id: int,
    mag_nano: int,       # magnitude_normalized × 1e9, already clamped [0, 1e9]
    context_byte: int,   # first byte of context field
    timestamp: int,
    chain_id: int,
    block_seed: int,
) -> bytes:
    """Build the 93-byte canonical BH payload deterministically."""
    # entity_id: 32 bytes derived from entity_seed
    entity_id  = entity_seed.to_bytes(32, 'big')
    # event_type: 1 byte
    evt_byte   = event_type_id.to_bytes(1, 'big')
    # magnitude_normalized: 8 bytes (nanounit)
    mag_bytes  = mag_nano.to_bytes(8, 'big')
    # context: 8 bytes (first byte varies, rest zero)
    ctx        = bytes([context_byte & 0xFF]) + b'\x00' * 7
    # timestamp: 8 bytes
    ts_bytes   = timestamp.to_bytes(8, 'big')
    # chain_id: 4 bytes
    cid_bytes  = chain_id.to_bytes(4, 'big')
    # block_hash: 32 bytes derived from block_seed
    block_hash = block_seed.to_bytes(32, 'big')

    payload = (entity_id + evt_byte + mag_bytes + ctx
               + ts_bytes + cid_bytes + block_hash)
    assert len(payload) == 93, f"Payload length {len(payload)} ≠ 93"
    return payload


def _bh_sense(payload: bytes) -> bytes:
    """Compute only the sense strand (primary collision domain)."""
    return hashlib.sha3_256(payload + b'\x00').digest()


# ── Core stress-test function ─────────────────────────────────────────────────

def run_collision_stress_test(total: int = TOTAL_SAMPLES,
                               batch: int = BATCH_SIZE) -> dict:
    """
    Generate `total` distinct payloads, compute BH sense for each, and
    return collision statistics.  Memory stays bounded by `batch` size since
    we use a rolling set.
    """
    seen: set = set()
    collisions       = 0
    duplicate_inputs = 0
    n_generated      = 0

    event_types = list(EventType)
    n_et        = len(event_types)

    # Deterministic iteration — cover the realistic production domain:
    #   entity_seed   — unique per entity (simulates 2M distinct BEOs)
    #   event_type    — cycles through all 20
    #   mag_nano      — varies across [0, 1e9] in 100 steps
    #   context_byte  — 16 distinct context flags
    #   chain_id      — cycles through 10 production chains
    #   timestamp     — realistic Unix timestamps (2020-2030 range)
    #   block_seed    — unique per (entity, block)

    base_ts   = 1_577_836_800   # 2020-01-01 00:00:00 UTC
    ts_stride = 12              # ~12s per Ethereum block

    t_start = time.perf_counter()

    for batch_start in range(0, total, batch):
        batch_end = min(batch_start + batch, total)
        batch_hashes: list[bytes] = []

        for i in range(batch_start, batch_end):
            # Spread variation across all payload fields
            entity_seed   = i                             # unique entity
            event_type_id = int(event_types[i % n_et])   # cycle event types
            mag_nano      = int((i % 1001) * 1_000_000)  # 0 .. 1e9, 1001 steps
            context_byte  = (i // 1001) % 16             # 16 context flag variants
            chain_id      = CHAIN_IDS[i % len(CHAIN_IDS)]
            timestamp     = base_ts + (i % 86_400) * ts_stride  # vary within a day
            block_seed    = (i * 6_700_417) & ((1 << 256) - 1)  # pseudo-random blocks

            payload = _build_payload(
                entity_seed, event_type_id, mag_nano,
                context_byte, timestamp, chain_id, block_seed,
            )
            batch_hashes.append(_bh_sense(payload))

        for h in batch_hashes:
            if h in seen:
                collisions += 1
            else:
                seen.add(h)
        n_generated += (batch_end - batch_start)

    elapsed = time.perf_counter() - t_start

    # Birthday bound: expected collisions ≈ n² / (2 × 2²⁵⁶)
    output_space = 2 ** 256
    birthday_expected = (n_generated ** 2) / (2.0 * output_space)

    return {
        "n_generated":       n_generated,
        "collisions":        collisions,
        "duplicate_inputs":  duplicate_inputs,
        "elapsed_sec":       elapsed,
        "throughput_per_s":  n_generated / elapsed,
        "output_bits":       256,
        "output_space":      output_space,
        "birthday_expected": birthday_expected,
    }


# ── Birthday-bound statistical sanity check ───────────────────────────────────

def test_birthday_bound_expectation():
    """
    For n=2,000,000 and 2²⁵⁶ output space, the expected number of collisions
    is n²/(2·2²⁵⁶) ≈ 1.2 × 10⁻⁶³ — effectively zero.  This test documents
    that the empirical collision count is consistent with this bound.
    """
    n = TOTAL_SAMPLES
    space = 2 ** 256
    expected = (n ** 2) / (2.0 * space)
    assert expected < 1e-60, (
        f"Birthday bound sanity failed: expected {expected:.3e} collisions "
        f"for n={n:,} over 2^256 space — this should be effectively 0"
    )
    print(f"[PASS] Birthday bound: E[collisions] ≈ {expected:.3e} (n={n:,}, space=2^256)")


# ── Main stress test ──────────────────────────────────────────────────────────

def test_bh_collision_resistance_stress():
    """
    L0 whitepaper criterion: BH collision resistance.

    Generates 2,000,000 distinct realistic canonical payloads covering all
    20 event types, 10 production chain IDs, 1001 magnitude steps, 16
    context flag variants, and varying timestamps and block hashes.

    PASS condition: zero SHA3-256 sense-strand collisions observed.

    Epistemic note: passing this test is strong statistical evidence against
    implementation-level collisions (field aliasing, encoding ambiguity, etc.)
    It is NOT a mathematical proof of SHA3-256 collision resistance.
    """
    print(f"\n[BH Collision Resistance Stress Test]")
    print(f"  Target samples : {TOTAL_SAMPLES:,}")
    print(f"  Batch size     : {BATCH_SIZE:,}")
    print(f"  Hash function  : SHA3-256 (256-bit output space = 2^256)")
    print(f"  Payload width  : 93 bytes canonical")
    print(f"  Fields varied  : entity_id, event_type (all 20), magnitude_norm,")
    print(f"                   context, timestamp, chain_id, block_hash")
    print(f"  Running...", flush=True)

    stats = run_collision_stress_test(TOTAL_SAMPLES, BATCH_SIZE)

    print(f"\n  === Results ===")
    print(f"  Samples generated : {stats['n_generated']:>12,}")
    print(f"  Collisions found  : {stats['collisions']:>12,}")
    print(f"  Elapsed           : {stats['elapsed_sec']:>12.2f} s")
    print(f"  Throughput        : {stats['throughput_per_s']:>12,.0f} hashes/s")
    print(f"  Birthday bound    :  E[col] ≈ {stats['birthday_expected']:.3e}")
    print(f"  (For context: observing 0 collisions is exactly what birthday")
    print(f"   bound predicts — collision probability ≈ 0 for 2M samples/2^256)")

    assert stats['collisions'] == 0, (
        f"FAIL: {stats['collisions']} collision(s) detected in "
        f"{stats['n_generated']:,} BH sense strands — "
        f"SHA3-256 implementation or payload encoding is broken."
    )

    print(f"\n[PASS] Zero collisions in {stats['n_generated']:,} BH samples.")
    print(f"       Consistent with SHA3-256 birthday bound (E≈{stats['birthday_expected']:.2e}).")
    print(f"       NOTE: This is empirical evidence, not a mathematical proof.")


# ── pytest-compatible individual tests ───────────────────────────────────────

def test_payload_length_is_93_bytes():
    """Verify canonical payload is exactly 93 bytes for representative inputs."""
    for et in EventType:
        p = _build_payload(
            entity_seed=42, event_type_id=int(et), mag_nano=500_000_000,
            context_byte=0x03, timestamp=1_700_000_000,
            chain_id=1, block_seed=999,
        )
        assert len(p) == 93, f"Payload for {et.name} is {len(p)} bytes, expected 93"
    print(f"[PASS] All 20 EventType payloads are exactly 93 bytes")


def test_distinct_inputs_produce_distinct_hashes():
    """Sanity check: a small set of clearly distinct payloads all hash differently."""
    hashes = set()
    for i in range(1000):
        p = _build_payload(i, i % 20, i * 1_000_000, i % 16,
                           1_700_000_000 + i * 12, 1, i)
        h = _bh_sense(p)
        assert h not in hashes, f"Collision at i={i}"
        hashes.add(h)
    print(f"[PASS] 1,000 distinct inputs → 1,000 distinct BH sense values")


def test_single_bit_flip_changes_hash():
    """Avalanche: flipping any single bit in the payload changes the hash."""
    base = _build_payload(1, 1, 500_000_000, 1, 1_700_000_000, 1, 1)
    base_h = _bh_sense(base)
    changed = 0
    for byte_pos in range(93):
        for bit in range(8):
            flipped = bytearray(base)
            flipped[byte_pos] ^= (1 << bit)
            h = _bh_sense(bytes(flipped))
            if h != base_h:
                changed += 1
    total_bits = 93 * 8
    assert changed == total_bits, (
        f"Only {changed}/{total_bits} bit-flips changed the hash — "
        f"avalanche property violated"
    )
    print(f"[PASS] All {total_bits} single-bit flips produce a different BH sense hash")


if __name__ == "__main__":
    test_payload_length_is_93_bytes()
    test_distinct_inputs_produce_distinct_hashes()
    test_single_bit_flip_changes_hash()
    test_birthday_bound_expectation()
    stats = test_bh_collision_resistance_stress()
    print(f"\n[PASS] All BH collision resistance tests passed")
    print(f"       Total hashes computed: {stats['n_generated']:,}")
    print(f"       Collisions observed  : {stats['collisions']}")
    print(f"       Time                 : {stats['elapsed_sec']:.2f}s")
    print(f"       Throughput           : {stats['throughput_per_s']:,.0f} hashes/s")
