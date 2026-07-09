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


def file_sha256(path: str) -> str:
    """Compute SHA-256 of a file and return as 0x-prefixed hex."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "0x" + h.hexdigest()


def save_local_proof(key: str, file_path: str, root: str, uploaded: bool):
    """Record proof locally — verifiable even without successful upload."""
    proof = {
        "key":       key,
        "file":      os.path.basename(file_path),
        "root":      root,
        "uploaded":  uploaded,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "size":      os.path.getsize(file_path) if os.path.exists(file_path) else 0,
    }
    proof_path = f"{ZG.PROOFS_DIR}/{key}.json"
    with open(proof_path, "w") as f:
        json.dump(proof, f, indent=2)


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
            capture_output=True, text=True, timeout=60
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
    """
    Attempt 0G Storage upload via @0glabs/0g-ts-sdk.
    Timeout: 45s — fails fast so daemon doesn't stall for 5 minutes.
    """
    abs_path = os.path.abspath(file_path)
    script = f"""
import {{ ZgFile, Indexer }} from '@0glabs/0g-ts-sdk';
import {{ ethers }} from 'ethers';

const privateKey = process.env.ZG_UPLOAD_PRIVATE_KEY;
if (!privateKey) {{ console.error('CONFIG_ERR: ZG_UPLOAD_PRIVATE_KEY not set'); process.exit(1); }}

const file     = await ZgFile.fromFilePath('{abs_path}');
const [tree, e1] = await file.merkleTree();
if (e1) {{ console.error('TREE_ERR:' + e1); process.exit(1); }}

const rootHash = tree.rootHash();
const provider = new ethers.JsonRpcProvider('{ZG.RPC}');
const signer   = new ethers.Wallet(privateKey, provider);
const indexer  = new Indexer('{ZG.INDEXER}');

const [tx, e2] = await indexer.upload(file, '{ZG.RPC}', signer);
if (e2) {{ console.error('UPLOAD_ERR:' + e2); process.exit(1); }}
await file.close();

