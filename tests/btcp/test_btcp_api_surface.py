"""
TRION BTCP — API surface tests (Gaps #3 and #4)
===============================================

Covers the endpoints added to api/btcp_continuum_routes.py:

  Gap #4 — POST /api/v1/btcp/orchestrate
      runs the real BTCPOrchestrator six-step sequence (address validation,
      intent creation, VM encoding, gas estimation, ZK proofs, route
      tracking) with SQLite write-through persistence.

  Gap #3 — the eight docstring-promised module endpoints:
      GET  /api/v1/btcp/escrow/<id>          (persisted escrow lookup)
      POST /api/v1/btcp/bitp/match           (BITPMatcher, Module 2.5)
      POST /api/v1/btcp/netting              (NettingEngine, Module 2.6)
      POST /api/v1/btcp/aggregate            (IntentAggregator, Module 2.7)
      POST /api/v1/btcp/failure_classify     (FailureClassifier, 2.11)
      GET  /api/v1/btcp/version              (VersionHandler, 2.16)
      POST /api/v1/btcp/validator_fee        (ValidatorFeeCalculator, 2.17)
      POST /api/v1/btcp/sybil                (SybilResistance, 2.18)

Plus a docstring-truth test: every /api/... path the blueprint docstring
lists must be a registered route, and every registered route must be listed
— the drift that created Gap #3 can no longer happen silently.

The intent constructors are exercised against BOTH the current BITPIntent
dataclass (unknown extra fields ignored) and an extended variant with the
optional spec fields (action, value, max_total_gas, min_finality,
min_NL_score, chain_pref, privacy, btcp_version, nonce), so the routes keep
working when those fields land.

Run: pytest tests/btcp/test_btcp_api_surface.py -q
"""

import dataclasses
import re

import flask
import pytest

import api.btcp_continuum_routes as btcp_routes
from api.btcp_continuum_routes import btcp_bp


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_route_singletons():
    """Reset module-level caches so tests can't see each other's stores."""
    btcp_routes._ESCROW_STORES.clear()
    btcp_routes._ORCHESTRATOR = None
    yield
    btcp_routes._ESCROW_STORES.clear()
    btcp_routes._ORCHESTRATOR = None


@pytest.fixture()
def client():
    """Flask test client with only the btcp_continuum blueprint mounted."""
    app = flask.Flask(__name__)
    app.register_blueprint(btcp_bp)
    return app.test_client()


def _intent(entity, asset_in, asset_out, magnitude, chain_id, deadline=2_000_000):
    """A minimal BITP intent payload (hex fields as plain hex strings)."""
    return {
        "entity_id": entity,
        "asset_in": asset_in,
        "asset_out": asset_out,
        "magnitude": magnitude,
        "chain_id": chain_id,
        "deadline": deadline,
    }


A_INTENT = _intent("01" * 16, "aa" * 16, "bb" * 16, 1000.0, 1)
B_COMPLEMENT = _intent("02" * 16, "bb" * 16, "aa" * 16, 1000.0, 137)
N_OPPOSITE_SAME_CHAIN = _intent("03" * 16, "bb" * 16, "aa" * 16, 1000.0, 1)


# ── Gap #4: POST /api/v1/btcp/orchestrate ────────────────────────────────────

_ORCHESTRATE_MIN = {
    "source_chain": 1,
    "dest_chain": 137,
    "source_address": "0x" + "11" * 20,
    "dest_address": "0x" + "22" * 20,
    "amount": 1_000_000,
    "asset": "0x" + "aa" * 20,
}


