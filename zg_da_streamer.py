"""
TRION 0G DA Streamer
Submits behavioral event blobs to 0G DA every minute.
Uses the DA Client HTTP interface.
Provides data availability guarantees for the Akashic Index.

Falls back to SQLite bh_ledger.db when PostgreSQL is unavailable.

Run: python3 zg_da_streamer.py
"""
import asyncio
import os
import sys
import json
import time
import struct
import hashlib
import logging
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from zg_config import ZG

os.makedirs(ZG.LOGS_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [DA] %(message)s",
    handlers=[
        logging.FileHandler(f"{ZG.LOGS_DIR}/da_streamer.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("trion.0g.da")

DA_CLIENT_URL  = os.getenv("ZG_DA_CLIENT", "http://localhost:51001")
DA_ENTRANCE    = ZG.DA_ENTRANCE
MAX_BLOB_BYTES = 32_000_000

DA_STATE_PATH  = "0g-state/da_state.json"


def load_da_state() -> dict:
    if os.path.exists(DA_STATE_PATH):
        with open(DA_STATE_PATH) as f:
            return json.load(f)
    return {}


def save_da_state(state: dict):
    with open(DA_STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def build_blob(records: list) -> bytes:
    """
    Pack behavioral records into a DA blob.
    Format: [magic:8][count:4][records...]
    Max size: ~31 MB per blob.
    """
    buf = bytearray()
    buf += b"TRION_DA"
    buf += struct.pack("<I", len(records))

    for r in records:
        eid   = (r.get("entity_id") or "").encode()[:255]
        etype = r.get("event_type_byte", 0xFF)
        mag   = float(r.get("magnitude_norm", 0.0))
        chain = int(r.get("chain_id", 0))
        ts_ns = int(r.get("ts_ns", 0))
        sense = bytes.fromhex(r.get("sense_hash", "00" * 32))[:32]

        buf += struct.pack("<H", len(eid))
        buf += eid
        buf += struct.pack("<B", etype)
        buf += struct.pack("<f", mag)
        buf += struct.pack("<Q", chain)
        buf += struct.pack("<q", ts_ns)
        buf += sense.ljust(32, b'\x00')

    return bytes(buf)


async def submit_blob_to_da(blob: bytes, client) -> dict:
    import base64
    data_hash = "0x" + hashlib.sha3_256(blob).hexdigest()

    try:
        resp = await client.post(
            f"{DA_CLIENT_URL}/disperseBlob",
            json={
                "data":     base64.b64encode(blob).decode(),
                "quorumId": 0,
            },
            timeout=120.0,
        )
        if resp.status_code == 200:
            result = resp.json()
            log.info(f"✓ DA blob submitted: {data_hash[:18]}... ({len(blob)/1024:.0f} KB)")
            return {
                "success":      True,
                "data_hash":    data_hash,
                "blob_size":    len(blob),
                "block":        result.get("block", 0),
                "epoch":        result.get("epoch", 0),
                "quorum":       result.get("quorumId", 0),
                "submitted_at": datetime.now(timezone.utc).isoformat(),
            }
        else:
            log.warning(f"DA client {resp.status_code}: {resp.text[:100]}")

    except Exception as e:
        log.info(f"DA client offline ({type(e).__name__}) — storing hash proof locally")

    # Local-only proof — hash is verifiable even without DA submission
    return {
        "success":      False,
        "data_hash":    data_hash,
        "blob_size":    len(blob),
        "local_only":   True,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "note":         "DA client offline — hash recorded locally",
    }


async def record_da_commitment_onchain(commitment: dict, w3, private_key: str,
                                       contract_address: str):
    if not contract_address or not w3 or not private_key:
        return

    try:
        abi_path = "artifacts/contracts/AkashicProof.sol/AkashicProof.json"
        if not os.path.exists(abi_path):
            return

        with open(abi_path) as f:
            abi = json.load(f)["abi"]

        contract = w3.eth.contract(
            address=w3.to_checksum_address(contract_address),
            abi=abi,
        )
        account  = w3.eth.account.from_key(private_key)
        data_hash = w3.keccak(text=commitment["data_hash"])

        nonce = w3.eth.get_transaction_count(account.address)
        tx    = contract.functions.recordDACommitment(
            data_hash,
            commitment.get("blob_size", 0),
            commitment.get("block", 0),
            commitment.get("epoch", 0),
            commitment.get("quorum", 0),
        ).build_transaction({
            "from":     account.address,
            "nonce":    nonce,
            "gas":      200_000,
            "gasPrice": w3.eth.gas_price,
        })
        signed  = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        log.info(f"DA commitment onchain: {tx_hash.hex()}")

    except Exception as e:
        log.warning(f"DA onchain record failed: {e}")


# ── SQLite BH-ledger data source (no PostgreSQL needed) ──────────

def fetch_sqlite_records(last_id: int, limit: int = 5000) -> tuple:
    """
    Fetch behavioral records from bh_ledger.db (SQLite).
    Returns (records_list, max_id).
    """
    db_path = "bh_ledger.db"
    if not os.path.exists(db_path):
        return [], last_id

    event_type_map = {
        "Transfer": 0, "Swap": 1, "Liquidity": 2, "Stake": 3, "Unstake": 4,
        "Governance": 5, "Borrow": 7, "Repay": 8, "Liquidate": 9,
    }

    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT id, entity_id, event_type_name, magnitude_norm,
                   chain_id, ts, sense_hex
            FROM bh_ledger
            WHERE id > ?
            ORDER BY id ASC
            LIMIT ?
        """, (last_id, limit))
        rows = cur.fetchall()
        conn.close()

        if not rows:
            return [], last_id

        records = []
        max_id  = last_id
        for r in rows:
            records.append({
                "entity_id":       r["entity_id"] or "",
                "event_type_byte": event_type_map.get(r["event_type_name"] or "", 0xFF),
                "magnitude_norm":  float(r["magnitude_norm"] or 0),
                "chain_id":        int(r["chain_id"] or 0),
                "ts_ns":           int((r["ts"] or 0) * 1e9),
                "sense_hash":      r["sense_hex"] or "00" * 32,
            })
            max_id = max(max_id, int(r["id"]))

        return records, max_id

    except Exception as e:
        log.error(f"SQLite fetch error: {e}")
        return [], last_id


# ── PostgreSQL data source ────────────────────────────────────────

async def fetch_postgres_records(pool, last_id: int) -> tuple:
    """Fetch behavioral records from PostgreSQL."""
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, entity_id, event_type, magnitude_norm,
                       chain_id, block_number, sense_hash, ts
                FROM behavioral_events
                WHERE id > $1
                ORDER BY id ASC
                LIMIT 10000
            """, last_id)

        if not rows:
            return [], last_id

        event_type_map = {
            "Transfer": 0, "Swap": 1, "Liquidity": 2, "Stake": 3, "Unstake": 4,
            "Governance": 5, "Borrow": 7, "Repay": 8, "Liquidate": 9,
        }

        records = []
        max_id  = last_id
        for r in rows:
            records.append({
                "entity_id":       r["entity_id"],
                "event_type_byte": event_type_map.get(r["event_type"], 0xFF),
                "magnitude_norm":  float(r["magnitude_norm"] or 0),
                "chain_id":        int(r["chain_id"] or 0),
                "ts_ns":           int(r["ts"].timestamp() * 1e9) if r["ts"] else 0,
                "sense_hash":      r["sense_hash"] or "00" * 32,
            })
            max_id = max(max_id, int(r["id"]))

        return records, max_id

    except Exception as e:
        log.error(f"PostgreSQL fetch failed: {e}")
        return [], last_id


# ── Main DA stream cycle ──────────────────────────────────────────

async def da_stream_cycle(pool, w3):
    da_state = load_da_state()
    last_pg_id     = da_state.get("last_submitted_id", 0)
    last_sqlite_id = da_state.get("last_sqlite_id", 0)

    records = []
    max_id  = last_pg_id
    source  = "none"

    # Prefer PostgreSQL, fall back to SQLite
    if pool:
        records, max_id = await fetch_postgres_records(pool, last_pg_id)
        source = "postgresql"
    else:
        records, max_sqlite_id = fetch_sqlite_records(last_sqlite_id)
        source = "sqlite"

    if not records:
        log.debug(f"No new behavioral records for DA (source={source})")
        return

    log.info(f"DA: {len(records):,} records from {source} → building blob(s)...")

    blob   = build_blob(records)
    blobs  = []
    offset = 0
    while offset < len(blob):
        blobs.append(blob[offset: offset + MAX_BLOB_BYTES])
        offset += MAX_BLOB_BYTES

    log.info(f"DA: {len(blob)/1024/1024:.2f} MB → {len(blobs)} blob(s)")

    try:
        import httpx
        async with httpx.AsyncClient() as client:
            for i, b in enumerate(blobs):
                result = await submit_blob_to_da(b, client)
                status = "✓ submitted" if result["success"] else "~ local proof"
                log.info(
                    f"DA blob {i+1}/{len(blobs)}: {status} "
                    f"{result['data_hash'][:18]}... "
                    f"({result['blob_size']/1024:.0f} KB)"
                )

                # Record first blob commitment on-chain
                if i == 0 and ZG.PRIVATE_KEY and ZG.AKASHIC_PROOF_CONTRACT:
                    await record_da_commitment_onchain(
                        result, w3, ZG.PRIVATE_KEY, ZG.AKASHIC_PROOF_CONTRACT
                    )

    except ImportError:
        log.error("httpx not installed — pip install httpx")
        return

    # Save proof summary
    proof = {
        "timestamp":    datetime.now(timezone.utc).isoformat(),
        "source":       source,
        "record_count": len(records),
        "blob_count":   len(blobs),
        "total_bytes":  len(blob),
        "data_hash":    "0x" + hashlib.sha3_256(blob).hexdigest(),
    }
    proof_path = f"0g-state/proofs/da_{int(time.time())}.json"
    with open(proof_path, "w") as f:
        json.dump(proof, f, indent=2)

    # Update state
    if source == "postgresql":
        da_state["last_submitted_id"] = max_id
    else:
        da_state["last_sqlite_id"] = max_sqlite_id if "max_sqlite_id" in dir() else last_sqlite_id

    da_state["last_run"]      = datetime.now(timezone.utc).isoformat()
    da_state["total_blobs"]   = da_state.get("total_blobs", 0) + len(blobs)
    da_state["total_records"] = da_state.get("total_records", 0) + len(records)
    da_state["source"]        = source
    save_da_state(da_state)

    log.info(f"DA cycle complete: {len(records):,} records, {len(blobs)} blobs, source={source}")


async def da_main():
    log.info("TRION 0G DA Streamer starting...")
    log.info(f"DA Client: {DA_CLIENT_URL}")
    log.info(f"Network:   {ZG.NETWORK}")

    pool = None
    try:
        import asyncpg
        db_url = os.getenv("DATABASE_URL",
                 "postgresql://postgres:password@localhost:5432/trion")
        pool = await asyncpg.create_pool(db_url, min_size=1, max_size=3)
        log.info("✓ PostgreSQL connected")
    except Exception as e:
        log.info(f"PostgreSQL not available ({type(e).__name__}) — using SQLite bh_ledger.db")
        if os.path.exists("bh_ledger.db"):
            import sqlite3
            conn = sqlite3.connect("bh_ledger.db")
            cur  = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM bh_ledger")
            count = cur.fetchone()[0]
            conn.close()
            log.info(f"SQLite bh_ledger.db: {count:,} behavioral records available")

    w3 = None
    try:
        from web3 import Web3
        from web3.middleware import ExtraDataToPOAMiddleware
        w3 = Web3(Web3.HTTPProvider(ZG.RPC))
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        log.info(f"✓ 0G Chain connected: block {w3.eth.block_number}")
    except Exception as e:
        log.warning(f"Web3 not available: {e}")

    while True:
        try:
            await da_stream_cycle(pool, w3)
        except Exception as e:
            log.error(f"DA cycle error: {e}")
        await asyncio.sleep(ZG.DA_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(da_main())
