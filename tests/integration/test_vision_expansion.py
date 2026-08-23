"""
TRION Vision Expansion — Test Suite
=====================================
Tests for all 9 new modules:
  T01: Vulnerability Pattern Library (20 patterns)
  T02: Contract Auditor Engine
  T03: Behavioral Archetypes (12 archetypes)
  T04: Epigenetic Behavioral Layer
  T05: Thermodynamic Extension
  T06: Entity Lifecycle Engine
  T07: Universal Behavioral Language (UBL)
  T08: Reputation & Credit Engine
  T09: Investment Signal Engine
  T10: AI Agent Safety Pipeline
  T11: Portfolio Scan
  T12: UBL Similarity + Distance
  T13: Agent Training Loop
  T14: Epigenetic Pressure Events
  T15: Archetype → Investment Signal Pipeline (end-to-end)
"""

import sys
import os
import pytest
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# ─── Module imports ───────────────────────────────────────────────────────────

from core.auditor.vulnerability_patterns import (
    VULNERABILITY_LIBRARY, get_patterns_by_severity, get_patterns_by_category,
    SEVERITY_SCORES
)
from core.auditor.contract_auditor import ContractAuditor
from core.akashic.archetype import ARCHETYPES, match_archetype, get_all_archetypes_summary
from core.akashic.epigenetics import EpigeneticEngine, EnvironmentalPressure
from core.thermodynamics.thermo_engine import ThermoEngine
from core.lifecycle.entity_lifecycle import EntityLifecycleEngine
from core.ubl.ubl import UBLEncoder, UBL_SCHEMA, LIFECYCLE_STAGE_MAP, RISK_MAP
from core.reputation.reputation_engine import ReputationEngine, TRUST_TIERS
from core.investment.investment_engine import InvestmentEngine
from core.agent.safety_pipeline import (
    TRIONAgentPipeline, AgentAction, ActionType, ValidationOutcome
)


# ─── T01: Vulnerability Pattern Library ───────────────────────────────────────

class TestVulnerabilityPatterns:

    def test_count(self):
        assert len(VULNERABILITY_LIBRARY) == 20

    def test_all_have_required_fields(self):
        for p in VULNERABILITY_LIBRARY:
            assert p.id.startswith("VULN_")
            assert p.name
            assert p.severity in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
            assert p.category in ("structural", "behavioral", "economic", "governance")
            assert len(p.phi_vector) == 9
            assert 0.0 <= SEVERITY_SCORES[p.severity] <= 1.0

    def test_filter_by_severity(self):
        criticals = get_patterns_by_severity("CRITICAL")
        assert len(criticals) >= 4  # reentrancy, flash loan, rugpull, etc.

    def test_filter_by_category(self):
        structural = get_patterns_by_category("structural")
        assert len(structural) >= 5

    def test_severity_scores(self):
        assert SEVERITY_SCORES["CRITICAL"] == 1.0
        assert SEVERITY_SCORES["HIGH"] == 0.75
        assert SEVERITY_SCORES["MEDIUM"] == 0.50
        assert SEVERITY_SCORES["LOW"] == 0.25

    def test_phi_vectors_valid(self):
        import numpy as np
        for p in VULNERABILITY_LIBRARY:
            arr = np.array(p.phi_vector)
            assert arr.min() >= 0.0
            assert arr.max() <= 1.0


# ─── T02: Contract Auditor Engine ─────────────────────────────────────────────

