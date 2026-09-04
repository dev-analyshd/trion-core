#!/usr/bin/env python3
"""TRION Akashic Index — Hedera Genesis Backfill. Walks blocks via Hedera's
public Mirror Node REST API from block 0 to tip, extracts a 128-dim vector,
POSTs to FAISS."""
import os, sys, json, math, time, hashlib, logging, argparse, requests
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s [HEDERA-BACKFILL] %(message)s")
logger = logging.getLogger(__name__)

DIMENSION  = 128
FAISS_URL  = os.environ.get("FAISS_SERVICE_URL", "http://127.0.0.1:8000")
API        = os.environ.get("HEDERA_API_URL", "https://mainnet-public.mirrornode.hedera.com")
WORKERS    = int(os.environ.get("BACKFILL_WORKERS", "4"))
BATCH_SIZE = int(os.environ.get("BACKFILL_BATCH", "40"))
CHAIN_ID   = 28000  # canonical registry id (config/chain_registry.json)


def get_latest_number() -> int:
    try:
        r = requests.get(f"{API}/api/v1/blocks", params={"limit": 1, "order": "desc"}, timeout=10).json()
        blocks = r.get("blocks", [])
        return int(blocks[0]["number"]) if blocks else 0
    except Exception as e:
        logger.warning("Could not fetch latest block: %s", e)
        return 0


def get_block(number: int):
    try:
        r = requests.get(f"{API}/api/v1/blocks/{number}", timeout=15)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception as e:
        logger.warning("Block fetch error at %d: %s", number, e)
        return None


def extract_features(block: dict):
    n = int(block.get("count", 0) or 0)
    if n == 0:
        return None
    gas_used = float(block.get("gas_used", 0) or 0)
    size = float(block.get("size", 0) or 0)

    f1 = n / 20.0
    f2 = gas_used / 1e7
    f3 = size / 100000.0

    base = [f1, f2, f3]
    vec = [0.0] * DIMENSION
    for i, val in enumerate(base):
        for k in range(30):
            idx = i * 30 + k
            if idx < DIMENSION:
                vec[idx] = float(val * math.cos(k * math.pi / 30.0))
    h = block.get("hash", "0")
    hb = h.encode()
    for i in range(min(10, DIMENSION)):
        vec[-(i + 1)] = float(hb[i % len(hb)]) / 255.0
    return vec


def ingest_block(number: int):
    block = get_block(number)
    if not block:
        return {"number": number, "indexed": False}
    vec = extract_features(block)
    if vec is None:
        return {"number": number, "skipped": True}
    block_hash = block.get("hash", str(number))
    ts_from = block.get("timestamp", {}).get("from") if isinstance(block.get("timestamp"), dict) else None
    ts = float(ts_from) if ts_from else time.time()
    entity_id = f"hedera-mainnet_block_{number}"
    bh_id = hashlib.sha3_256(("hedera-mainnet" + str(number) + block_hash).encode()).hexdigest()
    payload = {
        "entity_id": entity_id, "vector": vec, "magnitude": 0.5, "entropy": 0.5,
        "timestamp": ts, "bh_id": bh_id, "block_num": number, "chain_id": CHAIN_ID, "block_hash": block_hash,
    }
    try:
        r = requests.post(f"{FAISS_URL}/index/add", json=payload, timeout=10)
        r.raise_for_status()
        return {"number": number, "indexed": True}
    except Exception as e:
        return {"number": number, "indexed": False, "error": str(e)}


def load_checkpoint(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"last_number": -1, "indexed": 0}


def save_checkpoint(cp, path):
    with open(path, "w") as f:
        json.dump(cp, f, indent=2)


def run_backfill(start: int, end: int):
    checkpoint_file = "genesis_backfill_checkpoint_hedera-mainnet.json"
    cp = load_checkpoint(checkpoint_file)
    resume = cp["last_number"] + 1
    if resume > start:
        start = resume
    total_indexed = cp["indexed"]
    for batch_start in range(start, end + 1, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE - 1, end)
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = [ex.submit(ingest_block, n) for n in range(batch_start, batch_end + 1)]
            for fut in as_completed(futs):
                r = fut.result()
                if r.get("indexed"):
                    total_indexed += 1
        cp["last_number"] = batch_end
        cp["indexed"] = total_indexed
        save_checkpoint(cp, checkpoint_file)
        logger.info("Progress: block %d-%d | indexed=%d", batch_start, batch_end, total_indexed)
        time.sleep(0.1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-block", type=int, default=0)
    parser.add_argument("--end-block", type=str, default="latest")
    args = parser.parse_args()
    end = get_latest_number() if args.end_block == "latest" else int(args.end_block)
    if end == 0:
        logger.error("Could not reach Hedera Mirror Node API — skipping this cycle.")
        sys.exit(0)
    run_backfill(args.start_block, end)
