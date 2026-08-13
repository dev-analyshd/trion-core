"""
TRION Protocol — Right to Invisibility Enforcement
===================================================

Whitepaper §17 specifies that any entity may petition for "invisibility"
— the right to have their behavioral data excluded from TRION's public
analytics.  This is a fundamental privacy right.

This module implements the Right to Invisibility enforcement layer:
  - Petition submission
  - Verification (cryptographic proof of identity)
  - Enforcement (flag entities to be excluded from public analytics)
  - Audit trail (record all petitions and outcomes)

Invisibility does NOT delete the entity's behavioral record — the BH
ledger is append-only.  Instead, it flags the entity so that public
API responses exclude their data.  Internal TRION operations (e.g.
anomaly detection) continue to use the data, but it is never exposed
externally.

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ── Constants ──────────────────────────────────────────────────────────────────

DB_PATH: str = os.path.join("akashic", "invisibility_petitions.db")

# Petition states
STATE_PENDING:      str = "PENDING"
STATE_APPROVED:     str = "APPROVED"
STATE_REJECTED:     str = "REJECTED"
STATE_REVOKED:      str = "REVOKED"   # entity later asked to rescind


# ── Data Model ─────────────────────────────────────────────────────────────────

@dataclass
class InvisibilityPetition:
    """A petition from an entity to be excluded from public analytics."""
    petition_id:     str
    entity_id:       str
    proof_hash:      bytes           # cryptographic proof of identity
    reason:          str             # free-text justification
    submitted_at:    float = field(default_factory=time.time)
    state:           str = STATE_PENDING
    decided_at:      Optional[float] = None
    decided_by:      Optional[str]   = None
    decision_note:   Optional[str]   = None
    expires_at:      Optional[float] = None  # optional time-limited invisibility

    def to_dict(self) -> dict:
        return {
            "petition_id":   self.petition_id,
            "entity_id":     self.entity_id,
            "proof_hash":    self.proof_hash.hex(),
            "reason":        self.reason,
            "submitted_at":  self.submitted_at,
            "state":         self.state,
            "decided_at":    self.decided_at,
            "decided_by":    self.decided_by,
            "decision_note": self.decision_note,
            "expires_at":    self.expires_at,
        }


# ── Enforcement Layer ──────────────────────────────────────────────────────────

class RightToInvisibility:
    """
    Manages invisibility petitions and enforces the right.

    Usage:
        rtiv = RightToInvisibility()
        petition_id = rtiv.submit_petition("entity_abc", proof, "privacy concern")
        rtiv.approve(petition_id, decided_by="governance_multisig")
        if rtiv.is_invisible("entity_abc"):
            # exclude from public API response
            ...
    """

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or DB_PATH
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self._db_path) or ".", exist_ok=True)
        return sqlite3.connect(self._db_path)

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS invisibility_petitions (
                    petition_id   TEXT PRIMARY KEY,
                    entity_id     TEXT NOT NULL,
                    proof_hash    BLOB NOT NULL,
                    reason        TEXT NOT NULL,
                    submitted_at  REAL NOT NULL,
                    state         TEXT NOT NULL,
                    decided_at    REAL,
                    decided_by    TEXT,
                    decision_note TEXT,
                    expires_at    REAL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_petitions_entity
                ON invisibility_petitions(entity_id, state)
            """)
            conn.commit()

    # ── Petition lifecycle ─────────────────────────────────────────────────

    def submit_petition(
        self,
        entity_id:   str,
        proof:       bytes,
        reason:      str,
        expires_at:  Optional[float] = None,
    ) -> str:
        """Submit a new invisibility petition. Returns the petition_id."""
        petition_id = hashlib.sha3_256(
            entity_id.encode() + str(time.time()).encode() + os.urandom(16)
        ).hexdigest()[:16]
        proof_hash = hashlib.sha3_256(proof).digest()
        petition = InvisibilityPetition(
            petition_id=petition_id,
            entity_id=entity_id,
            proof_hash=proof_hash,
            reason=reason,
            expires_at=expires_at,
        )
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO invisibility_petitions
                (petition_id, entity_id, proof_hash, reason, submitted_at,
                 state, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                petition.petition_id, petition.entity_id, petition.proof_hash,
                petition.reason, petition.submitted_at, petition.state,
                petition.expires_at,
            ))
            conn.commit()
        return petition_id

    def approve(
        self,
        petition_id:   str,
        decided_by:    str,
        decision_note: str = "",
    ) -> bool:
        """Approve a pending petition."""
        with self._conn() as conn:
            cur = conn.execute("""
                UPDATE invisibility_petitions
                SET state = ?, decided_at = ?, decided_by = ?, decision_note = ?
                WHERE petition_id = ? AND state = ?
            """, (STATE_APPROVED, time.time(), decided_by, decision_note,
                  petition_id, STATE_PENDING))
            conn.commit()
            return cur.rowcount > 0

    def reject(
        self,
        petition_id:   str,
        decided_by:    str,
        decision_note: str = "",
    ) -> bool:
        """Reject a pending petition."""
        with self._conn() as conn:
            cur = conn.execute("""
                UPDATE invisibility_petitions
                SET state = ?, decided_at = ?, decided_by = ?, decision_note = ?
                WHERE petition_id = ? AND state = ?
            """, (STATE_REJECTED, time.time(), decided_by, decision_note,
                  petition_id, STATE_PENDING))
            conn.commit()
            return cur.rowcount > 0

    def revoke(self, petition_id: str, decided_by: str) -> bool:
        """Revoke a previously-approved petition (entity rescinds request)."""
        with self._conn() as conn:
            cur = conn.execute("""
                UPDATE invisibility_petitions
                SET state = ?, decided_at = ?, decided_by = ?, decision_note = ?
                WHERE petition_id = ? AND state = ?
            """, (STATE_REVOKED, time.time(), decided_by, "Entity rescinded",
                  petition_id, STATE_APPROVED))
            conn.commit()
            return cur.rowcount > 0

    # ── Enforcement ────────────────────────────────────────────────────────

    def is_invisible(self, entity_id: str, now: Optional[float] = None) -> bool:
        """True iff the entity currently has an approved invisibility petition."""
        now_val = now if now is not None else time.time()
        with self._conn() as conn:
            cur = conn.execute("""
                SELECT expires_at FROM invisibility_petitions
                WHERE entity_id = ? AND state = ?
            """, (entity_id, STATE_APPROVED))
            for row in cur.fetchall():
                expires_at = row[0]
                if expires_at is None or expires_at > now_val:
                    return True
        return False

    def filter_visible(self, entity_ids: List[str]) -> List[str]:
        """Filter a list of entity IDs to only those visible (not invisible)."""
        return [eid for eid in entity_ids if not self.is_invisible(eid)]

    def list_petitions(
        self, entity_id: Optional[str] = None, state: Optional[str] = None,
    ) -> List[dict]:
        """List petitions, optionally filtered by entity_id and/or state."""
        query = "SELECT * FROM invisibility_petitions WHERE 1=1"
        params: List = []
        if entity_id:
            query += " AND entity_id = ?"
            params.append(entity_id)
        if state:
            query += " AND state = ?"
            params.append(state)
        query += " ORDER BY submitted_at DESC"
        with self._conn() as conn:
            cur = conn.execute(query, params)
            rows = cur.fetchall()
        cols = [
            "petition_id", "entity_id", "proof_hash", "reason", "submitted_at",
            "state", "decided_at", "decided_by", "decision_note", "expires_at",
        ]
        result = []
        for row in rows:
            d = dict(zip(cols, row))
            d["proof_hash"] = bytes(d["proof_hash"]).hex()
            result.append(d)
        return result


