# SWEEP-B — Cross-Language Parity Audit (Rust / TypeScript / contracts vs Python canon)

**Task ID:** SWEEP-B (TEAM G, master command §9/§11/§17)
**Repo:** /home/z/trion-core @ HEAD `c6c38e4` (clean; only untracked `docs/audit/canonical-sweep/`)
**Mode:** research-only. No repo files modified. All throwaway scripts under `/tmp/sweepb/`.
**Executions:** bun (TS), /home/z/.venv/bin/python3 (Python + tests), node --check, WebAssembly.Module.exports. No cargo (static verification only).

---

## 1. Rust crate inventory (indexers/crates — 21 chain crates + trion-common = 22 workspace members)

Workspace: `indexers/Cargo.toml` members = 22 (21 chain crates + `trion-common`) — matches expectation.
All 21 chain crates call `trion_common::hash_dna::canonical_bh` (re-exported at `trion-common/src/lib.rs:29`); 58 `canonical_bh` references across 23 files. All magnitude functions use the deterministic §4 formula `min(1, log10(human+1)/log10(1001))` — **zero session-maxima residue** (no `session_max`/`max_observed` outside a stale doc comment, see §8-D1).

| crate | family | chain_id (const, registry-verified) | timestamp source (§5) | magnitude input (decimals) | block_hash source |
|---|---|---|---|---|---|
| trion-evm | EVM ×55 | ETH=1, ARB=42161, BASE=8453, OP=10, POLYGON=137, BNB=56, MANTLE=5000, LINEA=59144, SCROLL=534352, … (all sampled ✓) | `block.timestamp` hex→secs (main.rs:758) | wei /1e18 (:592-600) | `block.hash` (:757) |
| trion-botchain | EVM-style | 677 ✓ | hex→secs (:289) | wei /1e18 (:132-139) | `block.hash` (:288) |
| trion-svm | SVM | 900 ✓ (Solana) | `blockTime` secs (:239-242) | lamports /1e9 (:120-127) | `blockhash` (:243) else `sol_slot:` synthetic (:245) |
| trion-sui | Sui | 20100 ✓ | checkpoint `timestamp_ms`/1000 (:210-212) | per-tx **gas proxy** /1e9 (:115-122, documented §4 caveat) | checkpoint `digest` (:214) else `sui_cp:` synthetic (:216) |
| trion-near | NEAR | 23000 ✓ | header ns /1e9 (:246) | yocto /1e24 (:112-119) | `header.hash` (:249) else synthetic (:251) |
| trion-aptos | Aptos | 20000 ✓ | `block_timestamp` µs /1e6 (:223-225) | octas /1e8 (:114-121) | `block_hash` (:227) else synthetic — **Python streamer uses `previous_block_hash`** (bh_streamer.py:878) — D3 |
| trion-movement | Movement | 20200 ✓ (5002→20200 fix verified) | µs /1e6 (:225-227) | octas /1e8 (:120-127) | `block_hash` (:229) else synthetic (:231) |
| trion-starknet | Starknet | 24000 ✓ | `timestamp` secs (:216) | **max_fee proxy** /1e18 (:116-123, documented) | `block_hash` (:218) else synthetic (:220) |
| trion-tron | Tron | 26000 ✓ | raw_data ms /1000 (:235) | sun /1e6 (:129-136) | `blockID` (:238) |
| trion-pvm | PVM | 25000 ✓ (Polkadot) | **0 always** (:361, canonical unknown per §5) | planck /1e10 per-tx (:171-178); extrinsic-count proxy block-level (:385-386, documented) | synthetic `pvm_block:` bh_id (:363) — Python uses real `chain_getBlockHash` (:1122-1135) — D3 |
| trion-cosmos | Cosmos ×6+ | 10000/10014/10004/10005/10006/10015 ✓ | `header.time` RFC3339 → `iso8601_to_epoch` (:266-268) | uatom /1e6 (:151-158) | `block_id.hash` (:270) else synthetic (:272). Proposer pseudo-event et=6 mag=0.5 hardcoded (:292-293) |
| trion-utxo | UTXO ×4 | BTC=21000, LTC=21004, DOGE=21003, DASH=21005 ✓ | block `timestamp` secs (:190) | sats /1e8 (:97-104) | `hash` (:192) else synthetic (:194). Coinbase pseudo-event et=13 mag=0.0 (:113-114) |
| trion-xrpl | XRPL | 31000 ✓ | `close_time`+946684800 (:286-288) | drops /1e6 (:195-202) | `ledger_hash` (:284) else synthetic (:306) |
| trion-pi | Stellar | 27000 ✓ | `created_at` ISO → epoch (:225-231) | stroops /1e7 (:109-116) | **synthetic `pi_ledger:` bh_id (:233)** — Python writes `"0x0"` (:993) — D3 |
| trion-ton | TON | 22000/22001 ✓ | first-tx `utime` (:227-229) | nano /1e9 (:108-115) | **synthetic `ton_block:` bh_id (:231)** — Python uses real root_hash (:924) — D3 |
| trion-waves | Waves | 30000 ✓ | ms /1000 (:272) | wavy /1e8 (:184-191) | signature (:281) else synthetic (:282) |
| trion-algorand | Algorand | 8200 ✓ | `/block/ts` secs (:175) | micro /1e6 (:105-112) | `cert/proposal/ophash` (:172) else synthetic (:184) |
| trion-cardano | Cardano | 9400 ✓ | Koios `block_time` ISO (:174-179) | lovelace /1e6 (:108-115) | tx `block_hash` (:181) else synthetic (:190) |
| trion-multiversx | MultiversX | 32000 ✓ | hyper `timestamp` secs (:310) | wei /1e18 (:190-198) | hyper `hash` (:308) else synthetic (:322) |
| trion-hedera | Hedera | 28000 ✓ | hex-string secs parse (:221-225) | **/1e18 "EVM-style wei" — registry decimals = 8** (:129-138) — D2 | **`bh_id(hash_hex)` SHA3 substitution** (:235-239) — D1 |
| trion-vechain | VeChain | 29000 ✓ | `timestamp` secs (:244) | wei /1e18 (:140-148) | block `id` (:242) else synthetic (:255) |
| trion-common | — | — | `iso8601_to_epoch` helper (hash_dna.rs:331-398) + 10 pinned unit tests | `canonical_bh` core (hash_dna.rs:227-282) | `hex_to_32bytes` lenient decoder (:284-295) |

