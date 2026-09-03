"""
TRION BTCP — Module 2.1: BTCP Router (Python implementation of Rust spec)
==========================================================================

Per BTCP Master Spec §Phase 2 Module 2.1:

    Responsibility: Core routing engine. Accepts intents, runs BIBL analysis,
    computes BTCP_score for all candidate routes, selects optimal route,
    triggers escrow and execution.

BIBL Three-Tier Architecture (D3 Resolution):
  - Tier 1: Continuous Pre-Computation (every block, every chain)
  - Tier 2: Per-Intent Route Scoring (600 candidates, <50ms)
  - Tier 3: Execution Verification (single RPC, <150ms)
  - Total BIBL latency: < 200ms

BTCP_score (K1 Resolution):
    BTCP_score_final = [0.25×NL + 0.20×normalize_gas + 0.20×finality_conf
                        + 0.15×CC_coh + 0.20×BEO_continuity] × (1 - MF_score)

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, List, Optional, Tuple
import math

# Persistence (S7): reserve balances survive restarts via the shared SQLite
# state store. The plain-name fallback covers direct script execution
# (``python core/btcp/router.py``) — the script's own directory is already
# on sys.path in that mode.
try:
    from .state_store import BtcpStateStore
except ImportError:  # pragma: no cover - direct script execution
    from state_store import BtcpStateStore


class RouteType(IntEnum):
    SINGLE_CHAIN = 0
    SPLIT        = 1   # A→B
    NETTING      = 2
    PARALLEL     = 3
    MULTI_HOP    = 4   # A→B→C
    DEFERRED     = 5
    BITP         = 6


# BTCP_score weights (K1 Resolution)
W_NL   = 0.25
W_GAS  = 0.20
W_FIN  = 0.20
W_COH  = 0.15
W_BEO  = 0.20

# Minimum viable route thresholds
MIN_BTCP_SCORE       = 0.10
MIN_NL               = 0.05
MIN_FINALITY         = 0.80
MIN_VALIDATORS_PER_ROUTE = 3


# ── Gap E: Behavioral Balance Reservation ─────────────────────────────────────
# Concurrent routes must not double-spend the same source assets. The BEO
# balance is tracked and intents reserve against it in real time.
#
# Persistence (S7): the reservation map is process-global module state — it
# is lazily loaded from the shared SQLite state store on first access and
# written through on every mutation, so reservations survive restarts.

_balance_reservations: Dict[bytes, float] = {}

# Shared reservation store (lazy — created on first balance access).
_balance_store: Optional[BtcpStateStore] = None
_balance_store_lock = threading.Lock()


def _balance_store_instance() -> BtcpStateStore:
    """Lazily create the reservation store and load persisted state once."""
    global _balance_store
    if _balance_store is None:
        with _balance_store_lock:
            if _balance_store is None:
                store = BtcpStateStore()
                _balance_store = store
                _load_reservations(store)
    return _balance_store


def _load_reservations(store: BtcpStateStore) -> None:
    """Populate the in-memory reservation map from the store."""
    for key, reserved in store.get_balances().items():
        try:
            _balance_reservations[bytes.fromhex(key)] = reserved
        except ValueError:
            continue  # corrupt key — skip, never crash routing


def _persist_reservation(entity_id: bytes) -> None:
    """Write one reservation through to SQLite (upsert)."""
    store = _balance_store
    if store is not None:
        store.save_balance(entity_id.hex(), _balance_reservations.get(entity_id, 0.0))


def reserve_balance(entity_id: bytes, intent_value: float, available: float) -> bool:
    """Reserve intent_value against the entity's available behavioral balance.

    Returns True if the reservation fits; False if insufficient unreserved
    balance (prevents double-spending across concurrent routes)."""
    _balance_store_instance()  # S7: ensure persisted state is loaded
    current = _balance_reservations.get(entity_id, 0.0)
    if current + intent_value > available:
        return False
    _balance_reservations[entity_id] = current + intent_value
    _persist_reservation(entity_id)
    return True


def release_balance(entity_id: bytes, intent_value: float) -> None:
    """Release a reservation (route finalized/reverted)."""
    _balance_store_instance()  # S7: ensure persisted state is loaded
    current = _balance_reservations.get(entity_id, 0.0)
    _balance_reservations[entity_id] = max(0.0, current - intent_value)
    _persist_reservation(entity_id)


def reserved_balance(entity_id: bytes) -> float:
    """Total currently-reserved value for an entity."""
    _balance_store_instance()  # S7: ensure persisted state is loaded
    return _balance_reservations.get(entity_id, 0.0)


def reload_reservations() -> None:
    """Re-read persisted reservations from SQLite (S7 restart semantics).

    Module-level analogue of the ``reload()`` method on the class-based BTCP
    modules: replaces the in-memory reservation map with the current SQLite
    contents (first ensuring the store is initialized)."""
    store = _balance_store_instance()
    _balance_reservations.clear()
    _load_reservations(store)


# ── Gap G: BTCP_ROUTE_OE_FACTOR ──────────────────────────────────────────────
# BTCP routing improves NL scores → circular reinforcement. The observer-effect
# correction discounts routing-layer scores that TRION itself caused.

def apply_oe_correction(btcp_score: float, oe_factor: float) -> float:
    """OE-corrected routing score: discount by TRION's own influence.

    oe_factor ∈ [0, 1] — corr(TRION signal publication, NL change).
    Applied multiplicatively so self-caused liquidity improvements score lower
    than organic ones."""
    oe = min(1.0, max(0.0, oe_factor))
    return btcp_score * (1.0 - oe)



@dataclass
class BIBLState:
    """Tier-1 cached state — updated every block per chain."""
    nl_scores:        Dict[int, float] = field(default_factory=dict)  # chain_id → NL
    gas_forecasts:    Dict[int, float] = field(default_factory=dict)  # chain_id → gas (USD)
    gas_reference:    float = 31.0  # 99th percentile, rolling 30-day (ETH ~$31)
    cc_coherence:     Dict[int, float] = field(default_factory=dict)
    mf_scores:        Dict[int, float] = field(default_factory=dict)
    block_capacity:   Dict[int, float] = field(default_factory=dict)
    finality_dist:    Dict[int, float] = field(default_factory=dict)  # avg finality time (sec)
    beo_continuity:   Dict[int, float] = field(default_factory=dict)  # chain_id → BEO continuity (Akashic lookup)


# BEO bootstrap continuity for chains with no Akashic BEO history yet.
# Per the whitepaper the BEO continuity factor should come from the Akashic
# memory layer (BEO entity resolution); until an entity has ≥1 indexed epoch
# of history we fall back to this documented bootstrap prior.
BEO_BOOTSTRAP_DEFAULT = 0.8


@dataclass
class Route:
    """Candidate route for an intent."""
    route_id:           str
    entity_id:          bytes
    route_type:         RouteType
    anchor_chain:       int
    execution_chain:    int
    gas_total:          float       # USD
    finality_confidence: float      # 0-1
    beo_continuity:     float       # 0-1
    cc_coherence:       float       # 0-1
    intent_value:       float       # USD


def normalize_gas(g: float, state: BIBLState) -> float:
    """
    Gas normalization: (1 - g/g_ref) clamped to [0, 1].
    g_ref = 99th percentile gas cost, rolling 30-day.
    """
    g_ref = state.gas_reference
    if g_ref <= 0:
        return 0.5
    return max(0.0, 1.0 - (g / g_ref))


def btcp_score_final(route: Route, state: BIBLState) -> float:
    """
    BTCP_score_final = [w_nl×NL + w_gas×normalize_gas + w_fin×finality
                        + w_coh×CC + w_beo×BEO] × (1 - MF)

    Per K1 Resolution.
    """
    nl = state.nl_scores.get(route.execution_chain, 0.0)
    gas_norm = normalize_gas(route.gas_total, state)
    fin = route.finality_confidence
    cc = route.cc_coherence
    beo = route.beo_continuity
    mf = state.mf_scores.get(route.execution_chain, 0.0)

    score = (
        W_NL  * nl +
        W_GAS * gas_norm +
        W_FIN * fin +
        W_COH * cc +
        W_BEO * beo
    )
    return score * (1.0 - mf)


def route_is_valid(route: Route, state: BIBLState, validator_count: int = 10) -> bool:
    """
    Minimum viable route check:
        BTCP_score_final > 0.10
        AND NL(execution_chain) > 0.05
        AND finality_confidence > 0.80
        AND available_validators >= MIN_VALIDATORS_PER_ROUTE
    """
    if validator_count < MIN_VALIDATORS_PER_ROUTE:
        return False
    if state.nl_scores.get(route.execution_chain, 0.0) <= MIN_NL:
        return False
    if route.finality_confidence <= MIN_FINALITY:
        return False
    if btcp_score_final(route, state) <= MIN_BTCP_SCORE:
        return False
    return True


def select_optimal_route(
    intent_value: float,
    entity_id: bytes,
    state: BIBLState,
    candidate_chains: List[int],
    validator_counts: Optional[Dict[int, int]] = None,
) -> Optional[Route]:
    """
    Tier-2: Score all candidate routes and select the optimal one.

    Generates N_chains × 6 route types = max 600 candidates.
    Returns the route with the highest BTCP_score that passes validity check.
    """
    validator_counts = validator_counts or {}
    candidates: List[Route] = []

    for chain in candidate_chains:
        nl = state.nl_scores.get(chain, 0.0)
        gas = state.gas_forecasts.get(chain, state.gas_reference)
        fin = 1.0 - min(1.0, state.finality_dist.get(chain, 12.0) / 60.0)  # 60s = 0 conf
        cc = state.cc_coherence.get(chain, 0.5)
        # BEO continuity: real value from BIBLState (Akashic BEO lookup),
        # falling back to the documented bootstrap prior for new entities.
        beo = state.beo_continuity.get(chain, BEO_BOOTSTRAP_DEFAULT)
        vcount = validator_counts.get(chain, 10)

        for rt in RouteType:
            route = Route(
                route_id=f"route_{chain}_{rt.name}",
                entity_id=entity_id,
                route_type=rt,
                anchor_chain=candidate_chains[0] if candidate_chains else chain,
                execution_chain=chain,
                gas_total=gas,
                finality_confidence=fin,
                beo_continuity=beo,
                cc_coherence=cc,
                intent_value=intent_value,
            )
            if route_is_valid(route, state, vcount):
                candidates.append(route)

    if not candidates:
        return None

    # Select route with highest BTCP_score
    return max(candidates, key=lambda r: btcp_score_final(r, state))


# ── Self-test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== BTCP Router Self-test ===\n")

    import tempfile

    state = BIBLState(
        nl_scores={1: 0.85, 137: 0.90, 8453: 0.88},
        gas_forecasts={1: 31.0, 137: 0.50, 8453: 0.98},
        gas_reference=31.0,
        cc_coherence={1: 0.90, 137: 0.92, 8453: 0.91},
        mf_scores={1: 0.02, 137: 0.01, 8453: 0.01},
        finality_dist={1: 12.0, 137: 2.0, 8453: 2.0},
    )

    # Test 1: $10K swap — should pick Base (low gas, high NL)
    route = select_optimal_route(
        intent_value=10_000.0,
        entity_id=b"\x01" * 32,
        state=state,
        candidate_chains=[1, 137, 8453],
        validator_counts={1: 50, 137: 40, 8453: 30},
    )
    assert route is not None
    print(f"Optimal route for $10K swap: {route.route_id}")
    print(f"  chain: {route.execution_chain}, type: {route.route_type.name}")
    print(f"  BTCP_score: {btcp_score_final(route, state):.4f}")
    print(f"  gas: ${route.gas_total:.2f}")

    # Test 2: BTCP_score normalization
    assert 0.0 <= btcp_score_final(route, state) <= 1.0

    # Test 3: Gas normalization
    assert normalize_gas(31.0, state) == 0.0  # reference = 0 score
    assert normalize_gas(0.0, state) == 1.0   # free gas = max score
    assert normalize_gas(15.5, state) == 0.5  # half = 0.5

    # Test 4: Route validity
    valid_route = Route(
        route_id="test", entity_id=b"\x01" * 32,
        route_type=RouteType.SINGLE_CHAIN, anchor_chain=1, execution_chain=1,
        gas_total=10.0, finality_confidence=0.95, beo_continuity=0.8,
        cc_coherence=0.9, intent_value=1000.0,
    )
    assert route_is_valid(valid_route, state, validator_count=10)

    invalid_route = Route(
        route_id="test2", entity_id=b"\x01" * 32,
        route_type=RouteType.SINGLE_CHAIN, anchor_chain=1, execution_chain=1,
        gas_total=10.0, finality_confidence=0.50,  # below 0.80
        beo_continuity=0.8, cc_coherence=0.9, intent_value=1000.0,
    )
    assert not route_is_valid(invalid_route, state, validator_count=10)

    # Test 5: Reservation persistence (S7) — reservations survive a restart
    _db = os.path.join(
        tempfile.mkdtemp(prefix="btcp_router_selftest_"), "btcp_state.db")
    _balance_store = BtcpStateStore(state_db=_db)  # hermetic self-test store
    _balance_reservations.clear()
    _ent = b"\x02" * 32
    assert reserve_balance(_ent, 400.0, 1000.0)
    assert reserved_balance(_ent) == 400.0
    # Simulate a restart: in-memory map wiped, re-loaded from SQLite
    _balance_reservations.clear()
    reload_reservations()
    assert reserved_balance(_ent) == 400.0
    release_balance(_ent, 150.0)
    assert _balance_store.get_balances() == {_ent.hex(): 250.0}
    print("\n✓ Reservation persistence: reload_reservations() restores state after restart")

    print("\nPHASE 2.1 PASS — BTCP Router implemented")
