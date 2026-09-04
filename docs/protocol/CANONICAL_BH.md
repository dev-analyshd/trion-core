# TRION Canonical Behavioral Hash (BH) — Cross-Language Specification

**Status:** NORMATIVE (Wave 1, master command §22 deliverable)
**Applies to:** every implementation that constructs, ingests, or verifies a
Behavioral Hash — Python (`core/primitives/`, `core/realtime/bh_streamer.py`,
`anima-service/faiss_service.py`), Rust (`indexers/crates/trion-common/src/hash_dna.rs`
+ all 21 indexer crates), TypeScript (`chains/shared/canonical_bh.ts`), and any
future Solidity port.
**Machine-readable twin:** `config/bh_schema_v1.json`
**Golden vectors:** `tests/golden/vectors.json` (verified by
`tests/golden/test_golden_vectors.py`)

> **One rule above all:** for the same transaction event, every implementation,
> on every machine, at every point in time, MUST produce the **same 93-byte
> payload** and therefore the **same (sense, antisense) pair**. Any input that
  makes the hash depend on process state (session maxima, wall clocks,
  ingestion order) is a canonical violation.

---

## 1. Canonical form (v1 — 93 bytes, production schema)

```
BH(event) = Hash_DNA(payload)

payload (93 bytes, ALL fields big-endian):

  offset  width  field            type        encoding
  ──────  ─────  ───────────────  ──────────  ──────────────────────────────────────
  0       32     entity_id        bytes[32]   SHA3-256(normalise(sender)) — see §6
  32      1      event_type       uint8       canonical event-type ID, 0..19 — §3
  33      8      magnitude_nano   uint64      trunc(magnitude_normalized × 10^9) — §4
  41      8      context          uint64      venue/layer flags, big-endian — §7
  49      8      timestamp_secs   uint64      block time (unix seconds) — §5
  57      4      chain_id         uint32      TRION canonical registry chain id — §8
  61      32     block_hash       bytes[32]   lenient hex→32B of chain block hash — §9
  ──────  ─────  ───────────────  ──────────
  61+32 = 93 bytes total
```

Dual-strand construction (DNA-mimetic, whitepaper L0.1):

```
sense     = SHA3-256(payload || 0x00)
antisense = SHA3-256(payload || 0xFF) XOR NOT(sense)     # byte-wise complement
```

Verification invariant (self-verifying, no external reference):

```
sense XOR antisense == NOT(SHA3-256(payload || 0xFF))
```

Serialized output: two 64-char lowercase hex strings
(`sense_hex`, `antisense_hex`). Tampering with either strand breaks
complementarity and is detected immediately.

**Int widths & endianness:** every integer field is unsigned, **big-endian**
(network order). `magnitude_nano` is an unsigned fixed-point
(nanounit) encoding: `floor(clamp(magnitude_normalized, 0, 1) × 1,000,000,000)`,
which can exactly represent every value in [0, 1] at 10⁻⁹ resolution and keeps
the payload free of floating-point bytes.

**Truncation rule (all languages):** the float→integer conversion for
`magnitude_nano` MUST truncate toward zero, never round:
Python `int(...)`, Rust `as u64`, TypeScript `BigInt(Math.trunc(...))`.

---

## 2. Version and domain separation

* **v1 (this document, 93 bytes): NO domain tag.** The payload length (93),
  the implicit `bh_schema_v1.json` version, and the fixed field layout are the
  domain separation. This is the deployed production schema pinned by the
  cross-language golden vectors (`config/bh_schema_v1.json::test_vector`,
  `indexers/crates/trion-common/src/hash_dna.rs::cross_language_canonical_bh_vector`,
  `tests/golden/vectors.json`). Changing it would break every pinned digest,
  the Rust↔Python↔TS parity guarantees, the BH ledger, and FAISS index keys.

  > Engineering decision (hierarchy level 8, recorded): the whitepaper MD
  > sketched a v2 payload with `DOMAIN_SEPARATOR ||
  > keccak256("TRION_BEHAVIORAL_HASH_V1" || chain_id || contract_address)`.
  > We deliberately did NOT retrofit a domain tag into the 93-byte v1 payload:
  > the vectors are frozen and cross-verified, and a mid-flight re-domain would
  > invalidate the entire Akashic BH ledger. v1 is canonical-with-note.

