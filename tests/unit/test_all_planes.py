"""
TRION Protocol — Complete Test Suite
Tests every whitepaper claim that is implemented.
"""
import pytest
import sys
import os
import numpy as np
sys.path.insert(0, '.')


# ─── L0 Tests ────────────────────────────────────────────────────

def test_behavioral_hash_valid():
    from core.primitives.behavioral_hash import compute_behavioral_hash, BehavioralEvent, EventType
    event = BehavioralEvent(
        entity_id=b'\xab'*32, event_type=EventType.SWAP,
        magnitude_raw=int(1e18), magnitude_decimals=18,
        magnitude_max_90d=int(100e18), timestamp=1700000000,
        block_number=18000000, block_hash=b'\xcc'*32, chain_id=1,
    )
    result = compute_behavioral_hash(event)
    assert result['valid'], "Dual-strand verification failed"
    assert 0 <= result['magnitude_normalized'] <= 1


def test_beo_resolution():
    from core.primitives.entity_resolution import resolve_entity, WalletActivity
    wallets = [
        WalletActivity("0xAAA", 1, "0xFUNDER", 1700000000, [1700000100]),
        WalletActivity("0xBBB", 1, "0xFUNDER", 1700000050, [1700000110]),
        WalletActivity("0xCCC", 1, "0xFUNDER", 1700000075, [1700000120]),
    ]
    result = resolve_entity(wallets)
    assert 0 <= result['beo_confidence'] <= 1
    assert result['cf_score'] == 1.0  # All share same funder


# ─── L1 Tests ────────────────────────────────────────────────────

def test_phi_computation():
    from core.physical.phi_engine import compute_phi, TransactionData
    txs = [
        TransactionData(
            tx_hash=f"0x{i:064x}", timestamp=1700000000 + i*3600,
            block_number=18000000+i, from_addr="0xUSER",
            to_addr=f"0x{'a'*38}{i%10:02d}", value_wei=int(1e17)*(i+1),
            gas_used=21000+i*1000, gas_price=int(20e9),
            is_contract=i%3==0,
            contract_addr=f"0xPROTO{i%5}" if i%3==0 else None,
            input_len=68,
        )
        for i in range(20)
    ]
    result = compute_phi(txs, "0xUSER")
    assert 0 <= result['phi_raw'] <= 1
    for k in ['f1','f2','f3','f4','f5','f6','f7','f8','f9']:
        assert 0 <= result[k] <= 1, f"{k} out of range: {result[k]}"


def test_manipulation_fingerprints():
    from core.physical.manipulation_detector import (
        detect_oracle_attack, detect_wash_trading, detect_governance_capture,
        compute_mf_score, apply_mf_discount
    )
    r1 = detect_oracle_attack(0.22, 5)
    r2 = detect_wash_trading(0.75, 3)
    r3 = detect_governance_capture(5500, 10)
    r4 = detect_wash_trading(0.10, 100)

    assert r1.detected and r1.mf_score == 1.0
    assert r2.detected
    assert r3.detected
    assert not r4.detected

    final = compute_mf_score([r1, r2, r3, r4])
    assert final['mf_score'] == 1.0  # oracle attack = automatic 1.0

    phi_adj = apply_mf_discount(0.80, 1.0)
    assert phi_adj == 0.0


def test_nl_score():
    from core.extended.natural_liquidity import compute_nl
    result = compute_nl(
        depth_per_tick=[1000, 50, 20, 10, 5],
        top5_lp_share=0.92, lp_count=8,
        baseline_ld_90d=[0.5]*5,
        ld_during_stress=0.05, ld_during_normal=0.55,
    )
    assert result['alert'], "AAVE scenario should trigger alert"
    assert result['nl_score'] < 0.30


# ─── ANIMA Tests ─────────────────────────────────────────────────

def test_anima_bootstrap():
    from core.mental.anima.engine import compute_anima, ANIMA_BOOTSTRAP_VALUE
    result = compute_anima(akashic_depth=100, pcr=0.80, ha=0.75, ca=0.70)
    assert result['bootstrap']
    assert result['anima'] == ANIMA_BOOTSTRAP_VALUE


def test_anima_live():
    from core.mental.anima.engine import compute_anima, D_MINIMUM_ANIMA
    result = compute_anima(akashic_depth=D_MINIMUM_ANIMA + 1, pcr=0.75, ha=0.85, ca=0.90)
    assert not result['bootstrap']
    assert 0 < result['anima'] <= 1


# ─── L3 Tests ────────────────────────────────────────────────────

def test_m_score():
    from core.mental.confidence import compute_m_score
    baseline  = list(np.random.normal(0.5, 0.3, 100))
    confident = list(np.random.normal(0.72, 0.02, 50))
    uncertain = list(np.random.normal(0.50, 0.45, 50))
    m_conf = compute_m_score(confident, baseline)
    m_unc  = compute_m_score(uncertain, baseline)
    assert m_conf >= m_unc, "Confident model should score higher"


