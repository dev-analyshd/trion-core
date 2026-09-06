"""BH streamer non-EVM fetcher field pins — R-21 (cosmos) and R-14 (TON).

The Python fetchers must read the SAME chain fields the fixed Rust indexer
crates read, so both pipelines derive identical bytes from the same block:

  * R-21 — fetch_cosmos_block used to return `header.last_block_id.hash`
    (the PARENT block's hash) while trion-cosmos reads the CURRENT block's
    `block_id.hash` (LCD /blocks/{h}).  Pinned: result.block_id.hash, with
    the documented "0x0" fallback.
  * R-14 — fetch_ton_block used to stamp the TIP's root_hash (from
    getMasterchainInfo) on every seqno.  Pinned: per-seqno GET /getBlockHeader
    (workchain=-1, shard=8000000000000000 — the same call trion-ton uses for
    catch-up seqnos), result.root_hash verbatim, genuinely-missing → warn +
    honest "0x0" (CANONICAL_BH.md §9).

Run: pytest tests/unit/test_bh_streamer_fetchers.py -q
"""
import io
import json
import urllib.request

import pytest

import core.realtime.bh_streamer as bs


class _FakeResp:
    def __init__(self, payload):
        self._buf = io.BytesIO(json.dumps(payload).encode())

    def read(self):
        return self._buf.read()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeUrlopen:
    """urllib.request.urlopen stand-in: records requested URLs, serves canned
    bodies from .bodies in FIFO order."""

    def __init__(self):
        self.calls = []
        self.bodies = []

    def __call__(self, req, timeout=10):
        url = req.full_url if isinstance(req, urllib.request.Request) else str(req)
        self.calls.append(url)
        return _FakeResp(self.bodies.pop(0))


@pytest.fixture()
def http(monkeypatch):
    fake = _FakeUrlopen()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return fake


class TestCosmosCurrentBlockHash:
    """R-21 — current block's own block_id.hash, never the parent's."""

    def test_reads_current_block_id_hash(self, http):
        http.bodies.append({
            "result": {
                "block_id": {"hash": "CURRENTBLOCKHASH0000111"},
                "block": {
                    "header": {"time": "2026-01-02T03:04:05Z",
                               "last_block_id": {"hash": "PARENTHASH000000000000"}},
                    "data": {"txs": ["tx1", "tx2"]},
                },
            }
        })
        block = bs.fetch_cosmos_block("http://rpc", 54321)
        assert block["hash"] == "CURRENTBLOCKHASH0000111"
        assert block["number"] == 54321
        assert block["hash"] != "PARENTHASH000000000000"  # parent must not leak
        assert http.calls == ["http://rpc/block?height=54321"]

    def test_missing_block_id_falls_back_to_zero(self, http):
        http.bodies.append({"result": {"block": {"header": {"time": ""},
                                                  "data": {"txs": []}}}})
        block = bs.fetch_cosmos_block("http://rpc", 1)
        assert block["hash"] == "0x0"


class TestTonPerSeqnoHeaderHash:
    """R-14 — each seqno carries its own root_hash from getBlockHeader."""

    def test_seqno_gets_its_own_root_hash(self, http):
        http.bodies.append({"ok": True, "result": {
            "seqno": 42, "root_hash": "PERSEQROOT42==", "file_hash": "x"}})
        block = bs.fetch_ton_block("http://toncenter", 42)
        assert block["hash"] == "PERSEQROOT42=="
        assert block["number"] == 42
        # the per-seqno call trion-ton uses — NOT getMasterchainInfo
        assert http.calls == [
            "http://toncenter/getBlockHeader?workchain=-1&shard=8000000000000000&seqno=42"]

    def test_distinct_seqnos_get_distinct_hashes(self, http):
        http.bodies.append({"ok": True, "result": {"root_hash": "HASHOF41"}})
        http.bodies.append({"ok": True, "result": {"root_hash": "HASHOF42"}})
        b41 = bs.fetch_ton_block("http://toncenter", 41)
        b42 = bs.fetch_ton_block("http://toncenter", 42)
        # the old code stamped the SAME tip root_hash on both (R-14)
        assert b41["hash"] == "HASHOF41"
        assert b42["hash"] == "HASHOF42"
        assert b41["hash"] != b42["hash"]

    def test_missing_root_hash_is_honest_zero(self, http, capsys):
        http.bodies.append({"ok": True, "result": {"seqno": 7}})
        block = bs.fetch_ton_block("http://toncenter", 7)
        assert block["hash"] == "0x0"
        assert "no root_hash" in capsys.readouterr().err

    def test_api_error_is_honest_zero(self, http):
        http.bodies.append({"ok": False, "error": "block not found"})
        block = bs.fetch_ton_block("http://toncenter", 9)
        assert block["hash"] == "0x0"
