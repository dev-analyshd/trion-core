"""
W3-M — API truth-boundary attack battery
=========================================

Master command §15: "APIs submit evidence, never manufacture truth."

Flask-test-client attacks against every API surface that accepts
security-critical values from a caller:

  * POST /api/v1/btcp/orchestrate  — adversarial behavioral_data /
    iap_economics must be surfaced as caller-supplied WITNESS EVIDENCE
    (witness_source labels, zk_pending list) and must never be presented
    as verified truth (W2-F handoff).
  * POST /api/v1/btcp/bitp/match   — price_tolerance is CAPPED (an
    unbounded tolerance degenerates price discovery into arbitrary
    pairing); POST /api/v1/btcp/netting — same cap for ``tolerance``.
  * POST /api/v1/continuum/settlement — ``btcp_route_verified`` is a
    settlement GATE: caller claims are labeled caller_attested (default
    False), and with ``route_id`` the gate is DERIVED from persisted
    route proofs (caller assertion ignored).
  * POST /api/v1/governance/gratitude  — self-reported disclosures are
    recorded UNVERIFIED (the old route hardcoded verified=True).
  * POST /api/v1/kv/signal/<id>        — demo KV write labeled honestly
    (the old response claimed immutable=True / da_submitted=True).
  * POST /api/v1/governance/slashing/file — evidence-only filing with
    caller-declared quorum base labeled unverified; no accuser default.
  * POST /api/v1/reputation/observe (+endorse/dispute) — caller-attested
    observations and unauthenticated endorser ids labeled as such.
  * POST /api/v1/btcp/sanctions       — fail-closed without credentials.
  * POST /api/v1/cex/webhook/register — SSRF guard (private/loopback).
  * API key middleware (TRION_API_KEY) enforcement on write methods.
  * POST /api/v1/price/seed + the Chainlink-style price responses —
    provenance labels (bootstrap_demo vs relayer_submitted).

Plus static source assertions for the relayer (fail-closed signal
validation, honest single-signature docstring, node --check) and the SDK
(no client-side signing / quorum truth; trust-model README).

Run: pytest tests/unit/test_api_truth_boundaries.py -q
"""
import json
import os
import re
import shutil
import subprocess

import flask
import pytest

import api.btcp_continuum_routes as btcp_routes
from api.btcp_continuum_routes import btcp_bp

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_route_singletons():
    """Reset module-level caches so tests can't see each other's stores."""
    btcp_routes._ESCROW_STORES.clear()
    btcp_routes._ORCHESTRATOR = None
    btcp_routes._SANCTIONS_ORACLE = None
    yield
    btcp_routes._ESCROW_STORES.clear()
    btcp_routes._ORCHESTRATOR = None
    btcp_routes._SANCTIONS_ORACLE = None


@pytest.fixture()
def client():
    """Flask test client with only the btcp_continuum blueprint mounted."""
    app = flask.Flask(__name__)
    app.register_blueprint(btcp_bp)
    return app.test_client()


@pytest.fixture(scope="module")
def full_app_client():
    """Test client for the FULL api.app (app.py routes + middleware).

    Imported once per module (heavy import, same pattern as
    tests/adversarial/test_adversarial_suite.py). Rate-limit buckets are
    cleared so the middleware tests start from a clean slate.
    """
    from api.app import app  # noqa: import side effects match other tests
    import api.app as api_app
    with api_app._rl_lock:
        api_app._rl_buckets.clear()
    return app.test_client()


_ORCH_MIN = {
    "source_chain": 1,
    "dest_chain": 137,
    "source_address": "0x" + "11" * 20,
    "dest_address": "0x" + "22" * 20,
    "amount": 1_000_000,
    "asset": "0x" + "aa" * 20,
}


# ── /api/v1/btcp/orchestrate — witness provenance surfacing (W2-F) ───────────

