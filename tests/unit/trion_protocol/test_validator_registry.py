"""
Phase 6 — Validator Registry tests
==================================
Verifies the ValidatorRegistry that tracks registered validators and
enforces the whitepaper §4 launch threshold (100 validators across
4 continents).
"""
import os
import tempfile
import numpy as np
import pytest

from core.spiritual.validator_registry import (
    CONTINENTS,
    MIN_CONTINENTS_LAUNCH,
    MIN_VALIDATORS_LAUNCH,
    SIGMA_BOOTSTRAP_VALUE,
    Validator,
    ValidatorRegistry,
)


@pytest.fixture
def registry():
    """A fresh registry backed by a temporary SQLite DB."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db = os.path.join(tmpdir, "test_validators.db")
        yield ValidatorRegistry(db_path=db)


@pytest.fixture
def sample_validator():
    return Validator(
        validator_id="v-001",
        address="0xabc",
        continent="AF",
        stake=10_000.0,
        valuation=0.72,
        model_outputs=np.array([0.70, 0.71, 0.72]),
    )


# ── Registration tests ─────────────────────────────────────────────────────────

class TestRegistration:
    def test_register_one_validator(self, registry, sample_validator):
        registry.register(sample_validator)
        assert len(registry.all_validators()) == 1
        assert registry.get("v-001") is not None

    def test_register_rejects_invalid_continent(self, registry, sample_validator):
        sample_validator.continent = "XX"
        with pytest.raises(ValueError, match="Invalid continent"):
            registry.register(sample_validator)

    def test_deregister_removes_validator(self, registry, sample_validator):
        registry.register(sample_validator)
        assert registry.deregister("v-001") is True
        assert registry.get("v-001") is None
        assert registry.deregister("v-001") is False  # already removed

    def test_persistence_across_instances(self, sample_validator):
        """Registry state should survive restart via SQLite."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = os.path.join(tmpdir, "test_validators.db")
            r1 = ValidatorRegistry(db_path=db)
            r1.register(sample_validator)

            r2 = ValidatorRegistry(db_path=db)
            assert len(r2.all_validators()) == 1
            assert r2.get("v-001") is not None
            assert r2.get("v-001").continent == "AF"

    def test_update_valuation(self, registry, sample_validator):
        # Force a known earlier timestamp so the update is provably later
        sample_validator.last_active_at = 1000.0
        registry.register(sample_validator)
        new_outputs = np.array([0.80, 0.81, 0.82])
        ok = registry.update_valuation("v-001", 0.80, model_outputs=new_outputs)
        assert ok is True
        v = registry.get("v-001")
        assert v.valuation == 0.80
        assert v.last_active_at > 1000.0

    def test_update_nonexistent_validator_returns_false(self, registry):
        assert registry.update_valuation("nonexistent", 0.5) is False


# ── Geographic distribution tests ──────────────────────────────────────────────

class TestGeographicDistribution:
    def test_empty_registry_has_zero_continents(self, registry):
        assert registry.continent_count() == 0

    def test_one_validator_per_continent(self, registry):
        for i, c in enumerate(["AF", "AS", "EU", "NA"]):
            v = Validator(
                validator_id=f"v-{i}",
                address=f"0x{i:040x}",
                continent=c,
                stake=1000.0,
            )
            registry.register(v)
        assert registry.continent_count() == 4
        dist = registry.continent_distribution()
        assert dist["AF"] == 1
        assert dist["AS"] == 1
        assert dist["EU"] == 1
        assert dist["NA"] == 1

    def test_inactive_validators_excluded_from_distribution(self, registry):
        v1 = Validator(validator_id="v-1", address="0x1", continent="AF", stake=100.0, active=True)
        v2 = Validator(validator_id="v-2", address="0x2", continent="AS", stake=100.0, active=False)
        registry.register(v1)
        registry.register(v2)
        assert registry.continent_count() == 1  # only AF counts


# ── Launch readiness tests ─────────────────────────────────────────────────────

class TestLaunchReadiness:
    def test_empty_registry_not_launch_ready(self, registry):
        assert registry.is_launch_ready() is False

    def test_few_validators_not_launch_ready(self, registry):
        for i in range(50):
            v = Validator(
                validator_id=f"v-{i}",
                address=f"0x{i:040x}",
                continent="AF",
                stake=1000.0,
            )
            registry.register(v)
        # 50 validators but only 1 continent
        assert registry.is_launch_ready() is False

    def test_four_continents_few_validators_not_launch_ready(self, registry):
        for i in range(50):
            v = Validator(
                validator_id=f"v-{i}",
                address=f"0x{i:040x}",
                continent=["AF", "AS", "EU", "NA"][i % 4],
                stake=1000.0,
            )
            registry.register(v)
        # 50 validators across 4 continents — still below 100 threshold
        assert registry.is_launch_ready() is False

    def test_launch_ready_at_100_validators_4_continents(self, registry):
        for i in range(100):
            v = Validator(
                validator_id=f"v-{i}",
                address=f"0x{i:040x}",
                continent=["AF", "AS", "EU", "NA"][i % 4],
                stake=1000.0,
                valuation=0.72,
                model_outputs=np.array([0.70, 0.71, 0.72, 0.73]),
            )
            registry.register(v)
        assert registry.is_launch_ready() is True

    def test_launch_status_report(self, registry):
        status = registry.launch_status()
        assert "launch_ready" in status
        assert "active_validators" in status
        assert "min_required_validators" in status
        assert status["min_required_validators"] == MIN_VALIDATORS_LAUNCH
        assert status["min_required_continents"] == MIN_CONTINENTS_LAUNCH
        assert "disclosure" in status


# ── Σ computation tests ────────────────────────────────────────────────────────

class TestSigmaComputation:
    def test_bootstrap_returns_disclosed_value(self, registry):
        result = registry.compute_sigma_with_disclosure()
        assert result["sigma"] == SIGMA_BOOTSTRAP_VALUE
        assert result["bootstrap"] is True
        assert "disclosure" in result
        assert "bootstrap" in result["disclosure"].lower()

    def test_real_sigma_computed_when_launch_ready(self, registry):
        np.random.seed(42)
        for i in range(100):
            v = Validator(
                validator_id=f"v-{i}",
                address=f"0x{i:040x}",
                continent=["AF", "AS", "EU", "NA"][i % 4],
                stake=1000.0 + i * 100,
                valuation=0.72 + np.random.normal(0, 0.02),
                model_outputs=np.array([0.70 + j * 0.005 + np.random.normal(0, 0.01)
                                        for j in range(20)]),
            )
            registry.register(v)
        result = registry.compute_sigma_with_disclosure()
        assert result["bootstrap"] is False
        assert "sigma" in result
        assert 0.0 <= result["sigma"] <= 1.0
        assert result["validator_count"] == 100


# ── Constants tests ────────────────────────────────────────────────────────────

class TestConstants:
    def test_min_validators_is_100(self):
        assert MIN_VALIDATORS_LAUNCH == 100

    def test_min_continents_is_4(self):
        assert MIN_CONTINENTS_LAUNCH == 4

    def test_bootstrap_value_is_0_25(self):
        assert SIGMA_BOOTSTRAP_VALUE == 0.25

    def test_seven_continents_recognized(self):
        assert len(CONTINENTS) == 7
        assert "AF" in CONTINENTS
        assert "AS" in CONTINENTS
        assert "EU" in CONTINENTS
        assert "NA" in CONTINENTS
        assert "SA" in CONTINENTS
        assert "OC" in CONTINENTS
        assert "AN" in CONTINENTS
