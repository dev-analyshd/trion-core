"""
Phase 0 — Formal tests for Hash_DNA, 7-Plane Coherence, 7 MF Fingerprints.
"""
import pytest
from core.primitives.hash_dna import (
    HashDNAEvent, hash_dna, hash_dna_hex, build_event,
    compute_domain_separator, compute_currency_id,
    normalize_magnitude_18dec,
    context_hash_swap, context_hash_transfer, context_hash_borrow,
    context_hash_stake, context_hash_liquidity, context_hash_generic,
    context_hash_none, keccak256, run_test_vectors,
)
from core.planes.seven_plane_coherence import (
    PlaneType, PlaneInput, PlaneResult,
    PLANE_WEIGHTS, MAGNITUDE_Z_THRESHOLD, VELOCITY_MAX_MULTIPLIER,
    check_magnitude, check_temporal, check_protocol, check_counterparty,
    check_velocity, check_cross_chain, check_statistical,
    compute_7plane_coherence, coherence_with_conscious_review,
)
from core.manipulation.btcp_mf_detector import (
    MFType, MFInput, MFResult, MF_WEIGHTS,
    detect_t1_sandwich, detect_t2_wash, detect_t3_oracle,
    detect_t4_layering, detect_t5_spoofing, detect_t6_cross_protocol,
    detect_t7_statistical, compute_mf_score, aggregate_chain_mf,
)


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 0.1 — Hash_DNA Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestHashDNAVectors:
    """Hash_DNA test vectors from the formal spec (Gap 7 Resolution)."""

    def test_run_all_test_vectors(self):
        """Run the built-in test vector suite."""
        results = run_test_vectors()
        assert results["all_tests_passed"] is True

    def test_hash_dna_returns_32_bytes(self):
        event = build_event(
            entity_id=b"\x01" * 32, event_type_id=1, raw_amount=10**18,
            asset_decimals=18, asset_chain_id=1,
            asset_address="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            asset_symbol="USDC", timestamp=1700000000, block_number=18000000,
            block_hash=b"\xcc" * 32, chain_id=1,
            contract_address="0x1d129D34279d1246aB08a41dfE610EaF8D794237",
        )
        h = hash_dna(event)
        assert len(h) == 32

    def test_hash_dna_hex_has_0x_prefix(self):
        event = build_event(
            entity_id=b"\x01" * 32, event_type_id=1, raw_amount=10**18,
            asset_decimals=18, asset_chain_id=1,
            asset_address="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            asset_symbol="USDC", timestamp=1700000000, block_number=18000000,
            block_hash=b"\xcc" * 32, chain_id=1,
            contract_address="0x1d129D34279d1246aB08a41dfE610EaF8D794237",
        )
        h = hash_dna_hex(event)
        assert h.startswith("0x")
        assert len(h) == 66  # 0x + 64 hex chars

    def test_determinism(self):
        """Same input → same output."""
        kwargs = dict(
            entity_id=b"\x01" * 32, event_type_id=1, raw_amount=10**18,
            asset_decimals=18, asset_chain_id=1,
            asset_address="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            asset_symbol="USDC", timestamp=1700000000, block_number=18000000,
            block_hash=b"\xcc" * 32, chain_id=1,
            contract_address="0x1d129D34279d1246aB08a41dfE610EaF8D794237",
        )
        h1 = hash_dna(build_event(**kwargs))
        h2 = hash_dna(build_event(**kwargs))
        assert h1 == h2

    def test_different_nonce_different_hash(self):
        """Replay protection: different nonce → different hash."""
        kwargs = dict(
            entity_id=b"\x01" * 32, event_type_id=1, raw_amount=10**18,
            asset_decimals=18, asset_chain_id=1,
            asset_address="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            asset_symbol="USDC", timestamp=1700000000, block_number=18000000,
            block_hash=b"\xcc" * 32, chain_id=1,
            contract_address="0x1d129D34279d1246aB08a41dfE610EaF8D794237",
        )
        h1 = hash_dna(build_event(nonce=0, **kwargs))
        h2 = hash_dna(build_event(nonce=1, **kwargs))
        assert h1 != h2

    def test_different_entity_different_hash(self):
        kwargs = dict(
            event_type_id=1, raw_amount=10**18, asset_decimals=18,
            asset_chain_id=1, asset_address="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            asset_symbol="USDC", timestamp=1700000000, block_number=18000000,
            block_hash=b"\xcc" * 32, chain_id=1,
            contract_address="0x1d129D34279d1246aB08a41dfE610EaF8D794237",
        )
        h1 = hash_dna(build_event(entity_id=b"\x01" * 32, **kwargs))
        h2 = hash_dna(build_event(entity_id=b"\x02" * 32, **kwargs))
        assert h1 != h2

    def test_different_chain_different_hash(self):
        """Cross-chain domain separation."""
        kwargs = dict(
            entity_id=b"\x01" * 32, event_type_id=1, raw_amount=10**18,
            asset_decimals=18, asset_chain_id=1,
            asset_address="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            asset_symbol="USDC", timestamp=1700000000, block_number=18000000,
            block_hash=b"\xcc" * 32,
            contract_address="0x1d129D34279d1246aB08a41dfE610EaF8D794237",
        )
        h1 = hash_dna(build_event(chain_id=1, **kwargs))
        h2 = hash_dna(build_event(chain_id=137, **kwargs))
        assert h1 != h2