def test_orchestrate_surfaces_zk_pending_and_witness_inputs(client):
    """A BASIC route with no witness inputs: deferred proofs must be hoisted
    to the top level as zk_pending and the fail-closed verdict must be
    False — the response may never read as 'fully proven'."""
    r = client.post("/api/v1/btcp/orchestrate", json=_ORCH_MIN)
    assert r.status_code == 200
    j = r.get_json()

    prov = j["proof_provenance"]
    assert "note" in prov and "zk_pending" in prov["note"]
    # the IAP share proof is deferred without batch economics
    assert "iap_share" in prov["zk_pending"]
    # witness inputs honestly reported as absent
    assert j["witness_inputs"]["behavioral_data"] is False
    assert j["witness_inputs"]["iap_economics"] is False
    # fail-closed: pending proofs make the route NOT fully proven
    assert j["proof_verification"]["all_valid"] is False
    assert any("pending" in e for e in j["proof_verification"]["errors"])


def test_orchestrate_labels_adversarial_behavioral_data_as_self_attested(client):
    """FULL privacy + adversarial behavioral_data (perfect self-claimed
    coherence): the response must label the credential witness_source=
    caller_self_attested at BOTH the proof level and the top-level summary,
    and must not present the self-attested claim as verified."""
    payload = dict(_ORCH_MIN)
    payload["privacy_level"] = "FULL"
    payload["behavioral_data"] = {
        "coherence": 1.0,       # perfect self-attestation
        "manipulation": 0.0,
        "liquidity": 1.0,
        "depth": 99999.0,
    }
    payload["iap_economics"] = {
        "total_gas": 1_000_000,
        "entity_gas": 151_000,
        "total_btcp_fee_wei": 10 ** 16,
        "entity_share_wei": 15 * 10 ** 14,
        "num_participants": 10,
    }
    r = client.post("/api/v1/btcp/orchestrate", json=payload)
    assert r.status_code == 200
    j = r.get_json()

    # proof-level label (landed by W1-F in the orchestrator)
    cred = j["proofs"]["behavioral_credential"]
    assert cred["witness_source"] == "caller_self_attested"

    # W2-F/W3-M: the label must ALSO be surfaced at the top level
    prov = j["proof_provenance"]
    assert prov["per_proof"]["behavioral_credential"]["witness_source"] \
        == "caller_self_attested"
    assert "behavioral_credential" in prov["witness_source_labels"]
    assert "iap_share" in prov["witness_source_labels"] or \
        "iap_share" in prov["zk_pending"]
    assert j["witness_inputs"]["behavioral_data"] is True
    assert j["witness_inputs"]["iap_economics"] is True

    # no genomic strands supplied → complementarity deferred → the route is
    # NOT fully proven even though the caller claimed perfect coherence
    assert "complementarity" in prov["zk_pending"]
    assert j["proof_verification"]["all_valid"] is False


def test_orchestrate_rejects_non_object_witness_inputs(client):
    payload = dict(_ORCH_MIN)
    payload["behavioral_data"] = "not-an-object"
    r = client.post("/api/v1/btcp/orchestrate", json=payload)
    assert r.status_code == 400
    assert "behavioral_data" in r.get_json()["error"]


# ── /api/v1/btcp/bitp/match — price_tolerance cap ────────────────────────────

def _intent(entity, magnitude, chain_id=1, asset_in="aa" * 16, asset_out="bb" * 16):
    return {
        "entity_id": entity,
        "asset_in": asset_in,
        "asset_out": asset_out,
        "magnitude": magnitude,
        "chain_id": chain_id,
        "deadline": 2_000_000,
    }


def _complement(entity, magnitude, chain_id=137):
    """The BITP complement: wants what A has, has what A wants."""
    return _intent(entity, magnitude, chain_id,
                   asset_in="bb" * 16, asset_out="aa" * 16)


def test_bitp_match_price_tolerance_capped(client):
    """An attacker-supplied price_tolerance above the cap must be rejected —
    behavioral price discovery cannot run with an unbounded band."""
    body = {
        "intent": _intent("01" * 16, 1000.0),
        "candidates": [_complement("02" * 16, 5000.0)],
        "price_tolerance": 0.5,     # 50% — way past the 0.10 cap
    }
    r = client.post("/api/v1/btcp/bitp/match", json=body)
    assert r.status_code == 400
    assert "capped" in r.get_json()["error"]


def test_bitp_match_price_tolerance_rejects_negative_and_nan(client):
    body = {"intent": _intent("01" * 16, 1000.0),
            "candidates": [_complement("02" * 16, 1000.0)]}
    r = client.post("/api/v1/btcp/bitp/match",
                    json={**body, "price_tolerance": -0.01})
    assert r.status_code == 400
    # NaN smuggled through non-strict JSON
    nan_body = json.dumps(body)[:-1] + ', "price_tolerance": NaN}'
    r = client.post("/api/v1/btcp/bitp/match",
                    data=nan_body, content_type="application/json")
    assert r.status_code == 400


