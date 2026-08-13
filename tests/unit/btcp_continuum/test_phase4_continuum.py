"""
Phase 4 — CONTINUUM Engine Tests
"""
import pytest
import time
import math
from continuum.engines import (
    BIDEngine, BIDResult, CMEEngine, CMEResult,
    PMOSystem, PreManifestOrder, BDCEngine,
    ThermodynamicSettlement, SettlementTrigger,
    CCPDistribution,
)


class TestBIDEngine:
    def test_detect_buy_direction(self):
        bid = BIDEngine()
        # Buyer signal: counterparty diversity up, temporal up, cross-protocol up
        result = bid.detect(
            current_features=[0.9, 0.8, 0.9, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1],
            baseline_features=[0.7, 0.6, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1],
            pretrade_signature=[0.1, 0.1, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            depth_d=500.0,
        )
        assert result.direction == "BUY"
        assert result.detected

    def test_detect_sell_direction(self):
        bid = BIDEngine()
        result = bid.detect(
            current_features=[0.5, 0.4, 0.5, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1],
            baseline_features=[0.7, 0.6, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1],
            pretrade_signature=[-0.1, -0.1, -0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            depth_d=500.0,
        )
        assert result.direction == "SELL"

    def test_depth_factor_caps_at_1(self):
        bid = BIDEngine()
        result = bid.detect(
            current_features=[0.8]*9, baseline_features=[0.7]*9,
            pretrade_signature=[0.1]*9, depth_d=10000.0,
        )
        assert result.depth_factor == 1.0  # min(1, 10000/100)

    def test_low_depth_reduces_confidence(self):
        bid = BIDEngine()
        result = bid.detect(
            current_features=[0.8]*9, baseline_features=[0.7]*9,
            pretrade_signature=[0.1]*9, depth_d=50.0,  # below D_MINIMUM
        )
        assert result.depth_factor == 0.5  # 50/100
        assert result.confidence < 1.0

    def test_no_detection_below_threshold(self):
        bid = BIDEngine()
        result = bid.detect(
            current_features=[0.7]*9, baseline_features=[0.7]*9,  # no delta
            pretrade_signature=[0.1]*9, depth_d=500.0,
        )
        assert not result.detected  # confidence = 0


class TestCMEEngine:
    def test_find_complement(self):
        cme = CMEEngine()
        vec_a = [1.0] + [0.0] * 127
        vec_b = [0.0, 1.0] + [0.0] * 126
        candidates = [
            {"entity_id": b"\x02"*32, "vector": vec_b, "direction": "SELL",
             "behavioral_health": 0.85, "liquidity": 0.9, "timestamp": time.time()},
        ]
        result = cme.find_complement(vec_a, "BUY", candidates)
        assert result.matched
        assert result.complement_id == b"\x02"*32

    def test_no_complement_same_direction(self):
        cme = CMEEngine()
        vec_a = [1.0] + [0.0] * 127
        candidates = [
            {"entity_id": b"\x02"*32, "vector": [0.0]*128, "direction": "BUY",  # same direction
             "behavioral_health": 0.85, "liquidity": 0.9, "timestamp": time.time()},
        ]
        result = cme.find_complement(vec_a, "BUY", candidates)
        assert not result.matched

    def test_no_complement_low_health(self):
        cme = CMEEngine()
        vec_a = [1.0] + [0.0] * 127
        vec_b = [0.0, 1.0] + [0.0] * 126
        candidates = [
            {"entity_id": b"\x02"*32, "vector": vec_b, "direction": "SELL",
             "behavioral_health": 0.40,  # below threshold
             "liquidity": 0.9, "timestamp": time.time()},
        ]
        result = cme.find_complement(vec_a, "BUY", candidates)
        assert not result.matched

    def test_no_complement_coordinated(self):
        """beo_independence too low — entities are coordinated."""
        cme = CMEEngine()
        # Identical vectors → cos_sim = 1.0 → independence = 0.0
        vec = [1.0] + [0.0] * 127
        candidates = [
            {"entity_id": b"\x02"*32, "vector": vec, "direction": "SELL",
             "behavioral_health": 0.85, "liquidity": 0.9, "timestamp": time.time()},
        ]
        result = cme.find_complement(vec, "BUY", candidates)
        assert not result.matched


class TestPMOSystem:
    def test_create_pmo(self):
        pmo_sys = PMOSystem()
        pmo = pmo_sys.create_pmo(
            entity_id=b"\x01"*32, intent_data=b"swap", entity_bh=b"\xAA"*32,
            nonce=42, trion_valuation=2000.0, ccp_premium=5.0,
            complement_id=b"\x02"*32,
        )
        assert pmo.price_guarantee == 2005.0
        assert pmo.status == "ACTIVE"
        assert len(pmo.behavioral_commitment) == 32

    def test_fill_pmo(self):
        pmo_sys = PMOSystem()
        pmo = pmo_sys.create_pmo(
            entity_id=b"\x01"*32, intent_data=b"swap", entity_bh=b"\xAA"*32,
            nonce=42, trion_valuation=2000.0, ccp_premium=5.0,
            complement_id=b"\x02"*32,
        )
        assert pmo_sys.fill_pmo(pmo.behavioral_commitment)
        assert pmo_sys.get_pmo(pmo.behavioral_commitment).status == "FILLED"

    def test_fill_nonexistent_pmo_fails(self):
        pmo_sys = PMOSystem()
        assert not pmo_sys.fill_pmo(b"\x00"*32)

    def test_expire_pmo(self):
        pmo_sys = PMOSystem()
        pmo = pmo_sys.create_pmo(
            entity_id=b"\x01"*32, intent_data=b"swap", entity_bh=b"\xAA"*32,
            nonce=42, trion_valuation=2000.0, ccp_premium=5.0,
            complement_id=b"\x02"*32,
        )
        assert pmo_sys.expire_pmo(pmo.behavioral_commitment)
        assert pmo_sys.get_pmo(pmo.behavioral_commitment).status == "EXPIRED"


class TestBDCEngine:
    def test_credit_limit_computation(self):
        bdc = BDCEngine()
        result = bdc.compute_credit_limit(
            depth_d=730.0,
            phi_history_90d=[0.8, 0.81, 0.79, 0.8, 0.82, 0.78, 0.8, 0.81, 0.79, 0.8],
            avg_trade_size_90d=1000.0,
        )
        assert result["credit_limit"] > 0
        assert result["confidence_multiplier"] == 2.0  # min(2, 730/100)

    def test_confidence_multiplier_caps_at_2(self):
        bdc = BDCEngine()
        result = bdc.compute_credit_limit(
            depth_d=10000.0,  # very high
            phi_history_90d=[0.8]*10,
            avg_trade_size_90d=1000.0,
        )
        assert result["confidence_multiplier"] == 2.0

    def test_low_depth_reduces_multiplier(self):
        bdc = BDCEngine()
        result = bdc.compute_credit_limit(
            depth_d=50.0,  # below D_MINIMUM
            phi_history_90d=[0.8]*10,
            avg_trade_size_90d=1000.0,
        )
        assert result["confidence_multiplier"] == 0.5  # 50/100

    def test_insufficient_history(self):
        bdc = BDCEngine()
        result = bdc.compute_credit_limit(
            depth_d=500.0, phi_history_90d=[0.8], avg_trade_size_90d=1000.0,
        )
        assert result["credit_limit"] == 0.0
        assert result["reason"] == "insufficient_history"

    def test_high_consistency_yields_high_credit(self):
        bdc = BDCEngine()
        consistent = [0.80] * 10  # std=0 → consistency=1.0
        result = bdc.compute_credit_limit(500.0, consistent, 1000.0)
        assert result["consistency_ratio"] == 1.0


class TestThermodynamicSettlement:
    def test_all_conditions_met_triggers(self):
        ts = ThermodynamicSettlement()
        result = ts.check_trigger(
            coherence_a=0.85, threshold_a=0.55,
            coherence_b=0.80, threshold_b=0.55,
            btcp_route_verified=True,
            temporal_alignment_valid=True,
            mf_detected=False,
        )
        assert result.triggered

    def test_mf_detected_blocks_settlement(self):
        ts = ThermodynamicSettlement()
        result = ts.check_trigger(
            coherence_a=0.85, threshold_a=0.55,
            coherence_b=0.80, threshold_b=0.55,
            btcp_route_verified=True,
            temporal_alignment_valid=True,
            mf_detected=True,
        )
        assert not result.triggered
        assert "no_mf" in result.reason

    def test_coherence_below_threshold_blocks(self):
        ts = ThermodynamicSettlement()
        result = ts.check_trigger(
            coherence_a=0.40, threshold_a=0.55,  # below
            coherence_b=0.80, threshold_b=0.55,
            btcp_route_verified=True,
            temporal_alignment_valid=True,
            mf_detected=False,
        )
        assert not result.triggered
        assert "coherence_a_passes" in result.reason

    def test_btcp_not_verified_blocks(self):
        ts = ThermodynamicSettlement()
        result = ts.check_trigger(
            coherence_a=0.85, threshold_a=0.55,
            coherence_b=0.80, threshold_b=0.55,
            btcp_route_verified=False,
            temporal_alignment_valid=True,
            mf_detected=False,
        )
        assert not result.triggered


class TestCCPDistribution:
    def test_ccp_computation(self):
        ccp = CCPDistribution()
        result = ccp.compute_ccp(
            best_exchange_spread=0.003,  # 30 bps
            btcp_routing_cost=0.0005,    # 5 bps
            trade_value=10_000.0,
        )
        assert result["ccp_total"] == 25.0  # (0.003 - 0.0005) × 10000
        assert result["ccp_a"] == 10.0       # 40%
        assert result["ccp_b"] == 10.0       # 40%
        assert result["ccp_validators"] == 3.0  # 12%
        assert result["ccp_protocol"] == 2.0    # 8%

    def test_split_sums_to_1(self):
        ccp = CCPDistribution()
        total = ccp.SPLIT_A + ccp.SPLIT_B + ccp.SPLIT_VALIDATORS + ccp.SPLIT_PROTOCOL
        assert abs(total - 1.0) < 1e-9

    def test_btcp_cost_exceeds_spread(self):
        """If BTCP routing cost > exchange spread, CCP = 0."""
        ccp = CCPDistribution()
        result = ccp.compute_ccp(
            best_exchange_spread=0.001,
            btcp_routing_cost=0.005,  # higher than spread
            trade_value=10_000.0,
        )
        assert result["ccp_total"] == 0.0

    def test_specific_split_ratios(self):
        ccp = CCPDistribution()
        assert ccp.SPLIT_A == 0.40
        assert ccp.SPLIT_B == 0.40
        assert ccp.SPLIT_VALIDATORS == 0.12
        assert ccp.SPLIT_PROTOCOL == 0.08