**SystemTime::now residue (mission 1a §5 check):** exactly 3 hits in `indexers/`:
- `trion-evm/src/main.rs:800` and `trion-botchain/src/main.rs:329` — both feed `VectorEntry.timestamp` (FAISS submission **metadata**), NOT the BH payload; the `canonical_bh` calls at :782/:664 and :311/:196 use the block `timestamp` var. §5 explicitly permits wall-clock for vector metadata. **Not a canonical violation**, but inconsistent with the other 19 crates which put block-time in `VectorEntry.timestamp` (drift risk only).
- `trion-common/src/living_security.rs:41` — heartbeat `now_secs()`, unrelated to BH.
**Verdict: no §5 payload violations.**

**Chain-id compliance:** 15 single-chain consts + 14 sampled multi-chain ids all match `config/chain_registry.json` exactly (programmatic diff, incl. decimals except Hedera — D2). IDs are hardcoded per crate (drift risk if registry changes; no runtime registry read).

### 1c. Golden vector pin (Rust)
`hash_dna.rs::cross_language_canonical_bh_vector` (:495-518) — inputs entity `"deadbeef…"`, et=1, mag 0.5, ctx 0, ts 1.7e9, chain 1, block `"ab"*32`; pinned `sense=a6639d2a18029b1f6fb1f00a4ed028db1ad800f8d19870f944eb8edbe6db2164`, antisense `63f44f42…d2fb4a9`.
- **Identical to `tests/golden/vectors.json` vectors[1] `ref_cross_lang_rust_vector`** (sense+antisense byte-equal, verified programmatically).
- It is **NOT** `ref_schema_v1_vector` (vectors[0]: entity `"ab"*32`, et=7, chain 421614, block `"cc"*32`, sense `7060238a…`) — v0 is pinned instead by `config/bh_schema_v1.json::test_vector` + `tests/unit/bh_cross_language_vector.py` (which loads the schema vector dynamically, no hardcoded digests). Both reference vectors are covered by the golden file; the Rust crate pins v1 only, with `canonical_bh_output_lengths` (:419-428) touching v0's inputs but asserting only lengths.
- `cross_language_bh_id_vector` (:522-532) pins `f9769049b9d4b778…` — reproduced live by Python `sha3_256("0xdeadbeef…")` ✓ (entity_id parity, §6).