def test_bitp_match_within_band_still_works(client):
    """Legitimate tolerances (spec default 0.02, widened ≤ 0.10) keep
    working and the response echoes the enforced cap."""
    body = {
        "intent": _intent("01" * 16, 1000.0),
        "candidates": [_complement("02" * 16, 1005.0)],
    }
    r = client.post("/api/v1/btcp/bitp/match", json=body)
    assert r.status_code == 200
    j = r.get_json()
    assert j["matched"] is True
    assert j["price_tolerance"] == 0.02
    assert j["price_tolerance_cap"] == btcp_routes.MATCH_TOLERANCE_MAX

    r = client.post("/api/v1/btcp/bitp/match",
                    json={**body, "price_tolerance": 0.05})
    assert r.status_code == 200
    assert r.get_json()["price_tolerance"] == 0.05


def test_bitp_match_capped_tolerance_cannot_match_divergent_magnitudes(client):
    """Even the MAXIMUM allowed tolerance must not pair a 10%-divergent
    magnitude — the cap is a ceiling, not a license for arbitrary pairing."""
    body = {
        "intent": _intent("01" * 16, 1000.0),
        "candidates": [_complement("02" * 16, 1200.0)],
        "price_tolerance": 0.10,    # exactly at the cap
    }
    r = client.post("/api/v1/btcp/bitp/match", json=body)
    assert r.status_code == 200
    assert r.get_json()["matched"] is False


def test_netting_tolerance_capped(client):
    body = {
        "intent": _intent("01" * 16, 1000.0),
        "candidates": [_intent("03" * 16, 1000.0)],
        "tolerance": 2.0,
    }
    r = client.post("/api/v1/btcp/netting", json=body)
    assert r.status_code == 400
    assert "capped" in r.get_json()["error"]


# ── /api/v1/continuum/settlement — the btcp_route_verified gate ──────────────

def test_settlement_default_gate_is_not_verified(client):
    """Omitting btcp_route_verified must NOT read as 'route verified'
    (the old default was True — a silent settlement authorization)."""
    r = client.post("/api/v1/continuum/settlement", json={})
    assert r.status_code == 200
    j = r.get_json()
    assert j["btcp_route_verified"] is False
    assert j["btcp_route_verified_provenance"] == "caller_attested"
    assert j["input_provenance"]["coherence_a"] == "caller_supplied"
    assert j["triggered"] is False  # gate closed → no settlement trigger


def test_settlement_caller_claim_is_labeled_not_trusted(client):
    """A caller asserting btcp_route_verified=true gets a computation
    preview that is EXPLICITLY labeled caller_attested."""
    r = client.post("/api/v1/continuum/settlement",
                    json={"btcp_route_verified": True})
    assert r.status_code == 200
    j = r.get_json()
    assert j["btcp_route_verified"] is True
    assert j["btcp_route_verified_provenance"] == "caller_attested"
    assert j["input_provenance"]["note"]
    # non-boolean gate claims are rejected outright
    r = client.post("/api/v1/continuum/settlement",
                    json={"btcp_route_verified": "yes"})
    assert r.status_code == 400


def test_settlement_route_id_derives_gate_from_state_and_ignores_claim(client):
    """With route_id, the gate is DERIVED from the persisted route's proof
    verification. A forged caller claim (btcp_route_verified=true on a
    zk_pending route) must be ignored — derived verdict wins."""
    r = client.post("/api/v1/btcp/orchestrate", json=_ORCH_MIN)
    assert r.status_code == 200
    route_id = r.get_json()["route_id"]
    assert route_id

    # attacker: claim the route is verified
    r = client.post("/api/v1/continuum/settlement",
                    json={"route_id": route_id,
                          "btcp_route_verified": True})
    assert r.status_code == 200
    j = r.get_json()
    # the freshly created BASIC route has a deferred iap_share proof →
    # derived verdict is False and the caller's True claim is ignored
    assert j["btcp_route_verified_provenance"] == \
        "derived_from_persisted_route_proofs"
    assert j["btcp_route_verified"] is False
    assert j["caller_claim_ignored"]
    assert j["route_verification"]["route_id"] == route_id
    assert j["route_verification"]["proofs_all_valid"] is False
    assert j["triggered"] is False


