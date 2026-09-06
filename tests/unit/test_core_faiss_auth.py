"""core/-side FAISS client auth — the R-22 unkeyed-caller sweep pin.

faiss_service.py (SEC-01) requires X-API-Key on every non-public route, so
any core/ HTTP client that talks to the FAISS ANIMA service must resolve and
send the key with the service's own order:

    FAISS_API_KEY → FAISS_SERVICE_API_KEY → TRION_API_KEY

core/physical/transduction_integrity.py and core/realtime/bh_streamer.py
(the FAISSAccumulator) were keyed in earlier waves; this battery pins the
remaining five core/ callers found by the R-22 sweep:

  * core/akashic/genesis.py             — POST /archetypes/match_vector
  * core/price/behavioral_price_engine.py — GET /bh/stats
  * core/auditor/contract_auditor.py    — GET /api/v1/planes/{addr}/physical
  * core/trading/live_feed.py           — GET /api/v1/trading/signal/{id} (httpx)
  * core/trading/signal_engine.py       — GET /api/v1/signal/{id} (httpx)

Each helper stays LOCAL to its module (same rule as the two reference
resolvers): core/ must not import from the api/ package above it.

Run: pytest tests/unit/test_core_faiss_auth.py -q
"""
import asyncio

import pytest

import core.akashic.genesis as genesis
import core.auditor.contract_auditor as contract_auditor
import core.price.behavioral_price_engine as bpe
import core.trading.live_feed as live_feed
import core.trading.signal_engine as signal_engine

_KEY_VARS = ("FAISS_API_KEY", "FAISS_SERVICE_API_KEY", "TRION_API_KEY")


@pytest.fixture(autouse=True)
def _clean_key_env(monkeypatch):
    for var in _KEY_VARS:
        monkeypatch.delenv(var, raising=False)


def _set_all_three(monkeypatch, direct="", service="", trion=""):
    monkeypatch.setenv("FAISS_API_KEY", direct)
    monkeypatch.setenv("FAISS_SERVICE_API_KEY", service)
    monkeypatch.setenv("TRION_API_KEY", trion)


class _FakeResponse:
    status_code = 200

    def json(self):
        return {"status": "ok", "archetypes": []}

    def raise_for_status(self):
        pass


class TestModuleLevelHeaderHelpers:
    """The requests-based callers: shared _faiss_headers() per module."""

    def test_resolution_order_follows_the_service(self, monkeypatch):
        _set_all_three(monkeypatch, "k-direct", "k-service", "k-trion")
        for mod in (genesis, bpe, contract_auditor):
            assert mod._faiss_headers() == {"X-API-Key": "k-direct"}, mod.__name__
        monkeypatch.delenv("FAISS_API_KEY")
        for mod in (genesis, bpe, contract_auditor):
            assert mod._faiss_headers() == {"X-API-Key": "k-service"}, mod.__name__
        monkeypatch.delenv("FAISS_SERVICE_API_KEY")
        for mod in (genesis, bpe, contract_auditor):
            assert mod._faiss_headers() == {"X-API-Key": "k-trion"}, mod.__name__

    def test_blank_or_unset_resolves_to_no_header(self):
        for mod in (genesis, bpe, contract_auditor):
            assert mod._faiss_headers() == {}, mod.__name__


