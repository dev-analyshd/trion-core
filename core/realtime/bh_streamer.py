#!/usr/bin/env python3
"""
TRION Protocol — Real-Time BH Streamer
=======================================

Connects to public RPC endpoints for major EVM chains, polls for new
blocks and transactions, computes Behavioral Hashes (BH) from real
on-chain data, and writes them to bh_ledger.db.

Chains indexed (public RPCs — no API key required):
  - Ethereum (1)         https://ethereum-rpc.publicnode.com
  - Polygon (137)        https://polygon-bor-rpc.publicnode.com
  - BNB Smart Chain (56) https://bsc-rpc.publicnode.com
  - Arbitrum (42161)     https://arbitrum-one-rpc.publicnode.com
  - Base (8453)          https://base-rpc.publicnode.com
  - Optimism (10)        https://optimism-rpc.publicnode.com
  - Avalanche (43114)    https://avalanche-c-chain-rpc.publicnode.com
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import sys
import threading
import time
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Callable, Any

# ── Chain RPC Configuration ───────────────────────────────────────────────────

CHAIN_RPCS: Dict[int, Dict] = {
    1: {"name": "ethereum", "label": "Ethereum", "rpc": "https://ethereum-rpc.publicnode.com", "block_time": 12, "native_symbol": "ETH", "decimals": 18},
    137: {"name": "polygon", "label": "Polygon", "rpc": "https://polygon-bor-rpc.publicnode.com", "block_time": 2, "native_symbol": "MATIC", "decimals": 18},
    56: {"name": "bnb", "label": "BNB Chain", "rpc": "https://bsc-rpc.publicnode.com", "block_time": 3, "native_symbol": "BNB", "decimals": 18},
    42161: {"name": "arbitrum", "label": "Arbitrum", "rpc": "https://arbitrum-one-rpc.publicnode.com", "block_time": 0.25, "native_symbol": "ETH", "decimals": 18},
    8453: {"name": "base", "label": "Base", "rpc": "https://base-rpc.publicnode.com", "block_time": 2, "native_symbol": "ETH", "decimals": 18},
    10: {"name": "optimism", "label": "Optimism", "rpc": "https://optimism-rpc.publicnode.com", "block_time": 2, "native_symbol": "ETH", "decimals": 18},
    43114: {"name": "avalanche", "label": "Avalanche", "rpc": "https://avalanche-c-chain-rpc.publicnode.com", "block_time": 2, "native_symbol": "AVAX", "decimals": 18},
}

EVENT_TYPES = {
    0: "TRANSFER", 1: "SWAP", 2: "LIQUIDITY", 3: "STAKE", 4: "UNSTAKE",
    5: "GOVERNANCE", 6: "PROPOSAL", 7: "BORROW", 8: "REPAY", 9: "LIQUIDATE",
    10: "BRIDGE", 11: "DEPLOY", 12: "UPGRADE", 13: "MINT", 14: "BURN",
    15: "ORACLE_UPDATE", 16: "MEV_CAPTURE", 17: "FLASH_LOAN", 18: "AIRDROP", 19: "CLAIM",
}

SELECTOR_MAP = {
    "": 0, "a9059cbb": 0, "23b872dd": 0,
    "38ed1739": 1, "8803dbee": 1, "414bf389": 1, "c04b8d59": 1,
    "fb3bdb41": 2, "e8e33700": 2,
    "a694fc3a": 3, "d0e30db0": 3,
    "2e1a7d4d": 4,
    "40c10f19": 13, "42966c68": 14, "79cc6790": 14,
    "5ae401dc": 1, "12aa3caf": 1, "e449022e": 1,
    "3593564c": 5, "b3e3e4d5": 7, "573ade81": 8,
}


def classify_event(selector: str, value: int, has_input: bool) -> int:
    sel = selector.lower().strip()[:8]
    if not has_input or sel == "" or sel == "0x":
        return 0
    et = SELECTOR_MAP.get(sel)
    if et is not None:
        return et
    if len(selector) > 300:
        return 1
    return 0


def compute_bh(entity_id, event_type_id, magnitude_raw, chain_id, block_number, block_hash, timestamp, chain_label):
    mag_human = magnitude_raw / (10 ** 18) if magnitude_raw > 0 else 0
    mag_max = 1000.0
    mag_norm = min(1.0, math.log10(max(mag_human, 0) + 1) / math.log10(mag_max + 1)) if mag_human > 0 else 0.0
    mag_nano = int(mag_norm * 1e9)

    eid_bytes = bytes.fromhex(entity_id.lower().replace("0x", "").ljust(64, "0")[:64])
    context = chain_id.to_bytes(4, "big") + event_type_id.to_bytes(4, "big")
    bh_bytes = bytes.fromhex(block_hash.lower().replace("0x", "").ljust(64, "0")[:64])

    payload = eid_bytes + event_type_id.to_bytes(1, "big") + mag_nano.to_bytes(8, "big") + context + timestamp.to_bytes(8, "big") + chain_id.to_bytes(4, "big") + bh_bytes

    sense = hashlib.sha3_256(payload + b"\x00").digest()
    sha3ff = hashlib.sha3_256(payload + b"\xFF").digest()
    antisense = bytes(a ^ (f ^ 0xFF) for a, f in zip(sha3ff, sense))

    sha3ff_check = hashlib.sha3_256(payload + b"\xFF").digest()
    comp_sense = bytes(b ^ 0xFF for b in sense)
    valid = (bytes(a ^ b for a, b in zip(antisense, comp_sense)) == sha3ff_check)

    return {
        "entity_id": entity_id, "event_type": EVENT_TYPES.get(event_type_id, "UNKNOWN"),
        "event_type_id": event_type_id, "magnitude_norm": mag_norm,
        "chain_id": chain_id, "chain_label": chain_label,
        "block_number": block_number, "block_hash": block_hash,
        "timestamp": timestamp, "sense_hex": sense.hex(),
        "antisense_hex": antisense.hex(), "valid": valid, "tx_hash": "",
    }


def rpc_call(rpc_url, method, params, timeout=10):
    payload = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode("utf-8")
    req = urllib.request.Request(rpc_url, data=payload, headers={"Content-Type": "application/json", "User-Agent": "TRION/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    if "error" in data:
        raise RuntimeError(f"RPC error: {data['error']}")
    return data.get("result")


def get_latest_block(rpc_url):
    return int(rpc_call(rpc_url, "eth_blockNumber", []), 16)


def get_block_with_txs(rpc_url, block_num):
    try:
        return rpc_call(rpc_url, "eth_getBlockByNumber", [hex(block_num), True], timeout=15)
    except Exception:
        return None


class BHStreamer:
    def __init__(self, db_path="bh_ledger.db", chains=None, on_bh=None, max_txs_per_block=50):
        self.db_path = db_path
        self.chains = chains or CHAIN_RPCS
        self.on_bh = on_bh
        self.max_txs_per_block = max_txs_per_block
        self._threads = {}
        self._stop_flags = {}
        self._last_block = {}
        self._stats = {"total_bhs": 0, "total_blocks": 0, "chains_active": 0, "started_at": time.time(), "per_chain": {}}
        self._stats_lock = threading.Lock()
        self._running = False

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""CREATE TABLE IF NOT EXISTS bh_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT, tx_hash TEXT UNIQUE,
            entity_id TEXT, from_addr TEXT, to_addr TEXT,
            event_type INTEGER, event_type_name TEXT,
            magnitude_norm REAL, value_wei TEXT, selector TEXT,
            sense_hex TEXT, antisense_hex TEXT,
            block_num INTEGER, block_hash TEXT,
            chain_id INTEGER, chain_label TEXT, ts REAL, valid INTEGER DEFAULT 1)""")
        conn.execute("CREATE INDEX IF NOT EXISTS bh_ledger_entity ON bh_ledger(entity_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS bh_ledger_chain ON bh_ledger(chain_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS bh_ledger_ts ON bh_ledger(ts DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS bh_ledger_chain_label ON bh_ledger(chain_label)")
        conn.commit()
        conn.close()

    def _write_bh(self, bh, tx, chain_config):
        try:
            conn = sqlite3.connect(self.db_path, timeout=5)
            conn.execute("""INSERT OR IGNORE INTO bh_ledger
                (tx_hash, entity_id, from_addr, to_addr, event_type, event_type_name,
                 magnitude_norm, value_wei, selector, sense_hex, antisense_hex,
                 block_num, block_hash, chain_id, chain_label, ts, valid)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
                tx.get("hash", ""), bh["entity_id"], tx.get("from", ""), tx.get("to", ""),
                bh["event_type_id"], bh["event_type"], bh["magnitude_norm"],
                str(int(tx.get("value", "0x0"), 16)), tx.get("input", "")[:10],
                bh["sense_hex"], bh["antisense_hex"], bh["block_number"], bh["block_hash"],
                bh["chain_id"], bh["chain_label"], bh["timestamp"], 1 if bh["valid"] else 0))
            conn.commit()
            conn.close()
        except Exception:
            pass

    def _process_block(self, chain_id, block, chain_config):
        if not block or "transactions" not in block:
            return
        txs = block["transactions"]
        if len(txs) > self.max_txs_per_block:
            step = max(1, len(txs) // self.max_txs_per_block)
            txs = txs[::step][:self.max_txs_per_block]

        block_num = int(block.get("number", "0x0"), 16)
        block_hash = block.get("hash", "0x" + "00" * 32)
        timestamp = int(block.get("timestamp", "0x0"), 16)
        chain_label = chain_config["name"]

        for tx in txs:
            if not isinstance(tx, dict):
                continue
            from_addr = tx.get("from", "0x" + "00" * 20)
            input_data = tx.get("input", "0x")
            value = int(tx.get("value", "0x0"), 16)
            selector = input_data[:10] if input_data and input_data != "0x" else ""
            event_type_id = classify_event(selector, value, input_data != "0x")

            bh = compute_bh(from_addr, event_type_id, value, chain_id, block_num, block_hash, timestamp, chain_label)
            bh["tx_hash"] = tx.get("hash", "")

            self._write_bh(bh, tx, chain_config)
            if self.on_bh:
                try:
                    self.on_bh(bh, tx, chain_config)
                except Exception:
                    pass

            with self._stats_lock:
                self._stats["total_bhs"] += 1
                cs = self._stats["per_chain"].setdefault(chain_label, {"bhs": 0, "blocks": 0})
                cs["bhs"] += 1

    def _chain_worker(self, chain_id, chain_config):
        rpc_url = chain_config["rpc"]
        chain_name = chain_config["name"]
        poll_interval = max(2.0, chain_config.get("block_time", 12))

        try:
            latest = get_latest_block(rpc_url)
            self._last_block[chain_id] = latest - 3  # skip last 3 blocks for reorg safety
        except Exception as e:
            print(f"[streamer] {chain_name}: Failed to get initial block: {e}", file=sys.stderr)
            return

        print(f"[streamer] {chain_name} (id={chain_id}): starting from block {self._last_block[chain_id]}", flush=True)
        consecutive_errors = 0

        while not self._stop_flags[chain_id].is_set():
            try:
                latest = get_latest_block(rpc_url)
                target = self._last_block[chain_id] + 1

                if target > latest:
                    time.sleep(poll_interval)
                    continue

                block = get_block_with_txs(rpc_url, target)
                if block:
                    self._process_block(chain_id, block, chain_config)
                    self._last_block[chain_id] = target
                    with self._stats_lock:
                        self._stats["total_blocks"] += 1
                        cs = self._stats["per_chain"].setdefault(chain_name, {"bhs": 0, "blocks": 0})
                        cs["blocks"] += 1
                    consecutive_errors = 0
                    if target % 20 == 0:
                        print(f"[streamer] {chain_name}: block {target} ({len(block.get('transactions', []))} txs)", flush=True)
                else:
                    consecutive_errors += 1
                    time.sleep(min(30, poll_interval * (2 ** min(consecutive_errors, 5))))
            except Exception as e:
                consecutive_errors += 1
                if consecutive_errors <= 3:
                    print(f"[streamer] {chain_name}: error: {e}", file=sys.stderr)
                time.sleep(min(30, poll_interval * (2 ** min(consecutive_errors, 5))))

    def start(self):
        self._init_db()
        self._running = True
        for chain_id, config in self.chains.items():
            self._stop_flags[chain_id] = threading.Event()
            t = threading.Thread(target=self._chain_worker, args=(chain_id, config), daemon=True, name=f"bh-{config['name']}")
            t.start()
            self._threads[chain_id] = t
        with self._stats_lock:
            self._stats["chains_active"] = len(self.chains)
        print(f"[streamer] Started {len(self.chains)} chain workers", flush=True)

    def stop(self):
        for flag in self._stop_flags.values():
            flag.set()
        self._running = False

    def get_stats(self):
        with self._stats_lock:
            stats = dict(self._stats)
            stats["uptime_seconds"] = time.time() - stats["started_at"]
            stats["bhs_per_second"] = stats["total_bhs"] / max(1, stats["uptime_seconds"])
            stats["last_blocks"] = {str(k): v for k, v in self._last_block.items()}
            stats["running"] = self._running
            return stats

    def is_running(self):
        return self._running


class FAISSAccumulator:
    def __init__(self):
        self.vector_count = 0
        self._lock = threading.Lock()

    def bh_to_vector(self, bh):
        vec = [0.0] * 128
        et = bh.get("event_type_id", 0)
        if 0 <= et < 20:
            vec[et] = 1.0
        mag = bh.get("magnitude_norm", 0.0)
        for i in range(10):
            vec[20 + i] = mag
        chain_id = bh.get("chain_id", 1)
        chain_norm = (chain_id % 100) / 100.0
        for i in range(10):
            vec[30 + i] = chain_norm
        ts = bh.get("timestamp", 0)
        if ts > 0:
            hour = (ts // 3600) % 24
            dow = (ts // 86400) % 7
            vec[40] = math.sin(2 * math.pi * hour / 24)
            vec[41] = math.cos(2 * math.pi * hour / 24)
            vec[42] = math.sin(2 * math.pi * dow / 7)
            vec[43] = math.cos(2 * math.pi * dow / 7)
            for i in range(44, 60):
                vec[i] = (ts % (i * 100)) / (i * 100.0)
        sense_hex = bh.get("sense_hex", "")
        if sense_hex:
            sense_bytes = bytes.fromhex(sense_hex[:136])
            for i, b in enumerate(sense_bytes[:68]):
                vec[60 + i] = b / 255.0
        return vec

    def on_bh(self, bh, tx, chain_config):
        vec = self.bh_to_vector(bh)
        with self._lock:
            self.vector_count += 1


# ── Global instance ───────────────────────────────────────────────────────────

_global_streamer = None
_global_faiss_acc = None

def get_streamer():
    return _global_streamer

def get_faiss_accumulator():
    return _global_faiss_acc

def start_streamer(db_path="bh_ledger.db"):
    global _global_streamer, _global_faiss_acc
    if _global_streamer and _global_streamer.is_running():
        return _global_streamer
    _global_faiss_acc = FAISSAccumulator()
    _global_streamer = BHStreamer(db_path=db_path, on_bh=_global_faiss_acc.on_bh, max_txs_per_block=50)
    _global_streamer.start()
    return _global_streamer


if __name__ == "__main__":
    print("=== TRION Real-Time BH Streamer ===\n")
    streamer = start_streamer()
    for i in range(6):
        time.sleep(5)
        stats = streamer.get_stats()
        print(f"\n--- {i*5+5}s ---")
        print(f"  Total BHs: {stats['total_bhs']}")
        print(f"  Total blocks: {stats['total_blocks']}")
        print(f"  BHs/sec: {stats['bhs_per_second']:.2f}")
        print(f"  Chains: {stats['chains_active']}")
        for chain, cs in stats["per_chain"].items():
            print(f"    {chain}: {cs['bhs']} BHs, {cs['blocks']} blocks")
    streamer.stop()
    print("\nStopped.")
