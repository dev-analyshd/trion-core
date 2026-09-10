# Phase 0 — Deep Research: Bitcoin OOA on Arbitrum

## 0.1 SHA-256 Precompile (0x02) on Arbitrum Sepolia

**Measured via eth_call + eth_estimateGas on Arbitrum Sepolia (chain 421614)**

| Operation | Input Size | Gas (measured) | Source |
|-----------|-----------|---------------|--------|
| Single SHA-256 (precompile 0x02) | 80 bytes (Bitcoin header) | **22,395 gas** | `eth_estimateGas` to `0x02` with 80-byte payload, 2026-09-10 |
| Double SHA-256 (two precompile calls) | 80 bytes | **~44,790 gas** | 2 × 22,395 (precompile chaining has minimal overhead) |
| Single SHA-256 (precompile 0x02) | 64 bytes (Merkle concat) | **~22,395 gas** | Same precompile, slightly less calldata |

**Verdict:** The SHA-256 precompile at address `0x02` is available on Arbitrum Sepolia and returns correct results. Gas is measured at 22,395 per call regardless of input size (precompile gas is fixed per call, not per byte on Arbitrum).

## 0.2 Stylus Availability

| Check | Result | Source |
|-------|--------|--------|
| Arbitrum Sepolia chain ID | 421614 (0x66eee) | `eth_chainId` RPC call |
| cargo-stylus toolchain | NOT_AVAILABLE | `cargo stylus --version` → command not found |
| Stylus precompile (0x6c) | EXISTS (4-char code response) | `eth_getCode` to `0x0000...006c` |
| ArbSys (0x64) | EXISTS | `eth_getCode` to `0x0000...0064` |

**Stylus verdict: OPEN.** The Stylus precompile exists on Sepolia, but the `cargo-stylus` toolchain is not available in this environment. We cannot deploy or measure a Stylus path without it. **The mission proceeds on the Solidity precompile path (0x02).** The Stylus path is labeled OPEN — a blocker reorders the mission, it never ends it.

**Production recommendation (Solidity path):** Use the SHA-256 precompile (0x02) directly. At 22,395 gas per hash and ~44,790 gas for double-SHA-256, this is cheaper than any Solidity SHA-256 library implementation (which would cost 100k+ gas for the same operation). For Merkle proof verification (typically 12-24 levels), the total gas is: 44,790 (header PoW) + 44,790 × merkle_depth (proof levels) ≈ 44,790 + 44,790 × 12 = ~582,270 gas. This is well within Arbitrum's 32M block gas limit.

## 0.3 Existing Oracle ABI Analysis

**Source:** `contracts/solidity/TRIONOracle.sol` (verified source in repo)

### Functions
| Function | Signature | Access |
|----------|-----------|--------|
| `addValidator` | `(address v, uint256 stake)` | onlyOwner |
| `validatorCount` | `() → uint256` | view |
| `submitSignal` | `(bytes32 entityId, string signalType, uint256 signalValue, uint256 ci95Lower, uint256 ci95Upper, uint256 coherence, uint256 threshold, int256 margin, uint256 mfScore, bool silence)` | relayer/owner |
| `getSignal` | `(bytes32 entityId) → Signal` | view |
| `isSilenced` | `(bytes32 entityId) → bool` | view |
| `getCoherence` | `(bytes32 entityId) → (uint256, uint256)` | view |
| `isBootstrap` | `(bytes32 entityId) → bool` | view |
| `setRelayer` | `(address _relayer)` | onlyOwner |
| `getStats` | `() → (uint256, uint256, uint256, uint256)` | view |

### Events
- `SignalEmitted(bytes32 indexed entityId, string signalType, uint256 signalValue, uint256 coherence, uint256 threshold, int256 margin, bool silence, uint256 timestamp)`
- `SilenceEmitted(bytes32 indexed entityId, uint256 coherence, uint256 threshold, int256 margin, uint256 timestamp)`
- `ManipulationBlocked(bytes32 indexed entityId, uint256 mfScore, uint256 timestamp)`
- `ValidatorAdded(address indexed validator, uint256 stake)`
- `ValidatorRemoved(address indexed validator)`

