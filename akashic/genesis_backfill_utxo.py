#!/usr/bin/env python3
"""TRION Akashic Index — UTXO Genesis Backfill (generic).
Walks any Bitcoin-family chain (BTC, LTC, DOGE, DASH) from height 0 to tip
using a per-chain public block-explorer API adapter, extracts a 128-dim
behavioral vector from block/tx shape, and POSTs to FAISS."""
import os, sys, json, math, time, hashlib, logging, argparse, requests
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s [UTXO-BACKFILL] %(message)s")
logger = logging.getLogger(__name__)

DIMENSION  = 128
FAISS_URL  = os.environ.get("FAISS_SERVICE_URL", "http://127.0.0.1:8000")

# Each chain gets its own conservative worker/batch/delay settings to respect
# free public API rate limits (blockcypher especially: ~3 req/sec unauth).
UTXO_CHAINS = {
    "btc":  {"chain_id": 40001, "workers": 4, "batch": 40, "delay": 0.0},
    "ltc":  {"chain_id": 40002, "workers": 2, "batch": 20, "delay": 0.4},
    "doge": {"chain_id": 40003, "workers": 2, "batch": 20, "delay": 0.4},
    "dash": {"chain_id": 40004, "workers": 3, "batch": 30, "delay": 0.1},
}


# ---------------------------------------------------------------------------
# Per-chain adapters: get_latest_height(), get_block(height) -> normalized dict
#   { "hash": str, "tx_count": int, "size": int, "time": int, "tx_ids": [str] }
# ---------------------------------------------------------------------------

def _btc_latest():
    r = requests.get("https://blockstream.info/api/blocks/tip/height", timeout=10)
    return int(r.text)


def _btc_block(height):
    h = requests.get(f"https://blockstream.info/api/block-height/{height}", timeout=10).text
    if not h or "Block not found" in h:
        return None
    b = requests.get(f"https://blockstream.info/api/block/{h}", timeout=10).json()
    return {
        "hash": b.get("id", h), "tx_count": b.get("tx_count", 0),
        "size": b.get("size", 0), "time": b.get("timestamp", 0),
    }


def _blockcypher_latest(coin):
    r = requests.get(f"https://api.blockcypher.com/v1/{coin}/main", timeout=10).json()
    return int(r.get("height", 0))


def _blockcypher_block(coin, height):
    r = requests.get(f"https://api.blockcypher.com/v1/{coin}/main/blocks/{height}", timeout=15)
    if r.status_code != 200:
        return None
    b = r.json()
    if "error" in b:
        return None
    ts = 0
    if b.get("time"):
        try:
            import datetime
            ts = int(datetime.datetime.fromisoformat(b["time"].replace("Z", "+00:00")).timestamp())
        except Exception:
            ts = 0
    return {
        "hash": b.get("hash", str(height)), "tx_count": b.get("n_tx", len(b.get("txids", []))),
        "size": b.get("size", 0), "time": ts,
    }


def _dash_latest():
    r = requests.get("https://insight.dash.org/insight-api/status", timeout=10).json()
    return int(r.get("info", {}).get("blocks", 0))


def _dash_block(height):
    idx = requests.get(f"https://insight.dash.org/insight-api/block-index/{height}", timeout=10)
    if idx.status_code != 200:
        return None
    h = idx.json().get("blockHash")
    if not h:
        return None
    b = requests.get(f"https://insight.dash.org/insight-api/block/{h}", timeout=15).json()
    return {
        "hash": b.get("hash", h), "tx_count": len(b.get("tx", [])),
        "size": b.get("size", 0), "time": b.get("time", 0),
    }


ADAPTERS = {
    "btc":  {"latest": _btc_latest, "block": _btc_block},
    "ltc":  {"latest": lambda: _blockcypher_latest("ltc"), "block": lambda h: _blockcypher_block("ltc", h)},
    "doge": {"latest": lambda: _blockcypher_latest("doge"), "block": lambda h: _blockcypher_block("doge", h)},
    "dash": {"latest": _dash_latest, "block": _dash_block},
}


