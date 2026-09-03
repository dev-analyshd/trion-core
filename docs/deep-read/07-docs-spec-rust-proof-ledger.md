# Deep Read: docs/ + spec/ + rust/ + proof-ledger/ (Agent 2-g)

**Scope:** 80 files read in full — `docs/` (21), `spec/` (14), `rust/` (25), `proof-ledger/` (20).
**Repo:** /home/z/trion-core (TRION Protocol, "behavioral truth oracle", branch main).
**Method:** every file read end-to-end; JSON artifacts parsed; Rust `#[test]` count machine-verified (94); cross-references grepped.

---

## 1. Overview

TRION is presented as a five-plane behavioral coherence oracle (Φ physical entropy, M mental, Σ validator consensus, K human annotation, A "ANIMA") whose master equation `T(t) = [C≥Θ]·C·e^M_moat` gates signal emission (SILENCE unless coherent), plus **BTCP**, a "zero-bridge" cross-chain routing protocol implemented as a Rust crate, a Python core, Solidity contracts, and a multi-VM deployment story.

My four directories reveal a project with **three mutually inconsistent canonical layers**:

1. **`spec/` (L0–L9)** — a clean, self-consistent 14-document specification of a *chain-internal* consensus protocol (BFT quorums, slashing, fork resolution, lunar governance cadence). Its "BTCP" = *Behavioral Trusted Channel Protocol / TRION Behavioral Transfer Protocol* (a jurisdictional/compliance transport).
2. **`docs/FORMULA_REFERENCE.md` + README claims** — a *different* canonical mapping (84/105 formulas, 19 modules, BTCP_score weights, sybil layers) describing BTCP as the Rust *zero-bridge router*.
3. **`rust/src/*`** — implements the FORMULA_REFERENCE version of BTCP, **not** the spec/ version. The spec/ layer (L0.1 BH layout, DW-BFT quorum formula, L4 8-component genome, slashing registry, HHI×10000 tiers, F1–F15 falsifiability) has **no Rust implementation in this crate**.

`proof-ledger/` is a directory of deployment receipts (addresses + tx hashes + balances) for 13 networks, mostly from a **self-declared "tainted" deployer wallet**, with honest failure records mixed into marketing-grade summaries elsewhere.

The docs themselves disclose a coherent "honest bootstrap" posture (MAINNET_RUNBOOK is unusually candid: no third-party audit, D(t)=18.3%, tainted deployer, no validator network). The problem is **documentation drift**: at least 5 different chain counts, 4 different PCR/HA/CA expansions, 3 different ANIMA bootstrap values, 3 different test totals, and spec↔docs formula conflicts on nearly every shared constant.

---

## 2. Per-directory findings

### 2.1 docs/ (root, 7 files)

- **ARCHITECTURE.md** (284 ln) — Five-plane ASCII diagram; C(t) formula; dynamic Θ(t)=0.55+0.37·V; moat `e^(D·Q·R·X·F·N)`; 6 VM adapters; 5 ZK circuits; 6-step BTCP execution; security (Genomic Key evolving every 100 blocks, Chameleon σ 0.002→0.025, escalation 2.5×); FAISS stats "980 vectors, 16 entities, 64 archetypes" (vs endpoints.md "current_depth 1,262,330" and audit "22,080 vectors" — three different index sizes). Config table: A_bootstrap **0.28** (conflicts with 0.10 in 3 other docs).
- **README.md** (25 ln) — index; links `research/formal/…`, `research/math/…` etc. but actual path is `research/archive/` (all 4 links broken); links `TRION_FUNDING_GUIDE.md` which **does not exist anywhere in the repo**.
- **FORMULA_REFERENCE.md** (446 ln) — the most load-bearing doc. L0.1 BH = 93-byte payload `entity_id(32)||event_type(1)||magnitude_nano(8)||context(8)||timestamp(8)||chain_id(4)||block_hash(32)`, dual-strand sense/antisense SHA3-256; 20 event types; BEO weights 0.40/0.25/0.25/0.10 (4-signal); 9 Φ features (volume entropy, counterparty diversity, … MEV); 7 MF types with exact trigger values; Θ tests Θ(0)=0.55, Θ(0.5)=0.735, Θ(1)=0.92; DEFAULT_BALANCED α/β/γ/δ/ε = 0.25/0.30/0.25/0.10/0.10, 11 profiles; moat N(t)=1−e^(−t/τ), τ=1e8s; **BTCP_score = [0.25·NL + 0.20·normalize_gas + 0.20·finality_conf + 0.15·CC + 0.20·BEO_continuity]×(1−MF)** with "route valid: score>0.10 ∧ NL>0.05 ∧ finality>0.80 ∧ validators≥3"; sybil L1 `⌊log₂(D/D_min)×10⌋`, L2 `1+0.2n`, L4 `7n²`, L5 ">20 sponsored"; BITP "magnitude within 2% tolerance"; finality "max(A,B) NOT A+B"; OOA `conf_max·(1−e^(−k·depth))`, Θ×1.5; validator fees `BASE·rarity·volume·uptime` 60/40. Verification totals table: 105 formulas, 533 unit, **25 Rust tests**, "900+ checks" — the 25/94 and 84/105 discrepancies are pure staleness. References `rust/src/living_security.rs` — **file does not exist**.
- **DEPLOYMENT.md** (344 ln) — nginx/gunicorn/systemd/docker ops guide; ports 5000/8000/6000/3000; systemd sandboxing flags; claims EVM "✅ Production" incl. Avalanche (no deployment receipt for Avalanche in proof-ledger); dated 2026-08-15.
- **MAINNET_RUNBOOK.md** (138 ln) — **the most honest doc in the repo.** States: professional audit ❌ REQUIRED, Akashic depth 18.3% (8,439/46,051), validator network bootstrap-only, deployer wallet **TAINTED** (`0xdBbf66…42d20`, key exposed in git history) — "all contracts must be redeployed from a fresh key". Claims "94/94 Rust, 105/105 formulas, 671 Python, 30/30 Golden". Phase plan: observation-only 6 months → 100 validators/4 continents → INIT ceremony → only then BTCPEscrow.
- **SUBMISSION.md** (182 ln) — 0G APAC Hackathon 2026 pitch. Claims 37 chains/13 VM families, 84/84 formulas, 184 tests+5 skipped, **12 implementation languages**, 0G 6/6 components, "$44B+ would have been blocked", 168h Ronin lead time, 10 archetypes (GUARDIAN 0.97 … FLASH_LOAN_ATTACKER 0.04). Integration snippet shows `checkExecution(msg.sender)` returning `(bool, string)` — **the deployed ABI (proof-ledger) takes `(bytes32,address)` and returns `(bool,bytes32)`**.
- **CHAIN_MANIFEST.md** (97 ln) — 126 chains / 18 VM families / 22 indexer crates, bridge-pair math N(N−1)/2=7,875, canonical 20-type event table. (README elsewhere: 21/21 crates; SUBMISSION: 37 chains; RUNBOOK: 87 chains — four different chain counts.)

