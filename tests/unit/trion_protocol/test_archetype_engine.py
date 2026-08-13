"""
Tests for src/akashic/archetypes.py — TRION L2 Akashic Archetypes.
Actual module imported by api/app.py at line 815.
match_archetype() returns a dict (not BehavioralArchetype object).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.akashic.archetypes import (
    BehavioralArchetype, ARCHETYPES, match_archetype, get_all_archetypes_summary,
)


def test_archetypes_loaded():
    assert len(ARCHETYPES) >= 10, f"Expected >= 10 archetypes, got {len(ARCHETYPES)}"
    print(f"[PASS] {len(ARCHETYPES)} archetypes loaded")


def test_all_archetypes_have_required_fields():
    required = ["id", "name", "phi_vector", "mental_score", "sigma_score",
                "karma_score", "anima_score", "risk_level", "investment_signal"]
    for arch in ARCHETYPES:
        for f in required:
            assert hasattr(arch, f), f"Archetype {arch.id} missing field: {f}"
    print(f"[PASS] All archetypes have {len(required)} required fields")


def test_phi_vectors_are_9dim():
    for arch in ARCHETYPES:
        assert len(arch.phi_vector) == 9, \
            f"{arch.id} phi_vector is {len(arch.phi_vector)}-dim, expected 9"
    print(f"[PASS] All phi_vectors are 9-dimensional")


def test_all_plane_scores_in_unit_interval():
    for arch in ARCHETYPES:
        for attr in ["mental_score", "sigma_score", "karma_score", "anima_score"]:
            v = getattr(arch, attr)
            assert 0.0 <= v <= 1.0, f"{arch.id}.{attr}={v} out of [0,1]"
    print(f"[PASS] All plane scores in [0,1]")


def test_risk_levels_are_valid():
    valid = {"SAFE", "CAUTION", "DANGER", "CRITICAL"}
    for arch in ARCHETYPES:
        assert arch.risk_level in valid, \
            f"{arch.id} risk_level={arch.risk_level} not in {valid}"
    print(f"[PASS] All risk_levels valid")


def test_investment_signals_are_valid():
    valid = {"BUY", "WATCH", "AVOID", "SHORT"}
    for arch in ARCHETYPES:
        assert arch.investment_signal in valid, \
            f"{arch.id} investment_signal={arch.investment_signal} not in {valid}"
    print(f"[PASS] All investment_signals valid")


def test_match_archetype_returns_dict_with_keys():
    phi_vec = [0.32, 0.28, 0.38, 0.30, 0.22, 0.18, 0.34, 0.29, 0.35]
    result = match_archetype(phi_vec)
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    required = ["archetype_id", "archetype_name", "risk_level", "investment_signal"]
    for k in required:
        assert k in result, f"Missing key: {k}"
    print(f"[PASS] match_archetype → {result['archetype_id']}: {result['archetype_name']}")


def test_match_archetype_exploit_phi_yields_critical():
    exploit_phi = [0.96, 0.92, 0.88, 0.94, 0.04, 0.03, 0.94, 0.90, 0.96]
    result = match_archetype(exploit_phi)
    assert result["risk_level"] in ("DANGER", "CRITICAL"), \
        f"Exploit phi should match DANGER/CRITICAL, got {result['risk_level']}"
    print(f"[PASS] Exploit phi → {result['archetype_id']} ({result['risk_level']})")


def test_get_all_archetypes_summary_structure():
    summary = get_all_archetypes_summary()
    assert isinstance(summary, list)
    assert len(summary) == len(ARCHETYPES)
    for item in summary:
        assert "id" in item, f"Summary entry missing 'id': {item}"
    print(f"[PASS] get_all_archetypes_summary: {len(summary)} entries with 'id'")


if __name__ == "__main__":
    test_archetypes_loaded()
    test_all_archetypes_have_required_fields()
    test_phi_vectors_are_9dim()
    test_all_plane_scores_in_unit_interval()
    test_risk_levels_are_valid()
    test_investment_signals_are_valid()
    test_match_archetype_returns_dict_with_keys()
    test_match_archetype_exploit_phi_yields_critical()
    test_get_all_archetypes_summary_structure()
    print("\n[PASS] All archetypes (L2 Akashic) tests passed")
