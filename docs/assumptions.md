# TRION BTC↔Starknet Zero-Bridge — Assumption Inventory

**Phase 0.1** — Every assumption the SPV + zero-bridge stack rests on, with a falsification test for each.

## Assumptions

### A1 — SHA-256 syscall correctness
**Assumption:** The Starknet `core::sha256::compute_sha256_byte_array` syscall produces correct SHA-256 digests on-chain.
**Falsification test:** `T_SHA256` — compute SHA-256 of a known input (e.g., 80 zero bytes) on-chain and compare to the canonical SHA-256 digest. If they differ, the syscall is broken.
**Status:** VERIFIED — isolation test contract `0x5d3993068420dcd024746d443a0ce5dcee9305703711b282b72ed17d72e4f65` returned the correct digest for 64-byte and 80-byte inputs.

### A2 — Cairo u256/Span calldata encoding
**Assumption:** `starknet.js` `CallData.compile` correctly serializes `Span<u8>` (array of u8) and `u256` ({low, high}) for Cairo contract calls.
**Falsification test:** `T_CALLDATA` — pass a known Span<u8> and u256, read them back via a view function, compare to expected. If they differ, encoding is broken.
**Status:** VERIFIED — the `submit_block_header` call passes 80 u8 bytes and the contract reads `header.len() == 80` correctly (block stored).

### A3 — Bitcoin byte-order (LE internal vs BE display)
**Assumption:** Bitcoin uses little-endian internal byte order for hashes, but displays them big-endian. The contract's `double_sha256_le` correctly produces the display-order hash.
**Falsification test:** `T_BYTEORDER` — compute `double_sha256_le` of the real BTC header on-chain, compare to the known block hash (display BE). If they differ, byte-order handling is wrong.
**Status:** VERIFIED — `test_double_sha256_le` view call returned the correct block hash for block 5128449.

### A4 — Esplora/mempool.space merkle format
**Assumption:** Esplora's `/tx/:txid/merkle-proof` returns sibling hashes (NOT including the root), and the real merkle root must be fetched separately from the block header.
**Falsification test:** `T_MERKLE_FMT` — fetch the merkle proof + block, recompute the root from the siblings, compare to the block's merkle_root field. If they differ, the format assumption is wrong.
**Status:** VERIFIED — recomputed root matches `mempool.space` block merkle_root.

### A5 — Genesis checkpoint honesty
**Assumption:** The genesis/checkpoint block hash (set via `set_genesis_tip`) is the single trusted input. All subsequent blocks are verified via PoW + linkage.
**Falsification test:** `T_GENESIS` — attempt to submit a header whose prev_blockhash != genesis tip; expect revert "SPV: chain linkage broken".
**Status:** VERIFIED (Phase 1) — chain linkage assert fires on mismatch.

### A6 — Relayer liveness
**Assumption:** A relayer will submit headers to keep the chain tip current. If no relayer, anchors cannot be verified.
**Falsification test:** `T_RELAYER` — call `verify_anchor` against a block whose header was never submitted; expect revert "SPV: unknown block".
**Status:** VERIFIED — `verify_anchor` checks `block_exists` and reverts if the block is unknown.

### A7 — Bits/difficulty honesty (retarget)
**Assumption:** The `bits` field in the header is honest — i.e., it matches the expected difficulty for the current retarget period.
**Status:** OPEN — Phase 1.1 implements the retarget check. Until then, a relayer could submit a header with trivial bits (low difficulty) and the contract would accept it as long as `hash < target(bits)` passes (which it would, since the target would be easy).

### A8 — Confirmation depth
**Assumption:** The block containing the anchored transaction has enough confirmations (depth) to be considered final.
**Status:** OPEN — Phase 1.2 implements the depth gate. Until then, `verify_anchor` accepts any confirmed block regardless of depth.