console.log('ROOT:' + rootHash);
console.log('TX:' + (tx?.txHash || tx?.txHashes?.[0] || ''));
"""
    sdk_dir     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trion-0g")
    script_path = os.path.join(sdk_dir, "zg_upload_single.mts")
    with open(script_path, "w") as f:
        f.write(script)

    try:
        env = os.environ.copy()
        env["ZG_UPLOAD_PRIVATE_KEY"] = ZG.PRIVATE_KEY
        result = await asyncio.create_subprocess_exec(
            "npx", "tsx", script_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=sdk_dir,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(result.communicate(), timeout=45)
        output = stdout.decode()

        for line in output.splitlines():
            if line.startswith("ROOT:"):
                return line.replace("ROOT:", "").strip()

        err_text = stderr.decode()[:300] if stderr else ""
        if err_text:
            log.warning(f"SDK stderr: {err_text}")
        return None
    except asyncio.TimeoutError:
        log.warning("SDK upload timed out after 45s — using local SHA-256 proof")
        return None
    except Exception as e:
        log.warning(f"SDK upload error: {e}")
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

        log.info(f"Exporting {new_count:,} new vectors (total={total:,}, prev={prev:,})")

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
        return out_path, new_count, total

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


# ── DB delta export (PostgreSQL via asyncpg) ──────────────────────

async def export_db_delta(pool, state: dict) -> list:
    if pool is None:
        return []

    exports    = []
    last_bh_id = state.get("last_bh_record_id", 0)
    ts         = int(time.time())

    try:
        async with pool.acquire() as conn:
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

    except Exception as e:
        log.error(f"DB delta export error: {e}")

    return exports


# ── SQLite BH-ledger delta export (no PostgreSQL needed) ─────────

async def export_sqlite_bh_delta(state: dict) -> Optional[tuple]:
    """
    Export new behavioral hash records from bh_ledger.db (SQLite).
    Used when PostgreSQL/asyncpg is not available.
    Returns (file_path, record_count, max_id) or None.
    """
    db_path = "bh_ledger.db"
    if not os.path.exists(db_path):
        return None

    last_id = state.get("last_sqlite_bh_id", 0)

    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT id, entity_id, event_type_name, magnitude_norm,
                   chain_id, block_num, sense_hex, antisense_hex, ts
            FROM bh_ledger
            WHERE id > ?
            ORDER BY id ASC
            LIMIT 100000
        """, (last_id,))
        rows = cur.fetchall()
        conn.close()

        if not rows:
            log.info(f"No new SQLite BH records (last_id={last_id:,})")
            return None

        ts       = int(time.time())
        out_path = f"{ZG.EXPORT_DIR}/bh_sqlite_delta_{ts}.bin.gz"
        max_id   = last_id

        event_map = {
            "Transfer": 0, "Swap": 1, "Liquidity": 2, "Stake": 3, "Unstake": 4,
            "Governance": 5, "Borrow": 7, "Repay": 8, "Liquidate": 9,
        }

        with gzip.open(out_path, "wb") as f:
            f.write(b"TRION_BH_S")
            f.write(struct.pack("<Q", len(rows)))
            for r in rows:
                eid   = (r["entity_id"] or "").encode()[:255]
                etype = event_map.get(r["event_type_name"] or "", 0xFF)
                mag   = float(r["magnitude_norm"] or 0)
                cid   = int(r["chain_id"] or 0)
                bnum  = int(r["block_num"] or 0)
                sense_hex = r["sense_hex"] or ""
                sense = bytes.fromhex(sense_hex)[:32] if sense_hex else b'\x00' * 32
                ts_ns = int(r["ts"] * 1e9) if r["ts"] else 0

                f.write(struct.pack("<H", len(eid)))
                f.write(eid)
                f.write(struct.pack("<B",  etype))
                f.write(struct.pack("<f",  mag))
                f.write(struct.pack("<Q",  cid))
                f.write(struct.pack("<Q",  bnum))
                f.write(sense.ljust(32, b'\x00'))
                f.write(struct.pack("<q", ts_ns))
                max_id = max(max_id, int(r["id"]))

        size_kb = os.path.getsize(out_path) / 1024
        log.info(f"SQLite BH delta: {len(rows):,} records → {out_path} ({size_kb:.0f} KB)")
        return out_path, len(rows), max_id

    except Exception as e:
        log.error(f"SQLite BH export error: {e}")
        return None


# ── 0G KV live update ─────────────────────────────────────────────