class TestRequestsCallsCarryKey:

    @pytest.fixture()
    def calls(self, monkeypatch):
        import requests
        seen = []
        monkeypatch.setattr(
            requests, "post",
            lambda url, json=None, timeout=2.0, headers=None:
                seen.append(("POST", url, headers)) or _FakeResponse())
        monkeypatch.setattr(
            requests, "get",
            lambda url, timeout=3.0, headers=None:
                seen.append(("GET", url, headers)) or _FakeResponse())
        return seen

    def test_genesis_archetype_match_post_is_keyed(self, calls, monkeypatch):
        """query_faiss_archetype_similarities POSTs to the FAISS service."""
        import numpy as np
        monkeypatch.setenv("FAISS_API_KEY", "genesis-key")
        out = genesis.query_faiss_archetype_similarities(np.zeros(4, dtype=float))
        assert out == []
        method, url, headers = calls[0]
        assert method == "POST"
        assert url.endswith("/archetypes/match_vector")
        assert headers == {"X-API-Key": "genesis-key"}

    def test_bh_stats_get_is_keyed(self, calls, monkeypatch):
        """_fetch_bh_stats pulls the global ledger stats from FAISS."""
        monkeypatch.setenv("FAISS_API_KEY", "btv-key")
        with bpe._bh_stats_lock:
            bpe._bh_stats_cache.clear()
        bpe._fetch_bh_stats()
        method, url, headers = calls[0]
        assert method == "GET"
        assert url.endswith("/bh/stats")
        assert headers == {"X-API-Key": "btv-key"}

    def test_auditor_epigenetic_drift_get_is_keyed(self, calls, monkeypatch):
        """ContractAuditor._compute_epigenetic_drift reads the FAISS baseline."""
        import numpy as np
        monkeypatch.setenv("FAISS_API_KEY", "auditor-key")
        auditor = contract_auditor.ContractAuditor(faiss_url="http://faiss:8000")
        drift = auditor._compute_epigenetic_drift(
            np.zeros(9, dtype=np.float32), "0xdeadbeef", 1)
        assert drift == 0.0  # 9-dim baseline absent in the stub — fallback path
        method, url, headers = calls[0]
        assert method == "GET"
        assert "/api/v1/planes/0xdeadbeef/physical" in url
        assert headers == {"X-API-Key": "auditor-key"}

    def test_unkeyed_modules_send_no_header(self, calls):
        import numpy as np
        with bpe._bh_stats_lock:
            bpe._bh_stats_cache.clear()
        bpe._fetch_bh_stats()
        method, url, headers = calls[0]
        assert (method, url) == ("GET", f"{bpe.FAISS_API_URL}/bh/stats")
        assert headers in (None, {})


class _FakeAsyncClient:
    """httpx.AsyncClient stand-in capturing client.get() calls."""
    seen = []

    def __init__(self, timeout=None):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, headers=None):
        _FakeAsyncClient.seen.append((url, headers))

        class _R:
            status_code = 200

            def json(self):
                return {"signal": "NEUTRAL", "confidence": 0.5}
        return _R()


@pytest.fixture()
def fake_httpx(monkeypatch):
    _FakeAsyncClient.seen = []
    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)
    return _FakeAsyncClient


class TestHttpxCallsCarryKey:

    def test_live_feed_signal_get_is_keyed(self, fake_httpx, monkeypatch):
        monkeypatch.setenv("FAISS_API_KEY", "feed-key")
        feed = live_feed.TRIONSignalFeed(faiss_url="http://faiss:8000")
        asyncio.run(feed.fetch_signal("entity-11c"))
        url, headers = fake_httpx.seen[-1]
        assert url == "http://faiss:8000/api/v1/trading/signal/entity-11c"
        assert headers == {"X-API-Key": "feed-key"}

    def test_signal_engine_vector_get_is_keyed(self, fake_httpx, monkeypatch):
        monkeypatch.setenv("FAISS_SERVICE_API_KEY", "engine-key")
        engine = signal_engine.TradingSignalEngine(faiss_url="http://faiss:8000")
        asyncio.run(engine.fetch_entity_vector("entity-11c"))
        url, headers = fake_httpx.seen[-1]
        assert url == "http://faiss:8000/api/v1/signal/entity-11c"
        assert headers == {"X-API-Key": "engine-key"}

    def test_httpx_clients_resolve_the_key_once_at_construction(self, monkeypatch):
        """Same FAISSAccumulator pattern: key resolved in __init__."""
        _set_all_three(monkeypatch, "k-direct", "k-service", "k-trion")
        feed = live_feed.TRIONSignalFeed()
        assert feed._faiss_api_key == "k-direct"
        engine = signal_engine.TradingSignalEngine()
        assert engine._faiss_api_key == "k-direct"

        monkeypatch.setenv("FAISS_API_KEY", "")
        feed2 = live_feed.TRIONSignalFeed()
        assert feed2._faiss_api_key == "k-service"

    def test_unkeyed_httpx_clients_send_empty_headers(self, fake_httpx):
        feed = live_feed.TRIONSignalFeed(faiss_url="http://faiss:8000")
        engine = signal_engine.TradingSignalEngine(faiss_url="http://faiss:8000")
        assert feed._faiss_headers() == {}
        assert engine._faiss_headers() == {}
        asyncio.run(feed.fetch_signal("entity-11c"))
        url, headers = fake_httpx.seen[-1]
        assert headers == {}