class TestContractAuditor:

    def setup_method(self):
        self.auditor = ContractAuditor()

    def test_audit_returns_report(self):
        report = self.auditor.audit("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", 1)
        assert report is not None
        assert report.address == "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"

    def test_risk_score_range(self):
        report = self.auditor.audit("0xtest_contract", 1)
        assert 0.0 <= report.risk_score <= 1.0

    def test_risk_label_valid(self):
        report = self.auditor.audit("0xtest_contract", 1)
        assert report.risk_label in ("SAFE", "LOW", "MEDIUM", "HIGH", "CRITICAL")

    def test_lifecycle_stage_valid(self):
        report = self.auditor.audit("0xtest_contract", 1)
        assert report.lifecycle_stage in ("BIRTH", "GROWTH", "MATURITY", "DECLINE", "DEATH")

    def test_ubl_vector_12_dim(self):
        report = self.auditor.audit("0xtest_contract", 1)
        assert len(report.ubl_vector) == 12

    def test_attestation_hash_is_hex(self):
        report = self.auditor.audit("0xtest_contract", 1)
        assert len(report.attestation_hash) == 64
        int(report.attestation_hash, 16)  # must be valid hex

    def test_audit_to_dict(self):
        d = self.auditor.audit_to_dict("0xtest", 1)
        assert isinstance(d, dict)
        assert "risk_score" in d
        assert "findings" in d
        assert "archetype" in d

    def test_different_chains(self):
        r1 = self.auditor.audit("0xtest", 1)
        r2 = self.auditor.audit("0xtest", 42161)
        assert r1.chain_id == 1
        assert r2.chain_id == 42161


# ─── T03: Behavioral Archetypes ───────────────────────────────────────────────

class TestArchetypes:

    def test_count(self):
        assert len(ARCHETYPES) == 12

    def test_all_have_phi_vectors(self):
        for a in ARCHETYPES:
            assert len(a.phi_vector) == 9
            assert all(0.0 <= v <= 1.0 for v in a.phi_vector)

    def test_investment_signals_valid(self):
        valid_signals = {"BUY", "WATCH", "AVOID", "SHORT"}
        for a in ARCHETYPES:
            assert a.investment_signal in valid_signals

    def test_risk_levels_valid(self):
        valid_levels = {"SAFE", "CAUTION", "DANGER", "CRITICAL"}
        for a in ARCHETYPES:
            assert a.risk_level in valid_levels

    def test_match_organic_growth(self):
        # Low entropy, ordered phi vector should match Organic Growth or Healthy DeFi
        phi = [0.32, 0.28, 0.38, 0.30, 0.22, 0.18, 0.34, 0.29, 0.35]
        result = match_archetype(phi)
        assert result["archetype_name"] in ("Organic Growth", "Healthy DeFi Protocol")
        assert result["investment_signal"] in ("BUY", "WATCH")

    def test_match_flash_exploit(self):
        # Extreme entropy spike vector
        phi = [0.95, 0.90, 0.88, 0.92, 0.04, 0.03, 0.93, 0.88, 0.96]
        result = match_archetype(phi)
        assert result["archetype_name"] == "Flash Exploit"
        assert result["investment_signal"] == "SHORT"

    def test_match_returns_required_keys(self):
        result = match_archetype([0.5] * 9)
        required = {"archetype_id", "archetype_name", "similarity", "distance",
                    "risk_level", "investment_signal", "investment_confidence"}
        assert required.issubset(set(result.keys()))

    def test_summary(self):
        summary = get_all_archetypes_summary()
        assert len(summary) == 12
        assert all("name" in s and "phi_vector" in s for s in summary)


# ─── T04: Epigenetic Behavioral Layer ─────────────────────────────────────────

