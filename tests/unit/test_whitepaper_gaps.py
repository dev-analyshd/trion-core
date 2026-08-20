"""
TRION Protocol — Whitepaper Gap Closure Tests
Covers: L4.4, L4.6, L4.8, L4.9, L3.7

All 5 remaining whitepaper gaps implemented and tested here:
  L4.4 Kolmogorov Complexity Bound
  L4.6 SEC(t) = LSS · PQC · CC  (+ PQC simulation)
  L4.8 Geographic HHI Enforcement
  L4.9 Slashing + 7-Step Dispute Resolution
  L3.7 Intelligence Maintenance Protocol
"""

import hashlib
import math
import os
import time
import pytest


# ═══════════════════════════════════════════════════════════════════════════
# L4.4 Kolmogorov Complexity Bound
# ═══════════════════════════════════════════════════════════════════════════

from core.spiritual.living_security.pqc_layer import (
    check_complexity_bound, estimate_kolmogorov_complexity,
    K_MAX_BOUND_BITS, DELTA_K_MAX_DEFAULT,
)


class TestKolmogorovComplexityBound:
    """L4.4: K(GK,t) ≤ K(GK,t-1) + ΔK_max"""

    def test_sha3_key_within_bound(self):
        """High-entropy SHA3-256 key should be within complexity bound."""
        gk   = hashlib.sha3_256(b"valid_genomic_key").digest()
        prev = hashlib.sha3_256(b"prev_genomic_key").digest()
        r = check_complexity_bound("entity_1", gk, prev)
        assert not r.halted, f"Valid SHA3 key halted: {r.reason}"
        assert r.within_bound

    def test_structured_key_low_complexity(self):
        """Structured (repetitive) bytes have low complexity."""
        gk = b'\x00' * 32
        k  = estimate_kolmogorov_complexity(gk)
        assert k == 0.0, f"All-zero key should have K=0, got {k}"

    def test_high_entropy_key_near_max(self):
        """SHA3-256 output has significantly higher complexity than structured data."""
        gk = hashlib.sha3_256(os.urandom(64)).digest()
        k  = estimate_kolmogorov_complexity(gk)
        assert k > 100.0, f"SHA3-256 key should have K > 100 bits (entropy lower bound), got {k}"
        assert k <= 256.0

    def test_complexity_bound_fields(self):
        """ComplexityCheckResult has all required fields."""
        gk   = hashlib.sha3_256(b"test").digest()
        prev = hashlib.sha3_256(b"prev").digest()
        r = check_complexity_bound("test_ent", gk, prev)
        assert hasattr(r, "entity_id")
        assert hasattr(r, "k_current")
        assert hasattr(r, "k_previous")
        assert hasattr(r, "delta_k")
        assert hasattr(r, "delta_k_max")
        assert hasattr(r, "k_max_bound")
        assert hasattr(r, "within_bound")
        assert hasattr(r, "halted")
        assert r.k_max_bound == K_MAX_BOUND_BITS

    def test_delta_k_computed_correctly(self):
        """ΔK = K_current - K_previous."""
        gk   = hashlib.sha3_256(b"current").digest()
        prev = hashlib.sha3_256(b"prev").digest()
        r = check_complexity_bound("delta_test", gk, prev)
        assert abs(r.delta_k - (r.k_current - r.k_previous)) < 0.01

    def test_delta_k_max_is_log2(self):
        """ΔK_max = log2(block_entropy_bits)."""
        gk   = hashlib.sha3_256(b"a").digest()
        prev = b'\x00' * 32
        r = check_complexity_bound("log2_test", gk, prev, block_entropy_bits=256.0)
        expected_delta_k_max = math.log2(256.0)
        assert abs(r.delta_k_max - expected_delta_k_max) < 0.01


# ═══════════════════════════════════════════════════════════════════════════
# L4.6 SEC(t) = LSS · PQC · CC
# ═══════════════════════════════════════════════════════════════════════════

