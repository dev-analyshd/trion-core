"""tests/unit/test_beo_witness_binding.py — W3-D BEO binding + persisted nonces.

Two W3-D remediations (W2-F handoff / INV-016, spec §4.1):

1. BEO WITNESS BINDING — core/akashic/beo_lookup.py gives the BTCP
   privacy router a READ-ONLY lookup into the Akashic BEO ledger
   (anima-service/faiss_service.py's SQLite WAL store: beo_clusters →
   entity_meta/entity_records). A behavioral credential's ENTITY is bound
   when the ledger knows it (witness_source upgrades to
   ``akashic_beo_bound`` with the ledger's own facts); an unknown entity
   or absent ledger keeps the honest ``caller_self_attested`` label with
   the reason — scores are NEVER upgraded, only identity-level binding.

2. PERSISTED PER-ENTITY NONCES (spec §4.1) — the BTCP orchestrator's
   per-entity monotonic nonce is store-backed (KV kind ``entity_nonce``):
   the counter survives restarts (fresh orchestrator instance on the same
   state DB resumes from the persisted value instead of re-seeding from
   wall-clock ms), stays strictly monotonic, wraps at 2^32, and degrades
   to the session-scoped counter when the store fails.
"""

import sqlite3

import pytest

from core.akashic.beo_lookup import (
    lookup_beo_binding,
    resolve_beo_db_path,
)
from core.btcp.orchestrator import BTCPOrchestrator, ENTITY_NONCE_KIND, PrivacyLevel


SRC = "0x" + "11" * 20
DST = "0x" + "22" * 20

LEDGER_DDL = """
    CREATE TABLE beo_clusters (address TEXT PRIMARY KEY, canonical TEXT, funding TEXT);
    CREATE TABLE entity_meta (beo_id TEXT PRIMARY KEY, last_active REAL, archetype_id INTEGER);
    CREATE TABLE entity_records (beo_id TEXT, ts REAL, magnitude REAL, entropy REAL, arch_sim REAL, vector BLOB, PRIMARY KEY (beo_id, ts));
"""


def _ledger(tmp_path, rows=True):
    """Synthetic Akashic BEO ledger with SRC bound to beo_001."""
    path = str(tmp_path / "ledger.db")
    conn = sqlite3.connect(path)
    conn.executescript(LEDGER_DDL)
    if rows:
        conn.execute("INSERT INTO beo_clusters VALUES (?, 'beo_001', '0xfund')",
                     (SRC.lower(),))
        conn.execute("INSERT INTO entity_meta VALUES ('beo_001', 1700000000.0, 7)")
        conn.execute(
            "INSERT INTO entity_records VALUES "
            "('beo_001', 1700000100.0, 12.5, 0.71, 0.83, NULL)")
        conn.execute(
            "INSERT INTO entity_records VALUES "
            "('beo_001', 1700000200.0, 13.0, 0.69, 0.81, NULL)")
    conn.commit()
    conn.close()
    return path


# ─── resolve_beo_db_path ──────────────────────────────────────────────────────