class TestMagnitudeNormalization:
    """Magnitude normalization: raw_amount × 10^(18 - asset_decimals)."""

    def test_6_decimals_to_18(self):
        # 1M USDC (6 dec) → 1e18 at 18 dec
        assert normalize_magnitude_18dec(1_000_000, 6) == 10**18

    def test_18_decimals_noop(self):
        assert normalize_magnitude_18dec(10**18, 18) == 10**18

    def test_8_decimals(self):
        # 1 token at 8 dec → 1e18 at 18 dec
        assert normalize_magnitude_18dec(10**8, 8) == 10**18

    def test_0_decimals(self):
        assert normalize_magnitude_18dec(1, 0) == 10**18

    def test_rejects_negative_decimals(self):
        with pytest.raises(ValueError):
            normalize_magnitude_18dec(100, -1)

    def test_rejects_excessive_decimals(self):
        with pytest.raises(ValueError):
            normalize_magnitude_18dec(100, 37)


class TestDomainSeparator:
    def test_deterministic(self):
        ds1 = compute_domain_separator(1, "0x1d129D34279d1246aB08a41dfE610EaF8D794237")
        ds2 = compute_domain_separator(1, "0x1d129D34279d1246aB08a41dfE610EaF8D794237")
        assert ds1 == ds2

    def test_case_insensitive_address(self):
        ds1 = compute_domain_separator(1, "0x1d129D34279d1246aB08a41dfE610EaF8D794237")
        ds2 = compute_domain_separator(1, "0x1d129d34279d1246ab08a41dfe610eaf8d794237")
        assert ds1 == ds2

    def test_different_chain_different_separator(self):
        ds1 = compute_domain_separator(1, "0xabc")
        ds2 = compute_domain_separator(137, "0xabc")
        assert ds1 != ds2

    def test_different_contract_different_separator(self):
        ds1 = compute_domain_separator(1, "0xabc")
        ds2 = compute_domain_separator(1, "0xdef")
        assert ds1 != ds2


class TestCurrencyID:
    def test_deterministic(self):
        cid1 = compute_currency_id(1, "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", "USDC")
        cid2 = compute_currency_id(1, "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", "USDC")
        assert cid1 == cid2

    def test_different_symbol_different_id(self):
        cid1 = compute_currency_id(1, "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", "USDC")
        cid2 = compute_currency_id(1, "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", "USDT")
        assert cid1 != cid2


