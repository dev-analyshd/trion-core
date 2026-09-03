"""
TRION BTCP — Shared SQLite State Store (S7 remediation)
=======================================================

Due-diligence finding S7: all mutable BTCP Python state (orchestrator routes,
router reserve balances, escrow-monitor escrows, dispute-resolution cases and
annotators) previously lived in plain in-memory dicts — a process restart
wiped routes/escrows/disputes.  This module provides the durable backing store
those modules write through.

Design:
  * stdlib ``sqlite3``, WAL journal mode, ``busy_timeout`` for cross-process
    access, and a per-instance ``RLock`` for in-process concurrency.
  * Versioned schema (``btcp_meta`` table, ``schema_version`` key).  A store
    written by a NEWER runtime refuses to load rather than silently
    mis-reading rows; older schemas go through ``_migrate()``.
  * One generic row table keyed by (kind, key) with a type tag per row —
    modules own their to_row/from_row serialization (see e.g.
    ``core/btcp/escrow_monitor.py``) so this store never imports BTCP
    classes (no import cycles).
  * All writes run inside a transaction; every read/write is guarded by the
    per-store lock.

State-DB path resolution (first match wins):
  1. explicit ``state_db=...`` constructor argument
  2. ``TRION_STATE_DB`` environment variable
  3. default shared path ``db/btcp_state.db`` (production) — EXCEPT when the
     store is constructed from test code, in which case an isolated
     per-instance temp file is used (see "Test isolation" below).

Test isolation
--------------
The four BTCP modules keep their hot state in memory and write through to
this store on every mutation; constructors load persisted state on init.
That is exactly what production wants (restart survival via the shared
``db/btcp_state.db``), but existing tests construct these classes with no
arguments and use fixed escrow/case IDs — pointed at the shared file, the
*second* test run would collide with state persisted by the first
(e.g. ``lock_escrow("e1")`` raising "already exists").  Tests therefore get
an isolated throw-away store UNLESS they explicitly opt into the shared
path via ``state_db=...`` or ``TRION_STATE_DB``.  Test context is detected
via ``PYTEST_CURRENT_TEST``, ``pytest`` being loaded, or a caller frame
originating under a ``tests/`` directory.  Remove ``_running_under_test``
from ``resolve_state_db()`` to force the shared default everywhere.

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import atexit
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import sqlite3
from typing import Any, Dict, Optional, Tuple

__all__ = [
    "BtcpStateStore",
    "resolve_state_db",
    "SCHEMA_VERSION",
    "DEFAULT_DB_PATH",
    "STATE_DB_ENV_VAR",
]

SCHEMA_VERSION = 1
STATE_DB_ENV_VAR = "TRION_STATE_DB"
DEFAULT_DB_PATH = os.path.join("db", "btcp_state.db")

# Row "kind" namespaces (one row per persisted object, keyed within its kind).
KIND_ROUTE     = "route"
KIND_BALANCE   = "balance"
KIND_ESCROW    = "escrow"
KIND_CASE      = "case"
KIND_ANNOTATOR = "annotator"

BALANCE_ROW_TYPE = "balance_v1"


# ── Test-context detection ──────────────────────────────────────────────────

def _running_under_test() -> bool:
    """True when the store is being constructed from test code.

    Checks, in order: the ``PYTEST_CURRENT_TEST`` env var (set by pytest for
    the duration of each test), ``pytest`` being imported in this process,
    and any caller frame whose file lives under a ``tests/`` directory
    (covers script-style harnesses run as ``python tests/<file>.py``).
    """
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    if "pytest" in sys.modules:
        return True
    try:
        frame = sys._getframe(1)
        for _ in range(64):
            if frame is None:
                break
            fname = frame.f_code.co_filename
            if fname:
                parts = os.path.normpath(os.path.abspath(fname)).split(os.sep)
                if "tests" in parts[:-1]:  # a parent directory named "tests"
                    return True
            frame = frame.f_back
    except Exception:  # pragma: no cover - restricted environments
        pass
    return False


# Temp stores are cleaned up best-effort at interpreter exit (registered
# before the per-store close handlers below, so atexit LIFO order closes
# the SQLite connections first, then removes the directories).
_temp_store_dirs: set = set()
_temp_store_lock = threading.Lock()


def _new_temp_db_path() -> str:
    directory = tempfile.mkdtemp(prefix="trion_btcp_state_")
    with _temp_store_lock:
        _temp_store_dirs.add(directory)
    return os.path.join(directory, "btcp_state.db")


@atexit.register
def _cleanup_temp_stores() -> None:
    with _temp_store_lock:
        directories = list(_temp_store_dirs)
    for directory in directories:
        shutil.rmtree(directory, ignore_errors=True)


def resolve_state_db(state_db: Optional[str] = None) -> str:
    """Resolve the state-DB path: explicit arg → TRION_STATE_DB → default.

    The default is the shared production path ``db/btcp_state.db`` unless the
    store is constructed from test code (see module docstring) — then an
    isolated per-instance temp file is used so tests never share production
    state unless they explicitly pass ``state_db`` or set the env var.
    """
    if state_db:
        return state_db
    env_path = os.environ.get(STATE_DB_ENV_VAR)
    if env_path:
        return env_path
    if _running_under_test():
        return _new_temp_db_path()
    return DEFAULT_DB_PATH


# ── Store ───────────────────────────────────────────────────────────────────

class BtcpStateStore:
    """SQLite-backed durable state store for the BTCP Python modules.

    Usage (modules own their serialization):

        store = BtcpStateStore()                # or BtcpStateStore(path)
        store.save_escrow(escrow_id, row_dict, "escrow_v1")
        rows = store.get_escrows()              # {escrow_id: (type_tag, payload)}
        store.delete_escrow(escrow_id)

    The hot path stays in each module's in-memory dict; this store is the
    write-through mirror that makes state survive restarts.
    """

    def __init__(self, state_db: Optional[str] = None):
        self._path = os.path.abspath(resolve_state_db(state_db))
        self._lock = threading.RLock()
        parent = os.path.dirname(self._path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(self._path, timeout=30.0, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=30000")
        self._init_schema()
        atexit.register(self.close)

    # ── Schema ──────────────────────────────────────────────────────────

    def _init_schema(self) -> None:
        with self._lock:
            with self._conn:  # transaction
                self._conn.execute("""
                    CREATE TABLE IF NOT EXISTS btcp_meta (
                        key   TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                """)
                self._conn.execute("""
                    CREATE TABLE IF NOT EXISTS btcp_state (
                        kind       TEXT NOT NULL,
                        key        TEXT NOT NULL,
                        type_tag   TEXT NOT NULL,
                        payload    TEXT NOT NULL,   -- JSON
                        updated_at REAL NOT NULL,
                        PRIMARY KEY (kind, key)
                    )
                """)
                row = self._conn.execute(
                    "SELECT value FROM btcp_meta WHERE key = 'schema_version'"
                ).fetchone()
                if row is None:
                    self._conn.execute(
                        "INSERT OR REPLACE INTO btcp_meta (key, value) "
                        "VALUES ('schema_version', ?)",
                        (str(SCHEMA_VERSION),),
                    )
                else:
                    existing = int(row[0])
                    if existing > SCHEMA_VERSION:
                        raise RuntimeError(
                            f"{self._path}: btcp_state schema v{existing} is newer "
                            f"than this runtime supports (v{SCHEMA_VERSION}) — "
                            f"upgrade TRION before reading this store."
                        )
                    if existing < SCHEMA_VERSION:
                        self._migrate(existing)

    def _migrate(self, from_version: int) -> None:
        """Bring an older schema up to SCHEMA_VERSION (in-transaction)."""
        # v1 is the first schema — nothing to migrate yet.
        self._conn.execute(
            "INSERT OR REPLACE INTO btcp_meta (key, value) "
            "VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )

    # ── Core generic API ────────────────────────────────────────────────

    def save(self, kind: str, key: str, payload: Any, type_tag: str) -> None:
        """Upsert one row (transactional write-through)."""
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        with self._lock:
            with self._conn:
                self._conn.execute(
                    "INSERT OR REPLACE INTO btcp_state "
                    "(kind, key, type_tag, payload, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (kind, key, type_tag, blob, time.time()),
                )

    def delete(self, kind: str, key: str) -> None:
        """Remove one row (transactional)."""
        with self._lock:
            with self._conn:
                self._conn.execute(
                    "DELETE FROM btcp_state WHERE kind = ? AND key = ?",
                    (kind, key),
                )

    def load_all(self, kind: str) -> Dict[str, Tuple[str, Any]]:
        """Read every row of a kind: {key: (type_tag, payload)}.

        Corrupt rows are skipped — the store is a rebuildable cache and must
        never crash a module's startup.
        """
        with self._lock:
            rows = self._conn.execute(
                "SELECT key, type_tag, payload FROM btcp_state WHERE kind = ?",
                (kind,),
            ).fetchall()
        out: Dict[str, Tuple[str, Any]] = {}
        for key, type_tag, blob in rows:
            try:
                out[key] = (type_tag, json.loads(blob))
            except (ValueError, TypeError):
                continue
        return out

    # ── Typed convenience API ───────────────────────────────────────────

    # Routes (orchestrator)
    def save_route(self, route_id: str, payload: Any, type_tag: str) -> None:
        self.save(KIND_ROUTE, route_id, payload, type_tag)

    def get_routes(self) -> Dict[str, Tuple[str, Any]]:
        return self.load_all(KIND_ROUTE)

    def delete_route(self, route_id: str) -> None:
        self.delete(KIND_ROUTE, route_id)

    # Reserve balances (router) — plain key/value rows
    def save_balance(self, entity_key: str, reserved: float) -> None:
        self.save(KIND_BALANCE, entity_key, {"reserved": float(reserved)}, BALANCE_ROW_TYPE)

    def get_balances(self) -> Dict[str, float]:
        return {
            key: float(payload.get("reserved", 0.0))
            for key, (_tag, payload) in self.load_all(KIND_BALANCE).items()
        }

    # Escrows (escrow_monitor)
    def save_escrow(self, escrow_id: str, payload: Any, type_tag: str) -> None:
        self.save(KIND_ESCROW, escrow_id, payload, type_tag)

    def get_escrows(self) -> Dict[str, Tuple[str, Any]]:
        return self.load_all(KIND_ESCROW)

    def delete_escrow(self, escrow_id: str) -> None:
        self.delete(KIND_ESCROW, escrow_id)

    # Dispute cases (dispute_resolution)
    def save_case(self, case_id: str, payload: Any, type_tag: str) -> None:
        self.save(KIND_CASE, case_id, payload, type_tag)

    def get_cases(self) -> Dict[str, Tuple[str, Any]]:
        return self.load_all(KIND_CASE)

    # Annotators (dispute_resolution)
    def save_annotator(self, annotator_id: str, payload: Any, type_tag: str) -> None:
        self.save(KIND_ANNOTATOR, annotator_id, payload, type_tag)

    def get_annotators(self) -> Dict[str, Tuple[str, Any]]:
        return self.load_all(KIND_ANNOTATOR)

    # ── Lifecycle ───────────────────────────────────────────────────────

    @property
    def path(self) -> str:
        return self._path

    def close(self) -> None:
        """Close the SQLite connection (idempotent, best-effort)."""
        with self._lock:
            try:
                self._conn.close()
            except Exception:  # pragma: no cover - already closed
                pass

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"BtcpStateStore(path={self._path!r}, schema=v{SCHEMA_VERSION})"


# ── Self-test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== BTCP State Store Self-test ===\n")

    import tempfile as _tempfile

    _db = os.path.join(_tempfile.mkdtemp(prefix="btcp_state_selftest_"), "btcp_state.db")

    # Test 1: schema bootstrap + round-trip
    store = BtcpStateStore(state_db=_db)
    assert os.path.exists(_db)
    store.save_escrow("esc1", {"escrow_id": "esc1", "amount": 1000.0}, "escrow_v1")
    rows = store.get_escrows()
    assert rows["esc1"] == ("escrow_v1", {"escrow_id": "esc1", "amount": 1000.0})
    print("✓ schema created + escrow row round-trips")

    # Test 2: a second store on the same file sees the row (restart survival)
    store2 = BtcpStateStore(state_db=_db)
    assert store2.get_escrows()["esc1"][1]["amount"] == 1000.0
    print("✓ second instance on same DB sees persisted state")

    # Test 3: upsert + delete
    store.save_escrow("esc1", {"escrow_id": "esc1", "amount": 999.0}, "escrow_v1")
    assert store2.get_escrows()["esc1"][1]["amount"] == 999.0  # upsert visible
    store.delete_escrow("esc1")
    assert "esc1" not in store2.get_escrows()
    print("✓ upsert and delete work")

    # Test 4: balances kv
    store.save_balance(b"\x01".hex(), 42.5)
    assert store2.get_balances() == {"01": 42.5}
    print("✓ balance kv round-trips")

    # Test 5: unknown type tags survive as data (forward compat)
    store.save_escrow("esc2", {"x": 1}, "escrow_v999")
    assert store2.get_escrows()["esc2"][0] == "escrow_v999"
    print("✓ type tag preserved for forward compatibility")

    # Test 6: schema version recorded
    version = store._conn.execute(
        "SELECT value FROM btcp_meta WHERE key='schema_version'"
    ).fetchone()[0]
    assert int(version) == SCHEMA_VERSION
    print(f"✓ schema_version = {SCHEMA_VERSION}")

    store.close()
    store2.close()
    print("\nBTCP STATE STORE — ALL TESTS PASS")