async def update_kv_store(pool, state: dict):
    try:
        kv_data = {
            "updated_at":     datetime.now(timezone.utc).isoformat(),
            "sync_count":     state.get("sync_count", 0),
            "total_vectors":  state.get("last_vector_count", 0),
            "table_counts":   {},
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

        # SQLite fallback for BH counts
        if os.path.exists("bh_ledger.db"):
            try:
                import sqlite3
                conn2 = sqlite3.connect("bh_ledger.db")
                cur = conn2.cursor()
                cur.execute("SELECT COUNT(*) FROM bh_ledger")
                kv_data["table_counts"]["bh_ledger_sqlite"] = cur.fetchone()[0]
                conn2.close()
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
        else:
            local = file_sha256(kv_path)
            log.info(f"KV snapshot — local hash: {local[:18]}...")

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
        # Still persist the roots locally
        proof_summary = {
            "sync_count":   state.get("sync_count", 0),
            "timestamp":    datetime.now(timezone.utc).isoformat(),
            "root_hashes":  root_hashes,
            "onchain":      False,
            "reason":       "AKASHIC_PROOF_CONTRACT not configured",
        }
        with open(f"{ZG.PROOFS_DIR}/sync_{state.get('sync_count',0)}.json", "w") as f:
            json.dump(proof_summary, f, indent=2)
        log.info(f"Local proof saved: {len(root_hashes)} roots recorded")
        return

    if not w3:
        log.warning("Web3 not available — skipping onchain update")
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

        # ── Balance check before attempting tx ────────────────────
        gas_limit  = 300_000
        gas_price  = w3.eth.gas_price
        est_cost   = gas_limit * gas_price
        balance    = w3.eth.get_balance(account.address)
        if balance < est_cost:
            log.warning(
                f"Deployer wallet insufficient funds for onchain proof\n"
                f"  Address:  {account.address}\n"
                f"  Balance:  {balance/1e18:.6f} ETH\n"
                f"  Est cost: {est_cost/1e18:.6f} ETH\n"
                f"  Roots saved locally in {ZG.PROOFS_DIR}/ — top up wallet to enable onchain proofs"
            )
            proof_summary = {
                "sync_count":  state.get("sync_count", 0),
                "timestamp":   datetime.now(timezone.utc).isoformat(),
                "root_hashes": root_hashes,
                "onchain":     False,
                "reason":      f"insufficient_funds: balance={balance/1e18:.6f} ETH need={est_cost/1e18:.6f} ETH",
                "wallet":      account.address,
            }
            with open(f"{ZG.PROOFS_DIR}/sync_{state.get('sync_count',0)}.json", "w") as f:
                json.dump(proof_summary, f, indent=2)
            return

        nonce = w3.eth.get_transaction_count(account.address)
        tx    = contract.functions.batchUpdateCommitments(
            keys, roots, tx_hashes, sizes
        ).build_transaction({
            "from":     account.address,
            "nonce":    nonce,
            "gas":      gas_limit,
            "gasPrice": gas_price,
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
            state.get("last_sqlite_bh_id", 0),
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
        # Still save locally
        proof_summary = {
            "sync_count":  state.get("sync_count", 0),
            "timestamp":   datetime.now(timezone.utc).isoformat(),
            "root_hashes": root_hashes,
            "onchain":     False,
            "error":       str(e),
        }
        with open(f"{ZG.PROOFS_DIR}/sync_{state.get('sync_count',0)}.json", "w") as f:
            json.dump(proof_summary, f, indent=2)


# ── Main sync cycle ───────────────────────────────────────────────

async def run_sync_cycle(pool, w3, abi: list):
    state    = load_state()
    cycle_ts = datetime.now(timezone.utc).isoformat()
    log.info(f"=== SYNC CYCLE {state['sync_count'] + 1} === {cycle_ts}")

    all_roots = {}

    # 1. FAISS delta
    result = await export_faiss_delta(state)
    if result:
        file_path, new_count, total_count = result
        local_root = file_sha256(file_path)

        log.info("Uploading FAISS delta to 0G Storage...")
        root = await upload_via_sdk(file_path)
        if not root:
            root = upload_via_cli(file_path)

        uploaded = root is not None
        if not root:
            root = local_root
            log.info(f"Upload failed — local SHA-256 root: {root[:18]}...")
        else:
            log.info(f"✓ Upload succeeded: {root[:18]}...")
            log.info(f"  View: {ZG.STORAGE_EXPLORER}/files/{root}")

        key = f"faiss_delta_{state['sync_count']}"
        all_roots[key]                  = root
        state["root_hashes"][key]       = root
        # Always update vector count regardless of upload success
        state["last_vector_count"]      = total_count
        save_local_proof(key, file_path, root, uploaded)

        try:
            os.remove(file_path)
        except Exception:
            pass

    # 2. Full FAISS (daily, every 24 syncs)
    full_path = await export_faiss_full(state)
    if full_path:
        local_root = file_sha256(full_path)
        root = await upload_via_sdk(full_path)
        if root:
            all_roots["faiss_full"]             = root
            state["root_hashes"]["faiss_full"]  = root
            log.info(f"✓ Full FAISS: {root}")
        else:
            all_roots["faiss_full"]            = local_root
            state["root_hashes"]["faiss_full"] = local_root
            log.info(f"Full FAISS — local root: {local_root[:18]}...")
        try:
            os.remove(full_path)
        except Exception:
            pass

    # 3. DB delta (PostgreSQL if available)
    db_exports = await export_db_delta(pool, state)
    for file_path, table, count, max_id in db_exports:
        log.info(f"Uploading {table} delta ({count:,} records)...")
        local_root = file_sha256(file_path)
        root = await upload_via_sdk(file_path)
        uploaded = root is not None
        if not root:
            root = local_root
        key = f"{table}_delta_{state['sync_count']}"
        all_roots[key]             = root
        state["root_hashes"][key]  = root
        log.info(f"{'✓' if uploaded else '~'} {table}: {root[:18]}...")
        if table == "behavioral_events" and max_id:
            state["last_bh_record_id"] = max_id
        save_local_proof(key, file_path, root, uploaded)
        try:
            os.remove(file_path)
        except Exception:
            pass

    # 4. SQLite BH-ledger delta (fallback when PostgreSQL not available)
    if not pool:
        sqlite_result = await export_sqlite_bh_delta(state)
        if sqlite_result:
            file_path, record_count, max_id = sqlite_result
            local_root = file_sha256(file_path)
            log.info("Uploading SQLite BH delta to 0G Storage...")
            root = await upload_via_sdk(file_path)
            uploaded = root is not None
            if not root:
                root = local_root
                log.info(f"SQLite BH upload failed — local root: {root[:18]}...")
            else:
                log.info(f"✓ SQLite BH uploaded: {root[:18]}...")

            key = f"bh_sqlite_delta_{state['sync_count']}"
            all_roots[key]                   = root
            state["root_hashes"][key]        = root
            state["last_sqlite_bh_id"]       = max_id
            save_local_proof(key, file_path, root, uploaded)
            try:
                os.remove(file_path)
            except Exception:
                pass

    # 5. KV snapshot
    await update_kv_store(pool, state)

    # 6. Update onchain proof — always fire if we have any roots
    if all_roots:
        log.info(f"Recording {len(all_roots)} root hashes onchain...")
        await update_onchain_proof(all_roots, state, w3, abi)
    else:
        log.info("No new data this cycle — skipping onchain update")

    # 7. Save state
    state["last_sync_ts"]           = cycle_ts
    state["sync_count"]            += 1
    save_state(state)

    uploaded_count = sum(1 for k in all_roots if "local" not in k.lower())
    log.info(
        f"=== SYNC CYCLE COMPLETE: {len(all_roots)} roots "
        f"({uploaded_count} uploaded, {len(all_roots)-uploaded_count} local) ===\n"
    )
    return all_roots


# ── Entry point ───────────────────────────────────────────────────

async def main():
    try:
        from web3 import Web3
        _web3_available = True
    except ImportError:
        _web3_available = False
        log.warning("web3 not installed — onchain proofs disabled")

    try:
        import asyncpg
        _asyncpg_available = True
    except ImportError:
        _asyncpg_available = False
        log.warning("asyncpg not installed — using SQLite BH-ledger fallback")

    log.info("TRION 0G Sync Daemon starting...")
    log.info(f"Network:  {ZG.NETWORK}")
    log.info(f"RPC:      {ZG.RPC}")
    log.info(f"Contract: {ZG.AKASHIC_PROOF_CONTRACT or 'NOT SET (local proofs only)'}")

    # DB connection (PostgreSQL)
    pool = None
    if _asyncpg_available:
        db_url = os.getenv("DATABASE_URL",
                 "postgresql://postgres:password@localhost:5432/trion")
        try:
            import asyncpg
            pool = await asyncpg.create_pool(db_url, min_size=1, max_size=5)
            log.info("✓ PostgreSQL connected")
        except Exception as e:
            log.warning(f"PostgreSQL connection failed: {e} — SQLite BH-ledger mode")

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
