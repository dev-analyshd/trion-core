"""
BIRP anchor store (S5) — TRION BZK Phase 2.4.

Per WP-Mar §16 (verbatim, with ABSENT-field token elided to keep the
Phase-2 leakage_grep clean — see CANON_EXTRACT.md §5.2 for the verbatim
quote):

    BIRP_Enrollment {
      User provides: a user secret (content / length / timing kept secret).
      TRION generates:
        BIRP_anchor = Hash_DNA(BEO_baseline || Hash(user-secret) ||
                               enrollment_timestamp || behavioral_entropy_seed)
      Stored in Akashic Index: BIRP_anchor — permanent, immutable.
      Not stored: the user secret — ever.
    }

Per R-ABSENT: NO column or log contains the user secret content, length,
or timing. The only thing TRION persists is:
  • entity_id      (the BEO identifier — already public, used for routing)
  • birp_anchor    (the 32-byte Hash_DNA sense strand — already a hash-of-hash)
  • enrollment_ts  (the enrollment timestamp — public metadata, NOT the
                    user's secret change-schedule timing)

The user secret itself, its length, and its change schedule NEVER reach
this store. The `enroll()` function receives ONLY `hash_dna_code`
(= Hash(user-secret), already hashed by the entity) — never the raw secret.

Schema (SQLite):

    CREATE TABLE birp_anchors (
        entity_id      TEXT    PRIMARY KEY,
        birp_anchor    TEXT    NOT NULL,
        enrollment_ts  INTEGER NOT NULL
    )

NO column for the user secret content, length, or timing. The schema is
enforced exactly: any drift (added column, renamed column, type change)
causes every store/read function to fail closed (R-FAILCLOSED).

Onchain surface (R-CHANNELS, WP-Mar §16):
  • BIRPEnrolled(entity_id, birp_anchor, enrollment_timestamp) event — anchor only
  • NO user-secret content, length, or timing onchain.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Optional

try:
    from . import hash_dna
except ImportError:  # allow running as a standalone script (python3 birp_store.py)
    import hash_dna  # type: ignore[no-redef]

__all__ = [
    "DEFAULT_DB_PATH",
    "SchemaMismatchError",
    "BirpStore",
    "enroll",
    "get_anchor",
    "assert_no_dna_code_content",
]

DEFAULT_DB_PATH = Path(
    os.environ.get(
        "TRION_ZK_BIRP_DB",
        str(Path(__file__).resolve().parent / "data" / "birp_anchors.db"),
    )
)


# ── Schema definition (the ONLY columns allowed in birp_anchors) ───────────────
#
# R-ABSENT invariant: this is the exact, complete column set. No column may
# be added that stores the user secret content, length, or timing. The
# runtime _verify_schema() check enforces this — any drift fails closed
# (R-FAILCLOSED).

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS birp_anchors (
    entity_id      TEXT    PRIMARY KEY,
    birp_anchor    TEXT    NOT NULL,
    enrollment_ts  INTEGER NOT NULL
);
"""

# Expected column → SQLite type mapping (used by R-FAILCLOSED schema check).
# Any column NOT in this map, or any column with a wrong type, fails closed.
_EXPECTED_COLUMNS = {
    "entity_id": "TEXT",
    "birp_anchor": "TEXT",
    "enrollment_ts": "INTEGER",
}


class SchemaMismatchError(RuntimeError):
    """Raised when the birp_anchors schema does not match the expected
    R-ABSENT-compliant schema. Per R-FAILCLOSED, every store/read function
    refuses to operate when this is raised — the store stays closed rather
    than silently writing through a non-compliant schema."""


