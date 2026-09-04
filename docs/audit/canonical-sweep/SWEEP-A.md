# SWEEP-A — Auxiliary-Language & Python Sweep (Canonical Reconstruction)

Task ID: SWEEP-A · Repo: /home/z/trion-core @ c6c38e4 (clean tree, no modifications made)
Agent: TEAM A + auxiliary-language auditor
Method: static read + live execution (python imports, wasm probes, test runs). Every claim carries file:line. Prior docs (docs/audit/*.md) were treated as claims-only; all relied-upon claims below were re-verified in code.

---

## 1. Language inventory (tracked files, git ls-files)

| Language | Files | Primary locations | Role class |
|---|---|---|---|
| Python | 335 | core/ (154), tests/ (92), anima-service/ (31), scripts/ (25), api/ (15), zg/4, backtest/3, misc roots | Main engine + tests + ops |
| Rust | 89 | indexers/crates, contracts/svm, rust/ | Indexer fleet + contracts (out of scope) |
| TypeScript | 54+52+23 | chains/, sdk/, relayer/ | Chain integration + SDK (out of scope) |
| Solidity/Cairo/Move/FC/Vyper | 51+33+7+18+3 | contracts/ | Wave-2 VM verifiers (out of scope) |
| Go | 20 | validator/ (19), network/health_monitor.go, docs/research/archive/validator_network.go | Consensus engine + mesh |
| Shell | 19 | scripts/, supervisors/, entrypoints | Deployment/CI/ops |
| C++ | 5 | signal-processing/ (4), docs/research/archive/signal_processor.cpp | FFT/sensor reference |
| Haskell | 4 | formal/ (3), docs/research/archive/proofs.hs | Formal layer |
| Julia | 3 | math/src, math/test, docs/research/archive/trion_math.jl | Math verification |
| WASM | 2 | sdk/src/wasm/signal_processor.{wasm,wat} | Browser signal verification |
| SQL | 1 | schema.sql (36 CREATE TABLE) | Reference DDL |

## 2. Python classification map (subsystem → class → evidence)

| Subsystem | Class | Evidence |
|---|---|---|
| serve.py | PRODUCTION | gunicorn/socketio entry, port 5000, creates bh_ledger.db fallback schema (serve.py:13-58) |
| main.py | PRODUCTION | import shim for gunicorn (main.py:1-14) |
| api/app.py | PRODUCTION (Oracle API) | 11,179 lines; AWA publication hooks app.py:1215-1217, 2675-2677; COLD_START guard app.py:862-889; 62 `is_synthetic` literals (61 True) |
| api/price_feed_routes.py | PRODUCTION w/ labeled synthetic | synthetic pairs flagged is_synthetic=True (87, 184-187, 497); relayer-submitted pairs is_synthetic=False + data_provenance (427) |
| api/{blockchain,chains_registry,socket_push,dashboard_routes,protocol_*,btcp_continuum_routes,self_verification_routes,cex_integration,validation}.py | PRODUCTION/INTEGRATION | Flask blueprints registered on app; cex discloses oe_factor synthetic (cex_integration.py:669-705) |
| anima-service/faiss_service.py | PRODUCTION (Akashic FAISS store) | ingest `/index/add_tx_bh_batch` verifies BH complementarity per record (faiss_service.py:3714-3760); SQLite bh_ledger writer; seed_fallback phi labeled is_synthetic (10563-10567) |
| anima-service/genesis_backfill_*.py (20) | INTEGRATION (one-time ingestion) | per-VM backfill workers, driven by scripts/genesis_backfill_runner.py |
| anima-service/{anima_engine,anima_regulatory,liquidity_ocean,multilingual_sentiment,exploit_precursor_analysis,nl_score_engine,brt_scheduler,btcp_gas_forecast,crawler_pool,batch_contract_audit,backfill_entity_records}.py | RESEARCH/REFERENCE + production support | anima_engine implements L3.3-L3.7 ANIMA (A=PCR×HA×CA) per whitepaper; crawler_pool feeds ANIMA sources |
| core/primitives/behavioral_hash.py | PRODUCTION-CANONICAL (BH builder) | 93-byte payload, §4 below |
| core/primitives/extended_payload.py | REFERENCE (opt-in v2) | 176-byte extended layout, POST /api/v1/bh/v2/extended (CANONICAL_BH.md:87-100) |
| core/consensus/certificate.py | PRODUCTION-CANONICAL (cert encoder) | §5 below |
| core/realtime/bh_streamer.py | PRODUCTION ingestion | real public-RPC polling, urllib, 60 EVM + 30 non-EVM chains (bh_streamer.py:36-65, 713+) |
| core/realtime/orchestrator.py | PRODUCTION support | streamer lifecycle |
| core/master/ (signal_factory, coherence, d_engine, moat, …) | PRODUCTION truth path | signal_factory consults AWA gate (signal_factory.py:431-468); coherence.py 11 weight profiles (47-62) |
| core/governance/awa.py | PRODUCTION (emission gate) | EmissionGate singleton awa.py:103-199; see §3c |
| core/governance/{love_protocol,elder_wisdom,unknown_unknown,open_research_questions,intelligence_maintenance}.py | RESEARCH | whitepaper governance concepts, self-tested |
| core/governance/{slashing,falsifiability_registry,right_to_invisibility,adaptive_consensus,sba_engine,initialization}.py | PRODUCTION-adjacent | slashing feeds AWA/slashing_log; falsifiability registry tracked in tests |
| core/btcp/* (11) | PRODUCTION-side engine (off-chain) | durable SQLite write-through state_store.py:1-12 (S7 remediation); orchestrator writes step-6 records |
| continuum/engines.py | REFERENCE/SIMULATION | BID/CME/PMO/BDC + thermodynamic settlement engines (off-chain BTCP continuum sim) |
| core/extended/ (9) | INTEGRATION (external fetchers) | GBIF/IUCN/IMF/WB fetchers; GBIF longitude bug FIXED at 66482ce (biological_capital.py:176 now reads decimalLongitude) |
| core/mental/ (18), core/spiritual/ (15), core/akashic/ (13) | REFERENCE/RESEARCH (whitepaper layer impls) | every file has inline self-tests; living_security 1381 lines; not all wired to live data |
| core/price/ (3) | PRODUCTION-adjacent | btcp_price_oracle (TWAP + attack detection), behavioral_price_engine |
| core/{trading,reputation,investment,lifecycle,ubl,pipeline,agent,auditor,planes,thermodynamics,novel,manipulation,protocol,physical,api} | RESEARCH/SUPPORT mix | e.g. pipeline/signal_publication.py wires coherence→on-chain publication; novel/ = EXPERIMENTAL (BIRP, Chameleon) |
| scripts/ (25) | DEPLOYMENT/OPS | bootstrap.sh, deploy_*.py/mjs, genesis_backfill_runner, cross_lang_bh_check.py, simulate_attacks*.py |
| tests/ (92) | VERIFICATION | unit: 1025 passed/6 skipped (live run, 51.6s); golden: 134 passed; certificate: 68 passed; schema-writers: 18 passed |
| zg/zg_api_routes.py | INTEGRATION (0G) | Flask blueprint exposing live 0G data |
| backtest/ | EXPERIMENTAL | replay_engine + held-out backtest |
| run_btcp_crossvm_full.py, run_crossvm_zero_bridge.py | INTEGRATION one-shot | cross-VM bridge runners |

## 3. Synthetic-data boundary findings

(a) **app.py labeling still holds.** 62 `"is_synthetic":` literals, 61 with value True (rg count, app.py). Synthetic markets (sin+md5 noise), SBA/XSL demo inputs, NL approximations all carry the key plus `synthetic_reason` (e.g. app.py:1464-1472, 3121-3122, 3169-3170). The historic hash-seeded plane fabrications were REMOVED: cold-start guard app.py:862-889, removal notes app.py:895-925 (M-plane), 906-917 (sensor bootstrap defaults disclosed), 921-925 (depth from FAISS).

(b) **faiss_service.py.** Ingestion path is real: `/index/add_tx_bh_batch` (3714) stores Rust-indexer records and verifies the dual-strand XOR invariant per record. `seed_fallback` phi (10530-10567) — deterministic entity-id-derived 9-feature vector when FAISS vector can't be reconstructed — is labeled is_synthetic=True with reason. PQC verify falls back to "TRION-SHA3-fallback-approx" (5695+) only for legacy fallback-signed messages, real ML-DSA-87 used when liboqs present (5735-5741).

(c) **bh_streamer.py ingestion is real-RPC** for EVM (publicnode/official endpoints, urllib JSON-RPC polling, bh_streamer.py:36-65) and real block data for non-EVM. Non-EVM sender attribution is honestly-synthetic: `_synthetic_tx_sender` = SHA3-256("{chain}:{txhash}") (bh_streamer.py:823-841) — distinct per tx, replacing the old from="unknown" single-entity collapse; values default "0", to "unknown" for some families (865, 878) — real blocks, degraded attribution, documented.

(d) **Residual synthetic-in-truth-path (disclosed, not machine-flagged):** Σ-plane and K-plane bootstrap priors (Σ=0.25 via `_get_sigma_plane` fallback app.py:649-669; K bootstrap default) enter C(t) with `sigma_source`/`k_source` strings and a prose `calibration_note` (app.py:1087-1094) but no machine-readable is_synthetic flag on the coherence endpoint. `degraded_mode` reflects only FAISS enrichment (app.py:1071).

(e) **AWA production wiring feeds synthetic/hardcoded inputs** — see Divergence D3 (MEDIUM-HIGH): the only production caller of `AWAEnforcer.evaluate()` is `/api/v1/governance/awa` (app.py:2888-2893) with `consensus_quorum=0.72` (hardcoded PASS ≥2/3), `public_good_pct=0.20` (hardcoded PASS ≥0.15), and `validator_hhi = 1200 + 800·vol` where vol is the documented synthetic time-noise (app.py:1424) — proxy max 2000 < 4000, so the HHI CRITICAL freeze path can never fire through this endpoint; anti-centralization distributions omitted → data-pending → PASS (awa.py:478-481, 494-497). Gratitude (decays 0.95/week, awa.py:307-321), R_inv (auto-detect, awa.py:420-451) and SDP flag remain the only live freeze triggers in the deployed Oracle.

(f) **Price feed:** synthetic cross-rates and demo pairs labeled is_synthetic=True (price_feed_routes.py:87, 497); relayer-submitted real observations is_synthetic=False with witness_note that they are relayer-attested, not TRION-verified (427-443).

## 4. Canonical Python BH builder — parity verdict: MATCH

Module: **core/primitives/behavioral_hash.py** (self-declared canonical reference, header lines 1-42).
- 93-byte payload: `entity_32(32) || event_type(1) || magnitude_nano(8) || context(8) || timestamp(8) || chain_id(4) || block_hash(32)` (payload assembly lines 266-274, assert 276). All ints big-endian.
- magnitude: canonical fixed scale `min(1, log10(human+1)/log10(1001))` (canonical_magnitude_norm, 144-172); nano = `int(mag*1e9)` (line 269) — truncation toward zero, matching CANONICAL_BH.md §4 truncation rule. NaN fails closed (P-PY-01, 160-162); chain_id validated not masked (P-PY-02, 175-184).
- Lenient §9 normalization: hex_to_32bytes (117-134), bytes_to_32 (137-141).
- Dual strand: SHA3-256(payload||0x00) / SHA3-256(payload||0xFF) XOR complement(sense) (hash_dna, 187-200) — matches doc §1. Whitepaper USD/90d form kept only as non-canonical display path (`normalize_magnitude`, 203-228; returned as magnitude_normalized_usd).
- Live verification: computed BH for a synthetic event; `bh_from_rust_hex` strict 93-byte re-verify (302-378) recomputes strands and raises on invariant failure.
- **Cross-implementation live probe:** bh_streamer.compute_bh(entity '0xAbC…001', SWAP, 5e18 wei, chain 1, ts 1700000000, block 'cc'×32) vs core/primitives builder on identical logical event → **identical sense AND antisense hex** (executed this session). bh_streamer matches field semantics (context=0 Rust parity, SHA3-256(normalised addr) entity, bh_streamer.py:182-263).
- Golden vectors: tests/golden/test_golden_vectors.py — **134 passed** (live run). Layout in vectors.json matches doc offsets exactly.
- Minor discipline note: bh_streamer masks chain_id (`& 0xFFFFFFFF`, line 242) where core/primitives raises — Divergence D5 (LOW).

## 5. Certificate encoder summary (core/consensus/certificate.py, 685 lines)

- **346-byte payload, all big-endian, fixed widths, no floats** (encode_payload, 278-307). OFFSETS table (86-110):
  domain_tag "TRION-CERT-V1"(0,13) · certificate_kind uint8(13) · protocol_version uint24 packed semver(14) · validator_epoch uint32(17) · certificate_nonce uint64(21) · escrow_id b32(29) · route_id b32(61) · intent_hash b32(93) · entity_id b32(125) · source_chain u32(157) · dest_chain u32(161) · destination b32(165) · amount uint256(197) · anchor_bh b32(229) · execution_bh b32(261) · coherence u64 ×1e6(293) · threshold u64 ×1e6(301) · hhi_at_emission u64 ×1e4(309) · total_effective_power u64 ×1e6(317) · validator_count u32(325) · awa_enforced u8(329) · issued_at u64(330) · ttl u64(338).
- **Domain separation:** 13-byte tag "TRION-CERT-V1" at offset 0 (79); strict decode rejects wrong tag/width (from_payload, 310-345). Kinds: ESCROW_RELEASE=1, BOOTSTRAP_MULTISIG=2 (148-157), fail-closed on unknown (246-251).
- **Digests (§3.2):** certificate_hash = FIPS SHA3-256(P) (349-353, cross-VM id); EVM family = keccak256(P) with EIP-191 wrap "\x19Ethereum Signed Message:\n32" (355-366; pycryptodome keccak with loud fallback warning 62-72); STARK family = 31-byte felt chunking, 346→12 felts, domain felt = int("TRION-CERT-V1") (368-386).
- **Quorum (L4.2):** epoch-set effective power w_j = s_j·d_j (×1e6 integer, 470-472); D_consensus = mean(d_j) (502-504); tiers: d ≥ 0.60 → 2/3 STRICT (3·signed > 2·total, 537), d ≥ 0.40 → 0.75 (4·signed ≥ 3·total, 539), else 0.85 (20·signed ≥ 17·total, 541). Quorum computed from registered epoch set, never envelope claims (518-542); envelope weights are claims cross-checked in check_epoch_set_conformance (612-633).
- **HHI bound:** hhi_at_emission > 4000 (×1e4) → certificate invalid "L4.8 CRITICAL" (117, 579-583). EpochSet.hhi integer arithmetic (544-555).
- **TTL:** value tiers (ED-A3) <$1k→1h, <$100k→24h, <$10M→3d, ≥$10M→7d (132-137); freshness widens lower bound only (395-399); ttl=0 born-expired (590-591).
- **AWA bit:** awa_enforced=0 → structural rejection "emission was frozen (MD §17)" (584-585). Envelope requires ≥ MIN_SIGNERS=3 distinct signers (125, 575-578, 435-448).
- **Epochs:** 6h cadence, grace 2 (127-129); future-epoch and stale-epoch rejection (594-604).
- Live run: self-test → payload 346 bytes, structure OK, quorum tier 1 met. tests/unit/test_certificate_domain_separation.py: **68 passed**. Consumers: contracts/{svm,starknet,near,move,ton,cairo} + tests; **NOT validator/ (Go)** — see D1.

## 6. Go static review (validator/, 20 files, 8,449 lines; no toolchain, static only)

- **Consensus engine (internal/consensus/engine.go, 1347 lines): genuine Tendermint-family DW-BFT state machine.** NewHeight→Propose→Prevote→Precommit→Commit with lock-on-precommit, POLRound justification requiring a SEEN polka, deterministic weighted leader election seeded by (set hash, height, round) (57-59, 20-28). STRICT >2/3 quorum in integer arithmetic `3*power > 2*total` (86-88) — matches certificate.py tier-1 semantics and the Python strict-2/3 discipline. No unlock-on-nil, with a correct written justification vs equivocation attacks (38-48).
- **prevValSet refresh:** enterNewHeight sets prevValSet = valSet on EVERY height transition with an explicit comment on why stale sets stall LastCommit validation (686-695); tombstoned validators removed deterministically next height (697-707). pendingCommit: commit quorum witnessed before block arrival finishes commit on block hash match (846-848, 1073).
- **Slashing/tombstoning (slashing.go):** equivocation = two signed conflicting votes same (H,R,type); evidence self-verifying from embedded votes (51-89); evidence hash "TRION-EV…" sign-bytes-ordered for cross-node idempotency (94-118); tombstone N blocks, removal committed via block. TODO(on-chain burn): in-memory accounting only; wiring to contracts/vyper/TRIONStaking.vy::slash_validator explicitly outstanding (26-37).
- **Mesh (internal/p2p + cmd):** TCP line-JSON gossip; legacy attestation frames vs typed consensus envelopes backward compatible (validator_mesh.go:295-321, bft_mesh.go:30-39). Attestations feed engine mempool via SetAttestationHook (validator_mesh.go:103-116). Mesh attestation-layer quorum is the OLDER float ≥2/3 layer (validator_mesh.go:163-229) — engine header explicitly distinguishes it (engine.go:7-9).
- **Diversity:** two formulas coexist — p2p.ComputeDiversityWeight d_j = 1−corr(M_j, M̄) (consensus.go:134-176, used by engine via NewValidatorSetFromP2P engine.go:180-202) and the older sqrt-overlap diversityWeight (validator_mesh.go:241-249). Both clamp to [0,1].
- **HHI:** warning 1500 / danger 2500 / critical 4000 (consensus.go:34-36); recomputeHHI freezes SignalsFrozen at >4000 (440-465) — but there is NO unfreeze path (fail-closed forever until restart; diverges from Python AWA release-on-passing-evaluate).
- **Health monitor (network/health_monitor.go, 243 lines):** external-chain + internal-service probe utility; gateway notes the port discipline (gateway.go:98-131).
- **Certificate correspondence: NONE.** `rg TRION-CERT|certificate` over validator/ → zero hits. The Go fleet does not encode, sign, verify, or transport the 346-byte canonical certificate. Quorum arithmetic semantics (strict 2/3, micro-units ×1e6, HHI 4000) align with certificate.py, but there is no structural parity because there is no consumption.
- **Deployment status:** both cmd/trion-validator `main()`s are self-test programs (validator_mesh.go:336-380 runs mesh + BFT demos then exits). APIGateway (gateway.go:36-67) and ConsensusNode (consensus.go:91-113) are only constructed in tests (p2pgo_test.go:553). No production main starts them; scripts/start_trion.sh:6-8 runs the validator as a one-shot self-test. Classification: **PROTOTYPE (well-tested: engine_test.go 1247 lines, p2pgo_test.go 821, bft mesh test 320) — not a deployed daemon.**

## 7. C++ / Julia / Haskell / WASM findings

### C++ (5 files)
- signal-processing/src/fft_engine.cpp (297): radix-2 Cooley-Tukey FFT, one-sided PSD Shannon entropy normalized by log2(half), wash-trade periodicity detector; embedded self-test main (246). test/test_fft.cpp (63): real unit tests via TRION_FFT_NO_MAIN include guard (noise vs tone entropy, strict-cycle detection, no false positive). sensor_interface.cpp (225): BRT hardware abstraction — system clock now, GPS/NTP "in production" (43-70); HSM entropy via /dev/urandom fallback. signal_conditioning.cpp (36): moving-average + Hanning window.
- Buildable: signal-processing/CMakeLists.txt (C++17, -O3 -ffast-math), Makefile:39 target; **not in any CI workflow** (no cmake/signal-processing hits in .github/workflows). **No FFI boundary:** no ctypes/cffi/cython consumer anywhere; the Python plane computations duplicate the formulas independently.
- Integer widths/endian: N/A — pure float64 signal math, no canonical serialization. BRT moduli (86400/5400/2551442/31557600) match faiss_service.py:2435 and WASM globals — three-language constant parity.
- Classification: **REFERENCE/PROTOTYPE** (compilable, tested, unwired). docs/research/archive/signal_processor.cpp (333): earlier superset with BRT + FFT + hardware channels — **LEGACY/RESEARCH**.

### Julia (3 files)
- math/src/TRIONMath.jl (317): shannon_entropy (2 methods), magnitude_norm (whitepaper 90d form), phi_score, coherence (5 profiles), convergence_bound, verify_scale_invariance, prediction_interval_calibration, moat_compound, bootstrap_weight_decay, kolmogorov_bound, entropy_budget; standalone self-test suite (234-316). math/test/runtests.jl: real hspec-style Test suite per function (was a trivial placeholder before TEST-1 fix — header note).
- Parity vs Python (verified by formula comparison + numeric check this session): coherence profiles balanced/speed/intelligence/certainty/full_spectrum == core/master/coherence.py DEFAULT/SPEED/INTELLIGENCE/CERTAINTY/FULL_SPECTRUM **5/5 exact** (TRIONMath.jl:82-88 vs coherence.py:47-62; Julia is the 5-profile subset of Python's 11). bootstrap_weight_decay λ=1e-4 == awa.py:73 LAMBDA_BOOT, identical exp form (awa.py:357-359). shannon_entropy math-form == core/physical/phi_engine.py:35-40 (Python reimplementation reproduced Julia's self-test values exactly). **Divergence (LOW, documented):** Julia magnitude_norm = log10(v+1)/log10(max_90d+1) (TRIONMath.jl:51-54) is the whitepaper session-relative form that CANONICAL_BH.md §4 and behavioral_hash.py:19-22 explicitly exclude from the canonical payload — Julia is a whitepaper-math reference, not canonical-BH parity.
- CI: .github/workflows/ci-julia.yml runs math/test/runtests.jl on Julia 1.10.
- Classification: **REFERENCE (mathematical verification layer, Channel 20)**. docs/research/archive/trion_math.jl: **LEGACY** (669 diff lines; older "Channel 20" framing).

### Haskell (4 files)
- formal/src/TRION/Theorems.hs (465): 9 "theorems". Honest-status header (5-46) — **machine-checked by types: T2 SilenceCompleteness (phantom-kind TRIONSignal 'Silence vs 'Valuation, 99-130) and T8 AkashicAppendOnly (GADT BHLedger n with bhAppend n→Succ n, 240-300). Property tests only: T1 (misnamed "CoherenceConvergence" — range check), T3-T7 (spot-value checks). T9 BehavioralHashCollisionFree is VACUOUS: mkBHSense is string concatenation, not SHA3 (309-402).**
- Assumptions vs production: the type-level proofs hold **in the Haskell model only** — production signals are Python dataclasses with no phantom types, and the production ledger is SQLite with no GADT. T4 Θ∈[0.55,0.92] linear and T5 Φ×(1−MF) match production formulas (coherence.py threshold, app.py:919) so the property checks track real constants; hhiMax=2500 (216) is the whitepaper §20.2 rebalance tier (== Go DANGER tier), not the 4000 CRITICAL.
- formal/test/Spec.hs: real hspec suite over the exported API (was a putStrLn stub before TEST-2). formal/app/Main.hs + package.yaml: cabal-run wrapper (main-is fix). CI: ci-haskell.yml runs `runghc Theorems.hs` + hspec suite (GHC 9.4.8).
- Classification: **REFERENCE formal layer with honestly-limited guarantees** — per mission rule, NOT counted as production security proof. docs/research/archive/proofs.hs: **LEGACY** — carries the retracted overclaim "If the code compiles, the theorem is proved" (diff vs current header, lines 2-7), which Theorems.hs:5-46 explicitly corrects.

### WASM (sdk/src/wasm/signal_processor.wasm + .wat)
- Exports verified live via node WebAssembly.instantiate: compute_threshold, signal_emits, is_silence_type, is_valuation_type, apply_mf_correction, compute_pc_limit, brt_circadian/ultradian/lunar/seasonal, signal_type_count (24), is_extended_signal, compute_coherence, shannon_entropy, memory — 15 exports, all present.
- Parity probes (executed this session):
  1. compute_threshold(0.3)=0.661 == 0.55+0.37·0.3 exact; clamp at V=5 → 0.92 exact.
  2. compute_coherence(0.8,0.6,0.5,0.4,0.2)=0.5650000000000001 == Python DEFAULT-profile sum bit-exact.
  3. shannon_entropy([0.25]×4)=1.9999999999999982 vs Python 2.0 (Δ≈2e-15 — wat uses a 14-term artanh series log2 to avoid the f64.log2 opcode, .wat:168-231); shannon_entropy([1,2,3,4])=1.8464393446710154 == Python 1.8464393446710154 **bit-exact**.
  4. apply_mf_correction(0.8,0.6)=0.32000000000000006 exact; compute_pc_limit(0.1,1.0)=0.9 exact; brt_circadian(1700000000)=0.9259259259259259 == Python.
- Consumer: sdk/TrionSDK.ts:684-763 — verifyCoherenceWasm() (client-side tamper check of server coherence) + shannon entropy helper with explicit export-existence errors. Θ constants 0.55/0.92 and the 24 signal-type IDs match signal_factory.py (WAT globals 28-50).
- Verdict: **PRODUCTION (browser-side verification), semantic parity CONFIRMED within float tolerance (≤2e-15).**

## 7b. Shell + SQL classification

- scripts/{bootstrap,setup,start_trion,stop_trion}.sh: DEPLOYMENT (bootstrap creates bh_ledger.db symlink; start_trion orders FAISS→Oracle→validator one-shot self-test, scripts/start_trion.sh:5-8).
- supervisors/*.sh (7): PROCESS SUPERVISION wrappers (oracle, indexers, relayers, zg services).
- railway-entrypoint.sh (276) / render-entrypoint.sh / anima-service/start.sh (100): DEPLOYMENT (gated startup order, /readyz waits).
- run_0g_full.sh: DEPLOYMENT one-shot (0G integration launch). genesis_backfill_runner.sh, run_whitepaper_tests.sh: OPS. chains/starknet/scripts/build-and-verify.sh, contracts/svm/scripts/deploy.sh: BUILD/DEPLOY per-chain.
- schema.sql: **REFERENCE DDL** for external TimescaleDB deployment; the operative store is SQLite (header OPERATIVE STORE NOTE, schema.sql:5-25). 36 CREATE TABLE; every table carries an `-- operative-writer:` marker — 17 are `NONE` (declaration-only), the rest name live writers (core/btcp/state_store.py, orchestrator, escrow_monitor, faiss_service, timescale dual-write gated on psycopg2/TIMESCALEDB_URL). Markers machine-checked by tests/unit/test_schema_writers.py — **18 passed (live run)**. (Task brief said 33 tables; actual count at HEAD is 36.)

## 8. Divergence / contradiction findings (severity-ordered)

| ID | Sev | Finding | Evidence |
|---|---|---|---|
| D1 | HIGH | **Go validator fleet does not consume the canonical certificate.** certificate.py claims "Emission-side signing lives in the validator fleet (validator/) using the family digests defined here" (certificate.py:31-32) — but rg over validator/ finds zero TRION-CERT/certificate references. Canonical cert consumers are contracts/{svm,starknet,near,move,ton,cairo} + Python tests only. The claimed Go emission/signing side of the certificate pipeline does not exist in code. | certificate.py:31-32 vs rg validator/ (0 hits) |
| D2 | MED-HIGH | **AWA production wiring cannot trigger quorum/HHI freeze.** Only production caller of AWAEnforcer.evaluate() passes hardcoded consensus_quorum=0.72 (always ≥2/3), public_good_pct=0.20 (always ≥0.15), and hhi = 1200+800·vol (≤2000, never ≥4000 CRITICAL); distribution inputs omitted → data-pending → PASS. Gate is fail-closed by design (awa.py:103-199, release only via passing evaluate) but the deployed inputs make quorum/HHI/centralization conditions structurally untriggerable; live freeze risk reduces to gratitude decay + R_inv + SDP. Also undiclosed-hardcoded on the endpoint. | app.py:2884-2893; awa.py:536-545, 478-481, 579-580 |
| D3 | MEDIUM | **Σ-plane "live_validator_mesh" source unreachable.** app.py GETs http://127.0.0.1:6000/api/v1/consensus/sigma; the Go gateway serves POST /consensus/sigma (no /api/v1 prefix, POST-only) and no production main ever starts the gateway (only p2pgo_test.go:553). → Σ always falls back to FAISS-local or bootstrap 0.25. | app.py:660-669 vs gateway.go:54, 191-212 |
| D4 | MEDIUM | **/consensus/hhi is a demo endpoint** computing HHI over a hardcoded example weight vector, labeled "Demo". | gateway.go:214-224 |
| D5 | LOW | bh_streamer masks chain_id (`int(chain_id) & 0xFFFFFFFF`) instead of validating like the canonical builder (P-PY-02 raises). No practical aliasing for registry ids, but inconsistent canonical discipline between the two Python BH builders. | bh_streamer.py:242 vs behavioral_hash.py:175-184 |
| D6 | LOW | bh_streamer chain table: id 999 "hyperliquid" → rpc.hyperliquid-testnet.xyz (a TESTNET endpoint in the mainnet table); id 10143 "monad" → rpc.monad.xyz (unverifiable). Data-quality risk: mislabeled chain source. | bh_streamer.py:54, 41 |
| D7 | INFO | Go cmd binaries are self-test mains; ConsensusNode/APIGateway constructed only in tests → "validator fleet" is a tested prototype, not a running daemon (start script runs it one-shot). | validator_mesh.go:336-380; start_trion.sh:6-8 |
| D8 | INFO | Go p2p recomputeHHI freezes SignalsFrozen at HHI>4000 with **no unfreeze path** (fail-closed-until-restart); Python AWA gate releases on a passing evaluate — asymmetric semantics between layers. | consensus.go:440-465 vs awa.py:146-164 |
| D9 | LOW | Julia magnitude_norm implements the whitepaper 90d-window form that the canonical BH excludes (display path only). Reference-only divergence, documented at both ends. | TRIONMath.jl:51-54 vs behavioral_hash.py:19-22 |
| D10 | INFO | app.py AWA endpoint docstring still uses the deprecated mislabel "Adaptive Watchdog Architecture" (K15); core/governance/awa.py:5-8 declares Anti-Weaponization Architecture normative. | app.py:2878 vs awa.py:5-8 |
| D11 | INFO | Σ/K bootstrap priors enter C(t) disclosed via strings/calibration_note but without a machine-readable is_synthetic key (unlike 61 other endpoints). | app.py:1087-1094, 649-669 |
| V1 | POSITIVE | Prior-doc bug claims now FIXED at HEAD: GBIF longitude reading (fixed in 66482ce, biological_capital.py:176), compute_xsl import shadowing (aliased, core/extended/__init__.py:54-62), api/routes.py import-time print (file removed — only empty routes/ package remains). Verified this session. | git 66482ce; rg api/ |
| V2 | POSITIVE | Test health at HEAD: tests/unit 1025 passed / 6 skipped (51.6s); golden vectors 134 passed; certificate domain-separation 68 passed; schema writers 18 passed. BH parity core↔streamer bit-exact (live probe). | live runs this session |

## 9. TRION-vs-BTCP assignment per component

**TRION core (truth infrastructure):**
- core/primitives (BH), core/consensus (certificate), core/master (C(t)/signal factory), core/governance (AWA gate), core/realtime (BH streamer), core/mental+spiritual+akashic (plane engines, reference grade), anima-service/faiss_service (Akashic store), api/app.py + price_feed (Oracle), core/pipeline (publication), core/physical, core/planes, core/novel (Chameleon → AWA freeze hook), core/thermodynamics, validator/ Go (TRION DW-BFT), network/health_monitor, formal/ + math/ + signal-processing/ + WASM (verification/reference layers), schema.sql akashic-side tables, tests/.

**BTCP (payment/routing layer):**
- core/btcp/* (orchestrator, router, bibl_engine, escrow_monitor, modules, state_store, dispute_resolution, mainnet_bootstrap, rust_bridge), continuum/engines.py (BID/CME/PMO/BDC), core/extended/ (NL, SBA, XSL, BC feeders feeding the BTCP score), core/manipulation/btcp_mf_detector.py, api/btcp_continuum_routes.py, zg/ (0G transport integration), run_btcp_crossvm_full.py, schema.sql btcp_* tables (12, mirrored to SQLite by state_store), contracts btcp_escrow family (out of scope here).
- Cross-boundary object: the canonical certificate (ESCROW_RELEASE kind) is the TRION→BTCP hand-off — produced per TRION consensus semantics, consumed by BTCP escrow contracts.

— END SWEEP-A —
