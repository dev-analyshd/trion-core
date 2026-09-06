"""Spec-table presence pins for the TimescaleDB reference DDL (M-215).

Wave-6 schema alignment: the D3 (BTCP master spec) extraction names every
TimescaleDB table the spec requires — §5.5's five-table full DDL
(D3-127), §14.1 Phase 0's seven-table list (D3-214), the version registry
and the IAP pool (D3-116). This battery parses schema.sql and asserts:

  * every spec-named table exists as CREATE TABLE DDL,
  * the D3-127 abridged column lists are covered column-by-column
    (the repo tables are supersets — spec columns must all be present),
  * the behavioral_event_type enum carries exactly the canonical 20
    event types, compared against the authoritative Python enum
    (core/primitives/behavioral_hash.EventType — read-only import),
  * the akashic_bh hypertable + compression policy (the file's Timescale
    conventions) are declared.

M-215's residual depth gap is writer-side, not DDL-side: 17 of the 35
tables carry `-- operative-writer: NONE` (declaration-only, pinned
separately by test_schema_writers.py). Nothing in the spec's table list
is missing here — this file pins that statement so a dropped table fails
loudly.

Run: pytest tests/unit/test_schema_spec_tables.py -q
"""
import os
import re

import pytest

from core.primitives.behavioral_hash import EventType  # read-only source of truth

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCHEMA_SQL = os.path.join(REPO, "schema.sql")

# ── The D3 spec's table list ──────────────────────────────────────────────────
# D3-127 §5.5 full DDL (five tables) + D3-214 §14.1 Phase 0 (seven tables,
# superset of the five) + btcp_version_registry + intent_pools (D3-116).
SPEC_TABLES = (
    # §14.1 Phase 0 / D3-214 — the seven-table list (CRITICAL priority).
    "btcp_intent_registry", "btcp_routes", "btcp_escrow_states",
    "bitp_clipboard", "blo_orders", "shadow_observations",
    "genesis_commitments",
    # Additional spec-named tables: version registry (§11 Fix 3) and the
    # IAP pool structure (§5.3 / D3-116).
    "btcp_version_registry", "intent_pools",
)

# D3-127 abridged column lists — every spec column must exist in the repo
# DDL (repo tables are supersets; missing spec columns are conformance
# findings per the extraction's own verifiability note).
SPEC_COLUMNS = {
    "blo_orders": [
        "commitment_hash", "entity_id", "intent_hash", "asset_in", "asset_out",
        "magnitude", "filled_amount", "expiry_block", "status", "created_at",
        "akashic_depth", "behavioral_proof_root",
    ],
    "btcp_intent_registry": [
        "intent_hash", "entity_id", "action", "asset_in", "asset_out",
        "magnitude", "deadline", "max_gas_usd", "privacy_mode", "btcp_version",
        "created_at", "route_selected", "status",
    ],
    "btcp_routes": [
        "route_id", "intent_hash", "anchor_bh", "execution_bh", "anchor_chain",
        "execution_chain", "entity_id", "gas_saved_vs_bridge",
        "beo_continuity_score", "cc_coherence", "route_type", "status",
        "created_at", "finalized_at",
    ],
    "btcp_escrow_states": [
        "escrow_id", "route_id", "entity_id", "amount", "lock_block",
        "timeout_blocks", "state", "created_at", "resolved_at",
    ],
    "bitp_clipboard": [
        "commitment_hash", "entity_id", "asset_x", "asset_y", "chain_a",
        "chain_b", "magnitude", "behavioral_proof_root", "status",
        "created_at", "matched_at", "counterparty_hash",
    ],
}

# intent-hash deadline conformance: the spec's single `deadline` constraint
# is carried by the repo as the deadline_block/deadline_ts pair (§4.1
# Intent Object allows block number OR timestamp).
SPEC_COLUMN_ALIASES = {"deadline": ("deadline_block", "deadline_ts")}

