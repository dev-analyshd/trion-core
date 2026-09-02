# Deep Read: tests/ + backtest/ — Agent 2-h

Scope: all 63 tracked files under `/home/z/trion-core/tests/` (~53 files) and `/home/z/trion-core/backtest/` (10 files), ~24,565 lines. Every file read (large ones chunked; JSONs parsed programmatically). Key suites **executed empirically** where deps allowed (numpy/pytest/hypothesis/eth-account/flask installed ad-hoc in sandbox; faiss/feedparser/kyber-py stack NOT installable → those suites characterized by reading).

---

## 1. Overview

| Area | Files | Nature |
|---|---|---|
| tests/unit/trion_protocol/ | 13 test modules + `__init__.py` | Real production imports (`core.*`), plain pytest; the **"549 passed"** suite |
| tests/unit/btcp_continuum/ | 5 phase files | Phase 0–5 spec tests; phase1 = Solidity **source-text grep audit** |
| tests/unit/ (root) | 8 files + ANIMA_STRESS_REPORT.md | Mix: real unit tests, 2 pure tautologies, 1 broken script, 1 monitor script |
| tests/adversarial/ | 6 files | Real ECDSA/DDoS/proof/boundary tests + 4 protocol-health modules |
| tests/integration/ | 9 files | Live-stack HTTP suites (anima_full 45 sections), mocked hermetic suites, live-boot subprocess suite |
| tests/crossvm/ | 2 files | "On-chain" Solana↔BOT demos w/ **hardcoded foreign-machine paths + hardcoded BTCP components** |
| tests/ root | 13 files | golden_test.py, master_formula_verification.py, stress/large suites, scripts |
| backtest/ | 10 files | Circular original backtest + never-run "non-circular" successor + committed degenerate results + fabricated-looking on-chain proof |

**Empirically verified in this sandbox:**
- `pytest tests/unit/` → **555 collected**; run (minus 2M-hash stress test): **545 passed, 3 failed (all PQC-dep), 6 skipped**.
- `pytest tests/` (unit+adversarial+root, crossvm/integration ignored): **723 collected** → 708 pass, 7 fail, 7 skip.
- `pytest tests/` full tree (conftest ignores applied): **930 collected**.
- `python tests/master_formula_verification.py` → **"104 passed, 1 failed"** (❌ L4.7 PQC all-active L3 = 0.90).
- `python tests/unit/bh_cross_language_vector.py` → **FileNotFoundError** (wrong schema path).
- Merkle root of `backtest/results/merkle_proof.json` **recomputes exactly** from its 40 leaves; onchain_proof.json root **does not match** it.

---

## 2. Per-directory findings

### 2.1 tests/unit/trion_protocol/ (14 files) — the "549 passed" suite

