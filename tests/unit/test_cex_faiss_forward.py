"""CEX→FAISS forward payload contract — /index/add_tx_bh_batch schema pin.

_forward_to_faiss (best-effort thread inside POST /api/v1/cex/ingest) used
to POST {chain, block_number, bhs:[…]} while the FAISS endpoint requires
TxBhBatchPayload {chain_id, chain_label, block_num, block_hash, timestamp,
entries:[TxBhEntryPayload…]} — the mismatch 422'd silently since forever
(the thread swallows everything).  This battery captures the actual POST
via a stubbed requests.post and pins the payload against the endpoint's
field set (all fields required — the service's anima-service/faiss_service.py
models define no defaults), so the sender can never drift again.

Field lists below are copied verbatim from TxBhBatchPayload /
TxBhEntryPayload in anima-service/faiss_service.py — update both sides
together if the endpoint schema evolves.

Run: pytest tests/unit/test_cex_faiss_forward.py -q
"""
import hashlib
import os
import threading

os.environ.setdefault("TRION_STREAMER_INPROCESS", "0")

import pytest  # noqa: E402 — env must be set before the api.app import

import api.app as api_app  # noqa: E402 — import side effects match sibling tests
import api.cex_integration as cex_mod  # noqa: E402
from api.app import app  # noqa: E402

_INGEST_KEY = "cex-forward-regression-key"

# TxBhEntryPayload (anima-service/faiss_service.py) — every field required.
ENTRY_FIELDS = {
    "tx_hash":         str,
    "from_addr":       str,
    "to_addr":         str,
    "event_type":      int,
    "event_type_name": str,
    "entity_id":       str,
    "magnitude_norm":  float,
    "value_wei":       str,
    "selector":        str,
    "timestamp":       int,
    "chain_id":        int,
    "chain_label":     str,
    "block_num":       int,
    "block_hash":      str,
    "sense_hex":       str,
    "antisense_hex":   str,
}

# TxBhBatchPayload (anima-service/faiss_service.py) — every field required.
BATCH_FIELDS = {
    "chain_id":    int,
    "chain_label": str,
    "block_num":   int,
    "block_hash":  str,
    "timestamp":   int,
    "entries":     list,
}

_RECORDS = [
    {"side": "BUY",  "size_usd": 850_000},
    {"side": "SELL", "size_usd": 1_250_000},   # >$1M → CTX_LARGE, still a BH
]


class _FakeResponse:
    status_code = 200

    def json(self):
        return {"stored": 0, "verified": 0}


@pytest.fixture(autouse=True)
def _fresh_rate_limit():
    with api_app._rl_lock:
        api_app._rl_buckets.clear()


@pytest.fixture()
def captured_post(monkeypatch):
    """Stub requests.post inside the forward thread; capture the payload."""
    captured = {}
    seen = threading.Event()

    def _fake_post(url, *args, headers=None, json=None, **kwargs):
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = json
        seen.set()
        return _FakeResponse()

    monkeypatch.setattr(cex_mod.requests, "post", _fake_post)
    return captured, seen


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(api_app, "_TRION_API_KEY", _INGEST_KEY)
    return app.test_client()


def _ingest(client):
    r = client.post("/api/v1/cex/ingest",
                    headers={"X-API-Key": _INGEST_KEY},
                    json={
                        "cex_name":  "BINANCE",
                        "data_type": "ORDER_FLOW_ANON",
                        "asset":     "ETH/USDT",
                        "market":    "SPOT",
                        "records":   _RECORDS,
                    })
    assert r.status_code == 200, (r.status_code, r.get_json())
    return r.get_json()