class TestResolvePath:
    def test_explicit_path_wins(self, tmp_path, monkeypatch):
        p = _ledger(tmp_path)
        monkeypatch.setenv("TRION_BEO_DB", "/nonexistent/env.db")
        assert resolve_beo_db_path(p) == p

    def test_explicit_missing_path_is_none(self):
        assert resolve_beo_db_path("/nonexistent/ledger.db") is None

    def test_env_trion_beo_db(self, tmp_path, monkeypatch):
        p = _ledger(tmp_path)
        monkeypatch.setenv("TRION_BEO_DB", p)
        assert resolve_beo_db_path(None) == p

    def test_env_faiss_state_db(self, tmp_path, monkeypatch):
        faiss = str(tmp_path / "faiss.db")
        open(faiss, "w").close()
        monkeypatch.delenv("TRION_BEO_DB", raising=False)
        monkeypatch.setenv("FAISS_STATE_DB", faiss)
        assert resolve_beo_db_path(None) == faiss

    def test_faiss_companion_ledger(self, tmp_path, monkeypatch):
        """FAISS_STATE_DB's sibling akashic_state.db is a candidate."""
        monkeypatch.delenv("TRION_BEO_DB", raising=False)
        monkeypatch.setenv("FAISS_STATE_DB", str(tmp_path / "faiss_missing.db"))
        companion = str(tmp_path / "akashic_state.db")
        open(companion, "w").close()          # empty file — existence check only
        assert resolve_beo_db_path(None) == companion

    def test_nonexistent_env_candidates_fall_through(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRION_BEO_DB", str(tmp_path / "missing.db"))
        monkeypatch.setenv("FAISS_STATE_DB", str(tmp_path / "missing2.db"))
        # no candidate exists → None (no ledger ⇒ unbound, never an error)
        assert resolve_beo_db_path(str(tmp_path / "missing.db")) is None


# ─── lookup_beo_binding ───────────────────────────────────────────────────────


class TestLookup:
    def test_address_resolves_to_canonical_beo(self, tmp_path):
        p = _ledger(tmp_path)
        binding = lookup_beo_binding(SRC, db_path=p)
        assert binding is not None
        assert binding["beo_id"] == "beo_001"
        assert binding["address"] == SRC
        assert binding["last_active"] == 1700000000.0
        assert binding["archetype_id"] == 7
        assert binding["ledger_records"] == 2
        assert binding["latest_record"]["ts"] == 1700000200.0
        assert binding["latest_record"]["entropy"] == 0.69
        assert binding["ledger_db"] == p

    def test_uppercase_address_is_normalized(self, tmp_path):
        p = _ledger(tmp_path)
        assert lookup_beo_binding(SRC.upper(), db_path=p)["beo_id"] == "beo_001"

    def test_direct_beo_id_input(self, tmp_path):
        p = _ledger(tmp_path)
        binding = lookup_beo_binding("beo_001", db_path=p)
        assert binding is not None and binding["beo_id"] == "beo_001"

    def test_unknown_address_is_none(self, tmp_path):
        p = _ledger(tmp_path)
        assert lookup_beo_binding("0xdead", db_path=p) is None

    def test_missing_ledger_is_none(self):
        assert lookup_beo_binding(SRC, db_path="/nonexistent/ledger.db") is None

    def test_empty_ledger_unbinds_everything(self, tmp_path):
        p = _ledger(tmp_path, rows=False)
        assert lookup_beo_binding(SRC, db_path=p) is None

    def test_empty_input_is_none(self, tmp_path):
        assert lookup_beo_binding("", db_path=_ledger(tmp_path)) is None

    def test_never_raises_on_corrupt_db(self, tmp_path):
        bad = str(tmp_path / "bad.db")
        with open(bad, "w") as f:
            f.write("this is not a sqlite file")
        assert lookup_beo_binding(SRC, db_path=bad) is None

    def test_env_ledger_is_used(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRION_BEO_DB", _ledger(tmp_path))
        assert lookup_beo_binding(SRC)["beo_id"] == "beo_001"


# ─── orchestrator witness binding (INV-016 / W3-D) ────────────────────────────


def _route(orch, source=SRC, privacy=PrivacyLevel.FULL):
    return orch.create_route(
        source_chain=1,
        dest_chain=137,
        source_address=source,
        dest_address=DST,
        amount=1_000_000,
        asset="0x" + "aa" * 20,
        intent_type="TRANSFER",
        privacy_level=privacy,
        behavioral_data={"coherence": 0.90, "manipulation": 0.05,
                         "liquidity": 0.85, "depth": 900.0},
    )


class TestWitnessBinding:
    def test_bound_entity_upgrades_witness_source(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRION_BEO_DB", _ledger(tmp_path))
        orch = BTCPOrchestrator(state_db=str(tmp_path / "btcp.db"))
        result = _route(orch)
        assert result.success, result.errors
        cred = result.route.proofs["behavioral_credential"]
        assert cred["witness_source"] == "akashic_beo_bound"
        # the binding carries the LEDGER's own facts — not caller claims
        assert cred["beo_binding"]["beo_id"] == "beo_001"
        assert cred["beo_binding"]["ledger_records"] == 2
        # scores stay honestly labeled as caller-supplied
        assert cred["witness_scores_source"] == "caller_supplied_behavioral_data"

    def test_unknown_entity_stays_self_attested_with_reason(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRION_BEO_DB", _ledger(tmp_path, rows=False))
        orch = BTCPOrchestrator(state_db=str(tmp_path / "btcp.db"))
        result = _route(orch)
        cred = result.route.proofs["behavioral_credential"]
        assert cred["witness_source"] == "caller_self_attested"
        assert cred["beo_binding"] is None
        assert "not present in the Akashic BEO ledger" in cred["beo_binding_reason"]
        assert cred["witness_scores_source"] == "caller_supplied_behavioral_data"

    def test_no_ledger_stays_self_attested(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRION_BEO_DB", str(tmp_path / "missing.db"))
        orch = BTCPOrchestrator(state_db=str(tmp_path / "btcp.db"))
        result = _route(orch)
        cred = result.route.proofs["behavioral_credential"]
        assert cred["witness_source"] == "caller_self_attested"
        assert cred["beo_binding"] is None


# ─── persisted per-entity nonces (spec §4.1, W3-D) ────────────────────────────


def _nonce_route(orch, source):
    result = orch.create_route(
        source_chain=1, dest_chain=137, source_address=source,
        dest_address=DST, amount=1_000_000, asset="0x" + "aa" * 20,
        intent_type="TRANSFER",
    )
    assert result.success, result.errors
    return result.route.intent.nonce


class TestPersistedNonces:
    def test_strictly_monotonic_within_instance(self, tmp_path):
        db = str(tmp_path / "n.db")
        orch = BTCPOrchestrator(state_db=db)
        src = "0x" + "ab" * 20
        n1, n2, n3 = (_nonce_route(orch, src) for _ in range(3))
        assert n1 < n2 < n3

    def test_persists_across_restart(self, tmp_path):
        """The W3-D point: a FRESH orchestrator on the same store resumes
        from the persisted counter (no wall-clock reseed rewind)."""
        db = str(tmp_path / "n.db")
        src = "0x" + "cd" * 20
        n1 = _nonce_route(BTCPOrchestrator(state_db=db), src)
        n2 = _nonce_route(BTCPOrchestrator(state_db=db), src)   # "restart"
        n3 = _nonce_route(BTCPOrchestrator(state_db=db), src)
        assert n1 < n2 < n3

    def test_resumes_from_seeded_persisted_value(self, tmp_path):
        from core.btcp.state_store import BtcpStateStore
        db = str(tmp_path / "n.db")
        src = "0x" + "ef" * 20
        store = BtcpStateStore(state_db=db)
        store.save(ENTITY_NONCE_KIND, src, 5000, "uint32")
        store.close()
        orch = BTCPOrchestrator(state_db=db)
        assert _nonce_route(orch, src) == 5001
        assert _nonce_route(orch, src) == 5002

    def test_wraparound_at_2_pow_32(self, tmp_path):
        from core.btcp.state_store import BtcpStateStore
        db = str(tmp_path / "n.db")
        src = "0x" + "fe" * 20
        store = BtcpStateStore(state_db=db)
        store.save(ENTITY_NONCE_KIND, src, 2 ** 32 - 1, "uint32")
        store.close()
        orch = BTCPOrchestrator(state_db=db)
        assert _nonce_route(orch, src) == 1          # documented wrap

    def test_entities_are_independent(self, tmp_path):
        db = str(tmp_path / "n.db")
        orch = BTCPOrchestrator(state_db=db)
        a = "0x" + "01" * 20
        b = "0x" + "02" * 20
        na1 = _nonce_route(orch, a)
        nb1 = _nonce_route(orch, b)
        na2 = _nonce_route(orch, a)
        assert na1 < na2
        assert na1 != nb1 or True     # different seeds may coincide —
        # the guarantee is per-entity monotonicity, not cross-entity
        # distinctness (spec §4.1: per-entity monotonic counter)

    def test_nonce_rows_live_in_the_state_store(self, tmp_path):
        from core.btcp.state_store import BtcpStateStore
        db = str(tmp_path / "n.db")
        src = "0x" + "d1" * 20
        orch = BTCPOrchestrator(state_db=db)
        nonce = _nonce_route(orch, src)
        store = BtcpStateStore(state_db=db)
        try:
            rows = store.load_all(ENTITY_NONCE_KIND)
            assert rows[src][1] == nonce
        finally:
            store.close()

    def test_session_fallback_when_store_fails(self, tmp_path, monkeypatch):
        """Store failure degrades to the session counter (monotonic
        in-process) instead of crashing route creation."""
        db = str(tmp_path / "n.db")
        src = "0x" + "d2" * 20
        orch = BTCPOrchestrator(state_db=db)
        real_store = orch._store

        class FlakyKVStore:
            """Delegates everything to the real store EXCEPT the generic
            KV API the nonce counter uses (load_all/save fail)."""
            def __getattr__(self, name):
                return getattr(real_store, name)

            def load_all(self, kind):
                raise RuntimeError("read failure")

            def save(self, *a, **k):
                raise RuntimeError("write failure")

        orch._store = FlakyKVStore()
        n1 = _nonce_route(orch, src)
        n2 = _nonce_route(orch, src)
        assert 0 < n1 < 2 ** 32
        assert n1 < n2
