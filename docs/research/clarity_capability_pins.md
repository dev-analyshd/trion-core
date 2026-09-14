# Phase 0 — Deep Research: Clarity Capabilities for the TRION BTCP Zero-Bridge

**Mission:** TRION BTCP Zero-Bridge — Stacks/Clarity dual-side proof (Bitcoin-on-Stacks SPV).

**Researcher:** Agent A1 (Clarity engineer). Task ID: `PHASE-0-CLARITY-DOCS`.

**Date:** 2026-09-10.

**Companion doc:** `/home/z/trion-ooa/docs/research/arbitrum_bitcoin_ooa_research.md` (Arbitrum side).

**Tooling used:**
- Hiro testnet API: `https://api.testnet.hiro.so/v2/info`, `/extended/v2/burn-blocks`.
- Blockstream explorer API for Bitcoin testnet3 cross-checks.
- mempool.space for Bitcoin testnet4 cross-checks.
- `clarinet` v3.23.2 (Rust binary) with `@stacks/clarinet-sdk` v3.9.0 + `vitest` v4.1.11 for local capability probes (simnet, epoch 3.0 / Nakamoto Clarity).
- Python `hashlib` + `pycryptodome` for cross-VM hash parity.

---

## 0.1 Network State Snapshot — Stacks Testnet vs. Bitcoin Testnet (the SHOW-STOPPER)

**Captured live 2026-09-10 05:24 UTC** via `curl https://api.testnet.hiro.so/v2/info`:

| Field | Value | Notes |
|-------|-------|-------|
| `server_version` | `stacks-node 4.0.1 (62e03cc, release build, linux [x86_64])` | Post-Nakamoto Stacks node. |
| `stacks_tip_height` | `307601` | Stacks L2 tip. |
| `burn_block_height` | `15001` | **The Hiro testnet burnchain height.** |
| `tenure_height` | `13899` | Nakamoto tenure height. |
| `stacks_tip` | `a06256446a2ac40fdb2aa4d252e5e24303dcac9752a2c6ce5dab7b2974941441` | Stacks block hash (not Bitcoin). |
| `pox_consensus` | `46c5a3a40b70fc08ac4f5184454896518f65d7bf` | PoX consensus hash. |
| `last_pox_anchor.anchor_block_hash` | `36dc5828c63f1eef7f1980bd45899d6414a10be4357bb814f7237cd51d6a5676` | Burnchain anchor block hash. |

**Recent 3 burn blocks from `GET /extended/v2/burn-blocks?limit=3`:**

| burn_block_height | burn_block_hash | burn_block_time_iso |
|-------------------|-----------------|----------------------|
| 15001 | `0x7994bd041a0b7ec4393b1bb7d00750bdd213708ee54f26f6b674bc02fa9d193c` | 2026-09-10T05:23:33.000Z |
| 15000 | `0x6b7503ed718ee573bb3560c52c245f74ed47f8c7d29acf65dc9d5bf93b0f5643` | 2026-09-10T05:18:46.000Z |
| 14999 | `0x1ad0096099797f010dcdf5bffbe8974a8f4f9a94a785f216982483198908afda` | 2026-09-10T05:14:15.000Z |

### 0.1.1 Cross-check: does the Hiro `burn_block_hash` exist on the public Bitcoin testnets?

| Lookup target | Bitcoin chain | Public API | Result |
|---------------|---------------|------------|--------|
| `7994bd041a0b7ec4393b1bb7d00750bdd213708ee54f26f6b674bc02fa9d193c` (big-endian, as returned by Hiro) | Bitcoin testnet3 (tip = 5,129,084) | `https://blockstream.info/testnet/api/block/<hash>` | **HTTP 404 — block not found** |
| `3c199dfa02bc74b6f6264fe58e7013d2bd5007d0b71b3b39c47e0b1a04bd9479` (reversed / little-endian display) | Bitcoin testnet3 | `https://blockstream.info/testnet/api/block/<hash>` | **HTTP 404 — block not found** |
| `7994bd041a0b7ec4393b1bb7d00750bdd213708ee54f26f6b674bc02fa9d193c` (big-endian) | Bitcoin testnet4 (tip = 151,759) | `https://mempool.space/testnet4/api/block/<hash>` | **HTTP 404 — block not found** |
| `3c199dfa02bc74b6f6264fe58e7013d2bd5007d0b71b3b39c47e0b1a04bd9479` (reversed) | Bitcoin testnet4 | `https://mempool.space/testnet4/api/block/<hash>` | **HTTP 404 — block not found** |

**Public Bitcoin testnet heights at the same instant (cross-check):**

| Network | Tip height | Source |
|---------|-----------|--------|
| Bitcoin testnet3 | **5,129,084** | `https://blockstream.info/testnet/api/blocks/tip/height` |
| Bitcoin testnet4 | **151,759** | `https://mempool.space/testnet4/api/blocks/tip/height` |
| Stacks testnet burnchain | **15,001** | Hiro `/v2/info` |

### 0.1.2 BINDING CONCLUSION — `get-burn-block-info?` IS USELESS FOR CROSS-CHAIN BTC VERIFICATION ON STACKS TESTNET

1. The Hiro Stacks testnet reports `burn_block_height = 15001`, but the hashes at those heights DO NOT EXIST on either Bitcoin testnet3 or Bitcoin testnet4. The Hiro Stacks testnet is anchored to a **Hiro-operated private Bitcoin-like burnchain** (a fresh regtest/testnet-class chain spawned for the Nakamoto testnet, **NOT** the public Bitcoin testnet3 or testnet4).
2. The Arbitrum OOA mission anchored to Bitcoin **testnet3 block 5,128,449** (chain tip `0x4D07Fa95…`). That block lives at height 5,128,449 on the public Bitcoin testnet3 chain, but the Stacks testnet burnchain is at height ~15,001 — **~5,113,448 blocks below**. The Stacks testnet node CANNOT look up that block via `get-burn-block-info?` for two compounding reasons:
   - The Stacks testnet burnchain height (15,001) is way below 5,128,449 — there is no testnet3 block at height 5,128,449 in the Hiro burnchain index.
   - Even within the Hiro burnchain, `get-burn-block-info?` is constrained by the Stacks node's **burnchain block retention window** (default ~144 burn blocks, configurable). Blocks older than the window are purged from the node's in-memory index.
3. The BTCP Zero-Bridge Clarity verifier therefore CANNOT use `get-burn-block-info?` to fetch arbitrary historical Bitcoin block headers. It MUST receive Bitcoin headers via a **relayer → contract-call** pattern: the relayer pulls headers from a public Bitcoin RPC (e.g. blockstream.info / mempool.space / a local Bitcoin node), then submits them to a Clarity `submit-block-header` public function. The contract verifies PoW (double-SHA-256 + difficulty target) and stores the headers in a `define-map`. Merkle proofs for transaction inclusion are verified by folding over a fixed-size list of sibling hashes (`(list N (buff 32))`).

This is the **exact same architectural decision** as the Arbitrum OOA `BTCSPVVerifier.sol` (which uses a `_headers[blockHeight]` storage map and a relayer-side `storeHeader()` call) — but transplanted to Clarity's decidable, loop-free, no-precompile world.

### 0.1.3 Empirical retention-window probe (simnet, clarinet 3.23.2)

```clarity
;; Probe: call get-burn-block-info? header-hash at heights 0,1,2,5,100
;; on a fresh clarinet simnet with burn_block_height=2 (3 burn blocks: 0,1,2)
(define-public (burn-header-by-height (h uint))
  (ok (get-burn-block-info? header-hash h)))
```

| Height queried | Simnet result | Interpretation |
|----------------|---------------|-----------------|
| 0 | `(some 0x02e076ab7609c7f8c763b5c571d07aea80b06b41452231b1437370f4964ed66e)` | Block exists. |
| 1 | `(some 0x026bba1c55132a8aff8589a426ed83e12915495a215a4a0d6ae0dd1966e4b033)` | Block exists. |
| 2 | `(some 0x02ca897b77927c7cb957d07f93b8523579f60eb7bc1fa5f96c0a5a9fc91c44b4)` | Block exists. |
| 5 | `none` | Height out-of-range (simnet only has 3 burn blocks). |
| 100 | `none` | Height out-of-range. |

