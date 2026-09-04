#!/usr/bin/env python3
"""TRION Akashic Index — StarkNet Genesis Backfill. Walks blocks via JSON-RPC
starknet_getBlockWithTxs from block 0 to tip, extracts a 128-dim vector, POSTs to FAISS."""
import os, sys, json, math, time, hashlib, logging, argparse, requests
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s [STARKNET-BACKFILL] %(message)s")
logger = logging.getLogger(__name__)

DIMENSION  = 128
FAISS_URL  = os.environ.get("FAISS_SERVICE_URL", "http://127.0.0.1:8000")
RPC        = os.environ.get("STARKNET_RPC_URL", "https://rpc.starknet.lava.build:443")
WORKERS    = int(os.environ.get("BACKFILL_WORKERS", "3"))
BATCH_SIZE = int(os.environ.get("BACKFILL_BATCH", "50"))
CHAIN_ID   = 24000  # canonical registry id (config/chain_registry.json)


def rpc_call(method, params):
    try:
        r = requests.post(RPC, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=10)
        return r.json().get("result")
    except Exception as e:
        logger.warning("RPC error (%s): %s", method, e)
        return None


def get_block(number: int):
    return rpc_call("starknet_getBlockWithTxs", [{"block_number": number}])


def get_latest_number() -> int:
    res = rpc_call("starknet_blockNumber", [])
    return int(res) if res is not None else 0


def extract_features(block: dict):
    txs = block.get("transactions", []) or []
    if not txs:
        return None
    tx_count = len(txs)
    types = [t.get("type", "") for t in txs]
    invoke = sum(1 for t in types if t == "INVOKE")
    declare = sum(1 for t in types if t == "DECLARE")
    deploy = sum(1 for t in types if "DEPLOY" in t)

    f1 = tx_count / 50.0
    f2 = invoke / tx_count
    f3 = declare / tx_count
    f4 = deploy / tx_count

    base = [f1, f2, f3, f4]
    vec = [0.0] * DIMENSION
    for i, val in enumerate(base):
        for k in range(25):
            idx = i * 25 + k
            if idx < DIMENSION:
                vec[idx] = float(val * math.cos(k * math.pi / 25.0))
    h = block.get("block_hash", "0x0")
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
    block_hash = block.get("block_hash", str(number))
    entity_id = f"starknet-mainnet_block_{number}"
    bh_id = hashlib.sha3_256(("starknet-mainnet" + block_hash).encode()).hexdigest()
    payload = {
        "entity_id": entity_id, "vector": vec, "magnitude": 0.5, "entropy": 0.5,
        "timestamp": float(block.get("timestamp", time.time())),
        "bh_id": bh_id, "block_num": number, "chain_id": CHAIN_ID, "block_hash": block_hash,
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
    checkpoint_file = "genesis_backfill_checkpoint_starknet-mainnet.json"
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
        logger.error("Could not reach StarkNet RPC — skipping this cycle.")
        sys.exit(0)
    run_backfill(args.start_block, end)
