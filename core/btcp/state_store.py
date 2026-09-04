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
  * The six ``btcp_*`` tables declared by the repo's ``schema.sql``
    (btcp_intent_registry, btcp_routes, btcp_escrow_states,
    btcp_version_registry, btcp_cross_chain_messages,
    btcp_route_rewards) are created here as SQLite-compatible mirrors of
    the Postgres/TimescaleDB DDL and written by the ``record_*`` methods —
    schema.sql's tables are no longer dead DDL (BTCP gap #7).  Writers:
    orchestrator step-6 execution records
    (``core/btcp/orchestrator.py:_record_execution``), route-status
    updates, and the ``save_escrow`` projection for escrow states.
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
    "BTCP_ADAPTER_VERSION",
    "BTCP_PROJECTION_TABLES",
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


# ── schema.sql BTCP projection tables (gap #7) ──────────────────────────────
# schema.sql declares six btcp_* tables as Postgres/TimescaleDB DDL; this
# SQLite store is the operative BTCP database, so the DDL below mirrors the
# schema.sql column names 1:1 with SQLite-compatible types
# (BYTEA→TEXT hex, NUMERIC→REAL, TIMESTAMPTZ→REAL unix epoch, enums→TEXT,
# BOOLEAN→INTEGER 0/1).  Deviations, all documented inline:
#   * REFERENCES/FK constraints omitted (SQLite does not enforce them by
#     default; the generic btcp_state store has always been FK-free).
#   * btcp_escrow_states.chain_id / destination and
#     btcp_cross_chain_messages.expiry_block are nullable here: the python
#     EscrowMonitor is chain-agnostic and the orchestrator has no block
#     height context — those columns are Rust-indexer domain.
#   * btcp_route_rewards carries a UNIQUE(epoch, validator_address, route_id)
#     index so replayed completion events cannot double-pay (schema.sql's
#     BIGSERIAL id has no such guard).
#   * btcp_escrow_states.state stores the python superset of the
#     schema.sql enum (PENDING_AKASHIC, EMERGENCY_REVERTED included).
# Writers: core/btcp/orchestrator.py (step-6 execution records + status
# updates + route rewards) and this module's save_escrow projection.

BTCP_ADAPTER_VERSION = "1.0.0"  # spec §4.1 default; VersionHandler min_verifier_version

BTCP_PROJECTION_TABLES = (
    "btcp_intent_registry",
    "btcp_routes",
    "btcp_escrow_states",
    "btcp_version_registry",
    "btcp_cross_chain_messages",
    "btcp_route_rewards",
)

