# Deep Read: core/ (149 files)

**Agent:** 2-a (Explore — core/ reader) · **Scope:** every file under `/home/z/trion-core/core/` (149 tracked files, ~42,964 lines, 25 packages) · **Read-only** (side-effect DBs created by test runs were deleted; `git status` clean).

Reading method: full end-to-end reads of all "special attention" files and most formula-bearing modules (~55 files read completely), remaining files read via docstring + structure + key-function inspection; several self-test suites **executed** to verify claims empirically.

---

## Overview (what core/ actually is)

`core/` is the Python "behavioral engine" of the TRION Protocol — the implementation layer of the whitepaper's L0–L9 formula stack. Its job, end-to-end:

1. **Ingest** on-chain events (`realtime/bh_streamer.py` polls ~60 EVM + ~37 non-EVM public RPCs) → compute canonical 93-byte dual-strand Behavioral Hashes (`primitives/behavioral_hash.py`) → persist to SQLite `bh_ledger.db` → push 128-dim handcrafted vectors to the FAISS service.
2. **Score** each entity across five "planes" — Φ (physical entropy, `physical/phi_engine.py`), M (mental/observer-effect, `mental/confidence.py`), Σ (validator consensus, `spiritual/consensus.py`+`sigma_engine.py`), K (human annotation, `spiritual/conscious/engine.py`), A (ANIMA intelligence, `mental/anima/engine.py`) — and combine them via the **Master Equation** `C(t)=αΦ+βM+γΣ+δK+εA` with dynamic threshold `Θ(t)=0.55+0.37·V(t)` (`master/coherence.py`), then `T(t)=[C≥Θ]·S·e^(M_moat·t)` (`master/master_equation.py`).
3. **Route** cross-chain value without bridges via BTCP (`btcp/` — router, orchestrator, escrow monitor, 15 modules) scored by `BTCP_score=[0.25NL+0.20gas+0.20fin+0.15CC+0.20BEO]×(1−MF)`.
4. **Secure** via "Living Security" (`spiritual/living_security/`) — Genomic Key evolution, CRISPR attack library, epigenetics, PQC round-trips — and govern via Love Protocol/AWA/falsifiability (`governance/`).

**The big picture:** core/ is two strata fused together:

- **Stratum A (genuinely implemented math):** coherence equation, moat, DW-BFT, dual-strand hashing, Schnorr multisig, PQC verification, BIBL pattern store, entropy features, escrow state machine, real public-API fetchers. Formula modules faithfully match their own docstrings, with weight-sum assertions and self-tests.
- **Stratum B (theatrical/placeholder):** CRISPR "immune defense" (substring matching of mnemonic strings), "106-chain bootstrap" (synthetic chain IDs, testnets counted), private BIBL (XOR "encryption"), non-EVM BH streamers (placeholder entities "unknown"), fabricated entropy values "to ensure signal selection gate passes", a fabricated future-dated (March 12, 2026) AAVE event used as evidence in two modules, and five fabricated 2026 attack signatures in the CRISPR library.

The repo maintains unusual *documentation honesty* in Stratum B (bootstrap disclosures "Σ=0.25", "K=0.10", "A=0.10", "not a simulation"/"synthetic-but-realistic" notes), but the surrounding claims infrastructure (channel registry "17/20 ACTIVE", primitives "7/7 IMPLEMENTED, 100%", "105/105 formulas") is self-asserted and partially non-reproducible.

---

## Per-directory findings

### master/ (13 files — the coherence core)
- **coherence.py** (259 L): L5 five-plane C(t). 11 weight profiles (7 asset-type + 4 query-mode: SPEED/INTELLIGENCE/CERTAINTY/FULL_SPECTRUM), all sum-1 asserted (line 128). Θ(t)=Θ_min+(Θ_max−Θ_min)·V, Θ∈[0.55,0.92]. Trend = OLS slope over last 5 C values (±0.02 bands). `eta_blocks = int(gap*1000)`. Bootstrap flags: Σ≤0.26, K≤0.11, A≤0.11. Delegates moat to MoatEngine. PC_limit (1−H_irr/H_future, clamped 0.9999). Self-test **runs and passes** (PHASE 14 PASS; needs PYTHONPATH due to absolute `core.` imports).
- **master_equation.py** (152 L): T(t)=[C≥Θ]·S·e^(M_moat·t), exponent clamped to e^36; S defaults to C. Clean, correct per its spec.
- **moat.py** (272 L): M_moat=D·Q·R·X·F·N. D=log1p(depth/1000)/log11; Q=K+0.15; R=1−0.30(M−0.5)²; X=log1p(depth/5000)/log3 (uses depth as proxy for chain breadth); F=0.90 registry baseline; N=1−e^(−t/1e8s) (τ≈3.17y). Self-test asserts monotonicity + [0,1] bounds over 4×4×4×3 grid — passes.
- **signal_factory.py** (1088 L): 24 signal types (19 canonical + 5 extended), each builder with CI_95, BRT 4 phases, genomic_signature (dual-strand SHA3 over entity+generation), bootstrap metadata. **Bugs:** `provenance: []` (line 194) — every signal ships an empty provenance list despite module header claiming "full provenance chain"; line 73 imports `akashic.brt_scheduler` (nonexistent at that path) inside try/except — observed-timestamp BRT path silently dead. Self-test passes (24/24).
- **btcp_score.py** (88 L): L1.1 BTCP score, is_safe = score≥0.50 ∧ NL≥0.30; BITP match quality weights.
- **channel_architecture.py** (384 L): 20-channel registry. **impl_paths are stale/broken** (src/signals/…, src/planes/…, cpp/sensor_interface.cpp, wasm/signal_processor.wat, go/validator_mesh.go — none exist at those paths); 17/20 marked ACTIVE — self-asserted.
- **trion_primitives.py** (314 L): registry declaring 7/7 primitives "IMPLEMENTED", completion 100.0% — self-declared status reporter, no external validation.
- **d_engine.py** (91 L): D(t)=Σ BH_count·e^(−0.0001·age_blocks)·(1+0.1(N_chains−1)); dormancy decay.
- **degradation.py** (196 L): NOMINAL/TIER_1/TIER_2/EMERGENCY tiers; `fund_safety_guarantee` property **always returns True** (a constant masquerading as an invariant).
- **homomorphic_mapping.py** (540 L): 9-dim universal feature space f1–f9; architecture-specific mappers (EVM native reference, BTC UTXO/CDD, Solana, Cosmos, generic); maturity weight w=1−e^(−λ·T). **Hardcoded** INTEGRATION_DAYS/LAMBDA_A tables (EVM 365d/0.010 … PI 60d/0.002) and default μ/σ baselines — presented as "Adaptive Layer" but constants are assumptions, not measurements. `verify_homomorphic_property` checks only ordering + vector distinctness (weak).

