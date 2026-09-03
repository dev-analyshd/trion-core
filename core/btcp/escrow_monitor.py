"""
TRION BTCP — Module 2.2: Escrow Monitor
========================================

Per BTCP Master Spec §Phase 2 Module 2.2:

    Responsibility: Watches BTCP_ESCROW contract states across all chains.
    Triggers release/revert based on TRION consensus signals. Handles
    timeouts and emergency conditions.

State Machine per Escrow:
    IDLE → HOLDING (on lock)
    HOLDING → PENDING_AKASHIC (if Akashic unavailable at execution time)
    HOLDING → RELEASED (on valid BTCP_ROUTE signal with execution_confirmed)
    HOLDING → REVERTED (on timeout OR execution_confirmed=FALSE)
    PENDING_AKASHIC → RELEASED/REVERTED (on Akashic recovery within 24h)
    PENDING_AKASHIC → REVERTED (after 24h Akashic outage)
    ANY → EMERGENCY_REVERTED (after 7 days, any cause, callable by anyone)

Multi-Hop Cascade Revert (Gap 9):
    - ESCROW_2 timeout < ESCROW_1 timeout always
    - If ESCROW_2 reverts → REVERT_CASCADE → ESCROW_1 reverts
    - ESCROW_1 holds until reverse route confirms

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, List, Optional

# Persistence (S7): escrow states survive restarts via the shared SQLite
# state store. The plain-name fallback covers direct script execution
# (``python core/btcp/escrow_monitor.py``) — the script's own directory is
# already on sys.path in that mode.
try:
    from .state_store import BtcpStateStore
except ImportError:  # pragma: no cover - direct script execution
    from state_store import BtcpStateStore


class EscrowState(IntEnum):
    IDLE                = 0
    HOLDING             = 1
    PENDING_AKASHIC     = 2
    RELEASED            = 3
    REVERTED            = 4
    EMERGENCY_REVERTED  = 5


class RevertReason(IntEnum):
    TIMEOUT              = 0
    COHERENCE_FAILURE    = 1
    ROUTE_INVALID        = 2
    MANUAL               = 3
    AKASHIC_OUTAGE_24H   = 4
    CASCADE_REVERT       = 5
    EMERGENCY_ESCAPE     = 6


EMERGENCY_ESCAPE_SECONDS = 7 * 24 * 3600   # 7 days
AKASHIC_RECOVERY_SECONDS = 24 * 3600       # 24 hours


@dataclass
class Escrow:
    escrow_id:       str
    route_id:        str
    entity_id:       bytes
    amount:          float
    lock_block:      int
    lock_timestamp:  float
    timeout_blocks:  int
    state:           EscrowState = EscrowState.HOLDING
    revert_reason:   RevertReason = RevertReason.TIMEOUT
    settled_at:      Optional[float] = None
    reverted_at:     Optional[float] = None
    parent_escrow_id: Optional[str] = None  # for cascade revert
    settlement_verified: bool = False


# ── Persistence (S7) ─────────────────────────────────────────────────────────
# Explicit row serialization: bytes / IntEnum / None fields are not directly
# JSON-serializable, so Escrow ⇄ row conversion is written out by hand.

ESCROW_ROW_TYPE = "escrow_v1"


def _escrow_to_row(esc: Escrow) -> Dict[str, object]:
    """Escrow → JSON-safe row dict for BtcpStateStore."""
    return {
        "escrow_id":           esc.escrow_id,
        "route_id":            esc.route_id,
        "entity_id":           esc.entity_id.hex(),
        "amount":              esc.amount,
        "lock_block":          esc.lock_block,
        "lock_timestamp":      esc.lock_timestamp,
        "timeout_blocks":      esc.timeout_blocks,
        "state":               esc.state.name,
        "revert_reason":       esc.revert_reason.name,
        "settled_at":          esc.settled_at,
        "reverted_at":         esc.reverted_at,
        "parent_escrow_id":    esc.parent_escrow_id,
        "settlement_verified": esc.settlement_verified,
    }


def _escrow_from_row(row: Dict[str, object]) -> Escrow:
    """Row dict → Escrow (inverse of _escrow_to_row)."""
    return Escrow(
        escrow_id=row["escrow_id"],
        route_id=row["route_id"],
        entity_id=bytes.fromhex(row["entity_id"]),
        amount=float(row["amount"]),
        lock_block=int(row["lock_block"]),
        lock_timestamp=float(row["lock_timestamp"]),
        timeout_blocks=int(row["timeout_blocks"]),
        state=EscrowState[row["state"]],
        revert_reason=RevertReason[row["revert_reason"]],
        settled_at=row.get("settled_at"),
        reverted_at=row.get("reverted_at"),
        parent_escrow_id=row.get("parent_escrow_id"),
        settlement_verified=bool(row.get("settlement_verified", False)),
    )


class EscrowMonitor:
    """
    Monitors escrow states and triggers transitions.

    In production, this would be a Rust service subscribing to chain events.
    Here it's a Python state machine for testing and integration — with its
    mutable state write-through persisted to SQLite (S7): a restart reloads
    escrows instead of wiping them.

    ``state_db``: optional SQLite path (default: env TRION_STATE_DB, then
    ``db/btcp_state.db``; test-context constructions get an isolated temp
    store — see core/btcp/state_store.py).
    """

    def __init__(self, state_db: Optional[str] = None):
        self._store = BtcpStateStore(state_db)
        self._escrows: Dict[str, Escrow] = {}
        self._load()

    # ── Persistence (S7) ────────────────────────────────────────────────

    def _load(self) -> None:
        """Load persisted escrows into memory (malformed rows are skipped)."""
        for escrow_id, (type_tag, row) in self._store.get_escrows().items():
            if type_tag != ESCROW_ROW_TYPE:
                continue
            try:
                self._escrows[escrow_id] = _escrow_from_row(row)
            except (KeyError, ValueError, TypeError):
                print(
                    f"[btcp.escrow_monitor] skipping malformed persisted escrow "
                    f"{escrow_id!r}",
                    file=sys.stderr,
                )

    def _persist(self, escrow_id: str) -> None:
        """Write one escrow through to SQLite (upsert)."""
        esc = self._escrows.get(escrow_id)
        if esc is None:
            return
        self._store.save_escrow(escrow_id, _escrow_to_row(esc), ESCROW_ROW_TYPE)

    def reload(self) -> None:
        """Re-read persisted escrow state from SQLite, replacing memory."""
        self._escrows = {}
        self._load()

    def lock_escrow(
        self,
        escrow_id: str,
        route_id: str,
        entity_id: bytes,
        amount: float,
        timeout_blocks: int,
        parent_escrow_id: Optional[str] = None,
        block_number: int = 1,
        timestamp: Optional[float] = None,
    ) -> Escrow:
        """Lock a new escrow. State → HOLDING."""
        if escrow_id in self._escrows:
            raise ValueError(f"Escrow {escrow_id} already exists")
        ts = timestamp if timestamp is not None else time.time()
        esc = Escrow(
            escrow_id=escrow_id,
            route_id=route_id,
            entity_id=entity_id,
            amount=amount,
            lock_block=block_number,
            lock_timestamp=ts,
            timeout_blocks=timeout_blocks,
            state=EscrowState.HOLDING,
            parent_escrow_id=parent_escrow_id,
        )
        self._escrows[escrow_id] = esc
        self._persist(escrow_id)
        return esc

    def verify_settlement(self, escrow_id: str) -> bool:
        """G1 Resolution: Two-Phase Confirmation."""
        esc = self._escrows.get(escrow_id)
        if not esc or esc.state != EscrowState.HOLDING:
            return False
        esc.settlement_verified = True
        self._persist(escrow_id)
        return True

    def release_escrow(
        self,
        escrow_id: str,
        coherence: float,
        min_coherence: float = 0.55,
        block_number: Optional[int] = None,
    ) -> bool:
        """Release escrow. Requires settlement verified + coherence >= threshold."""
        esc = self._escrows.get(escrow_id)
        if not esc:
            return False
        if esc.state != EscrowState.HOLDING:
            return False
        if not esc.settlement_verified:
            return False  # G1: settlement must be verified first
        if coherence < min_coherence:
            return False
        # Check timeout
        if block_number is not None and block_number > esc.lock_block + esc.timeout_blocks:
            return False

        esc.state = EscrowState.RELEASED
        esc.settled_at = time.time()
        self._persist(escrow_id)
        return True

    def enter_pending_akashic(self, escrow_id: str) -> bool:
        """E1: Akashic unavailable — enter PENDING_AKASHIC state."""
        esc = self._escrows.get(escrow_id)
        if not esc or esc.state != EscrowState.HOLDING:
            return False
        esc.state = EscrowState.PENDING_AKASHIC
        self._persist(escrow_id)
        return True

    def release_from_pending_akashic(
        self, escrow_id: str, coherence: float, min_coherence: float = 0.55,
    ) -> bool:
        """E1: Release after Akashic recovery (within 24h)."""
        esc = self._escrows.get(escrow_id)
        if not esc or esc.state != EscrowState.PENDING_AKASHIC:
            return False
        if time.time() > esc.lock_timestamp + AKASHIC_RECOVERY_SECONDS:
            return False  # 24h window expired
        if coherence < min_coherence:
            return False
        esc.state = EscrowState.RELEASED
        esc.settled_at = time.time()
        self._persist(escrow_id)
        return True

    def revert_escrow(
        self,
        escrow_id: str,
        reason: RevertReason,
        block_number: Optional[int] = None,
    ) -> bool:
        """Revert escrow. Triggers cascade revert if parent exists."""
        esc = self._escrows.get(escrow_id)
        if not esc:
            return False
        if esc.state not in (EscrowState.HOLDING, EscrowState.PENDING_AKASHIC):
            return False

        # Check if Akashic window expired (auto-revert)
        if esc.state == EscrowState.PENDING_AKASHIC:
            if time.time() > esc.lock_timestamp + AKASHIC_RECOVERY_SECONDS:
                reason = RevertReason.AKASHIC_OUTAGE_24H
        # Check timeout
        elif block_number is not None and block_number > esc.lock_block + esc.timeout_blocks:
            reason = RevertReason.TIMEOUT

        esc.state = EscrowState.REVERTED
        esc.revert_reason = reason
        esc.reverted_at = time.time()
        self._persist(escrow_id)

        # Cascade revert parent
        if esc.parent_escrow_id:
            self._cascade_revert(esc.parent_escrow_id, escrow_id)

        return True

    def revert_emergency(self, escrow_id: str) -> bool:
        """
        Gap 8: Emergency Escape Hatch.
        After 7 days, ANYONE can trigger revert — no TRION signal needed.
        """
        esc = self._escrows.get(escrow_id)
        if not esc:
            return False
        if esc.state not in (EscrowState.HOLDING, EscrowState.PENDING_AKASHIC):
            return False
        if time.time() < esc.lock_timestamp + EMERGENCY_ESCAPE_SECONDS:
            return False  # 7 days not yet elapsed

        esc.state = EscrowState.EMERGENCY_REVERTED
        esc.revert_reason = RevertReason.EMERGENCY_ESCAPE
        esc.reverted_at = time.time()
        self._persist(escrow_id)

        # Cascade to parent
        if esc.parent_escrow_id:
            self._cascade_revert(esc.parent_escrow_id, escrow_id)

        return True

    def _cascade_revert(self, parent_id: str, child_id: str) -> None:
        """Gap 9: Cascade revert for multi-hop nested escrows."""
        parent = self._escrows.get(parent_id)
        if not parent:
            return
        if parent.state not in (EscrowState.HOLDING, EscrowState.PENDING_AKASHIC):
            return

        parent.state = EscrowState.REVERTED
        parent.revert_reason = RevertReason.CASCADE_REVERT
        parent.reverted_at = time.time()
        self._persist(parent_id)

        # Recursively cascade to grandparent
        if parent.parent_escrow_id:
            self._cascade_revert(parent.parent_escrow_id, parent_id)

    def get_escrow(self, escrow_id: str) -> Optional[Escrow]:
        return self._escrows.get(escrow_id)

    def all_escrows(self) -> List[Escrow]:
        return list(self._escrows.values())

    def emergency_escape_available(self, escrow_id: str) -> bool:
        esc = self._escrows.get(escrow_id)
        if not esc:
            return False
        return (esc.state in (EscrowState.HOLDING, EscrowState.PENDING_AKASHIC) and
                time.time() >= esc.lock_timestamp + EMERGENCY_ESCAPE_SECONDS)


# ── Self-test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Escrow Monitor Self-test ===\n")

    # Hermetic self-test DB (S7): persistence is exercised without touching
    # the shared production store.
    import os as _os
    import tempfile as _tempfile
    _db = _os.path.join(_tempfile.mkdtemp(prefix="btcp_escrow_selftest_"), "btcp_state.db")

    mon = EscrowMonitor(state_db=_db)

    # Test 1: Normal lock → release
    mon.lock_escrow("esc1", "route1", b"\x01" * 32, 1000.0, 1000, block_number=100)
    assert mon.verify_settlement("esc1")
    assert mon.release_escrow("esc1", coherence=0.80, min_coherence=0.55, block_number=200)
    esc = mon.get_escrow("esc1")
    assert esc.state == EscrowState.RELEASED
    print(f"✓ Normal release: state={esc.state.name}")

    # Test 2: Timeout revert
    mon.lock_escrow("esc2", "route2", b"\x02" * 32, 500.0, 100, block_number=100)
    assert mon.revert_escrow("esc2", RevertReason.TIMEOUT, block_number=300)
    esc = mon.get_escrow("esc2")
    assert esc.state == EscrowState.REVERTED
    assert esc.revert_reason == RevertReason.TIMEOUT
    print(f"✓ Timeout revert: state={esc.state.name}, reason={esc.revert_reason.name}")

    # Test 3: Cascade revert (multi-hop)
    mon.lock_escrow("parent", "route_p", b"\x03" * 32, 2000.0, 1000, block_number=100)
    mon.lock_escrow("child", "route_c", b"\x03" * 32, 1500.0, 500,
                    parent_escrow_id="parent", block_number=100)
    # Child reverts → parent should cascade
    assert mon.revert_escrow("child", RevertReason.TIMEOUT, block_number=700)
    assert mon.get_escrow("child").state == EscrowState.REVERTED
    assert mon.get_escrow("parent").state == EscrowState.REVERTED
    assert mon.get_escrow("parent").revert_reason == RevertReason.CASCADE_REVERT
    print(f"✓ Cascade revert: child → parent reverted")

    # Test 4: PENDING_AKASHIC → release within 24h
    mon.lock_escrow("esc3", "route3", b"\x04" * 32, 750.0, 1000, block_number=100)
    assert mon.enter_pending_akashic("esc3")
    assert mon.get_escrow("esc3").state == EscrowState.PENDING_AKASHIC
    assert mon.release_from_pending_akashic("esc3", coherence=0.70, min_coherence=0.55)
    assert mon.get_escrow("esc3").state == EscrowState.RELEASED
    print(f"✓ PENDING_AKASHIC → release within 24h")

    # Test 5: Emergency escape (7 days)
    import time as _time
    old_time = _time.time
    try:
        # Mock time to be 8 days later
        _time.time = lambda: old_time() + 8 * 86400
        mon.lock_escrow("esc4", "route4", b"\x05" * 32, 999.0, 100,
                        block_number=100, timestamp=old_time())
        # Restore time for the lock, then advance
        _time.time = old_time
        esc = mon.get_escrow("esc4")
        esc.lock_timestamp = old_time() - 8 * 86400  # locked 8 days ago
        assert mon.emergency_escape_available("esc4")
        assert mon.revert_emergency("esc4")
        assert mon.get_escrow("esc4").state == EscrowState.EMERGENCY_REVERTED
        print(f"✓ Emergency escape after 7 days")
    finally:
        _time.time = old_time

    # Test 6: Persistence (S7) — a second monitor on the same DB sees the
    # escrows and their terminal states; reload() re-reads from SQLite.
    mon2 = EscrowMonitor(state_db=_db)
    assert mon2.get_escrow("esc1") is not None
    assert mon2.get_escrow("esc1").state == EscrowState.RELEASED
    assert mon2.get_escrow("esc1").settlement_verified  # two-phase flag survived
    assert mon2.get_escrow("parent").state == EscrowState.REVERTED
    assert mon2.get_escrow("parent").revert_reason == RevertReason.CASCADE_REVERT
    assert mon2.get_escrow("child").revert_reason == RevertReason.TIMEOUT
    mon2.lock_escrow("esc5", "route5", b"\x06" * 32, 123.0, 100, block_number=100)
    mon.reload()
    assert mon.get_escrow("esc5") is not None  # reload picked up mon2's write
    print("✓ Persistence: second instance + reload() see escrow state")

    print("\nPHASE 2.2 PASS — Escrow Monitor implemented")
