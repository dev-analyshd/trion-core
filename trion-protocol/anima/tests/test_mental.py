import sys
sys.path.insert(0, '../src')
from mental.mental_score import (
    compute_mental_score, ConformalPredictor, compute_observer_effect,
    InformationMarketProtocol
)
from mental.source_credibility import CredibilityRegistry, CredibilityEvent
from mental.anima_stub import AnimaStub, HA_FLAG_THRESHOLD, HA_DISABLE_THRESHOLD


def test_m_score_in_unit_interval():
    result = compute_mental_score(phi_adj=0.75)
    assert 0.0 <= result.m_adj <= 1.0, f"M(t) must be in [0,1], got {result.m_adj}"
    assert 0.0 <= result.m_raw <= 1.0
    assert result.ci_95[0] < result.ci_95[1], "CI_95 must be ordered"
    print(f"[PASS] M(t)={result.m_adj:.4f}, CI=[{result.ci_95[0]:.3f},{result.ci_95[1]:.3f}]")


def test_observer_effect_dampens_m():
    no_oe  = compute_mental_score(phi_adj=0.75, signal_impact=0.0)
    with_oe = compute_mental_score(phi_adj=0.75, signal_impact=1.0)
    assert with_oe.m_adj <= no_oe.m_adj, "OE must dampen M(t)"
    assert with_oe.oe_factor > 0.0, "OE factor must be positive when signal impacts market"
    print(f"[PASS] OE dampening: no_oe={no_oe.m_adj:.4f}, with_oe={with_oe.m_adj:.4f}")


def test_observer_effect_zero_when_no_impact():
    oe = compute_observer_effect(signal_impact=0.0, history_count=0)
    assert oe == 0.0, "OE must be 0 when signal_impact=0"
    print("[PASS] OE=0 when no signal impact")


def test_conformal_predictor_ci_always_ordered():
    predictor = ConformalPredictor()
    for v in [0.0, 0.1, 0.5, 0.9, 1.0]:
        ci = predictor.predict_interval(v)
        assert ci[0] < ci[1], f"CI_95 not ordered at v={v}: {ci}"
        assert 0.0 <= ci[0] <= 1.0
        assert 0.0 <= ci[1] <= 1.0
    print("[PASS] CI_95 always ordered and in [0,1]")


def test_conformal_predictor_calibrates():
    predictor = ConformalPredictor()
    for i in range(20):
        predictor.calibrate(0.05)  # small residuals
    ci_tight = predictor.predict_interval(0.70)

    predictor2 = ConformalPredictor()
    for i in range(20):
        predictor2.calibrate(0.40)  # large residuals
    ci_wide = predictor2.predict_interval(0.70)

    width_tight = ci_tight[1] - ci_tight[0]
    width_wide  = ci_wide[1]  - ci_wide[0]
    assert width_tight < width_wide, "Tight residuals must give narrower CI"
    print(f"[PASS] Conformal calibration: tight={width_tight:.3f} < wide={width_wide:.3f}")


def test_source_credibility_updates():
    registry = CredibilityRegistry()
    registry.register("src_A", 0.70)

    for _ in range(10):
        registry.update(CredibilityEvent("src_A", 0.75, 0.75, 0.0, 1.0))

    cred = registry.get_cred("src_A")
    assert cred > 0.50, f"High accuracy source must have cred > 0.50, got {cred}"
    print(f"[PASS] Source credibility updated: CRED={cred:.4f}")


def test_cross_source_agreement_high_when_consistent():
    registry = CredibilityRegistry()
    for src in ["A", "B", "C"]:
        registry.register(src)
    ca = registry.cross_source_agreement({"A": 0.72, "B": 0.74, "C": 0.70})
    assert ca > 0.80, f"Consistent sources must have high CA, got {ca}"
    print(f"[PASS] Cross-source agreement (consistent): CA={ca:.4f}")


def test_cross_source_agreement_low_when_divergent():
    registry = CredibilityRegistry()
    for src in ["A", "B", "C"]:
        registry.register(src)
    ca = registry.cross_source_agreement({"A": 0.10, "B": 0.90, "C": 0.50})
    assert ca < 0.70, f"Divergent sources must have low CA, got {ca}"
    print(f"[PASS] Cross-source agreement (divergent): CA={ca:.4f}")


def test_anima_stub_not_none():
    stub = AnimaStub()
    out  = stub.compute(phi_adj=0.75)
    assert out is not None
    assert out.is_stub == True
    assert out.ci_95 is not None
    assert out.ci_95[0] < out.ci_95[1]
    assert 0.0 <= out.a_score <= 1.0
    print(f"[PASS] ANIMA stub: A={out.a_score:.4f}, CI=[{out.ci_95[0]:.3f},{out.ci_95[1]:.3f}]")


def test_im_protocol_weight():
    im = InformationMarketProtocol()
    im.submit_market_score(0.80)
    im.submit_market_score(0.75)
    weight = im.compute_weight()
    assert 0.70 < weight < 0.90
    print(f"[PASS] IM Protocol weight: {weight:.4f}")


if __name__ == "__main__":
    test_m_score_in_unit_interval()
    test_observer_effect_dampens_m()
    test_observer_effect_zero_when_no_impact()
    test_conformal_predictor_ci_always_ordered()
    test_conformal_predictor_calibrates()
    test_source_credibility_updates()
    test_cross_source_agreement_high_when_consistent()
    test_cross_source_agreement_low_when_divergent()
    test_anima_stub_not_none()
    test_im_protocol_weight()
    print("\n[PHASE 4] ALL TESTS PASSED")
