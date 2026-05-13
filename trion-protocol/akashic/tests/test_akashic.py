import sys
sys.path.insert(0, '../src')
import numpy as np
from akashic.archetype_engine import ArchetypeLibrary
from akashic.resurrection import (
    ResurrectionInput, DormancyType, ResurrectionOutcome, compute_resurrection
)


def test_archetype_library_loads():
    lib = ArchetypeLibrary()
    assert len(lib.archetypes) >= 10, "Must have at least 10 seed archetypes"
    print(f"[PASS] Archetype library: {len(lib.archetypes)} archetypes loaded")


def test_genesis_inference_returns_all_fields():
    lib = ArchetypeLibrary()
    features = {"f1": 0.6, "f2": 0.7, "f3": 0.5, "f4": 0.4,
                "f5": 0.6, "f6": 0.5, "f7": 0.3, "f8": 0.7, "f9": 0.9}

    result = lib.genesis_inference(features, d_value=0.0)
    assert result["conf_genesis"] < 0.01, "At D=0 conf_genesis must be near 0"
    print(f"[PASS] Genesis at D=0: conf={result['conf_genesis']}, archetype={result['archetype_id']}")

    result_mature = lib.genesis_inference(features, d_value=100.0)
    assert result_mature["conf_genesis"] > 0.99, "At D=100 conf_genesis must be near 1"
    print(f"[PASS] Genesis at D=100: conf={result_mature['conf_genesis']:.4f}")


def test_conf_genesis_monotonically_increasing():
    lib = ArchetypeLibrary()
    features = {"f1": 0.7, "f2": 0.7, "f3": 0.7, "f4": 0.7,
                "f5": 0.7, "f6": 0.7, "f7": 0.7, "f8": 0.7, "f9": 0.7}
    prev_conf = -1.0
    for d in [0, 1, 5, 10, 20, 50, 100]:
        r = lib.genesis_inference(features, d_value=float(d))
        assert r["conf_genesis"] >= prev_conf, f"conf_genesis must be monotone, failed at D={d}"
        prev_conf = r["conf_genesis"]
    print("[PASS] conf_genesis is monotonically increasing with D(t)")


def test_trajectory_anomaly_detection():
    lib = ArchetypeLibrary()
    arch = lib.archetypes[0]

    normal_features = {"f1": 0.7, "f2": 0.7, "f3": 0.7, "f4": 0.7,
                       "f5": 0.7, "f6": 0.7, "f7": 0.7, "f8": 0.7, "f9": 0.7}
    kl_normal, _ = lib.trajectory_anomaly(normal_features, arch, kl_threshold=100.0)
    assert kl_normal >= 0, "KL divergence must be non-negative"
    print(f"[PASS] Trajectory anomaly KL={kl_normal:.4f}")


def test_resurrection_genuine_continuation():
    pre  = np.random.randn(128).astype(np.float32)
    pre  = pre / np.linalg.norm(pre)
    post = pre + np.random.randn(128).astype(np.float32) * 0.01
    post = post / np.linalg.norm(post)

    inp = ResurrectionInput(
        dormancy_type=DormancyType.HIBERNATION,
        dormancy_days=30.0,
        pre_dormancy_vector=pre,
        reactivation_vector=post,
        cross_chain_evidence=0.80,
        ownership_changed=False,
        team_continuity=0.90,
        community_continuity=0.85,
    )
    result = compute_resurrection(inp)
    assert result["outcome"] == ResurrectionOutcome.GENUINE_CONTINUATION.value
    print(f"[PASS] Genuine continuation: delta={result['delta_resurrection']:.4f}")


def test_resurrection_hostile_takeover():
    pre  = np.random.randn(128).astype(np.float32)
    post = np.random.randn(128).astype(np.float32)
    pre  /= np.linalg.norm(pre)
    post /= np.linalg.norm(post)

    inp = ResurrectionInput(
        dormancy_type=DormancyType.ABANDONED,
        dormancy_days=500.0,
        pre_dormancy_vector=pre,
        reactivation_vector=post,
        cross_chain_evidence=0.05,
        ownership_changed=True,
        team_continuity=0.0,
        community_continuity=0.10,
    )
    result = compute_resurrection(inp)
    assert result["outcome"] == ResurrectionOutcome.HOSTILE_TAKEOVER.value
    print(f"[PASS] Hostile takeover detected: delta={result['delta_resurrection']:.4f}")


def test_migration_no_kappa_decay():
    pre  = np.random.randn(128).astype(np.float32)
    pre /= np.linalg.norm(pre)
    post = pre.copy()

    inp = ResurrectionInput(
        dormancy_type=DormancyType.MIGRATION,
        dormancy_days=365.0,
        pre_dormancy_vector=pre,
        reactivation_vector=post,
        cross_chain_evidence=0.90,
        ownership_changed=False,
        team_continuity=0.95,
        community_continuity=0.90,
    )
    result = compute_resurrection(inp)
    assert result["decay_factor"] == 1.0, "MIGRATION kappa=0 must have decay=1.0"
    print(f"[PASS] Migration no decay: decay={result['decay_factor']}, outcome={result['outcome']}")


if __name__ == "__main__":
    test_archetype_library_loads()
    test_genesis_inference_returns_all_fields()
    test_conf_genesis_monotonically_increasing()
    test_trajectory_anomaly_detection()
    test_resurrection_genuine_continuation()
    test_resurrection_hostile_takeover()
    test_migration_no_kappa_decay()
    print("\n[PHASE 3] ALL TESTS PASSED")
