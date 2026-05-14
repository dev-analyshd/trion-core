"""
Tests for src/planes/physical/phi_engine.py — TRION L1 Physical Plane Φ(t).
Actual module used by oracle_api/app.py for physical plane computation.
Returns: {'phi_raw', 'f1'..'f9', 'tx_count', 'weights'}
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.planes.physical.phi_engine import (
    TransactionData, shannon_entropy, normalize_entropy,
    compute_f1_volume_entropy, compute_f2_counterparty_diversity,
    compute_f3_temporal_spacing, compute_f4_contract_entropy,
    compute_f5_value_flow, compute_phi,
)


def _tx(i: int, value: int = 1000, to_addr: str = None, from_addr: str = None,
        is_contract: bool = False, contract_addr: str = None) -> TransactionData:
    return TransactionData(
        tx_hash=f"0x{i:064x}",
        timestamp=float(1000 + i * 10),
        block_number=100 + i,
        from_addr=from_addr or f"0x{'a' * 38}{i:02x}",
        to_addr=to_addr or f"0x{'b' * 38}{i:02x}",
        value_wei=value,
        gas_used=21000,
        gas_price=20,
        is_contract=is_contract,
        contract_addr=contract_addr,
        input_len=0,
    )


def test_shannon_entropy_uniform_is_max():
    H = shannon_entropy([1.0, 1.0, 1.0, 1.0])
    assert abs(H - 2.0) < 1e-6     # log2(4) = 2.0
    print(f"[PASS] shannon_entropy uniform = log2(n): {H:.4f}")


def test_shannon_entropy_concentrated_is_zero():
    H = shannon_entropy([1000.0, 0.0, 0.0])
    assert H == 0.0
    print(f"[PASS] shannon_entropy concentrated = 0.0")


def test_normalize_entropy_clamps():
    assert normalize_entropy(2.0, 4) <= 1.0
    assert normalize_entropy(0.0, 4) == 0.0
    assert normalize_entropy(0.0, 1) == 0.0
    print(f"[PASS] normalize_entropy clamps to [0,1]")


def test_f1_volume_entropy_diverse():
    txs = [_tx(i, value=(i + 1) * 100) for i in range(20)]
    f1 = compute_f1_volume_entropy(txs)
    assert 0.0 <= f1 <= 1.0
    assert f1 > 0.0, "Diverse volume must have positive entropy"
    print(f"[PASS] f1 volume entropy diverse: {f1:.4f}")


def test_f1_empty_is_zero():
    assert compute_f1_volume_entropy([]) == 0.0
    print(f"[PASS] f1 empty = 0.0")


def test_f2_all_unique_counterparties():
    txs = [_tx(i, to_addr=f"0x{'c' * 38}{i:02x}") for i in range(20)]
    f2 = compute_f2_counterparty_diversity(txs)
    assert 0.0 <= f2 <= 1.0
    assert f2 > 0.0
    print(f"[PASS] f2 counterparty diversity (all unique): {f2:.4f}")


def test_f2_single_counterparty_is_zero():
    txs = [_tx(i, to_addr="0xdeadbeef") for i in range(10)]
    f2 = compute_f2_counterparty_diversity(txs)
    assert f2 == 0.0
    print(f"[PASS] f2 single counterparty = 0.0")


def test_f3_temporal_spacing_single_tx_is_zero():
    assert compute_f3_temporal_spacing([_tx(0)]) == 0.0
    print(f"[PASS] f3 single tx = 0.0")


def test_f4_contract_entropy():
    txs = [_tx(i, is_contract=True, contract_addr=f"0xcontract{i % 5:02x}") for i in range(15)]
    f4 = compute_f4_contract_entropy(txs)
    assert 0.0 <= f4 <= 1.0
    print(f"[PASS] f4 contract entropy: {f4:.4f}")


def test_f5_bidirectional_flow():
    entity = "0x" + "e" * 40
    txs = (
        [_tx(i, from_addr=entity, to_addr="0x" + "o" * 40, value=1000) for i in range(5)] +
        [_tx(i + 5, from_addr="0x" + "o" * 40, to_addr=entity, value=1000) for i in range(5)]
    )
    f5 = compute_f5_value_flow(txs, entity)
    assert 0.0 <= f5 <= 1.0
    print(f"[PASS] f5 bidirectional flow: {f5:.4f}")


def test_compute_phi_returns_all_features():
    txs = [_tx(i, value=(i + 1) * 500, is_contract=(i % 3 == 0),
               contract_addr=f"0xC{i % 4}" if i % 3 == 0 else None) for i in range(30)]
    result = compute_phi(txs, entity_addr="0x" + "e" * 40)
    required = ["phi_raw", "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "tx_count"]
    for k in required:
        assert k in result, f"Missing key: {k}"
    print(f"[PASS] compute_phi has all {len(required)} required keys, phi_raw={result['phi_raw']:.4f}")


def test_compute_phi_features_are_floats():
    txs = [_tx(i, value=(i + 1) * 200) for i in range(20)]
    result = compute_phi(txs, entity_addr="0x" + "a" * 40)
    for k in ["f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9"]:
        v = result[k]
        assert isinstance(v, float), f"{k} is not a float: {type(v)}"
    print(f"[PASS] All f1..f9 are floats")


if __name__ == "__main__":
    test_shannon_entropy_uniform_is_max()
    test_shannon_entropy_concentrated_is_zero()
    test_normalize_entropy_clamps()
    test_f1_volume_entropy_diverse()
    test_f1_empty_is_zero()
    test_f2_all_unique_counterparties()
    test_f2_single_counterparty_is_zero()
    test_f3_temporal_spacing_single_tx_is_zero()
    test_f4_contract_entropy()
    test_f5_bidirectional_flow()
    test_compute_phi_returns_all_features()
    test_compute_phi_features_are_floats()
    print("\n[PASS] All phi_engine (L1 physical) tests passed")
