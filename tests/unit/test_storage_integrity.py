"""
W3-N — Storage / data-integrity battery
========================================

Covers the four W3-N mission areas against the operative SQLite BTCP store
(core/btcp/state_store.py) and its schema.sql contract:

1. Reader/writer compatibility — round-trips for every projection table,
   including the escrow_v1 shape the API route
   (api/btcp_continuum_routes.py:btcp_escrow_state) reads.
2. Replay + atomicity — certificate-consumption replay guard
   (CONSUMED / REPLAY / EQUIVOCATION, on-chain consumed-nonce parity) and
   crash-mid-write atomicity via injected failures (record_execution,
   save_escrow, nested transactions).
3. ID namespaces — no two chains/entities produce ambiguous store keys
   (message ids, reward pools, consumed certificates; escrow-id hazard
   documented).
4. Backfill/migration idempotency — the schema v1→v2 store migration and
   the c93d237/e0bea25 streamer migration pattern re-run safely.

Run: pytest tests/unit/test_storage_integrity.py -q
"""

import hashlib
import os
import sqlite3
import time

import pytest

from core.btcp.state_store import (
    BtcpStateStore, BTCP_PROJECTION_TABLES, PHASE0_PROJECTION_TABLES,
    SCHEMA_VERSION, CertificateConsumption, certificate_consumption_key,
)
from core.consensus.certificate import CanonicalCertificate


def _store(tmp_path, name="s.db"):
    return BtcpStateStore(state_db=str(tmp_path / name))


# ═══ 1. Reader/writer compatibility — round-trips ═════════════════════════════


@pytest.mark.parametrize("table", BTCP_PROJECTION_TABLES)
def test_every_projection_table_round_trips(tmp_path, table):
    """Writer → table → reader round-trip for each mirrored table."""
    db = str(tmp_path / "s.db")
    store = BtcpStateStore(state_db=db)
    try:
        pk = {
            "btcp_intent_registry": "intent_hash",
            "btcp_routes": "route_id",
            "btcp_escrow_states": "escrow_id",
            "btcp_version_registry": None,   # composite PK
            "btcp_cross_chain_messages": "message_id",
            "btcp_route_rewards": None,      # autoincrement
            "blo_orders": "commitment_hash",
            "bitp_clipboard": "commitment_hash",
            "shadow_observations": None,     # autoincrement
            "genesis_commitments": "commitment_id",
            "btcp_consumed_certificates": "consumption_key",
            "btcp_certificate_conflicts": None,  # autoincrement
        }[table]
        if table == "btcp_intent_registry":
            store.record_intent("ih", entity_id="e", action="SWAP",
                                magnitude=1.0, source_chain_id=1, nonce=1)
        elif table == "btcp_routes":
            store.record_route("r", intent_hash="ih", route_type="NETTING",
                               anchor_bh="ab", anchor_chain=1,
                               execution_chain=137, entity_id="e",
                               btcp_score=0.9)
        elif table == "btcp_escrow_states":
            store.record_escrow("es", route_id="r", entity_id="e", amount=1.0,
                                lock_block=1)
        elif table == "btcp_version_registry":
            store.record_version(1)
        elif table == "btcp_cross_chain_messages":
            store.record_cross_chain_message(
                "m", msg_type="IntentBroadcast", sender_entity_id="e",
                sender_chain=1, target_chain=137, nonce=1, expiry_ts=9.0,
                payload_hash="p")
        elif table == "btcp_route_rewards":
            store.record_route_reward(0, "anchor_pool:1", "r", 1.0)
        elif table == "blo_orders":
            store.record_blo_order("ch", entity_id="e", intent_hash="ih",
                                   asset_in="a", asset_out="b",
                                   source_chain_id=1, magnitude=1.0,
                                   expiry_block=10)
        elif table == "bitp_clipboard":
            store.record_bitp_clipboard("ch", entity_id="e", asset_x="a",
                                        asset_y="b", chain_a=1, chain_b=137,
                                        magnitude=1.0, intent_hash="ih")
        elif table == "shadow_observations":
            store.record_shadow_observation(900, 1, "TRANSFER", "ev")
        elif table == "genesis_commitments":
            store.record_genesis_commitment(
                "gc", genesis_type="IDENTITY_GENESIS", entity_id="e")
        elif table == "btcp_consumed_certificates":
            store.consume_certificate(b"\x01" * 32, "ESCROW_RELEASE", 1,
                                      escrow_id="es")
        else:  # btcp_certificate_conflicts
            store.consume_certificate(b"\x01" * 32, "ESCROW_RELEASE", 1,
                                      escrow_id="es")
            store.consume_certificate(b"\x02" * 32, "ESCROW_RELEASE", 1,
                                      escrow_id="es")  # equivocation evidence
        rows = store.read_btcp_table(table)
        assert rows, f"{table}: writer wrote nothing"
        if pk:
            assert rows[0][pk]
    finally:
        store.close()

    # restart survival: a second store on the same file reads the same rows
    reopened = BtcpStateStore(state_db=db)
    try:
        assert len(reopened.read_btcp_table(table)) == len(rows)
    finally:
        reopened.close()


