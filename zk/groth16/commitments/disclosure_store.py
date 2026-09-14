"""
disclosure_hash store (S3) — TRION BZK Phase 2.3.

Per BTCP Fix 1 Step 4 verbatim: "TRION stores: disclosure_hash only.
TRION emits: TRAVEL_RULE_COMPLIANT = TRUE."

Per R-ABSENT: the disclosure payload, the regulator receipt, and any PII
NEVER touch TRION storage or logs. The only thing TRION persists is the
disclosure_hash (a 32-byte Hash_DNA sense strand) plus the minimum
metadata needed for routing/audit (entity_id, transaction_hash,
jurisdiction_id, stored_at timestamp).

Schema (SQLite):

    CREATE TABLE disclosure_hashes (
        entity_id        TEXT,
        tx_hash          TEXT,
        jurisdiction_id  TEXT,
        disclosure_hash  TEXT,
        stored_at        INTEGER,
        PRIMARY KEY(entity_id, tx_hash)
    )

NO column for the disclosure payload, the regulator receipt, or any PII.
The schema is enforced exactly: any drift (added column, renamed column,
type change) causes every store/read function to fail closed (R-FAILCLOSED).

Onchain surface (R-CHANNELS, BTCP Fix 1 Step 4):
  • TravelRuleProofSubmitted(entity_id, tx_hash, jurisdiction_id,
                              disclosure_hash, zk_proof_hash) event
  • TRAVEL_RULE_COMPLIANT = TRUE emission
  • NO disclosure plaintext, NO regulator receipt, NO PII onchain.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Optional

__all__ = [
    "DEFAULT_DB_PATH",
    "SchemaMismatchError",
    "DisclosureStore",
    "store_disclosure_hash",
    "get_disclosure_hash",
    "assert_no_plaintext",
]

DEFAULT_DB_PATH = Path(
    os.environ.get(
        "TRION_ZK_DISCLOSURE_DB",
        str(Path(__file__).resolve().parent / "data" / "disclosure_hashes.db"),
    )
)


# ── Schema definition (the ONLY columns allowed in disclosure_hashes) ─────────
#
# R-ABSENT invariant: this is the exact, complete column set. No column may
# be added that stores the disclosure payload, the regulator receipt, or any
# PII. The runtime _verify_schema() check enforces this — any drift fails
# closed (R-FAILCLOSED).

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS disclosure_hashes (
    entity_id        TEXT    NOT NULL,
    tx_hash          TEXT    NOT NULL,
    jurisdiction_id  TEXT    NOT NULL,
    disclosure_hash  TEXT    NOT NULL,
    stored_at        INTEGER NOT NULL,
    PRIMARY KEY(entity_id, tx_hash)
);
"""

# Expected column → SQLite type mapping (used by R-FAILCLOSED schema check).
# Any column NOT in this map, or any column with a wrong type, fails closed.
_EXPECTED_COLUMNS = {
    "entity_id": "TEXT",
    "tx_hash": "TEXT",
    "jurisdiction_id": "TEXT",
    "disclosure_hash": "TEXT",
    "stored_at": "INTEGER",
}


class SchemaMismatchError(RuntimeError):
    """Raised when the disclosure_hashes schema does not match the expected
    R-ABSENT-compliant schema. Per R-FAILCLOSED, every store/read function
    refuses to operate when this is raised — the store stays closed rather
    than silently writing through a non-compliant schema."""