* **v2 (extended, 176 bytes): OPT-IN, NOT the default.** Implemented by
  `core/primitives/extended_payload.py` and exposed at
  `POST /api/v1/bh/v2/extended`. It is the whitepaper-MD-shaped layout with a
  real domain tag and replay protection:

  ```
  offset  width  field
  ──────  ─────  ─────────────────────────
  0       4      domain_magic = "TRON" (0x54 0x52 0x4F 0x4E)
  4       32     entity_id
  36      1      event_type_id
  37      8      magnitude_nano
  45      2      magnitude_currency_id (ISO 4217-like: 0=USD, 1=ETH, …)
  47      8      timestamp_secs
  55      8      block_number
  63      32     block_hash
  95      4      chain_id
  99      32     counterparty_id (0×32 = "none")
  131     4      protocol_id
  135     32     context_hash
  167     1      btcp_version (currently 1)
  168     8      nonce (replay protection)
  ──────         176 bytes total
  ```

  The dual-strand construction over the 176-byte payload is identical
  (SHA3-256 || 0x00 / || 0xFF, XOR-NOT). v2 BHs are distinguishable from v1 by
  payload length alone (176 ≠ 93); consumers MUST reject lengths they do not
  understand. A coordinated migration v1→v2, if ever mandated by a spec
  revision, requires: a new domain magic, a new schema file, and re-issuance
  of the golden vectors in the same commit across all four languages.

---

## 3. Event-type ID table (all 20 — VM-agnostic)

Fixed enumeration, byte values are canonical and MUST NOT be renumbered:

| byte | name          | byte | name          | byte | name          |
|-----:|---------------|-----:|---------------|-----:|---------------|
| 0    | TRANSFER      | 7    | BORROW        | 14   | BURN          |
| 1    | SWAP          | 8    | REPAY         | 15   | ORACLE_UPDATE |
| 2    | LIQUIDITY     | 9    | LIQUIDATE     | 16   | MEV_CAPTURE   |
| 3    | STAKE         | 10   | BRIDGE        | 17   | FLASH_LOAN    |
| 4    | UNSTAKE       | 11   | DEPLOY        | 18   | AIRDROP       |
| 5    | GOVERNANCE    | 12   | UPGRADE       | 19   | CLAIM         |
| 6    | PROPOSAL      | 13   | MINT          |      |               |

Sources in lockstep: `config/bh_schema_v1.json::event_types`,
`config/event_types.json`, `core/primitives/behavioral_hash.py::EventType`,
`indexers/crates/trion-common/src/hash_dna.rs::event_type_name`,
`anima-service/faiss_service.py::EVENT_TYPE_BYTE`,
`chains/shared/canonical_bh.ts::EventType`.
Byte values 20..255 are **invalid**; builders MUST reject them, ingestion MAY
label them `UNKNOWN_<n>` but MUST NOT re-hash them as a canonical type.
Legacy aliases fold onto canonical values (`LIQUIDITY_ADD/REMOVE → 2`,
`GOVERNANCE_VOTE → 5`, `NFT_MINT → 13`, `NFT_TRANSFER → 0`,
`CONTRACT_DEPLOY → 11`).

Classification heuristics (EVM 4-byte selectors) live in
`hash_dna.rs::classify_event_type` and `core/realtime/bh_streamer.py::SELECTOR_MAP`;
they are **ingestion heuristics, not part of the canonical form** — the byte in
the payload is the canon.

---

## 4. Magnitude normalization (deterministic, per-chain decimals)

Canonical rule (a pure function of the transaction — no session state):

```
amount_human   = raw_native_amount / 10^decimals        # decimals from the chain registry
magnitude_norm = min(1, log10(amount_human + 1) / log10(1001))
magnitude_nano = trunc(magnitude_norm × 10^9)            # §1 truncation rule
```

* `raw_native_amount` is the chain-native smallest unit of the tx's principal
  value field (wei / lamports / yocto / stroops / drops / lovelace / sats / …).
* `decimals` is the canonical per-chain value from
  `config/chain_registry.json::chains[].decimals` (18 for all EVM chains, 6 for
  Cosmos/XRPL/Algorand/Cardano/Tron, 9 for Solana/TON/Sui, 8 for
  Aptos/Movement/UTXO/Waves/Hedera, 24 for NEAR, 7 for Stellar, 10 for Polkadot,
  18 for MultiversX/VeChain/Botchain, …).
* **Reference scale R = 1000 human units** (i.e. `log10(1001)` denominator) is
  the FIXED normalization scale for all chains.

