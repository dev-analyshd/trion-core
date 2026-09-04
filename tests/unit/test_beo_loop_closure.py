"""Regression: the sensing→memory loop must close on canonical entity ids.

First-asserts-the-exploit / now-asserts-the-defense (RED-4 / LIVE-2 class):
anima-service._maybe_merge_beo re-hashed 64-hex canonical entity ids
(BH §6 streamer/Rust-indexer form) via sha3(sha3(addr)) while every read
path (resolve_beo, /similarity, enrichment) resolves the same id as-is.
Write key ≠ read key ⇒ ~95% of streamed entities were unreachable on read
(history lookups always fell back to the L3.1 NEUTRAL_PRIOR) — the
CHAIN → TRION → AKASHIC → SIGNAL loop never closed.
"""

import hashlib

import pytest

faiss_service = pytest.importorskip("faiss_service")


RAW = "0xAbC0000000000000000000000000000000000001"  # raw EVM address
RAW_LOWER = RAW.lower()
CANON = hashlib.sha3_256(RAW_LOWER.encode()).hexdigest()  # 64-hex §6 entity_id


def _uncache(addr: str) -> None:
    """Drop any cached resolution so the no-cache code path is exercised."""
    faiss_service.address_to_canonical.pop(addr, None)


def test_exploit_double_hash_is_gone():
    """Old behavior: _maybe_merge_beo('64-hex') returned sha3('64-hex') —
    a key no read path could ever reach. Now it must return the id itself."""
    _uncache(CANON)
    canonical = faiss_service._maybe_merge_beo(CANON, [0.0] * 128)
    assert canonical == CANON, (
        "canonical 64-hex entity id was re-hashed on the write path — "
        f"expected {CANON}, got {canonical}"
    )


def test_raw_address_still_hashes():
    """Raw (non-64-hex) addresses keep the L0.2 sha3 resolution."""
    _uncache(RAW_LOWER)
    canonical = faiss_service._maybe_merge_beo(RAW, [0.0] * 128)
    assert canonical == CANON


def test_write_key_equals_read_key():
    """The loop-closure invariant: for BOTH input forms, the id the write
    path stores under must be the id the read path resolves to."""
    for probe in (CANON, RAW):
        _uncache(probe.lower())
        write_key = faiss_service._maybe_merge_beo(probe, [0.0] * 128)
        read_key = faiss_service.resolve_beo(probe)
        assert write_key == read_key, (
            f"write key {write_key} != read key {read_key} for input {probe!r} "
            "— ledger→FAISS→signal loop severed"
        )