def test_settlement_unknown_route_id_fails_closed(client):
    r = client.post("/api/v1/continuum/settlement",
                    json={"route_id": "route_does_not_exist"})
    assert r.status_code == 404
    assert "not found" in r.get_json()["error"]


# ── /api/v1/btcp/route — caller-supplied BIBL state is labeled ───────────────

_ROUTE_STATE = {
    "nl_scores": {1: 0.85, 137: 0.90, 8453: 0.88},
    "gas_forecasts": {1: 31.0, 137: 0.50, 8453: 0.98},
    "gas_reference": 31.0,
    "cc_coherence": {1: 0.90, 137: 0.92, 8453: 0.91},
    "mf_scores": {1: 0.02, 137: 0.01, 8453: 0.01},
    "finality_dist": {1: 12.0, 137: 2.0, 8453: 2.0},
    "beo_continuity": {1: 0.80, 137: 0.90, 8453: 0.85},
    "candidate_chains": [1, 137, 8453],
    "validator_counts": {1: 50, 137: 50, 8453: 50},
}


def test_btcp_route_labels_caller_supplied_state(client):
    r = client.post("/api/v1/btcp/route", json=_ROUTE_STATE)
    assert r.status_code == 200
    j = r.get_json()
    assert j["route"] is not None
    prov = j.get("state_provenance")
    assert prov and prov["nl_scores"] == "caller_supplied"
    assert "caller-supplied" in prov["note"]


# ── Sanctions upsert — fail-closed without credentials ──────────────────────