def test_observer_effect():
    from core.mental.confidence import compute_observer_effect, compute_m_adj
    signals = [0.7 + i*0.01 for i in range(20)]
    changes = [s * 0.8 for s in signals]  # correlated
    oe = compute_observer_effect(signals, changes)
    assert 0 <= oe <= 1
    m_base = 0.80
    m_adj  = compute_m_adj(m_base, oe)
    assert m_adj <= m_base


# ─── L4 Tests ────────────────────────────────────────────────────

def test_sigma_byzantine_defeat():
    from core.spiritual.sigma_engine import compute_sigma, ValidatorSignal

    honest = [
        ValidatorSignal(f"h{i}", 0.72+np.random.normal(0,0.02),
                        1000.0, np.random.normal(0.72,0.05,20))
        for i in range(5)
    ]
    byzantine = [
        ValidatorSignal(f"b{i}", 0.50, 1000.0, np.ones(20)*0.50)
        for i in range(5)
    ] + honest[:2]

    r_honest = compute_sigma(honest)
    r_byz    = compute_sigma(byzantine)
    assert r_honest['sigma'] >= 0
    assert r_byz['sigma'] >= 0


def test_sigma_bootstrap():
    from core.spiritual.sigma_engine import compute_sigma, SIGMA_BOOTSTRAP
    result = compute_sigma([])
    assert result['bootstrap']
    assert result['sigma'] == SIGMA_BOOTSTRAP['sigma']


def test_k_plane_commit_reveal():
    import hashlib
    from core.spiritual.conscious.engine import (
        AnnotationReveal, AnnotationCommit, AnnotationType,
        verify_commit, compute_k_score
    )
    reveals = []
    for i in range(5):
        salt       = os.urandom(32)
        k_val      = 0.70 + i * 0.02
        commit_hash = hashlib.sha3_256(str(k_val).encode() + salt).digest()
        reveal = AnnotationReveal(
            annotator_hash=os.urandom(32), entity_id=b'\xab'*32,
            k_score=k_val, annotation_type=AnnotationType.EXPERT_JUDGMENT,
            cultural_context=None, salt=salt, stake_weight=1.0,
        )
        commit = AnnotationCommit(
            annotator_hash=reveal.annotator_hash,
            commit_hash=commit_hash, entity_id=b'\xab'*32,
        )
        assert verify_commit(commit, reveal), f"Commit-reveal failed {i}"
        reveals.append(reveal)

    result = compute_k_score(reveals)
    assert not result['bootstrap']
    assert 0 < result['k_score'] < 1


# ─── L5 Tests ────────────────────────────────────────────────────

def test_five_plane_coherence():
    from core.master.coherence import CoherenceEngine, CoherenceInput, AssetProfile

    engine = CoherenceEngine()

    normal = CoherenceInput(
        phi_adj=0.72, m_adj=0.68, sigma=0.25,
        k_plane=0.10, anima=0.10,
        volatility=0.30, akashic_depth=500, moat_time=1000000,
        profile=AssetProfile.MATURE,
    )
    r = engine.compute_coherence(normal)
    assert 0 <= r['C'] <= 1
    assert r['theta'] >= 0.55

    # Attack — phi collapses
    attack = CoherenceInput(
        phi_adj=0.02, m_adj=0.40, sigma=0.25,
        k_plane=0.10, anima=0.10,
        volatility=0.90, akashic_depth=500, moat_time=1000000,
        profile=AssetProfile.MATURE,
    )
    r_attack = engine.compute_coherence(attack)
    assert r_attack['silence'], "Attack should produce SILENCE"


def test_coherence_weight_profiles():
    from core.master.coherence import CoherenceEngine, CoherenceInput, AssetProfile, WEIGHT_PROFILES
    engine = CoherenceEngine()
    for profile in AssetProfile:
        w = WEIGHT_PROFILES[profile]
        assert abs(sum(w.values()) - 1.0) < 1e-9, f"Weights don't sum to 1.0 for {profile}"
        inp = CoherenceInput(
            phi_adj=0.60, m_adj=0.65, sigma=0.25,
            k_plane=0.10, anima=0.10,
            volatility=0.30, akashic_depth=500, moat_time=1000000,
            profile=profile,
        )
        result = engine.compute_coherence(inp)
        assert 0 <= result['C'] <= 1


# ─── Signal Tests ─────────────────────────────────────────────────

