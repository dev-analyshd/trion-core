import sys
sys.path.insert(0, '../src')
from conscious.conscious_score import ConsciousScoreState, Annotation, K_MIN_ANNOTATORS
from conscious.sba import compute_sba, SBA_WEIGHTS


def test_k_blocks_without_enough_annotators():
    state = ConsciousScoreState("test_asset")
    for i in range(50):
        state.add_annotation(Annotation(
            f"annotator_{i}", "test_asset", 0.75,
            "US", "western", 0.80, 10.0,
        ))
    result = state.compute_k()
    assert not result["ready"], "K must block with < 100 annotators"
    print(f"[PASS] K blocked at {result['annotators']} annotators (need {K_MIN_ANNOTATORS})")


def test_k_computes_with_sufficient_annotators():
    state = ConsciousScoreState("test_asset_full")
    countries = ["US","GB","DE","FR","JP","CN","IN","BR","ZA","NG",
                 "EG","MX","ID","AU","CA","KR","TR","SA","AR","SE"]
    for i in range(100):
        state.add_annotation(Annotation(
            f"ann_{i}", "test_asset_full", 0.70 + (i % 10) * 0.02,
            countries[i % 20], "western" if i % 5 != 0 else f"indigenous_{i%3}",
            0.80, 10.0,
        ))
    result = state.compute_k()
    assert result["ready"], f"K must be ready with 100 annotators: {result}"
    assert 0 <= result["k_score"] <= 1
    print(f"[PASS] K computed: score={result['k_score']:.4f}, "
          f"countries={result['country_count']}, indigenous={result['indigenous_systems']}")


def test_sba_all_fields_present():
    sig = compute_sba("US", economic=0.72, institutional=0.80,
                      social=0.75, governance=0.70, cross_chain=0.65)
    assert sig.ci_95 is not None
    assert sig.ci_95[0] < sig.ci_95[1]
    assert sig.uncertainty_bounds_displayed
    assert sig.appeal_mechanism_url.startswith("https://")
    assert len(sig.data_sources) == 5
    assert sig.cultural_context_vector
    print(f"[PASS] SBA Sovereignty Dignity Protocol: score={sig.sba_score:.4f}")


def test_sba_weights_sum_to_one():
    total = sum(SBA_WEIGHTS.values())
    assert abs(total - 1.0) < 1e-6, f"SBA weights must sum to 1.0, got {total}"
    print(f"[PASS] SBA weights sum to {total}")


def test_sba_score_in_range():
    sig = compute_sba("TEST", economic=0.50, institutional=0.50,
                      social=0.50, governance=0.50, cross_chain=0.50)
    assert abs(sig.sba_score - 0.50) < 0.001
    print(f"[PASS] SBA score in range: {sig.sba_score}")


if __name__ == "__main__":
    test_k_blocks_without_enough_annotators()
    test_k_computes_with_sufficient_annotators()
    test_sba_all_fields_present()
    test_sba_weights_sum_to_one()
    test_sba_score_in_range()
    print("\n[PHASE 8] Conscious Layer tests passed")
