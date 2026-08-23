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

import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, List, Optional


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


class EscrowMonitor:
    """
    Monitors escrow states and triggers transitions.

    In production, this would be a Rust service subscribing to chain events.
    Here it's a Python in-memory state machine for testing and integration.
    """

    def __init__(self):
        self._escrows: Dict[str, Escrow] = {}

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
        return esc

    def verify_settlement(self, escrow_id: str) -> bool:
        """G1 Resolution: Two-Phase Confirmation."""
        esc = self._escrows.get(escrow_id)
        if not esc or esc.state != EscrowState.HOLDING:
            return False
        esc.settlement_verified = True
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
        return True

    def enter_pending_akashic(self, escrow_id: str) -> bool:
        """E1: Akashic unavailable — enter PENDING_AKASHIC state."""
        esc = self._escrows.get(escrow_id)
        if not esc or esc.state != EscrowState.HOLDING:
            return False
        esc.state = EscrowState.PENDING_AKASHIC
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

    mon = EscrowMonitor()

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

    print("\nPHASE 2.2 PASS — Escrow Monitor implemented")
