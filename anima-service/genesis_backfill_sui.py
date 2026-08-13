#!/usr/bin/env python3
"""TRION Akashic Index — Sui Genesis Backfill. Walks Sui checkpoints via
JSON-RPC sui_getCheckpoint from sequence 0 to tip, extracts a 128-dim vector,
POSTs to FAISS."""
import os, sys, json, math, time, hashlib, logging, argparse, requests
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s [SUI-BACKFILL] %(message)s")
logger = logging.getLogger(__name__)

DIMENSION  = 128
FAISS_URL  = os.environ.get("FAISS_SERVICE_URL", "http://127.0.0.1:8000")
RPC        = os.environ.get("SUI_RPC_URL", "https://fullnode.mainnet.sui.io:443")
WORKERS    = int(os.environ.get("BACKFILL_WORKERS", "4"))
BATCH_SIZE = int(os.environ.get("BACKFILL_BATCH", "50"))
CHAIN_ID   = 50001


def rpc_call(method, params):
    try:
        r = requests.post(RPC, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=10)
        d = r.json()
        if "error" in d:
            return None
        return d.get("result")
    except Exception as e:
        logger.warning("RPC error (%s): %s", method, e)
        return None


def get_latest_seq() -> int:
    res = rpc_call("sui_getLatestCheckpointSequenceNumber", [])
    return int(res) if res is not None else 0


def get_checkpoint(seq: int):
    return rpc_call("sui_getCheckpoint", [str(seq)])


def extract_features(cp: dict):
    tx_digests = cp.get("transactions", []) or []
    n = len(tx_digests)
    if n == 0:
        return None
    gas = cp.get("epochRollingGasCostSummary", {})
    comp = float(gas.get("computationCost", 0) or 0)
    storage = float(gas.get("storageCost", 0) or 0)
    rebate = float(gas.get("storageRebate", 0) or 0)

    f1 = n / 20.0
    f2 = comp / 1e9
    f3 = storage / 1e9
    f4 = rebate / 1e9

    base = [f1, f2, f3, f4]
    vec = [0.0] * DIMENSION
    for i, val in enumerate(base):
        for k in range(25):
            idx = i * 25 + k
            if idx < DIMENSION:
                vec[idx] = float(val * math.cos(k * math.pi / 25.0))
    digest = cp.get("digest", "0")
    hb = digest.encode()
    for i in range(min(10, DIMENSION)):
        vec[-(i + 1)] = float(hb[i % len(hb)]) / 255.0
    return vec


def ingest_checkpoint(seq: int):
    cp = get_checkpoint(seq)
    if not cp:
        return {"seq": seq, "indexed": False}
    vec = extract_features(cp)
    if vec is None:
        return {"seq": seq, "skipped": True}
    digest = cp.get("digest", str(seq))
    entity_id = f"sui-mainnet_checkpoint_{seq}"
    bh_id = hashlib.sha3_256(("sui-mainnet" + digest).encode()).hexdigest()
    ts_ms = float(cp.get("timestampMs", 0) or 0)
    payload = {
        "entity_id": entity_id, "vector": vec, "magnitude": 0.5, "entropy": 0.5,
        "timestamp": ts_ms / 1000.0 if ts_ms else time.time(),
        "bh_id": bh_id, "block_num": seq, "chain_id": CHAIN_ID, "block_hash": digest,
    }
    try:
        r = requests.post(f"{FAISS_URL}/index/add", json=payload, timeout=10)
        r.raise_for_status()
        return {"seq": seq, "indexed": True}
    except Exception as e:
        return {"seq": seq, "indexed": False, "error": str(e)}


def load_checkpoint_file(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"last_seq": -1, "indexed": 0}


def save_checkpoint_file(cp, path):
    with open(path, "w") as f:
        json.dump(cp, f, indent=2)


def run_backfill(start: int, end: int):
    checkpoint_file = "genesis_backfill_checkpoint_sui-mainnet.json"
    cp = load_checkpoint_file(checkpoint_file)
    resume = cp["last_seq"] + 1
    if resume > start:
        start = resume
    total_indexed = cp["indexed"]
    for batch_start in range(start, end + 1, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE - 1, end)
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = [ex.submit(ingest_checkpoint, s) for s in range(batch_start, batch_end + 1)]
            for fut in as_completed(futs):
                r = fut.result()
                if r.get("indexed"):
                    total_indexed += 1
        cp["last_seq"] = batch_end
        cp["indexed"] = total_indexed
        save_checkpoint_file(cp, checkpoint_file)
        logger.info("Progress: checkpoint %d-%d | indexed=%d", batch_start, batch_end, total_indexed)
        time.sleep(0.2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-checkpoint", type=int, default=0)
    parser.add_argument("--end-checkpoint", type=str, default="latest")
    args = parser.parse_args()
    end = get_latest_seq() if args.end_checkpoint == "latest" else int(args.end_checkpoint)
    if end == 0:
        logger.error("Could not reach Sui RPC — skipping this cycle.")
        sys.exit(0)
    run_backfill(args.start_checkpoint, end)
