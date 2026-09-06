#!/usr/bin/env python3
"""TRION Akashic Index — Algorand Genesis Backfill. Walks blocks via
AlgoNode's free public API from round 1 to tip, extracts a 128-dim vector,
POSTs to FAISS."""
import os, sys, json, math, time, hashlib, logging, argparse, requests
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s [ALGO-BACKFILL] %(message)s")
logger = logging.getLogger(__name__)

DIMENSION  = 128
FAISS_URL  = os.environ.get("FAISS_SERVICE_URL", "http://127.0.0.1:8000")
FAISS_KEY  = (os.environ.get("FAISS_API_KEY") or os.environ.get("FAISS_SERVICE_API_KEY")
              or os.environ.get("TRION_API_KEY") or "")
_HDRS      = {"X-API-Key": FAISS_KEY} if FAISS_KEY else {}   # SEC-01: FAISS service auth

API        = os.environ.get("ALGO_API_URL", "https://mainnet-api.algonode.cloud")
WORKERS    = int(os.environ.get("BACKFILL_WORKERS", "4"))
BATCH_SIZE = int(os.environ.get("BACKFILL_BATCH", "40"))
CHAIN_ID   = 8200   # canonical registry id (config/chain_registry.json)


def get_latest_round() -> int:
    try:
        r = requests.get(f"{API}/v2/status", timeout=10).json()
        return int(r.get("last-round", 0))
    except Exception as e:
        logger.warning("Could not fetch status: %s", e)
        return 0


def get_block(round_num: int):
    try:
        r = requests.get(f"{API}/v2/blocks/{round_num}", timeout=15)
        if r.status_code != 200:
            return None
        return r.json().get("block")
    except Exception as e:
        logger.warning("Block fetch error at %d: %s", round_num, e)
        return None


def extract_features(block: dict):
    txns = block.get("txns", []) or []
    n = len(txns)
    if n == 0:
        return None
    fees = float(block.get("fees", 0) or 0)

    f1 = n / 100.0
    f2 = fees / 1e9

    base = [f1, f2]
    vec = [0.0] * DIMENSION
    for i, val in enumerate(base):
        for k in range(40):
            idx = i * 40 + k
            if idx < DIMENSION:
                vec[idx] = float(val * math.cos(k * math.pi / 40.0))
    gh = str(block.get("gh", "0"))
    hb = gh.encode()
    for i in range(min(10, DIMENSION)):
        vec[-(i + 1)] = float(hb[i % len(hb)]) / 255.0
    return vec


def ingest_block(round_num: int):
    block = get_block(round_num)
    if not block:
        return {"round": round_num, "indexed": False}
    vec = extract_features(block)
    if vec is None:
        return {"round": round_num, "skipped": True}
    gh = str(block.get("gh", round_num))
    ts = block.get("ts", 0)
    entity_id = f"algorand-mainnet_round_{round_num}"
    bh_id = hashlib.sha3_256(("algorand-mainnet" + str(round_num) + gh).encode()).hexdigest()
    payload = {
        "entity_id": entity_id, "vector": vec, "magnitude": 0.5, "entropy": 0.5,
        "timestamp": float(ts) if ts else time.time(),
        "bh_id": bh_id, "block_num": round_num, "chain_id": CHAIN_ID, "block_hash": gh,
    }
    try:
        r = requests.post(f"{FAISS_URL}/index/add", json=payload, headers=_HDRS, timeout=10)
        r.raise_for_status()
        return {"round": round_num, "indexed": True}
    except Exception as e:
        return {"round": round_num, "indexed": False, "error": str(e)}


def load_checkpoint(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"last_round": 0, "indexed": 0}


def save_checkpoint(cp, path):
    with open(path, "w") as f:
        json.dump(cp, f, indent=2)


def run_backfill(start: int, end: int):
    checkpoint_file = "genesis_backfill_checkpoint_algorand-mainnet.json"
    cp = load_checkpoint(checkpoint_file)
    resume = cp["last_round"] + 1
    if resume > start:
        start = resume
    total_indexed = cp["indexed"]
    for batch_start in range(start, end + 1, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE - 1, end)
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = [ex.submit(ingest_block, r) for r in range(batch_start, batch_end + 1)]
            for fut in as_completed(futs):
                r = fut.result()
                if r.get("indexed"):
                    total_indexed += 1
        cp["last_round"] = batch_end
        cp["indexed"] = total_indexed
        save_checkpoint(cp, checkpoint_file)
        logger.info("Progress: round %d-%d | indexed=%d", batch_start, batch_end, total_indexed)
        time.sleep(0.1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-round", type=int, default=1)
    parser.add_argument("--end-round", type=str, default="latest")
    args = parser.parse_args()
    end = get_latest_round() if args.end_round == "latest" else int(args.end_round)
    if end == 0:
        logger.error("Could not reach AlgoNode API — skipping this cycle.")
        sys.exit(0)
    run_backfill(args.start_round, end)