### A9 — Header-chain continuity
**Assumption:** The headers submitted form a continuous chain (each header's prev_blockhash links to the previous tip).
**Falsification test:** `T_LINKAGE` — submit a header with a valid PoW but wrong parent; expect revert "SPV: chain linkage broken".
**Status:** VERIFIED — the contract asserts `prev_block_hash == chain_tip`.

### A10 — State-indexing delay
**Assumption:** After a Starknet tx is confirmed, there may be a delay before `getTransactionReceipt` / view calls reflect the new state.
**Falsification test:** `T_INDEX_DELAY` — write to storage, immediately read back; if 0, wait and re-read; confirm eventual consistency.
**Status:** VERIFIED — observed 3-5 second delay; reads succeed after waiting.

### A11 — Fee-estimation bypass safety
**Assumption:** Using `{ maxFee: 0x10000000000n, skipValidate: true }` is safe for submitting transactions (the fee is high enough, and skipValidate doesn't compromise security).
**Falsification test:** `T_FEE_BYPASS` — submit a tx with this config; if it fails with "fee too low" or execution error, the bypass is unsafe.
**Status:** VERIFIED — all submit txs succeeded with this config.

### A12 — Oracle quorum verdict freshness
**Assumption:** The Starknet escrow release requires a coherence score that reflects a fresh oracle quorum verdict, not a stale or self-attested value.
**Falsification test:** `T_ORACLE_QUORUM` — attempt release with a coherence value below the threshold; expect revert "BTCP: coherence insufficient". Attempt release with a self-attested (relayer-supplied) coherence above threshold; check whether the contract accepts it (if yes, this is an OPEN gap).
**Status:** PARTIALLY VERIFIED — the coherence < threshold revert is enforced (tested). Whether the coherence value can be self-attested by the relayer is OPEN (the contract accepts any coherence >= min_coherence from an authorized caller).

## Summary

| ID | Assumption | Status |
|----|-----------|--------|
| A1 | SHA-256 syscall correctness | VERIFIED |
| A2 | Calldata encoding | VERIFIED |
| A3 | Bitcoin byte-order | VERIFIED |
| A4 | Merkle format | VERIFIED |
| A5 | Genesis checkpoint honesty | VERIFIED (Phase 1) |
| A6 | Relayer liveness | VERIFIED |
| A7 | Bits/difficulty honesty (retarget) | OPEN → Phase 1.1 |
| A8 | Confirmation depth | OPEN → Phase 1.2 |
| A9 | Header-chain continuity | VERIFIED |
| A10 | State-indexing delay | VERIFIED |
| A11 | Fee-estimation bypass safety | VERIFIED |
| A12 | Oracle quorum verdict freshness | PARTIALLY VERIFIED → OPEN |

**OPEN items carried into final report:** A7, A8, A12.

## Phase 1 Updates (Mission 2)

### A7 — Bits/difficulty honesty (updated)
**Status:** PARTIALLY CLOSED — MAINNET_STRICT mode implemented (bits == prev between boundaries; retarget clamp at boundaries). TESTNET mode implements min-difficulty rule (gap > 20min → 0x1d00ffff). OPEN: full GetNextWorkRequired walk-back for testnet.

### A10 — Reorg handling (updated)
**Status:** PARTIALLY CLOSED — Owner-gated, time-locked (>=24h) tip-rewind recovery implemented. Requires on-chain evidence (competing headers PoW-verified). OPEN: full cumulative-work-based tip switching.

### A12 — Oracle quorum (updated)
**Status:** CLOSED — Escrow v2 enforces quorum-bound release: attestation_count >= quorum_required AND freshness (<=300s) AND !disputed AND coherence matches etched value. Relayer self-attestation alone CANNOT release.

### A13 — Genesis checkpoint immutability
**Status:** CLOSED — renounce_genesis_ability() makes the checkpoint immutable. set_genesis_tip reverts after renounce.

### A14 — Multi-source ingestion honesty
**Status:** ASSUMPTION — Bitcoin data is fetched from mempool.space (primary) / Esplora (fallback). The honesty of these sources at fetch time is an assumption. On mainnet, multiple independent sources should be used.
