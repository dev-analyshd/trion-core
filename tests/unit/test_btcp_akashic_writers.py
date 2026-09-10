"""
BTCP gap #7 — Akashic writers for the schema.sql btcp_* tables
==============================================================

schema.sql used to declare six btcp_* tables (intent registry, routes,
escrow states, version registry, cross-chain messages, route rewards) with
ZERO INSERT writers: the operative store was the generic SQLite row table
in core/btcp/state_store.py. These tests pin the closed gap — the six
tables now exist in the SQLite state store as mirrors of the schema.sql
DDL and are populated by the orchestrator's step-6 execution/recording
phase, by route-status updates (validator pool rewards on completion), and
by the escrow_monitor write-through projection.

No running services are required: every test builds an isolated
BtcpStateStore on a tmp_path database (the same TRION_STATE_DB /
state_db=... pattern as tests/btcp/test_btcp_api_surface.py).

Run: pytest tests/unit/test_btcp_akashic_writers.py -q
"""

import pytest

from core.btcp.state_store import (
    BtcpStateStore, BTCP_PROJECTION_TABLES, BTCP_ADAPTER_VERSION,
)
from core.btcp.orchestrator import (
    BTCPOrchestrator, RouteStatus, PrivacyLevel,
)
from core.btcp.escrow_monitor import EscrowMonitor


SRC = "0x" + "11" * 20
DST = "0x" + "22" * 20
SOL_DEST = "Vote111111111111111111111111111111111111111"


def _orchestrator(tmp_path, **kwargs):
    return BTCPOrchestrator(state_db=str(tmp_path / "btcp_state.db"), **kwargs)


def _create_route(orch, dest_chain=137, amount=1_000_000, privacy=PrivacyLevel.BASIC):
    return orch.create_route(
        source_chain=1,
        dest_chain=dest_chain,
        source_address=SRC,
        dest_address=DST if dest_chain != 900 else SOL_DEST,
        amount=amount,
        asset="0x" + "aa" * 20,
        intent_type="TRANSFER",
        privacy_level=privacy,
    )


# ── Store-level: the six tables exist and mirror schema.sql columns ─────────


