#!/usr/bin/env python3
"""TRION Akashic Index — MultiversX Genesis Backfill. Walks blocks via
MultiversX's public REST API using offset pagination (the API aggregates
blocks from all shards + metachain into one global feed) from index 0 to
tip, extracts a 128-dim vector, POSTs to FAISS."""
import os, sys, json, math, time, hashlib, logging, argparse, requests
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s [MULTIVERSX-BACKFILL] %(message)s")
logger = logging.getLogger(__name__)

DIMENSION  = 128
FAISS_URL  = os.environ.get("FAISS_SERVICE_URL", "http://127.0.0.1:8000")
API        = os.environ.get("MULTIVERSX_API_URL", "https://api.multiversx.com")
WORKERS    = int(os.environ.get("BACKFILL_WORKERS", "3"))
BATCH_SIZE = int(os.environ.get("BACKFILL_BATCH", "50"))
CHAIN_ID   = 32000  # canonical registry id (config/chain_registry.json)


def get_latest_count() -> int:
    try:
        r = requests.get(f"{API}/blocks/count", timeout=10)
        return int(r.text)
    except Exception as e:
        logger.warning("Could not fetch block count: %s", e)
        return 0


def get_blocks(offset: int, size: int):
    try:
        r = requests.get(f"{API}/blocks", params={"from": offset, "size": size}, timeout=15)
        if r.status_code != 200:
            return []
        return r.json()
    except Exception as e:
        logger.warning("Blocks fetch error at offset %d: %s", offset, e)
        return []


def extract_features(block: dict):
    n = int(block.get("txCount", 0) or 0)
    if n == 0:
        return None
    size = float(block.get("size", 0) or 0)
    shard = block.get("shard", 0)

    f1 = n / 20.0
    f2 = size / 100000.0
    f3 = (shard if isinstance(shard, int) and shard < 100 else 99) / 10.0

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


def ingest_block(offset: int, block: dict):
    vec = extract_features(block)
    if vec is None:
        return {"offset": offset, "skipped": True}
    block_hash = block.get("hash", str(offset))
    ts = block.get("timestamp", 0)
    entity_id = f"multiversx-mainnet_block_{block.get('nonce', offset)}_{block.get('shard', 0)}"
    bh_id = hashlib.sha3_256(("multiversx-mainnet" + block_hash).encode()).hexdigest()
    payload = {
        "entity_id": entity_id, "vector": vec, "magnitude": 0.5, "entropy": 0.5,
        "timestamp": float(ts) if ts else time.time(),
        "bh_id": bh_id, "block_num": block.get("nonce", offset), "chain_id": CHAIN_ID, "block_hash": block_hash,
    }
    try:
        r = requests.post(f"{FAISS_URL}/index/add", json=payload, timeout=10)
        r.raise_for_status()
        return {"offset": offset, "indexed": True}
    except Exception as e:
        return {"offset": offset, "indexed": False, "error": str(e)}


def load_checkpoint(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"last_offset": -1, "indexed": 0}


def save_checkpoint(cp, path):
    with open(path, "w") as f:
        json.dump(cp, f, indent=2)


def run_backfill(start: int, end: int):
    checkpoint_file = "genesis_backfill_checkpoint_multiversx-mainnet.json"
    cp = load_checkpoint(checkpoint_file)
    resume = cp["last_offset"] + 1
    if resume > start:
        start = resume
    total_indexed = cp["indexed"]
    offset = start
    while offset <= end:
        blocks = get_blocks(offset, BATCH_SIZE)
        if not blocks:
            offset += BATCH_SIZE
            time.sleep(1)
            continue
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = [ex.submit(ingest_block, offset + i, b) for i, b in enumerate(blocks)]
            for fut in as_completed(futs):
                r = fut.result()
                if r.get("indexed"):
                    total_indexed += 1
        offset += len(blocks)
        cp["last_offset"] = offset - 1
        cp["indexed"] = total_indexed
        save_checkpoint(cp, checkpoint_file)
        logger.info("Progress: offset up to %d | indexed=%d", offset, total_indexed)
        time.sleep(0.2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-offset", type=int, default=0)
    parser.add_argument("--end-offset", type=str, default="latest")
    args = parser.parse_args()
    end = get_latest_count() if args.end_offset == "latest" else int(args.end_offset)
    if end == 0:
        logger.error("Could not reach MultiversX API — skipping this cycle.")
        sys.exit(0)
    run_backfill(args.start_offset, end)
