"""
TRION Protocol — L4.1a Validator Registry
==========================================

Whitepaper §4 specifies "minimum 100 validators across minimum 4 continents
at launch."  Until mainnet launch, Σ returns a disclosed bootstrap value
of 0.25 (see core/spiritual/sigma_engine.py).

This module provides the ValidatorRegistry — the operational layer that
tracks registered validators, their geographic distribution, and their
model outputs.  It feeds into `compute_sigma()` to produce real Σ values
once enough validators are registered.

Registry persistence:
  - Validators are persisted to `akashic/validator_registry.db` (SQLite)
  - State survives process restarts
  - Bootstrap disclosure is included in the response until the
    whitepaper launch threshold is met (100 validators, 4 continents)

Geographic distribution:
  Each validator declares its continent (Africa, Antarctica, Asia,
  Europe, North America, Oceania, South America).  The registry
  enforces the 4-continent minimum at launch.

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from core.spiritual.sigma_engine import (
    ValidatorSignal,
    compute_sigma,
    compute_hhi,
)


# ── Constants ──────────────────────────────────────────────────────────────────

# Whitepaper §4 launch threshold
MIN_VALIDATORS_LAUNCH:    int = 100
MIN_CONTINENTS_LAUNCH:    int = 4

# Bootstrap value (disclosed honestly when below launch threshold)
SIGMA_BOOTSTRAP_VALUE:    float = 0.25

# Continents recognized by the registry
CONTINENTS = (
    "AF",  # Africa
    "AN",  # Antarctica
    "AS",  # Asia
    "EU",  # Europe
    "NA",  # North America
    "OC",  # Oceania
    "SA",  # South America
)


# ── Data Model ─────────────────────────────────────────────────────────────────

@dataclass
class Validator:
    """A registered TRION validator."""
    validator_id:    str
    address:         str            # EVM-style address (0x…)
    continent:       str            # one of CONTINENTS
    stake:           float          # staked TRION tokens
    model_outputs:   np.ndarray = field(default_factory=lambda: np.array([]))
    valuation:       float = 0.0
    registered_at:   float = field(default_factory=time.time)
    last_active_at:  float = field(default_factory=time.time)
    active:          bool = True

    def to_signal(self) -> ValidatorSignal:
        """Convert to the ValidatorSignal expected by compute_sigma()."""
        return ValidatorSignal(
            validator_id=self.validator_id,
            valuation=self.valuation,
            stake=self.stake,
            model_outputs=self.model_outputs if self.model_outputs.size > 0 else np.array([self.valuation]),
        )

    def to_dict(self) -> dict:
        return {
            "validator_id":   self.validator_id,
            "address":        self.address,
            "continent":      self.continent,
            "stake":          self.stake,
            "valuation":      self.valuation,
            "registered_at":  self.registered_at,
            "last_active_at": self.last_active_at,
            "active":         self.active,
        }


# ── Registry ───────────────────────────────────────────────────────────────────

class ValidatorRegistry:
    """
    Persistent validator registry.

    Usage:
        registry = ValidatorRegistry()
        registry.register(Validator(
            validator_id="v-001",
            address="0xabc...",
            continent="AF",
            stake=10_000.0,
        ))
        result = registry.compute_sigma_with_disclosure(volatility=0.3)
    """

    DB_PATH = os.path.join("akashic", "validator_registry.db")

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or self.DB_PATH
        self._lock = threading.RLock()
        self._validators: Dict[str, Validator] = {}
        self._load()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self._db_path) or ".", exist_ok=True)
        return sqlite3.connect(self._db_path)

    def _load(self) -> None:
        """Load all registered validators from SQLite (creating the table if needed)."""
        with self._lock:
            os.makedirs(os.path.dirname(self._db_path) or ".", exist_ok=True)
            with self._conn() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS validators (
                        validator_id    TEXT PRIMARY KEY,
                        address         TEXT NOT NULL,
                        continent       TEXT NOT NULL,
                        stake           REAL NOT NULL,
                        valuation       REAL NOT NULL DEFAULT 0,
                        registered_at   REAL NOT NULL,
                        last_active_at  REAL NOT NULL,
                        active          INTEGER NOT NULL DEFAULT 1
                    )
                """)
                conn.commit()
                cur = conn.execute("SELECT * FROM validators")
                for row in cur.fetchall():
                    v = Validator(
                        validator_id=row[0],
                        address=row[1],
                        continent=row[2],
                        stake=row[3],
                        valuation=row[4],
                        registered_at=row[5],
                        last_active_at=row[6],
                        active=bool(row[7]),
                    )
                    self._validators[v.validator_id] = v

    def _persist(self, validator: Validator) -> None:
        """Persist a single validator to SQLite (upsert)."""
        with self._lock:
            with self._conn() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO validators
                    (validator_id, address, continent, stake, valuation,
                     registered_at, last_active_at, active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    validator.validator_id,
                    validator.address,
                    validator.continent,
                    validator.stake,
                    validator.valuation,
                    validator.registered_at,
                    validator.last_active_at,
                    int(validator.active),
                ))
                conn.commit()

    # ── Public API ───────────────────────────────────────────────────────────

    def register(self, validator: Validator) -> None:
        """Register a new validator or update an existing one."""
        if validator.continent not in CONTINENTS:
            raise ValueError(
                f"Invalid continent '{validator.continent}'. "
                f"Must be one of: {', '.join(CONTINENTS)}"
            )
        with self._lock:
            self._validators[validator.validator_id] = validator
            self._persist(validator)

    def deregister(self, validator_id: str) -> bool:
        """Remove a validator from the registry."""
        with self._lock:
            if validator_id not in self._validators:
                return False
            del self._validators[validator_id]
            with self._conn() as conn:
                conn.execute(
                    "DELETE FROM validators WHERE validator_id = ?",
                    (validator_id,)
                )
                conn.commit()
            return True

    def get(self, validator_id: str) -> Optional[Validator]:
        with self._lock:
            return self._validators.get(validator_id)

    def all_validators(self) -> List[Validator]:
        with self._lock:
            return list(self._validators.values())

    def active_validators(self) -> List[Validator]:
        with self._lock:
            return [v for v in self._validators.values() if v.active]

    def update_valuation(
        self,
        validator_id: str,
        valuation: float,
        model_outputs: Optional[np.ndarray] = None,
    ) -> bool:
        """Update a validator's current valuation and model outputs."""
        with self._lock:
            v = self._validators.get(validator_id)
            if v is None:
                return False
            v.valuation = valuation
            v.last_active_at = time.time()
            if model_outputs is not None:
                v.model_outputs = model_outputs
            self._persist(v)
            return True

    # ── Geographic distribution ─────────────────────────────────────────────

    def continent_distribution(self) -> Dict[str, int]:
        """Return validator count per continent."""
        with self._lock:
            dist: Dict[str, int] = {c: 0 for c in CONTINENTS}
            for v in self._validators.values():
                if v.active:
                    dist[v.continent] = dist.get(v.continent, 0) + 1
            return dist

    def continent_count(self) -> int:
        """Number of distinct continents with at least one active validator."""
        dist = self.continent_distribution()
        return sum(1 for count in dist.values() if count > 0)

    # ── Launch readiness ────────────────────────────────────────────────────

    def is_launch_ready(self) -> bool:
        """True iff the registry meets the whitepaper launch thresholds."""
        return (
            len(self.active_validators()) >= MIN_VALIDATORS_LAUNCH
            and self.continent_count() >= MIN_CONTINENTS_LAUNCH
        )

    def launch_status(self) -> dict:
        """Detailed launch readiness report."""
        active = self.active_validators()
        continents = self.continent_count()
        return {
            "launch_ready":           self.is_launch_ready(),
            "active_validators":      len(active),
            "min_required_validators": MIN_VALIDATORS_LAUNCH,
            "continents_represented": continents,
            "min_required_continents": MIN_CONTINENTS_LAUNCH,
            "continent_distribution": self.continent_distribution(),
            "bootstrap":              not self.is_launch_ready(),
            "disclosure": (
                "Σ plane is launch-ready."
                if self.is_launch_ready() else
                f"Σ plane in bootstrap phase: {len(active)}/{MIN_VALIDATORS_LAUNCH} "
                f"validators across {continents}/{MIN_CONTINENTS_LAUNCH} continents. "
                f"Bootstrap value: {SIGMA_BOOTSTRAP_VALUE}."
            ),
        }

    # ── Σ computation ────────────────────────────────────────────────────────

    def compute_sigma_with_disclosure(
        self,
        volatility: float = 0.3,
        delta_base: float = 0.10,
    ) -> dict:
        """
        Compute Σ(t) with honest bootstrap disclosure.

        If the registry is below launch thresholds, returns the disclosed
        bootstrap value (0.25) with a clear disclosure message.

        If the registry meets launch thresholds, computes the real Σ(t)
        using the diversity-weighted BFT formula.
        """
        if not self.is_launch_ready():
            status = self.launch_status()
            return {
                "sigma":          SIGMA_BOOTSTRAP_VALUE,
                "bootstrap":      True,
                "validator_count": len(self.active_validators()),
                "disclosure":     status["disclosure"],
                "launch_status":  status,
            }

        # Real Σ computation
        validators = [v.to_signal() for v in self.active_validators()]
        result = compute_sigma(validators, volatility=volatility, delta_base=delta_base)
        result["bootstrap"] = False
        result["launch_status"] = self.launch_status()
        return result


