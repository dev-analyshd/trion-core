#!/usr/bin/env python3
"""TRION Akashic Index — XRPL Genesis Backfill. Walks ledgers via public
rippled JSON-RPC (method=ledger) from ledger 32570 (the earliest ledger
retained network-wide after the 2013 XRPL restart) to tip, extracts a
128-dim vector, POSTs to FAISS."""
import os, sys, json, math, time, hashlib, logging, argparse, requests
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s [XRPL-BACKFILL] %(message)s")
logger = logging.getLogger(__name__)

DIMENSION  = 128
FAISS_URL  = os.environ.get("FAISS_SERVICE_URL", "http://127.0.0.1:8000")
RPC        = os.environ.get("XRPL_RPC_URL", "https://xrplcluster.com")
WORKERS    = int(os.environ.get("BACKFILL_WORKERS", "3"))
BATCH_SIZE = int(os.environ.get("BACKFILL_BATCH", "30"))
CHAIN_ID   = 31000  # canonical registry id (config/chain_registry.json)
GENESIS_LEDGER = 32570  # earliest ledger available network-wide (pre-history lost in 2013 restart)


def get_latest_index() -> int:
    try:
        r = requests.post(RPC, json={"method": "ledger", "params": [{"ledger_index": "validated"}]}, timeout=10)
        d = r.json()
        return int(d["result"]["ledger"]["ledger_index"])
    except Exception as e:
        logger.warning("Could not fetch validated ledger: %s", e)
        return 0


def get_ledger(index: int):
    try:
        r = requests.post(RPC, json={"method": "ledger", "params": [{"ledger_index": index, "transactions": True, "expand": False}]}, timeout=15)
        d = r.json()
        if "error" in d.get("result", {}):
            return None
        return d["result"].get("ledger")
    except Exception as e:
        logger.warning("Ledger fetch error at %d: %s", index, e)
        return None


def extract_features(ledger: dict):
    txs = ledger.get("transactions", []) or []
    n = len(txs)
    if n == 0:
        return None
    close_time_res = ledger.get("close_time_resolution", 0) or 0
    total_coins = float(ledger.get("total_coins", 0) or 0)

    f1 = n / 30.0
    f2 = close_time_res / 30.0
    f3 = min(total_coins / 1e17, 1.0)

    base = [f1, f2, f3]
    vec = [0.0] * DIMENSION
    for i, val in enumerate(base):
        for k in range(30):
            idx = i * 30 + k
            if idx < DIMENSION:
                vec[idx] = float(val * math.cos(k * math.pi / 30.0))
    h = ledger.get("ledger_hash", "0")
    hb = h.encode()
    for i in range(min(10, DIMENSION)):
        vec[-(i + 1)] = float(hb[i % len(hb)]) / 255.0
    return vec


def ingest_ledger(index: int):
    ledger = get_ledger(index)
    if not ledger:
        return {"index": index, "indexed": False}
    vec = extract_features(ledger)
    if vec is None:
        return {"index": index, "skipped": True}
    ledger_hash = ledger.get("ledger_hash", str(index))
    close_time = ledger.get("close_time", 0)
    # XRPL epoch starts 2000-01-01, offset from Unix epoch = 946684800
    ts = float(close_time) + 946684800 if close_time else time.time()
    entity_id = f"xrpl-mainnet_ledger_{index}"
    bh_id = hashlib.sha3_256(("xrpl-mainnet" + ledger_hash).encode()).hexdigest()
    payload = {
        "entity_id": entity_id, "vector": vec, "magnitude": 0.5, "entropy": 0.5,
        "timestamp": ts, "bh_id": bh_id, "block_num": index, "chain_id": CHAIN_ID, "block_hash": ledger_hash,
    }
    try:
        r = requests.post(f"{FAISS_URL}/index/add", json=payload, timeout=10)
        r.raise_for_status()
        return {"index": index, "indexed": True}
    except Exception as e:
        return {"index": index, "indexed": False, "error": str(e)}


def load_checkpoint(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"last_index": GENESIS_LEDGER - 1, "indexed": 0}


def save_checkpoint(cp, path):
    with open(path, "w") as f:
        json.dump(cp, f, indent=2)


def run_backfill(start: int, end: int):
    checkpoint_file = "genesis_backfill_checkpoint_xrpl-mainnet.json"
    cp = load_checkpoint(checkpoint_file)
    resume = cp["last_index"] + 1
    if resume > start:
        start = resume
    total_indexed = cp["indexed"]
    for batch_start in range(start, end + 1, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE - 1, end)
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = [ex.submit(ingest_ledger, i) for i in range(batch_start, batch_end + 1)]
            for fut in as_completed(futs):
                r = fut.result()
                if r.get("indexed"):
                    total_indexed += 1
        cp["last_index"] = batch_end
        cp["indexed"] = total_indexed
        save_checkpoint(cp, checkpoint_file)
        logger.info("Progress: ledger %d-%d | indexed=%d", batch_start, batch_end, total_indexed)
        time.sleep(0.2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-ledger", type=int, default=GENESIS_LEDGER)
    parser.add_argument("--end-ledger", type=str, default="latest")
    args = parser.parse_args()
    end = get_latest_index() if args.end_ledger == "latest" else int(args.end_ledger)
    if end == 0:
        logger.error("Could not reach XRPL RPC — skipping this cycle.")
        sys.exit(0)
    run_backfill(args.start_ledger, end)
