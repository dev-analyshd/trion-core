# File Disposition — Session-Touched Files + Dead-Content Recommendations

**Task ID:** 9-c (original) · **Updated:** Task 12-a (Wave 7 §22 cleanup — §2 converted from recommendations into a disposition ledger: provable areas deleted with 9-point evidence, retained areas carry their blocking check) · **Scope:** (a) every file touched by the fix waves this session (git status vs c0ccb14: 79 modified + 1 rename + 4 new = 84 entries) with disposition and one-line evidence; (b) recommended dispositions for the repo's known dead/duplicate content areas from the deep read — recommendations as of 9-c, actioned where provable as of 12-a (Master Command §22: no blind deletion).

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

## 2. Dead / duplicate content areas — disposition ledger (§22 proofs run by Task 12-a)

Per Master Command §22 every DELETE requires proof-of-no-callers first. The 12-a pass ran the full 9-point proof (source / build-config / deploy / tests / scripts / dynamic loads / CI / integration / uploaded-spec) for every 9-c recommendation; results below. Nothing outside the recommendation areas was deleted. Deletions live in the working tree (uncommitted, restorable via `git checkout -- <path>`); post-deletion battery held at tests/unit 1136P/6S/0F + `import api.app` boot OK after each batch.

### 2a. DELETED (this session, 12-a) — all 9 checks passed

**#1 — `validator/cmd/trion-validator/crawler_coordinator.go`** (cmd-level stub copy of the remediated `internal/p2p/crawler.go`; hardcoded 0.50/0.40/SourceCount=0 placeholders). Replacement is pinned by `validator/internal/p2p/p2pgo_test.go` (real ANIMA-service crawler, CA/ CRED tests).
1. Source: zero references — every top-level identifier it defines (NLPSignal, CrawlerConfig, CrawlResult, CrawlerPool, NewCrawlerPool, crawlLanguage, updateCred, CrossSourceAgreement, DefaultCrawlerConfigs, CrawlerSelfTest) greps clean in the 3 sibling package files and repo-wide; `core/native_bridge.py` (:96/:177) and `core/master/channel_architecture.py` (:252) reference the pre-restructure path `go/crawler_coordinator.go` (nonexistent since the 2.0.0 restructure) — unaffected by this deletion.
2. Build configs: no config names the file — Makefile / railway-entrypoint.sh / ci-go.yml build the *package* `./cmd/trion-validator/`, whose `func main()` lives in validator_mesh.go and never calls CrawlerSelfTest.
3. Deploy refs: Dockerfile.railway copies `validator/` wholesale; no file-level reference.
4. Tests: no test references (internal/p2p tests exercise the real crawler, a different package).
5. Scripts: none (scripts/, root .mjs/.sh grep-clean, hidden dirs included).
6. Dynamic loads: none construct the validator/cmd path.
7. CI: no workflow step names the file (ci-go.yml = package-level build/test).
8. Integration: the cmd binary is the one-shot mesh self-test; nothing integrates the crawler stub.
9. Uploaded spec: M-233 / Channel-14 "Go crawler coordination" is satisfied by `internal/p2p/crawler.go`; no extracted-requirements mention of the cmd file.
Compile caveat: no Go toolchain in the sandbox (standing R-01-class gap) — deletion is an unused-file removal with zero symbol refs, so package compilation cannot regress; ci-go.yml `go build ./...` covers it in CI.

**#3 — `chains/near/deploy_wasm.cjs`** (CJS twin of the portable `deploy_wasm.mjs`; hard-requires `/home/runner/workspace/node_modules/…` → crashes on any non-GHA machine). The `.mjs` twin is KEPT (portable, has fs fallbacks).
1. Source: zero importers — repo-wide grep incl. hidden dirs finds only docs/deep-read descriptions and the file's own usage comment.
2. Build configs: no package.json script names it (chains/near/package.json scripts are cargo-only, pre- and post-12-a).
3. Deploy refs: none in Dockerfiles/compose/deploy/supervisors.
4. Tests: none.
5. Scripts: none.
6. Dynamic loads: none.
7. CI: none.
8. Integration: the NEAR deploy path of record is the `.mjs` — `docs/deployments/near_testnet.json` ("when_redeploying") names `chains/near/deploy_wasm.mjs` only.
9. Uploaded spec: no extracted-requirements mention.