def test_sanctions_upsert_refuses_unauthenticated_mutation(client, monkeypatch):
    """No TRION_ADMIN_TOKEN and no TRION_API_KEY → the write path must
    refuse (503), never let an anonymous caller delist a sanctioned address."""
    monkeypatch.delenv("TRION_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("TRION_API_KEY", raising=False)
    r = client.post("/api/v1/btcp/sanctions",
                    json={"address": "0x" + "ab" * 20, "remove": True})
    assert r.status_code == 503
    assert "disabled" in r.get_json()["error"]


def test_sanctions_upsert_admin_token_enforced(client, monkeypatch):
    monkeypatch.delenv("TRION_API_KEY", raising=False)
    monkeypatch.setenv("TRION_ADMIN_TOKEN", "w3m-admin-secret")
    addr = "0x" + "cd" * 20
    # wrong / missing bearer → 401
    r = client.post("/api/v1/btcp/sanctions", json={"address": addr})
    assert r.status_code == 401
    r = client.post("/api/v1/btcp/sanctions", json={"address": addr},
                    headers={"Authorization": "Bearer wrong-token"})
    assert r.status_code == 401
    # correct bearer → the feed verifier path works
    r = client.post("/api/v1/btcp/sanctions", json={"address": addr},
                    headers={"Authorization": "Bearer w3m-admin-secret"})
    assert r.status_code == 200
    assert r.get_json()["added"] is True


# ── app.py routes (full app) ────────────────────────────────────────────────

def test_api_key_middleware_gates_writes(full_app_client, monkeypatch):
    """TRION_API_KEY (env var documented in .env.example since 3388ff3) must
    be ENFORCED: writes need X-API-Key, reads stay public."""
    import api.app as api_app
    monkeypatch.setattr(api_app, "_TRION_API_KEY", "w3m-test-key")

    # write without a key → 401
    r = full_app_client.post("/api/v1/btcp/orchestrate", json=_ORCH_MIN)
    assert r.status_code == 401
    assert "X-API-Key" in r.get_json()["message"]
    # write with a wrong key → 403
    r = full_app_client.post("/api/v1/btcp/orchestrate", json=_ORCH_MIN,
                             headers={"X-API-Key": "wrong"})
    assert r.status_code == 403
    # write with the right key → passes the auth layer
    r = full_app_client.post("/api/v1/btcp/orchestrate", json=_ORCH_MIN,
                             headers={"X-API-Key": "w3m-test-key"})
    assert r.status_code == 200
    # reads are always public (oracle data is world-readable by design)
    r = full_app_client.get("/api/v1/btcp/version")
    assert r.status_code == 200


def test_gratitude_disclosure_is_not_auto_verified(full_app_client):
    """A public self-report must be recorded UNVERIFIED with zero credit —
    the old route hardcoded verified=True, minting gratitude credit."""
    r = full_app_client.post("/api/v1/governance/gratitude", json={
        "entity_id": "0x" + "11" * 20,
        "vulnerability_id": "VULN-W3M-001",
        "severity": "CRITICAL",
        "description": "self-reported claim",
    })
    assert r.status_code == 200
    j = r.get_json()
    assert j["verified"] is False
    assert j["credit"] == 0.0
    assert "UNVERIFIED" in j["verification_note"]

    # invalid severity is rejected (was silently accepted, multiplier 1.0)
    r = full_app_client.post("/api/v1/governance/gratitude", json={
        "entity_id": "0x" + "11" * 20,
        "vulnerability_id": "VULN-W3M-002",
        "severity": "CATASTROPHIC",
    })
    assert r.status_code == 400


def test_kv_put_signal_does_not_fabricate_persistence(full_app_client):
    """The demo KV write must not claim immutable/da_submitted truth —
    provenance and synthetic labels are mandatory."""
    r = full_app_client.post("/api/v1/kv/signal/0x" + "11" * 20,
                             json={"phi": 1.0, "theta": 0.1})
    assert r.status_code == 201
    j = r.get_json()
    assert j["is_synthetic"] is True
    assert j["data_provenance"] == "caller_supplied"
    assert j["log_layer"]["da_submitted"] is False
    assert j["log_layer"]["immutable"] is False
    assert j["kv_layer"]["persisted"] is False
    # the verdict is a local comparison of caller-supplied numbers
    assert j["signal"]["verdict"] == "ALLOWED"


def test_slashing_filing_is_evidence_only(full_app_client):
    """Accusation filing: no default 'protocol_monitor' impersonation,
    positive stake required, and the caller-declared quorum base labeled."""
    r = full_app_client.post("/api/v1/governance/slashing/file", json={
        "accused_id": "validator_7",
        "condition": "S1_DOUBLE_SIGNING",
    })
    assert r.status_code == 400   # accuser_id required — no silent default

    r = full_app_client.post("/api/v1/governance/slashing/file", json={
        "accused_id": "validator_7",
        "accuser_id": "0x" + "33" * 20,
        "condition": "S1_DOUBLE_SIGNING",
        "total_eligible_stake": 0.0001,   # tiny quorum base from a caller
    })
    assert r.status_code == 200
    j = r.get_json()
    assert j["evidence_only"] is True
    assert j["provenance"]["total_eligible_stake"] == \
        "caller_declared_unverified"
    assert "validator registry" in j["provenance"]["note"]

    # non-positive / non-numeric stake rejected
    r = full_app_client.post("/api/v1/governance/slashing/file", json={
        "accused_id": "validator_7",
        "accuser_id": "0x" + "33" * 20,
        "total_eligible_stake": -5,
    })
    assert r.status_code == 400


def test_reputation_observe_labels_caller_attestation(full_app_client):
    """Caller-supplied coherence/manipulation numbers must be labeled
    caller_self_attested — an observation is evidence, not measurement."""
    r = full_app_client.post("/api/v1/reputation/observe", json={
        "entity_id": "0x" + "44" * 20,
        "coherence": 1.0,          # self-attested perfect coherence
        "manipulation_score": 0.0,
    })
    assert r.status_code == 200
    j = r.get_json()
    assert j["witness_source"] == "caller_self_attested"
    assert "not a TRION-verified measurement" in j["witness_note"]
    # non-numeric coherence is rejected
    r = full_app_client.post("/api/v1/reputation/observe", json={
        "entity_id": "0x" + "44" * 20, "coherence": "very-high",
    })
    assert r.status_code == 400


def test_reputation_endorse_requires_and_labels_endorser(full_app_client):
    """The endorsement route no longer defaults to 'anonymous' and labels
    the endorser as unauthenticated (no validator signature is checked)."""
    entity = "0x" + "55" * 20
    # create the entity first via the server-side path
    full_app_client.get(f"/api/v1/reputation/{entity}")
    r = full_app_client.post(f"/api/v1/reputation/{entity}/endorse", json={})
    assert r.status_code == 400   # endorser_id required

    r = full_app_client.post(
        f"/api/v1/reputation/{entity}/endorse",
        json={"endorser_id": "validator_i_promise"})
    assert r.status_code == 200
    j = r.get_json()
    if "error" not in j:
        assert j["endorser_provenance"] == "unauthenticated_caller"
        assert "unverified claim" in j["endorser_note"]


def test_cex_webhook_register_blocks_private_targets(full_app_client):
    """SSRF guard: the server-side alert pusher must not be aimed at
    loopback/private ranges through an unauthenticated registration."""
    for url in ("http://127.0.0.1:8080/alerts",
                "http://localhost/alerts",
                "http://10.0.0.5/alerts",
                "http://192.168.1.10/alerts",
                "http://169.254.169.254/latest/meta-data"):
        r = full_app_client.post("/api/v1/cex/webhook/register",
                                 json={"url": url, "cex_name": "BINANCE"})
        assert r.status_code == 400, url
        assert "private" in r.get_json()["reason"]
    # a public HTTPS endpoint registers fine
    r = full_app_client.post("/api/v1/cex/webhook/register",
                             json={"url": "https://compliance.example.com/x",
                                   "cex_name": "BINANCE"})
    assert r.status_code == 200


# ── Price feed provenance ────────────────────────────────────────────────────

@pytest.fixture()
def price_client():
    """Flask test client with only the price_feed blueprint mounted."""
    from api.price_feed_routes import price_feed_bp, _pairs, _lock
    with _lock:
        _pairs.clear()
    # re-seed the bootstrap pairs for deterministic assertions
    import importlib
    import api.price_feed_routes as pfr
    importlib.reload(pfr)
    app = flask.Flask(__name__)
    app.register_blueprint(pfr.price_feed_bp)
    return app.test_client()


def test_price_feed_bootstrap_pairs_labeled_synthetic(price_client):
    r = price_client.get("/api/v1/price/ETH/USD")
    assert r.status_code == 200
    j = r.get_json()
    assert j["behavioral"]["data_provenance"] == "bootstrap_demo"
    assert j["behavioral"]["is_synthetic"] is True
    assert j["is_synthetic"] is True
    assert "bootstrap_demo" in j["synthetic_reason"]
    # the pairs listing surfaces provenance too
    r = price_client.get("/api/v1/price/pairs")
    pairs = r.get_json()["pairs"]
    eth = next(p for p in pairs if p["pair"] == "ETH/USD")
    assert eth["data_provenance"] == "bootstrap_demo"
    assert eth["is_synthetic"] is True


def test_price_seed_labels_relayer_submission(price_client):
    """A pushed observation is recorded with relayer_submitted provenance —
    never presented as TRION-verified behavioral consensus."""
    r = price_client.post("/api/v1/price/seed", json={
        "base": "DOGE", "quote": "USD", "price": 0.12,
        "coherence": 1.0, "confidence": 1.0,   # self-attested perfection
    })
    assert r.status_code == 200
    j = r.get_json()
    assert j["data_provenance"] == "relayer_submitted"
    assert "not TRION-verified" in j["witness_note"]

    r = price_client.get("/api/v1/price/DOGE/USD")
    assert r.status_code == 200
    j = r.get_json()
    assert j["behavioral"]["data_provenance"] == "relayer_submitted"
    assert j["behavioral"]["is_synthetic"] is False
    assert j["behavioral"]["coherence"] == 1.0  # surfaced, but labeled


# ── Relayer static assertions ───────────────────────────────────────────────

RELAYER_JS = os.path.join(ROOT, "relayer", "relayer.js")
RELAYER_NON_EVM_JS = os.path.join(ROOT, "relayer", "relayer_non_evm.js")
KMS_JS = os.path.join(ROOT, "relayer", "kms_provider.js")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_relayer_sources_parse_as_es_modules():
    for path in (RELAYER_JS, RELAYER_NON_EVM_JS, KMS_JS):
        proc = subprocess.run(
            ["node", "--input-type=module", "--check"],
            stdin=open(path, "rb"), capture_output=True, text=True)
        assert proc.returncode == 0, f"{path}: {proc.stderr}"


def test_relayer_fail_closed_signal_validation_present():
    """The relayer must never fabricate signal values: validateSignal is
    defined and enforced on every publish path (tick, pushToChain,
    pushToZGGate, packSignal) — no '?? 0.5' / '?? 0.55' defaults remain."""
    src = _read(RELAYER_JS)
    assert "function validateSignal(signal)" in src
    for marker in (
        "const verr = validateSignal(signal);",          # tick + chain push
        "const err = validateSignal(signal);",           # packSignal/gate
    ):
        assert src.count(marker) >= 2, marker
    # the old defaulting patterns are gone from the active paths
    assert "signal_value ?? 0.5" not in src
    assert "signal.threshold ?? 0.55" not in src
    assert "signal.coherence || 0.5" not in src
    assert "signal.threshold || 0.55" not in src


def test_relayer_docstring_is_honest_about_single_signature():
    """The header must not claim a multi-sig collection mechanism that does
    not exist (SIGNER_KEYS_JSON was documented but never implemented)."""
    src = _read(RELAYER_JS)
    assert "collect signatures from peers via SIGNER_KEYS_JSON" not in src
    assert "submits exactly ONE signature" in src
    assert "NOT implemented" in src
    # preflight warns when the signer is unregistered or quorum > 1
    assert "preflightChainAccess" in src
    assert "NOT a registered validator" in src


def test_relayer_commitments_are_labeled_as_commitments():
    """beoHash / daProofHash are transport commitments, not proofs — the
    source must say so at the definition site."""
    src = _read(RELAYER_JS)
    assert "TRANSPORT COMMITMENT" in src
    assert "this is NOT a \"proof\"" in src


def test_relayer_non_evm_keeps_fail_closed_self_halt():
    """relayer_non_evm.js: REL-1 (fail-closed self-halt) and REL-2 (synthetic
    provenance labels) must stay landed."""
    src = _read(RELAYER_NON_EVM_JS)
    assert "HALTING this cycle (fail-closed)" in src
    assert "SYNTHETIC_BLOCK_PROOF" in src


def test_kms_provider_documents_key_boundary():
    """kms_provider.js: env var is documented dev-only; HSM/KMS boundary
    claims must be explicit; the dev provider must warn."""
    src = _read(KMS_JS)
    assert "Plaintext env var (RELAYER_PRIVATE_KEY) — for development only" in src
    assert "private key never leaves the" in src
    assert "development mode" in src


# ── SDK static assertions ───────────────────────────────────────────────────

SDK_TS = os.path.join(ROOT, "sdk", "TrionSDK.ts")
SDK_README = os.path.join(ROOT, "sdk", "README.md")


def test_sdk_cannot_sign_or_verify_signatures():
    """No client-side signing surface and no signature verification: the SDK
    must be structurally incapable of manufacturing attestation truth."""
    sdk_files = [SDK_TS] + [
        os.path.join(ROOT, "sdk", "src", f)
        for f in ("index.ts", "trion.ts", "trion-sdk.ts", "client.ts")
    ]
    pattern = re.compile(
        r"privateKey|signMessage|signDigest|\.sign\(|wallet\.sign|"
        r"quorumMet|threshold_met|quorum_met|verifySignature")
    for path in sdk_files:
        if not os.path.exists(path):
            continue
        src = _read(path)
        matches = pattern.findall(src)
        assert not matches, f"{path} contains signing/quorum-truth surface: {matches}"


def test_sdk_sanctions_helper_is_fail_closed():
    """checkSanctions must keep the fail-closed contract: unreachable oracle
    ⇒ sanctioned=true + SCREENING_UNAVAILABLE + confidence 0."""
    src = _read(SDK_TS)
    assert "SCREENING_UNAVAILABLE" in src
    assert "Fail-closed" in src or "fail-closed" in src


def test_sdk_readme_documents_trust_model():
    assert os.path.exists(SDK_README)
    src = _read(SDK_README)
    for section in (
        "What this SDK does",
        "What this SDK deliberately does NOT do",
        "No signing",
        "No signature verification",
        "No quorum/threshold truth",
    ):
        assert section in src, section
    # the WASM "verify" function is called out as formula-checking only
    assert "verifyCoherenceWasm" in src
    assert "not an oracle attestation" in src


def test_sdk_packing_docs_state_the_quorum_gate():
    src = _read(SDK_TS)
    assert "pure serialization" in src
    assert "quorum of registered-validator signatures" in src
