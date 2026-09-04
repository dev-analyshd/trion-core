"""
Tests for src/planes/spiritual/sigma_engine.py — TRION L4 Σ(t).
Actual module imported by api/app.py (hhi_monitor also used).
Algorithm: w_eff = stake * d_j, d_j = 1 - corr(M_j, M̄)
Bootstrap: True when validator_count < 10.

DD §5.3 fix (Task 16-c): the README "Consensus Security 6/6 — 50 sybils with
75.8% nominal stake → 0.00% effective power" row previously matched NO test
in the repo (the number existed only as a hardcoded frontend constant). The
six tests below measure the REAL output of core/spiritual/consensus.py
(compute_dw_bft_consensus) and core/spiritual/hhi_monitor.py against that
scenario: 50 unit-stake sybil validators copying one behavioural vector vs
16 unit-stake honest validators → nominal sybil stake = 50/66 = 75.7576%.
Every quoted number is a measured engine output, not a target.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import numpy as np
from core.spiritual.sigma_engine import (
    ValidatorSignal, compute_sigma, compute_diversity_weight, compute_hhi,
    SIGMA_BOOTSTRAP,
)
from core.spiritual.consensus import (
    Validator, compute_dw_bft_consensus, compute_diversity_weights,
    classify_hhi, compute_dynamic_delta,
)
from core.spiritual.hhi_monitor import (
    ValidatorStake, compute_hhi_enforcement, HHITier,
    MAX_SINGLE_REGION, MAX_SINGLE_JURISDICTION, MIN_CONTINENTS,
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


# ════════════════════════════════════════════════════════════════════════════
# DD §5.3: real measurements for the README "Consensus Security" row.
# Deterministic constructions (fixed RandomState seeds — no global seeding).
# ════════════════════════════════════════════════════════════════════════════

_N_OUTPUTS = 20
_N_SYBILS = 50
_N_HONEST = 16
_SYBIL_VALUATION = 0.85          # the cartel's coordinated (biased) valuation


def _honest_validator(h: int, valuation_spread: float = 0.02) -> Validator:
    """Independent honest validator: own behavioural vector + own valuation."""
    rng = np.random.RandomState(1000 + h)
    outputs = [float(x) for x in rng.normal(0.72, 0.08, _N_OUTPUTS)]
    valuation = float(np.clip(rng.normal(0.72, valuation_spread), 0.0, 1.0))
    archs = ["Transformer", "LSTM", "GNN", "Hybrid"]
    geos = ["NorthAmerica", "Europe", "Asia", "Africa", "SouthAmerica", "Oceania"]
    return Validator(
        validator_id=f"honest_{h:02d}", stake=1.0, model_outputs=outputs,
        valuation=valuation, model_arch=archs[h % 4], geography=geos[h % 6],
        is_byzantine=False,
    )


# The behavioural vector the sybil cartel copies (wiggly → variance > 0,
# so corr(M_j, M̄) is well-defined and equals 1.0 at full coordination).
_SYBIL_SIGNAL = [float(x) for x in np.random.RandomState(999).normal(0.72, 0.08, _N_OUTPUTS)]


def _sybil_validator(j: int, coordination: float = 1.0) -> Validator:
    """Sybil validator j of the cartel.

    coordination interpolates the attack model:
      0.0 = independent own outputs (pairwise corr ≈ 0 — honest-like, not yet a
            cartel)
      1.0 = perfect copy of _SYBIL_SIGNAL (pairwise corr = 1 — the "copied
            behavioural vectors" of the frontend sybil-collapse simulation)
    """
    rng = np.random.RandomState(2000 + j)
    own = rng.normal(0.72, 0.08, _N_OUTPUTS)
    outputs = [float((1.0 - coordination) * o + coordination * s)
               for o, s in zip(own, _SYBIL_SIGNAL)]
    return Validator(
        validator_id=f"sybil_{j:02d}", stake=1.0, model_outputs=outputs,
        valuation=_SYBIL_VALUATION, model_arch="Transformer",
        geography="NorthAmerica", is_byzantine=True,
    )


def test_sybil_50_validators_75pct_nominal_stake_reduced_to_zero_effective_power():
    """README "Consensus Security" headline — measured on the real engine.

    50 sybils each copy the same behavioural vector and hold unit stake
    against 16 honest unit-stake validators → nominal sybil stake
    50/66 = 75.7576% (the README's "75.8%"). With 50 identical vectors the
    element-wise median M̄ IS the copied vector, so every sybil has
    corr(M_j, M̄) = 1.0 → d_j = 0 → effective power 0.
    """
    validators = ([_sybil_validator(j, coordination=1.0) for j in range(_N_SYBILS)]
                  + [_honest_validator(h) for h in range(_N_HONEST)])

    nominal_sybil_stake = sum(v.stake for v in validators if v.is_byzantine)
    nominal_total_stake = sum(v.stake for v in validators)
    nominal_share = nominal_sybil_stake / nominal_total_stake

    result = compute_dw_bft_consensus(validators)

    # Nominal cartel stake: measured 75.7576% (README rounds to 75.8%)
    assert 0.745 < nominal_share < 0.770, f"nominal sybil stake {nominal_share:.6f}"

    # (a) Effective power after diversity weighting: measured 0.0 exactly
    total_eff = result.total_effective_stake
    sybil_eff = result.byzantine_effective_weight
    assert total_eff > 0
    assert sybil_eff == 0.0, f"sybil effective weight {sybil_eff!r}"
    assert sybil_eff / total_eff < 1e-12
    for r in result.diversity_results:
        if r.validator_id.startswith("sybil_"):
            assert abs(r.correlation - 1.0) < 1e-12
            assert r.diversity_weight < 1e-12
            assert r.effective_weight < 1e-12
            assert r.within_consensus is False   # biased valuation, no weight

    # (b) Honest validators retain power: measured 100% of effective stake
    honest_results = [r for r in result.diversity_results
                      if not r.validator_id.startswith("sybil_")]
    assert all(r.effective_weight > 0 for r in honest_results)
    honest_share = sum(r.effective_weight for r in honest_results) / total_eff
    assert honest_share > 0.999, f"honest effective share {honest_share:.6f}"
    assert result.honest_effective_stake == result.total_effective_stake
    assert result.safety_holds is True and result.safety_margin > 0
    assert result.sigma == 1.0
    assert result.validators_in_consensus == _N_HONEST

    # (c) The coordinated valuation cannot capture the consensus value:
    #     classic stake-weighting lands at 0.8174 (dragged 0.102 toward the
    #     cartel target); DW-BFT stays at the honest mean (measured 0.7136).
    honest_valuations = [v.valuation for v in validators if not v.is_byzantine]
    honest_mean = sum(honest_valuations) / len(honest_valuations)
    classic_value = (nominal_sybil_stake * _SYBIL_VALUATION
                     + (nominal_total_stake - nominal_sybil_stake) * honest_mean) \
                    / nominal_total_stake
    assert abs(result.consensus_value - honest_mean) <= result.consensus_window
    assert abs(classic_value - honest_mean) > result.consensus_window

    # (d) Post-collapse HHI over effective weights: measured 678.54 → HEALTHY
    assert 0 < result.hhi < 1500
    assert result.hhi_health == "HEALTHY"

    print(f"[PASS] 50 sybils, {nominal_share * 100:.4f}% nominal stake → "
          f"{sybil_eff / total_eff * 100:.6f}% effective power (honest retain "
          f"{honest_share * 100:.2f}%, Σ={result.sigma}, safety margin "
          f"{result.safety_margin:.4f}, HHI {result.hhi:.2f})")


def test_sybil_coordination_collapse_curve_intermediate_gap_measured():
    """Coordination Collapse Theorem — measured, including the honest gap.

    sybil_j = (1−c)·own_j + c·signal; the cartel's pairwise correlation rises
    with c. Real engine output (50 sybils + 16 honest, unit stakes, nominal
    75.7576%):
        c=0.00 (pairwise corr ~0.00): 75.83% — independent validators are NOT
                                      punished (share ≈ nominal)
        c=0.25 (corr ~0.11):          69.94%
        c=0.50 (corr ~0.47):          49.22% — 2/3 safety bound VIOLATED here
        c=0.75 (corr ~0.87):          14.24%
        c=0.90 (corr ~0.98):           1.94%
        c=1.00 (corr  1.00):           0.00%
    The collapse is real but only COMPLETE at high coordination — the DD §5.3
    criticism ("an attacker who coordinates slightly imperfectly retains
    weight") is quantified, not hidden.
    """
    levels = [0.0, 0.25, 0.50, 0.75, 0.90, 1.00]
    honest = [_honest_validator(h) for h in range(_N_HONEST)]
    shares, safety, pairwise = [], [], []
    for c in levels:
        sybils = [_sybil_validator(j, coordination=c) for j in range(_N_SYBILS)]
        r = compute_dw_bft_consensus(sybils + honest)
        shares.append(r.byzantine_effective_weight / r.total_effective_stake)
        safety.append(r.safety_holds)
        corr_matrix = np.corrcoef(np.array([v.model_outputs for v in sybils]))
        pairwise.append((corr_matrix.sum() - len(sybils)) / (len(sybils) ** 2 - len(sybils)))

    # Monotone: effective power strictly decreases with coordination
    assert all(shares[i + 1] < shares[i] for i in range(len(shares) - 1)), shares
    # Independent sybils keep ≈ nominal power — no penalty for honest-like behaviour
    assert shares[0] > 0.70, shares[0]
    # Intermediate coordination (pairwise corr ≈ 0.5): ~49% retained, no 2/3 majority
    assert 0.40 < shares[2] < 0.55, shares[2]
    assert safety[2] is False
    # Strong coordination: drastic reduction, honest majority restored
    assert shares[3] < 0.16, shares[3]
    assert safety[3] is True
    assert shares[4] < 0.025, shares[4]
    # Perfect coordination: exactly zero
    assert shares[5] == 0.0
    assert safety[5] is True

    print("[PASS] Coordination collapse curve (nominal 75.7576%): "
          + " → ".join(f"{s * 100:.2f}%" for s in shares)
          + " | pairwise corr " + "/".join(f"{p:.2f}" for p in pairwise)
          + " | 2/3 safety " + "/".join("T" if s else "F" for s in safety))


def test_diversity_weight_bounds_copy_is_zero_independent_kept():
    """d_j = 1 − corr(M_j, M̄) semantics — the engine's real bounds are [0, 2].

    - a perfect copy of the median → corr = 1.0 → d = 0.0 (the collapse)
    - perfectly anti-correlated → corr = −1.0 → d = 2.0 (NOT clamped to 1.0;
      d is bounded only by the Pearson range)
    - 20 independent validators → mean d ≈ 0.86, none zeroed: validators that
      merely look independent keep their weight
    """
    base = _SYBIL_SIGNAL
    anti = [1.0 - x for x in base]
    trio = [
        Validator("copy_a", 1.0, list(base), 0.72, "Transformer", "Europe", False),
        Validator("copy_b", 1.0, list(base), 0.72, "LSTM", "Asia", False),
        Validator("anti", 1.0, anti, 0.72, "GNN", "Africa", False),
    ]
    # element-wise median of (copy_a, copy_b, anti) = the copied vector
    by_id = {r.validator_id: r for r in compute_diversity_weights(trio)}
    assert abs(by_id["copy_a"].correlation - 1.0) < 1e-12
    assert abs(by_id["copy_b"].correlation - 1.0) < 1e-12
    assert by_id["copy_a"].diversity_weight < 1e-12
    assert by_id["copy_b"].diversity_weight < 1e-12
    assert abs(by_id["anti"].correlation + 1.0) < 1e-12
    assert abs(by_id["anti"].diversity_weight - 2.0) < 1e-12   # 1 − (−1)

    independents = [
        Validator(f"ind_{i:02d}", 1.0,
                  [float(x) for x in np.random.RandomState(500 + i).normal(0.72, 0.08, _N_OUTPUTS)],
                  0.72, "Hybrid", "Oceania", False)
        for i in range(20)
    ]
    d_values = [r.diversity_weight for r in compute_diversity_weights(independents)]
    assert all(0.0 <= d <= 2.0 for d in d_values)
    assert all(d > 0.0 for d in d_values)            # nobody falsely zeroed
    mean_d = sum(d_values) / len(d_values)
    assert 0.70 < mean_d < 1.05, mean_d              # measured: 0.8628
    print(f"[PASS] d_j bounds [0,2]: copy→0.0, anti-correlated→2.0, "
          f"20 independents mean d={mean_d:.4f} (none zeroed)")


def test_hhi_four_tier_classification_consensus_engine():
    """L4.8 HHI tiers from the real engine (README: "HHI 2500–4000 DANGER").

    Post-sybil-collapse validator set → measured HHI 678.54 → HEALTHY; whale
    concentration → measured HHI 9610.88 → CRITICAL; classify_hhi boundary
    semantics: 1500 WARNING, 2500 DANGER, 4000 DANGER, 4000.01 CRITICAL.
    """
    boundaries = [
        (0.0, "HEALTHY"), (1499.99, "HEALTHY"), (1500.0, "WARNING"),
        (2499.99, "WARNING"), (2500.0, "DANGER"), (4000.0, "DANGER"),
        (4000.01, "CRITICAL"), (10000.0, "CRITICAL"),
    ]
    for hhi, expected in boundaries:
        got = classify_hhi(hhi)
        assert got == expected, f"classify_hhi({hhi}) = {got}, expected {expected}"

    # Post-collapse set (same construction as the headline test): HHI 678.54
    validators = ([_sybil_validator(j, coordination=1.0) for j in range(_N_SYBILS)]
                  + [_honest_validator(h) for h in range(_N_HONEST)])
    collapsed = compute_dw_bft_consensus(validators)
    assert collapsed.hhi < 1500 and collapsed.hhi_health == "HEALTHY"

    # Whale: one validator with ~90% of stake → HHI 9610.88 → CRITICAL
    whale_outputs = [0.6, 0.7, 0.8, 0.5, 0.9, 0.65, 0.75, 0.55, 0.85, 0.6,
                     0.7, 0.8, 0.5, 0.9, 0.65, 0.75, 0.55, 0.85, 0.6, 0.7]
    whale = Validator("whale", 900.0, whale_outputs, 0.72, "Transformer", "Europe", False)
    smalls = [Validator(f"small_{i}", 1.0,
                        [float(x) for x in np.random.RandomState(3000 + i).normal(0.72, 0.08, _N_OUTPUTS)],
                        0.72, "LSTM", "Asia", False)
              for i in range(20)]
    concentrated = compute_dw_bft_consensus([whale] + smalls)
    assert concentrated.hhi > 4000
    assert concentrated.hhi_health == "CRITICAL"

    print(f"[PASS] HHI tiers: post-sybil-collapse {collapsed.hhi:.2f} HEALTHY, "
          f"whale {concentrated.hhi:.2f} CRITICAL, boundaries "
          f"1500/2500/4000 verified (2500–4000 = DANGER)")


def test_hhi_geographic_enforcement_constraints():
    """L4.8 geographic enforcement (core/spiritual/hhi_monitor.py):
    max single region < 40% and jurisdiction < 30% of effective stake,
    ≥ 4 continents, F8 (HHI > 2500 sustained 30 days) and F9 (< 4 continents
    without corrective incentive) falsification flags.
    """
    # Diverse: 60 validators over 6 continents / 10 regions / 6 jurisdictions
    diverse = [
        ValidatorStake(
            validator_id=f"v{i:02d}", stake=100.0, diversity_score=0.9,
            effective_stake=90.0,
            geographic_region=f"region_{i % 10}",
            jurisdiction=f"juris_{i % 6}",
            continent=["Europe", "NorthAmerica", "Asia", "Africa",
                       "SouthAmerica", "Oceania"][i % 6],
        )
        for i in range(60)
    ]
    r = compute_hhi_enforcement(diverse)
    assert r.tier == HHITier.HEALTHY
    assert r.hhi < 1500                                  # measured: 166.7
    assert r.continent_count >= MIN_CONTINENTS          # 6 continents
    assert max(r.region_shares.values()) < MAX_SINGLE_REGION       # 0.100 < 0.40
    assert max(r.jurisdiction_shares.values()) < MAX_SINGLE_JURISDICTION  # 0.167 < 0.30
    assert r.geographic_violations == []
    assert not r.consensus_paused and not r.f8_violation and not r.f9_violation

    # Region/jurisdiction concentration: 75% of effective stake in eu-west/Germany
    concentrated = (
        [ValidatorStake(f"g{i:02d}", 100.0, 0.9, 90.0, "eu-west", "Germany", "Europe")
         for i in range(30)]
        + [ValidatorStake(f"h{i:02d}", 100.0, 0.9, 90.0, f"region_{i}", f"juris_{i}", "Asia")
           for i in range(10)]
    )
    rc = compute_hhi_enforcement(concentrated)
    assert rc.continent_count == 2
    assert any(v.startswith("region:eu-west") for v in rc.geographic_violations)
    assert any(v.startswith("juris:Germany") for v in rc.geographic_violations)
    # F9: < 4 continents without an automatic corrective incentive
    assert compute_hhi_enforcement(concentrated, continents_have_incentive=False).f9_violation
    assert not rc.f9_violation                            # incentive present by default

    # DANGER tier (measured HHI 2800): 15% weight cap on each >15% validator
    danger = (
        [ValidatorStake(f"big{i}", 300.0, 1.0, 300.0, f"r{i + 1}", f"j{i + 1}",
                        ["Europe", "Asia", "Africa"][i]) for i in range(3)]
        + [ValidatorStake("small", 100.0, 1.0, 100.0, "r4", "j4", "Oceania")]
    )
    rd = compute_hhi_enforcement(danger)
    assert rd.tier == HHITier.DANGER
    assert rd.weight_capped_validators == ["big0", "big1", "big2"]
    assert not rd.consensus_paused
    assert not rd.f8_violation                            # high HHI, 0 days
    assert compute_hhi_enforcement(danger, hhi_days_above_2500=30).f8_violation

    # CRITICAL tier (measured HHI 9900.8): consensus paused + governance emergency
    critical = [ValidatorStake("whale", 1000.0, 0.9, 900.0, "r1", "j1", "Europe")] + [
        ValidatorStake(f"s{i}", 1.0, 0.9, 0.9, f"r{i + 2}", f"j{i + 2}", "Asia")
        for i in range(5)
    ]
    rcr = compute_hhi_enforcement(critical)
    assert rcr.tier == HHITier.CRITICAL
    assert rcr.consensus_paused and rcr.governance_emergency

    print(f"[PASS] HHI geographic enforcement: diverse {r.hhi:.1f} HEALTHY "
          f"({r.continent_count} continents, region/juris caps hold), 75% "
          f"region flagged, DANGER {rd.hhi:.0f} weight-capped, CRITICAL "
          f"{rcr.hhi:.1f} paused, F8/F9 verified")


def test_dynamic_consensus_window_scales_with_volatility():
    """L4.2: δ(t) = δ_base·(1 + V(t)) — volatility widens the consensus window.

    V is clamped to [0, 1]. With honest valuations spread ±0.08 the wider
    window admits more validators into consensus (measured: 8 → 11 of 16
    in-window, Σ 0.4467 → 0.6753).
    """
    assert abs(compute_dynamic_delta(0.05, 0.0) - 0.05) < 1e-12
    assert abs(compute_dynamic_delta(0.05, 0.5) - 0.075) < 1e-12
    assert abs(compute_dynamic_delta(0.05, 1.0) - 0.10) < 1e-12
    assert abs(compute_dynamic_delta(0.05, 7.0) - 0.10) < 1e-12   # clamped high
    assert abs(compute_dynamic_delta(0.05, -3.0) - 0.05) < 1e-12  # clamped low

    spread = [_honest_validator(h, valuation_spread=0.08) for h in range(_N_HONEST)]
    calm = compute_dw_bft_consensus(spread, delta=0.05)
    volatile = compute_dw_bft_consensus(spread, delta=0.05, volatility=0.6)
    assert abs(volatile.consensus_window - 0.08) < 1e-9
    assert volatile.validators_in_consensus > calm.validators_in_consensus  # 11 > 8
    assert volatile.sigma > calm.sigma                                     # 0.675 > 0.447
    print(f"[PASS] Dynamic window δ(t): 0.05 → {volatile.consensus_window} at "
          f"V=0.6, in-consensus {calm.validators_in_consensus} → "
          f"{volatile.validators_in_consensus}, Σ {calm.sigma:.4f} → "
          f"{volatile.sigma:.4f}")


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
    test_sybil_50_validators_75pct_nominal_stake_reduced_to_zero_effective_power()
    test_sybil_coordination_collapse_curve_intermediate_gap_measured()
    test_diversity_weight_bounds_copy_is_zero_independent_kept()
    test_hhi_four_tier_classification_consensus_engine()
    test_hhi_geographic_enforcement_constraints()
    test_dynamic_consensus_window_scales_with_volatility()
    print("\n[PASS] All sigma_engine (L4 Σ) + DW-BFT consensus security tests passed")
