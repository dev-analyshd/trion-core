"""
Phase 2 — BTCP Module Tests
============================
Tests for all 18 BTCP modules (Python implementation of Rust spec).
"""
import pytest
import time
from core.btcp.router import (
    BIBLState, Route, RouteType, btcp_score_final, normalize_gas,
    route_is_valid, select_optimal_route, W_NL, W_GAS, W_FIN, W_COH, W_BEO,
    MIN_BTCP_SCORE, MIN_NL, MIN_FINALITY, MIN_VALIDATORS_PER_ROUTE,
)
from core.btcp.escrow_monitor import (
    EscrowMonitor, Escrow, EscrowState, RevertReason,
    EMERGENCY_ESCAPE_SECONDS, AKASHIC_RECOVERY_SECONDS,
)
from core.btcp.bibl_engine import (
    BIBLEngine, PerChainState, EndpointDiversity, ForkAssessment,
    FORK_ASSESSMENT_PERIOD_DAYS, MIN_ENDPOINTS_PER_CHAIN, CANONICAL_CHAIN_THRESHOLD,
)
from core.btcp.modules import (
    BTCPProofBuilder, BTCPProof, ConsensusProof, ValidatorSignature,
    BITPMatcher, BITPIntent, NettingEngine, IntentAggregator,
    OOAAnchor, ShadowObserver, StateCapsuleBuilder, StateCapsule,
    FailureClassifier, GenesisCommitmentProcessor, BLOScheduler,
    BehavioralStateChannel, FinalityNormalizer, VersionHandler,
    ValidatorFeeCalculator, SybilResistance,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Module 2.1: BTCP Router Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestBTCPRouter:
    def _state(self):
        return BIBLState(
            nl_scores={1: 0.85, 137: 0.90, 8453: 0.88},
            gas_forecasts={1: 31.0, 137: 0.50, 8453: 0.98},
            gas_reference=31.0,
            cc_coherence={1: 0.90, 137: 0.92, 8453: 0.91},
            mf_scores={1: 0.02, 137: 0.01, 8453: 0.01},
            finality_dist={1: 12.0, 137: 2.0, 8453: 2.0},
        )

    def test_weights_sum_to_1(self):
        assert abs(W_NL + W_GAS + W_FIN + W_COH + W_BEO - 1.0) < 1e-9

    def test_normalize_gas_reference_is_zero(self):
        assert normalize_gas(31.0, self._state()) == 0.0

    def test_normalize_gas_free_is_one(self):
        assert normalize_gas(0.0, self._state()) == 1.0

    def test_normalize_gas_half(self):
        assert normalize_gas(15.5, self._state()) == 0.5

    def test_btcp_score_in_unit_interval(self):
        state = self._state()
        route = Route(
            route_id="t", entity_id=b"\x01"*32, route_type=RouteType.SINGLE_CHAIN,
            anchor_chain=1, execution_chain=1, gas_total=10.0,
            finality_confidence=0.95, beo_continuity=0.8,
            cc_coherence=0.9, intent_value=1000.0,
        )
        score = btcp_score_final(route, state)
        assert 0.0 <= score <= 1.0

    def test_route_validity_requires_min_score(self):
        state = self._state()
        route = Route(
            route_id="t", entity_id=b"\x01"*32, route_type=RouteType.SINGLE_CHAIN,
            anchor_chain=1, execution_chain=1, gas_total=10.0,
            finality_confidence=0.95, beo_continuity=0.8,
            cc_coherence=0.9, intent_value=1000.0,
        )
        assert route_is_valid(route, state, validator_count=10)

    def test_route_invalid_low_finality(self):
        state = self._state()
        route = Route(
            route_id="t", entity_id=b"\x01"*32, route_type=RouteType.SINGLE_CHAIN,
            anchor_chain=1, execution_chain=1, gas_total=10.0,
            finality_confidence=0.50,  # below MIN_FINALITY
            beo_continuity=0.8, cc_coherence=0.9, intent_value=1000.0,
        )
        assert not route_is_valid(route, state, validator_count=10)

    def test_select_optimal_route(self):
        state = self._state()
        route = select_optimal_route(
            intent_value=10_000.0,
            entity_id=b"\x01"*32,
            state=state,
            candidate_chains=[1, 137, 8453],
            validator_counts={1: 50, 137: 40, 8453: 30},
        )
        assert route is not None
        assert route.execution_chain in [1, 137, 8453]

    def test_select_returns_none_if_no_valid_routes(self):
        state = BIBLState()  # empty state — all NL = 0
        route = select_optimal_route(
            intent_value=1000.0, entity_id=b"\x01"*32, state=state,
            candidate_chains=[1], validator_counts={1: 1},  # below MIN_VALIDATORS
        )
        assert route is None


# ═══════════════════════════════════════════════════════════════════════════════
# Module 2.2: Escrow Monitor Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestEscrowMonitor:
    def test_lock_and_release(self):
        mon = EscrowMonitor()
        mon.lock_escrow("e1", "r1", b"\x01"*32, 1000.0, 1000, block_number=100)
        assert mon.verify_settlement("e1")
        assert mon.release_escrow("e1", coherence=0.80, block_number=200)
        assert mon.get_escrow("e1").state == EscrowState.RELEASED

    def test_release_requires_settlement_verification(self):
        """G1: Two-Phase Confirmation."""
        mon = EscrowMonitor()
        mon.lock_escrow("e2", "r2", b"\x02"*32, 1000.0, 1000, block_number=100)
        # No verify_settlement call → release should fail
        assert not mon.release_escrow("e2", coherence=0.80, block_number=200)

    def test_timeout_revert(self):
        mon = EscrowMonitor()
        mon.lock_escrow("e3", "r3", b"\x03"*32, 500.0, 100, block_number=100)
        assert mon.revert_escrow("e3", RevertReason.TIMEOUT, block_number=300)
        assert mon.get_escrow("e3").state == EscrowState.REVERTED
        assert mon.get_escrow("e3").revert_reason == RevertReason.TIMEOUT

    def test_cascade_revert(self):
        """Gap 9: Multi-hop cascade revert."""
        mon = EscrowMonitor()
        mon.lock_escrow("parent", "rp", b"\x04"*32, 2000.0, 1000, block_number=100)
        mon.lock_escrow("child", "rc", b"\x04"*32, 1500.0, 500,
                        parent_escrow_id="parent", block_number=100)
        mon.revert_escrow("child", RevertReason.TIMEOUT, block_number=700)
        assert mon.get_escrow("child").state == EscrowState.REVERTED
        assert mon.get_escrow("parent").state == EscrowState.REVERTED
        assert mon.get_escrow("parent").revert_reason == RevertReason.CASCADE_REVERT

    def test_pending_akashic_release(self):
        """E1: Akashic recovery within 24h."""
        mon = EscrowMonitor()
        mon.lock_escrow("e4", "r4", b"\x05"*32, 750.0, 1000, block_number=100)
        assert mon.enter_pending_akashic("e4")
        assert mon.get_escrow("e4").state == EscrowState.PENDING_AKASHIC
        assert mon.release_from_pending_akashic("e4", coherence=0.70)
        assert mon.get_escrow("e4").state == EscrowState.RELEASED

    def test_emergency_escape_after_7_days(self):
        """Gap 8: Emergency Escape Hatch."""
        mon = EscrowMonitor()
        mon.lock_escrow("e5", "r5", b"\x06"*32, 999.0, 100, block_number=100)
        esc = mon.get_escrow("e5")
        esc.lock_timestamp = time.time() - 8 * 86400  # 8 days ago
        assert mon.emergency_escape_available("e5")
        assert mon.revert_emergency("e5")
        assert mon.get_escrow("e5").state == EscrowState.EMERGENCY_REVERTED

    def test_emergency_not_available_before_7_days(self):
        mon = EscrowMonitor()
        mon.lock_escrow("e6", "r6", b"\x07"*32, 999.0, 1000, block_number=100)
        assert not mon.emergency_escape_available("e6")
        assert not mon.revert_emergency("e6")

    def test_constants(self):
        assert EMERGENCY_ESCAPE_SECONDS == 7 * 24 * 3600
        assert AKASHIC_RECOVERY_SECONDS == 24 * 3600


# ═══════════════════════════════════════════════════════════════════════════════
# Module 2.3: BIBL Engine Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestBIBLEngine:
    def test_update_chain_state(self):
        bibl = BIBLEngine()
        bibl.update_chain_state(
            chain_id=1, nl_score=0.85, gas_forecast=31.0,
            gas_ci_95=(28.0, 34.0), cc_coherence=0.90, mf_score=0.02,
            block_capacity=0.80, finality_sec=12.0, block_number=18000000,
        )
        state = bibl.get_chain_state(1)
        assert state.nl_score == 0.85

    def test_endpoint_diversity_no_penalty(self):
        """A1: 3+ independent endpoints → no penalty."""
        bibl = BIBLEngine()
        div = EndpointDiversity(
            chain_id=1, endpoints=["a", "b", "c"],
            regions=["us", "eu", "ap"], asns=["AS1", "AS2", "AS3"],
            cloud_providers=["aws", "gcp", "azure"],
        )
        bibl.register_endpoint_diversity(div)
        assert bibl.diversity_penalty(1) == 1.0

    def test_endpoint_diversity_penalty(self):
        bibl = BIBLEngine()
        div = EndpointDiversity(
            chain_id=1, endpoints=["a", "b"],
            regions=["us", "us"], asns=["AS1", "AS1"],
            cloud_providers=["aws", "aws"],
        )
        bibl.register_endpoint_diversity(div)
        assert bibl.diversity_penalty(1) < 1.0

    def test_fork_detection_suspends_chain(self):
        """Gap 12: Fork detection suspends routing for 30 days."""
        bibl = BIBLEngine()
        bibl.detect_fork(chain_id=1, chain_a_id=1, chain_b_id=1001)
        assert bibl.is_chain_suspended(1)

    def test_fork_resolution_canonical_chain(self):
        """Gap 12: Canonical chain must retain ≥67% weighted score."""
        bibl = BIBLEngine()
        bibl.detect_fork(chain_id=1, chain_a_id=1, chain_b_id=1001)
        canonical = bibl.update_fork_assessment(
            chain_id_original=1,
            chain_a_validator_retention=0.80, chain_a_tvl_retention=0.85, chain_a_dev_activity=0.90,
            chain_b_validator_retention=0.20, chain_b_tvl_retention=0.15, chain_b_dev_activity=0.10,
        )
        assert canonical == 1
        assert not bibl.is_chain_suspended(1)

    def test_bibl_snapshot_excludes_suspended(self):
        bibl = BIBLEngine()
        bibl.update_chain_state(1, 0.8, 30, (28, 32), 0.9, 0.02, 0.8, 12, 100)
        bibl.update_chain_state(137, 0.9, 0.5, (0.4, 0.6), 0.92, 0.01, 0.9, 2, 100)
        bibl.detect_fork(chain_id=137, chain_a_id=137, chain_b_id=2137)
        snapshot = bibl.get_bibl_snapshot()
        assert 1 in snapshot
        assert 137 not in snapshot  # suspended

    def test_bibl_snapshot_finality_distribution(self):
        """Spec §2.3: snapshot carries the statistical finality distribution
        computed from OBSERVED finality samples (not just the mean)."""
        bibl = BIBLEngine()
        # A single sample: stats fall back to the observed value, count
        # discloses the evidence size (no fabricated distribution).
        bibl.update_chain_state(1, 0.85, 31.0, (28, 34), 0.9, 0.02, 0.8, 12.0, 100)
        snap = bibl.get_bibl_snapshot()[1]
        assert snap["finality_sample_count"] == 1
        assert snap["finality_p50_sec"] == 12.0
        assert snap["finality_p95_sec"] == 12.0

        # Six observed samples → real percentiles over the recorded window
        for f in (11.5, 12.5, 13.0, 14.0, 25.0):
            bibl.update_chain_state(1, 0.85, 31.0, (28, 34), 0.9, 0.02, 0.8, f, 100)
        snap = bibl.get_bibl_snapshot()[1]
        assert snap["finality_sample_count"] == 6
        assert snap["finality_p50_sec"] == 12.5   # median of {11.5,12,12.5,13,14,25}
        assert snap["finality_p95_sec"] == 25.0   # p95 tail
        # Spec-required Tier-1 fields all present and caller-supplied
        for key in ("nl_score", "gas_forecast", "cc_coherence", "mf_score",
                    "block_capacity", "finality_avg_sec"):
            assert key in snap


# ═══════════════════════════════════════════════════════════════════════════════
# Module 2.4: BTCP Proof Builder Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestBTCPProofBuilder:
    def test_build_and_verify_proof(self):
        pb = BTCPProofBuilder()
        proof = pb.build_proof(
            anchor_bh=b"\x01"*32, intent_hash=b"\x02"*32,
            route_type=1, certification_block=18000000, value_usd=5000.0,
            validator_signatures=[ValidatorSignature(b"\x03"*32, b"\x04"*65, 0.8)],
            diversity_weights=[0.8, 0.7, 0.6], hhi=1500.0,
            coherence=0.85, threshold=0.55,
        )
        assert pb.verify_proof(proof, current_block=18000001)

    def test_expired_proof_fails(self):
        pb = BTCPProofBuilder()
        proof = pb.build_proof(
            anchor_bh=b"\x01"*32, intent_hash=b"\x02"*32,
            route_type=1, certification_block=18000000, value_usd=5000.0,
            validator_signatures=[ValidatorSignature(b"\x03"*32, b"\x04"*65, 0.8)],
            diversity_weights=[0.8], hhi=1500.0, coherence=0.85, threshold=0.55,
        )
        assert not pb.verify_proof(proof, current_block=18000000 + 100000)

    def test_cert_expiry_by_value_tier(self):
        """A3: Certification validity windows."""
        pb = BTCPProofBuilder()
        assert pb.compute_cert_expiry(500) == 10_000       # <$1K
        assert pb.compute_cert_expiry(50_000) == 50_000     # $1K-$100K
        assert pb.compute_cert_expiry(5_000_000) == 200_000  # $100K-$10M
        assert pb.compute_cert_expiry(50_000_000) == 500_000  # >$10M


# ═══════════════════════════════════════════════════════════════════════════════
# Module 2.5: BITP Matcher Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestBITPMatcher:
    def test_find_complement(self):
        bm = BITPMatcher()
        a = BITPIntent(b"\x01"*32, b"\xAA"*32, b"\xBB"*32, 1000.0, 1, 1000)
        b = BITPIntent(b"\x02"*32, b"\xBB"*32, b"\xAA"*32, 1000.0, 137, 1000)
        match = bm.find_complement(a, [b])
        assert match is not None

    def test_no_complement_same_chain(self):
        bm = BITPMatcher()
        a = BITPIntent(b"\x01"*32, b"\xAA"*32, b"\xBB"*32, 1000.0, 1, 1000)
        b = BITPIntent(b"\x02"*32, b"\xBB"*32, b"\xAA"*32, 1000.0, 1, 1000)  # same chain
        match = bm.find_complement(a, [b])
        assert match is None

    def test_paste_zero_cross_chain_movement(self):
        bm = BITPMatcher()
        a = BITPIntent(b"\x01"*32, b"\xAA"*32, b"\xBB"*32, 1000.0, 1, 1000)
        b = BITPIntent(b"\x02"*32, b"\xBB"*32, b"\xAA"*32, 1000.0, 137, 1000)
        result = bm.execute_paste(a, b)
        assert result["cross_chain_movement"] == 0
        assert result["bridge"] == "NONE"


# ═══════════════════════════════════════════════════════════════════════════════
# Module 2.6: Netting Engine Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestNettingEngine:
    def test_find_netting_pair(self):
        ne = NettingEngine()
        a = BITPIntent(b"\x01"*32, b"\xAA"*32, b"\xBB"*32, 1000.0, 1, 1000)
        c = BITPIntent(b"\x03"*32, b"\xBB"*32, b"\xAA"*32, 1000.0, 1, 1000)
        pair = ne.find_netting_pair(a, [c])
        assert pair is not None

    def test_netting_gas_is_minimal(self):
        assert NettingEngine().netting_gas_cost() == 0.05


# ═══════════════════════════════════════════════════════════════════════════════
# Module 2.7: Intent Aggregator Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntentAggregator:
    def test_find_aggregation_pool(self):
        ia = IntentAggregator()
        intents = [
            BITPIntent(b"\x01"*32, b"\xAA"*32, b"\xBB"*32, 100.0, 1, 1000),
            BITPIntent(b"\x02"*32, b"\xAA"*32, b"\xBB"*32, 200.0, 1, 1000),
            BITPIntent(b"\x03"*32, b"\xAA"*32, b"\xBB"*32, 150.0, 1, 1000),
        ]
        pool = ia.find_aggregation_pool(intents)
        assert len(pool) >= 3

    def test_per_user_gas_100x_savings(self):
        ia = IntentAggregator()
        per_user = ia.compute_per_user_gas(0.80, 100)
        assert per_user == 0.008


# ═══════════════════════════════════════════════════════════════════════════════
# Module 2.8: OOA Anchor Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestOOAAnchor:
    def test_confidence_grows_with_depth(self):
        ooa = OOAAnchor()
        low = ooa.compute_ooa_confidence(100, 0.85)
        high = ooa.compute_ooa_confidence(1000, 0.85)
        assert high > low

    def test_threshold_higher_for_ooa(self):
        ooa = OOAAnchor()
        assert ooa.compute_ooa_threshold(0.55) > 0.55


# ═══════════════════════════════════════════════════════════════════════════════
# Module 2.9: Shadow Observer Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestShadowObserver:
    def test_reconstruct_shadow_bh(self):
        so = ShadowObserver()
        sources = [{"data": "x", "weight": 0.8}, {"data": "y", "weight": 0.6}]
        bh, conf = so.reconstruct_shadow_bh(sources)
        assert len(bh) == 32
        assert conf > 0

    def test_empty_sources(self):
        so = ShadowObserver()
        bh, conf = so.reconstruct_shadow_bh([])
        assert bh == b"\x00" * 32
        assert conf == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# Module 2.10: State Capsule Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestStateCapsule:
    def test_build_capsule(self):
        scb = StateCapsuleBuilder()
        cap = scb.build_capsule(2000.0, 5.0, b"\x01"*32, b"\x02"*32, 0.95)
        assert cap.price_at_anchor == 2000.0
        assert cap.balance_X == 5.0


# ═══════════════════════════════════════════════════════════════════════════════
# Module 2.11: Failure Classifier Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestFailureClassifier:
    def test_external_cause(self):
        fc = FailureClassifier()
        result = fc.classify(True, True, False, False, False, False, False, False)
        assert result == "EXTERNAL_CAUSE"

    def test_entity_cause(self):
        fc = FailureClassifier()
        result = fc.classify(False, False, False, False, True, True, False, False)
        assert result == "ENTITY_CAUSE"

    def test_ambiguous_first_time_external_benefit(self):
        fc = FailureClassifier()
        result = fc.classify(False, False, False, False, False, False, False, False,
                             prior_ambiguous_count=0)
        assert result == "EXTERNAL_CAUSE"

    def test_ambiguous_third_time_entity(self):
        fc = FailureClassifier()
        result = fc.classify(False, False, False, False, False, False, False, False,
                             prior_ambiguous_count=2)
        assert result == "ENTITY_CAUSE"


# ═══════════════════════════════════════════════════════════════════════════════
# Module 2.12-2.18: Remaining Modules
# ═══════════════════════════════════════════════════════════════════════════════

class TestGenesisCommitment:
    def test_initiate_genesis(self):
        gc = GenesisCommitmentProcessor()
        result = gc.initiate_genesis(b"\x01"*32, "stake", 1000.0)
        assert result["conf_genesis"] == 0.01

    def test_invalid_pathway(self):
        gc = GenesisCommitmentProcessor()
        with pytest.raises(ValueError):
            gc.initiate_genesis(b"\x01"*32, "invalid")


class TestBLOScheduler:
    def test_find_optimal_window(self):
        bs = BLOScheduler()
        window = bs.find_optimal_window([2, 3, 4], [3, 4, 5], [4, 5, 6])
        assert window == [4]


class TestBehavioralStateChannel:
    def test_open_operate_close(self):
        bsc = BehavioralStateChannel()
        bsc.open_channel("ch1", b"\x01"*32, b"\x02"*32, 1000.0, 1000.0, b"\x03"*32)
        for _ in range(50):
            assert bsc.operate("ch1", {"action": "swap"})
        assert bsc.close_channel("ch1", {"final": True})
        assert bsc._channels["ch1"]["interaction_count"] == 50


class TestFinalityNormalizer:
    def test_max_not_sum(self):
        fn = FinalityNormalizer()
        assert fn.effective_latency(12.0, 2.0) == 12.0  # max, not 14 (sum)

    def test_eth_to_base(self):
        fn = FinalityNormalizer()
        # ETH 12s, Base 2s → effective 12s
        assert fn.effective_latency(12.0, 2.0) == 12.0


class TestVersionHandler:
    def test_compatible(self):
        vh = VersionHandler()
        assert vh.is_compatible("2.1.0", "2.0.0")
        assert not vh.is_compatible("1.5.0", "2.0.0")

    def test_breaking_change(self):
        vh = VersionHandler()
        assert vh.is_breaking_change("1.0.0", "2.0.0")
        assert not vh.is_breaking_change("2.0.0", "2.1.0")


class TestValidatorFeeCalculator:
    def test_rarity_factor(self):
        vfc = ValidatorFeeCalculator()
        # 5% of validators cover chain → rarity = 20
        assert vfc.compute_rarity_factor(5, 100) == 20.0

    def test_btcp_route_split(self):
        vfc = ValidatorFeeCalculator()
        assert vfc.compute_btcp_route_reward(100.0, is_anchor=True) == 60.0
        assert vfc.compute_btcp_route_reward(100.0, is_anchor=False) == 40.0

    def test_coverage_bonus(self):
        vfc = ValidatorFeeCalculator()
        bonus = vfc.compute_coverage_bonus(
            chains_covered=[1, 137],
            validators_per_chain={1: 50, 137: 10},
            total_validators=100,
            volume_per_chain={1: 0.8, 137: 0.5},
            uptime_per_chain={1: 0.99, 137: 0.95},
        )
        assert bonus > 0


class TestSybilResistance:
    def test_layer1_max_sponsored(self):
        sr = SybilResistance()
        assert sr.layer1_max_sponsored(10000, 100) > 0

    def test_layer2_scrutuity(self):
        sr = SybilResistance()
        assert sr.layer2_scrutiny_multiplier(5) == 2.0

    def test_layer3_sockpuppet_alert(self):
        sr = SybilResistance()
        assert sr.layer3_is_sockpuppet(0.90)
        assert not sr.layer3_is_sockpuppet(0.80)

    def test_layer4_quadratic_spacing(self):
        sr = SybilResistance()
        assert sr.layer4_min_spacing_days(3) == 63  # 7 × 9

    def test_layer5_star_pattern(self):
        sr = SybilResistance()
        graph = {b"\x01"*32: [b"\x02"*32] * 25}
        suspicious = sr.layer5_detect_star_pattern(graph)
        assert len(suspicious) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Orchestrator ZK honesty (deep-read fix: dummy proof + hardcoded IAP economics)
# ═══════════════════════════════════════════════════════════════════════════════

class TestOrchestratorZKHonesty:
    """
    The STANDARD privacy level previously fabricated a "dummy complementarity
    proof" from secrets.token_bytes(32) with a hardcoded block 18,000,000, and
    the IAP share witness used hardcoded economics (1M gas / 151k entity gas /
    0.01 ETH fee / 0.0015 share / 10 participants). Now:

      - real witness data  -> real proofs (verified)
      - missing witness    -> honest deferral {"zk_proof": None, "status":
        "zk_pending"} and verify_proofs() fails closed.
    """

    def _intent(self):
        from core.btcp.orchestrator import PrivacyRouter, PrivacyLevel
        from adapters import BTCPIntent
        import time as _t
        intent = BTCPIntent(
            intent_id="t_zk",
            source_chain=1,
            dest_chain=42161,
            source_address="0x1F98431c8aD98523631AE4a59f267346ea31F984",
            dest_address="0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
            amount=10**18,
            asset="ETH",
            intent_type="SWAP",
            deadline=int(_t.time()) + 3600,
            nonce=7,
        )
        return intent

    def test_missing_witness_defers_honestly(self):
        from core.btcp.orchestrator import PrivacyRouter, PrivacyLevel
        router = PrivacyRouter()
        proofs = router.generate_proofs(self._intent(), PrivacyLevel.STANDARD)
        # API shape preserved: keys still present
        assert set(proofs) >= {"intent_commitment", "complementarity", "iap_share"}
        # intent commitment is always real (derived from the actual intent)
        assert proofs["intent_commitment"].get("status") != "zk_pending"
        # no witness data → honest pending, never fake proof bytes
        comp = proofs["complementarity"]
        assert comp["zk_proof"] is None
        assert comp["status"] == "zk_pending"
        assert "reason" in comp
        iap = proofs["iap_share"]
        assert iap["zk_proof"] is None
        assert iap["status"] == "zk_pending"
        # fail closed: a route with deferred circuits is not "all valid"
        all_valid, errors = router.verify_proofs(proofs)
        assert all_valid is False
        assert any("complementarity" in e for e in errors)
        assert any("iap_share" in e for e in errors)

    def test_real_witness_generates_real_proofs(self):
        import secrets
        from core.btcp.orchestrator import PrivacyRouter, PrivacyLevel
        router = PrivacyRouter()
        sense = secrets.token_bytes(32)                    # test fixture strands
        antisense = bytes(b ^ 0xFF for b in sense)         # true complement
        proofs = router.generate_proofs(
            self._intent(), PrivacyLevel.STANDARD,
            behavioral_data={
                "genomic_sense": sense.hex(),
                "genomic_antisense": antisense.hex(),
                "block_number": 18_500_000,
            },
            iap_economics={
                "total_gas": 2_400_000, "entity_gas": 240_000,
                "total_btcp_fee_wei": int(0.02 * 10**18),
                "entity_share_wei": int(0.002 * 10**18),
                "num_participants": 12,
            },
        )
        deferred = [n for n, p in proofs.items()
                    if isinstance(p, dict) and p.get("status") == "zk_pending"]
        assert not deferred, f"real witness must yield real proofs: {deferred}"
        # the real IAP witness reflects the supplied economics, not the old
        # hardcoded 1_000_000 gas / 10 participants. entity_gas is committed
        # (not public); fair_allocation=True proves the supplied share
        # matches the entity_gas/total_gas fraction (240k/2.4M = 1/12).
        pi = proofs["iap_share"]["public_inputs"]
        assert pi.get("total_gas") == 2_400_000
        assert pi.get("num_participants") == 12
        assert pi.get("fair_allocation") is True
        all_valid, errors = router.verify_proofs(proofs)
        assert all_valid, f"real proofs must verify: {errors}"

    def test_gas_estimates_flow_into_iap_witness(self):
        import secrets
        from dataclasses import dataclass
        from core.btcp.orchestrator import PrivacyRouter, PrivacyLevel

        @dataclass
        class _Gas:
            gas_limit: int = 0

        router = PrivacyRouter()
        proofs = router.generate_proofs(
            self._intent(), PrivacyLevel.BASIC,
            gas_estimates=[_Gas(120_000), _Gas(80_000)],
            iap_economics={
                "total_gas": 2_400_000,
                "total_btcp_fee_wei": int(0.02 * 10**18),
                # fair share for a 200k/2.4M = 1/12 gas fraction — proves the
                # real adapter estimates (120k + 80k) flowed into the witness:
                # with the old hardcoded entity_gas (151k) this share would
                # NOT verify as fair and the proof would fail.
                "entity_share_wei": int(0.02 * 10**18 / 12),
                "num_participants": 12,
            },
        )
        pi = proofs["iap_share"]["public_inputs"]
        assert pi.get("total_gas") == 2_400_000
        assert pi.get("fair_allocation") is True
        all_valid, errors = router.verify_proofs(proofs)
        assert all_valid, f"proof over real estimates must verify: {errors}"

    def test_orchestrator_route_keeps_pending_shape(self):
        from core.btcp.orchestrator import BTCPOrchestrator, PrivacyLevel
        orch = BTCPOrchestrator()
        result = orch.create_route(
            source_chain=1,
            dest_chain=42161,
            source_address="0x1F98431c8aD98523631AE4a59f267346ea31F984",
            dest_address="0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
            amount=10**18,
            asset="ETH",
            intent_type="SWAP",
            privacy_level=PrivacyLevel.STANDARD,
        )
        assert result.success
        route = result.route
        # API shape preserved: proofs dict still carries all circuit keys
        assert {"intent_commitment", "complementarity", "iap_share"} <= set(route.proofs)
        assert route.proofs["complementarity"]["status"] == "zk_pending"
        # zero-bridge invariant untouched
        assert route.assets_bridged is False
        d = route.to_dict()  # serialization still works with pending entries
        assert "proofs" in d