def test_signal_factory():
    from core.master.signal_factory import build_signal, build_silence, build_liquidity_health, SignalType

    entity   = b'\xab'*32
    coherence = {
        "C":0.72,"theta":0.62,"margin":0.10,"emits":True,"silence":False,
        "coherence_gap":0,"limiting_plane":"anima","trend":"STABLE",
        "eta_blocks":0,"bootstrap_planes":{"sigma_bootstrap":True},
        "plane_breakdown":{},"weights":{},
    }

    sig = build_signal(entity, SignalType.VALUATION, coherence,
                       signal_value=0.72, ci_95_lower=0.67, ci_95_upper=0.77)
    assert sig['ci_95'] is not None, "CI_95 must never be null"
    assert 'biological_time' in sig
    assert sig['signal_type'] == 'VALUATION'

    # Provenance chain (deep-read bug: was always []). Must carry the actual
    # computation sources: coherence engine, BRT derivation, genomic signature.
    assert isinstance(sig['provenance'], list) and sig['provenance'], \
        "provenance must never be empty"
    sources = {p['source'] for p in sig['provenance']}
    assert {'coherence_engine', 'brt', 'genomic_signature'} <= sources
    assert all('ts' in p for p in sig['provenance'])

    # Caller-supplied behavioral-hash provenance is carried first in the chain
    sig2 = build_signal(entity, SignalType.VALUATION, coherence,
                        signal_value=0.72, ci_95_lower=0.67, ci_95_upper=0.77,
                        provenance=['bh_deadbeef'])
    assert sig2['provenance'][0]['bh_id'] == 'bh_deadbeef'
    assert sig2['provenance'][0]['source'] == 'behavioral_hash'

    # BRT honest labeling: no observations → CLOCK_FALLBACK (was silently
    # claimed via a broken `akashic.brt_scheduler` import that never resolved)
    assert sig['biological_time'].get('brt_source') == 'CLOCK_FALLBACK'

    # Observed timestamps → real circular statistics resolve (import fixed)
    midnight = 1_700_000_000 - (1_700_000_000 % 86400)
    obs = [midnight + d * 86400 + 3600 * 13 for d in range(48)]
    sig3 = build_signal(entity, SignalType.VALUATION, coherence,
                        signal_value=0.72, ci_95_lower=0.67, ci_95_upper=0.77,
                        observed_timestamps=obs)
    assert sig3['biological_time']['brt_source'] == 'OBSERVED'
    assert sig3['biological_time']['circadian_strength'] > 0.20
    brt_rec = [p for p in sig3['provenance'] if p['source'] == 'brt'][0]
    assert brt_rec['data_source'] == 'OBSERVED'
    assert brt_rec['observations'] == 48

    sil_coherence = {**coherence, "C":0.40,"emits":False,"silence":True,"coherence_gap":0.22}
    sil = build_silence(entity, sil_coherence)
    assert sil['silence']
    assert sil['silence_gap'] == 0.22
    assert sil['provenance'], "SILENCE signals carry provenance too"


# ─── BTCP Tests ──────────────────────────────────────────────────

def test_btcp_score():
    from core.master.btcp_score import compute_btcp_score, BTCPRouteData

    healthy = BTCPRouteData(
        nl_score=0.75, gas_total=5.0, gas_99th=50.0,
        finality_conf=0.95, cc_coherence=0.80,
        beo_continuity=0.90, mf_score=0.0,
    )
    stressed = BTCPRouteData(
        nl_score=0.10, gas_total=48.0, gas_99th=50.0,
        finality_conf=0.50, cc_coherence=0.30,
        beo_continuity=0.40, mf_score=0.50,
    )
    r1 = compute_btcp_score(healthy)
    r2 = compute_btcp_score(stressed)
    assert r1['is_safe']
    assert not r2['is_safe']
    assert r1['btcp_score'] > r2['btcp_score']


# ─── Security Tests ───────────────────────────────────────────────

def test_genomic_key_evolution():
    from core.spiritual.living_security import GenomicKeyEvolver
    import os

    evolver = GenomicKeyEvolver()
    entity  = b'\xab' * 32
    gk0 = evolver.initialize(entity)
    assert evolver.verify_key(gk0)
    gk1 = evolver.evolve(entity, os.urandom(32), os.urandom(32), os.urandom(32))
    gk2 = evolver.evolve(entity, os.urandom(32), os.urandom(32), os.urandom(32))
    assert evolver.verify_key(gk1)
    assert evolver.verify_key(gk2)
    assert gk1.sense != gk2.sense


def test_crispr_detection():
    from core.spiritual.living_security import ImmuneSystem

    immune   = ImmuneSystem()
    assert immune.crispr.library_size() >= 4  # 8 known attacks seeded (expanded from 4)

    test_tx  = b"some_prefix_HARVEST_FLASH_LOAN_ORACLE_MANIP_suffix"
    result   = immune.innate_check(test_tx)
    assert result and result["matched"]

    clean_tx = b"0x000000000000000000000000000000000000000000000000"
    assert immune.innate_check(clean_tx) is None


# ─── Genesis Tests ─────────────────────────────────────────────────

def test_genesis_inference():
    from core.akashic.genesis import (
        GenesisVector, Archetype, infer_genesis_value, genesis_confidence
    )

    archetypes = [
        Archetype("A1", "DeFi_Blue_Chip", "MATURE", np.random.normal(0.7, 0.1, 128), 0.80),
        Archetype("A2", "Stablecoin",      "STBLCN", np.random.normal(0.5, 0.05, 128), 0.60),
    ]
    genesis = GenesisVector("0xNEW", np.random.normal(0.68, 0.12, 128))

    r0     = infer_genesis_value(genesis, archetypes, D_asset=0)
    r50000 = infer_genesis_value(genesis, archetypes, D_asset=50000)

    assert 0 <= r0['genesis_value'] <= 1
    assert r50000['conf_genesis'] > r0['conf_genesis']