class DisclosureStore:
    """SQLite-backed disclosure_hash store. Hash-only — never persists the
    disclosure payload, regulator receipt, or any PII.

    Per BTCP Fix 1 Step 4 + R-ABSENT. Per R-FAILCLOSED, every method first
    verifies the schema matches the expected R-ABSENT-compliant schema; on
    mismatch, the method raises SchemaMismatchError and refuses to read or
    write.
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
        """Create the disclosure_hashes table if it does not exist."""
        with self._connect() as conn:
            conn.executescript(_SCHEMA_SQL)
            conn.commit()

    def _verify_schema(self, conn: sqlite3.Connection) -> None:
        """R-FAILCLOSED: verify the disclosure_hashes table schema matches
        the expected R-ABSENT-compliant schema EXACTLY. Any drift (added
        column, renamed column, type change) raises SchemaMismatchError."""
        cursor = conn.execute("PRAGMA table_info(disclosure_hashes)")
        rows = cursor.fetchall()
        if not rows:
            raise SchemaMismatchError(
                "disclosure_hashes table does not exist — refusing to operate"
            )
        actual: dict = {}
        for row in rows:
            # row: (cid, name, type, notnull, dflt_value, pk)
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
                "disclosure_hashes schema mismatch — R-FAILCLOSED. "
                f"extra_columns={sorted(extra)} "
                f"missing_columns={sorted(missing)} "
                f"type_mismatch={sorted(type_mismatch)}. "
                "R-ABSENT invariant: only entity_id, tx_hash, jurisdiction_id, "
                "disclosure_hash, stored_at are permitted columns."
            )

    def store_disclosure_hash(
        self,
        entity_id: str,
        tx_hash: str,
        jurisdiction_id: str,
        disclosure_hash: bytes,
    ) -> int:
        """Store ONLY the disclosure_hash + metadata. NEVER the plaintext
        disclosure, NEVER the regulator receipt, NEVER any PII.

        Per BTCP Fix 1 Step 4 verbatim: "TRION stores: disclosure_hash only."

        Returns the stored_at timestamp (unix seconds).

        Raises SchemaMismatchError if the schema has drifted (R-FAILCLOSED).
        Raises TypeError if any argument has the wrong type.
        Raises ValueError if disclosure_hash is not a 32-byte digest.
        """
        if not isinstance(entity_id, str) or not entity_id:
            raise TypeError("entity_id must be a non-empty str")
        if not isinstance(tx_hash, str) or not tx_hash:
            raise TypeError("tx_hash must be a non-empty str")
        if not isinstance(jurisdiction_id, str) or not jurisdiction_id:
            raise TypeError("jurisdiction_id must be a non-empty str")
        if not isinstance(disclosure_hash, (bytes, bytearray)):
            raise TypeError("disclosure_hash must be bytes")
        if len(disclosure_hash) != 32:
            raise ValueError(
                f"disclosure_hash must be a 32-byte SHA3-256/Hash_DNA digest, "
                f"got {len(disclosure_hash)} bytes"
            )

        stored_at = int(time.time())
        hash_hex = bytes(disclosure_hash).hex()

        with self._connect() as conn:
            self._verify_schema(conn)  # R-FAILCLOSED
            conn.execute(
                """
                INSERT OR REPLACE INTO disclosure_hashes
                    (entity_id, tx_hash, jurisdiction_id, disclosure_hash, stored_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (entity_id, tx_hash, jurisdiction_id, hash_hex, stored_at),
            )
            conn.commit()
        return stored_at

    def get_disclosure_hash(
        self, entity_id: str, tx_hash: str
    ) -> Optional[bytes]:
        """Retrieve the disclosure_hash for (entity_id, tx_hash).

        Returns the 32-byte disclosure_hash, or None if no record exists.

        Raises SchemaMismatchError if the schema has drifted (R-FAILCLOSED).
        """
        if not isinstance(entity_id, str) or not isinstance(tx_hash, str):
            raise TypeError("entity_id and tx_hash must be str")

        with self._connect() as conn:
            self._verify_schema(conn)  # R-FAILCLOSED
            cursor = conn.execute(
                """
                SELECT disclosure_hash FROM disclosure_hashes
                WHERE entity_id = ? AND tx_hash = ?
                """,
                (entity_id, tx_hash),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return bytes.fromhex(row[0])

    def count(self) -> int:
        """Return the number of stored disclosure_hash records.
        R-FAILCLOSED: verifies schema first."""
        with self._connect() as conn:
            self._verify_schema(conn)
            cursor = conn.execute("SELECT COUNT(*) FROM disclosure_hashes")
            return int(cursor.fetchone()[0])


# ── Module-level convenience API ──────────────────────────────────────────────

_default_store: Optional[DisclosureStore] = None


def _get_default_store() -> DisclosureStore:
    global _default_store
    if _default_store is None:
        _default_store = DisclosureStore()
    return _default_store


def store_disclosure_hash(
    entity_id: str,
    tx_hash: str,
    jurisdiction_id: str,
    disclosure_hash: bytes,
) -> int:
    """Module-level convenience wrapper around DisclosureStore.store_disclosure_hash.
    Uses the default DB path (DEFAULT_DB_PATH or TRION_ZK_DISCLOSURE_DB env var)."""
    return _get_default_store().store_disclosure_hash(
        entity_id, tx_hash, jurisdiction_id, disclosure_hash
    )


def get_disclosure_hash(
    entity_id: str, tx_hash: str
) -> Optional[bytes]:
    """Module-level convenience wrapper around DisclosureStore.get_disclosure_hash."""
    return _get_default_store().get_disclosure_hash(entity_id, tx_hash)


def assert_no_plaintext(db_path: Optional[Path] = None) -> None:
    """R-ABSENT runtime self-check.

    Verifies two invariants:
      1. The disclosure_hashes table schema has EXACTLY the expected
         R-ABSENT-compliant columns (entity_id, tx_hash, jurisdiction_id,
         disclosure_hash, stored_at). Any drift fails this check.
      2. The leakage_grep.sh script (which greps the entire commitments/
         directory for forbidden ABSENT-field tokens) exits 0. If the script
         is not present, this check is skipped (the source-grep is best-effort
         at runtime; the schema check is mandatory).

    Raises SchemaMismatchError if the schema has drifted.
    Raises RuntimeError if the leakage_grep.sh script exits non-zero.
    """
    store = DisclosureStore(db_path) if db_path else _get_default_store()
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
      1. store_disclosure_hash + get_disclosure_hash round-trip.
      2. get_disclosure_hash returns None for missing (entity_id, tx_hash).
      3. Schema mismatch (extra column) causes R-FAILCLOSED.
      4. assert_no_plaintext passes on a fresh, compliant schema.
      5. Storage of a non-32-byte hash raises ValueError.
    """
    import tempfile
    out: dict = {}

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_disclosure.db"
        store = DisclosureStore(db_path)

        # 1. Round-trip.
        eid = "entity_0xdeadbeef"
        txh = "0xabc123"
        jur = "FATF-40"
        d_hash = bytes(range(32))  # 32 bytes
        ts = store.store_disclosure_hash(eid, txh, jur, d_hash)
        assert isinstance(ts, int) and ts > 0, "store_disclosure_hash must return a timestamp"
        retrieved = store.get_disclosure_hash(eid, txh)
        assert retrieved == d_hash, f"round-trip failed: {retrieved!r} != {d_hash!r}"

        # 2. Missing record.
        missing = store.get_disclosure_hash("nonexistent_entity", "0xnope")
        assert missing is None, "missing record must return None"

        # 3. R-FAILCLOSED on schema mismatch.
        with store._connect() as conn:
            conn.execute("ALTER TABLE disclosure_hashes ADD COLUMN leak_column TEXT")
            conn.commit()
        try:
            store.store_disclosure_hash("e2", "0xt2", "JUR", bytes(range(32)))
            raise AssertionError("R-FAILCLOSED: store must refuse to write through drifted schema")
        except SchemaMismatchError:
            pass  # expected

        # Recreate a clean DB to verify the good path still works.
        db_path2 = Path(tmp) / "test_disclosure2.db"
        store2 = DisclosureStore(db_path2)
        store2.store_disclosure_hash(eid, txh, jur, d_hash)
        assert store2.get_disclosure_hash(eid, txh) == d_hash

        # 4. assert_no_plaintext on a compliant schema.
        # (leakage_grep.sh may or may not exist yet; assert_no_plaintext is
        # best-effort on the grep but mandatory on the schema check.)
        assert_no_plaintext(db_path2)

        # 5. Non-32-byte hash raises ValueError.
        try:
            store2.store_disclosure_hash("e3", "0xt3", "JUR", b"too-short")
            raise AssertionError("store must reject non-32-byte disclosure_hash")
        except ValueError:
            pass  # expected

    out["all_passed"] = True
    return out


if __name__ == "__main__":
    import json
    print("=== disclosure_hash store (S3) — self-test ===")
    res = _self_test()
    print(json.dumps({k: v for k, v in res.items() if not isinstance(v, bytes)}, indent=2))
    assert res.get("all_passed"), "self-test FAILED"
    print("PASS — disclosure_hash store (BTCP Fix 1 Step 4 + R-ABSENT + R-FAILCLOSED)")
