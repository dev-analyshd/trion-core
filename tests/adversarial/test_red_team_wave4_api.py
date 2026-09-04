"""
WAVE 4 — AGENT P RED-TEAM BATTERY, part 2 (API truth / auth / push / frontend)
==============================================================================

Flask-test-client + static-source attacks on the post-M2-hardened surfaces.
Every attack was RUN live before being pinned here.

CONFIRMED EXPLOITS (asserted as CURRENT behavior + TODO(Wave-5) — the fix
is the Wave 5 work order):

  P-API-01  Settlement-gate vacuity: POST /api/v1/btcp/orchestrate with
            malformed `iap_economics` (all 5 required keys present, one
            not int-coercible) makes PrivacyRouter.generate_proofs RAISE
            mid-batch; BTCPOchestrator.create_route catches it and
            persists the route with proofs = {} (status INTENT_CREATED).
            PrivacyRouter.verify_proofs({}) then returns the VACUOUS
            verdict (True, []) — an EMPTY proof set verifies as
            all-valid — so POST /api/v1/continuum/settlement with that
            route_id derives btcp_route_verified=True with provenance
            "derived_from_persisted_route_proofs" and the settlement
            trigger fires. The M2 "gate DERIVED from persisted proofs,
            fail-closed" discipline is defeated by the empty set.
            Root cause: core/btcp/orchestrator.py:618-661 (verify_proofs
            never requires a non-empty known-name proof set) +
            orchestrator.py:1093-1096 (proof-generation failure is
            swallowed into a persisted, still-verifiable route).
  P-API-02  GET-registered write routes escape the X-API-Key write gate:
            api/app.py:164-190 `_require_api_key` gates only
            non-GET/HEAD/OPTIONS methods, but /api/v1/publish/<id>
            (app.py:1165 — on-chain publication + feed push),
            /api/v1/zg/storage/store (2594), /api/v1/zg/da/submit (2628),
            /api/v1/zg/compute/infer (2658) and /api/v1/zg/sync (2496)
            are registered with methods including GET and perform writes.
            With TRION_API_KEY set, an UNAUTHENTICATED GET enters the
            full publication path (POST control → 401, GET attack → 200).

PINNED DEFENSES (attack attempted, BLOCKED — asserted so a regression
that reopens the hole fails CI):
  - a PUBLIC (privacy_level=0) route can never derive a True settlement
    gate: the UNCONDITIONAL iap_share zk_pending entry is load-bearing
    dead-code-hazard documentation for Agent Q (deleting the "always add
    IAP" branch would flip proof-less routes to verifiable)
  - verify_proofs ignores unknown-name proof entries (allowlist skip) —
    pinned with the vacuity root cause so Wave 5 fixes both
  - POST/PUT without a key → 401; wrong key → 403 (compare_digest);
    correct key passes; reads always public
  - the /api/v1/health auth exemption is EXACT-match only (path
    confusion / traversal variants do not bypass the write gate)
  - socket push (/feed namespace): NO client-emit relay handler exists —
    a connected client cannot forge 'signal'/'health' broadcasts
  - frontend: no dangerouslySetInnerHTML/innerHTML fed by API/feed data
    (the only two usages are a static theme script and a static JSON-LD
    block) — React escaping covers the feed payloads
  - relayer validateSignal (executed live via node on the actual source):
    NaN / Infinity / missing / out-of-range / string-typed coherence and
    threshold values are rejected fail-closed before any packing

Run: pytest tests/adversarial/test_red_team_wave4_api.py -q
"""
import json
import os
import re
import subprocess

import flask
import pytest

import api.btcp_continuum_routes as btcp_routes
from api.btcp_continuum_routes import btcp_bp

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── fixtures ─────────────────────────────────────────────────────────────────

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
    tests/unit/test_api_truth_boundaries.py). Rate-limit buckets cleared
    so middleware tests start from a clean slate.
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


