#!/usr/bin/env python3
"""
TRION Akashic Index — Genesis Bootstrap / Historical Backfill
Whitepaper mandate: Full EVM history from genesis, zero gaps.

Usage:
    python genesis_backfill.py --start-block 0 --end-block latest --rpc <url>

This script ingests every Arbitrum block from the given range into the Akashic
FAISS Intelligence Engine, generating 128-dimensional behavioral vectors for
each block and registering them via the /index/add endpoint.

Parallel ingestion is used for throughput. Progress is checkpointed every 1000
blocks so the process is resumable. A gap-validation pass is run at the end.
"""

import os
import sys
import json
import math
import time
import hashlib
import logging
import argparse
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Optional

import numpy as np

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [BACKFILL] %(message)s",
)
logger = logging.getLogger(__name__)

DIMENSION      = 128
FAISS_URL      = os.environ.get("FAISS_SERVICE_URL", "http://127.0.0.1:8000")
ARBITRUM_RPC   = os.environ.get("ARBITRUM_RPC_URL",  "https://arb-one.api.pocket.network")
WORKERS        = int(os.environ.get("BACKFILL_WORKERS", "4"))
BATCH_SIZE     = int(os.environ.get("BACKFILL_BATCH",   "50"))

# Known EVM chain_ids for the chains this backfill has been run against so far.
CHAIN_IDS = {
    "eth-mainnet": 1,
    "arb-mainnet": 42161,
}


# ── RPC helpers ────────────────────────────────────────────────────────────────

def rpc_call(rpc_url: str, method: str, params: list) -> Optional[dict]:
    body = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    try:
        if REQUESTS_AVAILABLE:
            r = requests.post(rpc_url, json=body, timeout=10)
            return r.json().get("result")
        # Fallback: subprocess curl
        body_str = json.dumps(body)
        out = subprocess.check_output(
            ["curl", "-s", "-X", "POST", "-H", "Content-Type: application/json",
             "--data", body_str, rpc_url],
            timeout=15
        )
        return json.loads(out).get("result")
    except Exception as e:
        logger.warning("RPC error (%s): %s", method, e)
        return None


def get_block(rpc_url: str, block_number: int) -> Optional[dict]:
    hex_block = hex(block_number)
    return rpc_call(rpc_url, "eth_getBlockByNumber", [hex_block, True])


def get_latest_block_number(rpc_url: str) -> int:
    result = rpc_call(rpc_url, "eth_blockNumber", [])
    if result:
        return int(result, 16)
    return 0


# ── Feature extraction (mirrors trion-l0 logic) ───────────────────────────────

def hex_to_int(h: str) -> int:
    if not h or h == "0x":
        return 0
    return int(h, 16)


def extract_features(block: dict) -> Optional[np.ndarray]:
    """
    Extract the same 9 L1 features as trion-l0, then expand to 128 dimensions
    via a deterministic, lossless encoding for FAISS indexing.
    """
    txs = block.get("transactions", [])
    if not txs:
        return None

    base_fee = hex_to_int(block.get("baseFeePerGas", "0x0"))
    tx_count = len(txs)

    senders, receivers = set(), set()
    total_value = 0
    zero_value  = 0
    contract_interactions = 0
    gas_limits  = []

    for tx in txs:
        frm   = (tx.get("from") or "").lower()
        to    = (tx.get("to")   or "").lower()
        val   = hex_to_int(tx.get("value", "0x0"))
        gas   = hex_to_int(tx.get("gas",   "0x0"))
        inp   = tx.get("input", "0x")

        senders.add(frm)
        if to:
            receivers.add(to)
        total_value += val
        if val == 0:
            zero_value += 1
        if not to or (inp and inp != "0x" and len(inp) > 2):
            contract_interactions += 1
        gas_limits.append(gas)

    gas_limits.sort()
    total_gas  = sum(gas_limits) or 1
    top10_start = max(0, int(tx_count * 0.90))
    top10_gas  = sum(gas_limits[top10_start:])

    f1 = tx_count
    f2 = base_fee
    f3 = total_value / 1e18
    f4 = len(senders) / tx_count
    f5 = len(receivers) / max(len(senders), 1)
    f6 = contract_interactions / tx_count
    f7 = top10_gas / total_gas
    f8 = zero_value / tx_count
    diversity = f4 * 0.25 + min(f5 / 2.0, 1.0) * 0.15
    activity  = f6 * 0.20
    health    = (1.0 - f8) * 0.25 + (1.0 - min(f7, 1.0)) * 0.15
    f9        = min(diversity + activity + health, 1.0)

    # Expand 9 features → 128 dimensions
    # Each feature is projected into a 14-dim subspace using a deterministic
    # trigonometric basis. This is lossless and invertible.
    base_features = np.array([f1 / 1000.0, f2 / 1e10, f3, f4, f5, f6, f7, f8, f9], dtype="float64")
    vec = np.zeros(DIMENSION, dtype="float32")
    for i, val in enumerate(base_features):
        for k in range(14):
            idx = i * 14 + k
            if idx < DIMENSION:
                vec[idx] = float(val * math.cos(k * math.pi / 14.0))

    # Add block hash entropy for uniqueness
    block_hash = block.get("hash", "0x00")
    hash_bytes = bytes.fromhex(block_hash[2:].zfill(64))
    for i in range(min(10, DIMENSION)):
        vec[-(i + 1)] = float(hash_bytes[i]) / 255.0

    return vec


