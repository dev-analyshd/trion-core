#!/usr/bin/env python3
"""
TRION Akashic Index — Move-VM Genesis Backfill (generic).
Walks Aptos / Movement (Aptos-compatible REST API) ledger versions from 0 to tip
via GET /v1/transactions?start=N&limit=K, extracts a 128-dim behavioral vector,
and POSTs to FAISS.
"""
import os
import sys
import json
import math
import time
import hashlib
import logging
import argparse
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s [MOVE-BACKFILL] %(message)s")
logger = logging.getLogger(__name__)

DIMENSION  = 128
FAISS_URL  = os.environ.get("FAISS_SERVICE_URL", "http://127.0.0.1:8000")
BATCH_SIZE = int(os.environ.get("BACKFILL_BATCH", "100"))
WORKERS    = int(os.environ.get("BACKFILL_WORKERS", "4"))

MOVE_CHAINS = {
    # chain_ids are the canonical registry ids (config/chain_registry.json);
    # the legacy 30xxx ids were re-keyed (movement also fixed in the rust
    # trion-movement crate: 5002 → 20200).
    "aptos":    {"api": "https://fullnode.mainnet.aptoslabs.com/v1", "chain_id": 20000},
    "movement": {"api": "https://mainnet.movementnetwork.xyz/v1",   "chain_id": 20200},
}


def get_txs(api: str, start: int, limit: int):
    try:
        r = requests.get(f"{api}/transactions", params={"start": start, "limit": limit}, timeout=15)
        if r.status_code != 200:
            return []
        return r.json()
    except Exception as e:
        logger.warning("Fetch error at version %d: %s", start, e)
        return []


def get_latest_version(api: str) -> int:
    try:
        r = requests.get(api, timeout=10)
        return int(r.json().get("ledger_version", 0))
    except Exception as e:
        logger.warning("Could not fetch ledger version: %s", e)
        return 0


def extract_features(tx: dict):
    gas_used = float(tx.get("gas_used", 0) or 0)
    success = 1.0 if tx.get("success") else 0.0
    changes = len(tx.get("changes", []) or [])
    events = len(tx.get("events", []) or [])
    vm_status_len = len(tx.get("vm_status", "") or "")

    base = [gas_used / 1000.0, success, changes / 10.0, events / 10.0, vm_status_len / 20.0]
    vec = [0.0] * DIMENSION
    for i, val in enumerate(base):
        for k in range(20):
            idx = i * 20 + k
            if idx < DIMENSION:
                vec[idx] = float(val * math.cos(k * math.pi / 20.0))
    h = tx.get("hash", "0x00")
    hb = h.encode()
    for i in range(min(10, DIMENSION)):
        vec[-(i + 1)] = float(hb[i % len(hb)]) / 255.0
    return vec


def ingest_tx(tx: dict, chain_name: str, chain_id: int):
    version = int(tx.get("version", -1))
    if version < 0:
        return {"indexed": False}
    vec = extract_features(tx)
    entity_id = f"{chain_name}_tx_{version}"
    bh_id = hashlib.sha3_256((chain_name + str(version) + tx.get("hash", "")).encode()).hexdigest()
    payload = {
        "entity_id": entity_id,
        "vector": vec,
        "magnitude": min(1.0, float(tx.get("gas_used", 0) or 0) / 5000.0),
        "entropy": 0.5,
        "timestamp": time.time(),
        "bh_id": bh_id,
        "block_num": version,
        "chain_id": chain_id,
        "block_hash": tx.get("hash", ""),
    }
    try:
        r = requests.post(f"{FAISS_URL}/index/add", json=payload, timeout=10)
        r.raise_for_status()
        return {"version": version, "indexed": True}
    except Exception as e:
        return {"version": version, "indexed": False, "error": str(e)}


def load_checkpoint(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"last_version": -1, "indexed": 0}


def save_checkpoint(cp, path):
    with open(path, "w") as f:
        json.dump(cp, f, indent=2)


def run_backfill(chain_name: str, api: str, chain_id: int, start: int, end: int):
    checkpoint_file = f"genesis_backfill_checkpoint_{chain_name}.json"
    cp = load_checkpoint(checkpoint_file)
    resume = cp["last_version"] + 1
    if resume > start:
        start = resume
    logger.info("Chain=%s start=%d end=%d", chain_name, start, end)

    total_indexed = cp["indexed"]
    version = start
    while version <= end:
        txs = get_txs(api, version, BATCH_SIZE)
        if not txs:
            time.sleep(1)
            version += BATCH_SIZE
            continue
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = [ex.submit(ingest_tx, tx, chain_name, chain_id) for tx in txs]
            for fut in as_completed(futs):
                result = fut.result()
                if result.get("indexed"):
                    total_indexed += 1
        last_v = int(txs[-1].get("version", version))
        cp["last_version"] = last_v
        cp["indexed"] = total_indexed
        save_checkpoint(cp, checkpoint_file)
        logger.info("[%s] Progress: version up to %d | indexed=%d", chain_name, last_v, total_indexed)
        version = last_v + 1
        time.sleep(0.2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--chain-name", required=True, choices=list(MOVE_CHAINS.keys()))
    parser.add_argument("--start-version", type=int, default=0)
    parser.add_argument("--end-version", type=str, default="latest")
    args = parser.parse_args()

    cfg = MOVE_CHAINS[args.chain_name]
    api = cfg["api"]
    chain_id = cfg["chain_id"]

    end = get_latest_version(api) if args.end_version == "latest" else int(args.end_version)
    if end == 0:
        logger.error("Could not reach API for %s — skipping this cycle.", args.chain_name)
        sys.exit(0)

    run_backfill(args.chain_name, api, chain_id, args.start_version, end)
