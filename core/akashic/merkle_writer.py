"""
TRION Protocol — TimescaleDB Merkle Root Writer
===============================================

Wires INSERT path for the `merkle_roots` TimescaleDB table.

Per audit (worklog FINAL-VERDICT gap #15), the `merkle_roots` table
(expected 7 rows for 7 days of Merkle roots) was empty — the in-memory
`merkle_roots` dict and SQLite `merkle_state` table were updated by
`_register_bh_leaf()` in anima-service/faiss_service.py, but the
canonical TimescaleDB hypertable was deploy-only DDL with no writer.

This module:
  - `compute_daily_merkle_root(date)`:
      Queries `akashic_bh` for all `bh_id` (canonical L0.1 sense strand)
      rows on the given date, builds an O(log N) SHA3-256 Merkle tree,
      and returns (root_bytes, leaf_count).
  - `persist_daily_merkle(date)`:
      Computes the root and UPSERTs into `merkle_roots` (PK = date).
  - `backfill_merkle_roots(n_days=7)`:
      Backfills the last N days that have akashic_bh data.
  - `start_scheduler()`:
      APScheduler daily cron — computes yesterday's root at 00:05 UTC.

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import psycopg2  # noqa: F401
    _PG_OK = True
except ImportError:  # pragma: no cover
    _PG_OK = False


def _tsdb_url() -> str:
    return (
        os.environ.get("TIMESCALEDB_URL")
        or os.environ.get("DATABASE_URL")
        or os.environ.get("TIMESCALE_DB_URL")
        or ""
    )


def _pg_available() -> bool:
    return _PG_OK and bool(_tsdb_url())


def _connect():
    if not _pg_available():
        return None
    try:
        conn = psycopg2.connect(_tsdb_url(), connect_timeout=15,
                                application_name="trion-merkle-writer")
        conn.autocommit = True
        return conn
    except Exception as exc:
        logger.error("[merkle_writer] TSDB connect failed: %s", exc)
        return None


# ── Core Merkle computation ─────────────────────────────────────────────────

def _build_merkle_root(leaves: List[bytes]) -> bytes:
    """O(log N) SHA3-256 Merkle tree root from raw byte leaves.

    Each leaf is hashed with SHA3-256 first (defensive: ensures uniform
    length even if the source column varies), then paired up layer-by-layer
    with last-leaf duplication on odd counts.
    """
    if not leaves:
        return hashlib.sha3_256(b"empty").digest()

    # Each leaf = SHA3-256(bh_id bytes). For akashic_bh.bh_id (BYTEA),
    # we hash the raw bytes directly.
    layer: List[bytes] = [hashlib.sha3_256(leaf).digest() for leaf in leaves]

    while len(layer) > 1:
        if len(layer) % 2 == 1:
            layer.append(layer[-1])  # duplicate last
        layer = [
            hashlib.sha3_256(layer[i] + layer[i + 1]).digest()
            for i in range(0, len(layer), 2)
        ]
    return layer[0]


def compute_daily_merkle_root(day: date) -> Tuple[bytes, int]:
    """Compute the Merkle root for all akashic_bh rows on `day`.

    Returns (root_bytes_32, leaf_count). Empty days return
    (SHA3-256("empty"), 0).
    """
    conn = _connect()
    if conn is None:
        return (hashlib.sha3_256(b"empty").digest(), 0)
    try:
        cur = conn.cursor()
        # Pull all bh_id (sense strand) BYTEA values for this day, ordered
        # by (time, bh_id) for deterministic tree construction.
        cur.execute(
            """
            SELECT bh_id
            FROM akashic_bh
            WHERE time >= %s::date
              AND time <  (%s::date + INTERVAL '1 day')
            ORDER BY time ASC, bh_id ASC
            """,
            (day, day),
        )
        rows = cur.fetchall()
        cur.close()
        leaves = [bytes(r[0]) for r in rows] if rows else []
        root = _build_merkle_root(leaves)
        return (root, len(leaves))
    except Exception as exc:
        logger.error("[merkle_writer] compute_daily_merkle_root(%s) failed: %s",
                     day, exc)
        return (hashlib.sha3_256(b"empty").digest(), 0)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def persist_daily_merkle(day: date) -> Dict[str, object]:
    """Compute Merkle root for `day` and UPSERT into `merkle_roots` TSDB.

    Returns: {"ok": bool, "date": str, "leaf_count": int,
              "root_hex": str, "reason": str?}
    """
    if not _pg_available():
        return {"ok": False, "reason": "TimescaleDB unavailable", "date": str(day)}

    root_bytes, leaf_count = compute_daily_merkle_root(day)
    root_hex = root_bytes.hex()

    conn = _connect()
    if conn is None:
        return {"ok": False, "reason": "connect failed", "date": str(day)}
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO merkle_roots (date, root_hash, leaf_count, computed_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (date) DO UPDATE SET
              root_hash    = EXCLUDED.root_hash,
              leaf_count   = EXCLUDED.leaf_count,
              computed_at  = EXCLUDED.computed_at
            RETURNING computed_at
            """,
            (day, root_bytes, leaf_count),
        )
        row = cur.fetchone()
        cur.close()
        return {
            "ok":         True,
            "date":       str(day),
            "leaf_count": leaf_count,
            "root_hex":   root_hex,
            "computed_at": row[0].isoformat() if row else None,
        }
    except Exception as exc:
        logger.error("[merkle_writer] persist_daily_merkle(%s) failed: %s",
                     day, exc)
        return {"ok": False, "reason": str(exc), "date": str(day)}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def backfill_merkle_roots(n_days: int = 7) -> Dict[str, object]:
    """Backfill `merkle_roots` for the last N days that have akashic_bh data.

    Walks back from the most-recent day with akashic_bh data, computing one
    Merkle root per day until N days have been processed (or no more data).

    Returns: {"days_processed": N, "ok_count": M, "results": [...]}
    """
    if not _pg_available():
        return {"ok": False, "reason": "TimescaleDB unavailable", "days_processed": 0}

    # Find the most recent day with akashic_bh data (anchors the backfill on
    # real data rather than wall-clock NOW, which may have gaps).
    conn = _connect()
    if conn is None:
        return {"ok": False, "reason": "connect failed", "days_processed": 0}
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT date_trunc('day', time)::date AS d
            FROM akashic_bh
            WHERE time > NOW() - INTERVAL '30 days'
            ORDER BY d DESC
            LIMIT %s
        """, (n_days,))
        days = [r[0] for r in cur.fetchall()]
        cur.close()
    finally:
        try:
            conn.close()
        except Exception:
            pass

    results = []
    ok = 0
    for day in days:
        r = persist_daily_merkle(day)
        results.append(r)
        if r.get("ok"):
            ok += 1
    return {
        "days_processed": len(days),
        "ok_count":       ok,
        "results":        results,
    }


def count_merkle_roots() -> int:
    """Return the current row count of merkle_roots."""
    if not _pg_available():
        return 0
    conn = _connect()
    if conn is None:
        return 0
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM merkle_roots;")
        n = cur.fetchone()[0]
        cur.close()
        return int(n)
    except Exception as exc:
        logger.error("[merkle_writer] count failed: %s", exc)
        return 0
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ── APScheduler daily cron ─────────────────────────────────────────────────

_SCHEDULER = None


def start_scheduler(run_hour: int = 0, run_minute: int = 5) -> Dict[str, str]:
    """Start APScheduler daily cron — computes yesterday's Merkle root at
    00:05 UTC by default. Idempotent.
    """
    global _SCHEDULER
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        return {"ok": False, "reason": "apscheduler not installed"}

    if _SCHEDULER and _SCHEDULER.running:
        return {"ok": True, "status": "already_running"}

    def _daily_merkle_job():
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()
        result = persist_daily_merkle(yesterday)
        if result.get("ok"):
            logger.info("[merkle_writer] persisted root for %s: leaves=%d",
                        result["date"], result["leaf_count"])
        else:
            logger.warning("[merkle_writer] failed for %s: %s",
                          result.get("date"), result.get("reason"))

    sched = BackgroundScheduler(daemon=True)
    sched.add_job(
        _daily_merkle_job,
        trigger=CronTrigger(hour=run_hour, minute=run_minute, timezone="UTC"),
        id="trion_daily_merkle",
        name="TRION daily Merkle root writer",
        max_instances=1,
        coalesce=True,
    )
    sched.start()
    _SCHEDULER = sched
    logger.info("[merkle_writer] scheduler started — daily at %02d:%02d UTC",
                run_hour, run_minute)
    return {"ok": True, "status": "started", "run_at_utc": f"{run_hour:02d}:{run_minute:02d}"}


def stop_scheduler() -> Dict[str, str]:
    global _SCHEDULER
    if not _SCHEDULER:
        return {"ok": True, "status": "not_running"}
    try:
        _SCHEDULER.shutdown(wait=False)
        return {"ok": True, "status": "stopped"}
    except Exception as e:
        return {"ok": False, "reason": str(e)}
    finally:
        _SCHEDULER = None


# ── CLI ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":  # pragma: no cover
    import argparse, json
    p = argparse.ArgumentParser(description="TRION Merkle root TSDB writer")
    sub = p.add_subparsers(dest="cmd", required=True)
    pd = sub.add_parser("persist", help="Compute + persist root for a date")
    pd.add_argument("date", help="YYYY-MM-DD")
    sub.add_parser("count", help="Print merkle_roots row count")
    bf = sub.add_parser("backfill", help="Backfill last N days")
    bf.add_argument("n_days", type=int, default=7)
    sub.add_parser("serve", help="Start daily APScheduler daemon")
    args = p.parse_args()

    if args.cmd == "persist":
        d = datetime.strptime(args.date, "%Y-%m-%d").date()
        print(json.dumps(persist_daily_merkle(d), indent=2, default=str))
    elif args.cmd == "count":
        print(f"merkle_roots: {count_merkle_roots()} rows")
    elif args.cmd == "backfill":
        print(json.dumps(backfill_merkle_roots(args.n_days), indent=2, default=str))
    elif args.cmd == "serve":
        print(json.dumps(start_scheduler(), indent=2))
        import time
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            print(json.dumps(stop_scheduler(), indent=2))
