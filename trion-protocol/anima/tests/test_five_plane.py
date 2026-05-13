import sys
sys.path.insert(0, '../src')
from five_plane_c import compute_five_plane_c, information_conservation_check


def test_all_6_profiles_five_plane():
    for asset_type in ["NEW_TOKEN", "MATURE_PROTOCOL", "STABLECOIN",
                       "GOVERNANCE_TOKEN", "BRIDGE_ASSET", "WRAPPED_ASSET"]:
        result = compute_five_plane_c(0.75, 0.70, 0.80, 0.65, 0.72, asset_type=asset_type)
        assert 0 <= result.c_score <= 1, f"{asset_type}: C out of range"
        assert abs(sum(result.weights_used.values()) - 1.0) < 1e-6
    print("[PASS] All 6 asset-type profiles valid in five-plane C(t)")


def test_emergence_c_above_max_plane():
    result = compute_five_plane_c(0.70, 0.72, 0.68, 0.71, 0.73)
    print(f"[INFO] C={result.c_score:.4f}, max_plane={result.max_single_plane:.4f}, "
          f"emergence={result.emergence_detected}")
    assert 0 <= result.c_score <= 1


def test_information_conservation():
    result = information_conservation_check(
        bh_generated=100.0, a_absorbed=50.0,
        s_emitted=30.0, e_lost=10.0, prev_i_trion=1000.0
    )
    assert result["conserved"], "Information conservation must hold"
    assert result["i_trion"] > 1000.0

    bad = information_conservation_check(
        bh_generated=5.0, a_absorbed=0.0,
        s_emitted=100.0, e_lost=50.0, prev_i_trion=1000.0
    )
    assert bad["violation"], "Excess emission must trigger conservation violation"
    print("[PASS] Information conservation law enforced")


def test_five_plane_output_in_range():
    for phi in [0.0, 0.5, 1.0]:
        result = compute_five_plane_c(phi, phi, phi, phi, phi)
        assert 0 <= result.c_score <= 1
    print("[PASS] Five-plane C(t) always in [0,1]")


if __name__ == "__main__":
    test_all_6_profiles_five_plane()
    test_emergence_c_above_max_plane()
    test_information_conservation()
    test_five_plane_output_in_range()
    print("\n[PHASE 9] Five-Plane Full tests passed")