### 1d. Workspace structure + compile-sanity
- `rust/` (trion-btcp) is a **separate standalone package** (own Cargo.toml/Cargo.lock, lib + 2 bins) — NOT a member of the `indexers/` workspace. `indexers/` workspace = 22 members exactly.
- Brace/paren/bracket balance (string/comment-aware scanner) on the 5 most recently committed .rs files: hash_dna.rs (43/43, 260/260, 40/40), btcp_proof_builder.rs (37/37,143/143,20/20), trion-evm main.rs (118/118,284/284,97/97), contracts/svm/btcp_escrow (104/104,433/433,218/218), contracts/svm/btcp_common (40/40,143/143,121/121) — **all balanced, no crate would fail on structure**. (No cargo toolchain — true compile remains an open external boundary, consistent with CANONICAL_BH.md §12 note.)

---

## 2. BTCP rust/src/ module map → 6-step orchestration (+Step 0)

Python 6-step reference: `core/btcp/orchestrator.py:1007-1013` (1 validate addresses, 2 create intent, 3 encode for both VMs, 4 estimate gas, 5 generate ZK proofs, 6 track route) + Step 0 registry membership (:1028-1042).

| Rust module (rust/src/) | orchestration stage | notes |
|---|---|---|
| `adapters/mod.rs` + `adapters/evm.rs` | Step 1 (validate_address) + Step 3 (VM translation, spec §4.2 Step 4) + Step 4 (`estimate_gas`, :139) | EvmAdapter honestly NotConnected (no RPC dep); `verify_execution`/ExecutionReceipt |
| `types.rs` (Intent + IntentConstraints §4.1), `bitp_matcher.rs` (BITPIntentData), `intent_aggregator.rs` (IAP pooling) | Step 2 (create standardized intent) | §4.1 field set complete (see §3) |
| `bibl_engine.rs` (BIBLAnalysis: NL, gas forecast, CC, MF, capacity, finality) | Step 4 (gas/finality estimation, Phase 2) | |
| `btcp_proof_builder.rs` | Step 5 (proofs; consensus proof + diversity cert) | HONEST LIMITATION: structural checks only, no ECDSA dep — `UnverifiedSignatures` ceiling; cert TTL tiers = Python parity (§7) |
| `btcp_router.rs` (BTCPRouter: register_intent :154, btcp_score :169, select_route_type :192, create_route :298, update_status :347) | Step 6 (route tracking) + route selection; Step 0 not implemented (no registry gate in Rust — Python-only, P-PY-03) | MIN_BTCP_SCORE unified 0.10 (lib.rs:105) |
| `btcp_escrow_monitor.rs`, `finality_normalizer.rs` (max(A,B)), `behavioral_state_channel.rs` | Step 6 execution/settlement lifecycle | |
| `netting_engine.rs`, `blo_scheduler.rs` (BRT windows), `state_capsule.rs` (Water 4), `ooa_anchor.rs`/`shadow_observer.rs` (Water 2; ShadowSource.simulated flag :485), `genesis_commitment.rs`, `sybil_resistance.rs`, `validator_fee_calculator.rs`, `dispute_resolution.rs`, `btcp_version_handler.rs`, `btcp_failure_classifier.rs`, `master_equation.rs` (L5 C(t)/Θ(t)/T(t)), `signal_emitter.rs` (§14.2, 24 types) | supporting layers | `bin/router.rs`, `bin/escrow_monitor.rs` = runnable binaries |

19 spec modules + 3 GAP-RUST additions, as documented in lib.rs:7-16.

---

## 3. Intent §4.1 field-by-field parity — Python `BITPIntent` (core/btcp/modules.py:575-659) vs Rust `BITPIntentData` (rust/src/bitp_matcher.rs:27-64)

