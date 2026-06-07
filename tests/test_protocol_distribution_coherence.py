"""
test_protocol_distribution_coherence.py — Tests for DistributionCoherenceEngine

Tests cover:
  - JSD = 0 for identical distributions
  - JSD = 1 (max) for maximally different distributions
  - DC = 1 - JSD symmetry
  - Distribution normalisation
  - Anomalous event detection (spike factor threshold)
  - Attack probability for high FLASH_LOAN / LIQUIDATE ratios
  - Interpretation strings
  - Baseline update + rolling window
  - Graceful handling of empty distributions
"""
import sys
import math
import pytest

sys.path.insert(0, ".")

from src.protocol.distribution_coherence import (
    DistributionCoherenceEngine,
    distribution_coherence_score,
    jensen_shannon_divergence,
    ALL_EVENT_TYPES,
)


# ── Pure JSD function ─────────────────────────────────────────────────────────

def test_jsd_identical_distributions():
    dist = {"SWAP": 0.6, "LIQUIDITY": 0.3, "BORROW": 0.1}
    jsd = jensen_shannon_divergence(dist, dist)
    assert jsd == pytest.approx(0.0, abs=1e-6)


def test_jsd_completely_different():
    p = {"FLASH_LOAN": 1.0}
    q = {"GOVERNANCE": 1.0}
    jsd = jensen_shannon_divergence(p, q)
    assert jsd > 0.8


def test_jsd_bounded():
    for _ in range(10):
        import random
        p = {k: random.random() for k in ALL_EVENT_TYPES[:5]}
        q = {k: random.random() for k in ALL_EVENT_TYPES[5:10]}
        jsd = jensen_shannon_divergence(p, q)
        assert 0.0 <= jsd <= 1.0, f"JSD out of bounds: {jsd}"


def test_jsd_symmetric():
    p = {"SWAP": 0.7, "BORROW": 0.3}
    q = {"FLASH_LOAN": 0.5, "MEV_CAPTURE": 0.5}
    assert jensen_shannon_divergence(p, q) == pytest.approx(
        jensen_shannon_divergence(q, p), abs=1e-9
    )


def test_jsd_empty_input():
    jsd = jensen_shannon_divergence({}, {})
    assert 0.0 <= jsd <= 1.0


# ── DC score ─────────────────────────────────────────────────────────────────

def test_dc_identical_is_one():
    dist = {"SWAP": 0.5, "LIQUIDITY": 0.5}
    dc = distribution_coherence_score(dist, dist)
    assert dc == pytest.approx(1.0, abs=1e-5)


def test_dc_different_is_low():
    p = {"FLASH_LOAN": 1.0}
    q = {"GOVERNANCE": 1.0}
    dc = distribution_coherence_score(p, q)
    assert dc < 0.3


def test_dc_bounded():
    dc = distribution_coherence_score({"SWAP": 0.8}, {"LIQUIDITY": 0.9})
    assert 0.0 <= dc <= 1.0


def test_dc_empty_returns_midpoint():
    dc = distribution_coherence_score({}, {})
    assert dc == 0.5


# ── Engine ────────────────────────────────────────────────────────────────────

def test_engine_compute_basic():
    engine = DistributionCoherenceEngine()
    normal_dist = {"SWAP": 0.5, "LIQUIDITY": 0.3, "BORROW": 0.2}
    result = engine.compute("0xtest", normal_dist)

    assert "distribution_coherence" in result
    assert "jsd" in result
    assert "attack_probability" in result
    assert "anomalous_events" in result
    assert "interpretation" in result
    assert 0.0 <= result["distribution_coherence"] <= 1.0
    assert 0.0 <= result["attack_probability"] <= 1.0


def test_engine_stable_activity():
    engine = DistributionCoherenceEngine()
    baseline = {"SWAP": 0.6, "LIQUIDITY": 0.3, "BORROW": 0.1}
    engine.update_baseline("0xstable", baseline)
    result = engine.compute("0xstable", baseline)
    assert result["distribution_coherence"] > 0.85


def test_engine_attack_detected():
    engine = DistributionCoherenceEngine()
    baseline = {"SWAP": 0.6, "LIQUIDITY": 0.3, "BORROW": 0.1}
    engine.update_baseline("0xattack", baseline)
    attack_dist = {"FLASH_LOAN": 0.7, "LIQUIDATE": 0.25, "SWAP": 0.05}
    result = engine.compute("0xattack", attack_dist)

    assert result["distribution_coherence"] < 0.5
    assert result["attack_probability"] > 0.3


def test_engine_anomalous_events_detected():
    engine = DistributionCoherenceEngine()
    baseline = {"SWAP": 0.6, "LIQUIDITY": 0.3, "FLASH_LOAN": 0.02}
    engine.update_baseline("0xanom", baseline)
    spike_dist = {"SWAP": 0.1, "LIQUIDITY": 0.1, "FLASH_LOAN": 0.8}
    result = engine.compute("0xanom", spike_dist)

    events = [e["event"] for e in result["anomalous_events"]]
    assert "FLASH_LOAN" in events


def test_engine_baseline_update_rolling():
    engine = DistributionCoherenceEngine(baseline_window_days=30)
    dist1 = {"SWAP": 0.7, "LIQUIDITY": 0.3}
    dist2 = {"BORROW": 0.6, "LIQUIDITY": 0.4}
    engine.update_baseline("0xroll", dist1)
    engine.update_baseline("0xroll", dist2)
    assert "0xroll" in engine._baselines
    assert isinstance(engine._baselines["0xroll"], dict)


def test_interpretation_labels():
    engine = DistributionCoherenceEngine()
    assert "STABLE" in engine._interpret(0.90)
    assert "DRIFTING" in engine._interpret(0.70)
    assert "ANOMALOUS" in engine._interpret(0.50)
    assert "CRITICAL" in engine._interpret(0.20)


def test_attack_probability_high_flash():
    engine = DistributionCoherenceEngine()
    result = engine.compute("0xflash", {"FLASH_LOAN": 0.9, "LIQUIDATE": 0.1})
    assert result["attack_probability"] > 0.4


def test_attack_probability_normal():
    engine = DistributionCoherenceEngine()
    result = engine.compute("0xnorm", {"SWAP": 0.7, "LIQUIDITY": 0.3})
    assert result["attack_probability"] < 0.3