# ════════════════════════════════════════════════════════════════════════════
# 1. SETTLEMENT-GATE VACUITY (P-API-01) + root-cause pins
# ════════════════════════════════════════════════════════════════════════════

def test_settlement_gate_forced_true_by_proof_generation_failure(client):
    """P-API-01 CONFIRMED: a route whose proof generation FAILED (proofs={})
    is persisted and then derives btcp_route_verified=True from the
    VACUOUS verify_proofs({}) == (True, []) verdict — the settlement
    trigger fires on caller-manufactured "proofs".
    TODO(Wave-5): (a) verify_proofs must fail closed on an empty/unknown-
    only proof set; (b) create_route must not leave a proof-generation
    failure as a verifiable route (or verify_route_proofs must treat
    INTENT_CREATED-with-no-proofs as unverified)."""
    # ATTACK STEP 1 — persist a route with ZERO proofs (all 5 iap keys
    # present so the batch looks complete, one not int-coercible → the
    # proof loop raises mid-batch → swallowed → proofs = {})
    r = client.post("/api/v1/btcp/orchestrate", json={
        **_ORCH_MIN,
        "privacy_level": "BASIC",
        "iap_economics": {"total_gas": "EVIL:not-an-int", "entity_gas": 1,
                          "total_btcp_fee_wei": 1, "entity_share_wei": 1,
                          "num_participants": 1},
    })
    assert r.status_code == 200
    body = r.get_json()
    route_id = body["route"]["route_id"]
    assert len(body["route"]["proofs"]) == 0  # the attack surface

    # ATTACK STEP 2 — derive the settlement gate from the proof-less route
    r2 = client.post("/api/v1/continuum/settlement", json={
        "route_id": route_id,
        "btcp_route_verified": False,        # caller claim must be IGNORED
        "coherence_a": 0.9, "threshold_a": 0.55,
        "coherence_b": 0.9, "threshold_b": 0.55,
    })
    assert r2.status_code == 200
    b2 = r2.get_json()
    # CURRENT (broken) behavior: the gate is derived True from an EMPTY
    # proof set with a "derived from persisted route proofs" provenance.
    assert b2["btcp_route_verified"] is True
    assert b2["btcp_route_verified_provenance"] == "derived_from_persisted_route_proofs"
    assert b2["route_verification"]["proofs_all_valid"] is True
    assert b2["route_verification"]["verify_errors"] == []
    assert b2["triggered"] is True


def test_verify_proofs_empty_set_is_vacuously_true_root_cause():
    """Root cause pin for P-API-01: PrivacyRouter.verify_proofs({}) returns
    (True, []) — an empty proof set is vacuously all-valid. Asserted as
    CURRENT behavior so the Wave 5 fix (fail closed on empty/unknown-only)
    flips this test and forces the exploit test above to be updated."""
    from core.btcp.orchestrator import PrivacyRouter
    ok, errors = PrivacyRouter().verify_proofs({})
    assert ok is True and errors == []


def test_verify_proofs_unknown_names_are_skipped():
    """Root cause pin 2: unknown-name proof entries are silently skipped
    (the `continue` allowlist) — {"bogus": {...}} also verifies vacuously.
    Pinned so Wave 5 closes both halves of the vacuity."""
    from core.btcp.orchestrator import PrivacyRouter
    ok, errors = PrivacyRouter().verify_proofs({"bogus_circuit": {"junk": 1}})
    assert ok is True and errors == []