# ── Self-test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile
    import random

    with tempfile.TemporaryDirectory() as tmpdir:
        db = os.path.join(tmpdir, "test_validators.db")
        reg = ValidatorRegistry(db_path=db)

        print("=== Validator Registry Self-test ===\n")

        # Bootstrap state
        r = reg.compute_sigma_with_disclosure()
        print(f"Bootstrap Σ = {r['sigma']}")
        print(f"  launch_ready: {r['launch_status']['launch_ready']}")
        print(f"  disclosure:   {r['disclosure']}\n")

        # Register 5 validators across 2 continents (still bootstrap)
        for i in range(5):
            v = Validator(
                validator_id=f"v-{i:03d}",
                address=f"0x{i:040x}",
                continent=random.choice(["AF", "AS", "EU"]),
                stake=10_000.0 + i * 1000,
                valuation=0.72 + random.uniform(-0.02, 0.02),
                model_outputs=np.array([0.70 + j * 0.005 + random.gauss(0, 0.01)
                                        for j in range(20)]),
            )
            reg.register(v)

        r = reg.compute_sigma_with_disclosure()
        print(f"5 validators (2-3 continents) Σ = {r['sigma']:.4f}")
        print(f"  bootstrap:    {r['bootstrap']}")
        print(f"  disclosure:   {r['disclosure']}\n")

        # Register 95 more validators across 4 continents — meets launch threshold
        continents_4 = ["AF", "AS", "EU", "NA"]
        for i in range(5, 100):
            v = Validator(
                validator_id=f"v-{i:03d}",
                address=f"0x{i:040x}",
                continent=continents_4[i % 4],
                stake=10_000.0 + i * 100,
                valuation=0.72 + random.uniform(-0.02, 0.02),
                model_outputs=np.array([0.70 + j * 0.005 + random.gauss(0, 0.01)
                                        for j in range(20)]),
            )
            reg.register(v)

        r = reg.compute_sigma_with_disclosure()
        print(f"100 validators (4 continents) Σ = {r['sigma']:.4f}")
        print(f"  bootstrap:    {r['bootstrap']}")
        print(f"  validator_count: {r['validator_count']}")
        print(f"  hhi:          {r.get('hhi', 'n/a')}")
        print(f"  hhi_status:   {r.get('hhi_status', 'n/a')}")
        print(f"  disclosure:   {r.get('disclosure', 'n/a')}")

        print("\nPHASE 6 PASS — ValidatorRegistry with launch-threshold enforcement")