_BTCP_TABLE_DDL = (
    """
    CREATE TABLE IF NOT EXISTS btcp_intent_registry (
        intent_hash         TEXT    PRIMARY KEY,
        entity_id           TEXT    NOT NULL,
        action              TEXT    NOT NULL,
        asset_in            TEXT,
        asset_out           TEXT,
        magnitude           REAL    NOT NULL,
        source_chain_id     INTEGER NOT NULL,
        deadline_block      INTEGER,
        deadline_ts         REAL,
        max_gas_usd         REAL,
        min_finality        INTEGER DEFAULT 1,
        min_nl_score        REAL    DEFAULT 0.30,
        chain_pref          TEXT    DEFAULT 'OPTIMAL',
        privacy_mode        TEXT    DEFAULT 'PUBLIC',
        btcp_version        TEXT    NOT NULL DEFAULT '1.0.0',
        nonce               INTEGER NOT NULL DEFAULT 0,
        route_selected      TEXT,
        status              TEXT    DEFAULT 'PENDING',
        btcp_score          REAL,
        created_at          REAL    NOT NULL,
        routed_at           REAL,
        completed_at        REAL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS btcp_routes (
        route_id                TEXT    PRIMARY KEY,
        intent_hash             TEXT    NOT NULL,
        route_type              TEXT    NOT NULL,
        anchor_bh               TEXT    NOT NULL,
        execution_bh            TEXT,
        anchor_chain            INTEGER NOT NULL,
        execution_chain         INTEGER NOT NULL,
        entity_id               TEXT    NOT NULL,
        counterparty_entity_id  TEXT,
        btcp_score              REAL    NOT NULL,
        nl_score                REAL,
        gas_saved_vs_bridge     REAL,
        gas_saved_vs_single     REAL,
        gas_total_usd           REAL,
        beo_continuity_score    REAL,
        cc_coherence            REAL,
        mf_score                REAL,
        consensus_hhi           REAL,
        coherence_at_emission   REAL,
        travel_rule_proof       TEXT,
        btcp_version            TEXT    NOT NULL DEFAULT '1.0.0',
        status                  TEXT    NOT NULL DEFAULT 'PENDING',
        failure_cause           TEXT,
        created_at              REAL    NOT NULL,
        finalized_at            REAL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS btcp_escrow_states (
        escrow_id           TEXT    PRIMARY KEY,
        route_id            TEXT    NOT NULL,
        entity_id           TEXT    NOT NULL,
        chain_id            INTEGER,           -- schema.sql: NOT NULL (Rust layer knows the chain)
        contract_address    TEXT,
        amount              REAL    NOT NULL,
        token_address       TEXT,
        lock_block          INTEGER NOT NULL,
        timeout_blocks      INTEGER NOT NULL DEFAULT 300,
        state               TEXT    NOT NULL DEFAULT 'HOLDING',
        destination         TEXT,              -- schema.sql: NOT NULL (Rust layer knows it)
        tx_hash_lock        TEXT,
        tx_hash_release     TEXT,
        created_at          REAL    NOT NULL,
        resolved_at         REAL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS btcp_version_registry (
        chain_id                INTEGER NOT NULL,
        adapter_version         TEXT    NOT NULL,
        min_verifier_version    TEXT    NOT NULL DEFAULT '1.0.0',
        feature_flags           TEXT    NOT NULL DEFAULT '{}',
        registered_at           REAL    NOT NULL,
        last_seen_at            REAL    NOT NULL,
        is_deprecated           INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (chain_id, adapter_version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS btcp_cross_chain_messages (
        message_id          TEXT    PRIMARY KEY,   -- SHA3 replay-prevention ID
        msg_type            TEXT    NOT NULL,
        sender_entity_id    TEXT    NOT NULL,
        sender_chain        INTEGER NOT NULL,
        target_chain        INTEGER NOT NULL,
        nonce               INTEGER NOT NULL,
        expiry_block        INTEGER,               -- schema.sql: NOT NULL (block heights are indexer domain)
        expiry_ts           REAL    NOT NULL,
        payload_hash        TEXT    NOT NULL,
        btcp_version        TEXT    NOT NULL DEFAULT '1.0.0',
        status              TEXT    NOT NULL DEFAULT 'ACCEPTED',
        reject_reason       TEXT,
        created_at          REAL    NOT NULL
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_msg_nonce_unique
        ON btcp_cross_chain_messages (sender_entity_id, sender_chain, target_chain, nonce)
    """,
    """
    CREATE TABLE IF NOT EXISTS btcp_route_rewards (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        epoch                   INTEGER NOT NULL,
        validator_address       TEXT    NOT NULL,
        route_id                TEXT,
        base_reward             REAL    NOT NULL DEFAULT 0,
        coverage_bonus_factor   REAL    NOT NULL DEFAULT 1.0,
        emergency_multiplier    REAL    NOT NULL DEFAULT 1.0,
        final_reward            REAL    NOT NULL DEFAULT 0,
        diversity_weight        REAL    NOT NULL DEFAULT 1.0,
        coverage_rate           REAL    NOT NULL DEFAULT 1.0,
        uptime_7d               REAL    NOT NULL DEFAULT 1.0,
        rewarded_at             REAL    NOT NULL
    )
    """,
    # Idempotency guard (deviation from schema.sql, see block comment above):
    # a replayed route-completion event must not double-pay the pools.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_rewards_replay_guard
        ON btcp_route_rewards (epoch, validator_address, route_id)
    """,
)


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
                # BTCP gap #7: the schema.sql btcp_* tables exist (and get
                # written) in the operative SQLite store too. CREATE TABLE IF
                # NOT EXISTS makes this a no-op on already-initialized stores,
                # so pre-gap-#7 databases are migrated in place, idempotently.
                for ddl in _BTCP_TABLE_DDL:
                    self._conn.execute(ddl)
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
        # BTCP gap #7: escrow_monitor's write-through also lands in the
        # schema.sql btcp_escrow_states projection (same payload, same key).
        # Only rows that actually look like escrow_monitor's escrow_v1 rows
        # are projected — a generic/partial payload is skipped, and a
        # projection failure must never break the module's own write path.
        if type_tag == "escrow_v1" and isinstance(payload, dict):
            try:
                self._project_escrow_row(escrow_id, payload)
            except Exception:
                pass

    def _project_escrow_row(self, escrow_id: str, payload: Dict[str, Any]) -> None:
        """escrow_monitor's escrow_v1 row → btcp_escrow_states projection."""
        required = ("route_id", "entity_id", "amount", "lock_block")
        if any(payload.get(k) is None for k in required):
            return  # not a full escrow row (e.g. self-test partial payload)
        resolved_at = payload.get("settled_at")
        if resolved_at is None:
            resolved_at = payload.get("reverted_at")
        self.record_escrow(
            escrow_id,
            route_id=str(payload["route_id"]),
            entity_id=str(payload["entity_id"]),
            amount=float(payload["amount"]),
            lock_block=int(payload["lock_block"]),
            timeout_blocks=int(payload.get("timeout_blocks", 300)),
            state=str(payload.get("state", "HOLDING")),
            created_at=payload.get("lock_timestamp"),
            resolved_at=resolved_at,
            # chain_id / destination / contract_address / tx hashes are
            # Rust-escrow-layer fields — NULL here (see DDL comment).
        )

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

    # ── schema.sql btcp_* projection writers (gap #7) ────────────────────
    # These mirror the schema.sql tables column-for-column.  All writers are
    # idempotent (upserts keyed on the table PK / replay guards) so a re-run
    # of the orchestrator sequence neither duplicates rows nor crashes.

    def _btcp_upsert(self, table: str, row: Dict[str, Any],
                     ignore: bool = False) -> None:
        """INSERT (OR REPLACE | OR IGNORE) into a btcp_* projection table.

        Unknown column names are dropped (typo protection); values use the
        row dict's own types (SQLite stores them per-column affinity).
        """
        if table not in BTCP_PROJECTION_TABLES:
            raise ValueError(f"not a btcp_* projection table: {table!r}")
        cols = [c for c in row if self._is_btcp_column(table, c)]
        if not cols:
            return
        verb = "INSERT OR IGNORE" if ignore else "INSERT OR REPLACE"
        sql = (
            f"{verb} INTO {table} ({', '.join(cols)}) "
            f"VALUES ({', '.join('?' * len(cols))})"
        )
        with self._lock:
            with self._conn:
                self._conn.execute(sql, tuple(row[c] for c in cols))

    def _is_btcp_column(self, table: str, column: str) -> bool:
        """True when ``column`` exists in ``table`` (cached per connection)."""
        cache = getattr(self, "_btcp_columns", None)
        if cache is None:
            cache = self._btcp_columns = {}
        if table not in cache:
            rows = self._conn.execute(f"PRAGMA table_info({table})").fetchall()
            cache[table] = {r[1] for r in rows}
        return column in cache[table]

    def record_intent(self, intent_hash: str, **columns: Any) -> None:
        """Upsert one btcp_intent_registry row (schema.sql §Intent Registry)."""
        row = {"intent_hash": intent_hash, **columns}
        if "created_at" not in row or row["created_at"] is None:
            row["created_at"] = time.time()
        self._btcp_upsert("btcp_intent_registry", row)

    def record_route(self, route_id: str, **columns: Any) -> None:
        """Upsert one btcp_routes row (schema.sql §BTCP Routes)."""
        row = {"route_id": route_id, **columns}
        if "created_at" not in row or row["created_at"] is None:
            row["created_at"] = time.time()
        self._btcp_upsert("btcp_routes", row)

    def record_escrow(self, escrow_id: str, **columns: Any) -> None:
        """Upsert one btcp_escrow_states row (schema.sql §Escrow States)."""
        row = {"escrow_id": escrow_id, **columns}
        if "created_at" not in row or row["created_at"] is None:
            row["created_at"] = time.time()
        self._btcp_upsert("btcp_escrow_states", row)

    def record_cross_chain_message(self, message_id: str, **columns: Any) -> None:
        """Insert one btcp_cross_chain_messages row (replay-prevention log).

        INSERT OR IGNORE: the message_id PK (and the unique
        (sender, source, target, nonce) index) make re-broadcasting the same
        message a no-op instead of a duplicate audit-trail row.
        """
        row = {"message_id": message_id, **columns}
        if "created_at" not in row or row["created_at"] is None:
            row["created_at"] = time.time()
        self._btcp_upsert("btcp_cross_chain_messages", row, ignore=True)

    def record_route_reward(self, epoch: int, validator_address: str,
                            route_id: Optional[str], base_reward: float,
                            final_reward: Optional[float] = None,
                            **columns: Any) -> None:
        """Insert one btcp_route_rewards row (schema.sql §Route Rewards, Fix 4).

        Idempotent via the (epoch, validator_address, route_id) replay guard:
        a route-completion event replayed by a supervisor does not double-pay.
        """
        row = {
            "epoch": int(epoch),
            "validator_address": validator_address,
            "route_id": route_id,
            "base_reward": float(base_reward),
            "final_reward": float(
                final_reward if final_reward is not None else base_reward
            ),
            "rewarded_at": time.time(),
            **columns,
        }
        self._btcp_upsert("btcp_route_rewards", row, ignore=True)

    def record_version(self, chain_id: int,
                       adapter_version: str = BTCP_ADAPTER_VERSION,
                       min_verifier_version: str = "1.0.0",
                       feature_flags: Optional[Dict[str, Any]] = None) -> None:
        """Upsert one btcp_version_registry row for a chain the engine touched.

        Registers the (chain_id, adapter_version) pair on first sight and
        refreshes last_seen_at on every subsequent route — per-chain adapter
        version tracking for protocol upgrade routing (§2.16).
        """
        now = time.time()
        flags = json.dumps(feature_flags or {}, sort_keys=True)
        with self._lock:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO btcp_version_registry
                        (chain_id, adapter_version, min_verifier_version,
                         feature_flags, registered_at, last_seen_at, is_deprecated)
                    VALUES (?, ?, ?, ?, ?, ?, 0)
                    ON CONFLICT (chain_id, adapter_version)
                    DO UPDATE SET last_seen_at = excluded.last_seen_at
                    """,
                    (int(chain_id), adapter_version, min_verifier_version,
                     flags, now, now),
                )

    def read_btcp_table(self, table: str) -> list:
        """Read every row of a btcp_* projection table as dicts (whitelisted)."""
        if table not in BTCP_PROJECTION_TABLES:
            raise ValueError(f"not a btcp_* projection table: {table!r}")
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            try:
                rows = self._conn.execute(f"SELECT * FROM {table}").fetchall()
            finally:
                self._conn.row_factory = None
        return [dict(r) for r in rows]

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

    # Test 7: the six schema.sql btcp_* projection tables exist and round-trip
    for table in BTCP_PROJECTION_TABLES:
        n = store._conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()[0]
        assert n == 1, f"missing projection table {table}"
    store.record_intent(
        "ih1", entity_id="0xabc", action="TRANSFER", magnitude=1000.0,
        source_chain_id=1, nonce=7, status="ROUTING",
    )
    store.record_intent(
        "ih1", entity_id="0xabc", action="TRANSFER", magnitude=1000.0,
        source_chain_id=1, nonce=7, status="COMPLETED", completed_at=1.5,
    )  # upsert — one row, latest status
    intents = store.read_btcp_table("btcp_intent_registry")
    assert len(intents) == 1 and intents[0]["status"] == "COMPLETED"
    store.record_cross_chain_message("m1", msg_type="IntentBroadcast",
                                     sender_entity_id="0xabc", sender_chain=1,
                                     target_chain=137, nonce=7, expiry_ts=99.0,
                                     payload_hash="0x" + "00" * 32)
    store.record_cross_chain_message("m1", msg_type="IntentBroadcast",
                                     sender_entity_id="0xabc", sender_chain=1,
                                     target_chain=137, nonce=7, expiry_ts=99.0,
                                     payload_hash="0x" + "00" * 32)  # replay
    assert len(store.read_btcp_table("btcp_cross_chain_messages")) == 1
    store.record_route_reward(0, "anchor_pool:1", "route_1", 60.0)
    store.record_route_reward(0, "anchor_pool:1", "route_1", 60.0)  # replay
    assert len(store.read_btcp_table("btcp_route_rewards")) == 1
    store.record_version(1)
    store.record_version(1)  # upsert — last_seen_at refreshes, one row
    versions = store.read_btcp_table("btcp_version_registry")
    assert len(versions) == 1 and versions[0]["adapter_version"] == "1.0.0"
    print("✓ six btcp_* projection tables round-trip + idempotent")

    # Test 8: escrow_v1 write-through projects into btcp_escrow_states
    store.save_escrow("esc9", {
        "escrow_id": "esc9", "route_id": "route_1", "entity_id": "01" * 16,
        "amount": 5.0, "lock_block": 10, "lock_timestamp": 1000.0,
        "timeout_blocks": 300, "state": "HOLDING", "revert_reason": "TIMEOUT",
        "settled_at": None, "reverted_at": None, "parent_escrow_id": None,
        "settlement_verified": False,
    }, "escrow_v1")
    escrows = store.read_btcp_table("btcp_escrow_states")
    assert len(escrows) == 1 and escrows[0]["route_id"] == "route_1"
    assert escrows[0]["state"] == "HOLDING"
    assert store2.get_escrows()["esc9"][1]["amount"] == 5.0  # original path intact
    print("✓ escrow write-through projects into btcp_escrow_states")

    store.close()
    store2.close()
    print("\nBTCP STATE STORE — ALL TESTS PASS")