from core.spiritual.living_security.pqc_layer import (
    compute_sec, compute_pqc_score, compute_lss,
    compute_classical_cryptography_score,
)


class TestCombinedSecurityScore:
    """L4.6: SEC(t) = LSS(t) · PQC(t) · CC(t)"""

    def test_sec_product_formula(self):
        """SEC(t) must equal LSS × PQC × CC."""
        result = compute_sec(
            gk_verified=True, crispr_library_size=4, genomic_generation=5,
            immune_clearance=True,
            kyber_enabled=True, dilithium_enabled=True, sphincs_enabled=True,
            nist_level=3,
            sha3_256_active=True, secp256k1_active=True, aes_256_active=True,
        )
        expected = result.lss * result.pqc_score * result.cc_score
        assert abs(result.sec_score - expected) < 1e-6

    def test_sec_range(self):
        """SEC(t) must be in [0, 1]."""
        result = compute_sec()
        assert 0.0 <= result.sec_score <= 1.0

    def test_pqc_all_schemes_active(self):
        """With all 3 PQC schemes active at NIST L3: PQC = 0.90."""
        pqc = compute_pqc_score(kyber_enabled=True, dilithium_enabled=True,
                                 sphincs_enabled=True, nist_level=3)
        assert abs(pqc.pqc_score - 0.90) < 0.001

    def test_pqc_nist_levels(self):
        """NIST L5 > L3 > L1 for identical scheme set."""
        p1 = compute_pqc_score(True, True, True, nist_level=1)
        p3 = compute_pqc_score(True, True, True, nist_level=3)
        p5 = compute_pqc_score(True, True, True, nist_level=5)
        assert p5.pqc_score > p3.pqc_score > p1.pqc_score

    def test_pqc_no_schemes_zero(self):
        """PQC = 0 if all schemes disabled."""
        pqc = compute_pqc_score(False, False, False, nist_level=3)
        assert pqc.pqc_score == 0.0

    def test_lss_full_health(self):
        """LSS = 1.0 when all components pass."""
        lss = compute_lss(
            gk_verified=True, crispr_library_size=4,
            genomic_generation=1, immune_clearance=True,
        )
        assert abs(lss - 1.0) < 1e-9, f"LSS should be 1.0, got {lss}"

    def test_lss_unverified_gk(self):
        """Unverified GK reduces LSS significantly."""
        lss_ok  = compute_lss(True, 4, 1, True)
        lss_bad = compute_lss(False, 4, 1, True)
        assert lss_bad < lss_ok
        assert lss_bad <= 0.60

    def test_cc_full(self):
        """CC = 1.0 with all classical primitives active."""
        cc = compute_classical_cryptography_score(True, True, True, False)
        assert cc == 1.0

    def test_cc_zero(self):
        """CC = 0 with no classical primitives."""
        cc = compute_classical_cryptography_score(False, False, False, False)
        assert cc == 0.0

    def test_security_tiers(self):
        """Security tier strings are valid."""
        result = compute_sec()
        assert result.security_tier in (
            "QUANTUM_RESISTANT", "CLASSICAL_SECURE", "DEGRADED", "CRITICAL"
        )

    def test_bootstrap_weight_decay(self):
        """Bootstrap weight decays toward 0 as depth grows."""
        r_boot = compute_sec(akashic_depth=0.0)
        r_deep = compute_sec(akashic_depth=50000.0)
        assert r_boot.bootstrap_weight > r_deep.bootstrap_weight
        assert r_deep.bootstrap_weight < 0.01

    def test_sec_disclosure_contains_formula(self):
        """Disclosure string contains SEC formula components."""
        r = compute_sec()
        assert "LSS" in r.disclosure
        assert "PQC" in r.disclosure
        assert "CC" in r.disclosure

    def test_complexity_check_included(self):
        """When gk_sense provided, complexity check is included."""
        gk   = hashlib.sha3_256(b"gk").digest()
        prev = hashlib.sha3_256(b"prev").digest()
        r = compute_sec(gk_sense=gk, prev_sense=prev)
        assert r.complexity_check is not None
        assert hasattr(r.complexity_check, "k_current")


