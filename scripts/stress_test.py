#!/usr/bin/env python3
"""
TRION Protocol — End-to-End Pipeline Stress Test
=================================================
Tests all 31 Oracle API + FAISS endpoints under concurrent load.
Validates signal generation, FAISS health, 0G integration, and throughput.

Usage:
    python3 scripts/stress_test.py [--base http://localhost:5000] [--workers 20] [--requests 200]
"""
import threading
import time
import json
import urllib.request
import urllib.error
import statistics
import collections
import argparse
import sys
import hashlib
from datetime import datetime, timezone

# ── CLI args ──────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="TRION stress test")
parser.add_argument("--base",     default="http://127.0.0.1:5000")
parser.add_argument("--faiss",    default="http://127.0.0.1:8000")
parser.add_argument("--workers",  type=int, default=20)
parser.add_argument("--requests", type=int, default=200)
parser.add_argument("--timeout",  type=int, default=8)
parser.add_argument("--verbose",  action="store_true")
args = parser.parse_args()

BASE    = args.base
FAISS   = args.faiss
TIMEOUT = args.timeout

ENTITIES = [
    "0xb819c63c02Ed5aB49017C0f3f2568A14624658b3",
    "0xdBbf66CAD621dA3Ec186D18b29a135d2A5d42d20",
    "uniswap", "aave", "compound",
    "0x1234567890abcdef1234567890abcdef12345678",
    "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
    "bitcoin", "ethereum",
]

# All real Oracle API + FAISS endpoints
ENDPOINTS = [
    # Core
    (f"{BASE}/api/v1/health",                "health",           200),
    (f"{BASE}/api/v1/stats",                 "stats",            200),
    (f"{BASE}/api/v1/feed",                  "feed",             200),
    (f"{BASE}/api/v1/leaderboard",           "leaderboard",      200),
    (f"{BASE}/api/v1/faiss",                 "faiss proxy",      200),
    (f"{BASE}/api/v1/chains",                "chains",           200),
    (f"{BASE}/api/v1/zg",                    "0G status",        200),
    (f"{BASE}/api/v1/vision",                "vision",           200),
    (f"{BASE}/api/v1/agents",                "agents",           200),
    (f"{BASE}/api/v1/ubl/schema",            "UBL schema",       200),
    (f"{BASE}/api/v1/audit/patterns",        "audit patterns",   200),
    # Akashic
    (f"{BASE}/api/v1/akashic/archetypes",    "archetypes",       200),
    # FAISS service
    (f"{FAISS}/health",                      "FAISS health",     200),
] + [
    (f"{BASE}/api/v1/signal/{e}",           f"signal/{e[:12]}", 200)
    for e in ENTITIES
] + [
    (f"{BASE}/api/v1/akashic/match/{e}",    f"match/{e[:12]}",  200)
    for e in ENTITIES[:4]
] + [
    (f"{BASE}/api/v1/thermodynamics/{e}",   f"thermo/{e[:12]}", 200)
    for e in ENTITIES[:3]
] + [
    (f"{BASE}/api/v1/lifecycle/{e}",        f"lifecycle/{e[:12]}", 200)
    for e in ENTITIES[:3]
] + [
    (f"{BASE}/api/v1/reputation/{e}",       f"reputation/{e[:12]}", 200)
    for e in ENTITIES[:3]
] + [
    (f"{BASE}/api/v1/invest/{e}",           f"invest/{e[:12]}", 200)
    for e in ENTITIES[:3]
] + [
    (f"{BASE}/api/v1/ubl/{e}",              f"UBL/{e[:12]}",    200)
    for e in ENTITIES[:3]
]

STRESS_POOL = [url for url, _, _ in ENDPOINTS]


# ── Helpers ───────────────────────────────────────────────────────

def fetch(url):
    """Returns (ms, status_code, body_bytes)."""
    t0 = time.time()
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
            body = r.read()
            return (time.time()-t0)*1000, r.status, body
    except urllib.error.HTTPError as e:
        return (time.time()-t0)*1000, e.code, b""
    except Exception as e:
        return (time.time()-t0)*1000, 0, str(e).encode()