def compute_magnitude(block: dict) -> float:
    txs = block.get("transactions", [])
    if not txs:
        return 0.0
    total_value = sum(hex_to_int(tx.get("value", "0x0")) for tx in txs)
    return min(1.0, total_value / 1e21)   # normalise to [0,1]


def compute_entropy(block: dict) -> float:
    txs = block.get("transactions", [])
    n   = len(txs)
    if n == 0:
        return 0.0
    unique_senders = len(set((tx.get("from") or "").lower() for tx in txs))
    return min(1.0, unique_senders / n)


# ── Checkpoint management ──────────────────────────────────────────────────────

def load_checkpoint(checkpoint_file: str) -> dict:
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file) as f:
            return json.load(f)
    return {"last_block": -1, "indexed": 0, "gaps": []}


def save_checkpoint(cp: dict, checkpoint_file: str):
    with open(checkpoint_file, "w") as f:
        json.dump(cp, f, indent=2)


# ── FAISS ingestion ────────────────────────────────────────────────────────────

def ingest_block(rpc_url: str, block_number: int, chain_name: str = "arb-mainnet",
                  chain_id: int = 42161) -> Optional[dict]:
    """Fetch a block, extract features, POST to FAISS /index/add."""
    block = get_block(rpc_url, block_number)
    if not block:
        return None

    vec = extract_features(block)
    if vec is None:
        return {"block_num": block_number, "skipped": True, "reason": "empty"}

    ts        = hex_to_int(block.get("timestamp", "0x0"))
    block_hash = block.get("hash", "0x00")
    # Prefix with chain name so entity_ids never collide across chains that
    # share overlapping block numbers (each chain's FAISS/TimescaleDB rows
    # must stay distinguishable — see chain_id column in schema.sql).
    entity_id  = f"{chain_name}_block_{block_number}"
    bh_id      = hashlib.sha3_256((chain_name + block_hash).encode()).hexdigest()

    payload = {
        "entity_id":  entity_id,
        "vector":     vec.tolist(),
        "magnitude":  compute_magnitude(block),
        "entropy":    compute_entropy(block),
        "timestamp":  float(ts),
        "bh_id":      bh_id,
        "block_num":  block_number,
        "chain_id":   chain_id,
        "block_hash": block_hash,
    }

    try:
        if REQUESTS_AVAILABLE:
            r = requests.post(f"{FAISS_URL}/index/add", json=payload, timeout=10)
            r.raise_for_status()
            return {"block_num": block_number, "indexed": True, **r.json()}
    except Exception as e:
        logger.warning("Failed to index block %d: %s", block_number, e)
        return {"block_num": block_number, "indexed": False, "error": str(e)}

    return None


# ── Gap validation ─────────────────────────────────────────────────────────────

def validate_no_gaps(start: int, end: int, indexed_blocks: set) -> list:
    """Return list of missing block numbers (gaps)."""
    missing = []
    for b in range(start, end + 1):
        if b not in indexed_blocks:
            missing.append(b)
    return missing


# ── Main backfill loop ────────────────────────────────────────────────────────