def test_escrow_v1_writer_matches_api_reader_shape(tmp_path):
    """The escrow_v1 row the escrow_monitor writes is exactly the shape the
    /api/v1/btcp/escrow/<id> route (21-a) reads: get_escrows() payload with
    a string ``state`` key, plus the btcp_escrow_states projection carrying
    the schema.sql column set."""
    from core.btcp.escrow_monitor import (
        Escrow, EscrowState, RevertReason, _escrow_to_row,
    )
    db = str(tmp_path / "s.db")
    store = BtcpStateStore(state_db=db)
    try:
        esc = Escrow(escrow_id="e1", route_id="r1", entity_id=b"\x01" * 32,
                     amount=1234.5, lock_block=100, lock_timestamp=1000.0,
                     timeout_blocks=300)
        row = _escrow_to_row(esc)
        store.save_escrow("e1", row, "escrow_v1")

        # what the API route reads (type_tag, row) via store.get_escrows()
        type_tag, api_row = store.get_escrows()["e1"]
        assert type_tag == "escrow_v1"
        assert api_row["state"] == EscrowState.HOLDING.name  # string, not int
        assert api_row["amount"] == 1234.5
        assert set(api_row) == {
            "escrow_id", "route_id", "entity_id", "amount", "lock_block",
            "lock_timestamp", "timeout_blocks", "state", "revert_reason",
            "settled_at", "reverted_at", "parent_escrow_id",
            "settlement_verified",
        }
        # the projection carries the schema.sql escrow column set
        prow = store.read_btcp_table("btcp_escrow_states")[0]
        assert prow["escrow_id"] == "e1"
        assert prow["route_id"] == "r1"
        assert prow["entity_id"] == (b"\x01" * 32).hex()
        assert prow["state"] == "HOLDING"
        assert prow["amount"] == 1234.5
        assert prow["resolved_at"] is None
    finally:
        store.close()