def test_orchestrate_runs_full_six_step_sequence(client):
    r = client.post("/api/v1/btcp/orchestrate", json=_ORCHESTRATE_MIN)
    assert r.status_code == 200
    j = r.get_json()
    assert j["success"] is True
    assert j["errors"] == []
    assert j["route_id"].startswith("route_")

    assert list(j["steps"].keys()) == [
        "1_validate_addresses", "2_create_intent", "3_encode_for_vms",
        "4_estimate_gas", "5_generate_proofs", "6_track_route",
    ]
    assert j["steps"]["1_validate_addresses"]["address_errors"] == []
    assert j["steps"]["2_create_intent"]["intent_id"].startswith("btcp_")
    assert j["steps"]["2_create_intent"]["deadline"] > 0
    assert j["steps"]["3_encode_for_vms"]["source_vm"] == "EVM"
    assert j["steps"]["3_encode_for_vms"]["source_encoded"] is True
    assert j["steps"]["3_encode_for_vms"]["dest_encoded"] is True
    assert j["steps"]["4_estimate_gas"]["source_gas"]["vm_type"] == "EVM"
    assert j["steps"]["4_estimate_gas"]["total_fee"] > 0
    assert j["steps"]["5_generate_proofs"]["generated"]  # at least one circuit
    assert j["steps"]["6_track_route"]["status"] in (
        "INTENT_CREATED", "PROOFS_GENERATED")

    # full route + proofs are returned, and the SQLite write-through landed
    assert j["route"]["route_id"] == j["route_id"]
    assert j["route"]["intent"]["source_chain"] == 1
    assert j["route"]["intent"]["dest_chain"] == 137
    assert j["route"]["assets_bridged"] is False  # zero-bridge invariant
    assert "intent_commitment" in j["proofs"]
    assert j["persistence"]["persisted"] is True
    assert j["persistence"]["state_db"]
    assert j["execution_time_ms"] > 0


def test_orchestrate_route_survives_restart(client):
    """S7 write-through: a fresh orchestrator on the same DB reloads the route."""
    j = client.post("/api/v1/btcp/orchestrate", json=_ORCHESTRATE_MIN).get_json()
    from core.btcp.orchestrator import BTCPOrchestrator
    orch2 = BTCPOrchestrator(state_db=j["persistence"]["state_db"])
    reloaded = orch2.get_route(j["route_id"])
    assert reloaded is not None
    assert reloaded.status.name == j["steps"]["6_track_route"]["status"]
    assert reloaded.intent is not None
    assert reloaded.intent.amount == _ORCHESTRATE_MIN["amount"]


def test_orchestrate_standard_privacy_generates_real_proofs(client):
    """With real witness data every STANDARD-level circuit is a real proof."""
    payload = dict(
        _ORCHESTRATE_MIN,
        privacy_level="STANDARD",
        behavioral_data={
            "genomic_sense": "ab" * 16,
            "genomic_antisense": "cd" * 16,
            "block_number": 18_000_000,
        },
        iap_economics={
            "total_gas": 1_000_000,
            "entity_gas": 151_000,
            "total_btcp_fee_wei": 10**16,
            "entity_share_wei": 10**15,
            "num_participants": 10,
        },
    )
    r = client.post("/api/v1/btcp/orchestrate", json=payload)
    assert r.status_code == 200
    j = r.get_json()
    status = j["steps"]["5_generate_proofs"]["proof_status"]
    assert set(status) == {"intent_commitment", "complementarity", "iap_share"}
    assert all(v == "generated" for v in status.values())
    # real proofs carry actual proof material; deferred ones carry
    # zk_proof: None + status "zk_pending"
    assert j["proofs"]["complementarity"]["proof"]
    assert j["proofs"]["iap_share"]["proof"]


def test_orchestrate_defers_proofs_without_witness_data(client):
    """Without HashDNA strands the complementarity proof is honestly deferred."""
    payload = dict(_ORCHESTRATE_MIN, privacy_level="STANDARD")
    j = client.post("/api/v1/btcp/orchestrate", json=payload).get_json()
    status = j["steps"]["5_generate_proofs"]["proof_status"]
    assert status["complementarity"] == "zk_pending"
    assert j["proofs"]["complementarity"]["zk_proof"] is None
    assert j["proofs"]["complementarity"]["status"] == "zk_pending"
    # fail-closed: deferred circuits make the route NOT fully proven
    assert j["proof_verification"]["all_valid"] is False


def test_orchestrate_privacy_level_by_number(client):
    payload = dict(_ORCHESTRATE_MIN, privacy_level=2)  # STANDARD
    j = client.post("/api/v1/btcp/orchestrate", json=payload).get_json()
    assert j["route"]["privacy_level"] == "STANDARD"


