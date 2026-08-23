"""
Phase 8 — Held-out backtest split tests
========================================
Verifies the non-circular backtest's dataset split is:
  - Deterministic (same seed → same split)
  - Disjoint (no exploit in both TRAIN and TEST)
  - Proportional (67/33 split)
"""
import os
import pytest

from backtest.run_held_out_backtest import (
    load_dataset,
    split_dataset,
    wilson_ci,
    cohen_d,
    bootstrap_ci,
    RANDOM_SEED,
    TRAIN_FRACTION,
)


class TestDatasetSplit:
    def test_split_is_deterministic(self):
        data = load_dataset()
        train1, test1 = split_dataset(data["exploits"])
        train2, test2 = split_dataset(data["exploits"])
        assert [e["id"] for e in train1] == [e["id"] for e in train2]
        assert [e["id"] for e in test1]  == [e["id"] for e in test2]

    def test_train_test_disjoint(self):
        data = load_dataset()
        train, test = split_dataset(data["exploits"])
        train_ids = {e["id"] for e in train}
        test_ids  = {e["id"] for e in test}
        assert train_ids.isdisjoint(test_ids)

    def test_union_is_full_dataset(self):
        data = load_dataset()
        exploits = data["exploits"]
        train, test = split_dataset(exploits)
        all_ids = {e["id"] for e in exploits}
        split_ids = {e["id"] for e in train} | {e["id"] for e in test}
        assert all_ids == split_ids

    def test_proportional_split(self):
        data = load_dataset()
        exploits = data["exploits"]
        train, test = split_dataset(exploits)
        assert len(train) + len(test) == len(exploits)
        # Allow ±1 for rounding
        expected_train = int(len(exploits) * TRAIN_FRACTION)
        assert abs(len(train) - expected_train) <= 1

    def test_train_size_is_20_test_size_is_10(self):
        """With 30 exploits and 67% split, expect 20/10."""
        data = load_dataset()
        train, test = split_dataset(data["exploits"])
        assert len(train) == 20
        assert len(test) == 10


class TestStatisticalHelpers:
    def test_wilson_ci_basic(self):
        # 10/10 successes → high CI
        lo, hi = wilson_ci(10, 10)
        assert 0.5 < lo < 1.0
        assert hi == 1.0

    def test_wilson_ci_zero_successes(self):
        lo, hi = wilson_ci(0, 10)
        assert lo == 0.0
        assert 0.0 < hi < 0.5

    def test_wilson_ci_handles_zero_total(self):
        lo, hi = wilson_ci(0, 0)
        assert lo == 0.0
        assert hi == 1.0

    def test_cohen_d_zero_when_identical(self):
        d = cohen_d([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
        assert d == 0.0

    def test_cohen_d_positive_when_a_higher(self):
        d = cohen_d([3.0, 4.0, 5.0], [1.0, 2.0, 3.0])
        assert d > 0.0

    def test_cohen_d_negative_when_a_lower(self):
        d = cohen_d([1.0, 2.0, 3.0], [3.0, 4.0, 5.0])
        assert d < 0.0

    def test_bootstrap_ci_returns_tuple(self):
        ci = bootstrap_ci([1.0, 2.0, 3.0], [0.5, 1.0, 1.5])
        assert isinstance(ci, tuple)
        assert len(ci) == 2
        assert ci[0] <= ci[1]

    def test_bootstrap_ci_handles_empty(self):
        ci = bootstrap_ci([], [1.0, 2.0])
        assert ci == (0.0, 0.0)


class TestDatasetIntegrity:
    def test_dataset_has_30_exploits(self):
        data = load_dataset()
        assert len(data["exploits"]) == 30

    def test_each_exploit_has_attacker_address(self):
        data = load_dataset()
        for ex in data["exploits"]:
            assert "attacker_address" in ex
            assert ex["attacker_address"].startswith("0x")

    def test_each_exploit_has_id(self):
        data = load_dataset()
        for ex in data["exploits"]:
            assert "id" in ex
            assert ex["id"].startswith("EX")