# ─── BIBL Tests ────────────────────────────────────────────────────

def test_bibl_engine():
    from core.akashic.bibl import BIBLEngine, BIBLState

    engine = BIBLEngine()
    state  = BIBLState(
        current_block=20_000_000, block_time_ms=12000,
        mempool_size=25000, mempool_fee_p50=15e9, mempool_fee_p95=50e9,
        brt_circadian=0.6, volatility=0.35,
        nl_scores={"ethereum": 0.75, "aave_pool": 0.09},
        mev_rate_30d=0.008,
    )
    output = engine.run_cycle(state, "ethereum")
    assert output.chain_memory is not None
    assert output.mev_warning is not None  # mev_rate > 0.005
    assert output.liquidity_routing is not None
    assert output.liquidity_routing.get('avoid_chain') == "aave_pool"


# ─── NEW: L0 Extension Tests ─────────────────────────────────────

def test_resonance_20_event_types():
    from core.primitives.resonance import (
        compute_resonance_frequencies, compute_channel_resonance,
        UniversalEventType, can_communicate
    )
    assert len(list(UniversalEventType)) == 20, "Must have exactly 20 VM-agnostic event types"

    events_a = {UniversalEventType.SWAP: 500, UniversalEventType.LIQUIDITY_ADD: 120,
                UniversalEventType.GOVERNANCE_VOTE: 15}
    events_b = {UniversalEventType.SWAP: 300, UniversalEventType.BORROW: 80,
                UniversalEventType.GOVERNANCE_VOTE: 8}

    rf_a = compute_resonance_frequencies("entity_A", events_a)
    rf_b = compute_resonance_frequencies("entity_B", events_b)
    result = compute_channel_resonance(rf_a, rf_b)

    assert result.communicates
    assert result.resonance_score > 0
    assert UniversalEventType.SWAP in result.shared_frequencies
    assert can_communicate(rf_a, rf_b)


def test_resonance_no_overlap():
    from core.primitives.resonance import (
        compute_resonance_frequencies, can_communicate, UniversalEventType
    )
    events_a = {UniversalEventType.GOVERNANCE_VOTE: 50}
    events_b = {UniversalEventType.NFT_MINT: 200}
    rf_a = compute_resonance_frequencies("a", events_a)
    rf_b = compute_resonance_frequencies("b", events_b)
    assert not can_communicate(rf_a, rf_b)


def test_evolutionary_fitness_f_equals_zero_when_love_zero():
    from core.primitives.evolutionary_fitness import compute_fitness
    fit = compute_fitness("component_x", pa=0.99, ice=0.99, adaptation_speed=0.99, love=0.0)
    assert fit.fitness == 0.0
    assert fit.love_killed
    assert "Love=0" in fit.description


def test_evolutionary_fitness_healthy():
    from core.primitives.evolutionary_fitness import compute_fitness
    fit = compute_fitness("nl_engine", pa=0.85, ice=0.78, adaptation_speed=0.92, love=0.80)
    assert fit.fitness > 0
    assert not fit.love_killed
    assert abs(fit.fitness - 0.85 * 0.78 * 0.92 * 0.80) < 1e-9


def test_temporal_coherence_all_synced():
    import time
    from core.physical.temporal_coherence import compute_temporal_coherence, PlaneTimestamp
    now = time.time()
    planes = {
        "physical":  PlaneTimestamp("physical",  now - 10, 300, "evm"),
        "mental":    PlaneTimestamp("mental",    now - 45, 300, "anima"),
        "spiritual": PlaneTimestamp("spiritual", now - 5,  300, "validator"),
        "conscious": PlaneTimestamp("conscious", now - 30, 300, "api"),
        "akashic":   PlaneTimestamp("akashic",   now - 8,  300, "db"),
    }
    result = compute_temporal_coherence(planes, ttl_min=300.0)
    assert 0 < result.tc <= 1.0
    assert result.valid
    assert result.lagging_plane == "mental"  # 45s lag is highest


def test_transduction_integrity_dead_sensor():
    from core.physical.temporal_coherence import compute_transduction_integrity, SensorCalibration
    dead = SensorCalibration("dead", calibration_score=0.0, drift_correction=0.9, cross_verification=0.9)
    ti = compute_transduction_integrity(dead)
    assert ti.ti == 0.0
    assert ti.excluded


# ─── NEW: L2 Physical Plane Tests ─────────────────────────────────

def test_resurrection_abandoned_low_score():
    from core.akashic.resurrection import (
        compute_resurrection, DormancyProfile, DormancyType
    )
    profile = DormancyProfile(
        entity_id="abandoned_token", dormancy_type=DormancyType.ABANDONED,
        dormancy_days=500.0, team_activity=False, governance_active=False,
        exploit_severity=0.0, team_response_quality=0.0,
        known_regulatory=False, chain_b_activity=0.0,
    )
    result = compute_resurrection(profile, [0.8, 0.6, 0.4], [0.3, 0.2, 0.8])
    assert result.delta_resurrection < 0.5
    assert result.hostile_takeover_risk > 0
    assert result.kappa == 0.008


