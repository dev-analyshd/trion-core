#!/usr/bin/env python3
"""TRION Akashic Index — Tron Genesis Backfill. Walks blocks via TronGrid
public REST API (wallet/getblockbynum) from block 0 to tip, extracts a
128-dim vector, POSTs to FAISS."""
import os, sys, json, math, time, hashlib, logging, argparse, requests
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s [TRON-BACKFILL] %(message)s")
logger = logging.getLogger(__name__)

DIMENSION  = 128
FAISS_URL  = os.environ.get("FAISS_SERVICE_URL", "http://127.0.0.1:8000")
API        = os.environ.get("TRON_API_URL", "https://api.trongrid.io")
WORKERS    = int(os.environ.get("BACKFILL_WORKERS", "3"))
BATCH_SIZE = int(os.environ.get("BACKFILL_BATCH", "30"))
CHAIN_ID   = 26000  # canonical registry id (config/chain_registry.json)


def get_latest_number() -> int:
    try:
        r = requests.get(f"{API}/wallet/getnowblock", timeout=10).json()
        return int(r.get("block_header", {}).get("raw_data", {}).get("number", 0))
    except Exception as e:
        logger.warning("Could not fetch latest block: %s", e)
        return 0


def get_block(number: int):
    try:
        r = requests.get(f"{API}/wallet/getblockbynum", params={"num": number}, timeout=15)
        if r.status_code != 200:
            return None
        b = r.json()
        if not b or "blockID" not in b:
            return None
        return b
    except Exception as e:
        logger.warning("Block fetch error at %d: %s", number, e)
        return None


def extract_features(block: dict):
    txs = block.get("transactions", []) or []
    n = len(txs)
    if n == 0:
        return None
    contract_types = []
    for tx in txs:
        try:
            contract_types.append(tx["raw_data"]["contract"][0]["type"])
        except Exception:
            contract_types.append("Unknown")
    transfer = sum(1 for c in contract_types if "Transfer" in c)
    trigger = sum(1 for c in contract_types if c == "TriggerSmartContract")

    f1 = n / 50.0
    f2 = transfer / n
    f3 = trigger / n

    base = [f1, f2, f3]
    vec = [0.0] * DIMENSION
    for i, val in enumerate(base):
        for k in range(30):
            idx = i * 30 + k
            if idx < DIMENSION:
                vec[idx] = float(val * math.cos(k * math.pi / 30.0))
    h = block.get("blockID", "0")
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
    block_id = block.get("blockID", str(number))
    ts = block.get("block_header", {}).get("raw_data", {}).get("timestamp", 0)
    entity_id = f"tron-mainnet_block_{number}"
    bh_id = hashlib.sha3_256(("tron-mainnet" + block_id).encode()).hexdigest()
    payload = {
        "entity_id": entity_id, "vector": vec, "magnitude": 0.5, "entropy": 0.5,
        "timestamp": float(ts) / 1000.0 if ts else time.time(),
        "bh_id": bh_id, "block_num": number, "chain_id": CHAIN_ID, "block_hash": block_id,
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
    checkpoint_file = "genesis_backfill_checkpoint_tron-mainnet.json"
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
        time.sleep(0.2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-block", type=int, default=0)
    parser.add_argument("--end-block", type=str, default="latest")
    args = parser.parse_args()
    end = get_latest_number() if args.end_block == "latest" else int(args.end_block)
    if end == 0:
        logger.error("Could not reach TronGrid API — skipping this cycle.")
        sys.exit(0)
    run_backfill(args.start_block, end)
