#!/usr/bin/env python3
"""TRION Akashic Index — NEAR Genesis Backfill. Walks NEAR blocks by height via
JSON-RPC `block` method from height 1 to tip, extracts a 128-dim vector, POSTs to FAISS."""
import os, sys, json, math, time, hashlib, logging, argparse, requests
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s [NEAR-BACKFILL] %(message)s")
logger = logging.getLogger(__name__)

DIMENSION  = 128
FAISS_URL  = os.environ.get("FAISS_SERVICE_URL", "http://127.0.0.1:8000")
FAISS_KEY  = (os.environ.get("FAISS_API_KEY") or os.environ.get("FAISS_SERVICE_API_KEY")
              or os.environ.get("TRION_API_KEY") or "")
_HDRS      = {"X-API-Key": FAISS_KEY} if FAISS_KEY else {}   # SEC-01: FAISS service auth

RPC        = os.environ.get("NEAR_RPC_URL", "https://rpc.mainnet.near.org")
WORKERS    = int(os.environ.get("BACKFILL_WORKERS", "3"))
BATCH_SIZE = int(os.environ.get("BACKFILL_BATCH", "50"))
CHAIN_ID   = 23000  # canonical registry id (config/chain_registry.json)


def rpc_call(method, params):
    try:
        r = requests.post(RPC, json={"jsonrpc": "2.0", "id": "1", "method": method, "params": params}, timeout=10)
        return r.json().get("result")
    except Exception as e:
        logger.warning("RPC error (%s): %s", method, e)
        return None


def get_block(height: int):
    return rpc_call("block", {"block_id": height})


def get_latest_height() -> int:
    res = rpc_call("status", {})
    if res:
        return int(res.get("sync_info", {}).get("latest_block_height", 0))
    return 0


def extract_features(block: dict):
    chunks = block.get("chunks", []) or []
    if not chunks:
        return None
    tx_roots = [c.get("tx_root", "") for c in chunks]
    gas_used = sum(c.get("gas_used", 0) for c in chunks)
    gas_limit = sum(c.get("gas_limit", 1) for c in chunks) or 1
    n_chunks = len(chunks)

    f1 = n_chunks / 10.0
    f2 = gas_used / 1e14
    f3 = gas_used / gas_limit
    f4 = len(set(tx_roots)) / max(n_chunks, 1)

    base = [f1, f2, f3, f4]
    vec = [0.0] * DIMENSION
    for i, val in enumerate(base):
        for k in range(25):
            idx = i * 25 + k
            if idx < DIMENSION:
                vec[idx] = float(val * math.cos(k * math.pi / 25.0))
    h = block.get("header", {}).get("hash", "0")
    hb = h.encode()
    for i in range(min(10, DIMENSION)):
        vec[-(i + 1)] = float(hb[i % len(hb)]) / 255.0
    return vec


def ingest_block(height: int):
    block = get_block(height)
    if not block:
        return {"height": height, "indexed": False}
    vec = extract_features(block)
    if vec is None:
        return {"height": height, "skipped": True}
    header = block.get("header", {})
    block_hash = header.get("hash", str(height))
    entity_id = f"near-mainnet_block_{height}"
    bh_id = hashlib.sha3_256(("near-mainnet" + block_hash).encode()).hexdigest()
    payload = {
        "entity_id": entity_id, "vector": vec, "magnitude": 0.5, "entropy": 0.5,
        "timestamp": float(header.get("timestamp", 0)) / 1e9 if header.get("timestamp") else time.time(),
        "bh_id": bh_id, "block_num": height, "chain_id": CHAIN_ID, "block_hash": block_hash,
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


def run_backfill(start: int, end: int):
    checkpoint_file = "genesis_backfill_checkpoint_near-mainnet.json"
    cp = load_checkpoint(checkpoint_file)
    resume = cp["last_height"] + 1
    if resume > start:
        start = resume
    total_indexed = cp["indexed"]
    for batch_start in range(start, end + 1, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE - 1, end)
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = [ex.submit(ingest_block, h) for h in range(batch_start, batch_end + 1)]
            for fut in as_completed(futs):
                r = fut.result()
                if r.get("indexed"):
                    total_indexed += 1
        cp["last_height"] = batch_end
        cp["indexed"] = total_indexed
        save_checkpoint(cp, checkpoint_file)
        logger.info("Progress: height %d-%d | indexed=%d", batch_start, batch_end, total_indexed)
        time.sleep(0.2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-height", type=int, default=1)
    parser.add_argument("--end-height", type=str, default="latest")
    args = parser.parse_args()
    end = get_latest_height() if args.end_height == "latest" else int(args.end_height)
    if end == 0:
        logger.error("Could not reach NEAR RPC — skipping this cycle.")
        sys.exit(0)
    run_backfill(args.start_height, end)