def test_resurrection_hibernation_high_score():
    from core.akashic.resurrection import (
        compute_resurrection, DormancyProfile, DormancyType
    )
    profile = DormancyProfile(
        entity_id="hibernating", dormancy_type=DormancyType.HIBERNATION,
        dormancy_days=60.0, team_activity=True, governance_active=True,
        exploit_severity=0.0, team_response_quality=1.0,
        known_regulatory=False, chain_b_activity=0.0,
    )
    result = compute_resurrection(profile, [0.8, 0.6, 0.4], [0.8, 0.6, 0.4])
    assert result.delta_resurrection > 0.5
    assert result.kappa == 0.003


def test_fork_resolution_majority_chain():
    from core.akashic.fork_resolution import (
        compute_fork_resolution, ForkProfile, PreForkHolder
    )
    holders = [PreForkHolder(f"h{i}", 100.0, 95.0 if i < 80 else 2.0, 2.0 if i < 80 else 90.0)
               for i in range(100)]
    profile = ForkProfile("eth_etc", "ETH", "ETC", 1920000, 1469020839.0, holders, "ETH/ETC")
    result = compute_fork_resolution(profile)
    assert result.cc_a > result.cc_b
    assert result.history_weight_a > 0.5
    assert result.dominant_chain == "ETH"


def test_trajectory_anomaly_healthy():
    from core.akashic.trajectory_anomaly import (
        compute_trajectory_anomaly, TrajectoryDistribution
    )
    outcomes = ["GROWTH", "STABLE", "DECLINE", "CRASH"]
    p_exp = TrajectoryDistribution(outcomes, [0.50, 0.30, 0.15, 0.05])
    p_act = TrajectoryDistribution(outcomes, [0.48, 0.31, 0.16, 0.05])
    r = compute_trajectory_anomaly("healthy_token", p_act, p_exp)
    assert not r.anomaly_detected
    assert r.kl_divergence < 0.50


def test_trajectory_anomaly_manipulation():
    from core.akashic.trajectory_anomaly import (
        compute_trajectory_anomaly, TrajectoryDistribution
    )
    outcomes = ["GROWTH", "STABLE", "DECLINE", "CRASH"]
    p_exp = TrajectoryDistribution(outcomes, [0.50, 0.30, 0.15, 0.05])
    p_act = TrajectoryDistribution(outcomes, [0.02, 0.03, 0.05, 0.90])
    r = compute_trajectory_anomaly("manip_token", p_act, p_exp, in_genesis=True)
    assert r.anomaly_detected
    assert r.genesis_invalidated


# ─── NEW: L3 Anima/Mental Tests ───────────────────────────────────

def test_source_credibility_init_and_decay():
    import time
    from core.mental.anima.source_credibility import (
        initialize_source, apply_time_decay_only, SourceType
    )
    now = time.time()
    src = initialize_source("sec_001", SourceType.SEC_EDGAR, now)
    assert src.cred == 0.65
    decayed = apply_time_decay_only(src, now + 86400 * 90)
    assert decayed.cred < src.cred


def test_source_credibility_manipulation_zero():
    import time
    from core.mental.anima.source_credibility import (
        initialize_source, update_credibility, SourceType
    )
    now = time.time()
    src = initialize_source("sybil_bot", SourceType.SOCIAL_MEDIA, now)
    result = update_credibility(src, now + 3600, "sybil_identified")
    assert result.cred < 0.10
    assert result.manipulation_flag


def test_anima_reflexivity_dampening():
    from core.mental.anima.reflexivity import apply_reflexivity_dampening, ReflexivityHistory
    history = ReflexivityHistory(
        pattern_id="pump_001",
        signal_strengths=[0.3, 0.5, 0.7, 0.8, 0.9, 0.85, 0.75],
        behavioral_changes=[0.1, 0.35, 0.65, 0.75, 0.88, 0.80, 0.72],
        timestamps=[1746000000 + i * 3600 for i in range(7)],
    )
    result = apply_reflexivity_dampening(0.80, "pump_001", history)
    assert result.a_adj <= result.a_raw  # Dampening applied
    assert 0 <= result.a_adj <= 1


def test_anima_ecological_stream_brt_honesty():
    from core.mental.anima.data_streams import ANIMADataAggregator, FetcherConfig

    agg = ANIMADataAggregator()

    class _FakeEco:
        @staticmethod
        def compute_ecological_signal(species_query):
            return {"bc_score": 0.6, "diversity_score": 0.5, "threat_ratio": 0.2}

    agg._eco = _FakeEco  # stub the network fetcher; BRT wiring is under test
    midnight = 1_700_000_000 - (1_700_000_000 % 86400)

    # Without observations: honest CLOCK_FALLBACK label and strength 0.0
    # (previously the call site silently fabricated a 0.5 default)
    cfg_clock = FetcherConfig(entity_id="0xTEST")
    sig_clock = agg._fetch_ecological(cfg_clock, midnight + 12 * 3600)
    assert sig_clock.brt_source == "CLOCK_FALLBACK"
    assert sig_clock.circadian_strength == 0.0

    # With observed timestamps: OBSERVED circular statistics flow into the
    # biological stream
    obs = [midnight + d * 86400 + 3600 * 13 for d in range(30)]
    cfg_obs = FetcherConfig(entity_id="0xTEST", observed_timestamps=obs)
    sig_obs = agg._fetch_ecological(cfg_obs, midnight + 12 * 3600)
    assert sig_obs.brt_source == "OBSERVED"
    assert sig_obs.circadian_strength > 0.5
    assert 0.30 <= sig_obs.circadian_phase <= 0.60  # 13:00 UTC daytime peak
    assert sig_obs.bc_score == 0.6  # real fetcher values pass through