def test_orchestrate_validates_input(client):
    # missing required field
    bad = dict(_ORCHESTRATE_MIN)
    del bad["amount"]
    r = client.post("/api/v1/btcp/orchestrate", json=bad)
    assert r.status_code == 400
    assert "amount" in r.get_json()["error"]

    # unknown privacy level name
    r = client.post("/api/v1/btcp/orchestrate",
                    json=dict(_ORCHESTRATE_MIN, privacy_level="MAXIMUM"))
    assert r.status_code == 400
    assert "privacy_level" in r.get_json()["error"]

    # out-of-range privacy level number
    r = client.post("/api/v1/btcp/orchestrate",
                    json=dict(_ORCHESTRATE_MIN, privacy_level=99))
    assert r.status_code == 400

    # negative chain id
    r = client.post("/api/v1/btcp/orchestrate",
                    json=dict(_ORCHESTRATE_MIN, source_chain=-1))
    assert r.status_code == 400

    # non-positive deadline offset
    r = client.post("/api/v1/btcp/orchestrate",
                    json=dict(_ORCHESTRATE_MIN, deadline_offset=0))
    assert r.status_code == 400

    # behavioral_data must be an object
    r = client.post("/api/v1/btcp/orchestrate",
                    json=dict(_ORCHESTRATE_MIN, behavioral_data=["nope"]))
    assert r.status_code == 400
    assert "behavioral_data" in r.get_json()["error"]


def test_orchestrate_is_not_slow(client):
    """The orchestrator is pure-Python and fast — a full route is well under
    a second, which is why the endpoint runs it synchronously."""
    import time
    t0 = time.perf_counter()
    r = client.post("/api/v1/btcp/orchestrate", json=_ORCHESTRATE_MIN)
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 5.0


# ── Gap #3: GET /api/v1/btcp/escrow/<id> ─────────────────────────────────────

def test_escrow_unknown_id_is_honest_404(client):
    r = client.get("/api/v1/btcp/escrow/no-such-escrow")
    assert r.status_code == 404
    j = r.get_json()
    assert j["found"] is False
    assert "not found" in j["error"]
    assert isinstance(j["persisted_escrow_count"], int)


def test_escrow_lookup_returns_persisted_state(client, monkeypatch, tmp_path):
    """Escrows locked by the monitor (any process) are visible read-back."""
    db = tmp_path / "btcp_state.db"
    monkeypatch.setenv("TRION_STATE_DB", str(db))

    from core.btcp.escrow_monitor import EscrowMonitor
    monitor = EscrowMonitor(state_db=str(db))
    esc = monitor.lock_escrow(
        "esc_api_1", "route_1", b"\x01" * 16, 250.0, 500)
    assert esc.state.name == "HOLDING"

    r = client.get("/api/v1/btcp/escrow/esc_api_1")
    assert r.status_code == 200
    j = r.get_json()
    assert j["found"] is True
    assert j["type_tag"] == "escrow_v1"
    assert j["state"] == "HOLDING"
    assert j["escrow"]["escrow_id"] == "esc_api_1"
    assert j["escrow"]["route_id"] == "route_1"
    assert j["escrow"]["entity_id"] == "01" * 16
    assert j["escrow"]["amount"] == 250.0
    assert j["escrow"]["timeout_blocks"] == 500
    # state transitions are visible read-back too
    monitor.verify_settlement("esc_api_1")
    assert monitor.release_escrow("esc_api_1", coherence=0.9)
    j2 = client.get("/api/v1/btcp/escrow/esc_api_1").get_json()
    assert j2["state"] == "RELEASED"
    assert j2["escrow"]["settlement_verified"] is True


# ── Gap #3: POST /api/v1/btcp/bitp/match ─────────────────────────────────────

def test_bitp_match_finds_cross_chain_complement(client):
    r = client.post("/api/v1/btcp/bitp/match",
                    json={"intent": A_INTENT, "candidates": [B_COMPLEMENT]})
    assert r.status_code == 200
    j = r.get_json()
    assert j["matched"] is True
    assert j["complement"]["entity_id"] == "02" * 16
    assert j["complement"]["asset_in"] == "bb" * 16
    assert j["complement"]["chain_id"] == 137
    assert j["candidates_considered"] == 1
    # PASTE phase result: zero cross-chain movement, no bridge
    assert j["paste"]["cross_chain_movement"] == 0
    assert j["paste"]["bridge"] == "NONE"
    assert j["paste"]["asset_x_stays_on_chain_a"] is True


