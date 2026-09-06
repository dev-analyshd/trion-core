# Master Requirements Matrix — TRION / BTCP (296 requirements, 15 domains)

**Task ID:** 9-a/9-c (Master Command §2/§29) · **Matrix built:** 2026-09-05 (Task 5) from 620 source requirements (D1-001..150, D2-001..174, D3-001..296; every source ID in exactly one row, validated programmatically)
**This file:** repo-side consolidation at docs/audit/master-audit/ — row set identical to upload/extracted/requirements_master.md; statuses re-annotated where the fix waves (Tasks 7-a…7-f, 8-a…8-c) changed the evidence. Fix-wave changes live in the working tree (uncommitted at write time; coordinator commit pending).
**Columns:** ID · Requirement (short) · Sources · Type · Pri (max of source priorities) · Contra (⚠ = docs disagree — see Contradiction section) · Status · Evidence (repo paths @ c0ccb14 + fix-wave notes)

**Status legend:** IMPLEMENTED · PARTIALLY IMPLEMENTED · MISSING · CONTRADICTORY · DEAD/FALSE CLAIM · UNKNOWN. "IMPLEMENTED" = code exists and matches spec per the 9-agent deep read — live production operation is NOT implied (no validator fleet, single-sig relayer, testnet deployments self-reported). Rust/Go/Cairo verified statically (no cargo/go/forge/scarb in sandbox).

✏️ = changed / hardened / corrected during this audit session (annotation names the wave and the regression test).

---

## DASHBOARD

### Status distribution (matrix build → after this session's fixes)

| Status | At build (Task 5) | After fix waves | Δ |
|---|---:|---:|---|
| IMPLEMENTED | 211 | 212 | +1 (M-004 SILENCE payload fields landed, 8-c) |
| PARTIALLY IMPLEMENTED | 71 | 70 | −1 |
| MISSING | 3 | 3 | — (M-184 validator fleet, M-266 Coq/Lean/TLA+, M-288 mainnet) |
| CONTRADICTORY | 3 | 3 | — (doc-level: M-073, M-168, M-296) |
| BROKEN | 0 | 0 | — |
| DEAD/FALSE CLAIM | 1 | 1 | — (M-203 Aave "real validation") |
| UNKNOWN | 7 | 7 | — |
| **TOTAL** | **296** | **296** | 1 status flip, 13 ✏️ annotations |

### Priority distribution

| Priority | Count |
|---|---:|
| CRITICAL | 84 |
| HIGH | 147 |
| MEDIUM | 60 |
| LOW | 5 |

### Requirements per domain

| Domain | Rows |
|---|---:|
| 1. Formulas & Math (72) | 72 |
| 2. Signal System (35) | 35 |
| 3. Five-Plane Architecture (10) | 10 |
| 4. BTCP Protocol (50) | 50 |
| 5. Contracts (15) | 15 |
| 6. Consensus/Validators (6) | 6 |
| 7. Security/Crypto/PQC (18) | 18 |
| 8. ZK (5) | 5 |
| 9. Indexers/Data (10) | 10 |
| 10. APIs/Services (6) | 6 |
| 11. Frontends/SDK (5) | 5 |
| 12. Deployment/Infra (9) | 9 |
| 13. Testing/Verification (26) | 26 |
| 14. Governance/Team/Roadmap (21) | 21 |
| 15. Documentation Claims (8) | 8 |
| **TOTAL (programmatic count)** | **296** |

### Status × domain (post-session)

| Domain | IMPL | PARTIAL | MISS | CONTRA | DEAD | UNK |
|---:|---:|---:|---:|---:|---:||
| 1. Formulas & Math (72) | 69 | 3 | 0 | 0 | 0 | 0 |
| 2. Signal System (35) | 29 | 5 | 0 | 1 | 0 | 0 |
| 3. Five-Plane Architecture (10) | 7 | 3 | 0 | 0 | 0 | 0 |
| 4. BTCP Protocol (50) | 42 | 8 | 0 | 0 | 0 | 0 |
| 5. Contracts (15) | 11 | 3 | 0 | 1 | 0 | 0 |
| 6. Consensus/Validators (6) | 3 | 1 | 1 | 0 | 0 | 1 |
| 7. Security/Crypto/PQC (18) | 16 | 1 | 0 | 0 | 1 | 0 |
| 8. ZK (5) | 0 | 5 | 0 | 0 | 0 | 0 |
| 9. Indexers/Data (10) | 8 | 2 | 0 | 0 | 0 | 0 |
| 10. APIs/Services (6) | 5 | 1 | 0 | 0 | 0 | 0 |
| 11. Frontends/SDK (5) | 5 | 0 | 0 | 0 | 0 | 0 |
| 12. Deployment/Infra (9) | 4 | 5 | 0 | 0 | 0 | 0 |
| 13. Testing/Verification (26) | 2 | 23 | 1 | 0 | 0 | 0 |
| 14. Governance/Team/Roadmap (21) | 9 | 9 | 1 | 0 | 0 | 2 |
| 15. Documentation Claims (8) | 2 | 1 | 0 | 1 | 0 | 4 |

---

## CONTRADICTORY items (19 — docs disagree on the requirement itself)

None were resolved this session: contradictions are doc-vs-doc conflicts; the fix waves only hardened the repo side. Full notes: upload/extracted/requirements_master.md §Contradiction Register; repo-internal conflicts K1–K22: docs/audit/CANONICAL_SPEC_MATRIX.md.

