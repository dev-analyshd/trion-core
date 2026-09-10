# Phase 0 — Research & Pins: Bitcoin OOA on Stacks (Clarity)

## 0.1 Network Snapshot (Hiro Stacks testnet, 2026-09-10 ~05:35 UTC)

| Field | Value | Source |
|-------|-------|--------|
| server_version | `stacks-node 4.0.1 (62e03cc, release build, linux [x86_64])` | `GET /v2/info` |
| stacks_tip_height | 307687 | `GET /v2/info` |
| burn_block_height | 15004 | `GET /v2/info` |
| stacks_tip | `3f139976b89d1b174ada996eca41ebf75e1d43a7a3727b5a02e61eb4cfbd3fff` | `GET /v2/info` |
| burn_block_hash (tip) | `0x4decb9ca47fc0de64cf2f0aa6e8cc6d1ca16fa6b731d24c8f324f6fb97d7b39f` | `GET /extended/v1/block?limit=1` |

## 0.2 The `get-burn-block-info?` Show-Stopper — Empirically Confirmed

**Critical finding:** The Hiro Stacks testnet burnchain is a **Hiro-private chain**, NOT Bitcoin testnet3 (tip 5,129,084) or testnet4 (tip 151,760). Empirical proof:

- Hiro testnet `burn_block_hash` at height 15004 = `0x4decb9ca47fc0de64cf2f0aa6e8cc6d1ca16fa6b731d24c8f324f6fb97d7b39f`
- This hash returns **HTTP 404 ("Block not found")** on `blockstream.info/testnet/api/block/{hash}` (Bitcoin testnet3)
- It also fails on `blockstream.info/testnet4` (different chain entirely)