def extract_features(block: dict):
    tx_count = block.get("tx_count", 0)
    if tx_count == 0:
        return None
    size = block.get("size", 1) or 1
    avg_tx_size = size / tx_count

    f1 = min(tx_count / 500.0, 1.0)
    f2 = size / 1_000_000.0
    f3 = avg_tx_size / 1000.0
    f4 = min(tx_count / 3000.0, 1.0)

    base = [f1, f2, f3, f4]
    vec = [0.0] * DIMENSION
    for i, val in enumerate(base):
        for k in range(25):
            idx = i * 25 + k
            if idx < DIMENSION:
                vec[idx] = float(val * math.cos(k * math.pi / 25.0))
    h = block.get("hash", "0")
    hb = h.encode()
    for i in range(min(10, DIMENSION)):
        vec[-(i + 1)] = float(hb[i % len(hb)]) / 255.0
    return vec


def ingest_height(chain_name: str, chain_id: int, height: int):
    block = ADAPTERS[chain_name]["block"](height)
    if not block:
        return {"height": height, "indexed": False}
    vec = extract_features(block)
    if vec is None:
        return {"height": height, "skipped": True}
    entity_id = f"{chain_name}-mainnet_block_{height}"
    bh_id = hashlib.sha3_256((chain_name + str(height) + block["hash"]).encode()).hexdigest()
    payload = {
        "entity_id": entity_id, "vector": vec,
        "magnitude": min(1.0, block.get("tx_count", 0) / 1000.0), "entropy": 0.5,
        "timestamp": float(block.get("time") or time.time()),
        "bh_id": bh_id, "block_num": height, "chain_id": chain_id, "block_hash": block["hash"],
    }
    try:
        r = requests.post(f"{FAISS_URL}/index/add", json=payload, timeout=10)
        r.raise_for_status()
        return {"height": height, "indexed": True}
    except Exception as e:
        return {"height": height, "indexed": False, "error": str(e)}


def load_checkpoint(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"last_height": -1, "indexed": 0}


def save_checkpoint(cp, path):
    with open(path, "w") as f:
        json.dump(cp, f, indent=2)


def run_backfill(chain_name: str, chain_id: int, start: int, end: int, workers: int, batch: int, delay: float):
    checkpoint_file = f"genesis_backfill_checkpoint_{chain_name}-mainnet.json"
    cp = load_checkpoint(checkpoint_file)
    resume = cp["last_height"] + 1
    if resume > start:
        start = resume
    logger.info("Chain=%s start=%d end=%d", chain_name, start, end)

    total_indexed = cp["indexed"]
    for batch_start in range(start, end + 1, batch):
        batch_end = min(batch_start + batch - 1, end)
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(ingest_height, chain_name, chain_id, h) for h in range(batch_start, batch_end + 1)]
            for fut in as_completed(futs):
                r = fut.result()
                if r.get("indexed"):
                    total_indexed += 1
        cp["last_height"] = batch_end
        cp["indexed"] = total_indexed
        save_checkpoint(cp, checkpoint_file)
        logger.info("[%s] Progress: height %d-%d | indexed=%d", chain_name, batch_start, batch_end, total_indexed)
        if delay:
            time.sleep(delay)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--chain-name", required=True, choices=list(UTXO_CHAINS.keys()))
    parser.add_argument("--start-height", type=int, default=0)
    parser.add_argument("--end-height", type=str, default="latest")
    args = parser.parse_args()

    cfg = UTXO_CHAINS[args.chain_name]
    try:
        end = ADAPTERS[args.chain_name]["latest"]() if args.end_height == "latest" else int(args.end_height)
    except Exception as e:
        logger.error("Could not reach %s API (%s) — skipping this cycle.", args.chain_name, e)
        sys.exit(0)
    if not end:
        logger.error("Could not reach %s API — skipping this cycle.", args.chain_name)
        sys.exit(0)

    run_backfill(args.chain_name, cfg["chain_id"], args.start_height, end, cfg["workers"], cfg["batch"], cfg["delay"])