def test_phase0_writers_round_trip_real_module_outputs(tmp_path):
    """The Phase-0 store writers accept the real outputs of the modules.py
    classes that produce the data (BITPMatcher, BLOScheduler,
    ShadowObserver, GenesisCommitmentProcessor)."""
    from core.btcp.modules import (
        BITPIntent, BITPMatcher, BLOScheduler, GenesisCommitmentProcessor,
        ShadowObserver,
    )
    store = _store(tmp_path)
    try:
        # BITP CUT/MATCH — commitment keyed on the intent hash (§4.1)
        intent_a = BITPIntent(entity_id=b"\x01" * 32, asset_in=b"\x0a" * 20,
                              asset_out=b"\x0b" * 20, magnitude=50.0,
                              chain_id=1, deadline=99999, nonce=5)
        intent_b = BITPIntent(entity_id=b"\x02" * 32, asset_in=b"\x0b" * 20,
                              asset_out=b"\x0a" * 20, magnitude=50.5,
                              chain_id=137, deadline=99999, nonce=9)
        matcher = BITPMatcher()
        match = matcher.find_complement(intent_a, [intent_b])
        assert match is intent_b
        paste = matcher.execute_paste(intent_a, match)
        store.record_bitp_clipboard(
            intent_a.hash().hex(), entity_id=intent_a.entity_id.hex(),
            asset_x=intent_a.asset_in.hex(), asset_y=intent_a.asset_out.hex(),
            chain_a=paste["chain_a"], chain_b=paste["chain_b"],
            magnitude=intent_a.magnitude,
            intent_hash=intent_a.hash().hex(), status="MATCHED",
            matched_at=time.time(),
            counterparty_hash=match.hash().hex())
        row = store.read_btcp_table("bitp_clipboard")[0]
        assert row["status"] == "MATCHED"
        assert row["chain_a"] == 1 and row["chain_b"] == 137
        assert row["counterparty_hash"] == match.hash().hex()

        # BLO — deferred intent with a BRT-scheduled activation window
        window = BLOScheduler().find_optimal_window([2, 3, 4], [3, 4], [2, 4])
        store.record_blo_order(
            hashlib.sha3_256(b"blo").hexdigest(),
            entity_id=intent_a.entity_id.hex(),
            intent_hash=intent_a.hash().hex(),
            asset_in=intent_a.asset_in.hex(),
            asset_out=intent_a.asset_out.hex(),
            source_chain_id=1, target_chain_id=137,
            magnitude=intent_a.magnitude, expiry_block=1_000_000,
            status="OPEN", scheduled_activation=window[0] if window else None,
            brt_confidence=0.78)
        blo = store.read_btcp_table("blo_orders")[0]
        assert blo["status"] == "OPEN"
        assert blo["brt_confidence"] == 0.78

        # Shadow observation — reconstructed shadow BH lands in the row
        observer = ShadowObserver()
        shadow_sources = [
            {"data": "tx:0xabc", "weight": 0.8, "type": "TRANSFER",
             "source_chain": 1, "observed_chain": 900},
            {"data": "bridge:0xdef", "weight": 0.6, "type": "BRIDGE_EVENT",
             "source_chain": 137, "observed_chain": 900},
        ]
        shadow_bh, confidence = observer.reconstruct_shadow_bh(shadow_sources)
        for src in shadow_sources:
            store.record_shadow_observation(
                src["observed_chain"], src["source_chain"], src["type"],
                hashlib.sha3_256(src["data"].encode()).hexdigest(),
                confidence_weight=src["weight"],
                shadow_bh=shadow_bh.hex(), block_num=42)
        observations = store.read_btcp_table("shadow_observations")
        assert len(observations) == 2
        assert all(o["shadow_bh"] == shadow_bh.hex() for o in observations)
        assert max(o["confidence_weight"] for o in observations) == 0.8

        # Genesis commitment — the processor output dict maps 1:1
        genesis = GenesisCommitmentProcessor().initiate_genesis(
            b"\x03" * 32, "stake", stake_amount=100.0)
        store.record_genesis_commitment(
            hashlib.sha3_256(b"genesis").hexdigest(),
            genesis_type="IDENTITY_GENESIS",
            entity_id=genesis["entity_id"],
            stake_bond=genesis["stake_amount"],
            conf_genesis=genesis["conf_genesis"])
        gc = store.read_btcp_table("genesis_commitments")[0]
        assert gc["conf_genesis"] == 0.01
        assert gc["stake_bond"] == 100.0
        assert gc["status"] == "ACTIVE"
    finally:
        store.close()


# ═══ 2a. Replay guard — certificate consumption ═══════════════════════════════


def test_consume_certificate_first_use_is_consumed(tmp_path):
    store = _store(tmp_path)
    try:
        cert = CanonicalCertificate(
            certificate_nonce=7, escrow_id=b"\x11" * 32,
            source_chain=1, dest_chain=137,
            issued_at=int(time.time()), ttl=60)
        verdict = store.consume_certificate(
            cert.certificate_hash(), "ESCROW_RELEASE", 7,
            chain_id=1, escrow_id="esc_9", epoch=0,
            certificate_kind="ESCROW_RELEASE")
        assert verdict is CertificateConsumption.CONSUMED
        assert store.certificate_is_consumed(
            "ESCROW_RELEASE", 7, chain_id=1, escrow_id="esc_9")
        rows = store.read_consumed_certificates()
        assert rows[0]["certificate_hash"] == cert.certificate_hash().hex()
        assert rows[0]["replay_count"] == 0
    finally:
        store.close()


def test_consume_certificate_replay_is_idempotent_noop(tmp_path):
    """Same certificate, same key → REPLAY; consumed_at NOT refreshed
    (TON §8.2 parity), replay_count audits the attempt."""
    store = _store(tmp_path)
    try:
        cert = b"\x0a" * 32
        store.consume_certificate(cert, "ESCROW_RELEASE", 1, escrow_id="e1")
        first = [r for r in store.read_consumed_certificates()
                 if r["escrow_id"] == "e1"][0]
        time.sleep(0.01)
        verdict = store.consume_certificate(
            cert, "ESCROW_RELEASE", 1, escrow_id="e1")
        assert verdict is CertificateConsumption.REPLAY
        rows = store.read_consumed_certificates()
        assert len(rows) == 1
        assert rows[0]["replay_count"] == 1
        assert rows[0]["consumed_at"] == first["consumed_at"]
    finally:
        store.close()