def test_public_route_cannot_derive_true_gate(client):
    """PINNED DEFENSE (and dead-code hazard warning for Agent Q): a
    privacy_level=PUBLIC route still cannot derive a True settlement
    gate — the UNCONDITIONAL iap_share zk_pending entry (generate_proofs
    runs the IAP branch at every privacy level) keeps verify_proofs
    fail-closed. That branch is load-bearing: removing it as 'dead code'
    would flip proof-less routes to vacuously verified (P-API-01)."""
    r = client.post("/api/v1/btcp/orchestrate", json={
        **_ORCH_MIN, "privacy_level": "PUBLIC"})
    assert r.status_code == 200
    route_id = r.get_json()["route"]["route_id"]
    r2 = client.post("/api/v1/continuum/settlement", json={
        "route_id": route_id,
        "coherence_a": 0.9, "threshold_a": 0.55,
        "coherence_b": 0.9, "threshold_b": 0.55})
    b2 = r2.get_json()
    assert b2["btcp_route_verified"] is False
    assert b2["route_verification"]["proofs_all_valid"] is False
    assert any("iap" in e for e in b2["route_verification"]["verify_errors"])
    assert b2["triggered"] is False


def test_fully_proven_route_derives_gate_and_labels_caller_economics(client):
    """Control for P-API-01: the intended verified path — full iap
    economics + BASIC privacy — still derives True, and the caller-owned
    batch economics stay labeled. (The exploit is the EMPTY set, not the
    derivation mechanism itself.)"""
    r = client.post("/api/v1/btcp/orchestrate", json={
        **_ORCH_MIN,
        "privacy_level": "BASIC",
        "iap_economics": {"total_gas": 1_000_000, "entity_gas": 151_000,
                          "total_btcp_fee_wei": 10**16,
                          "entity_share_wei": 15 * 10**14,
                          "num_participants": 10},
    })
    assert r.status_code == 200
    body = r.get_json()
    route_id = body["route"]["route_id"]
    proofs = body["route"]["proofs"]
    assert "intent_commitment" in proofs and "iap_share" in proofs
    r2 = client.post("/api/v1/continuum/settlement", json={
        "route_id": route_id,
        "btcp_route_verified": False,
        "coherence_a": 0.9, "threshold_a": 0.55,
        "coherence_b": 0.9, "threshold_b": 0.55})
    b2 = r2.get_json()
    assert b2["btcp_route_verified"] is True
    assert b2["route_verification"]["proofs_all_valid"] is True


# ════════════════════════════════════════════════════════════════════════════
# 2. X-API-Key BYPASS ATTEMPTS (P-API-02)
# ════════════════════════════════════════════════════════════════════════════

def test_get_registered_write_routes_bypass_api_key(full_app_client, monkeypatch):
    """P-API-02 CONFIRMED: with TRION_API_KEY enforced, an UNAUTHENTICATED
    GET still enters the full write path of /api/v1/publish/<id> (chain
    publication + feed push) and /api/v1/zg/da/submit (external DA
    submission) — the middleware's method model assumes GET is
    side-effect-free. POST control → 401.
    TODO(Wave-5): drop GET from the write routes (or make the middleware
    path-aware for the known write paths on every method)."""
    import api.app as api_app
    monkeypatch.setattr(api_app, "_TRION_API_KEY", "w4p-redteam-key")

    # control: POST without a key is correctly rejected
    r = full_app_client.post("/api/v1/publish/some-entity-id")
    assert r.status_code == 401

    # ATTACK: GET without a key enters the publication path (not 401/403).
    # In this test env the relay is unconfigured, so the response honestly
    # reports 'chain relay not configured' — in production the relay IS
    # configured and this is an unauthenticated on-chain publication.
    r = full_app_client.get("/api/v1/publish/some-entity-id")
    assert r.status_code == 200
    body = r.get_json()
    assert "chain" in body            # the publication path ran

    # ATTACK: GET on a 0G write route — the module actually executes
    # (the response is the module's own result, not an auth rejection).
    r = full_app_client.get("/api/v1/zg/da/submit?id=trion-protocol")
    assert r.status_code == 200

    # ATTACK: GET on the storage-store write route
    r = full_app_client.get("/api/v1/zg/storage/store?id=trion-protocol")
    assert r.status_code == 200