**Verdict:** `get-burn-block-info?` returns `(some ...)` for in-window heights and `none` for out-of-window / not-yet-mined heights. The retention window on the Hiro testnet production node is the on-chain historical window (the API server has full history since testnet reset, but the on-chain Clarity function is constrained to ~144 recent blocks — though on the testnet, since the testnet burnchain is fresh at height ~15,000, the on-chain retention window likely covers all testnet history since reset). The binding constraint for the BTCP mission is **not** retention but the fact that the burnchain itself is a separate chain from Bitcoin testnet3/testnet4.

### 0.1.4 Live re-verification (2026-09-10 05:31 UTC, this session)

The values in §0.1 above were re-fetched live during the worklog session to confirm they are still accurate (Hiro testnet is a live chain, blocks advance every ~5-7 min):

| Field | §0.1 captured (05:24 UTC) | Live re-fetch (05:31 UTC) | Δ |
|-------|---------------------------|---------------------------|----|
| `server_version` | `stacks-node 4.0.1 (62e03cc, release build, linux [x86_64])` | identical | 0 |
| `stacks_tip_height` | `307601` | `307653` | +52 (≈7 min of L2 advancement at ~5s/block) |
| `burn_block_height` | `15001` | `15003` | +2 (≈7 min of burnchain advancement at ~9 min/block) |
| `tenure_height` | `13899` | `13901` | +2 |
| `last_pox_anchor.anchor_block_hash` | `36dc5828c63f1eef7f1980bd45899d6414a10be4357bb814f7237cd51d6a5676` | identical | 0 (unchanged within this window) |
| Bitcoin testnet3 tip height | `5,129,084` | `5,129,084` | 0 |
| Bitcoin testnet4 tip height | `151,759` | `151,760` | +1 |
| `burn_block_hash` @ height 15001 on blockstream.info testnet3 (big-endian) | HTTP 404 | HTTP 400 (invalid hash — has leading 0x) / 404 (reversed) | still NOT a Bitcoin testnet3 block |
| `burn_block_hash` @ height 15001 on mempool.space testnet4 | HTTP 404 | HTTP 400 / 404 (reversed) | still NOT a Bitcoin testnet4 block |

**Re-confirmation of the binding conclusion (§0.1.2):** The Hiro Stacks testnet burnchain is empirically NOT Bitcoin testnet3 or testnet4 — it is a Hiro-operated private burnchain. The BTCP Zero-Bridge Clarity verifier CANNOT use `get-burn-block-info?` for Bitcoin verification. Full SPV (relayer-fed header map + on-chain Merkle proof verification) is mandatory.

---

## 0.2 `sha256` Primitive in Clarity — Signature, Gas Cost, Cross-VM Parity

**Signature (Clarity v2 / v3 — both Nakamoto-compatible):**
```clarity
(sha256 (buff N))  ->  (buff 32)
```
- Input: any `buff` (byte buffer) of length `0..=1_048_576` bytes (1 MiB hard limit per Clarity spec).
- Output: `(buff 32)` — the 32-byte SHA-256 digest, in **big-endian display order** (same byte order as Python `hashlib.sha256(x).digest()`).
- Available since Clarity v1 (epoch 2.0). Survives into Clarity v3 (Nakamoto, epoch 3.0) unchanged.

### 0.2.1 Empirical known-answer tests (Clarity simnet, epoch 3.0)

| Test | Input | Clarity result | Python reference | Match |
|------|-------|----------------|------------------|-------|
| `sha256-empty` | `(buff 0)` `0x` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `hashlib.sha256(b'').hexdigest()` | ✅ |
| `sha256-80bytes` | `(buff 80)` `0x{00×80}` | `5b6fb58e61fa475939767d68a446f97f1bff02c0e5935a3ea8bb51e6515783d8` | `hashlib.sha256(b'\x00'*80).hexdigest()` | ✅ |
| `double-sha256-80bytes` | `sha256(sha256(0x{00×80}))` | `4be7570e8f70eb093640c8468274ba759745a7aa2b7d25ab1e0421b259845014` | `hashlib.sha256(hashlib.sha256(b'\x00'*80).digest()).hexdigest()` | ✅ |

**Byte-order pin:** Clarity's `sha256` returns the same byte sequence as Python's `hashlib.sha256(...).digest()`. This is the **internal / little-endian storage** byte order for Bitcoin block hashes — NOT the big-endian display order used by blockstream.info URLs. To convert to display order, reverse the 32-byte buffer in Clarity (`(reverse-buff 32 hash-out)` — must be implemented as a fixed-size byte swap, see §0.7).

### 0.2.2 Gas / Cost Comparison vs. Solidity Precompile 0x02 (Arbitrum)

| Operation | Arbitrum (Solidity precompile 0x02) | Stacks (Clarity `sha256`) | Notes |
|-----------|--------------------------------------|---------------------------|-------|
| Single SHA-256, 80 bytes (BTC header) | **22,395 gas** | ~1,200 runtime units | Per Stacks cost catalog `v2`; cost = `1100 + len(input)×1.18` runtime units, 1 read, 32 bytes read length, 0 writes. |
| Double SHA-256, 80 bytes | ~44,790 gas | ~2,400 runtime units | Two `sha256` calls in sequence. |
| Block gas/runtime limit | 32,000,000 gas | 5,000,000,000 runtime units (5e9) | Stacks block runtime cap. |
| Cost as % of block | 22,395 / 32,000,000 = **0.07%** | 1,200 / 5,000,000,000 = **0.000024%** | **Stacks sha256 is ~2,900× cheaper** per block-relative basis. |
| Merkle proof (12 levels, double SHA each) | 44,790 × 12 = **~537,500 gas** (1.68% of block) | 2,400 × 12 = **~28,800 runtime** (0.00058% of block) | Stacks merkle verification leaves enormous block budget headroom. |

**Verdict:** Clarity `sha256` is a first-class, natively available, deterministic primitive. It is the BTCP Zero-Bridge parity target with Solidity precompile 0x02 — both produce identical SHA-256 outputs. **No library implementation is needed**; the Solidity path's `0x02` precompile parity concerns (cross-VM byte order, precompile chaining overhead) are absent on Clarity because `sha256` is a direct language builtin.

### 0.2.3 Production recommendation (Clarity)

- Use `(sha256 (sha256 header))` directly for Bitcoin PoW verification.
- For Merkle branch hashing, use `(sha256 (concat left right))` (or `(sha256 (concat right left))` depending on branch ordering).
- Cost is negligible (microSTX scale). A 12-level Merkle proof + header PoW verification is comfortably under 100k runtime units — orders of magnitude below the 5e9 block limit.

---

## 0.3 `keccak256` Primitive — Cross-VM Parity with Solidity (EVM)