def test_consume_certificate_equivocation_is_rejected_with_evidence(tmp_path):
    """A different certificate claiming a consumed key is refused and the
    attempt is logged as evidence (NEAR CertificateEquivocation parity)."""
    store = _store(tmp_path)
    try:
        good = b"\x0a" * 32
        rogue = b"\x0b" * 32
        store.consume_certificate(good, "ESCROW_RELEASE", 1, escrow_id="e1")
        verdict = store.consume_certificate(
            rogue, "ESCROW_RELEASE", 1, escrow_id="e1")
        assert verdict is CertificateConsumption.EQUIVOCATION
        # the winning certificate is unchanged
        rows = store.read_consumed_certificates()
        assert len(rows) == 1
        assert rows[0]["certificate_hash"] == good.hex()
        assert rows[0]["replay_count"] == 0
        # evidence recorded
        conflicts = store.read_certificate_conflicts()
        assert len(conflicts) == 1
        assert conflicts[0]["recorded_hash"] == good.hex()
        assert conflicts[0]["attempted_hash"] == rogue.hex()
    finally:
        store.close()


def test_consume_certificate_bytes_and_hex_normalized(tmp_path):
    store = _store(tmp_path)
    try:
        cert = b"\x0c" * 32
        store.consume_certificate(cert, "SCOPE", 1)
        # the same hash as a hex string is the same certificate
        verdict = store.consume_certificate(cert.hex(), "SCOPE", 1)
        assert verdict is CertificateConsumption.REPLAY
    finally:
        store.close()


def test_consume_certificate_survives_restart(tmp_path):
    db = str(tmp_path / "s.db")
    store = BtcpStateStore(state_db=db)
    try:
        store.consume_certificate(b"\x0d" * 32, "ESCROW_RELEASE", 3,
                                  escrow_id="e3")
    finally:
        store.close()
    reopened = BtcpStateStore(state_db=db)
    try:
        assert reopened.certificate_is_consumed(
            "ESCROW_RELEASE", 3, escrow_id="e3")
        verdict = reopened.consume_certificate(
            b"\x0d" * 32, "ESCROW_RELEASE", 3, escrow_id="e3")
        assert verdict is CertificateConsumption.REPLAY
        verdict = reopened.consume_certificate(
            b"\x0e" * 32, "ESCROW_RELEASE", 3, escrow_id="e3")
        assert verdict is CertificateConsumption.EQUIVOCATION
    finally:
        reopened.close()


def test_consume_certificate_composes_atomically_with_escrow_write(tmp_path):
    """The intended py release path: consume the certificate and write the
    escrow state in ONE transaction — a failure between them rolls back
    both (no consumed certificate without the recorded release, and vice
    versa)."""
    db = str(tmp_path / "s.db")
    store = BtcpStateStore(state_db=db)
    try:
        cert = b"\x0f" * 32
        # happy path: both land
        with store.transaction():
            verdict = store.consume_certificate(
                cert, "ESCROW_RELEASE", 9, escrow_id="e9")
            store.record_escrow("e9", route_id="r9", entity_id="ent",
                                amount=1.0, lock_block=1, state="RELEASED")
        assert verdict is CertificateConsumption.CONSUMED
        assert store.read_btcp_table("btcp_escrow_states")[0]["state"] == "RELEASED"

        # injected failure after consumption: BOTH rolled back
        class Boom(Exception):
            pass
        original = store.record_escrow
        try:
            def _boom(*a, **k):
                raise Boom("crash after consuming the certificate")
            store.record_escrow = _boom
            with pytest.raises(Boom):
                with store.transaction():
                    store.consume_certificate(
                        b"\x10" * 32, "ESCROW_RELEASE", 10, escrow_id="e10")
                    store.record_escrow("e10", route_id="r10", entity_id="ent",
                                        amount=1.0, lock_block=1)
        finally:
            store.record_escrow = original
        assert not store.certificate_is_consumed(
            "ESCROW_RELEASE", 10, escrow_id="e10")
        assert all(r["escrow_id"] != "e10"
                   for r in store.read_btcp_table("btcp_escrow_states"))
    finally:
        store.close()


# ═══ 2b. Atomicity — crash-mid-write leaves consistent state ══════════════════