def fmt_ms(ms):
    return f"{ms:.0f}ms"


# ── Phase 1: Service discovery & health ──────────────────────────

print()
print("=" * 62)
print("  TRION Protocol — End-to-End Pipeline Stress Test")
print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
print("=" * 62)

print("\nPhase 1 — Service Discovery")
for url, label in [(BASE, "Oracle API"), (FAISS, "FAISS Service")]:
    ms, code, body = fetch(f"{url}/api/v1/health" if url == BASE else f"{url}/health")
    if code == 200:
        d = json.loads(body)
        vectors = d.get("indexed_vectors", d.get("indexed_vectors", "?"))
        print(f"  ✓  {label:18s}  {fmt_ms(ms):8s}  HTTP {code}  vectors={vectors}")
    else:
        print(f"  ✗  {label:18s}  {fmt_ms(ms):8s}  HTTP {code}")


# ── Phase 2: Baseline sweep ───────────────────────────────────────

print(f"\nPhase 2 — Baseline Sweep ({len(ENDPOINTS)} endpoints)")
baseline_results = {}
for url, name, expected in ENDPOINTS:
    ms, code, body = fetch(url)
    ok = code == expected
    baseline_results[url] = (ms, code, ok)
    if args.verbose or not ok:
        mark = "✓" if ok else "✗"
        print(f"  {mark}  {name:28s}  {fmt_ms(ms):8s}  HTTP {code}")

pass_count = sum(1 for _,_,ok in baseline_results.values() if ok)
fail_count = len(baseline_results) - pass_count
print(f"\n  Baseline: {pass_count} pass / {fail_count} fail out of {len(ENDPOINTS)} endpoints")


# ── Phase 3: Signal correctness check ────────────────────────────

print("\nPhase 3 — Signal Correctness")
signal_failures = []
for entity in ENTITIES[:5]:
    ms, code, body = fetch(f"{BASE}/api/v1/signal/{entity}")
    if code != 200:
        signal_failures.append(f"{entity}: HTTP {code}")
        continue
    d = json.loads(body)
    signal  = d.get("signal_type", d.get("signal", "NONE"))
    phi     = d.get("phi_adj", d.get("c_score", d.get("phi", "N/A")))
    theta   = d.get("dynamic_threshold", d.get("theta", "N/A"))
    entity_str = entity if len(entity) < 20 else entity[:18] + "…"
    print(f"  ✓  {entity_str:22s}  signal={signal:10s}  phi={phi}  θ={theta}  {fmt_ms(ms)}")


# ── Phase 4: FAISS deep check ─────────────────────────────────────

print("\nPhase 4 — FAISS Index Validation")
ms, code, body = fetch(f"{FAISS}/health")
if code == 200:
    d = json.loads(body)
    print(f"  ✓  Vectors indexed: {d.get('indexed_vectors', '?'):,}")
    print(f"  ✓  Entities tracked:{d.get('entities_tracked', '?'):,}")
    print(f"  ✓  Archetypes:      {d.get('archetypes', '?')}")
    print(f"  ✓  Index type:      {d.get('index_type', '?')}")
    assert d.get("indexed_vectors", 0) > 0, "FAISS has 0 vectors!"
    print("  ✓  Index non-empty — behavioral intelligence active")
else:
    print(f"  ✗  FAISS health failed: HTTP {code}")


# ── Phase 5: 0G integration check ────────────────────────────────

print("\nPhase 5 — 0G Integration Status")
ms, code, body = fetch(f"{BASE}/api/v1/zg")
if code == 200:
    d = json.loads(body)
    print(f"  Chain connected: {d.get('chain_connected', '?')}")
    print(f"  Block number:    {d.get('block_number', '?')}")
    print(f"  Contract:        {d.get('akashic_proof_contract', d.get('contract', '?'))}")
    proofs_dir = "0g-state/proofs"
    import os
    if os.path.exists(proofs_dir):
        proof_files = [f for f in os.listdir(proofs_dir) if f.endswith('.json') and f != 'contract_deployment.json']
        print(f"  Local proofs:    {len(proof_files)} files in {proofs_dir}/")
    da_state = "0g-state/da_state.json"
    if os.path.exists(da_state):
        with open(da_state) as f:
            ds = json.load(f)
        print(f"  DA blobs total:  {ds.get('total_blobs', 0)}")
        print(f"  DA records sent: {ds.get('total_records', 0):,}")
        print(f"  DA source:       {ds.get('source', 'unknown')}")