> Spec-provenance note (hierarchy): WHITEPAPER_V2 L0.1 defines
> `log10(USD_value+1) / log10(max_observed_90d+1)`. A rolling 90-day max is
> **not a pure function of the transaction**: the same tx would hash
> differently as the window evolves, which contradicts the Akashic
> append-only identity of a BH (L0.4) and the cross-language parity
> requirement. V2's USD path is therefore **not canonical**; it survives only
> as an optional display/analysis layer (`compute_behavioral_hash(usd_value=…)`
> fallback). WHITEPAPER_MD's `raw_amount × 10^(18−asset_decimals)` is honored
> in spirit via the per-chain decimals scaling to human units. The fixed
> R = 1000 scale, uniform across chains, is the documented engineering
> resolution (level 8) first adopted in Task 20 commit 19decc3 and now pinned
> here as canonical.
>
> **Known per-family proxy caveat:** three Rust ingestors currently use a
> deterministic *proxy* for the principal value (Sui: per-tx gas; Starknet:
> tx max_fee; PVM: extrinsic count). The formula is canonical; the *input
> field* choice for those families is documented divergence to be aligned when
> those chains expose a principal-value field.

Edge cases:
* `raw = 0` → `magnitude_norm = 0` → `magnitude_nano = 0` (zero-value tx is a
  valid canonical event).
* `amount_human` ≥ 1000 → clamps to 1.0 → `magnitude_nano = 1_000_000_000`.
* Values beyond u64 (e.g. u128 wei) are scaled in f64 — the log10 scale
  absorbs the precision; both pipelines must divide by the same power of ten.

---

## 5. Timestamp semantics — BLOCK TIME, never wall clock

Canonical: **`timestamp_secs` = the unix time of the block (or ledger /
checkpoint / round / slot equivalent) that contains the transaction**, as
reported by the chain itself.

* Ingestion time / wall clock / `SystemTime::now()` MUST NEVER enter the
  payload. Two nodes ingesting the same tx at different moments must agree.
* When a family's fetched payload genuinely carries no block time (e.g. a raw
  Substrate `chain_getBlock` without the timestamp pallet), the canonical
  value is **0** — deterministic and honestly "unknown" — never a wall clock.
* Block-level pseudo-entities (e.g. `svm:slot:<n>`) use the same block time.
* FAISS vector *metadata* timestamps (when the vector was indexed) are outside
  the BH payload and may remain wall-clock — they are not the hash input.

Per-family block-time source (Python streamer ↔ Rust indexer parity):

| family   | source field                                        | scale      |
|----------|-----------------------------------------------------|------------|
| EVM      | `eth_getBlockByNumber → block.timestamp`            | hex→secs   |
| SVM      | `getBlock → blockTime`                              | secs       |
| Cosmos   | `/blocks/{h} → block.header.time` (RFC 3339)        | ISO→secs   |
| Aptos/Move | `/blocks/by_height/{h} → block_timestamp`         | µs→secs    |
| Sui      | `sui_getCheckpoint → timestamp_ms`                  | ms→secs    |
| NEAR     | block `header.timestamp`                            | ns→secs    |
| Starknet | `starknet_getBlockWithTxs → timestamp`              | secs       |
| Tron     | `block_header.raw_data.timestamp`                   | ms→secs    |
| UTXO     | block `median_time`/`time`                          | secs       |
| Stellar  | ledger `closed_at` (or tx `created_at`)             | ISO→secs   |
| MultiversX | hyper `timestamp`                                 | secs       |
| Waves    | block `timestamp`                                   | ms→secs    |
| Algorand | `block.ts`                                          | secs       |
| Cardano  | Koios `block_time`                                  | ISO→secs   |
| XRPL     | `ledger.close_time + 946684800`                     | secs       |
| TON      | tx `utime` (first tx of block)                      | secs       |
| PVM      | sidecar timestamp when present, else **0**          | secs       |

---

## 6. Sender / entity resolution — `entity_id`

Canonical: **`entity_id = SHA3-256(normalise(sender_address))`** — the stable
BEO routing key, byte-identical to Rust `hash_dna.rs::bh_id()` and TypeScript
`entityIdFromAddr()`.

```
normalise(raw):
    s = raw.trim().to_lowercase()
    if s starts with "0x" and len(s) >= 42: return s
    if len(s) == 40 and s is all hex:        return "0x" + s
    return s                                  # non-EVM ids pass through unchanged
entity_id = SHA3-256(utf8(normalise(sender)))      # 32 bytes, hex-encoded = 64 chars
```

* This is the Task 20 decision (commit 19decc3), verified against the spec:
  WHITEPAPER_V2 L0.2 mandates "`entity_id` in BH = BEO identifier, not raw
  address" — the SHA3-256 of the normalised address IS the BEO routing
  identifier (`bh_id`) used by the FAISS primary key and the Akashic ledger,
  so both ingestion pipelines hash the same 32-byte BEO key for the same
  actor. (A raw 20-byte address would also violate the 32-byte field width.)
