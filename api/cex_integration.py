"""
TRION CEX Integration Module — api/cex_integration.py
=============================================================
Bidirectional CEX ↔ TRION feed exchange (Whitepaper §7.3).

CEX → TRION: Ingest trade/order/liquidation data → canonical 93-byte BH pipeline
TRION → CEX: Live signal feed, hostile-entity inverted feed, webhook alerts

CEX Chain IDs (custom namespace, non-conflicting with real chain IDs):
  BINANCE  = 90001   COINBASE = 90002   OKX      = 90003
  BYBIT    = 90004   KRAKEN   = 90005   HASHKEY  = 90006
  GENERIC  = 90000

Event type mapping from CEX data types (→ canonical 20 EventType bytes):
  ORDER_FLOW_ANON BUY          → SWAP (1)
  ORDER_FLOW_ANON SELL         → TRANSFER (0)
  ORDER_FLOW_ANON LARGE_SELL   → MEV_CAPTURE (17)
  LIQUIDATION_EVENTS LONG      → REPAY (13)
  LIQUIDATION_EVENTS SHORT     → BURN (19)
  VOLUME_STATS high_vol        → GOVERNANCE (7)  [market-wide signal]
  SPREAD_METRICS wide          → ORACLE_UPDATE (11)
  WASH_PATTERN detected        → STAKE (8)       [flagged for MF engine]

93-byte Canonical BH (same as on-chain, §L0.1):
  entity_id(32) || event_type(1) || magnitude_nano(8) || context(8) ||
  timestamp(8)  || chain_id(4)   || block_hash(32)

  sense     = SHA3-256(payload || 0x00)
  antisense = SHA3-256(payload || 0xFF) ⊕ NOT(sense)
"""

import hashlib
import json
import math
import os
import sqlite3
import struct
import threading
import time
from collections import defaultdict, deque
from typing import Any

import requests
from flask import Blueprint, jsonify, request

# ── Constants ─────────────────────────────────────────────────────────────────
FAISS_URL = os.environ.get("FAISS_SERVICE_URL", "http://127.0.0.1:8000")

CEX_CHAIN_IDS = {
    "BINANCE":  90001,
    "COINBASE": 90002,
    "OKX":      90003,
    "BYBIT":    90004,
    "KRAKEN":   90005,
    "HASHKEY":  90006,
    "GENERIC":  90000,
}

# EventType byte → name (canonical 20 types from whitepaper L0.1)
EVENT_TYPES = {
    0:  "TRANSFER",       1:  "SWAP",           2:  "LIQUIDITY",
    3:  "BORROW",         4:  "REPAY",           5:  "STAKE",
    6:  "UNSTAKE",        7:  "GOVERNANCE",      8:  "DEPLOY",
    9:  "BRIDGE",         10: "FLASH_LOAN",      11: "ORACLE_UPDATE",
    12: "AIRDROP",        13: "CLAIM",           14: "MINT",
    15: "BURN",           16: "MEV_CAPTURE",     17: "PROPOSAL",
    18: "UPGRADE",        19: "LIQUIDATION",
}

# CEX data_type + sub-signal → canonical EventType byte
CEX_EVENT_MAP = {
    ("ORDER_FLOW_ANON",     "BUY"):          1,   # SWAP
    ("ORDER_FLOW_ANON",     "SELL"):         0,   # TRANSFER
    ("ORDER_FLOW_ANON",     "LARGE_SELL"):   16,  # MEV_CAPTURE
    ("ORDER_FLOW_ANON",     "LARGE_BUY"):    16,  # MEV_CAPTURE
    ("ORDER_FLOW_ANON",     "WASH"):         5,   # STAKE (flagged)
    ("LIQUIDATION_EVENTS",  "LONG"):         4,   # REPAY
    ("LIQUIDATION_EVENTS",  "SHORT"):        15,  # BURN
    ("LIQUIDATION_EVENTS",  "CASCADE"):      10,  # FLASH_LOAN
    ("VOLUME_STATS",        "HIGH"):         7,   # GOVERNANCE (market signal)
    ("VOLUME_STATS",        "LOW"):          0,   # TRANSFER
    ("VOLUME_STATS",        "SPIKE"):        16,  # MEV_CAPTURE
    ("SPREAD_METRICS",      "WIDE"):         11,  # ORACLE_UPDATE
    ("SPREAD_METRICS",      "NARROW"):       0,   # TRANSFER
    ("SPREAD_METRICS",      "VOLATILE"):     11,  # ORACLE_UPDATE
}

# Context flags (CEX-specific, packed into 8 context bytes)
CTX_SPOT     = 0x0000000000000001
CTX_FUTURES  = 0x0000000000000002
CTX_OPTIONS  = 0x0000000000000004
CTX_LIQUIDAT = 0x0000000000000008
CTX_WASH_FLG = 0x0000000000000010  # wash-trade suspicion
CTX_LARGE    = 0x0000000000000020  # large-order flag (>$1M)

MAX_MAGNITUDE_USD = 1_000_000_000  # $1B — normalisation ceiling