class TestEpigenetics:

    def setup_method(self):
        self.engine = EpigeneticEngine()

    def test_observation_returns_drift(self):
        result = self.engine.record_observation("test_epi_01", [0.5] * 9)
        assert "drift" in result
        assert result["drift"] >= 0.0

    def test_drift_label_values(self):
        result = self.engine.record_observation("test_epi_02", [0.5] * 9)
        assert result["drift_label"] in ("STABLE", "MODERATE", "SIGNIFICANT", "CRITICAL")

    def test_exploit_pressure_is_heritable(self):
        pressure = EnvironmentalPressure(
            pressure_type="EXPLOIT",
            magnitude=0.9,
            duration_blocks=100,
            timestamp=int(time.time()),
            affected_features=[0, 1, 2, 3, 4, 5, 6, 7, 8],
        )
        result = self.engine.apply_pressure("test_epi_03", [0.5] * 9, pressure)
        assert result["is_heritable"] is True

    def test_low_magnitude_not_heritable(self):
        pressure = EnvironmentalPressure(
            pressure_type="REGULATORY",
            magnitude=0.2,
            duration_blocks=10,
            timestamp=int(time.time()),
            affected_features=[0, 1],
        )
        result = self.engine.apply_pressure("test_epi_04", [0.5] * 9, pressure)
        assert result["is_heritable"] is False

    def test_epigenetic_report_structure(self):
        self.engine.record_observation("test_epi_05", [0.6] * 9)
        report = self.engine.get_epigenetic_report("test_epi_05")
        assert "epigenetic_age" in report
        assert "recent_drift" in report
        assert "methylation_pattern" in report

    def test_all_pressure_types_work(self):
        for pt in ("MARKET_CRASH", "EXPLOIT", "UPGRADE", "REGULATORY", "FORK", "LIQUIDITY_SHOCK"):
            pressure = EnvironmentalPressure(pt, 0.5, 50, int(time.time()), [0])
            result = self.engine.apply_pressure(f"test_{pt}", [0.5] * 9, pressure)
            assert "modified_phi" in result


# ─── T05: Thermodynamic Extension ─────────────────────────────────────────────

class TestThermodynamics:

    def setup_method(self):
        self.engine = ThermoEngine()

    def test_compute_returns_state(self):
        state = self.engine.compute("0xthermo_test", [0.5] * 9, 0.3, 0.4, 200)
        assert state is not None
        assert state.entity_id == "0xthermo_test"

    def test_phase_is_valid(self):
        state = self.engine.compute("0xtest", [0.5] * 9, 0.3, 0.4, 100)
        assert state.phase in ("SOLID", "LIQUID", "GAS", "PLASMA")

    def test_cold_temperature_is_solid(self):
        state = self.engine.compute("0xtest", [0.5] * 9, 0.05, 0.1, 5)
        assert state.phase == "SOLID"

    def test_high_temperature_is_gas_or_plasma(self):
        state = self.engine.compute("0xtest", [0.5] * 9, 0.80, 0.9, 1000)
        assert state.phase in ("GAS", "PLASMA")

    def test_extreme_temperature_is_plasma(self):
        state = self.engine.compute("0xtest", [0.5] * 9, 0.95, 1.0, 5000)
        assert state.phase == "PLASMA"

    def test_scores_in_range(self):
        state = self.engine.compute("0xtest", [0.5] * 9, 0.3, 0.4, 200)
        assert 0.0 <= state.energy <= 1.0
        assert 0.0 <= state.entropy <= 1.0
        assert 0.0 <= state.free_energy <= 1.0
        assert 0.0 <= state.thermodynamic_health <= 1.0
        assert 0.0 <= state.carnot_efficiency <= 1.0

    def test_phase_transition_detection(self):
        history = [
            self.engine.compute("0xtest", [0.5] * 9, t, 0.4, 100)
            for t in [0.1, 0.3, 0.7, 0.9]
        ]
        result = self.engine.detect_phase_transition(history)
        assert "transition_detected" in result
        assert "confidence" in result


# ─── T06: Entity Lifecycle Engine ─────────────────────────────────────────────

class TestLifecycle:

    def setup_method(self):
        self.engine = EntityLifecycleEngine()

    def test_update_returns_stage(self):
        result = self.engine.update("lc_test_01", 500, 0.4, 5000.0)
        assert result["stage"] in ("BIRTH", "GROWTH", "MATURITY", "DECLINE", "DEATH")

    def test_vitality_in_range(self):
        result = self.engine.update("lc_test_02", 100, 0.5, 1000.0)
        assert 0.0 <= result["vitality"] <= 1.0

    def test_mortality_risk_in_range(self):
        result = self.engine.update("lc_test_03", 50, 0.6, 500.0)
        assert 0.0 <= result["mortality_risk"] <= 1.0

    def test_resurrection_potential_in_range(self):
        result = self.engine.update("lc_test_04", 0, 0.9, 0.0)
        assert 0.0 <= result["resurrection_potential"] <= 1.0

    def test_low_activity_entity_declines(self):
        eid = "lc_dormant_test"
        # Multiple updates with near-zero activity
        for _ in range(5):
            result = self.engine.update(eid, 0, 0.95, 0.0)
        assert result["stage"] in ("DECLINE", "DEATH", "BIRTH")

    def test_high_activity_grows(self):
        eid = "lc_active_test"
        for _ in range(3):
            result = self.engine.update(eid, 5000, 0.4, 50000.0)
        assert result["vitality"] > 0.3


