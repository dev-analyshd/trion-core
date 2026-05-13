"""Tests for src/core/consensus_bft.py — Diversity-Weighted BFT Consensus."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.core.consensus_bft import (
    Validator, compute_sigma, compute_hhi, hhi_status,
    apply_slash, dynamic_window, SlashingType, HHIStatus,
    BFT_FAULT_TOLERANCE, HHI_HEALTHY, HHI_CRITICAL,
)


def _make_validators(n=9, stake=10000.0):
    return [Validator(f"V{i}", stake=stake, diversity=0.8, history=0.9) for i in range(n)]


def test_bft_safe_with_no_byzantine():
    vs    = _make_validators(9)
    votes = {v.validator_id: 0.75 for v in vs}
    r     = compute_sigma(vs, votes)
    assert r.bft_safe, "No Byzantine → must be BFT safe"
    assert abs(r.sigma - 0.75) < 1e-6
    print(f"[PASS] BFT safe: sigma={r.sigma}")


def test_bft_unsafe_at_one_third_slashed():
    vs = _make_validators(9)
    for v in vs[:3]:
        v.is_slashed = True
    votes = {v.validator_id: 0.75 for v in vs}
    r = compute_sigma(vs, votes)
    assert not r.bft_safe, f"1/3 slashed must be BFT UNSAFE, byz_frac={r.byzantine_weight_fraction}"
    print(f"[PASS] BFT unsafe at 1/3 Byzantine: byz_frac={r.byzantine_weight_fraction:.3f}")


def test_excluded_not_counted_as_byzantine():
    vs = _make_validators(9)
    vs[0].is_excluded = True
    votes = {v.validator_id: 0.80 for v in vs}
    r = compute_sigma(vs, votes)
    assert r.participant_count == 8, "Excluded validator should not participate"
    assert r.bft_safe, "Excluded is not Byzantine"
    print(f"[PASS] Excluded != Byzantine: participants={r.participant_count}")


def test_hhi_healthy():
    vs = [Validator(f"V{i}", stake=1000.0, diversity=1.0, history=1.0) for i in range(20)]
    hhi = compute_hhi(vs)
    assert hhi < HHI_HEALTHY, f"Equal stake → HHI should be HEALTHY, got {hhi}"
    print(f"[PASS] HHI HEALTHY: {hhi:.0f}")


def test_hhi_critical_monopoly():
    vs = [Validator("V0", stake=9999.0, diversity=1.0, history=1.0),
          Validator("V1", stake=1.0,    diversity=1.0, history=1.0)]
    hhi = compute_hhi(vs)
    assert hhi > HHI_CRITICAL, f"Near-monopoly → HHI should be CRITICAL, got {hhi}"
    print(f"[PASS] HHI CRITICAL: {hhi:.0f}")


def test_slash_rates():
    for slash_type in SlashingType:
        v = Validator("V0", stake=10000.0, diversity=1.0, history=1.0)
        amt = apply_slash(v, slash_type)
        assert v.is_slashed
        assert amt > 0
        assert v.stake < 10000.0
    print(f"[PASS] All {len(list(SlashingType))} slash types work correctly")


def test_dynamic_window_range():
    low  = dynamic_window(1.0)
    high = dynamic_window(0.0)
    assert low == 3,  f"High volatility → window=3, got {low}"
    assert high == 21, f"Low volatility → window=21, got {high}"
    print(f"[PASS] Dynamic window: V=1→{low}, V=0→{high}")


def test_sigma_to_dict():
    vs    = _make_validators(4)
    votes = {v.validator_id: 0.60 for v in vs}
    r     = compute_sigma(vs, votes)
    d     = r.to_dict()
    assert "sigma" in d and "bft_safe" in d and "hhi_status" in d
    print(f"[PASS] ConsensusResult.to_dict() has required keys")


if __name__ == "__main__":
    test_bft_safe_with_no_byzantine()
    test_bft_unsafe_at_one_third_slashed()
    test_excluded_not_counted_as_byzantine()
    test_hhi_healthy()
    test_hhi_critical_monopoly()
    test_slash_rates()
    test_dynamic_window_range()
    test_sigma_to_dict()
    print("\n[PASS] All BFT consensus tests passed")