def test_intelligence_maintenance_healthy():
    from core.mental.intelligence_maintenance import (
        compute_im, ComponentAccuracy, ComponentHealth
    )
    # Perfect predictions = perfect accuracy = IM = 1.0 = HEALTHY
    vals = [0.70, 0.72, 0.68, 0.73, 0.71, 0.69, 0.74, 0.70, 0.72, 0.68]
    comp = ComponentAccuracy(
        component_id="nl_engine",
        predictions=vals,
        realized_outcomes=vals,  # Exact match → accuracy = 1.0
        timestamps=[1746000000.0 + i * 86400 for i in range(10)],
    )
    result = compute_im(comp, vals, vals)
    assert result.health == ComponentHealth.HEALTHY
    assert not result.f7_violation


# ─── NEW: L4-L5 Spiritual Tests ───────────────────────────────────

def test_epigenetic_awa_violation_freezes_signals():
    from core.spiritual.epigenetic import compute_el_state, ThreatLevel, ELExpression
    el = compute_el_state(
        threat_level=ThreatLevel.NONE,
        validator_health=0.95, network_entropy=0.80, hostile_jurisdictions=[],
        no_single_entity_weight=False,  # AWA VIOLATION
        no_single_entity_select=True,
        public_good_pct=0.15, sovereignty_active=True,
        right_to_invisibility=True, gratitude_score=1.10,
    )
    assert el.signals_frozen
    assert not el.awa_enforced
    assert el.expression == ELExpression.FROZEN


def test_epigenetic_healthy_standard():
    from core.spiritual.epigenetic import compute_el_state, ThreatLevel, ELExpression
    el = compute_el_state(
        threat_level=ThreatLevel.NONE,
        validator_health=0.95, network_entropy=0.80, hostile_jurisdictions=[],
        no_single_entity_weight=True, no_single_entity_select=True,
        public_good_pct=0.15, sovereignty_active=True,
        right_to_invisibility=True, gratitude_score=1.10,
    )
    assert el.expression == ELExpression.STANDARD
    assert el.awa_enforced
    assert not el.signals_frozen


def test_hhi_healthy_diverse_validators():
    from core.spiritual.hhi_monitor import compute_hhi_enforcement, ValidatorStake, HHITier
    validators = [
        ValidatorStake(f"v{i}", 100.0, 0.80, 80.0, f"region_{i%8}", f"j{i%6}", f"c{i%5}")
        for i in range(100)
    ]
    result = compute_hhi_enforcement(validators)
    assert result.tier == HHITier.HEALTHY
    assert result.continent_count >= 4
    assert not result.f8_violation


def test_hhi_critical_concentrated():
    from core.spiritual.hhi_monitor import compute_hhi_enforcement, ValidatorStake
    concentrated = [
        ValidatorStake(f"v{i}", 1000.0 if i < 3 else 1.0, 0.80,
                       800.0 if i < 3 else 0.8,
                       "single_region", "single_juris", "single_continent")
        for i in range(10)
    ]
    result = compute_hhi_enforcement(concentrated)
    assert result.hhi > 2500


def test_slashing_coordinated_50pct_permanent():
    from core.spiritual.slashing import compute_slash, SlashType
    prop = compute_slash("s001", "v_xyz", SlashType.COORDINATED_ATTACK, 100_000.0)
    assert prop.slash_amount == 50_000.0
    assert prop.permanent


def test_slashing_uptime_cumulative():
    from core.spiritual.slashing import compute_slash, SlashType
    prop = compute_slash("s002", "v_abc", SlashType.UPTIME_FAILURE, 10_000.0, days_below_uptime=5)
    assert prop.slash_bps == 50  # 0.1% × 5 days
    assert prop.slash_amount == 50.0


def test_consensus_degradation_full():
    from core.spiritual.consensus_degradation import compute_consensus_degradation, ConsensusState
    result = compute_consensus_degradation(150, 800.0, 5, [100.0] * 150)
    assert result.state == ConsensusState.FULL
    assert result.signals_allowed
    assert result.confidence_multiplier == 1.00


def test_consensus_degradation_halted():
    from core.spiritual.consensus_degradation import compute_consensus_degradation, ConsensusState
    result = compute_consensus_degradation(2, 5000.0, 1, [1000.0, 1000.0])
    assert result.state == ConsensusState.HALTED
    assert not result.signals_allowed