def _bundle(store, intent_hash="ih", route_id="r", message_id="m", nonce=1):
    return dict(
        intent={"intent_hash": intent_hash, "entity_id": "e",
                "action": "TRANSFER", "magnitude": 1.0,
                "source_chain_id": 1, "nonce": nonce},
        route={"route_id": route_id, "intent_hash": intent_hash,
               "route_type": "SINGLE_CHAIN", "anchor_bh": "ab" * 16,
               "anchor_chain": 1, "execution_chain": 137, "entity_id": "e",
               "btcp_score": 0.9, "status": "ROUTING"},
        message={"message_id": message_id, "msg_type": "IntentBroadcast",
                 "sender_entity_id": "e", "sender_chain": 1,
                 "target_chain": 137, "nonce": nonce, "expiry_ts": 99.0,
                 "payload_hash": "00" * 32},
        version_chain_ids=(1, 137),
    )


@pytest.mark.parametrize("fail_at", [
    "record_route", "record_cross_chain_message", "record_version",
])
def test_step6_bundle_atomic_under_injected_failure(tmp_path, fail_at):
    """A crash between any two step-6 writes rolls back the whole bundle —
    no half-recorded execution (intent row without route row, etc.)."""
    store = _store(tmp_path)
    try:
        class Boom(Exception):
            pass
        original = getattr(store, fail_at)

        def _boom(*a, **k):
            raise Boom(f"simulated crash at {fail_at}")
        setattr(store, fail_at, _boom)
        try:
            with pytest.raises(Boom):
                store.record_execution(**_bundle(store))
        finally:
            setattr(store, fail_at, original)

        # nothing from the failed bundle survived
        assert store.read_btcp_table("btcp_intent_registry") == []
        assert store.read_btcp_table("btcp_routes") == []
        assert store.read_btcp_table("btcp_cross_chain_messages") == []
        assert store.read_btcp_table("btcp_version_registry") == []

        # and the store still works afterwards (transaction closed cleanly)
        store.record_execution(**_bundle(store))
        assert len(store.read_btcp_table("btcp_intent_registry")) == 1
        assert len(store.read_btcp_table("btcp_routes")) == 1
        assert len(store.read_btcp_table("btcp_cross_chain_messages")) == 1
        assert {v["chain_id"]
                for v in store.read_btcp_table("btcp_version_registry")} == {1, 137}
    finally:
        store.close()


def test_step6_bundle_commit_is_visible_to_a_second_store(tmp_path):
    db = str(tmp_path / "s.db")
    store = BtcpStateStore(state_db=db)
    try:
        store.record_execution(**_bundle(store))
    finally:
        store.close()
    reopened = BtcpStateStore(state_db=db)
    try:
        assert len(reopened.read_btcp_table("btcp_intent_registry")) == 1
        assert len(reopened.read_btcp_table("btcp_routes")) == 1
    finally:
        reopened.close()


def test_save_escrow_generic_row_and_projection_are_atomic(tmp_path):
    """save_escrow writes the btcp_state row + the btcp_escrow_states
    projection in one transaction: either both land or neither."""
    db = str(tmp_path / "s.db")
    store = BtcpStateStore(state_db=db)
    payload = {
        "escrow_id": "e1", "route_id": "r1", "entity_id": "01" * 16,
        "amount": 5.0, "lock_block": 10, "lock_timestamp": 1000.0,
        "timeout_blocks": 300, "state": "HOLDING",
    }
    try:
        class Boom(Exception):
            pass
        original = store._project_escrow_row

        def _boom(*a, **k):
            raise Boom("crash between generic row and projection")
        store._project_escrow_row = _boom
        try:
            # projection failure must not break the module's write path
            store.save_escrow("e1", payload, "escrow_v1")
        except Boom:  # pragma: no cover — the failure is swallowed by design
            pytest.fail("projection failure broke the module write path")
        finally:
            store._project_escrow_row = original
        # generic row committed, projection absent (documented design)
        assert store.get_escrows()["e1"][1]["amount"] == 5.0
        assert store.read_btcp_table("btcp_escrow_states") == []

        # happy path: both atomically
        store.save_escrow("e2", {**payload, "escrow_id": "e2"}, "escrow_v1")
        assert store.get_escrows()["e2"][1]["amount"] == 5.0
        assert store.read_btcp_table("btcp_escrow_states")[0]["escrow_id"] == "e2"
    finally:
        store.close()