| §4.1 field | Python BITPIntent | Rust BITPIntentData | parity |
|---|---|---|---|
| action | `str = "SWAP"` (:609) | `action: String` = "SWAP" (:45, :90) | ✓ same default + same 5-value domain (SWAP/TRANSFER/LIQUIDITY/STAKE/BORROW) |
| value | `Optional[int] = None` (:610) | `value: Option<u128>` = None (:49, :91) | ✓ (legacy `magnitude: f64` carries matching info in both) |
| max_total_gas | `Optional[int] = None` (:611) | `Option<u128>` = None (:52, :92) | ✓ |
| min_finality | `str = "STANDARD"` (:612) | `MinFinality::Standard` enum (:54, :93) | ✓ FAST/STANDARD/SECURE |
| min_NL_score (min_nl_score) | `int = 300` ×1000 (:613) | `u16 = 300` (:57, :94) | ✓ |
| chain_pref | `Union[str, List[int]] = "OPTIMAL"` (:614) | `ChainPreference` enum Optimal/SingleChain/Allowed(Vec) (:59, :95) | ✓ semantics; encoding differs in commitment text (see below) |
| privacy | `str = "PUBLIC"` (:615) | `SpecPrivacy::Public` (:61, :96) | ✓ PUBLIC/ZK_CREDENTIAL/INVISIBLE |
| btcp_version | `str = "1.0.0"` (:616) | `SemVer::new(1,0,0)` (:63, :97) | ✓ |
| nonce | `int = 0` (:617) | `nonce: u64` (:42) | ✓ |
| behavioral_proof_root | `Optional[bytes] = None` (:629, §17 binding) | `behavioral_proof_root: H256` (required; :38) | ✓ semantics (H256::default ≡ None) |
| (hash inputs) | `hash()` = §4.1 set colon-joined via `_canonical_intent_field` (:641-659) | `types::Intent::hash` (:172-201) — different legacy field set, acknowledged in both | ✗ different byte streams (by design, append-only policy documented both sides) |

**Field set: PARITY (10/10 §4.1 fields in both).** `types.rs::Intent/IntentConstraints` also carries the full §4.1 set (types.rs:209-231) with legacy↔spec bridges (`PrivacyLevel::spec_code` :265-271).

**§17 CUT commitment — DIVERGENT (D4, demonstrated live):** `AkashicClipboard._commitment` (modules.py:784-813) claims "Byte-compatible with rust/src/bitp_matcher.rs::execute_cut" — **false**. Executed both encodings on identical intent (entity 0x11*32, assets AAA/BBB, mag 0.5, deadline 1000, all defaults): Python digest `c1bda0c5…cacdacaf` vs Rust-format digest `df7b0d6d…495d565da`. Root causes: Rust `H256::to_hex()` emits `0x`-prefix (types.rs:30) where Python uses bare `.hex()`; Rust `None`→`"none"` (:134,:137) vs Python `str(None)`→`"None"` (:803-804); Rust unset proof root → `"0x"+"00"*32` (:184) vs Python `"0"*64` (:798-799); chain_pref allow-list `ALLOWED[1,2]` (:116-122) vs Python `"1,2"` (:807-808). Python's own `BITPIntent.hash()` uses the "none" convention — the §17 commitment does not.

---

## 4. TS golden vector live run — chains/shared/canonical_bh.ts

Throwaway script `/tmp/sweepb/golden.ts` (bun): loops all 52 vectors in `tests/golden/vectors.json`, rebuilds the 93-byte payload from vector INPUT fields (payload_hex compared + sha3(payload‖0x00)→sense tie-in), then calls `canonicalBH` (canonical_bh.ts:91) and compares sense/antisense.

**RESULT: PASS 52/52, FAIL 0.** (Both sense and antisense byte-identical for every vector, including the 0.5-ulp truncation edge, lenient-hex edges, u32-max chain_id rejection path via RangeError at canonical_bh.ts:103-105.)

Corroboration (repo-owned): `tests/golden/test_golden_vectors.py` — **134 passed** (Python doc-exact rebuild, Python core builder, Python streamer builder, frozen reference pins incl. presence of the Rust pinned digests in hash_dna.rs, entity rules, event table, magnitude rule, Rust static layout check, TS execution). `tests/contracts/test_canonical_certificate_sol.py` — **38 passed, 0 failed** on real EVM (py-evm): CanonicalCertificate.sol golden-vector parity.

Prior-session claim re-verified: SENSE `bc417a52…` reproduction is consistent with this full-suite pass.

---

## 5. SDK surface analysis (post d4660f0 "isolate the four duplicate TS SDK copies")

**Five distinct SDK surface files remain** (verified by bun import of all five):