class TestContextHashes:
    def test_swap_context_hash(self):
        h = context_hash_swap(b"\x01" * 32, b"\x02" * 32, 2000, 50)
        assert len(h) == 32

    def test_transfer_context_hash(self):
        h = context_hash_transfer(b"\x01" * 32, 137, "0xabc")
        assert len(h) == 32

    def test_borrow_context_hash(self):
        h = context_hash_borrow(b"\x01" * 32, b"\x02" * 32, 7500)
        assert len(h) == 32

    def test_stake_context_hash(self):
        h = context_hash_stake(b"\x01" * 32, 1000, b"\x02" * 32)
        assert len(h) == 32

    def test_liquidity_context_hash(self):
        h = context_hash_liquidity(b"\x01" * 32, b"\x02" * 32, 30)
        assert len(h) == 32

    def test_generic_context_hash_bytes(self):
        h = context_hash_generic(b"\x01" * 32, b"\x02" * 32)
        assert len(h) == 32

    def test_generic_context_hash_int(self):
        h = context_hash_generic(42, 100)
        assert len(h) == 32

    def test_none_context_hash(self):
        h = context_hash_none()
        assert h == b"\x00" * 32


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 0.2 — 7-Plane Coherence Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestSevenPlaneWeights:
    def test_weights_sum_to_1(self):
        total = sum(PLANE_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9

    def test_seven_planes_defined(self):
        assert len(PLANE_WEIGHTS) == 7

    def test_specific_weights(self):
        assert PLANE_WEIGHTS[PlaneType.MAGNITUDE] == 0.20
        assert PLANE_WEIGHTS[PlaneType.TEMPORAL] == 0.10
        assert PLANE_WEIGHTS[PlaneType.PROTOCOL] == 0.10
        assert PLANE_WEIGHTS[PlaneType.COUNTERPARTY] == 0.15
        assert PLANE_WEIGHTS[PlaneType.VELOCITY] == 0.20
        assert PLANE_WEIGHTS[PlaneType.CROSS_CHAIN] == 0.20
        assert PLANE_WEIGHTS[PlaneType.STATISTICAL] == 0.05


class TestPlane1Magnitude:
    def test_perfect_consistency(self):
        r = check_magnitude(100.0, [100.0, 100.0, 100.0, 100.0, 100.0])
        assert r.passed
        assert r.score == 1.0

    def test_within_z_threshold(self):
        # z-score should be < 3.0 for typical variation
        # Use values with realistic std dev: [98, 99, 100, 101, 102, 103]
        # mu=100.5, sigma≈1.87, z for 105 = 4.5/1.87 = 2.4 < 3.0 → passes
        r = check_magnitude(105.0, [98.0, 99.0, 100.0, 101.0, 102.0, 103.0])
        assert r.passed

    def test_exceeds_z_threshold(self):
        # z-score = |110 - 100| / 2 = 5.0 > 3.0 → fails
        r = check_magnitude(110.0, [100.0, 100.0, 100.0, 100.0, 100.0, 102.0])
        assert not r.passed

    def test_insufficient_history(self):
        r = check_magnitude(100.0, [100.0])
        assert r.passed  # benefit of the doubt
        assert r.score == 0.5


class TestPlane2Temporal:
    def test_strong_temporal_pattern(self):
        _now = 1_700_000_000
        # 19 events at the same hour, 1 day apart
        times = [_now - i * 86400 for i in range(1, 20)]
        r = check_temporal(_now, "circadian_peak", times)
        assert r.passed
        assert r.score > 0.5

    def test_no_temporal_pattern(self):
        _now = 1_700_000_000
        # Events spread across all hours — no peak
        times = [_now - i * 3600 for i in range(1, 24)]  # 23 different hours
        r = check_temporal(_now, "normal", times)
        # Current hour is not in historical hours
        assert not r.passed or r.score < 0.5

    def test_insufficient_history(self):
        r = check_temporal(1700000000, "normal", [1700000000 - 3600])
        assert r.score == 0.5


class TestPlane3Protocol:
    def test_familiar_protocol(self):
        r = check_protocol("uniswap", ["uniswap"] * 15 + ["curve"] * 3)
        assert r.passed
        assert r.score > 0.5

    def test_new_protocol_with_exploration(self):
        # Entity used 4 different protocols — exploration behavior
        r = check_protocol("new_protocol", ["a", "b", "c", "d"])
        assert r.passed  # allowed due to exploration

    def test_new_entity(self):
        r = check_protocol("uniswap", [])
        assert r.passed
        assert r.score == 0.5


class TestPlane4Counterparty:
    def test_direct_counterparty(self):
        graph = {"self": ["0xabc", "0xdef"], "0xabc": ["self"], "0xdef": ["self"]}
        r = check_counterparty("0xabc", graph)
        assert r.passed
        assert r.score > 0.5

    def test_no_counterparty(self):
        r = check_counterparty("", {})
        assert r.passed
        assert r.score == 1.0

    def test_unknown_counterparty(self):
        graph = {"self": ["0xabc"]}
        r = check_counterparty("0xxyz", graph)
        assert not r.passed


class TestPlane5Velocity:
    def test_normal_velocity(self):
        r = check_velocity(10, 10.0)
        assert r.passed
        assert r.score == 1.0

    def test_velocity_spike(self):
        r = check_velocity(100, 10.0)  # 10x spike
        assert not r.passed
        assert r.score == 0.0

    def test_below_average(self):
        r = check_velocity(5, 10.0)  # half average
        assert r.passed
        assert r.score == 1.0


class TestPlane6CrossChain:
    def test_perfect_agreement(self):
        vecs = {1: [0.8, 0.7, 0.9], 137: [0.8, 0.7, 0.9]}
        r = check_cross_chain(vecs)
        assert r.passed
        assert r.score > 0.999  # floating-point tolerance

    def test_divergent_chains(self):
        vecs = {1: [1.0, 0.0, 0.0], 137: [0.0, 1.0, 0.0]}
        r = check_cross_chain(vecs)
        assert not r.passed
        assert r.score < 0.5

    def test_single_chain(self):
        vecs = {1: [0.8, 0.7, 0.9]}
        r = check_cross_chain(vecs)
        assert r.passed
        assert r.score == 1.0


class TestPlane7Statistical:
    def test_minor_kc_change(self):
        r = check_statistical(0.51, 0.50)
        assert r.passed
        assert not r.needs_conscious_review

    def test_major_kc_change(self):
        r = check_statistical(0.80, 0.50)  # 60% increase
        assert r.needs_conscious_review

    def test_no_baseline(self):
        r = check_statistical(0.5, 0.0)
        assert r.passed


class TestSevenPlaneCoherence:
    def _perfect_input(self):
        _now = 1_700_000_000
        return PlaneInput(
            magnitude=100.0,
            historical_magnitudes=[99.0, 100.0, 101.0, 100.0, 99.5],
            event_timestamp=_now,
            brt_phase="circadian_peak",
            historical_event_times=[_now - i * 86400 for i in range(1, 20)],
            protocol_id="uniswap_v3",
            historical_protocols=["uniswap_v3"] * 15 + ["curve"] * 3,
            counterparty_id="0xabc",
            behavioral_graph={"self": ["0xabc", "0xdef"], "0xabc": ["self"], "0xdef": ["self"]},
            recent_tx_count=10,
            historical_avg_per_N=10.0,
            behavioral_vectors={1: [0.8, 0.7, 0.9, 0.8], 137: [0.79, 0.71, 0.88, 0.81]},
            recent_kc=0.50,
            historical_kc=0.49,
        )

    def test_perfect_input_high_score(self):
        score, results = compute_7plane_coherence(self._perfect_input())
        assert score > 0.7
        assert all(r.passed for r in results)

    def test_returns_7_results(self):
        score, results = compute_7plane_coherence(self._perfect_input())
        assert len(results) == 7

    def test_conscious_review_adjustment(self):
        inp = self._perfect_input()
        # Use a smaller delta so plane 7 score is non-zero but review is triggered
        inp.recent_kc = 0.555  # 11% increase from 0.50 — triggers review (>10%)
        inp.historical_kc = 0.50
        score, results = compute_7plane_coherence(inp)
        assert results[6].needs_conscious_review

        # With conscious_review_score=0 (reject), score should be lower
        score_rejected, _ = coherence_with_conscious_review(inp, conscious_review_score=0.0)
        assert score_rejected < score


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 0.3 — 7 MF Fingerprint Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestMFWeights:
    def test_weights_sum_to_1(self):
        total = sum(MF_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9

    def test_seven_types_defined(self):
        assert len(MF_WEIGHTS) == 7

    def test_specific_weights(self):
        assert MF_WEIGHTS[MFType.T1_SANDWICH] == 0.20
        assert MF_WEIGHTS[MFType.T2_WASH_TRADING] == 0.15
        assert MF_WEIGHTS[MFType.T3_ORACLE_MANIP] == 0.25
        assert MF_WEIGHTS[MFType.T4_LAYERING] == 0.15
        assert MF_WEIGHTS[MFType.T5_SPOOFING] == 0.10
        assert MF_WEIGHTS[MFType.T6_CROSS_PROTOCOL] == 0.10
        assert MF_WEIGHTS[MFType.T7_STATISTICAL] == 0.05


class TestT1Sandwich:
    def test_detects_sandwich(self):
        inp = MFInput(
            intent_a_side="BUY", intent_b_side="SELL",
            victim_tx_between=True, magnitude_similarity=0.95,
        )
        r = detect_t1_sandwich(inp)
        assert r.detected

    def test_no_victim_no_detection(self):
        inp = MFInput(
            intent_a_side="BUY", intent_b_side="SELL",
            victim_tx_between=False, magnitude_similarity=0.95,
        )
        r = detect_t1_sandwich(inp)
        assert not r.detected

    def test_same_side_no_detection(self):
        inp = MFInput(
            intent_a_side="BUY", intent_b_side="BUY",
            victim_tx_between=True, magnitude_similarity=0.95,
        )
        r = detect_t1_sandwich(inp)
        assert not r.detected


class TestT2Wash:
    def test_detects_wash(self):
        inp = MFInput(self_trade_ratio=0.8, counterparty_diversity=0.2, trade_frequency=8.0)
        r = detect_t2_wash(inp)
        assert r.detected

    def test_no_self_trade_no_detection(self):
        inp = MFInput(self_trade_ratio=0.0, counterparty_diversity=1.0, trade_frequency=1.0)
        r = detect_t2_wash(inp)
        assert not r.detected


class TestT3Oracle:
    def test_detects_oracle_manip(self):
        inp = MFInput(
            large_swap_deviation=0.20, oracle_update_deviation=0.25,
            borrow_liquidate_within_10_blocks=True,
        )
        r = detect_t3_oracle(inp)
        assert r.detected

    def test_no_exploit_window_no_detection(self):
        inp = MFInput(
            large_swap_deviation=0.20, oracle_update_deviation=0.25,
            borrow_liquidate_within_10_blocks=False,
        )
        r = detect_t3_oracle(inp)
        assert not r.detected


class TestT4Layering:
    def test_detects_layering(self):
        inp = MFInput(order_submission_rate=25.0, order_cancellation_rate=0.9)
        r = detect_t4_layering(inp)
        assert r.detected

    def test_low_cancellation_no_detection(self):
        inp = MFInput(order_submission_rate=25.0, order_cancellation_rate=0.1)
        r = detect_t4_layering(inp)
        assert not r.detected


class TestT5Spoofing:
    def test_detects_spoofing(self):
        inp = MFInput(behavioral_similarity_to_high_D=0.92, own_D=50.0, high_D_threshold=1000.0)
        r = detect_t5_spoofing(inp)
        assert r.detected

    def test_high_D_entity_no_detection(self):
        inp = MFInput(behavioral_similarity_to_high_D=0.92, own_D=2000.0, high_D_threshold=1000.0)
        r = detect_t5_spoofing(inp)
        assert not r.detected


class TestT6CrossProtocol:
    def test_detects_coordination(self):
        inp = MFInput(correlated_timing_score=0.85, protocol_overlap_count=4)
        r = detect_t6_cross_protocol(inp)
        assert r.detected

    def test_single_protocol_no_detection(self):
        inp = MFInput(correlated_timing_score=0.85, protocol_overlap_count=1)
        r = detect_t6_cross_protocol(inp)
        assert not r.detected


class TestT7Statistical:
    def test_detects_anomaly(self):
        inp = MFInput(historical_kc=0.5, kc_complexity_delta=0.25)
        r = detect_t7_statistical(inp)
        assert r.detected

    def test_minor_change_no_detection(self):
        inp = MFInput(historical_kc=0.5, kc_complexity_delta=0.02)
        r = detect_t7_statistical(inp)
        assert not r.detected


class TestMFScore:
    def test_clean_entity_low_score(self):
        inp = MFInput(
            self_trade_ratio=0.0, counterparty_diversity=1.0, trade_frequency=1.0,
            order_submission_rate=1.0, order_cancellation_rate=0.1,
            own_D=500.0, high_D_threshold=1000.0,
            historical_kc=0.5, kc_complexity_delta=0.02,
        )
        score, results, review = compute_mf_score(inp)
        assert score < 0.1
        assert not review

    def test_t7_holds_at_0_5(self):
        inp = MFInput(historical_kc=0.5, kc_complexity_delta=0.25)
        score, results, review = compute_mf_score(inp)
        assert review
        assert score >= 0.5

    def test_multi_attack_highest_weight_wins(self):
        inp = MFInput(
            # T3 (weight 0.25) detected
            large_swap_deviation=0.2, oracle_update_deviation=0.25,
            borrow_liquidate_within_10_blocks=True,
            # T1 (weight 0.20) also detected
            intent_a_side="BUY", intent_b_side="SELL",
            victim_tx_between=True, magnitude_similarity=0.95,
        )
        score, results, _ = compute_mf_score(inp)
        detected_types = [r.mf_type for r in results if r.detected]
        assert MFType.T1_SANDWICH in detected_types
        assert MFType.T3_ORACLE_MANIP in detected_types
        # T3 has highest weight (0.25)
        assert score >= 0.25


class TestChainMFAggregation:
    def test_empty_list(self):
        assert aggregate_chain_mf([]) == 0.0

    def test_max_entity_score(self):
        scores = [0.1, 0.5, 0.9, 0.3]
        chain_mf = aggregate_chain_mf(scores)
        assert chain_mf >= 0.9

    def test_boost_for_elevated_fraction(self):
        # >20% of entities with elevated MF → boost
        scores = [0.5, 0.5, 0.5, 0.5, 0.5]  # 100% elevated
        chain_mf = aggregate_chain_mf(scores)
        assert chain_mf >= 0.5  # at least max