def test_bitp_match_accepts_top_level_intent(client):
    """The intent may also be supplied at the top level of the payload."""
    r = client.post("/api/v1/btcp/bitp/match",
                    json=dict(A_INTENT, candidates=[B_COMPLEMENT]))
    assert r.status_code == 200
    assert r.get_json()["matched"] is True


def test_bitp_match_no_complement(client):
    same_chain = _intent("02" * 16, "bb" * 16, "aa" * 16, 1000.0, 1)
    r = client.post("/api/v1/btcp/bitp/match",
                    json={"intent": A_INTENT, "candidates": [same_chain]})
    assert r.status_code == 200
    j = r.get_json()
    assert j["matched"] is False
    assert j["complement"] is None
    assert j["paste"] is None

    # empty candidate list → no match, not an error
    r = client.post("/api/v1/btcp/bitp/match",
                    json={"intent": A_INTENT, "candidates": []})
    assert r.status_code == 200
    assert r.get_json()["matched"] is False


def test_bitp_match_validates_intent_fields(client):
    # invalid hex entity id
    r = client.post("/api/v1/btcp/bitp/match",
                    json={"intent": dict(A_INTENT, entity_id="zz"),
                          "candidates": []})
    assert r.status_code == 400
    assert "entity_id" in r.get_json()["error"]

    # missing magnitude
    bad = dict(A_INTENT)
    del bad["magnitude"]
    r = client.post("/api/v1/btcp/bitp/match",
                    json={"intent": bad, "candidates": []})
    assert r.status_code == 400
    assert "magnitude" in r.get_json()["error"]

    # candidates must be a list
    r = client.post("/api/v1/btcp/bitp/match",
                    json={"intent": A_INTENT, "candidates": "nope"})
    assert r.status_code == 400
    assert "candidates" in r.get_json()["error"]


def test_bitp_match_tolerates_optional_intent_fields(client):
    """Payloads carrying the §4.1 optional intent fields (action, value,
    max_total_gas, min_finality, min_NL_score, chain_pref, privacy,
    btcp_version, nonce) work whether or not the running BITPIntent
    dataclass declares them — forwarded when present, ignored when not.
    The strict forwarding assertions live in the builder unit test below.
    """
    intent = dict(A_INTENT, action="SWAP", value=100.0,
                  max_total_gas=50.0, min_finality="FAST", min_NL_score=400,
                  chain_pref=[1, 137], privacy="ZK_CREDENTIAL",
                  btcp_version="1.2.0", nonce=7)
    r = client.post("/api/v1/btcp/bitp/match",
                    json={"intent": intent, "candidates": [B_COMPLEMENT]})
    assert r.status_code == 200
    assert r.get_json()["matched"] is True


def test_bitp_intent_builder_forwards_optional_fields(monkeypatch):
    """The intent builder passes optional fields through when (and only when)
    the running BITPIntent dataclass declares them — proven with an extended
    dataclass that mimics the planned spec fields."""
    import core.btcp.modules as modules_mod

    @dataclasses.dataclass
    class ExtendedIntent:
        entity_id: bytes
        asset_in: bytes
        asset_out: bytes
        magnitude: float
        chain_id: int
        deadline: int
        action: str = "SWAP"
        value: float = 0.0
        max_total_gas: float = 0.0
        min_finality: float = 0.0
        min_nl_score: int = 300
        chain_pref: list = dataclasses.field(default_factory=list)
        privacy: str = "PUBLIC"
        btcp_version: str = "1.0.0"
        nonce: int = 0

    monkeypatch.setattr(modules_mod, "BITPIntent", ExtendedIntent)

    payload = dict(
        A_INTENT,
        action="TRANSFER", value=250.0, max_total_gas=31.0,
        min_finality=12.0, min_NL_score=0.85, chain_pref=[1, 8453],
        privacy="STANDARD", btcp_version="1.2.0", nonce=9,
        totally_unknown_field="ignored",
    )
    intent = btcp_routes._build_bitp_intent(payload)
    assert isinstance(intent, ExtendedIntent)
    assert intent.entity_id == bytes.fromhex("01" * 16)
    assert intent.asset_in == bytes.fromhex("aa" * 16)
    assert intent.magnitude == 1000.0
    # optional fields forwarded (spec spelling min_NL_score → field
    # min_nl_score through the alias)
    assert intent.action == "TRANSFER"
    assert intent.value == 250.0
    assert intent.max_total_gas == 31.0
    assert intent.chain_pref == [1, 8453]
    assert intent.privacy == "STANDARD"
    assert intent.btcp_version == "1.2.0"
    assert intent.nonce == 9
    assert intent.min_finality == 12.0
    # a payload WITHOUT optional fields keeps the dataclass defaults
    bare = btcp_routes._build_bitp_intent(A_INTENT)
    assert bare.privacy == "PUBLIC"
    assert bare.max_total_gas == 0.0
    assert bare.nonce == 0


