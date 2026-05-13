import sys
sys.path.insert(0, '../src')
from coherence_score import (
    emit_signal, SignalType, compute_c_score, dynamic_threshold,
    WEIGHT_PROFILES, TRIONSignal
)


def test_valuation_signal_emitted_when_above_threshold():
    sig = emit_signal("WETH", phi_adj=0.80, m_adj=0.75, sigma=0.85,
                      conf_genesis=0.70, ci_95=(0.72, 0.91),
                      tc_valid=True, volatility=0.10)
    assert sig.signal_type == SignalType.VALUATION
    assert sig.c_score is not None and sig.c_score > 0
    errors = sig.validate()
    assert not errors, f"Signal validation errors: {errors}"
    print(f"[PASS] VALUATION: C={sig.c_score:.4f}, Theta={sig.theta:.4f}")


def test_silence_emitted_when_below_threshold():
    sig = emit_signal("NEW_TOKEN", phi_adj=0.20, m_adj=0.15, sigma=0.30,
                      conf_genesis=0.05, ci_95=(0.10, 0.40),
                      tc_valid=False, volatility=0.30)
    assert sig.signal_type == SignalType.SILENCE
    assert sig.c_gap is not None and sig.c_gap > 0
    assert sig.limiting_plane is not None
    assert sig.eta_hours is not None
    print(f"[PASS] SILENCE: gap={sig.c_gap:.4f}, limit={sig.limiting_plane}, eta={sig.eta_hours}h")


def test_silence_never_suppressed():
    for phi in [0.0, 0.1, 0.3]:
        sig = emit_signal("TEST", phi_adj=phi, m_adj=0.1, sigma=0.1,
                          conf_genesis=0.0, ci_95=(0.0, 0.2),
                          tc_valid=False, volatility=0.50)
        assert sig is not None, "Signal must never be None"
        assert sig.signal_type == SignalType.SILENCE
    print("[PASS] Silence is never suppressed")


def test_ci_95_always_nonnull():
    for phi in [0.0, 0.5, 0.9]:
        sig = emit_signal("CI_TEST", phi_adj=phi, m_adj=phi, sigma=phi,
                          conf_genesis=phi, ci_95=(phi*0.8, phi*1.1 + 0.01),
                          tc_valid=phi > 0.5)
        assert sig.ci_95 is not None
        assert len(sig.ci_95) == 2
    print("[PASS] CI_95 always non-null across all signal types")


def test_plane_breakdown_shows_zeros_for_inactive():
    sig = emit_signal("TEST_PLANES", phi_adj=0.75, m_adj=0.70, sigma=0.80,
                      conf_genesis=0.60, ci_95=(0.65, 0.88), tc_valid=True)
    assert sig.k_score == 0.0, "K must be 0.0 until Phase 8"
    assert sig.a_score == 0.0, "A must be 0.0 until Phase 7 full"
    print("[PASS] Inactive planes show 0.0 (not fake data)")


def test_all_6_asset_type_profiles():
    for asset_type in ["NEW_TOKEN", "MATURE_PROTOCOL", "STABLECOIN",
                       "GOVERNANCE_TOKEN", "BRIDGE_ASSET", "WRAPPED_ASSET"]:
        c, w = compute_c_score(0.75, 0.70, 0.80, asset_type=asset_type)
        assert 0 <= c <= 1, f"{asset_type}: C out of range: {c}"
        total_w = w["alpha"] + w["beta"] + w["gamma"] + w["delta"] + w["epsilon"]
        assert abs(total_w - 1.0) < 1e-6, f"{asset_type}: weights don't sum to 1: {total_w}"
    print("[PASS] All 6 asset type profiles produce valid C(t)")


def test_dynamic_threshold_increases_with_volatility():
    thetas = [dynamic_threshold(v) for v in [0.0, 0.25, 0.5, 0.75, 1.0]]
    assert thetas == sorted(thetas), f"Theta must be monotone with V: {thetas}"
    assert thetas[0] == 0.55, f"Theta_min must be 0.55, got {thetas[0]}"
    assert thetas[-1] == 0.92, f"Theta_max must be 0.92, got {thetas[-1]}"
    print(f"[PASS] Dynamic threshold: {[round(t,2) for t in thetas]}")


def test_all_19_signal_types_defined():
    all_types = [t.value for t in SignalType]
    assert len(all_types) == 19, f"Must have 19 signal types, got {len(all_types)}"
    print(f"[PASS] All 19 signal types defined: {all_types[:5]}...")


if __name__ == "__main__":
    test_valuation_signal_emitted_when_above_threshold()
    test_silence_emitted_when_below_threshold()
    test_silence_never_suppressed()
    test_ci_95_always_nonnull()
    test_plane_breakdown_shows_zeros_for_inactive()
    test_all_6_asset_type_profiles()
    test_dynamic_threshold_increases_with_volatility()
    test_all_19_signal_types_defined()
    print("\n[PHASE 6] ALL TESTS PASSED")
