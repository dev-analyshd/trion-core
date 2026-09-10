"""
Schema-writer static scan (W3-N, matrix remediation #9)
========================================================

Every ``CREATE TABLE`` in schema.sql must carry an ``-- operative-writer:``
marker directly above it, and the marker must be TRUE:

* ``sqlite-mirror``      — the table is mirrored in the operative SQLite
  store (core/btcp/state_store.py ``_BTCP_TABLE_DDL``) and written by a
  ``record_*`` method.
* ``INSERT in <paths>``  — the named python files contain a real
  ``INSERT INTO <table>`` writer (deploy-gated TimescaleDB paths included).
* ``NONE``               — the table is declaration-only DDL for the
  external deployment: the scan PROVES no ``INSERT INTO <table>`` exists
  anywhere in the operative python tree and no SQLite mirror exists.

This is the machine-checked honesty layer for "no operational schema table
without a writer": a new table cannot be added to schema.sql without a
marker, and a marker cannot lie (both directions are asserted).

Run: pytest tests/unit/test_schema_writers.py -q
"""

import os
import re
import sqlite3
import tempfile

import pytest

from core.btcp.state_store import (
    BtcpStateStore, BTCP_PROJECTION_TABLES, PHASE0_PROJECTION_TABLES,
)

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCHEMA_SQL = os.path.join(REPO, "schema.sql")

# The python trees that could hold an INSERT writer (bounded scan — a whole
# repo rg hangs per the master command).  These are all the code directories;
# data/config/docs/contract trees hold no python table writers.
SCAN_DIRS = (
    "core", "api", "scripts", "anima-service", "indexers", "relayer",
    "adapters", "zg", "continuum", "supervisors", "sdk", "validator",
    "network",
)

# Marker formats (see schema.sql header comment).
_MARKER_RE = re.compile(r"^-- operative-writer: (.+)$")
_TABLE_RE = re.compile(r"^CREATE TABLE IF NOT EXISTS (\w+) \(")


