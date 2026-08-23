"""
segmentation.py — Sub-entity extraction for protocol contracts.

Instead of treating `uniswap_contract` as one behavioral identity (which
aggregates millions of diverse users and produces incoherent Mental-plane
scores), we decompose protocol activity into (contract, caller) pairs.

Each (contract, caller) is a SubEntity with its own transaction history,
role, and C(t)-style coherence score — giving a meaningful behavioral
identity to each participant.

DB: ./bh_ledger.db  (SQLite, written by Rust/Node indexers)
"""

import os
import math
import time
import sqlite3
import threading
import logging
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)

_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "bh_ledger.db",
)

_cache: dict = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 60


@dataclass
class SubEntity:
    contract: str
    caller: str
    entity_id: str
    tx_count: int
    event_type_counts: dict
    magnitude_stats: dict
    chains: list
    first_seen: float
    last_seen: float
    dominant_event: str
    role: Optional[str] = None
    coherence_score: Optional[float] = None
    plane_breakdown: dict = field(default_factory=dict)


def _get_conn() -> Optional[sqlite3.Connection]:
    if not os.path.exists(_DB_PATH):
        log.warning("bh_ledger.db not found at %s", _DB_PATH)
        return None
    conn = sqlite3.connect(_DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


class ProtocolSegmenter:
    """
    Decomposes a protocol contract address into per-caller SubEntity records.

    Usage:
        seg = ProtocolSegmenter()
        sub_entities = seg.get_sub_entities("0xUniswapV3Pool", limit=100)
    """

    def get_sub_entities(
        self,
        contract_address: str,
        limit: int = 100,
        since_ts: Optional[float] = None,
        event_types: Optional[list] = None,
    ) -> list[SubEntity]:
        cache_key = f"{contract_address}:{limit}:{since_ts}:{event_types}"
        with _cache_lock:
            if cache_key in _cache:
                entry, ts = _cache[cache_key]
                if time.time() - ts < _CACHE_TTL:
                    return entry

        result = self._query(contract_address, limit, since_ts, event_types)
        with _cache_lock:
            _cache[cache_key] = (result, time.time())
        return result

    def _query(
        self,
        contract: str,
        limit: int,
        since_ts: Optional[float],
        event_types: Optional[list],
    ) -> list[SubEntity]:
        conn = _get_conn()
        if conn is None:
            return []

        try:
            addr_lower = contract.lower()
            params: list = [addr_lower, addr_lower]
            since_clause = ""
            if since_ts:
                since_clause = "AND ts >= ?"
                params.append(since_ts)
            ev_clause = ""
            if event_types:
                placeholders = ",".join("?" * len(event_types))
                ev_clause = f"AND event_type IN ({placeholders})"
                params.extend(event_types)

            params.append(limit)

            sql = f"""
                SELECT
                    LOWER(to_addr)   AS contract,
                    LOWER(from_addr) AS caller,
                    COUNT(*)         AS tx_count,
                    GROUP_CONCAT(DISTINCT event_type_name) AS event_names,
                    GROUP_CONCAT(event_type)               AS event_types_raw,
                    GROUP_CONCAT(magnitude_norm)           AS magnitudes_raw,
                    GROUP_CONCAT(DISTINCT chain_label)     AS chains_raw,
                    MIN(ts)  AS first_seen,
                    MAX(ts)  AS last_seen
                FROM bh_ledger
                WHERE (LOWER(to_addr) = ? OR LOWER(entity_id) = ?)
                  {since_clause}
                  {ev_clause}
                GROUP BY LOWER(to_addr), LOWER(from_addr)
                ORDER BY tx_count DESC
                LIMIT ?
            """
            rows = conn.execute(sql, params).fetchall()

            subs = []
            for r in rows:
                event_type_counts = self._count_events(r["event_types_raw"] or "")
                magnitudes = self._parse_floats(r["magnitudes_raw"] or "")
                chains = [c.strip() for c in (r["chains_raw"] or "").split(",") if c.strip()]
                dominant = max(event_type_counts, key=event_type_counts.get) if event_type_counts else "UNKNOWN"
                mag_stats = self._magnitude_stats(magnitudes)

                se = SubEntity(
                    contract=r["contract"] or contract,
                    caller=r["caller"] or "",
                    entity_id=f"{(r['contract'] or contract)[:10]}:{(r['caller'] or '')[:10]}",
                    tx_count=r["tx_count"],
                    event_type_counts=event_type_counts,
                    magnitude_stats=mag_stats,
                    chains=chains,
                    first_seen=r["first_seen"] or 0,
                    last_seen=r["last_seen"] or 0,
                    dominant_event=dominant,
                )
                subs.append(se)

            return subs
        except Exception as exc:
            log.error("segmentation query error: %s", exc)
            return []
        finally:
            conn.close()

    def get_protocol_activity(
        self,
        contract_address: str,
        window_seconds: int = 3600,
    ) -> dict:
        """Return bucketed event-type distribution for the last window_seconds."""
        conn = _get_conn()
        if conn is None:
            return {}
        try:
            since = time.time() - window_seconds
            addr_lower = contract_address.lower()
            rows = conn.execute(
                """
                SELECT event_type_name, COUNT(*) as cnt
                FROM bh_ledger
                WHERE (LOWER(to_addr) = ? OR LOWER(entity_id) = ?)
                  AND ts >= ?
                GROUP BY event_type_name
                """,
                [addr_lower, addr_lower, since],
            ).fetchall()
            total = sum(r["cnt"] for r in rows)
            if total == 0:
                return {}
            return {r["event_type_name"]: r["cnt"] / total for r in rows}
        except Exception as exc:
            log.error("protocol_activity error: %s", exc)
            return {}
        finally:
            conn.close()

    def get_global_activity(self, window_seconds: int = 3600) -> dict:
        """Return global event-type distribution across all entities (baseline)."""
        conn = _get_conn()
        if conn is None:
            return {}
        try:
            since = time.time() - window_seconds
            rows = conn.execute(
                """
                SELECT event_type_name, COUNT(*) as cnt
                FROM bh_ledger
                WHERE ts >= ?
                GROUP BY event_type_name
                """,
                [since],
            ).fetchall()
            total = sum(r["cnt"] for r in rows)
            if total == 0:
                return {}
            return {r["event_type_name"]: r["cnt"] / total for r in rows}
        finally:
            conn.close()

    @staticmethod
    def _count_events(raw: str) -> dict:
        counts: dict = {}
        for name in raw.split(","):
            name = name.strip()
            if name:
                counts[name] = counts.get(name, 0) + 1
        return counts

    @staticmethod
    def _parse_floats(raw: str) -> list:
        result = []
        for v in raw.split(","):
            try:
                result.append(float(v.strip()))
            except ValueError:
                pass
        return result

    @staticmethod
    def _magnitude_stats(values: list) -> dict:
        if not values:
            return {"mean": 0.0, "max": 0.0, "std": 0.0, "p95": 0.0}
        n = len(values)
        mean = sum(values) / n
        variance = sum((v - mean) ** 2 for v in values) / max(n - 1, 1)
        std = math.sqrt(variance)
        sorted_v = sorted(values)
        p95_idx = min(int(0.95 * n), n - 1)
        return {
            "mean": round(mean, 6),
            "max": round(max(values), 6),
            "std": round(std, 6),
            "p95": round(sorted_v[p95_idx], 6),
        }