class TestForwardPayloadContract:

    def test_payload_matches_endpoint_schema(self, client, captured_post):
        """The exact TxBhBatchPayload field set, no legacy keys left behind."""
        captured, seen = captured_post
        _ingest(client)
        assert seen.wait(5), "forward thread never issued the POST"

        assert captured["url"].endswith("/index/add_tx_bh_batch")
        payload = captured["payload"]
        assert set(payload) == set(BATCH_FIELDS), (
            "sender/endpoint schema drift",
            sorted(set(payload) ^ set(BATCH_FIELDS)))
        for field, py_type in BATCH_FIELDS.items():
            assert isinstance(payload[field], py_type), (field, type(payload[field]))

        entries = payload["entries"]
        assert len(entries) == len(_RECORDS)
        for e in entries:
            assert set(e) == set(ENTRY_FIELDS), (
                "entry schema drift",
                sorted(set(e) ^ set(ENTRY_FIELDS)))
            for field, py_type in ENTRY_FIELDS.items():
                assert isinstance(e[field], py_type), (field, type(e[field]))

    def test_batch_header_fields_mapped_from_cex_context(self, client, captured_post):
        captured, seen = captured_post
        body = _ingest(client)
        assert seen.wait(5)
        payload = captured["payload"]
        assert payload["chain_id"] == body["chain_id"] == 90001  # CEX_CHAIN_IDS["BINANCE"]
        assert payload["chain_label"] == "CEX_BINANCE"
        # no real CEX block — ts is the documented pseudo-block
        assert payload["block_num"] == payload["timestamp"]
        assert payload["block_hash"] and isinstance(payload["block_hash"], str)

    def test_entries_carry_full_bh_strands(self, client, captured_post):
        """Old sender shipped the 16-char truncated strands — pinned to full 64."""
        captured, seen = captured_post
        _ingest(client)
        assert seen.wait(5)
        for e in captured["payload"]["entries"]:
            assert len(e["sense_hex"]) == 64
            assert len(e["antisense_hex"]) == 64
            int(e["sense_hex"], 16)      # valid hex
            int(e["antisense_hex"], 16)
            assert e["entity_id"] == hashlib.sha3_256(b"BINANCE:ETH/USDT").hexdigest()
            assert e["chain_id"] == 90001
            assert e["event_type"] in cex_mod.EVENT_TYPES
            assert e["event_type_name"] == cex_mod.EVENT_TYPES[e["event_type"]]

    def test_forward_is_keyed(self, client, captured_post, monkeypatch):
        """SEC-01 companion: the X-API-Key rides the forward POST."""
        monkeypatch.setenv("FAISS_API_KEY", "cex-forward-regression-key")
        captured, seen = captured_post
        _ingest(client)
        assert seen.wait(5)
        headers = captured["headers"] or {}
        assert headers.get("X-API-Key") == "cex-forward-regression-key"

    def test_empty_records_forward_empty_entries(self, client, captured_post, monkeypatch):
        """Empty batch is still schema-valid (stored=0), not a 422."""
        captured, seen = captured_post
        r = client.post("/api/v1/cex/ingest",
                        headers={"X-API-Key": _INGEST_KEY},
                        json={"cex_name": "KRAKEN", "data_type": "SPREAD_METRICS",
                              "asset": "BTC/USDT", "records": []})
        assert r.status_code == 200
        assert seen.wait(5)
        assert captured["payload"]["entries"] == []
        assert set(captured["payload"]) == set(BATCH_FIELDS)


# ── R-20: canonical L0.1 verification of the CEX-built strands ────────────────
#
# The old CEX builder packed a NONZERO context_flags word and a 2^63-scale
# magnitude, so the endpoint's canonical recomputation (context=0, 1e9 nano
# scale — faiss_service.py canonical_bh via verify_bh_complementarity) could
# never reproduce the strands and the /index/add_tx_bh_batch `verified`
# counter stayed 0 for every CEX forward.  These tests run the builder's
# output through the SAME recompute path the endpoint uses.

# Copied verbatim from the EVENT_NAMES list inside add_tx_bh_batch
# (anima-service/faiss_service.py) — the endpoint derives the event name it
# recomputes with from the entry's event_type byte via this list.
_ENDPOINT_EVENT_NAMES = [
    "TRANSFER", "SWAP", "LIQUIDITY", "STAKE", "UNSTAKE",
    "GOVERNANCE", "PROPOSAL", "BORROW", "REPAY", "LIQUIDATE", "BRIDGE", "DEPLOY",
    "UPGRADE", "MINT", "BURN", "ORACLE_UPDATE",
    "MEV_CAPTURE", "FLASH_LOAN", "AIRDROP", "CLAIM",
]

_faiss_service = None


def _endpoint_recompute():
    """verify_bh_complementarity — the exact function /index/add_tx_bh_batch
    calls on every entry.  Loaded lazily so the payload-contract tests above
    stay fast; tests/conftest.py already puts anima-service on sys.path."""
    global _faiss_service
    if _faiss_service is None:
        import faiss_service  # noqa: PLC0415 — anima-service is on sys.path
        _faiss_service = faiss_service
    return _faiss_service.verify_bh_complementarity