### 2.2 docs/architecture/ (4 files)

- **five_planes.md** (103 ln) — plane math; 7 asset weight profiles (DEFAULT 0.25/0.30/0.25/0.10/0.10). Defines PCR = *Positive Cultural Reception*, HA = *Historical Alignment*, CA = *Cross-lingual Agreement*.
- **bootstrap.md** (73 ln) — bootstrap values Σ=0.25, K=0.10, **A=0.10** (vs ARCHITECTURE 0.28); "D(t) 1.26M+ behavioral events"; 4 falsifiable predictions.
- **chameleon.md** (85 ln) — noise σ_base 0.002 / σ_probe 0.025, escalation text says "0.002→0.027" (=base+probe; ARCHITECTURE says 0.025); threshold 1.8; cites `src/security/chameleon_protocol.py` — a **stale Replit path** (repo has `core/…`).
- **living_security.md** (88 ln) — GK evolution, CRISPR 4 signatures, innate/adaptive immunity; "classical fallback threshold 0.55 regardless of volatility".

### 2.3 docs/audit/ (3 files)

- **README.md** (17 ln) — 84/84 formulas, **337 tests** passing, "19 bugs fixed in June 2026 session".
- **TRION_COMPLETE_AUDIT.md** (558 ln) — "Deep Senior Architect Audit" dated 2026-06-01, auditor = **"Replit Agent (Senior Architect Mode)"** — i.e., a self-audit, not third-party (contradicting its directory README's "independent audit reports" claim). Verdict "97% production complete". Formula tables map L0.x–L10 to `src/core/…` paths that **don't exist in this repo** (audit ran against the old Replit layout). PCR/HA/CA = *Pattern Coherence/Historical Accuracy/Chain Alignment* — a **fourth** expansion of the acronyms. Parts: 24 signals, 7 primitives (P1 BH, P2 BEO, P3 Akashic, P4 ZK partial, P5 Living Security, P6 BIRP, P7 Relayer) — **a different P1–P7 set than spec/novel_primitives.md**; 20 channels (17 active, 2 stubs: IUCN + HSM, 1 mainnet); F1–F15 **completely different conditions** than spec/falsifiability_registry.md; 5 open research questions Q1–Q5; 15 contracts "deployed" incl. "Solana devnet ✅ LIVE" (proof-ledger says ACCOUNT_CREATED only) and NEAR "304,895-byte WASM" (which is `/tmp/near_hello.wasm` — a hello-world artifact).
- **AUDIT_REPORT.md** (217 ln) — 2026-06-04, "Implemented by Replit Agent — autonomous engineering session". 9 workflows RUNNING; T001–T008 fixes (ethers/es5-ext install, FAISS degradation fields `faiss_enriched`/`degraded_mode`/`data_staleness_s`, ANIMA PCR/HA/CA de-stubbed, falsifiability sample counts wired). 337 pass/24 skip. Honest residuals: all relayers DRY_RUN, 0G DA DNS unreachable, test_e2e OOM.

### 2.4 docs/proofs/ (2 files)

- **attack_simulations.md** (86 ln) — 7/7 historical attacks "blocked" via SILENCE (C≈0.40 < Θ≈0.81). Listed losses sum to **$738.5M** (197+114+182+61+89+46+49.5) but the doc claims "Total value protected: $388.9M" — arithmetic error. Includes "AAVE March 12 **2026**" — a *future/fictional* event presented as historical evidence.
- **falsifiability.md** (82 ln) — 5 predictions, attack replay table (Harvest −1 block etc.), "What TRION does NOT claim" section (commendable), forge-cost estimate $5,000 for D=1M on 5 chains.

### 2.5 docs/research/archive/ (4 files)

- **proofs.hs** (249 ln) — GADT `TRIONSignal EmitsValue/NoValue` (type-level SILENCE≠VALUATION — genuine and neat); everything else is **symbolic, not proofs**: `coordinationCollapse c = max 0 (1−c)` is a tautology; `verifyStrands` only checks `length == 32` (verifies nothing); `complementTransform` implements a **fake XOR** (`a mod 256 + b mod 256 − 2*(...)`, comment admits "Simplified… production uses Data.Bits"). COUNT: 6–7 "theorems" here vs FORMULA_REFERENCE "9 theorems" vs README "7 Theorems".
- **trion_math.jl** (406 ln) — clean numeric self-test: BRT phases, scale-invariance (trivially true for normalized entropy), entropy budget, PI calibration, Kolmogorov bound product form, Θ endpoints, NL product. Fine as sanity checks; "PROVED" labels on `prove_coordination_collapse` are just restatements (d=1−corr → 0).
- **signal_processor.cpp** (333 ln) — real iterative radix-2 Cooley–Tukey FFT + spectral-entropy coordination detector + /dev/urandom entropy + TI computation. Legitimate, self-contained, compiles standalone. Best-engineered file in docs/.
- **validator_network.go** (583 ln) — HTTP-based "P2P" validator mesh (handshake/consensus/peers/hhi endpoints), ComputeSigma/ComputeDiversityWeight/computeHHI (×10000 tiers 1500/2500/4000), heartbeat goroutine. **Bugs:** `broadcastHeartbeat` POSTs a **nil body and discards the marshaled payload** (`_ = payload`) — heartbeats carry no data; `SignMessage` hashes with SHA-256 and calls it a signature — `privateKeyHex` **unused**, no actual cryptography (security theater).

### 2.6 spec/ (14 files) — the L0–L9 layer spec

| File | Purpose / key contents |
|---|---|
| L0_universal_primitives.md | BH **93-byte layout: strand_A(32)+strand_B(32)+meta(16)+beo_id(9)+crc32(4)** (≠ FORMULA_REFERENCE layout!); BEO 0.85/0.50 thresholds with an audit note that production is 0.75/5-factor "code wins" citing a `TRION_AUDIT_REPORT.md` **that doesn't exist**; resonance R(X,Y) = 1/(1+Hamming)·cos(Δphase) with 4 channel bands; conservation I_total; signal selection τ=0.003 nats; fitness F=PA·ICE·AS·Love |
| L1_physical_layer.md | 9 features = **price ticks, volume profile, order-book imbalance, gas dist, inter-arrival, actor clusters, oracle updates, governance proposals, bridge flows** (≠ docs feature set); MF registry M1–M7 thresholds 0.70–0.85 (different from docs); TC = exp(−Δt/τ)·xcorr; TI = 1−\|H_phys−H_beh\|/H_phys |
| L2_akashic_index.md | D(t) exponential-decay integral (≠ docs' depth accrual formula); depth *tiers* 10/1/0.1; archetype cosine; GC decay μ=0.005; 5 dormancy types R1–R5; fork scoring; trajectory TA L2-norm tiers |
| L3_mental_anima.md | **M(t) = (1−η·O)(1−γ·PCL)·B** (≠ docs M=1−PI/PI_baseline); ANIMA tiers "unconscious <0.30 → Intelligence Maintenance"; PCL ≥ 0.05 bound; credibility EMA ρ=0.05; reflexivity dampening A−κ(A−A')² |
| L4_spiritual_security.md | **P_j = stake·(1+δ·d_j)** (a *bonus*, not multiplicative penalty — opposite of docs' s·d); quorum Q = 2/3 + 0.1(1−D); **8-component genome G1–G8** (GK, complementary strand, immune, epigenetic, recombination, noise, mitochondrial, CRISPR); HHI_geo/HHI_infra on 0–0.25 scale (≠ ×10000); 6 slashing conditions S1–S6 |
| L5_trion_master.md | Θ_max "corrected from 0.90 per July 2026 audit" (audit not in repo); **plane meanings differ: Σ = akashic convergence, K = cross-chain knowledge** (docs: Σ = validators, K = human annotation); 6 profiles P1–P6 (≠ docs' 11); master eq T(t)=[C≥Θ]·S(t)·e^(M_moat·t) with M_moat ≤ 0.02/epoch (≠ docs' 6-factor D·Q·R·X·F·N moat); degradation tiers T0–T3 |
| L6_biological_capital.md | BC = Flow·Resilience·Uniqueness·Interdependence; BRT 4 rhythms; **lunar governance window [0.40,0.60]**; circadian window scaling ±20%; seasonal recombination |
| L7_natural_liquidity.md | NL = LD·LO·LC·LS (matches docs); EP = VC·PA·DC; LH=√(NL·EP); NL tiers differ (docs: <0.30 alert; spec: ≤0.20 unnatural) |
| L8_sovereign_behavioral.md | SBA weights **0.30/0.20/0.20/0.15/0.15** (FORMULA_REFERENCE: 0.30/0.25/0.20/0.15/0.10); SDP privileges/obligations; sovereign Θ_min 0.65 |
| L9_cross_species.md | XSL = TV·FS·RR/(1+TP) (matches); K = 0.5·XSL+0.5·CI; conservation audit per lunar cycle; **"I_TRON" vs "I_TRION" typo** |
| signal_types.md | 24 canonical signals S1–S24 with mandatory envelope; **BTCP = "Behavioral Trusted Channel Protocol"** (S23 BTCP_ROUTE) |
| communication_channels.md | 20 channels C1–C20 in 10 layers; C17 = "TRION Behavioral Transfer Protocol (BTCP)" — **a third BTCP expansion** |
| falsifiability_registry.md | F1–F15 = **entirely different conditions** than the audit/proofs F1–F15 (spec: BH collision rate <10⁻¹⁸, BEO monotonicity, resonance AUC, DW-BFT halt rate, ZK soundness <10⁻⁹ …) |
| novel_primitives.md | 7 primitives: P1 Semi-Immutability, P2 **Behavioral Causal Keys (Argon2id KDF over BH history)**, P3 DW-BFT, P4 Behavioral ZK, P5 **BIBL inheritance ledger**, P6 BIRP recovery, P7 **Chameleon regulatory adaptation** — overlaps only P4/P6 with the audit's primitive list |

**Assessment:** spec/ is well-structured (consistent cross-references, invariants per formula, threshold tables) but describes a protocol that the Rust crate and most of docs/ do not implement; it reads like a separately commissioned ideal design. The internal quality is good; the *alignment* with the rest of the repo is poor.

### 2.7 rust/ (25 files) — crate `trion-btcp` v0.1.0

- **Cargo.toml** — name `trion-btcp`, deps only `sha3`+`hex` (no serde, no async, no crypto signing). BTCP = "Behavioral Transaction Continuity Protocol" — **a 4th expansion of the acronym**. 2 binaries.
- **Cargo.lock** (102 ln) — 10 transitive crates (sha3/block-buffer/cpufeatures/generic-array/typenum/keccak/libc + hex). Trivially small, consistent.
- **lib.rs** (63 ln) — declares **20 modules** (19 + types), re-exports, `BTCP_VERSION=1.0.0`, `GAS_99TH_PERCENTILE=1000.0`, **`MIN_BTCP_SCORE=0.50`**, `SAFE_CONFIRMATIONS=64`. Doc claims "All 19 required Rust modules per the BTCP Master Implementation Spec" — note: **the "BTCP Master Implementation Spec" itself is not in the repo** (referenced only by §-numbers in comments; grep shows no spec file defines §Phase 2 / §4.2 / Water Principles 1–7).
- **types.rs** (500 ln) — H256 (SHA3 helpers, hex round-trip), Intent (+`hash()` = SHA3 of a **format! string**, not the canonical 93-byte BH — no dual-strand anywhere in this crate), RouteType enum with **exactly 7 variants** (SingleChain, Split, Netting, Parallel, MultiHop, Deferred, BITP) ✓, PrivacyLevel 5 tiers, WeightedSignature/DiversityCertificate/ConsensusProof/BTCPProof, escrow/BLO/channel/dispute types. Clean, no unsafe.
- **btcp_router.rs** (443 ln) — `btcp_score()` = **(0.25·nl + 0.20·normalize_gas + 0.20·finality + 0.15·cc + 0.20·beo_continuity)×(1−mf)** — **weights match FORMULA_REFERENCE exactly ✓**. `select_route_type()` implements priority NETTING→SINGLE→MULTIHOP→PARALLEL→BITP→DEFERRED→SPLIT with policy consts (NL_ILLIQUID 0.30, PARALLEL ≥1e21 units, MULTIHOP_NL_LIFT 0.10, DEFER_MIN_LEAD 3600s, ultradian 5400s window). 11 tests incl. one per route type. `route_is_valid()` = score ≥ 0.50 only (no NL/finality/validator sub-checks → **deviation from documented validity rule**).
- **bibl_engine.rs** (262 ln) — per-chain state map + fork assessment. **`detect_fork()` returns hardcoded retention numbers (0.7/0.65/0.8 vs 0.3/0.35/0.2)** regardless of input — a stub. `diversity_penalty()` returns constant 0.0; `register_endpoint_diversity()` returns true unconditionally. `update_fork_assessment()` conflates "Chain B canonical" and "Undecided" (both → None).
- **btcp_proof_builder.rs** (230 ln) — builds BTCPProof (route_id = SHA3 of concatenation), cert windows by value tier (50k/100k/200k/500k blocks). `verify_proof()`: coherence≥threshold, **HHI ≤ 0.5 (0–1 scale — incompatible with the ×10000 convention used in docs/Go/spec)**, ≥3 signatures (✓ matches "validators ≥ 3"), version ≥1. **`current_block` parameter is unused — no expiry/reorg check despite the module's "reorg protection" docstring.** Mock signatures = 64 identical bytes.
- **btcp_escrow_monitor.rs** (317 ln) — 4-state machine (Holding/Released/Reverted/Disputed; **docs say 6 incl. IDLE, PENDING_AKASHIC, EMERGENCY_REVERTED**); 24h akashic-recovery & 7d emergency constants present but no logic uses them; dual-chain atomic_release (all-or-nothing) ✓; process_timeouts ✓. 7 tests.
- **bitp_matcher.rs** (175 ln) — CUT/MATCH/PASTE clipboard. Complement = asset swap + ratio within `price_tolerance` (parameter; test uses 1000.0). `execute_paste` removes both commitments with **no complementarity validation of the pair**. 2 tests.
- **netting_engine.rs** (249 ln) — reverse-direction pool matching; **tolerance is a parameter** `|Δamount| ≤ tol·amount` (u128-safe); tests use 0.10; **no 2% constant anywhere** (docs' "2% tolerance" is not implemented); `netting_gas_cost` = 5% + per-user overhead. 6 tests. Full-fill flag, remove_intent, same-direction rejection all correct.
- **intent_aggregator.rs** (166 ln) — pools by direction; MIN_INTENTS=3, MAX_POOL_SIZE=1000; `compute_per_user_gas_weighted` = G_total×value/total ✓ matches IAP formula; equal-split variant explicitly "value-weighted in production". 4 tests.
- **ooa_anchor.rs** (139 ln) — `conf_max·(1−e^(−k·depth))`, k=0.001, cap 0.85 ✓; Θ×1.5 penalty ✓ (0.55→0.825 exact test). 3 tests.
- **shadow_observer.rs** (213 ln) — collects (simulated) cross-chain references for hostile chains; `compute_shadow_bh` = SHA3 over concatenated "hash:conf:div" strings + avg confidence — a **string-hash, not the documented weighted Hash_DNA**; rejoin transfers `len×100` "depth" and computes N(N−1)/2 eliminated pairs ✓. 4 tests.
- **state_capsule.rs** (142 ln) — capsule build with escrow_lock = balance>0 (over-assumptive); `estimate_staleness` = volatility·√(latency/60) capped 0.1 — heuristic, undocumented in spec. 3 tests.
- **btcp_failure_classifier.rs** (210 ln) — External (outage/NL collapse/reorg>64/MF spike) vs Entity (invalid proof/collateral withdrawal/conflicting intents/systematic timeout) vs Ambiguous with **three-strikes-in-90-days** escalation ✓ matches its own docstring. 6 tests.
- **genesis_commitment.rs** (201 ln) — 3 pathways; `layer1_max_sponsored` uses **`ln` not `log₂`** and d_min default **100** (spec/whitepaper D_min = 10,000) — double deviation; cosine similarity + sockpuppet ≥0.85 ✓. 5 tests.
- **blo_scheduler.rs** (210 ln) — triple-window intersection (circadian∩NL∩MEV), fallback to circadian; gas<50 gwei heuristic; 12s-block/300-blocks-per-hour constants (Ethereum-centric). 6 tests.
- **behavioral_state_channel.rs** (226 ln) — open/record/close lifecycle, chain of Akashic-record hashes, dispute state; savings formula (N−2)/N → >90% at 50 interactions ✓. 3 tests.
- **finality_normalizer.rs** (128 ln) — `effective_latency = max(A,B)` ✓ exactly per docs; vs-bridge comparison; safe confirmations ×1.2 margin; CI max-of components. 5 tests.
- **btcp_version_handler.rs** (143 ln) — SemVer parse/compat, breaking = major delta; version penalty 50% major / 5% per minor capped 20%; ADAPTER_VERSION_BONUS 1.1. 6 tests.
- **validator_fee_calculator.rs** (272 ln) — coverage bonus `BASE(100)·rarity·volume·uptime` ✓, rarity = total/covering (5% → 20×) ✓, **60/40 anchor/exec split ✓**, route fee 0.1%; `NetworkStats` struct added to replace earlier hardcoded placeholders ("Fix 4", never invent rewards when stats absent) — evidence of real remediation work. 5 tests.
- **sybil_resistance.rs** (227 ln) — 5 layers: **L1 `ln` not `log₂` (deviation)**; **L2 1+0.5n (spec: 1+0.2n)**; **L3 ≥0.85 (spec: >0.85, trivial)**; **L4 `7×(1+0.5n)` days — linear, spec says `7n²` (n=3 → 17d actual vs 63d spec — 3.7× weaker protection)**; **L5 star at ≥5 sponsored (spec: >20)**. `can_sponsor` composes L1/L3/L4 but **never applies L2 scrutiny or L5**. 6 tests.
- **dispute_resolution.rs** (243 ln) — 3-of-5 majority, duplicate-vote rejection, auto-resolve at 5th vote ✓; annotator selection = **first 5, not random** ("production uses random selection"). 5 tests.
- **bin/router.rs** (77 ln) & **bin/escrow_monitor.rs** (71 ln) — **demo programs**: hardcoded intent/escrow, print route, then `--service` flag = `loop { sleep(60s) }` doing nothing. No RPC, no networking. The "Standalone BTCP routing service" claim is overstated; the main README at least labels the escrow one "demo".

**Test count:** `rg '#\[test\]'` = **94 exactly** — matches the "94/94 Rust" claim in MAINNET_RUNBOOK/README *by count*. No cargo toolchain in this sandbox, so pass status is unverified, but the code is dependency-light and the assertions are consistent with implementations, so passing is plausible.

### 2.8 proof-ledger/ (20 files)

**What it is:** a machine-written deployment receipt folder — JSON snapshots of contract deployments (addresses, tx hashes, balances, errors) plus one ABI. It is the evidence base for SUBMISSION's "live contracts" claims.

- **TRIONExecutionGate.abi.json** (34 entries; 25 functions, 8 events) — `checkExecution(bytes32,address)→(bool,bytes32)`; publishSignal; add/removeValidator; setQuorum; confirmStorageSync; stats counters; statuses SAFE/ELEVATED/COLLAPSE/HOSTILE. **Signature contradicts SUBMISSION.md's `checkExecution(msg.sender)→(bool,string)`.**
- **deploy_zerog_mainnet.json** — 0G Mainnet (16661) TRIONExecutionGate `0xA85B49…4199b` from deployer **0xEB909B…c911 (a fresh, non-tainted key)**, tx 0xb83aa8ce…, 2026-05-14 — the one genuinely clean mainnet artifact.
- **deploy_zerog_galileo.json** — full suite (OracleV3, LiquidityOcean, TravelRuleCompliance, BTCPSimpleEscrow, ExecutionGate) — but deployer = **tainted 0xdBbf66…42d20**.
- **btcp_infrastructure_deployments.json** — 10 entries; `integration.router` and `integration.attester` = the **same tainted EOA** (the "diversity-weighted validator" story reduced to one wallet); BNB + Base "failed" (replacement fee too low); HashKey mainnet "live" **with an embedded error string**; **duplicate keys `zeroG_galileo` and `zerog_galileo`** with different LiquidityOcean addresses (0x8D2Ab5… vs 0x105c7F…) — data-quality bug; ARB smoke test (proof/commit/settle txs + travelRuleVerified) is the strongest E2E evidence in the repo.
- **trion_relayer_live_txs.json** — relayer wallet = tainted EOA; **the same oracle address `0xb819c63c…` listed for 5 different chains** (arb/eth/base/op-sepolia + hashkey) though per-network deploy files show different oracles — copy-paste error in the "proof" ledger; honest NO_FUNDS notes for BNB/0G; Starknet "3/5 TXs confirmed… nonce collision, being fixed"; 0G storage upload blocked by 0 balance.
- **Per-chain deploy files** — eth_sepolia (insufficient balance note), arb_sepolia (V3+V4 oracles + escrow; **BTCPEscrow and BTCPSimpleEscrow aliased to the same address**), base_sepolia (note says "Escrow not yet deployed" **while listing escrow address + tx** — stale note), bnb_testnet (insufficient funds 0.0000078662 ETH), hashkey (mainnet 177 because testnet RPCs failed), 0g (escrow pending funded wallet), op_sepolia (live), **svm (status ACCOUNT_CREATED — "Upload BTCP .so binary to activate" → Solana program NOT deployed)**, **ton (FUNDED_RPC_RATE_LIMITED, deployTx null)**, **pvm (westend, 0 WND balance, no deploy)**, **near (deployed `/tmp/near_hello.wasm`, 304,895 B)**, polygon_amoy (**status: failed**, insufficient funds).
- **zg_storage_sync_latest.json** — storage root + merkle root + 1,020 vectors, **`uploaded_to_0g: false`**; chain_id says 16661 (mainnet) but explorer link points to **Galileo** (testnet) — mislabeled.
- **btcp_oracle_v4_addresses.json** — v4 oracle addresses; file/field naming confusion ("contract": "TRIONOracleV3", "version": "v4").

**Big picture:** the ledger is honest at the leaf level (failures recorded) but the aggregate claims built on it (SUBMISSION "LIVE", audit "15 contracts deployed") inflate partial deployments (account-created, funded-but-rate-limited, failed) into successes. ~10 of 20 files record success; the rest record failures or partials — all from the wallet the project itself declares tainted, except the 0G mainnet gate.

---

## 3. Spec-vs-implementation compliance matrix

The operative "19-module" spec is the **BTCP Master Implementation Spec referenced from rust/src** (not present in repo; reconstructed from module docstrings + FORMULA_REFERENCE "BTCP — Zero-Bridge Protocol" section). Matrix keyed to the 19 modules + shared plumbing:

| # | Module (rust/src) | Spec source | Implements docs formula? | Verdict |
|---|---|---|---|---|
| 0 | types.rs (plumbing) | — | 7 RouteType variants ✓; 8 RouteStatus; Intent hash = naive string SHA3 (not canonical BH) | ✅ structurally / ⚠️ not canonical hash |
| 1 | btcp_router.rs | §Phase 2, §4.2 | Weights **0.25/0.20/0.20/0.15/0.20 ×(1−MF) exactly ✓**; 7 route types all selectable ✓ | ✅ (validity rule deviates: 0.50 vs 0.10+NL+finality+validators) |
| 2 | bibl_engine.rs | §Phase 2 | Multi-chain snapshot ✓; **fork assessment hardcoded stub**; diversity penalty stub | ⚠️ partial |
| 3 | btcp_proof_builder.rs | §Phase 2 | Proof struct + HHI + ≥3 validators ✓; **current_block unused → no reorg/expiry check**; HHI scale mismatch (0–1 vs ×10000) | ⚠️ partial |
| 4 | btcp_escrow_monitor.rs | §Phase 2 / Gap 8/9 | Holding→Released/Reverted + atomic dual release + timeouts ✓; **4 states vs documented 6**; PENDING_AKASHIC/EMERGENCY logic absent | ⚠️ partial |
| 5 | bitp_matcher.rs | §Water P1 / §5.1 | CUT/MATCH/PASTE ✓; complement + tolerance ✓; **no 2% constant**; paste doesn't validate pair complementarity | ⚠️ partial |
| 6 | netting_engine.rs | §Water P1 ext | Reverse-direction match + tolerance + full-fill ✓; **tolerance parameterized, tests at 10%, no spec'd value** | ✅ mechanism / ⚠️ constant |
| 7 | intent_aggregator.rs | §Water P3 | Pool by direction, MIN 3, value-weighted gas share ✓ ("100× cheaper") | ✅ |
| 8 | ooa_anchor.rs | §Water P2 | `conf_max(1−e^{−k·depth})`, cap 0.85, Θ×1.5 ✓ exact | ✅ |
| 9 | shadow_observer.rs | §Water P2 ext | Shadow sources, rejoin, N(N−1)/2 ✓; BH = string hash, "depth" = count×100 (ad hoc) | ⚠️ partial |
| 10 | state_capsule.rs | §Water P4 | Capsule + staleness CI heuristic; escrow_lock assumption | ⚠️ partial |
| 11 | btcp_failure_classifier.rs | §Phase 2 | External/Entity/Ambiguous + 3-strikes/90d ✓ | ✅ |
| 12 | genesis_commitment.rs | §Phase 2 | 3 pathways ✓; **L1 formula ln≠log₂, d_min 100≠10,000** | ⚠️ formula drift |
| 13 | blo_scheduler.rs | §Water P5 | Triple-window intersection ✓, BRT 5400s ✓; heuristics Ethereum-centric | ⚠️ partial |
| 14 | behavioral_state_channel.rs | §Water P7 | Open/operate/close, savings (N−2)/N ✓ | ✅ |
| 15 | finality_normalizer.rs | §Phase 2 | **max(A,B) not A+B ✓ exact**, +20% confirmations margin | ✅ |
| 16 | btcp_version_handler.rs | §Phase 2 | SemVer compat, penalties, bonus 1.1 | ✅ |
| 17 | validator_fee_calculator.rs | §Phase 2 | BASE·rarity·volume·uptime ✓, **60/40 split ✓**, no-placeholder stats (Fix 4) | ✅ |
| 18 | sybil_resistance.rs | §Phase 2 | 5 layers present; **L1 ln≠log₂, L2 0.5≠0.2, L4 linear≠quadratic (17d vs 63d @n=3), L5 ≥5≠>20; L2/L5 unused in can_sponsor** | ⚠️ 4/5 deviate |
| 19 | dispute_resolution.rs | §Phase 2 / K plane | 3-of-5, dedup, auto-resolve ✓; selection not random | ✅ / ⚠️ |

**Cross-layer (spec/L0–L9) compliance: essentially 0%.** The rust crate contains no: canonical 93-byte dual-strand BH, DW-BFT quorum computation, 8-component genome, HHI×10000 enforcement, slashing, lunar cadence, L5.2 six-profile coherence, master equation, or F1–F15 registry hooks. Those live (if anywhere) in the Python core/ and validator/ trees covered by other agents.

**Headline spec claims verified:** BTCP_score weights ✓ (exact), 7 route types ✓, 19 modules + types ✓ (20 `pub mod`), 94 tests ✓ (by count), netting tolerance mechanism ✓ / 2% constant ✗.

---

## 4. Code quality assessment

**Rust crate: B-/C+.** Uniform structure (docstring→types→impl→tests), zero `unsafe`, zero dependencies beyond sha3/hex, every module unit-tested (94), constants documented against spec §-numbers. Weaknesses: (a) simulation-grade logic throughout — stubs in bibl_engine (hardcoded fork), shadow_observer (fabricated sources, `current_timestamp()` mixed into "deterministic" hashes making route/paste IDs non-reproducible across runs), proof builder mock signatures; (b) hashing via `format!` string concatenation instead of the canonical byte layout — the crate never produces a Behavioral Hash that would interop with the Python/Solidity/TS implementations; (c) parameter mismatches vs documented formulas (sybil layers, MIN score, escrow states); (d) `current_timestamp()` called inside `classify`/`create_route` harms testability; (e) binaries are print-and-sleep demos.

**spec/: B+.** Best-written prose in the repo: consistent notation, per-formula invariants, threshold tables, cross-references resolve internally. Fails only as *the* spec, because the code follows a different one.

**docs/: C.** Informative but drifted: at least 15 material contradictions with code or with each other (enumerated below). The audit docs are self-audits with nonexistent file paths. FORMULA_REFERENCE is 80% accurate as a map of the *Python* implementation but cites a nonexistent `rust/src/living_security.rs` and stale test counts.

**proof-ledger/: C+ / honest.** Machine-generated receipts; failure states preserved (rare and good); but duplicate-case keys, copy-pasted oracle addresses across chains, stale notes contradicting sibling fields, and universal use of the self-declared tainted deployer undermine it as "proof".

**research/archive/: B for cpp, C for Haskell/Julia/Go.** C++ FFT is real code. Haskell leverages one genuine GADT theorem; the rest is decorative ("Q.E.D." on tautologies). Go mesh has a dead heartbeat and a fake signer.

---

## 5. Bugs / issues / inconsistencies (file:line)

**Cross-document contradictions (docs vs docs vs spec vs code):**

1. `docs/README.md:12-15` — links to `research/formal|math|hardware|validator/…`; actual path `research/archive/` — all 4 broken. Link to `TRION_FUNDING_GUIDE.md` — file absent from repo.
2. BH 93-byte layout conflict: `spec/L0_universal_primitives.md:22-27` (strand_A/strand_B/meta/beo_id/crc) vs `docs/FORMULA_REFERENCE.md:16-24` (entity_id/event_type/magnitude/context/ts/chain_id/block_hash). Same length, disjoint fields.
3. PCR/HA/CA expansions — 4 versions: Pattern Completion Ratio/Human Alignment/Cultural Alignment (ARCHITECTURE.md:126-128); Positive Cultural Reception/Historical Alignment/Cross-lingual Agreement (five_planes.md:86-90); Pattern Coherence/Historical Accuracy/Chain Alignment (AUDIT_REPORT.md:92-94); Predictive Coherence Ratio/Historical Accuracy/Contextual Awareness (spec/L3:94-96).
4. ANIMA bootstrap value: 0.28 (ARCHITECTURE.md:246) vs 0.10 (bootstrap.md:12, endpoints.md:171, FORMULA_REFERENCE L3.3).
5. M(t): `1−PI/PI_baseline` (FORMULA_REFERENCE:196) vs `(1−ηO)(1−γPCL)B` (spec/L3.1:20).
6. Plane semantics: Σ=validators, K=human (ARCHITECTURE/five_planes) vs Σ=akashic convergence, K=cross-chain knowledge (spec/L5.2:60-64).
7. F1–F15 registries disjoint: `spec/falsifiability_registry.md` (collision rates, AUC, halt rates) vs `docs/audit/TRION_COMPLETE_AUDIT.md:195-213` (MF precision, SILENCE precede rate…). Same IDs, zero overlap.
8. Sybil formulas: spec'd log₂/0.2/7n²/>20 vs implemented ln/0.5/linear/≥5 — `rust/src/sybil_resistance.rs:37-81` vs `docs/FORMULA_REFERENCE.md:379-385`.
9. Route validity: score>0.10∧NL>0.05∧finality>0.80∧validators≥3 (FORMULA_REFERENCE:355) vs `route.btcp_score >= 0.50` only (`rust/src/lib.rs:60`, `btcp_router.rs:216-218`).
10. HHI scale: ×10000 with 4000 critical (docs/Go/spec L4.8 uses 0.25) vs 0–1 with 0.5 limit (`rust/src/btcp_proof_builder.rs:104`).
11. Chameleon σ escalation: 0.025 (ARCHITECTURE.md:201) vs 0.027 (chameleon.md:42).
12. Chain counts: 126 (CHAIN_MANIFEST:3) vs 37 (SUBMISSION:104) vs 87 (RUNBOOK:66) vs "18 chains" relayer (AUDIT_REPORT:24).
13. Test totals: 25 Rust (FORMULA_REFERENCE:440) vs 94 (RUNBOOK:17, README) — code has 94; 84 formulas (SUBMISSION/audit) vs 105 (FORMULA_REFERENCE/README); 337 (AUDIT_REPORT) vs 533 (FORMULA_REFERENCE) vs 671 (README) Python tests; 328 vs 337 across the two audit docs.
14. Θ_max history: "corrected from 0.90 per July 2026 audit" (spec/L5.1:29) — that audit and `TRION_AUDIT_REPORT.md` (spec/L0.2:82) are not in the repo.
15. SBA weights 0.30/0.20/0.20/0.15/0.15 (spec/L8:45) vs 0.30/0.25/0.20/0.15/0.10 (FORMULA_REFERENCE:341).
16. checkExecution signature: `(bytes32,address)→(bool,bytes32)` (proof-ledger ABI) vs `(address)→(bool,string)` (SUBMISSION.md:18-20).
17. Attack-sim arithmetic: losses sum $738.5M but "Total value protected: $388.9M" (`docs/proofs/attack_simulations.md:6` vs :14-60); "AAVE March 12 **2026**" presented as historical (:56, :26).
18. "Independent audit reports" (`docs/audit/README.md:3`) — both audits performed by "Replit Agent" (`TRION_COMPLETE_AUDIT.md:2`, `AUDIT_REPORT.md:5`); RUNBOOK itself concedes "No third-party audit exists."
19. `rust/src/living_security.rs` cited as implementation (FORMULA_REFERENCE:274) — does not exist.
20. Escrow states: 4 in Rust (`btcp_escrow_monitor.rs:13-18`) vs 6 in docs (FORMULA_REFERENCE:362-371).
21. Audit's implementation paths `src/core/…`, `src/planes/…` (TRION_COMPLETE_AUDIT throughout) — nonexistent in this repo (stale Replit-era layout).
22. Netting/BITP "2% tolerance" (FORMULA_REFERENCE:392) — no such constant in Rust (parameter, tests at 10%/1000.0).
23. `deploy_base_sepolia.json` — "Escrow not yet deployed" note alongside populated `BTCPEscrow` + `escrow_tx` fields.
24. `btcp_infrastructure_deployments.json:121-137,168-185` — duplicate `zeroG_galileo`/`zerog_galileo` keys with conflicting addresses.
25. `trion_relayer_live_txs.json:8-45` — identical oracle address `0xb819c63c…` recorded for 5 chains (contradicted by per-chain deploy files).
26. `zg_storage_sync_latest.json` — `chain_id: 16661` (mainnet) + Galileo explorer link + `uploaded_to_0g: false`.
27. FAISS index stats: 980 vectors/16 entities/64 archetypes (ARCHITECTURE:212-214) vs 22,080/22,074 (AUDIT_REPORT:20-21) vs 1,262,330 depth (endpoints.md:173) vs 14,639 vectors (relayer_live_txs 0g_storage).

**Code bugs (rust):**

28. `rust/src/btcp_proof_builder.rs:97-119` — `verify_proof(proof, current_block)`: `current_block` unused; certification expiry computed (`compute_cert_expiry`) but never enforced → advertised reorg protection absent.
29. `rust/src/bibl_engine.rs:149-167` — `detect_fork` ignores inputs, returns hardcoded 70/65/80 retention and canonical=chain A.
30. `rust/src/bibl_engine.rs:190-196` — `update_fork_assessment` returns `None` for both "Chain B canonical" and "Undecided" (indistinguishable); also compares a_score to threshold without comparing to b_score.
31. `rust/src/sybil_resistance.rs:106-139` — `can_sponsor` applies Layers 1/3/4 only; L2 scrutiny and L5 star-pattern never enforced in the composite check.
32. `rust/src/btcp_router.rs:192-193` & similar in bitp/blo/dispute — IDs derived from hashes that embed `current_timestamp()` → non-deterministic route/commitment IDs (breaks reproducibility the "behavioral hash" narrative depends on).
33. `rust/src/intent_aggregator.rs:28-33` — `should_aggregate` compares `intent.constraints.deadline` but pool stores `window_deadline` as min of deadlines; `window_blocks` parameter of `find_aggregation_pool` unused.
34. `rust/src/state_capsule.rs:38` — `escrow_lock: balance > 0` — assumes any nonzero balance is escrowed.
35. `rust/src/btcp_version_handler.rs:55-66` — `version_penalty` minor-behind computed against `current.minor` without major context (2.9 vs 2.5 minor mismatch after major bump handled by early return, OK; but penalty uses absolute minor diff only — acceptable).

**Code bugs (research archive):**

36. `docs/research/archive/validator_network.go:459-481` — heartbeat POSTs nil body, discards `payload` (`_ = payload`); peers never receive validator info.
37. `validator_network.go:574-578` — `SignMessage` ignores `privateKeyHex`; SHA-256 digest presented as signature (no authentication).
38. `docs/research/archive/proofs.hs:207-218` — `complementTransform` is not XOR (admitted in comment); `verifyStrands` checks only lengths.
39. `proofs.hs:22 import Numeric (log)` — unused import; module won't exercise half its "theorems".

**proof-ledger / deployment integrity:**

40. All deployments except 0G-mainnet gate come from the wallet MAINNET_RUNBOOK.md:24 declares **tainted** (`0xdBbf66CAD621dA3Ec186D18b29a135d2A5d42d20`) — including the relayer wallet (`trion_relayer_live_txs.json:4`) and the router/attester roles in integrations (`btcp_infrastructure_deployments.json`).
41. Solana: program **not deployed** (account created only) — `deploy_svm_contract.json` vs audit claim "SVM contract ✅ LIVE".
42. NEAR: deployed artifact is `/tmp/near_hello.wasm` (`deploy_near_contract.json:8`) — placeholder-grade.
43. TON/PVM/Polygon Amoy: no successful deploy recorded (rate-limited / 0 balance / insufficient funds).
44. `deploy_arb_sepolia.json:11-12` — `BTCPEscrow` and `BTCPSimpleEscrow` = same address (aliasing two contract names).

---

## 6. Claims vs reality

| Claim (source) | Reality (verified here) |
|---|---|
| "94/94 Rust tests PASS" (README, RUNBOOK) | **94 `#[test]` exist — count checks out exactly**; not runnable in this sandbox (no cargo), but code/assert alignment makes pass plausible. FORMULA_REFERENCE's older "25" is stale. |
| "19/19 required Rust modules" (README, lib.rs doc) | **20 `pub mod`** = 19 modules + types ✓ structurally true — but the "BTCP Master Implementation Spec" it cites **is not in the repo**; compliance is self-asserted. |
| "Full 7-route-type selection" (README) | ✓ True — `RouteType` has 7 variants; `select_route_type` reaches all 7; 7 dedicated tests. |
| "Netting tolerance" (README) | Mechanism ✓ (parameterized `|Δ|≤tol·amount`, u128-safe); the docs' specific 2% constant is nowhere; tests use 10%. |
| BTCP_score 0.25/0.20/0.20/0.15/0.20 (FORMULA_REFERENCE, README) | ✓ Exact match in `btcp_router.rs:54-59` incl. ×(1−MF). |
| "84/84 (or 105/105) whitepaper formulas LIVE" (SUBMISSION, audit, FORMULA_REFERENCE) | **Unverifiable from my scope** (Python core is other agents' scope); the two counts contradict each other; audit maps them to nonexistent `src/` paths; spec/ describes a disjoint formula set. |
| "15 contracts deployed" (TRION_COMPLETE_AUDIT) | proof-ledger shows ~10 EVM successes (all tainted key), Solana account-only, TON/PVM not deployed, Amoy failed, NEAR hello-wasm. Only 0G mainnet gate (1 contract) from a clean key. |
| "Independent audit reports" (docs/audit/README) | Both are Replit Agent self-audits; MAINNET_RUNBOOK concedes no third-party audit exists. |
| "$388.9M protected" (attack_simulations) | Own table sums to $738.5M; includes a fictional 2026 AAVE event. SUBMISSION separately claims "$44B+ blocked" — a 100× jump with no evidence in scope. |
| "37 chains indexed" (SUBMISSION) vs "126 chains" (CHAIN_MANIFEST) vs "87" (RUNBOOK) vs "21/22 crates" | Four irreconcilable counts in four shipped documents. |
| "0G Storage: FAISS index + BH ledger persisted… ✅ Active" (SUBMISSION:32) | `zg_storage_sync_latest.json`: `uploaded_to_0g: false`; relayer: "manifest_computed_insufficient_og_for_confirm". |
| "The Bridge is Mathematics, Not Contracts" (lib.rs:4) | The crate's "hashes" are `format!`-string SHA3 with wall-clock timestamps — no canonical 93-byte dual-strand BH anywhere in rust/src. |
| "Honest disclosure 100/100" (TRION_COMPLETE_AUDIT:337) | Partially earned (RUNBOOK + failure receipts are genuinely candid) — but undercut by the audit's own overstatements (SVM "LIVE", nonexistent paths, $388.9M arithmetic). |

**Bottom line on claims:** the Rust-crate-level claims (94 tests, 19 modules, 7 routes, weights) are *literally true by count/structure*; the protocol-level claims (formula coverage, deployments, audits, protected-value) are inflated, stale, or rest on artifacts the repo itself flags as tainted or partial. The project's most credible asset is its candid runbook + failure-preserving proof-ledger; its least credible is the audit/audit-adjacent marketing layer.

---

## 7. Suggested next actions (for the author persona)

1. **Reconcile the three canonical layers**: pick spec/ L0–L9 *or* FORMULA_REFERENCE as canonical; add a redirect header to the loser. At minimum fix the BH 93-byte layout, F1–F15, PCR/HA/CA, SBA weights, sybil formulas, and plane-semantics conflicts.
2. **Fix the Rust formula drifts**: sybil L1 log₂, L2 0.2, L4 7n², L5 >20; wire L2/L5 into `can_sponsor`; add expiry check using `current_block` in `verify_proof`; adopt ×10000 HHI or document the 0–1 scale; align `MIN_BTCP_SCORE` and multi-condition route validity with docs; implement the 6-state escrow machine incl. PENDING_AKASHIC/EMERGENCY_REVERTED.
3. **Replace stubs or mark them**: `detect_fork` hardcode, shadow source fabrication, first-5 annotator selection, nil-body Go heartbeat, unused-key "SignMessage".
4. **Determinism**: remove `current_timestamp()` from commitment/route/paste ID derivation; implement the canonical 93-byte BH in `types.rs` so the crate interops with Python/Solidity hash_dna.
5. **proof-ledger hygiene**: dedupe `zeroG/zerog_galileo`, fix the 5-chain oracle copy-paste, resolve base_sepolia's stale note, relabel `zg_storage_sync` chain, and add a README stating which entries are tainted-key deployments.
6. **Docs**: update FORMULA_REFERENCE test totals (25→94), remove `rust/src/living_security.rs`, restore `TRION_FUNDING_GUIDE.md` or drop the link, fix `research/…` paths, recompute attack-sim totals, and re-caption the audits as internal self-audits.
7. **Verification**: re-run `cargo test` in CI with the count pinned (94) and gate the README badge on it; no cargo toolchain existed in this reading sandbox to confirm pass status.
