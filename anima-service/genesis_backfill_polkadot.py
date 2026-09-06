#!/usr/bin/env python3
"""TRION Akashic Index — Polkadot Genesis Backfill. Walks Substrate blocks via
JSON-RPC (chain_getBlockHash + chain_getBlock) from block 0 to tip, extracts a
128-dim vector, POSTs to FAISS."""
import os, sys, json, math, time, hashlib, logging, argparse, requests
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s [POLKADOT-BACKFILL] %(message)s")
logger = logging.getLogger(__name__)

DIMENSION  = 128
FAISS_URL  = os.environ.get("FAISS_SERVICE_URL", "http://127.0.0.1:8000")
FAISS_KEY  = (os.environ.get("FAISS_API_KEY") or os.environ.get("FAISS_SERVICE_API_KEY")
              or os.environ.get("TRION_API_KEY") or "")
_HDRS      = {"X-API-Key": FAISS_KEY} if FAISS_KEY else {}   # SEC-01: FAISS service auth

RPC        = os.environ.get("POLKADOT_RPC_URL", "https://polkadot-rpc.publicnode.com")
WORKERS    = int(os.environ.get("BACKFILL_WORKERS", "3"))
BATCH_SIZE = int(os.environ.get("BACKFILL_BATCH", "50"))
CHAIN_ID   = 25000  # canonical registry id (config/chain_registry.json); was 900 — collided with canonical Solana


def rpc_call(method, params):
    try:
        r = requests.post(RPC, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=10)
        return r.json().get("result")
    except Exception as e:
        logger.warning("RPC error (%s): %s", method, e)
        return None


def get_latest_number() -> int:
    header = rpc_call("chain_getHeader", [])
    if header:
        return int(header.get("number", "0x0"), 16)
    return 0


def get_block(number: int):
    block_hash = rpc_call("chain_getBlockHash", [number])
    if not block_hash:
        return None
    return rpc_call("chain_getBlock", [block_hash]), block_hash


def extract_features(block: dict):
    extrinsics = block.get("block", {}).get("extrinsics", []) or []
    n = len(extrinsics)
    if n == 0:
        return None
    lens = [len(e) for e in extrinsics]
    total = sum(lens) or 1
    avg = total / n

    f1 = n / 20.0
    f2 = total / 10000.0
    f3 = avg / 500.0
    f4 = max(lens) / total

    base = [f1, f2, f3, f4]
    vec = [0.0] * DIMENSION
    for i, val in enumerate(base):
        for k in range(25):
            idx = i * 25 + k
            if idx < DIMENSION:
                vec[idx] = float(val * math.cos(k * math.pi / 25.0))
    return vec


def ingest_block(number: int):
    result = get_block(number)
    if not result or not result[0]:
        return {"number": number, "indexed": False}
    block, block_hash = result
    vec = extract_features(block)
    if vec is None:
        return {"number": number, "skipped": True}
    hb = block_hash.encode()
    for i in range(min(10, DIMENSION)):
        vec[-(i + 1)] = float(hb[i % len(hb)]) / 255.0

    entity_id = f"polkadot-mainnet_block_{number}"
    bh_id = hashlib.sha3_256(("polkadot-mainnet" + block_hash).encode()).hexdigest()
    payload = {
        "entity_id": entity_id, "vector": vec, "magnitude": 0.5, "entropy": 0.5,
        "timestamp": time.time(), "bh_id": bh_id, "block_num": number,
        "chain_id": CHAIN_ID, "block_hash": block_hash,
    }
    try:
        r = requests.post(f"{FAISS_URL}/index/add", json=payload, headers=_HDRS, timeout=10)
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
    checkpoint_file = "genesis_backfill_checkpoint_polkadot-mainnet.json"
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
        logger.error("Could not reach Polkadot RPC — skipping this cycle.")
        sys.exit(0)
    run_backfill(args.start_block, end)