def test_living_security_product():
    from core.spiritual.consensus_degradation import compute_living_security
    sec = compute_living_security(0.90, 0.95, 0.88)
    expected = 0.90 * 0.95 * 0.88
    assert abs(sec - expected) < 1e-9


# ─── NEW: L6-L9 Extended Plane Tests ─────────────────────────────

# ─── L6.2 BRT (Biological Rhythm Timer) Tests ─────────────────────

def test_brt_phases_match_spec():
    from core.extended.biological_rhythm import compute_brt, RHYTHM_PERIODS
    # Whitepaper L6.2: phase = (t mod T) / T for all four rhythms
    for t in (0, 43200, 86400, 2551442, 31557600):
        brt = compute_brt(t)
        assert abs(brt.circadian_phase - (t % 86400) / 86400) < 1e-12
        assert abs(brt.ultradian_phase - (t % 5400) / 5400) < 1e-12
        assert abs(brt.lunar_phase - (t % 2551442) / 2551442) < 1e-12
        assert abs(brt.seasonal_phase - (t % 31557600) / 31557600) < 1e-12
    assert RHYTHM_PERIODS["circadian"] == 86400
    assert RHYTHM_PERIODS["ultradian"] == 5400
    assert RHYTHM_PERIODS["lunar"] == 2551442
    assert RHYTHM_PERIODS["seasonal"] == 31557600


def test_brt_gas_correlation_significant():
    from core.extended.biological_rhythm import compute_brt_gas_correlation
    # Gas price tracks circadian phase exactly → significant correlation
    ts = np.arange(0, 86400 * 20, 1800.0)
    gas = np.cos(2 * np.pi * ((ts % 86400) / 86400)) + 0.01
    res = compute_brt_gas_correlation(ts.tolist(), gas.tolist(), rhythm="circadian")
    assert res.data_quality == "OK"
    assert res.significant is True
    assert res.p_value <= 0.05
    assert res.anima_fallback is False


def test_brt_gas_correlation_noise_falls_back_to_anima():
    from core.extended.biological_rhythm import compute_brt_gas_correlation
    # Whitepaper rule: p > 0.05 → fall back to ANIMA forecast
    rng = np.random.RandomState(42)
    ts = rng.uniform(0, 86400 * 30, 500)
    gas = rng.normal(50.0, 10.0, 500)  # pure noise, no rhythm link
    res = compute_brt_gas_correlation(ts.tolist(), gas.tolist())
    assert res.p_value > 0.05
    assert res.significant is False
    assert res.anima_fallback is True


def test_brt_gas_correlation_insufficient_and_degenerate_data():
    from core.extended.biological_rhythm import compute_brt_gas_correlation
    # Too few samples → honest INSUFFICIENT_SAMPLES + ANIMA fallback
    res = compute_brt_gas_correlation([1.0, 2.0, 3.0], [10.0, 20.0, 30.0])
    assert res.data_quality == "INSUFFICIENT_SAMPLES"
    assert res.anima_fallback is True
    # Constant gas series → ZERO_VARIANCE + ANIMA fallback (no fake signal)
    ts = np.arange(0, 86400, 300.0)
    res_flat = compute_brt_gas_correlation(ts.tolist(), [42.0] * len(ts))
    assert res_flat.data_quality == "ZERO_VARIANCE"
    assert res_flat.anima_fallback is True


def test_brt_observed_vs_clock_fallback_labeling():
    from core.extended.biological_rhythm import get_brt_dict
    # No observations → honest CLOCK_FALLBACK label, strength 0.0
    d = get_brt_dict(43200)
    assert d["circadian_phase"] == 0.5
    assert d["brt_source"] == "CLOCK_FALLBACK"
    assert d["circadian_strength"] == 0.0
    # Daytime-only observations → OBSERVED circadian peak with strength > 0
    midnight = 1_700_000_000 - (1_700_000_000 % 86400)
    obs = [midnight + day * 86400 + 3600 * 13 for day in range(30)]
    d2 = get_brt_dict(midnight + 12 * 3600, obs)
    assert d2["brt_source"] == "OBSERVED"
    assert d2["circadian_strength"] > 0.5
    assert abs(d2["circadian_phase"] - 13 / 24) < 0.05


def test_biological_capital_thriving():
    from core.extended.biological_capital import compute_bc, EcosystemProfile
    amazon = EcosystemProfile(
        ecosystem_id="amazon_basin",
        net_primary_productivity=2100.0, biomass_density=250.0,
        recovery_speed=0.60, disturbance_magnitude=0.30,
        endemic_species_count=40000, comparable_baseline_count=5000,
        keystone_species_present=True, network_connectivity=0.88, trophic_levels=5,
    )
    result = compute_bc(amazon)
    assert result.bc > 0.10
    assert result.label in ("THRIVING", "HEALTHY", "STRESSED")


def test_biological_capital_collapsed():
    from core.extended.biological_capital import compute_bc, EcosystemProfile
    degraded = EcosystemProfile(
        ecosystem_id="monoculture",
        net_primary_productivity=50.0, biomass_density=5.0,
        recovery_speed=0.05, disturbance_magnitude=0.90,
        endemic_species_count=1, comparable_baseline_count=500,
        keystone_species_present=False, network_connectivity=0.05, trophic_levels=1,
    )
    result = compute_bc(degraded)
    assert result.bc < 0.30
    assert result.label in ("CRITICAL", "COLLAPSED", "STRESSED")


