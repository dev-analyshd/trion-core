"""
TRION Protocol — Biological Rhythm TSDB Writer
==============================================

Wires INSERT path for the `biological_rhythm` TimescaleDB hypertable.

Per audit (worklog FINAL-VERDICT gap #16), the BRT scheduler existed in
anima-service/brt_scheduler.py but never persisted rhythm phase
computations to the TimescaleDB table — `biological_rhythm` had 0 rows.

This module:
  - `compute_rhythm_row(ts)`:
      Computes (time, circadian_phase, lunar_phase, seasonal_phase,
      activity_score, anomaly_flag) for a given timestamp. The phase
      labels match the schema.sql TEXT domain exactly.
      activity_score is derived from real akashic_bh behavioral hashes
      in the preceding 15-minute window (mean magnitude × event count
      factor), so the BRT row reflects real network activity.
  - `persist_rhythm_row(ts)`:
      INSERT the computed row into biological_rhythm hypertable.
  - `backfill_rhythm(n_rows=100, interval_minutes=15)`:
      Backfill N rows walking back from the latest akashic_bh time.
  - `start_scheduler()`:
      APScheduler every 15 minutes (one BRT row per cycle).

Schema:
    time             TIMESTAMPTZ NOT NULL,
    circadian_phase  TEXT (DAWN/MORNING/AFTERNOON/EVENING/NIGHT),
    lunar_phase      TEXT (NEW_MOON/WAXING/FULL_MOON/WANING),
    seasonal_phase   TEXT (Q1_WINTER/Q2_SPRING/Q3_SUMMER/Q4_AUTUMN),
    activity_score   DOUBLE,
    anomaly_flag     BOOLEAN

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import logging
import math
import os
import time
from datetime import datetime, timedelta, timezone
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
                                application_name="trion-brt-writer")
        conn.autocommit = True
        return conn
    except Exception as exc:
        logger.error("[brt_writer] TSDB connect failed: %s", exc)
        return None


# ── Phase labels (match schema.sql TEXT domain) ─────────────────────────────

def detect_circadian_phase(ts: float) -> str:
    """Map UTC hour → circadian phase label (5 buckets)."""
    hour = datetime.fromtimestamp(ts, tz=timezone.utc).hour
    if 5  <= hour < 9:  return "DAWN"
    if 9  <= hour < 12: return "MORNING"
    if 12 <= hour < 17: return "AFTERNOON"
    if 17 <= hour < 21: return "EVENING"
    return "NIGHT"


# Reference new moon: 2000-01-06 18:14 UTC (astronomical epoch)
_REF_NEW_MOON_TS = 947182440.0
_LUNAR_PERIOD_SEC = 2551442.8  # 29.53 days


def detect_lunar_phase(ts: float) -> str:
    """Approximate lunar phase label (4 buckets)."""
    elapsed = (ts - _REF_NEW_MOON_TS) % _LUNAR_PERIOD_SEC
    phase_pct = elapsed / _LUNAR_PERIOD_SEC
    if phase_pct < 0.125:  return "NEW_MOON"
    if phase_pct < 0.375:  return "WAXING"
    if phase_pct < 0.625:  return "FULL_MOON"
    if phase_pct < 0.875:  return "WANING"
    return "NEW_MOON"


def detect_seasonal_phase(ts: float) -> str:
    """Map calendar month → seasonal/fiscal quarter label."""
    month = datetime.fromtimestamp(ts, tz=timezone.utc).month
    if month <= 3:  return "Q1_WINTER"
    if month <= 6:  return "Q2_SPRING"
    if month <= 9:  return "Q3_SUMMER"
    return "Q4_AUTUMN"


# ── Activity score from akashic_bh ──────────────────────────────────────────

def _fetch_activity_score(window_start: datetime, window_end: datetime) -> Tuple[float, int]:
    """Compute activity_score [0, 1] for a 15-min window from akashic_bh.

    Activity score = sqrt(tx_count) / 100, clamped to [0, 1].
    Scaled so that 10k tx → 1.0 (saturated). Returns (score, tx_count).
    """
    conn = _connect()
    if conn is None:
        return (0.0, 0)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT count(*), avg(magnitude_norm), stddev(magnitude_norm)
            FROM akashic_bh
            WHERE time >= %s AND time < %s
            """,
            (window_start, window_end),
        )
        row = cur.fetchone()
        cur.close()
        if not row or row[0] is None or row[0] == 0:
            return (0.0, 0)
        n_tx = int(row[0])
        # sqrt scaling: 10k tx → 1.0
        score = min(1.0, math.sqrt(n_tx) / 100.0)
        return (round(score, 6), n_tx)
    except Exception as exc:
        logger.error("[brt_writer] _fetch_activity_score failed: %s", exc)
        return (0.0, 0)
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ── Row computation + persistence ───────────────────────────────────────────

def compute_rhythm_row(ts: float) -> Dict[str, object]:
    """Compute one biological_rhythm row for the given Unix timestamp.

    Returns dict with all schema columns:
      {time, circadian_phase, lunar_phase, seasonal_phase,
       activity_score, anomaly_flag, tx_count}
    """
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    circ = detect_circadian_phase(ts)
    lunar = detect_lunar_phase(ts)
    season = detect_seasonal_phase(ts)
    # Activity score: 15-minute window ending at ts.
    window_end = dt
    window_start = dt - timedelta(minutes=15)
    score, n_tx = _fetch_activity_score(window_start, window_end)
    # Anomaly: high activity during NIGHT phase (03:00-05:00 UTC) — this
    # is a behavioral anomaly per L6.2 spec (network should be quieter).
    anomaly = (circ == "NIGHT" and score > 0.5)
    return {
        "time":             dt,
        "circadian_phase":  circ,
        "lunar_phase":      lunar,
        "seasonal_phase":   season,
        "activity_score":   score,
        "anomaly_flag":     anomaly,
        "tx_count":         n_tx,
    }


