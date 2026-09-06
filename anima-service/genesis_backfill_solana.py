#!/usr/bin/env python3
"""
TRION Akashic Index — Solana Genesis Bootstrap / Historical Backfill
Whitepaper mandate: Full chain history from genesis, zero gaps.

Mirrors akashic/genesis_backfill.py but walks Solana slots via getBlock
instead of EVM eth_getBlockByNumber. Ingests every Solana block into the
Akashic FAISS Intelligence Engine (128-dim behavioral vectors), which in
turn dual-writes to TimescaleDB when TIMESCALEDB_URL is configured.

Usage:
    python genesis_backfill_solana.py --start-slot 0 --end-slot latest
"""

import os
import sys
import json
import math
import time
import hashlib
import logging
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import numpy as np

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [SOL-BACKFILL] %(message)s")
logger = logging.getLogger(__name__)

DIMENSION   = 128
FAISS_URL   = os.environ.get("FAISS_SERVICE_URL", "http://127.0.0.1:8000")
FAISS_KEY  = (os.environ.get("FAISS_API_KEY") or os.environ.get("FAISS_SERVICE_API_KEY")
              or os.environ.get("TRION_API_KEY") or "")
_HDRS      = {"X-API-Key": FAISS_KEY} if FAISS_KEY else {}   # SEC-01: FAISS service auth

SOLANA_RPC  = os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
CHAIN_ID    = 900   # canonical registry id (config/chain_registry.json); trion-svm indexer uses 900 too (was 101)
CHAIN_NAME  = "sol-mainnet"
WORKERS     = int(os.environ.get("BACKFILL_WORKERS", "2"))   # public RPC — stay conservative
BATCH_SIZE  = int(os.environ.get("BACKFILL_BATCH", "20"))


def rpc_call(method: str, params: list) -> Optional[dict]:
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    try:
        r = requests.post(SOLANA_RPC, json=body, timeout=15)
        data = r.json()
        if "error" in data:
            logger.debug("RPC error (%s): %s", method, data["error"])
            return None
        return data.get("result")
    except Exception as e:
        logger.warning("RPC error (%s): %s", method, e)
        return None


def get_latest_slot() -> int:
    result = rpc_call("getSlot", [])
    return int(result) if result else 0


def get_block(slot: int) -> Optional[dict]:
    return rpc_call("getBlock", [slot, {
        "encoding": "json",
        "transactionDetails": "full",
        "rewards": False,
        "maxSupportedTransactionVersion": 0,
    }])


def extract_features(block: dict) -> Optional[np.ndarray]:
    txs = block.get("transactions", [])
    if not txs:
        return None

    senders, involved = set(), set()
    total_fee = 0
    failed = 0
    ix_counts = []

    for tx in txs:
        meta = tx.get("meta") or {}
        msg = (tx.get("transaction") or {}).get("message") or {}
        keys = msg.get("accountKeys", [])
        if keys:
            senders.add(keys[0] if isinstance(keys[0], str) else keys[0].get("pubkey", ""))
            for k in keys:
                involved.add(k if isinstance(k, str) else k.get("pubkey", ""))
        total_fee += meta.get("fee", 0) or 0
        if meta.get("err") is not None:
            failed += 1
        ix_counts.append(len(msg.get("instructions", [])))

    n = len(txs)
    ix_counts.sort()
    total_ix = sum(ix_counts) or 1
    top10_start = max(0, int(n * 0.90))
    top10_ix = sum(ix_counts[top10_start:])

    f1 = n
    f2 = total_fee / max(n, 1)
    f3 = total_fee / 1e9
    f4 = len(senders) / n
    f5 = len(involved) / max(len(senders), 1)
    f6 = sum(1 for c in ix_counts if c > 1) / n  # proxy for program/contract interactions
    f7 = top10_ix / total_ix
    f8 = failed / n
    diversity = f4 * 0.25 + min(f5 / 2.0, 1.0) * 0.15
    activity  = f6 * 0.20
    health    = (1.0 - f8) * 0.25 + (1.0 - min(f7, 1.0)) * 0.15
    f9 = min(diversity + activity + health, 1.0)

    base = np.array([f1 / 1000.0, f2 / 1e6, f3, f4, f5, f6, f7, f8, f9], dtype="float64")
    vec = np.zeros(DIMENSION, dtype="float32")
    for i, val in enumerate(base):
        for k in range(14):
            idx = i * 14 + k
            if idx < DIMENSION:
                vec[idx] = float(val * math.cos(k * math.pi / 14.0))

    block_hash = block.get("blockhash", "0" * 44)
    hash_bytes = hashlib.sha3_256(block_hash.encode()).digest()
    for i in range(min(10, DIMENSION)):
        vec[-(i + 1)] = float(hash_bytes[i]) / 255.0

    return vec


