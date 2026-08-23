"""
Phase 7 — Tests for new governance modules
============================================
Tests for the 4 new whitepaper-feature modules:
  - Adaptive Consensus recommendations
  - Right to Invisibility enforcement
  - Elder Wisdom Protocol
  - Love Protocol (F coefficient)
"""
import os
import tempfile
import pytest

from core.governance.adaptive_consensus import (
    AdaptiveConsensusEngine,
    ConsensusRecommendation,
    DEFAULT_BLOCK_SIZE,
    DEFAULT_FINALITY,
    MAX_BLOCK_SIZE,
    MIN_BLOCK_SIZE,
)
from core.governance.right_to_invisibility import (
    RightToInvisibility,
    STATE_APPROVED,
    STATE_PENDING,
    STATE_REJECTED,
    STATE_REVOKED,
)
from core.governance.elder_wisdom import (
    ElderWisdomProtocol,
    ELDER_STAKE_MULTIPLIER,
    MIN_PREDICTION_ACC,
    MIN_TENURE_SECONDS,
)
from core.governance.love_protocol import (
    LoveInputs,
    LoveProtocol,
    PILLARS,
)


# ── Adaptive Consensus tests ───────────────────────────────────────────────────

class TestAdaptiveConsensus:
    def test_healthy_chain_produces_minimal_recommendations(self):
        engine = AdaptiveConsensusEngine()
        recs = engine.compute_recommendations(
            chain_id=1, sigma_score=0.85, mf_rate=0.001, mev_rate=0.001,
            hhi=800, validator_count=200,
        )
        # Healthy chain should produce 0-1 recommendations (block_size only)
        assert len(recs) <= 1

    def test_stressed_chain_produces_multiple_recommendations(self):
        engine = AdaptiveConsensusEngine()
        recs = engine.compute_recommendations(
            chain_id=137, sigma_score=0.30, mf_rate=0.08, mev_rate=0.02,
            hhi=3500, validator_count=30,
        )
        # Stressed chain should produce ≥4 recommendations
        assert len(recs) >= 4
        params = [r.parameter for r in recs]
        assert "block_size_limit" in params
        assert "gas_limit" in params
        assert "finality_threshold" in params
        assert "slashing_threshold_pct" in params
        assert "validator_set_size" in params

    def test_block_size_within_bounds(self):
        engine = AdaptiveConsensusEngine()
        recs = engine.compute_recommendations(
            chain_id=1, sigma_score=0.5, mf_rate=0.0, hhi=1000, validator_count=50,
        )
        for r in recs:
            if r.parameter == "block_size_limit":
                assert MIN_BLOCK_SIZE <= r.recommended_value <= MAX_BLOCK_SIZE

    def test_recommendation_includes_rationale_and_confidence(self):
        engine = AdaptiveConsensusEngine()
        recs = engine.compute_recommendations(
            chain_id=1, sigma_score=0.3, hhi=3000, validator_count=10,
        )
        for r in recs:
            assert isinstance(r.rationale, str) and len(r.rationale) > 0
            assert 0.0 <= r.confidence <= 1.0

    def test_to_dict_serialization(self):
        engine = AdaptiveConsensusEngine()
        recs = engine.compute_recommendations(chain_id=1, sigma_score=0.3)
        for r in recs:
            d = r.to_dict()
            assert "chain_id" in d
            assert "parameter" in d
            assert "recommended_value" in d
            assert "rationale" in d


# ── Right to Invisibility tests ────────────────────────────────────────────────

