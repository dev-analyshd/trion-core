"""Self-verification monitor auth + env resolution (SEC-01 companion).

The reflexive self-verification monitor (core/physical/transduction_integrity.py,
exposed by api/self_verification_routes.py) talks to the FAISS ANIMA service:

  * its GETs (/api/v1/transduction_integrity, /fitness) and the
    /fitness/update POST must carry X-API-Key — since faiss_service.py
    enforces the key on every non-health route, unkeyed calls 401 and the
    monitor permanently degrades to the neutral 0.5 stubs.  The resolver
    must follow the service's own order
    (FAISS_API_KEY → FAISS_SERVICE_API_KEY → TRION_API_KEY) and must stay
    a LOCAL helper — core/ must not import from the api/ package above it.
  * the Oracle-side feed probe (/api/v1/feed) must NOT receive the FAISS
    key (same non-leak rule as api/dashboard_routes.py _proxy: a different
    TRION_API_KEY would 403 against the Oracle).
  * the blueprint's FAISS URL must resolve FAISS_SERVICE_URL first, then
    the FAISS_URL alias — it previously read only the alias, so a
    deployment setting FAISS_SERVICE_URL silently left the monitor on the
    default host.

Run: pytest tests/unit/test_self_verification_auth.py -q
"""
import importlib
import os

os.environ.setdefault("TRION_STREAMER_INPROCESS", "0")

import pytest  # noqa: E402 — env must be set before the api imports

import core.physical.transduction_integrity as ti  # noqa: E402

_KEY_VARS = ("FAISS_API_KEY", "FAISS_SERVICE_API_KEY", "TRION_API_KEY")


@pytest.fixture(autouse=True)
def _clean_key_env(monkeypatch):
    for var in _KEY_VARS:
        monkeypatch.delenv(var, raising=False)


class _FakeResponse:
    status_code = 200

    def json(self):
        return {"components": {"TRION_SELF": {"fitness": 0.9}}}


class TestFaissHeaderResolution:

    def test_no_key_configured_means_no_header(self):
        assert ti._faiss_headers() == {}

    def test_resolution_order_follows_the_service(self, monkeypatch):
        monkeypatch.setenv("TRION_API_KEY", "k-trion")
        monkeypatch.setenv("FAISS_SERVICE_API_KEY", "k-service")
        monkeypatch.setenv("FAISS_API_KEY", "k-direct")
        assert ti._faiss_headers() == {"X-API-Key": "k-direct"}

        monkeypatch.delenv("FAISS_API_KEY")
        assert ti._faiss_headers() == {"X-API-Key": "k-service"}

        monkeypatch.delenv("FAISS_SERVICE_API_KEY")
        assert ti._faiss_headers() == {"X-API-Key": "k-trion"}

    def test_blank_values_resolve_to_no_header(self, monkeypatch):
        monkeypatch.setenv("FAISS_API_KEY", "   ")
        assert ti._faiss_headers() == {}


class TestMonitorCallsCarryKey:

    @pytest.fixture()
    def calls(self, monkeypatch):
        """Stub requests at the module the helpers lazy-import."""
        import requests
        seen = []
        monkeypatch.setattr(requests, "get",
                            lambda url, timeout=3.0, headers=None:
                            seen.append(("GET", url, headers)) or _FakeResponse())
        monkeypatch.setattr(requests, "post",
                            lambda url, json=None, timeout=3.0, headers=None:
                            seen.append(("POST", url, headers)) or _FakeResponse())
        return seen

    def test_transduction_integrity_get_is_keyed(self, calls, monkeypatch):
        monkeypatch.setenv("FAISS_API_KEY", "monitor-key")
        ti._score_transduction_integrity("http://faiss:8000")
        method, url, headers = calls[0]
        assert method == "GET"
        assert url == "http://faiss:8000/api/v1/transduction_integrity"
        assert headers == {"X-API-Key": "monitor-key"}

    def test_fitness_get_is_keyed(self, calls, monkeypatch):
        monkeypatch.setenv("FAISS_API_KEY", "monitor-key")
        ti._score_component_fitness("http://faiss:8000")
        method, url, headers = calls[0]
        assert (method, url) == ("GET", "http://faiss:8000/fitness")
        assert headers == {"X-API-Key": "monitor-key"}

    def test_fitness_update_post_is_keyed(self, calls, monkeypatch):
        monkeypatch.setenv("FAISS_API_KEY", "monitor-key")
        ti._register_self_component_fitness(
            "http://faiss:8000", "TRION_SELF", 0.8, 0.6, 0.7, 1.0)
        method, url, headers = calls[0]
        assert (method, url) == ("POST", "http://faiss:8000/fitness/update")
        assert headers == {"X-API-Key": "monitor-key"}

    def test_oracle_feed_probe_never_leaks_the_faiss_key(self, calls, monkeypatch):
        """_score_feed_temporal_spacing hits the FLASK oracle, not FAISS."""
        monkeypatch.setenv("FAISS_API_KEY", "monitor-key")
        ti._score_feed_temporal_spacing("http://oracle:5000")
        method, url, headers = calls[0]
        assert (method, url) == ("GET", "http://oracle:5000/api/v1/feed")
        assert headers is None

    def test_unkeyed_service_keeps_the_neutral_fallback(self, monkeypatch):
        """No key configured → header-less GET; a 401 answer degrades to 0.5."""
        import requests
        seen = []

        class _Denied:
            status_code = 401

        monkeypatch.setattr(
            requests, "get",
            lambda url, timeout=3.0, headers=None:
                seen.append((url, headers)) or _Denied())
        score, detail = ti._score_transduction_integrity("http://faiss:8000")
        assert score == 0.5
        assert detail == {"available": False}
        assert seen[0][1] in (None, {})  # unkeyed: no X-API-Key rides the request


class TestBlueprintEnvResolution:

    def _reload_with(self, monkeypatch, **env):
        for var in ("FAISS_SERVICE_URL", "FAISS_URL"):
            monkeypatch.delenv(var, raising=False)
        for var, val in env.items():
            monkeypatch.setenv(var, val)
        import api.self_verification_routes as svr
        return importlib.reload(svr)

    def test_service_url_wins(self, monkeypatch):
        svr = self._reload_with(monkeypatch,
                                FAISS_SERVICE_URL="http://faiss:8000",
                                FAISS_URL="http://stale:8000")
        assert svr.FAISS_URL == "http://faiss:8000"

    def test_faiss_url_alias_still_honored(self, monkeypatch):
        svr = self._reload_with(monkeypatch, FAISS_URL="http://alias:8000")
        assert svr.FAISS_URL == "http://alias:8000"

    def test_default_matches_the_rest_of_api(self, monkeypatch):
        svr = self._reload_with(monkeypatch)
        assert svr.FAISS_URL == "http://127.0.0.1:8000"