* Block-aggregate pseudo-entities use `block_entity_id(chain_label, height)`
  (`"<label>:<height>"`) → `bh_id` of that string — same construction, clearly
  namespaced, never colliding with an address form.
* Non-EVM chains without an address on a fetched tx use the deterministic
  synthetic per-tx sender
  `SHA3-256("<chain_name>:<tx_hash>")` — distinct per tx, never the old
  shared `sha3("unknown")` bucket.
* Future BEO clustering (L0.2 confidence > 0.75 merging wallets into one
  entity) is an ANALYSIS layer: it re-keys vectors, it does NOT rewrite the
  BH. The BH is pinned to the address-level entity at emission time.

---

## 7. Context field (8 bytes)

`context` is a u64 big-endian venue/layer flag field:

```
bits 0-1  venue type    (0=DEX, 1=LENDING, 2=BRIDGE, 3=NATIVE)
bits 2-3  settlement    (0=L1, 1=L2, 2=L3, 3=sidechain)
bits 4-7  reserved / protocol version
```

**Canonical value today: 0** — every Rust indexer crate and the Python
streamer pass 0 (the field is reserved; the old experimental
`chain_id << 32 | event_type` encoding could never match the Rust pipeline and
was removed in Task 20). Legacy string contexts are deterministically folded
to a u64 via `SHA3-256(utf8(context))[0:8]` big-endian (see
`faiss_service.compute_hash_dna`); empty/"0" contexts map to 0.

---

## 8. Chain ID semantics — the canonical registry

`chain_id` is the **TRION canonical chain id** (u32, big-endian) from
`config/chain_registry.json` (129 chains, 18 VM families) — NOT the chain's
own self-reported id space, and NOT ingestion-path-local namespaces.

Examples: Ethereum=1, Solana=900, Stellar=27000, Base=8453, Cosmos
Hub=10000, Aptos=1000003 (see registry for all). The registry is the single
source of truth; streamer non-EVM ids were re-keyed to it in Task 20
(c93d237), trion-movement was fixed 5002→20200 (3738b61). Producers MUST
resolve ids through the registry before hashing; `chain_id` is truncated to
u32 (`& 0xFFFFFFFF`).

---

## 9. Block hash semantics — lenient hex decode

`block_hash` is 32 bytes, decoded from the chain's block hash string by the
**lenient decoder** (byte-identical in all languages):

```
hex_to_32bytes(s):
    strip optional "0x"/"0X" prefix
    out = 32 zero bytes
    n = min(len(s) // 2, 32)          # LEFT-aligned, at most 32 bytes
    for i in 0..n:
        hi = hexval(s[2i])   # invalid nibble → 0
        lo = hexval(s[2i+1]) # invalid nibble → 0
        out[i] = (hi << 4) | lo
    return out
```

* Short hashes are **left-aligned and zero-padded on the right** (a 16-hex-char
  hash lands at bytes 0..8, NOT at the end of the field).
* Odd trailing nibble is dropped (`byte_count = len/2` truncating).
* Invalid hex characters decode as 0 — never an exception, never a silent
  SHA3 substitution (a substituted hash could never be reproduced by another
  implementation and was removed in Task 20).
* Chain families whose API has no block hash in the fetched payload (5
  non-EVM fetchers) write `0x0` → 32 zero bytes, via the same decoder.

---

## 10. Final serialization & self-verification

A canonical BH record is:

```json
{
  "entity_id":   "<64 lowercase hex>",   // sha3(normalise(sender))
  "event_type":  <0..19>,
  "magnitude_norm": <float in [0,1]>,    // informational; the payload carries the nano form
  "context":     <u64>,
  "timestamp":   <unix secs>,
  "chain_id":    <registry u32>,
  "block_hash":  "<chain hex string>",
  "sense_hex":     "<64 lowercase hex>", // SHA3-256(payload || 0x00)
  "antisense_hex": "<64 lowercase hex>", // SHA3-256(payload || 0xFF) XOR NOT(sense)
  "valid":      true
}
```

`valid` MUST be recomputed on ingestion:
`antisense XOR NOT(sense) == SHA3-256(payload || 0xFF)`
(`core/primitives/behavioral_hash.py::bh_from_rust_hex` is the strict
93-byte ingestion path and raises on failure).

---

## 11. Spec provenance and conflict resolution

Per the hierarchy of truth (spec > math > security > implementation > tests >
docs > judgment):

1. **WHITEPAPER_MD.txt L0.1 (newest, protocol semantics)** defines the BH as
   an ABI-encoded 14-field payload with DOMAIN_SEPARATOR (counterparty,
   protocol, currency, version, nonce…). This is the **v2 direction**, not the
   deployed form.