def test_write_method_auth_matrix(full_app_client, monkeypatch):
    """PINNED DEFENSE: the write gate itself is sound for non-GET verbs —
    missing key → 401 (with the X-API-Key hint), wrong key → 403,
    correct key passes, reads stay public."""
    import api.app as api_app
    monkeypatch.setattr(api_app, "_TRION_API_KEY", "w4p-redteam-key")

    r = full_app_client.post("/api/v1/btcp/orchestrate", json=_ORCH_MIN)
    assert r.status_code == 401
    assert "X-API-Key" in r.get_json()["message"]
    r = full_app_client.post("/api/v1/btcp/orchestrate", json=_ORCH_MIN,
                             headers={"X-API-Key": "wrong"})
    assert r.status_code == 403
    r = full_app_client.post("/api/v1/btcp/orchestrate", json=_ORCH_MIN,
                             headers={"X-API-Key": "w4p-redteam-key"})
    assert r.status_code == 200
    r = full_app_client.get("/api/v1/btcp/version")
    assert r.status_code == 200


def test_health_auth_exemption_is_exact_match(full_app_client, monkeypatch):
    """PINNED DEFENSE: the /api/v1/health auth exemption is an exact-path
    match — trailing-slash and path-confusion variants do not slip writes
    past the gate (Werkzeug normalization makes the traversal variants
    404/308 before any handler runs)."""
    import api.app as api_app
    monkeypatch.setattr(api_app, "_TRION_API_KEY", "w4p-redteam-key")

    for path in ("/api/v1/health/", "/api/v1/health/../publish/x",
                 "/api/v1/healthx", "//api/v1/health"):
        r = full_app_client.post(path)
        assert r.status_code in (401, 404, 308), (path, r.status_code)


def test_api_key_env_is_stripped_at_import():
    """Config-hygiene pin (Wave-5 note): TRION_API_KEY is .strip()ed at
    import — a whitespace-only deployment value silently DISABLES write
    auth (documented "absent = disabled" behavior extends to blank).
    Pinned as source so the behavior is a conscious decision, not drift."""
    src = open(os.path.join(ROOT, "api", "app.py")).read()
    assert 'os.environ.get("TRION_API_KEY", "").strip()' in src


# ════════════════════════════════════════════════════════════════════════════
# 3. SOCKET PUSH / FEED FORGERY
# ════════════════════════════════════════════════════════════════════════════

def test_socket_push_has_no_client_emit_relay_handlers():
    """PINNED DEFENSE: the /feed socket.io namespace registers ONLY
    connect/disconnect handlers — a malicious client can emit 'signal' or
    'health' all it wants; the server never relays a client emit to other
    clients (broadcasts come exclusively from the server-side pollers).
    A regression that adds @socketio.on("signal") would open client-side
    feed forgery (fake entity_id/coherence pushed to every dashboard)."""
    src = open(os.path.join(ROOT, "api", "socket_push.py")).read()
    handlers = re.findall(r'@socketio\.on\(\s*["\']([^"\']+)["\']', src)
    assert sorted(handlers) == ["connect", "disconnect"]
    # the only emits are server-side pushes
    assert "socketio.emit(" in src
    assert '@socketio.on("signal")' not in src


def test_socket_feed_key_is_not_authoritative():
    """PINNED DEFENSE (dedup design): the broadcaster's seen-set key is
    (entity_id, timestamp) — documented as the dedup unit. It is NOT an
    authenticity signal: two different signals with the same
    (entity_id, timestamp) dedup to one push. Pinned so nobody mistakes
    it for replay protection (the tx_hash is the ledger's replay key)."""
    src = open(os.path.join(ROOT, "api", "socket_push.py")).read()
    assert 'entry.get("entity_id", ""), int(entry.get("timestamp", 0))' in src


# ════════════════════════════════════════════════════════════════════════════
# 4. FRONTEND RENDERING (XSS via API/feed payloads)
# ════════════════════════════════════════════════════════════════════════════