def persist_rhythm_row(ts: float) -> Dict[str, object]:
    """Compute and INSERT one biological_rhythm row."""
    if not _pg_available():
        return {"ok": False, "reason": "TimescaleDB unavailable"}
    row = compute_rhythm_row(ts)
    conn = _connect()
    if conn is None:
        return {"ok": False, "reason": "connect failed"}
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO biological_rhythm
              (time, circadian_phase, lunar_phase, seasonal_phase,
               activity_score, anomaly_flag)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (row["time"], row["circadian_phase"], row["lunar_phase"],
             row["seasonal_phase"], row["activity_score"], row["anomaly_flag"]),
        )
        cur.close()
        return {"ok": True, "row": {k: (v.isoformat() if isinstance(v, datetime)
                                          else v)
                                     for k, v in row.items()}}
    except Exception as exc:
        logger.error("[brt_writer] persist_rhythm_row failed: %s", exc)
        return {"ok": False, "reason": str(exc)}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def backfill_rhythm(n_rows: int = 100, interval_minutes: int = 15) -> Dict[str, object]:
    """Backfill N rhythm rows walking back from the latest akashic_bh time.

    Anchors on the latest akashic_bh time so backfill reflects real network
    activity (not wall-clock NOW which may have gaps in the data).

    Returns: {"rows_inserted": N, "ok_count": M, "results": [...]}
    """
    if not _pg_available():
        return {"ok": False, "reason": "TimescaleDB unavailable", "rows_inserted": 0}

    # Anchor on the latest akashic_bh time.
    conn = _connect()
    if conn is None:
        return {"ok": False, "reason": "connect failed", "rows_inserted": 0}
    try:
        cur = conn.cursor()
        cur.execute("SELECT MAX(time) FROM akashic_bh;")
        row = cur.fetchone()
        cur.close()
        if not row or row[0] is None:
            # Fall back to NOW
            latest = datetime.now(timezone.utc)
        else:
            latest = row[0]
            if latest.tzinfo is None:
                latest = latest.replace(tzinfo=timezone.utc)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    results = []
    ok = 0
    # Walk back in 15-minute intervals. We use `interval_minutes` per step
    # and emit one row per step.
    for i in range(n_rows):
        ts = (latest - timedelta(minutes=i * interval_minutes)).timestamp()
        r = persist_rhythm_row(ts)
        results.append(r)
        if r.get("ok"):
            ok += 1
    return {
        "rows_inserted": ok,
        "ok_count":      ok,
        "anchor_time":   latest.isoformat(),
        "interval_min":  interval_minutes,
        "results":       results,
    }


def count_rhythm_rows() -> int:
    """Return current row count of biological_rhythm."""
    if not _pg_available():
        return 0
    conn = _connect()
    if conn is None:
        return 0
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM biological_rhythm;")
        n = cur.fetchone()[0]
        cur.close()
        return int(n)
    except Exception as exc:
        logger.error("[brt_writer] count failed: %s", exc)
        return 0
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ── APScheduler wiring ─────────────────────────────────────────────────────

_SCHEDULER = None


def start_scheduler(interval_minutes: int = 15) -> Dict[str, str]:
    """Start APScheduler every 15 minutes (one BRT row per cycle)."""
    global _SCHEDULER
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        return {"ok": False, "reason": "apscheduler not installed"}

    if _SCHEDULER and _SCHEDULER.running:
        return {"ok": True, "status": "already_running"}

    def _brt_tick():
        result = persist_rhythm_row(time.time())
        if result.get("ok"):
            logger.info("[brt_writer] persisted row: %s",
                        {k: v for k, v in result.get("row", {}).items()
                         if k in ("time", "circadian_phase", "lunar_phase",
                                  "activity_score", "anomaly_flag")})

    sched = BackgroundScheduler(daemon=True)
    sched.add_job(
        _brt_tick,
        trigger="interval",
        minutes=interval_minutes,
        id="trion_brt_writer",
        name="TRION biological rhythm TSDB writer",
        max_instances=1,
        coalesce=True,
    )
    sched.start()
    _SCHEDULER = sched
    logger.info("[brt_writer] scheduler started — interval=%dm", interval_minutes)
    return {"ok": True, "status": "started", "interval_minutes": interval_minutes}


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
    p = argparse.ArgumentParser(description="TRION biological_rhythm TSDB writer")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("now", help="Persist one row for current time")
    sub.add_parser("count", help="Print biological_rhythm row count")
    bf = sub.add_parser("backfill", help="Backfill N rows")
    bf.add_argument("n_rows", type=int, default=100)
    bf.add_argument("--interval-minutes", type=int, default=15)
    sub.add_parser("serve", help="Start APScheduler daemon")
    args = p.parse_args()

    if args.cmd == "now":
        print(json.dumps(persist_rhythm_row(time.time()), indent=2, default=str))
    elif args.cmd == "count":
        print(f"biological_rhythm: {count_rhythm_rows()} rows")
    elif args.cmd == "backfill":
        print(json.dumps(backfill_rhythm(n_rows=args.n_rows,
                                          interval_minutes=args.interval_minutes),
                          indent=2, default=str))
    elif args.cmd == "serve":
        print(json.dumps(start_scheduler(), indent=2))
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            print(json.dumps(stop_scheduler(), indent=2))