# ── Gap #3: POST /api/v1/btcp/netting ────────────────────────────────────────

def test_netting_finds_opposite_intent_same_chain(client):
    r = client.post("/api/v1/btcp/netting",
                    json={"intent": A_INTENT,
                          "candidates": [N_OPPOSITE_SAME_CHAIN, B_COMPLEMENT]})
    assert r.status_code == 200
    j = r.get_json()
    assert j["netting_found"] is True
    assert j["netting_pair"]["entity_id"] == "03" * 16
    assert j["netting_pair"]["chain_id"] == 1
    assert j["netting_gas_cost"] == 0.05  # $0.05 state-update floor
    assert j["tolerance"] == 0.01


def test_netting_rejects_cross_chain_candidate(client):
    """Netting is same-chain only — the cross-chain complement must NOT match."""
    r = client.post("/api/v1/btcp/netting",
                    json={"intent": A_INTENT, "candidates": [B_COMPLEMENT]})
    assert r.status_code == 200
    assert r.get_json()["netting_found"] is False


def test_netting_validates_input(client):
    r = client.post("/api/v1/btcp/netting", json={"intent": A_INTENT})
    assert r.status_code == 200  # no candidates → no pair, not an error
    r = client.post("/api/v1/btcp/netting",
                    json={"intent": dict(A_INTENT, asset_in="xyz")})
    assert r.status_code == 400
    assert "asset_in" in r.get_json()["error"]


# ── Gap #3: POST /api/v1/btcp/aggregate ──────────────────────────────────────

def test_aggregate_pools_same_direction_intents(client):
    pool = [
        _intent(f"{i:02x}" * 16, "aa" * 16, "bb" * 16, 100.0, 1)
        for i in range(1, 5)  # 4 intents, same assets+chain
    ]
    r = client.post("/api/v1/btcp/aggregate",
                    json={"intents": pool, "window_blocks": 10,
                          "total_gas": 0.80, "user_value": 100.0,
                          "total_value": 400.0})
    assert r.status_code == 200
    j = r.get_json()
    assert j["pool_found"] is True
    assert j["pool_size"] == 4
    assert j["min_intents"] == 3
    assert all(i["chain_id"] == 1 for i in j["pool"])
    assert j["per_user_gas"] == pytest.approx(0.20)
    # value-weighted: 0.80 × (100/400) = 0.20 for the uniform pool too
    assert j["per_user_gas_weighted"] == pytest.approx(0.20)


def test_aggregate_weighted_differs_for_unequal_values(client):
    pool = [
        _intent("01" * 16, "aa" * 16, "bb" * 16, 100.0, 1),
        _intent("02" * 16, "aa" * 16, "bb" * 16, 100.0, 1),
        _intent("03" * 16, "aa" * 16, "bb" * 16, 300.0, 1),
    ]
    r = client.post("/api/v1/btcp/aggregate",
                    json={"intents": pool, "total_gas": 0.80,
                          "user_value": 100.0, "total_value": 500.0})
    j = r.get_json()
    assert j["pool_found"] is True
    assert j["per_user_gas"] == pytest.approx(0.80 / 3)
    assert j["per_user_gas_weighted"] == pytest.approx(0.80 * 100.0 / 500.0)


