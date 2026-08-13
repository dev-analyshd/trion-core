"""
TRION Protocol — L14.1 Initialization Ceremony (INIT_valid)

Whitepaper §14.1: TRION does not emit signals before INIT_valid = TRUE.

INIT_valid iff all_of:
    N_validators >= 100
    geographic_coverage >= 4 continents
    D_akashic >= D_minimum (10,000)
    N_chains_indexed >= 3
    SEC_bootstrapped = TRUE
    Love(system, t₀) > 0

Before INIT_valid:
    - Only BOOTSTRAP and SILENCE signals allowed
    - No VALUATION emission
    - All consuming protocols receive SILENCE

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class InitState:
    """Current initialization ceremony state."""
    n_validators: int = 0
    n_continents: int = 0
    akashic_depth: float = 0.0
    n_chains_indexed: int = 0
    sec_bootstrapped: bool = False
    love_score: float = 0.0
    init_completed: bool = False
    init_timestamp: Optional[float] = None

    # Thresholds (WP1 §14.1)
    MIN_VALIDATORS = 100
    MIN_CONTINENTS = 4
    MIN_AKASHIC_DEPTH = 10_000
    MIN_CHAINS = 3

    @property
    def init_valid(self) -> bool:
        """INIT_valid iff all conditions met."""
        return (
            self.n_validators >= self.MIN_VALIDATORS
            and self.n_continents >= self.MIN_CONTINENTS
            and self.akashic_depth >= self.MIN_AKASHIC_DEPTH
            and self.n_chains_indexed >= self.MIN_CHAINS
            and self.sec_bootstrapped
            and self.love_score > 0
        )

    @property
    def signal_emission_allowed(self) -> bool:
        """Only BOOTSTRAP and SILENCE before INIT_valid."""
        return self.init_valid

    def missing_conditions(self) -> list:
        """List conditions not yet met."""
        missing = []
        if self.n_validators < self.MIN_VALIDATORS:
            missing.append(f"N_validators: {self.n_validators}/{self.MIN_VALIDATORS}")
        if self.n_continents < self.MIN_CONTINENTS:
            missing.append(f"Continents: {self.n_continents}/{self.MIN_CONTINENTS}")
        if self.akashic_depth < self.MIN_AKASHIC_DEPTH:
            missing.append(f"D_akashic: {self.akashic_depth:.0f}/{self.MIN_AKASHIC_DEPTH}")
        if self.n_chains_indexed < self.MIN_CHAINS:
            missing.append(f"N_chains: {self.n_chains_indexed}/{self.MIN_CHAINS}")
        if not self.sec_bootstrapped:
            missing.append("SEC_bootstrapped: FALSE")
        if self.love_score <= 0:
            missing.append("Love(system, t₀) <= 0")
        return missing

    def check_and_complete(self) -> bool:
        """Check if all conditions met and complete ceremony if so."""
        if self.init_valid and not self.init_completed:
            self.init_completed = True
            self.init_timestamp = time.time()
            return True
        return False


# Module-level singleton
_state = InitState()


def get_init_state() -> InitState:
    """Get the global initialization state."""
    return _state


def update_init_state(
    n_validators: Optional[int] = None,
    n_continents: Optional[int] = None,
    akashic_depth: Optional[float] = None,
    n_chains_indexed: Optional[int] = None,
    sec_bootstrapped: Optional[bool] = None,
    love_score: Optional[float] = None,
) -> InitState:
    """Update initialization state and check for completion."""
    global _state
    if n_validators is not None:
        _state.n_validators = n_validators
    if n_continents is not None:
        _state.n_continents = n_continents
    if akashic_depth is not None:
        _state.akashic_depth = akashic_depth
    if n_chains_indexed is not None:
        _state.n_chains_indexed = n_chains_indexed
    if sec_bootstrapped is not None:
        _state.sec_bootstrapped = sec_bootstrapped
    if love_score is not None:
        _state.love_score = love_score
    _state.check_and_complete()
    return _state


def is_signal_type_allowed(signal_type: str) -> bool:
    """Before INIT_valid, only BOOTSTRAP and SILENCE signals are allowed."""
    if _state.init_valid:
        return True  # All signal types allowed after INIT_valid
    allowed_before_init = {"BOOTSTRAP", "SILENCE"}
    return signal_type.upper() in allowed_before_init


if __name__ == "__main__":
    state = get_init_state()
    print(f"INIT_valid: {state.init_valid}")
    print(f"Missing: {state.missing_conditions()}")

    # Simulate meeting conditions
    update_init_state(
        n_validators=100, n_continents=4, akashic_depth=15000,
        n_chains_indexed=5, sec_bootstrapped=True, love_score=1.0
    )
    print(f"After update — INIT_valid: {state.init_valid}")
    print(f"Completed: {state.init_completed}")
    print(f"Signal emission allowed: {state.signal_emission_allowed}")
    assert state.init_valid
    assert is_signal_type_allowed("VALUATION")
    print("INIT_valid ceremony: PASS")
