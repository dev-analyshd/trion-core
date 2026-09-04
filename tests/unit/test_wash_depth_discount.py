"""tests/unit/test_wash_depth_discount.py — R-EC-03 wash-trading depth defense.

CANONICAL_SPEC_MATRIX R-EC-03 (top-10 remediation #6, Wave 3 D):
    wash-trading defense  D_effective = D·(1 − HHI(counterparty_distribution))
    (MD §5 L1.1 "Wash Trading Defense") — REQUIRED as a standalone function
    in the depth engine; matrix row marked
    "MUST-CREATE: tests/unit/test_wash_depth_discount.py".

Covers:
  * compute_counterparty_hhi — normalized HHI over the counterparty
    distribution (empty/None → 0, single counterparty → 1, uniform N → 1/N);
  * wash_trading_depth_discount — the exact MD formula, bounds, monotonicity;
  * effective_depth — the depth-engine entry view;
  * d_engine (core/master/d_engine.py) — compute_depth and the canonical
    monotone compute_depth_canonical carry the same D_effective projection;
  * K8/K9 canonicality: canonical depth is monotone (append-only, MD
    L0.4/L9.2) — adding history never decreases D; the legacy decayed
    form is labeled non-canonical.
"""

import math

import pytest

from core.akashic.depth import (
    compute_counterparty_hhi,
    effective_depth,
    wash_trading_depth_discount,
)
from core.master.d_engine import (
    BlockRecord,
    compute_depth,
    compute_depth_canonical,
)


# ─── compute_counterparty_hhi ─────────────────────────────────────────────────


class TestCounterpartyHHI:
    def test_empty_and_none_return_zero(self):
        """Unmeasured ⇒ 0 concentration — never a fabricated penalty."""
        assert compute_counterparty_hhi(None) == 0.0
        assert compute_counterparty_hhi({}) == 0.0

    def test_single_counterparty_is_one(self):
        """A wash ring cycling through ONE counterparty ⇒ HHI = 1."""
        assert compute_counterparty_hhi({"only": 100.0}) == 1.0

    def test_uniform_n_counterparties_is_one_over_n(self):
        n = 10
        dist = {f"cp_{i}": 1.0 for i in range(n)}
        assert compute_counterparty_hhi(dist) == pytest.approx(1 / n)

    def test_weighted_shares(self):
        """HHI = Σ share² — 90/10 split ⇒ 0.81 + 0.01 = 0.82."""
        hhi = compute_counterparty_hhi({"ring_a": 90.0, "ring_b": 10.0})
        assert hhi == pytest.approx(0.9 ** 2 + 0.1 ** 2)

    def test_scale_invariant(self):
        """Shares, not raw volumes — doubling every volume changes nothing."""
        a = {"x": 3.0, "y": 7.0}
        b = {"x": 30.0, "y": 70.0}
        assert compute_counterparty_hhi(a) == pytest.approx(compute_counterparty_hhi(b))

    def test_nonpositive_values_ignored(self):
        """None / zero / negative weights are not counterparties."""
        assert compute_counterparty_hhi({"a": 5.0, "junk": None, "neg": -1.0, "z": 0.0}) \
            == pytest.approx(1.0)

    def test_all_zero_total_returns_zero(self):
        assert compute_counterparty_hhi({"a": 0.0, "b": 0.0}) == 0.0

    def test_bounded_zero_one(self):
        dists = [
            {"a": 1.0, "b": 2.0, "c": 3.0},
            {i: i * 1.5 for i in range(25)},
            {"a": 99.0, "b": 1.0},
        ]
        for d in dists:
            assert 0.0 <= compute_counterparty_hhi(d) <= 1.0


# ─── wash_trading_depth_discount — the MD L1.1 formula ────────────────────────


class TestWashTradingDepthDiscount:
    def test_formula_exact(self):
        """D_effective = D × (1 − HHI(counterparty_distribution)) — MD verbatim."""
        D = 1000.0
        dist = {"ring_a": 90.0, "ring_b": 10.0}
        hhi = 0.9 ** 2 + 0.1 ** 2
        assert wash_trading_depth_discount(D, dist) == pytest.approx(D * (1 - hhi))

    def test_perfect_ring_collapses_depth(self):
        """HHI = 1 (all volume with one counterparty) ⇒ D_effective = 0."""
        assert wash_trading_depth_discount(5000.0, {"wash": 100.0}) == 0.0

    def test_unmeasured_passes_through(self):
        """No distribution ⇒ no discount (data-pending, not penalized)."""
        assert wash_trading_depth_discount(123.0, None) == 123.0
        assert wash_trading_depth_discount(123.0, {}) == 123.0

    def test_zero_depth_stays_zero(self):
        assert wash_trading_depth_discount(0.0, {"a": 1.0}) == 0.0
        assert wash_trading_depth_discount(-5.0, {"a": 1.0}) == 0.0

    def test_monotone_in_concentration(self):
        """More concentrated ⇒ less effective depth (MD intent)."""
        D = 100.0
        spread = {f"cp_{i}": 1.0 for i in range(20)}
        mid = {"a": 50.0, "b": 30.0, "c": 20.0}
        ring = {"a": 90.0, "b": 10.0}
        solo = {"a": 100.0}
        effs = [
            wash_trading_depth_discount(D, d) for d in (spread, mid, ring, solo)
        ]
        assert effs == sorted(effs, reverse=True)
        # spread of 20 ⇒ HHI 1/20 ⇒ D_eff = 0.95·D (still the exact formula)
        assert effs[0] == pytest.approx(D * (1 - 1 / 20))
        assert effs[-1] == 0.0

    def test_bounds_0_to_D(self):
        for dist in (None, {}, {"a": 1.0}, {"a": 1.0, "b": 1.0}):
            d_eff = wash_trading_depth_discount(77.0, dist)
            assert 0.0 <= d_eff <= 77.0