def test_six_btcp_projection_tables_exist(tmp_path):
    store = BtcpStateStore(state_db=str(tmp_path / "s.db"))
    names = {
        r[0] for r in store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    for table in BTCP_PROJECTION_TABLES:
        assert table in names


@pytest.mark.parametrize("table,columns", [
    ("btcp_intent_registry", [
        "intent_hash", "entity_id", "action", "asset_in", "asset_out",
        "magnitude", "source_chain_id", "deadline_block", "deadline_ts",
        "max_gas_usd", "min_finality", "min_nl_score", "chain_pref",
        "privacy_mode", "btcp_version", "nonce", "route_selected", "status",
        "btcp_score", "created_at", "routed_at", "completed_at",
    ]),
    ("btcp_routes", [
        "route_id", "intent_hash", "route_type", "anchor_bh", "execution_bh",
        "anchor_chain", "execution_chain", "entity_id",
        "counterparty_entity_id", "btcp_score", "nl_score",
        "gas_saved_vs_bridge", "gas_saved_vs_single", "gas_total_usd",
        "beo_continuity_score", "cc_coherence", "mf_score", "consensus_hhi",
        "coherence_at_emission", "travel_rule_proof", "btcp_version",
        "status", "failure_cause", "created_at", "finalized_at",
    ]),
    ("btcp_escrow_states", [
        "escrow_id", "route_id", "entity_id", "chain_id", "contract_address",
        "amount", "token_address", "lock_block", "timeout_blocks", "state",
        "destination", "tx_hash_lock", "tx_hash_release", "created_at",
        "resolved_at",
    ]),
    ("btcp_version_registry", [
        "chain_id", "adapter_version", "min_verifier_version",
        "feature_flags", "registered_at", "last_seen_at", "is_deprecated",
    ]),
    ("btcp_cross_chain_messages", [
        "message_id", "msg_type", "sender_entity_id", "sender_chain",
        "target_chain", "nonce", "expiry_block", "expiry_ts", "payload_hash",
        "btcp_version", "status", "reject_reason", "created_at",
    ]),
    ("btcp_route_rewards", [
        "id", "epoch", "validator_address", "route_id", "base_reward",
        "coverage_bonus_factor", "emergency_multiplier", "final_reward",
        "diversity_weight", "coverage_rate", "uptime_7d", "rewarded_at",
    ]),
])
def test_sqlite_columns_mirror_schema_sql(tmp_path, table, columns):
    """Column names are mirrored 1:1 from schema.sql (gap #7 contract)."""
    store = BtcpStateStore(state_db=str(tmp_path / "s.db"))
    actual = {r[1] for r in store._conn.execute(f"PRAGMA table_info({table})")}
    assert actual == set(columns)


def test_existing_store_gains_projection_tables_in_place(tmp_path):
    """A pre-gap-#7 database is migrated idempotently on next open."""
    db = str(tmp_path / "old.db")
    store = BtcpStateStore(state_db=db)
    # Simulate the pre-gap store: drop the projection tables, keep btcp_state.
    with store._conn:
        for table in BTCP_PROJECTION_TABLES:
            store._conn.execute(f"DROP TABLE IF EXISTS {table}")
    store.save_route("route_old", {"route_id": "route_old"}, "btcp_route_v1")
    store.close()

    reopened = BtcpStateStore(state_db=db)   # _init_schema re-creates them
    names = {
        r[0] for r in reopened._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert set(BTCP_PROJECTION_TABLES) <= names
    assert reopened.get_routes()["route_old"][1]["route_id"] == "route_old"
    reopened.close()


# ── Orchestrator step-6 execution records ───────────────────────────────────


def test_create_route_writes_all_step6_records(tmp_path):
    orch = _orchestrator(tmp_path)
    result = _create_route(orch)
    assert result.success
    store = orch._store

    intents = store.read_btcp_table("btcp_intent_registry")
    assert len(intents) == 1
    row = intents[0]
    assert row["intent_hash"].startswith("btcp_")
    assert row["entity_id"] == SRC
    assert row["action"] == "TRANSFER"
    assert row["asset_in"] == "0x" + "aa" * 20
    assert row["magnitude"] == 1_000_000
    assert row["source_chain_id"] == 1
    assert row["nonce"] == result.route.intent.nonce
    assert row["deadline_ts"] == result.route.intent.deadline
    assert row["privacy_mode"] == "ZK_CREDENTIAL"  # BASIC → zk-credential tier
    assert row["btcp_version"] == "1.0.0"
    assert row["route_selected"] == "SINGLE_CHAIN"
    assert row["status"] == "ROUTING"
    assert row["created_at"] == pytest.approx(result.route.created_at)
    assert row["routed_at"] is not None

    routes = store.read_btcp_table("btcp_routes")
    assert len(routes) == 1
    rrow = routes[0]
    assert rrow["route_id"] == result.route.route_id
    assert rrow["intent_hash"] == result.route.intent.intent_id
    assert rrow["route_type"] == "SINGLE_CHAIN"
    assert rrow["anchor_chain"] == 1
    assert rrow["execution_chain"] == 137
    assert rrow["entity_id"] == SRC
    assert rrow["anchor_bh"]                     # intent commitment or sha3 fallback
    assert len(rrow["anchor_bh"]) >= 16
    assert rrow["gas_total_usd"] == pytest.approx(result.route.total_fee)
    assert rrow["status"] == result.route.status.name
    assert rrow["created_at"] == pytest.approx(result.route.created_at)

    messages = store.read_btcp_table("btcp_cross_chain_messages")
    assert len(messages) == 1
    mrow = messages[0]
    assert mrow["msg_type"] == "IntentBroadcast"
    assert mrow["sender_entity_id"] == SRC
    assert mrow["sender_chain"] == 1
    assert mrow["target_chain"] == 137
    assert mrow["nonce"] == result.route.intent.nonce
    assert mrow["expiry_ts"] == result.route.intent.deadline
    assert mrow["payload_hash"]
    assert mrow["status"] == "ACCEPTED"

    versions = store.read_btcp_table("btcp_version_registry")
    assert {v["chain_id"] for v in versions} == {1, 137}
    assert all(v["adapter_version"] == BTCP_ADAPTER_VERSION for v in versions)
    assert all(v["last_seen_at"] >= v["registered_at"] for v in versions)


def test_public_privacy_level_maps_to_public_mode(tmp_path):
    orch = _orchestrator(tmp_path)
    _create_route(orch, privacy=PrivacyLevel.PUBLIC)
    row = orch._store.read_btcp_table("btcp_intent_registry")[0]
    assert row["privacy_mode"] == "PUBLIC"


def test_full_privacy_level_maps_to_invisible_mode(tmp_path):
    orch = _orchestrator(tmp_path)
    _create_route(orch, privacy=PrivacyLevel.FULL)
    row = orch._store.read_btcp_table("btcp_intent_registry")[0]
    assert row["privacy_mode"] == "INVISIBLE"


def test_travel_rule_proof_recorded_only_when_real(tmp_path):
    """COMPLIANT routes carry a real travel-rule commitment; BASIC ones NULL."""
    orch = _orchestrator(tmp_path)
    basic = _create_route(orch, privacy=PrivacyLevel.BASIC)
    compliant = _create_route(orch, privacy=PrivacyLevel.COMPLIANT)

    rows = {r["route_id"]: r for r in orch._store.read_btcp_table("btcp_routes")}
    assert rows[basic.route.route_id]["travel_rule_proof"] is None
    assert rows[compliant.route.route_id]["travel_rule_proof"]


# ── Route-status updates: terminal statuses + validator pool rewards ───────


def test_completed_route_pays_validator_pools_60_40(tmp_path):
    orch = _orchestrator(tmp_path)
    result = _create_route(orch, amount=1_000_000)
    orch.update_route_status(result.route.route_id, RouteStatus.COMPLETED)
    store = orch._store

    rewards = store.read_btcp_table("btcp_route_rewards")
    assert len(rewards) == 2
    by_pool = {r["validator_address"]: r for r in rewards}
    total = 1_000_000 * 0.001
    assert by_pool["anchor_pool:1"]["final_reward"] == pytest.approx(total * 0.60)
    assert by_pool["execution_pool:137"]["final_reward"] == pytest.approx(total * 0.40)
    for r in rewards:
        assert r["route_id"] == result.route.route_id
        assert r["epoch"] == int(r["rewarded_at"] // 86400)

    # the intent + route rows finalized
    irow = store.read_btcp_table("btcp_intent_registry")[0]
    assert irow["status"] == "COMPLETED"
    assert irow["completed_at"] is not None
    rrow = store.read_btcp_table("btcp_routes")[0]
    assert rrow["status"] == "COMPLETED"
    assert rrow["finalized_at"] is not None


def test_failed_route_finalizes_without_paying_pools(tmp_path):
    orch = _orchestrator(tmp_path)
    result = _create_route(orch)
    orch.update_route_status(result.route.route_id, RouteStatus.FAILED)
    store = orch._store
    assert store.read_btcp_table("btcp_route_rewards") == []
    irow = store.read_btcp_table("btcp_intent_registry")[0]
    assert irow["status"] == "FAILED"
    rrow = store.read_btcp_table("btcp_routes")[0]
    assert rrow["status"] == "FAILED"
    assert rrow["finalized_at"] is not None


def test_timeout_maps_to_expired_intent_status(tmp_path):
    orch = _orchestrator(tmp_path)
    result = _create_route(orch)
    orch.update_route_status(result.route.route_id, RouteStatus.TIMEOUT)
    irow = orch._store.read_btcp_table("btcp_intent_registry")[0]
    assert irow["status"] == "EXPIRED"


# ── Idempotency: replays never duplicate rows nor crash ─────────────────────


def test_replayed_completion_event_pays_pools_once(tmp_path):
    orch = _orchestrator(tmp_path)
    result = _create_route(orch)
    orch.update_route_status(result.route.route_id, RouteStatus.COMPLETED)
    orch.update_route_status(result.route.route_id, RouteStatus.COMPLETED)
    orch.update_route_status(result.route.route_id, RouteStatus.COMPLETED)
    rewards = orch._store.read_btcp_table("btcp_route_rewards")
    assert len(rewards) == 2  # one anchor leg + one execution leg, no more


def test_records_survive_restart_and_are_not_duplicated(tmp_path):
    """A second orchestrator on the same DB re-records nothing on reload."""
    db = str(tmp_path / "btcp_state.db")
    orch = BTCPOrchestrator(state_db=db)
    result = _create_route(orch)
    orch.update_route_status(result.route.route_id, RouteStatus.COMPLETED)

    orch2 = BTCPOrchestrator(state_db=db)  # fresh instance, same store
    assert orch2.get_route(result.route.route_id) is not None

    store2 = orch2._store
    assert len(store2.read_btcp_table("btcp_intent_registry")) == 1
    assert len(store2.read_btcp_table("btcp_routes")) == 1
    assert len(store2.read_btcp_table("btcp_cross_chain_messages")) == 1
    assert len(store2.read_btcp_table("btcp_route_rewards")) == 2
    assert len(store2.read_btcp_table("btcp_version_registry")) == 2


def test_version_registry_refreshes_last_seen_not_rows(tmp_path):
    orch = _orchestrator(tmp_path)
    _create_route(orch)
    first = orch._store.read_btcp_table("btcp_version_registry")
    _create_route(orch)  # another route on the same chains
    second = orch._store.read_btcp_table("btcp_version_registry")
    assert len(first) == len(second) == 2
    by_chain = {v["chain_id"]: v for v in second}
    assert by_chain[1]["last_seen_at"] >= by_chain[1]["registered_at"]


# ── Escrow write-through projection (escrow_monitor → btcp_escrow_states) ──


def test_escrow_monitor_write_through_lands_in_btcp_escrow_states(tmp_path):
    db = str(tmp_path / "btcp_state.db")
    mon = EscrowMonitor(state_db=db)
    esc = mon.lock_escrow(
        "esc_ak_1", "route_ak_1", b"\x07" * 32, 1234.5, 300, block_number=100,
    )
    rows = mon._store.read_btcp_table("btcp_escrow_states")
    assert len(rows) == 1
    row = rows[0]
    assert row["escrow_id"] == "esc_ak_1"
    assert row["route_id"] == "route_ak_1"
    assert row["entity_id"] == esc.entity_id.hex()
    assert row["amount"] == 1234.5
    assert row["lock_block"] == 100
    assert row["timeout_blocks"] == 300
    assert row["state"] == "HOLDING"
    assert row["created_at"] == pytest.approx(esc.lock_timestamp)
    assert row["resolved_at"] is None

    # state transitions upsert the same row (no duplicates)
    mon.verify_settlement("esc_ak_1")
    mon.release_escrow("esc_ak_1", coherence=0.9, block_number=150)
    rows = mon._store.read_btcp_table("btcp_escrow_states")
    assert len(rows) == 1
    assert rows[0]["state"] == "RELEASED"
    assert rows[0]["resolved_at"] is not None

    # the generic escrow_v1 path (what /api/v1/btcp/escrow/<id> reads)
    # is untouched by the projection.
    persisted = mon._store.get_escrows()
    assert persisted["esc_ak_1"][0] == "escrow_v1"
    assert persisted["esc_ak_1"][1]["amount"] == 1234.5


def test_escrow_projection_skips_partial_rows(tmp_path):
    """Partial/non-escrow payloads never crash the generic write path."""
    store = BtcpStateStore(state_db=str(tmp_path / "s.db"))
    store.save_escrow("partial", {"x": 1}, "escrow_v1")          # no required keys
    store.save_escrow("other", {"escrow_id": "other"}, "escrow_v999")  # wrong tag
    assert store.get_escrows()["partial"][1] == {"x": 1}
    assert store.read_btcp_table("btcp_escrow_states") == []


def test_cross_chain_message_replay_is_ignored(tmp_path):
    """Re-broadcasting the same (intent, nonce) message is a no-op."""
    store = BtcpStateStore(state_db=str(tmp_path / "s.db"))
    payload = dict(
        msg_type="IntentBroadcast", sender_entity_id=SRC, sender_chain=1,
        target_chain=137, nonce=99, expiry_ts=1.0, payload_hash="0x" + "00" * 32,
    )
    store.record_cross_chain_message("m" * 64, **payload)
    store.record_cross_chain_message("m" * 64, **payload)  # same id
    assert len(store.read_btcp_table("btcp_cross_chain_messages")) == 1
    payload["nonce"] = 100
    store.record_cross_chain_message("z" * 64, **payload)   # different nonce
    assert len(store.read_btcp_table("btcp_cross_chain_messages")) == 2
    # same (sender, chains, nonce) under a different id → blocked by the
    # unique nonce index (replay prevention), INSERT OR IGNORE swallows it
    payload["nonce"] = 100
    store.record_cross_chain_message("y" * 64, **payload)
    assert len(store.read_btcp_table("btcp_cross_chain_messages")) == 2


def test_read_btcp_table_is_whitelisted(tmp_path):
    store = BtcpStateStore(state_db=str(tmp_path / "s.db"))
    with pytest.raises(ValueError):
        store.read_btcp_table("btcp_state")
    with pytest.raises(ValueError):
        store._btcp_upsert("btcp_state", {"kind": "x"})  # not a projection table
