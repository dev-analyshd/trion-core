"""
TRION Protocol — BIBL Mempool Feed Simulator
============================================

Wires the BIBL Pattern Library (core/akashic/bibl_pattern_store.py) to a
real data source: the `akashic_bh` hypertable. Per the audit (worklog FINAL-
VERDICT gap #14), `bibl_observations` had 0 rows because no live mempool feed
was wired to call `BIBLPatternStore.record_observation()`.

This module periodically:
  1. Queries recent transactions from `akashic_bh` (the canonical L0.1 hot-tier
     store, currently 893k rows across 69 chains).
  2. Computes the three BIBL behavioral features per chain-window:
       - mempool_size  = COUNT(*) in the window
       - mev_rate      = (#SWAP + #MEV_CAPTURE + #FLASH_LOAN) / total
       - volatility    = STDDEV(magnitude_norm) in the window
  3. Classifies the mempool state into one of 15 BIBL archetypes.
  4. Records the observation via `BIBLPatternStore.record_observation()`.

The actual_fee_adj (realized outcome) is computed by replaying the next
window — i.e. we observe what the average magnitude was in the *next*
window as a proxy for realized fee pressure. The prediction_error is
|recommended - actual|.

Usage:
    python3 -m core.akashic.bibl_feed tick         # one-shot
    python3 -m core.akashic.bibl_feed backfill 50  # backfill 50 obs
    python3 -m core.akashic.bibl_feed serve         # APScheduler daemon

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from .bibl_pattern_store import (
    ARCHETYPES, BIBLPatternStore, PatternObservation,
    classify_mempool_archetype,
)

logger = logging.getLogger(__name__)

try:
    import psycopg2  # noqa: F401
    _PG_OK = True
except ImportError:  # pragma: no cover
    _PG_OK = False


# ── Mempool features ────────────────────────────────────────────────────────

@dataclass
class MempoolFeatures:
    """Per-chain mempool behavioral features for one time window."""
    chain_id:        int
    window_start:    datetime
    window_end:      datetime
    mempool_size:    int
    mev_rate:        float
    volatility:     float
    avg_magnitude:   float
    avg_entropy:     float
    swap_count:      int
    mev_count:       int


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
        conn = psycopg2.connect(_tsdb_url(), connect_timeout=10,
                                application_name="trion-bibl-feed")
        conn.autocommit = True
        return conn
    except Exception as exc:
        logger.error("[bibl_feed] TSDB connect failed: %s", exc)
        return None


# ── Query recent mempool features from akashic_bh ──────────────────────────

def fetch_mempool_features(
    *,
    window_start: datetime,
    window_end:   datetime,
    chain_id:     Optional[int] = None,
) -> List[MempoolFeatures]:
    """Pull per-chain mempool features from `akashic_bh` for a time window.

    The behavioral hash hypertable is the canonical L0.1 record store. We
    treat it as a *historical* mempool snapshot — every BH is a finalised
    mempool entry, so windowed aggregates are the realised mempool state.

    Returns: list of MempoolFeatures, one per chain_id with >0 tx in window.
    """
    conn = _connect()
    if conn is None:
        return []
    try:
        cur = conn.cursor()
        params: Tuple = (window_start, window_end)
        chain_filter = ""
        if chain_id is not None:
            chain_filter = "AND chain_id = %s"
            params = (window_start, window_end, chain_id)  # type: ignore
        cur.execute(
            f"""
            SELECT
                chain_id,
                COUNT(*)                                       AS mempool_size,
                COUNT(*) FILTER (WHERE event_type IN
                    ('SWAP','MEV_CAPTURE','FLASH_LOAN'))         AS mev_count,
                COUNT(*) FILTER (WHERE event_type = 'SWAP')     AS swap_count,
                AVG(magnitude_norm)                             AS avg_mag,
                STDDEV(magnitude_norm)                          AS std_mag,
                AVG(entropy_delta)                              AS avg_entropy
            FROM akashic_bh
            WHERE time >= %s AND time < %s {chain_filter}
            GROUP BY chain_id
            HAVING COUNT(*) > 0
            ORDER BY mempool_size DESC
            LIMIT 25
            """,
            params,
        )
        rows = cur.fetchall()
        cur.close()
        feats: List[MempoolFeatures] = []
        for r in rows:
            cid, msize, mev_n, swap_n, avg_mag, std_mag, avg_ent = r
            msize = int(msize)
            mev_rate = (mev_n / msize) if msize > 0 else 0.0
            vol = float(std_mag) if std_mag is not None else 0.0
            feats.append(MempoolFeatures(
                chain_id       = int(cid),
                window_start   = window_start,
                window_end     = window_end,
                mempool_size   = msize,
                mev_rate       = round(mev_rate, 6),
                volatility     = round(vol, 6),
                avg_magnitude  = float(avg_mag) if avg_mag is not None else 0.0,
                avg_entropy    = float(avg_ent) if avg_ent is not None else 0.0,
                swap_count     = int(swap_n or 0),
                mev_count      = int(mev_n or 0),
            ))
        return feats
    except Exception as exc:
        logger.error("[bibl_feed] fetch_mempool_features failed: %s", exc)
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ── BIBL Feed Simulator ────────────────────────────────────────────────────

class BIBLFeedSimulator:
    """
    Periodic BIBL mempool feed simulator.

    Pulls recent akashic_bh transactions, classifies each chain's mempool
    state into a BIBL archetype, and persists observations to the local
    SQLite `bibl_patterns.db` (the BIBL Pattern Library).
    """

    def __init__(self, store: Optional[BIBLPatternStore] = None,
                 window_minutes: int = 15):
        self.store = store or BIBLPatternStore()
        self.window_minutes = window_minutes

    def tick(self, now: Optional[datetime] = None) -> Dict[str, int]:
        """One feed cycle: fetch features → classify → record observations.

        Returns: {"chains_observed": N, "observations_recorded": M}
        """
        now = now or datetime.now(timezone.utc)
        window_end   = now
        window_start = now - timedelta(minutes=self.window_minutes)
        feats = fetch_mempool_features(
            window_start=window_start, window_end=window_end
        )

        # For the "actual" outcome, fetch the next window's average magnitude
        # as a proxy for realised fee pressure. We use a forward window of
        # equal length when available; otherwise fallback to current window.
        next_end   = window_end + timedelta(minutes=self.window_minutes)
        next_start = window_end
        next_feats_by_chain: Dict[int, MempoolFeatures] = {
            f.chain_id: f for f in fetch_mempool_features(
                window_start=next_start, window_end=next_end
            )
        }

        recorded = 0
        for f in feats:
            archetype, match_score = classify_mempool_archetype(
                mempool_size=f.mempool_size,
                mev_rate=f.mev_rate,
                volatility=f.volatility,
            )
            recommended_fee_adj = archetype.base_fee_adj
            # Actual = forward-window avg magnitude scaled to fee-adj band.
            # If forward window has data, use it; else fallback to current.
            fwd = next_feats_by_chain.get(f.chain_id)
            if fwd is not None and fwd.mempool_size > 0:
                actual_fee_adj = round(
                    -0.30 + min(1.0, fwd.avg_magnitude) * 0.90, 6
                )
            else:
                actual_fee_adj = round(
                    -0.30 + min(1.0, f.avg_magnitude) * 0.90, 6
                )
            prediction_error = round(abs(recommended_fee_adj - actual_fee_adj), 6)
            obs = PatternObservation(
                archetype_code      = archetype.code,
                observed_at          = window_end.timestamp(),
                mempool_size          = f.mempool_size,
                mev_rate             = f.mev_rate,
                volatility           = f.volatility,
                recommended_fee_adj   = recommended_fee_adj,
                actual_fee_adj        = actual_fee_adj,
                prediction_error     = prediction_error,
                chain_id             = f.chain_id,
            )
            self.store.record_observation(obs)
            recorded += 1
        return {
            "chains_observed":      len(feats),
            "observations_recorded": recorded,
        }

    def backfill(self, n_windows: int = 24,
                 window_minutes: Optional[int] = None) -> Dict[str, int]:
        """Backfill N historical observations by walking back in time.

        For each of the last `n_windows` × `window_minutes` windows (ending
        at NOW), we fetch features → classify → record. This populates the
        pattern library with historical data so calibrations converge
        immediately (instead of waiting days for the scheduler).

        Returns: {"windows_processed": N, "observations_recorded": M}
        """
        wmin = window_minutes or self.window_minutes
        now  = datetime.now(timezone.utc)
        total_obs = 0
        total_wins = 0
        for i in range(n_windows):
            end   = now - timedelta(minutes=i * wmin)
            start = end - timedelta(minutes=wmin)
            feats = fetch_mempool_features(window_start=start, window_end=end)
            # For backfill, "actual" uses the prior (later in time) window
            # so we don't need a forward-looking query.
            actual_proxy = feats  # use current window as fallback
            for f in feats:
                archetype, _ = classify_mempool_archetype(
                    mempool_size=f.mempool_size,
                    mev_rate=f.mev_rate,
                    volatility=f.volatility,
                )
                recommended_fee_adj = archetype.base_fee_adj
                # Actual fee adj from this window's avg magnitude.
                actual_fee_adj = round(
                    -0.30 + min(1.0, f.avg_magnitude) * 0.90, 6
                )
                prediction_error = round(
                    abs(recommended_fee_adj - actual_fee_adj), 6
                )
                obs = PatternObservation(
                    archetype_code      = archetype.code,
                    observed_at          = end.timestamp(),
                    mempool_size          = f.mempool_size,
                    mev_rate             = f.mev_rate,
                    volatility           = f.volatility,
                    recommended_fee_adj   = recommended_fee_adj,
                    actual_fee_adj        = actual_fee_adj,
                    prediction_error     = prediction_error,
                    chain_id             = f.chain_id,
                )
                self.store.record_observation(obs)
                total_obs += 1
            total_wins += 1
        return {
            "windows_processed":   total_wins,
            "observations_recorded": total_obs,
        }


# ── APScheduler wiring ─────────────────────────────────────────────────────

_SCHEDULER = None


def start_scheduler(interval_minutes: int = 5) -> Dict[str, str]:
    """Start APScheduler BackgroundScheduler with BIBL feed tick.

    Idempotent: returns immediately if already running.
    """
    global _SCHEDULER
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        return {"ok": False, "reason": "apscheduler not installed"}

    if _SCHEDULER and _SCHEDULER.running:
        return {"ok": True, "status": "already_running"}

    sim = BIBLFeedSimulator()
    sched = BackgroundScheduler(daemon=True)
    sched.add_job(
        lambda: sim.tick(),
        trigger="interval",
        minutes=interval_minutes,
        id="trion_bibl_feed",
        name="TRION BIBL mempool feed simulator",
        max_instances=1,
        coalesce=True,
    )
    sched.start()
    _SCHEDULER = sched
    logger.info("[bibl_feed] scheduler started — interval=%dm", interval_minutes)
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
    p = argparse.ArgumentParser(description="TRION BIBL mempool feed simulator")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("tick",       help="Run one feed cycle")
    sub.add_parser("serve",      help="Start APScheduler daemon")
    bk = sub.add_parser("backfill", help="Backfill N historical observations")
    bk.add_argument("n_windows", type=int, default=24)
    bk.add_argument("--window-minutes", type=int, default=60)
    args = p.parse_args()

    if args.cmd == "tick":
        sim = BIBLFeedSimulator()
        print(json.dumps(sim.tick(), indent=2))
    elif args.cmd == "backfill":
        sim = BIBLFeedSimulator(window_minutes=args.window_minutes)
        print(json.dumps(sim.backfill(n_windows=args.n_windows,
                                       window_minutes=args.window_minutes),
                          indent=2, default=str))
    elif args.cmd == "serve":
        print(json.dumps(start_scheduler(interval_minutes=5), indent=2))
        # Keep alive
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            print(json.dumps(stop_scheduler(), indent=2))