| ID | Pri | Requirement | Sources |
|---|---|---|---|
| M-002 | CRITICAL | Five-plane coherence C(t)=α·Φ_adj+β·M_adj+γ·Σ+δ·K+ε·A with Φ_adj=Φ·(1−MF), M_adj=M·(1−OE). | D1-005, D1-057, D2-005, D2-039, D3-261 |
| M-006 | CRITICAL | Behavioral Hash BH(event,t)=Hash_DNA(preimage) — canonical cross-VM preimage layout. | D1-009, D2-009, D3-266, D3-009 |
| M-008 | CRITICAL | BEO entity resolution: BEO_confidence=(w_CF·CF+w_ST·ST+w_SC·SC+w_BP·BP)/Σw; multi-wallet→one entity before hashing. | D1-012, D2-010, D3-269, D3-191 |
| M-021 | HIGH | MF 7 FAKE_VOLUME_PATTERN: entropy<threshold AND volume>10× baseline; score 0.80×(1−entropy). | D1-026, D1-072 |
| M-053 | MEDIUM | Sovereign Behavioral Assessment SBA=w_E·E+w_I·I+w_S·S+w_G·G+w_C·C (I=corr(stated policy, onchain enforcement)). | D1-066, D2-045 |
| M-054 | CRITICAL | BTCP_score (route optimization): [0.25·NL+0.20·normalize_gas+0.20·finality_conf+0.15·CC_coherence+0.20·BEO_continuity]×(… | D1-018, D1-109, D3-091, D3-263 |
| M-059 | MEDIUM | BITP/BLO commitment hashes: Hash_DNA(entity\|\|intent\|\|expiry\|\|behavioral_proof\|\|timestamp[\|\|nonce]). | D3-273, D3-274 |
| M-072 | CRITICAL | Canonical constants registry: every weight/threshold/κ/fee across all 3 docs indexed and implemented; D1 Appendix B =… | D1-150, D3-296 |
| M-073 | CRITICAL | Signal taxonomy closed at exactly 19 types. | D1-069, D2-077 |
| M-110 | CRITICAL | Σ/K/A planes must not be undisclosed fixed-value stubs in C(t) — real engines or disclosed bootstrap. | D3-076, D3-213 |
| M-168 | CRITICAL | Smart contracts for EXACTLY two things: (1) publishing signals to chains (Solidity), (2) economic coordination… | D1-084 |
| M-172 | CRITICAL | BTCP_ESCROW.vy (Vyper 0.3.10): 4 state constants IDLE/HOLDING/RELEASED/REVERTED, EscrowRecord struct, storage… | D3-217, D3-237, D3-238, D3-239, D3-241, D3-242, D3-023 |
| M-181 | CRITICAL | Akashic/DW-BFT consensus: TRION-BFT (Tendermint family), instant finality, diversity-weighted; Σ(t) indicator window… | D1-034, D2-099 |
| M-195 | CRITICAL | AWA (Anti-Weaponization Architecture): 6-condition conjunction, auto-freeze of ALL signal emission on violation. | D1-101, D2-154 |
| M-203 | HIGH | March 12, 2026 'Aave incident' presented as REAL validation ($50M USDT→AAVE, NL≈0.09, CI_95 [0.06,0.14], DO_NOT_ROUTE). | D1-143 |
| M-233 | CRITICAL | Exact language stack: Rust core/crypto; Go networking/crawler-coordination/API gateway; Python AI/ML training; TS… | D1-130, D2-113, D2-114, D2-115, D2-123 |
| M-277 | CRITICAL | Build discipline: do not skip levels; each level is the foundation of the next; test every level before proceeding. | D2-100, D2-112 |
| M-293 | MEDIUM | Scope claims: directly solves oracle manipulation + market manipulation + wash trading (+ '7 direct solves' vs 10… | D1-146, D1-147, D1-148, D1-145, D1-103 |
| M-296 | MEDIUM | Doc3 Appendix-A vs §2 internal discrepancy register + repo identity drift. | D3-294 |

---

## Top-20 implementation backlog (CRITICAL / HIGH, not IMPLEMENTED)

Ordered by status severity (MISSING / CONTRADICTORY / UNKNOWN first), then structural weight. M-004 left the backlog this session (8-c).

| # | ID | Pri | Requirement (short) | Status | Blocker |
|---|---|---|---|---|---|
| 1 | M-184 | CRITICAL | Validator set: minimum 100 validators across ≥4 continents at launch. | MISSING | No live fleet — emission via single-sig relayer; software launch gate exists, fleet does not |
| 2 | M-073 | CRITICAL | Signal taxonomy closed at exactly 19 types. | CONTRADICTORY | Repo emits 24 signal types, docs close at 19 (D3 adds 10 more); no canonical registry to arbitrate |
| 3 | M-168 | CRITICAL | Smart contracts for EXACTLY two things: (1) publishing signals to chains (Solidity), (2)… | CONTRADICTORY | Spec says contracts for exactly 2 things; repo has 9 VM languages, ~33.7k lines of contracts |
| 4 | M-110 | CRITICAL | Σ/K/A planes must not be undisclosed fixed-value stubs in C(t) — real engines or disclosed… | PARTIALLY IMPLEMENTED | Σ/K/A bootstrap fixed values still feed some paths (Σ=0.25, K=0.10, A=0.10) — engines real, disclosure partial |
| 5 | M-072 | CRITICAL | Canonical constants registry: every weight/threshold/κ/fee across all 3 docs indexed and… | PARTIALLY IMPLEMENTED | Constants scattered across core modules; no single canonical constants file (10 D1 + 9 D3 symbols unvalued) |
| 6 | M-183 | CRITICAL | Validator hardware: 32+ cores EPYC/Xeon, 256GB DDR5 ECC, 10TB NVMe, A100/H100, 10Gbps fiber… | UNKNOWN | Hardware spec (EPYC/256GB/HSM) has no repo enforcement and cannot be verified from code |
| 7 | M-163 | CRITICAL | Sensing Oracle / Dark Field Protocol: entity computes privately on-device, submits… | PARTIALLY IMPLEMENTED | Sensing-Oracle contract exists; the ZK coherence proof circuit is not built |
| 8 | M-166 | CRITICAL | Semi-immutability: bytecode immutable AND expression=f(bytecode, environment_signal) changes… | PARTIALLY IMPLEMENTED | Semi-immutability engines + API exist; no deployed semi-immutable contract demonstrated |
| 9 | M-215 | CRITICAL | Akashic Index on TimescaleDB (billions of events, microsecond queries); BH schema + BTCP_ROUTE… | PARTIALLY IMPLEMENTED | TimescaleDB 17/35 tables declaration-only; psycopg2 guarded — schema in-tree, depth absent |
| 10 | M-242 | CRITICAL | Proof 1 — Manipulation resistance: no rational actor profitably manipulates TRION for assets… | PARTIALLY IMPLEMENTED | Proof 1 manipulation-resistance: monitors + attack-cost model exist; theorem is prose |
| 11 | M-243 | CRITICAL | Proof 2 — Consensus safety: DW-BFT safe and live under conditions stronger than standard BFT. | PARTIALLY IMPLEMENTED | Proof 2 consensus safety: 50-sybil measured 75.8%→0%; bridge-vs-multisig comparison is prose |
| 12 | M-244 | CRITICAL | Proof 3 — Quantum resistance: LSS resistant to arbitrarily powerful quantum computers… | PARTIALLY IMPLEMENTED | Proof 3 quantum resistance: PQC round-trips real; the proof itself is prose (AN-10) |
| 13 | M-245 | CRITICAL | Proof 4 — Signal convergence: diversity-weighted consensus is a consistent estimator… | PARTIALLY IMPLEMENTED | Proof 4 convergence: monitors exist; consistent-estimator proof is prose |
| 14 | M-247 | CRITICAL | F1/F2 falsification (manipulation resistance + consensus safety): documented successful… | PARTIALLY IMPLEMENTED | F1/F2 falsification wired to modules + replay engine; continuous live monitoring not running (no fleet) |
| 15 | M-180 | CRITICAL | Vyper for security-critical contracts (staking/slashing/token); simpler syntax = smaller… | PARTIALLY IMPLEMENTED | Vyper for staking/slashing/token: token+escrow yes; staking is an ink! stub, slashing is Python/Go/Solidity |
| 16 | M-280 | CRITICAL | Roadmap L2 — Akashic Index: EVM-genesis bootstrap, archetype clustering (K-means 128-dim)… | PARTIALLY IMPLEMENTED | L2 bootstrap in progress (D(t)=18.3%); archetype evolution partial |
| 17 | M-284 | CRITICAL | Roadmap L6 — D1: BC/BRT/BIBL gas intelligence; D2: FIRST TESTNET SIGNAL (three-plane C(t), Θ… | PARTIALLY IMPLEMENTED | L6 first testnet signal live but via 3→5-plane bootstrap stubs |
| 18 | M-277 | CRITICAL | Build discipline: do not skip levels; each level is the foundation of the next; test every… | PARTIALLY IMPLEMENTED | Level discipline: repo followed L0→L9 order, but first signal predates full per-level testing |
| 19 | M-233 | CRITICAL | Exact language stack: Rust core/crypto; Go networking/crawler-coordination/API gateway; Python… | PARTIALLY IMPLEMENTED | All 10 languages present; Rust/Go statically verified only (no cargo/go in sandbox) |
| 20 | M-252 | CRITICAL | F8/F9 (D1): HHI>2500 sustained 30 days without correction; geographic distribution <4… | PARTIALLY IMPLEMENTED | F8/F9: HHI monitor + violation chips exist; auto-correction not live |

Runner-ups: M-248/M-249 (F3–F5 live windows need fleet+uptime), M-259 (F13 clean-history FP study), M-270/M-272 (governance vote/timelock mechanics), M-274/M-275 (team/finance-level, no code evidence), M-266 (Coq/Lean/TLA+ artifacts), M-288 (mainnet).

---

## MATRIX BY DOMAIN

### 1. Formulas & Math (72)

| ID | Requirement | Sources | Type | Pri | Contra | Status | Evidence |
|---|---|---|---|---|---|---|---|
| M-001 | Master Equation T(t)=[C(t)>=Θ(t)]·S(t)·e^(M_moat·t): binary emission gate (1→signal, 0→SILENCE), no partial emission. | D1-004, D1-007, D2-003, D2-040, D3-260 | formula | CRITICAL | no | IMPLEMENTED | core/master/ (MasterEquation, exponent clamp 36.0); rust/src/master_equation.rs (13 tests… |
| M-002 | Five-plane coherence C(t)=α·Φ_adj+β·M_adj+γ·Σ+δ·K+ε·A with Φ_adj=Φ·(1−MF), M_adj=M·(1−OE). | D1-005, D1-057, D2-005, D2-039, D3-261 | formula | CRITICAL | ⚠ YES | IMPLEMENTED | core/master/coherence.py (11 profiles, default 0.25/0.30/0.25/0.10/0.10); sdk/src/wasm… |
| M-003 | Dynamic threshold Θ(t)=Θ_min+(Θ_max−Θ_min)·V(t), Θ_min=0.55, Θ_max=0.92 (0.55+0.37·V). | D1-006, D2-038, D3-262 | constant | CRITICAL | no | IMPLEMENTED | rust/src/master_equation.rs (Θ=0.55+0.37·clamp(V)); core/master/; escrow coherence floors 0.55… |
| M-004 | Structured SILENCE payload: coherence_gap, limiting_plane, coherence_trend, estimated time-to-threshold; 'silence is information'. | D1-001, D1-071, D3-074 | schema | CRITICAL | no | IMPLEMENTED | core/master/signal factory + rust/src/signal_emitter.rs (SILENCE payload=Θ−C gap); api… ✏️ FIXED THIS AUDIT (8-c): limiting_plane/eta_blocks now derived at emission — engine passthrough, else argmin(w·plane) + int(gap×1000) (shared w/ TRIONOracleV3 SilenceRecordedV2); regressions tests/unit/test_all_planes.py::test_silence_payload_structured |
| M-005 | Moat M_moat(t)=D·Q·R·X·F·N — six multiplicative independently-growing factors. | D2-006, D2-049 | formula | HIGH | no | IMPLEMENTED | core/master/moat (MoatEngine D·Q·R·X·F·N; repo-specific sub-formulas D=log1p(d/1000)/log(11)… |
| M-006 | Behavioral Hash BH(event,t)=Hash_DNA(preimage) — canonical cross-VM preimage layout. | D1-009, D2-009, D3-266, D3-009 | formula | CRITICAL | ⚠ YES | IMPLEMENTED | core/primitives/behavioral_hash.py; indexers/crates/trion-common/src/hash_dna.rs… ✏️ HARDENED THIS AUDIT (7-d/8-b): indexer BH block_hash bytes [61..93] now carry real chain hashes (ton/pi/xrpl/mx/hedera), synthetic ids deleted per CANONICAL_BH §9 — the doc-level preimage contradiction itself is unchanged |
| M-007 | Dual-strand hashing: sense=SHA3-256(P\|\|0x00); antisense=SHA3-256(P\|\|0xFF) XOR complement(sense); verify sense⊕antisense==expected. | D1-010, D2-080, D3-267 | security | CRITICAL | no | IMPLEMENTED | Py/Rust/TS parity + Go meshsha3 (FIPS202 SHA3-256, XOR-NOT invariant tests); used in every BH… |
| M-008 | BEO entity resolution: BEO_confidence=(w_CF·CF+w_ST·ST+w_SC·SC+w_BP·BP)/Σw; multi-wallet→one entity before hashing. | D1-012, D2-010, D3-269, D3-191 | formula | CRITICAL | ⚠ YES | IMPLEMENTED | core/primitives/entity_resolution (BEO, resolve_batch/deployer APIs; cross-VM BEO golden vector… |
| M-009 | Resonance communication: Comm(A,B) iff ∃f: RF(A,f)>0 ∧ RF(B,f)>0 (shared behavioral vocabulary). | D1-013, D2-011 | protocol | HIGH | no | IMPLEMENTED | core/primitives/resonance; api /beo/resonance/{a}/{b} |
| M-010 | Thermodynamic information conservation: I_total(t)=I_total(t−1)+ΔI_consumed−ΔI_transformed, ΔI_transformed>=0; I_TRION ledger with… | D1-014, D1-068, D2-012, D2-047 | invariant | HIGH | no | IMPLEMENTED | core/primitives/thermodynamics; api /information/conservation, /conservation/status; conservation… |
| M-011 | Signal Selection Principle: select iff dI_gained/dS_entropy_cost>θ_selection. | D1-015, D2-013 | formula | MEDIUM | no | IMPLEMENTED | anima-service/faiss_service.py /index/add_batch (L0.5 gate mag_eff×entropy/0.1>θ=0.5); AWA… |
| M-012 | Evolutionary fitness F(c,t)=PA·ICE·AS·Love; Love=0 → component kill-switch. | D1-016, D2-014 | formula | HIGH | no | IMPLEMENTED | core/primitives/evolutionary_fitness (Love=0 kill-switch); api /fitness |
| M-013 | Physical Richness Φ(t)=(1/N)·Σ w·H(f(t)) — Shannon entropy over behavioral features, weights learned from Akashic history. | D2-015 | formula | CRITICAL | no | IMPLEMENTED | core/physical/phi_engine (9 entropy features f1–f9, weights 0.15/0.15/7×0.10; /phi/weights +… |
| M-014 | Manipulation aggregate: MF_score(t)=min(1, max(all active fingerprint contributions)); MF over threshold → Φ_adj collapses → SILENCE. | D1-019, D2-016 | formula | CRITICAL | no | IMPLEMENTED | core/physical/manipulation_detector + core/manipulation/ (T1–T7 weighted max, T7→0.5 hold); real… |
| M-015 | MF 1 WASH_TRADING: cyclic_flow_ratio>60% AND counterparty_count<5; score 0.70×cyclic_flow_ratio. | D1-020 | security | HIGH | no | IMPLEMENTED | core/physical/manipulation_detector (7 patterns); scripts/simulate_attacks.py replay |
| M-016 | MF 2 COORDINATED_PUMP: synchronized buy timing across BEO cluster with 3+ entities; score 0.85×sync_buy_ratio. | D1-021 | security | HIGH | no | IMPLEMENTED | core/physical/manipulation_detector; replay_engine.py sync-burst scripts |
| M-017 | MF 3 ORACLE_ATTACK: spot deviation >15% within 10 blocks of large swap; score 1.00 automatic. | D1-022 | security | HIGH | no | IMPLEMENTED | core/physical/manipulation_detector; core/price/btcp_price_oracle (7-check manipulation detection) |
| M-018 | MF 4 SYBIL_LIQUIDITY: top-5 LPs>80% of pool funded from <3 sources; score 0.60×concentration. | D1-023 | security | HIGH | no | IMPLEMENTED | core/physical/manipulation_detector; LO=1−Sybil_LP_ratio in NL |
| M-019 | MF 5 GOVERNANCE_CAPTURE: vote HHI>4000 AND proposal age<48h; score 0.50×scaled_HHI. | D1-024 | security | HIGH | no | IMPLEMENTED | core/physical/manipulation_detector; governance MF endpoints |
| M-020 | MF 6 MEV_EXTRACTION: mev_rate>0.5% sustained >7 days; score 0.40×scaled_rate. | D1-025 | security | HIGH | no | IMPLEMENTED | core/physical/manipulation_detector; api /mev/{id} |
| M-021 | MF 7 FAKE_VOLUME_PATTERN: entropy<threshold AND volume>10× baseline; score 0.80×(1−entropy). | D1-026, D1-072 | security | HIGH | ⚠ YES | IMPLEMENTED | core/physical/manipulation_detector T7; core/thermodynamics entropy band 0.15–0.85 |
| M-022 | Wash-trading depth defense: D_effective=D×(1−HHI(counterparty_distribution)). | D1-027 | formula | MEDIUM | no | IMPLEMENTED | core/akashic/depth (HHI wash discount on D(t)) |
| M-023 | Flash-loan defense: NL_smooth=median(NL(t−2),NL(t−1),NL(t)); FLASH_LOAN_DISCOUNT=0.15 in-block. | D1-028 | formula | MEDIUM | no | PARTIALLY IMPLEMENTED | NL smoothing via LC (90d baseline correlation) in core/extended/NL; explicit 0.15 flash-loan… |
| M-024 | Temporal coherence TC(t)=1−max_i(\|t_plane_i−t_ref\|)/TTL_min; stale plane collapses coherence→SILENCE. | D1-029, D2-017 | formula | HIGH | no | IMPLEMENTED | core/physical/temporal_coherence (TTL 300s); temporal_coherence field on every TRIONSignal |
| M-025 | Transduction integrity TI=Calibration·Drift_correction·Cross_verification for validator sensors; HSM-anchored. | D1-030, D2-018 | formula | HIGH | no | PARTIALLY IMPLEMENTED | core/physical/transduction_integrity implements software self-verification (SQLite GK hash-chain of… |
| M-026 | Akashic depth D(t)=∫₀ᵗ[A(τ)(1+M(τ))C(τ)]dτ; D(0)=full EVM-genesis bootstrap; D_minimum≈6 months live. | D1-032, D2-019 | formula | CRITICAL | no | IMPLEMENTED | core/akashic/depth (integral + canonical vs decayed variants); api /api/v1/depth; MAINNET_RUNBOOK… |
| M-027 | Genesis archetype similarity sim(G,A_k)=G·A_k/(‖G‖‖A_k‖) over 128-dim G. | D1-035, D2-020 | formula | HIGH | no | IMPLEMENTED | core/akashic/archetype (12 archetypes, K-means, FAISS L2→IVFPQ); api /similarity (cosine mental_m… |
| M-028 | Genesis pipeline steps 1–2: G vector from 7 components; V_genesis=Σ_k sim·V_k/Σ_k sim (similarity-weighted archetype valuation). | D2-087, D2-088 | formula | HIGH | no | IMPLEMENTED | core/akashic/genesis (6-dim fingerprint, V₀, variable λ; FAISS match); api /genesis… |
| M-029 | Genesis confidence blend + protection: conf_genesis=1−e^(−λ·D_asset); S_total=conf·S_direct+(1−conf)·S_archetype; TRAJ_ANOMALY>θ →… | D2-021, D2-089, D2-090 | formula | HIGH | no | IMPLEMENTED | anima-service _compute_signal (conf_genesis=1−e^(−0.001·D)); core/akashic/trajectory_anomaly… |
| M-030 | Resurrection formula Δ_resurrection with dormancy decay κ and behavioral similarity. | D2-022 | formula | HIGH | no | IMPLEMENTED | core/akashic/resurrection (κ taxonomy, weighted geometric mean); api /resurrection |
| M-031 | Dormancy taxonomy: 5 types (ABANDONED κ=0.008 etc.) with classification semantics and day windows. | D2-091 | formula | HIGH | no | IMPLEMENTED | core/akashic/resurrection (κ taxonomy); api /dormancy/{id} |
| M-032 | Convergence theorem: lim_{D→∞} E[\|T−V_true\|]=H_irreducible (quantum uncertainty floor). | D1-008, D2-023, D3-287 | invariant | HIGH | no | IMPLEMENTED | api /convergence/{id} monitors; theorem is prose-level (Haskell Theorems); ties to D3-188 security… |
| M-033 | Fork resolution: canonical chain = ≥67% original validators + highest TVL + highest dev activity; CC_A/CC_B holder continuity. | D1-037, D2-024 | protocol | HIGH | no | IMPLEMENTED | core/akashic/fork_resolution; api /fork_resolution (POST) |
| M-034 | Trajectory anomaly: TRAJ_ANOMALY=KL_divergence(P_actual, P_expected\|archetype,age); >2σ → TRAJECTORY signal. | D1-038, D2-025 | formula | HIGH | no | IMPLEMENTED | core/akashic/trajectory_anomaly (KL); api /trajectory_anomaly |
| M-035 | Mental confidence M(t)=1−PI_t/PI_baseline (prediction-interval width); confidence≠accuracy. | D2-026 | formula | HIGH | no | IMPLEMENTED | core/mental/confidence (PI-based); akashic/mental_transformer conformal intervals (2-layer PyTorch… |
| M-036 | Observer effect: OE_factor=corr(publication(t−1), behavioral_change(t)); M_adj=M·(1−OE). | D1-041, D2-027, D3-283 | formula | HIGH | no | IMPLEMENTED | core/mental/reflexivity; api /observer_effect (+/record_publication) |
| M-037 | ANIMA score A(t)=PCR·HA·CA. | D1-039, D2-028 | formula | CRITICAL | no | IMPLEMENTED | core/mental/anima/engine (PCR·HA·CA; 30 patterns θ_PCR 0.55–0.65); 0G path hardcodes ha=0.78… |
| M-038 | ANIMA reflexivity: ANIMA_reflexivity=corr(ANIMA strength, attributed behavioral change); A_adj=A·(1−β·reflexivity). | D2-030 | formula | HIGH | no | IMPLEMENTED | core/mental/anima/reflexivity (β=0.5 dampening); api /anima_reflexivity |
| M-039 | Source credibility: CRED(s,t)=CRED(s,t−1)·α_decay+verification_events·β_update; α_decay=0.99/day; deltas +1/−2/−3. | D1-042, D2-029 | formula | CRITICAL | no | IMPLEMENTED | core/mental/anima/source_credibility; 36-source registry with initial CRED tiers; Go crawler CRED… |
| M-040 | Predictive completeness limit PC_limit=1−H_irreducible/H(future)<1 always. | D2-031 | invariant | MEDIUM | no | IMPLEMENTED | api /predictive_limit; sdk wasm compute_pc_limit |
| M-041 | Intelligence Maintenance: IM=Accuracy/Acc_baseline; IM<threshold → auto-retrain / recalibrate / quarantine. | D1-017, D2-032 | protocol | HIGH | no | IMPLEMENTED | core/governance/intelligence_maintenance + core/mental/imp; api /intelligence_maintenance (+/record) |
| M-042 | Genomic Key evolution GK(entity,t)=Hash_DNA(GK(t−1)\|\|BE\|\|TM\|\|CV) — stolen snapshot instantly outdated. | D1-050, D2-034, D2-079, D3-270 | security | CRITICAL | no | IMPLEMENTED | core/spiritual/living_security (GK evolve endpoint, genomic_genealogy DAG); api /living_security/gk |
| M-043 | Security bootstrap blend: SEC_boot=e^(−λ_boot·D)·SEC_classical+(1−w)·SEC_living; SEC(t)=LSS·PQC·CC. | D2-035, D1-055 | formula | CRITICAL | no | IMPLEMENTED | core/spiritual/living_security; api /security/sec composite |
| M-044 | HHI(t)=Σ(s_j·d_j/Σs·d)²×10⁴ with automatic tiers <1500 HEALTHY / 1500–2500 WARNING (2× reward) / 2500–4000 DANGER / >4000. | D2-036, D1-047 | governance | CRITICAL | no | IMPLEMENTED | core/spiritual/hhi_monitor; TrionEpochRegistry HHI≤4000 gate; canonical cert HHI>4000 invalid; AWA… |
| M-045 | Diversity weighting & Coordination Collapse: d_j=1−corr(M_j,M̄); w_j=s_j·d_j; lim_{coord→1} Σ_Byzantine s_j·d_j=0; honesty = Nash… | D1-044, D1-045, D1-046, D1-075, D2-033, D2-095, D3-189, D3-268 | invariant | CRITICAL | no | IMPLEMENTED | core/spiritual/consensus.py (DW-BFT); validator/consensus.go ComputeDiversityWeight… |
| M-046 | Validator reward: REWARD=BASE×accuracy×diversity(d_j)×uptime×(1−slashing). | D2-098 | protocol | HIGH | no | IMPLEMENTED | api /validator/reward; rust/src/validator_fee_calculator.rs |
| M-047 | Biological Capital BC=Flow·Resilience·Uniqueness·Interdependence. | D1-059, D2-041 | formula | MEDIUM | no | IMPLEMENTED | core/extended/bc (GBIF real API); api /biological_capital |
| M-048 | Cross-Species Liquidity XSL=TerritoryViability·FoodSecurity·ReproductionRate/(1+ThreatPressure). | D2-046 | formula | MEDIUM | no | IMPLEMENTED | core/extended/xsl_engine (IUCN); api /cross_species_liquidity |
| M-049 | Biological Rhythm Timer BRT: circadian (t mod 86400)/86400, ultradian 5400, lunar 2551442, seasonal 31557600 phases. | D1-060, D2-042, D3-284 | formula | MEDIUM | no | IMPLEMENTED | core/extended/brt; api /biological_time, /biological_rhythm; sdk wasm 4 BRT phase functions |
| M-050 | Natural Liquidity NL=LD·LO·LC·LS (depth entropy × 1−Sybil_LP × baseline correlation × stress survival). | D1-063, D2-043, D3-264, D3-049, D3-075, D3-225 | formula | CRITICAL | no | IMPLEMENTED | core/extended/NL (LD·LO·LC·LS complete; doc3-era LC/LS stubs completed — anima-service + core/price… |
| M-051 | NL<0.30 → automatic LIQUIDITY_HEALTH signal = hard machine-readable block. | D1-064, D3-073 | invariant | CRITICAL | no | IMPLEMENTED | NL alert floor 0.30 in core/extended; scripts/simulate_attacks.py would-block rule (silence OR… |
| M-052 | Energy Participation EP=VC·PA·DC (value-creation vs MEV extraction). | D2-044 | formula | MEDIUM | no | IMPLEMENTED | core/extended/EP; api /energy_participation |
| M-053 | Sovereign Behavioral Assessment SBA=w_E·E+w_I·I+w_S·S+w_G·G+w_C·C (I=corr(stated policy, onchain enforcement)). | D1-066, D2-045 | formula | MEDIUM | ⚠ YES | IMPLEMENTED | core/governance/sba_engine + core/extended/sovereign_data_fetcher (IMF/WB real APIs); api… |
| M-054 | BTCP_score (route optimization): [0.25·NL+0.20·normalize_gas+0.20·finality_conf+0.15·CC_coherence+0.20·BEO_continuity]×(1−MF_score). | D1-018, D1-109, D3-091, D3-263 | formula | CRITICAL | ⚠ YES | IMPLEMENTED | core/btcp/router + core/master (BTCP score); rust/src/btcp_router.rs; api /api/v1/btcp/score POST… |
| M-055 | BITP match quality: MATCH_QUALITY_SCORE=0.40·price_efficiency+0.30·behavioral_trust+0.20·fill+0.10·time. | D1-065 | formula | MEDIUM | no | IMPLEMENTED | core/btcp modules CMEEngine complement matching (direction×temporal×behavioral_health>0.55×beo_indep… |
| M-056 | Gas formulas: G_total=Σ_chains G_chain×execution_fraction; IAP share G_per_entity=G_total×(value/total). | D3-100, D3-117, D3-276 | formula | HIGH | no | IMPLEMENTED | anima-service/btcp_gas_forecast.py (CI_95 per chain); rust/src/intent_aggregator.rs share split |
| M-057 | Liquidity Ocean: LIQUIDITY_OCEAN_SCORE=Σ_forms VALUE×SHIFT_COST⁻¹×SHIFT_TIME⁻¹×BEHAVIORAL_HEALTH; 'no asset has zero liquidity' (USDC… | D3-143, D3-265, D3-144, D3-146, D3-050 | formula | HIGH | no | IMPLEMENTED | core + anima-service/liquidity_ocean.py; tests/test_liquidity_ocean.py (379 L, 32 tests)… |
| M-058 | OOA confidence growth: OOA_conf(depth)=conf_max·(1−e^(−k·depth)), conf_max=0.85, k=0.001; Θ_OOA=Θ_base×penalty. | D3-113, D3-272 | formula | HIGH | no | IMPLEMENTED | rust/src/ooa_anchor.rs; unknown chain → OOA adapter (fail-closed instead of silent EVM routing) |
| M-059 | BITP/BLO commitment hashes: Hash_DNA(entity\|\|intent\|\|expiry\|\|behavioral_proof\|\|timestamp[\|\|nonce]). | D3-273, D3-274 | formula | MEDIUM | ⚠ YES | IMPLEMENTED | core/btcp/modules (BITP clipboard w/ §17 commitments — repo chose §17 variant) |
| M-060 | Behavioral price ratio (BITP exchange rate)=VALUATION(asset_X)/VALUATION(asset_Y); manipulation-resistant discovery. | D3-110, D3-275, D3-168, D3-224, D3-207 | formula | HIGH | no | IMPLEMENTED | core/price/btcp_price_oracle.py (TWAP + 7-check manipulation detection) |
| M-061 | Validator coverage economics: coverage_bonus=Σ BASE_RATE×rarity×volume×uptime; total_reward=base+coverage+btcp_route_reward−offset. | D3-171, D3-184, D3-185, D3-278, D3-047, D3-233 | formula | HIGH | no | IMPLEMENTED | rust/src/validator_fee_calculator.rs (Coverage Bonus, BTCP_ROUTE_REWARD, cost offset, anti-gaming… |
| M-062 | BTCP route reward split: 60% anchor-chain validators / 40% execution-chain validators. | D3-186, D3-279 | constant | HIGH | no | IMPLEMENTED | rust/src/validator_fee_calculator.rs |
| M-063 | Sybil L1 cap: max_sponsored(j)=floor(log₂(D(j)/D_minimum)×BASE_SPONSOR_CAP), cap=10. | D3-161, D3-280 | constant | HIGH | no | IMPLEMENTED | rust/src/sybil_resistance.rs (5 layers); frontend 5 sybil cards |
| M-064 | Sybil L2 scrutiny: scrutiny_multiplier(n)=1+(n×0.2). | D3-162 | constant | MEDIUM | no | IMPLEMENTED | rust/src/sybil_resistance.rs |
| M-065 | Sybil L3 similarity: cosine(BEO_a,BEO_b)>0.85 → SOCKPUPPET_ALERT → depth freeze + Conscious review. | D3-163, D3-281 | security | HIGH | no | IMPLEMENTED | rust/src/sybil_resistance.rs; CME beo_independence (1−cosSim>0.3) |
| M-066 | Sybil L4 spacing: MIN_SPACING(n)=7 days×n². | D3-164, D3-282 | constant | MEDIUM | no | IMPLEMENTED | rust/src/sybil_resistance.rs |
| M-067 | Sybil L5 network graph: star pattern → SPONSOR_NETWORK_ANOMALY; chain pattern depth_limit=3 hops. | D3-165, D3-209 | security | MEDIUM | no | IMPLEMENTED | rust/src/sybil_resistance.rs |
| M-068 | Finality normalization: effective_latency=max(finality_A, finality_B) — NOT the sum. | D3-045, D3-169, D3-285 | formula | HIGH | no | IMPLEMENTED | rust/src/finality_normalizer.rs |
| M-069 | Network effect: BRIDGE_PAIRS_ELIMINATED(N)=N(N−1)/2 (quadratic, instant pair establishment). | D3-248, D3-286, D3-251, D3-201 | formula | HIGH | no | IMPLEMENTED | rust/src/shadow_observer.rs (N(N−1)/2 pairs eliminated, tested); frontend |
| M-070 | BSC cost model: cost_per_interaction=G_close/N_interactions → 0. | D3-277 | formula | LOW | no | IMPLEMENTED | rust/src/behavioral_state_channel.rs |
| M-071 | Formula architecture is a strict layered L0→L9 dependency graph; every formula feeds upward. | D2-048 | architecture | HIGH | no | IMPLEMENTED | core/ layout mirrors levels; api /whitepaper/coverage (59-formula self-reported LIVE vs… |
| M-072 | Canonical constants registry: every weight/threshold/κ/fee across all 3 docs indexed and implemented; D1 Appendix B = canonical… | D1-150, D3-296 | constant | CRITICAL | ⚠ YES | PARTIALLY IMPLEMENTED | Constants scattered across core modules (worklog Θ=0.55+0.37·V; C-weights; 11 profiles; κ taxonomy… |

### 2. Signal System (35)

| ID | Requirement | Sources | Type | Pri | Contra | Status | Evidence |
|---|---|---|---|---|---|---|---|
| M-073 | Signal taxonomy closed at exactly 19 types. | D1-069, D2-077 | schema | CRITICAL | ⚠ YES | CONTRADICTORY | core/master/signal_factory (24 types); rust/src/signal_emitter.rs (24 registry ids 0–23); sdk (20… |
| M-074 | TRIONSignal full schema — every field present, no optional fields, no partial signals (34 fields / 7 groups). | D2-050 | schema | CRITICAL | no | IMPLEMENTED | core signal dataclasses; tests/test_extended_payload (176-byte v2 payload, 25 tests) |
| M-075 | Identity fields: signal_id bytes32, signal_type, entity_id bytes32 (BEO id). | D2-051 | schema | CRITICAL | no | IMPLEMENTED | core TRIONSignal dataclass; rust types.rs |
| M-076 | Content fields: signal_value float64 (S(t)) + confidence_interval CI_95 always present — never a bare point value. | D1-070, D2-052, D2-008 | schema | CRITICAL | no | IMPLEMENTED | ci_95 always non-null (SDK dataclass + conformal intervals in mental_transformer) |
| M-077 | Coherence fields: coherence, threshold, margin, plane_breakdown{physical,mental,spiritual,conscious,anima,limiting_plane}. | D2-053 | schema | CRITICAL | no | IMPLEMENTED | plane_breakdown in signal schema; api /planes/{id}/{physical,…} |
| M-078 | Quality metadata: temporal_coherence, entropy, akashic_depth, observer_effect, bootstrap_phase, conf_genesis, reflexivity_flag. | D2-054 | schema | HIGH | no | IMPLEMENTED | anima _compute_signal emits all; api /stats discloses synthetic residues |
| M-079 | Living-security fields: genomic_signature bytes64 (sense+antisense), immune_clearance bool, security_generation uint32. | D2-055 | schema | CRITICAL | no | IMPLEMENTED | core signal dataclasses; GK evolution |
| M-080 | Provenance fields: provenance []BehavioralHash (complete derivation chain), validator_count, validator_hhi. | D2-056 | schema | CRITICAL | no | PARTIALLY IMPLEMENTED | provenance chain in schema; validator_count/hhi are hash-derived demo values in api path (labeled… ✏️ IMPROVED THIS AUDIT (8-c): registry-first validator_count/hhi at emission + provenance layer 5 (status registry/caller/unavailable); api /stats demo figures remain a labeled fallback — no live fleet, so still PARTIAL; regression test_validator_provenance_figures |
| M-081 | Timing fields: timestamp, ttl, biological_time{circadian,ultradian,lunar,seasonal} on every signal. | D1-061, D2-057 | schema | HIGH | no | IMPLEMENTED | BRT in signal factory; api /biological_time |
| M-082 | VALUATION — C(t)≥Θ standard signal with 5-plane breakdown, CI_95, provenance. | D2-058 | schema | CRITICAL | no | IMPLEMENTED | signal factory; rust VALUATION payload=T(t) BE f64 |
| M-083 | SILENCE type — structured null with gap, limiting plane, trend, ETA. | D2-059 | schema | CRITICAL | no | IMPLEMENTED | signal factory + api /silence/{id}; rust SILENCE payload=Θ−C |
| M-084 | MANIPULATION_ALERT — MF>threshold; type, confidence, affected BEOs, duration estimate, fingerprint match. | D2-060 | schema | CRITICAL | no | IMPLEMENTED | core/physical/manipulation_detector → alert path; api /security/{id}/mf |
| M-085 | GENESIS — new asset; matched archetypes with sim scores, conf_genesis, trajectory monitoring. | D2-061 | schema | HIGH | no | IMPLEMENTED | core/akashic/genesis; api /genesis/{asset} |
| M-086 | RESURRECTION — dormant asset reactivated; dormancy duration, type, similarity score. | D2-062 | schema | HIGH | no | IMPLEMENTED | core/akashic/resurrection; api /resurrection/{id} |
| M-087 | FORK_DIVERGENCE — history inheritance weights + CC_A/CC_B values. | D2-063 | schema | HIGH | no | IMPLEMENTED | core/akashic/fork_resolution; api /fork_resolution |
| M-088 | TRAJECTORY — ANIMA pre-manifestation; full probability distribution, window, match count, reflexivity_flag. | D2-064 | schema | HIGH | no | IMPLEMENTED | core/akashic/trajectory_anomaly; api /trajectory/{id}, /manifestation_gap |
| M-089 | NEGATIVE_SPACE — significant expected pattern absent. | D2-065 | schema | MEDIUM | no | IMPLEMENTED | api /negative_space/{id} |
| M-090 | PHASE_TRANSITION — lifecycle birth/growth/maturity/decline classification. | D2-066 | schema | MEDIUM | no | IMPLEMENTED | core/thermodynamics/thermo_engine (GAS/LIQUID/SOLID/PLASMA); api /phase_transition |
| M-091 | SYSTEMIC_RISK — stress propagation through Protocol Dependency Graph; cascade reach, time-to-impact. | D2-067 | schema | HIGH | no | IMPLEMENTED | api /dependency_graph; protocol_monitor |
| M-092 | LIQUIDITY_HEALTH — quality not depth; real vs synthetic liquidity; NL breakdown. | D2-068 | schema | HIGH | no | IMPLEMENTED | api /liquidity_health/{id}; NL components |
| M-093 | GOVERNANCE_SIGNAL — power concentration, coordination patterns, outcome quality. | D2-069 | schema | MEDIUM | no | IMPLEMENTED | core/protocol/role_classifier + governance endpoints |
| M-094 | CROSS_CHAIN_COHERENCE — multi-chain divergence detection (selective manipulation). | D2-070 | schema | HIGH | no | IMPLEMENTED | api /cross_chain/{id}; BEO cross-chain coverage tests |
| M-095 | STABLECOIN_HEALTH — depeg risk indicators + collateral behavioral quality. | D2-071 | schema | HIGH | no | IMPLEMENTED | api /stablecoin_health/{asset} |
| M-096 | MEV_EXPOSURE — who extracts, rate, direction, EP impact. | D2-072 | schema | MEDIUM | no | IMPLEMENTED | api /mev/{id}; core/extended/EP |
| M-097 | INSTITUTIONAL_BEHAVIORAL — positioning shifts before filings. | D2-073 | schema | MEDIUM | no | PARTIALLY IMPLEMENTED | frontend-institutional + anima sources (SEC EDGAR Form 4/13F fetcher); pre-filing shift detection… |
| M-098 | REGULATORY_BEHAVIORAL — precursors to regulatory action; pattern matching + jurisdiction flags; sources: SEC/FCA/MAS/ESMA/CFTC, gov… | D2-074, D1-043, D3-053, D3-054 | schema | HIGH | no | IMPLEMENTED | anima-service/anima_regulatory.py (761 L; jurisdiction registry, JRS/AML); 19 RSS + 4 regulatory… |
| M-099 | ECOSYSTEM_HEALTH — developer activity, retention, competition (BC+EP components). | D2-075 | schema | MEDIUM | no | IMPLEMENTED | core data_sources GitHub; api /bc/evm, protocol monitor |
| M-100 | BOOTSTRAP — genesis-phase signal, archetype-derived, auto-transitions to VALUATION when conf_genesis exceeds exit threshold. | D2-076 | schema | HIGH | no | IMPLEMENTED | bootstrap_phase field + transition logic; api /bootstrap/status |
| M-101 | 20 VM-agnostic event types (TRANSFER, SWAP, LIQUIDITY, STAKE, … FLASH_LOAN) — closed cross-VM behavioral vocabulary. | D1-011, D3-190, D3-195 | schema | CRITICAL | no | IMPLEMENTED | EventType const table 0–19 in canonical_bh.ts / Rust / Python (bh_schema_v1.json); 61 EVM + 14… ✏️ FIXED THIS AUDIT (7-d): botchain MEV byte 17→16 (MEV_CAPTURE), Waves Burn→14 (BURN) — regression mev_detection_uses_canonical_byte_16 in trion-botchain |
| M-102 | BTCP_ROUTE signal end-to-end: anchor_BH, execution_BH, gas_saved, BEO_continuity; added to oracle taxonomy, SDK enum, schema linkage… | D3-066, D3-072, D3-236, D3-078, D3-016 | schema | HIGH | no | IMPLEMENTED | rust BTCPRouteSignal storage + event; schema.sql btcp_routes; sdk/TrionSDK.ts BTCP_ROUTE (L37)… |
| M-103 | BEHAVIORAL_TRUTH_SIGNAL (Sensing Oracle): coherence-only output — coherence_score, plane_results TRUE/FALSE, public_commitment; no… | D3-067, D3-150 | schema | HIGH | no | PARTIALLY IMPLEMENTED | contracts/solidity/TRIONSensingOracle.sol + interface exist; ZK coherence proof circuit not built… |
| M-104 | SHADOW_CHAIN_SIGNAL — hostile/unintegrated chain shadow confidence. | D3-068 | schema | MEDIUM | no | PARTIALLY IMPLEMENTED | rust/src/shadow_observer.rs (source collection SIMULATED flag, conf 0.7 placeholder; rejoin gated… |
| M-105 | LIQUIDITY_OCEAN_SIGNAL — ocean_score, form_breakdown, best_form_path, estimated_slippage. | D3-069, D3-145 | schema | MEDIUM | no | IMPLEMENTED | liquidity_ocean.py + signal fields; tests 32 |
| M-106 | CONSENSUS_ADAPTATION_SIGNAL — target chain, trigger, proposed parameter change, expected effect; every ACCEPT/REJECT/PARTIAL/DEFER… | D3-070, D1-111, D1-112 | schema | HIGH | no | PARTIALLY IMPLEMENTED | core/governance/adaptive_consensus module + api governance endpoints; frontend page is static… |
| M-107 | CHAIN_RELIABILITY_SIGNAL — failure-rate warning feeding routing decisions. | D3-071 | schema | MEDIUM | no | IMPLEMENTED | rust/src/btcp_failure_classifier.rs emits on failure classification |

### 3. Five-Plane Architecture (10)

| ID | Requirement | Sources | Type | Pri | Contra | Status | Evidence |
|---|---|---|---|---|---|---|---|
| M-108 | Five planes of reality: Physical Φ (behavioral entropy), Mental M (AI confidence), Spiritual Σ (diversity-weighted validator… | D1-056, D2-004 | architecture | CRITICAL | no | IMPLEMENTED | core/{physical,mental,spiritual} + anima-service; api /planes/{id}/{physical,mental,spiritual,consci… |
| M-109 | TRION expands beyond oracle into six subsystems: semi-immutability, BIRP, Chameleon, BIBL, adaptive consensus, cross-chain BTCP… | D1-002 | architecture | HIGH | no | IMPLEMENTED | All six present: core/novel/{semi-immutable via epigenetics, birp, chameleon}… |
| M-110 | Σ/K/A planes must not be undisclosed fixed-value stubs in C(t) — real engines or disclosed bootstrap. | D3-076, D3-213 | security | CRITICAL | ⚠ YES | PARTIALLY IMPLEMENTED | core/spiritual/sigma_engine; core/mental/anima; anima-service engines; api /stats… |
| M-111 | Consensus degradation tiers: T1 C(t)∈[0.5Θ,Θ) → STALE_SCORE flag, last-confirmed BIBL snapshot (max 50 blocks), routes suspended… | D1-058 | protocol | HIGH | no | IMPLEMENTED | core/spiritual/consensus_degradation; escrow INV-003 coherence floor + cascade revert |
| M-112 | 20 communication channels across 10 layers (physical reality → economic coordination). | D1-085 | architecture | CRITICAL | no | IMPLEMENTED | core/master 20-channel registry; api channel endpoints |
| M-113 | Homomorphic Behavioral Mapping: 9-dim universal behavioral space, cross-chain comparability. | D2-102 | architecture | CRITICAL | no | IMPLEMENTED | core/master homomorphic mapping (9-dim universal space); api /homomorphic/{chain}/{id} |
| M-114 | ANIMA is not a prediction engine — type-system enforced: no point-prediction field exists; outputs are probability distributions. | D2-092 | architecture | CRITICAL | no | IMPLEMENTED | core/mental/anima engine outputs distributions; conformal intervals; type-enforced |
| M-115 | ANIMA 4-category data architecture: onchain behavioral, structured offchain, unstructured offchain, cross-domain. | D2-093 | architecture | HIGH | no | IMPLEMENTED | core/mental/anima/data_streams (4 streams, 59 languages + tier weights)… |
| M-116 | ANIMA v1 build: 1,000+ concurrent crawlers, structured indexers, multilingual NLP (50+ languages), pattern completion, Manifestation… | D1-040, D2-094 | module | HIGH | no | PARTIALLY IMPLEMENTED | crawler pool + 36-source registry + 59 languages + real public APIs; 1,000-concurrent scale not… |
| M-117 | Conscious plane: K(t)=annotation_score×stake×temporal_consistency; 5 annotators/review 3-of-5 majority, pseudonymous, 12-month tenure… | D1-049, D2-109 | component | HIGH | no | PARTIALLY IMPLEMENTED | core/spiritual/conscious (commit-reveal, 6 anti-capture protections, annotators/elders… |

### 4. BTCP Protocol (50)

| ID | Requirement | Sources | Type | Pri | Contra | Status | Evidence |
|---|---|---|---|---|---|---|---|
| M-118 | Bridge problem context: cross-chain proof via multi-sig/light-client/optimistic bridges; BTCP reframe — move behavioral identity, not… | D3-080, D3-081, D3-082 | architecture | HIGH | no | IMPLEMENTED | Zero-bridge execution paths in rust/ + chains/ (zero-bridge-test scripts); BTCPEscrow native release |
| M-119 | Core claims: A (Akashic BH + DW-BFT > any static bridge proof) [PROVED-prose]; B (VM-agnostic 20-event layer) [NOVEL]; C (intent… | D3-083, D3-084, D3-085, D3-086 | invariant | HIGH | no | PARTIALLY IMPLEMENTED | Claim A is a prose argument (no machine proof); honest non-claims (not trustless ZK; still… |
| M-120 | Intent object schema: entity_id (BEO, same across chains), action, assets, magnitude, constraints, expiry. | D3-087 | schema | CRITICAL | no | IMPLEMENTED | rust/src/types.rs Intent; core/btcp orchestrator intent objects |
| M-121 | Intent registration by hash: full intent off-chain in Akashic Index, on-chain by intent_hash; BTCPIntent.sol registry +… | D3-088, D3-024, D3-218, D3-215, D3-031 | component | CRITICAL | no | IMPLEMENTED | contracts/solidity/BTCPIntent.sol; rust/src/btcp_router.rs (intent_hash); core state_store; api… |
| M-122 | BIBL activation in inter-block window (12s Ethereum): reads all integrated chains concurrently (mempool behavioral distribution, BRT… | D3-089, D3-090, D1-104, D1-105, D3-033 | module | HIGH | no | IMPLEMENTED | rust/src/bibl_engine.rs; core/btcp/bibl_engine (15 mempool archetypes + circular-stats BRT; Private… |
| M-123 | RouteType taxonomy: SingleChain, Split{anchor,exec}, Netting{counterparty}, Parallel, OOA, ZK_Private, Wait — Rust enum. | D3-092 | schema | HIGH | no | IMPLEMENTED | rust/src/btcp_router.rs route types; core/btcp/orchestrator route state machine |
| M-124 | Route selection priority (highest BTCP_score wins): NETTING 0.95–0.99 > SINGLE_CHAIN > SPLIT > PARALLEL > OOA > ZK > WAIT. | D3-093 | protocol | CRITICAL | no | IMPLEMENTED | rust/src/btcp_router.rs selection; orchestrator (zk_pending honesty, persisted nonces) |
| M-125 | BTCPProof structure: anchor_bh (H256), consensus_proof, intent_hash, btcp_route_id; proof builder with reorg-protection window (N… | D3-094, D3-034, D3-216, D3-167 | component | CRITICAL | no | IMPLEMENTED | rust/src/btcp_proof_builder.rs (anchor_BH from Hash_DNA, ConsensusProof assembly, reorg protection… |
| M-126 | ConsensusProof: validator_signatures s_j·d_j·sign(anchor_BH), diversity_cert, HHI, C(t); native execution on chain B verifies against… | D3-095, D3-096 | protocol | CRITICAL | no | IMPLEMENTED | core/consensus canonical 346-byte certificate (EIP-191 + felt chunking, L4.2 quorum tiers); full §6… |
| M-127 | ChainAdapter trait (6 methods) translating economic intent into native execution; no bytecode translation. | D3-097, D3-292 | interface | HIGH | no | IMPLEMENTED | core adapters 6-VM system + rust/src/adapters/ |
| M-128 | Event-to-VM mapping: SWAP→Uniswap/Curve/Jupiter/Orca/Osmosis/Aptos DEX; TRANSFER→ERC-20/SPL/bank/coin; LIQUIDITY/BORROW→Aave/Compound… | D3-098 | interface | HIGH | no | IMPLEMENTED | rust/src/adapters/{evm,svm,cosmos,move,cosmwasm,ooa}; core/continuum |
| M-129 | EVM adapter (priority 1): SWAP→best pool per NL, ERC-20 TRANSFER, Aave BORROW; extend existing evm_adapter. | D3-060, D3-219, D3-099 | interface | HIGH | no | IMPLEMENTED | rust/src/adapters/evm/ (btcp execution extension); chains/shared |
| M-130 | SVM adapter (priority 2): Jupiter/Orca SWAP, SPL TRANSFER. | D3-061 | interface | MEDIUM | no | IMPLEMENTED | rust/src/adapters/svm/; chains/svm + svm_indexer.py; Anchor programs in contracts/svm |
| M-131 | Cosmos adapter (priority 3): Osmosis SWAP, bank send, delegation. | D3-062 | interface | MEDIUM | no | IMPLEMENTED | rust/src/adapters/cosmos/ |
| M-132 | Move VM adapter: Aptos DEX SWAP, coin transfer. | D3-063 | interface | MEDIUM | no | IMPLEMENTED | rust/src/adapters/move/; contracts/move |
| M-133 | CosmWASM adapter. | D3-064 | interface | LOW | no | IMPLEMENTED | rust/src/adapters/cosmwasm/; contracts/cosmwasm (multi-denom P1 fixed) |
| M-134 | OOA adapter: Channel-6 no-permission indexing for non-integrated chains. | D3-065, D3-229, D3-038 | interface | MEDIUM | no | IMPLEMENTED | rust/src/ooa_anchor.rs; fail-closed unknown-chain routing |
| M-135 | Gas Abstraction Layer: user pays in source-chain value or TRION token; never holds execution-chain gas token. | D3-101, D3-166, D3-102 | component | HIGH | no | IMPLEMENTED | contracts/solidity/BTCPGasAbstraction.sol + anima-service/btcp_gas_forecast.py |
| M-136 | Route finalization: BTCPRouteSignal stored in TimescaleDB + on-chain event (route_id, anchor/execution chains, BHs, gas, score). | D3-103 | schema | HIGH | no | IMPLEMENTED | rust state_store (12 SQLite projection tables); schema.sql btcp_routes; certificate… |
| M-137 | BITP CUT: entity_A submits intent holding illiquid asset with behavioral_proof (BEO history as credit). | D3-104, D3-105 | protocol | HIGH | no | IMPLEMENTED | rust/src/bitp_matcher.rs; core/btcp modules BITP clipboard |
| M-138 | BITP MATCH: complement(intent_A) satisfying asset in/out reciprocity + price tolerance within bounds. | D3-106 | protocol | HIGH | no | IMPLEMENTED | rust/src/bitp_matcher.rs (exact + tolerance matching); CMEEngine |
| M-139 | BITP unmatched → Behavioral Limit Order in Akashic clipboard with expiry, globally visible. | D3-107 | protocol | HIGH | no | IMPLEMENTED | rust/src/bitp_matcher.rs → BLO creation; bitp_clipboard table |
| M-140 | BITP PASTE: emit release instructions to both chains natively with escrow reference; cross-chain movement ZERO, no lock/mint. | D3-108, D3-109, D3-202 | invariant | CRITICAL | no | IMPLEMENTED | rust/src/bitp_matcher.rs + BTCPEscrow release paths; zero-bridge tests; F-condition 'liquid-pair… |
| M-141 | BLO structure: commitment=Hash_DNA(entity\|\|intent\|\|expiry\|\|behavioral_proof), status lifecycle, bidder ranking by… | D3-123, D3-126, D3-025 | schema | HIGH | no | IMPLEMENTED | contracts/solidity/BehavioralLimitOrder.sol + core/btcp BLO modules |
| M-142 | BLO partial fill (remaining stays as new BLO, same expiry) + expiry semantics (revert, no penalty, honest behavioral record). | D3-124, D3-125, D3-223 | protocol | HIGH | no | IMPLEMENTED | BehavioralLimitOrder.sol partial fill + expiry/revert; rust blo_scheduler |
| M-143 | BLO 5-table DDL: blo_orders, bitp_clipboard, btcp_intent_registry, btcp_routes, btcp_escrow_states (+shadow_observations… | D3-127, D3-214 | schema | CRITICAL | no | IMPLEMENTED | schema.sql L369–557 (7 Phase-0 tables + btcp_version_registry verified present) |
| M-144 | IAP intent pool: direction, participants, total, window deadline, min 3 participants; N≥3 same-direction within window W. | D3-116, D3-226, D3-037 | protocol | MEDIUM | no | IMPLEMENTED | rust/src/intent_aggregator.rs (pool detection; ZK share proof deferred to Phase 4 with honest… |
| M-145 | IAP privacy: amounts hidden from participants; ZK proof of correct share; behavioral credit preserved. | D3-118, D3-119 | security | MEDIUM | no | PARTIALLY IMPLEMENTED | zk-circuits/zk_iap_share_proof/ exists (Merkle-sum circuit) but no build artifacts — Phase-4… |
| M-146 | Behavioral State Capsule: anchor chain/block/hash + behavioral price + staleness CI_95 by state type; chain_B reads capsule not live… | D3-120, D3-121, D3-122, D3-040, D3-227 | schema | HIGH | no | IMPLEMENTED | rust/src/state_capsule.rs (builder + staleness estimation + proof-builder integration) |
| M-147 | Behavioral State Channels: open (collateral in BTCP_ESCROW both chains), operate (any of 20 event types, zero on-chain cost, validator… | D3-134, D3-135, D3-136, D3-137, D3-044, D3-228, D3-208 | protocol | HIGH | no | IMPLEMENTED | rust/src/behavioral_state_channel.rs (full lifecycle) |
| M-148 | BRT scheduling: find_optimal_window(intent, lookahead 200) = circadian_low ∩ NL_peak ∩ MEV_valley; statistical fallback to ANIMA… | D3-138, D3-141, D3-142, D3-052, D3-231, D3-043 | protocol | MEDIUM | no | PARTIALLY IMPLEMENTED | anima-service/brt_scheduler.py + btcp_gas_forecast.py; api /brt; BRT predictions permanently… |
| M-149 | Shadow Observation: collect_shadow_sources (cross-chain references to hostile chain), shadow BH from weighted sources, ~80-byte… | D3-152, D3-153, D3-154, D3-155, D3-156, D3-039, D3-235, D3-204 | protocol | MEDIUM | no | PARTIALLY IMPLEMENTED | rust/src/shadow_observer.rs (295 L, 7 tests): collect_shadow_sources is SIMULATED (flag=true, conf… |
| M-150 | Null states: Liquidity Null (asset nonexistent) and Behavioral Null (entity unknown) must be handled, not crash. | D3-157, D3-158, D3-159, D3-192, D3-205 | protocol | HIGH | no | IMPLEMENTED | rust/src/genesis_commitment.rs (null-state detection, 3 genesis pathways); COLD_START typed SILENCE… |
| M-151 | Sponsored Genesis: sponsor with D>D_minimum stakes sponsor_bond; new entity inherits capped credibility; accountability window. | D3-160, D3-028, D3-042, D3-232 | protocol | HIGH | no | IMPLEMENTED | contracts/solidity/GenesisCommitment.sol; chains/pvm genesis (sponsor(), 14,400-block window… |
| M-152 | Behavioral balance reservation: BEO balances tracked, intents reserve funds in real time (no double-spend across concurrent routes). | D3-170 | invariant | CRITICAL | no | IMPLEMENTED | core/btcp/router S7-persisted balance reservations (SQLite write-through, restart-surviving) |
| M-153 | Routing observer-effect correction: BTCP_ROUTE_OE_FACTOR to prevent circular NL-score reinforcement from TRION's own routing. | D3-172 | formula | MEDIUM | no | PARTIALLY IMPLEMENTED | core/mental/anima/reflexivity provides the OE machinery; BTCP-route-specific OE wiring not… |
| M-154 | Failure classifier: FailureCause{External,Entity,Ambiguous}; External = chain outage/NL<0.10 collapse/reorg>SAFE_CONFIRNS/MF spike… | D3-178, D3-179, D3-180, D3-181, D3-041, D3-230 | protocol | HIGH | no | IMPLEMENTED | rust/src/btcp_failure_classifier.rs + CHAIN_RELIABILITY_SIGNAL emission |
| M-155 | Version governance: BTCPVersionProof (SemVer, min_verifier_ver, feature_flags); major→6-month transition→unupgraded chains drop to… | D3-182, D3-183, D3-046, D3-030 | governance | MEDIUM | no | IMPLEMENTED | rust/src/btcp_version_handler.rs + contracts/solidity/BTCPVersionRegistry.sol + schema.sql… |
| M-156 | ZK Travel Rule (FATF): identity travels with transfers >$1,000; private disclosure + ZK compliance proof; storage of proof hashes only. | D3-176, D3-029 | protocol | HIGH | no | IMPLEMENTED | contracts/solidity/TravelRuleCompliance.sol; anima-service/anima_regulatory.py (real… |
| M-157 | Chameleon integration tiers: LOW proof-optional/compliant-route preference; MEDIUM proof>$1,000; HIGH proof for all; CRITICAL = AWA… | D3-177, D1-100 | protocol | HIGH | no | IMPLEMENTED | chains/pvm travel_rule FatfMode Low/Medium/High/Critical; core/novel/chameleon (5-level threat… |
| M-158 | Dispute resolution: TRION vs chain validators disagree → Behavioral Evidence Standard, Conscious Layer 3-of-5 + stake-and-slash. | D3-174 | governance | MEDIUM | no | IMPLEMENTED | rust/src/dispute_resolution.rs (3-of-5); core/spiritual/slashing 7-step dispute; INV-015… |
| M-159 | BIBL emits: user guidance (timing/routing/batching), Chain Memory Instruction Signal, batch formation opportunities, cross-chain… | D1-106, D1-107, D1-108, D1-110 | protocol | HIGH | no | PARTIALLY IMPLEMENTED | core/btcp/bibl_engine (15 archetypes, circular stats); Private BIBL demo; GasPreferenceProfile +… |
| M-160 | OOA use cases + incentive: non-integrated chain observed at ooa_conf, integrated chain executes; OOA chains score lower in routing… | D3-112, D3-114, D3-115 | protocol | MEDIUM | no | IMPLEMENTED | rust/src/ooa_anchor.rs; routing preference integrated; progressive integration design |
| M-161 | Netting engine: counterparty matching (asset_in_B==asset_out_A), BTCP_score×behavioral_health ranking, simultaneous dual-side escrow… | D3-036, D3-221 | module | CRITICAL | no | IMPLEMENTED | rust/src/netting_engine.rs; CMEEngine complement matching; closing build-order #3 |
| M-162 | Escrow monitor: watch BTCP_ESCROW state, trigger release/revert on consensus signals; cascade revert. | D3-032 | module | HIGH | no | IMPLEMENTED | rust/src/btcp_escrow_monitor.rs + bin/escrow_monitor (state machine, INV-003 coherence floor 0.55… |
| M-163 | Sensing Oracle / Dark Field Protocol: entity computes privately on-device, submits public_commitment only; TRION stores commitment NOT… | D3-147, D3-149 | security | CRITICAL | no | PARTIALLY IMPLEMENTED | contracts/solidity/TRIONSensingOracle.sol + interface; entity-side private compute via root zk… |
| M-164 | Adoption precondition: every BTCP mechanism requires TRION integration on both source and target chains — integration is the primary… | D3-004 | architecture | HIGH | no | PARTIALLY IMPLEMENTED | config/chain_registry.json (129 chains, 40 'integrated' display, 18 VM families); only testnet… |
| M-165 | trion-btcp Rust module suite (doc3 §2 MISSING 17–18 modules + dispute_resolution): router, proof builder, bitp matcher, netting… | D3-290 | module | HIGH | no | IMPLEMENTED | rust/ crate trion-btcp 0.1.0: 21 lib modules + 2 bins, 7,861 lines, 147 #[test] — the entire doc3… |
| M-204 | BITP implementation files: bitp_matcher.rs (CUT/MATCH/PASTE engine), BehavioralLimitOrder.sol, btcp_price_oracle.py. | D3-111, D3-222, D3-035 | module | HIGH | no | IMPLEMENTED | rust/src/bitp_matcher.rs + contracts/solidity/BehavioralLimitOrder.sol +… |
| M-205 | Gas forecast engine: CI_95 gas prediction per chain + BRT gas correlation. | D3-051 | module | HIGH | no | IMPLEMENTED | anima-service/btcp_gas_forecast.py (doc3 MISSING list — now exists) |

### 5. Contracts (15)

| ID | Requirement | Sources | Type | Pri | Contra | Status | Evidence |
|---|---|---|---|---|---|---|---|
| M-166 | Semi-immutability: bytecode immutable AND expression=f(bytecode, environment_signal) changes continuously — without governance votes… | D1-080, D1-081, D1-083, D1-074 | architecture | CRITICAL | no | PARTIALLY IMPLEMENTED | core/novel + epigenetic EL modules; api /semi_immutable/signal/{id}; no deployed semi-immutable… |
| M-167 | CRISPR mechanism: new attack → ADAPTIVE characterizes ≤24h → signature into permanent library → every future match surgically… | D1-082, D1-054, D2-086 | security | HIGH | no | IMPLEMENTED | core/spiritual/living_security CRISPR library ~140 real exploit signatures (incl. Bybit 2025)… |
| M-168 | Smart contracts for EXACTLY two things: (1) publishing signals to chains (Solidity), (2) economic coordination… | D1-084 | architecture | CRITICAL | ⚠ YES | CONTRADICTORY | contracts/ (9 VM languages, ~33,700 source lines); worklog cross-VM contract matrix |
| M-169 | TRIONOracleV3.sol: C(t) signal publication, verifyExecution(), ThermodynamicSignalEtched events. | D3-005 | component | HIGH | no | IMPLEMENTED | contracts/solidity/TRIONOracleV3.sol (962 L: route attestations max(2,⌈2n/3⌉), canonical… |
| M-170 | TRIONProtectedVault.sol: onlyWhenCoherent modifier, pre-execution gate. | D3-006 | component | HIGH | no | IMPLEMENTED | contracts/solidity/TRIONProtectedVault.sol present; Vault-V3 deployed Arb Sepolia |
| M-171 | AttackSimulator.sol: historical exploit simulation (Jimbos, Rodeo, Sentiment). | D3-007 | component | HIGH | no | IMPLEMENTED | contracts/solidity/AttackSimulator.sol + scripts/simulate_attacks{,_onchain}.py |
| M-172 | BTCP_ESCROW.vy (Vyper 0.3.10): 4 state constants IDLE/HOLDING/RELEASED/REVERTED, EscrowRecord struct, storage (oracle/escrows/owner)… | D3-217, D3-237, D3-238, D3-239, D3-241, D3-242, D3-023 | component | CRITICAL | ⚠ YES | IMPLEMENTED | contracts/vyper/BTCP_ESCROW.vy (pragma ^0.3.10; vyper 0.3.10 installed to match)… |
| M-173 | Escrow functions: lock() payable→escrow_id; release() requires state==HOLDING + TRION consensus verification (is_safe, coherence… | D3-240, D3-243, D3-244, D3-245 | protocol | CRITICAL | no | IMPLEMENTED | BTCP_ESCROW.vy + BTCPEscrow.sol (two release paths: legacy oracle-gated + canonical; CEI… ✏️ FIXED THIS AUDIT (7-f, SEC-21): releaseEscrowCanonical verifies escrowBoundEthDigestOf(P, address(this)) — one quorum cert settles exactly one deployment; regression test_same_cert_double_pay_across_two_deployments (flipped to pass) |
| M-174 | Escrow events: EscrowLocked, EscrowReleased, EscrowReverted with indexed escrow_id. | D3-246 | interface | HIGH | no | IMPLEMENTED | BTCP_ESCROW.vy 3 events; cross-VM equivalents |
| M-175 | Escrow invariants: terminal states RELEASED or REVERTED only, no partial execution, TRION consensus is the only oracle (no… | D3-247, D3-198 | invariant | CRITICAL | no | IMPLEMENTED | Two-state atomic HOLDING→RELEASED\|REVERTED verified across VMs; INV-003 coherence floor 0.55… ✏️ FIXED THIS AUDIT (7-f, SEC-21): release path now deployment-bound (escrowBoundEthDigestOf) — the 2×-pay breach of this invariant is closed and test-pinned |
| M-176 | BTCPRoute.sol: route-id tracking, anchor_BH→execution_BH linking. | D3-026, D3-289 | component | HIGH | no | IMPLEMENTED | contracts/solidity/BTCPRoute.sol present; rust route state store |
| M-177 | LiquidityOcean.sol: form-equivalent liquidity tracking contract. | D3-027 | component | MEDIUM | no | IMPLEMENTED | contracts/solidity/LiquidityOcean.sol present + liquidity_ocean.py |
| M-178 | TRION token: fixed supply at genesis, no inflation; burn-on-use deflationary; 15% public-good genesis allocation. | D2-166 | governance | HIGH | no | IMPLEMENTED | contracts/vyper/TRIONToken.vy + ink/TON tokenomics unified (1B @18dec, 15% public-good reserve… |
| M-179 | Token utilities: validator stake (scales w/ influence), governance votes (AWA changes >75%), signal-consumption quality bonds (tiered… | D2-161, D2-163, D2-164, D3-175 | governance | HIGH | no | PARTIALLY IMPLEMENTED | Token contracts + 15% public-good routing + BTCPGasAbstraction implemented; pvm staking.rs is a… |
| M-180 | Vyper for security-critical contracts (staking/slashing/token); simpler syntax = smaller attack surface. | D2-117 | language | CRITICAL | no | PARTIALLY IMPLEMENTED | TRIONToken.vy + BTCP_ESCROW.vy in Vyper; but staking is ink!-stub, slashing lives in… |

### 6. Consensus/Validators (6)

| ID | Requirement | Sources | Type | Pri | Contra | Status | Evidence |
|---|---|---|---|---|---|---|---|
| M-181 | Akashic/DW-BFT consensus: TRION-BFT (Tendermint family), instant finality, diversity-weighted; Σ(t) indicator window with dynamic… | D1-034, D2-099 | protocol | CRITICAL | ⚠ YES | IMPLEMENTED | core/spiritual/consensus.py (DW-BFT, δ_base 0.05); validator/consensus.go (Σ(t), HHI tiers)… |
| M-182 | Validator node software + staking contracts (Vyper, formally verified) + slashing + HHI monitor (L4 build). | D2-105 | component | CRITICAL | no | IMPLEMENTED | validator/ Go Tendermint-style BFT (36 tests); core/spiritual/{slashing,hhi_monitor,validator_regist… |
| M-183 | Validator hardware: 32+ cores EPYC/Xeon, 256GB DDR5 ECC, 10TB NVMe, A100/H100, 10Gbps fiber, HSM (Thales Luna 7 / YubiHSM 2)… | D1-132, D2-096 | deployment | CRITICAL | no | UNKNOWN | No hardware enforcement or HSM integration anywhere in repo (worklog: no HSM evidence; validator… |
| M-184 | Validator set: minimum 100 validators across ≥4 continents at launch. | D2-097 | deployment | CRITICAL | no | MISSING | validator_registry has 100-validator/4-continent launch GATE (software); no live fleet — emission… |
| M-185 | Geographic enforcement: N_continents≥4 at all times, max single region <0.40, max single jurisdiction <0.30. | D1-048 | governance | HIGH | no | PARTIALLY IMPLEMENTED | validator_registry launch gate + geo endpoints + F9 monitor in falsifiability registry; not… |
| M-186 | Slashing conditions: coordinated attack 50%+permanent exclusion; sustained low accuracy 3%/30d; hardware/HSM violation 10%; uptime… | D2-037 | governance | CRITICAL | no | IMPLEMENTED | core/spiritual/slashing (5 conditions, 7-step dispute, 72h); 7-type slashing in token contracts… |

### 7. Security/Crypto/PQC (18)

| ID | Requirement | Sources | Type | Pri | Contra | Status | Evidence |
|---|---|---|---|---|---|---|---|
| M-187 | Living Security founded on three formally-implemented DNA properties: Causal Singularity, Structural Self-Verification (base-pair… | D2-078 | security | CRITICAL | no | IMPLEMENTED | core/spiritual/living_security (8 components; GK genealogy DAG; dual-strand everywhere; immune… |
| M-188 | Immune System 3 layers: INNATE pattern-matching <1 block vs Adaptive Threat Library; ADAPTIVE characterize→respond→update; MEMORY… | D1-052, D2-081 | security | HIGH | no | IMPLEMENTED | core/spiritual/living_security immune (adaptive + memory endpoints); ~140 CRISPR signatures |
| M-189 | Epigenetic Layer: EL_state=f(Threat_level, Validator_health, Network_entropy) — architecture unchanged, expression changes. | D1-053, D2-082 | security | HIGH | no | IMPLEMENTED | core/spiritual/epigenetic + api /living_security/epigenetic; akashic/epigenetics (methylation) |
| M-190 | Genetic Recombination: security parameters periodically re-derived from behavioral history — old attacks useless after each… | D2-083 | security | HIGH | no | IMPLEMENTED | core/spiritual/living_security recombination + epigenetic update path |
| M-191 | Cryptographic Noise: realistic-looking decoy sequences carrying no information; noise pattern itself authenticated. | D2-084 | security | HIGH | no | IMPLEMENTED | core/spiritual/living_security noise (api /living_security/noise/{id}) |
| M-192 | Mitochondrial Core: separate independently-maintained Behavioral DNA encoding only fundamental protocol properties; second… | D2-085 | security | HIGH | no | IMPLEMENTED | core/spiritual/living_security mitochondrial endpoint |
| M-193 | BCK / Kolmogorov bound: K(H(TRION,t)) ≥ Ω(t·N_chains·N_validators·H_environment); P(break)=P(reproduce causal history); lim P→0.… | D1-051, D1-073, D3-271, D3-199 | invariant | CRITICAL | no | PARTIALLY IMPLEMENTED | GK causal chaining + genomic_genealogy DAG implement the causal-history property; Ω lower bound is… |
| M-194 | PQC layer: CRYSTALS suite (Kyber ML-KEM + Dilithium ML-DSA + SPHINCS+ SLH-DSA). | D2-106 | security | CRITICAL | no | IMPLEMENTED | kyber-py/dilithium-py/pyspx round-trips verified (Task 3 L1/L3/L5 all True); api… |
| M-195 | AWA (Anti-Weaponization Architecture): 6-condition conjunction, auto-freeze of ALL signal emission on violation. | D1-101, D2-154 | governance | CRITICAL | ⚠ YES | IMPLEMENTED | core/governance/awa EmissionGate wired into signal_factory (503 when frozen)… |
| M-196 | Right to Invisibility: architectural enforcement — if not enforced, AWA_enforced=FALSE → emission FROZEN. | D1-090 | security | CRITICAL | no | IMPLEMENTED | core/governance/right_to_invisibility (SQLite petitions); AWA freeze path; frontend institutional… |
| M-197 | BIRP enrollment: DNA_Code known only to user (only Hash stored), user-defined min length; time-based invalidation (stolen code becomes… | D1-091, D1-092 | security | HIGH | no | IMPLEMENTED | core/novel/birp (5-phase §16 state machine) + behavioral_identity_recovery (32-dim, δ=0.15, Schnorr… ✏️ FIXED THIS AUDIT (7-b, SEC-04): BIRPAttestation.submit_proof now verifies StarkCurve ECDSA (r,s) over Poseidon('BIRP-ATT-V1', commitment, tier, confidence_bp, nonce) vs storage-pinned oracle pubkey; replay nonce burned post-verify; the (0,0)-placeholder honesty gap is closed; tests test_birp_attestation_cairo.py |
| M-198 | BIRP recovery phases: P1 DNA_Code (exact timing/length/dual-strand hash); P2 Akashic behavioral challenges; P3 temporal transaction… | D1-093, D1-094, D1-095, D1-096, D1-097 | protocol | HIGH | no | IMPLEMENTED | core/novel/birp 5-phase state machine + relay messages; cairo BIRPAttestation (attest/revoke; sig… ✏️ HARDENED THIS AUDIT (7-b, SEC-04): cairo attestation tier is now signature-verified (was relayer-trusting); birp-bridge.ts signs real (r,s), fail-closed without BIRP_ORACLE_PRIVATE_KEY |
| M-199 | BIRP honest limitation: challenges drawn from RECENT behavioral history (patterns drift); BEO baseline updates continuously. | D1-098 | protocol | MEDIUM | no | IMPLEMENTED | birp uses recent-history challenges; BEO baseline continuous updates |
| M-200 | Chameleon Protocol: detect coming government action (REGULATORY_BEHAVIORAL + SBA divergence + capital entropy); 5-level adaptation… | D1-099 | protocol | MEDIUM | no | IMPLEMENTED | core/novel/chameleon (σ 0.015→0.060 probe noise, 5-level state machine); api /chameleon/{id}… |
| M-201 | ZK proves compliance, not evasion — illegal transaction with ZK privacy proof is still detectable as non-compliant. | D1-102 | security | MEDIUM | no | IMPLEMENTED | anima_regulatory NIZK compliance-predicate (is_stub=False); travel-rule triggering |
| M-202 | Critical key hygiene: rotate hardhat.config.ts private key exposed in git history; move keys to env vars + .env.example; blacklist… | D3-079, D3-021, D3-211, D3-212 | security | CRITICAL | no | IMPLEMENTED | hardhat/ REMEDIATED: env-var RELAYER_PRIVATE_KEY, fail-closed mainnet key policy (12… ✏️ HARDENED THIS AUDIT (7-e, SEC-02/22): derive-address.mjs key/WIF redacted from stdout (opt-in DEBUG_KEYS=1 → stderr); .env.railway untracked → .env.railway.example + .gitignore rules |
| M-203 | March 12, 2026 'Aave incident' presented as REAL validation ($50M USDT→AAVE, NL≈0.09, CI_95 [0.06,0.14], DO_NOT_ROUTE). | D1-143 | integration | HIGH | ⚠ YES | DEAD/FALSE CLAIM | scripts/simulate_attacks.py ([SIMULATED] AAVE Mar 2026 retained as deterministic test vector)… |
| M-206 | Sybil-resistance implementation file: 5-layer Sponsored-Genesis protection (doc3 Fix 5). | D3-048, D3-187 | module | HIGH | no | IMPLEMENTED | rust/src/sybil_resistance.rs (doc3 MISSING list — now exists) |

### 8. ZK (5)

| ID | Requirement | Sources | Type | Pri | Contra | Status | Evidence |
|---|---|---|---|---|---|---|---|
| M-207 | Behavioral ZK concept: prove 'history H satisfies condition C' without revealing H; hidden info is dynamic/growing, backed by Akashic… | D1-088, D1-089, D1-076 | security | HIGH | no | PARTIALLY IMPLEMENTED | zk/ package (1,411 L): 5 real secp256k1 Schnorr-Pedersen ZK circuits (sigma protocol +… |
| M-208 | Five Circom circuits: zk_intent_commitment, zk_complementarity_proof, zk_behavioral_credential, zk_travel_rule, zk_iap_share_proof… | D3-055, D3-056, D3-057, D3-058, D3-059, D3-293, D3-234, D3-133 | component | MEDIUM | no | PARTIALLY IMPLEMENTED | zk-circuits/ (12 files, 5 folders, README): circuit sources + verifier stubs exist; NO build… |
| M-209 | ZK Intent Commitment 4-phase MEV privacy: commit H(intent\|\|nonce) only → ZK complementarity match → same-block atomic reveal →… | D3-128, D3-129, D3-130, D3-131, D3-210 | protocol | HIGH | no | PARTIALLY IMPLEMENTED | zk package intent-commitment circuit + orchestrator zk_pending honesty (deferred when witnesses… |
| M-210 | Opt-in privacy vs latency tradeoff: phases 1–3 only when MEV risk > latency cost; Intent.constraints privacy values (ZK_CREDENTIAL \|… | D3-132 | protocol | MEDIUM | no | PARTIALLY IMPLEMENTED | Intent constraints modeled; opt-in UI/latency-cost logic not evidenced |
| M-211 | Sensing-Oracle ZK coherence proof: SNARK 'my behavioral_hash is coherent with my historical BEO pattern' with public commitment only… | D3-148, D3-151, D3-203 | security | HIGH | no | PARTIALLY IMPLEMENTED | zk_behavioral_credential circuit source exists (unbuilt); privacy falsification condition tracked… |

### 9. Indexers/Data (10)

| ID | Requirement | Sources | Type | Pri | Contra | Status | Evidence |
|---|---|---|---|---|---|---|---|
| M-212 | Rust L0 daemon: block streaming + 9 Shannon-entropy features per block (doc3 EXISTS map, path trion-l0/ now consolidated into rust/). | D3-008, D3-288 | module | HIGH | no | IMPLEMENTED | rust/ crate + indexers/ (22-crate workspace); 9 entropy features in phi_engine + svm_indexer… |
| M-213 | Every transaction/swap/deposit/vote/bridge permanently recorded and read every block, every chain, continuously (behavioral… | D2-002 | architecture | HIGH | no | IMPLEMENTED | bh_streamer polls ~61 public RPCs; bh_ledger.db (SQLite WAL) + optional PG; FAISS vectors; 0G… |
| M-214 | Multi-chain RPC failover adapter covering Arbitrum, BNB, ETH, Base, Polygon, Avalanche. | D3-010 | module | MEDIUM | no | IMPLEMENTED | rust/src/adapters/evm; relayer retry/backoff; network/health_monitor.go (19 endpoints, goroutines) |
| M-215 | Akashic Index on TimescaleDB (billions of events, microsecond queries); BH schema + BTCP_ROUTE linkage tables. | D1-031, D1-033, D1-131, D2-121, D3-017, D3-077 | deployment | CRITICAL | no | PARTIALLY IMPLEMENTED | schema.sql (7 Phase-0 tables + btcp_version_registry + linkage); faiss_service psycopg2/TimescaleDB… |
| M-216 | Historical bootstrap: full EVM history from genesis loaded before first live signal; archetype library >90% behavioral coverage. | D1-036 | deployment | HIGH | no | PARTIALLY IMPLEMENTED | backfill checkpoints + /backfill/status + /index/bulk_backfill (~50× faster path); 12 archetypes +… |
| M-217 | FAISS semantic index (34,600 vectors, L2 search). | D3-012 | component | MEDIUM | no | IMPLEMENTED | anima-service/faiss_service.py (IndexFlatL2→IVFPQ auto-promotion; 165 routes; akashic_faiss.index) ✏️ HARDENED THIS AUDIT (7-a/8-a, SEC-01/24): X-API-Key middleware on all 165 routes (key set → 401; unset → fail-closed 503 on writes + /api/v1/pqc/sign), default bind 127.0.0.1, compose publish loopback-only; tests test_faiss_auth.py |
| M-218 | CRISPR anomaly pattern-matching module. | D3-013 | component | MEDIUM | no | IMPLEMENTED | akashic/crispr_anomaly.py + core CRISPR library |
| M-219 | ANIMA liquidity health engine (LD, LO real; LC, LS formerly stubs). | D3-014 | module | HIGH | no | IMPLEMENTED | anima-service + core/price engines exist; LC/LS completed post-Apr-2026 (D3's partial-stub finding… |
| M-220 | BRT timer module (circadian/ultradian/lunar/seasonal). | D3-015 | module | MEDIUM | no | IMPLEMENTED | akashic/brt.py + core/extended/brt |
| M-221 | 6 Python BTCP engines: nl_score_engine, liquidity_ocean, btcp_gas_forecast, brt_scheduler, anima_regulatory, btcp_price_oracle. | D3-291 | module | HIGH | no | IMPLEMENTED | anima-service/{nl_score_engine? → engine files}, liquidity_ocean.py, btcp_gas_forecast.py… |

### 10. APIs/Services (6)

| ID | Requirement | Sources | Type | Pri | Contra | Status | Evidence |
|---|---|---|---|---|---|---|---|
| M-222 | Akashic Oracle service: /api/v1/signal/:entity_id + /api/v1/health, performing C(t) computation ('live on Arbitrum Sepolia'). | D3-011 | service | HIGH | no | IMPLEMENTED | api/app.py Flask (11k lines, 100+ routes; boots clean from repo root; /healthz, /readyz 503 until… ✏️ HARDENED THIS AUDIT (7-c, SEC-03/14/20): unauthenticated writes → 503 auth_not_configured when TRION_API_KEY unset; CORS default same-origin (TRION_CORS_ORIGINS opt-in); publish path SHA3-256; tests test_api_auth_failclosed.py + test_api_publish_hashing.py |
| M-223 | SDK distribution: npm @trion/sdk (TS), cargo trion-sdk (Rust), pip trion-sdk (Python). | D2-167 | interface | HIGH | no | PARTIALLY IMPLEMENTED | sdk/TrionSDK.ts + sdk/src (npm package.json) + sdk/trion_sdk.py present; pip/cargo publishing not… |
| M-224 | SDK API — getSignal(entityId, {profile, assetType}). | D2-168 | interface | CRITICAL | no | IMPLEMENTED | trion_sdk.py get_signal (profiles/asset types); TrionSDK.ts fetchSignal |
| M-225 | SDK API — subscribe(entityId, callback, {types, minCoherence, onSilence EMIT\|SUPPRESS}). | D2-169 | interface | HIGH | no | IMPLEMENTED | trion_sdk.py subscribe; frontend polling + flask-socketio live streams |
| M-226 | SDK API — verifySignal(signal) → {valid, provenance_chain_depth, all_BH_retrievable, genomic_valid}. | D2-170 | interface | CRITICAL | no | IMPLEMENTED | trion_sdk.py verify_signal; BehavioralHash.verify() both strands |
| M-227 | SDK API — getHistory(entityId, {from, to, types}). | D2-171 | interface | HIGH | no | IMPLEMENTED | trion_sdk.py history; api /signal/{id}/history |

### 11. Frontends/SDK (5)

| ID | Requirement | Sources | Type | Pri | Contra | Status | Evidence |
|---|---|---|---|---|---|---|---|
| M-228 | TypeScript type enforcement: SILENCE cannot be misused as VALUATION — compile error; signal_value undefined on SilenceSignal; CI_95… | D1-087, D2-172 | interface | CRITICAL | no | IMPLEMENTED | sdk TS types (20 signal types); ci_95 non-null in dataclasses; wasm registry ids byte-identical |
| M-229 | On-chain integration interface ITRIONConsumer { consumeSignal(TRIONSignal) }; publish via pull (subscribe) + push (callback); 256-byte… | D2-173, D1-086 | interface | HIGH | no | IMPLEMENTED | interfaces in contracts/solidity; core/primitives/signal_packing (256-bit packed uint256, bit… |
| M-230 | WebAssembly: browser-side signal processing + SDK browser bundle (near-native, no server round-trips). | D2-122 | language | MEDIUM | no | IMPLEMENTED | sdk/src/wasm/signal_processor.wat (298 L: 24 types, threshold, coherence, BRT, hand-rolled log2) +… |
| M-231 | Developer + institutional frontends consuming live oracle/FAISS endpoints (annotation interface, dashboards, BTCP controls). |  | interface | HIGH | no | IMPLEMENTED | frontend/ (Next.js 16, ~115 page ids, live polling of oracle/FAISS; CoherenceEngine radar… |
| M-232 | TS language for SDK + annotation interface + consuming-protocol libraries. | D2-116 | language | HIGH | no | IMPLEMENTED | sdk TS + frontends + relayer/evm-tools TS; annotation interface APIs in anima-service |

### 12. Deployment/Infra (9)

| ID | Requirement | Sources | Type | Pri | Contra | Status | Evidence |
|---|---|---|---|---|---|---|---|
| M-233 | Exact language stack: Rust core/crypto; Go networking/crawler-coordination/API gateway; Python AI/ML training; TS interfaces… | D1-130, D2-113, D2-114, D2-115, D2-123 | language | CRITICAL | ⚠ YES | PARTIALLY IMPLEMENTED | All 10 languages present (337 Py, 89 Rust, 20 Go, 143 TS/JS, 51 Sol, 33 Cairo, Vyper, Julia math/… |
| M-234 | Julia for scale-invariance verification, entropy budget, PI mathematical validation. | D2-118 | language | MEDIUM | no | IMPLEMENTED | math/ (471 L) + ci-julia workflow (runtests) |
| M-235 | Haskell for formal verification (homomorphic proofs, consensus safety, quantum resistance) with theorems-as-types. | D2-119 | language | HIGH | no | PARTIALLY IMPLEMENTED | formal/ (642 L: Theorems + hspec run in CI); theorem-as-type encoding not achieved |
| M-236 | C++ for FFT, hardware drivers, real-time signal conditioning. | D2-120 | language | MEDIUM | no | PARTIALLY IMPLEMENTED | signal-processing/ (651 L) present; FFT/hardware drivers not evidenced in worklog |
| M-237 | Multi-stage Docker build (Rust + Node + Python) + containerized deploy. | D3-020 | deployment | LOW | no | IMPLEMENTED | 3 Dockerfiles + docker-compose + render.yaml + railway.toml + anima-service/start.sh (FAISS +… |
| M-238 | Four live Arbitrum Sepolia deployments: TRIONOracleV3 0xb819…58b3, Vault-V3 0x93fD…716D, Vault-AttackMatrix 0x91D7…7fE5… | D3-022 | deployment | HIGH | no | IMPLEMENTED | deployments.json (fallback Arb-Sepolia addresses); relayer CHAINS baked-in addresses; frontend… |
| M-239 | Integration roadmap + bootstrap chain sequencing (N(N−1)/2 maximization: ETH family → Solana → Cosmos…); 10-chain sequence; instant… | D3-249, D3-250, D3-173 | roadmap | MEDIUM | no | PARTIALLY IMPLEMENTED | config/chain_registry.json (129 chains, 40 integrated, 18 VM families); mainnet_bootstrap… |
| M-240 | Build phases 0–5 (doc3 §14.1) with timelines: Phase 0 security/schema (weeks 1–2), Phase 1 core routing (3–8), Phase 2 BITP/netting… | D3-220, D3-295 | roadmap | HIGH | no | PARTIALLY IMPLEMENTED | Repo build order mirrors closing sequence (escrow→router→netting priority); Phase-0 items done (key… |
| M-241 | CI: 10 GitHub workflows (pytest, hardhat compile, cargo, go, tsc, runghc, julia, security-audit, supply-chain, slither). |  | deployment | HIGH | no | IMPLEMENTED | .github/workflows/ (10 files, 340 lines; trigger-branch typo 'ain, dev]' noted); supply-chain runs… ✏️ CORRECTED THIS AUDIT (SEC-16): the 'trigger-branch typo ain,dev]' note was a display artifact — od -c shows branches [main, dev]; workflow file well-formed (REFUTED, no code change) |

### 13. Testing/Verification (26)

| ID | Requirement | Sources | Type | Pri | Contra | Status | Evidence |
|---|---|---|---|---|---|---|---|
| M-242 | Proof 1 — Manipulation resistance: no rational actor profitably manipulates TRION for assets with sufficient history; attack cost… | D2-134 | testing | CRITICAL | no | PARTIALLY IMPLEMENTED | api /manipulation/attack_cost/{id} + inverted_price_feed (C_manipulate=K·e^(α·D), K=$2M, α=0.46)… |
| M-243 | Proof 2 — Consensus safety: DW-BFT safe and live under conditions stronger than standard BFT. | D2-135, D3-188, D3-193 | testing | CRITICAL | no | PARTIALLY IMPLEMENTED | Haskell Theorems + tests/test_consensus_bft (50-sybil measured 75.8%→0%); bridge-vs-multisig… |
| M-244 | Proof 3 — Quantum resistance: LSS resistant to arbitrarily powerful quantum computers (P(break)=P(reproduce causal history)). | D2-136 | testing | CRITICAL | no | PARTIALLY IMPLEMENTED | PQC round-trips + GK causal DAG; quantum-resistance proof is prose (AN-10) |
| M-245 | Proof 4 — Signal convergence: diversity-weighted consensus is a consistent estimator; convergence to H_irreducible. | D2-137 | testing | CRITICAL | no | PARTIALLY IMPLEMENTED | convergence monitors + Haskell; prose-level proof |
| M-246 | Doc1 claim ledger: 6 PROVED / 4 CONJECTURE / 5 NOVEL primitives with statuses. | D1-113 | testing | HIGH | no | PARTIALLY IMPLEMENTED | core/governance/falsifiability registry (F1–F15 with status_source honesty labels)… |
| M-247 | F1/F2 falsification (manipulation resistance + consensus safety): documented successful manipulation at D>D_minimum; two contradictory… | D1-114, D1-115, D2-138, D2-139, D3-194, D3-206 | testing | CRITICAL | no | PARTIALLY IMPLEMENTED | falsifiability registry rows wired to modules; attack replay engine scores real pipeline… |
| M-248 | F3/F4 (D1): CI calibration persists wrong; Living Security breached without causal-history reproduction. | D1-116, D1-117, D2-141 | testing | CRITICAL | no | PARTIALLY IMPLEMENTED | conformal-interval calibration tests (test_conformal_predictor 8); LSS breach detection via… |
| M-249 | F5 convergence divergence (D1/D2). | D1-118, D2-142 | testing | CRITICAL | no | PARTIALLY IMPLEMENTED | convergence monitors + 12-month rolling windows designed; not live |
| M-250 | F6 genesis inference divergence (90-day, 100+ events). | D1-119, D2-143 | testing | HIGH | no | PARTIALLY IMPLEMENTED | genesis/archetype tests; held-out backtest (non-circular 67/33) |
| M-251 | F7 intelligence-maintenance degradation >24h undetected. | D1-120, D2-144 | testing | HIGH | no | PARTIALLY IMPLEMENTED | IM record path + /intelligence_maintenance; continuous detection not live |
| M-252 | F8/F9 (D1): HHI>2500 sustained 30 days without correction; geographic distribution <4 continents without incentive. | D1-121, D1-122, D2-145 | testing | CRITICAL | no | PARTIALLY IMPLEMENTED | hhi_monitor + F8/F9 violation chips in frontend; auto-correction not live |
| M-253 | F9 (D2): BC scores diverge from peer-reviewed ecosystem valuations. | D2-146 | testing | MEDIUM | no | PARTIALLY IMPLEMENTED | GBIF-calibrated BC engine; no peer-review comparison harness |
| M-254 | F10 (D1): SILENCE gap estimates systematically inaccurate vs actual recovery. | D1-123 | testing | MEDIUM | no | PARTIALLY IMPLEMENTED | silence gap field emitted; recovery-accuracy study not run |
| M-255 | F10 (D2): XSL early warning fails (species declines not preceded by XSL decline >30 days). | D2-147 | testing | MEDIUM | no | PARTIALLY IMPLEMENTED | XSL engine (IUCN); per-event validation not run |
| M-256 | F11 (D1): observer-effect circular reinforcement; F11 (D2): SBA divergence from IMF/WB composites. | D1-124, D2-148 | testing | MEDIUM | no | PARTIALLY IMPLEMENTED | observer_effect record + reflexivity dampening; sovereign fetcher (IMF/WB) exists; rolling… |
| M-257 | F12 (D1): AWA violation without system freeze. | D1-125 | testing | HIGH | no | PARTIALLY IMPLEMENTED | AWA freeze tested (TRIONExecutionGate.test.ts 14 behaviors incl. AWA freeze conditions + restore) |
| M-258 | F12 (D2): ANIMA probability distributions consistently miscalibrated (90-day rolling). | D2-149 | testing | HIGH | no | PARTIALLY IMPLEMENTED | anima calibrate endpoint + conformal tests; rolling calibration not live |
| M-259 | F13 (D1): MF false-positive rate >2% on clean histories; F13 (D2): known unified actors not clustered >95% (quarterly audit). | D1-126, D2-150, D3-196 | testing | CRITICAL | no | PARTIALLY IMPLEMENTED | test_property_based (Hypothesis 12) + BEO resolution tests; clean-history FP-rate study + quarterly… |
| M-260 | F14: BRT gas-circadian correlation failure (F-test, 90-day, 1M+ blocks). | D1-127, D1-062, D3-200, D3-003, D3-140, D3-259, D3-139 | testing | HIGH | no | PARTIALLY IMPLEMENTED | BRT predictions permanently labeled CONJECTURE until 90-day F14 validation (fail-closed labeling… |
| M-261 | F15 (D1): REGULATORY_BEHAVIORAL no significant advance warning over 24 months; F15 (D2): silence-gap uncorrelated with next-signal… | D1-128, D2-152 | testing | HIGH | no | PARTIALLY IMPLEMENTED | regulatory feeds + silence gaps emitted; both windows require live operation |
| M-262 | Gas-optimization superiority falsification: sustained BTCP routes costlier than optimal single-chain equivalent. | D3-197 | testing | HIGH | no | PARTIALLY IMPLEMENTED | gas_forecast + worked examples; sustained-route cost study not run |
| M-263 | F3 (D2): ANIMA-improves-signals claim — ANIMA-enhanced signals consistently less accurate than 3-plane alone (90-day rolling). | D2-140 | testing | HIGH | no | PARTIALLY IMPLEMENTED | anima calibrate endpoint + held-out backtest; A/B plane comparison harness not run live |
| M-264 | F14 (D2): Observer-effect correction — M_adj not lower than M_base for high-OE assets (continuous). | D2-151 | testing | HIGH | no | PARTIALLY IMPLEMENTED | reflexivity dampening implemented; high-OE asset class validation not run |
| M-265 | Attack simulation scripts: local (core detectors + NL) and on-chain proof generation; 7 historical exploits. | D3-018, D3-019, D1-144 | testing | MEDIUM | no | IMPLEMENTED | scripts/simulate_attacks.py (offline + --live Oracle:5000/FAISS:8000; Jimbos, Rodeo, Sentiment… |
| M-266 | Formal-verification specialists in Coq, Lean, TLA+ (tests find known bugs; proofs eliminate unknown bugs). | D2-128 | governance | HIGH | no | MISSING | No Coq/Lean/TLA+ artifacts anywhere in repo (Haskell Theorems + hspec only) |
| M-267 | Test-suite breadth evidence (no direct doc req): master formula verification, cross-language golden vectors, property-based, contract… |  | testing | HIGH | no | IMPLEMENTED | tests/ (~97 files, ~1,730 pytest functions): test suite TRUE baseline 1650 passed / 113 failed (all… ✏️ EXTENDED THIS AUDIT: +4 regression batteries (test_faiss_auth 11, test_api_auth_failclosed 19, test_api_publish_hashing 6, test_birp_attestation_cairo 11) + the flipped same-cert-double-pay regression; see FINAL_TEST_REPORT.md |

### 14. Governance/Team/Roadmap (21)

| ID | Requirement | Sources | Type | Pri | Contra | Status | Evidence |
|---|---|---|---|---|---|---|---|
| M-268 | Initialization ceremony INIT_valid: ≥100 validators, ≥4 continents, D_akashic≥D_minimum, ≥3 chains indexed, SEC_bootstrapped… | D2-153 | governance | CRITICAL | no | IMPLEMENTED | core/governance/initialization (INIT_valid checker); api /governance/init + ceremony endpoints… |
| M-269 | Gratitude Protocol: Gratitude=Value_given_to_life/Value_received≥1; sustained <1 → freeze. | D2-155 | governance | HIGH | no | IMPLEMENTED | core/governance/awa (Gratitude 0.95/wk tracked; gratitude≥1 in AWA); api /governance/gratitude |
| M-270 | Unknown-unknown provision: 10% of revenue reserved; spend requires >75% supermajority + 30-day timelock. | D2-156 | governance | HIGH | no | PARTIALLY IMPLEMENTED | core/governance/unknown_unknown (10% reserve module); supermajority vote + timelock mechanics NOT… |
| M-271 | Public Good Charter: 15% of fee revenue automatically routed to public-good pool; governance-disbursed. | D2-165 | governance | HIGH | no | IMPLEMENTED | Token contracts 15% public-good reserve (genesis split); AWA publicGood≥15% check; api… |
| M-272 | Token-weighted governance: parameter changes by vote; AWA modifications need >75% supermajority; emergency powers = 3-of-5 multisig… | D2-162 | governance | HIGH | no | PARTIALLY IMPLEMENTED | 3-of-5 multisig concept realized in dispute_resolution; token-weighted voting + emergency council… |
| M-273 | SBA signal governance: appeal mechanism (any entity incl. governments), cultural_context_vector, complete provenance, no legal advice. | D1-067 | governance | MEDIUM | no | IMPLEMENTED | api /sovereign_appeal/{id} (+/status) with cultural context + provenance |
| M-274 | Team plan: 17 people / 18 months / $8–12M for first signal (Rust 3, Py/ML 3, Go 2, Sol/Vyp 2, DB 2, math/FV 1, DevOps 2, comp-bio 1… | D2-124, D2-125, D2-126, D2-157, D2-158, D2-159 | governance | CRITICAL | no | UNKNOWN | Org/finance-level; no code evidence (worklog: single-developer-shaped repo, 83-commit… |
| M-275 | 7 critical non-obvious hires: cryptography researchers, FV specialists (Coq/Lean/TLA+), computational biologists, ecologists, embedded… | D2-127, D2-129, D2-130, D2-131, D2-132, D2-133 | governance | HIGH | no | UNKNOWN | Org-level; repo has corresponding modules (elder_wisdom, indigenous DB, love_protocol, chameleon)… |
| M-276 | Revenue model: 6 streams (signal consumption fees tiered by TVL, genesis inference, verification, data market, enterprise, API). | D2-160 | governance | HIGH | no | PARTIALLY IMPLEMENTED | api /trion/revenue (demo numbers); fee calculator; no live billing |
| M-277 | Build discipline: do not skip levels; each level is the foundation of the next; test every level before proceeding. | D2-100, D2-112 | roadmap | CRITICAL | ⚠ YES | PARTIALLY IMPLEMENTED | Repo construction order followed L0→L9 primitives map (core layout); first signal emitted at… |
| M-278 | Roadmap L0 — Behavioral Hash + entity resolution + EVM indexer (Rust) + TimescaleDB Akashic v1 + entropy calculator +… | D1-133, D2-101 | roadmap | CRITICAL | no | IMPLEMENTED | BH 93-byte dual-strand + entity_resolution + indexers + schema.sql + phi entropy… |
| M-279 | Roadmap L1 — Physical layer: 9-feature extraction, Φ(t), all 7 manipulation fingerprints, Φ_adj, transduction. | D1-134 | roadmap | HIGH | no | IMPLEMENTED | phi_engine f1–f9, manipulation_detector 7 types, temporal coherence; transduction software-only |
| M-280 | Roadmap L2 — Akashic Index: EVM-genesis bootstrap, archetype clustering (K-means 128-dim), FAISS search, archetype evolution, fork… | D1-135, D2-103 | roadmap | CRITICAL | no | PARTIALLY IMPLEMENTED | 12 archetypes + FAISS + fork_resolution + trajectory_anomaly; genesis bootstrap in progress… |
| M-281 | Roadmap L3 — Mental layer: base transformer on behavioral sequences, Genesis Inference v1, conformal PIs, M(t), OE_factor, M_adj, IM… | D1-136, D2-104 | roadmap | CRITICAL | no | IMPLEMENTED | akashic/mental_transformer (real 2-layer PyTorch + conformal intervals, synthetic-centroid training… |
| M-282 | Roadmap L4 — Spiritual layer: validator node software, BFT with diversity weights, d_j calculator, staking contracts, slashing, HHI… | D1-137 | roadmap | HIGH | no | IMPLEMENTED | validator/ Go BFT (36 tests) + core/spiritual suite; staking contracts minimal (ink stub); no live… |
| M-283 | Roadmap L5 — D1: five-plane coherence + SILENCE + master equation + convergence proof; D2: Living Security (GK, dual-strand, immune… | D1-138 | roadmap | HIGH | no | IMPLEMENTED | coherence+master equation+SILENCE+convergence monitors; living_security 8 components + PQC… |
| M-284 | Roadmap L6 — D1: BC/BRT/BIBL gas intelligence; D2: FIRST TESTNET SIGNAL (three-plane C(t), Θ, Silence, publication contracts, SDK v1). | D1-139, D2-107 | roadmap | CRITICAL | no | PARTIALLY IMPLEMENTED | Testnet signal LIVE on Arb Sepolia (C(t) etched on-chain) — but via 3→5-plane with bootstrap stubs… |
| M-285 | Roadmap L7 — D1: NL + BITP + full 19-signal suite; D2: ANIMA v1 (crawler, NLP 50+ languages, pattern completion, gap monitor… | D1-140, D2-108 | roadmap | HIGH | no | PARTIALLY IMPLEMENTED | NL/BITP engines + 24-signal factory done; ANIMA v1 real but sub-scale (59 languages, 36 sources, no… |
| M-286 | Roadmap L8 — D1: SBA + regulatory adaptation + Chameleon; D2: Conscious layer (annotation 20+ languages, stake-and-challenge, K(t)… | D1-141 | roadmap | MEDIUM | no | PARTIALLY IMPLEMENTED | SBA + Chameleon implemented; conscious plane infra + elders + indigenous DB present; no live… |
| M-287 | Roadmap L9 (D2) — five-plane full: all profiles, all 19 signal types, Protocol Dependency Graph, Negative Space, extended formulas. | D2-110 | roadmap | HIGH | no | PARTIALLY IMPLEMENTED | All planes + 11 profiles + 24 signals + PDG + negative space endpoints; Σ/K/A still… |
| M-288 | Roadmap L10/mainnet (D1-L9 + D2-L10): full validator network, adaptive consensus, BIRP, ZK behavioral proofs, cross-chain continuity… | D1-142, D2-111 | roadmap | HIGH | no | MISSING | MAINNET_RUNBOOK gates: professional audit REQUIRED, 6-month observation-only, ≥100 validators/4… |

### 15. Documentation Claims (8)

| ID | Requirement | Sources | Type | Pri | Contra | Status | Evidence |
|---|---|---|---|---|---|---|---|
| M-289 | Problem framing: >$3B documented DeFi oracle-manipulation losses; behavioral reality cannot be temporarily moved, only lived. | D1-003, D2-001 | architecture | HIGH | no | UNKNOWN | Context claim; scripts/generate_beo_report.py ($3.315B w/ SIMULATED disclosure) |
| M-290 | Seven novel primitives with claim statuses: BCK [NOVEL], semi-immutability [NOVEL], Coordination Collapse [PROVED], behavioral ZK… | D1-077, D1-078, D1-079 | architecture | HIGH | no | PARTIALLY IMPLEMENTED | All seven implemented as modules; novelty/prior-art validation outstanding |
| M-291 | Open research questions tracked: Q1–Q5 (Kolmogorov compression attack, ZK cost, SBA ethics, XSL data, BRT correlation) + OQ-1..8… | D1-129, D3-252, D3-253, D3-254, D3-255, D3-256, D3-257, D3-258 | governance | MEDIUM | no | IMPLEMENTED | core/governance/open_research_questions module; api /falsifiability; OQ list preserved in spec… |
| M-292 | Canonical glossary terminology (Akashic Index, BCK, BEO, MF, NL, TC, Θ, …) used consistently across implementation. | D1-149 | documentation | LOW | no | IMPLEMENTED | Glossary terms map to code identifiers across Py/Rust/TS; spec corpus L0–L9 docs |
| M-293 | Scope claims: directly solves oracle manipulation + market manipulation + wash trading (+ '7 direct solves' vs 10 listed — AN-4)… | D1-146, D1-147, D1-148, D1-145, D1-103 | documentation | MEDIUM | ⚠ YES | UNKNOWN | Doc scope claims; MF detectors + dynamic threshold + BIRP modules support the 'directly solves'… |
| M-294 | Doc2 differentiation/closing claims: reads behavioral history not prices; buildable today with complete math; difficulty is synthesis. | D2-007, D2-174 | documentation | LOW | no | UNKNOWN | Marketing-level; partially supported by repo breadth (1,244 files) and 1,650 passing tests |
| M-295 | Doc3 probability-of-success assessment (26 component rows, 4 overall bands: oracle 85–90%, EVM routing 75–80%, advanced 60–72%, full… | D3-001, D3-002 | roadmap | MEDIUM | no | UNKNOWN | Spec-internal honesty assessment; components cross-checkable against repo (BH exists, C(t) live, ZK… |
| M-296 | Doc3 Appendix-A vs §2 internal discrepancy register + repo identity drift. | D3-294 | documentation | MEDIUM | ⚠ YES | CONTRADICTORY | Doc's April-2026 gap analysis is HISTORICAL: current /home/z/trion-core has implemented essentially… |

---

## Method notes

- Source of truth: the three uploaded PDFs (extracted to upload/extracted/requirements_doc{1,2,3}.md) are the normative requirement set; code is the evidence. 620 source requirements merged to 296 rows (avg 2.09 sources/row); every source ID appears in exactly one row (Task-5 generator validated coverage 620/620, zero orphans/dups).
- Status assigned ONLY from worklog evidence (Tasks 1–4 deep read; Task 3 true test baseline 1650P/113F/28S/1x/3E). This session's ✏️ annotations come from the fix-wave worklog entries (Tasks 7-a…7-f, 8-a…8-c) and name their regression tests; only M-004's status flipped.
- Row grouping here re-sorts the 296 rows into the 15 domains by M-ID (the source file appended M-204/M-205 and M-206 under repeat section headers; the row set is identical — verified: 296 rows, IDs M-001..M-296).
- Caveat inherited from the source matrix: statuses are evidence-based guesses from the deep read, not a re-audit; spot-verification of any row should go to the cited repo paths first.
