#!/usr/bin/env python3
"""TRION Akashic Index — TON Genesis Backfill. Walks masterchain blocks via the
public toncenter.com v2 API (lookupBlock + getBlockHeader) from seqno 1 to tip,
extracts a 128-dim vector, POSTs to FAISS."""
import os, sys, json, math, time, hashlib, logging, argparse, requests
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s [TON-BACKFILL] %(message)s")
logger = logging.getLogger(__name__)

DIMENSION  = 128
FAISS_URL  = os.environ.get("FAISS_SERVICE_URL", "http://127.0.0.1:8000")
FAISS_KEY  = (os.environ.get("FAISS_API_KEY") or os.environ.get("FAISS_SERVICE_API_KEY")
              or os.environ.get("TRION_API_KEY") or "")
_HDRS      = {"X-API-Key": FAISS_KEY} if FAISS_KEY else {}   # SEC-01: FAISS service auth

API        = os.environ.get("TON_API_URL", "https://toncenter.com/api/v2")
WORKERS    = int(os.environ.get("BACKFILL_WORKERS", "2"))
BATCH_SIZE = int(os.environ.get("BACKFILL_BATCH", "20"))
CHAIN_ID   = 22000  # canonical registry id (config/chain_registry.json)
WORKCHAIN  = -1
SHARD      = "-9223372036854775808"


def get_latest_seqno() -> int:
    try:
        r = requests.get(f"{API}/getMasterchainInfo", timeout=10)
        return int(r.json()["result"]["last"]["seqno"])
    except Exception as e:
        logger.warning("Could not fetch masterchain info: %s", e)
        return 0


def get_block_header(seqno: int):
    try:
        r = requests.get(f"{API}/getBlockHeader", params={
            "workchain": WORKCHAIN, "shard": SHARD, "seqno": seqno
        }, timeout=10)
        data = r.json()
        if data.get("ok"):
            return data.get("result")
        return None
    except Exception as e:
        logger.warning("Header error at seqno %d: %s", seqno, e)
        return None


def extract_features(header: dict):
    tx_count = header.get("tx_count", 0) or 0
    if tx_count == 0:
        return None
    gen_utime = header.get("gen_utime", 0) or 0
    start_lt = int(header.get("start_lt", 0) or 0)
    end_lt = int(header.get("end_lt", 0) or 0)
    lt_span = max(end_lt - start_lt, 1)

    f1 = tx_count / 50.0
    f2 = lt_span / 1e6
    f3 = min(gen_utime % 1000 / 1000.0, 1.0)

    base = [f1, f2, f3]
    vec = [0.0] * DIMENSION
    for i, val in enumerate(base):
        for k in range(30):
            idx = i * 30 + k
            if idx < DIMENSION:
                vec[idx] = float(val * math.cos(k * math.pi / 30.0))
    return vec


def ingest_seqno(seqno: int):
    header = get_block_header(seqno)
    if not header:
        return {"seqno": seqno, "indexed": False}
    vec = extract_features(header)
    if vec is None:
        return {"seqno": seqno, "skipped": True}
    root_hash = header.get("root_hash", str(seqno))
    hb = root_hash.encode()
    for i in range(min(10, DIMENSION)):
        vec[-(i + 1)] = float(hb[i % len(hb)]) / 255.0

    entity_id = f"ton-mainnet_block_{seqno}"
    bh_id = hashlib.sha3_256(("ton-mainnet" + root_hash).encode()).hexdigest()
    payload = {
        "entity_id": entity_id, "vector": vec, "magnitude": 0.5, "entropy": 0.5,
        "timestamp": float(header.get("gen_utime", time.time())),
        "bh_id": bh_id, "block_num": seqno, "chain_id": CHAIN_ID, "block_hash": root_hash,
    }
    try:
        r = requests.post(f"{FAISS_URL}/index/add", json=payload, headers=_HDRS, timeout=10)
        r.raise_for_status()
        return {"seqno": seqno, "indexed": True}
    except Exception as e:
        return {"seqno": seqno, "indexed": False, "error": str(e)}


def load_checkpoint(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"last_seqno": 0, "indexed": 0}


def save_checkpoint(cp, path):
    with open(path, "w") as f:
        json.dump(cp, f, indent=2)


def run_backfill(start: int, end: int):
    checkpoint_file = "genesis_backfill_checkpoint_ton-mainnet.json"
    cp = load_checkpoint(checkpoint_file)
    resume = cp["last_seqno"] + 1
    if resume > start:
        start = resume
    total_indexed = cp["indexed"]
    for batch_start in range(start, end + 1, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE - 1, end)
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = [ex.submit(ingest_seqno, s) for s in range(batch_start, batch_end + 1)]
            for fut in as_completed(futs):
                r = fut.result()
                if r.get("indexed"):
                    total_indexed += 1
        cp["last_seqno"] = batch_end
        cp["indexed"] = total_indexed
        save_checkpoint(cp, checkpoint_file)
        logger.info("Progress: seqno %d-%d | indexed=%d", batch_start, batch_end, total_indexed)
        time.sleep(0.3)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-seqno", type=int, default=1)
    parser.add_argument("--end-seqno", type=str, default="latest")
    args = parser.parse_args()
    end = get_latest_seqno() if args.end_seqno == "latest" else int(args.end_seqno)
    if end == 0:
        logger.error("Could not reach TON API — skipping this cycle.")
        sys.exit(0)
    run_backfill(args.start_seqno, end)