def test_nested_transactions_join_the_outermost(tmp_path):
    store = _store(tmp_path)
    try:
        with store.transaction():
            store.record_intent("ih", entity_id="e", action="SWAP",
                                magnitude=1.0, source_chain_id=1, nonce=1)
            with store.transaction():  # nested — must NOT commit early
                store.record_route("r", intent_hash="ih",
                                   route_type="NETTING", anchor_bh="ab",
                                   anchor_chain=1, execution_chain=137,
                                   entity_id="e", btcp_score=0.9)
            # still inside the outer transaction: nothing committed yet
            # (a rollback from here discards both writes)
        assert len(store.read_btcp_table("btcp_routes")) == 1

        # and the rollback case
        class Boom(Exception):
            pass
        with pytest.raises(Boom):
            with store.transaction():
                store.record_intent("ih2", entity_id="e", action="SWAP",
                                    magnitude=1.0, source_chain_id=1, nonce=2)
                with store.transaction():
                    store.record_route("r2", intent_hash="ih2",
                                       route_type="NETTING", anchor_bh="ab",
                                       anchor_chain=1, execution_chain=137,
                                       entity_id="e", btcp_score=0.9)
                raise Boom()
        assert all(r["intent_hash"] != "ih2"
                   for r in store.read_btcp_table("btcp_intent_registry"))
        assert all(r["route_id"] != "r2"
                   for r in store.read_btcp_table("btcp_routes"))
    finally:
        store.close()


# ═══ 3. ID namespaces — no ambiguous keys across chains/entities ═════════════


def test_message_ids_are_chain_pair_scoped():
    """Orchestrator message-id construction (sha3 of intent:src:dst:nonce):
    same intent + nonce across different chain pairs → distinct ids, and
    the nonce uniqueness index is scoped per (sender, chain-pair)."""
    def message_id(intent_id, src, dst, nonce):
        return hashlib.sha3_256(
            f"{intent_id}:{src}:{dst}:{nonce}".encode()).hexdigest()

    a = message_id("intent-1", 1, 137, 7)
    b = message_id("intent-1", 1, 900, 7)   # different target chain
    c = message_id("intent-1", 137, 1, 7)   # reversed direction
    assert len({a, b, c}) == 3


def test_message_nonce_guard_is_chain_scoped_not_global(tmp_path):
    """The (sender, sender_chain, target_chain, nonce) unique index must not
    block legitimate messages on OTHER chain pairs with the same nonce."""
    store = _store(tmp_path)
    try:
        base = dict(msg_type="IntentBroadcast", sender_entity_id="e",
                    expiry_ts=9.0, payload_hash="p", status="ACCEPTED")
        store.record_cross_chain_message("m1", sender_chain=1, target_chain=137,
                                         nonce=7, **base)
        # same nonce, different chain pair → allowed (not a replay)
        store.record_cross_chain_message("m2", sender_chain=1, target_chain=900,
                                         nonce=7, **base)
        # same nonce, reversed direction → allowed
        store.record_cross_chain_message("m3", sender_chain=137, target_chain=1,
                                         nonce=7, **base)
        assert len(store.read_btcp_table("btcp_cross_chain_messages")) == 3
        # same chain pair + nonce under a new id → blocked (replay)
        store.record_cross_chain_message("m4", sender_chain=1, target_chain=137,
                                         nonce=7, **base)
        assert len(store.read_btcp_table("btcp_cross_chain_messages")) == 3
    finally:
        store.close()


def test_route_reward_pools_are_chain_scoped(tmp_path):
    """(epoch, "anchor_pool:<chain>", route) — same route completing legs on
    different chains pays distinct pool rows; each replays idempotently."""
    store = _store(tmp_path)
    try:
        for chain in (1, 137, 900):
            store.record_route_reward(0, f"anchor_pool:{chain}", "route_1", 60.0)
        assert len(store.read_btcp_table("btcp_route_rewards")) == 3
        # full replay of the completion event pays nobody twice
        for chain in (1, 137, 900):
            store.record_route_reward(0, f"anchor_pool:{chain}", "route_1", 60.0)
        assert len(store.read_btcp_table("btcp_route_rewards")) == 3
    finally:
        store.close()


