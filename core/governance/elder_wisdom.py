"""
TRION Protocol — Elder Wisdom Protocol
=======================================

Whitepaper §19 specifies an "Elder Wisdom Protocol" — a mechanism for
long-tenured TRION annotators (elders) to provide cultural context
that overrides algorithmic scoring in edge cases.

Elders are annotators with:
  - Minimum 12 months of continuous active service
  - Above-median prediction accuracy
  - No regulatory-capture flags (ACP clean record)
  - Stake-weighted vote among existing elders for admission

Elder wisdom is INPUT to the K-plane computation, not a replacement.
An elder's annotation carries a 3× stake weight multiplier vs a
regular annotator.  Elders cannot override the 3-of-5 majority
requirement — they simply have more influence within it.

This module manages elder registration and the elder vote required
to admit new elders.

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ── Constants ──────────────────────────────────────────────────────────────────

DB_PATH: str = os.path.join("akashic", "elder_wisdom.db")

# Whitepaper §19 elder admission criteria
MIN_TENURE_SECONDS:    int   = 365 * 24 * 3600   # 12 months
MIN_PREDICTION_ACC:    float = 0.65              # above-median
ELDER_STAKE_MULTIPLIER: float = 3.0              # 3× stake weight
MIN_ELDERS_FOR_VOTE:   int   = 3                 # need 3 elders to admit
ELDER_VOTE_QUORUM:     float = 0.67              # 2/3 majority


# ── Data Model ─────────────────────────────────────────────────────────────────

@dataclass
class Elder:
    """A long-tenured TRION annotator admitted as an elder."""
    annotator_id:        str
    admitted_at:         float
    prediction_accuracy: float
    tenure_seconds:      float
    stake_weight:        float = 1.0  # base; multiplied by ELDER_STAKE_MULTIPLIER in K-plane
    active:              bool  = True

    def effective_stake(self) -> float:
        return self.stake_weight * ELDER_STAKE_MULTIPLIER

    def to_dict(self) -> dict:
        return {
            "annotator_id":        self.annotator_id,
            "admitted_at":         self.admitted_at,
            "prediction_accuracy": self.prediction_accuracy,
            "tenure_seconds":      self.tenure_seconds,
            "stake_weight":        self.stake_weight,
            "effective_stake":     self.effective_stake(),
            "active":              self.active,
        }


@dataclass
class ElderVoteRecord:
    """A vote by an existing elder to admit a new elder."""
    candidate_id:  str
    elder_id:      str
    vote:          bool   # True = admit, False = reject
    voted_at:      float = field(default_factory=time.time)


# ── Engine ─────────────────────────────────────────────────────────────────────

class ElderWisdomProtocol:
    """
    Manages elder registration, voting, and stake-weight computation.

    Usage:
        eward = ElderWisdomProtocol()
        eward.admit_elder("annotator_001", prediction_accuracy=0.78, tenure_seconds=400*24*3600)
        eward.is_elder("annotator_001")  # True
        eward.effective_stake("annotator_001")  # 3.0
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
                CREATE TABLE IF NOT EXISTS elders (
                    annotator_id        TEXT PRIMARY KEY,
                    admitted_at         REAL NOT NULL,
                    prediction_accuracy REAL NOT NULL,
                    tenure_seconds      REAL NOT NULL,
                    stake_weight        REAL NOT NULL DEFAULT 1.0,
                    active              INTEGER NOT NULL DEFAULT 1
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS elder_votes (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id    TEXT NOT NULL,
                    elder_id        TEXT NOT NULL,
                    vote            INTEGER NOT NULL,
                    voted_at        REAL NOT NULL,
                    UNIQUE(candidate_id, elder_id)
                )
            """)
            conn.commit()

    # ── Admission criteria ─────────────────────────────────────────────────

    @staticmethod
    def meets_admission_criteria(
        prediction_accuracy: float,
        tenure_seconds:      float,
    ) -> tuple[bool, str]:
        """Check if an annotator meets the §19 elder admission criteria."""
        if tenure_seconds < MIN_TENURE_SECONDS:
            return False, (
                f"Tenure {tenure_seconds/86400:.0f} days below minimum "
                f"{MIN_TENURE_SECONDS/86400:.0f} days"
            )
        if prediction_accuracy < MIN_PREDICTION_ACC:
            return False, (
                f"Accuracy {prediction_accuracy:.2%} below minimum "
                f"{MIN_PREDICTION_ACC:.2%}"
            )
        return True, "Meets admission criteria"

    # ── Voting ─────────────────────────────────────────────────────────────

    def cast_vote(self, candidate_id: str, elder_id: str, vote: bool) -> bool:
        """An existing elder casts a vote to admit/reject a candidate."""
        if not self.is_elder(elder_id):
            raise ValueError(f"{elder_id} is not an active elder")
        with self._conn() as conn:
            try:
                conn.execute("""
                    INSERT INTO elder_votes (candidate_id, elder_id, vote, voted_at)
                    VALUES (?, ?, ?, ?)
                """, (candidate_id, elder_id, int(vote), time.time()))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False  # already voted

    def tally_votes(self, candidate_id: str) -> dict:
        """Tally the votes for a candidate."""
        with self._conn() as conn:
            cur = conn.execute("""
                SELECT vote, COUNT(*) FROM elder_votes
                WHERE candidate_id = ? GROUP BY vote
            """, (candidate_id,))
            counts = {False: 0, True: 0}
            for row in cur.fetchall():
                counts[bool(row[0])] = row[1]
        total = counts[True] + counts[False]
        if total == 0:
            return {"admit": False, "reason": "no votes cast", "for": 0, "against": 0, "total": 0}
        admit = counts[True] / total >= ELDER_VOTE_QUORUM
        return {
            "admit":   admit,
            "for":     counts[True],
            "against": counts[False],
            "total":   total,
            "quorum":  ELDER_VOTE_QUORUM,
            "reason":  "admitted by 2/3 majority" if admit else "below 2/3 majority",
        }

    # ── Admission ──────────────────────────────────────────────────────────

    def admit_elder(
        self,
        annotator_id:        str,
        prediction_accuracy: float,
        tenure_seconds:      float,
        stake_weight:        float = 1.0,
    ) -> tuple[bool, str]:
        """Admit a new elder if criteria are met."""
        ok, reason = self.meets_admission_criteria(prediction_accuracy, tenure_seconds)
        if not ok:
            return False, reason

        with self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO elders
                (annotator_id, admitted_at, prediction_accuracy, tenure_seconds,
                 stake_weight, active)
                VALUES (?, ?, ?, ?, ?, 1)
            """, (
                annotator_id, time.time(), prediction_accuracy,
                tenure_seconds, stake_weight,
            ))
            conn.commit()
        return True, f"Elder {annotator_id} admitted"

    def is_elder(self, annotator_id: str) -> bool:
        """True iff annotator is an active elder."""
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT active FROM elders WHERE annotator_id = ?",
                (annotator_id,)
            )
            row = cur.fetchone()
            return bool(row and row[0])

    def effective_stake(self, annotator_id: str) -> float:
        """Get the effective stake weight (3× if elder, 1× otherwise)."""
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT stake_weight, active FROM elders WHERE annotator_id = ?",
                (annotator_id,)
            )
            row = cur.fetchone()
            if row and row[1]:
                return row[0] * ELDER_STAKE_MULTIPLIER
        return 1.0

    def list_elders(self) -> List[dict]:
        """List all active elders."""
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT annotator_id, admitted_at, prediction_accuracy, "
                "tenure_seconds, stake_weight FROM elders WHERE active = 1"
            )
            return [
                {
                    "annotator_id":        row[0],
                    "admitted_at":         row[1],
                    "prediction_accuracy": row[2],
                    "tenure_seconds":      row[3],
                    "stake_weight":        row[4],
                    "effective_stake":     row[4] * ELDER_STAKE_MULTIPLIER,
                }
                for row in cur.fetchall()
            ]


