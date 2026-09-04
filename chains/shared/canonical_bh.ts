/**
 * TRION Protocol — Canonical Behavioral Hash (L0.1)
 * Dual-strand SHA3-256, matching rust-indexers/crates/trion-common/src/hash_dna.rs::canonical_bh()
 *
 * 93-byte payload layout (big-endian):
 *   [0..32]  entity_id_bytes  — 32 bytes (SHA3-256 of normalised address)
 *   [32]     event_type       — 1 byte (0-19 per whitepaper §2)
 *   [33..41] magnitude_nano   — u64 BE: magnitude_norm × 1e9
 *   [41..49] context          — u64 BE: venue/layer flags
 *   [49..57] timestamp_secs   — u64 BE
 *   [57..61] chain_id         — u32 BE
 *   [61..93] block_hash_bytes — 32 bytes
 *
 * sense     = SHA3-256(payload || 0x00)
 * antisense = SHA3-256(payload || 0xFF) XOR NOT(sense)  [byte-wise complement]
 * Invariant: sense XOR antisense == NOT(SHA3-256(payload || 0xFF))
 */

import { createHash } from "node:crypto";

// ── EventType byte encoding (whitepaper L0.1 §2 — 20 canonical types) ────────
// CANONICAL order — must match src/core/behavioral_hash.py (EventType enum)
// and rust-indexers/crates/trion-common/src/hash_dna.rs (event_type_name).
// A single cross-language test vector is defined in bh_schema_v1.json.
export const EventType = {
  TRANSFER:      0,
  SWAP:          1,
  LIQUIDITY:     2,
  STAKE:         3,
  UNSTAKE:       4,
  GOVERNANCE:    5,
  PROPOSAL:      6,
  BORROW:        7,
  REPAY:         8,
  LIQUIDATE:     9,
  BRIDGE:        10,
  DEPLOY:        11,
  UPGRADE:       12,
  MINT:          13,
  BURN:          14,
  ORACLE_UPDATE: 15,
  MEV_CAPTURE:   16,
  FLASH_LOAN:    17,
  AIRDROP:       18,
  CLAIM:         19,
} as const;

export type EventTypeValue = (typeof EventType)[keyof typeof EventType];

export interface BHResult {
  sense:       string;  // 64 lowercase hex chars
  antisense:   string;  // 64 lowercase hex chars
  payload_len: number;  // always 93
}

/**
 * Lenient hex → exactly 32 bytes, byte-identical to Rust hex_to_32bytes()
 * (indexers/crates/trion-common/src/hash_dna.rs) and Python
 * _hex_to_32bytes() (anima-service/faiss_service.py, bh_streamer.py):
 * strip optional 0x, LEFT-aligned, at most 32 bytes, zero-padded on the
 * right, invalid nibbles decode as 0 (never throws, never substitutes).
 * Per docs/protocol/CANONICAL_BH.md §9.
 */
function hexTo32Bytes(hex: string): Buffer {
  const clean = hex.replace(/^0[xX]/, "");
  const out = Buffer.alloc(32); // zero-initialized
  const nibble = (c: string): number => {
    const v = parseInt(c, 16);
    return Number.isNaN(v) ? 0 : v;
  };
  const byteCount = Math.min(Math.floor(clean.length / 2), 32);
  for (let i = 0; i < byteCount; i++) {
    out[i] = (nibble(clean[i * 2]) << 4) | nibble(clean[i * 2 + 1]);
  }
  return out;
}

/**
 * Derive the 32-byte canonical entity_id from any chain-native address.
 * Matches Rust `bh_id(raw)` = SHA3-256(normalise(address)).
 */
export function entityIdFromAddr(addr: string): string {
  const normalised = addr.trim().toLowerCase();
  return createHash("sha3-256").update(normalised).digest("hex");
}

/**
 * Compute the canonical BH per whitepaper L0.1 §3.1.
 * Output is identical to Rust `canonical_bh()` for the same inputs.
 */
export function canonicalBH(
  entityIdHex:   string,        // 64 hex chars (zero-padded to 32 bytes)
  eventType:     EventTypeValue, // 0-19
  magnitudeNorm: number,         // [0.0, 1.0]
  context:       bigint,         // 8-byte venue/layer flags
  timestampSecs: number,         // unix seconds
  chainId:       number,         // fits in u32
  blockHashHex:  string,         // 64 hex chars (zero-padded to 32 bytes)
): BHResult {
  const payload = Buffer.alloc(93);
  let off = 0;

  // entity_id: 32 bytes
  hexTo32Bytes(entityIdHex).copy(payload, off); off += 32;

  // event_type: 1 byte
  payload[off] = eventType & 0xFF; off += 1;

  // magnitude_nano: 8 bytes BE — TRUNCATE toward zero, never round: must
  // match Python int(...) and Rust `as u64` (docs/protocol/CANONICAL_BH.md §1).
  const magNano = BigInt(Math.trunc(Math.max(0, Math.min(1, magnitudeNorm)) * 1_000_000_000));
  payload.writeBigUInt64BE(magNano, off); off += 8;

  // context: 8 bytes BE
  payload.writeBigUInt64BE(context, off); off += 8;

  // timestamp: 8 bytes BE
  payload.writeBigUInt64BE(BigInt(Math.floor(timestampSecs)), off); off += 8;

  // chain_id: 4 bytes BE (u32)
  payload.writeUInt32BE(chainId >>> 0, off); off += 4;

  // block_hash: 32 bytes
  hexTo32Bytes(blockHashHex).copy(payload, off); // off += 32 (final)

  // Dual-strand hashing
  const p0  = Buffer.concat([payload, Buffer.from([0x00])]);
  const pFF = Buffer.concat([payload, Buffer.from([0xFF])]);

  const sense  = createHash("sha3-256").update(p0).digest();
  const sha3ff = createHash("sha3-256").update(pFF).digest();

  // antisense = sha3ff XOR NOT(sense)
  const antisense = Buffer.alloc(32);
  for (let i = 0; i < 32; i++) {
    antisense[i] = sha3ff[i] ^ (~sense[i] & 0xFF);
  }

  return {
    sense:       sense.toString("hex"),
    antisense:   antisense.toString("hex"),
    payload_len: 93,
  };
}

/**
 * Verify the dual-strand invariant:
 *   antisense XOR NOT(sense) == SHA3-256(payload || 0xFF)
 * Returns true if the BHResult is self-consistent.
 */
export function verifyBH(bh: BHResult, blockHashHex: string, entityIdHex: string,
  eventType: EventTypeValue, magnitudeNorm: number, context: bigint,
  timestampSecs: number, chainId: number): boolean {
  const recomputed = canonicalBH(entityIdHex, eventType, magnitudeNorm, context,
                                 timestampSecs, chainId, blockHashHex);
  return recomputed.sense === bh.sense && recomputed.antisense === bh.antisense;
}
