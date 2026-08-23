"""
TRION + BTCP + CONTINUUM — Phase 5: Full System Integration Test
=================================================================

Per BTCP Master Spec §Phase 5, this test exercises the full end-to-end
pipeline:

  Intent → BIBL → Route selection → Escrow lock → Execution → Settlement
         → Akashic recording

This test wires together all modules from Phases 0-4 and verifies that
the entire pipeline works as designed.
"""

from __future__ import annotations

import time
import hashlib
import pytest
from dataclasses import dataclass

# Phase 0 modules
from core.primitives.hash_dna import hash_dna, build_event, HashDNAEvent
from core.planes.seven_plane_coherence import (
    PlaneInput, compute_7plane_coherence, PlaneType,
)
from core.manipulation.btcp_mf_detector import (
    MFInput, compute_mf_score,
)

# Phase 2 modules (BTCP)
from core.btcp.router import (
    BIBLState, Route, RouteType, btcp_score_final, select_optimal_route,
)
from core.btcp.escrow_monitor import (
    EscrowMonitor, EscrowState, RevertReason,
)
from core.btcp.bibl_engine import BIBLEngine, EndpointDiversity
from core.btcp.modules import (
    BTCPProofBuilder, ValidatorSignature, BITPMatcher, BITPIntent,
    NettingEngine, IntentAggregator, FailureClassifier,
    FinalityNormalizer, ValidatorFeeCalculator, SybilResistance,
)

# Phase 3 modules
from core.btcp.integration import (
    BTCPIntegrationHub, PrivateBIBLProtocol, PrivacyLevel,
)