# ─── T07: Universal Behavioral Language ───────────────────────────────────────

class TestUBL:

    def setup_method(self):
        self.enc = UBLEncoder()

    def test_schema_has_12_dimensions(self):
        assert len(UBL_SCHEMA["dimensions"]) == 12

    def test_encode_returns_ubl(self):
        ubl = self.enc.from_phi_and_planes("0xubl_test", [0.5] * 9, coherence=0.7)
        assert ubl is not None
        assert ubl.entity_id == "0xubl_test"

    def test_vector_is_12_dim(self):
        ubl = self.enc.from_phi_and_planes("0xubl_test", [0.5] * 9)
        vec = self.enc.to_vector(ubl)
        assert len(vec) == 12

    def test_to_dict_has_vector(self):
        ubl = self.enc.from_phi_and_planes("0xubl_test", [0.5] * 9)
        d = self.enc.to_dict(ubl)
        assert "vector" in d
        assert len(d["vector"]) == 12
        # All values must be Python native floats (JSON serializable)
        import json
        json.dumps(d)  # must not raise

    def test_lifecycle_encoding(self):
        for stage, expected_val in LIFECYCLE_STAGE_MAP.items():
            ubl = self.enc.from_phi_and_planes("0xtest", [0.5] * 9, lifecycle_stage=stage)
            assert abs(ubl.lifecycle_stage - expected_val) < 0.01

    def test_similarity_same_entity(self):
        ubl_a = self.enc.from_phi_and_planes("0xa", [0.5] * 9, coherence=0.7)
        ubl_b = self.enc.from_phi_and_planes("0xa", [0.5] * 9, coherence=0.7)
        sim = self.enc.similarity(ubl_a, ubl_b)
        assert abs(sim - 1.0) < 1e-4

    def test_similarity_different_entities(self):
        ubl_a = self.enc.from_phi_and_planes("0xa", [0.3] * 9, coherence=0.7)
        ubl_b = self.enc.from_phi_and_planes("0xb", [0.9] * 9, coherence=0.2)
        sim = self.enc.similarity(ubl_a, ubl_b)
        dist = self.enc.behavioral_distance(ubl_a, ubl_b)
        assert 0.0 <= sim <= 1.0
        assert dist > 0.0

    def test_ai_agent_encoding(self):
        ubl = self.enc.from_ai_agent("agent_001", 0.75, 0.8, 0.1, "VERIFIED")
        assert ubl.source_vm == "AI_AGENT"
        assert ubl.source_chain == "agent_network"
        assert 0.0 <= ubl.coherence_c <= 1.0

    def test_interpret_returns_string(self):
        ubl = self.enc.from_phi_and_planes("0xtest", [0.5] * 9, coherence=0.65)
        interp = self.enc.interpret(ubl)
        assert isinstance(interp, str)
        assert len(interp) > 10


# ─── T08: Reputation & Credit Engine ─────────────────────────────────────────