def run_backfill(start_block: int, end_block: int, rpc_url: str,
                  chain_name: str = "arb-mainnet", chain_id: int = 42161,
                  checkpoint_file: Optional[str] = None):
    checkpoint_file = checkpoint_file or f"genesis_backfill_checkpoint_{chain_name}.json"

    logger.info("=" * 65)
    logger.info(" TRION Akashic Genesis Backfill")
    logger.info(" Chain       : %s (chain_id=%d)", chain_name, chain_id)
    logger.info(" Start block : %d", start_block)
    logger.info(" End block   : %d", end_block)
    logger.info(" Workers     : %d", WORKERS)
    logger.info(" Batch size  : %d", BATCH_SIZE)
    logger.info(" FAISS URL   : %s", FAISS_URL)
    logger.info(" Checkpoint  : %s", checkpoint_file)
    logger.info("=" * 65)

    cp = load_checkpoint(checkpoint_file)
    resume_from = cp["last_block"] + 1
    if resume_from > start_block:
        logger.info("Resuming from block %d (checkpoint).", resume_from)
        start_block = resume_from

    indexed_blocks  = set()
    total_indexed   = cp["indexed"]
    total_blocks    = max(end_block - start_block + 1, 1)

    for batch_start in range(start_block, end_block + 1, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE - 1, end_block)
        batch     = range(batch_start, batch_end + 1)

        with ThreadPoolExecutor(max_workers=WORKERS) as executor:
            futures = {executor.submit(ingest_block, rpc_url, b, chain_name, chain_id): b for b in batch}
            for future in as_completed(futures):
                result = future.result()
                if result and result.get("indexed"):
                    indexed_blocks.add(result["block_num"])
                    total_indexed += 1
                elif result and result.get("skipped"):
                    indexed_blocks.add(result["block_num"])  # empty blocks still count

        cp["last_block"] = batch_end
        cp["indexed"]    = total_indexed
        save_checkpoint(cp, checkpoint_file)

        pct = (batch_end - start_block + 1) / total_blocks * 100
        logger.info("Progress: %.4f%%  |  Blocks %d–%d  |  Indexed: %d",
                    pct, batch_start, batch_end, total_indexed)

        # Rate limiting — avoid hammering the RPC
        time.sleep(0.1)

    # Gap validation
    logger.info("Running gap validation...")
    gaps = validate_no_gaps(start_block, end_block, indexed_blocks)
    cp["gaps"] = gaps
    save_checkpoint(cp, checkpoint_file)

    if gaps:
        logger.warning("GAPS DETECTED: %d missing blocks. First 10: %s", len(gaps), gaps[:10])
        logger.info("Re-ingesting gaps...")
        for b in gaps:
            result = ingest_block(rpc_url, b, chain_name, chain_id)
            if result and (result.get("indexed") or result.get("skipped")):
                gaps.remove(b)

    logger.info("=" * 65)
    logger.info(" Backfill complete.")
    logger.info(" Total indexed : %d", total_indexed)
    logger.info(" Remaining gaps: %d", len(gaps))
    if not gaps:
        logger.info(" ✅ ZERO GAPS — Genesis mandate satisfied.")
    else:
        logger.warning(" ⚠️  %d gaps remain. Inspect checkpoint for details.", len(gaps))
    logger.info("=" * 65)

    # Trigger archetype training after backfill
    try:
        if REQUESTS_AVAILABLE:
            r = requests.post(f"{FAISS_URL}/archetypes/train", timeout=60)
            logger.info("Archetype training: %s", r.json().get("status"))
    except Exception as e:
        logger.warning("Archetype training failed: %s", e)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TRION Akashic Genesis Backfill")
    parser.add_argument("--start-block", type=int, default=0,        help="First block to index")
    parser.add_argument("--end-block",   type=str, default="latest", help="Last block to index (int or 'latest')")
    parser.add_argument("--rpc",         type=str, default=None,     help="EVM JSON-RPC endpoint")
    parser.add_argument("--chain-name",  type=str, default="arb-mainnet", help="Chain label, e.g. eth-mainnet")
    parser.add_argument("--chain-id",    type=int, default=None,     help="EVM chain id, e.g. 1 for Ethereum")
    args = parser.parse_args()

    rpc = args.rpc or ARBITRUM_RPC
    chain_id = args.chain_id if args.chain_id is not None else CHAIN_IDS.get(args.chain_name, 42161)
    start = args.start_block

    if args.end_block == "latest":
        end = get_latest_block_number(rpc)
        if end == 0:
            logger.error("Could not fetch latest block number. Check RPC URL.")
            sys.exit(1)
        logger.info("Latest block: %d", end)
    else:
        end = int(args.end_block)

    run_backfill(start, end, rpc, chain_name=args.chain_name, chain_id=chain_id)
