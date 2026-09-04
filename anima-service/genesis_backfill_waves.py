#!/usr/bin/env python3
"""TRION Akashic Index — Waves Genesis Backfill. Walks blocks via Waves'
public node REST API from height 1 to tip, extracts a 128-dim vector,
POSTs to FAISS."""
import os, sys, json, math, time, hashlib, logging, argparse, requests
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s [WAVES-BACKFILL] %(message)s")
logger = logging.getLogger(__name__)

DIMENSION  = 128
FAISS_URL  = os.environ.get("FAISS_SERVICE_URL", "http://127.0.0.1:8000")
API        = os.environ.get("WAVES_API_URL", "https://nodes.wavesnodes.com")
WORKERS    = int(os.environ.get("BACKFILL_WORKERS", "4"))
BATCH_SIZE = int(os.environ.get("BACKFILL_BATCH", "40"))
CHAIN_ID   = 30000  # canonical registry id (config/chain_registry.json)


def get_latest_height() -> int:
    try:
        r = requests.get(f"{API}/blocks/height", timeout=10).json()
        return int(r.get("height", 0))
    except Exception as e:
        logger.warning("Could not fetch height: %s", e)
        return 0


def get_block(height: int):
    try:
        r = requests.get(f"{API}/blocks/at/{height}", timeout=15)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception as e:
        logger.warning("Block fetch error at %d: %s", height, e)
        return None


def extract_features(block: dict):
    txs = block.get("transactions", []) or []
    n = block.get("transactionCount", len(txs))
    if not n:
        return None
    fee = float(block.get("totalFee", block.get("fee", 0)) or 0)

    f1 = n / 20.0
    f2 = fee / 1e8

    base = [f1, f2]
    vec = [0.0] * DIMENSION
    for i, val in enumerate(base):
        for k in range(40):
            idx = i * 40 + k
            if idx < DIMENSION:
                vec[idx] = float(val * math.cos(k * math.pi / 40.0))
    h = block.get("id", "0")
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
    block_id = block.get("id", str(height))
    ts = block.get("timestamp", 0)
    entity_id = f"waves-mainnet_block_{height}"
    bh_id = hashlib.sha3_256(("waves-mainnet" + str(height) + block_id).encode()).hexdigest()
    payload = {
        "entity_id": entity_id, "vector": vec, "magnitude": 0.5, "entropy": 0.5,
        "timestamp": float(ts) / 1000.0 if ts else time.time(),
        "bh_id": bh_id, "block_num": height, "chain_id": CHAIN_ID, "block_hash": block_id,
    }
    try:
        r = requests.post(f"{FAISS_URL}/index/add", json=payload, timeout=10)
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
    checkpoint_file = "genesis_backfill_checkpoint_waves-mainnet.json"
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
        time.sleep(0.1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-height", type=int, default=1)
    parser.add_argument("--end-height", type=str, default="latest")
    args = parser.parse_args()
    end = get_latest_height() if args.end_height == "latest" else int(args.end_height)
    if end == 0:
        logger.error("Could not reach Waves node API — skipping this cycle.")
        sys.exit(0)
    run_backfill(args.start_height, end)
