#!/usr/bin/env python3
"""
TRION Akashic Index — Cosmos-SDK Genesis Backfill (generic).
Walks any Tendermint/CometBFT RPC chain from height 1 to tip via /block?height=N,
extracts a 128-dim behavioral vector from tx count/size, and POSTs to FAISS.
Works for every Cosmos-SDK chain in COSMOS_CHAINS below — one script, many chains.
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [COSMOS-BACKFILL] %(message)s")
logger = logging.getLogger(__name__)

DIMENSION  = 128
FAISS_URL  = os.environ.get("FAISS_SERVICE_URL", "http://127.0.0.1:8000")
FAISS_KEY  = (os.environ.get("FAISS_API_KEY") or os.environ.get("FAISS_SERVICE_API_KEY")
              or os.environ.get("TRION_API_KEY") or "")
_HDRS      = {"X-API-Key": FAISS_KEY} if FAISS_KEY else {}   # SEC-01: FAISS service auth

WORKERS    = int(os.environ.get("BACKFILL_WORKERS", "3"))
BATCH_SIZE = int(os.environ.get("BACKFILL_BATCH", "50"))

COSMOS_CHAINS = {
    # chain_ids are the canonical registry ids (config/chain_registry.json);
    # the legacy 200xx streamer ids were re-keyed (was 20001-20010).
    "cosmos-hub": {"rpc": "https://cosmos-rpc.publicnode.com",   "chain_id": 10000},
    "kava":       {"rpc": "https://kava-rpc.publicnode.com",     "chain_id": 10014},
    "injective":  {"rpc": "https://injective-rpc.publicnode.com","chain_id": 10004},
    "sei":        {"rpc": "https://sei-rpc.polkachu.com",        "chain_id": 10005},
    "dydx":       {"rpc": "https://dydx-rpc.publicnode.com",     "chain_id": 10006},
    "initia":     {"rpc": "https://rpc.initia.xyz",               "chain_id": 10015},
    "osmosis":    {"rpc": "https://osmosis-rpc.publicnode.com",  "chain_id": 10001},
    "neutron":    {"rpc": "https://neutron-rpc.publicnode.com",  "chain_id": 10018},
    "celestia":   {"rpc": "https://celestia-rpc.publicnode.com", "chain_id": 10003},
    "terra":      {"rpc": "https://terra-rpc.publicnode.com",    "chain_id": 10009},
    # provenance is NOT in the canonical 129-chain registry — walked under
    # its legacy local id (no canonical id to re-key to; no collision either).
    "provenance": {"rpc": "https://rpc.provenance.io:443",       "chain_id": 20011},
}


def get_block(rpc: str, height: int):
    try:
        r = requests.get(f"{rpc}/block", params={"height": height}, timeout=10)
        if r.status_code != 200:
            return None
        return r.json().get("result")
    except Exception as e:
        logger.warning("RPC error at height %d: %s", height, e)
        return None


def get_latest_height(rpc: str) -> int:
    try:
        r = requests.get(f"{rpc}/status", timeout=10)
        return int(r.json()["result"]["sync_info"]["latest_block_height"])
    except Exception as e:
        logger.warning("Could not fetch latest height: %s", e)
        return 0


def extract_features(block_result: dict):
    block = block_result.get("block", {})
    data = block.get("data", {})
    txs = data.get("txs", []) or []
    if not txs:
        return None
    tx_count = len(txs)
    tx_sizes = [len(t) for t in txs]  # base64 length proxy for byte size
    total_size = sum(tx_sizes) or 1
    top_size = max(tx_sizes)
    avg_size = total_size / tx_count

    f1 = tx_count
    f2 = total_size / 1000.0
    f3 = avg_size / 1000.0
    f4 = top_size / total_size
    f5 = min(tx_count / 100.0, 1.0)

    base = [f1 / 100.0, f2, f3, f4, f5]
    vec = [0.0] * DIMENSION
    for i, val in enumerate(base):
        for k in range(20):
            idx = i * 20 + k
            if idx < DIMENSION:
                vec[idx] = float(val * math.cos(k * math.pi / 20.0))

    header_hash = block.get("header", {}).get("data_hash", "") or ""
    hb = header_hash.encode() if header_hash else b"\x00"
    for i in range(min(10, DIMENSION)):
        vec[-(i + 1)] = float(hb[i % len(hb)]) / 255.0 if hb else 0.0
    return vec


def ingest_height(rpc: str, height: int, chain_name: str, chain_id: int):
    block_result = get_block(rpc, height)
    if not block_result:
        return {"height": height, "indexed": False, "error": "no_block"}
    vec = extract_features(block_result)
    if vec is None:
        return {"height": height, "skipped": True}

    header = block_result.get("block", {}).get("header", {})
    ts_str = header.get("time", "")
    block_hash = header.get("data_hash", "") or str(height)

    entity_id = f"{chain_name}_block_{height}"
    bh_id = hashlib.sha3_256((chain_name + str(height) + block_hash).encode()).hexdigest()

    payload = {
        "entity_id": entity_id,
        "vector": vec,
        "magnitude": min(1.0, len(block_result.get("block", {}).get("data", {}).get("txs", [])) / 100.0),
        "entropy": 0.5,
        "timestamp": time.time(),
        "bh_id": bh_id,
        "block_num": height,
        "chain_id": chain_id,
        "block_hash": block_hash,
    }
    try:
        r = requests.post(f"{FAISS_URL}/index/add", json=payload, headers=_HDRS, timeout=10)
        r.raise_for_status()
        return {"height": height, "indexed": True}
    except Exception as e:
        return {"height": height, "indexed": False, "error": str(e)}


def load_checkpoint(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"last_height": 0, "indexed": 0}


def save_checkpoint(cp, path):
    with open(path, "w") as f:
        json.dump(cp, f, indent=2)


def run_backfill(chain_name: str, rpc: str, chain_id: int, start: int, end: int):
    checkpoint_file = f"genesis_backfill_checkpoint_{chain_name}.json"
    cp = load_checkpoint(checkpoint_file)
    resume = cp["last_height"] + 1
    if resume > start:
        start = resume
    logger.info("Chain=%s start=%d end=%d", chain_name, start, end)

    total_indexed = cp["indexed"]
    for batch_start in range(start, end + 1, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE - 1, end)
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = {ex.submit(ingest_height, rpc, h, chain_name, chain_id): h for h in range(batch_start, batch_end + 1)}
            for fut in as_completed(futs):
                result = fut.result()
                if result.get("indexed"):
                    total_indexed += 1
        cp["last_height"] = batch_end
        cp["indexed"] = total_indexed
        save_checkpoint(cp, checkpoint_file)
        logger.info("[%s] Progress: height %d-%d | indexed=%d", chain_name, batch_start, batch_end, total_indexed)
        time.sleep(0.2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--chain-name", required=True, choices=list(COSMOS_CHAINS.keys()))
    parser.add_argument("--start-height", type=int, default=1)
    parser.add_argument("--end-height", type=str, default="latest")
    args = parser.parse_args()

    cfg = COSMOS_CHAINS[args.chain_name]
    rpc = cfg["rpc"]
    chain_id = cfg["chain_id"]

    end = get_latest_height(rpc) if args.end_height == "latest" else int(args.end_height)
    if end == 0:
        logger.error("Could not reach RPC for %s — skipping this cycle.", args.chain_name)
        sys.exit(0)

    run_backfill(args.chain_name, rpc, chain_id, args.start_height, end)