| surface | lines | SignalType union | status |
|---|---|---|---|
| `sdk/TrionSDK.ts` | 797 | 17 types: 8 registry members + 9 non-registry (BEHAVIORAL_TRUTH, SHADOW_CHAIN, LIQUIDITY_OCEAN, CHAIN_RELIABILITY, BTCP_ESCROW_EVENT, BTCP_TIMEOUT, GENESIS_COMMITMENT, TEMPORAL_ANOMALY, UNKNOWN) | **CANONICAL** |
| `sdk/src/index.ts` | 659 | 17 types — **set-identical to TrionSDK.ts** (programmatic diff: missing=∅ extra=∅); body is a near-verbatim copy (only `./generated_chain_ids` vs `./src/generated_chain_ids` import differs) | DUPLICATE (header present at :10-23) |
| `sdk/src/client.ts` | 338 | 17 types — set-identical to TrionSDK.ts | DUPLICATE (header ✓) |
| `sdk/src/trion-sdk.ts` | 326 | 20 types = 24-type registry **minus SOVEREIGN_BEHAVIORAL, ENERGY_PARTICIPATION, BIOLOGICAL_CAPITAL, CONSENSUS_ADAPTATION** | DUPLICATE (header ✓) |
| `sdk/src/trion.ts` | 311 | none — `signal_type: string` (:49) | DUPLICATE (header ✓) |

All four duplicates carry the `DUPLICATE — NOT CANONICAL (W4-Q)` header as claimed by d4660f0; `sdk/README.md` records the disposition (deletion deferred to W5-S; two battery tests pin them: `test_chain_registry_canonical.py`, `test_api_truth_boundaries.py`). `generated_chain_ids.ts` (129 consts, both copies) + `wasm/` are correctly NOT duplicates.

**Signal-type enum identity across copies: NO.** 3 of 5 surfaces agree (17-type mixed union); trion-sdk.ts carries a different 20-type registry subset; trion.ts has no union. Against the canonical 24-type registry (Python `core/master/signal_factory.py:52-76`, `SIGNAL_TYPE_COUNT==24` ids 0-23; Rust `signal_emitter.rs:35-92` 24/24 name+id identical — **Python↔Rust PARITY**): TrionSDK/index/client miss 16 registry types (FORK_DIVERGENCE, TRAJECTORY, NEGATIVE_SPACE, PHASE_TRANSITION, SYSTEMIC_RISK, LIQUIDITY_HEALTH, GOVERNANCE_SIGNAL, CROSS_CHAIN_COHERENCE, STABLECOIN_HEALTH, MEV_EXPOSURE, INSTITUTIONAL_BHV, REGULATORY_BHV, ECOSYSTEM_HEALTH, SOVEREIGN_BEHAVIORAL, ENERGY_PARTICIPATION, BIOLOGICAL_CAPITAL) and add 7 documented Python *overlay* types + 2 TS-only (TEMPORAL_ANOMALY, UNKNOWN). The wasm module exports `signal_type_count()==24` + `is_extended_signal` (19-23) — i.e. the wasm agrees with Python/Rust, the TS unions do not. Severity: medium (type-level drift; runtime strings still flow through).

**Wasm exports:** verified via `WebAssembly.Module.exports` on the checked-in `sdk/src/wasm/signal_processor.wasm` — 15 exports (compute_threshold, signal_emits, is_silence_type, is_valuation_type, apply_mf_correction, compute_pc_limit, brt_*, signal_type_count, is_extended_signal, **compute_coherence, shannon_entropy, memory**) — exactly matching the `.wat` and every TS call site (TrionSDK.ts:731, :757). **No nonexistent wasm exports.**

**Signing:** no private-key API, no `signMessage`/fabricated signatures anywhere in sdk/ (headers declare "never sign"; README trust model; wasm helpers fail with explicit rebuild messages). **No fabricated signing.**

---

## 6. Relayer verification (EVM + non-EVM)