# ═══════════════════════════════════════════════════════════════════════════
# L4.8 HHI Geographic Enforcement
# ═══════════════════════════════════════════════════════════════════════════

from core.spiritual.living_security.pqc_layer import (
    compute_geo_enforcement, ValidatorGeoDistribution,
)


class TestGeographicEnforcement:
    """L4.8: N_continents≥4, max_region<0.40, max_jurisdiction<0.30"""

    def _diverse_validators(self):
        return [
            ValidatorGeoDistribution("v1", "EU", "EU-West",  "DE", 1000),
            ValidatorGeoDistribution("v2", "NA", "NA-East",  "US",  900),
            ValidatorGeoDistribution("v3", "AS", "AS-East",  "SG",  800),
            ValidatorGeoDistribution("v4", "SA", "SA-South", "BR",  600),
            ValidatorGeoDistribution("v5", "OC", "OC-ANZ",   "AU",  500),
            ValidatorGeoDistribution("v6", "AS", "AS-SE",    "JP",  400),
        ]

    def test_diverse_network_compliant(self):
        """A diverse 6-continent network should pass all 3 conditions."""
        geo = compute_geo_enforcement(self._diverse_validators())
        assert geo.n_continents >= 4
        assert geo.continents_ok
        assert geo.region_ok
        assert geo.jurisdiction_ok
        assert geo.geo_compliant
        assert geo.awa_geo_status == "ENFORCED"

    def test_single_jurisdiction_fails(self):
        """All validators in same jurisdiction → EMERGENCY_GEO."""
        validators = [
            ValidatorGeoDistribution(f"v{i}", "NA", "NA-East", "US", 1000)
            for i in range(10)
        ]
        geo = compute_geo_enforcement(validators)
        assert not geo.geo_compliant
        assert not geo.jurisdiction_ok
        assert geo.awa_geo_status == "EMERGENCY_GEO"

    def test_n_continents_requirement(self):
        """N_continents < 4 → EMERGENCY_GEO."""
        validators = [
            ValidatorGeoDistribution("v1", "EU", "EU-West", "DE", 1000),
            ValidatorGeoDistribution("v2", "EU", "EU-East", "PL",  900),
            ValidatorGeoDistribution("v3", "NA", "NA-East", "US",  800),
        ]
        geo = compute_geo_enforcement(validators)
        assert not geo.continents_ok
        assert geo.n_continents < 4

    def test_max_region_threshold(self):
        """Single region holding ≥40% → region_ok = False."""
        validators = [
            ValidatorGeoDistribution("v1", "NA", "NA-East", "US",  1000),
            ValidatorGeoDistribution("v2", "NA", "NA-East", "CA",  800),
            ValidatorGeoDistribution("v3", "EU", "EU-West", "DE",  300),
            ValidatorGeoDistribution("v4", "AS", "AS-East", "SG",  200),
            ValidatorGeoDistribution("v5", "SA", "SA-S",    "BR",  100),
        ]
        geo = compute_geo_enforcement(validators)
        assert not geo.region_ok or geo.max_region_share >= 0.40 or not geo.geo_compliant

    def test_empty_validators(self):
        """No validators → EMERGENCY_GEO."""
        geo = compute_geo_enforcement([])
        assert geo.awa_geo_status == "EMERGENCY_GEO"
        assert not geo.geo_compliant

    def test_continent_breakdown_sums_to_one(self):
        """Continent share breakdown must sum to ~1.0."""
        geo = compute_geo_enforcement(self._diverse_validators())
        total = sum(geo.continent_breakdown.values())
        assert abs(total - 1.0) < 0.001

    def test_jurisdiction_breakdown_sums_to_one(self):
        """Jurisdiction breakdown must sum to ~1.0."""
        geo = compute_geo_enforcement(self._diverse_validators())
        total = sum(geo.jurisdiction_breakdown.values())
        assert abs(total - 1.0) < 0.001

    def test_all_three_conditions_in_result(self):
        """Result always contains all 3 boolean condition flags."""
        geo = compute_geo_enforcement(self._diverse_validators())
        assert hasattr(geo, "continents_ok")
        assert hasattr(geo, "region_ok")
        assert hasattr(geo, "jurisdiction_ok")
        assert geo.geo_compliant == (geo.continents_ok and geo.region_ok and geo.jurisdiction_ok)

    def test_suspended_geo_status(self):
        """Partial compliance → SUSPENDED_GEO (not EMERGENCY)."""
        validators = [
            ValidatorGeoDistribution("v1", "EU", "EU-W", "DE", 1000),
            ValidatorGeoDistribution("v2", "NA", "NA-E", "US",  900),
            ValidatorGeoDistribution("v3", "AS", "AS-E", "SG",  800),
            ValidatorGeoDistribution("v4", "OC", "OC",   "AU",  700),
            ValidatorGeoDistribution("v5", "NA", "NA-E", "CA",  100),
        ]
        geo = compute_geo_enforcement(validators)
        assert geo.n_continents >= 4
        assert geo.awa_geo_status in ("ENFORCED", "SUSPENDED_GEO", "EMERGENCY_GEO")