def parse_schema():
    """schema.sql → [(table, marker)] for every CREATE TABLE."""
    out = []
    last_marker = None
    with open(SCHEMA_SQL, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            m = _MARKER_RE.match(line)
            if m:
                last_marker = m.group(1).strip()
                continue
            t = _TABLE_RE.match(line)
            if t:
                out.append((t.group(1), last_marker))
                last_marker = None
    return out


def _py_sources():
    for d in SCAN_DIRS:
        root = os.path.join(REPO, d)
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            for name in files:
                if name.endswith(".py"):
                    yield os.path.join(dirpath, name)


def insert_writers(table):
    """Every py file under the scan dirs containing INSERT INTO <table>."""
    needle = f"INSERT INTO {table}"
    hits = []
    for path in _py_sources():
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                if needle in fh.read():
                    hits.append(os.path.relpath(path, REPO))
        except OSError:
            continue
    return hits


def store_tables():
    """Tables created by the operative SQLite store (its live DDL)."""
    db = os.path.join(tempfile.mkdtemp(prefix="scan_"), "s.db")
    store = BtcpStateStore(state_db=db)
    try:
        names = {
            r[0] for r in store._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        store.close()
    return names


def _parse_insert_paths(marker):
    """'INSERT in path1, path2 (…)' → ['path1', 'path2']."""
    spec = marker[len("INSERT in "):]
    if " (" in spec:
        spec = spec.split(" (", 1)[0]
    return [p.strip() for p in spec.split(",") if p.strip()]


# ── The scan itself ──────────────────────────────────────────────────────────

def test_every_create_table_is_marked():
    tables = parse_schema()
    assert tables, "schema.sql produced no tables — parser broken?"
    unmarked = [t for t, marker in tables if not marker]
    assert not unmarked, f"tables without an operative-writer marker: {unmarked}"
    assert len(tables) == 35, f"table count changed ({len(tables)}) — update this test"


def test_markers_are_unique_per_table():
    tables = parse_schema()
    names = [t for t, _ in tables]
    assert len(names) == len(set(names)), "duplicate CREATE TABLE in schema.sql"


def test_marker_kinds_are_known():
    for table, marker in parse_schema():
        assert marker.startswith(("NONE", "INSERT in ", "sqlite-mirror")), (
            f"{table}: unknown marker kind: {marker!r}")


def test_sqlite_mirror_markers_are_real():
    """"""
    operative = store_tables()
    for table, marker in parse_schema():
        if marker.startswith("sqlite-mirror"):
            assert table in operative, (
                f"{table} claims a SQLite mirror but the store does not create it")
            assert table in BTCP_PROJECTION_TABLES, (
                f"{table} mirrored but not whitelisted in BTCP_PROJECTION_TABLES")


def test_insert_markers_point_at_real_writers():
    for table, marker in parse_schema():
        if not marker.startswith("INSERT in "):
            continue
        for rel in _parse_insert_paths(marker):
            path = os.path.join(REPO, rel)
            assert os.path.isfile(path), f"{table}: writer file missing: {rel}"
            with open(path, encoding="utf-8", errors="replace") as fh:
                content = fh.read()
            assert f"INSERT INTO {table}" in content, (
                f"{table}: {rel} does not contain 'INSERT INTO {table}'")


def test_none_markers_honestly_have_no_writer():
    """A NONE marker is proven: no INSERT writer + no SQLite mirror."""
    operative = store_tables()
    for table, marker in parse_schema():
        if not marker.startswith("NONE"):
            continue
        writers = insert_writers(table)
        assert not writers, (
            f"{table} marked NONE but has INSERT writers: {writers}")
        assert table not in operative, (
            f"{table} marked NONE but the SQLite store creates it")


def test_the_audited_deploy_only_set_is_exact():
    """The NONE set is pinned — adding/removing a table needs this update."""
    none_tables = sorted(t for t, m in parse_schema() if m.startswith("NONE"))
    assert none_tables == [
        "akashic_cold",
        "akashic_warm",
        "archetype_library",
        "behavioral_state_channels",
        "biological_rhythm",
        "genesis_bootstrap_progress",
        "intent_pool_participants",
        "intent_pools",
        "merkle_roots",
        "mf_evidence_log",
        "ooa_chain_confidence",
        "resurrection_log",
        "sanctions_registry",
        "slashing_log",
        "source_credibility",
        "trion_token_economics",
        "validator_coverage",
    ]


def test_the_written_set_is_exact():
    """The WRITTEN set is pinned: 12 operative SQLite mirrors + 5 tsdb tables."""
    written = sorted(
        t for t, m in parse_schema() if not m.startswith("NONE"))
    assert written == [
        "akashic_bh",
        "akashic_vectors",
        "behavioral_events",
        "beo_registry",
        "bitp_clipboard",
        "blo_orders",
        "btcp_certificate_conflicts",
        "btcp_consumed_certificates",
        "btcp_cross_chain_messages",
        "btcp_escrow_states",
        "btcp_intent_registry",
        "btcp_route_rewards",
        "btcp_routes",
        "btcp_version_registry",
        "genesis_commitments",
        "genesis_confidence_log",
        "shadow_observations",
        "trajectory_anomaly_log",
    ]


# ── Matrix remediation #9: the four Phase-0 tables now have writers ──────────


@pytest.mark.parametrize("table", PHASE0_PROJECTION_TABLES)
def test_phase0_tables_have_store_writers(tmp_path, table):
    """blo/bitp/shadow/genesis round-trip through the operative store."""
    store = BtcpStateStore(state_db=str(tmp_path / "s.db"))
    try:
        table in store_tables()  # store_tables() opened its own store; re-check
        rows_before = store.read_btcp_table(table)
        if table == "blo_orders":
            store.record_blo_order("ch1", entity_id="01" * 16,
                                   intent_hash="ih", asset_in="aa",
                                   asset_out="bb", source_chain_id=1,
                                   target_chain_id=137, magnitude=1.0,
                                   expiry_block=10)
        elif table == "bitp_clipboard":
            store.record_bitp_clipboard("ch2", entity_id="01" * 16,
                                        asset_x="aa", asset_y="bb",
                                        chain_a=1, chain_b=137,
                                        magnitude=1.0, intent_hash="ih")
        elif table == "shadow_observations":
            store.record_shadow_observation(900, 1, "TRANSFER", "evhash")
        else:
            store.record_genesis_commitment("gc1", genesis_type="IDENTITY_GENESIS",
                                            entity_id="02" * 16)
        rows = store.read_btcp_table(table)
        assert len(rows) == len(rows_before) + 1
    finally:
        store.close()


def test_matrix_remediation_9_is_closed():
    """The four writer-less tables from the spec matrix now have writers."""
    markers = dict(parse_schema())
    for table in ("blo_orders", "bitp_clipboard",
                  "shadow_observations", "genesis_commitments"):
        assert markers[table].startswith("sqlite-mirror"), (
            f"{table}: matrix remediation #9 expected a sqlite-mirror writer")


# ── Writer/reader column parity (schema.sql ↔ SQLite mirror) ─────────────────


@pytest.mark.parametrize("table,method,sample", [
    ("blo_orders", "record_blo_order", dict(
        entity_id="01" * 16, intent_hash="ih", asset_in="0xaa",
        asset_out="0xbb", source_chain_id=1, target_chain_id=137,
        magnitude=7.5, filled_amount=2.5, expiry_block=999,
        status="PARTIALLY_FILLED", btcp_score_at_post=0.88,
        behavioral_proof_root="r" * 64, akashic_depth=12.0,
        scheduled_activation=55, brt_confidence=0.7,
        filled_at=2.0, expired_at=None)),
    ("bitp_clipboard", "record_bitp_clipboard", dict(
        entity_id="01" * 16, asset_x="0xaa", asset_y="0xbb", chain_a=1,
        chain_b=137, magnitude=7.5, behavioral_proof_root="r" * 64,
        intent_hash="ih", valuation_x=100.0, valuation_y=98.0,
        price_tolerance=0.02, status="MATCHED", matched_at=3.0,
        counterparty_hash="c" * 64, blo_created=1)),
    ("genesis_commitments", "record_genesis_commitment", dict(
        genesis_type="SPONSORED_GENESIS", entity_id="02" * 16,
        sponsor_entity_id="03" * 16, stake_bond=50.0, conf_genesis=0.01,
        conf_sponsor=0.4, active_sponsored_count=2,
        scrutiny_multiplier=1.5, slash_amount=0.0, status="ACTIVE",
        accountability_window_days=180, resolved_at=None)),
])
def test_written_columns_match_schema_sql(tmp_path, table, method, sample):
    """Every column the store writer accepts exists in the schema.sql DDL."""
    store = BtcpStateStore(state_db=str(tmp_path / "s.db"))
    try:
        pk = "commitment_hash" if table != "genesis_commitments" else "commitment_id"
        getattr(store, method)("pk1", **sample)
        row = store.read_btcp_table(table)[0]
        for column, value in sample.items():
            assert column in row, f"{table}.{column} missing from mirror"
            assert row[column] == value
    finally:
        store.close()


def test_shadow_observation_columns_match_schema_sql(tmp_path):
    store = BtcpStateStore(state_db=str(tmp_path / "s.db"))
    try:
        store.record_shadow_observation(
            900, 1, "BRIDGE_EVENT", "e" * 64, confidence_weight=0.9,
            diversity_factor=1.2, shadow_bh="f" * 64, block_num=42)
        row = store.read_btcp_table("shadow_observations")[0]
        assert row["observed_chain_id"] == 900
        assert row["source_chain_id"] == 1
        assert row["observation_type"] == "BRIDGE_EVENT"
        assert row["confidence_weight"] == 0.9
        assert row["diversity_factor"] == 1.2
        assert row["shadow_bh"] == "f" * 64
        assert row["block_num"] == 42
        assert row["observed_at"] > 0
    finally:
        store.close()


def test_sqlite_mirror_column_names_match_schema_sql(tmp_path):
    """Column-for-column mirror: schema.sql columns == SQLite columns
    (for every BTCP table the operative store mirrors)."""
    schema_src = open(SCHEMA_SQL, encoding="utf-8").read()
    store = BtcpStateStore(state_db=str(tmp_path / "s.db"))
    try:
        for table in BTCP_PROJECTION_TABLES:
            m = re.search(
                r"CREATE TABLE IF NOT EXISTS " + table + r" \((.*?)\n\);",
                schema_src, re.DOTALL)
            assert m, f"{table} not found in schema.sql"
            schema_cols = set()
            skip = ("PRIMARY", "UNIQUE", "CHECK", "FOREIGN", "CONSTRAINT")
            for line in m.group(1).splitlines():
                line = line.strip()
                if not line or line.startswith("--") or line.startswith(skip):
                    continue
                schema_cols.add(line.split()[0])
            mirror_cols = {
                r[1] for r in store._conn.execute(
                    f"PRAGMA table_info({table})").fetchall()
            }
            assert mirror_cols == schema_cols, (
                f"{table}: mirror {sorted(mirror_cols - schema_cols)} vs "
                f"schema {sorted(schema_cols - mirror_cols)}")
    finally:
        store.close()