class TestRightToInvisibility:
    @pytest.fixture
    def rtiv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = os.path.join(tmpdir, "test.db")
            yield RightToInvisibility(db_path=db)

    def test_submit_returns_petition_id(self, rtiv):
        pid = rtiv.submit_petition("e1", b"proof", "reason")
        assert isinstance(pid, str) and len(pid) > 0

    def test_pending_petition_not_invisible(self, rtiv):
        pid = rtiv.submit_petition("e1", b"proof", "reason")
        assert not rtiv.is_invisible("e1")

    def test_approved_petition_makes_invisible(self, rtiv):
        pid = rtiv.submit_petition("e1", b"proof", "reason")
        assert rtiv.approve(pid, decided_by="gov")
        assert rtiv.is_invisible("e1")

    def test_rejected_petition_not_invisible(self, rtiv):
        pid = rtiv.submit_petition("e1", b"proof", "reason")
        assert rtiv.reject(pid, decided_by="gov")
        assert not rtiv.is_invisible("e1")

    def test_revoked_petition_not_invisible(self, rtiv):
        pid = rtiv.submit_petition("e1", b"proof", "reason")
        rtiv.approve(pid, decided_by="gov")
        assert rtiv.is_invisible("e1")
        rtiv.revoke(pid, decided_by="e1")
        assert not rtiv.is_invisible("e1")

    def test_filter_visible_excludes_invisible(self, rtiv):
        pid = rtiv.submit_petition("e1", b"proof", "reason")
        rtiv.approve(pid, decided_by="gov")
        visible = rtiv.filter_visible(["e1", "e2", "e3"])
        assert "e1" not in visible
        assert "e2" in visible
        assert "e3" in visible

    def test_persistence_across_instances(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = os.path.join(tmpdir, "test.db")
            r1 = RightToInvisibility(db_path=db)
            pid = r1.submit_petition("e1", b"proof", "reason")
            r1.approve(pid, decided_by="gov")

            r2 = RightToInvisibility(db_path=db)
            assert r2.is_invisible("e1")

    def test_list_petitions(self, rtiv):
        rtiv.submit_petition("e1", b"proof", "r1")
        rtiv.submit_petition("e2", b"proof", "r2")
        all_p = rtiv.list_petitions()
        assert len(all_p) == 2
        e1_p = rtiv.list_petitions(entity_id="e1")
        assert len(e1_p) == 1

    def test_cannot_approve_already_decided(self, rtiv):
        pid = rtiv.submit_petition("e1", b"proof", "reason")
        assert rtiv.approve(pid, decided_by="gov")
        # Second approve should fail (already approved)
        assert not rtiv.approve(pid, decided_by="gov")


# ── Elder Wisdom tests ─────────────────────────────────────────────────────────

class TestElderWisdom:
    @pytest.fixture
    def ew(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = os.path.join(tmpdir, "test.db")
            yield ElderWisdomProtocol(db_path=db)

    def test_meets_admission_criteria_high_tenure_high_acc(self):
        ok, _ = ElderWisdomProtocol.meets_admission_criteria(0.85, 400 * 24 * 3600)
        assert ok

    def test_meets_admission_criteria_low_tenure(self):
        ok, reason = ElderWisdomProtocol.meets_admission_criteria(0.85, 30 * 24 * 3600)
        assert not ok
        assert "tenure" in reason.lower()

    def test_meets_admission_criteria_low_accuracy(self):
        ok, reason = ElderWisdomProtocol.meets_admission_criteria(0.50, 400 * 24 * 3600)
        assert not ok
        assert "accuracy" in reason.lower()

    def test_admit_elder_succeeds_for_qualified(self, ew):
        ok, _ = ew.admit_elder("ann_001", 0.78, 400 * 24 * 3600)
        assert ok
        assert ew.is_elder("ann_001")

    def test_admit_elder_fails_for_unqualified(self, ew):
        ok, _ = ew.admit_elder("ann_002", 0.50, 30 * 24 * 3600)
        assert not ok
        assert not ew.is_elder("ann_002")

    def test_effective_stake_3x_for_elder(self, ew):
        ew.admit_elder("ann_001", 0.78, 400 * 24 * 3600, stake_weight=1.0)
        assert ew.effective_stake("ann_001") == 3.0

    def test_effective_stake_1x_for_non_elder(self, ew):
        assert ew.effective_stake("ann_999") == 1.0

    def test_list_elders(self, ew):
        ew.admit_elder("ann_001", 0.78, 400 * 24 * 3600)
        ew.admit_elder("ann_002", 0.85, 500 * 24 * 3600)
        elders = ew.list_elders()
        assert len(elders) == 2

    def test_cast_vote_requires_active_elder(self, ew):
        with pytest.raises(ValueError, match="not an active elder"):
            ew.cast_vote("cand_1", "nonexistent_elder", True)


# ── Love Protocol tests ────────────────────────────────────────────────────────

class TestLoveProtocol:
    def test_all_pillars_maxed_gives_F_1(self):
        result = LoveProtocol.compute(LoveInputs())
        assert result.F_love == 1.0
        assert not result.moat_collapse

    def test_one_pillar_zero_collapses_moat(self):
        for pillar in PILLARS:
            kwargs = {pillar: 0.0}
            inputs = LoveInputs(**kwargs)
            result = LoveProtocol.compute(inputs)
            assert result.F_love == 0.0
            assert result.moat_collapse
            assert result.weakest_pillar == pillar

    def test_F_is_min_of_pillars(self):
        inputs = LoveInputs(
            public_good_charter=0.9,
            indigenous_knowledge=0.7,
            right_to_invisibility=0.5,
            gratitude_protocol=0.8,
            elder_wisdom=0.6,
            unknown_unknown=0.4,
        )
        result = LoveProtocol.compute(inputs)
        assert result.F_love == 0.4
        assert result.weakest_pillar == "unknown_unknown"

    def test_scores_clamped_to_0_1(self):
        inputs = LoveInputs(public_good_charter=2.0, indigenous_knowledge=-0.5)
        result = LoveProtocol.compute(inputs)
        assert result.pillar_scores["public_good_charter"] == 1.0
        assert result.pillar_scores["indigenous_knowledge"] == 0.0

    def test_integrate_with_moat_when_no_collapse(self):
        result = LoveProtocol.integrate_with_moat(
            moat_without_F=0.75,
            love_inputs=LoveInputs(),
        )
        assert result["M_moat"] == 0.75
        assert not result["moat_collapse"]

    def test_integrate_with_moat_when_collapse(self):
        result = LoveProtocol.integrate_with_moat(
            moat_without_F=0.99,
            love_inputs=LoveInputs(public_good_charter=0.0),
        )
        assert result["M_moat"] == 0.0
        assert result["moat_collapse"]

    def test_six_pillars_defined(self):
        assert len(PILLARS) == 6
        assert "public_good_charter" in PILLARS
        assert "indigenous_knowledge" in PILLARS
        assert "right_to_invisibility" in PILLARS
        assert "gratitude_protocol" in PILLARS
        assert "elder_wisdom" in PILLARS
        assert "unknown_unknown" in PILLARS