def compute_magnitude(block: dict) -> float:
    txs = block.get("transactions", [])
    if not txs:
        return 0.0
    total_fee = sum((tx.get("meta") or {}).get("fee", 0) or 0 for tx in txs)
    return min(1.0, total_fee / 1e9)


def compute_entropy(block: dict) -> float:
    txs = block.get("transactions", [])
    n = len(txs)
    if n == 0:
        return 0.0
    senders = set()
    for tx in txs:
        keys = (((tx.get("transaction") or {}).get("message") or {}).get("accountKeys", []))
        if keys:
            senders.add(keys[0] if isinstance(keys[0], str) else keys[0].get("pubkey", ""))
    return min(1.0, len(senders) / n)


def load_checkpoint(path: str) -> dict:
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"last_slot": -1, "indexed": 0, "gaps": []}


def save_checkpoint(cp: dict, path: str):
    with open(path, "w") as f:
        json.dump(cp, f, indent=2)


def ingest_slot(slot: int) -> Optional[dict]:
    block = get_block(slot)
    if block is None:
        return {"slot": slot, "skipped": True, "reason": "no-block-or-skipped-slot"}

    vec = extract_features(block)
    if vec is None:
        return {"slot": slot, "skipped": True, "reason": "empty"}

    ts = block.get("blockTime") or 0
    block_hash = block.get("blockhash", "0" * 44)
    entity_id = f"{CHAIN_NAME}_slot_{slot}"
    bh_id = hashlib.sha3_256((CHAIN_NAME + block_hash).encode()).hexdigest()

    payload = {
        "entity_id": entity_id,
        "vector": vec.tolist(),
        "magnitude": compute_magnitude(block),
        "entropy": compute_entropy(block),
        "timestamp": float(ts),
        "bh_id": bh_id,
        "block_num": slot,
        "chain_id": CHAIN_ID,
        "block_hash": block_hash,
    }

    try:
        r = requests.post(f"{FAISS_URL}/index/add", json=payload, headers=_HDRS, timeout=10)
        r.raise_for_status()
        return {"slot": slot, "indexed": True, **r.json()}
    except Exception as e:
        logger.warning("Failed to index slot %d: %s", slot, e)
        return {"slot": slot, "indexed": False, "error": str(e)}


def run_backfill(start_slot: int, end_slot: int):
    checkpoint_file = "genesis_backfill_checkpoint_sol-mainnet.json"
    logger.info("=" * 65)
    logger.info(" TRION Akashic Genesis Backfill — Solana Mainnet")
    logger.info(" Start slot : %d", start_slot)
    logger.info(" End slot   : %d", end_slot)
    logger.info(" Workers    : %d", WORKERS)
    logger.info(" Batch size : %d", BATCH_SIZE)
    logger.info("=" * 65)

    cp = load_checkpoint(checkpoint_file)
    resume_from = cp["last_slot"] + 1
    if resume_from > start_slot:
        logger.info("Resuming from slot %d (checkpoint).", resume_from)
        start_slot = resume_from

    total_indexed = cp["indexed"]
    total_slots = max(end_slot - start_slot + 1, 1)

    for batch_start in range(start_slot, end_slot + 1, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE - 1, end_slot)
        batch = range(batch_start, batch_end + 1)

        with ThreadPoolExecutor(max_workers=WORKERS) as executor:
            futures = {executor.submit(ingest_slot, s): s for s in batch}
            for future in as_completed(futures):
                result = future.result()
                if result and result.get("indexed"):
                    total_indexed += 1

        cp["last_slot"] = batch_end
        cp["indexed"] = total_indexed
        save_checkpoint(cp, checkpoint_file)

        pct = (batch_end - start_slot + 1) / total_slots * 100
        logger.info("Progress: %.6f%%  |  Slots %d–%d  |  Indexed: %d",
                    pct, batch_start, batch_end, total_indexed)

        time.sleep(0.3)  # public RPC rate-limit courtesy

    logger.info("Backfill pass complete. Total indexed: %d", total_indexed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TRION Akashic Genesis Backfill — Solana")
    parser.add_argument("--start-slot", type=int, default=0)
    parser.add_argument("--end-slot", type=str, default="latest")
    args = parser.parse_args()

    start = args.start_slot
    end = get_latest_slot() if args.end_slot == "latest" else int(args.end_slot)
    if end == 0:
        logger.error("Could not fetch latest slot. Check SOLANA_RPC_URL.")
        sys.exit(1)

    run_backfill(start, end)