# Phase 4 modules (CONTINUUM)
from continuum.engines import (
    BIDEngine, CMEEngine, PMOSystem, BDCEngine,
    ThermodynamicSettlement, CCPDistribution,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Full Pipeline Integration Test
# ═══════════════════════════════════════════════════════════════════════════════

class TestFullPipeline:
    """
    End-to-end pipeline test:
      1. Entity initiates intent (Hash_DNA commitment)
      2. BIBL computes route scores (BTCP_score)
      3. 7-plane coherence check
      4. MF fingerprint check
      5. Escrow lock
      6. BID detects behavioral intent
      7. CME finds complement
      8. PMO creates pre-manifest order
      9. BDC computes credit limit
      10. Thermodynamic settlement trigger
      11. CCP distribution
      12. Escrow release
      13. Akashic recording (Hash_DNA of execution event)
    """

    def test_full_pipeline_happy_path(self):
        """Happy path: all conditions met, settlement succeeds."""
        now = int(time.time())

        # ── Step 1: Entity initiates intent ──────────────────────────────────
        intent_event = build_event(
            entity_id=b"\x01" * 32,
            event_type_id=1,  # SWAP
            raw_amount=1_000_000_000,  # 1000 USDC (6 dec)
            asset_decimals=6,
            asset_chain_id=1,
            asset_address="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            asset_symbol="USDC",
            timestamp=now,
            block_number=18_000_000,
            block_hash=b"\xcc" * 32,
            chain_id=1,
            contract_address="0x1d129D34279d1246aB08a41dfE610EaF8D794237",
            nonce=0,
        )
        intent_hash = hash_dna(intent_event)
        assert len(intent_hash) == 32

        # ── Step 2: BIBL computes route scores ──────────────────────────────
        bibl_state = BIBLState(
            nl_scores={1: 0.85, 137: 0.90, 8453: 0.88},
            gas_forecasts={1: 31.0, 137: 0.50, 8453: 0.98},
            gas_reference=31.0,
            cc_coherence={1: 0.90, 137: 0.92, 8453: 0.91},
            mf_scores={1: 0.02, 137: 0.01, 8453: 0.01},
            finality_dist={1: 12.0, 137: 2.0, 8453: 2.0},
        )
        route = select_optimal_route(
            intent_value=1000.0,
            entity_id=b"\x01" * 32,
            state=bibl_state,
            candidate_chains=[1, 137, 8453],
            validator_counts={1: 50, 137: 40, 8453: 30},
        )
        assert route is not None
        btcp_score = btcp_score_final(route, bibl_state)
        assert btcp_score > 0.10  # MIN_BTCP_SCORE

        # ── Step 3: 7-plane coherence check ─────────────────────────────────
        plane_input = PlaneInput(
            magnitude=1000.0,
            historical_magnitudes=[990, 1000, 1010, 1000, 995],
            event_timestamp=now,
            brt_phase="circadian_peak",
            historical_event_times=[now - i * 86400 for i in range(1, 20)],
            protocol_id="uniswap_v3",
            historical_protocols=["uniswap_v3"] * 15,
            counterparty_id="0xabc",
            behavioral_graph={"self": ["0xabc"], "0xabc": ["self"]},
            recent_tx_count=10,
            historical_avg_per_N=10.0,
            behavioral_vectors={1: [0.8, 0.7, 0.9], 137: [0.79, 0.71, 0.88]},
            recent_kc=0.50,
            historical_kc=0.49,
        )
        coherence, plane_results = compute_7plane_coherence(plane_input)
        assert coherence > 0.55  # above threshold

        # ── Step 4: MF fingerprint check ────────────────────────────────────
        mf_input = MFInput(
            self_trade_ratio=0.0,
            counterparty_diversity=1.0,
            trade_frequency=1.0,
            order_submission_rate=1.0,
            order_cancellation_rate=0.1,
            own_D=500.0,
            high_D_threshold=1000.0,
            historical_kc=0.5,
            kc_complexity_delta=0.02,
        )
        mf_score, mf_results, needs_review = compute_mf_score(mf_input)
        assert mf_score < 0.1  # clean entity
        assert not needs_review

        # ── Step 5: Escrow lock ─────────────────────────────────────────────
        monitor = EscrowMonitor()
        monitor.lock_escrow(
            escrow_id="esc_001",
            route_id=route.route_id,
            entity_id=b"\x01" * 32,
            amount=1000.0,
            timeout_blocks=1000,
            block_number=18_000_000,
        )
        assert monitor.get_escrow("esc_001").state == EscrowState.HOLDING

        # ── Step 6: BID detects behavioral intent ───────────────────────────
        bid = BIDEngine()
        bid_result = bid.detect(
            current_features=[0.9, 0.8, 0.9, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1],
            baseline_features=[0.7, 0.6, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1],
            pretrade_signature=[0.1, 0.1, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            depth_d=500.0,
        )
        assert bid_result.detected
        assert bid_result.direction == "BUY"

        # ── Step 7: CME finds complement ────────────────────────────────────
        cme = CMEEngine()
        vec_a = [1.0] + [0.0] * 127
        vec_b = [0.0, 1.0] + [0.0] * 126
        candidates = [
            {"entity_id": b"\x02" * 32, "vector": vec_b, "direction": "SELL",
             "behavioral_health": 0.85, "liquidity": 0.9, "timestamp": now},
        ]
        cme_result = cme.find_complement(vec_a, "BUY", candidates)
        assert cme_result.matched

        # ── Step 8: PMO creates pre-manifest order ──────────────────────────
        pmo_sys = PMOSystem()
        pmo = pmo_sys.create_pmo(
            entity_id=b"\x01" * 32,
            intent_data=b"swap 1000 USDC for ETH",
            entity_bh=intent_hash,
            nonce=42,
            trion_valuation=2000.0,
            ccp_premium=5.0,
            complement_id=cme_result.complement_id,
        )
        assert pmo.price_guarantee == 2005.0
        assert pmo.status == "ACTIVE"

        # ── Step 9: BDC computes credit limit ───────────────────────────────
        bdc = BDCEngine()
        bdc_result = bdc.compute_credit_limit(
            depth_d=730.0,
            phi_history_90d=[0.8, 0.81, 0.79, 0.8, 0.82, 0.78, 0.8, 0.81, 0.79, 0.8],
            avg_trade_size_90d=1000.0,
        )
        assert bdc_result["credit_limit"] > 0
        assert bdc_result["confidence_multiplier"] == 2.0

        # ── Step 10: Thermodynamic settlement trigger ───────────────────────
        # First: verify settlement (G1 Two-Phase Confirmation)
        monitor.verify_settlement("esc_001")

        settlement = ThermodynamicSettlement()
        trigger = settlement.check_trigger(
            coherence_a=coherence, threshold_a=0.55,
            coherence_b=0.80, threshold_b=0.55,
            btcp_route_verified=True,
            temporal_alignment_valid=True,
            mf_detected=mf_score > 0.3,
        )
        assert trigger.triggered

        # ── Step 11: CCP distribution ───────────────────────────────────────
        ccp = CCPDistribution()
        ccp_result = ccp.compute_ccp(
            best_exchange_spread=0.003,
            btcp_routing_cost=0.0005,
            trade_value=1000.0,
        )
        assert ccp_result["ccp_total"] > 0
        assert ccp_result["ccp_a"] == ccp_result["ccp_b"]  # 40/40 split

        # ── Step 12: Escrow release ─────────────────────────────────────────
        released = monitor.release_escrow(
            "esc_001",
            coherence=coherence,
            min_coherence=0.55,
            block_number=18_000_001,
        )
        assert released
        assert monitor.get_escrow("esc_001").state == EscrowState.RELEASED

        # ── Step 13: Akashic recording (execution event Hash_DNA) ───────────
        execution_event = build_event(
            entity_id=b"\x01" * 32,
            event_type_id=1,  # SWAP
            raw_amount=500_000_000,  # 500 USDC executed
            asset_decimals=6,
            asset_chain_id=137,
            asset_address="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            asset_symbol="USDC",
            timestamp=now + 12,  # 1 block later
            block_number=18_000_001,
            block_hash=b"\xdd" * 32,
            chain_id=137,
            contract_address="0x1d129D34279d1246aB08a41dfE610EaF8D794237",
            counterparty_id=b"\x02" * 32,
            nonce=1,
        )
        execution_hash = hash_dna(execution_event)
        assert len(execution_hash) == 32
        assert execution_hash != intent_hash  # different nonce + chain

    def test_pipeline_failure_mf_detected(self):
        """Pipeline fails when MF is detected — escrow reverts."""
        now = int(time.time())

        # Lock escrow
        monitor = EscrowMonitor()
        monitor.lock_escrow(
            "esc_mf", "route_mf", b"\x01" * 32, 1000.0, 1000,
            block_number=18_000_000,
        )

        # MF detected
        mf_input = MFInput(
            self_trade_ratio=0.9,
            counterparty_diversity=0.1,
            trade_frequency=15.0,
            historical_kc=0.5,
            kc_complexity_delta=0.4,  # huge anomaly
        )
        mf_score, _, _ = compute_mf_score(mf_input)
        assert mf_score >= 0.5  # high MF

        # Settlement trigger fails
        settlement = ThermodynamicSettlement()
        trigger = settlement.check_trigger(
            coherence_a=0.85, threshold_a=0.55,
            coherence_b=0.80, threshold_b=0.55,
            btcp_route_verified=True,
            temporal_alignment_valid=True,
            mf_detected=True,  # MF detected
        )
        assert not trigger.triggered

        # Escrow reverts due to MF
        monitor.verify_settlement("esc_mf")
        # Cannot release with low coherence (MF penalized)
        released = monitor.release_escrow(
            "esc_mf", coherence=0.30, min_coherence=0.55, block_number=18_000_001,
        )
        assert not released

        # Revert on coherence failure
        reverted = monitor.revert_escrow(
            "esc_mf", RevertReason.COHERENCE_FAILURE, block_number=18_000_001,
        )
        assert reverted
        assert monitor.get_escrow("esc_mf").state == EscrowState.REVERTED

    def test_pipeline_emergency_escape(self):
        """Pipeline supports emergency escape after 7 days."""
        monitor = EscrowMonitor()
        monitor.lock_escrow(
            "esc_emerg", "route_emerg", b"\x01" * 32, 5000.0, 100,
            block_number=18_000_000,
        )
        esc = monitor.get_escrow("esc_emerg")
        esc.lock_timestamp = time.time() - 8 * 86400  # 8 days ago

        # Emergency escape available
        assert monitor.emergency_escape_available("esc_emerg")
        assert monitor.revert_emergency("esc_emerg")
        assert monitor.get_escrow("esc_emerg").state == EscrowState.EMERGENCY_REVERTED

    def test_pipeline_cascade_revert(self):
        """Multi-hop cascade revert works end-to-end."""
        monitor = EscrowMonitor()
        monitor.lock_escrow("hop1", "r1", b"\x01"*32, 1000.0, 2000, block_number=100)
        monitor.lock_escrow("hop2", "r2", b"\x01"*32, 800.0, 1000,
                            parent_escrow_id="hop1", block_number=100)
        monitor.lock_escrow("hop3", "r3", b"\x01"*32, 600.0, 500,
                            parent_escrow_id="hop2", block_number=100)

        # hop3 times out → cascade to hop2 → cascade to hop1
        monitor.revert_escrow("hop3", RevertReason.TIMEOUT, block_number=700)

        assert monitor.get_escrow("hop3").state == EscrowState.REVERTED
        assert monitor.get_escrow("hop2").state == EscrowState.REVERTED
        assert monitor.get_escrow("hop2").revert_reason == RevertReason.CASCADE_REVERT
        assert monitor.get_escrow("hop1").state == EscrowState.REVERTED
        assert monitor.get_escrow("hop1").revert_reason == RevertReason.CASCADE_REVERT

    def test_pipeline_private_bibl(self):
        """Private BIBL protocol: encrypt → score → decrypt at execution."""
        proto = PrivateBIBLProtocol()
        proto.set_aggregate_public_key(hashlib.sha3_256(b"DEMO_KEY").digest())

        # Phase 2: Encrypt
        encrypted = proto.encrypt_payload(
            asset_in=b"\xAA" * 32, asset_out=b"\xBB" * 32,
            value=1000.0, max_gas=50.0, min_nl_score=0.30,
        )

        # Phase 3: Private BTCP_score (without decrypting individual intent)
        magnitude_bucket = proto.classify_magnitude_bucket(1000.0, 1000.0)
        score = proto.compute_btcp_score_private(
            public_params={"entity_id": b"\x01" * 32, "action": "SWAP"},
            encrypted_score_components={
                "nl": 0.85, "gas_norm": 0.9, "finality": 0.95,
                "cc": 0.9, "beo": 0.8,
            },
            magnitude_bucket=magnitude_bucket,
        )
        assert 0.0 <= score <= 1.0

        # Phase 4: Decrypt at execution block (zero front-running)
        asset_in, asset_out, value, max_gas, min_nl = proto.decrypt_payload(
            encrypted, validator_shares=[b"s1", b"s2", b"s3"],
        )
        assert value == 1000.0
        assert proto.zero_front_running_window() == 0

    def test_pipeline_validator_fee_distribution(self):
        """Validator fees computed correctly per Fix 4."""
        vfc = ValidatorFeeCalculator()

        # 100 validators, chain covered by 5 → rarity = 20
        rarity = vfc.compute_rarity_factor(5, 100)
        assert rarity == 20.0

        # Coverage bonus for covering underserved chain
        bonus = vfc.compute_coverage_bonus(
            chains_covered=[137],
            validators_per_chain={137: 5},
            total_validators=100,
            volume_per_chain={137: 0.5},
            uptime_per_chain={137: 0.99},
        )
        assert bonus > 0

        # BTCP route reward split: 60% anchor / 40% execution
        assert vfc.compute_btcp_route_reward(100.0, is_anchor=True) == 60.0
        assert vfc.compute_btcp_route_reward(100.0, is_anchor=False) == 40.0

    def test_pipeline_sybil_resistance_all_5_layers(self):
        """5-layer sybil resistance for sponsored genesis."""
        sr = SybilResistance()

        # Layer 1: Logarithmic cap
        max_sponsored = sr.layer1_max_sponsored(10000, 100)
        assert max_sponsored > 0

        # Layer 2: Scrutiny multiplier
        assert sr.layer2_scrutiny_multiplier(5) == 2.0

        # Layer 3: Similarity detection
        assert sr.layer3_is_sockpuppet(0.90)
        assert not sr.layer3_is_sockpuppet(0.80)

        # Layer 4: Quadratic spacing
        assert sr.layer4_min_spacing_days(3) == 63

        # Layer 5: Star pattern detection
        graph = {b"\x01"*32: [b"\x02"*32] * 25}
        suspicious = sr.layer5_detect_star_pattern(graph)
        assert len(suspicious) == 1

    def test_pipeline_finality_normalization(self):
        """Finality = max(A, B), not sum."""
        fn = FinalityNormalizer()
        # ETH (12s) → Base (2s): effective = 12s, not 14s
        assert fn.effective_latency(12.0, 2.0) == 12.0
        assert fn.effective_latency(12.0, 2.0) != 14.0

    def test_pipeline_failure_classifier(self):
        """Route failure classified as EXTERNAL vs ENTITY cause."""
        fc = FailureClassifier()

        # External: chain outage
        assert fc.classify(True, True, False, False, False, False, False, False) == "EXTERNAL_CAUSE"

        # Entity: invalid proof
        assert fc.classify(False, False, False, False, True, True, False, False) == "ENTITY_CAUSE"

    def test_pipeline_bitp_zero_cross_chain_movement(self):
        """BITP: assets never leave their native chains."""
        bm = BITPMatcher()
        intent_a = BITPIntent(b"\x01"*32, b"\xAA"*32, b"\xBB"*32, 1000.0, 1, 1000)
        intent_b = BITPIntent(b"\x02"*32, b"\xBB"*32, b"\xAA"*32, 1000.0, 137, 1000)

        match = bm.find_complement(intent_a, [intent_b])
        assert match is not None

        result = bm.execute_paste(intent_a, intent_b)
        assert result["cross_chain_movement"] == 0
        assert result["bridge"] == "NONE"

    def test_pipeline_intent_aggregation_100x_savings(self):
        """Intent aggregation: 100 users → 100× gas savings."""
        ia = IntentAggregator()
        intents = [
            BITPIntent(bytes([i % 256]) * 32, b"\xAA" * 32, b"\xBB" * 32, 100.0, 1, 1000)
            for i in range(100)
        ]
        pool = ia.find_aggregation_pool(intents)
        assert len(pool) >= 3

        per_user = ia.compute_per_user_gas(0.80, 100)
        assert per_user == 0.008  # 100× cheaper
