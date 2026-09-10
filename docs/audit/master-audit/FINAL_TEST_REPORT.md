# Final Test Report — Session Inventory (Baseline + Per-Wave Targeted Results)

**Task ID:** 9-c (inventory) + 10-b (final run) + 12-b (Wave-5 section) + 13-a (waves 5–7 final verification) · **Status:** **FINAL** — baseline, per-wave targeted results, the 10-b final full-suite run, the Wave-5 per-lane results, and the definitive waves 5–7 full-suite verification run (**1907 passed / 0 failed / 0 errors / 28 skipped / 1 xfailed**, Task 13-a) are all recorded below. No PENDING items remain.
**Environment:** /home/z/.venv Python 3.12.14; deps installed by Task 3 (incl. kyber-py/dilithium-py/pyspx for PQC, faiss-cpu 1.15.0, vyper 0.3.10 exact, web3[tester], py-solc-x). No cargo/go/func toolchains (Rust/Go paths are static-verified — see LANGUAGE_MATRIX). All targeted runs used `-p no:cacheprovider`; live-service tests boot real subprocesses on ephemeral ports and tear them down.

---

## 1. Baseline (pre-fix, Task 3 — the true full-suite state)

| Run | Result |
|---|---|
| Full pytest (Task 3 final) | **1650 passed / 113 failed / 28 skipped / 1 xfailed / 3 errors** in 198.54s |
| Composition of the 116 problems | 111 × tests/integration/test_anima_full.py (all ConnectionRefused to live FAISS :8000 — the file hardcodes BASE=127.0.0.1:8000 and never boots the service; sample TestHealth+TestIndexAdd 10/10 pass when the service runs) · 3 × test_beo_cross_chain_vm.py (need Flask+FAISS up) · 1 × anima_live_ingestion 60s-window load flake (passes in isolation in 61.3s) |
| Code bugs in the failures | ZERO — all environmental (verified by service-boot probes) |
| vs Task-2 cold baseline | 1086P/118F/32S/34E → +564 passed, −31 errors, −5 failed; the 1 xfail (INV-015 dispute-window unenforceable) now visible |

## 2. This session's targeted results (per fix wave)

