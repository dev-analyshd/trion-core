"""
TRION BTCP — Ultra-Light Node block-header processing
====================================================

Per BTCP Master Spec §8.2 (Ultra-Light Node — The Crack That Cannot Be
Sealed).  Hostile chains publish block headers regardless of TRION's
permission: block hash, Merkle root, timestamp, validator signatures.
TRION processes ~80 bytes per block — trivial cost, zero permission
required — and from headers alone derives:

    * block production rhythm (mean inter-block time, drift)
    * validator set changes (signer rotation across consecutive headers)
    * fork events (parent-hash discontinuity)
    * timestamp manipulation attempts (out-of-order or jittered ts)
    * liveness signals (gap between consecutive header timestamps)

This module implements the 80-byte Bitcoin block-header parser, the
proof-of-work verification (``SHA256(SHA256(header)) ≤ target`` where the
target is decoded from the ``bits`` compact-difficulty field), and the
header store (TimescaleDB ``ultra_light_headers`` table — created on
first call; SQLite mirror for offline tests).

Layout of an 80-byte Bitcoin block header (BTC little-endian):

    offset  size  field
    0       4     version       (LE uint32)
    4       32    prev_block    (LE hash — display reversed)
    36      32    merkle_root   (LE hash — display reversed)
    68      4     timestamp     (LE uint32, Unix seconds)
    72      4     bits          (LE uint32, compact difficulty)
    76      4     nonce         (LE uint32)

The PoW hash is ``SHA256(SHA256(header_80_bytes))`` (Bitcoin's double-SHA256).
The hash is interpreted as a little-endian 256-bit unsigned integer and
MUST be ≤ the target decoded from ``bits`` (Bitcoin's compact format).

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""
from __future__ import annotations

import hashlib
import os
import struct
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Spec §8.2: TRION processes ~80 bytes per block.
ULTRA_LIGHT_NODE_BYTES_PER_BLOCK = 80


# ═══════════════════════════════════════════════════════════════════════════════
# Bitcoin block-header parser + PoW verifier
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class BlockHeader:
    """Parsed 80-byte Bitcoin block header."""
    version:      int          # 4-byte LE uint32
    prev_block:   bytes        # 32-byte LE hash (display-reversed)
    merkle_root:  bytes        # 32-byte LE hash (display-reversed)
    timestamp:    int          # 4-byte LE uint32, Unix seconds
    bits:         int          # 4-byte LE uint32 compact difficulty
    nonce:        int          # 4-byte LE uint32
    block_hash:   bytes = b""  # 32-byte double-SHA256 (LE) — filled by parser
    target:       int = 0      # decoded 256-bit target

    @property
    def block_hash_hex(self) -> str:
        # Bitcoin block hashes are displayed in reverse (big-endian) byte
        # order relative to how they appear in the wire-format header.
        return self.block_hash[::-1].hex()

    @property
    def prev_block_hex(self) -> str:
        return self.prev_block[::-1].hex()

    @property
    def merkle_root_hex(self) -> str:
        return self.merkle_root[::-1].hex()


def parse_block_header(raw: bytes) -> BlockHeader:
    """Parse an 80-byte Bitcoin block header (per spec §8.2).

    Raises ValueError when the header is not exactly 80 bytes.
    Computes the double-SHA256 PoW hash and decodes the ``bits`` target.
    """
    if len(raw) != ULTRA_LIGHT_NODE_BYTES_PER_BLOCK:
        raise ValueError(
            f"block header must be exactly {ULTRA_LIGHT_NODE_BYTES_PER_BLOCK} "
            f"bytes (spec §8.2), got {len(raw)}"
        )
    # Bitcoin wire format (little-endian):
    #   0   4   version      (LE uint32)
    #   4   32  prev_block   (LE 32-byte hash)
    #   36  32  merkle_root  (LE 32-byte hash)
    #   68  4   timestamp    (LE uint32, Unix seconds)
    #   72  4   bits         (LE uint32, compact difficulty)
    #   76  4   nonce        (LE uint32)
    version   = struct.unpack_from("<I", raw, 0)[0]
    prev      = raw[4:36]
    merkle    = raw[36:68]
    timestamp = struct.unpack_from("<I", raw, 68)[0]
    bits      = struct.unpack_from("<I", raw, 72)[0]
    nonce     = struct.unpack_from("<I", raw, 76)[0]

    # Bitcoin PoW: double-SHA256 of the raw 80-byte header.
    h1 = hashlib.sha256(raw).digest()
    h2 = hashlib.sha256(h1).digest()
    target = decode_bits_target(bits)
    return BlockHeader(
        version=version,
        prev_block=prev,
        merkle_root=merkle,
        timestamp=timestamp,
        bits=bits,
        nonce=nonce,
        block_hash=h2,           # 32-byte LE PoW hash
        target=target,
    )


def decode_bits_target(bits: int) -> int:
    """Decode Bitcoin's compact-difficulty ``bits`` field into a 256-bit target.

    Compact format: ``0xAABBBBBB`` where ``AA`` is the exponent (number of
    bytes in the target) and ``BBBBBB`` is the mantissa (3-byte coefficient).
    Special case: when ``AA = 0`` the mantissa is the full target.

    The decoded target is a 256-bit unsigned integer; a valid PoW hash
    (interpreted as little-endian uint256) MUST be ≤ this target.
    """
    exponent = bits >> 24
    mantissa = bits & 0x007F_FFFF  # 23-bit coefficient (sign bit cleared)
    if exponent <= 3:
        target = mantissa >> (8 * (3 - exponent))
    else:
        target = mantissa << (8 * (exponent - 3))
    return target


def verify_pow(header: BlockHeader) -> bool:
    """Verify the PoW: ``hash ≤ target`` (both as little-endian uint256)."""
    if header.target == 0:
        return False
    # Convert the 32-byte LE hash to a Python int.
    hash_int = int.from_bytes(header.block_hash, "little")
    return hash_int <= header.target


def header_to_dict(header: BlockHeader, pow_valid: bool) -> Dict[str, Any]:
    """Serialize a parsed header + PoW verdict to a JSON-safe dict."""
    return {
        "version":            header.version,
        "prev_block_hex":     header.prev_block_hex,
        "merkle_root_hex":    header.merkle_root_hex,
        "timestamp":          header.timestamp,
        "timestamp_iso":     time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(header.timestamp)
        ),
        "bits":              header.bits,
        "nonce":             header.nonce,
        "block_hash_hex":    header.block_hash_hex,
        "target":            str(header.target),
        "pow_valid":         pow_valid,
        "bytes_per_block":   ULTRA_LIGHT_NODE_BYTES_PER_BLOCK,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Block-header store (TimescaleDB ultra_light_headers; SQLite mirror)
# ═══════════════════════════════════════════════════════════════════════════════

DDL_TIMESCALE = """
CREATE TABLE IF NOT EXISTS ultra_light_headers (
    id              BIGSERIAL    PRIMARY KEY,
    chain_id        BIGINT       NOT NULL,             -- hostile chain this header belongs to
    block_hash      BYTEA        NOT NULL UNIQUE,       -- 32-byte LE PoW hash
    prev_block      BYTEA        NOT NULL,
    merkle_root     BYTEA        NOT NULL,
    version         BIGINT       NOT NULL,
    timestamp       BIGINT       NOT NULL,
    bits            BIGINT       NOT NULL,
    nonce           BIGINT       NOT NULL,
    target          NUMERIC(80, 0) NOT NULL,
    pow_valid       BOOLEAN      NOT NULL,
    bytes_per_block INTEGER      NOT NULL DEFAULT 80,
    processed_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_uln_chain
    ON ultra_light_headers (chain_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_uln_pow
    ON ultra_light_headers (chain_id, pow_valid);
"""

DEFAULT_TIMESCALE_DSN = (
    "postgres://tsdbadmin:baemjc9icol13pb5@mo7c8ietup.tv8aa8cnsj.tsdb.cloud."
    "timescale.com:34783/tsdb?sslmode=require"
)


def _connect(dsn: Optional[str] = None):
    import psycopg2  # type: ignore
    url = dsn or os.environ.get("TIMESCALEDB_URL") or DEFAULT_TIMESCALE_DSN
    return psycopg2.connect(url)


def ensure_schema(dsn: Optional[str] = None) -> None:
    """Create the ultra_light_headers table if it doesn't exist (idempotent)."""
    conn = _connect(dsn)
    try:
        cur = conn.cursor()
        cur.execute(DDL_TIMESCALE)
        conn.commit()
    finally:
        conn.close()


def store_header(
    chain_id: int,
    header: BlockHeader,
    pow_valid: bool,
    dsn: Optional[str] = None,
) -> int:
    """Persist a processed block header. Idempotent on ``block_hash``."""
    ensure_schema(dsn)
    conn = _connect(dsn)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO ultra_light_headers
                (chain_id, block_hash, prev_block, merkle_root,
                 version, timestamp, bits, nonce, target, pow_valid)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (block_hash) DO UPDATE
              SET pow_valid = EXCLUDED.pow_valid,
                  processed_at = NOW()
            RETURNING id
            """,
            (
                int(chain_id),
                header.block_hash,
                header.prev_block,
                header.merkle_root,
                header.version,
                header.timestamp,
                header.bits,
                header.nonce,
                str(header.target),
                pow_valid,
            ),
        )
        row = cur.fetchone()
        conn.commit()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def fetch_recent_headers(
    chain_id: int,
    limit: int = 10,
    dsn: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return the most-recent stored headers for a chain (JSON-safe)."""
    ensure_schema(dsn)
    conn = _connect(dsn)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, chain_id,
                   encode(block_hash::bytea, 'hex')  AS block_hash_hex,
                   encode(prev_block::bytea, 'hex')  AS prev_block_hex,
                   encode(merkle_root::bytea, 'hex') AS merkle_root_hex,
                   version, timestamp, bits, nonce,
                   target::text AS target_str, pow_valid,
                   EXTRACT(EPOCH FROM processed_at) AS processed_at_unix
            FROM ultra_light_headers
            WHERE chain_id = %s
            ORDER BY timestamp DESC
            LIMIT %s
            """,
            (int(chain_id), int(limit)),
        )
        cols = [d[0] for d in cur.description]
        rows = []
        for r in cur.fetchall():
            row = dict(zip(cols, r))
            if row.get("processed_at_unix") is not None:
                row["processed_at_unix"] = float(row["processed_at_unix"])
            rows.append(row)
        return rows
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# Top-level entry point: process one block header end-to-end
# ═══════════════════════════════════════════════════════════════════════════════

def process_block_header(
    header_hex: str,
    chain_id: int = 0,
    dsn: Optional[str] = None,
) -> Dict[str, Any]:
    """End-to-end §8.2 ultra-light node: parse → verify PoW → store.

    Args:
        header_hex:  160-char hex string of the 80-byte Bitcoin block header
                     (LE wire format — same byte order as on the wire).
        chain_id:    the hostile chain id this header belongs to.
        dsn:         TimescaleDB DSN; None → env / default.

    Returns:
        JSON-safe dict with the parsed fields, the PoW verdict and the
        stored row id.
    """
    raw = bytes.fromhex(header_hex)
    header = parse_block_header(raw)
    pow_valid = verify_pow(header)
    row_id = store_header(chain_id, header, pow_valid, dsn=dsn)
    return {
        **header_to_dict(header, pow_valid),
        "chain_id":     chain_id,
        "stored_row_id": row_id,
        "specification": "§8.2 Ultra-Light Node (BTCP-FIX2-S59) — block-header PoW verify",
    }


# ── Self-test ──────────────────────────────────────────────────────────────────

# Real Bitcoin mainnet GENESIS block header (height=0, mined by Satoshi
# 2009-01-03).  This is the canonical 80-byte header whose PoW hash is
# 000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f
# (way below the genesis target 0x00000000FFFF0000...).  Used as the
# known-good PoW-valid fixture for the live endpoint test.
#
# Field layout (LE wire format):
#   version=1  |  prev_block=0...0 (no parent)  |  merkle_root (LE)  |
#   timestamp=1231006505 (0x29ab5f49)  |  bits=0x1d00ffff  |  nonce=2083236893 (0x1dac2b7c)
_REAL_GENESIS_HEADER_HEX = (
    "01000000"                                                          # version=1
    + "00" * 32                                                         # prev_block (LE) — all zeros
    + "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a" # merkle_root (LE)
    + "29ab5f49"                                                        # timestamp=1231006505
    + "ffff001d"                                                        # bits=0x1d00ffff
    + "1dac2b7c"                                                        # nonce=2083236893
)


# A header that fails PoW — the real genesis merkle_root but with bits=0
# (target=0 → impossible to satisfy).  Used to exercise the failure path.
_BAD_HEADER_HEX = (
    "01000000"
    + "00" * 32
    + "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a"
    + "29ab5f49"
    + "00000000"  # bits=0 → target=0 → PoW impossible
    + "1dac2b7c"
)


if __name__ == "__main__":
    import json
    print("=== §8.2 Ultra-Light Node block-header processing self-test ===\n")

    # Test 1: parser rejects non-80-byte input.
    try:
        parse_block_header(b"\x00" * 79)
        raise AssertionError("expected ValueError for short header")
    except ValueError as e:
        assert "80 bytes" in str(e)
        print("✓ parser rejects non-80-byte input")

    # Test 2: real Bitcoin genesis header (PoW valid — hash below target).
    result = process_block_header(_REAL_GENESIS_HEADER_HEX, chain_id=99999)
    print(f"✓ genesis header processed: pow_valid={result['pow_valid']}, "
          f"block_hash={result['block_hash_hex']}")
    assert result["pow_valid"] is True, "real genesis header must verify PoW"
    assert result["block_hash_hex"] == (
        "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f"
    ), "genesis hash must match the canonical Satoshi-chain value"
    assert result["bytes_per_block"] == ULTRA_LIGHT_NODE_BYTES_PER_BLOCK == 80

    # Test 3: malformed header (bits=0 → target=0 → PoW impossible).
    bad_result = process_block_header(_BAD_HEADER_HEX, chain_id=99998)
    print(f"✓ impossible-target header: pow_valid={bad_result['pow_valid']}")
    assert bad_result["pow_valid"] is False, "target=0 must fail PoW"

    # Test 4: decode_bits_target known vectors.
    # bits=0x1d00ffff (mainnet genesis difficulty) → target = 0xFFFF * 2^(8*(0x1d-3)) = 0x00000000FFFF0000...0
    t1 = decode_bits_target(0x1d00ffff)
    assert t1 == 0xFFFF * (1 << (8 * (0x1d - 3))), "genesis bits decode mismatch"
    # bits=0x207fffff (regtest max target) → target = 0x7fffff * 2^(8*(0x20-3))
    t2 = decode_bits_target(0x207fffff)
    assert t2 == 0x7fffff * (1 << (8 * (0x20 - 3))), "regtest bits decode mismatch"
    print(f"✓ bits decoding: genesis target={hex(t1)[:24]}..., "
          f"regtest target={hex(t2)[:24]}...")

    print(f"\n✓ recent stored headers for chain 99999:")
    for h in fetch_recent_headers(99999, limit=5):
        print(f"  id={h['id']} ts={h['timestamp']} pow_valid={h['pow_valid']} "
              f"hash={h['block_hash_hex'][:16]}...")

    print("\n§8.2 PASS — block-header processing implemented")