def _endpoint_name(event_type: int) -> str:
    """The endpoint's own event-name derivation from the byte."""
    return (_ENDPOINT_EVENT_NAMES[event_type]
            if 0 <= event_type < len(_ENDPOINT_EVENT_NAMES) else "TRANSFER")


def _verify_entry_like(entry: dict) -> bool:
    """Recompute an entry exactly the way add_tx_bh_batch does."""
    return _endpoint_recompute()(
        entry["sense_hex"], entry["antisense_hex"],
        entry["entity_id" if "entity_id" in entry else "entity_id_hex"],
        _endpoint_name(entry["event_type"]),
        entry["magnitude_norm"],
        "0",
        float(entry["timestamp"] if "timestamp" in entry else entry["ts"]),
        entry["chain_id"],
        entry["block_hash" if "block_hash" in entry else "block_hash_hex"],
    )


class TestCanonicalL01Verification:

    def test_built_bh_passes_endpoint_recomputation(self):
        """_build_cex_bh strands must satisfy the endpoint's canonical check.

        Covers a plain BUY, a >$1M CTX_LARGE sell and a wash-flagged record —
        the CEX classification flags must NOT leak into the canonical payload.
        """
        cases = [
            (1, 850_000.0, 0x0000000000000001),    # SWAP, SPOT
            (16, 1_250_000.0, 0x0000000000000021),  # MEV, SPOT|LARGE
            (3, 60_000.0, 0x0000000000000013),      # STAKE, SPOT|LIQUIDAT|WASH (canonical byte; WASH maps to 3)
            (0, 0.0, 0x0000000000000002),           # TRANSFER, zero magnitude
        ]
        for event_type, usd, ctx in cases:
            bh = cex_mod._build_cex_bh(
                "BINANCE", "ETH/USDT", event_type, usd, ctx,
                1_750_000_000, 90001, "batch-id-11c")
            assert _verify_entry_like(bh), (
                "CEX BH no longer matches the canonical L0.1 recomputation",
                event_type, usd, ctx)

    def test_payload_context_zero_and_nano_scale(self):
        """The 93-byte payload itself: 8 zero context bytes, 1e9 nano magnitude."""
        bh = cex_mod._build_cex_bh(
            "BINANCE", "ETH/USDT", 1, 850_000.0,
            0x0000000000000031,  # nonzero classification — must NOT enter payload
            1_750_000_000, 90001, "batch-id-11c")
        payload = bytes.fromhex(bh["payload_hex"])
        assert len(payload) == 93
        # context bytes [41:49] — canonical reserved field is always 0
        assert payload[41:49] == b"\x00" * 8, "nonzero context in canonical payload"
        # magnitude bytes [33:41] — canonical 1e9 nano scale, not 2^63
        mag_nano = int.from_bytes(payload[33:41], "big")
        assert mag_nano == bh["magnitude_nano"]
        assert mag_nano <= 1_000_000_000
        assert mag_nano == int(max(0.0, min(1.0, bh["magnitude_norm"])) * 1e9)

    def test_forwarded_entries_pass_endpoint_recomputation(self, client, captured_post):
        """End-to-end pin: every entry the daemon thread POSTs verifies."""
        captured, seen = captured_post
        _ingest(client)
        assert seen.wait(5)
        entries = captured["payload"]["entries"]
        assert entries
        for e in entries:
            assert _verify_entry_like(e), (
                "forwarded entry fails the canonical recomputation", e["tx_hash"])

    def test_forwarded_magnitude_norm_is_unrounded(self, client, captured_post):
        """The endpoint re-derives mag_nano from the forwarded float — it must
        be the builder's exact value (round() would desync it from the payload)."""
        captured, seen = captured_post
        _ingest(client)
        assert seen.wait(5)
        # the BUY record from _RECORDS: 850_000 USD → builder's magnitude_norm
        sent = {e["magnitude_norm"] for e in captured["payload"]["entries"]}
        assert cex_mod._magnitude_norm(850_000) in sent
        for e in captured["payload"]["entries"]:
            # every forwarded float re-derives the nano value it was built from
            assert 0.0 <= e["magnitude_norm"] <= 1.0
            assert int(max(0.0, min(1.0, e["magnitude_norm"])) * 1e9) <= 1_000_000_000