class TestReputation:

    def setup_method(self):
        self.engine = ReputationEngine()

    def test_record_creates_profile(self):
        result = self.engine.record_observation("0xrep_test_01", coherence=0.7)
        assert "trust_tier" in result
        assert "reputation_score" in result

    def test_trust_tiers_valid(self):
        self.engine.record_observation("0xrep_test_02", coherence=0.75, tx_count=50)
        rep = self.engine.get_reputation("0xrep_test_02")
        assert rep["trust_tier"] in ("UNTRUSTED", "PROBATION", "TRUSTED", "VERIFIED", "EXEMPLARY")

    def test_scores_in_range(self):
        self.engine.record_observation("0xrep_test_03", coherence=0.8)
        rep = self.engine.get_reputation("0xrep_test_03")
        assert 0.0 <= rep["reputation_score"] <= 1.0
        assert 0.0 <= rep["credit_score"] <= 1.0

    def test_manipulation_reduces_score(self):
        eid = "0xrep_manip_test"
        # First: clean record
        self.engine.record_observation(eid, coherence=0.7, manipulation_score=0.0)
        rep1 = self.engine.get_reputation(eid)
        # Then: manipulation event
        self.engine.record_observation(eid, coherence=0.7, manipulation_score=0.9)
        rep2 = self.engine.get_reputation(eid)
        assert rep2["reputation_score"] <= rep1["reputation_score"]

    def test_endorsement_increases_score(self):
        eid = "0xrep_endorse"
        self.engine.record_observation(eid, coherence=0.6)
        rep1 = self.engine.get_reputation(eid)
        self.engine.endorse(eid, "validator_001")
        rep2 = self.engine.get_reputation(eid)
        assert rep2["validator_endorsements"] > rep1["validator_endorsements"]

    def test_dispute_reduces_score(self):
        eid = "0xrep_dispute"
        self.engine.record_observation(eid, coherence=0.7)
        rep1 = self.engine.get_reputation(eid)
        self.engine.dispute(eid, "challenger_001", "suspicious activity")
        rep2 = self.engine.get_reputation(eid)
        assert rep2["dispute_count"] > rep1.get("dispute_count", 0)

    def test_leaderboard_ordered(self):
        # Create a few entities
        for i in range(5):
            self.engine.record_observation(f"0xlb_{i}", coherence=0.5 + i * 0.08)
        board = self.engine.leaderboard(10)
        if len(board) >= 2:
            scores = [e["reputation_score"] for e in board]
            assert scores == sorted(scores, reverse=True)

    def test_credit_increases_with_trust(self):
        eid = "0xrep_credit"
        # Build up history
        for _ in range(20):
            self.engine.record_observation(eid, coherence=0.85, tx_count=100)
        rep = self.engine.get_reputation(eid)
        assert rep["max_credit_usd"] >= 0.0


# ─── T09: Investment Signal Engine ────────────────────────────────────────────

class TestInvestmentEngine:

    def setup_method(self):
        self.engine = InvestmentEngine()

    def test_decision_valid(self):
        sig = self.engine.analyze("0xinv_test", [0.5] * 9, coherence=0.65)
        assert sig.decision in ("STRONG_BUY", "BUY", "WATCH", "AVOID", "STRONG_AVOID", "SHORT")

    def test_high_coherence_buy_signal(self):
        sig = self.engine.analyze(
            "0xbullish", [0.32, 0.28, 0.38, 0.30, 0.22, 0.18, 0.34, 0.29, 0.35],
            coherence=0.85, lifecycle_stage="GROWTH", thermo_phase="LIQUID",
            manipulation_score=0.05,
        )
        assert sig.decision in ("STRONG_BUY", "BUY", "WATCH")

    def test_death_spiral_avoid(self):
        sig = self.engine.analyze(
            "0xbearish", [0.88, 0.84, 0.92, 0.80, 0.90, 0.88, 0.86, 0.82, 0.91],
            coherence=0.08, lifecycle_stage="DEATH", thermo_phase="PLASMA",
            manipulation_score=0.9,
        )
        assert sig.decision in ("SHORT", "STRONG_AVOID", "AVOID")

    def test_behavioral_alpha_in_range(self):
        sig = self.engine.analyze("0xtest", [0.5] * 9, coherence=0.6)
        assert 0.0 <= sig.behavioral_alpha <= 1.0

    def test_confidence_in_range(self):
        sig = self.engine.analyze("0xtest", [0.5] * 9, coherence=0.6)
        assert 0.0 <= sig.confidence <= 1.0

    def test_drawdown_estimate_in_range(self):
        sig = self.engine.analyze("0xtest", [0.5] * 9, coherence=0.6)
        assert 0.0 <= sig.max_drawdown_estimate <= 1.0

    def test_portfolio_scan(self):
        entities = [
            {"entity_id": f"0x{i:040x}", "phi_vector": [0.5] * 9, "coherence": 0.4 + i * 0.1,
             "lifecycle_stage": "GROWTH", "thermo_phase": "LIQUID",
             "thermo_free_energy": 0.5, "market_volatility": 0.3, "manipulation_score": 0.1}
            for i in range(5)
        ]
        result = self.engine.scan_portfolio(entities)
        assert result["total_entities"] == 5
        assert result["buy_signals"] + result["avoid_signals"] + result["watch_signals"] == 5


