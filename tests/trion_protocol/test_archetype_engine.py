"""Tests for src/core/archetype_engine.py — Akashic Archetype Engine."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import math
import numpy as np
from src.core.archetype_engine import ArchetypeLibrary, EMBEDDING_DIM


def _healthy_features():
    return {"f1": 0.80, "f2": 0.90, "f3": 0.85, "f4": 0.70, "f5": 0.75,
            "f6": 0.65, "f7": 0.60, "f8": 0.80, "f9": 0.95}


def test_library_loads_ten_archetypes():
    lib = ArchetypeLibrary()
    assert len(lib.archetypes) == 10
    print(f"[PASS] Archetype library: {len(lib.archetypes)} archetypes")


def test_genesis_vector_is_unit_norm():
    lib = ArchetypeLibrary()
    vec = lib.features_to_genesis_vector(_healthy_features())
    assert vec.shape == (EMBEDDING_DIM,)
    assert abs(np.linalg.norm(vec) - 1.0) < 1e-5
    print(f"[PASS] Genesis vector: dim={vec.shape[0]}, unit norm")


def test_conf_genesis_monotone():
    lib = ArchetypeLibrary()
    feats = _healthy_features()
    prev = -1.0
    for d in [0, 1, 10, 50, 100, 500]:
        r = lib.genesis_inference(feats, d_value=float(d))
        cg = r["conf_genesis"]
        assert cg >= prev, f"conf_genesis not monotone at D={d}"
        prev = cg
    print(f"[PASS] conf_genesis monotone with D(t)")


def test_conf_genesis_at_zero():
    lib = ArchetypeLibrary()
    r = lib.genesis_inference(_healthy_features(), d_value=0.0)
    assert r["conf_genesis"] == 0.0
    print(f"[PASS] conf_genesis(D=0) = 0.0")


def test_genesis_inference_returns_required_fields():
    lib = ArchetypeLibrary()
    r = lib.genesis_inference(_healthy_features(), d_value=100.0)
    required = ["blended_signal", "conf_genesis", "archetype_id",
                "archetype_similarity", "top_3_archetypes"]
    for k in required:
        assert k in r, f"Missing field: {k}"
    print(f"[PASS] genesis_inference has all required fields")


def test_trajectory_anomaly_returns_kl_and_flag():
    lib = ArchetypeLibrary()
    arch = lib.archetypes[0]
    feats = _healthy_features()
    kl_div, is_anomaly = lib.trajectory_anomaly(feats, arch)
    assert isinstance(kl_div, float) and kl_div >= 0
    assert isinstance(is_anomaly, bool)
    print(f"[PASS] Trajectory anomaly KL={kl_div:.4f}, flag={is_anomaly}")


if __name__ == "__main__":
    test_library_loads_ten_archetypes()
    test_genesis_vector_is_unit_norm()
    test_conf_genesis_monotone()
    test_conf_genesis_at_zero()
    test_genesis_inference_returns_required_fields()
    test_trajectory_anomaly_returns_kl_and_flag()
    print("\n[PASS] All archetype engine tests passed")
