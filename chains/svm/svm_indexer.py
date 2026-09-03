#!/usr/bin/env python3
"""
TRION L0-SVM — Solana Behavioral Indexer
=========================================
Polls Solana mainnet RPC slot-by-slot, computes whitepaper L1.1 Φ-features
(Shannon entropies of program-id, fee, compute-unit, account-touch and
instruction-type distributions) for each block, and POSTs a 128-dim behavioral
vector batch to the FAISS service with vm_type="SVM".

Mirrors the contract followed by trion-l0/src/main.rs for EVM chains, but uses
Solana JSON-RPC (getSlot / getBlock) instead of eth_blockNumber / eth_getBlock.

Environment:
  SOLANA_RPC_URL    Solana JSON-RPC endpoint  (default: https://api.mainnet-beta.solana.com)
  SOLANA_CHAIN_ID   Numeric chain id          (default: 900  — canonical Solana Mainnet SVM id)
  SOLANA_LABEL      Human label               (default: "SOLANA_MAINNET")
  FAISS_SERVICE_URL FAISS ingest target       (default: http://127.0.0.1:8000)
  POLL_SLEEP_MS     Slot poll interval        (default: 800ms — Solana slot ≈400ms)

FIX-CLAIMS (chain-ID collision): the previous default was 101 — a local id that
collided with chains/sui (Sui, since moved to canonical 20100) and drifted from
the canonical registry. config/chain_registry.json (single source of truth per
P3-CONSOLIDATE; see core/generated_chain_bindings.py) assigns Solana Mainnet=900,
and chains/svm/execute.ts already used 900. GAP-PY follow-up: the
api/chains_registry.py display entries are now re-pointed to the canonical ids
(solana=900, solana-dev=901, sui=20100). Pre-existing inconsistencies left in
place (fixture/data entanglement — see FIX-CLAIMS report):
tests/integration/test_anima_full.py §2e posts (101, "solana"); crossvm
fixtures use 900 for "Solana Devnet" while canonical Devnet is 901;
core/realtime/bh_streamer.py uses 200101 for solana.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import time
from collections import Counter
from typing import Any

import requests

SOLANA_RPC_URL    = os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
SOLANA_CHAIN_ID   = int(os.environ.get("SOLANA_CHAIN_ID", "900"))  # canonical Solana Mainnet (was 101 — see module docstring)
SOLANA_LABEL      = os.environ.get("SOLANA_LABEL", "SOLANA_MAINNET")
FAISS_SERVICE_URL = os.environ.get("FAISS_SERVICE_URL", "http://127.0.0.1:8000").rstrip("/")
POLL_SLEEP_MS     = int(os.environ.get("POLL_SLEEP_MS", "800"))

DIM = 128

session = requests.Session()
session.headers.update({"Content-Type": "application/json"})


def rpc(method: str, params: list[Any]) -> Any:
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    r = session.post(SOLANA_RPC_URL, data=json.dumps(body), timeout=15)
    r.raise_for_status()
    j = r.json()
    if "error" in j:
        raise RuntimeError(f"RPC error {method}: {j['error']}")
    return j.get("result")


def shannon(counter: Counter) -> float:
    total = sum(counter.values())
    if total <= 0:
        return 0.0
    h = 0.0
    for v in counter.values():
        if v <= 0:
            continue
        p = v / total
        h -= p * math.log2(p)
    # Normalize to [0,1] by dividing by log2(N) where N = unique categories
    n = len(counter)
    if n <= 1:
        return 0.0
    return h / math.log2(n)


def features_from_block(block: dict) -> tuple[list[float], dict]:
    """Compute the 9 Φ-features + per-vector data for a Solana block."""
    txs = block.get("transactions") or []
    fee_counter = Counter()
    cu_counter = Counter()        # log10-bucketed CU (used for f5)
    cu_linear_counter = Counter() # linear-bucketed CU (used for f8 — distinct from f5)
    program_counter = Counter()
    account_counter = Counter()
    instr_count_counter = Counter()
    err_counter = Counter()
    acct_per_tx_counter = Counter()   # for f7: accounts-per-tx complexity entropy
    joint_fee_cu_counter = Counter()  # for f9: joint fee × CU correlation entropy

    total_lamports = 0
    successful = 0
    failed = 0

    for entry in txs:
        meta = entry.get("meta") or {}
        tx = entry.get("transaction") or {}
        msg = (tx.get("message") if isinstance(tx, dict) else {}) or {}

        fee = int(meta.get("fee") or 0)
        cu = int(meta.get("computeUnitsConsumed") or 0)
        err = meta.get("err")

        # Bin lamport fees and CU into log buckets for entropy stability
        fee_bucket = 0 if fee == 0 else int(math.floor(math.log10(fee + 1)))
        cu_bucket = 0 if cu == 0 else int(math.floor(math.log10(cu + 1)))
        fee_counter[fee_bucket] += 1
        cu_counter[cu_bucket] += 1
        # Linear CU bucket for f8 (distinct from log10 cu_bucket used in f5)
        cu_lin_bucket = (0 if cu == 0 else
                         1 if cu < 50_000 else
                         2 if cu < 200_000 else
                         3 if cu < 500_000 else
                         4 if cu < 1_000_000 else 5)
        cu_linear_counter[cu_lin_bucket] += 1

        if err is None:
            successful += 1
            err_counter["ok"] += 1
        else:
            failed += 1
            err_counter["err"] += 1

        accts = msg.get("accountKeys") or []
        for a in accts:
            # accountKeys may be strings or {"pubkey": ...} objects
            key = a if isinstance(a, str) else a.get("pubkey") if isinstance(a, dict) else None
            if key:
                account_counter[key] += 1

        # f7 tracking: bin accounts-per-tx into log2 buckets (tx complexity diversity)
        n_accts = len(accts)
        acct_bin = 0 if n_accts == 0 else min(5, int(math.floor(math.log2(n_accts + 1))))
        acct_per_tx_counter[acct_bin] += 1

        # f9 tracking: joint (fee_bucket, cu_bucket) for correlation entropy
        joint_fee_cu_counter[(fee_bucket, cu_bucket)] += 1

        instrs = msg.get("instructions") or []
        instr_count_counter[len(instrs)] += 1
        for ix in instrs:
            pid_idx = ix.get("programIdIndex")
            if isinstance(pid_idx, int) and 0 <= pid_idx < len(accts):
                pid = accts[pid_idx] if isinstance(accts[pid_idx], str) else (accts[pid_idx].get("pubkey") if isinstance(accts[pid_idx], dict) else None)
                if pid:
                    program_counter[pid] += 1

        total_lamports += fee

    # f1..f9 per L1.1 (Solana-mapped):
    # f1 fee entropy, f2 account diversity, f3 tx-success ratio entropy,
    # f4 program diversity, f5 cu entropy, f6 instr-count entropy,
    # f7 program concentration (1-Gini-style proxy via top-k share),
    # f8 cu/fee correlation proxy, f9 reserved (set to overall block entropy).
    f1 = shannon(fee_counter)
    f2 = shannon(account_counter)
    f3 = shannon(err_counter)
    f4 = shannon(program_counter)
    f5 = shannon(cu_counter)
    f6 = shannon(instr_count_counter)
    # f7: Shannon entropy of accounts-per-tx distribution (tx complexity diversity)
    #     H(log2-binned account counts per tx) — distinct from f2 (unique accounts)
    f7 = shannon(acct_per_tx_counter)
    # f8: Shannon entropy of CU linear-bucket distribution (distinct from f5)
    #     f5 uses log10 buckets (scale-invariant); f8 uses linear buckets (scale-sensitive)
    #     This captures whether CU distribution is skewed toward specific cost tiers
    f8 = shannon(cu_linear_counter)
    # f9: Shannon entropy of joint (fee_bucket × cu_bucket) distribution
    #     Captures fee-compute correlation patterns — independent signal from f1/f5
    f9 = shannon(joint_fee_cu_counter)

    feats = [f1, f2, f3, f4, f5, f6, f7, f8, f9]

    stats = {
        "tx_count": len(txs),
        "successful": successful,
        "failed": failed,
        "total_fee_lamports": total_lamports,
        "unique_programs": len(program_counter),
        "unique_accounts": len(account_counter),
        "phi": sum(feats) / 9.0,
    }
    return feats, stats


def vector_from_features(feats: list[float], slot: int) -> list[float]:
    """Expand the 9 features into a deterministic 128-dim behavioural vector.
    Bands 0-15 = f1, 16-31 = f2, ... 128-143 = f9 (last 17 reserved for slot
    salt to prevent collapse to a single FAISS centroid).
    """
    out: list[float] = []
    band = DIM // 9
    for v in feats:
        out.extend([float(v)] * band)
    # pad to DIM with a deterministic slot-derived salt
    seed = hashlib.sha256(f"{slot}".encode()).digest()
    while len(out) < DIM:
        b = seed[(len(out) - DIM) % 32]
        out.append((b / 255.0) - 0.5)
    return out[:DIM]


def push_block(slot: int, feats: list[float], stats: dict) -> None:
    entity_id = f"solana:slot:{slot}"
    vector = vector_from_features(feats, slot)
    payload = {
        "vectors": [{
            "entity_id":   entity_id,
            "vector":      vector,
            "magnitude":   max(1.0, math.log10(stats["total_fee_lamports"] + 1)),
            "entropy":     stats["phi"],
            "block_num":   slot,
            "chain_id":    SOLANA_CHAIN_ID,
            "chain_label": SOLANA_LABEL,
            "vm_type":     "SVM",
        }],
        "block_num":      slot,
        "block_features": feats,
        "block_phi":      stats["phi"],
        "entity_id":      entity_id,
        "chain_id":       SOLANA_CHAIN_ID,
        "chain_label":    SOLANA_LABEL,
        "vm_type":        "SVM",
        "metadata": {
            "source":       "trion-svm",
            "tx_count":     stats["tx_count"],
            "successful":   stats["successful"],
            "failed":       stats["failed"],
            "total_fee":    stats["total_fee_lamports"],
            "programs":     stats["unique_programs"],
            "accounts":     stats["unique_accounts"],
        },
    }
    url = f"{FAISS_SERVICE_URL}/index/add_batch"
    # Circuit breaker: when FAISS has been failing, back off so we don't
    # pile more requests into its queue (which is the main cause of
    # cascading 15s timeouts). Returns True on success, False on failure.
    global _faiss_failures, _faiss_skip_until
    now_ts = time.monotonic()
    if now_ts < _faiss_skip_until:
        return False
    try:
        # Short timeout (4s) so a slow FAISS doesn't hold the indexer thread
        # for 15s per slot. If FAISS can't respond in 4s it's saturated and
        # retrying will only make it worse — let the circuit breaker kick in.
        r = session.post(url, data=json.dumps(payload), timeout=4)
        if r.status_code != 200:
            print(f"[svm][slot={slot}] FAISS POST {r.status_code}: {r.text[:200]}", file=sys.stderr)
            _faiss_failures += 1
        else:
            j = r.json()
            print(f"[svm][slot={slot}] txs={stats['tx_count']:>4} ok={stats['successful']:>4} "
                  f"fail={stats['failed']:>3} prog={stats['unique_programs']:>3} "
                  f"acct={stats['unique_accounts']:>4} Φ={stats['phi']:.4f} "
                  f"→ added={j.get('added',0)} idx_total={j.get('indexed_vectors','?')}")
            _faiss_failures = 0
            return True
    except requests.RequestException as e:
        print(f"[svm][slot={slot}] FAISS POST failed: {e}", file=sys.stderr)
        _faiss_failures += 1
    # On 3+ consecutive failures: open circuit for 30s, giving FAISS room
    # to drain its queue and serve oracle reads (mental/spiritual/etc).
    if _faiss_failures >= 3:
        _faiss_skip_until = time.monotonic() + 30.0
        print(f"[svm] FAISS circuit OPEN for 30s (consecutive failures={_faiss_failures})", file=sys.stderr)
        _faiss_failures = 0
    return False


# Circuit-breaker state — used by post_to_faiss above.
_faiss_failures: int = 0
_faiss_skip_until: float = 0.0


def main() -> int:
    print("===============================================================")
    print(" TRION L0-SVM: SOLANA BEHAVIORAL INDEXER")
    print("===============================================================")
    print(f" RPC          : {SOLANA_RPC_URL}")
    print(f" Chain id     : {SOLANA_CHAIN_ID}  ({SOLANA_LABEL})")
    print(f" FAISS target : {FAISS_SERVICE_URL}")
    print(f" Poll         : {POLL_SLEEP_MS}ms")
    print(" Streaming live Solana slots into FAISS. Press Ctrl+C to stop.")
    print()

    # Public Solana RPCs typically only serve `getBlock` for slots that are
    # already FINALIZED. To stay reliably inside that window we keep our
    # cursor a fixed offset behind the finalized tip. SAFE_LAG = 40 slots
    # ≈ 16 s — well past the 32-block finality window.
    SAFE_LAG = 40
    last_slot = 0
    consecutive_failures = 0

    while True:
        try:
            current = rpc("getSlot", [{"commitment": "finalized"}])
            if not isinstance(current, int):
                time.sleep(POLL_SLEEP_MS / 1000.0)
                continue

            if last_slot == 0:
                last_slot = current - SAFE_LAG

            # Stay at least SAFE_LAG behind the finalized tip
            tip = current - SAFE_LAG
            if tip <= last_slot:
                time.sleep(POLL_SLEEP_MS / 1000.0)
                continue

            target = last_slot + 1
            try:
                block = rpc("getBlock", [target, {
                    "encoding": "json",
                    "transactionDetails": "full",
                    "maxSupportedTransactionVersion": 0,
                    "rewards": False,
                    "commitment": "finalized",
                }])
                consecutive_failures = 0
            except RuntimeError as e:
                msg = str(e)
                # Skipped slot (-32007 / -32009) — advance silently
                if "-32007" in msg or "-32009" in msg or "skipped" in msg.lower():
                    last_slot = target
                    continue
                # Slot data missing (-32004) — typically the public node hasn't
                # caught up. Skip ahead a bit and retry rather than spinning.
                if "-32004" in msg or "not available" in msg.lower() or "older than" in msg.lower():
                    consecutive_failures += 1
                    # Jump forward by min(consecutive_failures * 5, 100) slots,
                    # but never past the safe tip.
                    jump = min(consecutive_failures * 5, 100)
                    last_slot = min(last_slot + jump, tip)
                    if consecutive_failures % 20 == 1:
                        print(f"[svm] block missing for slot {target}, advancing +{jump} (cursor={last_slot}, tip={tip})", file=sys.stderr)
                    time.sleep(0.3)
                    continue
                raise

            if not block:
                last_slot = target
                continue

            feats, stats = features_from_block(block)
            push_block(target, feats, stats)
            last_slot = target
            consecutive_failures = 0

        except KeyboardInterrupt:
            print("\n[svm] shutdown requested")
            return 0
        except requests.HTTPError as e:
            # 429 = rate limited. Public Solana RPCs throttle aggressively;
            # back off for a longer window and resume from current confirmed slot.
            status = getattr(e.response, "status_code", None)
            if status == 429:
                print(f"[svm] rate-limited (429), sleeping 15s", file=sys.stderr)
                time.sleep(15.0)
                last_slot = 0   # re-bootstrap from current confirmed slot
            else:
                print(f"[svm] HTTP {status}: {e}", file=sys.stderr)
                time.sleep(3.0)
        except Exception as e:
            msg = str(e)
            if "429" in msg or "Too Many Requests" in msg:
                print(f"[svm] rate-limited (429), sleeping 15s", file=sys.stderr)
                time.sleep(15.0)
                last_slot = 0
            else:
                print(f"[svm] loop error: {e}", file=sys.stderr)
                time.sleep(2.0)


if __name__ == "__main__":
    sys.exit(main())
