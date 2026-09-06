# File Disposition — Session-Touched Files + Dead-Content Recommendations

**Task ID:** 9-c · **Scope:** (a) every file touched by the fix waves this session (git status vs c0ccb14: 79 modified + 1 rename + 4 new = 84 entries) with disposition and one-line evidence; (b) recommended dispositions for the repo's known dead/duplicate content areas from the deep read — **RECOMMENDATIONS ONLY** (Master Command §22: no blind deletion; nothing outside the fix lanes was touched this session).

All session changes are in the working tree (uncommitted at write time; coordinator commit pending). Dispositions for (a) are KEEP — every touched file carries a functional change with named test evidence. **Write-time note:** a parallel lane (no worklog entry at this file's write time) landed additional fixes in the tree during this session — cold-start signal-route 500s, the CEX→FAISS forward schema, keyed transduction-integrity calls, FAISS_SERVICE_URL resolution in self_verification_routes, and the algorand/aptos/cardano/pvm/sui/vechain verbatim-hash class fixes; they are included in §1 and verified green (tests re-run at write time: test_api_cold_start 8P, test_cex_faiss_forward 5P, golden+registry 150P).

---

## 1. Session-touched files (all KEEP)

### Lane 7-a / 8-a — FAISS auth boundary + key threading (SEC-01/24)

| File | Disposition | One-line evidence |
|---|---|---|
| anima-service/faiss_service.py | KEEP (MODIFY) | auth middleware enforce_api_key (:478) on 165 routes; FAISS_HOST default 127.0.0.1 (:11491) — test_faiss_auth.py 11/11 |
| api/faiss_client.py | KEEP (NEW) | shared X-API-Key resolution (FAISS_API_KEY→FAISS_SERVICE_API_KEY→TRION_API_KEY) for all internal FAISS clients — E2E 18/18 |
| api/app.py | KEEP (MODIFY) | SEC-03 fail-closed writes + SEC-14 CORS (7-c) + 21 FAISS call sites keyed (8-a) — test_api_auth_failclosed 19/19 |
| api/dashboard_routes.py | KEEP (MODIFY) | _proxy attaches key ONLY on FAISS URLs (never leaks to Oracle) — E2E matrix |
| api/cex_integration.py | KEEP (MODIFY) | SEC-15 resolving SSRF guard + keyed /index/add_tx_bh_batch POST (:565) — truth-boundaries 34P |
| api/socket_push.py | KEEP (MODIFY) | SocketIO origins from TRION_CORS_ORIGINS, else same-origin — CORS assertions |
| core/realtime/bh_streamer.py | KEEP (MODIFY) | FAISSAccumulator resolves key (:535) + flush header (:603) — keyed-flush E2E |
| indexers/crates/trion-common/src/faiss.rs | KEEP (MODIFY) | FaissClient api_key field + X-API-Key on both POSTs (:159/:187); is_healthy stays public — cargo check pending |
| anima-service/genesis_backfill_*.py (19) + backfill_entity_records.py | KEEP (MODIFY) | X-API-Key on every /index/add, /index/bulk_backfill, /archetypes/train POST |
| docker-compose.yml | KEEP (MODIFY) | 127.0.0.1-only port publish (both profiles) + FAISS_HOST/FAISS_API_KEY env + posture comment — YAML validated |
| .env.example | KEEP (MODIFY) | FAISS_API_KEY entry + resolution order + fail-closed TRION_API_KEY doc (stale :93 comment rewritten) |
| tests/integration/test_faiss_auth.py | KEEP (NEW) | 11 auth tests, subprocess boot, no sys.path hacks — 13/13 with hygiene |
| tests/adversarial/test_adversarial_suite.py | KEEP (MODIFY) | 50-thread write burst monkeypatches the key (measures contention, not auth) — 18/18 |
| tests/integration/test_anima_full.py, test_anima_live_ingestion.py, test_beo_cross_chain_vm.py | KEEP (MODIFY) | key headers on FAISS-bound calls (Flask calls untouched) — 13/13 + 2/2 live |

### Lane 7-b — Cairo BIRP / lib.cairo / test paths (SEC-04/06/25)

| File | Disposition | One-line evidence |
|---|---|---|
| contracts/starknet/src/BIRPAttestation.cairo | KEEP (MODIFY) | submit_proof verifies ECDSA over Poseidon('BIRP-ATT-V1',…) vs pinned pubkey; nonce burn — test_birp_attestation_cairo 69 checks, scarb 2.8.4+2.10.1 clean |
| contracts/starknet/src/lib.cairo, module_root.cairo | KEEP (MODIFY) | stale comment fixed / twin synced byte-identical |
| chains/starknet/src/lib.cairo | KEEP (MODIFY) | SEC-06: stale `pub mod cairo;` removed — crate compiles (was E0005) |
| chains/starknet/src/birp-bridge.ts | KEEP (MODIFY) | real (r,s) signing, fail-closed without BIRP_ORACLE_PRIVATE_KEY; no (0,0) placeholders — tsc no-new-errors |
| chains/starknet/src/{zero-bridge,loop,per-vm,full-zero-bridge}-test.ts | KEEP (MODIFY) | SEC-25: path → docs/deployments/evm_sepolia.json + graceful skip — all 4 run past load |
| tests/contracts/test_birp_attestation_cairo.py | KEEP (NEW) | Python mirror + attack battery + static source pins — 11/11 pytest |

### Lane 7-c — Flask fail-closed / CORS / SHA3 / SSRF (SEC-03/14/20/15)

| File | Disposition | One-line evidence |
|---|---|---|
| api/blockchain.py | KEEP (MODIFY) | _entity_to_bytes32/_commitment → sha3_256 (:242/:252) — test_api_publish_hashing 6 golden vectors |
| tests/unit/test_api_auth_failclosed.py | KEEP (NEW) | 19 tests; failing-first pre-fix run 8/19 (11 failures = the fixed behaviors) |
| tests/unit/test_api_publish_hashing.py | KEEP (NEW) | 6 SHA3-256 golden vectors for the publish path |
| tests/unit/test_awa_freeze.py, test_api_truth_boundaries.py | KEEP (MODIFY) | keyed-write updates so the AWA gate (not auth) is under test — 26P + 34P |

### Lanes 7-d / 8-b — Indexer integrity (SEC-05/17/18/19; hedera)

| File | Disposition | One-line evidence |
|---|---|---|
| indexers/crates/trion-ton/src/main.rs | KEEP (MODIFY) | real toncenter root_hash (tip + per-seqno); synthetic ton_block: deleted — golden+registry 150P |
| indexers/crates/trion-pi/src/main.rs | KEEP (MODIFY) | real Horizon ledger hash; synthetic pi_ledger: deleted |
| indexers/crates/trion-xrpl/src/main.rs | KEEP (MODIFY) | raw ledger hash verbatim (ledger.hash twin accepted); SHA3-substitution deleted |
| indexers/crates/trion-multiversx/src/main.rs | KEEP (MODIFY) | raw hyperblock hash verbatim; mx_hyperblock: fallback deleted |
| indexers/crates/trion-hedera/src/main.rs | KEEP (MODIFY) | Hashio block.hash verbatim; silent 0x0 → warn + "0x0"; re-encode dropped |
| indexers/crates/trion-hedera/Cargo.toml | KEEP (MODIFY) | hex workspace dep removed (only user was the dropped re-encode) |
| indexers/crates/trion-botchain/src/main.rs | KEEP (MODIFY) | MEV byte 17→16 + #[cfg(test)] regression mev_detection_uses_canonical_byte_16 |
| indexers/crates/trion-waves/src/main.rs | KEEP (MODIFY) | Burn arm 16→14; unreachable corrective deleted |
| indexers/crates/trion-cosmos/src/main.rs | KEEP (MODIFY) | proposer fallback mag 0.5→0.0; synthetic entry skipped + warn; et=6 name canonicalized |
| indexers/crates/trion-common/src/hash_dna.rs | KEEP (MODIFY) | 1-line pin assert event_type_name(16)=="MEV_CAPTURE" |
| docs/audit/canonical-sweep/SWEEP-B.md | KEEP (MODIFY) | Wave-2 refresh line + fixed rows for xrpl/pi/ton/mx/hedera; D2/D3-remainder/D4–D10 still marked open |

### Lane 7-e — Key hygiene (SEC-02/22)

| File | Disposition | One-line evidence |
|---|---|---|
| btc-tools/derive-address.mjs | KEEP (MODIFY) | stdout key/WIF redacted; DEBUG_KEYS=1 → stderr + warning — node --check + leak-check smoke |
| .gitignore | KEEP (MODIFY) | .env.railway ignored; !.env.railway.example un-ignored — git check-ignore both directions |
| .env.railway → .env.railway.example | KEEP (RENAME) | untracked from git, template stays tracked; local .env.railway remains on disk untracked |

### Lane 7-f — Escrow-bound certificates (SEC-21)

| File | Disposition | One-line evidence |
|---|---|---|
| contracts/solidity/BTCPEscrow.sol | KEEP (MODIFY) | _verifyCanonicalCertificate → escrowBoundEthDigestOf(payload, address(this)) — double-pay regression flipped to pass |
| contracts/solidity/libraries/CanonicalCertificate.sol | KEEP (MODIFY) | escrowBoundEthDigestOf + ESCROW_BINDING_DOMAIN keccak("TRION-ESCROW-BOUND-V1") |
| hardhat/contracts/{BTCPEscrow.sol, libraries/CanonicalCertificate.sol} | KEEP (MODIFY) | byte-identical twins (source_sync pins byte-identity) |
| contracts/solidity/compiled/*.json + evm-tools/compiled/*.json (5 each) | KEEP (REGENERATED) | compile.mjs regeneration; BTCPEscrow bytecode 33440→33618 hex chars; ABI pins green; pre-flight proved toolchain fidelity |
| tests/contracts/sol_helpers.py | KEEP (MODIFY) | ESCROW_BINDING_DOMAIN + optional escrow_address= signer param (None → plain digest keeps oracle tests unchanged) |
| tests/adversarial/test_red_team_wave4.py, test_red_team_pass3.py, test_final_red_team.py | KEEP (MODIFY) | _release_args escrow binding at all call sites; flipped regression — 46P + 9P + 26P |

### Lane 8-c — SILENCE payload / validator provenance (M-004/M-080)

| File | Disposition | One-line evidence |
|---|---|---|
| core/master/signal_factory.py | KEEP (MODIFY) | _derive_silence_payload (:334) + ETA_BLOCKS_PER_GAP=1000 (:321) + registry-first provenance (:410/:435) — test_all_planes 60P incl. 2 new tests |
| tests/unit/test_all_planes.py | KEEP (MODIFY) | +test_silence_payload_structured, +test_validator_provenance_figures; extended test_signal_factory |

### Parallel lane (landed during this session; verified at write time, tests re-run green)

| File | Disposition | One-line evidence |
|---|---|---|
| api/app.py (signal routes) | KEEP (MODIFY) | COLD_START KeyError + GOVERNANCE digest-overflow IndexError fixed — tests/unit/test_api_cold_start.py 8P (all 19 signal types 200 on a cold entity) |
| api/cex_integration.py (forward) | KEEP (MODIFY) | _forward_to_faiss now posts TxBhBatchPayload (chain_id/chain_label/block_num/entries) — tests/unit/test_cex_faiss_forward.py 5P (schema pin vs the endpoint models) |
| api/self_verification_routes.py | KEEP (MODIFY) | FAISS_URL resolution gains FAISS_SERVICE_URL precedence (was alias-only — env drift fixed); keyed by tests/unit/test_self_verification_auth.py (11P at write time) |
| core/physical/transduction_integrity.py | KEEP (MODIFY) | _faiss_headers() (:39) + X-API-Key on FAISS GET/POSTs (:159/:171/:194) — 8-a follow-up closed |
| indexers/crates/trion-{algorand,aptos,cardano,pvm,sui,vechain}/src/main.rs | KEEP (MODIFY) | verbatim real block-hash pattern extended to the SWEEP-B D3 remainder + same-class re-encode crates (warn + "0x0" when missing); golden + registry 150P at write time |
| indexers/crates/trion-{algorand,cardano,vechain}/Cargo.toml | KEEP (MODIFY) | hex dep dropped (only user was the removed re-encode) |

---

## 2. Dead / duplicate content areas — RECOMMENDED disposition (future cleanup pass)

Per Master Command §22 these are recommendations only: every DELETE requires proof-of-no-callers first; nothing was deleted this session except dead code arms inside files already being fixed (Waves unreachable fallback; synthetic-id generators; the stale `pub mod cairo;` line; the hedera hex re-encode).

| # | Area (deep-read evidence) | Current state | Recommended disposition |
|---|---|---|---|
| 1 | validator/cmd/trion-validator/crawler_coordinator.go — cmd-level STUB copy of the remediated internal/p2p crawler (hardcoded 0.50/0.40/SourceCount=0 placeholders) | stale duplicate; drift risk if anything calls it | **DELETE-WITH-PROOF**: grep callers of the cmd stub; if zero (expected — internal/p2p is the real path), remove in a housekeeping commit; else quarantine behind a deprecation comment |
| 2 | sdk/src — 4 overlapping TS clients; canonical is sdk/TrionSDK.ts (pinned by 2 tests) | deliberate consolidation deferral (W5-S) | **CONSOLIDATE** later: fold the 3 non-canonical clients into TrionSDK.ts façades or delete-with-proof per client |
| 3 | chains/near deploy_wasm.cjs vs deploy_wasm.mjs — near-duplicate deploy scripts; the .cjs hardcodes Replit-host absolute paths /home/runner/workspace/... (non-portable) | both tracked; mjs is the portable one | **DELETE-WITH-PROOF** the .cjs (no importers expected); keep the .mjs |
| 4 | Duplicate XSL/SBA implementations: extended/xsl_engine vs cross_species; governance/sba_engine vs extended/sovereign_behavioral; reconciled exports in extended/__init__ | dual implementations with reconciled exports | **KEEP + DOCUMENT**: pick the canonical module per concept, mark the other `# compatibility shim` (deleting risks import-graph churn; exports already reconciled) |
| 5 | core/physical/transduction_integrity.py — misnamed (docstring says self_verification.py); duplicate TI concept also in temporal_coherence.py | two files share the TI concept | **RENAME/DOC-FIX** in a docs pass; no functional change |
| 6 | mainmain_bootstrap.py — 152-chain display registry with sha3-derived synthetic chain ids + legacy duplicates (Aptos 5001 vs 20000) | self-labeled "display artifact" in comments | **KEEP (labeled)** or regenerate from config/chain_registry.json; do not delete — frontends consume it |
| 7 | trion-botchain vs trion-evm — BOT_CHAIN 677 is also in trion-evm's CHAINS ⇒ double BH rows if both run | config-level hazard (the MEV byte bug itself is fixed) | **OPERATOR GUIDANCE / CONFIG**: run one or the other per chain; add a startup warning or dedupe guard in a future pass |
| 8 | package.json dead script refs — `indexer.ts`, `client.ts`, `program/` don't exist in that dir | dead refs after CLEANUP-1 moved SVM programs to contracts/svm/programs/ | **CLEAN** in a housekeeping commit (remove dead script entries) |
| 9 | chains/starknet verify-contracts.ts / verify-all.ts — hardcode the expected deployer address (duplicating deployments JSON) | duplication risk on redeploy | **REFACTOR** to read the deployer from the deployments record |
| 10 | TimescaleDB — 17/35 tables declaration-only (schema.sql vs live writers) | documented per-table dispositions exist | **KEEP schema in-tree** (it is the normative DDL); keep the per-table writer labels accurate |
| 11 | Historical audit docs (docs/audit/*.md pre-dating the canonical sweep; TRION_AUDIT_REPORT.md root) | superseded banners present (TRION_AUDIT_REPORT.md header is exemplary) | **KEEP** — audit trail; ensure each carries a superseded/refresh pointer (SWEEP-B.md got its refresh line this session) |
| 12 | Runtime artifacts (akashic_state.db, bh_ledger.db, *.index, .hypothesis, .pytest_cache) | gitignored; recreated by test runs | **NO ACTION** — hygiene passes during the fix waves already removed caches; .gitignore covers the rest |
| 13 | vyper 0.3.10 — repo requires it exactly; undeclared in pyproject/requirements | dependency-declaration gap (Task-3 lesson) | **DECLARE** (add to dev deps) in a housekeeping commit — not done this session to stay in-lane |
| 14 | .env.railway (untracked local copy left on disk) | gitignored now; template example tracked | **LEAVE** local file; operators copy from .env.railway.example per its header |

---

## 3. Not touched, deliberately

- `rust/` crate (trion-btcp) — no fix lane touched it; 147 tests remain static-verified only.
- `validator/` Go code — fleet gap is operational, not code.
- `zk-circuits/` — blocked on ceremony.
- All doc-level contradiction sources (the three uploaded specs) — outside the repo.
- Historical `docs/deep-read/*.md` audit notes that mention `.env.railway` — left as historical records (only descriptive mentions, zero functional refs — verified in 7-e).