- `node --check` on relayer/kms_provider.js, relayer.js, relayer_non_evm.js — **all 3 pass**.
- **Keccak derivation:** `ethAddressFromPublicKey` (kms_provider.js:390-407) — DER/SPKI-stripped to 65-byte 0x04 point, `keccak256(X‖Y).slice(-40)`, EIP-55 via `ethers.getAddress`; throws on non-65-byte/non-04 input (fail-closed). PEM path (:468-479) notes the old sha3-256 bug (S7) is fixed.
- **KMS signing correctness:** `derSignatureToEth` (:425-446) — DER→r‖s‖v, EIP-2 low-s normalization, v recovered by verifying against the derived address, **throws when recovery fails** ("KMS key and derived address do not match"). AWS KMS `MessageType::DIGEST` signs the exact 32-byte digest (:160-164). `KmsEthersSigner` (extends `ethers.AbstractSigner`, :496+) wraps it; wired in relayer.js:828-839 (`createSigner` → `new KmsEthersSigner(kmsSigner)`).
- **DRY_RUN fail-closed:** `DRY_RUN = !PRIVATE_KEY && KMS_PROVIDER === "env"` (relayer.js:70). DRY_RUN branch logs "would publish" and records `mode:"DRY_RUN"` state (:583-591) — never signs/broadcasts. Live-mode digest = `solidityPackedKeccak256(chainId, oracleAddr, txId, packed)` EIP-191-signed (:601-606) — matches the on-chain `publishSignal` reconstruction. Fail-closed validation before packing (:517, :327), malformed oracle responses never packed (:571), **SELF-HALT** when `/api/v1/self` unreachable (:716-718), invalid oracle responses skip entity without defaults (:739-742). relayer_non_evm.js mirrors SELF-HALT (:291-302); keyless mode emits **honestly-marked synthetic block-proof vectors** (`data_provenance:"SYNTHETIC_BLOCK_PROOF"`, `synthetic:true`, seed-commitment strands with an explicit "not canonical BH" note, :355-381) — no fake signing. **Intact.**

---

## 7. Cross-language matrix (§17)

| canonical object | Python | Rust | TypeScript | contracts | golden vectors | verdict |
|---|---|---|---|---|---|---|
| **93-byte BH (v1)** | `core/primitives/behavioral_hash.py::compute_behavioral_hash` + `bh_streamer.py::compute_bh` + `anima-service/faiss_service.py::canonical_bh` | `indexers/crates/trion-common/src/hash_dna.rs::canonical_bh` (all 21 crates) | `chains/shared/canonical_bh.ts::canonicalBH` | ABSENT by design — EVM consumes BH strands as opaque bytes32 (CanonicalCertificate.sol:31-34, H-07); `HashDNA.sol` is the keccak/v2-shaped 14-field form, not v1 | `tests/golden/vectors.json` (52) + `config/bh_schema_v1.json::test_vector` | **PARITY** (Python live 134✓, TS live 52/52✓; Rust **STATIC-ONLY** — source-order layout/truncation verified, no cargo) |
| **entity_id / bh_id (§6)** | `bh_streamer.py::_normalise_addr`+sha3 (:157-166); `behavioral_hash.py` | `hash_dna.rs::bh_id/normalise` (:302-320) | `canonical_bh.ts::entityIdFromAddr` (:82-85) | ABSENT (entityId is input bytes32) | `hash_dna.rs::cross_language_bh_id_vector` f9769049… (reproduced live in Python); vectors.json entity-rule vectors | **Rust↔Python PARITY; TS DIVERGENT on §6 40-hex-no-0x branch** (D5): TS hashes the raw 40 chars (562413dd…) where Rust/Python hash `"0x"+s` (f9769049…) — golden vectors never exercise this helper, so 52/52 doesn't cover it |
| **certificate payload (346-byte, §2 CANONICAL_CERTIFICATE)** | `core/consensus/certificate.py` (canonical encoder, TTL_TIERS_USD) | **PARTIAL**: `btcp_proof_builder.rs` — DiversityCertificate + TTL tiers only (test :337-346 = Python tiers 3600/86400/259200/604800 ✓); no 346-byte encode/verify | **ABSENT** (no TS certificate impl) | `contracts/solidity/libraries/CanonicalCertificate.sol` (**live-verified 38✓ on py-evm**), `contracts/cairo/src/trion_certificate.cairo`, SVM `btcp_common`/`btcp_escrow`, NEAR `trion_oracle.rs`, TON `escrow.fc`, `contracts/test/CertificateProbe.sol` | 346-byte golden payload in `tests/unit/test_certificate_domain_separation.py` | **Python↔Solidity PARITY (live)**; other-VM contracts STATIC-ONLY; Rust PARTIAL; TS ABSENT |
| **intent §4.1 (10 fields)** | `core/btcp/modules.py::BITPIntent` (+ `adapters/__init__.py::BTCPIntent`) | `rust/src/types.rs::Intent/IntentConstraints` + `bitp_matcher.rs::BITPIntentData` | **ABSENT** (SDK fetches routes; no intent object) | `contracts/solidity/BTCPIntent.sol` (6/10: action, magnitude≈value, maxTotalGas, minFinality, minNLScore, privacy; no chain_pref/btcp_version/nonce/proof-root); PVM `intent/src/lib.rs` (action, max_gas_usd, min_nl_score, nonce); TON `intent.fc` (minimal) | no cross-language pin | **Python↔Rust field-set PARITY (10/10)**; §17 CUT commitment encoding **DIVERGENT** (D4, live demo); contracts PARTIAL; TS ABSENT |
| **signal types (24, ids 0-23)** | `core/master/signal_factory.py` (24, SIGNAL_TYPE_COUNT=24) | `rust/src/signal_emitter.rs` (24/24 names+ids) | SDK unions: 17-mixed ×3 surfaces; 20-subset ×1; string ×1 — **no TS surface carries the 24**; wasm carries 24 | `TRIONOracle.sol` stringly `signalType` (no enum enforcement) | none | **Python↔Rust PARITY; TS DIVERGENT** (D6); wasm PARITY |
| **chain registry ids (129/18/40)** | `core/generated_chain_bindings.py` ← `config/chain_registry.json` | hardcoded per-crate consts — 29/29 sampled match registry ✓ | `sdk/src/generated_chain_ids.ts` + `chains/shared/generated_chain_ids.ts` (129 generated consts); frontends hardcode 129/18/40; trion-0g **live derivation** | contract chain ids passed as params | `tests/unit/test_chain_registry_canonical.py` (per sdk README) | **PARITY** (Rust static-verified; hardcoded = drift risk) |
| **magnitude formula (§4, log10(1001))** | `behavioral_hash.py:149-172` + `bh_streamer.py:217-218` (mag_max=1000) | all 21 crates deterministic log10(1001) ✓ (Hedera exception D2) | **ABSENT** — `canonicalBH` takes `magnitudeNorm` as input; TS never normalizes | `HashDNA.sol::normalizeMagnitude` = `raw × 10^(18-dec)` (WHITEPAPER_MD form) — different rule (v2-shaped) | vectors.json magnitude/clamp/zero/0.5-ulp vectors | **Python↔Rust PARITY** (Hedera D2, 3 proxies documented); TS input-only; contracts DIVERGENT-form |

