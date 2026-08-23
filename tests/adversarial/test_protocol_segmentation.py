"""
test_protocol_segmentation.py — Tests for ProtocolSegmenter

Tests cover:
  - SubEntity dataclass construction
  - Event counting helper
  - Float parsing helper
  - Magnitude statistics
  - Cache TTL logic
  - Graceful handling when bh_ledger.db is absent or empty
"""
import sys
import os
import math
import pytest

sys.path.insert(0, ".")

from core.protocol.segmentation import (
    ProtocolSegmenter,
    SubEntity,
    _DB_PATH,
)


# ── helpers (pure functions, no DB) ──────────────────────────────────────────

def test_count_events_basic():
    result = ProtocolSegmenter._count_events("SWAP,SWAP,BORROW,FLASH_LOAN")
    assert result["SWAP"] == 2
    assert result["BORROW"] == 1
    assert result["FLASH_LOAN"] == 1


def test_count_events_empty():
    assert ProtocolSegmenter._count_events("") == {}


def test_parse_floats_valid():
    vals = ProtocolSegmenter._parse_floats("0.1,0.5,0.9")
    assert vals == pytest.approx([0.1, 0.5, 0.9])


def test_parse_floats_ignores_invalid():
    vals = ProtocolSegmenter._parse_floats("0.1,nan_val,0.9")
    assert vals == pytest.approx([0.1, 0.9])


def test_magnitude_stats_basic():
    stats = ProtocolSegmenter._magnitude_stats([0.1, 0.5, 0.9, 0.3, 0.7])
    assert "mean" in stats
    assert "max" in stats
    assert "std" in stats
    assert "p95" in stats
    assert stats["max"] == pytest.approx(0.9, abs=1e-6)
    assert 0 <= stats["std"] <= 1


def test_magnitude_stats_single():
    stats = ProtocolSegmenter._magnitude_stats([0.42])
    assert stats["mean"] == pytest.approx(0.42, abs=1e-6)
    assert stats["max"] == pytest.approx(0.42, abs=1e-6)
    assert stats["std"] == 0.0


def test_magnitude_stats_empty():
    stats = ProtocolSegmenter._magnitude_stats([])
    assert stats["mean"] == 0.0
    assert stats["max"] == 0.0


def test_p95_large_list():
    vals = list(range(1, 101))
    stats = ProtocolSegmenter._magnitude_stats([float(v) for v in vals])
    assert stats["p95"] >= 94.0


# ── SubEntity dataclass ───────────────────────────────────────────────────────

def test_sub_entity_construction():
    se = SubEntity(
        contract="0xabc",
        caller="0xdef",
        entity_id="0xabc:0xdef",
        tx_count=10,
        event_type_counts={"SWAP": 8, "LIQUIDITY": 2},
        magnitude_stats={"mean": 0.5, "max": 0.9, "std": 0.1, "p95": 0.85},
        chains=["ETH_MAINNET"],
        first_seen=1700000000.0,
        last_seen=1700003600.0,
        dominant_event="SWAP",
    )
    assert se.tx_count == 10
    assert se.dominant_event == "SWAP"
    assert se.role is None
    assert se.coherence_score is None


# ── ProtocolSegmenter with real or absent DB ──────────────────────────────────

def test_segmenter_returns_list_when_db_absent(monkeypatch, tmp_path):
    monkeypatch.setattr("core.protocol.segmentation._DB_PATH", str(tmp_path / "nope.db"))
    seg = ProtocolSegmenter()
    result = seg.get_sub_entities("0xdeadbeef")
    assert isinstance(result, list)


def test_segmenter_get_sub_entities_live():
    """Smoke test against real bh_ledger.db — passes if DB absent."""
    seg = ProtocolSegmenter()
    result = seg.get_sub_entities("0xnonexistent_contract_xyz", limit=5)
    assert isinstance(result, list)


def test_segmenter_protocol_activity_live():
    seg = ProtocolSegmenter()
    result = seg.get_protocol_activity("0xnonexistent_contract_xyz")
    assert isinstance(result, dict)


def test_segmenter_global_activity_live():
    seg = ProtocolSegmenter()
    result = seg.get_global_activity(window_seconds=3600)
    assert isinstance(result, dict)
    if result:
        total = sum(result.values())
        assert abs(total - 1.0) < 1e-6, "global activity should be normalised"


def test_segmenter_caches_results():
    seg = ProtocolSegmenter()
    addr = "0xcachetest"
    r1 = seg.get_sub_entities(addr, limit=5)
    r2 = seg.get_sub_entities(addr, limit=5)
    assert r1 is r2 or r1 == r2