- **Docstrings are stale**: nearly every file claims to test `src/akashic/archetypes.py`, `src/planes/mental/m_engine.py`, etc. (legacy layout removed in 2.0.0 restructure); actual imports are `core.akashic.archetype`, `core.mental.confidence`, … — imports are correct, docstrings lie about location (e.g. test_archetype_engine.py:2-4, test_conformal_predictor.py:2-3, test_consensus_bft.py:2-4, test_feature_extractor.py:2-3, test_five_plane_c.py:2-3).
- **test_archetype_engine.py** (96 L): structural checks on 12 archetypes; real `match_archetype` including exploit-φ→DANGER/CRITICAL case. Decent.
- **test_bh_collision_resistance.py** (287 L): honest epistemic disclaimer ("empirical stress test, NOT a mathematical proof"). **Circularity**: `_build_payload`/`_bh_sense` (lines 53-86) **re-implement** the BH construction ("mirrors compute_behavioral_hash exactly") — only `EventType` is imported from production. If production encoding changed, this test still passes. The 2,000,000-sample stress test (test at line 185) is deselected-in-practice (I deselected it; would add ~1-2 min); included in the 555 count.
- **test_birp_dna_code.py** (263 L): good pytest suite over `core.novel.birp` DNA_Code registration/rotation/verification incl. wrong-code, short-code, missing-code failures. Constants pinned to whitepaper (7-day quarantine, 90-day rotation, 0.67 quorum).
- **test_conformal_predictor.py** (86 L): M(t)/PI/observer-effect unit tests, incl. single-sample, empty-baseline, too-few-samples fallbacks. Real logic, weak assertions (mostly "is a float in [0,1]").
- **test_consensus_bft.py** (108 L): Σ(t)/HHI/diversity-weight; bootstrap <10 validators disclosure; HHI equal-stake exact formula check. Good.
- **test_extended_payload.py** (231 L): 176-byte v2 payload offset-by-offset layout tests, XOR invariant break tests, domain separation, replay nonce, all 20 event types parametrized, validation rejections. **Note: DOMAIN_MAGIC == b"TRON"** (line 68) — 4-byte magic spells "TRON", not "TRION" (probably deliberate 4-byte fit; worth flagging).
- **test_feature_extractor.py** (136 L): Φ f1–f5 real checks (entropy uniform=max, concentrated=0; counterparty single=0). f6–f9 only "are floats".
- **test_five_plane_c.py** (108 L): C(t) master equation — weight profiles sum to 1, θ dynamic range, SILENCE when low, limiting plane = weakest weighted. Good.
- **test_governance_modules.py** (275 L): adaptive consensus, right-to-invisibility (SQLite persistence + state machine), elder wisdom (3× stake), Love protocol (F=min of 6 pillars; collapse). Solid.
- **test_held_out_backtest.py** (118 L): tests ONLY the dataset split (determinism, disjointness, 20/10, 30 exploits) and statistical helpers (Wilson/Cohen's d/bootstrap). **It never verifies the recall/F1 claims** — the 100%-recall number is nowhere tested.
- **test_property_based.py** (288 L): Hypothesis property tests (payload=93B, 32-B strands, XOR invariant, determinism, monotone normalization, 176-B extended). High quality; needs hypothesis dep (installed ad-hoc; declared in pyproject per CHANGELOG).
- **test_validator_registry.py** (222 L): SQLite-backed registry; 100 validators/4 continents launch threshold; Σ bootstrap 0.25 disclosure. Good.

**Verdict on 549 claim**: 555 collected = 549 pass + 6 skip requires the PQC stack (kyber-py/dilithium-py/pyspx) installed; in bare env 3 tests fail (test_stress.py::test_lss_full_sec…, test_whitepaper_gaps PQC ×2). The 6 skips are all live-service gates (5× "Requires LIVE=1 and running server" in test_whitepaper_gaps.py:641-676; 1× "Oracle API not running on :5000" in test_stress.py:364) — the auto-skip claim is **TRUE**.

### 2.2 tests/unit/btcp_continuum/ (5 files)

- **test_phase0.py** (586 L): Hash_DNA spec vectors (determinism, nonce/entity/chain separation), magnitude normalization (6→18 decimals), domain separator, 7-plane weights pinned (0.20/0.10/0.10/0.15/0.20/0.20/0.05), 7 MF detectors T1–T7 with weights. Real modules (`core.primitives.hash_dna` — **a second, parallel BH implementation** vs `core.primitives.behavioral_hash` used by trion_protocol tests).
- **test_phase1_contracts.py** (358 L): **contract audit by source-text grep** — reads .sol files and asserts strings exist ("revertEmergency", "PENDING_AKASHIC", "7 days"); `test_emergency_callable_by_anyone` regex-parses the signature for absence of modifiers. No compilation, no behavior. Better than nothing; does not prove contract semantics.
- **test_phase2_modules.py** (517 L): real Python modules — router weights, escrow state machine (lock/verify/release, timeout, **cascade revert**, pending-akashic, 7-day emergency escape via time-faked `lock_timestamp`), BIBL endpoint diversity/fork suspension, proof builder/quorum/expiry, BITP complement, netting, aggregation, OOA, shadow observer. Good.
- **test_phase4_continuum.py** (275 L): CONTINUUM engines (BID buy/sell direction, CME complement, PMO, BDC credit, thermodynamic settlement gates, CCP split). Real.
- **test_phase5_integration.py** (468 L): full in-process pipeline Hash_DNA → BIBL → route → escrow → BID/CME/PMO/BDC → settlement → CCP → release, plus failure/cascade/private-BIBL/sybil-5-layer variants. **The genuine end-to-end test** — but entirely in-memory Python; no chain, no FAISS.

### 2.3 tests/unit/ root files

- **test_all_planes.py** (770 L, 52 tests): "Tests every whitepaper claim that is implemented" — L0→L9 real imports (BH, BEO, Φ, MF, NL, ANIMA bootstrap/live, M, Σ, K commit-reveal, C(t), signal factory, BTCP score, GK, CRISPR, genesis, BIBL, resonance, evolutionary fitness, temporal coherence, transduction, resurrection, fork resolution, trajectory anomaly, source credibility, reflexivity, intelligence maintenance, epigenetic AWA freeze, HHI, slashing (50% coordinated permanent), consensus degradation, biological capital, XSL vaquita, energy participation, SBA stable/hostile, information conservation via real `AkashicConservationLedger`, entropy gate). High-quality coverage; test data is hand-crafted (e.g. "Switzerland" with gini 0.78 — vibes, but only affects inputs).
- **test_stress.py** (477 L): BH XOR/collision/tamper/perf (<10ms target), LSS 100 entities (PQC==1.0 → env-dependent), GK 1000 evolutions, CRISPR signatures, epigenetic, mitochondrial, bootstrap monotone, 20 event types, concurrency, live-API test (proper skip). **Three tautologies**: `test_p_break_monotone_100_generations` (line 147: p = exp(-gen·0.01) computed *in the test*), `test_phi_healthy_vs_manipulated` (lines 323-331: hand-picked constants [0.92…] vs [0.10…], means compared — no production code), `test_information_conservation` (lines 404-414: I += 10+2−1−0.01 loop — arithmetic, even though the real `core.primitives.thermodynamics` module exists and is used elsewhere).
- **test_whitepaper_gaps.py** (682 L): L4.5 Kolmogorov complexity, L4.6 SEC=LSS·PQC·CC (PQC exact 0.90 at L3 — the env-dependent failures), L4.8 geographic HHI enforcement, 7-step slashing flow incl. quorum 67%, accused-can't-vote, HHI blocks slashing, appeal −50%, permanent ban no appeal; intelligence maintenance IM formula/statuses; LIVE-gated endpoint tests. Real and specific.
- **test_trading_signals.py** (131 L): pattern archetypes (8), signal engine SILENCE/MANIPULATION_ALERT gating, agent LONG/WAIT decisions, FAISS-vector alignment. Real.
- **bh_accumulation_test.py** (196 L): **not a test — a live monitor** (polls FAISS :8000, tails /tmp/trion-rust-logs/trion-evm.log); prints hard-coded "38 non-EVM relayers / 100+ total chains" regardless of reality; SyntaxWarning `\|` at line 78; collected by pytest only as a warning (no test functions).
- **bh_cross_language_vector.py** (130 L): **BROKEN** — `SCHEMA_PATH = parent³/"bh_schema_v1.json"` (line 17) but schema lives at `config/bh_schema_v1.json` → FileNotFoundError on run (verified). Not pytest-collected (name doesn't match patterns), so the breakage is invisible to CI. The adversarial matrix test uses the correct `config/` path.
- **ANIMA_STRESS_REPORT.md** (209 L): genuinely honest stress report (2026-07-20): 35,899 vectors, 417 rps reads, **13 rps write ceiling**, §11 ANIMA 0% after backlog, **Bug 1: `/api/v1/security/crispr/library` AttributeError `_signatures`**, **Bug 2: fork/resurrection/convergence endpoints 0% success at 60s timeout** (event-loop blocking). This file is the most candid artifact in the repo.

### 2.4 tests/adversarial/ (6 files)

- **test_adversarial_suite.py** (677 L): the strongest adversarial file. Real secp256k1 ECDSA via eth_account (high-s malleability twin with v-flip, v∉{27,28}, zero-address, nonce replay), BTCP proof verifier using **real `zk.merkle_root`** (tampered root, 2/5 vs 4/5 quorum, wrong chain, expired), DDoS (1000-request health flood, monkeypatched rate limiter → 429, 50-thread FAISS writes ≥80% + alive), boundaries (C=0/1/Θ exact, Love 0/1, AWA HHI>4000 EMERGENCY, quorum<2/3 SUSPENDED). Caveats: the signature/proof **verifiers are re-implemented in the test** ("mirrors the validation rules TRION's smart contracts enforce") — they test a mirror, not the Solidity; test_signer_zero_address_rejected lines 354-361 contains a pure tautology segment (`is_valid = addr==0; assert not is_valid`). DDoS tests need the full Flask/FastAPI stack (feedparser etc.) — failed in sandbox at import of `api.app`/`faiss_service`.
- **test_adversarial_matrix.py** (236 L): BH domain separation/strand tamper/event-type; manipulation detectors (wash mf=0.56, oracle mf=1.0, gov-capture formula, MEV, fake volume); observer effect, source poisoning escalation, PC limit; GK stale snapshot; **PQC downgrade (env-dependent failure)**; chameleon freeze; SILENCE; falsifiability registry self-check; init-valid gating; BH schema enum cross-check. Two filler "tests": `test_wrong_domain_separation` (hashlib trivia, no TRION code) and `test_replay_detected` (creates own SQLite table, asserts UNIQUE constraint — tests SQLite, not TRION).
- **test_protocol_distribution_coherence.py** (164 L): JSD properties (identity=0, symmetry, bounded), DC engine baselines/attacks. Real, good. (Named "adversarial" but is a functional unit test.)
- **test_protocol_health.py** (201 L): grade mapping parametrized, role coherence, user quality, recommendations, weights=1.0, engine smoke w/ empty DB. Real.
- **test_protocol_role_classifier.py** (169 L): 7 roles + UNKNOWN from event-count patterns; MEV_BOT/HIGH risk; ambiguous → low confidence; batch. Real.
- **test_protocol_segmentation.py** (135 L): pure helpers (count/parse/stats), SubEntity construction, DB-absent graceful behavior, caching. Real. `test_segmenter_global_activity_live` etc. touch the real bh_ledger.db path (side-effect-lite).

### 2.5 tests/integration/ (9 files)

- **test_anima_full.py** (2,477 L, 141 tests in 45 classes): the big live FAISS (:8000) suite — health, index add/batch/tx_bh, similarity, archetypes, ANIMA formula (A_adj = a(1−0.5r) exact), CRED decay, reflexivity, NL, liquidity ocean, LSS 8-component, GK, immune, epigenetics, noise, mito, BEO clusters, PHI weights, conservation, fitness, thermodynamics/lifecycle, conscious annotations/elders, spiritual diversity, publishing, BTCP routing, genesis locking, audit engine, agent validation, trading signals, SBA, slash/dispute, ZK behavioral proofs (offline), jurisdictional routing, fork/resurrection, bootstrap, 3 concurrent-load sections (1000 adds/reads/herd/mixed storm ≥70-75%), E2E pipeline. **No skip guard for missing service** (except optional-import skipifs) → fails wholesale without the stack. timeout=90s per call. This is the suite that would justify "system works", and it is *not* part of the 549/671 numbers unless run with live services.
- **test_anima_live_ingestion.py** (513 L): **best-engineered file in tests/**: boots FAISS as an isolated subprocess (tempdir index/DBs, free port, /healthz poll), starts BH streamer (real EVM RPC, 7 chains), then exercises every ANIMA connector with REAL HTTP (GitHub, news RSS, GBIF, SEC EFTS, arXiv, per-CIK). 60s budget. Genuinely live.
- **test_akashic_category4.py** (1,221 L): live-stack gated (skipif port 8000 + bh_ledger exists). T4.1 thermodynamic deletion: runs `runghc math/formal_verification.hs` — **stale path** (file moved to formal/src/TRION/Theorems.hs in 2.0.0) → that step fails/errs; probes DELETE routes (404/405 expected); mitochondrial `append_only_akashic`; SQLite UNIQUE as deletion barrier; direct RW probes of bh_ledger. T4.2 append-only, T4.3 fork resistance, T4.4 scalability, T4.5 cross-chain consistency.
- **test_beo_cross_chain_vm.py** (478 L): §1 real formula test (5 wallets/5 chains, CF=1.0); **§2 "byte-for-byte identical beo_id across 6 VMs" is a tautology** — it submits the SAME entity_id string with different chain_id/vm_type and asserts the deterministic SHA3 beo_id matches; the VM fields don't feed the hash (lines 174-228). §3 BEO merge via common funder against live FAISS.
- **test_btcp_cross_chain_e2e.py** (578 L): in-process, "ONLY real TRION Python modules — no mocks": BIBL state for ETH↔Arbitrum, route selection, BTCP score in [0,1], proofs generated+verified, `assets_bridged is False`, route types, gas bounds. Good, in-memory only.
- **test_chain_integrations.py** (727 L): **hermetic by mocking** — "All tests stub the actual network calls… Use LIVE=1". `_mock_post` returns the chainId from its own URL→id map (self-fulfilling liveness), oracle getCode always returns bytecode, FAKE_STATE files with per-chain φ (incl. relayer state where eth-sepolia is REJECTED "Insufficient quorum"). In LIVE mode, missing state files skip. Honest about it in the header, but citing this file as "chains integrated & verified" would be misleading. Mock data also embeds chain-ID chaos (SVM chains [103], PVM [901] vs 900/25000 elsewhere).
- **test_deep_vm_and_zg.py** (700 L): StarkNet/TON/SVM f6-f9 entropy semantics — **entropy helpers re-implemented in the test "mirrors all indexers"** (lines 39-58) → circular vs the Rust indexers; API 38-endpoint smoke (LIVE-gated for 2 classes); 0G integration; FAISS payload schema; epigenetics; agent train. LIVE-gated parts skip without oracle.
- **test_e2e_full.py** (800 L): live-stack script (excluded from pytest via conftest): 14 sections. "65 formulas verified" = reads `/api/v1/whitepaper/coverage` and asserts self-reported count ≥65 (line 628-631). "Attack library — all 32 simulations": asserts `attack_count >= 22` (line 527-528) while the docstring says 32. §9 claims "All 35 chain indexers confirmed" via BH ledger counts. §6 hits live RPC for contract auditor; §7/13 0G; §12 relayer receipts.
- **test_vision_expansion.py** (724 L): 9 new modules (vulnerability library exactly 20 patterns/4 criticals, auditor report, 12 archetypes, epigenetic, thermodynamic extension, lifecycle, UBL, etc.). Real imports, hard-coded counts (excluded from default collection).

### 2.6 tests/crossvm/ (2 files)

- **run_btcp_crossvm_full.py** (933 L) & **run_btcp_crossvm_hybrid.py** (583 L): both **cannot run in this repo** — `WORK_DIR = /home/user/.super_doubao/super-doubao-runtime/workspace/...` and `compiled_contracts.json` loaded from that foreign path (full:90-95, hybrid:47-52). The path betrays origin in an external AI-coding sandbox ("super_doubao" = Doubao runtime) and was never cleaned. Env keys properly externalized ("PHASE-1-SECURITY"). BOT Chain (rpc.bohr.life, 968) EVM side is real deploy/lock/release; Solana side = real tx construction + simulateTransaction only ("release — SIMULATED", "would be released").
- **The Cross-VM BTCP Score is fully hard-coded** (full:721-728; hybrid:411-418): `nl=0.75, gas_norm=0.85, finality=0.90, cc_coh=0.92, beo_cont=0.95, mf=0.00` → 0.8655 — **exactly the 0.8655 quoted in README's "Cross-VM Validation" table**. Line 469 even passes `865500` as coherence. The README's "BTCP Score" column is a hand-typed constant, not a measurement.
- `beo_from_evm_address` == `beo_from_solana_address` (identical bodies) — "cross-VM BEO" = hashing the same string.

### 2.7 tests/ root-level files

- **golden_test.py** (327 L, ~30 checks = "30/30 Golden Test"): boots real FAISS (uvicorn :8010) + Flask oracle (:5010) in threads; BEO resolution (real cross-chain wallet fixture); BTCP route; BTCP score **exact formula recomputation** (line 146-148 — recomputes the weighted formula in the test); BH dual-strand (weak — see bugs); escrow two-phase + coherence gate + revert; BITP zero-movement; master formula suite via subprocess (`"0 failed" in r.stdout` — **fails in bare env**); chain registry ≥100 (124 actual) & VMs ≥14 (18 actual); 20 channels ≥15 ACTIVE; SILENCE semantics; final verdict prints. Issues detailed in §6.
- **master_formula_verification.py** (689 L): the **"105/105 formulas"** source — 108 `check()` calls across L0-L9 + Love/Moat/BTCP; empirical run here: **104 passed, 1 failed (L4.7 PQC)**. Claim is dependency-conditional, not unconditional (matches agent 2-a's finding).
- **invention_verification.py** (394 L): all 36 inventions; mostly real module invocations; several weak checks (BEO tautology, BSC hasattr-fallback, LSS "or 'sec' in str", BZK = greps anima_regulatory.py source for "Pedersen/Schnorr/Fiat-Shamir", BLO/SensingOracle = greps .sol source). PQC check honestly fails when deps missing (try/except → check False).
- **chain_coverage_audit.py** (201 L): cross-references 5 registries + indexers + contracts; prints coverage matrix; writes /tmp/chain_audit_result.json. `has_adapter` is hard-coded True for a long VM list regardless of actual adapters (line 138). Not a pytest test (script); CHANGELOG honestly notes "identical pre-existing VM-name mismatches".
- **test_anima_stress_1000.py** (1,257 L): the stress harness behind ANIMA_STRESS_REPORT.md; §1-§3 unit sections incl. the same two tautologies (Φ constants at 392-398, information conservation loop 399-403); HTTP sections mostly `min_ok_pct=0.0` (assert `pct >= 0.0` — measurement-only, cannot fail); honest architecture note that throughput IS the finding.
- **test_btcp_bitp_sba_bibl.py** (1,132 L, 33 tests = README's "33/33 PASS"): real modules (`core.master.btcp_score` — **a third BTCP-score implementation** alongside core.btcp.router and test-recomputed), akashic price oracle (TWAP, manipulation, HHI), SBA (weights=1, Pearson I-component incl. deception case I<0.30 — the README "I=0.0015" flavor), BIBL mempool archetypes. Real formula tests; SBA hostile case asserts I<0.30 (not the 0.0015 quoted in README).
- **test_gk_living_security.py** (1,093 L, 14 tests = README's "14/14 PASS"): §1-§12 real GK/HashDNA/immune/adaptive/replay/entropy/epigenetic/noise/mito/isolation tests; §13 live FAISS report (skips if down); **§14 "Password vs GK comparison" ends in `assert True`** (line 1042) — a printed marketing table that cannot fail.
- **live_rpc_test.py** (109 L): honest — 20 real public mainnet RPC probes per VM family. Excluded from pytest collection.
- **per_vm_e2e_test.py** (132 L): boots FAISS in-process; ingests **the same [0.55]×128 vector for all 20 VM families**; BH storage check is `r2.json().get("stored", 0) >= 0` (line 99) — **always true**; the per-VM "E2E" proves ingestion plumbing, not per-VM behavior.
- **bh_pipeline_test.py** (129 L): canonical BH per VM family; §1 "BEO case-normalization" compares `sha3(addr.lower())` to `sha3(addr.upper().lower())` — **same string, tautology** (lines 61-68). Chain list has **STARKNET=7001 AND TRON=7001 duplicate** (lines 40-41) and **PVM=900 colliding with SVM=900** (line 43) — despite the header claiming "chain_id per canonical registry".
- **conftest.py** (27 L): path setup + `collect_ignore` for 6 live files (e2e_full, chain_integrations, vision_expansion, live_rpc_test, per_vm_e2e_test, golden_test).

### 2.8 backtest/ (10 files)

- **exploit_dataset.json** (30 exploits + 10 controls): genuine historical incidents (Ronin $625M, etc. with tx hashes, Rekt/Chainalysis sourcing metadata, $3.3158B total — sum verified). Controls: Uniswap V3 Router, Aave V3, Compound, Chainlink, MakerDAO, Curve, Lido, Vitalik, EF, Gnosis Safe.
- **run_backtest.py** (328 L): the ORIGINAL circular backtest (per audit finding #26). Queries live oracle `/api/v1/signal/{addr}`, `trion_flagged = not coherent or silence` with `silence` defaulting to `not coherent` → **flagged ≡ (coherence < threshold)**. **Failure-mode: on API error/unreachable it returns coherence=0.0 → every entity flagged → 100% recall trivially** (lines 42-54, 71-85). Builds SHA-256 Merkle tree (odd-length duplication), writes report/merkle/summary.
- **run_held_out_backtest.py** (302 L): the remediation for #26 (67/33 split, seed 42, Wilson CI, Cohen's d, bootstrap). **Never run — no held_out_report.json or held_out_summary.txt exists in results/**. Additional flaws: controls for Cohen's d/bootstrap are `synthetic_controls = [0.5 + random.gauss(0,0.05) ...]` (line 196) — imaginary, unseeded; `flagged = not coherent` inherits the same degenerate-detection semantics; precision/F1 impossible (no negatives in dataset); `import math` placed after the function that uses it (line 70 vs 109 — works at runtime, bad style).
- **results/backtest_report.json + merkle_proof.json + summary.txt** (dated 2026-08-02): see §5 — **the committed run is a degenerate flag-everything run**.
- **results/onchain_proof.json** (dated 2026-06-01, dry_run false): 30 attacker records — 28 "ALREADY_PUBLISHED" (skipped) + 2 confirmed with real-looking Arbitrum Sepolia txs/blocks/gas; embedded per-record signals from an EARLIER, non-degenerate run (coherence 0.35-0.54, thresholds ~0.74, real planes/archetypes/signal_ids). Metrics block identical (TP=30 FP=10 TN=0 FN=0). `merkle_root: d5f611…` ≠ committed merkle_proof.json root `b4132f…` — the on-chain anchor does NOT commit to the committed report. `merkle_txid` = `0x` + merkle_root (it's the publishSignal record key, not a transaction hash — misleading field name).
- **publish_proof.js** (325 L): ethers v6 publisher to TRIONOracleV3 on Arb Sepolia; EIP-191 signed digest per publishSignal; packs status/coherence/threshold/block/ts; **only publishes ATTACKER records (30)** — the 10 controls and the FP side are never anchored; summary record packs **precision as "coherence"** with status=1 SAFE ("the backtest itself passes the integrity check" — self-certification, line 236-239); console hard-codes "PUBLISHING MERKLE SUMMARY (precision=F1=85.71%, 30/30 recall)" (line 233).
- **package.json / package-lock.json**: ethers ^6 only — consistent.

---

## 3. Test quality & circularity assessment

**Genuinely good (would satisfy a careful reviewer):**
1. tests/unit/trion_protocol + test_all_planes + test_whitepaper_gaps — broad, specific, real-import coverage of the core/ math layer with whitepaper-pinned constants.
2. tests/unit/btcp_continuum phase0/2/4/5 — the only true multi-module pipeline test (in-memory).
3. tests/adversarial/test_adversarial_suite.py — real cryptography and real proof/quorum/expiry logic.
4. tests/integration/test_anima_live_ingestion.py — properly isolated subprocess boot + real external HTTP.
5. ANIMA_STRESS_REPORT.md — candid failure documentation.
6. Property-based (Hypothesis) tests; graceful live-service skips; deterministic seeds documented.

**Circular / self-fulfilling patterns found (file:line in §6):**
- **Re-implementing production logic in tests**: BH payload/hash (test_bh_collision_resistance.py:53-86), Shannon entropy "mirrors all indexers" (test_deep_vm_and_zg.py:39-58), ECDSA/BTCP verifier classes (test_adversarial_suite.py:61-208 — mirror of contract rules), BTCP score formula recomputed (golden_test.py:146-148), wilson/cohen fine (they're generic stats).
- **Tautologies** (assert arithmetic or constants, no production code): Φ healthy/manipulated (test_stress.py:323-331; test_anima_stress_1000.py:392-398), information conservation loop (test_stress.py:404-416; test_anima_stress_1000.py:399-403), P(break) exp monotone (test_stress.py:139-153), BEO cross-VM identical-hash (invention_verification.py:107-109; test_beo_cross_chain_vm.py §2; bh_pipeline_test.py:61-68; crossvm beo_from_* identical bodies), SQLite UNIQUE as "replay detection" (test_adversarial_matrix.py:34-40), `assert True` §14 (test_gk_living_security.py:1042), `stored >= 0` (per_vm_e2e_test.py:99), golden test `success is True or len(proofs) >= 0` (golden_test.py:115-116).
- **Hardcoded outcomes presented as measurements**: crossvm BTCP components (0.75/0.85/0.90/0.92/0.95/0.00 → 0.8655 = README table), monitor script's "38 non-EVM / 100+" (bh_accumulation_test.py:190-191), chain_coverage_audit adapter column (line 138).
- **Mocked liveness** (default mode) in test_chain_integrations.py — the mock provides the expected chainId itself.
- **Self-reported counts as verification**: "65 formulas" = API's own /whitepaper/coverage (test_e2e_full.py:628-631); falsifiability registry "0 failing" (test_adversarial_matrix.py:178-180).
- **Source-text greps as compliance proofs**: phase1_contracts.py, invention_verification BLO/Sensing/BZK.

**Parallel-implementation hazard**: at least **three BTCP-score code paths** (core.btcp.router, core.master.btcp_score, crossvm/root scripts inline) and **two BH constructions** (core.primitives.behavioral_hash vs core.primitives.hash_dna) — tests pin whichever one they import, so "the formula" is verified N times against N implementations (consistent with agents 2-a/2-g duplicate-module findings).

---

## 4. What the backtest results actually contain

The committed `backtest/results/` (2026-08-02) is the run cited by README "Proven Results":

```
TP=30 FP=10 TN=0 FN=0 | Precision=0.75 Recall=1.0 F1=0.8571 | FPR=1.0 FNR=0.0
avg_attacker_coherence = 0.0   avg_control_coherence = 0.0   separation = 0.0
```

- **All 40 entities (30 attackers + 10 innocent controls incl. Uniswap, Aave, Vitalik, Gnosis Safe) scored coherence 0.0, threshold 0.55, archetype "Explorer", empty planes, empty signal_id, empty genomic_sig.** Every entity was flagged → TP for all attackers, **FP for all 10 controls, FPR = 100%, zero discriminative power (separation 0.0)**.
- Therefore: **"30/30 — 100% recall" is the recall of a flag-everything classifier** (the oracle returned default/cold-start or error-path signals). **F1 85.71% is 2·(0.75·1)/(1.75)** where 0.75 precision exists only because 10/10 innocents were falsely flagged.
- The Merkle tree is internally consistent (root b4132f… recomputes from 40 leaves: `id:addr:0.0:TP|FP`) — it cryptographically commits to a **degenerate result set**.
- The earlier generation (onchain_proof.json, 2026-06-01) DID have real per-attacker signals (coherence 0.35-0.54 vs θ≈0.74, 12 archetypes, populated planes, real signal_ids) — but its metrics block ALSO shows FP=10/TN=0 (all controls flagged in that run too), only attacker records were ever published on-chain, and its merkle_root (d5f611…) **does not match** the currently committed tree (b4132f…) — i.e., **the on-chain anchor is stale relative to the committed report**.
- The **held-out (non-circular) backtest has never been executed** (no held_out_report.json/held_out_summary.txt), and even if run it inherits `flagged = not coherent` and synthetic-gauss controls.
- $3.3158B "value at risk" = the sum of dataset amounts (real historical data) — meaningful as dataset description, not as detection performance.

**Bottom line**: the README table "Exploits tested 30 | $3.315B | 30/30 — 100% recall | F1 85.71%" is arithmetic truth wrapped around a classifier that, in the committed run, flagged literally 100% of queried addresses including all ten legitimate protocols.

---

## 5. Claims vs reality

| Claim (where) | Reality (verified) |
|---|---|
| CHANGELOG: "pytest tests/unit/: **549 passed, 6 skipped, 0 failed**" | **Plausible only with PQC deps installed**: 555 collected = 549+6. Bare env: 545 pass, 3 PQC failures, 6 skips (all live-service gates — auto-skip claim TRUE). |
| README:859 & MAINNET_RUNBOOK: "671 Python passed, 5 skipped" | **Stale/under-specified**: full `pytest tests/` collects **930**; unit+adversarial+root = 723. 671+5=676 matches neither; cannot be reproduced against HEAD in any obvious combination. |
| MAINNET_RUNBOOK: "30/30 Golden Test" | golden_test.py has ~30 check() calls — consistent by count, but requires full stack (FAISS+Flask boot) and master-formula "0 failed" → **fails in bare env**; contains always-true/dead checks (see §6). |
| CHANGELOG/README/golden: "ALL SYSTEMS VERIFIED — 124 chains / 18 VM families, 105 formulas, 36 inventions" | 124/18 real (registry verified). "105 formulas" = master suite → **104/105 here** (PQC dep). "36 inventions" line is a **hardcoded print** (golden_test.py:327); invention_verification covers them but with several weak/tautological checks; golden test itself inventories no inventions. |
| README: "30/30 — 100% recall, F1 85.71%, $3.315B" | **Degenerate flag-everything run** (see §4); FPR 100%, separation 0.0, controls all flagged; on-chain anchor root mismatched. |
| README: "Consensus Security 6/6 PASS — 50 sybils, 75.8% nominal stake → 0.00% effective power" | **No test in the repo produces this** — the string "75.8" appears only in README.md:325. Unverifiable. |
| README: "Resonance 95/95 PASS" | Not in tests/; scripts/deep_resonance_test.py counts its own checks (scripts/ = agent 2-i scope); tests/ has 2 resonance tests. |
| README: "Living Security (GK) 14/14" | test_gk_living_security.py = 14 tests — count TRUE; §13 skips without FAISS; §14 is `assert True`. |
| README: "BTCP/SBA/BIBL 33/33 — I=0.0015" | 33 tests — count TRUE (real tests); the "I=0.0015" figure isn't asserted anywhere (test asserts I<0.30). |
| README cross-VM table: BTCP Score 0.8655/0.9205, "no asset ever left its native chain" | 0.8655 = **hardcoded constants** in crossvm scripts; Solana side simulated; scripts **cannot run** (foreign /home/user/.super_doubao paths). TON/NEAR rows come from similarly hand-scored runs elsewhere. |
| "Live-service tests auto-skip" | TRUE — 6 skips confirmed with proper gates; but integration/test_anima_full.py (141 tests) has **no** such gate and fails wholesale without the stack. |
| CHANGELOG: "PQC round-trip: kyber/dilithium/sphincs real PASS" | Dependency-conditional (3 tests fail without the libs; verified). |
| audit-fix note in golden_test (REG-2) | chain count now read from registry — honest fix confirmed (124/18). |

---

## 6. Bugs / issues / inconsistencies (file:line)

**backtest/**
1. `backtest/run_backtest.py:42-54,71-85` — unreachable/error oracle ⇒ coherence 0.0 ⇒ every entity flagged ⇒ 100% recall for free (root cause of the degenerate committed results).
2. `backtest/run_backtest.py:76-80` — `silence` defaults to `not coherent` ⇒ `trion_flagged ≡ not coherent` (classifier = "below threshold").
3. `backtest/results/backtest_report.json` — all-40 entities coherence 0.0 / archetype "Explorer" / FPR=1.0 / separation=0.0 committed as the flagship evidence.
4. `backtest/results/onchain_proof.json` vs `merkle_proof.json` — merkle roots mismatch (d5f611… vs b4132f…): the "anchored" proof does not commit to the committed report.
5. `backtest/results/onchain_proof.json` `merkle_txid` = `0x`+root — field named as tx id but is the publishSignal record key (misleading; the real summary tx is "ALREADY_PUBLISHED").
6. `backtest/publish_proof.js:163-229` — only attacker records anchored on-chain; controls/FP side unprovable on-chain.
7. `backtest/publish_proof.js:236-239` — packs precision as coherence w/ status=1 (SAFE): on-chain "integrity" record self-certifies the backtest.
8. `backtest/publish_proof.js:233` — hardcoded console claim "precision=F1=85.71%, 30/30 recall".
9. `backtest/run_held_out_backtest.py` — **never run** (results/held_out_report.json absent); `:196` unseeded synthetic gaussian controls; `:160,172` flagged≡not-coherent semantics; `:70 vs :109` `import math` after first use (style).
10. `tests/unit/trion_protocol/test_held_out_backtest.py` — advertises "non-circular backtest" verification but only tests split determinism/dataset shape, never the metrics.

**tests/**
11. `tests/unit/bh_cross_language_vector.py:17` — SCHEMA_PATH points to repo root; actual file at config/bh_schema_v1.json → script crashes (verified FileNotFoundError). Invisible to pytest (not collected).
12. `tests/crossvm/run_btcp_crossvm_full.py:90-95` and `run_btcp_crossvm_hybrid.py:47-52` — hardcoded `/home/user/.super_doubao/super-doubao-runtime/...` paths ⇒ both crossvm scripts unrunnable in this repo.
13. `tests/crossvm/run_btcp_crossvm_full.py:721-728` (hybrid `:411-418`) — BTCP score components hardcoded (0.8655 == README table value); `:469` passes 865500 as coherence.
14. `tests/golden_test.py:115-116` — `intent_result.success is True or len(intent_result.route.proofs) >= 0` — second disjunct always true (check cannot fail; crashes instead if route is None).
15. `tests/golden_test.py:119-120` — label "4+ ZK proofs generated" but asserts `>= 1`.
16. `tests/golden_test.py:180-187` — XOR `invariant` computed then discarded (dead code); actual check is only sense≠antisense.
17. `tests/golden_test.py:324-327` — final "105 formulas / 36 inventions" lines are hardcoded prints (36 never enumerated by this script).
18. `tests/golden_test.py:264` — formula gate `"0 failed" in stdout` fails in bare env (master suite 104/105).
19. `tests/invention_verification.py:107-109` — BEO "cross-substrate" check hashes the same string twice (tautology).
20. `tests/invention_verification.py:238` — BSC check's `hasattr(...) else True` fallback makes the clause vacuous.
21. `tests/invention_verification.py:327-329` — LSS check escape `or "sec" in sec_str` nearly always true.
22. `tests/invention_verification.py:349-351` — BZK "verification" = grep of anima_regulatory.py source text.
23. `tests/chain_coverage_audit.py:138` — adapter column hardcodes a VM allow-list as "yes" regardless of actual adapters.
24. `tests/test_stress.py:323-331, 404-416, 147` — Φ targets, information conservation and P(break) verified against in-test constants/arithmetic (whitepaper targets "proved" tautologically); duplicated in `tests/test_anima_stress_1000.py:392-403`.
25. `tests/unit/bh_accumulation_test.py:190-191` — monitor prints hardcoded "38 non-EVM / 100+ chains"; `:78` SyntaxWarning (invalid escape `\|`); collected by pytest as a warning-only module.
26. `tests/bh_pipeline_test.py:40-41,43` — chain-id 7001 used for BOTH STARKNET and TRON; PVM=900 collides with SVM=900 (contradicts its own "canonical registry" comment); `:61-68` case-normalization tautology (`addr.upper().lower()`).
27. `tests/per_vm_e2e_test.py:99` — `r2.json().get("stored", 0) >= 0` always true (BH-storage assertion vacuous); same constant vector for all 20 VMs (`:69`).
28. `tests/adversarial/test_adversarial_suite.py:354-361` — zero-address segment asserts the fixture equals itself (tautology); `:61-208` verifier classes are test-local mirrors of contract rules (not contract tests).
29. `tests/adversarial/test_adversarial_matrix.py:34-40` — "replay detection" tests SQLite's UNIQUE constraint; `:15-17` tests hashlib, not TRION.
30. `tests/integration/test_deep_vm_and_zg.py:39-58` — Shannon helpers re-implemented ("mirrors all indexers") ⇒ circular w.r.t. Rust indexers.
31. `tests/integration/test_akashic_category4.py:~177-179` — runs `runghc math/formal_verification.hs` (file moved to formal/src/TRION/Theorems.hs in 2.0.0) — stale path, step always errs.
32. `tests/integration/test_e2e_full.py:527-528` — docstring "all 32 simulations" vs assertion `attack_count >= 22`; `:628-631` "65 formulas verified" = API self-report.
33. `tests/integration/test_chain_integrations.py` (default mode) — hermetic mocks supply the expected answers (liveness self-fulfilling); mock vm_families embed chain-id set inconsistent with everywhere else (SVM 103, PVM 901).
34. `tests/test_anima_stress_1000.py` — most HTTP sections assert `pct >= 0.0` (`min_ok_pct=0.0`) — unfalsifiable (documented as measurement, but "PASS" lines imply assertions).
35. `tests/conftest.py:15-27` — golden/e2e/chain/vision/live_rpc/per_vm excluded from default collection ⇒ headline pytest numbers never include the heaviest claims-bearing suites.
36. Stale docstrings throughout tests/unit/trion_protocol referencing `src/...` layout (e.g. test_archetype_engine.py:2-4).
37. `tests/test_gk_living_security.py:1042` — `assert True` (§14 cannot fail).
38. `tests/unit/btcp_continuum/test_phase1_contracts.py` — Solidity compliance via source-text grep only (no compile/behavior).
39. Environment fragility: `tests/adversarial/test_adversarial_suite.py:56` needs eth_account (not in root requirements); DDoS tests need full api/anima-service dep tree (feedparser…); hypothesis needed by property tests — all outside a bare `pip install pytest numpy`.

---

## 7. Next actions (for the main agent)

1. Treat README "Proven Results" table as **unsupported**: cite the degenerate committed run (FPR 100%) and the root mismatch between onchain_proof.json and merkle_proof.json.
2. Reconcile test-count claims: 549 (tests/unit, PQC-dep-conditional) vs 671 (stale) vs 930 (actual collectible) — recommend one number + environment spec.
3. Cross-reference with 2-a (formula suite 104/105), 2-b (executor-fabricated φ/chain-ID collisions — confirmed again in bh_pipeline_test 7001/900), 2-f (FAISS/oracle real spine vs presentation layer), 2-i (CI: stress job `--ci` flag masked by continue-on-error; Makefile dead targets mean `make test` never runs any of this).
4. Fix list (top): golden_test dead/always-true checks (items 14-16), bh_cross_language_vector path (11), crossvm foreign paths + hardcoded scores (12-13), backtest error-path→flagged (1-2), actually run the held-out backtest with real benign controls.
5. The honest assets to highlight in any rewrite: test_anima_live_ingestion.py, btcp_continuum phase0-5, adversarial suite's crypto tests, ANIMA_STRESS_REPORT.md, and the 6 documented live-service skips.