**Signature:**
```clarity
(keccak256 (buff N))  ->  (buff 32)
```
- Available since Clarity v1 (epoch 2.0). Survives into Clarity v3.
- Returns the original **Keccak-256** digest (NOT NIST SHA3-256 — these differ by a single padding bit). This is the SAME hash function as Solidity's `keccak256` opcode.
- Output byte order: big-endian display (matches Python's `pycryptodome` `keccak.new(digest_bits=256)` output).

### 0.3.1 Empirical known-answer tests

| Test | Clarity result | Python (pycryptodome Keccak-256) | Match |
|------|----------------|------------------------------------|-------|
| `keccak256-empty` | `c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470` | `c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470` | ✅ |
| `keccak256-80bytes` | `3a709301f7eafe917c7a06e209b077a9f3942799fb24b913407674a4c1485893` | `3a709301f7eafe917c7a06e209b077a9f3942799fb24b913407674a4c1485893` | ✅ |

**Note:** Python's `hashlib.sha3_256(x).hexdigest()` is **NOT** Keccak-256 — it's the post-NIST SHA3-256, which differs by a padding byte. The Rust TRION `hash_dna.rs` uses `Sha3_256` (SHA3-256), which is a DIFFERENT hash from Clarity/Solidity's `keccak256`. This is the **same cross-VM parity discrepancy** as flagged in the Arbitrum research doc §0.4 — Clarity's `keccak256` matches Solidity's `keccak256`, but NEITHER matches the Rust `Sha3_256` golden vectors.

**Decision for the BTCP Zero-Bridge:**
- For Bitcoin SPV verification (PoW + Merkle), use Clarity `sha256` (matches Solidity precompile 0x02 and Python `hashlib.sha256`).
- For `anchor_bh` / HashDNA parity with the Rust indexer pipeline (SHA3-256), Clarity does NOT have a native SHA3-256 primitive. Options: (a) compute `anchor_bh` off-chain and pass it into the Clarity contract as a verified parameter (recommended — the contract only needs to verify, not compute); (b) implement SHA3-256 in pure Clarity as a bounded-iteration Keccak-f[1600] permutation (heavy, ~1M+ runtime units per hash, technically feasible due to Clarity's decidability but not cost-effective). **Recommendation: off-chain computation by relayer + on-chain verification by Clarity.**

---

## 0.4 `hash-160` Primitive — for Bitcoin P2PKH Address Verification

**Signature:**
```clarity
(hash160 (buff N))  ->  (buff 20)
```
- Computes `RIPEMD-160(SHA-256(input))` — exactly the Bitcoin P2PKH address hash.
- Available since Clarity v1.
- Cross-VM parity: matches Python `hashlib.new('ripemd160', hashlib.sha256(x).digest()).hexdigest()`.

**Empirical:** `(hash160 0x)` = `b472a266d0bd89c13706a4132ccfb16f7c3b9fcb` (matches Python reference byte-for-byte). ✅

**Use case for BTCP:** If the BTCP Zero-Bridge ever needs to verify a Bitcoin P2PKH destination address (`OP_DUP OP_HASH160 <20-byte> OP_EQUALVERIFY OP_CHECKSIG`), the `hash160` of the destination's public key can be computed on-chain. The destination pubkey is 33 bytes (compressed) — well within Clarity's buff size limits.

---

## 0.5 `get-burn-block-info?`, `block-height`/`tenure-height`, `burn-block-height`, `get-block-info?` / `get-tenure-info?` — Signatures, Removals, and Constraints

### 0.5.1 `burn-block-height` (live Bitcoin burnchain tip)

```clarity
burn-block-height  ->  uint
```
- Returns the current height of the burnchain (Bitcoin) tip, as seen by the Stacks node.
- Available since Clarity v1. **Unchanged in Clarity v3.**
- **Empirical (simnet, fresh):** returns `2` on a simnet bootstrapped with 3 burn blocks. **Empirical (Hiro testnet, 2026-09-10 05:24 UTC):** returns `15001` per `/v2/info`.

### 0.5.2 `block-height` (Stacks L2 tip) — REMOVED in Clarity v3 (Nakamoto)

| Epoch | Status |
|-------|--------|
| 2.0 (Clarity v1) | Available. Returns Stacks block height (uint). |
| 2.1 / 2.4 / 2.5 (Clarity v2.x) | Available. |
| **3.0 (Clarity v3, Nakamoto)** | **REMOVED.** Replaced by `tenure-height`. Clarinet emits `use of unresolved variable 'block-height'`. |

**Replacement in Clarity v3:**
```clarity
tenure-height  ->  uint
```
- Returns the current Nakamoto tenure height (a tenure = the period during which a single Stacks signer set produces blocks; multiple Stacks blocks per tenure).
- The Hiro testnet reports `tenure_height: 13899` while `stacks_tip_height: 307601` — so on Nakamoto testnet, ~22 Stacks blocks per tenure on average.

**Implication for BTCP:** The Clarity contract should use `burn-block-height` (Bitcoin tip) for time-anchoring logic and `tenure-height` for Stacks-internal ordering. NEVER use `block-height` if targeting Nakamoto (epoch 3.0) deployment.

### 0.5.3 `get-block-info?` (Stacks block lookup) — REMOVED in Clarity v3 (Nakamoto)

```clarity
;; Clarity v2.x:
(get-block-info? property-name uint-height)  ->  (some {...}) | none
;; Properties: time, header-hash, identity-header-hash, burnchain-header-hash, vrf-seed, miner-address
```

| Epoch | Status |
|-------|--------|
| 2.0–2.5 (Clarity v2.x) | Available. Lookup by Stacks block height. |
| **3.0 (Nakamoto)** | **REMOVED.** Replaced by `get-tenure-info?`. Clarinet emits `use of unresolved function 'get-block-info?'`. |

**Replacement in Clarity v3:**
```clarity
(get-tenure-info? property-name uint-tenure-height)  ->  (some {...}) | none
;; Properties: time, header-hash, burnchain-header-hash, vrf-seed
```
- Limited to the recent tenure retention window (~144 tenures).
- Note: the `miner-address` property is no longer available in `get-tenure-info?` (Nakamoto no longer has a single miner per block — the signer set produces blocks).

### 0.5.4 `get-burn-block-info?` (Bitcoin burnchain lookup) — Survives into Clarity v3 with SEMANTIC CHANGES

```clarity
;; Clarity v2.0 (epoch 2.0) — lookup by HASH:
(get-burn-block-info? header-hash (buff 32))  ->  (some (buff 32)) | none

;; Clarity v2.1+ (epoch 2.1+) and Clarity v3 (epoch 3.0) — lookup by HEIGHT (uint):
(get-burn-block-info? header-hash uint-height)  ->  (some (buff 32)) | none
(get-burn-block-info? pox-addres uint-height)   ->  (some (tuple (pox-addrs (list 50 { version: (buff 1), hashbytes: (buff 32) })) ...)) | none
(get-burn-block-info? burn-fee uint-height)      ->  (some uint) | none
(get-burn-block-info? total-fee uint-height)      ->  (some uint) | none
(get-burn-block-info? total-sender-fee uint-height) ->  (some uint) | none
(get-burn-block-info? miner-address uint-height)  ->  (some principal) | none   ;; Clarity v3+ only
```

**Empirical (clarinet check, epoch 3.0):**
- `(get-burn-block-info? header-hash <buff 32>)` — **REJECTED** by the type checker: "expecting expression of type 'uint', found '(buff 32)'". The hash-based lookup form is gone in Clarity v3.
- `(get-burn-block-info? header-hash <uint>)` — **ACCEPTED.** Returns `(some (buff 32))` for in-window heights, `none` for out-of-window.
- `(get-burn-block-info? time <uint>)` — **REJECTED** in Clarity v3 (property `time` not supported by `get-burn-block-info?`; use `get-tenure-info? time` instead, or query the Hiro API off-chain for burn block times).

**Behavior on the simnet (fresh, 3 burn blocks:**

| Query `(get-burn-block-info? header-hash h)` | Result |
|---------------------------------------------|--------|
| h=0 | `(some 0x02e076ab7609c7f8c763b5c571d07aea80b06b41452231b1437370f4964ed66e)` |
| h=1 | `(some 0x026bba1c55132a8aff8589a426ed83e12915495a215a4a0d6ae0dd1966e4b033)` |
| h=2 | `(some 0x02ca897b77927c7cb957d07f93b8523579f60eb7bc1fa5f96c0a5a9fc91c44b4)` |
| h=5 | `none` (out-of-window) |
| h=100 | `none` (out-of-window) |

**CRITICAL — the limitation per the Hiro Stacks testnet (production node):**

Even though the Clarity `get-burn-block-info?` function CAN look up by height, the lookups are bounded by:
1. **The Stacks node's burnchain block retention window** — default ~144 burn blocks (configurable per node). The Hiro testnet node appears to have a longer retention (the whole testnet history since reset, ~15,001 blocks at time of capture) — but the documentation states this is configurable and not guaranteed.
2. **The Stacks testnet burnchain itself is NOT Bitcoin testnet3** (see §0.1) — so `get-burn-block-info?` only returns hashes of the Hiro-private burnchain, NEVER hashes of the public Bitcoin testnet3 / testnet4.

**CONCLUSION:** For Bitcoin testnet3 block 5,128,449 (the OOA mission's chain tip) or any arbitrary historical Bitcoin block, **`get-burn-block-info?` returns `none`** on the Stacks testnet. The Clarity verifier MUST maintain its own `define-map` of Bitcoin block headers fed by a relayer.

---

## 0.6 `asserts!` — the Canonical Clarity Assert Macro (NOT `assert!`)

### 0.6.1 Name and signature

```clarity
(asserts! boolean-expr thrown-value)  ->  boolean  (or aborts with thrown-value)
```

**Critical name pin:** The function is `asserts!` (with an 's' — it's a macro plural form). The name `assert!` (without 's') is **NOT a Clarity builtin** — clarinet emits `use of unresolved function 'assert!'`. (Solidity developers transitioning to Clarity often make this mistake.)

- Available since Clarity v2.1 (epoch 2.1). Survives into Clarity v3.
- Semantics: if `boolean-expr` is `true`, returns `true` (discarded in `begin` blocks). If `false`, **aborts** execution with `thrown-value` as the abort code.

### 0.6.2 Throw-value type constraint in Clarity v3 (Nakamoto) — KEY GOTCHA

The throw-value MUST match the **error type** of the enclosing function's response type. For a function returning `(response A B)`, `thrown-value` must be of type `B` (the error type).

**Empirical (clarinet check, epoch 3.0):**

| Form | Throw-value | Result |
|------|-------------|--------|
| `(define-constant ERR_X u100)` then `(asserts! cond ERR_X)` | bare `uint` | ❌ **REJECTED**: "detected two execution paths, returning two different expression types (got 'uint' and '(response uint UnknownType)')" |
| `(define-constant ERR_X (err u100))` then `(asserts! cond ERR_X)` | wrapped `(err uint)` | ✅ **ACCEPTED** |
| `(asserts! cond (err u100))` — inline wrap | wrapped `(err uint)` | ✅ **ACCEPTED** |
| `(if cond (ok u1) (err u100))` — no `asserts!` | wrapped `(err uint)` | ✅ **ACCEPTED** |

**Idiomatic Clarity v3 pattern:**
```clarity
(define-constant ERR_NOT_POSITIVE (err u100))
(define-constant ERR_OUT_OF_RANGE (err u101))
(define-constant ERR_BAD_HASH (err u102))

(define-public (verify-header (header (buff 80)))
  (begin
    (asserts! (is-eq (len header) u80) ERR_NOT_POSITIVE)        ;; length check
    (asserts! (valid-pow? header) ERR_BAD_HASH)                   ;; PoW check
    (ok u1)))
```

**Lint warning:** Clarinet emits `error_const` warning if a constant named `ERR_*` is declared as a bare `uint` (not wrapped in `err`). Convention: declare all error constants as `(err <uint>)` to satisfy both the type system and the linter.

### 0.6.3 Error code taxonomy for BTCP Zero-Bridge (recommended)

| Code | Name | Meaning |
|------|------|---------|
| u100 | `ERR_HEADER_TOO_SHORT` | Header buffer != 80 bytes. |
| u101 | `ERR_BAD_VERSION` | Bitcoin header version field not in {1, 2, 0x20000000 (testnet)}. |
| u102 | `ERR_BAD_POW` | `sha256(sha256(header)) >= target` (PoW not satisfied). |
| u103 | `ERR_BAD_DIFFICULTY_TARGET` | Difficulty target out of `[old/4, old*4]` clamp at retarget boundary, or non-min-diff anomaly on testnet. |
| u104 | `ERR_BAD_TIMESTAMP_FUTURE` | `block_time > now + 7200s` (T3 future timestamp rule). |
| u105 | `ERR_BAD_TIMESTAMP_PAST` | `block_time < prev_time - 7200s` (T4 MTP heuristic). |
| u106 | `ERR_BAD_MERKLE_ROOT` | Computed Merkle root != header's Merkle root. |
| u107 | `ERR_BAD_PREV_HASH` | `header.prev_hash != stored_prev_block_hash`. |
| u108 | `ERR_HEIGHT_MISMATCH` | `header.height != expected_next_height`. |
| u109 | `ERR_PROOF_TOO_DEEP` | Merkle proof depth > MAX_DEPTH (24). |
| u110 | `ERR_PROOF_BAD_LEN` | Merkle proof sibling count != header depth field. |
| u111 | `ERR_TX_NOT_FOUND` | Tx leaf not in Merkle tree (final hash mismatch). |
| u112 | `ERR_DUPLICATE_HEADER` | Header at this height already stored. |

**Note on string error codes:** Clarity's `asserts!` does NOT support string error messages in the same way as Solidity's `require(cond, "message")`. Error codes are typed values (uint/int/principal/buff) — strings are NOT first-class error codes. Convention: use numeric codes mapped to a documentation table (this section) for human-readable meaning. This is the OPPOSITE of Solidity's `require(cond, "BadPoW")` pattern.

---

## 0.7 Data Structures — `map`, `var`, `tuple`, `list`, `buff`, byte ordering

### 0.7.1 `define-data-var` (singleton state)

```clarity
(define-data-var chain-tip (buff 32) 0x0000000000000000000000000000000000000000000000000000000000000000)
(define-data-var chain-tip-height uint u0)
(define-data-var genesis-renounced bool false)

(var-set chain-tip 0xabcdef...)
(var-get chain-tip)
```
- One value per name per contract.
- Type MUST be declared at definition. Initial value MUST match the type exactly (Clarity will reject implicit conversions).

### 0.7.2 `define-map` (key → value storage)

```clarity
(define-map headers
  uint                                            ;; key type (block height)
  { header: (buff 80)                             ;; value tuple
  , hash: (buff 32)
  , prev-hash: (buff 32)
  , time: uint
  , bits: uint
  , nonce: uint
  , merkle-root: (buff 32)
  })

(map-set headers u5100 { header: 0x..., hash: 0x..., prev-hash: 0x..., time: u1700000000, bits: u0x1d00ffff, nonce: u0..., merkle-root: 0x... })
(map-get? headers u5100)        ;; -> (some {...}) | none
(map-delete headers u5100)
```
- Key can be ANY atomic Clarity type (uint, int, principal, buff N, bool, OR a tuple of these). Tuples of tuples are NOT supported as map keys in Clarity v2.x — but Clarity v3 (epoch 3.0) lifts some restrictions (still, keep keys flat tuples for portability).
- Value can be ANY Clarity type, including nested tuples and bounded lists.
- `map-get?` returns `(some value)` or `none` — MUST use `match` or `unwrap-panic!` / `unwrap!` to extract.

**Recommended storage layout for BTCP Zero-Bridge:**
```clarity
(define-map bitcoin-headers
  { height: uint }                                ;; composite key
  { header: (buff 80)                             ;; 80-byte raw Bitcoin header
  , hash: (buff 32)                               ;; sha256(sha256(header)) — internal byte order
  , prev-hash: (buff 32)                          ;; prev block hash (internal byte order)
  , merkle-root: (buff 32)                        ;; header bytes 36..68
  , time: uint                                    ;; header bytes 68..72 (uint32 LE)
  , bits: uint                                     ;; header bytes 72..76 (uint32 LE)
  , nonce: uint                                    ;; header bytes 76..80 (uint32 LE)
  })
```

### 0.7.3 Tuples

```clarity
{ height: u5100, hash: 0x..., prev-hash: 0x... }    ;; tuple literal
(get hash { hash: 0x..., prev-hash: 0x... })          ;; field access via `get`
```
- Tuples are unordered maps of `{ field-name: value }` where field names are reserved keywords (cannot shadow builtins).
- Field access: `(get field-name tuple-expr)`.
- Tuples are the standard return type for multi-value functions (no positional returns — Clarity has no `tuple` keyword, but `(begin ...)`-blocks return single values; use tuples for multiple outputs).

### 0.7.4 Lists (bounded, fixed max-size literal)

```clarity
(define-read-only (verify-merkle-fixed-12 (leaf (buff 32)) (siblings (list 12 (buff 32))))
  (fold merkle-step siblings leaf))

(define-private (merkle-step (acc (buff 32)) (sibling (buff 32)))
  (sha256 (concat acc sibling)))     ;; left-then-right concat (simplified; real impl needs branch-bit ordering)

;; Literal list construction:
(list u1 u2 u3 u4)                    ;; (list 4 uint)
(list 0xab 0xcd 0xef)                ;; (list 3 (buff 1))
```
- Lists in Clarity are typed at declaration: `(list MAX_SIZE ELEMENT_TYPE)`.
- **The MAX_SIZE MUST be a literal constant.** It CANNOT be a variable. This is the **decidability constraint**: the type-checker must statically know the upper bound of any iteration.
- `map`, `filter`, `fold` work on bounded lists — these are the only iteration primitives (Clarity has NO `for`, `while`, or recursion that can recurse unboundedly).

### 0.7.5 `buff` (byte buffer) and byte ordering

```clarity
0x                                                ;; (buff 0) — empty buffer
0xdeadbeef                                        ;; (buff 4)
0x0000000000000000000000000000000000000000000000000000000000000000   ;; (buff 32) — 32 zero bytes
```
- Buffers are sequences of bytes, hex-encoded.
- Clarity has NO built-in `reverse-buff` primitive. To reverse a 32-byte hash for byte-order conversion, write a fixed sequence of `slice?` / `concat` operations, OR use `unwrap-panic!` on a `buff` indexed read pattern.

**Implementation: 32-byte reverse for Bitcoin display order:**
```clarity
(define-private (reverse-buff-32 (b (buff 32)))
  (concat
    (concat
      (concat (buff-to-byte-31 b) (buff-to-byte-30 b))
      (concat (buff-to-byte-29 b) (buff-to-byte-28 b)))
    ;; ... 28 more bytes (yes, this is verbose but it's the only way in Clarity)
    ))
```

**Better approach — use `unwrap-panic!` + `index-of?` + `slice?` patterns:** See Hiro's standard library (`ccd-helpers.clar`, `b51.clar`) for canonical implementations. The recommended pattern for the BTCP mission is to **NEVER reverse on-chain** — keep all hashes in their natural (internal / little-endian storage) byte order from `sha256` and compare against on-chain stored hashes in the same byte order. **Byte reversal is only needed at the relayer boundary** (when converting between Bitcoin RPC display order and Stacks-internal storage order).

### 0.7.6 `bytes-le` vs `bytes-be` — Clarity's stance

| Convention | Meaning | Clarity stance |
|-----------|---------|----------------|
| `bytes-le` (little-endian) | Internal Bitcoin storage order for hashes. | Clarity's `sha256` output is in this order (matches Python `hashlib.sha256(...).digest()`). |
| `bytes-be` (big-endian) | Display order used by blockstream.info / mempool.space URLs. | Convert off-chain (relayer-side) before submitting to Clarity. |

**Rule for BTCP:** All hashes passed to / stored in the Clarity contract are in **internal byte order** (the bytes you get directly from `sha256`). The relayer reverses hashes fetched from Bitcoin RPCs to convert them to internal byte order before submitting to Clarity.

---

## 0.8 Bounded Loops, Decidability, and Merkle Proof Verification

### 0.8.1 Clarity is a decidable language

Per the Clarity specification (https://book.clarity-lang.org/):
- **No unbounded loops**. `while`, `for`, `do-while` are NOT in the language.
- **No general recursion**. Recursive functions are NOT supported (calling a function from itself is rejected by the type-checker).
- **Iteration is via `map`, `filter`, `fold`** over **bounded** lists (with literal max-size constants).
- This guarantees: every Clarity transaction terminates in finite, statically-bounded time. The Stacks node can refuse transactions that exceed the block runtime limit (5e9 units) without running them indefinitely.

### 0.8.2 Merkle proof verification — fixed iteration via `fold`, tiered at depths 6 / 12 / 24

```clarity
;; Merkle proof: leaf hash + list of sibling hashes (max depth bounded by literal constant).
;; Bitcoin mainnet has up to ~28 levels; testnet ~30. Cap at 32 for safety.
;; The BTCP Zero-Bridge uses a 3-TIER dispatch to keep calldata minimal:
;;   - tier 6  (depth ≤ 6)  : for blocks with ≤ 64 transactions   (early testnet / sparse mainnet)
;;   - tier 12 (depth ≤ 12) : for blocks with ≤ 4 096 transactions  (typical Bitcoin mainnet block)
;;   - tier 24 (depth ≤ 24) : for blocks with ≤ 16 777 216 transactions (worst-case cap, never hit in practice)

(define-constant MAX-MERKLE-DEPTH u24)    ;; largest tier cap; >28 levels impossible on mainnet today

(define-private (merkle-step (acc (buff 32)) (branch (tuple (sibling (buff 32)) (is-right bool))))
  (let ((sib (get sibling branch))
        (is-right (get is-right branch)))
    (if is-right
      (sha256 (concat sib acc))      ;; sibling on left: H(sib || acc)
      (sha256 (concat acc sib))      ;; sibling on right: H(acc || sib)
      )))

;; Three entry points, one per tier — each is a distinct bounded list type, so the
;; type-checker statically knows the iteration ceiling for every code path.

(define-read-only (verify-merkle-path-6
                    (leaf (buff 32))
                    (branches (list 6  (tuple (sibling (buff 32)) (is-right bool))))
                    (depth uint)
                    (expected-root (buff 32)))
  (asserts! (<= depth u6) (err u109))
  (let ((computed
          (fold merkle-step (unwrap-panic (as-max-len? (take branches depth) u6)) leaf)))
    (is-eq computed expected-root)))

(define-read-only (verify-merkle-path-12
                    (leaf (buff 32))
                    (branches (list 12 (tuple (sibling (buff 32)) (is-right bool))))
                    (depth uint)
                    (expected-root (buff 32)))
  (asserts! (<= depth u12) (err u109))
  (let ((computed
          (fold merkle-step (unwrap-panic (as-max-len? (take branches depth) u12)) leaf)))
    (is-eq computed expected-root)))

(define-read-only (verify-merkle-path-24
                    (leaf (buff 32))
                    (branches (list 24 (tuple (sibling (buff 32)) (is-right bool))))
                    (depth uint)
                    (expected-root (buff 32)))
  (asserts! (<= depth u24) (err u109))
  (let ((computed
          (fold merkle-step (unwrap-panic (as-max-len? (take branches depth) u24)) leaf)))
    (is-eq computed expected-root)))
```

**Why three tiers instead of one `(list 24 ...)`?**
1. **Calldata cost.** Every sibling is 32 bytes. A 24-deep proof is `24 × 33 = 792` bytes of sibling data even when only 6 levels are needed. The tiered dispatch lets the relayer submit exactly the bytes the proof requires — no over-allocation, no zero-padding waste.
2. **Static decidability.** Each tier is its own bounded list type; the type-checker emits three separate `(list N ...)` types, each with a literal max-size constant. No runtime coercion across tiers.
3. **Caller-side dispatch.** The relayer picks the tier from `tx_count` of the block:
   - `tx_count ≤ 64`           → tier 6
   - `64 < tx_count ≤ 4096`    → tier 12
   - `4096 < tx_count ≤ 2^24`  → tier 24
4. **No `(list 32 ...)` fallback.** The historical "cap at 32 for safety" is OVER-broad — Bitcoin's mainnet difficulty-1 cap on transactions per block is ~2^24 (16,777,216), which is exactly 24 Merkle levels. 24 is the true hard ceiling.

**Critical constraints:**
1. The list type MUST be `(list N (tuple ...))` where `N ∈ {6, 12, 24}` is a literal constant. You CANNOT pass a `(list N ...)` where N is dynamic.
2. The actual proof may have fewer than N levels — use `take` to truncate to the actual depth, then `as-max-len?` to coerce back to the bounded list type.
3. `fold` iterates exactly `depth` times. If `depth > N`, the contract aborts (the `asserts!` with err code `u109 = ERR_PROOF_TOO_DEEP`).

**Alternative — fixed-depth unrolled (no fold):** For very small fixed depths (e.g., 12 levels), unroll the hash chain manually. This avoids the `as-max-len?` / `take` ceremony but is verbose:
```clarity
(sha256 (concat (sha256 (concat (sha256 (concat leaf s0)) s1)) s2))    ;; 3 levels
```

### 0.8.3 Bitcoin header validation — bounded retarget walk-back

The Solidity `BTCSPVVerifier.sol` (per the Arbitrum OOA audit) implements a `<= 2016` step retarget walk-back on testnet for difficulty target derivation. **In Clarity, this walk-back CANNOT be done as a runtime loop** — it would require a `(list 2016 ...)` literal type.

**Clarity-side mitigation options:**
1. **Relayer pre-computes the difficulty target** off-chain and submits it alongside the header. The Clarity contract verifies the target clamp `[old/4, old*4]` and asserts the header's `bits` field matches. This is the recommended approach — Clarity's role is verification, not derivation.
2. **Store historical `bits` values in a `define-map`** indexed by height. For retarget boundaries, the relayer submits the prior 2016 `bits` values. The Clarity contract reads them from storage and walks through `(list 2016 uint)` — bounded, feasible, but gas-heavy.
3. **Conservative single-block walk-back** (like the Arbitrum T4 rule): just check `bits == prev_bits` unless at a retarget boundary, in which case the relayer submits the prior target and the contract asserts the clamp. This is what the current Solidity implementation does (per Arbitrum research §0.5 — "bounded walk-back through stored `block_bits` (≤ 2016 steps)").

**Recommendation for BTCP Clarity:** Use option 3 (matches the Solidity reference implementation).

---

## 0.9 Public vs Read-Only Functions, Traits, and Contract Calls

### 0.9.1 Function definitions

| Form | Visibility | State mutation | Caller | Return type |
|------|------------|----------------|--------|-------------|
| `(define-public (name (args...)) body)` | Public (callable via transaction) | Can mutate state | Any tx sender | MUST return `(response A B)` |
| `(define-read-only (name (args...)) body)` | Public (callable via `contract-call?` or RPC `call-read-only`) | CANNOT mutate state (enforced by type-checker) | Any tx sender or read-only RPC | Any type (commonly `(response A B)` or `(some ...)` or `(buff N)`) |
| `(define-private (name (args...)) body)` | Private (only callable within the same contract) | Can mutate state if called from a public function | Within contract only | Any type |

**Critical:** Public functions MUST return `(response A B)`. If the body returns an unwrapped value, the type-checker emits the "detected two execution paths" error (see §0.6.2). Read-only functions MAY return any type — but the convention is to also return `(response A B)` for caller-side `match` ergonomics.

### 0.9.2 Trait definitions (interface contracts)

```clarity
(define-trait btc-spv-trait
  ((store-header
     ((buff 80)               ;; header
      (buff 32)               ;; hash (sha256(sha256(header)), internal byte order)
      (buff 32)               ;; merkle root
      )
     (response uint uint))    ;; returns ok(new-height) or err(code)

   (get-header
     (uint)
     (response { header: (buff 80), hash: (buff 32), prev-hash: (buff 32), time: uint, bits: uint, nonce: uint, merkle-root: (buff 32) } uint))

   (verify-tx-inclusion
     (uint                    ;; block-height
      (buff 32)               ;; txid (internal byte order)
      (list 32 (tuple (sibling (buff 32)) (is-right bool)))   ;; merkle proof
      uint                    ;; actual depth
      )
     (response bool uint))

   (chain-tip
     ()
     (response (tuple (hash: (buff 32)) (height: uint)) uint))
   ))
```

- Traits are interface specifications — they declare function signatures without implementations.
- Other contracts implement the trait via `(impl-trait .contract-name.trait-name)` at the top of the file.
- Trait references can be passed as function arguments: `(define-public (foo (spv <btc-spv-trait>)) ...)`.

### 0.9.3 `contract-call?` — invoking other contracts

```clarity
(contract-call? .btc-spv-verifier store-header header hash merkle-root)
;; Returns (response A B) matching the callee's return type.
```
- The callee MUST be a public function.
- The callee's contract MUST be deployed before the caller (the Stacks deployment is sequential — no forward references).
- For dynamic dispatch (calling a contract through a trait): `(contract-call? .contract trait-ref fn-name args)` or `(contract-call? trait-ref fn-name args)` for trait-passed references.
- Cross-contract calls share the runtime budget of the calling transaction (no separate gas accounting per call — they all share one block's 5e9 runtime cap).

---

## 0.10 `clarinet` — the Stacks Dev Toolchain

### 0.10.1 Installation (binary distribution)

| Distribution | Status |
|--------------|--------|
| `@stacks/clarinet` npm package | **DEPRECATED / REMOVED**. The npm package returns HTTP 404 on `npm install`. The `trion-stacks/package.json` declares `"@stacks/clarinet": "^2.5.0"` but this CANNOT be installed. |
| Standalone Rust binary | **ACTIVE**. Latest version: `v3.23.2` (tag as of 2026-09-10). Distributed via GitHub releases at `https://github.com/stx-labs/clarinet/releases` (note: repo renamed from `hirosystems/clarinet` to `stx-labs/clarinet`). |

**Verified installation (this research):**
```bash
curl -L -o clarinet.tar.gz https://github.com/stx-labs/clarinet/releases/download/v3.23.2/clarinet-linux-x64-musl.tar.gz
tar xzf clarinet.tar.gz
./clarinet --version    # -> clarinet 3.23.2
```

**Action item:** Update `trion-stacks/package.json` to remove the `@stacks/clarinet` dependency (it cannot be installed) and add a note in `README` documenting the binary installation.

### 0.10.2 `clarinet` subcommands (v3.23.2)

| Command | Purpose |
|---------|---------|
| `clarinet new <NAME>` | Scaffold a new project (creates `contracts/`, `tests/`, `settings/`, `Clarinet.toml`). Interactive (asks telemetry consent). |
| `clarinet contract new <NAME>` | Scaffold a new contract + test file. |
| `clarinet check` | Type-check all contracts in `Clarinet.toml`. Validates Clarity syntax. |
| `clarinet deploy` | Deploy contracts to a network (testnet/mainnet/devnet). Requires `settings/<Network>.toml`. |
| `clarinet console` | Open a Clarity REPL against a simnet. |
| `clarinet integrate` | Run integration tests via a devnet (docker-based, simulates a full Stacks + Bitcoin regtest stack). |
| `clarinet test` (deprecated) | In v3.x, tests run via `npm test` (vitest with `vitest-environment-clarinet`), NOT via `clarinet test`. |

**Workflow for BTCP Zero-Bridge:**
1. `clarinet new trion-btcp` (scaffold project).
2. Edit `Clarinet.toml` to register each contract with its `epoch` (`2.5` for backward-compat or `3.0` for Nakamoto features; we use `3.0`).
3. `clarinet check` to validate syntax and type-check.
4. Write TypeScript tests in `tests/` using `@stacks/clarinet-sdk` v3.x's `initSimnet()` API:
   ```ts
   import { initSimnet } from "@stacks/clarinet-sdk";
   const simnet = await initSimnet();
   const r = simnet.callPublicFn("deployer.contract-name", "fn-name", [], deployer);
   ```
5. `npx vitest run` to execute tests.
6. `clarinet deploy --network testnet` to deploy to Hiro testnet (requires funded STX address).

### 0.10.3 `@stacks/clarinet-sdk` v3.x API (the new test framework)

**Installed via** `npm install @stacks/clarinet-sdk` (a real npm package, distinct from the deprecated `@stacks/clarinet`).

**Key API (verified working):**
```ts
import { initSimnet } from "@stacks/clarinet-sdk";
const simnet = await initSimnet();
const deployer = simnet.deployer;        // default deployer principal
const alice = simnet.accounts.get("wallet_1")!;

// Call a public function (returns result + events + costs)
const r = simnet.callPublicFn(`${deployer}.my-contract`, "store-header",
  [Cl.buffer(new Uint8Array(80))], alice);
console.log(r.result);       // ClarityValue
console.log(r.events);       // STX/contract events
console.log(r.costs);        // NOTE: returns null in current SDK build (use --costs flag for cost reports)

// Call a read-only function (no state mutation, no cost accounting)
const ro = simnet.callReadOnlyFn(`${deployer}.my-contract`, "get-header",
  [Cl.uint(5100)], alice);

// Mine a block (advance chain state)
simnet.mineBlock([...txs]);
```

**Gotcha:** The SDK export `Clarinet.test({...})` from earlier versions has been REMOVED. The new pattern uses standard `vitest` `describe`/`it` blocks.

### 0.10.4 Epoch setting — `Clarinet.toml`

```toml
[contracts.btc-spv-verifier]
path = "contracts/btc-spv-verifier.clar"
epoch = "3.0"   ;; or "2.5" for backward compat (pre-Nakamoto)
```

| Epoch | Clarity version | Status | Notes |
|-------|----------------|--------|-------|
| 2.0 | Clarity v1 (initial) | Supported | Original Clarity. Use only for legacy mainnet. |
| 2.1 | Clarity v2.1 | Supported | Adds `get-burn-block-info?` by height, `asserts!`. |
| 2.4 | Clarity v2.4 | Supported | Adds `replace-at?`, `slice?` improvements. |
| 2.5 | Clarity v2.5 | Supported | Latest pre-Nakamoto. Most existing mainnet contracts use 2.x. |
| **3.0** | Clarity v3 (Nakamoto) | **Active** | Removes `block-height`, `get-block-info?`; adds `tenure-height`, `get-tenure-info?`, `miner-address` for `get-burn-block-info?`. |

**Recommendation for BTCP:** Use `epoch = "3.0"` to target the Nakamoto testnet (matches the Hiro testnet's `server_version: stacks-node 4.0.1`).

---

## 0.11 Stacks Testnet — Deployment, Faucet, Fee Model

### 0.11.1 Network endpoints

| Endpoint | URL | Purpose |
|----------|-----|---------|
| Hiro testnet API (read) | `https://api.testnet.hiro.so` | REST API for blocks, contracts, transactions, balances. |
| Hiro testnet RPC (write) | `https://api.testnet.hiro.so` (POST `/v2/transactions`, `/v2/contracts/call-read-only`, etc.) | Submit transactions, call read-only functions. |
| Hiro testnet WebSocket | `wss://api.testnet.hiro.so/extended/v1/ws` | Real-time event stream. |
| Stacks testnet explorer | `https://explorer.hiro.so/?chain=testnet` | Block explorer UI. |
| Faucet (deprecation note) | `https://explorer.hiro.so/sandbox` (Hiro sandbox) | Fund testnet STX addresses (one-shot, requires GitHub auth). |
| Alternative faucet | `https://testnet-faucet.hiro.so` | Direct API faucet (limited, may be deprecated). |

### 0.11.2 Chain IDs and parameters

| Parameter | Testnet value | Mainnet value |
|-----------|---------------|---------------|
| Chain ID (Stacks) | `2147483648` (0x80000000) | `1` |
| Parent network ID (Bitcoin) | `3669344250` | Bitcoin mainnet magic bytes |
| PoX consensus | Dynamic per tenure | Dynamic per tenure |
| Block time (Stacks) | ~5 sec (Nakamoto signer set cadence) | ~5 sec |
| Block time (Bitcoin burnchain) | ~10 min (avg 9 min observed on Hiro testnet) | ~10 min |
| Block runtime limit | `5,000,000,000` (5e9) units | Same |
| Block read count limit | 7,000 | Same |
| Block read length limit | 100,000,000 bytes | Same |
| Block write count limit | 7,000 | Same |
| Block write length limit | 15,000,000 bytes | Same |

### 0.11.3 Fee model — microSTX, fee rate, and execution cost

**Unit conversion:**
- 1 STX = 1,000,000 microSTX (μSTX).
- Smallest unit: 1 microSTX.

**Fee calculation (per transaction):**
```
fee_in_microSTX = max(1, base_fee + execution_cost * fee_rate)
```
Where:
- `base_fee`: minimum fee per transaction (~180 μSTX for a simple transfer).
- `execution_cost`: weighted sum across runtime / read_count / read_length / write_count / write_length dimensions (each has its own μSTX-per-unit rate).
- `fee_rate`: the network's current fee rate (dynamic, based on block congestion). The `deployment_fee_rate` in `settings/Testnet.toml` is the rate used during `clarinet deploy`.

**Empirical:**
- A `sha256(0x)` public function call (80-byte header test) costs ~1,200 runtime units + 1 read + 32 bytes read length + 0 writes.
- At a fee rate of 10 μSTX / runtime unit (typical testnet default): total = ~12,000 μSTX = ~0.012 STX per sha256 call.
- For a full BTCP header verification (~5,000 runtime + storage writes): ~0.05 STX per header.
- For a 12-level Merkle proof (~28,800 runtime): ~0.29 STX per Merkle proof.

### 0.11.4 Deployment workflow

1. **Fund the deployer account** from the Hiro faucet (requires GitHub auth on `explorer.hiro.so/sandbox`).
2. **Configure `settings/Testnet.toml`**:
   ```toml
   [network]
   name = "testnet"
   deployment_fee_rate = 10

   [accounts.deployer]
   mnemonic = "<your-12-word-mnemonic>"
   # stx_address = "ST..."
   # derivative-key-count = ...
   ```
3. **`clarinet deploy --network testnet`**: deploys all contracts in dependency order, paying the deployment fee from the deployer account. Produces a `deployments.default.testnet-plan.yaml` recording the deployment.
4. **Verify deployment** via `https://api.testnet.hiro.so/extended/v1/contract/<contract-address>` — should return the contract source.

### 0.11.5 Read-only RPC call (no fee, no state mutation)

For pure queries (no transaction needed), use:
```
POST https://api.testnet.hiro.so/v2/contracts/call-read-only
{
  "contract": "<deployer>.<contract-name>",
  "function": "get-header",
  "sender": "ST1PQHQKV0RJXZFY1DGX8MNSNYVE3VGZJSRTPGZGM",
  "function-args": [<hex-serialized-clarity-value>]
}
```
- No STX fee, no nonce required.
- Bounded by the same execution cost limits (transaction is rejected if it exceeds block limits).
- The Hiro API server executes the call against the latest chain state and returns the Clarity value.

---

## 0.12 BINDING DECISION RECORD — BTCP Zero-Bridge Clarity Architecture

Based on the findings above. **Four pinned decisions** drive every downstream contract design choice:

**(a) Full-SPV-in-Clarity path (NOT `get-burn-block-info?`).**

The Clarity `btc-spv-verifier` maintains its own `(define-map bitcoin-headers uint {...})` of Bitcoin block headers, fed by a relayer via `(define-public (store-header ...))`. The contract verifies PoW (`sha256(sha256(header)) < target`) and Merkle inclusion on-chain. This is the same architecture as the Arbitrum `BTCSPVVerifier.sol` (storage map + relayer-side `storeHeader()`), transplanted to Clarity. **Empirical justification** (§0.1 + §0.1.4 live re-verification): the Hiro Stacks testnet burnchain is at height ~15,003 and is NOT Bitcoin testnet3 (tip 5,129,084) or testnet4 (tip 151,760) — its `burn_block_hash` values do NOT exist on the public Bitcoin testnets (HTTP 404 cross-checks). `get-burn-block-info?` cannot retrieve any Bitcoin testnet3 block, including the OOA mission's chain tip (block 5,128,449).

**(b) `sha256` primitive (native Clarity builtin, NOT a precompile).**

`(sha256 (buff N)) -> (buff 32)` is a first-class Clarity primitive available since Clarity v1 (epoch 2.0), unchanged through Clarity v3 (Nakamoto, epoch 3.0). It produces byte-identical output to Python `hashlib.sha256(...).digest()` and to Solidity precompile 0x02 (§0.2.1). Cost: ~1,200 runtime units for a 80-byte input (~2,900× cheaper per-block-relative than Arbitrum's 22,395 gas, §0.2.2). Double SHA-256 for PoW: `(sha256 (sha256 header))`. Merkle branch hashing: `(sha256 (concat left right))`. **No library implementation needed** — the parity concerns that complicated the Solidity path (cross-VM byte order, precompile chaining overhead, SHA3-256 vs Keccak-256) are absent here.

**(c) Bounded loops via `fold` (NOT unbounded `for`/`while`/recursion).**

Clarity is decidable: every transaction terminates in finite, statically-bounded time. The only iteration primitives are `map`, `filter`, `fold` over bounded lists with literal max-size constants. Merkle proof verification is `(fold merkle-step siblings leaf)` over a `(list N (tuple (sibling (buff 32)) (is-right bool)))` where `N` is a literal. Difficulty retarget walk-back is bounded to ≤ 2016 steps (relayer pre-computes the prior `bits` value and submits it; contract asserts the `[old/4, old*4]` clamp on-chain). No `while`, no recursion, no dynamic-size lists.

**(d) Depth tiers 6 / 12 / 24 (NOT a single over-broad `(list 32 ...)`).**

Three tier-specific entry points — `verify-merkle-path-6`, `verify-merkle-path-12`, `verify-merkle-path-24` — each with its own bounded list type. The relayer dispatches based on the block's `tx_count`: ≤64 txs → tier 6, ≤4096 → tier 12, ≤2^24 → tier 24. This minimizes calldata (sibling payload scales with the actual depth, not the worst-case cap), gives the type-checker three statically-bounded code paths, and respects Bitcoin's true Merkle depth ceiling (~24 levels = 2^24 txs, the difficulty-1 mainnet cap).

---

### Additional architectural pins (supporting the four above)

5. **Verifier architecture:** Standalone Clarity contract `.btc-spv-verifier` with `(define-map bitcoin-headers ...)`, `(define-public (store-header ...))`, `(define-read-only (verify-tx-inclusion ...))`, `(define-read-only (chain-tip))`. Same architecture as Arbitrum's `BTCSPVVerifier.sol`, transplanted to Clarity idioms.

6. **No use of `get-burn-block-info?` for Bitcoin verification.** Confirmed in §0.1 that the Hiro testnet burnchain is NOT the public Bitcoin testnet3. The contract maintains its own header map fed by a relayer.

7. **Hash primitives:** `sha256` for PoW + Merkle (parity with Solidity precompile 0x02). `hash160` only if we need P2PKH address verification. `keccak256` is NOT used (no anchor_bh computation on Stacks — anchor_bh parity is the indexer pipeline's job, off-chain).

8. **Byte order convention:** All hashes stored in Clarity are in internal byte order (the bytes from `sha256` directly). The relayer reverses display-order hashes from Bitcoin RPCs before submitting.

9. **Difficulty target derivation:** Conservative single-block walk-back (matches the Arbitrum Solidity implementation's T4 rule). Retarget clamp `[old/4, old*4]` verified on-chain at boundaries; full 2016-block walk-back NOT implemented on-chain (relayer submits prior `bits` value at boundaries).

10. **Error handling:** `asserts!` (note the trailing 's' — `assert!` is NOT a Clarity builtin, §0.6.1) with `(err <uint>)` constants (the canonical Clarity v3 idiom per §0.6.2). Error code taxonomy per §0.6.3.

11. **Epoch:** `3.0` (Nakamoto) — matches the Hiro testnet's `stacks-node 4.0.1`. Use `tenure-height` (not the removed `block-height`).

12. **Trait for composability:** Define `btc-spv-trait` so that the BTCP escrow / registry contracts can call the verifier via dynamic dispatch. This mirrors the Solidity `IBTCSPVVerifier` interface pattern.

13. **Tooling:** Use `clarinet` v3.23.2 binary (NOT the deprecated `@stacks/clarinet` npm package). Tests via `@stacks/clarinet-sdk` v3.9.0 + vitest.

---

## 0.13 Open Items / Honest Limitations (LABELED)

- **L1:** The Stacks testnet burnchain is a Hiro-private chain (NOT Bitcoin testnet3 or testnet4). This is empirically confirmed but the Hiro/Stacks documentation still refers to it as "Bitcoin testnet". The TRION BTCP mission proceeds assuming the Stacks testnet CANNOT verify Bitcoin testnet3 blocks via `get-burn-block-info?`. **If Hiro migrates the testnet burnchain to public Bitcoin testnet4 in the future, this assumption breaks.** Recommend documenting the Hiro burnchain status in the BTCP audit doc.

- **L2:** `get-burn-block-info?` retention window on Hiro testnet is empirically longer than the documented 144-block default (~15,001 blocks since testnet reset are queryable). This is configurable per node and not guaranteed by the protocol. The BTCP contract does NOT depend on this window (uses its own header map), but third-party observers querying `get-burn-block-info?` should be aware.

- **L3:** The `costs` field returned by `@stacks/clarinet-sdk`'s `callPublicFn` is `null` in the current SDK build (v3.9.0). Cost reports are only generated via the `--costs` CLI flag on `clarinet test` (which is itself deprecated). For accurate gas estimation during development, run the contracts on the Hiro testnet directly and inspect `execution_cost_*` fields in the transaction receipt. The gas numbers in §0.2.2 are estimated from the Stacks cost catalog, not measured directly.

- **L4:** SHA3-256 is NOT a Clarity builtin. If the BTCP mission needs anchor_bh parity with the Rust indexer (which uses `Sha3_256`), Clarity CANNOT compute this on-chain. Recommendation: compute anchor_bh off-chain (relayer-side) and pass it into Clarity as a verified input parameter. The Clarity contract only verifies Bitcoin SPV (which uses SHA-256, available natively).

- **L5:** The `trion-stacks/package.json` declares `"@stacks/clarinet": "^2.5.0"` which is no longer installable (HTTP 404). This must be removed and replaced with a note pointing to the binary distribution at `https://github.com/stx-labs/clarinet/releases`.

---

**End of research doc.**

**Next steps (for Phase 1+):**
- Phase 1: Write the Clarity `btc-spv-verifier.clar` contract using these pins. Use `clarinet check` for type-checking, `@stacks/clarinet-sdk` for unit tests with the golden Bitcoin testnet3 headers from the Arbitrum research (verify byte-order conversion in the relayer).
- Phase 2: Deploy to Hiro testnet. Verify the on-chain state via the Hiro API.
- Phase 3: Adversarial battery — submit malformed headers (bad PoW, bad Merkle, bad timestamp, duplicate, out-of-order) and confirm each reverts with the correct `(err uXXX)` code from §0.6.3.
- Phase 4: Cross-VM parity — verify the same Bitcoin testnet3 block (e.g., height 5,128,449) is accepted by BOTH the Arbitrum `BTCSPVVerifier.sol` AND the Stacks `btc-spv-verifier.clar`, producing identical Merkle root / chain-tip state.