def test_consumed_certificate_keys_are_chain_scoped(tmp_path):
    """Same (nonce, escrow) on two chains = two independent consumption keys
    (mirrors the on-chain per-chain registries)."""
    assert (certificate_consumption_key("ESCROW_RELEASE", 7, chain_id=1, escrow_id="e")
            != certificate_consumption_key("ESCROW_RELEASE", 7, chain_id=137, escrow_id="e"))
    assert (certificate_consumption_key("ESCROW_RELEASE", 7, escrow_id="e")
            != certificate_consumption_key("ESCROW_RELEASE", 7, route_id="e"))
    assert (certificate_consumption_key("A", 7, escrow_id="e")
            != certificate_consumption_key("B", 7, escrow_id="e"))

    store = _store(tmp_path)
    try:
        cert = b"\x11" * 32
        for chain in (1, 137):
            verdict = store.consume_certificate(
                cert, "ESCROW_RELEASE", 7, chain_id=chain, escrow_id="e")
            assert verdict is CertificateConsumption.CONSUMED
        assert len(store.read_consumed_certificates()) == 2
    finally:
        store.close()


def test_escrow_id_namespace_hazard_is_documented(tmp_path):
    """DOCUMENTED HAZARD (W3-N audit, state_store.py "ID namespaces"):
    escrow ids are caller-supplied bare strings — two chains reusing the
    same bare id collide in the store. This test pins the current behavior
    so the fix (chain-scoped ids at the escrow_monitor call sites) is a
    visible, deliberate change, not a silent drift. New call sites must use
    chain-scoped ids (f"{chain_id}:{local_id}")."""
    store = _store(tmp_path)
    try:
        payload = {
            "escrow_id": "e1", "route_id": "r1", "entity_id": "01" * 16,
            "amount": 5.0, "lock_block": 10, "lock_timestamp": 1000.0,
            "timeout_blocks": 300, "state": "HOLDING",
        }
        store.save_escrow("e1", payload, "escrow_v1")
        # chain B reuses the bare id "e1" → clobbers chain A's row
        store.save_escrow("e1", {**payload, "amount": 99.0}, "escrow_v1")
        assert len(store.read_btcp_table("btcp_escrow_states")) == 1
        assert store.get_escrows()["e1"][1]["amount"] == 99.0  # the clobber
        # chain-scoped ids do NOT collide
        store.save_escrow("1:e1", {**payload, "escrow_id": "1:e1"}, "escrow_v1")
        store.save_escrow("137:e1", {**payload, "escrow_id": "137:e1"}, "escrow_v1")
        assert len(store.read_btcp_table("btcp_escrow_states")) == 3
    finally:
        store.close()


def test_orchestrator_route_ids_do_not_collide_across_instances(tmp_path):
    """W1-F intent identity: two orchestrator instances (random session tag
    + monotonic sequence) produce distinct route/intent ids — no clobbering
    of the live route by an identical submission."""
    from core.btcp.orchestrator import BTCPOrchestrator, PrivacyLevel
    SRC = "0x" + "11" * 20
    DST = "0x" + "22" * 20
    ids = []
    for i in range(2):
        orch = BTCPOrchestrator(state_db=str(tmp_path / f"o{i}.db"))
        result = orch.create_route(
            source_chain=1, dest_chain=137, source_address=SRC,
            dest_address=DST, amount=1_000_000, asset="0x" + "aa" * 20,
            intent_type="TRANSFER", privacy_level=PrivacyLevel.BASIC)
        assert result.success
        ids.append(result.route.route_id)
    assert ids[0] != ids[1]


# ═══ 4. Migration idempotency ═════════════════════════════════════════════════


def _make_v1_database(db_path):
    """A database as a v1 runtime left it: six btcp_* mirrors, no Phase-0
    tables, schema_version=1, with live data."""
    store = BtcpStateStore(state_db=db_path)
    with store._conn:
        for table in PHASE0_PROJECTION_TABLES + (
                "btcp_consumed_certificates", "btcp_certificate_conflicts"):
            store._conn.execute(f"DROP TABLE IF EXISTS {table}")
        store._conn.execute(
            "INSERT OR REPLACE INTO btcp_meta (key, value) "
            "VALUES ('schema_version', '1')")
    store.record_intent("legacy", entity_id="e", action="SWAP",
                        magnitude=1.0, source_chain_id=1, nonce=1)
    store.save_balance("01", 42.5)
    store.close()
    return db_path


