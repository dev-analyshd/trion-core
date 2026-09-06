"""SEC-03 / SEC-14 regression battery — fail-closed write default + CORS.

The out-of-the-box posture of the Flask oracle API (TRION_API_KEY unset)
must not be a fully open API:

  * GET/HEAD/OPTIONS reads stay public — oracle data is world-readable
    by design and the public dashboard/terminal consume read endpoints.
  * POST/PUT/PATCH/DELETE are REFUSED with 503 auth_not_configured.
    Before the fix every one of the 181 routes answered unauthenticated
    writes (reputation poisoning, engine-state mutation, on-chain
    publication relays) whenever the operator had not set a key.
  * The method-agnostic write-path set (_WRITE_PATHS — publish/, zg/da/
    submit, zg/storage/store, zg/sync, zg/compute/infer) is refused on
    EVERY method, GET included: those routes are writes regardless of
    verb (P-API-02), and /api/v1/publish/<id> answers GET.
  * /api/v1/health stays exempt on every method (monitoring probes use
    POST health checks) and on the read verbs.

With TRION_API_KEY SET the behavior is pinned as unchanged: 401 with the
X-API-Key hint when the header is missing, 403 on a wrong key
(compare_digest), 200 with the correct key, reads always public.

CORS (SEC-14): no Access-Control-Allow-Origin header is emitted by
default (same-origin only); TRION_CORS_ORIGINS entries are echoed
exactly and unlisted origins receive nothing (no wildcard fallback).

Run: pytest tests/unit/test_api_auth_failclosed.py -q
"""
import os

os.environ.setdefault("TRION_STREAMER_INPROCESS", "0")

import pytest  # noqa: E402 — env must be set before the api.app import

import api.app as api_app  # noqa: E402 — import side effects match sibling tests
from api.app import app  # noqa: E402

KEY = "sec03-regression-key"

# A plain (non-_WRITE_PATHS) POST endpoint: isolates the method-based
# fail-closed rule from the method-agnostic write-path rule.
_OBSERVE_OK = {"entity_id": "0x" + "44" * 20, "coherence": 1.0}


@pytest.fixture(autouse=True)
def _fresh_rate_limit():
    """Start every request from a clean rate-limit slate."""
    with api_app._rl_lock:
        api_app._rl_buckets.clear()


@pytest.fixture()
def client():
    return app.test_client()


# ── TRION_API_KEY unset: reads public, writes refused (SEC-03) ────────────────

class TestUnsetKeyFailClosed:

    @pytest.fixture(autouse=True)
    def _no_key(self, monkeypatch):
        monkeypatch.setattr(api_app, "_TRION_API_KEY", "")

    def test_post_without_configured_key_refused_503(self, client):
        r = client.post("/api/v1/reputation/observe", json=_OBSERVE_OK)
        assert r.status_code == 503, (
            "unconfigured deployment must refuse unauthenticated writes")
        j = r.get_json()
        assert j["error"] == "auth_not_configured"
        assert "TRION_API_KEY" in j["message"]

    def test_put_patch_delete_refused_503(self, client):
        for method in ("put", "patch", "delete"):
            r = client.open("/api/v1/reputation/observe", method=method.upper(),
                            json=_OBSERVE_OK)
            assert r.status_code == 503, (method, r.status_code)

    def test_write_path_refused_on_every_method(self, client):
        """P-API-02 applied to the unconfigured case: publish/ answers GET,
        zg/sync spawns a subprocess — verb is not proof of a read."""
        cases = [
            ("POST", "/api/v1/publish/sec03-regression-entity"),
            ("GET", "/api/v1/publish/sec03-regression-entity"),
            ("GET", "/api/v1/zg/sync"),
            ("POST", "/api/v1/zg/storage/store"),
        ]
        for method, path in cases:
            r = client.open(path, method=method, json={})
            assert r.status_code == 503, (method, path, r.status_code)

    def test_get_reads_stay_public(self, client):
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/api/v1/signal/batch?ids=a").status_code == 200

    def test_health_post_probe_stays_exempt(self, client):
        """Monitoring tools POST their health checks — the auth layer must
        be transparent for /api/v1/health on every method (the route itself
        may still answer 405 for non-GET verbs)."""
        r = client.post("/api/v1/health")
        assert r.status_code in (200, 405), r.status_code
        j = r.get_json(silent=True) or {}
        assert j.get("error") != "auth_not_configured"


# ── TRION_API_KEY set: matrix unchanged (SEC-03 fix must not regress it) ─────

class TestKeyedBehaviorUnchanged:

    @pytest.fixture(autouse=True)
    def _keyed(self, monkeypatch):
        monkeypatch.setattr(api_app, "_TRION_API_KEY", KEY)

    def test_missing_key_401_with_hint(self, client):
        r = client.post("/api/v1/reputation/observe", json=_OBSERVE_OK)
        assert r.status_code == 401
        assert "X-API-Key" in r.get_json()["message"]

    def test_wrong_key_403(self, client):
        r = client.post("/api/v1/reputation/observe", json=_OBSERVE_OK,
                        headers={"X-API-Key": "wrong"})
        assert r.status_code == 403

    def test_correct_key_passes_the_gate(self, client):
        r = client.post("/api/v1/reputation/observe", json=_OBSERVE_OK,
                        headers={"X-API-Key": KEY})
        assert r.status_code == 200
        assert r.get_json()["witness_source"] == "caller_self_attested"

    def test_reads_public_with_key_set(self, client):
        assert client.get("/api/v1/health").status_code == 200

    def test_health_post_probe_exempt_with_key_set(self, client):
        r = client.post("/api/v1/health")
        assert r.status_code in (200, 405), r.status_code
        assert "X-API-Key" not in (r.get_json(silent=True) or {}).get("message", "")


# ── CORS (SEC-14): opt-in origins, no wildcard default ───────────────────────

class TestCorsOrigins:

    def test_no_access_control_header_by_default(self, client, monkeypatch):
        monkeypatch.setattr(api_app, "_TRION_API_KEY", "")
        monkeypatch.setattr(api_app, "_CORS_ORIGINS", [])
        r = client.get("/api/v1/health",
                       headers={"Origin": "http://attacker.example"})
        assert "Access-Control-Allow-Origin" not in r.headers

    def test_configured_origin_is_echoed_exactly(self, client, monkeypatch):
        monkeypatch.setattr(api_app, "_CORS_ORIGINS",
                            ["http://localhost:3000", "https://dashboard.trion.io"])
        r = client.get("/api/v1/health",
                       headers={"Origin": "https://dashboard.trion.io"})
        assert r.headers.get("Access-Control-Allow-Origin") == \
            "https://dashboard.trion.io"

    def test_unlisted_origin_gets_no_header(self, client, monkeypatch):
        monkeypatch.setattr(api_app, "_CORS_ORIGINS", ["http://localhost:3000"])
        r = client.get("/api/v1/health",
                       headers={"Origin": "http://attacker.example"})
        assert "Access-Control-Allow-Origin" not in r.headers

    def test_no_origin_header_no_cors_headers(self, client, monkeypatch):
        monkeypatch.setattr(api_app, "_CORS_ORIGINS", ["http://localhost:3000"])
        r = client.get("/api/v1/health")
        assert "Access-Control-Allow-Origin" not in r.headers