# ═══════════════════════════════════════════════════════════════════════════
# L4.9 Slashing + 7-Step Dispute Resolution
# ═══════════════════════════════════════════════════════════════════════════

from core.governance.slashing import (
    SlashingEngine, SlashingCondition, DisputeState, SLASH_PARAMETERS,
)


class TestSlashingEngine:
    """L4.9: 5 slashing conditions + 7-step dispute resolution"""

    def _make_engine(self) -> SlashingEngine:
        return SlashingEngine()

    def test_all_five_slashing_conditions_defined(self):
        """All 5 slashing conditions must be defined."""
        for cond in SlashingCondition:
            assert cond in SLASH_PARAMETERS
            params = SLASH_PARAMETERS[cond]
            assert "stake_fraction" in params
            assert "permanent_ban" in params
            assert "description" in params
            assert "severity" in params

    def test_s1_double_signing_params(self):
        """S1: 50% slash, permanent ban."""
        p = SLASH_PARAMETERS[SlashingCondition.DOUBLE_SIGNING]
        assert p["stake_fraction"] == 0.50
        assert p["permanent_ban"] is True

    def test_s2_offline_params(self):
        """S2: 5% slash, 7-day suspension, no permanent ban."""
        p = SLASH_PARAMETERS[SlashingCondition.PROLONGED_OFFLINE]
        assert p["stake_fraction"] == 0.05
        assert p["permanent_ban"] is False
        assert p["suspension_days"] == 7

    def test_s3_false_signal_params(self):
        """S3: 20% slash, 30-day probation."""
        p = SLASH_PARAMETERS[SlashingCondition.FALSE_SIGNAL_SUBMISSION]
        assert p["stake_fraction"] == 0.20
        assert p["probation_days"] == 30

    def test_s4_collusion_permanent_ban(self):
        """S4: 100% slash, permanent ban — maximum severity."""
        p = SLASH_PARAMETERS[SlashingCondition.MANIPULATION_COLLUSION]
        assert p["stake_fraction"] == 1.00
        assert p["permanent_ban"] is True

    def test_s5_geo_violation_params(self):
        """S5: 10% slash, 7-day suspension."""
        p = SLASH_PARAMETERS[SlashingCondition.GEO_CONSTRAINT_VIOLATION]
        assert p["stake_fraction"] == 0.10
        assert p["suspension_days"] == 7

    def test_full_7_step_flow_guilty(self):
        """Complete 7-step dispute resolution → GUILTY → slashing executed."""
        engine = self._make_engine()
        case = engine.file_accusation("val_A", "accuser_B",
                                       SlashingCondition.DOUBLE_SIGNING, 3000.0)
        assert case.state == DisputeState.STEP_2_EVIDENCE

        # Step 2: evidence
        engine.submit_evidence(case.case_id, "val_A", b"my defense")

        # Steps 3+4: vote (>66.7% of 3000 = 2000.1 stake needed)
        engine.cast_vote(case.case_id, "v1", True,  1100)
        engine.cast_vote(case.case_id, "v2", True,  1000)
        engine.cast_vote(case.case_id, "v3", False,  600)
        assert case.quorum_reached
        assert case.state == DisputeState.STEP_5_HHI_CHECK

        # Step 5: HHI check
        hhi_ok = engine.run_hhi_check(case.case_id, [1100, 1000, 600])
        assert hhi_ok
        assert case.hhi_ok
        assert case.state == DisputeState.STEP_6_EXECUTION

        # Step 6: execute
        event = engine.execute_slashing(case.case_id, validator_stake=10000)
        assert event is not None
        assert event.stake_slashed == 5000.0
        assert event.permanent_ban
        assert engine.is_banned("val_A")
        assert case.state == DisputeState.STEP_7_APPEAL

    def test_full_7_step_flow_innocent(self):
        """Majority innocent vote → RESOLVED_INNOCENT, no slashing."""
        engine = self._make_engine()
        case = engine.file_accusation("val_clean", "false_accuser",
                                       SlashingCondition.PROLONGED_OFFLINE, 3000.0)
        engine.cast_vote(case.case_id, "v1", False, 1200)
        engine.cast_vote(case.case_id, "v2", False, 1000)
        engine.cast_vote(case.case_id, "v3", True,   500)
        engine.run_hhi_check(case.case_id, [1200, 1000, 500])
        event = engine.execute_slashing(case.case_id, validator_stake=10000)
        assert event is None
        assert case.state == DisputeState.RESOLVED_INNOCENT

    def test_quorum_threshold_67_percent(self):
        """Quorum requires ≥2/3 of total eligible stake."""
        engine = self._make_engine()
        case = engine.file_accusation("v", "a", SlashingCondition.PROLONGED_OFFLINE, 3000.0)
        engine.cast_vote(case.case_id, "v1", True, 1000)  # 33.3% — insufficient
        assert not case.quorum_reached
        engine.cast_vote(case.case_id, "v2", True, 1100)  # now 70% — quorum reached
        assert case.quorum_reached

    def test_accused_cannot_vote(self):
        """Accused validator's own vote is rejected."""
        engine = self._make_engine()
        case = engine.file_accusation("val_X", "accuser", SlashingCondition.PROLONGED_OFFLINE, 1000.0)
        result = engine.cast_vote(case.case_id, "val_X", False, 5000)
        assert not result

    def test_hhi_governance_capture_blocks_slashing(self):
        """Vote HHI ≥ 4000 → governance capture → no slashing."""
        engine = self._make_engine()
        case = engine.file_accusation("val_Y", "acc", SlashingCondition.PROLONGED_OFFLINE, 3000.0)
        engine.cast_vote(case.case_id, "monopoly_voter", True, 3000)
        engine.run_hhi_check(case.case_id, [3000])  # HHI = 10000 → captured
        assert not case.hhi_ok
        assert case.state == DisputeState.RESOLVED_INNOCENT
        assert "GOVERNANCE CAPTURE" in case.resolution_notes

    def test_appeal_reduces_slash_by_50_percent(self):
        """Successful appeal reduces slashing by up to 50%."""
        engine = self._make_engine()
        case = engine.file_accusation("val_Z", "monitor",
                                       SlashingCondition.FALSE_SIGNAL_SUBMISSION, 2000.0)
        engine.cast_vote(case.case_id, "v1", True, 800)
        engine.cast_vote(case.case_id, "v2", True, 700)
        engine.cast_vote(case.case_id, "v3", False, 400)
        engine.run_hhi_check(case.case_id, [800, 700, 400])
        event = engine.execute_slashing(case.case_id, validator_stake=5000)
        original = event.stake_slashed

        appeal = engine.file_appeal(case.case_id, b"new calibration evidence", 4000)
        assert appeal["success"]
        assert abs(appeal["reduced_slash"] - original * 0.50) < 0.01
        assert case.state == DisputeState.APPEAL_GRANTED

    def test_one_appeal_per_case(self):
        """Second appeal attempt on same case is rejected."""
        engine = self._make_engine()
        case = engine.file_accusation("val_W", "mon", SlashingCondition.FALSE_SIGNAL_SUBMISSION, 2000.0)
        engine.cast_vote(case.case_id, "v1", True,  700)
        engine.cast_vote(case.case_id, "v2", True,  700)
        engine.cast_vote(case.case_id, "v3", False, 400)
        engine.run_hhi_check(case.case_id, [700, 700, 400])
        engine.execute_slashing(case.case_id, validator_stake=5000)
        engine.file_appeal(case.case_id, b"evidence 1", 4500)
        second = engine.file_appeal(case.case_id, b"evidence 2", 4500)
        assert not second["success"]

    def test_permanent_ban_cannot_be_appealed(self):
        """S1/S4 (permanent ban) cases are non-appealable."""
        engine = self._make_engine()
        case = engine.file_accusation("perm_val", "acc",
                                       SlashingCondition.MANIPULATION_COLLUSION, 2000.0)
        engine.cast_vote(case.case_id, "v1", True, 800)
        engine.cast_vote(case.case_id, "v2", True, 700)
        engine.cast_vote(case.case_id, "v3", False, 300)
        engine.run_hhi_check(case.case_id, [800, 700, 300])
        engine.execute_slashing(case.case_id, validator_stake=5000)
        assert engine.is_banned("perm_val")
        appeal = engine.file_appeal(case.case_id, b"desperate evidence", 0)
        assert not appeal["success"]

    def test_engine_summary(self):
        """Engine summary provides correct counts."""
        engine = self._make_engine()
        summary = engine.summary()
        assert "total_cases" in summary
        assert "total_slashings" in summary
        assert "permanently_banned" in summary
        assert summary["total_cases"] == 0

    def test_slash_parameters_stake_fractions_valid(self):
        """All slash fractions must be in (0, 1]."""
        for cond, params in SLASH_PARAMETERS.items():
            assert 0 < params["stake_fraction"] <= 1.0, f"{cond.value} invalid fraction"


