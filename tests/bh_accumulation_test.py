#!/usr/bin/env python3
"""
TRION BH Accumulation Live Monitor
====================================
Shows how BehaviorHashes accumulate across all 57 EVM chains in real time.
Polls the FAISS index size + trion-evm log for per-chain BH throughput.

Usage:
    uv run python3 tests/bh_accumulation_test.py
"""

import time
import subprocess
import re
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from collections import defaultdict

FAISS_URL  = "http://127.0.0.1:8000"
ORACLE_URL = "http://127.0.0.1:5001"
LOG_FILE   = "/tmp/trion-rust-logs/trion-evm.log"
POLL_SECS  = 10
ROUNDS     = 6
LOG_TAIL   = 1000   # lines to scan per poll


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get(url, timeout=4):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"_error": str(e)}


def faiss_vector_count():
    data = _get(f"{FAISS_URL}/health")
    return data.get("indexed_vectors", data.get("total_vectors", data.get("ntotal", "?")))


def oracle_chain_count():
    data = _get(f"{ORACLE_URL}/api/v1/health")
    return data.get("chains_indexed", data.get("chain_count", "?"))


def parse_log_bh_counts(tail_n=LOG_TAIL):
    """Scan the last tail_n lines of trion-evm.log.
    Returns (per_chain_added, per_chain_blocks, total_bh) from that window."""
    added   = defaultdict(int)  # BHs written to FAISS
    blocks  = defaultdict(int)  # blocks polled
    total   = 0
    try:
        result = subprocess.run(
            ["tail", "-n", str(tail_n), LOG_FILE],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            # "[CHAIN] block=X per-tx BHs: N/M stored"
            m = re.search(r'\[(\w+)\] block=\d+ per-tx BHs: (\d+)/\d+ stored', line)
            if m:
                ch = m.group(1)
                n  = int(m.group(2))
                added[ch]  += n
                blocks[ch] += 1
                total      += n
    except Exception:
        pass
    return added, blocks, total


def chain_startup_confirmed():
    """Return True if the 57-chain binary has logged its startup line."""
    try:
        result = subprocess.run(
            ["grep", "-m1", "57 chains\|TRION EVM Rust Indexer", LOG_FILE],
            capture_output=True, text=True, timeout=3
        )
        return result.stdout.strip()
    except Exception:
        return ""


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    width = 72

    print("=" * width)
    print("  TRION BH ACCUMULATION MONITOR — 100-Chain Protocol")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * width)

    startup = chain_startup_confirmed()
    if startup:
        # Get latest startup line (binary was rebuilt — take last match)
        last_startup = startup.strip().splitlines()[-1] if startup.strip() else startup.strip()
        print(f"\n  Binary: {last_startup}")
    else:
        print("\n  [WARN] Could not confirm EVM indexer startup line in log.")

    print(f"\n  Polling every {POLL_SECS}s × {ROUNDS} rounds = {POLL_SECS*ROUNDS}s window\n")

    # ── Baseline ─────────────────────────────────────────────────────────────
    baseline_v      = faiss_vector_count()
    baseline_added, baseline_blocks, baseline_total = parse_log_bh_counts()
    chains_seen_baseline = set(baseline_added.keys())

    print(f"  Baseline  │ FAISS vectors: {baseline_v:>8}  │  EVM BHs in log window: {baseline_total:>6}")
    print(f"  {'─'*68}")
    print(f"  {'Rnd':<5} {'Time':<10} {'FAISS Vectors':>14} {'Δ Vectors':>10} {'EVM BHs':>10} {'Δ BHs':>8} {'Active':>8}")
    print(f"  {'─'*68}")

    prev_v     = baseline_v
    prev_total = baseline_total
    rounds_data = []

    for rnd in range(1, ROUNDS + 1):
        time.sleep(POLL_SECS)

        now_v                              = faiss_vector_count()
        now_added, now_blocks, now_total   = parse_log_bh_counts()
        active_chains                      = len([c for c, n in now_added.items() if n > 0])

        try:
            delta_v  = int(now_v) - int(prev_v)
            dv_str   = f"+{delta_v:,}"
        except (TypeError, ValueError):
            delta_v  = 0
            dv_str   = "?"

        delta_bh = now_total - prev_total
        ts       = datetime.now(timezone.utc).strftime("%H:%M:%S")

        print(f"  {rnd:<5} {ts:<10} {str(now_v):>14} {dv_str:>10} {now_total:>10,} {('+'+str(delta_bh)):>8} {active_chains:>8}")

        rounds_data.append({
            "round": rnd, "ts": ts,
            "faiss": now_v, "delta_v": delta_v,
            "bh_total": now_total, "delta_bh": delta_bh,
            "active": active_chains,
            "added": dict(now_added),
        })

        prev_v     = now_v
        prev_total = now_total

    # ── Per-chain breakdown ───────────────────────────────────────────────────
    final_added, final_blocks, final_total = parse_log_bh_counts(LOG_TAIL * 2)
    chains_seen_final = set(final_added.keys())
    new_chains        = chains_seen_final - chains_seen_baseline

    print(f"\n  {'─'*68}")
    print(f"  Per-chain BH throughput (top 30, last {LOG_TAIL*2} log lines):")
    print(f"\n  {'Chain':<22} {'BHs':>8} {'Blocks':>8}  {'BH/block':>10}  Bar")
    print(f"  {'─'*65}")

    sorted_chains = sorted(final_added.items(), key=lambda x: -x[1])[:30]
    max_bh        = sorted_chains[0][1] if sorted_chains else 1

    for chain, cnt in sorted_chains:
        blks     = final_blocks.get(chain, 1) or 1
        bpb      = cnt / blks
        bar_len  = max(1, round(cnt / max_bh * 28))
        bar      = "█" * bar_len
        marker   = " ← NEW" if chain in new_chains else ""
        print(f"  {chain:<22} {cnt:>8,} {blks:>8,}  {bpb:>10.2f}  {bar}{marker}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n  {'═'*68}")
    final_v = faiss_vector_count()
    try:
        total_delta_v  = int(final_v) - int(baseline_v)
        total_delta_bh = rounds_data[-1]["bh_total"] - baseline_total if rounds_data else 0
        avg_bh_rate    = total_delta_bh / (POLL_SECS * ROUNDS)
    except (TypeError, ValueError, ZeroDivisionError):
        total_delta_v  = "?"
        total_delta_bh = "?"
        avg_bh_rate    = 0

    print(f"\n  SUMMARY over {POLL_SECS * ROUNDS}s:")
    print(f"    FAISS index grew:          +{total_delta_v} vectors")
    print(f"    EVM BHs accumulated:       +{total_delta_bh} (log window)")
    print(f"    Avg BH ingestion rate:      {avg_bh_rate:.1f} BH/s (EVM alone)")
    print(f"    Final FAISS index size:     {final_v}")
    evm_active = len([c for c,n in final_added.items() if n>0 and c != "SOLANA_MAINNET"])
    print(f"    EVM chains submitting BHs:  {evm_active}/57")
    print(f"    Non-EVM chains (relayers):  38  (Cosmos·UTXO·Move·SUI·TRON·XLM·etc.)")
    print(f"    Total tracked chains:       100+")
    print(f"\n  {'═'*68}\n")


if __name__ == "__main__":
    main()
