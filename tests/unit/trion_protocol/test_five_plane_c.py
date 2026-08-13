"""
Tests for src/core/coherence_engine.py — TRION L5 C(t) master equation.
Actual module imported by api/app.py at line 262.
Return keys: C, theta, emits, limiting_plane, trend, plane_breakdown, moat_factor, weights...
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.core.coherence_engine import (
    CoherenceEngine, CoherenceInput, AssetProfile,
    WEIGHT_PROFILES, THETA_MIN, THETA_MAX,
)


def _inp(phi=0.75, m=0.70, sig=0.80, k=0.60, a=0.65,
         vol=0.10, depth=500.0, moat=365.0,
         profile=AssetProfile.MATURE) -> CoherenceInput:
    return CoherenceInput(
        phi_adj=phi, m_adj=m, sigma=sig, k_plane=k, anima=a,
        volatility=vol, akashic_depth=depth, moat_time=moat, profile=profile,
    )


def test_weight_profiles_all_sum_to_one():
    for profile, w in WEIGHT_PROFILES.items():
        total = sum(w.values())
        assert abs(total - 1.0) < 1e-9, f"{profile} weights sum to {total}"
    print(f"[PASS] All {len(WEIGHT_PROFILES)} weight profiles sum to 1.0")


def test_c_score_in_unit_interval():
    engine = CoherenceEngine()
    for profile in AssetProfile:
        result = engine.compute_coherence(_inp(profile=profile))
        c = result["C"]
        assert 0.0 <= c <= 1.0, f"C(t) out of range for {profile}: {c}"
    print(f"[PASS] C(t) in [0,1] across all {len(list(AssetProfile))} profiles")


def test_dynamic_threshold_range():
    engine = CoherenceEngine()
    lo = engine.compute_threshold(0.0)
    hi = engine.compute_threshold(1.0)
    assert abs(lo - THETA_MIN) < 1e-9
    assert abs(hi - THETA_MAX) < 1e-9
    print(f"[PASS] Θ(t): V=0→{lo}, V=1→{hi}")


def test_silence_when_all_planes_low():
    engine = CoherenceEngine()
    result = engine.compute_coherence(_inp(phi=0.1, m=0.1, sig=0.1, k=0.0, a=0.0, vol=0.5))
    assert not result["emits"], f"Low planes must produce SILENCE"
    assert result["C"] < result["theta"]
    print(f"[PASS] Low planes → SILENCE (C={result['C']:.3f}, θ={result['theta']:.3f})")


def test_valuation_when_planes_high():
    engine = CoherenceEngine()
    result = engine.compute_coherence(_inp(phi=0.95, m=0.90, sig=0.85, k=0.80, a=0.85, vol=0.0))
    assert result["emits"], f"High planes must produce signal"
    print(f"[PASS] High planes → signal (C={result['C']:.3f})")


def test_limiting_plane_is_weakest_weighted():
    engine = CoherenceEngine()
    result = engine.compute_coherence(_inp(phi=0.90, m=0.90, sig=0.90, k=0.10, a=0.90))
    assert result["limiting_plane"] == "conscious", \
        f"K=0.1 must be limiting plane, got {result['limiting_plane']}"
    print(f"[PASS] Limiting plane = {result['limiting_plane']} (K=0.10)")


def test_trend_computed_after_history():
    engine = CoherenceEngine()
    result = None
    for val in [0.60, 0.62, 0.64, 0.66, 0.68]:
        result = engine.compute_coherence(_inp(phi=val, m=val, sig=val, k=val, a=val))
    assert result["trend"] in ("RISING", "STABLE", "FALLING")
    print(f"[PASS] Trend computed from rolling history: {result['trend']}")


def test_result_has_required_keys():
    engine = CoherenceEngine()
    result = engine.compute_coherence(_inp())
    required = ["C", "theta", "emits", "limiting_plane", "trend", "plane_breakdown", "moat_factor"]
    for k in required:
        assert k in result, f"Missing key: {k}"
    print(f"[PASS] compute_coherence result has all {len(required)} required keys")


def test_moat_factor_in_unit_interval():
    engine = CoherenceEngine()
    result = engine.compute_coherence(_inp())
    mf = result["moat_factor"]
    assert 0.0 <= mf <= 1.0, f"moat_factor={mf} out of [0,1]"
    print(f"[PASS] moat_factor in [0,1]: {mf:.4f}")


if __name__ == "__main__":
    test_weight_profiles_all_sum_to_one()
    test_c_score_in_unit_interval()
    test_dynamic_threshold_range()
    test_silence_when_all_planes_low()
    test_valuation_when_planes_high()
    test_limiting_plane_is_weakest_weighted()
    test_trend_computed_after_history()
    test_result_has_required_keys()
    test_moat_factor_in_unit_interval()
    print("\n[PASS] All coherence_engine (L5 C(t)) tests passed")