def test_aggregate_requires_min_intents(client):
    pool = [
        _intent("01" * 16, "aa" * 16, "bb" * 16, 100.0, 1),
        _intent("02" * 16, "aa" * 16, "bb" * 16, 100.0, 1),
    ]
    r = client.post("/api/v1/btcp/aggregate", json={"intents": pool})
    assert r.status_code == 200
    j = r.get_json()
    assert j["pool_found"] is False
    assert j["pool"] == []
    assert j["pool_size"] == 0


def test_aggregate_validates_input(client):
    r = client.post("/api/v1/btcp/aggregate", json={"intents": "nope"})
    assert r.status_code == 400
    assert "intents" in r.get_json()["error"]
    r = client.post("/api/v1/btcp/aggregate", json={"intents": [{"bad": 1}]})
    assert r.status_code == 400
    assert "intents[0]" in r.get_json()["error"]


def test_aggregate_pool_round_trips_optional_intent_fields(client):
    """When the real BITPIntent carries the §4.1 optional fields they are
    forwarded and serialized back in the pool (skipped honestly while the
    dataclass still has only the legacy six fields)."""
    import dataclasses
    from core.btcp.modules import BITPIntent
    field_names = {f.name for f in dataclasses.fields(BITPIntent)}
    if "action" not in field_names:
        pytest.skip("BITPIntent §4.1 optional fields not present yet")

    pool = [
        dict(A_INTENT, action="TRANSFER", privacy="ZK_CREDENTIAL",
             btcp_version="1.2.0", nonce=11, min_nl_score=400),
        _intent("02" * 16, "aa" * 16, "bb" * 16, 100.0, 1),
        _intent("03" * 16, "aa" * 16, "bb" * 16, 100.0, 1),
    ]
    r = client.post("/api/v1/btcp/aggregate", json={"intents": pool})
    assert r.status_code == 200
    j = r.get_json()
    assert j["pool_found"] is True
    first = j["pool"][0]
    assert first["action"] == "TRANSFER"
    assert first["privacy"] == "ZK_CREDENTIAL"
    assert first["btcp_version"] == "1.2.0"
    assert first["nonce"] == 11
    assert first["min_nl_score"] == 400


# ── Gap #3: POST /api/v1/btcp/failure_classify ───────────────────────────────

def test_failure_classify_external_cause(client):
    r = client.post("/api/v1/btcp/failure_classify",
                    json={"chain_outage": True, "mf_spike": True})
    assert r.status_code == 200
    j = r.get_json()
    assert j["classification"] == "EXTERNAL_CAUSE"
    assert j["indicators"]["chain_outage"] is True
    assert j["indicators"]["invalid_proof"] is False
    assert j["prior_ambiguous_count"] == 0


def test_failure_classify_entity_cause(client):
    r = client.post("/api/v1/btcp/failure_classify",
                    json={"invalid_proof": True, "collateral_withdrawn": True})
    assert r.status_code == 200
    assert r.get_json()["classification"] == "ENTITY_CAUSE"


def test_failure_classify_ambiguous_escalation(client):
    """No indicators + prior_ambiguous_count >= 2 → ENTITY (benefit of
    doubt exhausted)."""
    r = client.post("/api/v1/btcp/failure_classify",
                    json={"prior_ambiguous_count": 2})
    assert r.get_json()["classification"] == "ENTITY_CAUSE"
    r = client.post("/api/v1/btcp/failure_classify",
                    json={"prior_ambiguous_count": 1})
    assert r.get_json()["classification"] == "EXTERNAL_CAUSE"


def test_failure_classify_validates_types(client):
    r = client.post("/api/v1/btcp/failure_classify", json={"chain_outage": "yes"})
    assert r.status_code == 400
    assert "chain_outage" in r.get_json()["error"]
    r = client.post("/api/v1/btcp/failure_classify",
                    json={"prior_ambiguous_count": "two"})
    assert r.status_code == 400
    assert "prior_ambiguous_count" in r.get_json()["error"]


# ── Gap #3: GET /api/v1/btcp/version ─────────────────────────────────────────

def test_version_defaults_and_compatibility(client):
    r = client.get("/api/v1/btcp/version")
    assert r.status_code == 200
    j = r.get_json()
    assert j["compatible"] is True  # 1.0.0 >= 1.0.0
    assert j["verifier_version"]["parsed"] == [1, 0, 0]
    assert j["adapter_version_bonus"] == 0.03

    r = client.get("/api/v1/btcp/version?verifier_version=1.9.9&min_version=2.0.0")
    assert r.get_json()["compatible"] is False


