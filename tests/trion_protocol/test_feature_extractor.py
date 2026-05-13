"""Tests for src/core/feature_extractor.py — TRION L1 Physical Features."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import math
import random
from src.core.feature_extractor import FeatureWindow, extract_features, shannon_entropy_normalized


def test_healthy_protocol_features():
    window = FeatureWindow(
        volumes=[100.0, 200.0, 150.0, 300.0, 250.0],
        counterparties=[f"0x{i:040x}" for i in range(5)],
        timestamps=[1000.0, 1010.0, 1025.0, 1040.0, 1060.0],
        contracts_touched=["0xA", "0xB", "0xC"],
        inflow=1000.0, outflow=900.0,
        protocol_ids=["uniswap", "aave", "compound"],
        gas_prices=[20.0, 22.0, 19.0, 21.0],
        mev_tx_count=0,
        total_tx_count=5,
    )
    feats = extract_features(window)
    assert feats["f1"] > 0.5, "healthy volume entropy should be > 0.5"
    assert feats["f2"] == 1.0, "all unique counterparties → diversity=1.0"
    assert feats["f9"] == 1.0, "no MEV → f9=1.0"
    print(f"[PASS] Healthy protocol: f1={feats['f1']:.4f} f2={feats['f2']} f9={feats['f9']}")


def test_zero_total_tx():
    window = FeatureWindow(
        volumes=[], counterparties=[], timestamps=[],
        contracts_touched=[], inflow=0.0, outflow=0.0,
        protocol_ids=[], gas_prices=[], mev_tx_count=0, total_tx_count=0,
    )
    feats = extract_features(window)
    assert all(v == 0.0 for v in feats.values()), "zero tx → all features=0"
    print(f"[PASS] Zero tx → all features 0.0")


def test_all_features_in_unit_interval():
    rng = random.Random(42)
    for _ in range(20):
        n = rng.randint(1, 100)
        window = FeatureWindow(
            volumes=[rng.uniform(0, 1000) for _ in range(n)],
            counterparties=[f"0x{rng.randint(0,999):04x}" for _ in range(n)],
            timestamps=sorted([rng.uniform(0, 10000) for _ in range(n)]),
            contracts_touched=[f"0xC{rng.randint(0,5)}" for _ in range(n)],
            inflow=rng.uniform(0, 1000),
            outflow=rng.uniform(0, 1000),
            protocol_ids=[f"p{rng.randint(0,9)}" for _ in range(n)],
            gas_prices=[rng.uniform(5, 200) for _ in range(n)],
            mev_tx_count=rng.randint(0, n),
            total_tx_count=n,
        )
        feats = extract_features(window)
        for k, v in feats.items():
            assert 0.0 <= v <= 1.0, f"Feature {k}={v} out of [0,1]"
    print(f"[PASS] All 9 features in [0,1] across 20 random windows")


def test_high_mev_reduces_f9():
    window = FeatureWindow(
        volumes=[100.0] * 10,
        counterparties=["0xA"] * 10,
        timestamps=list(range(10)),
        contracts_touched=["0xC"] * 10,
        inflow=500.0, outflow=500.0,
        protocol_ids=["p1"] * 10,
        gas_prices=[20.0] * 10,
        mev_tx_count=9,
        total_tx_count=10,
    )
    feats = extract_features(window)
    assert feats["f9"] <= 0.15, f"90% MEV → f9 should be low, got {feats['f9']}"
    print(f"[PASS] High MEV: f9={feats['f9']:.4f}")


def test_shannon_entropy_uniform():
    assert abs(shannon_entropy_normalized([1.0, 1.0, 1.0, 1.0]) - 1.0) < 1e-6
    print(f"[PASS] Shannon entropy uniform = 1.0")


def test_shannon_entropy_concentrated():
    result = shannon_entropy_normalized([1000.0, 0.0, 0.0, 0.0])
    assert result == 0.0
    print(f"[PASS] Shannon entropy concentrated = 0.0")


if __name__ == "__main__":
    test_healthy_protocol_features()
    test_zero_total_tx()
    test_all_features_in_unit_interval()
    test_high_mev_reduces_f9()
    test_shannon_entropy_uniform()
    test_shannon_entropy_concentrated()
    print("\n[PASS] All feature extractor tests passed")