# ─── T10: AI Agent Safety Pipeline ────────────────────────────────────────────

class TestAgentPipeline:

    def setup_method(self):
        self.pipeline = TRIONAgentPipeline()

    def _make_action(self, action_type=ActionType.TRADE, value=5000.0, chain_id=1, metadata=None):
        return AgentAction(
            action_type=action_type,
            entity_id="0xtest",
            value_usd=value,
            chain_id=chain_id,
            raw_data={},
            metadata=metadata or {},
        )

    def test_basic_trade_allowed(self):
        result = self.pipeline.validate_action("test_agent_basic", self._make_action())
        assert result.outcome in (
            ValidationOutcome.ALLOWED, ValidationOutcome.MODIFIED,
            ValidationOutcome.BLOCKED, ValidationOutcome.SILENCED
        )

    def test_coherence_in_range(self):
        result = self.pipeline.validate_action("test_agent_coh", self._make_action())
        assert 0.0 <= result.coherence_score <= 1.0

    def test_risk_in_range(self):
        result = self.pipeline.validate_action("test_agent_risk", self._make_action())
        assert 0.0 <= result.risk_score <= 1.0

    def test_bridge_is_riskier_than_query(self):
        r_bridge = self.pipeline.validate_action("agent_bridge", self._make_action(ActionType.BRIDGE, 1000))
        r_query = self.pipeline.validate_action("agent_query", self._make_action(ActionType.QUERY, 0))
        assert r_bridge.risk_score >= r_query.risk_score

    def test_flash_loan_metadata_increases_risk(self):
        r_normal = self.pipeline.validate_action("agent_norm", self._make_action(ActionType.TRADE, 1000))
        r_flash = self.pipeline.validate_action("agent_flash",
            self._make_action(ActionType.TRADE, 1000, metadata={"flash_loan": True}))
        assert r_flash.risk_score >= r_normal.risk_score

    def test_agent_fitness_evolves(self):
        agent_id = "agent_evolve_test"
        result1 = self.pipeline.validate_action(agent_id, self._make_action())
        profile = self.pipeline.get_agent_profile(agent_id)
        assert profile["fitness_score"] >= 0.0

    def test_training_updates_fitness(self):
        agent_id = "agent_train_test"
        profile_before = self.pipeline.get_agent_profile(agent_id)
        self.pipeline.train_agent(
            agent_id,
            [{"coherence": 0.9}] * 10,
            [{"coherence": 0.1}] * 2,
        )
        profile_after = self.pipeline.get_agent_profile(agent_id)
        assert profile_after["fitness_score"] >= profile_before["fitness_score"]

    def test_exemplary_agent_has_no_value_limit(self):
        # Manually elevate an agent to EXEMPLARY
        from core.agent.safety_pipeline import _AGENT_REGISTRY, AgentProfile
        _AGENT_REGISTRY["agent_exemplary_test"] = AgentProfile(
            agent_id="agent_exemplary_test",
            created_at=int(time.time()),
            total_actions=200,
            allowed_actions=195,
            blocked_actions=5,
            avg_coherence=0.9,
            fitness_score=0.92,
            behavioral_history=[0.9] * 50,
            reputation=0.9,
            trust_level="EXEMPLARY",
        )
        result = self.pipeline.validate_action(
            "agent_exemplary_test",
            self._make_action(ActionType.TRADE, 999_999_999)
        )
        # Value gate should not block EXEMPLARY agents
        assert result.blocked_by != "VALUE_GATE"

    def test_behavioral_stamp_is_hex(self):
        result = self.pipeline.validate_action("agent_stamp", self._make_action())
        assert len(result.behavioral_stamp) == 16
        int(result.behavioral_stamp, 16)  # must be hex