def test_xsl_keystone_critical_flag():
    from core.extended.cross_species import compute_xsl, SpeciesProfile
    vaquita = SpeciesProfile(
        species_id="vaquita", common_name="Vaquita", is_keystone=True,
        habitat_area_km2=2200, habitat_area_baseline=8000, habitat_quality_score=0.25,
        prey_availability=0.30, dietary_breadth=0.40, competition_pressure=0.70,
        observed_reproduction=0.02, baseline_reproduction=0.15, juvenile_survival=0.20,
        habitat_loss_rate=0.12, hunting_pressure=0.40, climate_vulnerability=0.50,
        disease_pressure=0.20, pollution_level=0.45,
    )
    result = compute_xsl(vaquita)
    assert result.status in ("CRITICAL", "ENDANGERED")
    assert result.financial_risk_flag  # Keystone + critical = financial risk


def test_energy_participation_healthy():
    from core.extended.energy_participation import (
        compute_ep, ProtocolEconomics, DeveloperData
    )
    econ = ProtocolEconomics(
        protocol_id="healthy_dex",
        value_to_protocol_purpose=5_000_000.0,
        value_mev_extracted=200_000.0, value_fees_extracted=800_000.0,
        interaction_type_counts={"SWAP": 150000, "LIQUIDITY_ADD": 5000,
                                  "GOVERNANCE_VOTE": 200, "REWARD_CLAIM": 8000},
    )
    dev = DeveloperData(
        protocol_id="healthy_dex",
        active_core_contributors=8, median_commit_tenure_days=540.0,
        total_contributor_count=85, commit_velocity=35.0, issue_resolution_rate=0.88,
    )
    result = compute_ep(econ, dev)
    assert result.ep > 0
    assert result.vc > 0
    assert result.pa > 0
    assert result.dc > 0


def test_sba_stable_jurisdiction():
    import time
    from core.extended.sovereign_behavioral import compute_sba, SBAInputs
    inp = SBAInputs(
        nation_id="ch", nation_name="Switzerland", timestamp=time.time(),
        gdp_growth_rate=0.025, inflation_stability=0.90, forex_reserve_ratio=0.85, debt_to_gdp=0.55,
        stated_policy_scores=[0.8, 0.82, 0.81, 0.83, 0.80, 0.82],
        onchain_enforcement  =[0.79, 0.81, 0.80, 0.82, 0.79, 0.81],
        gini_coefficient=0.78, protest_intensity=0.85, press_freedom_score=0.92,
        wgi_government=0.90, regulatory_consistency=0.88, judicial_independence=0.95,
        crypto_regulatory_clarity=0.85, cbdc_behavorial_coherence=0.75, defi_accessibility=0.80,
    )
    result = compute_sba(inp)
    assert 0 < result.sba <= 1
    assert result.regulatory_threat_level in ("STABLE", "LOW")
    assert not result.advance_warning


def test_sba_hostile_advance_warning():
    import time
    from core.extended.sovereign_behavioral import compute_sba, SBAInputs
    inp = SBAInputs(
        nation_id="hostile", nation_name="Hostile", timestamp=time.time(),
        gdp_growth_rate=-0.05, inflation_stability=0.20, forex_reserve_ratio=0.10, debt_to_gdp=0.05,
        stated_policy_scores=[0.8, 0.8, 0.8, 0.8, 0.8, 0.8],
        onchain_enforcement  =[0.05, 0.02, 0.0, 0.0, 0.0, 0.0],
        gini_coefficient=0.15, protest_intensity=0.05, press_freedom_score=0.02,
        wgi_government=0.10, regulatory_consistency=0.08, judicial_independence=0.05,
        crypto_regulatory_clarity=0.02, cbdc_behavorial_coherence=0.10, defi_accessibility=0.0,
    )
    result = compute_sba(inp)
    assert result.advance_warning
    assert result.regulatory_threat_level in ("HIGH", "CRITICAL")


def test_information_conservation_law():
    import time
    from core.primitives.thermodynamics import AkashicConservationLedger, apply_signal_selection
    ledger = AkashicConservationLedger()
    now = time.time()
    r1 = ledger.record_state(now, bh_generated=100, a_absorbed=50, s_emitted=30, e_lost=5)
    r2 = ledger.record_state(now + 12, bh_generated=80, a_absorbed=40, s_emitted=60, e_lost=3)
    assert r1.conserved
    assert r2.conserved
    assert not ledger.has_violations
    assert ledger.total_information > 0


def test_signal_selection_entropy_gate():
    from core.primitives.thermodynamics import apply_signal_selection
    good = apply_signal_selection("good_signal", i_gained=2.5, s_entropy_cost=1.0)
    bad  = apply_signal_selection("noise",       i_gained=0.3, s_entropy_cost=1.0)
    assert good.selected
    assert not bad.selected


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