def test_frontend_has_no_api_fed_inner_html():
    """PINNED DEFENSE: the Next.js frontend never injects API/feed data as
    raw HTML — the only dangerouslySetInnerHTML usages are a static theme
    bootstrap script and a static JSON-LD block (no request data); feed
    signals are stored in React state and rendered as escaped children."""
    hits = []
    for dirpath, _dirs, files in os.walk(os.path.join(ROOT, "frontend", "src")):
        for f in files:
            if not f.endswith((".tsx", ".ts")):
                continue
            src = open(os.path.join(dirpath, f), encoding="utf-8").read()
            if "dangerouslySetInnerHTML" in src:
                hits.append(os.path.join(dirpath, f))
            assert "document.write" not in src
            assert "eval(" not in src
    assert hits, "expected the two known static usages"
    for h in hits:
        src = open(h, encoding="utf-8").read()
        # the two allowed forms: static theme script, static JSON-LD object
        assert "localStorage.getItem('trion-theme')" in src or "jsonLd" in src, h


# ════════════════════════════════════════════════════════════════════════════
# 5. RELAYER INPUT VALIDATION (live node execution of the real source)
# ════════════════════════════════════════════════════════════════════════════

_NODE_HARNESS = r"""
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");
const start = src.indexOf("function _num");
const end = src.indexOf("function signalFields");
const code = src.slice(start, end);
eval(code);
const cases = [
  [{coherence_score: 0.5, threshold: 0.55}, null],
  [{coherence: 0.5, threshold: 0.55}, null],
  [{signal_value: 0.5, threshold: 0.55}, null],
  [{coherence_score: NaN, threshold: 0.55}, "not a finite number"],
  [{coherence_score: Infinity, threshold: 0.55}, "not a finite number"],
  [{coherence_score: -Infinity, threshold: 0.55}, "not a finite number"],
  [{coherence_score: 1.5, threshold: 0.55}, "out of range"],
  [{coherence_score: -0.1, threshold: 0.55}, "out of range"],
  [{threshold: 0.55}, "missing"],
  [{coherence_score: 0.5}, "missing"],
  [{coherence_score: 0.5, threshold: 0}, "out of range"],
  [{coherence_score: 0.5, threshold: -1}, "out of range"],
  [{coherence_score: 0.5, threshold: 1.5}, "out of range"],
  [{coherence_score: 0.5, threshold: NaN}, "not a finite number"],
  [{coherence_score: "0.5", threshold: 0.55}, "not a finite number"],
  [{coherence_score: true, threshold: 0.55}, "not a finite number"],
  [null, "not an object"],
  ["nope", "not an object"],
];
const out = cases.map(([sig, _]) => [JSON.stringify(sig), validateSignal(sig)]);
console.log(JSON.stringify(out));
"""


def test_relayer_validate_signal_rejects_forged_values():
    """PINNED DEFENSE: the ACTUAL relayer source's validateSignal (executed
    live via node — no fabrication) rejects NaN/Infinity/out-of-range/
    missing/string-typed/boolean-typed coherence and threshold values,
    and non-object responses, before anything is packed or signed."""
    node = shutil_which("node")
    if node is None:  # pragma: no cover — node present in this repo's env
        pytest.skip("node not available")
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(_NODE_HARNESS)
        harness = f.name
    try:
        proc = subprocess.run(
            [node, harness, os.path.join(ROOT, "relayer", "relayer.js")],
            capture_output=True, text=True, timeout=60)
    finally:
        os.unlink(harness)
    assert proc.returncode == 0, proc.stderr
    results = json.loads(proc.stdout)
    # valid field-name aliases pass
    for i in range(3):
        assert results[i][1] is None, results[i]
    # every forged value is rejected
    for sig, err in results[3:]:
        assert isinstance(err, str) and err != "", (sig, err)


def shutil_which(name):
    import shutil
    return shutil.which(name)