**Frontend static checks (2c):** `frontend/src/lib/config.ts:28-30` and `frontend-institutional/src/lib/trion/client.ts:15-17` hardcode CHAIN_COUNT=129 / VM_FAMILY_COUNT=18 / INTEGRATED_CHAIN_COUNT=40 with registry-source comments; registry live counts = **129/18/40 exact** (18 VM families: EVM 71, COSMOS 20, MOVE 6, UTXO 6, +14 singles). Spot-checked rendered claims: frontend layout.tsx:29 ("129 chains and 18 VM families"), frontend-institutional Sidebar.tsx:132 ("129 CHAINS · 18 VMs"), frontend core_principles.tsx:180 ("8,256 bridge pairs eliminated" = 129·128/2 ✓). Constants are pinned, not runtime-derived; trion-0g/src/registry_counts.mjs **is** runtime-derived (live-verified 129/18/40, returns null→"unknown" on unreadable registry — no fabricated fallback).

**trion-0g (2e):** CLI = `node trion-0g/src/index.mjs <command>` invoked by the Flask oracle (index.mjs:7-16): chain_status / storage_store / storage_root / da_submit / da_status / compute_status / compute_infer / full_status; modules zg_chain/zg_storage/zg_da/zg_compute; RELAYER_PRIVATE_KEY-gated. **C++ files (5, for SWEEP-A cross-reference):** `docs/research/archive/signal_processor.cpp`, `signal-processing/src/fft_engine.cpp`, `signal-processing/src/signal_conditioning.cpp`, `signal-processing/src/sensor_interface.cpp`, `signal-processing/test/test_fft.cpp` (CMake project `signal-processing/`).

---

## 8. Divergences (new findings, severity-ranked)