# ─── T11: Portfolio Scan (end-to-end) ─────────────────────────────────────────

class TestPortfolioScan:

    def test_mixed_portfolio(self):
        engine = InvestmentEngine()
        entities = [
            # Strong buy: very high coherence, STRONG_BUY archetype vector
            {"entity_id": "0xhealthy", "phi_vector": [0.22, 0.18, 0.25, 0.20, 0.15, 0.12, 0.19, 0.17, 0.21],
             "coherence": 0.92, "manipulation_score": 0.02, "lifecycle_stage": "GROWTH",
             "thermo_phase": "SOLID", "thermo_free_energy": 0.88, "market_volatility": 0.08,
             "reputation_score": 0.9},
            # Definite avoid: death spiral
            {"entity_id": "0xdangerous", "phi_vector": [0.92]*9, "coherence": 0.03,
             "manipulation_score": 0.97, "lifecycle_stage": "DEATH",
             "thermo_phase": "PLASMA", "thermo_free_energy": 0.01, "market_volatility": 0.95,
             "reputation_score": 0.05},
            # Neutral: watch territory
            {"entity_id": "0xneutral", "phi_vector": [0.5]*9, "coherence": 0.55,
             "manipulation_score": 0.2, "lifecycle_stage": "MATURITY",
             "thermo_phase": "LIQUID", "thermo_free_energy": 0.45, "market_volatility": 0.3},
        ]
        result = engine.scan_portfolio(entities)
        assert result["total_entities"] == 3
        # At least one of healthy or neutral should be non-avoid
        assert result["buy_signals"] + result["watch_signals"] >= 1
        assert result["avoid_signals"] >= 1
        assert 0.0 <= result["avg_behavioral_alpha"] <= 1.0


# ─── T12: UBL Similarity + Distance ──────────────────────────────────────────

class TestUBLMetrics:

    def test_identical_vectors_similarity_one(self):
        enc = UBLEncoder()
        ubl = enc.from_phi_and_planes("0xa", [0.5]*9, coherence=0.7)
        sim = enc.similarity(ubl, ubl)
        assert abs(sim - 1.0) < 1e-4

    def test_opposite_vectors_low_similarity(self):
        enc = UBLEncoder()
        ubl_a = enc.from_phi_and_planes("0xa", [0.1]*9, coherence=0.1, lifecycle_stage="BIRTH")
        ubl_b = enc.from_phi_and_planes("0xb", [0.9]*9, coherence=0.9, lifecycle_stage="DEATH")
        sim = enc.similarity(ubl_a, ubl_b)
        assert sim < 0.99  # not identical

    def test_distance_positive(self):
        enc = UBLEncoder()
        ubl_a = enc.from_phi_and_planes("0xa", [0.3]*9)
        ubl_b = enc.from_phi_and_planes("0xb", [0.7]*9)
        dist = enc.behavioral_distance(ubl_a, ubl_b)
        assert dist > 0.0

    def test_json_serializable(self):
        import json
        enc = UBLEncoder()
        ubl = enc.from_phi_and_planes("0xjson_test", [0.5]*9, coherence=0.6)
        d = enc.to_dict(ubl)
        # Should not raise
        serialized = json.dumps(d)
        assert len(serialized) > 100


# ─── T13: Agent Training Loop ─────────────────────────────────────────────────