_TABLE_BLOCK_RE = re.compile(
    r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\);", re.S)


def _load_schema() -> str:
    with open(SCHEMA_SQL, encoding="utf-8") as fh:
        return fh.read()


def _tables(source: str) -> dict:
    """schema.sql → {table_name: set(column names)}."""
    out = {}
    for m in _TABLE_BLOCK_RE.finditer(source):
        name, body = m.group(1), m.group(2)
        cols = set()
        for line in body.splitlines():
            tok = line.strip().split()
            if not tok:
                continue
            first = tok[0]
            if first.upper() in ("PRIMARY", "UNIQUE", "CHECK", "CONSTRAINT",
                                 "FOREIGN", "REFERENCES", "EXCLUDE"):
                continue
            cols.add(first)
        out[name] = cols
    return out


@pytest.fixture(scope="module")
def schema():
    return _load_schema()


@pytest.fixture(scope="module")
def tables(schema):
    return _tables(schema)


class TestSpecTablePresence:

    def test_every_spec_named_table_exists(self, tables):
        missing = [t for t in SPEC_TABLES if t not in tables]
        assert not missing, f"spec tables missing from schema.sql: {missing}"

    @pytest.mark.parametrize("table,spec_cols", sorted(SPEC_COLUMNS.items()))
    def test_d3_127_columns_covered(self, tables, table, spec_cols):
        """D3-127 column-level conformance — repo is a superset per column."""
        repo_cols = tables[table]
        for col in spec_cols:
            if col in SPEC_COLUMN_ALIASES:
                assert any(a in repo_cols for a in SPEC_COLUMN_ALIASES[col]), \
                    (table, col)
            else:
                assert col in repo_cols, (table, col)

    def test_btcp_routes_links_intent_registry(self, schema):
        """The BTCP_ROUTE linkage the spec's §2 audit flagged (D3-077):
        btcp_routes.intent_hash must reference btcp_intent_registry."""
        m = re.search(r"CREATE TABLE IF NOT EXISTS btcp_routes \(.*?\);", schema, re.S)
        assert m and "REFERENCES btcp_intent_registry(intent_hash)" in m.group(0)

    def test_escrow_state_enum_is_the_spec_state_machine(self, schema):
        """D3-238: IDLE | HOLDING | RELEASED | REVERTED."""
        m = re.search(r"CREATE TYPE btcp_escrow_state AS ENUM \((.*?)\)", schema, re.S)
        assert m
        states = re.findall(r"'(\w+)'", m.group(1))
        assert states == ["IDLE", "HOLDING", "RELEASED", "REVERTED"]


class TestCanonicalEventEnum:

    def test_behavioral_event_type_is_the_canonical_20(self, schema):
        """schema.sql's enum must carry exactly the authoritative 20 names
        in id order (whitepaper L0.1 §2 / core.primitives.behavioral_hash)."""
        m = re.search(r"CREATE TYPE behavioral_event_type AS ENUM \((.*?)\)", schema, re.S)
        assert m, "behavioral_event_type enum missing"
        enum_names = re.findall(r"'(\w+)'", m.group(1))
        canonical = [e.name for e in EventType]
        assert enum_names == canonical, (
            "schema.sql event enum drifted from the canonical L0.1 map",
            enum_names, canonical)


class TestTimescaleConventions:

    def test_akashic_bh_is_a_compressed_hypertable(self, schema):
        """The file's flagship convention: 1-day chunks + 7-day compression."""
        assert "create_hypertable('akashic_bh', 'time'" in schema
        assert "chunk_time_interval => INTERVAL '1 day'" in schema
        assert "add_compression_policy('akashic_bh', INTERVAL '7 days')" in schema

    def test_append_only_trigger_on_akashic_bh(self, schema):
        """L0.4 thermodynamic conservation — enforced by trigger."""
        assert "CREATE TRIGGER enforce_append_only" in schema