### btcp/ (11 files — cross-chain routing)
- **orchestrator.py** (762 L): BTCPOrchestrator + PrivacyRouter + CrossVMGateway + ProofAggregator; wires `zk/` and `adapters/`. **Synthetic elements:** STANDARD privacy generates a "dummy complementarity proof" from `secrets.token_bytes` (lines 177–187); IAP-share witness uses hardcoded economics (total_gas=1,000,000, entity_gas=151,000, fee 0.01 ETH, share 0.0015, 10 participants — lines 218–225); block_number hardcoded 18,000,000.
- **router.py** (293 L): Tier-2 route scoring; weights W_NL .25/W_GAS .20/W_FIN .20/W_COH .15/W_BEO .20; gas normalization vs 99th-pct reference $31; validity gates (score>0.10, NL>0.05, finality>0.80, ≥3 validators); module-level `_balance_reservations` dict (Gap E double-spend guard); `apply_oe_correction` (Gap G). Self-test passes.
- **bibl_engine.py** (348 L): per-chain Tier-1 state cache, endpoint-diversity penalties (A1), 30-day fork suspension + 67%-retention canonical-chain rule (Gap 12). `detect_fork` is caller-invoked (no actual chain watching here).
- **modules.py** (1168 L): modules 2.4–2.18. ProofBuilder with value-tiered cert windows (10K/50K/200K/500K blocks), consensus attestation wiring to `core.spiritual.consensus` (AUDIT-1 gap #5 fix), and **real Schnorr-multisig** consensus proofs via `signature_aggregation`; BITP matcher (CUT/MATCH/PASTE); netting engine; intent aggregator (N≥3); OOA anchor (conf=0.85·(1−e^(−0.001·depth))); shadow observer; state capsule; failure classifier (EXTERNAL vs ENTITY cause); genesis commitment (conf_genesis 0.01); BLO scheduler; in-memory state channel; finality normalizer (max, not sum); semver handler; validator fee calculator (rarity factor, 60/40 anchor/exec split); 5-layer sybil resistance (log2 cap, 0.2× scrutiny, 0.85 cosine, 7n² spacing, star pattern >20). All in-memory; economic figures ($0.05 netting gas, "78% savings", "100× cheaper") are illustrative constants. Self-test passes.
- **escrow_monitor.py** (318 L): IDLE→HOLDING→PENDING_AKASHIC→RELEASED/REVERTED/EMERGENCY state machine, 24h Akashic recovery window, 7-day anyone-callable emergency escape, recursive cascade revert. In-memory; self-test monkey-patches `time.time`.
- **dispute_resolution.py** (157 L): 3-of-5 annotator panel, 5% challenge bond, 72h window; memory-only singleton.
- **integration.py** (457 L): BTCPIntegrationHub imports anima-service modules by bare name (sys.path hack); PrivateBIBLProtocol — **XOR "encryption"** with SHA3-derived key, explicitly labeled "NOT cryptographically secure… production would use threshold Paillier/BLS"; `decrypt_payload` ignores the *content* of validator shares (threshold = count only); `zero_front_running_window()` returns 0 by assertion.
- **mainnet_bootstrap.py** (458 L): "106 chains, 14 VM families" registry. `_stable_chain_id = sha3(name)%100000` — **synthetic chain IDs** for most non-EVM entries; testnets (Sepolia, Holesky, Amoy…) counted inside mainnet phases; many entries have empty rpc/explorer URLs; only Ethereum carries an oracle address. Assertions (≥100 chains, ≥14 VMs, ≥4950 pairs) pass only by counting synthetic entries.
- **rust_bridge.py** (202 L): spec-compliance checker vs rust/src (19 files all present per agent 2-g); binary discovery incl. /tmp target dir.

### primitives/ (11 files — L0 core)
- **behavioral_hash.py** (364 L): **the highest-quality module in core/**. 93-byte canonical payload (entity 32‖event 1‖mag_norm 8‖context 8‖ts 8‖chain 4‖block_hash 32), 20 canonical event types with backward-compat aliases, log10 magnitude normalization (USD primary, token-unit fallback), dual-strand sense/antisense with XOR invariant **verified on every computation**, and `bh_from_rust_hex` strict ingestion of Rust-produced payloads (raises on tamper). Self-test passes.
- **hash_dna.py** (591 L): BTCP-layer Hash_DNA over keccak256 (420-byte 14-field payload, domain separator, currency IDs, context hashes per event type). **Silent fallback to NIST SHA3-256 when pycryptodome missing** (warned) — outputs would not match on-chain keccak. `verify_dual_strand` (lines 557–581) checks only lengths + non-zero XOR — does **not** verify complementarity (docstring admits needing original input).
- **entity_resolution.py** (272 L): BEO_confidence = 0.40CF+0.25ST+0.25SC+0.10BP, threshold >0.75 (strict). BP fallback is a **real deterministic SimHash-style 128-dim fingerprint** (chain/funder/timing/address-family/volume features hashed to ±1 dims, mean pairwise cosine) — an honest FAISS substitute, explicitly documented.
- **evolutionary_fitness.py** (218 L): F=PA·ICE·AS·Love with Love=0 → F=0 kill-switch; compute_love is all-or-nothing gates (5 conditions) + max(0.01,…) floor.
- **resonance.py** (273 L): Comm(A,B) iff shared event types; weighted-cosine resonance; **phase always 0.0** ("simplified: uniform phase unless timing data available" — never wired).
- **thermodynamics.py** (315 L): information-conservation ledger (I_total recursion with floor at 0), signal selection dI/dS>θ, KL information gain. Clean.
- **signal_packing.py** (227 L): 256-bit packed uint256 signal (status/coherence×1e6/threshold/block/ts/plane).
- **extended_payload.py** (364 L): optional 176-byte v2 payload with nonce + counterparty + protocol ID; domain magic "TRON".
- **event_types_generated.py** (33 L): regenerated enum from config/bh_schema_v1.json.

### spiritual/ (16 files — consensus, security, conscious)
- **living_security/__init__.py** (1381 L): the 8-component "Living Security System". Real parts: GenomicKeyEvolver (chained dual-strand hashes; `is_current_key` correctly rejects stale snapshots), EpigeneticLayer with SQLite persistence, recombination, decoy noise, mito core, thread-safe singleton. **Theatrical parts:** CRISPRDefense's KNOWN_ATTACKS is a ~126-entry list of *mnemonic ASCII signatures* (e.g. `b"HARVEST_FLASH_LOAN_ORACLE_MANIP"`) matched by **substring search against transaction bytes** (lines 667–697) — it only "intercepts" a tx whose raw bytes literally contain the exploit's label string; entries include **five fabricated 2026-dated attacks** (lines 594–606, header: "2026 — Simulated & Projected High-Severity Attacks"); ClassicalCryptoScore hardcodes sha3/aes/**zk_proofs** all True with no verification (1023–1039); `crispr_coverage = min(1, library/8)` (line 1125) is always 1.0 with 126 entries; `kolmogorov_bound` is a log2-sum heuristic. **Empirical bug:** self-test is non-idempotent — second run fails `Expected 126, got 127` (line 1339) because adaptive signatures persist in `akashic/crispr_adaptive.db` (side-effect DB written into the repo on import/run — verified, then cleaned).
- **living_security/pqc_layer.py** (635 L): **genuinely good** — real ML-KEM (kyber-py), ML-DSA (dilithium-py), SLH-DSA/SPHINCS+ (pyspx) keygen/encaps/sign **round-trips**, honest False when libs missing; Kolmogorov complexity via Shannon-entropy lower bound (self-admitted proxy); L4.8 geographic enforcement (≥4 continents, <40% region, <30% jurisdiction). This is why the formula suite's PQC check fails on a bare environment.
- **living_security/genomic_genealogy.py** (455 L): validator key-lineage DAG, contamination DFS propagation (0.5 per hop), divergence matrix, trust_modifier. `verify_key_integrity` has the same weak XOR≠0 check; method confusingly placed *after* the "Self-test" section header (line 375).
- **consensus.py** (396 L): DW-BFT exactly per formula — d_j=1−corr(M_j, M̄) over element-wise median vector, Σ(t) weighted in-window fraction, δ(t)=δ_base(1+V), 2/3 safety, HHI 4 tiers, "self-defeating proof" text generated per run. `build_demo_validators` (seed 42, 2 byzantine) and `simulate_coordination_attack` are demo constructs (byzantine outputs synthesized as `0.5+coord*0.1*j`).
- **sigma_engine.py** (155 L): numpy Σ(t) variant; honest SIGMA_BOOTSTRAP=0.25 disclosure; bootstrap if <10 validators.
- **hhi_monitor.py** (258 L): HHI tiers + F8/F9 falsifiability violations + geographic caps. Correct.
- **epigenetic.py** (264 L): threat-level → EL expression (FROZEN on AWA violation); `apply_epigenetic_adjustment` (×0.70 DISAGGREGATED).
- **signature_aggregation.py** (465 L): **real Bellare-Neven/Schnorr multisig on secp256k1** — s=k+e·x with per-signer Fiat-Shamir challenge H(R‖M‖pk), linear aggregation s_agg=Σs_i, verify s_agg·G=ΣR_i+Σe_i·pk_i; compressed-point codec; tamper and pubkey-order tests. Strongest crypto module in core/.
- **slashing.py** (277 L): L4.9 slash table: coordinated attack 50% permanent, low accuracy 3%/30d, HSM 10%, uptime 0.1%/day, sybil 25% permanent; disputes 72h/5% bond.
- **validator_registry.py** (384 L): SQLite-backed registry, continent validation, launch-threshold disclosure.
- **consensus/engine.py** (194 L): K(t) commit-reveal (SHA3 over k_score+salt), stake-weighted reveal aggregation, temporal consistency decay; 6 anti-capture protections (ACP1–6) documented; K_BOOTSTRAP=0.10.
- **consensus/indigenous_knowledge.py** (462 L): SQLite WAL registry of knowledge systems/consents/elders, revocable consent, elder annotations ×2.5 stake weight; honest "zero seeded entries" disclosure.
- **consensus_degradation.py** (233 L): FULL/REDUCED/DEGRADED/MINIMAL/HALTED tier classification from count+HHI+continents.

### governance/ (14 files)
- **love_protocol.py** (237 L): F = min(6 pillars: public_good≥15%, indigenous knowledge, invisibility, gratitude, elder wisdom, 10% unknown-unknown reserve); F=0 → moat collapse. Trivially correct; the "ethics" is a min() of caller-supplied floats.
- **falsifiability_registry.py** (234 L): F1–F15 canonical registry (WP2 §20), each with metric/threshold/window; AUDIT-3 reconciliation note (spec markdown is legacy).
- **initialization.py** (148 L): INIT_valid gate (≥100 validators, ≥4 continents, D≥10k, ≥3 chains, SEC bootstrapped, Love>0) — before that, only BOOTSTRAP/SILENCE.
- **awa.py** (525 L): AWA state machine (ENFORCED/SUSPENDED/DEGRADED/FROZEN/EMERGENCY), Gratitude Protocol (voluntary vulnerability disclosure credits, 0.95/week decay), bootstrap weight.
- **unknown_unknown.py** (448 L): 10% revenue reserve, 30-day timelock, >75% multisig quorum, epistemic humility score from anomaly rate (baseline 0.10).
- **sba_engine.py** (248 L): SBA = 0.30E+0.25I+0.20S+0.15G+0.10C (sovereign credibility).
- **slashing.py** (525 L): a **second, conflicting slashing system** (S1 double-sign 50%, S2 offline 5%, S3 false signal 20%, S4 collusion 100%, S5 geo 10%; 7-step dispute flow) — different from spiritual/slashing.py's table.
- Others: adaptive_consensus.py (non-binding parameter recommendations), elder_wisdom.py (SQLite, 12-month tenure, 3× weight), intelligence_maintenance.py (IMP retraining ladder — duplicates core/mental/intelligence_maintenance.py with different thresholds), open_research_questions.py (5-question tracker), right_to_invisibility.py (SQLite petition workflow; append-only record preserved).

### realtime/ (3 files)
- **bh_streamer.py** (1154 L): the live data spine. **Real:** JSON-RPC polling of ~60 EVM chains (publicnode & official RPCs), real BH computation (same dual-strand construction), SQLite ledger with UNIQUE tx_hash, indexes, schema migration for the `valid` column, **write-error counting instead of silent drops**, reorg skip (start at tip−3), exponential backoff, Railway memory cap via TRION_MAX_CHAINS with priority ordering. **Weak/synthetic:** SELECTOR_MAP has ~20 selectors (most calldata → TRANSFER); `classify_event` has dead heuristic (`len(selector)>300 → SWAP` — selector is input[:10], never >300) and an unused `value` param; non-EVM fetchers produce placeholder transactions — Solana signatures-only ("from":"unknown"), Cosmos/Aptos/Sui/NEAR/Waves/VeChain fabricated `*_tx_{h}_{i}` rows with value 0, **TON fabricates 10 txs from getMasterchainInfo ignoring the requested seq**, MultiversX fabricates `nonce%50` tx count — so most non-EVM "BHs" hash the entity string "unknown"; FAISSAccumulator's `entropy` field is a **fabricated formula bounded 0.60–0.95 explicitly "to ensure signal selection gate passes"** (lines 449–459); `bh_to_vector` is a handcrafted 128-dim layout (one-hot event, repeated magnitude, sense bytes) — not learned. **Chain-ID conflict:** Solana = 200101 here, 5773521 in mainnet_bootstrap.py, 900 in the Rust indexers. Module bottom monkey-patches `BHStreamer.start` to add non-EVM workers.
- **orchestrator.py** (217 L): process supervisor with backoff restarts + 60s RPC health pings; default processes (bh_streamer, gunicorn flask api) reference real entry points.

### akashic/ (14 files — memory layer)
- **bibl.py** (552 L): 15 mempool archetypes, chain-memory signal with **real historical match counts from the SQLite store** (not hardcoded — as claimed), Bayesian-calibrated confidence (≥10 samples), BRT from observed tx timestamps via **circular statistics** (mean + resultant length, 0.20 strength gate) — genuinely nice; batch-opportunity detector (P95/P50>1.5); MEV exposure heuristics.
- **bibl_pattern_store.py** (493 L): SQLite observations + calibrations tables; starts empty (honest); confidence = Bayesian update from base + sample.
- **genesis.py** (481 L): 6-dimension GenesisFingerprint → 128-dim vector; V₀ similarity-weighted stage values; **variable λ** = similarity-weighted convergence rate; FAISS-service archetype match with local cosine fallback; **`direct_value = 0.50` hardcoded** in the confidence blend (line ~399) — as D grows the genesis value converges toward a constant, not actual behavior.
- **mental_transformer.py** (590 L): a **real PyTorch 2-layer TransformerEncoder** (d_model 32, 4 heads, sinusoidal PE) for genesis inference v2; training data is **synthetic** (64×128 centroids + PCA projection + Gaussian noise, target = row-norm) — disclosed in the DATA NOTE and at runtime via log lines; graceful fallback to harmonic-cosine path.
- **timescale_store.py** (449 L): psycopg2 optional; 1-connection reconnecting pool; hot/warm/cold tiers; degrades to no-op lists when unavailable.
- **archetype.py** (351 L): 12 hand-tuned behavioral archetypes (phi vectors, risk, investment signals, examples incl. "Terra/LUNA (weeks before collapse)", CRISPR repair templates) — hand-authored priors.
- **depth.py** (99 L): trapezoidal D(t)=∫A(1+M)C dτ; bootstrap weight e^(−0.0005D).
- **epigenetics.py** (293 L): per-entity drift/methylation patterns; persistence path fixed per audit C3 (was /tmp).
- **fork_resolution.py** (222 L), **resurrection.py** (293 L), **trajectory_anomaly.py** (212 L): formula-faithful (holder-loyalty inheritance weights; 5 dormancy types with κ; KL-divergence anomaly threshold 0.50 locking genesis confidence).

### mental/ (17 files)
- **anima/engine.py** (569 L): A(t)=PCR·HA·CA with HA disable rule (<0.60 → A=0), stream-completeness degradation, reflexivity dampening (A_adj), probability-distribution output (mean/std/CI_95 always present), bootstrap 0.10 below D=10,000. HATracker = 1−2·MAE over rolling 1000. Well-structured.
- **anima/data_streams.py** (766 L): 4-stream bundle; **54 ISO 639-1 languages** with tiered CRED weights (0.15–1.00) — matches "50+ languages" claim by construction.
- **anima/pattern_library.py** (490 L): PCR pattern categories with per-category θ_PCR (0.65/0.55/0.50/0.45); manifestation-gap tracking.
- **anima/reflexivity.py** (320 L): A_adj = A·(1−0.50·corr(signal, behavioral_change)); manifestation gap monitor.
- **anima/source_credibility.py** (287 L): CRED decay 0.99/day + verification events; per-source-type initial CRED (SEC 0.65 → social 0.15).
- **anima/sec_edgar_fetcher.py** (221 L): real SEC REST fetch with fair-use rate limiting.
- **anima/data_sources/** (7 files): **real public-API fetchers** — arXiv, GBIF (ecological), GitHub events, 6 crypto RSS feeds with lexicon sentiment (not VADER despite docstring), SEC EFTS full-text search (field names fixed per "Phase 3 fix"), TTL caches, graceful degradation.
- **confidence.py** (100 L): M(t)=1−PI_t/PI_baseline via scipy t-prediction-interval.
- **intelligence_maintenance.py** (328 L): IMP ladder (HEALTHY 0.95 → FAILURE 0.40) — duplicated conceptually by governance/intelligence_maintenance.py.

### physical/ (5 files)
- **phi_engine.py** (224 L): 9 entropy features, all real Shannon entropies over binned distributions **except f9**, which synthesizes a 5-category MEV distribution from a single ratio (pseudo-entropy); weights [0.15,0.15,0.10×7].
- **manipulation_detector.py** (398 L): 7 MF patterns with score ranges; oracle-attack immediate MF=1.0.
- **temporal_coherence.py** + **transduction_integrity.py**: TC formula; self-verification with an unusually candid honesty note ("proxies are approximations… scored neutrally (0.5) and flagged, never silently assumed").

### novel/ (5), thermodynamics/ (3), manipulation/ (1), planes/ (1)
- **birp.py** (1009 L): 5-phase identity-recovery state machine with 7-day quarantine, 30-day cooldown, permanent rejection records.
- **behavioral_identity_recovery.py** (939 L): 32-dim fingerprint, Schnorr-Pedersen NIZK enrollment, multi-party witness sharding (K≥N/2+1).
- **chameleon.py**, **coordination_collapse.py** (re-export wrapper of consensus.py).
- **entropy_engine.py** (418 L): H_norm penalty bands (too-low <0.15 / healthy / too-high >0.85).
- **thermo_engine.py**: free energy F=E−T·S, phases GAS/LIQUID/SOLID/PLASMA, Carnot efficiency — physics metaphors mapped onto gas fees and volatility.
- **btcp_mf_detector.py** (547 L): BTCP-specific 7 MF types (T1–T7, weighted-max, T7 holds at 0.5 pending review).
- **planes/seven_plane_coherence.py** (635 L): 7-plane BTCP extension (magnitude z-score, BRT consistency, protocol familiarity, counterparty graph distance, velocity, cross-chain coherence, Kolmogorov delta).

### protocol/, trading/, extended/, price/, auditor/, ubl/, pipeline/, reputation/, investment/, lifecycle/, agent/, api/, native_bridge
- **protocol/**: distribution_coherence (M-substitute via Jensen-Shannon divergence — thoughtful), protocol_health H(t) weights, role_classifier (7 DeFi roles from event-type fingerprints), segmentation ((contract,caller) sub-entities over bh_ledger.db).
- **trading/**: signal_engine, pattern_archetypes (8 hand-coded 9-dim priors), market_data (DeFiLlama/Uniswap/CoinGecko fetchers), live_feed (httpx 30s poller), agent_interface (cosine-agreement weighting).
- **extended/**: biological_capital (BC=Flow·Resilience·Uniqueness·Interdependence), biological_rhythm, **cross_species.py (XSL = ecological: TerritoryViability·FoodSecurity·Reproduction/(1+Threat)) vs xsl_engine.py (XSL = financial: TV·FS·RR/(1+TP)) — two different formulas under the same name**; energy_participation (EP=VC·PA·DC); natural_liquidity (NL=LD·LO·LC·LS; docstring cites a **"March 12, 2026 AAVE pool: NL≈0.09 → BLOCKED"** — a fabricated future-dated event); sovereign_behavioral + sovereign_data_fetcher (real IMF DataMapper / World Bank API fetchers with TTL caches — plus **second SBA definition** differing from governance/sba_engine.py).
- **price/behavioral_price_engine.py** (608 L): explicitly a "LEGACY COMPATIBILITY LAYER", price-aware by design, warns against import from the core pipeline — good separation discipline.
- **auditor/**: contract_auditor (risk scoring vs 25 vulnerability patterns) + vulnerability_patterns (hand-encoded markers/phi vectors).
- **ubl/ubl.py** (225 L): 12-dim Universal Behavioral Language vector.
- **pipeline/signal_publication.py**: coherence → MasterEquation → signal packing → ChainRelay publication — the on-chain bridge module.
- **reputation/**, **investment/**, **lifecycle/**, **agent/safety_pipeline.py** (SILENCE-gated agent action validation), **api/routes.py** (API_SPEC dict documentation), **native_bridge.py** (compiles/invokes Go/Haskell/C++/Julia cross-checks, honest "available: False" when binaries absent).

---

## Key algorithms & formulas found (implemented for real)

| Formula | Module | Status |
|---|---|---|
| C(t)=αΦ+βM+γΣ+δK+εA; Θ=0.55+0.37V | master/coherence.py | exact, tested |
| T(t)=[C≥Θ]·S·e^(M_moat·t) (clamp e^36) | master/master_equation.py | exact |
| M_moat=D·Q·R·X·F·N; N=1−e^(−t/τ), τ=1e8s | master/moat.py | exact, invariants tested |
| BH 93-byte dual-strand: sense=SHA3(p‖0x00), antisense=SHA3(p‖0xFF)⊕NOT(sense) | primitives/behavioral_hash.py | exact, XOR invariant self-verified per hash |
| log10 magnitude normalization | behavioral_hash.py | exact (USD path + fallback) |
| BTCP_score=[.25NL+.20gas+.20fin+.15CC+.20BEO]×(1−MF) | btcp/router.py, master/btcp_score.py | exact (matches Rust per 2-g) |
| d_j=1−corr(M_j,M̄); Σ(t); 2/3 safety; HHI×10⁴ tiers | spiritual/consensus.py, sigma_engine.py | exact |
| Schnorr multisig: s=k+e·x, e=H(R‖M‖pk); s_agg=Σs_i; s_agg·G=ΣR_i+Σe_i·pk_i | spiritual/signature_aggregation.py | real crypto, tamper-tested |
| ML-KEM/ML-DSA/SLH-DSA round-trips (FIPS 203/204/205) | living_security/pqc_layer.py | real when libs installed; honest False otherwise |
| GK(t)=Hash_DNA(GK(t−1)‖BE‖TM‖CV) | living_security/__init__.py | real chaining (in-memory only) |
| BEO = 0.40CF+0.25ST+0.25SC+0.10BP (>0.75) + SimHash BP fallback | primitives/entity_resolution.py | exact + deterministic fallback |
| A(t)=PCR·HA·CA; HA<0.60→0; reflexivity dampening | mental/anima/engine.py | exact |
| CRED(t)=CRED(t−1)·0.99+events·0.10 | source_credibility.py | exact |
| BRT from observed timestamps (circular mean/strength) | akashic/bibl.py | real directional statistics |
| BIBL 15 archetypes + Bayesian calibration (SQLite) | akashic/bibl.py + bibl_pattern_store.py | real, store starts empty |
| D(t)=∫A(1+M)Cdτ (trapezoid); bootstrap e^(−λD) | akashic/depth.py | exact |
| Information conservation + signal selection dI/dS>θ; KL gain | primitives/thermodynamics.py | exact |
| K(t) commit-reveal annotation (SHA3(k+salt)) | spiritual/conscious/engine.py | exact |
| Escrow FSM + cascade revert + 7-day emergency escape | btcp/escrow_monitor.py | exact (in-memory) |
| JSD distribution-coherence M-substitute | protocol/distribution_coherence.py | exact |
| Entropy penalty bands (H_norm) | thermodynamics/entropy_engine.py | exact |
| Transformer genesis inference (2-layer, 4-head) | akashic/mental_transformer.py | real model, synthetic training data (disclosed) |

---

## Code quality assessment

**Strengths**
- Exceptional docstring discipline: every module cites whitepaper section (L-level), author, license; formulas restated in full before implementation; weight sums asserted at import time (e.g. sba_engine `assert abs(ΣW−1)<1e-9`).
- Self-tests everywhere (`if __name__ == "__main__"` with asserts) — ~60 of 149 files are independently runnable check scripts; most pass.
- Real engineering in the data spine: bh_streamer's write-error accounting + schema migration + reorg skip; behavioral_hash's per-hash invariant verification; signature_aggregation's real curve math; pqc_layer's honest dependency gating; SQLite WAL patterns; thread-safe singletons.
- Honesty labeling culture: SIGMA_BOOTSTRAP/K_BOOTSTRAP/ANIMA_BOOTSTRAP disclosures, "CLOCK_FALLBACK" vs "OBSERVED" BRT sources, "similarity_source: local_cosine_fallback", mental_transformer's DATA NOTE.

**Weaknesses**
- **Massive conceptual duplication:** two slashing systems (spiritual vs governance), two IMP modules, two XSL definitions (ecological vs financial), two SBA definitions, two BIBLEngines (btcp vs akashic), two intelligence-maintenance ladders, a "consensus_degradation" in both master/ and spiritual/ — with *conflicting constants* between the pairs.
- In-memory singletons everywhere: routes, escrows, disputes, state channels, genomic keys, balance reservations — none persisted except where explicitly SQLite'd; restarts reset trust state (GenomicKey generations → 0, contradicting the depth-grows-security narrative).
- Import hygiene: sys.path.insert hacks (bh_streamer? no — integration.py, bibl.py fallback, signal_engine), monkey-patching (BHStreamer.start), bare-name anima-service imports, cross-layer absolute imports that break direct execution (coherence.py needs PYTHONPATH).
- Path-rot: channel_architecture impl_paths, trion_primitives file references (mix of core/ and old src/ layouts), `akashic.brt_scheduler` import target missing.
- Theatrical security: CRISPR substring matching; "Kolmogorov bound" as log2-sum; MITO core "integrity" = structural check that always passes.
- Hardcoded economic constants presented as findings ($31 gas 99th-pct, $0.05 netting, 78%/100× savings, maturity tables).

---

## Bugs/issues/inconsistencies found (specific)

1. **core/master/signal_factory.py:73** — `from akashic.brt_scheduler import derive_brt_phase` targets a module that does not exist in `akashic/` (repo-root akashic/ has only 2 real files). Caught by broad `except Exception` → observed-timestamp BRT silently degrades to wall-clock in every signal.
2. **core/master/signal_factory.py:194** — `"provenance": []` — all 24 signal types ship an *empty* provenance chain; module header claims "full provenance chain" as a design guarantee.
3. **core/spiritual/living_security/__init__.py:1339** — self-test non-idempotent; second run fails `Expected 126, got 127` because adaptive CRISPR signatures persist in `akashic/crispr_adaptive.db`. Modules write DBs into the repo working directory as an import/run side effect (crispr_adaptive.db, epigenetic_immunity.db — both observed created, then removed to keep repo clean).
4. **core/spiritual/living_security/__init__.py:594–606** — KNOWN_ATTACKS contains five fabricated 2026-dated attacks (AAVE_2026, MEV_MULTIBLOCK_2026, INTENT_COLLISION_2026, GOVERNANCE_AI_2026, plus 2025 speculative classes) mixed with real historical exploits, section-labeled "Simulated & Projected" but ingested identically by `innate_check`.
5. **core/spiritual/living_security/__init__.py:667–697** — `innate_check` matches mnemonic ASCII signatures (`b"HARVEST_FLASH_LOAN_ORACLE_MANIP"`) by substring against transaction bytes; cannot intercept any real exploit; `matches` counters give the appearance of live defense telemetry.
6. **core/spiritual/living_security/__init__.py:1023–1039** — `ClassicalCryptoScore` hardcodes sha3/aes256/zk_proofs_active = True with zero verification.
7. **core/spiritual/living_security/__init__.py:1125** — `crispr_coverage = min(1.0, library_size/8.0)` — permanently 1.0 for the 126-entry library.
8. **core/primitives/hash_dna.py:557–581** — `verify_dual_strand` does not verify complementarity (length + non-zero-XOR only); docstring concedes full verification needs the original input. Same weakness in **genomic_genealogy.py:375–409** `verify_key_integrity`.
9. **core/btcp/orchestrator.py:177–187, 218–227** — STANDARD privacy level fabricates a "dummy complementarity proof" from random bytes; IAP-share proof uses hardcoded gas/fee/participant numbers not derived from the intent; block_number hardcoded 18,000,000 (line 185).
10. **core/btcp/integration.py:275–316** — Private BIBL "encryption" is repeating-key XOR (self-labeled insecure demo); `decrypt_payload` checks only the *count* of validator shares, never their content; `zero_front_running_window()` returns 0 by construction (assertion, not mechanism).
11. **core/btcp/mainnet_bootstrap.py:98–103, 165–383** — synthetic chain IDs (`sha3(name)%100000`) for ~40 chains; testnets inside PHASE_6_100_CHAINS; many empty rpc/explorer URLs; assertions (≥100 chains, 14 VMs, 4950 pairs) pass on synthetic data.
12. **core/realtime/bh_streamer.py:120–129** — `classify_event` dead branch (`len(selector)>300` unreachable; selector is `input[:10]`) and unused `value` parameter; SELECTOR_MAP covers ~20 selectors so event typing is coarse.
13. **core/realtime/bh_streamer.py:449–459** — FAISSAccumulator `entropy` explicitly engineered into [0.60, 0.95] "to ensure signal selection gate passes" — fabricated telemetry feeding the thermodynamics signal-selection gate.
14. **core/realtime/bh_streamer.py:732–740, 790–798, 671–841 passim** — TON fetcher fabricates 10 transactions from getMasterchainInfo (ignores requested seq); MultiversX fabricates `nonce%50` txs; Solana/Cosmos/Aptos/Sui/NEAR/Stellar/Waves/VeChain produce from/to="unknown", value=0 rows → BHs computed over the literal entity "unknown".
15. **Chain-ID conflict (3 registries):** Solana = **200101** (bh_streamer.py:591), **5773521** (mainnet_bootstrap.py:167), **900** (Rust indexers per agent 2-c). Also Polkadot 201501/25000, Aptos 200301/20100/5001 across files.
16. **core/master/channel_architecture.py:70–99, 167, 211, 307–339** — impl_paths point to nonexistent files (src/signals/signal_factory.py, src/planes/extended/*, src/security/*, cpp/sensor_interface.cpp, wasm/signal_processor.wat, go/validator_mesh.go, math/formal_verification.hs); "ACTIVE" status claimed for channels whose listed implementations don't exist at those paths.
17. **core/akashic/genesis.py:399** — `direct_value = 0.50` hardcoded; the confidence blend converges to a constant rather than to measured behavior.
18. **core/master/homomorphic_mapping.py:106–151, 355–364** — finality deltas, λ_A, integration ages, and default μ/σ baselines all hardcoded assumptions; `verify_homomorphic_property` checks only ordering preservation + vector distinctness (not the homomorphic property proper).
19. **Conflicting duplicate modules:** spiritual/slashing.py (50/3/10/0.1%/25%) vs governance/slashing.py (50/5/20/100/10% + 7-step flow); mental vs governance intelligence_maintenance (different threshold ladders); extended/cross_species.py XSL ≠ extended/xsl_engine.py XSL; governance/sba_engine.py SBA ≠ extended/sovereign_behavioral.py SBA; btcp/bibl_engine.BIBLEngine ≠ akashic/bibl.BIBLEngine.
20. **core/extended/natural_liquidity.py (docstring)** — cites "March 12, 2026 AAVE pool: NL ≈ 0.09 → BLOCKED" as motivating evidence; a **future-dated fabricated event**, cross-referenced by the fabricated CRISPR entry AAVE_2026_LIQUIDITY — synthetic evidence laundering between modules.
21. **Empirical: formula-verification suite fails on bare env** — running `tests/master_formula_verification.py` yields **104 passed, 1 failed** ("L4.7 PQC all-active L3 = 0.90") because kyber-py/dilithium-py/pyspx aren't installed; PQC honestly reports 0. The "105/105 ✅ ALL PASS" claim in docs/FORMULA_REFERENCE.md and MAINNET_RUNBOOK is dependency-conditional, not unconditional.
22. **Escrow/dispute/route state is memory-only** (btcp/escrow_monitor.py, dispute_resolution.py, orchestrator._routes, router._balance_reservations) — no persistence layer despite the "semi-immutable" narrative; GenomicKeys likewise reset on restart (living_security GenomicKeyEvolver has no persistence).
23. **core/master/degradation.py:56–62** — `fund_safety_guarantee` property returns literal True; disclosure strings assert "GUARANTEE: entity funds are safe" as a constant.
24. **core/physical/phi_engine.py:157–172** — f9 "MEV entropy" synthesizes a 5-category distribution from one ratio (0.3/0.2/0.2/0.1/(1−r)) — entropy of fabricated categories.
25. Minor: coherence.py and several self-tests require `PYTHONPATH=.` (absolute `core.` imports break direct execution); genomic_genealogy.verify_key_integrity placed after the "Self-test" header; signal_factory's `compute_brt` uses module-level `import hashlib` mid-file (style).

---

## Claims vs reality assessment

| Claim (source) | Reality in core/ |
|---|---|
| "105/105 formulas verified ALL PASS" (docs, runbook) | `tests/master_formula_verification.py` has 108 check() calls; **re-run: 104 pass / 1 fail** (PQC L4.7 — needs kyber-py/dilithium-py/pyspx). Claim true only with optional PQC deps installed. |
| "24 signal types" | TRUE — enum 0–23, all builders present, self-test passes. But `provenance` is always `[]`. |
| "20-Channel Architecture, 17 ACTIVE" | Self-asserted registry; impl_paths stale/broken for many channels; some "ACTIVE" channels map to files that don't exist at the listed paths (real implementations live elsewhere). |
| "7/7 primitives IMPLEMENTED, 100% completion" (trion_primitives.py) | Self-declared status list; the underlying modules exist and largely work, but "100%" hides placeholder internals (CRISPR substring matching, XOR privacy demo). |
| "CRISPR Defense: exact attack signatures, intercept before execution" | Mnemonic string substring matching; **zero real interception capability**; includes 5 fabricated 2026 attacks. |
| "Living Security: stolen key outdated at N+1" | True *within* an in-memory singleton; keys not persisted, so restart resets generations — the property evaporates across restarts. |
| "BIBL: real historical match counts (was hardcoded 100)" | TRUE — SQLite pattern store, starts empty, Bayesian calibration ≥10 samples. Genuinely fixed. |
| "100+ chains bootstrap (106 chains, 14 VMs)" | Registry padded with hash-derived synthetic chain IDs, testnets, empty URLs; only Ethereum has an oracle address. |
| "37 non-EVM chains live-indexed" (streamer) | Fetchers exist, but most produce placeholder transactions (entity "unknown", value 0); TON/MultiversX fabricate tx rows. Real EVM ingestion is solid; non-EVM is largely nominal. |
| "Genomic Key / Hash_DNA tamper-evident" | TRUE at hash level (XOR invariant verified per hash); the *verifier* functions (`verify_dual_strand`, `verify_key_integrity`) are weaker than the construction. |
| "PQC: real FIPS 203/204/205, no simulation" | TRUE when libs present; honestly False otherwise (and the formula suite's only failure proves the honesty works both ways). |
| "mental transformer (genuine PyTorch)" | TRUE architecture; trained on synthetic centroid sequences — disclosed in code. |
| "Σ=0.25 / K=0.10 / A=0.10 bootstrap" | Honest disclosures — meaning at current depth the engine's spiritual/conscious/anima planes are constants, and C(t) can never clear Θ for most profiles. |
| "March 12, 2026 AAVE collapse (NL≈0.09)" | Fabricated future-dated event cited as evidence in natural_liquidity.py and CRISPR library. |
| "Love Protocol kill-switch" | Real min() gate in code, but inputs are caller-supplied floats — the ethics enforcement is only as honest as its caller. |
| "price-agnostic core" | TRUE — price engine is quarantined as an explicitly-labeled legacy shim with import warnings. |

**Bottom line:** core/ is a large, unusually well-documented formula engine whose *mathematical skeleton* is real and largely matches its whitepaper (coherence, moat, DW-BFT, BH dual-strand, BTCP score, escrow FSM, Schnorr aggregation, PQC gating), but whose *operational claims* (immune defense, 106 chains, live non-EVM indexing, provenance chains, unconditional formula verification) are supported by synthetic or self-asserted evidence. The honesty labeling present in the code (bootstrap disclosures, fallback sources) is the most credible part of the project; the marketing-layer numbers (105/105, 20/17 channels, 7/7 primitives) are not reproducible without optional dependencies and generous interpretation.