# ─── effective_depth — the depth-engine entry view ────────────────────────────


class TestEffectiveDepthView:
    def test_fields_and_values(self):
        D = 1000.0
        dist = {"ring_a": 90.0, "ring_b": 10.0}
        view = effective_depth(D, dist)
        hhi = 0.9 ** 2 + 0.1 ** 2
        assert view["D"] == D
        assert view["D_effective"] == pytest.approx(D * (1 - hhi))
        assert view["counterparty_hhi"] == pytest.approx(hhi, abs=1e-6)
        assert view["discount_applied"] is True
        assert "MD L1.1" in view["formula"]

    def test_unmeasured_no_discount_flag(self):
        view = effective_depth(50.0, None)
        assert view["D_effective"] == 50.0
        assert view["counterparty_hhi"] == 0.0
        assert view["discount_applied"] is False

    def test_wash_ring_vs_healthy(self):
        """The defense distinguishes washed from organic counterparties."""
        D = 100.0
        washed = effective_depth(D, {"a": 99.0, "b": 1.0})["D_effective"]
        healthy = effective_depth(D, {f"cp_{i}": 1.0 for i in range(50)})["D_effective"]
        assert washed < 0.05 * D
        assert healthy > 0.95 * D


# ─── d_engine — block-level D(t) carries the same defense ─────────────────────


def _records(n=100, base=18_000_000, bh=(5,)):
    return [
        BlockRecord(
            block_number=base - i * 100,
            bh_count=bh[i % len(bh)],
            chain_id=1,
            timestamp=0.0,
        )
        for i in range(n)
    ]


class TestDEngineWashView:
    RING = {"ring_a": 90.0, "ring_b": 10.0}
    RING_HHI = 0.9 ** 2 + 0.1 ** 2

    def test_compute_depth_carries_depth_effective(self):
        out = compute_depth(_records(), current_block=18_000_000, n_chains=1,
                             counterparty_distribution=self.RING)
        assert out["depth"] > 0
        assert out["depth_effective"] == pytest.approx(
            out["depth"] * (1 - self.RING_HHI))
        assert out["counterparty_hhi"] == pytest.approx(self.RING_HHI, abs=1e-6)
        assert out["discount_applied"] is True

    def test_compute_depth_legacy_shape_unchanged(self):
        """No distribution ⇒ legacy keys only added to, never altered."""
        out = compute_depth(_records(), current_block=18_000_000, n_chains=3)
        assert out["depth"] > 0
        assert out["depth_effective"] == out["depth"]    # unmeasured
        assert out["discount_applied"] is False
        for key in ("record_count", "chains", "cc_multiplier",
                    "oldest_block", "newest_block", "span_blocks"):
            assert key in out

    def test_compute_depth_empty_records_wash_view(self):
        out = compute_depth([], current_block=1, counterparty_distribution=self.RING)
        assert out["depth"] == 0.0
        assert out["depth_effective"] == 0.0

    def test_canonical_depth_is_monotone(self):
        """K8/K9: canonical D never decays — append-only accumulation."""
        small = compute_depth_canonical(_records(10))
        bigger = compute_depth_canonical(_records(50))
        assert bigger["depth"] > small["depth"] > 0
        assert small["canonical"] is True and bigger["canonical"] is True

    def test_canonical_depth_ignores_block_age(self):
        """No recency weight: same bh counts ⇒ same D regardless of age."""
        old = _records(10, base=18_000_000)
        ancient = _records(10, base=1_000_000)
        assert compute_depth_canonical(old)["depth"] == \
            pytest.approx(compute_depth_canonical(ancient)["depth"])

    def test_canonical_depth_beats_decayed_form(self):
        """The decayed L2.md variant reads LOWER than canonical on old history."""
        recs = _records(100, base=18_000_000)
        decayed = compute_depth(recs, current_block=18_000_000, n_chains=1)
        canon = compute_depth_canonical(recs, n_chains=1)
        assert canon["depth"] > decayed["depth"]

    def test_canonical_depth_cross_chain_multiplier(self):
        recs = _records(10)
        one = compute_depth_canonical(recs, n_chains=1)
        five = compute_depth_canonical(recs, n_chains=5)
        assert five["depth"] == pytest.approx(one["depth"] * (1 + 0.1 * 4))

    def test_canonical_depth_carries_wash_view(self):
        recs = _records(20)
        out = compute_depth_canonical(recs, n_chains=2,
                                      counterparty_distribution=self.RING)
        raw = compute_depth_canonical(recs, n_chains=2)
        assert out["depth"] == raw["depth"]     # raw depth untouched (monotone)
        assert out["depth_effective"] == pytest.approx(
            raw["depth"] * (1 - self.RING_HHI))

    def test_decayed_form_formula_conformance(self):
        """D(t) = Σ BH·e^(−λ·age) × (1 + 0.1(N−1)) — legacy formula intact."""
        recs = _records(3, bh=(5, 7, 11))
        out = compute_depth(recs, current_block=18_000_000, n_chains=4)
        manual = sum(
            r.bh_count * math.exp(-0.0001 * (18_000_000 - r.block_number))
            for r in recs
        ) * (1 + 0.1 * 3)
        assert out["depth"] == pytest.approx(manual)
