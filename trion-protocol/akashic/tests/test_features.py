import sys
sys.path.insert(0, '../src')
from feature_extractor import FeatureWindow, extract_features, shannon_entropy_normalized


def test_healthy_protocol():
    window = FeatureWindow(
        volumes=[100, 250, 50, 1000, 300, 75, 400, 200],
        counterparties=[f"0x{i:040x}" for i in range(500)],
        timestamps=[1000 + i * 13 for i in range(8)],
        contracts_touched=[f"0xC{i}" for i in range(30)],
        inflow=2375, outflow=1800,
        protocol_ids=["uniswap", "aave", "compound", "curve", "balancer"],
        gas_prices=[20.1, 21.0, 19.5, 22.0, 20.5, 21.5, 20.0, 19.8],
        mev_tx_count=0,
        total_tx_count=8,
    )
    f = extract_features(window)
    assert all(0 <= v <= 1 for v in f.values()), "All features must be in [0,1]"
    assert f["f9"] > 0.90, f"No-MEV protocol must have f9 > 0.90, got {f['f9']}"
    print(f"[PASS] Healthy protocol features: {f}")


def test_wash_trading_low_diversity():
    window = FeatureWindow(
        volumes=[1000] * 5,
        counterparties=["0xAAA", "0xBBB", "0xAAA", "0xBBB", "0xAAA"],
        timestamps=[1000 + i for i in range(5)],
        contracts_touched=["0xC1"],
        inflow=5000, outflow=5000,
        protocol_ids=["unknown"],
        gas_prices=[20.0] * 5,
        mev_tx_count=0,
        total_tx_count=5,
    )
    f = extract_features(window)
    assert f["f2"] <= 0.5, f"Wash trading must produce low f2, got {f['f2']}"
    print(f"[PASS] Wash trading f2={f['f2']:.4f} (low diversity)")


def test_high_mev_reduces_f9():
    window = FeatureWindow(
        volumes=[100] * 10,
        counterparties=[f"0x{i}" for i in range(10)],
        timestamps=[1000 + i for i in range(10)],
        contracts_touched=[f"0xC{i}" for i in range(5)],
        inflow=500, outflow=500,
        protocol_ids=["uniswap"],
        gas_prices=[100.0] * 10,
        mev_tx_count=9,
        total_tx_count=10,
    )
    f = extract_features(window)
    assert f["f9"] < 0.20, f"High MEV must produce low f9, got {f['f9']}"
    print(f"[PASS] High MEV f9={f['f9']:.4f}")


def test_shannon_entropy():
    uniform   = [1.0] * 10
    h_uniform = shannon_entropy_normalized(uniform)
    assert abs(h_uniform - 1.0) < 1e-6, f"Uniform must be H=1.0, got {h_uniform}"

    concentrated = [100.0, 0.0, 0.0, 0.0]
    h_conc       = shannon_entropy_normalized(concentrated)
    assert h_conc < 0.10, f"Concentrated must be near H=0, got {h_conc}"
    print(f"[PASS] Shannon entropy: uniform={h_uniform:.4f}, concentrated={h_conc:.4f}")


def test_all_features_in_unit_interval():
    import random
    random.seed(42)
    for _ in range(20):
        window = FeatureWindow(
            volumes=[random.uniform(0, 1000) for _ in range(random.randint(1, 20))],
            counterparties=[f"0x{random.randint(0, 9999):040x}" for _ in range(random.randint(1, 50))],
            timestamps=sorted([random.uniform(1000, 2000) for _ in range(random.randint(2, 10))]),
            contracts_touched=[f"0xC{random.randint(0, 20)}" for _ in range(random.randint(1, 15))],
            inflow=random.uniform(0, 10000),
            outflow=random.uniform(0, 10000),
            protocol_ids=random.sample(["uniswap", "aave", "curve", "balancer", "comp"], random.randint(1, 5)),
            gas_prices=[random.uniform(10, 100) for _ in range(random.randint(1, 10))],
            mev_tx_count=random.randint(0, 5),
            total_tx_count=random.randint(1, 20),
        )
        f = extract_features(window)
        for k, v in f.items():
            assert 0.0 <= v <= 1.0, f"Feature {k}={v} out of [0,1]"
    print("[PASS] All features in [0,1] across 20 random windows")


if __name__ == "__main__":
    test_healthy_protocol()
    test_wash_trading_low_diversity()
    test_high_mev_reduces_f9()
    test_shannon_entropy()
    test_all_features_in_unit_interval()
    print("\n[PHASE 2] ALL TESTS PASSED")