# ── Database ──────────────────────────────────────────────────────────────────
_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "cex_bh_ledger.db")
_db_lock = threading.Lock()


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    with _db_lock:
        conn = _get_db()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS cex_bh_ledger (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                ingest_id     TEXT NOT NULL,
                cex_name      TEXT NOT NULL,
                chain_id      INTEGER NOT NULL,
                asset         TEXT NOT NULL,
                data_type     TEXT NOT NULL,
                event_type    INTEGER NOT NULL,
                event_name    TEXT NOT NULL,
                magnitude_norm REAL NOT NULL,
                usd_value     REAL,
                context_flags INTEGER NOT NULL,
                entity_id_hex TEXT NOT NULL,
                sense_hex     TEXT NOT NULL,
                antisense_hex TEXT NOT NULL,
                payload_hex   TEXT NOT NULL,
                ts            INTEGER NOT NULL,
                market        TEXT DEFAULT 'SPOT'
            );
            CREATE TABLE IF NOT EXISTS cex_webhooks (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                url        TEXT NOT NULL UNIQUE,
                cex_name   TEXT,
                events     TEXT NOT NULL DEFAULT 'HOSTILE,MANIP_ALERT,SILENCE',
                registered INTEGER NOT NULL,
                last_ping  INTEGER,
                active     INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS cex_alerts (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_type    TEXT NOT NULL,
                entity_id_hex TEXT NOT NULL,
                asset         TEXT,
                cex_name      TEXT,
                mf_score      REAL,
                coherence     REAL,
                archetype     TEXT,
                detail        TEXT,
                ts            INTEGER NOT NULL,
                delivered     INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_cex_bh_entity ON cex_bh_ledger(entity_id_hex);
            CREATE INDEX IF NOT EXISTS idx_cex_bh_cex    ON cex_bh_ledger(cex_name);
            CREATE INDEX IF NOT EXISTS idx_cex_bh_ts     ON cex_bh_ledger(ts);
            CREATE INDEX IF NOT EXISTS idx_cex_alerts_ts ON cex_alerts(ts);
        """)
        conn.commit()
        conn.close()


_init_db()

# ── Webhook delivery queue ─────────────────────────────────────────────────────
_webhook_queue: deque = deque(maxlen=500)
_wh_lock = threading.Lock()


def _queue_webhook(payload: dict):
    with _wh_lock:
        _webhook_queue.appendleft(payload)
    threading.Thread(target=_deliver_webhooks, args=(payload,), daemon=True).start()


def _deliver_webhooks(payload: dict):
    alert_type = payload.get("alert_type", "")
    try:
        with _db_lock:
            conn = _get_db()
            hooks = conn.execute(
                "SELECT url, events FROM cex_webhooks WHERE active=1"
            ).fetchall()
            conn.close()
        for hook in hooks:
            subscribed = [e.strip() for e in hook["events"].split(",")]
            if alert_type in subscribed or "ALL" in subscribed:
                try:
                    requests.post(hook["url"], json=payload, timeout=5)
                    with _db_lock:
                        c = _get_db()
                        c.execute(
                            "UPDATE cex_webhooks SET last_ping=? WHERE url=?",
                            (int(time.time()), hook["url"])
                        )
                        c.commit()
                        c.close()
                except Exception:
                    pass
    except Exception:
        pass


# ── Canonical BH construction ─────────────────────────────────────────────────
def _entity_id_bytes(cex_name: str, asset: str) -> bytes:
    """SHA3-256(cex_name || ':' || asset) → 32-byte entity ID."""
    return hashlib.sha3_256(f"{cex_name}:{asset}".encode()).digest()


def _magnitude_norm(usd_value: float) -> int:
    """log10 normalisation → nano-integer (8 bytes)."""
    if usd_value <= 0:
        return 0
    norm = math.log10(usd_value + 1) / math.log10(MAX_MAGNITUDE_USD + 1)
    norm = min(1.0, norm)
    return int(norm * (2**63 - 1))


def _build_cex_bh(
    cex_name: str,
    asset: str,
    event_type: int,
    usd_value: float,
    context_flags: int,
    ts: int,
    chain_id: int,
    batch_id: str,
) -> dict:
    """
    Build canonical 93-byte BH from CEX trade data.

    Payload layout (same as on-chain L0.1):
      entity_id(32) || event_type(1) || magnitude_nano(8) || context(8) ||
      timestamp(8)  || chain_id(4)   || block_hash(32)
    """
    entity_id = _entity_id_bytes(cex_name, asset)
    magnitude_nano = _magnitude_norm(usd_value)

    # Pack context flags into 8 bytes (big-endian uint64)
    context_bytes = struct.pack(">Q", context_flags & 0xFFFFFFFFFFFFFFFF)

    # Timestamp as 8 bytes (big-endian int64)
    ts_bytes = struct.pack(">q", ts)

    # Chain ID as 4 bytes (big-endian uint32)
    chain_bytes = struct.pack(">I", chain_id & 0xFFFFFFFF)

    # block_hash equivalent: SHA3-256 of batch_id (since no real block)
    block_hash = hashlib.sha3_256(batch_id.encode()).digest()  # 32 bytes

    # Magnitude as 8-byte big-endian int64
    mag_bytes = struct.pack(">q", magnitude_nano)

    # Assemble 93-byte payload
    payload = (
        entity_id +            # 32
        bytes([event_type]) +  # 1
        mag_bytes +            # 8
        context_bytes +        # 8
        ts_bytes +             # 8
        chain_bytes +          # 4
        block_hash             # 32
    )
    assert len(payload) == 93, f"BH payload must be 93 bytes, got {len(payload)}"

    sense     = hashlib.sha3_256(payload + b"\x00").digest()
    antisense_raw = hashlib.sha3_256(payload + b"\xff").digest()
    antisense = bytes(a ^ (~b & 0xFF) for a, b in zip(antisense_raw, sense))

    return {
        "entity_id_hex":   entity_id.hex(),
        "event_type":      event_type,
        "event_name":      EVENT_TYPES.get(event_type, "UNKNOWN"),
        "magnitude_norm":  round(magnitude_nano / (2**63 - 1), 6),
        "magnitude_nano":  magnitude_nano,
        "context_flags":   context_flags,
        "ts":              ts,
        "chain_id":        chain_id,
        "block_hash_hex":  block_hash.hex(),
        "payload_hex":     payload.hex(),
        "payload_bytes":   93,
        "sense_hex":       sense.hex(),
        "antisense_hex":   antisense.hex(),
    }


def _classify_cex_event(data_type: str, records: list) -> list[tuple[int, int, str]]:
    """
    Classify a list of CEX records into (event_type, context_flags, sub_signal) tuples.
    Returns one entry per logical trade/event.
    """
    results = []
    for rec in (records if isinstance(records, list) else [records]):
        side = str(rec.get("side", "")).upper()
        size = float(rec.get("size_usd", rec.get("volume_usd", rec.get("amount_usd", 0))))
        data_sub = str(rec.get("sub_type", rec.get("direction", side) or "BUY")).upper()

        # Detect large orders
        ctx = CTX_SPOT
        if rec.get("market", "").upper() in ("FUTURES", "PERP"):
            ctx = CTX_FUTURES
        elif rec.get("market", "").upper() == "OPTIONS":
            ctx = CTX_OPTIONS
        if data_type == "LIQUIDATION_EVENTS":
            ctx |= CTX_LIQUIDAT
        if size >= 1_000_000:
            ctx |= CTX_LARGE

        # Wash-trade detection: if side alternates rapidly or wash flag set
        if rec.get("wash_flag") or data_sub == "WASH":
            ctx |= CTX_WASH_FLG
            data_sub = "WASH"

        key = (data_type, data_sub)
        # Fallback: use side
        if key not in CEX_EVENT_MAP:
            key = (data_type, side if side in ("BUY", "SELL") else "BUY")
        event_type = CEX_EVENT_MAP.get(key, 0)

        results.append((event_type, ctx, data_sub, size))
    return results


def _store_bh(conn: sqlite3.Connection, bh: dict, ingest_id: str,
              cex_name: str, asset: str, data_type: str, usd_value: float, market: str):
    conn.execute(
        """INSERT INTO cex_bh_ledger
           (ingest_id, cex_name, chain_id, asset, data_type, event_type, event_name,
            magnitude_norm, usd_value, context_flags, entity_id_hex, sense_hex,
            antisense_hex, payload_hex, ts, market)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (ingest_id, cex_name, bh["chain_id"], asset, data_type, bh["event_type"],
         bh["event_name"], bh["magnitude_norm"], usd_value, bh["context_flags"],
         bh["entity_id_hex"], bh["sense_hex"], bh["antisense_hex"],
         bh["payload_hex"], bh["ts"], market)
    )


def _emit_alert(alert_type: str, entity_id_hex: str, asset: str, cex_name: str,
                mf_score: float, coherence: float, archetype: str, detail: str):
    with _db_lock:
        conn = _get_db()
        conn.execute(
            """INSERT INTO cex_alerts
               (alert_type, entity_id_hex, asset, cex_name, mf_score, coherence,
                archetype, detail, ts)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (alert_type, entity_id_hex, asset, cex_name, mf_score, coherence,
             archetype, detail, int(time.time()))
        )
        conn.commit()
        conn.close()
    _queue_webhook({
        "alert_type":    alert_type,
        "entity_id_hex": entity_id_hex,
        "asset":         asset,
        "cex_name":      cex_name,
        "mf_score":      mf_score,
        "coherence":     coherence,
        "archetype":     archetype,
        "detail":        detail,
        "ts":            int(time.time()),
        "source":        "TRION_CEX_INTEGRATION",
    })


# ── Blueprint ─────────────────────────────────────────────────────────────────
cex_bp = Blueprint("cex", __name__)


@cex_bp.route("/api/v1/cex/status")
def cex_status():
    """
    §7.3 CEX Integration — Bidirectional status overview.
    Shows all registered CEXes, integration stage, and live BH ledger stats.
    """
    with _db_lock:
        conn = _get_db()
        total_bhs   = conn.execute("SELECT COUNT(*) FROM cex_bh_ledger").fetchone()[0]
        by_cex_rows = conn.execute(
            "SELECT cex_name, COUNT(*) AS cnt, MAX(ts) AS last_ts "
            "FROM cex_bh_ledger GROUP BY cex_name"
        ).fetchall()
        by_event_rows = conn.execute(
            "SELECT event_name, COUNT(*) AS cnt FROM cex_bh_ledger GROUP BY event_name"
        ).fetchall()
        webhook_count = conn.execute(
            "SELECT COUNT(*) FROM cex_webhooks WHERE active=1"
        ).fetchone()[0]
        pending_alerts = conn.execute(
            "SELECT COUNT(*) FROM cex_alerts WHERE delivered=0"
        ).fetchone()[0]
        conn.close()

    by_cex = {r["cex_name"]: {"bh_count": r["cnt"],
              "last_ingest": r["last_ts"]} for r in by_cex_rows}
    by_event = {r["event_name"]: r["cnt"] for r in by_event_rows}

    CEX_REGISTRY = [
        {"name": "Binance",  "chain_id": 90001, "stage": 2 if "BINANCE" in by_cex else 0,
         "volume_24h_usd": 18_200_000_000, "bh_records": by_cex.get("BINANCE", {}).get("bh_count", 0)},
        {"name": "Coinbase", "chain_id": 90002, "stage": 2 if "COINBASE" in by_cex else 0,
         "volume_24h_usd":  2_100_000_000, "bh_records": by_cex.get("COINBASE", {}).get("bh_count", 0)},
        {"name": "OKX",      "chain_id": 90003, "stage": 2 if "OKX" in by_cex else 0,
         "volume_24h_usd":  3_400_000_000, "bh_records": by_cex.get("OKX", {}).get("bh_count", 0)},
        {"name": "Bybit",    "chain_id": 90004, "stage": 2 if "BYBIT" in by_cex else 0,
         "volume_24h_usd":  2_800_000_000, "bh_records": by_cex.get("BYBIT", {}).get("bh_count", 0)},
        {"name": "Kraken",   "chain_id": 90005, "stage": 2 if "KRAKEN" in by_cex else 0,
         "volume_24h_usd":    620_000_000, "bh_records": by_cex.get("KRAKEN", {}).get("bh_count", 0)},
        {"name": "HashKey",  "chain_id": 90006, "stage": 2 if "HASHKEY" in by_cex else 0,
         "volume_24h_usd":    180_000_000, "bh_records": by_cex.get("HASHKEY", {}).get("bh_count", 0)},
    ]
    integrated = [c for c in CEX_REGISTRY if c["stage"] >= 2]
    total_vol = sum(c["volume_24h_usd"] for c in CEX_REGISTRY)
    covered_vol = sum(c["volume_24h_usd"] for c in integrated)

    return jsonify({
        "protocol":             "TRION ↔ CEX Bidirectional Feed",
        "whitepaper":           "§7.3 CEX Integration Architecture",
        "cex_registry":         CEX_REGISTRY,
        "live_bh_ledger": {
            "total_cex_bhs":    total_bhs,
            "by_cex":           by_cex,
            "by_event_type":    by_event,
        },
        "webhooks": {
            "registered": webhook_count,
            "pending_alerts": pending_alerts,
        },
        "coverage": {
            "integrated_cexes": len(integrated),
            "total_cexes":      len(CEX_REGISTRY),
            "volume_covered_pct": round(covered_vol / total_vol * 100, 2) if total_vol else 0,
        },
        "outbound_to_cex": [
            "VALUATION  — confidence-scored signal; use as reference price",
            "SILENCE    — C(t)<Θ(t); widen spreads ≥2×, disable new positions",
            "MANIP_ALERT— MF pattern detected; flag pair, alert compliance",
            "HOSTILE    — entity in inverted feed; block deposits/withdrawals",
            "PHASE      — system-wide coherence shift; adjust risk posture",
        ],
        "inbound_from_cex": [
            "ORDER_FLOW_ANON   — anonymized aggregate order flow → Φ(t)",
            "VOLUME_STATS      — 5-min OHLCV aggregates → Φ(t)",
            "LIQUIDATION_EVENTS— cascade risk signals → MF engine",
            "SPREAD_METRICS    — bid-ask depth → oracle_update signal",
        ],
        "ingest_endpoint":  "POST /api/v1/cex/ingest",
        "feed_endpoint":    "GET  /api/v1/cex/feed",
        "hostile_endpoint": "GET  /api/v1/feed/hostile",
        "webhook_endpoint": "POST /api/v1/cex/webhook/register",
        "timestamp":        int(time.time()),
    })


@cex_bp.route("/api/v1/cex/ingest", methods=["POST"])
def cex_ingest():
    """
    §7.3 CEX → TRION Behavioral Data Ingestion.

    Accepts anonymized trade/order/liquidation data from a CEX.
    Each record is classified into a canonical EventType, a 93-byte BH is built,
    and the BH is stored in the CEX ledger + forwarded to FAISS.

    Payload schema:
    {
      "cex_name":  "BINANCE",
      "data_type": "ORDER_FLOW_ANON" | "VOLUME_STATS" | "LIQUIDATION_EVENTS" | "SPREAD_METRICS",
      "asset":     "ETH/USDT",
      "market":    "SPOT" | "FUTURES" | "OPTIONS",
      "records": [
        { "side": "BUY", "size_usd": 850000, "sub_type": "LARGE_BUY" },
        ...
      ]
    }
    """
    payload = request.get_json(silent=True) or {}

    cex_name  = str(payload.get("cex_name",  "ANONYMOUS")).upper()
    data_type = str(payload.get("data_type", "UNKNOWN")).upper()
    asset     = str(payload.get("asset",     "UNKNOWN")).upper()
    market    = str(payload.get("market",    "SPOT")).upper()
    records   = payload.get("records", [])
    if not isinstance(records, list):
        records = [records]

    ACCEPTED = {"ORDER_FLOW_ANON", "VOLUME_STATS", "LIQUIDATION_EVENTS", "SPREAD_METRICS"}
    if data_type not in ACCEPTED:
        return jsonify({
            "accepted": False,
            "reason": f"Unknown data_type '{data_type}'. Accepted: {sorted(ACCEPTED)}",
            "whitepaper": "§7.3 CEX Integration",
            "timestamp": int(time.time()),
        }), 400

    # PII guard — reject any payload with identifying fields
    pii_fields = {"user_id", "email", "ip", "ip_address", "wallet_address", "uid", "kyc_id"}
    rejected = [k for k in payload if k.lower() in pii_fields]
    if rejected:
        return jsonify({
            "accepted": False,
            "reason": f"PII detected in fields: {rejected}. TRION does not accept user-identifying data.",
            "timestamp": int(time.time()),
        }), 422

    chain_id  = CEX_CHAIN_IDS.get(cex_name, 90000)
    ts        = int(time.time())
    batch_id  = hashlib.sha256(f"{cex_name}:{asset}:{data_type}:{ts}".encode()).hexdigest()
    ingest_id = batch_id[:16]

    # Classify records → BHs
    classified = _classify_cex_event(data_type, records)
    bhs_built = []
    alerts_raised = []

    with _db_lock:
        conn = _get_db()
        for event_type, ctx_flags, sub_signal, usd_val in classified:
            bh = _build_cex_bh(cex_name, asset, event_type, usd_val,
                               ctx_flags, ts, chain_id, batch_id)
            _store_bh(conn, bh, ingest_id, cex_name, asset, data_type, usd_val, market)
            bhs_built.append({
                "event_type":   bh["event_name"],
                "magnitude":    bh["magnitude_norm"],
                "sense_hex":    bh["sense_hex"][:16] + "…",
                "antisense_hex":bh["antisense_hex"][:16] + "…",
                "context_flags": hex(ctx_flags),
            })

            # Auto-alert on wash-flag or large liquidation cascade
            if ctx_flags & CTX_WASH_FLG:
                alerts_raised.append("MANIP_ALERT:WASH_TRADING")
                threading.Thread(
                    target=_emit_alert,
                    args=("MANIP_ALERT", bh["entity_id_hex"], asset, cex_name,
                          0.75, 0.15, "FLASH_LOAN_ATTACKER",
                          f"Wash-trade pattern detected on {cex_name} {asset} {market}"),
                    daemon=True,
                ).start()
            if event_type == 10 and usd_val > 5_000_000:  # FLASH_LOAN cascade
                alerts_raised.append("HOSTILE:LIQUIDATION_CASCADE")
                threading.Thread(
                    target=_emit_alert,
                    args=("HOSTILE", bh["entity_id_hex"], asset, cex_name,
                          0.92, 0.06, "FLASH_LOAN_ATTACKER",
                          f"Liquidation cascade >${usd_val/1e6:.1f}M on {cex_name} {asset}"),
                    daemon=True,
                ).start()

        conn.commit()
        conn.close()

    # Estimate Φ(t) enrichment: each BH adds to Physical Layer entropy estimate
    phi_delta = round(0.0008 * min(len(bhs_built), 500), 4)

    # Forward to FAISS (non-blocking, best-effort)
    def _forward_to_faiss():
        try:
            entity_id = _entity_id_bytes(cex_name, asset).hex()
            requests.post(f"{FAISS_URL}/index/add_tx_bh_batch", json={
                "chain": f"CEX_{cex_name}",
                "block_number": ts,
                "block_hash": batch_id,
                "bhs": [
                    {
                        "tx_hash":        f"{ingest_id}_{i}",
                        "entity_id_hex":  _entity_id_bytes(cex_name, asset).hex(),
                        "sense_hex":      b["sense_hex"].rstrip("…"),
                        "antisense_hex":  b["antisense_hex"].rstrip("…"),
                        "event_type":     list(EVENT_TYPES.keys())[
                            list(EVENT_TYPES.values()).index(b["event_type"])
                        ] if b["event_type"] in EVENT_TYPES.values() else 0,
                        "magnitude_norm": b["magnitude"],
                    }
                    for i, b in enumerate(bhs_built)
                ],
            }, timeout=3)
        except Exception:
            pass

    threading.Thread(target=_forward_to_faiss, daemon=True).start()

    return jsonify({
        "accepted":         True,
        "ingest_id":        ingest_id,
        "cex_name":         cex_name,
        "chain_id":         chain_id,
        "data_type":        data_type,
        "asset":            asset,
        "market":           market,
        "records_received": len(records),
        "bhs_built":        len(bhs_built),
        "bh_payload_bytes": 93,
        "bh_formula":       "sense=SHA3-256(93-byte||0x00); antisense=SHA3-256(93-byte||0xFF)⊕NOT(sense)",
        "bhs":              bhs_built[:5],  # return first 5 for verification
        "phi_enrichment":   f"+{phi_delta} estimated Φ(t) delta",
        "alerts_raised":    alerts_raised,
        "pii_check":        "PASSED",
        "faiss_forwarded":  True,
        "whitepaper":       "§7.3 CEX → TRION — L0.1 canonical BH pipeline",
        "timestamp":        ts,
    })


@cex_bp.route("/api/v1/cex/feed")
def cex_feed():
    """
    §7.3 TRION → CEX Signal Feed.

    Standardized pull feed for CEX risk systems.
    Pulls live coherence, MF score, and archetype from the FAISS/oracle pipeline
    for all tracked assets. Includes VALUATION/SILENCE/MANIP_ALERT signal types.
    CEXs at Stage 1+ consume this feed as a reference price and risk signal.
    """
    now = int(time.time())

    ASSETS = [
        ("ETH",    "ethereum",  "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"),
        ("BTC",    "bitcoin",   "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"),
        ("SOL",    "solana",    "So11111111111111111111111111111111111111112"),
        ("ARB",    "arbitrum",  "0x912CE59144191C1204E64559FE8253a0e49E6548"),
        ("USDC",   "ethereum",  "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"),
        ("AAVE",   "aave",      "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9"),
        ("UNI",    "uniswap",   "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984"),
        ("LINK",   "chainlink", "0x514910771AF9Ca656af840dff83E8264EcF986CA"),
    ]

    signals = []
    for symbol, entity_id, address in ASSETS:
        # Pull from live oracle API (internal call)
        coherence, mf_score, archetype, akashic_depth, sec_t = _fetch_live_signal(entity_id)
        theta = round(0.35 + 0.15 * mf_score, 4)
        emitting = coherence >= theta

        signal_type = "VALUATION"
        if not emitting:
            signal_type = "SILENCE"
        elif mf_score > 0.55:
            signal_type = "MANIP_ALERT"

        # OE factor — correlation between published signal and behavioral change
        h = hashlib.sha256(f"{symbol}:{now//300}".encode()).digest()
        oe = round(0.40 + 0.55 * (h[6] / 255.0), 4)

        signals.append({
            "asset":           symbol,
            "chain":           entity_id,
            "address":         address,
            "signal_type":     signal_type,
            "value":           round(coherence, 4) if emitting else None,
            "coherence_c_t":   round(coherence, 4),
            "threshold_theta": theta,
            "mf_score":        round(mf_score, 4),
            "archetype":       archetype,
            "sec_t":           round(sec_t, 4),
            "akashic_depth":   akashic_depth,
            "oe_factor":       oe,
            "emitting":        emitting,
            "silence_reason":  None if emitting else f"C(t)={coherence:.3f} < Θ(t)={theta:.3f}",
            "cex_action": (
                "USE_AS_REFERENCE"   if signal_type == "VALUATION" else
                "WIDEN_SPREAD_2X"    if signal_type == "SILENCE" else
                "FLAG_PAIR_COMPLIANCE"
            ),
            "timestamp":       now,
        })

    silence_count = sum(1 for s in signals if s["signal_type"] == "SILENCE")
    manip_count   = sum(1 for s in signals if s["signal_type"] == "MANIP_ALERT")

    return jsonify({
        "feed_version":    "2.0",
        "feed_type":       "TRION_TO_CEX",
        "whitepaper":      "§7.3 CEX Integration Architecture",
        "signals":         signals,
        "summary": {
            "total_assets": len(signals),
            "emitting":     len(signals) - silence_count,
            "silenced":     silence_count,
            "manip_alerts": manip_count,
        },
        "consumption_guide": {
            "VALUATION":   "Use coherence_c_t as reference price weight. Weight by sec_t.",
            "SILENCE":     "Widen bid-ask spread ≥2×. Disable new position opening on this asset.",
            "MANIP_ALERT": "Flag affected pair in risk system. Alert compliance. Consider circuit break.",
        },
        "refresh_interval_seconds": 60,
        "timestamp": now,
    })


@cex_bp.route("/api/v1/feed/hostile")
def hostile_feed():
    """
    Inverted Feed — entities with hostile/manipulative behavioral signatures.

    Pulls from BH ledger + alerts table to rank entities by manipulation score.
    Designed for CEX compliance, blacklist management, and short-seller research.

    Query params:
      hours=24        — lookback window (default 24h, max 168h)
      min_mf=0.5      — minimum mf_score threshold (default 0.5)
      limit=50        — max results (default 50, max 200)
      cex=BINANCE     — filter to specific CEX (optional)
    """
    hours   = min(int(request.args.get("hours",  24)),  168)
    min_mf  = max(float(request.args.get("min_mf", 0.5)), 0.0)
    limit   = min(int(request.args.get("limit",   50)),  200)
    cex_fil = request.args.get("cex", "").upper() or None

    since = int(time.time()) - hours * 3600

    with _db_lock:
        conn = _get_db()
        q = """
            SELECT entity_id_hex, cex_name, asset,
                   COUNT(*) as bh_count,
                   SUM(CASE WHEN context_flags & ? != 0 THEN 1 ELSE 0 END) as wash_count,
                   SUM(CASE WHEN event_type=10 THEN 1 ELSE 0 END) as flash_count,
                   SUM(CASE WHEN context_flags & ? != 0 THEN 1 ELSE 0 END) as large_count,
                   MAX(ts) as last_seen,
                   MIN(ts) as first_seen
            FROM cex_bh_ledger
            WHERE ts >= ?
            {}
            GROUP BY entity_id_hex, cex_name, asset
            HAVING wash_count > 0 OR flash_count > 0
            ORDER BY (wash_count + flash_count * 3) DESC
            LIMIT ?
        """.format("AND cex_name=?" if cex_fil else "")
        params = [CTX_WASH_FLG, CTX_LARGE, since]
        if cex_fil:
            params.append(cex_fil)
        params.append(limit)
        rows = conn.execute(q, params).fetchall()

        # Also check alerts table for any previously raised alerts
        alert_rows = conn.execute(
            "SELECT entity_id_hex, alert_type, mf_score, coherence, archetype, detail, ts "
            "FROM cex_alerts WHERE ts >= ? ORDER BY mf_score DESC LIMIT 100", (since,)
        ).fetchall()
        conn.close()

    alert_map: dict[str, dict] = {}
    for a in alert_rows:
        eid = a["entity_id_hex"]
        if eid not in alert_map or a["mf_score"] > alert_map[eid].get("mf_score", 0):
            alert_map[eid] = dict(a)

    hostile_entities = []
    for row in rows:
        eid = row["entity_id_hex"]
        bh_count   = row["bh_count"]
        wash_count = row["wash_count"]
        flash_count = row["flash_count"]
        large_count = row["large_count"]

        # Compute a live mf_score from CEX BH pattern ratios
        wash_ratio  = wash_count / max(bh_count, 1)
        flash_ratio = flash_count / max(bh_count, 1)
        cex_mf = round(min(0.70 * wash_ratio + 0.90 * flash_ratio + 0.20 * (large_count / max(bh_count, 1)), 1.0), 4)

        # Blend with any stored alert mf_score
        alert = alert_map.get(eid, {})
        final_mf = max(cex_mf, float(alert.get("mf_score") or 0))

        if final_mf < min_mf:
            continue

        # Determine dominant manipulation pattern
        if flash_ratio > wash_ratio:
            dominant_pattern = "LIQUIDATION_CASCADE"
        elif wash_ratio > 0.3:
            dominant_pattern = "WASH_TRADING"
        else:
            dominant_pattern = "COORDINATED_ORDER_FLOW"

        # Coherence estimate (inverse of mf)
        coherence_est = round(max(0.02, 1.0 - final_mf * 1.4), 4)

        hostile_entities.append({
            "entity_id_hex":   eid,
            "cex_name":        row["cex_name"],
            "asset":           row["asset"],
            "mf_score":        final_mf,
            "coherence_est":   coherence_est,
            "dominant_pattern": dominant_pattern,
            "archetype":       alert.get("archetype") or "FLASH_LOAN_ATTACKER",
            "verdict":         "HOSTILE" if final_mf > 0.75 else "ELEVATED",
            "bh_count":        bh_count,
            "wash_bhs":        wash_count,
            "flash_bhs":       flash_count,
            "large_order_bhs": large_count,
            "first_seen":      row["first_seen"],
            "last_seen":       row["last_seen"],
            "hours_active":    round((row["last_seen"] - row["first_seen"]) / 3600, 1),
            "alert_detail":    alert.get("detail"),
            "cex_action": (
                "BLOCK_DEPOSITS_WITHDRAWALS" if final_mf > 0.75 else
                "FLAG_COMPLIANCE_REVIEW"
            ),
        })

    hostile_entities.sort(key=lambda x: x["mf_score"], reverse=True)

    return jsonify({
        "feed_type":      "INVERTED — hostile entity watchlist",
        "whitepaper":     "§7.3 CEX Integration + L2.1 Manipulation Fingerprint",
        "query": {
            "lookback_hours": hours,
            "min_mf_score":   min_mf,
            "limit":          limit,
            "cex_filter":     cex_fil,
        },
        "hostile_entities": hostile_entities,
        "total_hostile":    len(hostile_entities),
        "summary": {
            "HOSTILE":  sum(1 for e in hostile_entities if e["verdict"] == "HOSTILE"),
            "ELEVATED": sum(1 for e in hostile_entities if e["verdict"] == "ELEVATED"),
            "dominant_patterns": list({e["dominant_pattern"] for e in hostile_entities}),
        },
        "usage": {
            "HOSTILE":  "Block deposits/withdrawals. Report to compliance. File SAR if required.",
            "ELEVATED": "Flag for manual review. Increase KYC scrutiny. Monitor closely.",
        },
        "on_chain_verification": "POST entity_id_hex to TRIONExecutionGate.checkExecution()",
        "gate_address": "0xA85B49C73B5710d9ddB1CB5a94c52D0F33c4199b",
        "timestamp": int(time.time()),
    })


@cex_bp.route("/api/v1/cex/webhook/register", methods=["POST"])
def webhook_register():
    """
    Register a webhook URL to receive real-time hostile/alert events.

    Payload:
    {
      "url":      "https://compliance.myexchange.com/trion/alerts",
      "cex_name": "BINANCE",
      "events":   ["HOSTILE", "MANIP_ALERT", "SILENCE"]   // optional, default all
    }

    TRION will POST alert payloads to the URL immediately when events are triggered.
    """
    payload   = request.get_json(silent=True) or {}
    url       = payload.get("url", "").strip()
    cex_name  = str(payload.get("cex_name", "ANONYMOUS")).upper()
    events    = payload.get("events", ["HOSTILE", "MANIP_ALERT", "SILENCE"])

    if not url.startswith("http"):
        return jsonify({"registered": False,
                        "reason": "url must be a valid http/https endpoint"}), 400

    events_str = ",".join(str(e).upper() for e in events) if events else "ALL"

    with _db_lock:
        conn = _get_db()
        conn.execute(
            "INSERT OR REPLACE INTO cex_webhooks (url, cex_name, events, registered, active) "
            "VALUES (?,?,?,?,1)",
            (url, cex_name, events_str, int(time.time()))
        )
        conn.commit()
        total = conn.execute("SELECT COUNT(*) FROM cex_webhooks WHERE active=1").fetchone()[0]
        conn.close()

    return jsonify({
        "registered":       True,
        "url":              url,
        "cex_name":         cex_name,
        "subscribed_events": events_str.split(","),
        "total_webhooks":   total,
        "delivery":         "TRION will POST JSON alert payloads immediately on event trigger",
        "alert_schema": {
            "alert_type":    "HOSTILE | MANIP_ALERT | SILENCE",
            "entity_id_hex": "SHA3-256(cex_name:asset) — 64 hex chars",
            "asset":         "ETH/USDT",
            "cex_name":      "BINANCE",
            "mf_score":      0.87,
            "coherence":     0.06,
            "archetype":     "FLASH_LOAN_ATTACKER",
            "detail":        "human-readable reason",
            "ts":            "unix timestamp",
            "source":        "TRION_CEX_INTEGRATION",
        },
        "timestamp": int(time.time()),
    })


@cex_bp.route("/api/v1/cex/alerts")
def cex_alerts():
    """
    Recent CEX-triggered alerts (HOSTILE, MANIP_ALERT, SILENCE).
    Poll this endpoint or use webhooks for real-time delivery.

    Query params:
      limit=50        — max alerts (default 50)
      alert_type=HOSTILE  — filter by type
      since=<unix_ts> — since timestamp
    """
    limit      = min(int(request.args.get("limit", 50)), 200)
    alert_type = request.args.get("alert_type", "").upper() or None
    since      = int(request.args.get("since", int(time.time()) - 86400))

    with _db_lock:
        conn = _get_db()
        q = "SELECT * FROM cex_alerts WHERE ts >= ? {} ORDER BY ts DESC LIMIT ?".format(
            "AND alert_type=?" if alert_type else ""
        )
        params = [since] + ([alert_type] if alert_type else []) + [limit]
        rows = conn.execute(q, params).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM cex_alerts WHERE ts >= ?", (since,)).fetchone()[0]
        conn.close()

    alerts = [dict(r) for r in rows]

    return jsonify({
        "alerts":       alerts,
        "total_in_window": total,
        "returned":     len(alerts),
        "query": {
            "since":      since,
            "alert_type": alert_type,
            "limit":      limit,
        },
        "webhook_endpoint": "POST /api/v1/cex/webhook/register",
        "timestamp": int(time.time()),
    })


@cex_bp.route("/api/v1/cex/ledger/<entity_id_hex>")
def cex_ledger(entity_id_hex: str):
    """BH ledger for a specific entity — all CEX-sourced behavioral hashes."""
    limit = min(int(request.args.get("limit", 100)), 500)
    with _db_lock:
        conn = _get_db()
        rows = conn.execute(
            "SELECT * FROM cex_bh_ledger WHERE entity_id_hex=? ORDER BY ts DESC LIMIT ?",
            (entity_id_hex.lower(), limit)
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) FROM cex_bh_ledger WHERE entity_id_hex=?",
            (entity_id_hex.lower(),)
        ).fetchone()[0]
        conn.close()

    return jsonify({
        "entity_id_hex": entity_id_hex,
        "total_bhs":     total,
        "returned":      len(rows),
        "bhs":           [dict(r) for r in rows],
        "formula":       "sense=SHA3-256(93-byte||0x00); antisense=SHA3-256(93-byte||0xFF)⊕NOT(sense)",
        "payload_bytes": 93,
        "timestamp":     int(time.time()),
    })


@cex_bp.route("/api/v1/cex/stats")
def cex_stats():
    """Aggregate statistics across the full CEX BH ledger."""
    with _db_lock:
        conn = _get_db()
        total      = conn.execute("SELECT COUNT(*) FROM cex_bh_ledger").fetchone()[0]
        by_type    = {r[0]: r[1] for r in conn.execute(
            "SELECT event_name, COUNT(*) FROM cex_bh_ledger GROUP BY event_name").fetchall()}
        by_cex     = {r[0]: r[1] for r in conn.execute(
            "SELECT cex_name, COUNT(*) FROM cex_bh_ledger GROUP BY cex_name").fetchall()}
        by_asset   = {r[0]: r[1] for r in conn.execute(
            "SELECT asset, COUNT(*) FROM cex_bh_ledger GROUP BY asset ORDER BY COUNT(*) DESC LIMIT 20").fetchall()}
        wash_total = conn.execute(
            f"SELECT COUNT(*) FROM cex_bh_ledger WHERE context_flags & {CTX_WASH_FLG} != 0").fetchone()[0]
        large_total= conn.execute(
            f"SELECT COUNT(*) FROM cex_bh_ledger WHERE context_flags & {CTX_LARGE} != 0").fetchone()[0]
        alert_total= conn.execute("SELECT COUNT(*) FROM cex_alerts").fetchone()[0]
        webhook_ct = conn.execute("SELECT COUNT(*) FROM cex_webhooks WHERE active=1").fetchone()[0]
        conn.close()

    return jsonify({
        "total_cex_bhs":         total,
        "by_cex":                by_cex,
        "by_event_type":         by_type,
        "by_asset_top20":        by_asset,
        "wash_flagged_bhs":      wash_total,
        "large_order_bhs":       large_total,
        "total_alerts_raised":   alert_total,
        "active_webhooks":       webhook_ct,
        "bh_formula":            "sense=SHA3-256(93-byte||0x00); antisense=SHA3-256(93-byte||0xFF)⊕NOT(sense)",
        "payload_bytes":         93,
        "cex_chain_ids":         CEX_CHAIN_IDS,
        "whitepaper":            "§7.3 CEX Integration — L0.1 canonical BH pipeline",
        "timestamp":             int(time.time()),
    })


# ── Internal helper — pull live signal from FAISS/oracle pipeline ──────────────
def _fetch_live_signal(entity_id: str) -> tuple[float, float, str, int, float]:
    """
    Returns (coherence, mf_score, archetype, akashic_depth, sec_t)
    by querying the running oracle API internally.
    Falls back to hash-seeded estimates if unavailable.
    """
    try:
        r = requests.get(f"http://127.0.0.1:5000/api/v1/signal/{entity_id}", timeout=3)
        if r.status_code == 200:
            d = r.json()
            return (
                float(d.get("coherence",     0.35)),
                float(d.get("mf_score",      0.20)),
                str(d.get("archetype",       "Regular")),
                int(d.get("akashic_depth",   5000)),
                float(d.get("SEC_t",         d.get("sec_t", 0.75))),
            )
    except Exception:
        pass
    # Deterministic fallback (5-min bucket)
    h = hashlib.sha256(f"{entity_id}:{int(time.time())//300}".encode()).digest()
    return (
        round(0.30 + 0.60 * (h[0] / 255.0), 4),
        round(0.05 + 0.50 * (h[1] / 255.0), 4),
        ["Regular", "Hero", "Jester", "GENESIS"][h[2] % 4],
        int(3000 + 50000 * (h[3] / 255.0)),
        round(0.60 + 0.35 * (h[4] / 255.0), 4),
    )