def test_version_breaking_change_detection(client):
    r = client.get("/api/v1/btcp/version"
                   "?verifier_version=2.1.0&min_version=2.0.0"
                   "&old_version=1.9.0&new_version=2.0.0")
    assert r.status_code == 200
    j = r.get_json()
    assert j["compatible"] is True
    assert j["breaking_change"] is True
    assert j["old_version"]["parsed"] == [1, 9, 0]

    r = client.get("/api/v1/btcp/version"
                   "?old_version=2.0.0&new_version=2.1.0")
    assert r.get_json()["breaking_change"] is False


def test_version_validates_input(client):
    r = client.get("/api/v1/btcp/version?verifier_version=not-semver")
    assert r.status_code == 400
    # old/new must be supplied together
    r = client.get("/api/v1/btcp/version?old_version=1.0.0")
    assert r.status_code == 400
    assert "together" in r.get_json()["error"]


# ── Gap #3: POST /api/v1/btcp/validator_fee ──────────────────────────────────

_FEE_PAYLOAD = {
    "chains_covered": [1, 137],
    "validators_per_chain": {"1": 50, "137": 30},
    "total_validators": 100,
    "volume_per_chain": {"1": 1.0, "137": 0.8},
    "uptime_per_chain": {"1": 0.99, "137": 0.95},
}


def test_validator_fee_coverage_bonus_and_route_split(client):
    r = client.post("/api/v1/btcp/validator_fee",
                    json=dict(_FEE_PAYLOAD, total_route_reward=1000.0))
    assert r.status_code == 200
    j = r.get_json()
    assert j["base_rate"] == 100.0
    # rarity = total / covering
    assert j["rarity_factors"]["1"] == pytest.approx(2.0)
    assert j["rarity_factors"]["137"] == pytest.approx(100 / 30)
    # bonus = 100·2·1·0.99 + 100·(100/30)·0.8·0.95
    expected = 100 * 2.0 * 1.0 * 0.99 + 100 * (100 / 30) * 0.8 * 0.95
    assert j["coverage_bonus"] == pytest.approx(expected)
    # 60/40 split (Fix 4)
    reward = j["btcp_route_reward"]
    assert reward["anchor_validators"] == pytest.approx(600.0)
    assert reward["execution_validators"] == pytest.approx(400.0)
    assert reward["anchor_share"] == 0.60


def test_validator_fee_without_route_reward(client):
    r = client.post("/api/v1/btcp/validator_fee", json=_FEE_PAYLOAD)
    assert r.status_code == 200
    assert "btcp_route_reward" not in r.get_json()


def test_validator_fee_validates_input(client):
    # rarity factor is undefined for an uncovered chain → 400, not inf
    r = client.post("/api/v1/btcp/validator_fee", json={
        "chains_covered": [1],
        "validators_per_chain": {"1": 0},
        "total_validators": 10,
    })
    assert r.status_code == 400
    assert "rarity" in r.get_json()["error"]

    r = client.post("/api/v1/btcp/validator_fee",
                    json=dict(_FEE_PAYLOAD, total_validators=0))
    assert r.status_code == 400
    assert "total_validators" in r.get_json()["error"]

    r = client.post("/api/v1/btcp/validator_fee",
                    json=dict(_FEE_PAYLOAD, chains_covered="1"))
    assert r.status_code == 400
    assert "chains_covered" in r.get_json()["error"]


# ── Gap #3: POST /api/v1/btcp/sybil ──────────────────────────────────────────