| # | severity | finding | evidence |
|---|---|---|---|
| D1 | **HIGH** | **Hedera block_hash SHA3 substitution (§9 violation):** tx-level canonical_bh receives `bh_id(block_hash_hex)` — the 32-byte payload field holds SHA3-256(hash-hex-string), not the lenient-decoded chain hash. Deterministic but unreproducible by Python/TS — exactly what §9 forbids ("never a silent SHA3 substitution"). | trion-hedera/src/main.rs:235-239, :269 |
| D2 | **HIGH** | **Hedera magnitude scale:** divides by 1e18 ("EVM-style wei") while registry says decimals=8 — §4 rule violated; realistic tinybar values → magnitude ≈ 0. Code comment admits "tinybar differs". | trion-hedera/src/main.rs:129-138 vs chain_registry.json (Hedera dec 8) |
| D3 | **MEDIUM** | **Cross-pipeline block_hash/entity input divergence (Rust indexer vs Python streamer) for 4 families:** TON (Rust synthetic `ton_block:` vs Python real root_hash), Stellar/Pi (synthetic `pi_ledger:` vs Python `"0x0"`), PVM (synthetic vs real `chain_getBlockHash`), Aptos (own `block_hash` vs Python `previous_block_hash`). Same algorithm, different inputs ⇒ the two live pipelines emit **different BH digests for the same tx**. Also Sui entity: Rust `bh_id(digest)` (:151) vs Python `_synthetic_tx_sender` = sha3("sui:"+digest) — §6 says the latter. | trion-ton:231; trion-pi:233; trion-pvm:363; trion-aptos:227; bh_streamer.py:878,924,993,1135,823-838 |
| D4 | **MEDIUM** | **§17 BITP CUT commitment not byte-compatible despite docstring claim:** Python `AkashicClipboard._commitment` vs Rust `execute_cut` differ (0x-prefixes, "None" vs "none", "0"*64 vs "0x000…", "ALLOWED[a,b]" vs "a,b"). Live demo: `c1bda0c5…` vs `df7b0d6d…`. Cross-language clipboard ids can never agree. | modules.py:784-813 (claim) vs bitp_matcher.rs:170-192; demo in §3 |
| D5 | **MEDIUM** | **TS `entityIdFromAddr` missing §6 40-hex→0x normalisation:** unprefixed 40-hex EVM address hashes to a different entity_id than Rust/Python (562413dd… vs f9769049…). 0x-prefixed/case-insensitive paths are correct; golden vectors don't exercise this helper. | canonical_bh.ts:82-85 vs hash_dna.rs:313-320 / bh_streamer.py:157-166 |
| D6 | **MEDIUM** | **TS SDK signal-type unions diverge from the 24-type registry and from each other** (17-mixed ×3, 20-subset ×1, string ×1). d4660f0 isolated the copies but did not unify the enums. | §5 tables |
| D7 | **LOW** | **Stale docstring in bh_streamer.py:196-198** still claims "the Rust crates use a session-relative ratio — known divergence on their side" — outdated since the deterministic-magnitude fix (CANONICAL_BH.md §12). Also faiss.rs:75 doc comment still describes the old `max_90d` formula. | bh_streamer.py:196-198; trion-common/src/faiss.rs:75 |
| D8 | **LOW** | **VectorEntry.timestamp inconsistency:** trion-evm/trion-botchain store wall-clock in the FAISS metadata timestamp while the other 19 crates store block time. §5-permitted (metadata), but inconsistent. | trion-evm:800; trion-botchain:329 |
| D9 | **LOW** | **Rust BTCPRouter lacks the Step-0 registry-membership gate** (P-PY-03) that the Python orchestrator enforces fail-closed; Rust accepts any chain id at type level. | orchestrator.py:1028-1042 vs btcp_router.rs |
| D10 | **INFO** | Deterministic synthetic pseudo-events: cosmos proposer (et=6, mag=0.5 hardcoded), utxo coinbase (et=13, mag=0.0) — canonical-form but fabricated magnitudes, fine for determinism, worth documenting. | trion-cosmos:292-293; trion-utxo:113-114 |

**Verification discipline note:** Rust findings are static-only (no cargo in environment) per CANONICAL_BH.md §12's declared boundary; every Python/TS/bun/node claim above was executed live at HEAD c6c38e4.