**#8 — dead `package.json` script entries** (12 entries across `chains/{starknet,pvm,svm,sui,ton,near}/package.json` pointing at never-committed files: `indexer`/`client`/`dev`→indexer.ts|client.ts (6 dirs), `start`→indexer.ts (sui), `build:program`/`check:program`/`test:program`→`program/` (svm — CLEANUP-1 moved SVM programs to `contracts/svm/programs/`)). Live entries kept: execute/fund-check (starknet — files exist), cargo contract/oracle/contracts entries (near/pvm — dirs exist), ton echo stubs.
1. Source: no source invokes them — zero repo hits for `tsx indexer.ts` / `tsx client.ts` / `npm run indexer|client` outside the package.json files themselves and docs describing them as broken.
2. Build configs: referenced files don't exist in their dirs (deep-read 02 §179); tsconfigs use globs (`src/**/*`, `*.ts`) with no explicit file refs; root package.json scripts (`trion:index-*`) all resolve to existing files.
3. Deploy refs: none.
4. Tests: none.
5. Scripts: none (scripts/ grep-clean).
6. Dynamic loads: none.
7. CI: no workflow step calls them.
8. Integration: the live chain-adapter entrypoints are `execute.ts` + the Rust/Python indexers; no integration consumes the dead entries.
9. Uploaded spec: no extracted-requirements mention.
All 6 files re-validated as JSON (json.load + node parse) after the edit.

### 2b. Retained — blocking check / standing reason (original numbering)

| # | Area | Retained because (blocking check or standing reason) |
|---|---|---|
| 2 | sdk/src — 4 overlapping TS clients; canonical is sdk/TrionSDK.ts | check (1) fails: live consumers exist — `tests/unit/test_chain_registry_canonical.py` reads sdk/src/index.ts and pins sdk/src/generated_chain_ids.ts (:123/:231/:508), sdk/trion_sdk.py references the TS twins; disposition is CONSOLIDATE (deliberate W5-S deferral), and sdk/ is an actively-edited lane this wave — not a provable-dead deletion target |
| 4 | XSL/SBA dual implementations (extended/xsl_engine vs cross_species; governance/sba_engine vs extended/sovereign_behavioral; reconciled exports in extended/__init__) | disposition is KEEP + DOCUMENT (compatibility-shim marking is a code edit, not a deletion; deleting risks import-graph churn; exports already reconciled) |
| 5 | core/physical/transduction_integrity.py misnamed docstring; TI concept duplicated in core/physical/temporal_coherence.py | disposition is RENAME/DOC-FIX only — and core/ is an actively-edited lane (the file carries uncommitted keyed-FAISS changes from §1) |
| 6 | mainmain_bootstrap.py — 152-chain display registry | recommendation VOID: no such file at HEAD af5317b, in git history (`git log --diff-filter=D` clean), or the working tree — the only repo mention of the name is this ledger (presumably removed before the current git history); recorded so future cleanup passes don't hunt for it |
| 7 | trion-botchain vs trion-evm BOT_CHAIN 677 double-BH hazard | config/operator-guidance item (startup warning or dedupe guard) — nothing to delete; the MEV byte bug itself was fixed in 7-d |
| 9 | chains/starknet verify-contracts.ts / verify-all.ts hardcode the deployer address | disposition is REFACTOR (read deployer from the deployments record) — a code change, not a deletion |
| 10 | TimescaleDB — 17/35 tables declaration-only | KEEP: schema.sql is the normative DDL; per-table writer labels stay accurate (12-c pinned them with tests/unit/test_schema_spec_tables.py 11P) |
| 11 | Historical audit docs (docs/audit/*.md pre-canonical-sweep; TRION_AUDIT_REPORT.md root) | KEEP: audit trail with superseded banners — deleting history is not a §22 deletion target |
| 12 | Runtime artifacts (akashic_state.db, *.index, .hypothesis, .pytest_cache) | NO ACTION: gitignored, recreated by test runs; hygiene passes remove them (12-a cleaned caches again post-run) |
| 13 | vyper 0.3.10 undeclared in pyproject/requirements | DECLARE is a dependency *addition*, not a deletion — out of the 12-a deletion lane; stays a housekeeping recommendation |
| 14 | .env.railway untracked local copy | LEAVE: gitignored; operators copy from .env.railway.example (7-e) |

Out-of-lane observation for core/ owners (recorded, not actioned): `core/native_bridge.py` builds/runs `crawler_coordinator` from the pre-restructure `go/` path that no longer exists, so the live `go_crawler_selftest` API keys (`api/app.py` :4982, `api/dashboard_routes.py` :472) report `available:false` by construction; `core/master/channel_architecture.py` impl_paths for Channel 14 likewise lists `go/crawler_coordinator.go`. None of these referenced the deleted validator/cmd file, so the #1 deletion is independent of them.

---

## 3. Not touched, deliberately

- `rust/` crate (trion-btcp) — no fix lane touched it; 147 tests remain static-verified only.
- `validator/` Go code — fleet gap is operational, not code (12-a touched validator/ only to delete the dead cmd-level crawler stub in §2a; no functional validator code changed).
- `zk-circuits/` — blocked on ceremony.
- All doc-level contradiction sources (the three uploaded specs) — outside the repo.
- Historical `docs/deep-read/*.md` audit notes that mention `.env.railway` — left as historical records (only descriptive mentions, zero functional refs — verified in 7-e).