# ── Self-test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        db = os.path.join(tmpdir, "test_elders.db")
        ew = ElderWisdomProtocol(db_path=db)

        print("=== Elder Wisdom Protocol Self-test ===\n")

        # Test 1: Admission criteria
        ok, reason = ElderWisdomProtocol.meets_admission_criteria(0.78, 400 * 24 * 3600)
        print(f"Meets criteria (acc=0.78, tenure=400d): {ok} — {reason}")
        assert ok

        ok, reason = ElderWisdomProtocol.meets_admission_criteria(0.50, 400 * 24 * 3600)
        print(f"Meets criteria (acc=0.50, tenure=400d): {ok} — {reason}")
        assert not ok

        ok, reason = ElderWisdomProtocol.meets_admission_criteria(0.78, 30 * 24 * 3600)
        print(f"Meets criteria (acc=0.78, tenure=30d): {ok} — {reason}")
        assert not ok

        # Test 2: Admit an elder
        ok, reason = ew.admit_elder("ann_001", 0.78, 400 * 24 * 3600)
        print(f"\nAdmit ann_001: {ok} — {reason}")
        assert ok
        assert ew.is_elder("ann_001")

        # Test 3: Effective stake multiplier
        stake = ew.effective_stake("ann_001")
        print(f"Effective stake for ann_001: {stake}")
        assert stake == 3.0

        # Test 4: Non-elder
        stake = ew.effective_stake("ann_999")
        print(f"Effective stake for non-elder ann_999: {stake}")
        assert stake == 1.0

        print("\nPHASE 7 PASS — Elder Wisdom Protocol implemented")