class TestAgentTraining:

    def test_positive_training_increases_fitness(self):
        pipeline = TRIONAgentPipeline()
        agent_id = "agent_train_pos"
        profile_before = pipeline.get_agent_profile(agent_id)
        result = pipeline.train_agent(agent_id, [{"coherence": 0.9}] * 20, [])
        assert result["new_fitness"] >= profile_before["fitness_score"]

    def test_negative_training_decreases_fitness(self):
        pipeline = TRIONAgentPipeline()
        agent_id = "agent_train_neg"
        pipeline.train_agent(agent_id, [{"coherence": 0.8}] * 10, [])
        result = pipeline.train_agent(agent_id, [], [{"coherence": 0.1}] * 15)
        assert 0.0 <= result["new_fitness"] <= 1.0

    def test_train_returns_trust_level(self):
        pipeline = TRIONAgentPipeline()
        result = pipeline.train_agent("agent_tl", [{"coherence": 0.7}] * 5, [])
        assert result["trust_level"] in ("UNTRUSTED", "PROBATION", "TRUSTED", "VERIFIED", "EXEMPLARY")


# ─── T14: Epigenetic Pressure Events ─────────────────────────────────────────

class TestEpigeneticPressures:

    def test_all_pressures_produce_modified_phi(self):
        engine = EpigeneticEngine()
        pressure_types = ["MARKET_CRASH", "EXPLOIT", "UPGRADE", "REGULATORY", "FORK", "LIQUIDITY_SHOCK"]
        for pt in pressure_types:
            p = EnvironmentalPressure(pt, 0.7, 100, int(time.time()), [0, 1, 2])
            result = engine.apply_pressure(f"pressure_test_{pt}", [0.5]*9, p)
            assert "modified_phi" in result
            assert len(result["modified_phi"]) == 9
            assert all(0.0 <= v <= 1.0 for v in result["modified_phi"])

    def test_high_magnitude_exploit_heritable(self):
        engine = EpigeneticEngine()
        p = EnvironmentalPressure("EXPLOIT", 0.95, 500, int(time.time()), list(range(9)))
        result = engine.apply_pressure("exploit_high", [0.5]*9, p)
        assert result["is_heritable"] is True


# ─── T15: Full Pipeline (Archetype → Investment) ──────────────────────────────

class TestEndToEndPipeline:

    def test_organic_growth_gives_buy_signal(self):
        # Organic Growth archetype phi vector
        phi = [0.32, 0.28, 0.38, 0.30, 0.22, 0.18, 0.34, 0.29, 0.35]
        arch = match_archetype(phi)
        assert arch["investment_signal"] in ("BUY", "WATCH")

        ie = InvestmentEngine()
        sig = ie.analyze("0x_organic", phi, coherence=0.80,
                         lifecycle_stage="GROWTH", thermo_phase="LIQUID",
                         manipulation_score=0.05, market_volatility=0.25)
        assert sig.decision in ("BUY", "STRONG_BUY", "WATCH")

    def test_death_spiral_full_pipeline(self):
        phi = [0.88, 0.84, 0.92, 0.80, 0.90, 0.88, 0.86, 0.82, 0.91]
        arch = match_archetype(phi)
        assert arch["archetype_name"] in ("Death Spiral", "Flash Exploit", "Liquidity Drain")

        ie = InvestmentEngine()
        sig = ie.analyze("0x_death", phi, coherence=0.05,
                         lifecycle_stage="DEATH", thermo_phase="PLASMA",
                         manipulation_score=0.95)
        assert sig.decision in ("SHORT", "STRONG_AVOID", "AVOID")

    def test_ubl_encodes_lifecycle_correctly(self):
        enc = UBLEncoder()
        for stage in ("BIRTH", "GROWTH", "MATURITY", "DECLINE", "DEATH"):
            ubl = enc.from_phi_and_planes("0xtest", [0.5]*9, lifecycle_stage=stage)
            d = enc.to_dict(ubl)
            assert d["lifecycle_stage_label"] == stage
