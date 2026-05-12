import sys
sys.path.insert(0, '../../src')
from adapters.biological_capital import compute_bc, EcosystemMetrics, BiologicalRhythmTimer
from adapters.natural_liquidity import compute_nl
from adapters.energy_participation import compute_ep
from anima_v1 import AnimaV1, ManifestationGapMonitor


def test_bc_multiplicative_structure():
    metrics = EcosystemMetrics("test", flow=0.0, resilience=0.8,
                               uniqueness=0.9, interdependence=0.7)
    result = compute_bc(metrics)
    assert result["bc_score"] == 0.0, "Zero flow must collapse BC"
    print(f"[PASS] BC multiplicative: zero flow -> BC=0")


def test_nl_warning_at_low_score():
    result = compute_nl(ld=0.20, lo=0.30, lc=0.90, ls=0.80)
    assert result["emit_liquidity_health_signal"], "Low NL must trigger warning"
    print(f"[PASS] NL warning: score={result['nl_score']:.4f}")


def test_biological_rhythm_phases_in_range():
    timer  = BiologicalRhythmTimer()
    phases = timer.current_phase(unix_timestamp=1_700_000_000.0)
    for name, phase in phases.items():
        assert 0 <= phase <= 1, f"{name} phase out of range: {phase}"
    print(f"[PASS] Biological rhythms: {phases}")


def test_manifestation_gap_calibrates():
    mg = ManifestationGapMonitor("test_asset")
    for _ in range(40):
        mg.record(predicted=0.80, observed=0.65)
    assert mg.rolling_mean > 0, "Systematic over-prediction must produce positive MG"
    raw       = 0.80
    corrected = mg.adjusted_prediction(raw)
    assert corrected < raw, "MG correction must reduce over-predictions"
    print(f"[PASS] MG calibration: raw={raw}, corrected={corrected:.4f}")


def test_anima_v1_not_stub():
    anima  = AnimaV1("test_asset")
    result = anima.compute({"s1": 0.70, "s2": 0.65, "s3": 0.72})
    assert not result.is_stub, "ANIMA v1 must not be a stub"
    assert result.ci_95 is not None
    assert result.ci_95[0] < result.ci_95[1], "CI_95 must be ordered"
    print(f"[PASS] ANIMA v1: A={result.a_score:.4f}, is_stub=False")


def test_ep_feeds_phi():
    result = compute_ep(vc=0.60, pa=0.70, dc=0.65)
    assert 0 <= result["ep_score"] <= 1
    assert "Phase 9" in result["note"]
    print(f"[PASS] EP score={result['ep_score']:.4f}")


if __name__ == "__main__":
    test_bc_multiplicative_structure()
    test_nl_warning_at_low_score()
    test_biological_rhythm_phases_in_range()
    test_manifestation_gap_calibrates()
    test_anima_v1_not_stub()
    test_ep_feeds_phi()
    print("\n[PHASE 7] ANIMA v1 tests passed")
