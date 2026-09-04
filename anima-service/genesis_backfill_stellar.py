#!/usr/bin/env python3
"""TRION Akashic Index — Stellar Genesis Backfill. Walks ledgers via public
Horizon REST API. The public horizon.stellar.org instance only retains a
rolling window of history (not full genesis-to-tip); this script starts at
the oldest ledger that instance currently tracks (history_elder_ledger) and
walks forward, since full network genesis history requires downloading and
parsing XDR checkpoint files from the Stellar history archives, which is
out of scope for a lightweight public-API backfill."""
import os, sys, json, math, time, hashlib, logging, argparse, requests
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s [STELLAR-BACKFILL] %(message)s")
logger = logging.getLogger(__name__)

DIMENSION  = 128
FAISS_URL  = os.environ.get("FAISS_SERVICE_URL", "http://127.0.0.1:8000")
API        = os.environ.get("STELLAR_HORIZON_URL", "https://horizon.stellar.org")
WORKERS    = int(os.environ.get("BACKFILL_WORKERS", "4"))
BATCH_SIZE = int(os.environ.get("BACKFILL_BATCH", "40"))
CHAIN_ID   = 27000  # canonical registry id (config/chain_registry.json)


def get_bounds():
    try:
        r = requests.get(API + "/", timeout=10).json()
        return int(r.get("history_elder_ledger", 0)), int(r.get("history_latest_ledger", 0))
    except Exception as e:
        logger.warning("Could not fetch horizon root: %s", e)
        return 0, 0


def get_ledger(seq: int):
    try:
        r = requests.get(f"{API}/ledgers/{seq}", timeout=15)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception as e:
        logger.warning("Ledger fetch error at %d: %s", seq, e)
        return None


def extract_features(ledger: dict):
    ops = int(ledger.get("operation_count", 0) or 0)
    txs = int(ledger.get("successful_transaction_count", 0) or 0)
    failed = int(ledger.get("failed_transaction_count", 0) or 0)
    if ops == 0 and txs == 0:
        return None

    f1 = txs / 500.0
    f2 = ops / 1000.0
    f3 = failed / 100.0

    base = [f1, f2, f3]
    vec = [0.0] * DIMENSION
    for i, val in enumerate(base):
        for k in range(30):
            idx = i * 30 + k
            if idx < DIMENSION:
                vec[idx] = float(val * math.cos(k * math.pi / 30.0))
    h = ledger.get("hash", "0")
    hb = h.encode()
    for i in range(min(10, DIMENSION)):
        vec[-(i + 1)] = float(hb[i % len(hb)]) / 255.0
    return vec


def ingest_ledger(seq: int):
    ledger = get_ledger(seq)
    if not ledger:
        return {"seq": seq, "indexed": False}
    vec = extract_features(ledger)
    if vec is None:
        return {"seq": seq, "skipped": True}
    lhash = ledger.get("hash", str(seq))
    closed_at = ledger.get("closed_at")
    ts = time.time()
    if closed_at:
        try:
            import datetime
            ts = datetime.datetime.fromisoformat(closed_at.replace("Z", "+00:00")).timestamp()
        except Exception:
            pass
    entity_id = f"stellar-mainnet_ledger_{seq}"
    bh_id = hashlib.sha3_256(("stellar-mainnet" + lhash).encode()).hexdigest()
    payload = {
        "entity_id": entity_id, "vector": vec, "magnitude": 0.5, "entropy": 0.5,
        "timestamp": ts, "bh_id": bh_id, "block_num": seq, "chain_id": CHAIN_ID, "block_hash": lhash,
    }
    try:
        r = requests.post(f"{FAISS_URL}/index/add", json=payload, timeout=10)
        r.raise_for_status()
        return {"seq": seq, "indexed": True}
    except Exception as e:
        return {"seq": seq, "indexed": False, "error": str(e)}


def load_checkpoint(path, default_start):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"last_seq": default_start - 1, "indexed": 0}


def save_checkpoint(cp, path):
    with open(path, "w") as f:
        json.dump(cp, f, indent=2)


def run_backfill(start: int, end: int):
    checkpoint_file = "genesis_backfill_checkpoint_stellar-mainnet.json"
    cp = load_checkpoint(checkpoint_file, start)
    resume = cp["last_seq"] + 1
    if resume > start:
        start = resume
    total_indexed = cp["indexed"]
    for batch_start in range(start, end + 1, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE - 1, end)
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = [ex.submit(ingest_ledger, s) for s in range(batch_start, batch_end + 1)]
            for fut in as_completed(futs):
                r = fut.result()
                if r.get("indexed"):
                    total_indexed += 1
        cp["last_seq"] = batch_end
        cp["indexed"] = total_indexed
        save_checkpoint(cp, checkpoint_file)
        logger.info("Progress: ledger %d-%d | indexed=%d", batch_start, batch_end, total_indexed)
        time.sleep(0.1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-ledger", type=str, default="elder")
    parser.add_argument("--end-ledger", type=str, default="latest")
    args = parser.parse_args()
    elder, latest = get_bounds()
    if latest == 0:
        logger.error("Could not reach Stellar Horizon API — skipping this cycle.")
        sys.exit(0)
    start = elder if args.start_ledger == "elder" else int(args.start_ledger)
    end = latest if args.end_ledger == "latest" else int(args.end_ledger)
    run_backfill(start, end)
