#!/usr/bin/env python3
"""BH Streamer keep-alive script for Railway deployment.
Uses BH_LEDGER_DB env (set by entrypoint) with /app fallback for containers."""
import sys, os, time
sys.path.insert(0, os.environ.get("TRION_ROOT", "/app"))
os.chdir(os.environ.get("TRION_ROOT", "/app"))
from core.realtime.bh_streamer import start_streamer

DB = os.environ.get("BH_LEDGER_DB", "/app/bh_ledger.db")
s = start_streamer(db_path=DB)
print(f'BH Streamer started: {s.is_running()} db={DB}', flush=True)

while True:
    time.sleep(60)
    try:
        stats = s.get_stats()
        print(f'[BH] {stats["total_bhs"]:,} BHs, {stats["chains_active"]} chains active', flush=True)
    except Exception:
        pass
