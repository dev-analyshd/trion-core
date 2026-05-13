import sys
sys.path.insert(0, '../src')
from spiritual.consensus import (
    Validator, compute_sigma, compute_hhi, hhi_status, dynamic_window,
    apply_slash, SlashingType, HHIStatus
)
from spiritual.living_security import (
    GenomicKey, ImmuneSystem, EpigeneticLayer, EpigeneticState,
    CRISPRDefense, CRISPRAttackType, INITCeremony
)


def make_validators(n=10, stake=10000.0):
    return [Validator(
        validator_id=f"V{i}", stake=stake,
        diversity=0.80, history=0.90
    ) for i in range(n)]


def make_votes(validators, value=0.75):
    return {v.validator_id: value for v in validators}


def test_bft_safe_below_one_third_byzantine():
    vals  = make_validators(10)
    votes = make_votes(vals)
    result = compute_sigma(vals, votes)
    assert result.bft_safe, "0 Byzantine must be BFT safe"
    assert abs(result.sigma - 0.75) < 0.001
    print(f"[PASS] BFT safe: sigma={result.sigma:.4f}")


def test_bft_unsafe_at_one_third_slashed():
    vals  = make_validators(9)
    votes = make_votes(vals)
    for v in vals[:3]:
        v.is_slashed = True  # 3/9 = 1/3 Byzantine
    result = compute_sigma(vals, votes)
    assert not result.bft_safe, "1/3 Byzantine must be BFT UNSAFE"
    print(f"[PASS] BFT unsafe at 1/3 Byzantine: byz_frac={result.byzantine_weight_fraction:.3f}")


def test_excluded_not_slashed_still_counted():
    vals  = make_validators(10)
    vals[0].is_excluded = True  # excluded, NOT slashed
    votes = make_votes(vals)
    result = compute_sigma(vals, votes)
    assert result.bft_safe, "Excluded validator must not count as Byzantine"
    assert result.participant_count == 9
    print(f"[PASS] Excluded != Slashed: participants={result.participant_count}")


def test_hhi_healthy_with_equal_stakes():
    vals   = make_validators(20)
    hhi    = compute_hhi(vals)
    status = hhi_status(hhi)
    assert status == HHIStatus.HEALTHY, f"Equal stakes must be HEALTHY, got {status}"
    print(f"[PASS] HHI HEALTHY: {hhi:.0f}")


def test_hhi_critical_with_concentrated_stake():
    vals    = make_validators(10, stake=100.0)
    vals[0] = Validator("V0", stake=10000.0, diversity=0.8, history=0.9)
    hhi     = compute_hhi(vals)
    status  = hhi_status(hhi)
    assert status in [HHIStatus.DANGER, HHIStatus.CRITICAL]
    print(f"[PASS] HHI {status.value}: {hhi:.0f}")


def test_dynamic_window_decreases_with_volatility():
    w_low  = dynamic_window(0.0)
    w_high = dynamic_window(1.0)
    assert w_high < w_low, "Higher volatility must give smaller consensus window"
    assert w_low  == 21, f"Max window must be 21, got {w_low}"
    assert w_high == 3,  f"Min window must be 3, got {w_high}"
    print(f"[PASS] Dynamic window: V=0→{w_low}, V=1→{w_high}")


def test_slashing_reduces_stake():
    v = Validator("V_slash", stake=10000.0, diversity=0.8, history=0.9)
    amount = apply_slash(v, SlashingType.DOUBLE_SIGN)
    assert abs(amount - 1000.0) < 0.01, f"DOUBLE_SIGN must slash 10%, got {amount}"
    assert v.is_slashed
    assert v.stake < 10000.0
    print(f"[PASS] Slash DOUBLE_SIGN: amount={amount:.2f}, remaining={v.stake:.2f}")


def test_all_slash_types():
    rates = {
        SlashingType.DOUBLE_SIGN:        0.10,
        SlashingType.SUSTAINED_DOWNTIME: 0.02,
        SlashingType.MANIPULATION:       0.25,
        SlashingType.SYBIL_COLLUSION:    0.15,
        SlashingType.GOVERNANCE_CAPTURE: 0.20,
    }
    for slash_type, expected_rate in rates.items():
        v = Validator(f"V_{slash_type.value}", stake=10000.0, diversity=0.8, history=0.9)
        amount = apply_slash(v, slash_type)
        expected = 10000.0 * expected_rate
        assert abs(amount - expected) < 0.01, f"{slash_type}: expected {expected}, got {amount}"
    print("[PASS] All 5 slash types with correct rates")


