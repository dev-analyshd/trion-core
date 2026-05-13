"""
TRION 0G DA Streamer
Submits behavioral event blobs to 0G DA every minute.
Uses the DA Client HTTP interface.
Provides data availability guarantees for the Akashic Index.

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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [DA] %(message)s",
    handlers=[
        logging.FileHandler(f"{ZG.LOGS_DIR}/da_streamer.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("trion.0g.da")

DA_CLIENT_URL = os.getenv("ZG_DA_CLIENT", "http://localhost:51001")
DA_ENTRANCE   = ZG.DA_ENTRANCE
MAX_BLOB_BYTES = 32_000_000


def build_blob(records: list) -> bytes:
    """
    Pack behavioral records into a DA blob.
    Format: [magic:8][count:4][records...]
    Max size: ~31MB per blob
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
            log.warning(f"DA client returned {resp.status_code}: {resp.text[:100]}")

    except Exception as e:
        log.warning(f"DA client not reachable ({e}) — storing hash proof locally")

    return {
        "success":      False,
        "data_hash":    data_hash,
        "blob_size":    len(blob),
        "local_only":   True,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "note":         "DA client offline — run: docker run 0g-da-client combined",
    }


async def record_da_commitment_onchain(commitment: dict, w3, private_key: str,
                                       contract_address: str):
    if not contract_address or not w3:
        return

    try:
        abi_path = "artifacts/contracts/AkashicProof.sol/AkashicProof.json"
        if not os.path.exists(abi_path):
            return

        with open(abi_path) as f:
            abi = json.load(f)["abi"]

        contract  = w3.eth.contract(
            address=w3.to_checksum_address(contract_address),
            abi=abi,
        )
        account   = w3.eth.account.from_key(private_key)
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
        signed   = account.sign_transaction(tx)
        tx_hash  = w3.eth.send_raw_transaction(signed.raw_transaction)
        log.info(f"DA commitment onchain: {tx_hash.hex()}")

    except Exception as e:
        log.warning(f"DA onchain record failed: {e}")


async def da_stream_cycle(pool, w3):
    if not pool:
        log.debug("No DB pool — skipping DA cycle")
        return

    da_state_path = "0g-state/da_state.json"
    da_state = {}
    if os.path.exists(da_state_path):
        with open(da_state_path) as f:
            da_state = json.load(f)

    last_id = da_state.get("last_submitted_id", 0)

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
    except Exception as e:
        log.error(f"DB fetch failed: {e}")
        return

    if not rows:
        log.debug("No new behavioral events for DA")
        return

    log.info(f"DA: Preparing {len(rows):,} records for blob submission...")

    event_type_map = {
        "Transfer": 0, "Swap": 1, "Liquidity": 2, "Stake": 3, "Unstake": 4,
        "Governance": 5, "Borrow": 7, "Repay": 8, "Liquidate": 9,
    }

    records = [
        {
            "entity_id":       r["entity_id"],
            "event_type_byte": event_type_map.get(r["event_type"], 0xFF),
            "magnitude_norm":  float(r["magnitude_norm"] or 0),
            "chain_id":        int(r["chain_id"] or 0),
            "ts_ns":           int(r["ts"].timestamp() * 1e9) if r["ts"] else 0,
            "sense_hash":      r["sense_hash"] or "00" * 32,
        }
        for r in rows
    ]

    blob   = build_blob(records)
    blobs  = []
    offset = 0
    while offset < len(blob):
        blobs.append(blob[offset: offset + MAX_BLOB_BYTES])
        offset += MAX_BLOB_BYTES

    log.info(f"DA: {len(blob) / 1024 / 1024:.2f} MB → {len(blobs)} blob(s)")

    try:
        import httpx
        async with httpx.AsyncClient() as client:
            for i, b in enumerate(blobs):
                result = await submit_blob_to_da(b, client)
                status = "✓" if result["success"] else "⚠"
                log.info(
                    f"DA blob {i + 1}/{len(blobs)}: {status} "
                    f"{result['data_hash'][:18]}... "
                    f"({result['blob_size'] / 1024:.0f} KB)"
                )

                if i == 0 and ZG.PRIVATE_KEY:
                    await record_da_commitment_onchain(
                        result, w3, ZG.PRIVATE_KEY, ZG.AKASHIC_PROOF_CONTRACT
                    )
    except ImportError:
        log.error("httpx not installed — pip install httpx")
        return

    max_id = max(int(r["id"]) for r in rows)
    da_state["last_submitted_id"] = max_id
    da_state["last_run"]          = datetime.now(timezone.utc).isoformat()
    da_state["total_blobs"]       = da_state.get("total_blobs", 0) + len(blobs)
    da_state["total_records"]     = da_state.get("total_records", 0) + len(rows)

    with open(da_state_path, "w") as f:
        json.dump(da_state, f, indent=2)

    log.info(f"DA cycle complete: {len(rows):,} records, {len(blobs)} blobs")


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
        log.info("✓ Database connected")
    except Exception as e:
        log.warning(f"DB connection failed: {e} — DA streamer will wait")

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