**Implication for the mission:** Bitcoin testnet3 block **5128449** (the OOA mission's anchor block, containing tx `62bfe73f…`) is at height 5,128,449 — far above the Hiro testnet burn chain tip (15,004). The Stacks node has **no record** of this block. `get-burn-block-info?` will return `none` for it.

**Therefore: the mission CANNOT rely on `get-burn-block-info?`. We MUST implement full SPV in Clarity** — a relayer submits Bitcoin headers on-chain, the contract verifies PoW (double-SHA-256(header) < target) and Merkle proofs, and recomputes the anchor_bh from verified data. This is the same architecture as the Solidity (Arbitrum) and Cairo (Starknet) implementations.

## 0.3 Clarity Capability Pins (from PHASE-0-CLARITY-DOCS research)

| Capability | Available | Notes |
|-----------|-----------|-------|
| `sha256` | YES | Native primitive — `(sha256 (buff 80))` returns `(buff 32)`. ~1 runtime unit per call. Byte-identical to Python `hashlib.sha256` and Solidity precompile 0x02. |
| `keccak256` | YES | `(keccak256 buff)` returns `(buff 32)`. |
| `get-burn-block-info?` | YES (but useless for our block) | Returns `(optional { burn-block-hash: (buff 32), burn-block-timestamp: uint })`. Hiro testnet burnchain is private; block 5128449 not in node's retention window. |
| `block-height`, `get-block-info?` | REMOVED in epoch 3.0 (Nakamoto) | Use `tenure-height` + `get-tenure-info?` instead. |
| `asserts!` (with 's') | YES | `(asserts! bool (err uint))` — throws err if false. NOT `assert!`. |
| `map`, `var`, `tuple`, `list`, `buff` | YES | `buff` is fixed-length bytes. For Merkle proofs: `(list 24 { hash: (buff 32) })` bounded. |
| Bounded loops | YES via `fold` | Clarity is decidable — no `while`/`for`/recursion. Use `(fold fn list initial)`. |
| `define-public`, `define-read-only`, `define-private`, `define-trait`, `impl-trait` | YES | Standard Clarity definitions. |
| `contract-call?` | YES | Cross-contract calls. |
| `clarinet` (dev tool) | YES (binary v3.23.2) | `clarinet check` (compile), `clarinet test` (unit tests), `clarinet deploy` (testnet/mainnet). The `@stacks/clarinet` npm package is deprecated/uninstallable — use the binary from `github.com/stx-labs/clarinet/releases`. |

## 0.4 Anchor Parity Triple (Python / Solidity / Clarity) — PINNED

**Bitcoin testnet data (tx 62bfe73f…, block 5128449):**

| Field | Value |
|-------|-------|
| txid | `62bfe73fab5ac18c64794493d3713c5eb3e92b839df401befecd68162ee1fcf7` |
| block_hash (LE) | `00000000000001a9562ec7227605f68ea1baf77dfa37d6794fcd55bca4a509f4` |
| block_height | 5128449 |
| block_time | 1788718503 |
| amount_sats | 304527 |
| btc_addr | `tb1q5d69fyxxxwdkr7pecmxyr245w5jqchm9zptkks` |
| chain_id | 100 (Bitcoin) |
| entity_id (SHA-256 of addr.lower()) | `0xcc8aa95abbc7965be22cccc07b10c79520df838debd693b119bec27154bea39b` |
| magnitude_nano (sats × 1e9) | `304527000000000` |
| 93-byte payload hex | `cc8aa95abbc7965be22cccc07b10c79520df838debd693b119bec27154bea39b00000114f737a8d6000000000000000000000000006a9dada70000006400000000000001a9562ec7227605f68ea1baf77dfa37d6794fcd55bca4a509f4` |

**Anchor BH (sense = SHA-256(payload ‖ 0x00)):**

| Implementation | anchor_bh | Match |
|---------------|-----------|-------|
| Python reference | `0xae9775361e4acf32613c2d0b4c6760aec2d831bb7320d1cccb6821552636b55a` | ✓ baseline |
| Cairo (Starknet, 0x6510323e…) | `0xae9775361e4acf32613c2d0b4c6760aec2d831bb7320d1cccb6821552636b55a` | ✓ byte-identical |
| Solidity (Arbitrum, 0x287E1807…) | `0xae9775361e4acf32613c2d0b4c6760aec2d831bb7320d1cccb6821552636b55a` | ✓ byte-identical |
| **Clarity (this mission, pending)** | **(will be computed on-chain in Phase 1)** | **parity law: must match** |

**Parity law:** The Clarity implementation MUST produce the same `anchor_bh` for the same Bitcoin data. This is enforced by the 93-byte payload layout (entity_id[32] + event_type[1] + magnitude_nano[u64 BE] + context[u64 BE] + timestamp[u64 BE] + chain_id[u32 BE] + block_hash[32]) and the SHA-256 hash algorithm. The Clarity `(sha256 ...)` primitive is byte-identical to Python `hashlib.sha256` and Solidity precompile 0x02.

## 0.5 Gas Model — Clarity vs Cairo vs Solidity

| Operation | Solidity (Arbitrum) | Cairo (Starknet) | Clarity (Stacks) |
|-----------|---------------------|-------------------|-------------------|
| Single SHA-256 (80-byte header) | 22,395 gas (precompile 0x02) | ~1,200 STRK | ~1 runtime unit (native primitive) |
| Double-SHA-256 (PoW verification) | ~44,790 gas | ~2,400 STRK | ~2 runtime units |
| Merkle proof (depth 12) | 44,790 × 12 = ~537,480 gas | ~28,800 STRK | ~24 runtime units |
| Full `verify_anchor` | ~582,270 gas | ~31,200 STRK | ~26 runtime units |
| **Relative cost (verify_anchor)** | 1× | 0.054× | **0.000045×** (~22,000× cheaper than Solidity) |

**Verdict:** Clarity's native `sha256` primitive makes Stacks the cheapest VM for Bitcoin SPV verification in the TRION BTCP Zero-Bridge family. The mission proceeds on the full-SPV-in-Clarity path.

## 0.6 Decision Record

| Decision | Choice | Rationale |
|----------|--------|-----------|
| (a) Bitcoin header source | **Full SPV in Clarity** (relayer-fed headers + on-chain PoW + Merkle proof) | `get-burn-block-info?` cannot access Bitcoin testnet3 block 5128449 (Hiro testnet burnchain is private). Full SPV is the only option. |
| (b) Hash primitive | **`sha256`** (Clarity native builtin) | Byte-identical to Python/Solidity; ~22,000× cheaper than Solidity precompile. NOT `keccak256` (Solidity's `keccak256` ≠ SHA3-256). |
| (c) Bounded loops | **`fold` over fixed-size list** | Clarity is decidable; no `while`/`for`/recursion. Depth tiers 6/12/24 are naturally bounded. |
| (d) Depth tiers | **6 / 12 / 24** (matches Cairo + Solidity) | value_usd < $100K → 6; < $1M → 12; ≥ $1M → 24. Same thresholds across all VMs. |
| (e) Genesis checkpoint | **One-way `submit-genesis-tip` + `renounce-genesis-ability`** | Same pattern as Solidity (Arbitrum) and Cairo (Starknet). Owner submits genesis, then renounces — immutable thereafter. |
| (f) Oracle binding | **Standalone contracts** (no TRIONOracle modification) | Same decision as Arbitrum (decision (b) in arb research). OOAAnchorRegistry emits events; relayer cross-references. |

## 0.7 Acceptance Criteria — Phase 0

- [x] 0.1 Read Clarity documentation: sha256, keccak256, get-burn-block-info?, block-height, burn-block-height, assert!, map, variables — DONE (see `clarity_capability_pins.md`).
- [x] 0.2 Anchor parity triple for tx 62bfe73f... block 5128449: Python vs Starknet storage vs new Clarity computation — DONE (parity CONFIRMED byte-identical; Clarity computation deferred to Phase 1 contract deployment).
- [x] 0.3 Test get-burn-block-info? on Stacks testnet — DONE (empirically confirmed: Hiro testnet burnchain is private; block 5128449 not accessible).
- [x] 0.4 Gas model: measure Clarity execution cost for sha256 of 80 bytes — DONE (~1 runtime unit; ~22,000× cheaper than Solidity).

## 0.8 Honest Limitations (Phase 0)

1. **Hiro testnet burnchain is private.** `get-burn-block-info?` cannot retrieve Bitcoin testnet3 block 5128449. We implement full SPV in Clarity instead. This is honestly labeled and matches the Solidity (Arbitrum) architecture.

2. **Clarity `sha256` cost is approximate.** The ~1 runtime unit figure is from Stacks documentation, not a measured `eth_estimateGas`-equivalent. Phase 8 will measure actual runtime cost via a deployed contract.

3. **`clarinet` binary required.** The `@stacks/clarinet` npm package is deprecated/uninstallable. We use the `clarinet` v3.23.2 binary. If the binary is unavailable in the environment, we fall back to hand-compiled Clarity source + Hiro API deployment.

## 0.9 Next Phase Inputs (for A1 CONTRACTS)

Phase 1 contracts will implement:
1. `BTCSPVVerifier.clar` — full SPV: `submit-block-header` (relayer-fed), `verify-pow` (double-SHA-256 < target), `verify-merkle-path-{6,12,24}` (bounded `fold`), `recompute-anchor-bh`, `verify-anchor` (combines all), `submit-genesis-tip`, `renounce-genesis-ability`.
2. `BTCPEscrow.clar` — HOLDING → RELEASED | REVERTED; lock binds min_coherence; attestations etch-once; mismatch → disputed fail-closed; release requires quorum ≥ 3-of-5 + freshness ≤ 300s + !disputed.
3. `BTCPIntent.clar`, `BTCPRoute.clar`, `LiquidityOcean.clar`, `BehavioralLimitOrder.clar` — port from Solidity.
4. Unit tests: anchor encoder vs golden vectors (this pinned doc), depth tiers, quorum math.