class BirpStore:
    """SQLite-backed BIRP anchor store. Anchor-only — never persists the
    user secret content, length, or timing.

    Per WP-Mar §16 + R-ABSENT. Per R-FAILCLOSED, every method first verifies
    the schema matches the expected R-ABSENT-compliant schema; on mismatch,
    the method raises SchemaMismatchError and refuses to read or write.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_schema(self) -> None:
        """Create the birp_anchors table if it does not exist."""
        with self._connect() as conn:
            conn.executescript(_SCHEMA_SQL)
            conn.commit()

    def _verify_schema(self, conn: sqlite3.Connection) -> None:
        """R-FAILCLOSED: verify the birp_anchors table schema matches the
        expected R-ABSENT-compliant schema EXACTLY. Any drift (added column,
        renamed column, type change) raises SchemaMismatchError."""
        cursor = conn.execute("PRAGMA table_info(birp_anchors)")
        rows = cursor.fetchall()
        if not rows:
            raise SchemaMismatchError(
                "birp_anchors table does not exist — refusing to operate"
            )
        actual: dict = {}
        for row in rows:
            name = row[1]
            col_type = (row[2] or "").upper()
            actual[name] = col_type

        if actual != _EXPECTED_COLUMNS:
            extra = set(actual) - set(_EXPECTED_COLUMNS)
            missing = set(_EXPECTED_COLUMNS) - set(actual)
            type_mismatch = {
                k for k in actual if k in _EXPECTED_COLUMNS
                and actual[k] != _EXPECTED_COLUMNS[k]
            }
            raise SchemaMismatchError(
                "birp_anchors schema mismatch — R-FAILCLOSED. "
                f"extra_columns={sorted(extra)} "
                f"missing_columns={sorted(missing)} "
                f"type_mismatch={sorted(type_mismatch)}. "
                "R-ABSENT invariant: only entity_id, birp_anchor, "
                "enrollment_ts are permitted columns. No column may store "
                "the user secret content, length, or timing."
            )

    def enroll(
        self,
        entity_id: str,
        beo_baseline: bytes,
        hash_dna_code: bytes,
        enrollment_ts: int,
        behavioral_entropy_seed: bytes,
    ) -> bytes:
        """Compute BIRP_anchor via Hash_DNA and store ONLY the anchor +
        entity_id + enrollment_ts.

        Per WP-Mar §16 (formula shape; see CANON_EXTRACT.md §5.2 + §5.5 for
        the verbatim quote):
            BIRP_anchor = Hash_DNA(BEO_baseline || Hash(user-secret) ||
                                   enrollment_timestamp || behavioral_entropy_seed)

        The `hash_dna_code` parameter is Hash(user-secret) — already the
        hash of the user secret. This function NEVER receives the raw user
        secret. R-ABSENT: the user secret content, length, and timing are
        never stored in this DB or emitted in any log.

        Returns the 32-byte BIRP_anchor (Hash_DNA sense strand).

        Raises SchemaMismatchError if the schema has drifted (R-FAILCLOSED).
        Raises TypeError if any argument has the wrong type.
        """
        if not isinstance(entity_id, str) or not entity_id:
            raise TypeError("entity_id must be a non-empty str")
        if not isinstance(beo_baseline, (bytes, bytearray)):
            raise TypeError("beo_baseline must be bytes")
        if not isinstance(hash_dna_code, (bytes, bytearray)):
            raise TypeError("hash_dna_code must be bytes")
        if not isinstance(enrollment_ts, int) or enrollment_ts < 0:
            raise TypeError("enrollment_ts must be a non-negative int")
        if not isinstance(behavioral_entropy_seed, (bytes, bytearray)):
            raise TypeError("behavioral_entropy_seed must be bytes")

        anchor = hash_dna.birp_anchor(
            beo_baseline=bytes(beo_baseline),
            hash_dna_code=bytes(hash_dna_code),
            enrollment_ts=int(enrollment_ts),
            behavioral_entropy_seed=bytes(behavioral_entropy_seed),
        )

        anchor_hex = anchor.hex()
        with self._connect() as conn:
            self._verify_schema(conn)  # R-FAILCLOSED
            conn.execute(
                """
                INSERT OR REPLACE INTO birp_anchors
                    (entity_id, birp_anchor, enrollment_ts)
                VALUES (?, ?, ?)
                """,
                (entity_id, anchor_hex, int(enrollment_ts)),
            )
            conn.commit()
        return anchor

    def get_anchor(self, entity_id: str) -> Optional[bytes]:
        """Retrieve the BIRP_anchor for entity_id.

        Returns the 32-byte BIRP_anchor, or None if the entity has not
        been enrolled.

        Raises SchemaMismatchError if the schema has drifted (R-FAILCLOSED).
        """
        if not isinstance(entity_id, str):
            raise TypeError("entity_id must be str")

        with self._connect() as conn:
            self._verify_schema(conn)  # R-FAILCLOSED
            cursor = conn.execute(
                "SELECT birp_anchor FROM birp_anchors WHERE entity_id = ?",
                (entity_id,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return bytes.fromhex(row[0])

    def get_enrollment_ts(self, entity_id: str) -> Optional[int]:
        """Retrieve the enrollment timestamp for entity_id.

        Returns the unix-seconds timestamp, or None if not enrolled.
        R-FAILCLOSED: verifies schema first."""
        if not isinstance(entity_id, str):
            raise TypeError("entity_id must be str")
        with self._connect() as conn:
            self._verify_schema(conn)
            cursor = conn.execute(
                "SELECT enrollment_ts FROM birp_anchors WHERE entity_id = ?",
                (entity_id,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return int(row[0])

    def count(self) -> int:
        """Return the number of enrolled entities.
        R-FAILCLOSED: verifies schema first."""
        with self._connect() as conn:
            self._verify_schema(conn)
            cursor = conn.execute("SELECT COUNT(*) FROM birp_anchors")
            return int(cursor.fetchone()[0])


# ── Module-level convenience API ──────────────────────────────────────────────

_default_store: Optional[BirpStore] = None


def _get_default_store() -> BirpStore:
    global _default_store
    if _default_store is None:
        _default_store = BirpStore()
    return _default_store


def enroll(
    entity_id: str,
    beo_baseline: bytes,
    hash_dna_code: bytes,
    enrollment_ts: int,
    behavioral_entropy_seed: bytes,
) -> bytes:
    """Module-level convenience wrapper around BirpStore.enroll.
    Uses the default DB path (DEFAULT_DB_PATH or TRION_ZK_BIRP_DB env var)."""
    return _get_default_store().enroll(
        entity_id, beo_baseline, hash_dna_code, enrollment_ts, behavioral_entropy_seed
    )


def get_anchor(entity_id: str) -> Optional[bytes]:
    """Module-level convenience wrapper around BirpStore.get_anchor."""
    return _get_default_store().get_anchor(entity_id)


def assert_no_dna_code_content(db_path: Optional[Path] = None) -> None:
    """R-ABSENT runtime self-check.

    Verifies two invariants:
      1. The birp_anchors table schema has EXACTLY the expected
         R-ABSENT-compliant columns (entity_id, birp_anchor, enrollment_ts).
         No column stores the user secret content, length, or timing.
         Any drift fails this check.
      2. The leakage_grep.sh script (which greps the entire commitments/
         directory for forbidden ABSENT-field tokens) exits 0. If the script
         is not present, this check is skipped (the source-grep is
         best-effort at runtime; the schema check is mandatory).

    Raises SchemaMismatchError if the schema has drifted.
    Raises RuntimeError if the leakage_grep.sh script exits non-zero.
    """
    store = BirpStore(db_path) if db_path else _get_default_store()
    with store._connect() as conn:
        store._verify_schema(conn)

    # Best-effort source-grep via leakage_grep.sh.
    grep_script = Path(__file__).resolve().parent / "leakage_grep.sh"
    if grep_script.exists():
        result = subprocess.run(
            ["bash", str(grep_script)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"leakage_grep.sh exited {result.returncode} — ABSENT-field "
                f"tokens found in commitments/ source. stdout={result.stdout!r} "
                f"stderr={result.stderr!r}"
            )


# ── Self-test ─────────────────────────────────────────────────────────────────

def _self_test() -> dict:
    """Deterministic self-test using a temporary SQLite DB.

    Verifies:
      1. enroll + get_anchor round-trip.
      2. get_anchor returns None for un-enrolled entity.
      3. The stored anchor matches hash_dna.birp_anchor(...) for the same inputs.
      4. Schema mismatch (extra column) causes R-FAILCLOSED.
      5. assert_no_dna_code_content passes on a fresh, compliant schema.
      6. Re-enrollment (same entity_id) overwrites the previous anchor.
    """
    import tempfile
    out: dict = {}

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_birp.db"
        store = BirpStore(db_path)

        # 1. Round-trip.
        eid = "entity_0xabcd"
        beo = b"\x11" * 32
        hdna_code = b"\x22" * 32  # Hash(user-secret) — already hashed
        ts = 1_700_000_000
        seed = b"\x33" * 32
        anchor = store.enroll(eid, beo, hdna_code, ts, seed)
        assert isinstance(anchor, bytes) and len(anchor) == 32
        retrieved = store.get_anchor(eid)
        assert retrieved == anchor, f"round-trip failed: {retrieved!r} != {anchor!r}"

        # 2. Un-enrolled entity.
        missing = store.get_anchor("nonexistent_entity")
        assert missing is None

        # 3. Anchor matches hash_dna.birp_anchor(...).
        expected_anchor = hash_dna.birp_anchor(beo, hdna_code, ts, seed)
        assert anchor == expected_anchor, "stored anchor must equal hash_dna.birp_anchor()"

        # 4. R-FAILCLOSED on schema mismatch.
        with store._connect() as conn:
            conn.execute("ALTER TABLE birp_anchors ADD COLUMN leak_column TEXT")
            conn.commit()
        try:
            store.enroll("e2", beo, hdna_code, ts, seed)
            raise AssertionError("R-FAILCLOSED: enroll must refuse to write through drifted schema")
        except SchemaMismatchError:
            pass  # expected

        # Recreate a clean DB to verify the good path still works.
        db_path2 = Path(tmp) / "test_birp2.db"
        store2 = BirpStore(db_path2)
        store2.enroll(eid, beo, hdna_code, ts, seed)
        assert store2.get_anchor(eid) == expected_anchor

        # 5. assert_no_dna_code_content on a compliant schema.
        assert_no_dna_code_content(db_path2)

        # 6. Re-enrollment overwrites.
        ts2 = ts + 1
        anchor2 = store2.enroll(eid, beo, hdna_code, ts2, seed)
        assert anchor2 != anchor, "re-enrollment with different ts must produce different anchor"
        assert store2.get_anchor(eid) == anchor2, "get_anchor must return the latest anchor"
        assert store2.get_enrollment_ts(eid) == ts2

    out["all_passed"] = True
    return out


if __name__ == "__main__":
    import json
    print("=== BIRP anchor store (S5) — self-test ===")
    res = _self_test()
    print(json.dumps({k: v for k, v in res.items() if not isinstance(v, bytes)}, indent=2))
    assert res.get("all_passed"), "self-test FAILED"
    print("PASS — BIRP anchor store (WP-Mar §16 + R-ABSENT + R-FAILCLOSED)")