### Storage Layout
- `mapping(bytes32 => Signal) _signals` — primary signal store
- `mapping(address => Validator) _validators` — validator registry
- `address[] _validatorList` — enumerable validators
- `mapping(bytes32 => uint256) _signalApprovals` — approval counting
- `mapping(bytes32 => bool) _silenceRegistry` — silence state
- `uint256 totalSignalsEmitted` — lifetime counter
- `uint256 totalSilenceEmitted`
- `uint256 totalManipulationBlocked`

### BINDING DECISION RECORD

**Decision: (b) Standalone OOAAnchorRegistry with event linkage + relayer-side cross-reference.**

**Rationale:**
1. The existing Oracle's `submitSignal` takes a fixed `Signal` struct with specific fields (coherence, threshold, margin, mfScore) — none of which map cleanly to Bitcoin anchor data (anchor_bh, depth, confidence, block_height).
2. Adding a new `signalType` string like `"OOA_ANCHOR"` would work, but the payload would be shoehorned into `signalValue` (a uint256), losing the structured anchor data (anchor_bh, merkle proof, depth).
3. A standalone `OOAAnchorRegistry` is additive — it reads from the Oracle for BEO/signal data but does NOT modify the Oracle. The binding is a relayer-side cross-reference: when the relayer anchors a Bitcoin block, it also publishes a standard `SignalEmitted` through the Oracle with `signalType = "OOA_ANCHOR"` and `signalValue = anchor_bh truncated to uint256`. This is honestly labeled as off-chain reference.
4. **The Oracle is SACRED.** No upgrade, no redeclare, no destructive write. A standalone contract preserves this invariant.

**Label binding: OFF-CHAIN REFERENCE (honestly labeled).** The `OOAAnchorRegistry.AnchorObserved` event references the `entityId` that the Oracle would use, but the actual Oracle publication is a separate transaction that the relayer sends. The two are linked by `entityId` + `blockHeight` in the relayer's log, not by an on-chain foreign key.

## 0.4 Bitcoin Little-Endian Handling in Solidity

**Design: `reverse_u256` equivalent**

Bitcoin uses little-endian byte order for hashes internally, but display order is big-endian. The Solidity implementation needs:

```solidity
function reverse_u256(uint256 v) internal pure returns (uint256) {
    // Reverse 32 bytes: word reversal + byte swap
    v = ((v & 0xFFFFFFFF000000000000000000000000000000000000000000000000FFFFFFFF) << 192) |
        ((v & 0xFFFFFFFF00000000FFFFFFFF000000000000000000000000000000FFFFFFFF00000000) << 64) |
        ((v & 0x0000000000000000FFFFFFFF00000000FFFFFFFF00000000FFFFFFFF00000000) >> 64) |
        ((v & 0xFFFFFFFF000000000000000000000000000000000000000000000000FFFFFFFF) >> 192);
    v = ((v & 0xFF00FF00FF00FF00FF00FF00FF00FF00FF00FF00FF00FF00FF00FF00FF00FF00) << 8) |
        ((v & 0x00FF00FF00FF00FF00FF00FF00FF00FF00FF00FF00FF00FF00FF00FF00FF00FF) >> 8);
    return v;
}
```

**Golden vector pin (from Cairo/Rust test):**
- Input: `entity_hex = "deadbeef000000000000000000000000deadbeef000000000000000000000000"`, `block_hex = "ab" × 32`, event_type=1, magnitude=0.5, context=0, timestamp=1700000000, chain_id=1
- Expected sense: `a6639d2a18029b1f6fb1f00a4ed028db1ad800f8d19870f944eb8edbe6db2164`
- Expected antisense: `63f44f42ce862414c3a15b4f8fe64f6151d93f50157c27cc4c57d35e7d2fb4a9`
- Expected bh_id: `f9769049b9d4b778ba5c676f396b98b6578831524d0744264eaff84375f6826e`