2. **WHITEPAPER_V2.txt L0.1** defines the 7-field core
   (`entity_id || event_type || magnitude_normalized || context || timestamp ||
   chain_id || block_hash`) and the dual-strand construction — this is exactly
   the v1 field set, and the dual-strand algebra is implemented verbatim.
3. The **deployed canonical** is the 93-byte binary v1 (schema
   `config/bh_schema_v1.json`, "The 93-byte payload is the CANONICAL
   production schema (v1). The expanded whitepaper payload … is a future v2
   extension.") — pinned by cross-language golden vectors in Rust, Python and
   TypeScript since before Task 20, and by the BH ledger + FAISS keys.
4. Where MD and V2 disagree (domain tag, ABI vs fixed binary, rolling-max
   magnitude), v1 keeps the V2-shaped core with deterministic normalization
   (§4) and defers the MD extras to the opt-in v2 payload (§2). This is the
   recorded resolution: **do not break the frozen vectors without a spec
   mandate plus a coordinated four-language re-issuance.**
5. Both specs' dual-strand definitions agree:
   `sense = SHA3-256(input||0x00)`, `antisense = SHA3-256(input||0xFF) XOR
   complement_transform(sense)`, `complement_transform = bitwise NOT`.

---

## 12. Compliance matrix (audited Wave 1 / Agent B)

| implementation | file | verdict |
|---|---|---|
| Rust core builder | `indexers/crates/trion-common/src/hash_dna.rs::canonical_bh` | **COMPLIANT** — exact 93-byte layout, truncating nano, lenient hex, dual-strand |
| Rust entity key | same file `bh_id`/`normalise` | **COMPLIANT** — §6 |
| Rust per-crate magnitude | all 21 `indexers/crates/*/src/main.rs` | **FIXED (this wave)** — session-max rolling state removed; deterministic §4 formula pinned (static fix, needs cargo verification) |
| Rust per-crate timestamps | 12 crates used `SystemTime::now()` | **FIXED (this wave)** — block-time sources / 0 fallback per §5 (static fix, needs cargo verification) |
| Python reference | `core/primitives/behavioral_hash.py::compute_behavioral_hash` | **FIXED (this wave)** — entity/block fields now lenient 32-byte canonical; magnitude nano path already truncating; USD path retained as non-canonical display fallback |
| Python streamer | `core/realtime/bh_streamer.py::compute_bh` | **COMPLIANT** — §4/§5/§6/§8/§9 all deterministic (Task 20) |
| Python FAISS service | `anima-service/faiss_service.py::canonical_bh` | **COMPLIANT** — byte-identical Rust port incl. `_hex_to_32bytes` |
| TypeScript | `chains/shared/canonical_bh.ts` | **FIXED (this wave)** — magnitude rounding → truncation; `hexTo32Bytes` right-aligned/padStart → lenient left-aligned §9 port |
| Python extended v2 | `core/primitives/extended_payload.py` | **COMPLIANT (v2 opt-in)** — 176-byte layout per §2 |

Unverified boundary (external toolchain policy): the Rust changes are
**statically** verified (source-order parity tests + no cargo toolchain in the
environment). `cargo build/test` on `indexers/` remains an open external
boundary. Cross-language libm differences in `log10` are absorbed by the
10⁻⁹ nano quantization except at exact half-ulp boundaries — the golden
vectors pin the shared digests, and any future failure would surface there
first.

---

## 13. Golden vectors

`tests/golden/vectors.json` pins ≥ 12 canonical vectors (plain transfer, swap,
MEV/flash-loan, max magnitudes, zero value, minimal fields, per-chain decimal
normalization 18/9/6dp, distinct chain ids, every event-type byte, lenient
block-hash edge cases) with `payload_hex`, `sense`, `antisense` for each.
`tests/golden/test_golden_vectors.py` verifies, for every vector:

1. the **Python** canonical builder reproduces the pinned bytes/digests;
2. the **Rust** builder would produce the same bytes — by static source-order
   verification of `hash_dna.rs::canonical_bh` (field widths/order/endian
   match the §1 table, the same way `tests/unit/test_intent_spec_fields.py`
   pins Rust structs);
3. the **TypeScript** builder (`chains/shared/canonical_bh.ts`) — executed via
   `node`/`bun` — produces byte-identical digests.

The pre-existing single-vector checks stay authoritative and MUST keep
passing: `tests/unit/bh_cross_language_vector.py` (schema vector),
`scripts/cross_lang_bh_check.py` (parity vector), and the Rust
`cross_language_canonical_bh_vector` unit test.
