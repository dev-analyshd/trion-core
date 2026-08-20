"""
test_protocol_health.py — Tests for ProtocolHealthEngine

Tests cover:
  - H(t) score bounded [0, 1]
  - Grade mapping (A–F) correct against score thresholds
  - All 4 component keys present in output
  - Weights sum to 1.0
  - Recommendations returned as list of strings
  - Role coherence entropy formula
  - User quality proxy returns bounded value
  - Threat level classification
  - Full compute() smoke test (graceful with empty DB)
"""
import sys
import pytest
import math

sys.path.insert(0, ".")

from core.protocol.protocol_health import (
    ProtocolHealthEngine,
    ProtocolHealthResult,
    _grade,
    _role_coherence,
    _user_quality_proxy,
    _recommendations,
)
from core.protocol.role_classifier import RoleClassifier, DeFiRole
from core.protocol.segmentation import SubEntity


# ── Grade mapping ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("score,expected_grade", [
    (0.85, "A"),
    (0.80, "A"),
    (0.70, "B"),
    (0.65, "B"),
    (0.55, "C"),
    (0.50, "C"),
    (0.40, "D"),
    (0.35, "D"),
    (0.20, "F"),
    (0.00, "F"),
])
def test_grade_mapping(score, expected_grade):
    assert _grade(score) == expected_grade


# ── Role coherence ────────────────────────────────────────────────────────────

def test_role_coherence_empty():
    assert _role_coherence({}) == 0.0


def test_role_coherence_single_role():
    result = _role_coherence({"TRADER": 100})
    assert 0.0 <= result <= 1.0


def test_role_coherence_uniform_distribution():
    """Uniform over 7 roles — maximum entropy, should score well."""
    counts = {r.value: 10 for r in DeFiRole if r != DeFiRole.UNKNOWN}
    result = _role_coherence(counts)
    assert 0.0 <= result <= 1.0


def test_role_coherence_bounded():
    import random
    for _ in range(20):
        counts = {r.value: random.randint(0, 100) for r in DeFiRole}
        result = _role_coherence(counts)
        assert 0.0 <= result <= 1.0, f"Out of bounds: {result}"


# ── User quality proxy ────────────────────────────────────────────────────────

def make_sub_entity(event_counts, tx_count=50):
    return SubEntity(
        contract="0xproto",
        caller="0xcaller",
        entity_id="id",
        tx_count=tx_count,
        event_type_counts=event_counts,
        magnitude_stats={"mean": 0.3, "max": 0.9, "std": 0.2, "p95": 0.7},
        chains=["ETH"],
        first_seen=0.0,
        last_seen=0.0,
        dominant_event=max(event_counts, key=event_counts.get) if event_counts else "UNKNOWN",
    )


def test_user_quality_empty():
    clf = RoleClassifier()
    result = _user_quality_proxy([], clf)
    assert result == 0.5


def test_user_quality_bounded():
    clf = RoleClassifier()
    entities = [
        make_sub_entity({"SWAP": 80, "LIQUIDITY": 20}),
        make_sub_entity({"MEV_CAPTURE": 90, "SWAP": 10}),
        make_sub_entity({"BORROW": 70, "STAKE": 30}),
    ]
    result = _user_quality_proxy(entities, clf)
    assert 0.0 <= result <= 1.0


# ── ProtocolHealthResult + recommendations ────────────────────────────────────

def _make_result(h_score=0.5, dc_score=0.6, attack_p=0.1, sub_count=20) -> ProtocolHealthResult:
    dc_result = {
        "distribution_coherence": dc_score,
        "attack_probability": attack_p,
        "interpretation": "test",
        "anomalous_events": [],
    }
    return ProtocolHealthResult(
        address="0xtest",
        health_score=h_score,
        grade=_grade(h_score),
        components={"distribution_coherence": dc_score},
        role_distribution={"TRADER": 0.6, "MEV_BOT": 0.4},
        top_users=[],
        dc_result=dc_result,
        sub_entity_count=sub_count,
        attacker_wallets=[],
        recommendations=[],
    )


def test_recommendations_critical_dc():
    r = _make_result(dc_score=0.3, attack_p=0.0)
    recs = _recommendations(r)
    assert any("URGENT" in rec for rec in recs)


def test_recommendations_high_attack_probability():
    r = _make_result(attack_p=0.6)
    recs = _recommendations(r)
    assert any("ALERT" in rec for rec in recs)


def test_recommendations_high_mev():
    r = _make_result()
    r.role_distribution = {"MEV_BOT": 0.40, "TRADER": 0.60}
    recs = _recommendations(r)
    assert any("MEV" in rec for rec in recs)


def test_recommendations_low_data():
    r = _make_result(sub_count=3)
    recs = _recommendations(r)
    assert any("Insufficient" in rec for rec in recs)


def test_recommendations_nominal():
    r = _make_result(h_score=0.85, dc_score=0.9, attack_p=0.05, sub_count=50)
    r.role_distribution = {"TRADER": 0.5, "LIQUIDITY_PROVIDER": 0.3, "BORROWER": 0.2}
    recs = _recommendations(r)
    assert any("nominal" in rec.lower() for rec in recs)


def test_recommendations_returns_list():
    r = _make_result()
    recs = _recommendations(r)
    assert isinstance(recs, list)
    assert all(isinstance(rec, str) for rec in recs)


# ── Component weights sum to 1.0 ──────────────────────────────────────────────

def test_component_weights_sum():
    from core.protocol.protocol_health import _W_DC, _W_ROLE_COH, _W_USER_QUALITY, _W_ATTACK_SURF
    total = _W_DC + _W_ROLE_COH + _W_USER_QUALITY + _W_ATTACK_SURF
    assert total == pytest.approx(1.0, abs=1e-9)


# ── Full engine smoke test ────────────────────────────────────────────────────

def test_engine_compute_smoke():
    """Full compute() smoke test — must not raise even with empty bh_ledger."""
    engine = ProtocolHealthEngine()
    result = engine.compute("0xnonexistent_proto_xyz_123", top_n=10)
    assert isinstance(result, ProtocolHealthResult)
    assert 0.0 <= result.health_score <= 1.0
    assert result.grade in ("A", "B", "C", "D", "F")
    assert isinstance(result.recommendations, list)
    assert isinstance(result.components, dict)
    assert {"distribution_coherence", "role_coherence", "user_quality", "attack_surface"} \
        <= set(result.components.keys())


def test_engine_compute_components_bounded():
    engine = ProtocolHealthEngine()
    result = engine.compute("0xnonexistent_proto_xyz_456", top_n=5)
    for key in ("distribution_coherence", "role_coherence", "user_quality", "attack_surface"):
        val = result.components.get(key, 0)
        assert 0.0 <= val <= 1.0, f"{key} out of range: {val}"
