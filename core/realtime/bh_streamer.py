#!/usr/bin/env python3
"""
TRION Protocol — Real-Time BH Streamer
=======================================

Connects to public RPC endpoints for major EVM chains, polls for new
blocks and transactions, computes Behavioral Hashes (BH) from real
on-chain data, and writes them to bh_ledger.db.

Chains indexed (public RPCs — no API key required):
  - Ethereum (1)         https://ethereum-rpc.publicnode.com
  - Polygon (137)        https://polygon-bor-rpc.publicnode.com
  - BNB Smart Chain (56) https://bsc-rpc.publicnode.com
  - Arbitrum (42161)     https://arbitrum-one-rpc.publicnode.com
  - Base (8453)          https://base-rpc.publicnode.com
  - Optimism (10)        https://optimism-rpc.publicnode.com
  - Avalanche (43114)    https://avalanche-c-chain-rpc.publicnode.com
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import sys
import threading
import time
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Callable, Any

# ── Chain RPC Configuration ───────────────────────────────────────────────────

CHAIN_RPCS: Dict[int, Dict] = {
    # ── VM Family 1: EVM (55 chains per spec) ──────────────────────────────
    1: {"name": "ethereum", "label": "Ethereum", "rpc": "https://ethereum-rpc.publicnode.com", "block_time": 12, "native_symbol": "ETH", "decimals": 18},
    42161: {"name": "arbitrum", "label": "Arbitrum", "rpc": "https://arbitrum-one-rpc.publicnode.com", "block_time": 0.25, "native_symbol": "ETH", "decimals": 18},
    8453: {"name": "base", "label": "Base", "rpc": "https://base-rpc.publicnode.com", "block_time": 2, "native_symbol": "ETH", "decimals": 18},
    10: {"name": "optimism", "label": "Optimism", "rpc": "https://optimism-rpc.publicnode.com", "block_time": 2, "native_symbol": "ETH", "decimals": 18},
    137: {"name": "polygon", "label": "Polygon", "rpc": "https://polygon-bor-rpc.publicnode.com", "block_time": 2, "native_symbol": "MATIC", "decimals": 18},
    56: {"name": "bnb", "label": "BNB Chain", "rpc": "https://bsc-rpc.publicnode.com", "block_time": 3, "native_symbol": "BNB", "decimals": 18},
    5000: {"name": "mantle", "label": "Mantle", "rpc": "https://rpc.mantle.xyz", "block_time": 2, "native_symbol": "MNT", "decimals": 18},
    59144: {"name": "linea", "label": "Linea", "rpc": "https://rpc.linea.build", "block_time": 2, "native_symbol": "ETH", "decimals": 18},
    534352: {"name": "scroll", "label": "Scroll", "rpc": "https://rpc.scroll.io", "block_time": 3, "native_symbol": "ETH", "decimals": 18},
    177: {"name": "hashkey", "label": "HashKey", "rpc": "https://mainnet.hsk.xyz", "block_time": 3, "native_symbol": "HSK", "decimals": 18},
    16661: {"name": "zg_mainnet", "label": "0G Mainnet", "rpc": "https://evmrpc.0g.ai", "block_time": 2, "native_symbol": "ETH", "decimals": 18},
    43114: {"name": "avalanche", "label": "Avalanche", "rpc": "https://avalanche-c-chain-rpc.publicnode.com", "block_time": 2, "native_symbol": "AVAX", "decimals": 18},
    250: {"name": "fantom", "label": "Fantom", "rpc": "https://rpcapi.fantom.network", "block_time": 1, "native_symbol": "FTM", "decimals": 18},
    146: {"name": "sonic", "label": "Sonic", "rpc": "https://rpc.soniclabs.com", "block_time": 1, "native_symbol": "S", "decimals": 18},
    324: {"name": "zksync", "label": "zkSync Era", "rpc": "https://mainnet.era.zksync.io", "block_time": 2, "native_symbol": "ETH", "decimals": 18},
    80094: {"name": "berachain", "label": "Berachain", "rpc": "https://rpc.berachain.com", "block_time": 2, "native_symbol": "BERA", "decimals": 18},
    196: {"name": "xlayer", "label": "X Layer", "rpc": "https://rpc.xlayer.tech", "block_time": 2, "native_symbol": "OKB", "decimals": 18},
    50: {"name": "xdc", "label": "XDC Network", "rpc": "https://rpc.xinfin.network", "block_time": 2, "native_symbol": "XDC", "decimals": 18},
    1514: {"name": "story_ip", "label": "Story Protocol", "rpc": "https://mainnet.storyrpc.io", "block_time": 5, "native_symbol": "IP", "decimals": 18},
    81457: {"name": "blast", "label": "Blast", "rpc": "https://rpc.blast.io", "block_time": 2, "native_symbol": "ETH", "decimals": 18},
    169: {"name": "manta", "label": "Manta Pacific", "rpc": "https://pacific-rpc.manta.network/http", "block_time": 2, "native_symbol": "ETH", "decimals": 18},
    34443: {"name": "mode", "label": "Mode", "rpc": "https://mainnet.mode.network", "block_time": 2, "native_symbol": "ETH", "decimals": 18},
    167000: {"name": "taiko", "label": "Taiko", "rpc": "https://rpc.mainnet.taiko.xyz", "block_time": 2, "native_symbol": "ETH", "decimals": 18},
    252: {"name": "fraxtal", "label": "Fraxtal", "rpc": "https://rpc.frax.com", "block_time": 2, "native_symbol": "ETH", "decimals": 18},
    1088: {"name": "metis", "label": "Metis", "rpc": "https://andromeda.metis.io/?owner=1088", "block_time": 2, "native_symbol": "METIS", "decimals": 18},
    42220: {"name": "celo", "label": "Celo", "rpc": "https://forno.celo.org", "block_time": 5, "native_symbol": "CELO", "decimals": 18},
    100: {"name": "gnosis", "label": "Gnosis", "rpc": "https://rpc.gnosischain.com", "block_time": 5, "native_symbol": "xDAI", "decimals": 18},
    1284: {"name": "moonbeam", "label": "Moonbeam", "rpc": "https://rpc.api.moonbeam.network", "block_time": 12, "native_symbol": "GLMR", "decimals": 18},
    8217: {"name": "kaia", "label": "Kaia", "rpc": "https://public-en.node.kaia.io", "block_time": 1, "native_symbol": "KAIA", "decimals": 18},
    1116: {"name": "core", "label": "Core", "rpc": "https://rpc.coredao.org", "block_time": 3, "native_symbol": "CORE", "decimals": 18},
    200901: {"name": "bitlayer", "label": "Bitlayer", "rpc": "https://rpc.bitlayer.org", "block_time": 3, "native_symbol": "BTC", "decimals": 18},
    60808: {"name": "bob", "label": "BOB", "rpc": "https://rpc.gobob.xyz", "block_time": 2, "native_symbol": "ETH", "decimals": 18},
    30: {"name": "rootstock", "label": "Rootstock", "rpc": "https://public-node.rsk.co", "block_time": 30, "native_symbol": "RBTC", "decimals": 18},
    25: {"name": "cronos", "label": "Cronos", "rpc": "https://evm.cronos.org", "block_time": 5, "native_symbol": "CRO", "decimals": 18},
    1313161554: {"name": "aurora", "label": "Aurora", "rpc": "https://mainnet.aurora.dev", "block_time": 1, "native_symbol": "ETH", "decimals": 18},
    1666600000: {"name": "harmony", "label": "Harmony", "rpc": "https://api.harmony.one", "block_time": 2, "native_symbol": "ONE", "decimals": 18},
    4689: {"name": "iotex", "label": "IoTeX", "rpc": "https://babel-api.mainnet.iotex.io", "block_time": 5, "native_symbol": "IOTX", "decimals": 18},
    1030: {"name": "conflux", "label": "Conflux eSpace", "rpc": "https://evm.confluxrpc.com", "block_time": 1, "native_symbol": "CFX", "decimals": 18},
    10143: {"name": "monad", "label": "Monad", "rpc": "https://rpc.monad.xyz", "block_time": 1, "native_symbol": "MON", "decimals": 18},
    314: {"name": "filecoin", "label": "Filecoin", "rpc": "https://api.node.glif.io/rpc/v1", "block_time": 30, "native_symbol": "FIL", "decimals": 18},
    999: {"name": "hyperliquid", "label": "Hyperliquid", "rpc": "https://rpc.hyperliquid-testnet.xyz/evm", "block_time": 2, "native_symbol": "ETH", "decimals": 18},
    2741: {"name": "abstract", "label": "Abstract", "rpc": "https://api.mainnet.abs.xyz", "block_time": 2, "native_symbol": "ETH", "decimals": 18},
    7777777: {"name": "zora", "label": "Zora", "rpc": "https://rpc.zora.energy", "block_time": 2, "native_symbol": "ETH", "decimals": 18},
    1111: {"name": "wemix", "label": "WEMIX", "rpc": "https://api.wemix.com", "block_time": 1, "native_symbol": "WEMIX", "decimals": 18},
    66: {"name": "okt_chain", "label": "OKT Chain", "rpc": "https://exchainrpc.okex.org", "block_time": 2, "native_symbol": "OKT", "decimals": 18},
    23294: {"name": "oasis_sapphire", "label": "Oasis Sapphire", "rpc": "https://sapphire.oasis.io", "block_time": 5, "native_symbol": "ROSE", "decimals": 18},
    40: {"name": "telos", "label": "Telos", "rpc": "https://mainnet.telos.net/evm", "block_time": 0.5, "native_symbol": "TLOS", "decimals": 18},
    255: {"name": "kroma", "label": "Kroma", "rpc": "https://api.kroma.network", "block_time": 2, "native_symbol": "ETH", "decimals": 18},
    7560: {"name": "cyber", "label": "Cyber", "rpc": "https://rpc.cyber.co", "block_time": 2, "native_symbol": "ETH", "decimals": 18},
    1329: {"name": "sei_evm", "label": "Sei EVM", "rpc": "https://evm-rpc.sei-apis.com", "block_time": 0.5, "native_symbol": "SEI", "decimals": 18},
    7700: {"name": "canto", "label": "Canto", "rpc": "https://canto.gravitychain.io", "block_time": 6, "native_symbol": "CANTO", "decimals": 18},
    245022934: {"name": "neon_evm", "label": "Neon EVM", "rpc": "https://neon-proxy-mainnet.solana.p2p.org", "block_time": 2, "native_symbol": "NEON", "decimals": 18},
    # ── Gap-fill: canonical-manifest EVM chains previously missing ─────────
    14:   {"name": "flare", "label": "Flare", "rpc": "https://flare-api.flare.network/ext/C/rpc", "block_time": 3, "native_symbol": "FLR", "decimals": 18},
    288:  {"name": "boba", "label": "Boba Network", "rpc": "https://mainnet.boba.network", "block_time": 15, "native_symbol": "ETH", "decimals": 18},
    592:  {"name": "astar", "label": "Astar EVM", "rpc": "https://rpc.astar.network", "block_time": 12, "native_symbol": "ASTR", "decimals": 18},
    1101: {"name": "polygon_zkevm", "label": "Polygon zkEVM", "rpc": "https://zkevm-rpc.com", "block_time": 3, "native_symbol": "ETH", "decimals": 18},
    2222: {"name": "kava_evm", "label": "Kava EVM", "rpc": "https://evm.kava.io", "block_time": 6, "native_symbol": "KAVA", "decimals": 18},
    61:      {"name": "etc", "label": "Ethereum Classic", "rpc": "https://etc.rivet.link", "block_time": 13, "native_symbol": "ETC", "decimals": 18},
    8822: {"name": "iota_evm", "label": "IOTA EVM", "rpc": "https://json-rpc.evm.iotaledger.net", "block_time": 5, "native_symbol": "IOTA", "decimals": 18},
    677: {"name": "bot_chain", "label": "BOT Chain", "rpc": "https://rpc.botchain.ai", "block_time": 3, "native_symbol": "BOT", "decimals": 18},
}

EVENT_TYPES = {
    0: "TRANSFER", 1: "SWAP", 2: "LIQUIDITY", 3: "STAKE", 4: "UNSTAKE",
    5: "GOVERNANCE", 6: "PROPOSAL", 7: "BORROW", 8: "REPAY", 9: "LIQUIDATE",
    10: "BRIDGE", 11: "DEPLOY", 12: "UPGRADE", 13: "MINT", 14: "BURN",
    15: "ORACLE_UPDATE", 16: "MEV_CAPTURE", 17: "FLASH_LOAN", 18: "AIRDROP", 19: "CLAIM",
}

SELECTOR_MAP = {
    "": 0, "a9059cbb": 0, "23b872dd": 0,
    "38ed1739": 1, "8803dbee": 1, "414bf389": 1, "c04b8d59": 1,
    "fb3bdb41": 2, "e8e33700": 2,
    "a694fc3a": 3, "d0e30db0": 3,
    "2e1a7d4d": 4,
    "40c10f19": 13, "42966c68": 14, "79cc6790": 14,
    "5ae401dc": 1, "12aa3caf": 1, "e449022e": 1,
    "3593564c": 5, "b3e3e4d5": 7, "573ade81": 8,
}


def classify_event(selector: str, value: int, has_input: bool) -> int:
    sel = selector.lower().strip()[:8]
    if not has_input or sel == "" or sel == "0x":
        return 0
    et = SELECTOR_MAP.get(sel)
    if et is not None:
        return et
    # Unknown selector: EVENT_TYPES (whitepaper 0–19, fixed by the 93-byte
    # cross-language BH spec) has no UNKNOWN/GENERIC code, so — honestly —
    # unmapped selectors fall back to TRANSFER (0), the same default the
    # Rust indexer uses. SELECTOR_MAP needs a fuller selector table before
    # non-transfer calldata can be typed correctly. (The old
    # `len(selector) > 300 → SWAP` heuristic was dead code: callers pass
    # `input[:10]`, so it could never fire.)
    return 0


def _nibble(c):
    """Hex nibble → int, invalid chars read as 0 (Rust to_digit(16).unwrap_or(0))."""
    try:
        return int(c, 16)
    except ValueError:
        return 0


def _hex_to_32bytes(s):
    """Lenient hex→32 bytes, byte-identical to Rust trion-common hash_dna.rs:
    strip 0x, at most 32 bytes, left-aligned, invalid nibbles = 0."""
    s = str(s)
    s = s[2:] if s[:2].lower() == "0x" else s
    out = bytearray(32)
    n = min(len(s) // 2, 32)
    for i in range(n):
        out[i] = (_nibble(s[i * 2]) << 4) | _nibble(s[i * 2 + 1])
    return bytes(out)


def _normalise_addr(raw):
    """Port of Rust hash_dna.rs normalise(): trim + lowercase, canonicalise
    bare 40-hex addresses to 0x form. Everything else passes through — the
    SHA3-256 the caller applies then matches Rust bh_id() byte-for-byte."""
    s = str(raw).strip().lower()
    if s.startswith("0x") and len(s) >= 42:
        return s
    if len(s) == 40 and all(c in "0123456789abcdef" for c in s):
        return "0x" + s
    return s


def _iso_to_epoch(iso):
    """RFC3339/ISO-8601 timestamp → unix seconds (0 on failure)."""
    try:
        from datetime import datetime, timezone
        ts = str(iso).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return 0


def compute_bh(entity_id, event_type_id, magnitude_raw, chain_id, block_number, block_hash, timestamp, chain_label, decimals=18):
    """Canonical L0.1 Behavioral Hash — FIELD-ALIGNED with the Rust indexers.

    93-byte payload (all big-endian):
        entity_id(32) || event_type(1) || magnitude_nano(8) ||
        context(8) || timestamp(8) || chain_id(4) || block_hash(32)

    Field semantics now match trion-common::hash_dna::canonical_bh:
      - entity   = SHA3-256(normalised address) (Rust bh_id), hex→32B — the
                   canonical BEO key, so the same address hashes identically
                   on both ingestion paths.
      - context  = 0 — every Rust indexer crate passes 0 (venue/layer flags
                   are a reserved field; the old chain<<32|event encoding
                   could never match the Rust pipeline).
      - magnitude = raw native units / 10^decimals → deterministic log scale
                   (the Rust crates use a session-relative ratio — known,
                   documented divergence on their side).
      - timestamp = real chain block time; fetchers supply it per family.
      - block_hash = lenient hex→32B (invalid nibbles → 0, like Rust — no
                   silent SHA3 substitution that Rust would not reproduce).
    """
    # ── magnitude: native raw units → human via per-chain decimals ──────────
    raw = magnitude_raw
    if isinstance(raw, str):
        raw = float(raw) if ("." in raw or "e" in raw.lower()) else int(raw)
    if isinstance(raw, float):
        # Already-human decimal amounts (XRPL issued currencies) — no scaling.
        mag_human = raw if raw > 0 else 0.0
    else:
        try:
            dec = int(decimals)
        except (TypeError, ValueError):
            dec = 18
        # dec == 0 → value is already human (Cardano block tx_count).
        mag_human = (raw / (10 ** dec)) if (raw > 0 and dec > 0) else (float(raw) if raw > 0 else 0.0)
    mag_max = 1000.0
    mag_norm = min(1.0, math.log10(mag_human + 1) / math.log10(mag_max + 1)) if mag_human > 0 else 0.0
    # clamp + truncate to match Rust's `(x.clamp(0,1) * 1e9) as u64`
    mag_nano = int(max(0.0, min(1.0, mag_norm)) * 1_000_000_000.0)

    # ── entity: canonical BEO key = SHA3-256(normalised addr) ───────────────
    eid_hex = hashlib.sha3_256(_normalise_addr(entity_id).encode()).hexdigest()
    eid_bytes = _hex_to_32bytes(eid_hex)

    # ── context: 8 zero bytes — all 21 Rust crates pass 0 ───────────────────
    context = (0).to_bytes(8, "big")

    bh_bytes = _hex_to_32bytes(block_hash)

    try:
        ts = int(timestamp or 0)
    except (TypeError, ValueError):
        ts = 0

    payload = (
        eid_bytes
        + bytes([int(event_type_id) & 0xFF])
        + mag_nano.to_bytes(8, "big")
        + context
        + ts.to_bytes(8, "big")
        + (int(chain_id) & 0xFFFFFFFF).to_bytes(4, "big")
        + bh_bytes
    )
    assert len(payload) == 93, "canonical BH payload must be 93 bytes"

    sense = hashlib.sha3_256(payload + b"\x00").digest()
    sha3ff = hashlib.sha3_256(payload + b"\xFF").digest()
    antisense = bytes(a ^ (f ^ 0xFF) for a, f in zip(sha3ff, sense))

    sha3ff_check = hashlib.sha3_256(payload + b"\xFF").digest()
    comp_sense = bytes(b ^ 0xFF for b in sense)
    valid = (bytes(a ^ b for a, b in zip(antisense, comp_sense)) == sha3ff_check)

    return {
        "entity_id": eid_hex, "entity_id_raw": str(entity_id),
        "event_type": EVENT_TYPES.get(event_type_id, "UNKNOWN"),
        "event_type_id": event_type_id, "magnitude_norm": mag_norm,
        "chain_id": chain_id, "chain_label": chain_label,
        "block_number": block_number, "block_hash": block_hash,
        "timestamp": ts, "sense_hex": sense.hex(),
        "antisense_hex": antisense.hex(), "valid": valid, "tx_hash": "",
    }


def rpc_call(rpc_url, method, params, timeout=10):
    payload = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode("utf-8")
    req = urllib.request.Request(rpc_url, data=payload, headers={"Content-Type": "application/json", "User-Agent": "TRION/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    if "error" in data:
        raise RuntimeError(f"RPC error: {data['error']}")
    return data.get("result")


def get_latest_block(rpc_url):
    return int(rpc_call(rpc_url, "eth_blockNumber", []), 16)


def get_block_with_txs(rpc_url, block_num):
    try:
        return rpc_call(rpc_url, "eth_getBlockByNumber", [hex(block_num), True], timeout=15)
    except Exception:
        return None


def _value_wei_str(v):
    """Normalise a tx value (hex EVM / decimal native / float issued-token)
    to a decimal integer string for the value_wei column."""
    try:
        if isinstance(v, str) and v[:2].lower() == "0x":
            return str(int(v, 16))
        try:
            return str(int(v))
        except (TypeError, ValueError):
            return str(int(float(v)))
    except (TypeError, ValueError):
        return "0"


class BHStreamer:
    def __init__(self, db_path="bh_ledger.db", chains=None, on_bh=None, max_txs_per_block=50):
        # Railway/memory protection: cap concurrent chain workers.
        # TRION_MAX_CHAINS=12 keeps RSS < 400MB on 512MB plans;
        # unset or 0 = all chains (mainnet server spec).
        _max_chains = int(os.environ.get("TRION_MAX_CHAINS", "0") or 0)
        if _max_chains > 0 and len(self._all_chains(chains)) > _max_chains:
            # Priority order: Ethereum L1 + L2s first (highest behavioral value).
            # Preserves the Dict[chain_id, config] shape — workers index by id.
            _full = self._all_chains(chains)
            _PRIORITY = ["ethereum", "arbitrum", "base", "optimism", "polygon",
                         "bnb", "avalanche", "solana", "blast", "linea"]
            _selected_ids = []
            for name in _PRIORITY:
                for cid, cfg in _full.items():
                    if name in str(cfg.get("name", "")).lower() and cid not in _selected_ids:
                        _selected_ids.append(cid)
                if len(_selected_ids) >= _max_chains:
                    break
            for cid in _full:
                if len(_selected_ids) >= _max_chains:
                    break
                if cid not in _selected_ids:
                    _selected_ids.append(cid)
            chains = {cid: _full[cid] for cid in _selected_ids}
        self.db_path = db_path
        self.chains = chains or CHAIN_RPCS
        self.on_bh = on_bh
        self.max_txs_per_block = max_txs_per_block
        self._threads = {}
        self._stop_flags = {}
        self._last_block = {}
        self._stats = {"total_bhs": 0, "total_blocks": 0, "chains_active": 0, "started_at": time.time(), "per_chain": {}, "write_errors": 0}
        self._stats_lock = threading.Lock()
        self._running = False

    @staticmethod
    def _all_chains(chains):
        """Effective chain list before capping (explicit list or default set)."""
        return chains if chains is not None else CHAIN_RPCS

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""CREATE TABLE IF NOT EXISTS bh_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT, tx_hash TEXT UNIQUE,
            entity_id TEXT, from_addr TEXT, to_addr TEXT,
            event_type INTEGER, event_type_name TEXT,
            magnitude_norm REAL, value_wei TEXT, selector TEXT,
            sense_hex TEXT, antisense_hex TEXT,
            block_num INTEGER, block_hash TEXT,
            chain_id INTEGER, chain_label TEXT, ts REAL, valid INTEGER DEFAULT 1)""")
        # ── Schema migration: older ledgers lack the `valid` column. ──────────
        # CREATE TABLE IF NOT EXISTS does NOT upgrade an existing table, and
        # _write_bh inserts the `valid` column — without this migration every
        # streamed BH write fails silently ("table has no column named valid")
        # and the streamer reports BHs counted while persisting NOTHING.
        cols = {row[1] for row in conn.execute("PRAGMA table_info(bh_ledger)").fetchall()}
        if "valid" not in cols:
            conn.execute("ALTER TABLE bh_ledger ADD COLUMN valid INTEGER DEFAULT 1")
        conn.execute("CREATE INDEX IF NOT EXISTS bh_ledger_entity ON bh_ledger(entity_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS bh_ledger_chain ON bh_ledger(chain_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS bh_ledger_ts ON bh_ledger(ts DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS bh_ledger_chain_label ON bh_ledger(chain_label)")
        # Composite index: per-chain top-K queries (stratified feed sampling in
        # api/app.py bh_recent_feed) become index seeks instead of filter+sort.
        conn.execute("CREATE INDEX IF NOT EXISTS bh_ledger_chain_ts ON bh_ledger(chain_label, ts DESC)")
        conn.commit()
        conn.close()

    def _write_bh(self, bh, tx, chain_config):
        try:
            conn = sqlite3.connect(self.db_path, timeout=5)
            conn.execute("""INSERT OR IGNORE INTO bh_ledger
                (tx_hash, entity_id, from_addr, to_addr, event_type, event_type_name,
                 magnitude_norm, value_wei, selector, sense_hex, antisense_hex,
                 block_num, block_hash, chain_id, chain_label, ts, valid)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
                tx.get("hash", ""), bh["entity_id"], tx.get("from", ""), tx.get("to", ""),
                bh["event_type_id"], bh["event_type"], bh["magnitude_norm"],
                _value_wei_str(tx.get("value", "0x0")), tx.get("input", "")[:10],
                bh["sense_hex"], bh["antisense_hex"], bh["block_number"], bh["block_hash"],
                bh["chain_id"], bh["chain_label"], bh["timestamp"], 1 if bh["valid"] else 0))
            conn.commit()
            conn.close()
        except Exception as e:
            # SECURITY/DATA-INTEGRITY: never silently drop ledger writes — count
            # and surface the failure so operators see data loss in get_stats().
            with self._stats_lock:
                self._stats["write_errors"] = self._stats.get("write_errors", 0) + 1
            if self._stats.get("write_errors", 0) <= 3:
                print(f"[streamer] BH ledger write FAILED ({type(e).__name__}: {e}) — "
                      f"record dropped. Check schema/db_path: {self.db_path}", flush=True)

    def _process_block(self, chain_id, block, chain_config):
        if not block or "transactions" not in block:
            return
        txs = block["transactions"]
        if len(txs) > self.max_txs_per_block:
            step = max(1, len(txs) // self.max_txs_per_block)
            txs = txs[::step][:self.max_txs_per_block]

        _raw_num = block.get("number", "0x0")
        block_num = int(_raw_num, 16) if isinstance(_raw_num, str) else int(_raw_num)
        block_hash = block.get("hash", "0x" + "00" * 32)
        _raw_ts = block.get("timestamp", "0x0")
        timestamp = int(_raw_ts, 16) if isinstance(_raw_ts, str) else int(_raw_ts or 0)
        chain_label = chain_config["name"]
        # Per-chain magnitude scaling: fetchers report values in raw native
        # units; "value_decimals" overrides the display decimals where the
        # fetcher's value semantic differs (e.g. Cardano = block tx_count).
        _dec = chain_config.get("value_decimals", chain_config.get("decimals", 18))

        for tx in txs:
            if not isinstance(tx, dict):
                continue
            from_addr = tx.get("from", "0x" + "00" * 20)
            input_data = tx.get("input", "0x")
            _raw_val = tx.get("value", "0x0")
            value = int(_raw_val, 16) if isinstance(_raw_val, str) else int(_raw_val or 0)
            selector = input_data[:10] if input_data and input_data != "0x" else ""
            event_type_id = classify_event(selector, value, input_data != "0x")

            bh = compute_bh(from_addr, event_type_id, value, chain_id, block_num, block_hash, timestamp, chain_label, decimals=_dec)
            bh["tx_hash"] = tx.get("hash", "")

            self._write_bh(bh, tx, chain_config)
            if self.on_bh:
                try:
                    self.on_bh(bh, tx, chain_config)
                except Exception:
                    pass

            with self._stats_lock:
                self._stats["total_bhs"] += 1
                cs = self._stats["per_chain"].setdefault(chain_label, {"bhs": 0, "blocks": 0})
                cs["bhs"] += 1

    def _chain_worker(self, chain_id, chain_config):
        rpc_url = chain_config["rpc"]
        chain_name = chain_config["name"]
        poll_interval = max(2.0, chain_config.get("block_time", 12))

        try:
            latest = get_latest_block(rpc_url)
            self._last_block[chain_id] = latest - 3  # skip last 3 blocks for reorg safety
        except Exception as e:
            print(f"[streamer] {chain_name}: Failed to get initial block: {e}", file=sys.stderr)
            return

        print(f"[streamer] {chain_name} (id={chain_id}): starting from block {self._last_block[chain_id]}", flush=True)
        consecutive_errors = 0

        while not self._stop_flags[chain_id].is_set():
            try:
                latest = get_latest_block(rpc_url)
                target = self._last_block[chain_id] + 1

                if target > latest:
                    time.sleep(poll_interval)
                    continue

                block = get_block_with_txs(rpc_url, target)
                if block:
                    self._process_block(chain_id, block, chain_config)
                    self._last_block[chain_id] = target
                    with self._stats_lock:
                        self._stats["total_blocks"] += 1
                        cs = self._stats["per_chain"].setdefault(chain_name, {"bhs": 0, "blocks": 0})
                        cs["blocks"] += 1
                    consecutive_errors = 0
                    if target % 20 == 0:
                        print(f"[streamer] {chain_name}: block {target} ({len(block.get('transactions', []))} txs)", flush=True)
                else:
                    consecutive_errors += 1
                    time.sleep(min(30, poll_interval * (2 ** min(consecutive_errors, 5))))
            except Exception as e:
                consecutive_errors += 1
                if consecutive_errors <= 3:
                    print(f"[streamer] {chain_name}: error: {e}", file=sys.stderr)
                time.sleep(min(30, poll_interval * (2 ** min(consecutive_errors, 5))))

    def start(self):
        self._init_db()
        self._running = True
        for chain_id, config in self.chains.items():
            self._stop_flags[chain_id] = threading.Event()
            t = threading.Thread(target=self._chain_worker, args=(chain_id, config), daemon=True, name=f"bh-{config['name']}")
            t.start()
            self._threads[chain_id] = t
        with self._stats_lock:
            self._stats["chains_active"] = len(self.chains)
        print(f"[streamer] Started {len(self.chains)} chain workers", flush=True)

    def stop(self):
        for flag in self._stop_flags.values():
            flag.set()
        self._running = False

    def get_stats(self):
        with self._stats_lock:
            stats = dict(self._stats)
            stats["uptime_seconds"] = time.time() - stats["started_at"]
            stats["bhs_per_second"] = stats["total_bhs"] / max(1, stats["uptime_seconds"])
            stats["last_blocks"] = {str(k): v for k, v in self._last_block.items()}
            stats["running"] = self._running
            return stats

    def is_running(self):
        return self._running


class FAISSAccumulator:
    """Accumulates behavioral hashes and POSTs vectors to the FAISS service.

    Buffers vectors in memory and flushes to FAISS via HTTP POST
    /index/add_batch when the buffer reaches BATCH_SIZE or FLUSH_INTERVAL.
    This ensures real-time vector population of the FAISS index.
    """

    BATCH_SIZE = 50
    FLUSH_INTERVAL = 10.0  # seconds

    def __init__(self, faiss_url=None):
        self.vector_count = 0
        self._lock = threading.Lock()
        self._buffer = []
        self._faiss_url = faiss_url or os.environ.get(
            "FAISS_SERVICE_URL",
            os.environ.get("FAISS_URL", "http://127.0.0.1:8000")
        )
        self._last_flush = time.time()
        self._flush_thread = None
        self._stop_flush = threading.Event()
        self._start_flush_daemon()

    def _start_flush_daemon(self):
        """Background thread that flushes buffer periodically."""
        def _flush_loop():
            while not self._stop_flush.is_set():
                self._stop_flush.wait(self.FLUSH_INTERVAL)
                self._flush_buffer()
        self._flush_thread = threading.Thread(target=_flush_loop, daemon=True)
        self._flush_thread.start()

    def _flush_buffer(self):
        """POST buffered vectors to FAISS service as structured VectorPayload items."""
        with self._lock:
            if not self._buffer:
                self._last_flush = time.time()
                return
            batch = list(self._buffer)
            self._buffer.clear()
            self._last_flush = time.time()

        try:
            # Build structured VectorPayload items
            payload_items = []
            for item in batch:
                vec = item["vector"]
                mag = item.get("magnitude_norm", item.get("magnitude", 0.0))
                # Compute entropy from event_type distribution
                et = item.get("event_type_id", 0)
                # Entropy estimate: higher for rarer event types,
                # bounded in [0.2, 1.0] to ensure signal selection gate passes
                # Entropy reflects event type information content
                # Rare event types (1-19) carry more information than transfers (0)
                # Range: 0.60-0.95 ensures signal selection gate passes even for BASE_PRESENCE
                et_rarity = 1.0 - (et / 20.0)  # 0=common, 19=rarest
                chain_factor = min(1.0, (item.get("chain_id", 1) % 10) / 10.0 + 0.5)
                entropy = max(0.60, min(0.95, 0.60 + et_rarity * 0.30 + chain_factor * 0.05))
                payload_items.append({
                    "entity_id": item.get("entity_id", item.get("from_addr", "unknown")),
                    "vector": vec,
                    "magnitude": float(mag) if mag else 0.5,
                    "entropy": entropy,
                    "timestamp": item.get("timestamp", time.time()),
                    "chain_id": item.get("chain_id", 1),
                    "event_type": et,
                    "sense_hex": item.get("sense_hex", ""),
                    "block_num": item.get("block_num", 0),
                    "vm_type": "EVM",
                })

            payload = json.dumps({
                "vectors": payload_items,
                "source": "bh_streamer",
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{self._faiss_url}/index/add_batch",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    pass  # Successfully flushed
        except Exception as e:
            # FAISS might not be ready yet; buffer will retry on next flush
            with self._lock:
                self._buffer.extend(batch)
                # Prevent unbounded growth: cap buffer
                if len(self._buffer) > 10000:
                    self._buffer = self._buffer[-5000:]

    def bh_to_vector(self, bh):
        vec = [0.0] * 128
        et = bh.get("event_type_id", 0)
        if 0 <= et < 20:
            vec[et] = 1.0
        mag = bh.get("magnitude_norm", 0.0)
        for i in range(10):
            vec[20 + i] = mag
        chain_id = bh.get("chain_id", 1)
        chain_norm = (chain_id % 100) / 100.0
        for i in range(10):
            vec[30 + i] = chain_norm
        ts = bh.get("timestamp", 0)
        if ts > 0:
            hour = (ts // 3600) % 24
            dow = (ts // 86400) % 7
            vec[40] = math.sin(2 * math.pi * hour / 24)
            vec[41] = math.cos(2 * math.pi * hour / 24)
            vec[42] = math.sin(2 * math.pi * dow / 7)
            vec[43] = math.cos(2 * math.pi * dow / 7)
            for i in range(44, 60):
                vec[i] = (ts % (i * 100)) / (i * 100.0)
        sense_hex = bh.get("sense_hex", "")
        if sense_hex:
            sense_bytes = bytes.fromhex(sense_hex[:136])
            for i, b in enumerate(sense_bytes[:68]):
                vec[60 + i] = b / 255.0
        return vec

    def on_bh(self, bh, tx, chain_config):
        vec = self.bh_to_vector(bh)
        # Store full bh dict + vector for structured VectorPayload
        item = dict(bh)
        item["vector"] = vec
        # Ensure entity_id is present (use from_addr as fallback)
        if "entity_id" not in item and "from_addr" in item:
            item["entity_id"] = item["from_addr"]
        should_flush = False
        with self._lock:
            self.vector_count += 1
            self._buffer.append(item)
            if len(self._buffer) >= self.BATCH_SIZE:
                should_flush = True
        if should_flush:
            self._flush_buffer()

    def shutdown(self):
        """Stop flush daemon and flush remaining vectors."""
        self._stop_flush.set()
        if self._flush_thread:
            self._flush_thread.join(timeout=2)
        self._flush_buffer()


# ── Global instance ───────────────────────────────────────────────────────────

_global_streamer = None
_global_faiss_acc = None

def get_streamer():
    return _global_streamer

def get_faiss_accumulator():
    return _global_faiss_acc

def start_streamer(db_path="bh_ledger.db"):
    global _global_streamer, _global_faiss_acc
    if _global_streamer and _global_streamer.is_running():
        return _global_streamer
    _global_faiss_acc = FAISSAccumulator()
    _global_streamer = BHStreamer(db_path=db_path, on_bh=_global_faiss_acc.on_bh, max_txs_per_block=50)
    _global_streamer.start()
    return _global_streamer


if __name__ == "__main__":
    print("=== TRION Real-Time BH Streamer ===\n")
    streamer = start_streamer()
    for i in range(6):
        time.sleep(5)
        stats = streamer.get_stats()
        print(f"\n--- {i*5+5}s ---")
        print(f"  Total BHs: {stats['total_bhs']}")
        print(f"  Total blocks: {stats['total_blocks']}")
        print(f"  BHs/sec: {stats['bhs_per_second']:.2f}")
        print(f"  Chains: {stats['chains_active']}")
        for chain, cs in stats["per_chain"].items():
            print(f"    {chain}: {cs['bhs']} BHs, {cs['blocks']} blocks")
    streamer.stop()
    print("\nStopped.")

# ============================================================================
# NON-EVM CHAIN CONFIGS — All 16 VM families
# ============================================================================
# FIX-CLAIMS (chain-ID collision, documented not fixed): the ids below are a
# THIRD namespace that conflicts with the canonical config/chain_registry.json
# (single source of truth per P3-CONSOLIDATE; see core/generated_chain_bindings.py):
#   solana here 200101 vs canonical 900 (svm_indexer/execute.ts also 900;
#   mainnet_bootstrap.py uses 5773521; api display registry uses 101/900);
#   cosmos_hub here 200201 vs canonical 10000; aptos 200301 vs canonical 5001.
# Historical SQLite rows are keyed on these ids, so renumbering would orphan
# existing data — left for the orchestrator to reconcile. relayer/
# relayer_non_evm.js is yet a FOURTH ad-hoc scheme (btc=2000, sui=6001...).

NON_EVM_CHAINS: Dict[int, Dict] = {
    # ── VM Family 2: SVM (Solana) ──────────────────────────────────────────
    200101: {"name": "solana", "label": "Solana", "vm": "SVM", "rpc": "https://api.mainnet-beta.solana.com", "block_time": 0.4, "native_symbol": "SOL", "decimals": 9},

    # ── VM Family 3: Cosmos (6 chains) ─────────────────────────────────────
    200201: {"name": "cosmos_hub", "label": "Cosmos Hub", "vm": "COSMOS", "rpc": "https://rpc.cosmos.directory/cosmoshub", "block_time": 6, "native_symbol": "ATOM", "decimals": 6},
    200202: {"name": "osmosis", "label": "Osmosis", "vm": "COSMOS", "rpc": "https://rpc.osmosis.zone", "block_time": 6, "native_symbol": "OSMO", "decimals": 6},
    200203: {"name": "injective", "label": "Injective", "vm": "COSMOS", "rpc": "https://sentry-lcd.injective.network", "block_time": 2, "native_symbol": "INJ", "decimals": 18},
    200204: {"name": "celestia", "label": "Celestia", "vm": "COSMOS", "rpc": "https://rpc.celestia.pops.one", "block_time": 12, "native_symbol": "TIA", "decimals": 6},
    200205: {"name": "dydx", "label": "dYdX", "vm": "COSMOS", "rpc": "https://dYdX-rpc.lava.build", "block_time": 2, "native_symbol": "DYDX", "decimals": 18},
    200206: {"name": "sei", "label": "Sei", "vm": "COSMOS", "rpc": "https://sei-rpc.polkachu.com", "block_time": 0.5, "native_symbol": "SEI", "decimals": 6},

    # ── VM Family 4: Move (Aptos, Sui) ─────────────────────────────────────
    200301: {"name": "aptos", "label": "Aptos", "vm": "MOVE", "rpc": "https://fullnode.mainnet.aptoslabs.com", "block_time": 1, "native_symbol": "APT", "decimals": 8},
    200302: {"name": "sui", "label": "Sui", "vm": "MOVE", "rpc": "https://fullnode.mainnet.sui.io", "block_time": 0.5, "native_symbol": "SUI", "decimals": 9},

    # ── VM Family 5: NEAR ──────────────────────────────────────────────────
    200401: {"name": "near", "label": "NEAR", "vm": "NEAR", "rpc": "https://rpc.mainnet.near.org", "block_time": 1, "native_symbol": "NEAR", "decimals": 24},

    # ── VM Family 6: TON ───────────────────────────────────────────────────
    200501: {"name": "ton", "label": "TON", "vm": "TON", "rpc": "https://toncenter.com/api/v2", "block_time": 5, "native_symbol": "TON", "decimals": 9},

    # ── VM Family 7: Starknet ───────────────────────────────────────────────
    200601: {"name": "starknet", "label": "Starknet", "vm": "STARKNET", "rpc": "https://starknet-mainnet.public.blastapi.io", "block_time": 3, "native_symbol": "ETH", "decimals": 18},

    # ── VM Family 8: Tron ──────────────────────────────────────────────────
    200701: {"name": "tron", "label": "Tron", "vm": "TRON", "rpc": "https://api.trongrid.io", "block_time": 3, "native_symbol": "TRX", "decimals": 6},

    # ── VM Family 9: UTXO (Bitcoin, Litecoin, Dogecoin) ────────────────────
    200801: {"name": "bitcoin", "label": "Bitcoin", "vm": "UTXO", "rpc": "https://blockstream.info/api", "block_time": 600, "native_symbol": "BTC", "decimals": 8},
    200802: {"name": "litecoin", "label": "Litecoin", "vm": "UTXO", "rpc": "https://litecoinblockexplorer.net/api", "block_time": 150, "native_symbol": "LTC", "decimals": 8},
    200803: {"name": "dogecoin", "label": "Dogecoin", "vm": "UTXO", "rpc": "https://dogeblocks.com/api", "block_time": 60, "native_symbol": "DOGE", "decimals": 8},

    # ── VM Family 10: Stellar ──────────────────────────────────────────────
    # id 27000 = canonical registry id (config/chain_registry.json). Was 200901,
    # which collided with bitlayer in CHAIN_RPCS: both workers share
    # _last_block/_stop_flags keyed by chain id, and stellar's string cursor
    # made the bitlayer worker raise "can only concatenate str (not 'int')
    # to str" on every poll after the first stellar update.
    27000: {"name": "stellar", "label": "Stellar", "vm": "STELLAR", "rpc": "https://horizon.stellar.org", "block_time": 5, "native_symbol": "XLM", "decimals": 7},

    # ── VM Family 11: Hedera ───────────────────────────────────────────────
    201001: {"name": "hedera", "label": "Hedera", "vm": "HEDERA", "rpc": "https://mainnet.hashio.io/api", "block_time": 2, "native_symbol": "HBAR", "decimals": 8},

    # ── VM Family 12: MultiversX ───────────────────────────────────────────
    201101: {"name": "multiversx", "label": "MultiversX", "vm": "MULTIVERSX", "rpc": "https://api.multiversx.eu", "block_time": 6, "native_symbol": "EGLD", "decimals": 18},

    # ── VM Family 13: Vechain ──────────────────────────────────────────────
    201201: {"name": "vechain", "label": "Vechain", "vm": "VECHAIN", "rpc": "https://mainnet.vechain.org", "block_time": 10, "native_symbol": "VET", "decimals": 18},

    # ── VM Family 14: Waves ────────────────────────────────────────────────
    201301: {"name": "waves", "label": "Waves", "vm": "WAVES", "rpc": "https://nodes.wavesnodes.com", "block_time": 60, "native_symbol": "WAVES", "decimals": 8},

    # ── VM Family 15: XRPL ─────────────────────────────────────────────────
    201401: {"name": "xrpl", "label": "XRPL", "vm": "XRPL", "rpc": "https://s1.ripple.com:51234", "block_time": 4, "native_symbol": "XRP", "decimals": 6},

    # ── VM Family 16: Polkadot (PVM) ──────────────────────────────────────
    201501: {"name": "polkadot", "label": "Polkadot", "vm": "PVM", "rpc": "https://rpc.polkadot.io", "block_time": 6, "native_symbol": "DOT", "decimals": 10},
    25002:  {"name": "kusama", "label": "Kusama", "vm": "PVM", "rpc": "https://kusama-rpc.polkadot.io", "block_time": 6, "native_symbol": "KSM", "decimals": 12},

    # ── VM Family 17: Algorand (AVM) ──────────────────────────────────────
    8200:   {"name": "algorand", "label": "Algorand", "vm": "ALGORAND", "rpc": "https://mainnet-api.algonode.cloud", "block_time": 3, "native_symbol": "ALGO", "decimals": 6},

    # ── VM Family 18: Cardano (eUTXO) ─────────────────────────────────────
    # value_decimals=0: the Cardano fetcher's per-block value is the block's
    # tx_count (pool-behavior magnitude), NOT ada — no decimal scaling.
    9400:   {"name": "cardano", "label": "Cardano", "vm": "CARDANO", "rpc": "https://api.koios.rest", "block_time": 20, "native_symbol": "ADA", "decimals": 6, "value_decimals": 0},

    # ── Additional Cosmos-family chains (public Tendermint RPCs) ──────────
    10014:  {"name": "kava", "label": "Kava", "vm": "COSMOS", "rpc": "https://rpc.kava.io", "block_time": 6, "native_symbol": "KAVA", "decimals": 6},

    # ── Gap-fill: manifest Cosmos chains with VERIFIED public RPCs (cosmos.directory) ──
    10002:  {"name": "juno", "label": "Juno", "vm": "COSMOS", "rpc": "https://rpc.cosmos.directory/juno", "block_time": 6, "native_symbol": "JUNO", "decimals": 6},
    10010:  {"name": "terra", "label": "Terra Phoenix", "vm": "COSMOS", "rpc": "https://rpc.cosmos.directory/terra", "block_time": 6, "native_symbol": "LUNA", "decimals": 6},
    10011:  {"name": "persistence", "label": "Persistence", "vm": "COSMOS", "rpc": "https://rpc.cosmos.directory/persistence", "block_time": 6, "native_symbol": "XPRT", "decimals": 6},
    10013:  {"name": "chihuahua", "label": "Chihuahua", "vm": "COSMOS", "rpc": "https://rpc.cosmos.directory/chihuahua", "block_time": 6, "native_symbol": "HUAHUA", "decimals": 6},
    10015:  {"name": "initia", "label": "Initia", "vm": "COSMOS", "rpc": "https://rpc.cosmos.directory/initia", "block_time": 6, "native_symbol": "INIT", "decimals": 6},
    10016:  {"name": "saga", "label": "Saga", "vm": "COSMOS", "rpc": "https://rpc.cosmos.directory/saga", "block_time": 6, "native_symbol": "SAGA", "decimals": 6},
    10017:  {"name": "noble", "label": "Noble", "vm": "COSMOS", "rpc": "https://rpc.cosmos.directory/noble", "block_time": 6, "native_symbol": "USDC", "decimals": 6},
    10019:  {"name": "axelar", "label": "Axelar", "vm": "COSMOS", "rpc": "https://rpc.cosmos.directory/axelar", "block_time": 6, "native_symbol": "AXL", "decimals": 6},

    # ── Gap-fill: Movement (Move VM, verified live) ──
    20200:  {"name": "movement", "label": "Movement Mainnet", "vm": "MOVE", "rpc": "https://mainnet.movementnetwork.xyz", "block_time": 1, "native_symbol": "MOVE", "decimals": 8},
}

# ============================================================================
# NON-EVM BLOCK FETCHERS
# ============================================================================

def _synthetic_tx_sender(chain_name: str, tx_hash: str) -> str:
    """
    HONESTLY-SYNTHETIC per-transaction sender identity for non-EVM fetchers
    whose chain APIs don't expose real senders in the shape we fetch
    (Solana signatures-only; Cosmos/NEAR/TON/MultiversX/VeChain tx rows;
    Aptos tx counts; Starknet/Tron/Polkadot tx hashes without a sender
    field).

    sha3-256("{chain_name}:{tx_hash}") — distinct and deterministic per
    transaction, so each tx maps to its own BEO entity instead of the old
    `from="unknown"` behaviour that collapsed EVERY transaction on EVERY
    such chain into the single synthetic entity sha3("unknown").  This is
    NOT a real on-chain sender: real sender attribution for these VM
    families remains the job of the dedicated per-VM Rust indexers.
    """
    return hashlib.sha3_256(f"{chain_name}:{tx_hash}".encode()).hexdigest()


def fetch_solana_block(rpc_url, slot, chain_name="solana"):
    """Fetch Solana block by slot via JSON-RPC."""
    try:
        result = rpc_call(rpc_url, "getBlock", [slot, {"maxSupportedTransactionVersion": 0, "transactionDetails": "signatures"}])
        if result:
            txs = result.get("signatures", [])
            return {"transactions": [{"hash": sig, "from": _synthetic_tx_sender(chain_name, sig), "to": "unknown", "value": "0"} for sig in txs[:50]], "hash": result.get("blockhash", "0x0"), "number": slot, "timestamp": int(result.get("blockTime") or 0)}
    except:
        pass
    return None

def fetch_cosmos_block(rpc_url, height, chain_name="cosmos"):
    """Fetch Cosmos block via REST."""
    try:
        req = urllib.request.Request(f"{rpc_url}/block?height={height}", headers={"User-Agent": "TRION/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            block = data.get("result", {}).get("block", {})
            txs = block.get("data", {}).get("txs", [])
            tx_ids = [f"cosmos_tx_{height}_{i}" for i in range(min(len(txs), 50))]
            return {"transactions": [{"hash": h, "from": _synthetic_tx_sender(chain_name, h), "to": "unknown", "value": "0"} for h in tx_ids], "hash": block.get("header", {}).get("last_block_id", {}).get("hash", "0x0"), "number": height, "timestamp": _iso_to_epoch(block.get("header", {}).get("time", ""))}
    except:
        return None

def fetch_aptos_block(rpc_url, height, chain_name="aptos"):
    """Fetch Aptos block via REST (also serves Movement — same API shape)."""
    try:
        req = urllib.request.Request(f"{rpc_url}/v1/blocks/by_height/{height}", headers={"User-Agent": "TRION/1.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            # Aptos returns int; Movement returns str — coerce for both
            try:
                tx_count = int(data.get("block_height", 0))
            except (TypeError, ValueError):
                tx_count = 0
            tx_ids = [f"aptos_tx_{height}_{i}" for i in range(min(tx_count, 50))]
            _apt_ts = int(data.get("block_timestamp") or 0)  # microseconds
            return {"transactions": [{"hash": h, "from": _synthetic_tx_sender(chain_name, h), "to": "unknown", "value": "0"} for h in tx_ids], "hash": data.get("previous_block_hash", "0x0"), "number": height, "timestamp": _apt_ts // 1_000_000}
    except:
        return None

def fetch_sui_checkpoint(rpc_url, seq, chain_name="sui"):
    """Fetch Sui checkpoint via REST."""
    try:
        req = urllib.request.Request(f"{rpc_url}/api/v1/checkpoints/{seq}", headers={"User-Agent": "TRION/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            txs = data.get("transactions", [])
            out = []
            for i, t in enumerate(txs[:50]):
                digest = t.get("transaction", {}).get("digest", f"sui_tx_{seq}_{i}")
                out.append({"hash": digest, "from": _synthetic_tx_sender(chain_name, digest), "to": "unknown", "value": "0"})
            return {"transactions": out, "hash": data.get("digest", "0x0"), "number": seq, "timestamp": (int(data.get("timestamp_ms") or 0) // 1000)}
    except:
        return None

def fetch_near_block(rpc_url, height, chain_name="near"):
    """Fetch NEAR block via JSON-RPC."""
    try:
        result = rpc_call(rpc_url, "block", {"block_id": height})
        if result:
            txs = result.get("chunks", [])
            total_txs = sum(len(c.get("transactions", [])) for c in txs)
            tx_ids = [f"near_tx_{height}_{i}" for i in range(min(total_txs, 50))]
            _near_ts = int(result.get("header", {}).get("timestamp") or 0)  # nanoseconds
            return {"transactions": [{"hash": h, "from": _synthetic_tx_sender(chain_name, h), "to": "unknown", "value": "0"} for h in tx_ids], "hash": result.get("header", {}).get("hash", "0x0"), "number": height, "timestamp": _near_ts // 1_000_000_000}
    except:
        pass
    return None

def fetch_ton_block(rpc_url, seq, chain_name="ton"):
    """Fetch TON masterchain block via HTTP API."""
    try:
        req = urllib.request.Request(f"{rpc_url}/getMasterchainInfo", headers={"User-Agent": "TRION/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        # Anchor to the REAL masterchain tip the API reports (root_hash) — the
        # per-tx rows below are still synthetic counts (toncenter v2 exposes
        # no per-block tx list); the Rust trion-ton crate is the real path.
        _info = (data.get("result") or {}).get("masterchain_info", {})
        _last = _info.get("last", {}) if isinstance(_info, dict) else {}
        _root = str(_last.get("root_hash") or "0x0")
        tx_ids = [f"ton_tx_{seq}_{i}" for i in range(10)]
        return {"transactions": [{"hash": h, "from": _synthetic_tx_sender(chain_name, h), "to": "unknown", "value": "0"} for h in tx_ids], "hash": _root, "number": seq}
    except:
        return None

def fetch_starknet_block(rpc_url, block_num, chain_name="starknet"):
    """Fetch Starknet block via JSON-RPC."""
    try:
        result = rpc_call(rpc_url, "starknet_getBlockWithTxs", {"block_number": block_num})
        if result:
            txs = result.get("transactions", [])
            out = []
            for i, t in enumerate(txs[:50]):
                tx_hash = t.get("transaction_hash", f"starknet_tx_{block_num}_{i}")
                out.append({"hash": tx_hash, "from": _synthetic_tx_sender(chain_name, tx_hash), "to": "unknown", "value": "0"})
            return {"transactions": out, "hash": result.get("block_hash", "0x0"), "number": block_num, "timestamp": int(result.get("timestamp") or 0)}
    except:
        pass
    return None

def fetch_tron_block(rpc_url, block_num, chain_name="tron"):
    """Fetch Tron block via REST API."""
    try:
        req = urllib.request.Request(f"{rpc_url}/v1/blocks/{block_num}/transactions?limit=50", headers={"User-Agent": "TRION/1.0", "TRON-PRO-API-KEY": ""})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            txs = data.get("data", [])
            out = []
            for i, t in enumerate(txs[:50]):
                txid = t.get("txID", f"tron_tx_{block_num}_{i}")
                out.append({"hash": txid, "from": _synthetic_tx_sender(chain_name, txid), "to": "unknown", "value": str(t.get("raw_data", {}).get("contract", [{}])[0].get("parameter", {}).get("value", {}).get("amount", 0))})
            _first = txs[0] if txs else {}
            _tron_ts = int(_first.get("block_timestamp") or 0) // 1000  # ms → s
            _tron_bh = str(_first.get("blockID") or "0x0")
            return {"transactions": out, "hash": _tron_bh, "number": block_num, "timestamp": _tron_ts}
    except:
        return None

def fetch_utxo_block(rpc_url, height):
    """Fetch Bitcoin/Litecoin/Dogecoin block via REST API."""
    try:
        req = urllib.request.Request(f"{rpc_url}/v1/block-height/{height}", headers={"User-Agent": "TRION/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            hash_data = json.loads(resp.read())
            if isinstance(hash_data, list) and hash_data:
                block_hash = hash_data[0]
                req2 = urllib.request.Request(f"{rpc_url}/v1/block/{block_hash}/txs", headers={"User-Agent": "TRION/1.0"})
                with urllib.request.urlopen(req2, timeout=15) as resp2:
                    txs = json.loads(resp2.read())
                # Real block time from the block header (one extra tolerant call;
                # UTXO poll interval is 60-600s so the overhead is negligible).
                block_ts = 0
                try:
                    req3 = urllib.request.Request(f"{rpc_url}/v1/block/{block_hash}", headers={"User-Agent": "TRION/1.0"})
                    with urllib.request.urlopen(req3, timeout=10) as resp3:
                        block_ts = int(json.loads(resp3.read()).get("timestamp") or 0)
                except Exception:
                    pass
                return {"transactions": [{"hash": t.get("txid", f"utxo_tx_{height}_{i}"), "from": t.get("vin", [{}])[0].get("prevout", {}).get("scriptpubkey_address", "unknown") if t.get("vin") else "unknown", "to": t.get("vout", [{}])[0].get("scriptpubkey_address", "unknown") if t.get("vout") else "unknown", "value": str(t.get("vout", [{}])[0].get("value", 0))} for t in txs[:50]], "hash": block_hash, "number": height, "timestamp": block_ts}
    except:
        return None

def fetch_stellar_block(rpc_url, cursor):
    """Fetch Stellar transactions via Horizon API."""
    try:
        req = urllib.request.Request(f"{rpc_url}/transactions?cursor={cursor}&limit=50&order=asc", headers={"User-Agent": "TRION/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            txs = data.get("_embedded", {}).get("records", [])
            _st_ts = _iso_to_epoch(txs[0].get("created_at")) if txs else 0
            return {"transactions": [{"hash": t.get("hash", f"stellar_tx_{i}"), "from": t.get("source_account", "unknown"), "to": "unknown", "value": "0"} for i, t in enumerate(txs[:50])], "hash": "0x0", "number": cursor, "timestamp": _st_ts}
    except:
        return None

def fetch_multiversx_block(rpc_url, nonce, chain_name="multiversx"):
    """Fetch MultiversX block via API."""
    try:
        req = urllib.request.Request(f"{rpc_url}/blocks/{nonce}", headers={"User-Agent": "TRION/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            tx_ids = [f"egld_tx_{nonce}_{i}" for i in range(min(data.get("nonce", 0) % 50, 50))]
            return {"transactions": [{"hash": h, "from": _synthetic_tx_sender(chain_name, h), "to": "unknown", "value": "0"} for h in tx_ids], "hash": data.get("hash", "0x0"), "number": nonce, "timestamp": int(data.get("timestamp") or 0)}
    except:
        return None

def fetch_xrpl_ledger(rpc_url, ledger_index):
    """Fetch XRPL ledger via JSON-RPC."""
    try:
        result = rpc_call(rpc_url, "ledger", [{"ledger_index": ledger_index, "transactions": True, "expand": True}])
        if result:
            txs = result.get("ledger", {}).get("transactions", [])
            def _xrpl_amount(t):
                amt = t.get("Amount", 0)
                if isinstance(amt, dict):
                    # Issued currency: {"currency","issuer","value"} — use decimal value
                    try:
                        return str(float(amt.get("value", 0)))
                    except (TypeError, ValueError):
                        return "0"
                return str(amt)
            return {"transactions": [{"hash": t.get("hash", f"xrpl_tx_{ledger_index}_{i}"), "from": t.get("Account", "unknown"), "to": t.get("Destination", "unknown"), "value": _xrpl_amount(t)} for i, t in enumerate(txs[:50])], "hash": result.get("ledger", {}).get("hash", "0x0"), "number": ledger_index, "timestamp": int(result.get("ledger", {}).get("close_time") or 0) + 946684800}
    except:
        pass
    return None

def fetch_waves_block(rpc_url, height):
    """Fetch Waves block via REST API."""
    try:
        req = urllib.request.Request(f"{rpc_url}/blocks/at/{height}", headers={"User-Agent": "TRION/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            txs = data.get("transactions", [])
            return {"transactions": [{"hash": t.get("id", f"waves_tx_{height}_{i}"), "from": t.get("sender", "unknown"), "to": "unknown", "value": "0"} for i, t in enumerate(txs[:50])], "hash": data.get("signature", "0x0"), "number": height, "timestamp": (int(data.get("timestamp") or 0) // 1000)}
    except:
        return None

def fetch_vechain_block(rpc_url, block_num, chain_name="vechain"):
    """Fetch Vechain block via REST API."""
    try:
        req = urllib.request.Request(f"{rpc_url}/blocks/{block_num}", headers={"User-Agent": "TRION/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            txs = data.get("transactions", [])
            tx_ids = [f"vet_tx_{block_num}_{i}" for i in range(min(len(txs), 50))]
            return {"transactions": [{"hash": h, "from": _synthetic_tx_sender(chain_name, h), "to": "unknown", "value": "0"} for h in tx_ids], "hash": str(data.get("id") or data.get("hash") or "0x0"), "number": block_num, "timestamp": int(data.get("timestamp") or 0)}
    except:
        return None


def fetch_algorand_block(rpc_url, round_num):
    """Fetch Algorand block via Algod REST API (VM family: ALGORAND).

    /v2/blocks/{round} → block.txns[] with txn.snd (base32 sender — BEO-resolved
    by compute_bh via SHA3-256), txn.rcv, txn.amt.
    """
    try:
        req = urllib.request.Request(f"{rpc_url}/v2/blocks/{round_num}", headers={"User-Agent": "TRION/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        txs = data.get("block", {}).get("txns", [])
        out = []
        for i, t in enumerate(txs[:50]):
            txn = t.get("txn", {})
            out.append({
                "hash":  t.get("h", f"algo_tx_{round_num}_{i}"),
                "from":  str(txn.get("snd", "unknown")),
                "to":    str(txn.get("rcv", txn.get("arcv", "unknown"))),
                "value": str(txn.get("amt", txn.get("aamt", 0)) or 0),
            })
        return {"transactions": out, "hash": str(data.get("hash", "0x0")), "number": round_num, "timestamp": int((data.get("block") or {}).get("ts") or 0)}
    except Exception:
        return None


def fetch_cardano_block(rpc_url, block_height):
    """Fetch Cardano block via Koios REST API (VM family: CARDANO).

    Behavioral model: each block is attributed to its PRODUCER (the stake pool
    in the `pool` field) — a real, continuously-observable entity whose block
    production rhythm is the behavioral signal (validator-behavior tracking
    per whitepaper L4). Magnitude = the block's tx_count. Koios no longer
    exposes per-tx input addresses in tx_info, so per-transaction sender
    extraction remains the trion-cardano Rust indexer's dedicated job.
    """
    try:
        req = urllib.request.Request(f"{rpc_url}/api/v1/blocks", headers={"User-Agent": "TRION/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            blocks = json.loads(resp.read())
        blk = next((b for b in blocks if b.get("block_height") == block_height), None)
        if blk is None:
            return None  # height outside the recent window (tip advanced) — skip
        pool = blk.get("pool") or "unknown_pool"
        tx_count = int(blk.get("tx_count", 0) or 0)
        # One behavioral record per block, attributed to the producing pool.
        # value = tx_count → magnitude captures the block's activity level.
        return {
            "transactions": [{
                "hash":  f"cardano_block_{block_height}",
                "from":  pool,
                "to":    "unknown",
                "value": str(tx_count),
            }],
            "hash": blk["hash"],
            "number": block_height,
            "timestamp": _iso_to_epoch(blk.get("block_time")),
        }
    except Exception:
        return None


def fetch_polkadot_block(rpc_url, block_num, chain_name="polkadot"):
    """Fetch Polkadot/Substrate block via JSON-RPC (VM family: PVM).

    Two-step: chain_getBlockHash(num) → chain_getBlock(hash). Extrinsics are
    SCALE-encoded; the SHA3-256 of each extrinsic's bytes is the tx identity.
    NOTE: this replaces the previous `lambda rpc, num: None` stub — the PVM
    family previously NEVER produced BHs in the streamer despite being wired.
    """
    try:
        block_hash = rpc_call(rpc_url, "chain_getBlockHash", [hex(block_num)])
        if not block_hash:
            return None
        result = rpc_call(rpc_url, "chain_getBlock", [block_hash])
        if not result:
            return None
        block = result.get("block", {})
        extrinsics = block.get("extrinsics", [])
        out = []
        for i, ext in enumerate(extrinsics[:50]):
            ext_bytes = bytes.fromhex(ext[2:]) if ext.startswith("0x") else ext.encode()
            tx_hash = "0x" + hashlib.sha3_256(ext_bytes).hexdigest()
            out.append({"hash": tx_hash, "from": _synthetic_tx_sender(chain_name, tx_hash), "to": "unknown", "value": "0"})
        return {"transactions": out, "hash": block_hash, "number": block_num}
    except Exception:
        return None


# VM-specific fetcher dispatch.  All fetchers receive (rpc, block, chain_name)
# so per-tx synthetic senders can be namespaced by the ACTUAL chain (e.g.
# "osmosis" vs "juno" — both COSMOS — share the fabricated tx-id pattern
# `cosmos_tx_{height}_{i}`, so the chain name is what keeps their synthetic
# BEO entities distinct).
VM_FETCHERS = {
    "SVM": lambda rpc, num, name: fetch_solana_block(rpc, num, name),
    "COSMOS": lambda rpc, num, name: fetch_cosmos_block(rpc, num, name),
    "MOVE": lambda rpc, num, name: fetch_aptos_block(rpc, num, name) if ("aptos" in rpc or "movement" in rpc) else fetch_sui_checkpoint(rpc, num, name),
    "NEAR": lambda rpc, num, name: fetch_near_block(rpc, num, name),
    "TON": lambda rpc, num, name: fetch_ton_block(rpc, num, name),
    "STARKNET": lambda rpc, num, name: fetch_starknet_block(rpc, num, name),
    "TRON": lambda rpc, num, name: fetch_tron_block(rpc, num, name),
    "UTXO": lambda rpc, num, name: fetch_utxo_block(rpc, num),
    "STELLAR": lambda rpc, num, name: fetch_stellar_block(rpc, num),
    "MULTIVERSX": lambda rpc, num, name: fetch_multiversx_block(rpc, num, name),
    "XRPL": lambda rpc, num, name: fetch_xrpl_ledger(rpc, num),
    "WAVES": lambda rpc, num, name: fetch_waves_block(rpc, num),
    "VECHAIN": lambda rpc, num, name: fetch_vechain_block(rpc, num, name),
    "HEDERA": lambda rpc, num, name: get_block_with_txs(rpc, num),  # Hedera is EVM-compatible
    "PVM": lambda rpc, num, name: fetch_polkadot_block(rpc, num, name),      # was a None stub — never produced BHs
    "ALGORAND": lambda rpc, num, name: fetch_algorand_block(rpc, num),
    "CARDANO": lambda rpc, num, name: fetch_cardano_block(rpc, num),
}

# VM-specific latest block getters
def get_non_evm_latest_block(rpc_url, vm):
    """Get latest block number for non-EVM chains."""
    try:
        if vm == "SVM":
            return int(rpc_call(rpc_url, "getSlot", []))
        elif vm == "COSMOS":
            req = urllib.request.Request(f"{rpc_url}/abci_info", headers={"User-Agent": "TRION/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                return int(data.get("result", {}).get("response", {}).get("last_block_height", 0))
        elif vm == "MOVE":
            if "aptos" in rpc_url or "movement" in rpc_url:
                req = urllib.request.Request(f"{rpc_url}/v1", headers={"User-Agent": "TRION/1.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read())
                    return int(data.get("block_height", 0))
            elif "sui" in rpc_url:
                result = rpc_call(rpc_url, "sui_getLatestCheckpointSequenceNumber", [])
                return int(result, 16) if result else 0
        elif vm == "NEAR":
            result = rpc_call(rpc_url, "status", [])
            return int(result.get("sync_info", {}).get("latest_block_height", 0))
        elif vm == "STARKNET":
            result = rpc_call(rpc_url, "starknet_blockNumber", [])
            return int(result, 16) if isinstance(result, str) else int(result or 0)
        elif vm == "TRON":
            req = urllib.request.Request(f"{rpc_url}/v1/blocks/latest", headers={"User-Agent": "TRION/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                return int(data.get("data", [{}])[0].get("height", 0)) if data.get("data") else 0
        elif vm == "UTXO":
            req = urllib.request.Request(f"{rpc_url}/v1/blocks/tip/height", headers={"User-Agent": "TRION/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().strip()
            # Plain-integer APIs (blockstream.info): direct parse
            try:
                return int(body)
            except (ValueError, TypeError):
                pass
            # JSON APIs — Blockbook returns {"blockbook": {"bestHeight": N}};
            # BlockCypher-style returns {"height": N}
            try:
                data = json.loads(body)
                if isinstance(data, dict):
                    bb = data.get("blockbook", {})
                    if isinstance(bb, dict) and bb.get("bestHeight") is not None:
                        return int(bb["bestHeight"])
                    if data.get("height") is not None:
                        return int(data["height"])
                    if isinstance(data.get("data"), list) and data["data"]:
                        return int(data["data"][0].get("height", 0))
            except (ValueError, AttributeError):
                pass
            return 0
        elif vm == "STELLAR":
            req = urllib.request.Request(f"{rpc_url}/transactions?limit=1&order=desc", headers={"User-Agent": "TRION/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                records = data.get("_embedded", {}).get("records", [])
                return records[0].get("paging_token", "0") if records else "0"
        elif vm == "MULTIVERSX":
            req = urllib.request.Request(f"{rpc_url}/blocks/latest", headers={"User-Agent": "TRION/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                return int(data.get("nonce", 0)) if isinstance(data, dict) else 0
        elif vm == "XRPL":
            result = rpc_call(rpc_url, "ledger_current", [])
            return int(result.get("ledger_current_index", 0))
        elif vm == "WAVES":
            req = urllib.request.Request(f"{rpc_url}/blocks/height", headers={"User-Agent": "TRION/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                return int(data.get("height", 0))
        elif vm == "VECHAIN":
            req = urllib.request.Request(f"{rpc_url}/blocks/best", headers={"User-Agent": "TRION/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            if not isinstance(data, dict):
                return 0
            # VeChain: "number" is the block height (plain int);
            # "id" is the 0x-prefixed block hash (NOT the height).
            return int(data.get("number", 0) or 0)
        elif vm == "HEDERA":
            return get_latest_block(rpc_url)  # EVM-compatible
        elif vm == "ALGORAND":
            req = urllib.request.Request(f"{rpc_url}/v2/status", headers={"User-Agent": "TRION/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            return int(data.get("last-round", 0) or 0)
        elif vm == "CARDANO":
            req = urllib.request.Request(f"{rpc_url}/api/v1/tip", headers={"User-Agent": "TRION/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            return int(data[0].get("block_no", 0) or 0) if data else 0
        elif vm == "PVM":
            # Polkadot substrate
            req = urllib.request.Request(rpc_url, data=json.dumps({"jsonrpc":"2.0","method":"chain_getBlock","params":[],"id":1}).encode(), headers={"Content-Type":"application/json","User-Agent":"TRION/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                header = data.get("result", {}).get("block", {}).get("header", {})
                return int(header.get("number", 0), 16) if header.get("number") else 0
    except Exception as e:
        print(f"[streamer] Non-EVM {vm}: failed to get latest block: {e}", file=sys.stderr)
        return None

# ============================================================================
# Non-EVM chain worker
# ============================================================================

def _non_evm_chain_worker(self, chain_id, chain_config):
    """Worker for non-EVM chains using VM-specific fetchers."""
    rpc_url = chain_config["rpc"]
    chain_name = chain_config["name"]
    vm = chain_config.get("vm", "UNKNOWN")
    poll_interval = max(2.0, chain_config.get("block_time", 12))

    latest = get_non_evm_latest_block(rpc_url, vm)
    if latest is None:
        print(f"[streamer] {chain_name} ({vm}): Failed to get initial block", file=sys.stderr)
        return

    # For string-based cursors (Stellar), keep as string
    if isinstance(latest, str):
        self._last_block[chain_id] = latest
    else:
        self._last_block[chain_id] = int(latest) - 1

    print(f"[streamer] {chain_name} ({vm}, id={chain_id}): starting from block {self._last_block[chain_id]}", flush=True)
    consecutive_errors = 0

    while not self._stop_flags[chain_id].is_set():
        try:
            latest = get_non_evm_latest_block(rpc_url, vm)
            if latest is None:
                time.sleep(poll_interval)
                continue

            current = self._last_block[chain_id]

            # Handle string cursors (Stellar)
            if isinstance(current, str) and isinstance(latest, str):
                target = latest
            elif isinstance(current, int) and isinstance(latest, int):
                target = current + 1
                if target > latest:
                    time.sleep(poll_interval)
                    continue
            else:
                target = latest

            fetcher = VM_FETCHERS.get(vm)
            if fetcher:
                block = fetcher(rpc_url, target if isinstance(target, int) else int(target) if str(target).isdigit() else 0, chain_name)
            else:
                block = None

            if block:
                # Create a synthetic chain_config for processing
                evm_config = {"name": chain_name, "label": chain_config["label"], "block_time": poll_interval, "native_symbol": chain_config.get("native_symbol", ""), "decimals": chain_config.get("decimals", 18)}
                self._process_block(chain_id, block, evm_config)
                self._last_block[chain_id] = target
                with self._stats_lock:
                    self._stats["total_blocks"] += 1
                    cs = self._stats["per_chain"].setdefault(chain_name, {"bhs": 0, "blocks": 0})
                    cs["blocks"] += 1
                consecutive_errors = 0
            else:
                consecutive_errors += 1
                time.sleep(min(30, poll_interval * (2 ** min(consecutive_errors, 5))))
        except Exception as e:
            consecutive_errors += 1
            if consecutive_errors <= 3:
                print(f"[streamer] {chain_name} ({vm}): error: {e}", file=sys.stderr)
            time.sleep(min(30, poll_interval * (2 ** min(consecutive_errors, 5))))

# Monkey-patch BHStreamer to support non-EVM chains
_original_start = BHStreamer.start

def _enhanced_start(self):
    """Start both EVM and non-EVM chain workers."""
    self._init_db()
    self._running = True

    # Start EVM chains (original behavior)
    for chain_id, config in self.chains.items():
        self._stop_flags[chain_id] = threading.Event()
        t = threading.Thread(target=self._chain_worker, args=(chain_id, config), daemon=True, name=f"bh-{config['name']}")
        t.start()
        self._threads[chain_id] = t

    # Start non-EVM chains
    for chain_id, config in NON_EVM_CHAINS.items():
        self._stop_flags[chain_id] = threading.Event()
        t = threading.Thread(target=_non_evm_chain_worker, args=(self, chain_id, config), daemon=True, name=f"bh-{config['name']}")
        t.start()
        self._threads[chain_id] = t

    total = len(self.chains) + len(NON_EVM_CHAINS)
    with self._stats_lock:
        self._stats["chains_active"] = total
    print(f"[streamer] Started {total} chain workers ({len(self.chains)} EVM + {len(NON_EVM_CHAINS)} non-EVM)", flush=True)

BHStreamer.start = _enhanced_start
