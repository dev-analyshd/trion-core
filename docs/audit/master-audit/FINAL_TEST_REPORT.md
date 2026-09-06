# Final Test Report — Session Inventory (Baseline + Per-Wave Targeted Results)

**Task ID:** 9-c (inventory) + 10-b (final run) · **Status:** COMPLETE — baseline, per-wave targeted results, and the final full-suite run with live services are all recorded below.
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
- test_evm_extras_supervisor_has_all_three_chains — BNB_TESTNET supervisor gap (fails at HEAD) — note: PASSED in the final 10-b run (the supervisor gap appears to have been closed by a session lane; supervisor file is in the uncommitted tree).
- anima_live_ingestion 60s window load flake + GitHub-API network flake — still present in the final run as the (a)/(b) classification below documents.
- test_bh_ledger_cross_chain_coverage — pre-existing test-design gap (≥2-chain global BH-ledger expectation that no suite test satisfies); see the final run's classification table.
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