| Wave | Scope | Result | Regression artifacts |
|---|---|---|---|
| 7-a (FAISS auth) | NEW tests/integration/test_faiss_auth.py | **11/11** (×2 runs, ~8s) | 401/503 matrix both modes, curl matrix live both modes |
| 7-a | anima_full TestHealth+TestIndexAdd vs live keyed :8000 | 10/10 | key headers proven end-to-end |
| 7-a | live_ingestion TestFaissConcurrent | 2/2 | self-booted keyed service |
| 7-b (Cairo) | NEW tests/contracts/test_birp_attestation_cairo.py | **69/69 checks, pytest 11/11** | self-attestation/tamper/replay/rotation battery + static source pins |
| 7-b | full tests/contracts/ battery | 69 passed, 0 failed | no regressions incl. escrow cairo 18/18 |
| 7-b | scarb builds | chains/starknet ✓ (was E0005); BIRP isolated crate ✓ under 2.8.4 + 2.10.1 | build-level regression for SEC-06 |
| 7-c (Flask) | NEW test_api_auth_failclosed.py + test_api_publish_hashing.py | **19/19** (failing-first pre-fix: 8/19 — the 11 failures were exactly the fixed behaviors) | fail-closed matrix + SHA3 golden vectors |
| 7-c | test_awa_freeze / test_api_truth_boundaries / wave4_api+btcp_api_surface / final_red_team | 26 / 34 / 52 / 26 — **157 passed across the Flask lane files** | keyed-write test updates |
| 7-c | -k "publish or blockchain or cex or webhook or cors or auth" | 41/42 (the 1 = pre-existing live-FAISS env failure) | cross-selection sanity |
| 7-c | live Flask boot smoke | GET /api/v1/health 200; POST key-unset → 503 auth_not_configured + WARNING log; keyed POST 200; no ACAO by default | boot-level evidence |
| 7-d (indexers) | tests/golden/test_golden_vectors.py + tests/unit/test_chain_registry_canonical.py | **150 passed** | static scans of every crate main.rs (context-0, no AtomicU64/.store, block-time markers, log10(1001)) |
| 7-d | test_chain_integrations.py -k rust/supervisor | 14 passed + **1 PRE-EXISTING failure** (test_evm_extras_supervisor_has_all_three_chains: BNB_TESTNET missing from supervisors/evm_extras_indexers.sh — fails at HEAD, untouched) | documented, not a regression |
| 7-e (key hygiene) | node --check + functional smoke (dummy key) | SYNTAX_OK; redaction + stderr gating proven; 0 key/WIF bytes in stdout | smoke captures |
| 7-f (escrow) | test_red_team_wave4 / pass3 / final_red_team | 46 / 9 / 26 passed | **test_same_cert_double_pay_across_two_deployments FLIPPED to the regression** (second deployment reverts; paid == amount; escrowB HOLDING) |
| 7-f | tests/contracts/ (source_sync twins+ABI pins, golden, oracle, vyper/sol/move/svm/ton/cairo tiers) | 69 passed | BTCPEscrow bytecode 33440→33618 hex chars; artifacts regenerated via compile.mjs (toolchain fidelity pre-flighted on pristine source) |
| 7-f | combined targeted run | **156 passed** | certificate domain separation + compile checks (solc 0.8.24 via_ir, solcjs 0.8.36, vyper 0.3.10) |
| 8-a (threading) | test_faiss_auth + test_no_sys_path_hacks | **13/13** | sys.path-free boot |
| 8-a | tests/adversarial/test_adversarial_suite.py | **18/18** (incl. the re-keyed 50-thread write burst: 0/50 → 50/50) | contention now measured, not auth |
| 8-a | api batteries (failclosed + publish + truth + awa) | **79/79** | consolidated Flask lane result |
| 8-a | live keyed FAISS :8000 → anima_full sample + concurrent classes | 13/13 + 4/4 | live_ingestion 2/2 (1 remaining failure = documented GitHub-API network flake, not auth) |
| 8-a | E2E single-script (keyed FAISS :8901 + Flask :5901) | **18/18** | public reads keyless, internal calls keyed, writes 401/503 without key, keyed writes land (bh ledger + FAISS index), ports released |
| 8-b (hedera) | golden + chain_registry | **150 passed** | no test pinned the old hedera behavior (verified by read-only grep) |
| 8-c (signal) | tests/unit/test_all_planes.py | **60 passed** (1 extended + 2 new tests: test_silence_payload_structured, test_validator_provenance_figures) | M-004/M-080 regressions |
| 8-c | tests/unit FULL | **1051 passed / 6 skipped / 0 failed** (incl. other lanes' in-flight files at that moment) | strongest unit-tier signal of cross-lane health |
| 8-c | test_signal_registry + trion_protocol five_plane_c/liquidity_ocean | 57 passed | signal registry integrity |
| 8-c | test_awa_freeze + test_no_sys_path_hacks | 28 passed | no sys.path regressions |
| 8-c | tests/master_formula_verification.py (script-style, direct run) | 105 passed / 0 failed | formula suite |
| 8-c | golden + invention_verification | 105 enforced / 44 passed | canonical invariants |
| 8-c | signal_factory __main__ self-test | 24/24 + 7/7 BTCP subtypes | factory-level self-check (provenance 6 records, validator_registry source asserted) |
| parallel lane (write-time) | NEW tests/unit/test_api_cold_start.py + tests/unit/test_cex_faiss_forward.py | **8P + 5P (13 passed, re-run at this file's write time)** | cold-entity 19 signal types 200 (both pre-existing 500s pinned fixed); CEX→FAISS forward payload schema pin |
| parallel lane (write-time) | tests/golden + test_chain_registry_canonical (re-run) | **150 passed** | confirms the algorand/aptos/cardano/pvm/sui/vechain verbatim-hash lane broke no canonical pin |

## 3. New test files added this session (inventoried)

| File | Tests | Covers |
|---|---:|---|
| tests/integration/test_faiss_auth.py | 11 | SEC-01/24 — FAISS auth matrix, both key modes |
| tests/unit/test_api_auth_failclosed.py | 19 | SEC-03/14 — Flask fail-closed default + CORS posture |
| tests/unit/test_api_publish_hashing.py | 6 | SEC-20 — SHA3-256 publish identity golden vectors |
| tests/contracts/test_birp_attestation_cairo.py | 11 (69 checks) | SEC-04/06/25 — BIRP mirror + attacks + source pins |
| tests/adversarial/test_red_team_wave4.py (modified) | 46 total | SEC-21 — incl. the flipped double-pay regression |
| tests/unit/test_all_planes.py (modified) | 60 total | M-004/M-080 — silence payload + provenance figures |
| tests/unit/test_api_cold_start.py (NEW, parallel lane) | 8 | cold-entity signal routes (both pre-existing 500s) |
| tests/unit/test_cex_faiss_forward.py (NEW, parallel lane) | 5 | CEX→FAISS forward payload contract |

## 4. Known test-visible residuals (verified pre-existing at HEAD, not this session's regressions)

- tests/integration/test_anima_full.py 111 env-gated failures (live FAISS :8000 by design of that file) — **CLEARED in the final run** (all 111 pass with the service booted keyed; see the final section).
- test_evm_extras_supervisor_has_all_three_chains — BNB_TESTNET supervisor gap (failed at the 7-d baseline) — CLOSED: PASSED in the 10-b final runs and in both 13-a runs; BNB Testnet is present in the committed `supervisors/evm_extras_indexers.sh` (R-17 closed in RISK_REGISTER).
- anima_live_ingestion 60s-window load flake + GitHub-API network flake — both RESOLVED in the 13-a final run: the GitHub leg now skips honestly (11-d rate-limit gate), and the clean-boot deadline flake did not recur (see the waves 5–7 final section).
- test_bh_ledger_cross_chain_coverage — pre-existing test-design gap — CLOSED by 11-d: the test self-supplies two-chain BH-ledger evidence and PASSED in both 13-a runs.
- INV-015 dispute-window xfail (intentional, honest).
- api-lane 500s observed by 8-c (/api/v1/signal/type/* COLD_START KeyError; GOVERNANCE_SIGNAL digest-overflow IndexError) — pre-existing at HEAD; FIXED by a parallel lane during this session and pinned by tests/unit/test_api_cold_start.py (8P at write time).
- Rust/Go/Cairo-contract-crate: untestable in sandbox (no toolchains) — the new Rust regression module (mev_detection_uses_canonical_byte_16) runs only when cargo exists.

---

## FULL SUITE — FINAL RUN (Task 10-b, post-fix tree, live services) — 2026-09-05, re-verified 2026-09-06 00:14 UTC

**Environment.** `/home/z/.venv` Python 3.12.14 · pytest 9.0.2 · faiss-cpu 1.15.0 · vyper 0.3.10 (exact). Both live services booted from the repo root in the same shell invocation as the pytest run (the sandbox reaps background processes at command end, so service + suite share one invocation):

- **FAISS service** — `FAISS_API_KEY=trion-test-key python3 anima-service/faiss_service.py` → FastAPI/uvicorn on `127.0.0.1:8000`; `/healthz` → `{"status":"ok"}` (auth middleware on, DB-less minimal boot).
- **Flask API** — `TRION_API_KEY=trion-test-key python3 -c "from api.app import app; app.run(host='127.0.0.1', port=5000, debug=False)"` → werkzeug on `127.0.0.1:5000`; `/api/v1/health` → `status: healthy`, oracle `TRION Protocol v2.0.0` (TimescaleDB features disabled — psycopg2 guarded).

**Command.** `cd /home/z/trion-core && FAISS_API_KEY=trion-test-key TRION_API_KEY=trion-test-key python3 -m pytest tests/ -q -p no:cacheprovider`

**Result.** **1831 passed · 2 failed · 27 skipped · 1 xfailed · 1 error · 17 warnings** — total tests collected: **1862**. Reproduced identically by the final-verification agent in an independent re-run: **463.16s (0:07:43)** for the original run and **485.55s (0:08:05)** for the verification re-run, identical counts on both. Captures: `/tmp/trion_final_suite.txt` (original) and `/tmp/trion_final_suite_10b.txt` (verification re-run) — numbers transcribed here.

**Delta vs the Task-3 true baseline (1650P/113F/28S/1x/3E, 198.54s, no services):**

| Metric | Baseline | Final | Δ |
|---|---:|---:|---|
| passed | 1650 | 1831 | **+181** |
| failed | 113 | 2 | **−111** |
| errors | 3 | 1 | **−2** |
| skipped | 28 | 27 | −1 (one skip-conditioned test executed under live services — favorable) |
| xfailed | 1 | 1 | INV-015, unchanged (intentional) |
| total tests | 1795 | 1862 | **+67** (65 new tests in 7 session-added files: faiss_auth 11 · api_auth_failclosed 14 · api_publish_hashing 5 · birp_attestation_cairo 11 · api_cold_start 8 · cex_faiss_forward 5 · self_verification_auth 11; +2 tests added into already-modified files) |

**Expected-movement check (from the 9-c placeholder):** anima_full 111 env-gated → **all 111 PASS** (108 formerly-failed + 3 formerly-error) · beo 4 → **3 PASS** (oracle_cross_chain_coherence, same_entity_six_vm_families, merge_via_common_funder) + 1 documented pre-existing gap (below) · live_ingestion 60s-window flake → still failing, now via the GitHub leg (a) · the flipped double-pay regression test passes inside the suite · new batteries all green. No failure outside the documented residual set.

**Failure classification — every remaining problem, named:**

| Test | Outcome | Category | Root cause & evidence |
|---|---|---|---|
| `tests/integration/test_anima_live_ingestion.py::TestAnimaLiveIngestion::test_live_ingestion_within_60s` | FAILED (full run AND isolated reruns) | **(a) live-network flake** (with a secondary (b) load-timing leg) | The only failing step in the full suite is the external-feed assert: `GitHub returned 0 events: []` (test:331). Live probe: `api.github.com/events` → HTTP 403 `API rate limit exceeded` with `x-ratelimit-remaining: 0` (the unauthenticated 60/hr quota for the shared egress IP is exhausted by the suite + streamer polls + external tenants — probe timeline during verification: 37/60 remaining at 00:26 UTC, 0 remaining at 00:29 UTC with reset ~47min out). `fetch_github_activity()` is untouched this session (the file's session diff is X-API-Key auth plumbing only — no change to any failing leg); every service-side step passes (healthz, /stats, /api/v1/health, streamer running, BH ledger > 0 — real blocks ingested, e.g. arbitrum 502162920). Passed in isolation at Task 3 when quota was available; isolated verification reruns failed on the same GitHub leg (once additionally on a step-4 `/stats` 10s timeout under cold-start streamer load — the same load-timing class as the (b) row). |
| `tests/integration/test_anima_live_ingestion.py::TestFaissConcurrent::test_stats_endpoint` | ERROR at setup (full run, both runs); **PASSED in isolation** | **(b) timing flake under contention** | The function-scoped `faiss_service_clean` fixture boots its own isolated FAISS subprocess on an ephemeral port with a **30s /healthz deadline**; under full-suite load (2 live services + 1862 tests) the boot exceeded 30s — `RuntimeError: FAISS service did not become healthy on port 38873. Process alive=True` — the service log shows a normal startup (no crash; faiss loads ~5s, PQC/ML-DSA-87 init, scheduler start). Isolated rerun: **1 passed** (90.26s combined module run during verification; 57.32s in the original 10-b run). |
| `tests/integration/test_beo_cross_chain_vm.py::test_bh_ledger_cross_chain_coverage` | FAILED (deterministic, both runs) | **(d) pre-existing test-design gap** | Asserts the GLOBAL `bh_ledger` covers ≥ 2 distinct `chain_label`s (test:391), but the suite's only BH-ledger writers — `test_anima_full.py` §4a/§4b/§45, every `/index/add_tx_bh_batch` call — submit `chain_label: "ethereum"` exclusively; the multi-chain tests (§2e cross-chain, beo six-VM, merge) use `/index/add`, which feeds the vector store, not the BH ledger. The ≥2-chain expectation presumes live multi-chain indexer/streamer traffic, which the DB-less minimal boot doesn't provide. Service verified CORRECT **independently by both runs**: direct two-chain experiment (distinct tx hashes — a shared tx hash is deduplicated by design — ethereum + solana `add_tx_bh_batch` → `/bh/stats`) returned `per_chain: {solana: 1, ethereum: 1}`. Failed at the Task-3 baseline too (then as connection-refused, FAISS not booted). |

**Session-caused regressions (category c): ZERO.** Every failure above is (a)/(b)/(d); the 2 failed + 1 error are all in integration files that were failing/erroring or service-gated at baseline, and no previously-green test appears in the failure list. All 116 baseline problems resolved to passes except the 3 classified above.

**Hygiene.** After each run both services were terminated by PID (verification re-run: explicit `kill` + `wait`, ports 8000/5000 confirmed connection-refused afterwards — a standalone nohup-boot attempt also proved the sandbox reaps background processes at command end, hence the single-invocation service+suite design), `.pytest_cache`/`.hypothesis` and all service/test runtime artifacts (`akashic_state.db`, `bh_ledger.db`, `cex_bh_ledger.db`, `self_verification.db`, `akashic_faiss.index`, `trion_archetype_centroids.npy` at root and under `anima-service/`, `akashic/*.db`, `data/trion_reputation_state.json`) were removed — `git status` contains source changes only (105 entries, the session's fix waves + audit docs; all runtime artifacts gitignored-verified before removal).

**Verdict.** The suite is **green modulo 3 classified environmental/pre-existing items**; the tree is ready for the coordinator commit, with the standing gaps unchanged: cargo check on `indexers/` (R-01 — the 10-b tron fix included), the GitHub-rate-limit leg of live_ingestion (retry when quota resets), and the beo coverage gap (needs either a second BH-writing test chain or live streamer traffic — owner decision, see RISK_REGISTER R-20…R-22 for the adjacent residuals).

---

## WAVE 5 — per-lane results (Tasks 11-a…11-d, recorded by 12-b) — the definitive post-Waves-5–7 full-suite re-run is recorded in the final section below (Task 13-a)

The 10-b final run above predates Wave 5. Each Wave-5 lane ran its own batteries plus a full `tests/unit` pass at its own close (the lanes landed in-tree concurrently, so the full-unit counts differ by what was merged at each moment — the definitive post-Wave-5 full-suite number is Wave 7's to produce). All runs `-p no:cacheprovider`; environment repairs were venv-only (11-b: eth-tester/py-solc-x/py-evm/vyper 0.3.10; 11-c: flask stack + httpx + ecdsa/web3/hypothesis/kyber-py — repo requirements untouched).

| Lane | Scope | Result | Regression artifacts |
|---|---|---|---|
| 11-a (signal taxonomy — M-073 ruling) | tests/unit/test_signal_registry.py +2 classes (+20 tests: TestM073RulingTaxonomy, TestSpecFaithfulBuilders) | prescribed battery 91P; 8-c-style battery 72P; consumer battery 159P; **FULL tests/unit 1107 passed / 9 skipped / 0 failed** | taxonomy arithmetic 19+10=29 / 27-name closed set / dual-family / all-27 classifiable / per-type payload fields / escrow-timeout-pathway fail-closed |
| 11-a | invention_verification + master_formula_verification + signal_factory `__main__` self-test | 44P / 105P / 24+7+7 self-test | tsc on TrionSDK.ts: only the 2 pre-existing errors (identical at HEAD) |
| 11-b (cairo corelib — R-16) | scarb build contracts/starknet AND contracts/cairo under scarb 2.8.4 AND 2.10.1 | **4/4 Finished** (sierra+casm, zero errors — the 34 pre-existing corelib-skew errors closed); twin byte-identity re-confirmed (cmp) | build-level regression for R-16 |
| 11-b | pytest tests/contracts/ | **69 passed / 0 failed** | incl. twin identity + static source pins of the migrated pattern; cairo-test runtime integration remains the documented pre-mainnet follow-up |
| 11-c (integrity residuals — R-20/R-21/R-22/R-14) | test_cex_faiss_forward.py +TestCanonicalL01Verification (4 new) + test_self_verification_auth.py | **20 passed** (was 16 pre-wave) | canonical-CEX construction pinned by importing the endpoint's OWN verify_bh_complementarity |
| 11-c | NEW tests/unit/test_core_faiss_auth.py | **10 passed** | 5 core/-side FAISS callers keyed (3-var order, blank→no header, key-resolved-once) |
| 11-c | NEW tests/unit/test_bh_streamer_fetchers.py | **6 passed** | TON per-seqno getBlockHeader + cosmos current block_id.hash + honest-"0x0" fallbacks |
| 11-c | streamer-adjacent battery (storage_integrity + backfill_chain_ids + golden vectors + chain_registry_canonical + no_sys_path_hacks + core_faiss_auth) | **215 passed** | R-14/R-20/R-21/R-22 cross-battery |
| 11-c | **FULL tests/unit** (at 11-c close) | **1092 passed / 9 skipped / 0 failed** | pre-11-a-merge tree state |
| 11-c | R-20 LIVE PROOF (keyed FAISS :8931 + Flask test_client, single-invocation) | unkeyed POST → 401; real `/api/v1/cex/ingest` (BUY 850k / SELL 1.25M / wash 60k) → forward 200 `stored:3, verified:3`; /bh/ledger rows + /bh/stats per_chain CEX_BINANCE: 3 | the verified counter 9-a saw stuck at 0 is 3/3 live |
| 11-d (test honesty — beo self-sufficiency) | tests/integration/test_beo_cross_chain_vm.py::test_bh_ledger_cross_chain_coverage | **1 passed in 1.04s** (live against booted FAISS) | self-supplies EVM ETH_MAINNET (chain_id 1) + SVM SOLANA_MAINNET (chain_id 900) rows via /index/add_tx_bh_batch before asserting global + per-entity coverage — closes the final run's (d) classification |
| 11-d | test_anima_live_ingestion.py step 7a | rate-limit skip logic verified (probes the exact connector URL/headers; skips ONLY on 403/429 + x-ratelimit-remaining: 0; other failures still fail) — external dependency, syntax-verified (py_compile) not executed | closes the (a) classification path honestly when the shared-egress-IP quota is exhausted |

**Wave-5 net adds:** 2 new test files (test_core_faiss_auth.py 10, test_bh_streamer_fetchers.py 6), +20 tests into test_signal_registry.py, +4 into test_cex_faiss_forward.py → **+40 tests**; tests/contracts re-run 69P/0F; per-lane full tests/unit 1092P…1107P / 9S / 0F. **The 10-b failure classifications: (d) beo coverage — CLOSED by 11-d; (a) GitHub rate-limit — honest skip added by 11-d (the underlying quota is external); (b) boot-deadline contention flake — unchanged (environmental).**

---

## WAVES 5–7 FULL SUITE — FINAL VERIFICATION RUN (Task 13-a, waves 5–7 tree, live services) — 2026-09-06, 04:05–04:18 UTC

**Environment.** Same as the 10-b final run: `/home/z/.venv` Python 3.12.14 · pytest 9.0.2 · faiss-cpu 1.15.0 · vyper 0.3.10. Both live services booted keyed from the repo root in the same shell invocation as the suite (single-invocation design kept per protocol; this sandbox instance demonstrably did not reap the background services between commands, but the pattern was unchanged):

- **FAISS service** — `FAISS_API_KEY=trion-test-key TRION_API_KEY=trion-test-key python3 anima-service/faiss_service.py` → `127.0.0.1:8000`; `/healthz` → `{"status":"ok"}`.
- **Flask API** — `TRION_API_KEY=trion-test-key python3 -c "from api.app import app; app.run(host='127.0.0.1', port=5000, debug=False)"` → `127.0.0.1:5000`; `/api/v1/health` → `status: healthy`, oracle `TRION Protocol v2.0.0` (TimescaleDB features guarded off).

**Command.** `cd /home/z/trion-core && FAISS_API_KEY=trion-test-key TRION_API_KEY=trion-test-key python3 -m pytest tests/ -q -p no:cacheprovider` (the verification re-run added `-rs` for skip transparency; no other flag differences).

**Result.** **1907 passed · 0 failed · 28 skipped · 1 xfailed · 0 errors · 239 warnings — 1936 tests collected — pytest exit code 0 — in 236.02s (0:03:56).** Reproduced identically by an independent verification re-run: **1907P / 0F / 28S / 1x / 0E in 231.62s (0:03:51), exit code 0** — counts identical, wall times within 2%. Captures: `/tmp/trion_final_suite_13a.txt` + `/tmp/trion_final_suite_13a_rerun.txt`.

**Delta vs the 10-b final (1831P / 2F / 27S / 1x / 1E, 1862 collected):**

| Metric | 10-b final | 13-a final (waves 5–7) | Δ |
|---|---:|---:|---|
| passed | 1831 | 1907 | **+76** |
| failed | 2 | 0 | **−2** — both resolved (table below) |
| errors | 1 | 0 | **−1** — the boot-deadline flake did not recur in either run |
| skipped | 27 | 28 | +1 — the GitHub leg now skips honestly instead of failing |
| xfailed | 1 | 1 | INV-015, unchanged (intentional) |
| total collected | 1862 | 1936 | **+74** |

**New-test arithmetic (exact, from `--collect-only` + def-level git diffs):** +74 = 5 new files (test_core_faiss_auth.py 10 · test_bh_streamer_fetchers.py 6 · test_api_signal_taxonomy.py 15 · test_schema_spec_tables.py 11 · test_trion_staking_vy.py 13 = 55) + 15 test defs added to test_signal_registry.py + 4 to test_cex_faiss_forward.py. (Bookkeeping note: the Wave-5 lane table above says "+20 into test_signal_registry.py / +40 wave net" — the def-level diff is authoritative: +15 registry defs (31 vs 16 at HEAD) → wave-5 net 35, wave-6/7 net 39, total exactly 74.)

**The three 10-b classified items — every one resolved:**

| 10-b item | 13-a outcome | Evidence |
|---|---|---|
| (a) `TestAnimaLiveIngestion::test_live_ingestion_within_60s` — GitHub 0-events assert | **HONEST SKIP** — the 11-d gate fired exactly as designed | Steps 1–6 (service healthz, 30s-window probes, `/api/v1/health`, BH ledger > 0) all passed, then step 7a: `fetch_github_activity()` returned empty AND `_github_rate_limited()` matched → `pytest.skip("GitHub API rate limit exhausted (shared egress IP) — live leg not verifiable this run")` (test:420). Live probe this session: `api.github.com` → HTTP **403**, `x-ratelimit-remaining: 0`, `x-ratelimit-used: 60/60`, egress IP 47.57.242.119 — exactly the skip condition; any other failure mode still fails the test (the gate fires only on 403/429 + remaining 0). |
| (b) `TestFaissConcurrent::test_stats_endpoint` — clean-boot 30s deadline exceeded under full-suite load (ERROR at setup in both 10-b runs) | **PASSED** in both 13-a runs | No error entries in either capture; the isolated-FAISS fixture booted within its 30s /healthz deadline under full-suite load both times. |
| (d) `test_beo_cross_chain_vm::test_bh_ledger_cross_chain_coverage` — global ≥2-chain BH-ledger expectation no suite test satisfied | **PASSED** in both 13-a runs — self-sufficient per 11-d | Live service log (in-suite): the test's own two-chain submission landed — `bh_ledger chain=ETH_MAINNET block=1 stored=1` + `chain=SOLANA_MAINNET block=1 stored=1` (unique tx hashes per run; the ledger dedups shared hashes) before the global + per-entity coverage asserts. |

**Failure classification: NONE REQUIRED — zero failures, zero errors, exit code 0.** Category (c) session regressions from waves 5–7: **ZERO** — trivially (nothing failed), and no previously-green test changed outcome; the only outcome movements are the two 10-b flakes resolving upward (fail→pass, fail→honest skip).

**All 28 skips, named and classified (every one environmental/honest; none caused by waves 5–7):**

- 19 × `tests/integration/test_deep_vm_and_zg.py` — "requires live oracle at ORACLE_URL" (env-gated class, unchanged from 10-b).
- 5 × `tests/unit/test_whitepaper_gaps.py` — "Requires LIVE=1 and running server" (env-gated, unchanged).
- 2 × `tests/integration/test_akashic_category4.py` — "live FAISS/Oracle stack + akashic/bh_ledger.db not running" (needs the extra akashic-DB boot mode, unchanged).
- 1 × `tests/integration/test_anima_live_ingestion.py:420` — the GitHub rate-limit honest skip (row (a) above).
- 1 × `tests/test_gk_living_security.py:913` — "FAISS HTTP unavailable (backfill load): 401 Unauthorized for `…/api/v1/living_security/…`" — the unkeyed backfill probe receives 401 from the now-keyed service and treats it as unavailable. Cosmetic skip posture, unchanged since the service was keyed in wave 7-a (the 401 is correct fail-closed behavior; exercising that probe's live leg would require sending the key — observation only, not a failure, not a regression).

**Warnings 17 → 239 (benign, explained):** the 13 new vyper-staking tests (12-c) compile Vyper source through eth-tester every run, emitting ~120 vyper-ast `DeprecationWarning`s per run (`ast.Str` / `node.n` / Python-3.14 advisories) on top of the pre-existing SELFDESTRUCT / ResourceWarning / PytestReturnNotNone set. No correctness impact.

**Wall time ~2× faster than 10-b (236.02s / 231.62s vs 463.16s / 485.55s).** Both 13-a runs agree within 2% and neither hit a timeout (no `--ignore` split was needed). The delta vs 10-b is consistent with the GitHub leg now failing fast under an exhausted quota (instant 403 → honest skip at step 7a) instead of 10-b's full-window + retry path before the step-8 failure, plus lighter egress contention this session.

**Hygiene.** Services terminated (`pkill -f faiss_service`, `pkill -f 'api.app'`), both ports verified connection-refused afterwards (curl rc=7 on 8000 and 5000). All runtime artifacts removed after gitignore-verification (`akashic_state.db`, `bh_ledger.db`, `cex_bh_ledger.db`, `self_verification.db`, `akashic_faiss.index`, `trion_archetype_centroids.npy`, `data/trion_reputation_state.json`, `anima-service/indigenous_knowledge.db`, `akashic/{bibl_patterns,crspr_adaptive,epigenetic_immunity}.db`; `.hypothesis/` is self-ignoring and was also removed). `.pytest_cache` was never created (`-p no:cacheprovider` throughout). `git status` = **54 entries, byte-identical to the pre-run listing** — waves 5–7 source changes only (signal taxonomy, cairo corelib, integrity residuals, API alignment, vyper staking, dead-code deletions, docs refresh).

**Verdict.** **The suite is fully green: 1907 passed, zero failures, zero errors, reproduced across two independent runs.** Both 10-b flakes are resolved in-tree (beo self-sufficient; ingestion honest-skip), all +74 wave-5–7 tests pass, and the tree is ready for the coordinator commit. Standing gaps unchanged: `cargo check`/`cargo test` on indexers/ + rust/ (R-01 — waves 5–7 verified to touch NO Rust paths: `git status --short | grep -E 'indexers|rust/'` → empty, so R-01's scope is exactly the waves 1–4 Rust edits), the external GitHub quota (resets hourly; the skip is honest), and the runbook fleet/ceremony/audit gates (R-03…R-07).