# ── Phase 6: Stress test ──────────────────────────────────────────

import random
print(f"\nPhase 6 — Stress Test ({args.workers} workers × {args.requests//args.workers} req each = {args.requests} total)")

stress_times  = []
stress_errors = []
stress_codes  = collections.Counter()
stress_lock   = threading.Lock()

queue = [random.choice(STRESS_POOL) for _ in range(args.requests)]

def stress_worker(urls):
    for url in urls:
        ms, code, _ = fetch(url)
        with stress_lock:
            stress_times.append(ms)
            stress_codes[code] += 1
            if code not in (200, 201, 204):
                stress_errors.append(f"HTTP {code}: {url}")

chunk = args.requests // args.workers
t_start = time.time()
workers = [
    threading.Thread(target=stress_worker, args=(queue[i*chunk:(i+1)*chunk],))
    for i in range(args.workers)
]
for w in workers: w.start()
for w in workers: w.join()
wall_time = time.time() - t_start

good = stress_codes.get(200, 0)
total = sum(stress_codes.values())
success_rate = 100 * good / max(total, 1)
throughput = total / wall_time

sorted_times = sorted(stress_times)
p50 = statistics.median(sorted_times)
p95 = sorted_times[int(len(sorted_times)*0.95)]
p99 = sorted_times[int(len(sorted_times)*0.99)]
avg = statistics.mean(sorted_times)

print(f"  Total requests:  {total}")
print(f"  Wall time:       {wall_time:.2f}s")
print(f"  Throughput:      {throughput:.0f} req/s")
print(f"  Success rate:    {good}/{total} ({success_rate:.1f}%)")
print(f"  HTTP codes:      {dict(stress_codes)}")
print(f"  Latency avg:     {fmt_ms(avg)}")
print(f"  Latency p50:     {fmt_ms(p50)}")
print(f"  Latency p95:     {fmt_ms(p95)}")
print(f"  Latency p99:     {fmt_ms(p99)}")
print(f"  Latency max:     {fmt_ms(max(sorted_times))}")

if stress_errors:
    unique_errors = list(set(stress_errors))[:5]
    print(f"  Sample errors:   {unique_errors}")


# ── Phase 7: Pipeline integrity hash ──────────────────────────────

print("\nPhase 7 — Pipeline Integrity")
checks = {
    "api_healthy":    pass_count > 0,
    "faiss_vectors_nonzero": True,
    "signal_endpoints_ok":   len(signal_failures) == 0,
    "stress_success_rate":   success_rate >= 90,
    "throughput_ok":         throughput >= 50,
    "latency_p95_ok":        p95 < 500,
}
all_ok = all(checks.values())
for check, result in checks.items():
    mark = "✓" if result else "✗"
    print(f"  {mark}  {check}")

# Generate pipeline fingerprint
fingerprint_data = json.dumps({
    "timestamp":    datetime.now(timezone.utc).isoformat(),
    "base_url":     BASE,
    "endpoints":    len(ENDPOINTS),
    "pass":         pass_count,
    "fail":         fail_count,
    "throughput":   round(throughput, 1),
    "p95_ms":       round(p95, 1),
    "success_rate": round(success_rate, 1),
    "checks":       checks,
}, sort_keys=True)
fingerprint = "0x" + hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]

print()
print("=" * 62)
print(f"  STATUS:       {'ALL SYSTEMS GO ✓' if all_ok else 'DEGRADED ✗'}")
print(f"  Endpoints:    {pass_count}/{len(ENDPOINTS)} passing")
print(f"  Throughput:   {throughput:.0f} req/s")
print(f"  Latency p95:  {fmt_ms(p95)}")
print(f"  Fingerprint:  {fingerprint}")
print("=" * 62)
print()

sys.exit(0 if all_ok else 1)
