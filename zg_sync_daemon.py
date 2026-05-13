"""
TRION 0G Storage Sync Daemon
Uploads delta vectors to 0G Storage every hour.
Tracks last sync state — only uploads NEW data.
Updates AkashicProof contract onchain after each sync.

Run: python3 zg_sync_daemon.py
"""
import asyncio
import os
import sys
import json
import struct
import gzip
import time
import subprocess
import hashlib
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from zg_config import ZG

# ── Logging ───────────────────────────────────────────────────────
os.makedirs(ZG.LOGS_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(f"{ZG.LOGS_DIR}/sync_daemon.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("trion.0g.sync")

os.makedirs(ZG.EXPORT_DIR, exist_ok=True)
os.makedirs(ZG.PROOFS_DIR, exist_ok=True)
os.makedirs("0g-state", exist_ok=True)


# ── State management ──────────────────────────────────────────────

def load_state() -> dict:
    if os.path.exists(ZG.STATE_FILE):
        with open(ZG.STATE_FILE) as f:
            return json.load(f)
    return {
        "last_sync_ts":         None,
        "last_vector_count":    0,
        "last_bh_record_id":    0,
        "last_signal_id":       None,
        "sync_count":           0,
        "root_hashes":          {},
        "total_bytes_uploaded": 0,
    }


def save_state(state: dict):
    with open(ZG.STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ── 0G Storage upload via CLI ─────────────────────────────────────

def upload_via_cli(file_path: str) -> Optional[str]:
    try:
        result = subprocess.run(
            [
                "0g-storage-client", "upload",
                "--url",      ZG.INDEXER,
                "--key",      ZG.PRIVATE_KEY,
                "--file",     file_path,
                "--node-url", ZG.RPC,
            ],
            capture_output=True, text=True, timeout=300
        )
        for line in result.stdout.splitlines():
            if "root" in line.lower() or "hash" in line.lower():
                parts = line.split()
                for p in parts:
                    if p.startswith("0x") and len(p) == 66:
                        return p
        return None
    except Exception as e:
        log.warning(f"CLI upload failed: {e}")
        return None


async def upload_via_sdk(file_path: str) -> Optional[str]:
    # Always resolve to absolute path — script runs from trion-0g/ subdir
    abs_path = os.path.abspath(file_path)
    script = f"""
import {{ ZgFile, Indexer }} from '@0glabs/0g-ts-sdk';
import {{ ethers }} from 'ethers';

const file     = await ZgFile.fromFilePath('{abs_path}');
const [tree, e1] = await file.merkleTree();
if (e1) {{ console.error('TREE_ERR:' + e1); process.exit(1); }}

const rootHash = tree.rootHash();
const provider = new ethers.JsonRpcProvider('{ZG.RPC}');
const signer   = new ethers.Wallet('{ZG.PRIVATE_KEY}', provider);
const indexer  = new Indexer('{ZG.INDEXER}');

const [tx, e2] = await indexer.upload(file, '{ZG.RPC}', signer);
if (e2) {{ console.error('UPLOAD_ERR:' + e2); process.exit(1); }}
await file.close();

console.log('ROOT:' + rootHash);
console.log('TX:' + (tx?.txHash || tx?.txHashes?.[0] || ''));
"""
    # Write script to trion-0g dir where @0glabs/0g-ts-sdk is installed
    sdk_dir    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trion-0g")
    script_path = os.path.join(sdk_dir, "zg_upload_single.mts")
    with open(script_path, "w") as f:
        f.write(script)

    try:
        result = await asyncio.create_subprocess_exec(
            "npx", "tsx", script_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=sdk_dir,
        )
        stdout, stderr = await asyncio.wait_for(result.communicate(), timeout=300)
        output = stdout.decode()

        for line in output.splitlines():
            if line.startswith("ROOT:"):
                return line.replace("ROOT:", "").strip()

        if stderr:
            log.warning(f"SDK upload stderr: {stderr.decode()[:200]}")
        return None
    except asyncio.TimeoutError:
        log.error("SDK upload timed out after 300s")
        return None
    except Exception as e:
        log.error(f"SDK upload error: {e}")
        return None


# ── FAISS delta export ────────────────────────────────────────────

async def export_faiss_delta(state: dict) -> Optional[tuple]:
    try:
        import faiss

        index_paths = [
            "akashic_faiss.index",
            "/persistent/trion_faiss.index",
            "akashic/data/trion_faiss.index",
            "data/trion_faiss.index",
        ]
        index = None
        for p in index_paths:
            if os.path.exists(p):
                index = faiss.read_index(p)
                log.info(f"FAISS index loaded from: {p}")
                break

        if index is None:
            log.warning("FAISS index not found — skipping vector export")
            return None

        total     = index.ntotal
        prev      = state.get("last_vector_count", 0)
        new_count = total - prev

        if new_count <= 0:
            log.info(f"No new vectors (total={total:,}, prev={prev:,})")
            return None

        log.info(f"Exporting {new_count:,} new vectors (total={total:,})")

        dim      = index.d
        ts       = int(time.time())
        out_path = f"{ZG.EXPORT_DIR}/faiss_delta_{ts}.bin.gz"

        with gzip.open(out_path, "wb") as f:
            f.write(b"TRION_DELTA")
            f.write(struct.pack("<Q", ts))
            f.write(struct.pack("<Q", prev))
            f.write(struct.pack("<Q", new_count))
            f.write(struct.pack("<I", dim))

            batch_size = 50_000
            for start in range(prev, total, batch_size):
                end   = min(start + batch_size, total)
                batch = np.zeros((end - start, dim), dtype=np.float32)
                index.reconstruct_n(start, end - start, batch)
                f.write(batch.tobytes())

        size_mb = os.path.getsize(out_path) / (1024 * 1024)
        log.info(f"Delta export: {out_path} ({size_mb:.2f} MB)")
        return out_path, new_count

    except ImportError:
        log.error("faiss not installed — pip install faiss-cpu")
        return None
    except Exception as e:
        log.error(f"FAISS export error: {e}")
        return None


async def export_faiss_full(state: dict) -> Optional[str]:
    sync_count = state.get("sync_count", 0)
    if sync_count % 24 != 0:
        return None

    try:
        index_paths = [
            "akashic_faiss.index",
            "/persistent/trion_faiss.index",
            "akashic/data/trion_faiss.index",
        ]
        for p in index_paths:
            if os.path.exists(p):
                ts       = int(time.time())
                out_path = f"{ZG.EXPORT_DIR}/faiss_full_{ts}.bin"
                shutil.copy2(p, out_path)
                log.info(f"Full FAISS exported: {out_path}")
                return out_path
        return None
    except Exception as e:
        log.error(f"Full FAISS export error: {e}")
        return None


# ── DB delta export ───────────────────────────────────────────────

async def export_db_delta(pool, state: dict) -> list:
    if pool is None:
        return []

    exports    = []
    last_bh_id = state.get("last_bh_record_id", 0)
    ts         = int(time.time())

    try:
        async with pool.acquire() as conn:

            # behavioral_events delta
            rows = await conn.fetch("""
                SELECT id, entity_id, event_type, magnitude_norm,
                       chain_id, block_number, sense_hash, antisense_hash, ts
                FROM behavioral_events
                WHERE id > $1
                ORDER BY id ASC
                LIMIT 500000
            """, last_bh_id)

            if rows:
                out_path = f"{ZG.EXPORT_DIR}/bh_delta_{ts}.bin.gz"
                max_id   = 0
                with gzip.open(out_path, "wb") as f:
                    f.write(b"TRION_BH_D")
                    f.write(struct.pack("<Q", len(rows)))
                    for r in rows:
                        eid   = (r["entity_id"] or "").encode()[:255]
                        etype = {"Transfer": 0, "Swap": 1, "Liquidity": 2}.get(
                            r["event_type"], 0xFF)
                        f.write(struct.pack("<H", len(eid)))
                        f.write(eid)
                        f.write(struct.pack("<B",  etype))
                        f.write(struct.pack("<f",  float(r["magnitude_norm"] or 0)))
                        f.write(struct.pack("<Q",  int(r["chain_id"] or 0)))
                        f.write(struct.pack("<Q",  int(r["block_number"] or 0)))
                        sense = bytes.fromhex(r["sense_hash"] or "00" * 32)[:32]
                        anti  = bytes.fromhex(r["antisense_hash"] or "00" * 32)[:32]
                        f.write(sense.ljust(32, b'\x00'))
                        f.write(anti.ljust(32, b'\x00'))
                        ts_ns = int(r["ts"].timestamp() * 1e9) if r["ts"] else 0
                        f.write(struct.pack("<q", ts_ns))
                        max_id = max(max_id, int(r["id"]))

                exports.append((out_path, "behavioral_events", len(rows), max_id))
                log.info(f"BH delta: {len(rows):,} records → {out_path}")

            # trion_signals delta
            try:
                sig_rows = await conn.fetch("""
                    SELECT signal_id, asset_id, signal_type, c_score,
                           phi_adj, m_adj, sigma, k_score, a_score,
                           ci_95_lower, ci_95_upper, conf_genesis,
                           tc_valid, emitted_at
                    FROM trion_signals
                    WHERE emitted_at > NOW() - INTERVAL '2 hours'
                    ORDER BY emitted_at ASC
                """)

                if sig_rows:
                    sig_path = f"{ZG.EXPORT_DIR}/signals_delta_{ts}.jsonl.gz"
                    with gzip.open(sig_path, "wt") as f:
                        for r in sig_rows:
                            rec = dict(r)
                            rec["emitted_at"] = rec["emitted_at"].isoformat()
                            rec["signal_id"]  = str(rec["signal_id"])
                            f.write(json.dumps(rec) + "\n")
                    exports.append((sig_path, "trion_signals", len(sig_rows), None))
                    log.info(f"Signals delta: {len(sig_rows):,} → {sig_path}")
            except Exception:
                pass

            # phi_scores delta
            try:
                phi_rows = await conn.fetch("""
                    SELECT asset_id, chain_id, phi_raw, phi_adj,
                           mf_score, mf_type, ts
                    FROM phi_scores
                    WHERE ts > NOW() - INTERVAL '2 hours'
                    ORDER BY ts ASC
                """)
                if phi_rows:
                    phi_path = f"{ZG.EXPORT_DIR}/phi_delta_{ts}.jsonl.gz"
                    with gzip.open(phi_path, "wt") as f:
                        for r in phi_rows:
                            rec = dict(r)
                            rec["ts"] = rec["ts"].isoformat()
                            f.write(json.dumps(rec) + "\n")
                    exports.append((phi_path, "phi_scores", len(phi_rows), None))
            except Exception:
                pass

    except Exception as e:
        log.error(f"DB delta export error: {e}")

    return exports


# ── 0G KV live update ─────────────────────────────────────────────

async def update_kv_store(pool, state: dict):
    try:
        kv_data = {
            "updated_at":    datetime.now(timezone.utc).isoformat(),
            "sync_count":    state.get("sync_count", 0),
            "total_vectors": state.get("last_vector_count", 0),
            "table_counts":  {},
            "latest_signals": [],
        }

        if pool:
            async with pool.acquire() as conn:
                for table in ["behavioral_events", "trion_signals",
                              "beo_clusters", "phi_scores"]:
                    try:
                        count = await conn.fetchval(
                            f"SELECT COUNT(*) FROM {table}")
                        kv_data["table_counts"][table] = int(count or 0)
                    except Exception:
                        kv_data["table_counts"][table] = 0

                try:
                    latest_sigs = await conn.fetch("""
                        SELECT DISTINCT ON (asset_id)
                            asset_id, signal_type, c_score,
                            phi_adj, m_adj, sigma, emitted_at
                        FROM trion_signals
                        ORDER BY asset_id, emitted_at DESC
                        LIMIT 50
                    """)
                    kv_data["latest_signals"] = [
                        {
                            "asset_id":    r["asset_id"],
                            "signal_type": r["signal_type"],
                            "c_score":     float(r["c_score"] or 0),
                            "phi_adj":     float(r["phi_adj"] or 0),
                            "m_adj":       float(r["m_adj"] or 0),
                            "sigma":       float(r["sigma"] or 0),
                        }
                        for r in latest_sigs
                    ]
                except Exception:
                    pass

        kv_path = f"{ZG.EXPORT_DIR}/kv_snapshot_{int(time.time())}.json"
        with open(kv_path, "w") as f:
            json.dump(kv_data, f)

        root = await upload_via_sdk(kv_path)
        if root:
            log.info(f"KV snapshot uploaded: {root}")
            state["kv_root"]       = root
            state["kv_updated_at"] = datetime.now(timezone.utc).isoformat()

        try:
            os.remove(kv_path)
        except Exception:
            pass

    except Exception as e:
        log.error(f"KV update error: {e}")


# ── Update AkashicProof contract ──────────────────────────────────

async def update_onchain_proof(root_hashes: dict, state: dict, w3, abi: list):
    if not ZG.AKASHIC_PROOF_CONTRACT:
        log.warning("AKASHIC_PROOF_CONTRACT not set — skipping onchain update")
        return

    try:
        contract = w3.eth.contract(
            address=w3.to_checksum_address(ZG.AKASHIC_PROOF_CONTRACT),
            abi=abi,
        )
        account = w3.eth.account.from_key(ZG.PRIVATE_KEY)

        keys      = list(root_hashes.keys())
        roots     = [w3.keccak(text=h) for h in root_hashes.values()]
        tx_hashes = [b'\x00' * 32] * len(keys)
        sizes     = [0] * len(keys)

        if not keys:
            return

        nonce = w3.eth.get_transaction_count(account.address)
        tx    = contract.functions.batchUpdateCommitments(
            keys, roots, tx_hashes, sizes
        ).build_transaction({
            "from":     account.address,
            "nonce":    nonce,
            "gas":      500_000,
            "gasPrice": w3.eth.gas_price,
        })

        signed  = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        log.info(f"Onchain proof updated: {tx_hash.hex()}")
        log.info(f"  Block:    {receipt['blockNumber']}")
        log.info(f"  Explorer: {ZG.CHAIN_EXPLORER}/tx/{tx_hash.hex()}")

        state["last_onchain_tx"]    = tx_hash.hex()
        state["last_onchain_block"] = receipt["blockNumber"]

        # Record sync cycle
        manifest_hash = w3.keccak(text=json.dumps(root_hashes))
        nonce2 = w3.eth.get_transaction_count(account.address)
        tx2    = contract.functions.recordSyncCycle(
            len(keys),
            state.get("last_vector_count", 0),
            state.get("last_bh_record_id", 0),
            manifest_hash,
        ).build_transaction({
            "from":     account.address,
            "nonce":    nonce2,
            "gas":      300_000,
            "gasPrice": w3.eth.gas_price,
        })
        signed2  = account.sign_transaction(tx2)
        tx_hash2 = w3.eth.send_raw_transaction(signed2.raw_transaction)
        w3.eth.wait_for_transaction_receipt(tx_hash2, timeout=120)
        log.info(f"Sync cycle recorded: {tx_hash2.hex()}")

    except Exception as e:
        log.error(f"Onchain proof update error: {e}")


# ── Main sync cycle ───────────────────────────────────────────────

async def run_sync_cycle(pool, w3, abi: list):
    state    = load_state()
    cycle_ts = datetime.now(timezone.utc).isoformat()
    log.info(f"=== SYNC CYCLE {state['sync_count'] + 1} === {cycle_ts}")

    uploaded_roots = {}

    # 1. FAISS delta
    result = await export_faiss_delta(state)
    if result:
        file_path, new_count = result
        log.info("Uploading FAISS delta to 0G Storage...")
        root = await upload_via_sdk(file_path)
        if not root:
            root = upload_via_cli(file_path)
        if root:
            key = f"faiss_delta_{state['sync_count']}"
            uploaded_roots[key]           = root
            state["last_vector_count"]   += new_count
            state["root_hashes"][key]     = root
            log.info(f"✓ FAISS delta: {root}")
            log.info(f"  View: {ZG.STORAGE_EXPLORER}/files/{root}")
            try:
                os.remove(file_path)
            except Exception:
                pass

    # 2. Full FAISS (daily, every 24 syncs)
    full_path = await export_faiss_full(state)
    if full_path:
        root = await upload_via_sdk(full_path)
        if root:
            uploaded_roots["faiss_full"]       = root
            state["root_hashes"]["faiss_full"] = root
            log.info(f"✓ Full FAISS: {root}")
            try:
                os.remove(full_path)
            except Exception:
                pass

    # 3. DB delta
    db_exports = await export_db_delta(pool, state)
    for file_path, table, count, max_id in db_exports:
        log.info(f"Uploading {table} delta ({count:,} records)...")
        root = await upload_via_sdk(file_path)
        if root:
            key = f"{table}_delta_{state['sync_count']}"
            uploaded_roots[key]       = root
            state["root_hashes"][key] = root
            log.info(f"✓ {table}: {root}")
            if table == "behavioral_events" and max_id:
                state["last_bh_record_id"] = max_id
            try:
                os.remove(file_path)
            except Exception:
                pass

    # 4. KV snapshot
    await update_kv_store(pool, state)

    # 5. Update onchain proof
    if uploaded_roots and abi:
        await update_onchain_proof(uploaded_roots, state, w3, abi)

    # 6. Save state
    state["last_sync_ts"]           = cycle_ts
    state["sync_count"]            += 1
    state["total_bytes_uploaded"]   = state.get("total_bytes_uploaded", 0)
    save_state(state)

    log.info(f"=== SYNC CYCLE COMPLETE: {len(uploaded_roots)} files uploaded ===\n")
    return uploaded_roots


# ── Entry point ───────────────────────────────────────────────────

async def main():
    try:
        from web3 import Web3
        from web3.middleware import ExtraDataToPOAMiddleware
        _web3_available = True
    except ImportError:
        _web3_available = False
        log.warning("web3 not installed — onchain proofs disabled")

    try:
        import asyncpg
        _asyncpg_available = True
    except ImportError:
        _asyncpg_available = False
        log.warning("asyncpg not installed — DB exports disabled")

    log.info("TRION 0G Sync Daemon starting...")
    log.info(f"Network:  {ZG.NETWORK}")
    log.info(f"RPC:      {ZG.RPC}")
    log.info(f"Contract: {ZG.AKASHIC_PROOF_CONTRACT or 'NOT SET'}")

    # DB connection
    pool = None
    if _asyncpg_available:
        db_url = os.getenv("DATABASE_URL",
                 "postgresql://postgres:password@localhost:5432/trion")
        try:
            import asyncpg
            pool = await asyncpg.create_pool(db_url, min_size=1, max_size=5)
            log.info("✓ Database connected")
        except Exception as e:
            log.warning(f"Database connection failed: {e} — FAISS-only mode")

    # Web3 connection
    w3 = None
    if _web3_available:
        from web3 import Web3
        from web3.middleware import ExtraDataToPOAMiddleware
        try:
            w3 = Web3(Web3.HTTPProvider(ZG.RPC))
            w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
            log.info(f"✓ 0G Chain connected: block {w3.eth.block_number}")
        except Exception as e:
            log.warning(f"0G Chain connection failed: {e}")
            w3 = None

    # Load AkashicProof ABI
    abi = []
    abi_path = "artifacts/contracts/AkashicProof.sol/AkashicProof.json"
    if os.path.exists(abi_path):
        with open(abi_path) as f:
            abi = json.load(f)["abi"]
        log.info("✓ AkashicProof ABI loaded")

    # Run first sync immediately
    await run_sync_cycle(pool, w3, abi)

    log.info(f"Sync daemon running — next sync in {ZG.SYNC_INTERVAL_SECONDS}s")
    while True:
        await asyncio.sleep(ZG.SYNC_INTERVAL_SECONDS)
        try:
            await run_sync_cycle(pool, w3, abi)
        except Exception as e:
            log.error(f"Sync cycle error: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
