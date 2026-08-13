"""
test_protocol_role_classifier.py — Tests for RoleClassifier

Tests cover:
  - All 7 DeFi roles correctly identified from canonical event patterns
  - UNKNOWN returned for insufficient signal
  - Confidence bounded [0, 1]
  - Archetype and risk_level mapping consistency
  - Batch classification
  - Edge cases: empty counts, single event type, very large tx count
"""
import sys
import pytest

sys.path.insert(0, ".")

from src.protocol.role_classifier import RoleClassifier, DeFiRole, RoleResult
from src.protocol.segmentation import SubEntity


clf = RoleClassifier()


def make_se(event_counts: dict, tx_count: int = 50) -> SubEntity:
    return SubEntity(
        contract="0xproto",
        caller="0xcaller",
        entity_id="0xproto:0xcaller",
        tx_count=tx_count,
        event_type_counts=event_counts,
        magnitude_stats={"mean": 0.3, "max": 0.9, "std": 0.1, "p95": 0.7},
        chains=["ETH_MAINNET"],
        first_seen=1700000000.0,
        last_seen=1700003600.0,
        dominant_event=max(event_counts, key=event_counts.get) if event_counts else "UNKNOWN",
    )


# ── Role detection ────────────────────────────────────────────────────────────

def test_mev_bot_detected():
    result = clf.classify({"MEV_CAPTURE": 80, "SWAP": 15, "FLASH_LOAN": 5}, tx_count=100)
    assert result.role == DeFiRole.MEV_BOT
    assert result.risk_level == "HIGH"


def test_liquidator_detected():
    result = clf.classify({"LIQUIDATE": 60, "FLASH_LOAN": 30, "SWAP": 10}, tx_count=100)
    assert result.role == DeFiRole.LIQUIDATOR


def test_liquidity_provider_detected():
    result = clf.classify({"LIQUIDITY": 85, "SWAP": 10, "CLAIM": 5}, tx_count=50)
    assert result.role == DeFiRole.LIQUIDITY_PROVIDER
    assert result.risk_level == "LOW"


def test_borrower_detected():
    result = clf.classify({"BORROW": 60, "STAKE": 20, "UNSTAKE": 15, "CLAIM": 5}, tx_count=40)
    assert result.role == DeFiRole.BORROWER


def test_arbitrageur_detected():
    result = clf.classify({"SWAP": 60, "BRIDGE": 35, "CLAIM": 5}, tx_count=200)
    assert result.role == DeFiRole.ARBITRAGEUR


def test_governance_actor_detected():
    result = clf.classify({"GOVERNANCE": 70, "PROPOSAL": 25, "CLAIM": 5}, tx_count=10)
    assert result.role == DeFiRole.GOVERNANCE_ACTOR


def test_trader_detected():
    result = clf.classify({"SWAP": 90, "CLAIM": 5, "BURN": 5}, tx_count=30)
    assert result.role == DeFiRole.TRADER


def test_unknown_below_min_tx():
    result = clf.classify({"SWAP": 1}, tx_count=1)
    assert result.role == DeFiRole.UNKNOWN
    assert result.confidence == 0.0


def test_unknown_empty_counts():
    result = clf.classify({}, tx_count=0)
    assert result.role == DeFiRole.UNKNOWN


def test_unknown_ambiguous_signal():
    result = clf.classify(
        {"SWAP": 10, "BORROW": 10, "LIQUIDITY": 10, "GOVERNANCE": 10},
        tx_count=40
    )
    assert result.confidence <= 0.5


# ── Confidence bounds ─────────────────────────────────────────────────────────

def test_confidence_bounded():
    for counts in [
        {"MEV_CAPTURE": 100},
        {"LIQUIDITY": 100},
        {"BORROW": 50, "STAKE": 50},
        {},
    ]:
        tx = max(sum(counts.values()), 1)
        result = clf.classify(counts, tx_count=tx)
        assert 0.0 <= result.confidence <= 1.0, f"Confidence out of range: {result.confidence}"


# ── Archetype mapping ─────────────────────────────────────────────────────────

def test_archetype_mapping_complete():
    """Every DeFiRole except UNKNOWN maps to a non-empty archetype."""
    for role in DeFiRole:
        if role != DeFiRole.UNKNOWN:
            assert role.archetype, f"{role} has no archetype"


def test_risk_level_mapping_complete():
    """Every DeFiRole has a risk_level."""
    for role in DeFiRole:
        assert role.risk_level in ("LOW", "MEDIUM", "HIGH", "UNKNOWN")


# ── RoleResult structure ──────────────────────────────────────────────────────

def test_role_result_has_evidence():
    result = clf.classify({"SWAP": 80, "BRIDGE": 20}, tx_count=60)
    assert "all_scores" in result.evidence
    assert "event_frequencies" in result.evidence
    assert isinstance(result.evidence["all_scores"], dict)


def test_role_result_description_not_empty():
    result = clf.classify({"LIQUIDITY": 100}, tx_count=50)
    assert len(result.description) > 10


# ── Batch classification ──────────────────────────────────────────────────────

def test_batch_classify_sets_role():
    entities = [
        make_se({"MEV_CAPTURE": 80, "SWAP": 20}),
        make_se({"LIQUIDITY": 90, "SWAP": 10}),
        make_se({"BORROW": 70, "STAKE": 30}),
    ]
    results = clf.classify_batch(entities)
    assert len(results) == 3
    for se, role_res in results:
        assert se.role is not None
        assert isinstance(role_res, RoleResult)


def test_batch_classify_empty():
    results = clf.classify_batch([])
    assert results == []


# ── DeFiRole enum ─────────────────────────────────────────────────────────────

def test_defi_role_str_values():
    assert DeFiRole.MEV_BOT.value == "MEV_BOT"
    assert DeFiRole.LIQUIDITY_PROVIDER.value == "LIQUIDITY_PROVIDER"


def test_defi_role_count():
    """There should be exactly 8 roles (7 meaningful + UNKNOWN)."""
    assert len(list(DeFiRole)) == 8