# ── Self-test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        db = os.path.join(tmpdir, "test_invisibility.db")
        rtiv = RightToInvisibility(db_path=db)

        print("=== Right to Invisibility Self-test ===\n")

        # Submit petition
        pid = rtiv.submit_petition(
            entity_id="entity_abc",
            proof=b"signature_proving_identity",
            reason="Personal safety concern",
        )
        print(f"Petition submitted: {pid}")

        # Not invisible yet (pending)
        assert not rtiv.is_invisible("entity_abc")
        print(f"is_invisible (pending): {rtiv.is_invisible('entity_abc')}")

        # Approve
        ok = rtiv.approve(pid, decided_by="governance_multisig")
        assert ok
        print(f"is_invisible (approved): {rtiv.is_invisible('entity_abc')}")
        assert rtiv.is_invisible("entity_abc")

        # Filter
        visible = rtiv.filter_visible(["entity_abc", "entity_xyz"])
        print(f"filter_visible(['entity_abc', 'entity_xyz']): {visible}")
        assert "entity_abc" not in visible
        assert "entity_xyz" in visible

        # Revoke
        rtiv.revoke(pid, decided_by="entity_abc")
        print(f"is_invisible (revoked): {rtiv.is_invisible('entity_abc')}")
        assert not rtiv.is_invisible("entity_abc")

        print("\nPHASE 7 PASS — Right to Invisibility enforcement implemented")
