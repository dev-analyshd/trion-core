"""
Tests for src/planes/spiritual/sigma_engine.py — TRION L4 Σ(t).
Actual module imported by api/app.py (hhi_monitor also used).
Algorithm: w_eff = stake * d_j, d_j = 1 - corr(M_j, M̄)
Bootstrap: True when validator_count < 10.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import numpy as np
from src.planes.spiritual.sigma_engine import (
    ValidatorSignal, compute_sigma, compute_diversity_weight, compute_hhi,
    SIGMA_BOOTSTRAP,
)


def _val(vid: str, valuation: float, n_outputs: int = 20,
         stake: float = 1.0, seed: int = 0) -> ValidatorSignal:
    rng = np.random.RandomState(seed)
    outputs = rng.uniform(0.5, 0.9, n_outputs)
    return ValidatorSignal(
        validator_id=vid, valuation=valuation,
        stake=stake, model_outputs=outputs,
    )


def test_bootstrap_when_no_validators():
    result = compute_sigma([])
    assert result["bootstrap"] is True
    assert result["sigma"] == 0.25
    assert "disclosure" in result
    print(f"[PASS] Bootstrap sigma=0.25 with no validators")


def test_sigma_in_unit_interval():
    validators = [_val(f"V{i}", valuation=0.70 + i * 0.02, seed=i) for i in range(15)]
    result = compute_sigma(validators)
    assert 0.0 <= result["sigma"] <= 1.0
    assert result["bootstrap"] is False
    print(f"[PASS] Sigma in [0,1]: sigma={result['sigma']:.4f}")


def test_bootstrap_true_below_ten_validators():
    validators = [_val(f"V{i}", 0.72, seed=i) for i in range(9)]
    result = compute_sigma(validators)
    assert result["bootstrap"] is True, "< 10 validators must remain in bootstrap"
    print(f"[PASS] Bootstrap still True with 9 validators (< 10 threshold)")


def test_hhi_healthy_equal_stake():
    n = 20
    weights = [1.0] * n
    hhi = compute_hhi(weights)
    expected = (1.0 / n) ** 2 * n * 10000
    assert abs(hhi - expected) < 1e-6
    print(f"[PASS] HHI equal stake: {hhi:.0f}")


def test_hhi_critical_monopoly():
    weights = [9999.0, 1.0]
    hhi = compute_hhi(weights)
    assert hhi > 9000, f"Near-monopoly HHI should be critical, got {hhi}"
    print(f"[PASS] HHI monopoly: {hhi:.0f}")


def test_diversity_weight_in_unit_interval():
    np.random.seed(42)
    m_j = np.random.uniform(0, 1, 50)
    m_bar = np.random.uniform(0, 1, 50)
    d = compute_diversity_weight(m_j, m_bar)
    assert 0.0 <= d <= 1.0
    print(f"[PASS] Diversity weight in [0,1]: d={d:.4f}")


def test_diversity_weight_perfectly_correlated_is_zero():
    m_j = np.array([0.1, 0.3, 0.5, 0.7, 0.9, 0.2, 0.4, 0.6, 0.8, 1.0])
    m_bar = m_j.copy()
    d = compute_diversity_weight(m_j, m_bar)
    assert d < 1e-10, f"Perfect correlation → diversity≈0, got {d}"
    print(f"[PASS] Diversity weight perfectly correlated = 0.0")


def test_sigma_result_has_hhi_status():
    validators = [_val(f"V{i}", 0.72, seed=i) for i in range(15)]
    result = compute_sigma(validators)
    assert "hhi_status" in result
    assert result["hhi_status"] in ("HEALTHY", "WARNING", "DANGER", "CRITICAL")
    print(f"[PASS] sigma result has hhi_status: {result['hhi_status']}")


def test_sigma_bootstrap_constant_keys():
    required = ["sigma", "bootstrap", "disclosure"]
    for k in required:
        assert k in SIGMA_BOOTSTRAP, f"SIGMA_BOOTSTRAP missing key: {k}"
    print(f"[PASS] SIGMA_BOOTSTRAP constant has all {len(required)} required keys")


if __name__ == "__main__":
    test_bootstrap_when_no_validators()
    test_sigma_in_unit_interval()
    test_bootstrap_true_below_ten_validators()
    test_hhi_healthy_equal_stake()
    test_hhi_critical_monopoly()
    test_diversity_weight_in_unit_interval()
    test_diversity_weight_perfectly_correlated_is_zero()
    test_sigma_result_has_hhi_status()
    test_sigma_bootstrap_constant_keys()
    print("\n[PASS] All sigma_engine (L4 Σ) tests passed")
