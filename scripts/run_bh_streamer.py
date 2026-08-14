#!/usr/bin/env python3
"""BH Streamer keep-alive script for Railway deployment."""
import sys, os, time
sys.path.insert(0, '/app')
os.chdir('/app')
from core.realtime.bh_streamer import start_streamer

s = start_streamer(db_path='/app/bh_ledger.db')
print(f'BH Streamer started: {s.is_running()}', flush=True)

while True:
    time.sleep(60)
    try:
        stats = s.get_stats()
        print(f'[BH] {stats["total_bhs"]:,} BHs, {stats["chains_active"]} chains active', flush=True)
    except Exception:
        pass
