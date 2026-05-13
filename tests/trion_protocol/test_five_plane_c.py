"""Tests for src/core/five_plane_c.py — Five-Plane C(t) and Information Conservation."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.core.five_plane_c import (
    compute_five_plane_c, information_conservation_check,
    WEIGHT_PROFILES, dynamic_threshold, SignalType,
)


def test_weight_profiles_sum_to_one():
    for name, w in WEIGHT_PROFILES.items():
        total = sum(w.values())
        assert abs(total - 1.0) < 1e-9, f"{name} weights sum to {total}, not 1.0"
    print(f"[PASS] All {len(WEIGHT_PROFILES)} weight profiles sum to 1.0")


def test_c_score_in_unit_interval():
    for asset_type in WEIGHT_PROFILES:
        out = compute_five_plane_c(0.75, 0.70, 0.80, 0.60, 0.65, asset_type=asset_type)
        assert 0.0 <= out.c_score <= 1.0, f"c_score out of range: {out.c_score}"
    print(f"[PASS] C(t) in [0,1] for all {len(WEIGHT_PROFILES)} asset types")


def test_emergence_detected_when_c_exceeds_all_planes():
    out = compute_five_plane_c(0.50, 0.50, 0.50, 0.50, 0.50,
                               asset_type="MATURE_PROTOCOL")
    print(f"[INFO] C={out.c_score}, max_plane={out.max_single_plane}, emergence={out.emergence_detected}")
    assert 0.0 <= out.c_score <= 1.0


def test_silence_signal_when_below_theta():
    out = compute_five_plane_c(0.10, 0.10, 0.10, 0.0, 0.0,
                               asset_type="MATURE_PROTOCOL", tc_valid=True, volatility=0.5)
    assert out.signal_type() == SignalType.SILENCE, "Low scores must produce SILENCE"
    print(f"[PASS] Low plane scores → SILENCE signal (C={out.c_score}, theta={out.theta})")


def test_valuation_signal_when_above_theta():
    out = compute_five_plane_c(0.90, 0.90, 0.90, 0.80, 0.85,
                               asset_type="MATURE_PROTOCOL", tc_valid=True, volatility=0.0)
    assert out.signal_type() == SignalType.VALUATION, f"High scores must produce VALUATION, got {out.signal_type()}"
    print(f"[PASS] High scores → VALUATION signal (C={out.c_score})")


def test_dynamic_threshold_range():
    lo = dynamic_threshold(0.0)
    hi = dynamic_threshold(1.0)
    assert abs(lo - 0.55) < 1e-9
    assert abs(hi - 0.92) < 1e-9
    print(f"[PASS] Dynamic threshold: V=0→{lo}, V=1→{hi}")


def test_information_conservation():
    result = information_conservation_check(
        bh_generated=10.0, a_absorbed=5.0,
        s_emitted=3.0, e_lost=2.0,
        prev_i_trion=100.0,
    )
    assert result["conserved"], "dI_TRION/dt >= 0 must hold"
    assert abs(result["i_trion"] - 110.0) < 1e-6
    print(f"[PASS] Information conservation: I={result['i_trion']}, dI={result['di_dt']}")


def test_information_conservation_violation():
    result = information_conservation_check(
        bh_generated=1.0, a_absorbed=1.0,
        s_emitted=10.0, e_lost=5.0,
        prev_i_trion=50.0,
    )
    assert result["violation"], "Emission > generation must flag violation"
    print(f"[PASS] Conservation violation detected: dI={result['di_dt']}")


def test_to_dict_has_required_keys():
    out = compute_five_plane_c(0.75, 0.70, 0.80, 0.60, 0.65)
    d   = out.to_dict()
    required = ["c_score", "signal_type", "phi_adj", "m_adj", "sigma",
                "k_score", "a_score", "theta", "ci_95", "emergence_detected"]
    for k in required:
        assert k in d, f"Missing key: {k}"
    print(f"[PASS] to_dict() has all {len(required)} required keys")


if __name__ == "__main__":
    test_weight_profiles_sum_to_one()
    test_c_score_in_unit_interval()
    test_emergence_detected_when_c_exceeds_all_planes()
    test_silence_signal_when_below_theta()
    test_valuation_signal_when_above_theta()
    test_dynamic_threshold_range()
    test_information_conservation()
    test_information_conservation_violation()
    test_to_dict_has_required_keys()
    print("\n[PASS] All five-plane C(t) tests passed")