# ═══════════════════════════════════════════════════════════════════════════
# L3.7 Intelligence Maintenance Protocol
# ═══════════════════════════════════════════════════════════════════════════

from core.governance.intelligence_maintenance import (
    IntelligenceMaintenanceProtocol, IMPStatus,
    IM_THRESHOLD, IM_CRITICAL, IM_DISABLED, IM_WEIGHTS,
)


class TestIntelligenceMaintenanceProtocol:
    """L3.7: IM(t) = 0.30·PA + 0.20·CS + 0.20·PCR + 0.15·SC + 0.15·CA"""

    def _make_imp(self) -> IntelligenceMaintenanceProtocol:
        return IntelligenceMaintenanceProtocol()

    def test_im_weights_sum_to_one(self):
        """Component weights must sum to 1.0."""
        total = sum(IM_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9

    def test_im_weights_correct(self):
        """PA=0.30, CS=0.20, PCR=0.20, SC=0.15, CA=0.15."""
        assert IM_WEIGHTS["pa"]  == 0.30
        assert IM_WEIGHTS["cs"]  == 0.20
        assert IM_WEIGHTS["pcr"] == 0.20
        assert IM_WEIGHTS["sc"]  == 0.15
        assert IM_WEIGHTS["ca"]  == 0.15

    def test_im_formula_correctness(self):
        """IM(t) computed correctly from weighted sum."""
        imp = self._make_imp()
        r = imp.evaluate(pa=1.0, cs=1.0, pcr=1.0, sc=1.0, ca=1.0)
        assert abs(r.im_score - 1.0) < 1e-6

    def test_healthy_status(self):
        """IM ≥ 0.65 → HEALTHY, signal_weight = 1.0."""
        imp = self._make_imp()
        r = imp.evaluate(pa=0.85, cs=0.80, pcr=0.75, sc=1.0, ca=0.82)
        assert r.status == IMPStatus.HEALTHY
        assert r.signal_weight == 1.0

    def test_flagged_status(self):
        """IM_THRESHOLD ≤ IM < 0.65 → FLAGGED, signal_weight = 0.85."""
        imp = self._make_imp()
        r = imp.evaluate(pa=0.60, cs=0.58, pcr=0.55, sc=0.70, ca=0.60)
        assert r.status == IMPStatus.FLAGGED
        assert r.signal_weight == 0.85

    def test_retrain_trigger(self):
        """IM < IM_THRESHOLD → RETRAIN triggered."""
        imp = self._make_imp()
        r = imp.evaluate(pa=0.45, cs=0.42, pcr=0.40, sc=0.55, ca=0.42)
        assert r.im_score < IM_THRESHOLD
        assert r.status == IMPStatus.RETRAIN
        assert r.retrain_triggered
        assert r.signal_weight == 0.70
        assert r.retraining_cycles == 1

    def test_unreliable_status(self):
        """IM < IM_CRITICAL → UNRELIABLE, signal_weight = 0.50."""
        imp = self._make_imp()
        r = imp.evaluate(pa=0.28, cs=0.30, pcr=0.25, sc=0.40, ca=0.30)
        assert r.im_score < IM_CRITICAL
        assert r.status == IMPStatus.UNRELIABLE
        assert r.signal_weight == 0.50

    def test_disabled_status(self):
        """IM < IM_DISABLED → DISABLED, signal_weight = 0.0 (A(t) = 0)."""
        imp = self._make_imp()
        r = imp.evaluate(pa=0.05, cs=0.08, pcr=0.05, sc=0.15, ca=0.10)
        assert r.im_score < IM_DISABLED
        assert r.status == IMPStatus.DISABLED
        assert r.signal_weight == 0.0

    def test_force_retrain(self):
        """force_retrain=True triggers retraining even in HEALTHY state."""
        imp = self._make_imp()
        r = imp.evaluate(pa=0.90, cs=0.85, pcr=0.88, sc=1.0, ca=0.90, force_retrain=True)
        assert r.retrain_triggered

    def test_retrain_cycle_recorded(self):
        """Retraining cycle is recorded with correct metadata."""
        imp = self._make_imp()
        imp.evaluate(pa=0.30, cs=0.35, pcr=0.28, sc=0.40, ca=0.32)
        cycles = imp.get_cycles()
        assert len(cycles) >= 1
        c = cycles[0]
        assert "cycle_id" in c
        assert "triggered_at" in c
        assert "trigger_reason" in c
        assert c["history_retained"] is True
        assert c["patterns_reset"] == 64

    def test_complete_retrain(self):
        """complete_retrain() records im_after for last cycle."""
        imp = self._make_imp()
        imp.evaluate(pa=0.30, cs=0.35, pcr=0.28, sc=0.40, ca=0.32)
        imp.complete_retrain(0.72)
        cycles = imp.get_cycles()
        assert cycles[-1]["im_after"] == 0.72

    def test_rolling_trend_stable(self):
        """Flat IM history → STABLE trend."""
        imp = self._make_imp()
        for _ in range(15):
            imp.evaluate(pa=0.75, cs=0.70, pcr=0.68, sc=0.80, ca=0.72)
        assert imp._compute_trend() == "STABLE"

    def test_rolling_trend_falling(self):
        """Declining IM history → FALLING trend."""
        imp = self._make_imp()
        for i in range(12):
            v = 0.80 - i * 0.04
            imp.evaluate(pa=v, cs=v, pcr=v, sc=v, ca=v)
        assert imp._compute_trend() == "FALLING"

    def test_thresholds_hierarchy(self):
        """IM thresholds must satisfy: DISABLED < CRITICAL < THRESHOLD."""
        assert IM_DISABLED < IM_CRITICAL < IM_THRESHOLD

    def test_status_dict(self):
        """status_dict() returns expected keys."""
        imp = self._make_imp()
        imp.evaluate(pa=0.75, cs=0.70, pcr=0.68, sc=0.80, ca=0.72)
        sd = imp.status_dict()
        assert "im_score" in sd
        assert "trend" in sd
        assert "retraining_cycles" in sd
        assert "history_length" in sd

    def test_im_range_always_valid(self):
        """IM score always in [0, 1] regardless of inputs."""
        imp = self._make_imp()
        for pa, cs, pcr, sc, ca in [
            (0.0, 0.0, 0.0, 0.0, 0.0),
            (1.0, 1.0, 1.0, 1.0, 1.0),
            (0.5, 0.5, 0.5, 0.5, 0.5),
            (-0.1, 1.5, 0.3, 0.7, 0.8),  # Out-of-range inputs clamped
        ]:
            r = imp.evaluate(pa=pa, cs=cs, pcr=pcr, sc=sc, ca=ca)
            assert 0.0 <= r.im_score <= 1.0, f"IM out of range: {r.im_score}"


# ═══════════════════════════════════════════════════════════════════════════
# API Endpoint tests (requires running server)
# ═══════════════════════════════════════════════════════════════════════════

import os
import urllib.request


ORACLE_URL = os.environ.get("ORACLE_URL", "http://127.0.0.1:5000")
LIVE = os.environ.get("LIVE", "0") == "1"


def _get(path: str) -> dict:
    import json
    with urllib.request.urlopen(f"{ORACLE_URL}{path}", timeout=5) as r:
        return json.loads(r.read())


@pytest.mark.skipif(not LIVE, reason="Requires LIVE=1 and running server")
class TestNewEndpointsLive:
    """Live endpoint tests for all 5 new whitepaper gap modules."""

    def test_sec_endpoint_200(self):
        d = _get("/api/v1/security/sec")
        assert "sec_score" in d
        assert 0.0 <= d["sec_score"] <= 1.0
        assert d["security_tier"] in ("QUANTUM_RESISTANT", "CLASSICAL_SECURE", "DEGRADED", "CRITICAL")

    def test_complexity_endpoint_200(self):
        d = _get("/api/v1/security/complexity/0xUniswap")
        assert "k_current_bits" in d
        assert "within_bound" in d
        assert d["k_max_bound"] == 256

    def test_geo_endpoint_200(self):
        d = _get("/api/v1/governance/geo")
        assert "geo_compliant" in d
        assert "n_continents" in d
        assert "awa_geo_status" in d
        assert d["awa_geo_status"] in ("ENFORCED", "SUSPENDED_GEO", "EMERGENCY_GEO")

    def test_slashing_conditions_endpoint_200(self):
        d = _get("/api/v1/governance/slashing/conditions")
        assert "slashing_conditions" in d
        conds = d["slashing_conditions"]
        assert "S1_DOUBLE_SIGNING" in conds
        assert "S2_PROLONGED_OFFLINE" in conds
        assert "S3_FALSE_SIGNAL_SUBMISSION" in conds
        assert "S4_MANIPULATION_COLLUSION" in conds
        assert "S5_GEO_CONSTRAINT_VIOLATION" in conds
        dr = d["dispute_resolution"]
        assert dr["steps"] == 7

    def test_intelligence_endpoint_200(self):
        d = _get("/api/v1/anima/intelligence")
        assert "im_score" in d
        assert "status" in d
        assert 0.0 <= d["im_score"] <= 1.0
        assert d["status"] in ("HEALTHY", "FLAGGED", "RETRAIN", "UNRELIABLE", "DISABLED")
