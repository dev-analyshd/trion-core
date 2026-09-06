#!/usr/bin/env python3
"""TRION Akashic Index — Cardano Genesis Backfill. Walks blocks via Koios'
free public PostgREST API (block_height=eq.N direct lookups) from height 1
to tip, extracts a 128-dim vector, POSTs to FAISS."""
import os, sys, json, math, time, hashlib, logging, argparse, requests
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s [CARDANO-BACKFILL] %(message)s")
logger = logging.getLogger(__name__)

DIMENSION  = 128
FAISS_URL  = os.environ.get("FAISS_SERVICE_URL", "http://127.0.0.1:8000")
FAISS_KEY  = (os.environ.get("FAISS_API_KEY") or os.environ.get("FAISS_SERVICE_API_KEY")
              or os.environ.get("TRION_API_KEY") or "")
_HDRS      = {"X-API-Key": FAISS_KEY} if FAISS_KEY else {}   # SEC-01: FAISS service auth

API        = os.environ.get("KOIOS_API_URL", "https://api.koios.rest/api/v1")
WORKERS    = int(os.environ.get("BACKFILL_WORKERS", "2"))
BATCH_SIZE = int(os.environ.get("BACKFILL_BATCH", "20"))
CHAIN_ID   = 9400   # canonical registry id (config/chain_registry.json)


def get_latest_height() -> int:
    try:
        r = requests.get(f"{API}/tip", timeout=10).json()
        return int(r[0]["block_no"]) if r else 0
    except Exception as e:
        logger.warning("Could not fetch tip: %s", e)
        return 0


def get_block(height: int):
    try:
        r = requests.get(f"{API}/blocks", params={"block_height": f"eq.{height}"}, timeout=15)
        if r.status_code != 200:
            return None
        blocks = r.json()
        return blocks[0] if blocks else None
    except Exception as e:
        logger.warning("Block fetch error at %d: %s", height, e)
        return None


def extract_features(block: dict):
    n = int(block.get("tx_count", 0) or 0)
    if n == 0:
        return None
    size = float(block.get("block_size", 0) or 0)

    f1 = n / 20.0
    f2 = size / 90000.0

    base = [f1, f2]
    vec = [0.0] * DIMENSION
    for i, val in enumerate(base):
        for k in range(40):
            idx = i * 40 + k
            if idx < DIMENSION:
                vec[idx] = float(val * math.cos(k * math.pi / 40.0))
    h = block.get("hash", "0")
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
    h = block.get("hash", str(height))
    ts = block.get("block_time", 0)
    entity_id = f"cardano-mainnet_block_{height}"
    bh_id = hashlib.sha3_256(("cardano-mainnet" + str(height) + h).encode()).hexdigest()
    payload = {
        "entity_id": entity_id, "vector": vec, "magnitude": 0.5, "entropy": 0.5,
        "timestamp": float(ts) if ts else time.time(),
        "bh_id": bh_id, "block_num": height, "chain_id": CHAIN_ID, "block_hash": h,
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
    checkpoint_file = "genesis_backfill_checkpoint_cardano-mainnet.json"
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
        time.sleep(0.3)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-height", type=int, default=1)
    parser.add_argument("--end-height", type=str, default="latest")
    args = parser.parse_args()
    end = get_latest_height() if args.end_height == "latest" else int(args.end_height)
    if end == 0:
        logger.error("Could not reach Koios API — skipping this cycle.")
        sys.exit(0)
    run_backfill(args.start_height, end)