def test_v1_database_upgrades_to_v2_in_place(tmp_path):
    db = _make_v1_database(str(tmp_path / "s.db"))
    store = BtcpStateStore(state_db=db)
    try:
        assert store._conn.execute(
            "SELECT value FROM btcp_meta WHERE key='schema_version'"
        ).fetchone()[0] == str(SCHEMA_VERSION)
        names = {
            r[0] for r in store._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert set(PHASE0_PROJECTION_TABLES) <= names
        assert {"btcp_consumed_certificates",
                "btcp_certificate_conflicts"} <= names
        # pre-existing data survives the migration
        assert store.get_balances() == {"01": 42.5}
        assert store.read_btcp_table("btcp_intent_registry")[0][
            "intent_hash"] == "legacy"
    finally:
        store.close()


def test_migration_re_runs_safely(tmp_path):
    """c93d237/e0bea25 pattern: the migration is idempotent — running it
    twice (double open + explicit re-migrate) changes nothing."""
    db = _make_v1_database(str(tmp_path / "s.db"))
    store = BtcpStateStore(state_db=db)  # first run: v1 → v2
    try:
        # second, explicit run on the now-current schema
        store._migrate(SCHEMA_VERSION)
        store._migrate(SCHEMA_VERSION)
        names = {
            r[0] for r in store._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        # no duplicate tables, data intact
        assert len(names) == len(set(names))
        assert store.get_balances() == {"01": 42.5}
        assert len(store.read_btcp_table("btcp_intent_registry")) == 1
    finally:
        store.close()
    # third run: reopen — a no-op
    reopened = BtcpStateStore(state_db=db)
    try:
        assert reopened.get_balances() == {"01": 42.5}
    finally:
        reopened.close()


def test_newer_schema_version_is_refused(tmp_path):
    db = str(tmp_path / "s.db")
    store = BtcpStateStore(state_db=db)
    with store._conn:
        store._conn.execute(
            "INSERT OR REPLACE INTO btcp_meta (key, value) "
            "VALUES ('schema_version', '99')")
    store.close()
    with pytest.raises(RuntimeError, match="newer"):
        BtcpStateStore(state_db=db)


def test_streamer_migration_pattern_re_runs_safely(tmp_path):
    """The c93d237 BHStreamer migration (ALTER ADD COLUMN + legacy chain-id
    UPDATE re-key) is idempotent: constructing the streamer twice on a
    legacy-shaped ledger preserves the row and does not duplicate or crash.
    (e0bea25 backfill re-keys are covered by
    tests/unit/test_backfill_chain_ids.py.)"""
    from core.realtime.bh_streamer import BHStreamer
    db = str(tmp_path / "ledger.db")
    # legacy ledger: no `valid` column, legacy 200101 streamer chain id
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE bh_ledger (
        id INTEGER PRIMARY KEY AUTOINCREMENT, tx_hash TEXT UNIQUE,
        entity_id TEXT, from_addr TEXT, to_addr TEXT,
        event_type INTEGER, event_type_name TEXT,
        magnitude_norm REAL, value_wei TEXT, selector TEXT,
        sense_hex TEXT, antisense_hex TEXT,
        block_num INTEGER, block_hash TEXT,
        chain_id INTEGER, chain_label TEXT, ts REAL)""")
    conn.execute(
        "INSERT INTO bh_ledger (tx_hash, entity_id, chain_id, chain_label, ts) "
        "VALUES ('0xleg', 'beo', 200101, 'solana', 1.0)")
    conn.commit()
    conn.close()

    BHStreamer(db_path=db)._init_db()            # migration run #1 (ALTER + re-key)
    BHStreamer(db_path=db)._init_db()            # migration run #2 — idempotent
    conn = sqlite3.connect(db)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(bh_ledger)")}
        assert "valid" in cols
        rows = conn.execute(
            "SELECT chain_id, valid FROM bh_ledger WHERE tx_hash='0xleg'"
        ).fetchall()
        # legacy 200101 re-keyed to canonical 900, valid backfilled
        assert rows == [(900, 1)]
    finally:
        conn.close()


# ═══ Whitelist sanity for the new tables ═══════════════════════════════════════


def test_projection_whitelist_rejects_unknown_tables(tmp_path):
    store = _store(tmp_path)
    try:
        with pytest.raises(ValueError):
            store.read_btcp_table("btcp_state")
        with pytest.raises(ValueError):
            store._btcp_upsert("btcp_state", {"kind": "x"})
    finally:
        store.close()


def test_phase0_writers_drop_unknown_columns(tmp_path):
    """Typo protection: unknown columns are dropped, not written."""
    store = _store(tmp_path)
    try:
        store.record_blo_order("ch", entity_id="e", intent_hash="ih",
                               asset_in="a", asset_out="b",
                               source_chain_id=1, magnitude=1.0,
                               expiry_block=10,
                               not_a_real_column="typo")
        row = store.read_btcp_table("blo_orders")[0]
        assert "not_a_real_column" not in row
        assert row["entity_id"] == "e"
    finally:
        store.close()