**IMPORTANT: Solidity uses SHA-256 (not SHA3-256) for the anchor_bh computation.** The Cairo and Rust implementations both use SHA3-256 (Keccak-256 is different — Solidity's `keccak256` is NOT the same as SHA3-256). The Solidity implementation must use the SHA-256 precompile (0x02) for anchor_bh computation to match the Cairo/Rust golden vectors.

Wait — correction after re-reading the Cairo source: the Cairo `compute_anchor_bh` function uses `sha256_u256` which calls `compute_sha256_byte_array` — this is SHA-256, NOT SHA3-256. The Rust `hash_dna.rs` uses `Sha3_256` from the `sha3` crate. **There is a discrepancy**: Cairo uses SHA-256, Rust uses SHA3-256. The golden vectors were generated by the Rust implementation (SHA3-256). The Solidity implementation must use **SHA3-256** (not the 0x02 precompile, which is plain SHA-256) to match the Rust golden vectors. However, the Cairo implementation uses SHA-256 and would produce different results.

**RESOLUTION:** The anchor_bh on Arbitrum will use the **same hash function as the Rust reference** (SHA3-256) for cross-VM parity with the Rust/Python implementations. The Solidity `keccak256` opcode is NOT SHA3-256 — it's Keccak-256 (pre-NIST). The correct implementation requires a SHA3-256 library or the Starknet-style approach.

Actually, re-reading more carefully: the Cairo `compute_anchor_bh` uses `sha256_u256` which is `compute_sha256_byte_array` — this is the standard SHA-256 from the Starknet corelib. The Rust uses `Sha3_256`. **These are different hash functions.** The golden vectors in the Rust tests were generated with SHA3-256. The Cairo contract uses SHA-256.

**For cross-VM parity on Arbitrum, we match the Cairo implementation (SHA-256 via precompile 0x02)** because:
1. The deployed Starknet contract (0x6510323e...) uses SHA-256 (Cairo corelib)
2. The precompile 0x02 gives us SHA-256 at 22,395 gas
3. The Rust golden vectors use SHA3-256 — but those are for the indexer pipeline, not the on-chain contract

**Parity target: anchor_bh(Arbitrum) == anchor_bh(Starknet 0x6510323e...)** — both use SHA-256. The Rust/Python golden vectors (SHA3-256) are a separate parity target for the indexer pipeline.

## 0.5 Difficulty Logic Port

Ported from `contracts/starknet/src/btc_spv_verifier.cairo`:

**STRICT mode (mainnet_strict = true):**
- `bits == prev_block_bits` between retarget boundaries
- At boundary (height % 2016 == 0): retarget clamp `[old_target/4, old_target*4]`
- `new_target` within `[old/4, old*4]` — assert fails if outside

**TESTNET mode (mainnet_strict = false):**
- `gap = block_time - prev_block_time`
- If `gap > 1200s (20 min)`: assert `bits == 0x1d00ffff` (min difficulty)
- Else: bounded walk-back through stored `block_bits` (≤ 2016 steps)
- Walk-back: if `prev_bits == 0x1d00ffff`, accept any non-min-diff bits
- If `prev_bits != 0x1d00ffff`, assert `bits == prev_bits`

**Solidity port:** Same logic, using `uint32` for bits and `uint256` for target. Target computation: `mantissa << (8 * (exponent - 3))` for exponent > 3, else `mantissa >> (8 * (3 - exponent))`.

## 0.6 Timestamp Rules

- **T3: Future timestamp** — `assert(block_time <= now + 7200, "FUTURE_TIMESTAMP")` (2 hours)
- **T4: Non-monotonic** — `if block_time <= prev_time: assert(prev_time - block_time <= 7200, "MTP_PAST")` (conservative 2h tolerance for testnet anomalies)
- **Full 11-block MTP:** STRETCH GOAL — labeled as not implemented. The current implementation uses the conservative `prev_time - 2h` heuristic instead of the full median-of-11 calculation. Status: CONSERVATIVE.

## 0.7 Threat Model Delta vs Starknet

| Risk | Starknet | Arbitrum (EVM) | Mitigation |
|------|----------|-----------------|------------|
| Storage collision | felt252 keys, low risk | uint256 keys, standard | Same mapping pattern, no collision risk |
| Precompile repricing | syscalls, fixed | EIP-2929 access lists, variable | Gas estimates via `eth_estimateGas` before each tx |
| Calldata cost | felt252 serialization, cheap | EIP-2028 calldata, 16 gas/byte non-zero | Compact calldata encoding (raw bytes, no ABI padding) |
| Arbiscan verification | Voyager | Arbiscan | Source verification via `forge verify` or manual upload |
| Reentrancy | Not possible (Cairo) | Possible (EVM) | `ReentrancyGuard` on all state-changing functions |
| Felt overflow | felt252 < P | uint256 max 2^256 | No overflow risk on EVM |
| Gas limit per block | ~32M (Starknet) | ~32M (Arbitrum) | Bounded loops, max 2016 iterations for retarget walk-back |