def test_genomic_key_evolution():
    gk0 = GenomicKey(generation=0, key_bytes=b'\x00' * 32)
    gk1 = gk0.evolve(b'entropy1', b'threat1', b'cv0001')
    assert gk1.generation == 1
    assert gk1.key_bytes != gk0.key_bytes
    assert len(gk1.key_bytes) == 32
    print(f"[PASS] GK evolution: gen={gk1.generation}, key changes")


def test_kolmogorov_bound_decreases():
    gk = GenomicKey(generation=0, key_bytes=b'\x00' * 32)
    bounds = []
    for gen in [0, 100, 1000, 10000, 50000]:
        gk_i = GenomicKey(generation=gen, key_bytes=b'\x00' * 32)
        bounds.append(gk_i.kolmogorov_bound())
    assert bounds == sorted(bounds, reverse=True), "P(break) must decrease with generation"
    print(f"[PASS] Kolmogorov bound monotone: {[f'{b:.4f}' for b in bounds]}")


def test_immune_system_memory_permanent():
    immune = ImmuneSystem()
    event  = {"type": "flash_loan", "value": 1000000}
    immune.register_attack(event, "ATTACK_001")
    assert immune.memory_check("ATTACK_001"), "Memory must be permanent once registered"
    assert not immune.memory_check("ATTACK_002"), "Unseen threat not in memory"
    print("[PASS] Immune system memory permanent")


def test_immune_cascade_innate_adaptive_memory():
    immune = ImmuneSystem()
    event  = {"type": "oracle_manipulation", "magnitude": 0.6}
    immune.register_attack(event, "ORACLE_ATK_001")

    result = immune.respond(event, "ORACLE_ATK_001")
    assert result["neutralized"], "Known attack must be neutralized"
    assert result["memory"], "Known threat must hit memory"
    print(f"[PASS] Immune cascade: {result}")


def test_epigenetic_transitions():
    epi = EpigeneticLayer()

    state = epi.update(threat_level=0.10, validator_health=0.90, network_entropy=0.80)
    assert state == EpigeneticState.NORMAL

    state = epi.update(threat_level=0.50, validator_health=0.70, network_entropy=0.60)
    assert state in [EpigeneticState.ELEVATED, EpigeneticState.DEFENSIVE]

    for _ in range(8):
        state = epi.update(threat_level=0.90, validator_health=0.20, network_entropy=0.30)
    assert state == EpigeneticState.LOCKDOWN
    print("[PASS] Epigenetic transitions: NORMAL → ELEVATED/DEFENSIVE → LOCKDOWN")


def test_crispr_detects_known_attacks():
    crispr = CRISPRDefense()

    harvest_event = {"oracle_deviation": 0.50, "flash_loan": True}
    result = crispr.detect(harvest_event)
    assert result == CRISPRAttackType.HARVEST_FINANCE, f"Expected HARVEST_FINANCE, got {result}"

    beanstalk_event = {"gov_flash_loan": True, "proposal_age_hours": 0}
    result2 = crispr.detect(beanstalk_event)
    assert result2 == CRISPRAttackType.BEANSTALK

    print("[PASS] CRISPR detects HARVEST_FINANCE and BEANSTALK")


def test_init_ceremony_all_conditions():
    init = INITCeremony()
    status = init.status()
    assert not status["init_valid"], "INIT must not be valid before conditions met"
    assert status["conditions_met"] == 0

    init.min_validators_recruited = True
    init.diversity_threshold_met  = True
    init.security_audit_complete  = True
    init.hhi_below_danger         = True
    init.genomic_key_initialized  = True
    init.immune_system_armed      = True
    init.falsifiability_seeded    = True
    init.awa_conditions_met       = True

    status = init.status()
    assert status["init_valid"], "INIT must be valid when all 8 conditions met"
    assert status["conditions_met"] == 8
    print(f"[PASS] INIT Ceremony: {status['conditions_met']}/8 conditions → init_valid=True")


if __name__ == "__main__":
    test_bft_safe_below_one_third_byzantine()
    test_bft_unsafe_at_one_third_slashed()
    test_excluded_not_slashed_still_counted()
    test_hhi_healthy_with_equal_stakes()
    test_hhi_critical_with_concentrated_stake()
    test_dynamic_window_decreases_with_volatility()
    test_slashing_reduces_stake()
    test_all_slash_types()
    test_genomic_key_evolution()
    test_kolmogorov_bound_decreases()
    test_immune_system_memory_permanent()
    test_immune_cascade_innate_adaptive_memory()
    test_epigenetic_transitions()
    test_crispr_detects_known_attacks()
    test_init_ceremony_all_conditions()
    print("\n[PHASE 5] ALL TESTS PASSED")