def test_sybil_all_five_layers(client):
    star_sponsor = "aa" * 16
    sponsor_graph = {
        star_sponsor: [f"{i:02x}" * 16 for i in range(25)],  # > 20 → star
        "bb" * 16: ["cc" * 16, "dd" * 16],                   # normal sponsor
    }
    r = client.post("/api/v1/btcp/sybil", json={
        "depth_d": 800.0, "depth_d_min": 100.0,
        "n_sponsored": 4,
        "cosine_similarity": 0.90,
        "sponsor_graph": sponsor_graph,
    })
    assert r.status_code == 200
    j = r.get_json()
    layers = j["layers"]
    # layer 1: floor(log2(8) × 10) = 30
    assert layers["layer1_max_sponsored"] == 30
    # layer 2: 1 + 4×0.2
    assert layers["layer2_scrutiny_multiplier"] == pytest.approx(1.8)
    # layer 3: 0.90 > 0.85 threshold
    assert layers["layer3_sockpuppet_alert"] is True
    # layer 4: 7 × 4²
    assert layers["layer4_min_spacing_days"] == pytest.approx(112.0)
    # layer 5: only the star sponsor is flagged
    assert layers["layer5_suspicious_sponsors"] == [star_sponsor]
    assert j["constants"]["similarity_threshold"] == 0.85


def test_sybil_partial_layers(client):
    r = client.post("/api/v1/btcp/sybil", json={"cosine_similarity": 0.50})
    assert r.status_code == 200
    j = r.get_json()
    assert set(j["layers"]) == {"layer3_sockpuppet_alert"}
    assert j["layers"]["layer3_sockpuppet_alert"] is False


def test_sybil_zero_cap_when_depth_below_minimum(client):
    r = client.post("/api/v1/btcp/sybil",
                    json={"depth_d": 50.0, "depth_d_min": 100.0})
    assert r.get_json()["layers"]["layer1_max_sponsored"] == 0


def test_sybil_validates_input(client):
    r = client.post("/api/v1/btcp/sybil", json={})
    assert r.status_code == 400
    assert "no layer inputs" in r.get_json()["error"]

    # depth given without depth_d_min
    r = client.post("/api/v1/btcp/sybil", json={"depth_d": 800.0})
    assert r.status_code == 400
    assert "depth_d_min" in r.get_json()["error"]

    # malformed sponsor graph
    r = client.post("/api/v1/btcp/sybil",
                    json={"sponsor_graph": {"zz": ["01" * 16]}})
    assert r.status_code == 400
    assert "not valid hex" in r.get_json()["error"]

    r = client.post("/api/v1/btcp/sybil",
                    json={"sponsor_graph": {"01" * 16: "not-a-list"}})
    assert r.status_code == 400
    assert "must be a list" in r.get_json()["error"]


# ── Docstring truth + full-app wiring ────────────────────────────────────────

def _normalize(path):
    """Collapse <param> placeholders so docstring and url_map agree."""
    return re.sub(r"<[^>]+>", "<x>", path)


def test_docstring_lists_exactly_the_registered_routes(client):
    """Gap #3 regression guard: every /api/... path promised in the blueprint
    docstring must be a real registered route — and every registered route
    must be promised. Placeholder names (<id> vs <escrow_id>) normalize."""
    doc = btcp_routes.__doc__ or ""
    listed = re.findall(r"^\s+(/api/v1/\S+)", doc, re.MULTILINE)
    assert listed, "docstring endpoint list not found"
    assert len(listed) == len(set(listed)), "duplicate docstring paths"

    app = flask.Flask(__name__)
    app.register_blueprint(btcp_bp)
    rules = {str(r) for r in app.url_map.iter_rules()
             if not str(r).startswith("/static")}
    assert rules, "blueprint registered no routes"

    listed_norm = {_normalize(p) for p in listed}
    rules_norm = {_normalize(r) for r in rules}
    missing = listed_norm - rules_norm
    undocumented = rules_norm - listed_norm
    assert not missing, f"docstring promises non-existent routes: {sorted(missing)}"
    assert not undocumented, f"routes missing from the docstring: {sorted(undocumented)}"


def test_new_routes_are_wired_into_the_full_api_app():
    """The blueprint's new endpoints must be live on the real app too."""
    from api.app import app  # noqa: import side effects match other tests
    rules = {str(r) for r in app.url_map.iter_rules()}
    for path in (
        "/api/v1/btcp/orchestrate",
        "/api/v1/btcp/escrow/<escrow_id>",
        "/api/v1/btcp/bitp/match",
        "/api/v1/btcp/netting",
        "/api/v1/btcp/aggregate",
        "/api/v1/btcp/failure_classify",
        "/api/v1/btcp/version",
        "/api/v1/btcp/validator_fee",
        "/api/v1/btcp/sybil",
    ):
        assert path in rules, f"{path} not registered on the full app"
