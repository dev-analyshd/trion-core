# TRION + BTCP — Canonical Specification Matrix

> **Wave 1, Agent A (specification architect).** Single source of truth for every
> normative requirement extracted from the authoritative specification set. This
> document is the CONTRACT subsequent waves implement and audit against.
>
> Compiled at HEAD f91a19b (Wave 1 open) from a full line-by-line read of every
> authoritative source (spec/WHITEPAPER_MD.txt, spec/WHITEPAPER_V2.txt,
> spec/BTCP_SPEC.txt, spec/L0–L9 *.md, spec/signal_types.md, spec/novel_primitives.md,
> spec/falsifiability_registry.md, spec/communication_channels.md; spec/DD_REPORT.txt
> used as audit input only) cross-referenced against the implementation tree
> (core/, api/, anima-service/, rust/, validator/, contracts/, adapters/, akashic/,
> zg/, indexers/, sdk/, zk/, zk-circuits/, relayer/).

## Specification hierarchy (fixed at freeze)

1. **spec/WHITEPAPER_MD.txt** (Feb 2026, updated Mar 2026) — canonical protocol
   semantics. **Wins semantic conflicts.** Cited as **MD**.
2. **spec/WHITEPAPER_V2.txt** (Feb 2026) — complete implementation spec. **Wins
   where MD is silent.** Cited as **V2**.
3. **spec/BTCP_SPEC.txt** (Apr 2026) — governs BTCP absolutely. Cited as **BTCP**.
4. **spec/L0–L9 *.md + signal_types.md + novel_primitives.md +
   falsifiability_registry.md + communication_channels.md** — authoritative in
   their domains, subordinate to 1–3 where they conflict (see §Conflicts; several
   of these are older per-layer drafts whose formulas predate the freeze).
5. **spec/DD_REPORT.txt** — audit input; never a spec.

## How to read this matrix

Every requirement below carries ALL TWELVE mandatory columns:
`requirement | source | specification section | mathematical definition |
canonical data structure | canonical implementation | all implementations |
current compliance | deviations | security impact | required remediation |
verification method`.

Compliance ratings (per the no-fake-production rule — a research/stub component
must be labeled honestly, and every rating below reflects what the code itself
claims about its production-readiness, not what marketing claims):

| Rating | Meaning |
|---|---|
| COMPLIANT | Implemented per spec, tested, honestly represented |
| PARTIAL | Implemented with spec-visible gaps (fields, tiers, or persistence missing) |
| DEVIANT | Implemented, but semantics differ from the canonical spec resolution |
| MISSING | Required by spec, absent from code |
| RESEARCH-ONLY | Exists as research/simulation/bootstrap component; code itself discloses non-production status |

File paths are repo-relative. Test names are the concrete proof artifacts that
exist today, or the test that MUST be created (marked **MUST-CREATE**).

---

## Canonical terminology

| Term | Canonical one-line definition | Defined in |
|---|---|---|
| **BH** (Behavioral Hash) | Dual-strand SHA3-256 hash over the 93-byte canonical behavioral payload; the foundational atom of the whole system | V2 L0.1 (p.6); MD L0.1 §4 |
| **Hash_DNA** | keccak256-based 14-field BTCP-layer hash (domain-separated, 18-decimal magnitude) used for route proofs, intent and BLO commitments | MD L0.1 §4 (formula); BTCP §17 formula index |
| **sense / antisense** | The two self-verifying BH strands: `sense = SHA3-256(payload ∥ 0x00)`, `antisense = SHA3-256(payload ∥ 0xFF) XOR complement_transform(sense)`; tamper with either breaks complementarity | MD L0.1; V2 L0.1 |
| **BEO** (Behavioral Entity Object) | The resolved multi-wallet economic actor; `BEO_confidence` over CF/ST/SC/BP (+GX) evidence channels, valid > 0.75; `entity_id` in every BH is the BEO id, not a raw address | MD L0.2; V2 L0.2 |
| **Akashic Index** | The append-only permanent behavioral database storing every BH ever generated; foundation of depth D(t) and the moat | MD §6; V2 Level 2 |
| **BIBL** (Behavioral Inter-Block Layer) | Active behavioral intelligence in the inter-block window (12s on Ethereum): reads mempool/BRT/ANIMA/archetypes and emits user guidance + Chain Memory Instruction Signal | MD §18; BTCP §4.2 Step 1 |
| **BITP** (Behavioral Intent Transfer Protocol — illiquid pairs) | CUT/MATCH/PASTE mechanism that moves behavioral commitments instead of assets: complementary intents matched cross-chain, both assets settle natively | BTCP §5.1 |
| **BITP matching score** | `price_efficiency×0.40 + behavioral_trust×0.30 + fill_completeness×0.20 + time_priority×0.10` | MD L7.2 |
| **BLO** (Behavioral Limit Order) | An unmatched intent persisted in the Akashic clipboard with expiry, partial fill, and behavioral ranking of bidders | BTCP §5.5 |
| **IAP** (Intent Aggregation Protocol) | Pools ≥3 same-direction intents into one execution; gas shared `G_per_entity = G_total × (value/total)`; ZK share proof planned | BTCP §5.3 |
| **OOA** (Observation-Only Anchoring) | Channel-6 permissionless indexing of non-integrated chains; confidence `conf_max·(1−e^(−k·depth))` approaching but never reaching integration | BTCP §5.2 |
| **OOA (intent object)** | Also the router's adapter for unknown chains — routed to the OOA adapter per BTCP §5.2 rather than defaulting to EVM | BTCP §5.2 (repo usage) |
| **AWA** | **Anti-Weaponization Architecture** (canonical, MD §17): signal emission FROZEN unless all six anti-weaponization conditions hold. Repo code labels it "Adaptive Watchdog Architecture" — naming deviation, see conflicts | MD §17; V2 §14.2 |
| **DW-BFT** (Diversity-Weighted BFT) | BFT consensus where effective power is `s_j·d_j`; Byzantine coordination drives `corr(M_j, M̄)→1` hence `d_j→0` — the Coordination Collapse Theorem | MD L4.1; V2 L4.1; BTCP §12.2 |
| **HHI** | Herfindahl–Hirschman index over **effective** (stake×diversity) validator power, ×10 000 scale, with 1500/2500/4000 enforcement tiers plus geographic constraints | MD L4.1; V2 L4.8 |
| **d_j** | Diversity weight `d_j = 1 − corr(M_j, M̄)`; the multiplicative penalty on coordinated validators | MD L4.1; V2 L4.1 |
| **Θ (Θ(t))** | Dynamic coherence threshold `Θ(t) = Θ_min + (Θ_max−Θ_min)·V(t)` with Θ_min=0.55, Θ_max=0.92 | MD §3/L5.2; V2 L5.1 |
| **Σ** | The Spiritual plane: diversity-weighted validator consensus score `Σ(t) = Σ_j[s_j·d_j·𝟙(|v_j−v̄|≤δ(t))]/Σ_j[s_j·d_j]` | V2 L4.1; MD L4.1 |
| **T(t)** | Master equation output: `T(t) = [C(t)≥Θ(t)]·S(t)·e^(M_moat·t)` — 0 ⇒ structured SILENCE, else signal strength compounded by the moat | MD §3; V2 L5.4 |
| **Moat (M_moat)** | Compounding security/value factor `M_moat(t) = D·Q·R·X·F·N` (depth, quality, regulatory record, cross-chain, falsifiability, network) | V2 §2.3 (MD silent → V2 wins) |
| **Archetypes** | The append-only library of behavioral feature vectors (128-dim per MD/V2) against which new assets are matched for Genesis Inference | MD L2.2; V2 L2.2 |
| **Dormancy / Resurrection** | Five dormancy types (ABANDONED κ=0.008, HIBERNATION 0.003, MIGRATION 0.000, REGULATORY_PAUSE 0.001, EXPLOIT_RECOVERY 0.005) with `Δ_resurrection` decay and GENUINE/NEW_ENTITY_OLD_SHELL/HOSTILE/ZOMBIE classification | V2 L2.4 / §7.2; BTCP §11 Fix 2 |
| **BIRP** | Behavioral Identity Recovery Protocol — identity recovery from behavioral proof (DNA_Code + Akashic BEO baseline, 5 phases, 7-day quarantine) | MD §16; novel_primitives.md P6 |
| **BCK** | Behavioral Causal Key — key material whose security is ontological (causal history reproduction), not computational | MD L4.3 / §13 P1; novel_primitives.md P2 |
| **BRT** | Biological Rhythm Timer — circadian/ultradian/lunar/seasonal phases carried in every signal's `biological_time` | MD L6.2; V2 L6.2 |
| **NL** | Natural Liquidity score `NL = LD·LO·LC·LS`; `NL < 0.30` ⇒ LIQUIDITY_HEALTH signal | MD L7.1; V2 L7.1 |
| **BTCP** | Behavioral Transaction Continuity Protocol — the cross-chain behavioral information-flow system (intents, not transactions) | BTCP title/§3 |
| **BTCP_score** | `[0.25·NL + 0.20·normalize_gas + 0.20·finality_conf + 0.15·CC_coherence + 0.20·BEO_continuity]·(1−MF_score)` — the core routing signal | MD L1.1; BTCP §4.2 Step 2 |
| **MF_score** | Manipulation fingerprint aggregate `min(1.0, max(active type contributions))` over the 7 fingerprint types | V2 L1.2 |
| **SILENCE** | Structured null signal carrying `coherence_gap, limiting_plane, coherence_trend (RISING\|FALLING), eta` | MD §11; V2 L5.4 |
| **CI_95** | The 95% confidence interval — present in every TRIONSignal, never null | MD §2/§11; V2 Part 5 |
| **V(t)** | Market volatility index normalized to [0,1] driving Θ(t) | MD §3 |
| **C(t)** | Five-plane coherence `C(t) = α·Φ_adj + β·M_adj + γ·Σ + δ·K + ε·A`, weights sum 1 | MD L5.2; V2 L5.2 |

---

## Conflicting / obsolete specification fragments

Every internal contradiction found in the authoritative sources, with the chosen
canonical resolution (per the fixed hierarchy: MD wins semantics, V2 wins
implementation detail where MD is silent, BTCP_SPEC governs BTCP, layer .md files
are subordinate to all three).

| # | Conflict | Fragments | Canonical resolution |
|---|---|---|---|
| K1 | **Two different "Behavioral Hash" constructions.** MD L0.1 defines a 14-field keccak-style `Hash_DNA` with `DOMAIN_SEPARATOR`, currency id, counterparty, protocol, context hash, btcp_version, nonce and magnitude `raw×10^(18−decimals)`. V2 L0.1 defines a 7-field payload (`entity_id ∥ event_type ∥ magnitude_normalized ∥ context ∥ timestamp ∥ chain_id ∥ block_hash`, log10 USD magnitude) with SHA3-256 dual-strand output. | MD L0.1 vs V2 L0.1 | **Both are canonical, at different layers**: the V2 93-byte dual-strand construction is the L0 *stream* hash (implemented byte-identically in Rust/Python/TS, DD-verified — the repo's one portable asset); the MD 14-field `Hash_DNA` is the *BTCP-layer commitment* hash (implemented as `core/primitives/hash_dna.py`, keccak256). `core/primitives/behavioral_hash.py` and `rust/indexers/crates/trion-common` implement the former; `hash_dna.py` the latter. Remediation: state this two-primitive split explicitly in spec (see R-BH-01). |
| K2 | **93-byte payload layout disagreement.** `spec/L0_universal_primitives.md` L0.1 defines a 93-byte payload as `strand_A(32) ∥ strand_B(32) ∥ meta(16) ∥ beo_id(9) ∥ crc32(4)` — an *output*-shaped layout with CRC and 9-byte beo. The implemented (and V2-shaped) 93 bytes are the *preimage*: `entity_id(32) ∥ event_type(1) ∥ magnitude(8) ∥ context(8) ∥ timestamp(8) ∥ chain_id(4) ∥ block_hash(32)`. | L0.md L0.1 vs V2 L0.1 + implementation | **V2 layout is canonical** (MD is silent on byte layout; V2 fills it; tri-language golden vectors pin it). L0.md's layout is an obsolete draft — it must not be treated as the 93-byte BH contract. Remediation: rewrite L0.md L0.1 to the implemented layout or delete the file (W4/R scope). |
| K3 | **Magnitude normalization.** MD: `raw_amount × 10^(18−asset_decimals)` (18-dec fixed point). V2: `log10(USD+1)/log10(max90d+1) ∈ [0,1]`. | MD L0.1 vs V2 L0.1 | **Split by primitive** (follows K1): 93-byte BH uses the V2 log10 form (MD is implementation-silent); BTCP Hash_DNA uses the MD 18-decimal form. Both implemented exactly this way (`behavioral_hash.py::normalize_magnitude` vs `hash_dna.py`). Record in spec. |
| K4 | **Signal type count and set.** MD §11 lists 19; V2 Part 5 lists a *different* 19 (swaps SOVEREIGN_BEHAVIORAL/ENERGY_PARTICIPATION/BIOLOGICAL_CAPITAL/BTCP_ROUTE/CONSENSUS_ADAPTATION for RESURRECTION/NEGATIVE_SPACE/INSTITUTIONAL_BHV/ECOSYSTEM_HEALTH/BOOTSTRAP); `spec/signal_types.md` declares "exactly 24"; BTCP §14.2 adds 10 more names. | MD §11 vs V2 Part 5 vs signal_types.md vs BTCP §14.2 | **Canonical 19 = MD's list** (MD wins semantics). The 5 V2-only types are retained as *extended* types (V2 authoritative where MD silent) → total 24, which is exactly what `core/master/signal_factory.py` implements and `signal_types.md` enumerates. BTCP §14.2's extra 10 (SHADOW_CHAIN, LIQUIDITY_OCEAN, CHAIN_RELIABILITY, BTCP_ESCROW_EVENT, BTCP_TIMEOUT, GENESIS_COMMITMENT, BEHAVIORAL_TRUTH…) are BTCP-domain additions, currently unimplemented in the signal registry. |
| K5 | **"BTCP" acronym expansion.** `signal_types.md` S23 expands BTCP as "Behavioral Trusted Channel Protocol"; everywhere else it is "Behavioral Transaction Continuity Protocol". | signal_types.md S23 vs BTCP title/§3 | **Behavioral Transaction Continuity Protocol** (BTCP_SPEC governs). signal_types.md S23 wording is an error; fix in W4. |
| K6 | **"BIBL" name collision.** MD §18: Behavioral **Inter-Block** Layer (inter-block intelligence window). `novel_primitives.md` P5: BIBL = "Behavioral **Inheritance and Biological Ledger**" (fork-inheritance protocol with opt-in BEO inheritance). | MD §18 vs novel_primitives.md P5 | **MD wins**: BIBL = inter-block layer. The P5 fork-inheritance concept is real but must be **renamed** (e.g. "Behavioral Ledger Inheritance, BLI"); `core/akashic/bibl.py` implements the MD inter-block cycle (Chain Memory Instruction Signal, GasPreferenceProfile); `core/btcp/bibl_engine.py` implements the per-chain BIBL analysis feed. No code implements P5 inheritance. |
| K7 | **Σ and K plane definitions.** `spec/L5_trion_master.md` L5.2 defines Σ as the *akashic* plane (L2.5 convergence) and K as the *knowledge/cross-chain* plane (L9); MD/V2 define Σ = diversity-weighted validator consensus, K = human annotation (Conscious). | L5.md L5.2 vs MD §8/§9, V2 §2.2 | **MD wins**: Σ = validator consensus, K = Conscious human plane, A = ANIMA, Φ = physical, M = mental. Implementation follows MD (`core/spiritual/sigma_engine.py`, `core/spiritual/conscious/`). L5.md is an obsolete draft. |
| K8 | **Genesis confidence direction.** V2 L2.3: `conf_genesis(t) = 1 − e^(−λ·D_asset)` — confidence GROWS with accumulated depth. `spec/L2_akashic_index.md` L2.3: `GC(t) = GC_0·e^(−μ(t−t_genesis))` — confidence DECAYS. | V2 L2.3 vs L2.md L2.3 | **V2 wins** (MD silent; implementation `core/akashic/genesis.py` uses the growing form with archetype-matched λ). L2.md's decay form describes a different quantity (novelty decay) and is non-canonical. |
| K9 | **Akashic depth decay vs conservation.** MD L0.4/L9.2: information is conserved, the Akashic Index is append-only, never destroyed. `spec/L2_akashic_index.md` L2.1: D(t) has exponential decay (λ=0.01/epoch), "fossilized" BEOs pruned. | MD L0.4/L9.2 vs L2.md L2.1 | **MD wins**: append-only, monotone accumulation (V2 L2.1 integral). Implementation (`core/akashic/depth.py`, `core/master/d_engine.py`, `akashic/timescale_store.py`) is append-only. L2.md's decay is non-canonical. |
| K10 | **BEO threshold and factor count.** V2 L0.2/MD L0.2: 4 factors, >0.75. L0.md L0.2: 0.85/0.50/0.5 three-band thresholds, plus a July-2026 audit note declaring production = 5 factors (GX 0.10) at 0.75. | V2 L0.2 vs L0.md L0.2 (with embedded audit note) | **Production = 5 factors at 0.75** (the L0.md audit note is itself the recorded resolution: code wins, `anima-service/faiss_service.py` + `core/primitives/entity_resolution.py` GX path). MD's 4-factor formula is the reference model; both are implemented side-by-side in `entity_resolution.py`. Record: L0.md body thresholds (0.85/0.50) are non-canonical. |
| K11 | **HHI scale and scope.** MD L4.1/V2 L4.8: HHI over effective stake ×10 000 with 1500/2500/4000 tiers + geographic rules. L4.md L4.8: HHI_geo/HHI_infra on 0–1 scale with 0.15/0.25 and 0.10/0.18 thresholds. | MD/V2 vs L4.md | **MD/V2 ×10 000 form canonical** (implemented `core/spiritual/hhi_monitor.py`, Go mesh). L4.md's per-jurisdiction/infra HHI is a useful *supplement* (infra-concentration is otherwise unspecified) — keep as engineering extension, document as such. |
| K12 | **Slashing registries.** V2 L4.9: 5 conditions (COORDINATED_ATTACK 50%, LOW_ACCURACY 3%/30d, HSM 10%, UPTIME 0.1%/day, SYBIL_CLUSTER 25%) + 72h dispute with 3 validators + 1 human council. L4.md L4.9: 6 conditions S1–S6 (double-signing 100%, liveness 5%, diversity fraud 50%, genome 30%, geo misreport 20%, manipulation 100%). TRIONStaking.vy: "7-type schedule". | V2 L4.9 vs L4.md L4.9 vs contracts | **V2 L4.9 canonical** (implemented in `core/spiritual/slashing.py` + `core/governance/slashing.py` dispute flow + Go `validator/internal/consensus/slashing.go` evidence-based double-signing). L4.md S1–S6 must be merged into one registry (double-signing 100% is already the Go/Tendermint rule; TRIONStaking.vy's "7-type" comment needs the table). Remediation in W4. |
| K13 | **Falsifiability numbering.** MD §20 and V2 Part 13 share F1–F15 (manipulation resistance, contradictory signals, CI calibration, LSS breach, convergence, genesis, IM 24h, HHI, geography, SILENCE eta, OE, AWA, FP<2%, BRT, regulatory). `spec/falsifiability_registry.md` defines a COMPLETELY DIFFERENT F1–F15 (BH collision rate, BEO monotonicity, resonance AUC, …). `core/governance/falsifiability_registry.py` implements the **MD/V2** set. | MD §20/V2 Part 13 vs falsifiability_registry.md | **MD/V2 F1–F15 canonical.** The registry .md's per-layer conditions are valuable *operational monitors* — renumber them (e.g. R-F1…R-F15) to remove the collision. Implemented file already follows MD/V2. |
| K14 | **20-channel taxonomy.** MD §15 (cosmological, ecological, HSM, thermodynamic, entropy-budget, chain indexing, BEO inference, CRISPR interception, resonance, FAISS vectors, genomic key, self-verifying strands, immune memory, ANIMA absorption, CRED weight, d_j validator channel, Go mesh, type system, epigenetic, proof). `communication_channels.md`: a different 20 (Physical Ledger, Environmental Telemetry, Entropy Budget, Resonance, State Query, Event Subscription, Mempool, Simulation, Bridge Message, Akashic Sync, Oracle, Indexer, Governance, Attestation, ZK, Formal Verification, Behavioral Transfer, Semantic Translation, Compliance, Enforcement). | MD §15 vs communication_channels.md | **MD §15 canonical** (implemented `core/master/channel_architecture.py`, layer names match MD incl. "LAYER 4 — CRYPTOGRAPHIC LIVING CHANNELS"). communication_channels.md's taxonomy is an engineering transport map — keep as supplementary transport spec, not the channel registry. |
| K15 | **AWA expansion and condition set.** MD §17: AWA = **Anti-Weaponization Architecture**, enforced iff 6 conditions (no single entity controls signal weights / validator selection, Public Good ≥15%, SDP active, Right to Invisibility, Gratitude ≥1). `core/governance/awa.py`: "Adaptive Watchdog Architecture", 8 conditions (quorum ≥2/3, HHI<4000, gratitude, public good + 4 anti-centralization). | MD §17 vs V2 §14.2 vs implementation | **MD §17 condition set canonical**; V2 §14.2 matches it. The code's 8-condition superset is an engineering strengthening (quorum/HHI in addition) — keep, but rename the docstring to Anti-Weaponization Architecture and map each of the 6 canonical conditions explicitly (Sovereignty_Dignity_Protocol_active and Right_to_Invisibility_enforced are not currently encoded as named checks). |
| K16 | **Moat decomposition.** V2 §2.3: `M_moat = D·Q·R·X·F·N` (six multiplicative factors). L5.md L5.4: M_moat = "cumulative distinct archetypes indexed", capped 0.02/epoch. | V2 §2.3 vs L5.md L5.4 | **V2 wins** (MD silent). Implementation `core/master/moat.py` = six-factor form. L5.md's archetype-count moat is non-canonical (its 0.02 cap does appear as a numerical guard nowhere — see R-ME-05). |
| K17 | **Θ_max value.** L5.md notes a correction "0.90 → 0.92 per July 2026 audit" to match `core/master/coherence.py::THETA_MAX`; MD/V2 both say 0.92. | resolved | No open conflict — Θ_max = **0.92** everywhere now. |
| K18 | **BTCP score weight provenance.** BTCP §4.2 Step 2 code comment uses `GAS_99TH_PERCENTILE` normalization identical to MD L1.1; both agree on weights 0.25/0.20/0.20/0.15/0.20 ×(1−MF). MD §18 restates as a product `NL × (1/gas) × finality × CC × BEO`. | MD §18 vs MD L1.1/BTCP §4.2 | **Weighted-sum form (L1.1/BTCP §4.2) canonical** — implemented in `rust/src/btcp_router.rs::btcp_score` and `core/master/btcp_score.py`. MD §18's product restatement is narrative, not the formula of record. |
| K19 | **Φ plane feature set.** V2 L1.1 defines 9 EVM features f1–f9 (volume entropy, counterparty diversity, …). `spec/L1_physical_layer.md` defines a DIFFERENT 9 (price ticks, volume profile, order book, gas price, inter-arrival, actor clusters, oracle updates, governance, cross-chain) and calls the aggregate PR_scalar. | V2 L1.1 vs L1.md L1.1 | **V2 L1.1 canonical** for Φ; L1.md's feature set is the per-indexer entropy feature set that the Rust indexers actually compute (DD: "9 Shannon entropy features"). Both live in code: `core/physical/phi_engine.py` (V2 set) and `rust/indexers/crates/*/features` (L1.md set). Record the split in spec; unify naming in W4. |
| K20 | **Resonance communication.** MD L0.3: `Comm(A,B) iff ∃f: RF(A,f)>0 ∧ RF(B,f)>0` (shared behavioral event type = shared frequency). L0.md L0.3: resonance coefficient `R(X,Y) = 1/(1+dist(BH_X,BH_Y))·cos(phaseX−phaseY)` with 4 channel tiers. | MD L0.3 vs L0.md L0.3 | **MD wins** for the communication semantics; L0.md's R(X,Y) is an implemented *supplementary* metric (`core/primitives/resonance.py`), spec-silent engineering extension — document or remove. |
| K21 | **C(t) input for Φ.** L5.md says Φ = PR_scalar (L1.md features); L7.md says P1 Currency profile uses `LH_composite = sqrt(NL·EP)` as Φ. | L5.md vs L7.md vs MD | **MD/V2 win**: Φ = physical behavioral entropy (V2 f1–f9). The LH_composite→Φ substitution is non-canonical engineering guidance; not implemented as such. |
| K22 | **"Extended payload".** `spec/L0_universal_primitives.md` beo_id is 9 bytes; the canonical BH uses a 32-byte BEO id. `core/primitives/extended_payload.py` exists for a longer event encoding. | L0.md vs V2/MD | 32-byte entity_id canonical (V2 L0.2: "entity_id in BH = BEO identifier"; BTCP §4.1: bytes32). The 9-byte beo in L0.md is obsolete. |

---

## Domain 1 — TRION master equation T(t)

Canonical semantics: MD §3 (updated Mar 2026); implementation detail: V2 §2.1, §2.2,
§2.3, Part 4 Level 5; L5 semantics per MD (see conflict K7).

#### R-ME-01 — Master equation evaluation
- **requirement**: Emit `T(t) = [C(t) ≥ Θ(t)] · S(t) · e^(M_moat·t)`; indicator 0 ⇒ structured SILENCE, 1 ⇒ signal amplified by the compounding moat.
- **source**: MD §3; V2 §2.1/L5.4.
- **specification section**: MD "THE MASTER EQUATION"; V2 L5.4.
- **mathematical definition**: `T(t) = 𝟙[C(t)≥Θ(t)] · S(t) · e^(M_moat(t)·t)`, moat exponent clamped for numerical stability (code adds MAX_MOAT_EXPONENT=36).
- **canonical data structure**: `MasterEquationResult{t, c, theta, emits, moat_factor, margin, limiting_plane, trend, signal_value, time_years, silence_reason}`.
- **canonical implementation**: `core/master/master_equation.py::MasterEquation.compute`.
- **all implementations**: `core/master/master_equation.py`; `rust/src/master_equation.rs`; `api/app.py::_compute_signal` (composed); `core/master/signal_factory.py` (consumes); `tests/master_formula_verification.py`.
- **current compliance**: **COMPLIANT** (formula exact; S(t) falls back to C(t) when no separate signal value — documented in code).
- **deviations**: Moat exponent clamp (engineering guard, spec-silent); S(t)=C(t) fallback is spec-permissible but under-specifies S(t) provenance.
- **security impact**: Low (clamp prevents overflow; fallback documented).
- **required remediation**: Document the clamp and the S(t) fallback rule in the spec's formula index.
- **verification method**: `tests/master_formula_verification.py` (exact-value tests incl. L5.4); `tests/unit/trion_protocol/test_five_plane_c.py`.

#### R-ME-02 — Five-plane coherence C(t)
- **requirement**: `C(t) = α·Φ_adj + β·M_adj + γ·Σ + δ·K + ε·A` with α+β+γ+δ+ε=1.
- **source**: MD §3/§9 L5.2; V2 §2.2/L5.2.
- **specification section**: MD L5.2; V2 L5.2.
- **mathematical definition**: Weighted sum of the five adjusted plane scores; Φ_adj = Φ·(1−MF_score); M_adj = M·(1−OE_factor).
- **canonical data structure**: `CoherenceInput{phi_adj, m_adj, sigma, k_plane, anima, volatility, akashic_depth, moat_time, profile}` → result dict with `C, theta, margin, emits, limiting_plane, plane_breakdown`.
- **canonical implementation**: `core/master/coherence.py::CoherenceEngine.compute_coherence`.
- **all implementations**: `core/master/coherence.py`; `core/planes/seven_plane_coherence.py` (7-plane variant, see R-LS-08); `core/master/master_equation.py`; `rust/src/master_equation.rs`; `api/app.py::_plane_values` (live plane assembly); `tests/master_formula_verification.py`; `tests/unit/trion_protocol/test_five_plane_c.py`; `tests/unit/test_all_planes.py`.
- **current compliance**: **COMPLIANT** for the arithmetic; **PARTIAL** for live wiring (per DD §5.3 and the BTCP spec's own stub disclosure, Σ/K/A planes come from the FAISS/Go services and are bootstrap-grade in the absence of a live validator fleet; `core/spiritual/consensus.py` discloses BOOTSTRAP MODE).
- **deviations**: None in formula. Bootstrap provenance of Σ/K/A inputs is disclosed in code but must stay disclosed (see R-VC-04).
- **security impact**: High — C(t) is the emission gate for every signal and the escrow release input; a fake plane score publishes false truth.
- **required remediation**: Keep the bootstrap-plane disclosure pinned in every consumer; add plane-provenance fields to the API response (partially present: `bootstrap_planes` flags in coherence result).
- **verification method**: `tests/master_formula_verification.py`; `tests/unit/test_all_planes.py`; `tests/unit/trion_protocol/test_five_plane_c.py`.

#### R-ME-03 — Weight profiles (asset-type + query-mode)
- **requirement**: Named weight profiles: DEFAULT(0.25/0.30/0.25/0.10/0.10), SPEED, INTELLIGENCE, CERTAINTY, FULL_SPECTRUM (V2 §2.2) and asset-type profiles NEW_TOKEN, MATURE_PROTOCOL, STABLECOIN, GOVERNANCE_TOKEN, BRIDGE_ASSET, WRAPPED_ASSET (V2 L5.2).
- **source**: V2 §2.2 + L5.2 (MD silent on profiles → V2 wins).
- **specification section**: V2 "Five-Plane Coherence — Weight Profiles", L5.2 "Asset-Type Profiles".
- **mathematical definition**: Per-profile (α,β,γ,δ,ε), all summing to 1.
- **canonical data structure**: `AssetProfile` enum + `WEIGHT_PROFILES` dict.
- **canonical implementation**: `core/master/coherence.py::WEIGHT_PROFILES`.
- **all implementations**: `core/master/coherence.py`; `tests/master_formula_verification.py` (profile weight assertions); L5.md's 6 profiles (P1 Currency … P6 Biological) are a *different, non-canonical* set (conflict: L5.md L5.2).
- **current compliance**: **COMPLIANT** for the V2 sets (all 11 profiles present with spec values).
- **deviations**: L5.md's P1–P6 profiles are unimplemented and non-canonical (see conflicts K7/K21).
- **security impact**: Low.
- **required remediation**: Mark L5.md profiles as superseded in W4 docs pass.
- **verification method**: `tests/master_formula_verification.py` (weight-profile table tests); **MUST-CREATE**: a test asserting every V2 profile value exactly (partially covered by master formula suite).

#### R-ME-04 — Dynamic threshold Θ(t)
- **requirement**: `Θ(t) = Θ_min + (Θ_max−Θ_min)·V(t)` with Θ_min=0.55, Θ_max=0.92; V(t)∈[0,1].
- **source**: MD §3/L5.2; V2 L5.1.
- **specification section**: MD §3; V2 L5.1.
- **mathematical definition**: Linear interpolation between 0.55 and 0.92 by market volatility.
- **canonical data structure**: `THETA_MIN/THETA_MAX` constants; `compute_threshold(volatility)`.
- **canonical implementation**: `core/master/coherence.py::CoherenceEngine.compute_threshold`.
- **all implementations**: `core/master/coherence.py`; `core/master/master_equation.py` (consumes); `contracts/solidity/TRIONOracleV3.sol` (threshold carried on-chain, ×1e6); `contracts/solidity/BTCPEscrow.sol` (coherence ≥ threshold gate).
- **current compliance**: **COMPLIANT** (0.55/0.92 exact; L5.md's 0.90 correction was already applied — conflict K17 resolved).
- **deviations**: None.
- **security impact**: Medium — threshold too low ⇒ signals under uncertainty; too high ⇒ silence storms.
- **required remediation**: None.
- **verification method**: `tests/master_formula_verification.py` (L5.Θ tests: 0.55/0.92 endpoints, monotonicity).

#### R-ME-05 — Moat M_moat(t)
- **requirement**: `M_moat(t) = D(t)·Q(t)·R(t)·X(t)·F(t)·N(t)` — six multiplicative factors (Akashic depth, signal quality, regulatory record, cross-chain breadth, falsifiability survived, network effects).
- **source**: V2 §2.3 (MD silent on decomposition → V2 wins).
- **specification section**: V2 2.3 "The Moat — Why It Compounds".
- **mathematical definition**: Product of the six factors; each grows independently with time.
- **canonical data structure**: `MoatInput` → `moat_result{moat_factor, components}`.
- **canonical implementation**: `core/master/moat.py::MoatEngine.compute`.
- **all implementations**: `core/master/moat.py`; `core/master/coherence.py` (delegates); `core/master/d_engine.py` (block-level D accumulation feeding M).
- **current compliance**: **PARTIAL** — Q uses validator conscious-plane score (not the spec's "rolling accuracy record" directly), R is an OE-stability proxy, N is a τ-saturating growth curve (engineering instantiation, spec gives no closed forms). All factors present and multiplicative.
- **deviations**: Factor instantiations are engineering choices (spec-silent on formulas); L5.md's archetype-count moat is non-canonical (K16).
- **security impact**: Low (moat affects amplification only, not emission).
- **required remediation**: Document the chosen closed forms for Q/R/X/F/N in the spec or a canonical doc.
- **verification method**: `tests/master_formula_verification.py` (moat factor tests); **MUST-CREATE**: factor-boundary tests (each factor → 0 kills the moat).

#### R-ME-06 — Convergence theorem
- **requirement**: `lim_{D(t)→∞} E[|T(t) − V_true|] = H_irreducible` (cannot go lower — physics; cannot stay higher — statistical consistency).
- **source**: MD §3 ("Convergence theorem [PROVED]"); V2 L2.5/Part 13 Proof 4.
- **specification section**: MD §3; V2 Proof 4.
- **mathematical definition**: Expectation of absolute error converges to the quantum uncertainty floor as depth grows.
- **canonical data structure**: n/a (theorem + falsification condition F5).
- **canonical implementation**: Theorem is asserted, not computed. Empirical monitor exists as part of `core/governance/falsifiability_registry.py` F5 bookkeeping.
- **all implementations**: `core/governance/falsifiability_registry.py` (F5 entry); no runtime convergence tracker.
- **current compliance**: **RESEARCH-ONLY** (proof stated in spec; no machine-checked proof — DD §4.2 confirms "575 LOC GADT modeling + boolean self-checks; not machine-checked" in `formal/`).
- **deviations**: None in code (nothing to deviate).
- **security impact**: Low direct; high reputational (a false convergence claim is F5-falsifiable).
- **required remediation**: Keep the F5 monitor wired to realized-vs-emitted divergence stats when live history exists.
- **verification method**: `formal/` (Haskell models, self-described as not machine-checked — keep that labeling); **MUST-CREATE**: rolling F5 divergence report.

#### R-ME-07 — Consensus degradation tiers
- **requirement**: Tier 1 (0.5Θ ≤ C < Θ): STALE_SCORE flag, last confirmed BIBL snapshot used (max 50 blocks), new routes suspended, in-flight complete. Tier 2 (C < 0.5Θ): all new routes suspended, Emergency Escape unaffected. GUARANTEE: entity funds never at risk.
- **source**: MD L5.3; V2 (silent on 50-block snapshot → MD wins).
- **specification section**: MD L5.3 "Consensus Degradation Tiers".
- **mathematical definition**: Two-tier degradation policy on C/Θ ratio.
- **canonical data structure**: Tier enum + route-suspension state.
- **canonical implementation**: `core/master/degradation.py` (tier classification); `core/spiritual/consensus_degradation.py`.
- **all implementations**: `core/master/degradation.py`; `core/spiritual/consensus_degradation.py`; `core/btcp/orchestrator.py` (in-flight route completion semantics); Go `validator/internal/consensus` (liveness, not tiers).
- **current compliance**: **PARTIAL** — tier classification exists; the "last confirmed BIBL snapshot (max 50 blocks)" fallback is not implemented as a persisted snapshot; route suspension on degradation is not wired into the live orchestrator gate.
- **deviations**: 50-block BIBL snapshot cache MISSING.
- **security impact**: High — during degradation, executing new routes on stale coherence is exactly the failure mode the tier exists to prevent.
- **required remediation**: Wire degradation tier into `BTCPOrchestrator.create_route` (refuse new routes at Tier 1+), and persist a rolling last-confirmed BIBL snapshot with 50-block bound.
- **verification method**: **MUST-CREATE**: `tests/btcp/test_degradation_gate.py` (orchestrator refuses new intents when C<Θ; in-flight complete).

---

## Domain 2 — Behavioral Hash (BH)

Canonical semantics: MD L0.1 §4 + Appendix B; V2 L0.1; BTCP §17 formula index;
L0.md is subordinate (conflicts K1–K3, K22).

#### R-BH-01 — Canonical 93-byte dual-strand BH
- **requirement**: Every behavioral observation reduces to the fixed 93-byte canonical payload, hashed dual-strand: `sense = SHA3-256(payload ∥ 0x00)`, `antisense = SHA3-256(payload ∥ 0xFF) XOR complement_transform(sense)`; verification `sense XOR antisense == expected_complement`; collision probability < 2^-128.
- **source**: V2 L0.1 (byte layout — MD silent); MD L0.1 (dual-strand semantics).
- **specification section**: V2 "L0.1 — The Behavioral Hash"; MD L0.1 "Dual-Strand Verification".
- **mathematical definition**: Payload `entity_id(32) ∥ event_type(1) ∥ magnitude_normalized(8, nano-units) ∥ context(8) ∥ timestamp(8) ∥ chain_id(4) ∥ block_hash(32)` = 93 bytes; strands as above.
- **canonical data structure**: `BehavioralEvent` dataclass; result dict `{sense_hex, antisense_hex, valid, magnitude_normalized, event_type, context_hex, chain_id, block_number, timestamp, payload_len}`.
- **canonical implementation**: `core/primitives/behavioral_hash.py::compute_behavioral_hash` (Python), `rust/indexers/crates/trion-common::canonical_bh` (Rust), `sdk/src` (TS pack/unpack).
- **all implementations**: `core/primitives/behavioral_hash.py`; `rust/indexers/crates/trion-common/src/*` (canonical BH + hash_dna); `core/realtime/bh_streamer.py` (pure-Python ingestion path producing canonical BHs); `anima-service/faiss_service.py` (stores BHs); `core/primitives/extended_payload.py`; `scripts/cross_lang_bh_check.py`; `tests/golden_test.py`; `tests/unit/bh_cross_language_vector.py`; `tests/unit/trion_protocol/test_bh_collision_resistance.py`; `tests/bh_pipeline_test.py`; `sdk/TrionSDK.ts`.
- **current compliance**: **COMPLIANT** — tri-language byte-identical (DD §4.3: "the project's one portable engineering asset"); XOR invariant verified on ingest (`bh_from_rust_hex` raises on failure).
- **deviations**: The L0.md 93-byte layout (strand_A/strand_B/meta/beo_id/crc) is NOT the implemented contract (K2) — treat as obsolete.
- **security impact**: Critical — BH is the root of every signal, proof and escrow linkage.
- **required remediation**: Rewrite `spec/L0_universal_primitives.md` L0.1 to the implemented layout (W4); keep golden vectors pinned.
- **verification method**: `tests/unit/bh_cross_language_vector.py` (Python↔Rust byte identity); `scripts/cross_lang_bh_check.py`; `tests/unit/trion_protocol/test_bh_collision_resistance.py`; `tests/golden_test.py` step 5.

#### R-BH-02 — 20 canonical event types
- **requirement**: Exactly the 20 VM-agnostic event types: TRANSFER, SWAP, LIQUIDITY, STAKE, UNSTAKE, GOVERNANCE, PROPOSAL, BORROW, REPAY, LIQUIDATE, BRIDGE, DEPLOY, UPGRADE, MINT, BURN, ORACLE_UPDATE, MEV_CAPTURE, FLASH_LOAN, AIRDROP, CLAIM — each expressing economic intent, not execution path.
- **source**: MD L0.1; V2 L0.1; BTCP §12.3 (completeness proof by enumeration).
- **specification section**: MD L0.1 "The 20 VM-agnostic event types"; BTCP §12.3.
- **mathematical definition**: Enum 0–19 (canonical order fixed by V2 listing).
- **canonical data structure**: `EventType(IntEnum)` 0..19 + `EVENT_TYPE_NAMES`; `core/primitives/event_types_generated.py`.
- **canonical implementation**: `core/primitives/behavioral_hash.py::EventType`.
- **all implementations**: `core/primitives/behavioral_hash.py`; `core/primitives/event_types_generated.py` (generated per-VM bindings); rust `trion-common` event enum; `rust/src/types.rs` (BTCP intent actions); every `indexers/crates/trion-*` indexer emits them; `tests/golden_test.py` (20-type hash check).
- **current compliance**: **COMPLIANT** (all 20, canonical order, aliases mapped: LIQUIDITY_ADD→LIQUIDITY etc.).
- **deviations**: None.
- **security impact**: High — a missing/renumbered type breaks cross-VM resonance (L0.3) and VM-agnostic routing.
- **required remediation**: None.
- **verification method**: `tests/golden_test.py` (all 20 hash cleanly); generated bindings test `tests/unit/test_generated_chain_bindings.py`.

#### R-BH-03 — Magnitude normalization
- **requirement**: `magnitude_normalized = log10(USD_value+1)/log10(max_observed_90d+1) ∈ [0,1]` for the 93-byte BH (V2); `raw_amount × 10^(18−asset_decimals)` for the BTCP Hash_DNA (MD).
- **source**: V2 L0.1; MD L0.1 (split per K3).
- **specification section**: V2 L0.1 magnitude; MD L0.1 magnitude line.
- **mathematical definition**: Two canonical forms by primitive (BH log10; Hash_DNA 18-dec fixed point).
- **canonical data structure**: nano-unit 8-byte field (BH); uint256 (Hash_DNA).
- **canonical implementation**: `core/primitives/behavioral_hash.py::normalize_magnitude`; `core/primitives/hash_dna.py` (18-dec path).
- **all implementations**: both files above; Rust `trion-common` magnitude; `core/realtime/bh_streamer.py` (per-chain decimals applied — Task 20 commit 19decc3).
- **current compliance**: **COMPLIANT** (both forms; USD path with token-unit fallback documented).
- **deviations**: Rust indexers previously diverged on magnitude (session-max vs 90d-max) — Task 20 Stage Summary notes cross-language hash parity except Rust-side session-max magnitude determinism (needs cargo to verify).
- **security impact**: Medium — normalization divergence produces different BHs for the same event across languages.
- **required remediation**: When cargo is available, run `scripts/cross_lang_bh_check.py` against Rust builds to close the magnitude-determinism gap.
- **verification method**: `tests/unit/bh_cross_language_vector.py`; `scripts/cross_lang_bh_check.py` (cargo-gated).

#### R-BH-04 — Context field
- **requirement**: BH carries an 8-byte context encoding execution-context flags (venue type, settlement layer, protocol version/reserved).
- **source**: V2 L0.1 `context` field (semantics engineering-defined).
- **specification section**: V2 L0.1 payload list.
- **mathematical definition**: 8 bytes: bits 0–1 venue (DEX/LENDING/BRIDGE/NATIVE), 2–3 settlement (L1/L2/L3/sidechain), 4–7 version/reserved.
- **canonical data structure**: `BehavioralEvent.context: bytes(8)`.
- **canonical implementation**: `core/primitives/behavioral_hash.py` (context normalization to exactly 8 bytes).
- **all implementations**: `core/primitives/behavioral_hash.py`; Rust canonical BH; streamer (context=0 canonical default, Task 20 fix 19decc3).
- **current compliance**: **COMPLIANT**.
- **deviations**: None.
- **security impact**: Low (differentiates otherwise identical events).
- **required remediation**: None.
- **verification method**: `tests/unit/bh_cross_language_vector.py`; `tests/golden_test.py`.

#### R-BH-05 — Timestamps, block number, block hash, chain id
- **requirement**: BH binds the observation to its causal position: unix timestamp (8B), block number (carried in event), 32B block hash, 4B chain id — reorg-sensitive and chain-scoped by construction.
- **source**: V2 L0.1; BTCP §17 (chain_id, block_hash fields).
- **specification section**: V2 L0.1 payload; MD L0.1 field list.
- **mathematical definition**: Fixed-width big-endian fields in the 93-byte payload; chain_id from the canonical 129-chain registry ids.
- **canonical data structure**: `BehavioralEvent{timestamp, block_number, block_hash, chain_id}`.
- **canonical implementation**: `core/primitives/behavioral_hash.py`.
- **all implementations**: same as R-BH-01 set; chain ids re-keyed to canonical registry (Task 20 commit c93d237: 22 non-EVM chains 200101→900 etc.).
- **current compliance**: **COMPLIANT** (block times now real per fetcher — Task 20; lenient block hashes documented for chains without hash APIs).
- **deviations**: Ingestion timestamp vs on-chain timestamp distinction for streamer path (documented in Task 20).
- **security impact**: Medium (chain-id confusion previously cross-credited chains — fixed).
- **required remediation**: Keep the canonical-registry id discipline for any new chain.
- **verification method**: `tests/unit/test_backfill_chain_ids.py`; `tests/chain_coverage_audit.py`.

#### R-BH-06 — Entity/sender resolution into BH
- **requirement**: `entity_id` in the BH is the **BEO identifier** (32B), never a raw address; all manipulation fingerprints and routing operate on BEOs.
- **source**: V2 L0.2 ("entity_id in BH = BEO identifier, not raw address"); MD L0.2.
- **specification section**: V2 L0.2.
- **mathematical definition**: 32-byte canonical BEO id (resolution per Domain 4).
- **canonical data structure**: `BehavioralEvent.entity_id: bytes(32)`.
- **canonical implementation**: BEO resolution pipeline → `core/primitives/behavioral_hash.py` consumer.
- **all implementations**: `core/primitives/entity_resolution.py`; `anima-service/faiss_service.py` (production resolver, 5-factor); `core/realtime/bh_streamer.py` (entity = sha3 of bh_id for raw stream — Task 20 canonical decision); `scripts/apply_entity_id_validation.py`.
- **current compliance**: **PARTIAL** — the streamer assigns entity=sha3(bh_id) until a BEO resolution pass runs (documented engineering decision); backfill scripts resolve real BEOs.
- **deviations**: Streamer default is a placeholder identity, not a resolved BEO (honest, documented).
- **security impact**: Medium — unresolved entities weaken fingerprint detection (BEO-level patterns).
- **required remediation**: Wire periodic BEO re-resolution over the accumulated BH ledger (backfill tooling exists: `anima-service/backfill_entity_records.py`).
- **verification method**: `scripts/apply_entity_id_validation.py`; `tests/golden_test.py` step 2 (BEO identity across chains).

#### R-BH-07 — Domain/version separation
- **requirement**: `DOMAIN_SEPARATOR = keccak256("TRION_BEHAVIORAL_HASH_V1" ∥ chain_id ∥ contract_address)` prefixes the Hash_DNA input; `btcp_version` and `nonce` fields prevent cross-domain replay.
- **source**: MD L0.1 (DOMAIN_SEPARATOR, btcp_version, nonce fields); BTCP §17.
- **specification section**: MD L0.1 BH formula.
- **mathematical definition**: Hash_DNA over `DOMAIN_SEPARATOR ∥ entity_id ∥ event_type_id ∥ magnitude_normalized ∥ magnitude_currency_id ∥ timestamp ∥ block_number ∥ block_hash ∥ chain_id ∥ counterparty_id ∥ protocol_id ∥ context_hash ∥ btcp_version ∥ nonce`.
- **canonical data structure**: 14-field keccak256 preimage; `hash_dna.py` field encoder.
- **canonical implementation**: `core/primitives/hash_dna.py` (keccak256 via pycryptodome, SHA3 fallback warned).
- **all implementations**: `core/primitives/hash_dna.py` (docstring: "BTCP-layer primitive for cross-chain route proofs, intent commitments, BLO commitment_hash"); `rust/src/btcp_proof_builder.rs` (route proofs); `rust/src/bitp_matcher.rs` (BITP commitments).
- **current compliance**: **COMPLIANT** for the construction; **PARTIAL** for the ecosystem split (V2-style BH and MD-style Hash_DNA coexist without a spec note — conflict K1).
- **deviations**: None functional; documentation-level conflict only.
- **security impact**: Medium — domain separation is the anti-cross-domain-replay control; keccak/SHA3 fallback mismatch would break on-chain verifiability (warned at import).
- **required remediation**: Spec note codifying the two-primitive split (K1/K3); enforce pycryptodome presence in CI for BTCP paths.
- **verification method**: `tests/unit/trion_protocol/test_bh_collision_resistance.py`; **MUST-CREATE**: domain-separation negative test (same fields, different DOMAIN_SEPARATOR ⇒ different hash).

#### R-BH-08 — Chain semantics / block-hash semantics
- **requirement**: BHs are chain-scoped (chain_id in payload) and reorg-bound (block_hash in payload); a reorged observation is detectable because its block hash no longer sits on the canonical chain; BTCP anchors additionally apply a reorg protection window before `anchor_confirmed`.
- **source**: V2 L0.1; BTCP §10 Gap B (Reorg Protection Window).
- **specification section**: BTCP §10 row B.
- **mathematical definition**: N confirmations before anchor confirmation (Gap B).
- **canonical data structure**: `Route{anchor_confirmed}` + SAFE_CONFIRMATIONS.
- **canonical implementation**: `rust/src/btcp_proof_builder.rs` (reorg_depth check per spec file map).
- **all implementations**: `rust/src/btcp_proof_builder.rs`; `core/btcp/orchestrator.py` (proof step validates anchor); `core/btcp/bibl_engine.py` (fork assessment).
- **current compliance**: **PARTIAL** — implemented in the Rust crate (94 tests), but Python orchestrator treats anchor confirmation structurally (no live reorg polling without external RPCs).
- **deviations**: None structural.
- **security impact**: High — a reorged anchor can release escrow on a nonexistent event.
- **required remediation**: Live-RPC integration test for reorg windows (external-toolchain gated).
- **verification method**: Rust unit tests in `btcp_proof_builder.rs` (in-crate); **MUST-CREATE** (cargo-gated): reorg-window integration test.

#### R-BH-09 — Sense/antisense self-verification invariant
- **requirement**: Verification requires no external reference: `antisense XOR complement_transform(sense) == SHA3-256(payload ∥ 0xFF)`; tamper with either strand breaks complementarity → immediate detection.
- **source**: MD L0.1; V2 L0.1; MD §15 channel 12.
- **specification section**: MD L0.1 "Dual-Strand Verification".
- **mathematical definition**: XOR invariant above.
- **canonical data structure**: `verify_strand_with_payload(sense, antisense, payload)`.
- **canonical implementation**: `core/spiritual/living_security/__init__.py::verify_strand_*`; `core/primitives/behavioral_hash.py` inline verification.
- **all implementations**: both above; `rust/indexers/crates/trion-common` strand verify; `tests/test_gk_living_security.py`.
- **current compliance**: **COMPLIANT** (verified at construction AND ingest; `bh_from_rust_hex` raises ValueError on failure).
- **deviations**: None.
- **security impact**: Critical (the tamper-evidence root).
- **required remediation**: None.
- **verification method**: `tests/test_gk_living_security.py`; `tests/unit/bh_cross_language_vector.py`; golden test step 5.

---

## Domain 3 — Hash_DNA (BTCP-layer commitment hash)

Canonical: MD L0.1 formula + BTCP §17; implemented as `core/primitives/hash_dna.py`.

#### R-HD-01 — Hash_DNA 14-field construction
- **requirement**: `Hash_DNA(event) = keccak256(DOMAIN_SEPARATOR_BEHAVIORAL ∥ entity_id ∥ event_type_id ∥ magnitude_normalized(18-dec) ∥ magnitude_currency_id ∥ timestamp ∥ block_number ∥ block_hash ∥ chain_id ∥ counterparty_id ∥ protocol_id ∥ context_hash ∥ btcp_version ∥ nonce)`.
- **source**: MD L0.1; BTCP §17 formula index; BTCP Phase 0 Task 0.1.
- **specification section**: MD L0.1; BTCP §17 "Behavioral Hash".
- **mathematical definition**: keccak256 over the 14 concatenated fields, domain-separated per chain+contract.
- **canonical data structure**: `HashDNA` encoder in `core/primitives/hash_dna.py`.
- **canonical implementation**: `core/primitives/hash_dna.py`.
- **all implementations**: `core/primitives/hash_dna.py`; `rust/src/btcp_proof_builder.rs` (anchor/proof hashes); `rust/src/bitp_matcher.rs` (BITP commitment_hash); `rust/src/blo_scheduler.rs` (BLO commitment hashes).
- **current compliance**: **COMPLIANT** (construction + domain separation + per-event context-hash table).
- **deviations**: keccak256 requires pycryptodome; SHA3 fallback changes outputs (warned).
- **security impact**: High (all BTCP commitments derive from it).
- **required remediation**: CI guard that pycryptodome is installed for BTCP test paths.
- **verification method**: `tests/test_btcp_bitp_sba_bibl.py`; `tests/unit/btcp_continuum` suite.

#### R-HD-02 — Canonical asset identifier (magnitude_currency_id)
- **requirement**: `magnitude_currency_id = keccak256(chain_id_of_origin ∥ contract_address ∥ symbol)` — the universal asset identifier used in intents (`asset_in/asset_out`, bytes32).
- **source**: MD L0.1 currency field; BTCP §4.1 asset fields.
- **specification section**: BTCP §4.1 Intent object.
- **mathematical definition**: keccak256 triple.
- **canonical data structure**: bytes32 asset id.
- **canonical implementation**: `core/primitives/hash_dna.py` asset-id helper.
- **all implementations**: `core/primitives/hash_dna.py`; `core/btcp/modules.py` (asset_in/out as bytes32/hex); rust `types.rs`.
- **current compliance**: **PARTIAL** — asset ids accepted as hex passthrough in intents (registry of symbol→id not enforced end-to-end).
- **deviations**: No single asset-id registry service (engineering simplification).
- **security impact**: Medium — inconsistent asset ids break BITP complement matching.
- **required remediation**: Canonical asset registry table (chain, address, symbol → id) with validation at intent registration.
- **verification method**: **MUST-CREATE**: `tests/unit/test_asset_id_registry.py`.

#### R-HD-03 — Per-event context hash table
- **requirement**: `context_hash` = keccak256 of event-specific fields per type (SWAP: asset_in‖asset_out‖price‖slippage; TRANSFER: asset‖dest_chain‖dest_addr; BORROW: collateral‖borrowed‖ltv; STAKE: validator‖duration‖reward; LIQUIDITY: tokenA‖tokenB‖fee; others event-specific; none → bytes32(0)).
- **source**: MD L0.1 context_hash (BTCP Phase 0 Task 0.1 detail).
- **specification section**: BTCP spec Phase 0 / hash_dna docstring table.
- **mathematical definition**: keccak256 per-type encodings.
- **canonical data structure**: per-type encoder map.
- **canonical implementation**: `core/primitives/hash_dna.py` context table.
- **all implementations**: `core/primitives/hash_dna.py`; rust adapters emit context per type.
- **current compliance**: **COMPLIANT** (table implemented for the five named types + default).
- **deviations**: "All others → event-specific fields" is open-ended; only defaults implemented beyond the five.
- **security impact**: Low.
- **required remediation**: Enumerate the remaining 15 types' context fields in spec.
- **verification method**: `tests/unit/btcp_continuum` (hash_dna context cases).

---

## Domain 4 — BEO (Behavioral Entity Object)

Canonical: MD L0.2; V2 L0.2; L0.md L0.2 subordinate (K10).

#### R-BEO-01 — BEO confidence formula
- **requirement**: `BEO_confidence = (w_CF·CF + w_ST·ST + w_SC·SC + w_BP·BP)/Σw` with w_CF=0.40, w_ST=0.25, w_SC=0.25, w_BP=0.10; production adds GX (graph co-occurrence, w_GX=0.10) per the recorded July 2026 audit resolution.
- **source**: MD L0.2; V2 L0.2; L0.md L0.2 production note.
- **specification section**: MD L0.2; V2 L0.2.
- **mathematical definition**: Weighted evidence aggregation; CF = common funding source, ST = synchronized timing (ρ>0.85), SC = shared contract ownership, BP = 128-dim behavioral pattern match (sim>0.80), GX = tx-graph co-occurrence.
- **canonical data structure**: `WalletActivity` → `BEO_confidence` + cluster id.
- **canonical implementation**: `core/primitives/entity_resolution.py` (4-factor reference + 5-factor GX path); `anima-service/faiss_service.py` (production 5-factor, threshold 0.75).
- **all implementations**: `core/primitives/entity_resolution.py`; `anima-service/faiss_service.py`; `anima-service/backfill_entity_records.py`; `contracts/solidity/BEOAttestation.sol` (on-chain attestation); `rust/src/types.rs::BEOState`; `scripts/generate_beo_report.py`; `scripts/live_beo_proof.py`; `tests/master_formula_verification.py` (L0.2 exact-value tests).
- **current compliance**: **COMPLIANT** (both 4- and 5-factor forms with spec weights).
- **deviations**: L0.md body thresholds (0.85/0.50 bands) superseded by 0.75 production (K10 — recorded resolution, keep).
- **security impact**: High — entity resolution failure ⇒ all BEO-level manipulation detection fails (BTCP falsifiability: resolution failure > 5% on quarterly audit).
- **required remediation**: Merge the 4-factor reference and 5-factor production paths into one documented resolver (both currently live).
- **verification method**: `tests/master_formula_verification.py` (L0.2); **MUST-CREATE**: labeled-cluster accuracy test (F13/quarterly audit harness).

#### R-BEO-02 — 128-dimensional behavioral space (BP)
- **requirement**: BP = behavioral pattern match in 128-dimensional tx-graph cosine similarity (FAISS), threshold 0.80; BP fingerprint features hashed per wallet.
- **source**: MD L0.2 (BP 128-dim cosine); V2 L0.2.
- **specification section**: MD L0.2; V2 L0.2.
- **mathematical definition**: cosine similarity in 128-d space over behavioral feature fingerprints.
- **canonical data structure**: 128-float vector per wallet; FAISS index.
- **canonical implementation**: `core/primitives/entity_resolution.py::behavioral_fingerprint` (SimHash-style deterministic fallback) + FAISS path in `anima-service/faiss_service.py`.
- **all implementations**: `anima-service/faiss_service.py` (real FAISS, 34.6k+ vectors); `core/primitives/entity_resolution.py` (fallback); `core/master/signal_factory.py` (BEO vectors for signals); `tests/test_anima_stress_1000.py`.
- **current compliance**: **COMPLIANT** (FAISS primary + honest deterministic fallback documented as "NOT a substitute for the full ANIMA/FAISS pipeline").
- **deviations**: Fallback is SimHash, not cosine-in-learned-space (documented).
- **security impact**: Medium (fallback quality governs resolution accuracy when FAISS down).
- **required remediation**: None beyond keeping the honest labeling.
- **verification method**: `tests/test_anima_stress_1000.py`; `tests/golden_test.py` step 2.

#### R-BEO-03 — Cross-chain BEO identity continuity
- **requirement**: BEO identity is chain-agnostic: the same economic actor resolves to one BEO across all chains; `BEO_continuity(entity, A, B) = TRUE iff ∃ BH(e1,t1,A) → BH(e2,t2,B) sharing entity_id, linked through BTCP_route_id`.
- **source**: MD L0.2; BTCP §12.4 (proof by construction).
- **specification section**: BTCP §12.4 "BEO Identity Continuity Across Chains".
- **mathematical definition**: BH chain linked by route id in Akashic Index.
- **canonical data structure**: route linkage table (`btcp_routes.anchor_bh/execution_bh/entity_id` in schema.sql).
- **canonical implementation**: `core/btcp/orchestrator.py` (S7 write-through records anchor/execution BH + entity); `schema.sql::btcp_routes`.
- **all implementations**: `core/btcp/state_store.py` (SQLite mirror); `schema.sql`; `tests/integration/test_beo_cross_chain_vm.py`; `tests/crossvm/run_btcp_crossvm_full.py`.
- **current compliance**: **COMPLIANT** (route linkage persisted; DD's "SHA3 of one normalized string ×8" critique addressed by real route-linked BHs in the current orchestrator path).
- **deviations**: DD notes historical proof artifacts used same-chain loops; current e2e tests are cross-VM in-process, live-RPC pending.
- **security impact**: High (identity continuity is the zero-bridge thesis).
- **required remediation**: Two-distinct-chain, two-distinct-key live demonstration (DD recommendation, external-toolchain gated).
- **verification method**: `tests/integration/test_beo_cross_chain_vm.py`; `tests/crossvm/run_btcp_crossvm_full.py`.

---

## Domain 5 — Akashic Index

Canonical: MD §6 (L2.1–L2.4); V2 Level 2 + Part 7; L2.md subordinate (K8, K9).

#### R-AK-01 — Append-only persistence (TimescaleDB)
- **requirement**: The Akashic Index is a permanent append-only behavioral database storing every BH; technology TimescaleDB; consensus TRION-BFT; append-only, narrow scope.
- **source**: MD §6/L2.1; V2 Part 11 (storage row).
- **specification section**: MD L2.1 "Technology"; V2 Part 11.
- **mathematical definition**: Insert-only event store; information conservation law (L0.4/L9.2) forbids deletion.
- **canonical data structure**: `akashic_bh` hypertable + HOT/WARM/COLD tiers; SQLite WAL ledger as fallback.
- **canonical implementation**: `core/akashic/timescale_store.py::TimescaleStore`.
- **all implementations**: `core/akashic/timescale_store.py`; `schema.sql`; `anima-service/faiss_service.py` (SQLite WAL ledger + TimescaleDB dual-write); `core/btcp/state_store.py` (BTCP tables); `scripts/init_bh_ledger.py`; `tests/unit/test_btcp_akashic_writers.py`.
- **current compliance**: **PARTIAL** — TimescaleDB code path real but requires external DB (sandbox: SQLite ledger live); append-only honored (no delete paths exposed).
- **deviations**: TimescaleDB unreachable in sandbox (documented external-toolchain boundary).
- **security impact**: High (the moat IS the accumulated history).
- **required remediation**: External TimescaleDB deployment verification (Wave 3/N scope).
- **verification method**: `tests/unit/test_btcp_akashic_writers.py`; live-DB integration test (toolchain-gated).

#### R-AK-02 — Akashic depth D(t)
- **requirement**: `D(t) ∝ ∫₀ᵗ [A(τ)·(1+M(τ))·C(τ)]dτ`; D(t=0) = EVM genesis history (full bootstrap); D_minimum ≈ 6 months live operation; bootstrap falls back to multi-sig 7-of-12 + human oversight until D_minimum.
- **source**: MD L2.1; V2 L2.1.
- **specification section**: MD L2.1 "Akashic Depth"; V2 L2.1.
- **mathematical definition**: Trapezoidal integral over block samples; D_MINIMUM = 10 000 behavioral events (code constant).
- **canonical data structure**: `block_samples → D` float; depth tiers.
- **canonical implementation**: `core/akashic/depth.py::compute_akashic_depth` + `bootstrap_weight`.
- **all implementations**: `core/akashic/depth.py`; `core/master/d_engine.py` (block-level accumulation); `api/app.py` depth plane query; `tests/master_formula_verification.py` (L2.1).
- **current compliance**: **COMPLIANT** for the integral and bootstrap weight; **PARTIAL** for genesis bootstrap (full EVM history from genesis NOT loaded — genesis_backfill_* scripts exist per chain but not run to spec scale; DD: volume claims unverifiable).
- **deviations**: L2.md's decaying/fossilized depth is non-canonical (K9).
- **security impact**: High (D_minimum gates Living Security activation and INIT_valid).
- **required remediation**: Real historical bootstrap run + documented D(t) measurement; until then keep bootstrap_weight honest.
- **verification method**: `tests/master_formula_verification.py` (L2.1 exact values); `anima-service/genesis_backfill_*.py` runners (toolchain-gated).

#### R-AK-03 — Genesis inference (new-asset pricing)
- **requirement**: For assets with no history: 128-dim genesis vector G (initial distribution, first tx graph, contract architecture hash, deployer behavioral signature, launch context, cross-protocol debut, initial holder composition); `sim(G,A_k) = (G·A_k)/(‖G‖‖A_k‖)`; archetype library >90% coverage; `conf_genesis(0)=0`, grows with depth; blend `S_total = conf_genesis·S_direct + (1−conf_genesis)·S_archetype`.
- **source**: MD L2.2; V2 L2.2/L2.3 + §7.1.
- **specification section**: MD L2.2; V2 7.1 "Genesis Inference — Complete Architecture".
- **mathematical definition**: cosine similarity + archetype-weighted valuation + exponential confidence convergence (variable λ per asset class).
- **canonical data structure**: `GenesisVector`, `Archetype`, `GenesisFingerprint`.
- **canonical implementation**: `core/akashic/genesis.py` (variable-λ convergence, FAISS similarity query).
- **all implementations**: `core/akashic/genesis.py`; `core/akashic/archetype.py`; `anima-service/genesis_backfill_*.py` (24 chain backfills); `anima-service/faiss_service.py` (FAISS search); `tests/unit/trion_protocol/test_archetype_engine.py`.
- **current compliance**: **PARTIAL** — mechanism complete; ">90% behavioral space coverage" unverified (no measured coverage stat); deployer-behavioral-signature input needs a populated Akashic history.
- **deviations**: L2.md's decay-form GC non-canonical (K8).
- **security impact**: High (F6: genesis inference must track realized behavior or signals mislead).
- **required remediation**: Coverage measurement harness; GENESIS signal always displays conf_genesis (implemented — verify enforced).
- **verification method**: `tests/unit/trion_protocol/test_archetype_engine.py`; `tests/master_formula_verification.py` (L2.3); F6 monitor (`core/governance/falsifiability_registry.py`).

#### R-AK-04 — Trajectory anomaly monitor
- **requirement**: `TRAJ_ANOMALY(asset,t) = KL_divergence(P_actual, P_expected(matched_archetype, same_age))`; elevated ⇒ TRAJECTORY signal; discontinuous change ⇒ MANIPULATION_ALERT + Genesis invalidation; conf_genesis LOCKED during anomaly; UPGRADE event triggers before/after comparison.
- **source**: MD L2.4; V2 L2.7.
- **specification section**: MD L2.4; V2 L2.7.
- **mathematical definition**: KL divergence between actual and archetype-expected behavioral distributions; θ_anomaly > 2σ.
- **canonical data structure**: `TrajectoryDistribution`, `TrajectoryAnomalyResult{kl, theta, invalidated, locked}`.
- **canonical implementation**: `core/akashic/trajectory_anomaly.py::compute_trajectory_anomaly`.
- **all implementations**: `core/akashic/trajectory_anomaly.py`; `core/master/signal_factory.py` (TRAJECTORY signal builder); `tests/master_formula_verification.py` (KL case).
- **current compliance**: **COMPLIANT** (KL + invalidation + conf_genesis locking all present).
- **deviations**: L2.md's L2-η norm anomaly score is a different formula — non-canonical.
- **security impact**: High (this is the anti "mimic archetype then pivot" control).
- **required remediation**: None.
- **verification method**: `tests/master_formula_verification.py`; unit tests in `trajectory_anomaly.py` module main.

#### R-AK-05 — Dormancy taxonomy and resurrection
- **requirement**: Five dormancy types with κ (ABANDONED 0.008 >365d; HIBERNATION 0.003 30–365d; MIGRATION 0.000; REGULATORY_PAUSE 0.001; EXPLOIT_RECOVERY 0.005); `Δ_resurrection = w_d·e^(−κT)·w_c·sim(S_pre,S_react)·w_x·g(C)`; classification GENUINE_CONTINUATION / NEW_ENTITY_OLD_SHELL / HOSTILE_TAKEOVER / ZOMBIE.
- **source**: V2 L2.4 + §7.2; MD (silent → V2 wins).
- **specification section**: V2 L2.4 "Resurrection Inference"; §7.2 "Dormancy Taxonomy".
- **mathematical definition**: Exponential decay by dormancy type × continuity similarity × context quality.
- **canonical data structure**: `DormancyType` enum, `KAPPA` map, `ResurrectionResult`.
- **canonical implementation**: `core/akashic/resurrection.py`.
- **all implementations**: `core/akashic/resurrection.py`; `core/novel/birp.py` (BIRP uses resurrection machinery); `tests/master_formula_verification.py`; RESURRECTION signal in `core/master/signal_factory.py`.
- **current compliance**: **COMPLIANT** (all five κ values exact, classification outcomes implemented).
- **deviations**: L2.md's R1–R5 revival registry (epoch-based) is a different taxonomy — non-canonical.
- **security impact**: High (HOSTILE_TAKEOVER detection is the abandoned-token takeover defense).
- **required remediation**: None.
- **verification method**: `tests/master_formula_verification.py` (L2.4 κ table); resurrection module self-tests.

#### R-AK-06 — Fork resolution
- **requirement**: `CC_A`/`CC_B` = proportion of pre-fork holders still holding each chain; dominant fork inherits full D; other inherits `D×(1−CC_dominant)` with confidence discount; near-equal ⇒ both ×0.5 with divergence_flag; canonical chain = ≥67% original validators + highest TVL + developer activity; TYPE A/B/C fork semantics.
- **source**: MD L2.3; V2 L2.6.
- **specification section**: MD L2.3 "Fork Resolution"; V2 L2.6.
- **mathematical definition**: CC-weighted depth inheritance; FORK_DIVERGENCE signal on both branches.
- **canonical data structure**: `ForkResolution{cc_a, cc_b, winner, divergence_flag}`.
- **canonical implementation**: `core/akashic/fork_resolution.py`.
- **all implementations**: `core/akashic/fork_resolution.py`; `core/btcp/bibl_engine.py::detect_fork/update_fork_assessment` (runtime fork detection for routing); FORK_DIVERGENCE signal in signal_factory.
- **current compliance**: **PARTIAL** — CC math implemented; the ≥67%-validators + TVL + developer-activity multi-factor canonical-chain rule is not encoded (single-factor CC only).
- **deviations**: Multi-factor tie-break MISSING.
- **security impact**: Medium (fork mis-resolution splits behavioral history wrongly).
- **required remediation**: Add validator-share/TVL/activity tie-breakers to `fork_resolution.py`.
- **verification method**: `tests/master_formula_verification.py` (L2.6); **MUST-CREATE**: tie-break test.

#### R-AK-07 — Archetype library
- **requirement**: Append-only archetype library; archetypes cannot be deleted; new archetype ⇒ GENESIS signal; similarity search <10ms at 1B+ records (build-level completion criterion).
- **source**: V2 L2.2 (invariants); MD L2.2.
- **specification section**: V2 L2.2 invariants.
- **mathematical definition**: cosine similarity in 128-d space; append-only store.
- **canonical data structure**: archetype vectors + FAISS index.
- **canonical implementation**: `core/akashic/archetype.py`.
- **all implementations**: `core/akashic/archetype.py`; `anima-service/faiss_service.py`; L2.md's 9-dim archetype variant non-canonical.
- **current compliance**: **PARTIAL** (append-only in store; performance criterion unmeasured at 1B records; 34.6k vectors live).
- **deviations**: None structural.
- **security impact**: Low.
- **required remediation**: Latency benchmark at scale (ops).
- **verification method**: `tests/unit/trion_protocol/test_archetype_engine.py`.

#### R-AK-08 — Epigenetics persistence
- **requirement**: Epigenetic/CRISPR/immune state persists across restarts (databases, not memory); expression changes are recorded behavioral state.
- **source**: Spec-silent at persistence level (engineering requirement from DD S7 "state loss on restart").
- **specification section**: — (spec-silent, engineering decision).
- **mathematical definition**: n/a.
- **canonical data structure**: SQLite stores `akashic/epigenetic_immunity.db`, `akashic/crispr_adaptive.db`, `akashic/bibl_patterns.db`.
- **canonical implementation**: `core/akashic/epigenetics.py::EpigeneticEngine` (DB-backed).
- **all implementations**: `core/akashic/epigenetics.py`; CRISPR adaptive DB; BIBL pattern store.
- **current compliance**: **COMPLIANT** (DB-backed, survives restart — the DD restart-wipe finding was remediated for these components).
- **deviations**: Spec-silent, engineering decision — document in spec or remove.
- **security impact**: Medium (state loss on restart previously reset immune/expression state — trust continuity).
- **required remediation**: Spec note on state persistence layer.
- **verification method**: restart-persistence tests in epigenetics module; `tests/unit/test_btcp_akashic_writers.py` (BTCP side).

---

## Domain 6 — Entropy, coherence (Σ), threshold (Θ), manipulation detection, moat

Canonical: MD §5 (L1.1–L1.4), §8 (L4.1), §3; V2 L1.1/L1.2, L4.1, L4.8.

#### R-EC-01 — Physical richness Φ(t)
- **requirement**: `Φ(t) = (1/N)·Σᵢ wᵢ·H(fᵢ(t))` over the nine EVM features f1–f9 (V2 set); weights learned from Akashic history, not fixed; high Φ = organic, low Φ = synthetic.
- **source**: V2 L1.1 (MD §5 defines Φ_adj usage; feature set per V2).
- **specification section**: V2 L1.1 "Physical Richness".
- **mathematical definition**: Weighted mean of feature entropies; feature normalization `fᵢ = H(raw)/log2(|alphabet|)` (L1.md form used by indexers).
- **canonical data structure**: 9-feature vector + learned weights.
- **canonical implementation**: `core/physical/phi_engine.py`.
- **all implementations**: `core/physical/phi_engine.py`; Rust indexers' 9-feature Shannon extractors (`indexers/crates/trion-*`); `tests/master_formula_verification.py` (L1.1); `tests/unit/trion_protocol/test_feature_extractor.py`.
- **current compliance**: **PARTIAL** — features computed; "weights learned from Akashic history" is a fixed default in code (no online learning loop).
- **deviations**: Learned-weight requirement unimplemented (fixed weights).
- **security impact**: Medium (fixed weights can be gamed once understood).
- **required remediation**: Weight-learning loop from realized outcomes (research task) or spec amendment.
- **verification method**: `tests/master_formula_verification.py`; `tests/unit/trion_protocol/test_feature_extractor.py`.

#### R-EC-02 — The 7 manipulation fingerprints
- **requirement**: All seven types with exact triggers and scores: WASH_TRADING (cyclic_flow>0.60 ∧ counterparties<5 → 0.70×ratio); COORDINATED_PUMP (sync_buy>0.80 across 3+ BEO → 0.85×ratio); ORACLE_ATTACK_ATTEMPT (deviation>15% within 10 blocks of large swap → 1.00 automatic); SYBIL_LIQUIDITY (top5 LPs>80% ∧ funded<3 sources → 0.60×concentration); GOVERNANCE_CAPTURE (vote HHI>4000 ∧ proposal<48h → 0.50×scaled_HHI); MEV_EXTRACTION_SUSTAINED (rate>0.5% sustained 7d → 0.40×scaled_rate); FAKE_VOLUME_PROTOCOL (entropy<threshold ∧ volume>10×baseline → 0.80×(1−entropy)).
- **source**: MD §5 L1.2 + §12; V2 L1.2.
- **specification section**: MD L1.2 table; V2 L1.2 TYPE 1–7.
- **mathematical definition**: Per-type trigger + score; `MF_score = min(1.0, max(active contributions))`.
- **canonical data structure**: `MFResult{pattern_type, detected, mf_score, confidence, description, evidence}`.
- **canonical implementation**: `core/physical/manipulation_detector.py`.
- **all implementations**: `core/physical/manipulation_detector.py`; `core/manipulation/btcp_mf_detector.py` (BTCP-layer MF for routing); Rust indexers emit MEV/entropy features; `tests/master_formula_verification.py` (L1.2 exact formulas); `backtest/` exploit replay suite; `tests/adversarial/` (120/121).
- **current compliance**: **COMPLIANT** (all 7 with exact constants; MF_score aggregation matches V2).
- **deviations**: L1.md's feature-combo registry (M1–M7 with r_Mk thresholds) is a different formulation — non-canonical but partially aligned.
- **security impact**: Critical (these gate Φ_adj collapse → SILENCE).
- **required remediation**: Keep F13 FP-rate monitor <2% on clean histories (registry entry exists; live labeled data needed).
- **verification method**: `tests/master_formula_verification.py` (L1.2); `backtest/results/` + `tests/adversarial/test_adversarial_suite.py`; F8/F13 in `core/governance/falsifiability_registry.py`.

#### R-EC-03 — Manipulation discount and defenses
- **requirement**: `Φ_adj = Φ·(1−MF_score)`; wash-trading defense `D_effective = D·(1−HHI(counterparty_distribution))`; flash-loan defense `NL_smooth = median(NL(t−2),NL(t−1),NL(t))`, FLASH_LOAN_DISCOUNT 0.15 same-block.
- **source**: MD §5 L1.1/L1.2.
- **specification section**: MD L1.1 (BTCP score ×(1−MF)); MD "Wash Trading Defense"/"Flash Loan Defense".
- **mathematical definition**: As stated.
- **canonical data structure**: discount functions.
- **canonical implementation**: `core/master/coherence.py::apply_mf_to_phi`; flash-loan discount in `anima-service/nl_score_engine.py`.
- **all implementations**: `core/master/coherence.py`; `core/master/btcp_score.py` (×(1−MF) in BTCP_score); NL smoothing in nl_score_engine.
- **current compliance**: **PARTIAL** — Φ_adj and NL smoothing present; wash-trading HHI discount on depth D not found as a standalone function.
- **deviations**: D_effective HHI discount MISSING.
- **security impact**: Medium (washed depth inflates D).
- **required remediation**: Implement `D_effective = D×(1−HHI(counterparty_distribution))` in the depth engine.
- **verification method**: **MUST-CREATE**: `tests/unit/test_wash_depth_discount.py`.

#### R-EC-04 — Temporal coherence TC(t)
- **requirement**: `TC(t) = 1 − max_i(|t_plane_i − t_reference|)/TTL_min`; all five planes temporally coherent; stale plane collapses coherence → SILENCE; TC published with every signal.
- **source**: MD L1.3; V2 L1.3.
- **specification section**: MD L1.3; V2 L1.3 (adds TC_valid iff TC > TC_minimum).
- **mathematical definition**: Max-plane staleness normalized by TTL.
- **canonical data structure**: TC float in signal quality metadata.
- **canonical implementation**: `core/physical/temporal_coherence.py`.
- **all implementations**: `core/physical/temporal_coherence.py`; `api/app.py::_plane_values_staleness_s` (live staleness measurement); signal_factory publishes TC.
- **current compliance**: **COMPLIANT** (staleness measured live in API; TC included in signals).
- **deviations**: L1.md's exponential-decay TC with cross-correlation is a different formula — non-canonical.
- **security impact**: High (stale planes = acting on old truth).
- **required remediation**: None.
- **verification method**: `tests/master_formula_verification.py` (L1.3); api staleness unit path.

#### R-EC-05 — Transduction integrity TI
- **requirement**: `TI(sensor,t) = Calibration·Drift_correction·Cross_verification`; TI=0 uncalibrated → excluded; physical sensors at validator nodes; HSM (Thales Luna 7 / YubiHSM 2) NON-NEGOTIABLE; H_environment > 0 feeds Genomic Key bound.
- **source**: MD L1.4; V2 L1.4.
- **specification section**: MD L1.4; V2 L1.4.
- **mathematical definition**: Product of three sensor-quality factors.
- **canonical data structure**: TI score per sensor.
- **canonical implementation**: `core/physical/transduction_integrity.py`.
- **all implementations**: `core/physical/transduction_integrity.py` (tiers + compensation); HSM hardware requirement is ops-level (validator fleet not deployed — see R-VC-08).
- **current compliance**: **PARTIAL** — TI software model implemented; physical HSM sensor layer is a deployment requirement (not code); L1.md's entropy-difference TI form is non-canonical but related.
- **deviations**: HSM enforcement absent (no fleet).
- **security impact**: High (H_environment > 0 underwrites the Kolmogorov bound condition).
- **required remediation**: Validator HSM attestation in the onboarding registry when fleet deploys.
- **verification method**: `tests/master_formula_verification.py` (L1.4); **MUST-CREATE**: HSM attestation check in validator onboarding.

#### R-EC-06 — Entropy/conservation accounting (I_TRION)
- **requirement**: `I_TRION(t) = BH_generated + A_absorbed − S_emitted − E_lost` (E_lost = Landauer bound); `dI/dt ≥ 0`; Akashic append-only for this reason.
- **source**: MD L0.4/L9.2; V2 L9.2.
- **specification section**: MD L0.4 "Thermodynamic Information Conservation".
- **mathematical definition**: System-level information ledger with non-decreasing invariant.
- **canonical data structure**: conservation terms per block.
- **canonical implementation**: `core/primitives/thermodynamics.py`.
- **all implementations**: `core/primitives/thermodynamics.py`; `core/akashic/timescale_store.py` (append-only enforcement in practice); channel C3 reporting hooks in `core/master/channel_architecture.py`.
- **current compliance**: **PARTIAL** — accounting implemented; the lunar-cycle conservation audit with transfer suspension (L9.2 audit rule) is not automated.
- **deviations**: L0.md's entropy-budget form `S_emit ≤ BH_gen + A_abs − E_lost` is a variant; both implemented? only the terms ledger.
- **security impact**: Medium (conservation audit is the information-leak tripwire).
- **required remediation**: Automate the lunar-cycle audit with SYSTEMIC_RISK on |delta| > τ_audit.
- **verification method**: `tests/master_formula_verification.py` (L0.4); **MUST-CREATE**: conservation audit test.

#### R-EC-07 — Signal selection principle
- **requirement**: Signal selected iff `dI_gained/dS_entropy_cost > θ_selection`; TRION does not listen to everything.
- **source**: MD L0.5; V2 L0.5.
- **specification section**: MD L0.5.
- **mathematical definition**: Information-gain-per-entropy-cost threshold.
- **canonical data structure**: selection gate in signal pipeline.
- **canonical implementation**: `core/primitives/thermodynamics.py` + signal pipeline gate (L0.5 function present in formula suite).
- **all implementations**: formula coverage in `tests/master_formula_verification.py` (L0.5); runtime gate not enforced in signal_factory.
- **current compliance**: **PARTIAL** (formula tested; not wired as an emission gate — all computed signals are emitted regardless of entropy budget).
- **deviations**: Runtime enforcement MISSING.
- **security impact**: Low-Medium (cost control, not adversarial).
- **required remediation**: Wire the selection gate into `signal_factory` emission path.
- **verification method**: **MUST-CREATE**: entropy-budget gate test.

---

## Domain 7 — 19 signal types, 7 novel primitives, 20-channel communication

Canonical: MD §11, §13, §15; V2 Part 5, Part 6; signal_types.md/novel_primitives.md/communication_channels.md subordinate (K4–K6, K13, K14).

#### R-SG-01 — TRIONSignal schema (no optional fields)
- **requirement**: Every signal contains: signal_id, signal_type, entity_id, signal_value, CI_95 (always present, never null), coherence, threshold, margin, plane_breakdown{physical..anima, limiting_plane}, temporal_coherence, entropy, akashic_depth, observer_effect, bootstrap_phase, conf_genesis, reflexivity_flag, genomic_signature (sense+antisense), immune_clearance, security_generation, provenance (complete derivation chain), validator_count, validator_hhi, timestamp, ttl, biological_time{4 phases}. No partial signals.
- **source**: V2 Part 5 (MD lists envelope requirements: CI_95 always, biological_time, provenance, coherence breakdown).
- **specification section**: V2 "TRIONSignal — Complete Schema"; MD §11 preamble.
- **mathematical definition**: n/a (schema).
- **canonical data structure**: `TRIONSignal` dict factory output.
- **canonical implementation**: `core/master/signal_factory.py`.
- **all implementations**: `core/master/signal_factory.py` (provenance non-empty — prior "always empty" fixed); `core/primitives/signal_packing.py` (256-byte on-chain packing); `sdk/TrionSDK.ts` (packSignal/unpackSignal, isSafe); `contracts/solidity/TRIONOracleV3.sol::publishBehavioralSignal` (on-chain BehavioralSignal struct).
- **current compliance**: **COMPLIANT** for field presence incl. CI_95/biological_time/provenance (signal_factory docstring + tests enforce); **PARTIAL** for on-chain encoding (BehavioralSignal carries the core subset, not all 25 fields — 256-byte gas-optimized form by design).
- **deviations**: signal_types.md's mandatory envelope (evidence_hash, severity, expires_at) overlaps but differs — V2 schema canonical.
- **security impact**: High (CI_95 "always present" is a headline invariant; SILENCE≠VALUATION type separation).
- **required remediation**: Keep docstring-truth tests; add schema-diff test against V2 Part 5 field list.
- **verification method**: `tests/unit/test_trading_signals.py`; `tests/master_formula_verification.py`; **MUST-CREATE**: field-presence schema test.

#### R-SG-02 — SILENCE structured-null semantics
- **requirement**: SILENCE carries `coherence_gap (Θ−C), limiting_plane (PlaneType), coherence_trend (RISING|FALLING), eta (estimated seconds to threshold)`; the silence is information, not absence; SILENCE cannot be cast to VALUATION (type system).
- **source**: MD §11; V2 L5.4.
- **specification section**: MD §11 SILENCE row; V2 "The SILENCE carries".
- **mathematical definition**: Structured null payload.
- **canonical data structure**: SILENCE signal variant with 4 mandatory fields.
- **canonical implementation**: `core/master/signal_factory.py` (SILENCE construction incl. eta).
- **all implementations**: `core/master/signal_factory.py`; `contracts/solidity/TRIONOracleV3.sol` (SilenceRecorded + SilenceRecordedV2 events with gap + eta); TS SDK type separation; `tests/golden_test.py` step 11 (SILENCE semantics).
- **current compliance**: **COMPLIANT** (all four fields; on-chain V2 event includes gap + eta; type separation in TS).
- **deviations**: BTCP spec §2 noted "limiting_plane/eta/coherence_gap fields incomplete" in the original TRIONOracleV3 — remediated (V2 event).
- **security impact**: High (silent-when-uncertain is the core oracle honesty property).
- **required remediation**: None.
- **verification method**: `tests/golden_test.py` step 11; hardhat tests `hardhat/test/`.

#### R-SG-03 — 19 canonical signal types (+5 extended = 24 implemented)
- **requirement**: The 19 canonical types (MD §11 list); V2's 5 extra types (RESURRECTION, NEGATIVE_SPACE, INSTITUTIONAL_BHV, ECOSYSTEM_HEALTH, BOOTSTRAP) authoritative where MD silent → 24 total; BTCP §14.2's additional 10 are BTCP-domain additions.
- **source**: MD §11; V2 Part 5; BTCP §14.2 (conflict K4).
- **specification section**: MD §11 table; V2 "The 19 Signal Types".
- **mathematical definition**: Enum 0–23.
- **canonical data structure**: `SignalType(IntEnum)` in signal_factory (0–23).
- **canonical implementation**: `core/master/signal_factory.py::SignalType`.
- **all implementations**: `core/master/signal_factory.py`; `sdk/TrionSDK.ts` SignalType enum; signal_types.md S1–S24 registry; BTCP signal types BTCP_ROUTE etc.
- **current compliance**: **COMPLIANT** for 24 (19 canonical + 5 extended); **PARTIAL** for BTCP §14.2 additions (SHADOW_CHAIN, LIQUIDITY_OCEAN, CHAIN_RELIABILITY, BTCP_ESCROW_EVENT, BTCP_TIMEOUT, GENESIS_COMMITMENT, BEHAVIORAL_TRUTH, RESURRECTION-as-route-recovery) — not in the enum.
- **deviations**: signal_types.md S23's BTCP expansion error (K5).
- **security impact**: Medium (missing CHAIN_RELIABILITY/BTCP_TIMEOUT types weaken route-failure signaling).
- **required remediation**: Add BTCP §14.2 types to the registry (or spec note deferring them).
- **verification method**: `tests/unit/test_trading_signals.py`; **MUST-CREATE**: enum-completeness test against MD §11 ∪ V2 ∪ BTCP §14.2.

#### R-SG-04 — Primitive 1: Behavioral Causal Keys (BCK)
- **requirement**: Security from ontological uniqueness: `K(H(TRION,t)) ≥ Ω(t·N_chains·N_validators·H_environment)`; `P(break BCK) = P(reproduce causal_history)`; lim P→0; no quantum speedup for having-been-present; bound holds iff H_environment>0.
- **source**: MD L4.3 + §13 P1; V2 L4.3 Kolmogorov bound.
- **specification section**: MD L4.3 "[NOVEL PRIMITIVE] Behavioral Causal Key Security Bound".
- **mathematical definition**: Kolmogorov-complexity lower bound on the system history.
- **canonical data structure**: complexity check fields.
- **canonical implementation**: complexity-bound checker in `core/spiritual/living_security/` (tested via test_whitepaper_gaps complexity-bound tests).
- **all implementations**: `core/spiritual/living_security/`; `tests/unit/test_whitepaper_gaps.py` (test_complexity_bound_fields, test_sha3_key_within_bound); novel_primitives.md P2 (KDF/Argon2id form — a different construction: `BCK = KDF(BH(t0)‖…‖BH(tn))`).
- **current compliance**: **RESEARCH-ONLY** (the bound is modeled and unit-tested as arithmetic; novel_primitives P2's Argon2id BCK is NOT implemented — no KDF-based BCK in code).
- **deviations**: P2's concrete BCK derivation MISSING.
- **security impact**: High claim, low current exposure (no production keys rely on BCK).
- **required remediation**: Either implement P2's KDF construction in `core/novel/` or mark P2 as deferred in spec.
- **verification method**: `tests/unit/test_whitepaper_gaps.py`; **MUST-CREATE** if implemented: BCK derivation vectors.

#### R-SG-05 — Primitive 2: Semi-immutability
- **requirement**: `bytecode(P,t) = bytecode(P,t′) ∀t>t′` AND `expression(P,t) = f(bytecode(P), EL_state(t))` with `EL_state = g(Threat_level, Network_entropy, Validator_health)`; g defined by deployed bytecode (range immutably bounded); differs from proxy patterns (no governance vote, no new address).
- **source**: MD §13 P2 + §14; V2 (implicit via L4.5).
- **specification section**: MD §14 "SEMI-IMMUTABILITY ARCHITECTURE".
- **mathematical definition**: Two-property definition above.
- **canonical data structure**: EpigeneticState + expression mode.
- **canonical implementation**: `core/spiritual/living_security/__init__.py::EpigeneticLayer` (states NORMAL/ELEVATED/DEFENSIVE/LOCKDOWN per threat); `core/akashic/epigenetics.py` (persistent expression state); novel_primitives.md P1's five mutation gates G1–G5 (different formulation).
- **all implementations**: the two epigenetic engines; `core/spiritual/epigenetic.py`; concept references in channel_architecture/trion_primitives docstrings.
- **current compliance**: **PARTIAL** — expression-adaptation implemented (epigenetic layers react to threat/health/entropy); the bytecode-immutability side is a contract-deployment property (Vyper escrow immutable by construction, no proxy); P1's five mutation gates (merge/revival/reorg/CRISPR-quarantine/sovereign-freeze) are NOT implemented as a unified gate registry.
- **deviations**: Mutation-gate registry MISSING; no on-chain semi-immutability proof artifact.
- **security impact**: Medium (mutation gates prevent unauthorized record mutation; currently only CRISPR quarantine approximates G4).
- **required remediation**: Implement the five-gate registry over the Akashic store, or spec-note P1 as superseded by the epigenetic engine.
- **verification method**: epigenetics module tests; **MUST-CREATE**: mutation-gate test if implemented.

#### R-SG-06 — Primitive 3: Coordination Collapse Theorem (DW-BFT)
- **requirement**: `d_j = 1−corr(M_j, M̄)`; `w_j_effective = s_j·d_j`; `lim_{coordination→1} Σ_Byzantine s_j·d_j = 0` [PROVED]; honesty is the only Nash equilibrium; falsified by two contradictory signals certified simultaneously (F2).
- **source**: MD L4.1 + §13 P3; V2 L4.1/Part 13 Proof 2; BTCP §12.2.
- **specification section**: MD L4.1 "[PROVED] Coordination Collapse Theorem".
- **mathematical definition**: Algebraic proof as stated.
- **canonical data structure**: per-validator diversity result + Σ aggregation.
- **canonical implementation**: `core/spiritual/consensus.py` (Python), `validator/internal/p2p/consensus.go` (Go), `rust` (proof cert in BTCP proofs).
- **all implementations**: `core/spiritual/consensus.py` (discloses BOOTSTRAP MODE); `core/spiritual/sigma_engine.py`; `validator/internal/p2p/consensus.go` + `mesh.go`; `validator/internal/consensus/engine.go` (real Tendermint-family state machine with strict >2/3 quorum); `core/novel/coordination_collapse.py`; `tests/unit/trion_protocol/test_consensus_bft.py`; `validator/internal/consensus/engine_test.go` (incl. TestExactlyTwoThirdsPrecommitsDoNotCommit, sybil collapse tests).
- **current compliance**: **PARTIAL** — theorem's arithmetic faithfully implemented in three languages with a real Go BFT state machine; but no live fleet ⇒ Σ(t) inputs are bootstrap-grade (Python consensus discloses this; DD §5.3 confirms).
- **deviations**: None mathematical.
- **security impact**: Critical (this is the consensus security core; F2 continuously testable).
- **required remediation**: Deploy validator fleet (ops); keep the BOOTSTRAP MODE disclosure.
- **verification method**: `tests/unit/trion_protocol/test_consensus_bft.py`; `validator/internal/consensus/engine_test.go`; `validator/internal/p2p/p2pgo_test.go` (50-sybil collapse).

#### R-SG-07 — Primitive 4: Behavioral ZK proofs
- **requirement**: ZK proofs over Akashic behavioral commitments: "H satisfies C without revealing H"; constructible with Groth16/PLONK/STARKs [CONJECTURE — circuit construction not yet completed]; used for BIRP, sensing oracle, confidential disputes, IAP share proofs, travel rule.
- **source**: MD §16; V2 (P4 in novel_primitives.md adds claim schema C1–C6).
- **specification section**: MD §16 "Behavioral Zero-Knowledge Proofs" [CONJECTURE].
- **mathematical definition**: SNARK over behavioral commitments.
- **canonical data structure**: `BZK_proof{public_inputs, private_inputs, statement, binding}`.
- **canonical implementation**: `zk/` (self-described "Groth16-style proof simulation" — honest label), `zk-circuits/` (5 Circom circuits, no zkeys).
- **all implementations**: `zk/` (1 411-line simulated prover); `zk-circuits/zk_{intent_commitment,complementarity_proof,iap_share_proof,travel_rule,behavioral_credential}`; rust zk modules.
- **current compliance**: **RESEARCH-ONLY** — circuits ship without build artifacts; the Python layer self-labels as simulation (honest per no-fake-production rule; DD §4.2 agrees).
- **deviations**: None (spec itself marks feasibility as conjecture).
- **security impact**: High-if-misrepresented; honest today.
- **required remediation**: Do NOT represent zk/ as production anywhere; build zkeys + verifier deployments in the ZK workstream (W2+).
- **verification method**: zk module unit tests; **MUST-CREATE** (future): circuit build pipeline test.

#### R-SG-08 — Primitive 5: BIBL (inter-block layer) — see also R-BT-01
- **requirement**: BIBL fills the inter-block window with behavioral intelligence: reads mempool distribution, BRT phase, ANIMA pre-manifestation signals, archetype for traffic pattern, cross-chain health, 30-day MEV patterns, validator profiles; emits user guidance, Chain Memory Instruction Signal, batch opportunities, routing with behavioral profiles, MEV warnings.
- **source**: MD §18 (canonical; conflict K6).
- **specification section**: MD §18 "BIBL Operation Cycle".
- **mathematical definition**: Operation cycle between block N confirmation and N+1 production.
- **canonical data structure**: `BIBLOutput`, `ChainMemorySignal`, `GasPreferenceProfile`.
- **canonical implementation**: `core/akashic/bibl.py` (BIBL cycle, memory instruction signal, preference profiles).
- **all implementations**: `core/akashic/bibl.py`; `core/btcp/bibl_engine.py` (per-chain BIBLAnalysis: NL, gas forecast, CC coherence, MF, capacity, finality dist — the Step-1 analysis object); `rust/src/bibl_engine.rs`; `core/akashic/bibl_pattern_store.py` (persistent patterns).
- **current compliance**: **COMPLIANT** (operation cycle + memory instruction + preference profiles; feeds BTCP Step 1).
- **deviations**: novel_primitives.md P5's fork-inheritance BIBL is a name collision — not implemented (K6).
- **security impact**: Medium (BIBL drives routing quality).
- **required remediation**: Rename P5 (spec fix, W4).
- **verification method**: `tests/test_btcp_bitp_sba_bibl.py`; `tests/unit/btcp_continuum`.

#### R-SG-09 — Primitive 6: BIRP (cross-reference)
- **requirement**: Behavioral Identity Recovery Protocol — see the full canonical entry at R-CH-03 (Domain 14).
- **source**: MD §16; novel_primitives.md P6.
- **specification section**: MD §16.
- **mathematical definition**: `BIRP_anchor = Hash_DNA(BEO_baseline ∥ Hash(DNA_Code) ∥ enrollment_timestamp ∥ behavioral_entropy_seed)` + 5-phase recovery.
- **canonical data structure**: see R-CH-03.
- **canonical implementation**: `core/novel/birp.py`.
- **all implementations**: see R-CH-03.
- **current compliance**: see R-CH-03 (COMPLIANT).
- **deviations**: see R-CH-03.
- **security impact**: Critical (identity recovery surface).
- **required remediation**: see R-CH-03.
- **verification method**: `tests/unit/trion_protocol/test_birp_dna_code.py`.

#### R-SG-10 — Primitive 7: Chameleon (cross-reference)
- **requirement**: Regulatory adaptation through behavioral form change — see the full canonical entry at R-CH-01 (Domain 14).
- **source**: MD §13 P7 + §17.
- **specification section**: MD §17.
- **mathematical definition**: 5-level threat ladder → expression mode; P7 view-consistency invariant.
- **canonical data structure**: see R-CH-01.
- **canonical implementation**: `core/novel/chameleon.py`.
- **all implementations**: see R-CH-01.
- **current compliance**: see R-CH-01 (PARTIAL).
- **deviations**: see R-CH-01.
- **security impact**: High (wrong-jurisdiction disclosure leaks sovereign/user data).
- **required remediation**: see R-CH-01.
- **verification method**: chameleon module tests; **MUST-CREATE**: view-consistency test.

#### R-SG-11 — 20-channel communication architecture
- **requirement**: Exactly 20 channels over 10 layers (MD §15 taxonomy); smart contracts used for exactly two things: signal publication (Solidity) and economic coordination (Vyper); everything else operates through the channels; critical signals on all channels; channel failures emit SYSTEMIC_RISK.
- **source**: MD §15 (canonical; conflict K14).
- **specification section**: MD §15 "The 20 Channels" + "complete map".
- **mathematical definition**: channel registry 1–20 with layer assignment.
- **canonical data structure**: `CommunicationChannel` + `CHANNELS` dict (20 entries).
- **canonical implementation**: `core/master/channel_architecture.py`.
- **all implementations**: `core/master/channel_architecture.py` (asserts exactly 20, ids 1–20; layer names match MD); `tests/golden_test.py` step 10 (20-channel verification); communication_channels.md's alternative C1–C20 transport map (supplementary).
- **current compliance**: **COMPLIANT** (registry exists, golden test verifies); **PARTIAL** for transport realism (channels are a registry + status model, not 20 live transports — e.g. channel 3 HSM entropy and channel 1 GPS/NTP physical feeds await the validator fleet).
- **deviations**: K14 taxonomy split (documented).
- **security impact**: Medium (the "no uncanonical transport" invariant is not enforced at a consensus boundary — no such boundary exists yet).
- **required remediation**: When live, enforce the discard-of-non-canonical-transport rule.
- **verification method**: `tests/golden_test.py` step 10; channel_architecture module self-test.

---

## Domain 8 — Living Security (L4)

Canonical: MD §8 (L4.1–L4.7); V2 Part 6 (8 DNA components) + L4.3–4.9.

#### R-LS-01 — Eight DNA-mimetic security components
- **requirement**: (1) Genomic Key Evolution; (2) Complementary Strand; (3) Immune System (INNATE/ADAPTIVE/MEMORY); (4) Epigenetic Layer; (5) Genetic Recombination; (6) Cryptographic Noise (decoys, noise pattern is authentication); (7) Mitochondrial Core (independent second DNA); (8) CRISPR Defense (signature library, surgical neutralization below the contract layer).
- **source**: V2 Part 6 §6.2; MD §8 (L4.3–L4.6); L4.md G1–G8 (aligned registry).
- **specification section**: V2 "The Eight DNA Security Components".
- **mathematical definition**: component-wise construction (each has its own formula below).
- **canonical data structure**: `LivingSecuritySystem{genomic, strands, crispr, epigenetic, recombination, noise, mito}`.
- **canonical implementation**: `core/spiritual/living_security/__init__.py::LivingSecuritySystem`.
- **all implementations**: `core/spiritual/living_security/__init__.py` (all 8 classes); `core/spiritual/living_security/genomic_genealogy.py`; `core/spiritual/living_security/pqc_layer.py`; `core/akashic/epigenetics.py` (persistent expression); `anima-service` crispr_adaptive.db; `tests/test_gk_living_security.py`; `tests/unit/test_whitepaper_gaps.py` (SEC/LSS/PQC tests).
- **current compliance**: **COMPLIANT** (all 8 components as classes with health checks; DD's "fabricated attack library" concern: the CRISPR library ships historical-attack signatures — labeled; live ADAPTIVE characterization 24h loop is operational only with live traffic).
- **deviations**: None structural.
- **security impact**: Critical (LSS underwrites SEC(t) and F4).
- **required remediation**: Keep the "simulated 2026 attacks" labeling (DD S8) — do not cite them as external evidence.
- **verification method**: `tests/test_gk_living_security.py`; `tests/unit/test_whitepaper_gaps.py`.

#### R-LS-02 — Genomic Key evolution
- **requirement**: `GK(entity,t) = Hash_DNA(GK(entity,t−1) ∥ BE(t) ∥ TM(t) ∥ CV(t))` (behavioral events, threat map, consensus validator state per block); dual-strand verification; stolen snapshot outdated at next block.
- **source**: MD L4.3; V2 L4.3.
- **specification section**: MD L4.3 "Genomic Key Evolution (Behavioral Causal Keys)".
- **mathematical definition**: Chained dual-strand hash.
- **canonical data structure**: `GenomicKey` + `GenomicKeyEvolver`.
- **canonical implementation**: `core/spiritual/living_security/__init__.py::GenomicKeyEvolver`.
- **all implementations**: same file; `core/spiritual/living_security/genomic_genealogy.py` (lineage); `tests/test_gk_living_security.py`; `tests/master_formula_verification.py` (L4.3).
- **current compliance**: **COMPLIANT** (chaining formula exact; per-block evolution schedule runs when blocks flow).
- **deviations**: None.
- **security impact**: Critical.
- **required remediation**: None.
- **verification method**: `tests/test_gk_living_security.py`.

#### R-LS-03 — CRISPR Defense (pre-execution interception)
- **requirement**: Exact attack signatures permanently stored; incoming transaction matching a signature is surgically neutralized BEFORE execution — below the smart contract layer; legitimate transactions proceed; bytecode never changes.
- **source**: MD L4.6; V2 Part 6 component 8.
- **specification section**: MD L4.6 "CRISPR Defense".
- **mathematical definition**: signature match → intercept.
- **canonical data structure**: `AttackSignature` + `CRISPRDefense` (cross-chain attack library, adaptive DB).
- **canonical implementation**: `core/spiritual/living_security/__init__.py::CRISPRDefense`.
- **all implementations**: CRISPRDefense; `anima-service/crispr_anomaly.py` (pattern matching; original repo file); `akashic/crispr_adaptive.db` (persistence); `contracts/solidity/TRIONFirewall.sol` (on-chain analog).
- **current compliance**: **PARTIAL** — signature matching + library real; true pre-execution mempool interception requires a live mempool feed (indexers poll RPCs post-block; no mempool subscription).
- **deviations**: Interception point is post-observation, not pre-execution.
- **security impact**: High (the "contract that cannot be attacked" claim rests on pre-execution).
- **required remediation**: Mempool subscription channel (C7) when live RPCs are available; until then label CRISPR as detection-grade.
- **verification method**: `tests/test_gk_living_security.py` (signature match tests); **MUST-CREATE**: mempool interception test (toolchain-gated).

#### R-LS-04 — SEC(t) combined security + PQC
- **requirement**: `SEC(t) = LSS(t)·PQC(t)·CC(t)`; PQC = CRYSTALS suite (Kyber + Dilithium + SPHINCS+); CC = SHA-3, AES-256, ZK; all three layers required.
- **source**: MD L4.7; V2 L4.3-4.6 combined security.
- **specification section**: MD L4.7 "Living Security Score".
- **mathematical definition**: Product of three sub-scores; `P(break SEC) = P(LSS)·P(PQC)·P(CC)`.
- **canonical data structure**: `PQCScore`, `ClassicalCryptoScore`, SEC result.
- **canonical implementation**: `core/spiritual/living_security/__init__.py` (sec functions) + `pqc_layer.py`.
- **all implementations**: `core/spiritual/living_security/pqc_layer.py`; `tests/unit/test_whitepaper_gaps.py` (test_pqc_all_schemes_active, test_pqc_nist_levels, test_sec_product_formula, test_sec_range).
- **current compliance**: **PARTIAL** — formula and scheme registry complete; PQC crypto itself depends on optional kyber-py/dilithium-py (absent in sandbox — 4 tests skip; environmental, pre-proven).
- **deviations**: None (optional-dependency boundary documented).
- **security impact**: High (quantum-resistance claim).
- **required remediation**: Install PQC libs in CI image so the 4 tests run.
- **verification method**: `tests/unit/test_whitepaper_gaps.py` PQC block (currently env-skipped).

#### R-LS-05 — Security bootstrap protocol
- **requirement**: `bootstrap_weight(t) = e^(−λ_boot·D(t))`; `SEC_boot = w·SEC_classical + (1−w)·SEC_living`; classical = multi-sig 7-of-12 + rate limit + human oversight; at D_minimum living security fully active, classical retired; transition permanently logged.
- **source**: V2 L4.7; MD L2.1 (bootstrap behavior: multi-sig 7-of-12 + human oversight until D_minimum).
- **specification section**: V2 L4.7 "Security Bootstrap Protocol".
- **mathematical definition**: Exponential decay of classical weight with depth.
- **canonical data structure**: `bootstrap_weight(D)` function + transition log.
- **canonical implementation**: `core/spiritual/living_security/__init__.py::bootstrap_weight/sec_bootstrap`; `core/akashic/depth.py::bootstrap_weight`.
- **all implementations**: both files; `core/governance/awa.py` (bootstrap weight for governance).
- **current compliance**: **COMPLIANT** (formula + λ values); **PARTIAL** for the 7-of-12 multi-sig classical layer (not instantiated as an actual multisig contract in the current deployment path).
- **deviations**: 7-of-12 multisig wrapper MISSING.
- **security impact**: Medium (during bootstrap, classical protections are the actual control).
- **required remediation**: Instantiate a 7-of-12 multisig authority for the bootstrap phase or document its deferral.
- **verification method**: `tests/unit/test_whitepaper_gaps.py` (bootstrap weight decay test).

#### R-LS-06 — Conscious plane (K) — human annotation network
- **requirement**: `K(t) = human_annotation_score × stake_weight × temporal_consistency`; 5 annotators per review, 3-of-5 majority; pseudonymous identities; 12-month terms (max 24); commit-reveal voting; 6 anti-capture protections; K CANNOT override Akashic record or reverse settled transactions.
- **source**: MD L4.2; V2 (K plane in 2.2).
- **specification section**: MD L4.2 "Conscious Plane (K)".
- **mathematical definition**: Annotated K score.
- **canonical data structure**: annotation records → K plane value.
- **canonical implementation**: `core/spiritual/conscious/engine.py`.
- **all implementations**: `core/spiritual/conscious/engine.py`; `core/spiritual/conscious/indigenous_knowledge.py` (+ anima-service/indigenous_knowledge.db); `core/spiritual/conscious/` (K plane served to api via FAISS service); `api/app.py::_get_k_plane`.
- **current compliance**: **PARTIAL** — K computation and indigenous-knowledge interface exist; the annotation *network* (5-annotator, 3-of-5, commit-reveal, term limits) is not deployed (no human annotators; BTCP spec itself flagged Σ/K/A as fixed-value stubs in the pre-rebrand repo — current code sources them from live services, but they remain bootstrap-grade).
- **deviations**: Annotation governance MISSING (people, not code).
- **security impact**: Medium (K weight is 0.05–0.25 depending on profile).
- **required remediation**: Deploy annotation interface + commit-reveal contract (W3/M scope) or set δ=0 profiles honestly until then.
- **verification method**: `tests/unit/test_all_planes.py`; **MUST-CREATE**: commit-reveal annotation contract tests.

#### R-LS-07 — Immune system three layers
- **requirement**: INNATE (pattern match against Adaptive Threat Library <1 block); ADAPTIVE (characterize new attack → counter-response → add signature, ≤24h); MEMORY (permanent, never decays; every attack survived remembered).
- **source**: MD L4.4; V2 Part 6 component 3.
- **specification section**: MD L4.4 "Living Immune System".
- **mathematical definition**: 3-layer architecture with time bounds.
- **canonical data structure**: threat library + adaptive queue.
- **canonical implementation**: CRISPR + immune modules in `core/spiritual/living_security/__init__.py` (INNATE/ADAPTIVE/MEMORY phases) + `anima-service/crispr_adaptive.db`.
- **all implementations**: same; L4.md G3 (immune trained on L1.2 fingerprints — implemented as fingerprint→signature feed).
- **current compliance**: **COMPLIANT** (layers + persistence); the 24h characterization bound is operational (needs live attacks).
- **deviations**: None.
- **security impact**: High (F4-adjacent).
- **required remediation**: None.
- **verification method**: `tests/test_gk_living_security.py`.

#### R-LS-08 — Seven-plane coherence variant
- **requirement**: BTCP §7.1's sensing-oracle output carries `plane_results: [TRUE/FALSE × 7 planes]` — a 7-plane coherence check distinct from the five-plane C(t).
- **source**: BTCP §7.1 (BTCP governs).
- **specification section**: BTCP §7.1 BEHAVIORAL_TRUTH_SIGNAL.
- **mathematical definition**: 7 boolean plane results.
- **canonical data structure**: plane_results array.
- **canonical implementation**: `core/planes/seven_plane_coherence.py`.
- **all implementations**: `core/planes/seven_plane_coherence.py`.
- **current compliance**: **PARTIAL** (7-plane module exists; the sensing-oracle signal that consumes it is ZK-gated research — see R-BT-14).
- **deviations**: The 7 planes' identities are an engineering extension (spec lists 5 canonical planes + 7 check planes without enumeration).
- **security impact**: Medium.
- **required remediation**: Enumerate the 7 planes in spec.
- **verification method**: `tests/unit/test_all_planes.py`.

---

## Domain 9 — ANIMA (L3)

Canonical: MD §7 (L3.1–L3.4); V2 Part 8 + L3.1–L3.7.

#### R-AN-01 — ANIMA score A(t)
- **requirement**: `A(t) = PCR(t)·HA(t)·CA(t)`; PCR = pattern coherence ratio; HA = rolling 90-day accuracy (HA<0.70 flagged; HA<0.60 → A=0 disabled until recalibrated); CA = credibility-weighted cross-source agreement.
- **source**: MD L3.1; V2 L3.3.
- **specification section**: MD L3.1 "ANIMA Score"; V2 L3.3.
- **mathematical definition**: Product of three sub-scores; output ENFORCED as probability distribution (never point prediction).
- **canonical data structure**: `ANIMADistribution{type: PROBABILITY_DISTRIBUTION, mean, std_dev, CI_95, calibration}`; `HATracker`.
- **canonical implementation**: `core/mental/anima/engine.py::ANIMAEngine`.
- **all implementations**: `core/mental/anima/engine.py`; `anima-service/anima_engine.py` (service-plane); `api/app.py` A-plane query; `tests/master_formula_verification.py` (L3.3); `tests/test_anima_stress_1000.py`.
- **current compliance**: **COMPLIANT** (formula, HA gates, distribution-only output type).
- **deviations**: L3.md's PCR/HA/CA definitions differ in detail (Predictive Coherence Ratio etc.) — V2 wins.
- **security impact**: High (A plane weight up to 0.30).
- **required remediation**: None.
- **verification method**: `tests/master_formula_verification.py`; `tests/test_anima_stress_1000.py`.

#### R-AN-02 — Data sources (1 000+ concurrent crawlers, 50+ languages)
- **requirement**: Onchain + structured offchain (SEC EDGAR Form 4/8-K/13F, patents, MAS/FCA/ESMA/CFTC filings, hiring, M&A, transcripts) + unstructured NLP 50+ languages (repos, preprints, forums, news) + biological/ecological (BC, XSL, BRT).
- **source**: MD §7 L3.1 data sources; V2 Part 8.2.
- **specification section**: MD L3.1 "Data sources (1,000+ concurrent crawlers)".
- **mathematical definition**: n/a (coverage requirement).
- **canonical data structure**: `CrawlerSpec` registry.
- **canonical implementation**: `anima-service/crawler_pool.py::CrawlerPool`.
- **all implementations**: `anima-service/crawler_pool.py` (workers scale to 1000, default 50 — honest); `core/mental/anima/sec_edgar_fetcher.py`; `core/mental/anima/data_sources/`; `anima-service/multilingual_sentiment.py`; live crawlers per DD: SEC EDGAR, GitHub, arXiv, RSS, GDELT (5-6 real fetchers).
- **current compliance**: **PARTIAL** — real crawlers exist for the 5-6 core sources; "1 000+ concurrent" is a capacity target (pool scales), not a deployed count; 50+ languages covered by the multilingual sentiment module's design.
- **deviations**: Volume claims unverifiable (DD) — keep honest counts.
- **security impact**: Low direct; feeds A(t).
- **required remediation**: Publish real crawler counts in ops dashboards.
- **verification method**: `tests/test_anima_stress_1000.py` (1000-crawler stress); live ingestion `tests/integration/test_anima_live_ingestion.py`.

#### R-AN-03 — Observer effect correction
- **requirement**: `OE_factor = corr(signal_publication(t−1), behavioral_change(t))`; `M_adj = M_base·(1−OE_factor)`; `A_adj = A·(1−β_reflexivity·ANIMA_reflexivity)`; reflexivity flag to consumers ("this signal type may partially self-fulfill").
- **source**: MD L3.2; V2 L3.2/L3.5.
- **specification section**: MD L3.2 "Observer Effect Correction".
- **mathematical definition**: Correlation-based discount; OE published with every signal.
- **canonical data structure**: OE float + reflexivity_flag in TRIONSignal.
- **canonical implementation**: `core/mental/anima/reflexivity.py`; `core/master/coherence.py::apply_oe_to_m`.
- **all implementations**: `core/mental/anima/reflexivity.py`; `core/master/coherence.py`; `anima-service/nl_score_engine.py::apply_oe_correction` (BTCP layer Gap G); rust router OE correction; `tests/master_formula_verification.py` (L3.2).
- **current compliance**: **COMPLIANT** (formula + flag; BTCP Gap G applied at routing layer).
- **deviations**: None.
- **security impact**: High (F11: prevents circular reinforcement of TRION's own predictions).
- **required remediation**: None.
- **verification method**: `tests/master_formula_verification.py` (L3.2/L3.5); F11 registry monitor.

#### R-AN-04 — Source credibility evolution
- **requirement**: `CRED(source,t) = CRED(t−1)·α_decay + verification_events·β_update`, α_decay=0.99/day; deltas +1.0 verified / −2.0 falsified / −3.0 manipulation / −5.0 conflict-of-interest; CRED<0.30 flagged human review; <0.10 excluded from CA.
- **source**: MD L3.3; V2 L3.4.
- **specification section**: MD L3.3; V2 L3.4.
- **mathematical definition**: Decaying credibility ledger with event deltas.
- **canonical data structure**: per-source CRED record.
- **canonical implementation**: `core/mental/anima/source_credibility.py`.
- **all implementations**: `core/mental/anima/source_credibility.py`; L3.md's EMA form (ρ=0.05) is a variant — V2 wins.
- **current compliance**: **COMPLIANT** (α=0.99, all four deltas, flag/exclude thresholds).
- **deviations**: None.
- **security impact**: Medium (gaming ANIMA via fake sources).
- **required remediation**: None.
- **verification method**: `tests/master_formula_verification.py` (L3.4).

#### R-AN-05 — Intelligence maintenance protocol
- **requirement**: `IM = Accuracy(t)/Accuracy(t_baseline)`; IM < threshold triggers automatically (retrain / recalibrate / evolutionary replacement); 24h max; falsified if degradation undetected/uncorrected beyond 24h (F7).
- **source**: MD L0.6; V2 L3.7.
- **specification section**: MD L0.6 "Intelligence Maintenance Protocol"; V2 L3.7.
- **mathematical definition**: Ratio-based degradation detector with 24h SLA.
- **canonical data structure**: IM record per component.
- **canonical implementation**: `core/mental/intelligence_maintenance.py`; `core/governance/intelligence_maintenance.py`.
- **all implementations**: both files; `tests/master_formula_verification.py` (L0.6).
- **current compliance**: **PARTIAL** (trigger logic exists; "evolutionary engine generates replacement component" (Option 3) is research-grade).
- **deviations**: Option 3 MISSING (evolutionary component generation).
- **security impact**: Medium (silent degradation = stale truth).
- **required remediation**: Implement replacement-generation or spec-note Options 1–2 as the operational set.
- **verification method**: `tests/master_formula_verification.py`; F7 monitor.

#### R-AN-06 — Evolutionary fitness function (Love constraint)
- **requirement**: `F(component,t) = PA·ICE·AS·Love`; F=0 if Love=0 regardless of other factors; PA/ICE/AS definitions per spec.
- **source**: MD L0.6; V2 L0.6.
- **specification section**: MD L0.6.
- **mathematical definition**: Multiplicative fitness with hard zero on Love=0.
- **canonical data structure**: F score per component.
- **canonical implementation**: `core/primitives/evolutionary_fitness.py`.
- **all implementations**: `core/primitives/evolutionary_fitness.py`; `core/governance/love_protocol.py` (Gratitude adjacent); `tests/master_formula_verification.py` (L0.6 incl. Love=0 case).
- **current compliance**: **COMPLIANT** (hard-zero invariant tested).
- **deviations**: L0.md's PA/ICE/AS meanings differ (Persistence Adaptation etc.) — non-canonical.
- **security impact**: Low (philosophical constraint; also F7-adjacent).
- **required remediation**: None.
- **verification method**: `tests/master_formula_verification.py`.

---

## Domain 10 — Validator consensus (DW-BFT, HHI, quorum, epochs, rotation, slashing)

Canonical: MD §8 L4.1; V2 Part 9 + L4.1/L4.2/L4.8/L4.9; BTCP §12.2.

#### R-VC-01 — Diversity weight d_j and effective stake
- **requirement**: `d_j = 1 − corr(M_j, M̄)`; `w_j_effective = s_j·d_j`; recomputed every epoch from behavioral hashes.
- **source**: MD L4.1; V2 L4.1/9.1.
- **specification section**: MD L4.1; V2 9.1 "Core Innovation".
- **mathematical definition**: Pearson correlation of validator model-output vectors vs the (median — MD; mean — L4.md) reference.
- **canonical data structure**: `DiversityResult{validator_id, stake, diversity_weight, correlation, effective_weight}`.
- **canonical implementation**: `core/spiritual/consensus.py` (Python reference), `validator/internal/p2p/consensus.go::ComputeDiversityWeight`.
- **all implementations**: `core/spiritual/consensus.py`; `core/spiritual/sigma_engine.py::compute_diversity_weight`; Go consensus.go + mesh.go (MeshDiversityWeight variant for geo/client); rust proof certs carry d_j list.
- **current compliance**: **COMPLIANT** (arithmetic exact; median per MD used in Python; note L4.md's P_j = stake·(1+δ·d_j) bonus form is a reward-side variant — see R-VC-06).
- **deviations**: Median-vs-mean reference differs across docs (K7 family); code uses median (MD-correct).
- **security impact**: Critical.
- **required remediation**: None.
- **verification method**: `tests/unit/trion_protocol/test_consensus_bft.py`; Go engine/mesh tests.

#### R-VC-02 — Σ(t) aggregation with dynamic consensus window
- **requirement**: `Σ(t) = Σ_j[s_j·d_j·𝟙(|v_j−v̄|≤δ(t))]/Σ_j[s_j·d_j]` with `δ(t) = δ_base·(1+V(t))` (high volatility → wider window).
- **source**: V2 L4.1-4.2 (MD silent on δ → V2 wins).
- **specification section**: V2 L4.1-4.2.
- **mathematical definition**: Windowed consensus fraction of effective stake.
- **canonical data structure**: `BFTConsensusResult{sigma, consensus_value, consensus_window, safety_holds, ...}`.
- **canonical implementation**: `core/spiritual/sigma_engine.py::compute_sigma`.
- **all implementations**: `core/spiritual/sigma_engine.py`; `core/spiritual/consensus.py`; Go `validator/internal/p2p/consensus.go::ComputeSigma`; api `_get_sigma_plane`.
- **current compliance**: **COMPLIANT** (δ_base=0.10, volatility-scaled).
- **deviations**: None.
- **security impact**: Critical.
- **required remediation**: None.
- **verification method**: `tests/unit/trion_protocol/test_consensus_bft.py`; Go tests.

#### R-VC-03 — Quorum and block finality
- **requirement**: 2/3 diversity-weighted threshold (Tendermint-family, instant finality); a block requires Q_required of weighted power; the Go engine uses STRICT >2/3 (3·power > 2·total).
- **source**: MD L2.1 (TRION-BFT, 2/3 diversity-weighted); V2 L4.2 quorum tiers; Go engine strictness (engineering strengthening).
- **specification section**: MD L2.1 "Consensus"; V2 L4.2.
- **mathematical definition**: Weighted supermajority.
- **canonical data structure**: quorum check in engine.
- **canonical implementation**: `validator/internal/consensus/engine.go` (Tendermint state machine: NewHeight→Propose→Prevote→Precommit→Commit; lock-on-precommit; view change; evidence).
- **all implementations**: Go engine (+ `engine_test.go`: TestExactlyTwoThirdsPrecommitsDoNotCommit, view-change, deterministic replay, proposer frequency ∝ power); `validator/internal/p2p/mesh.go` (legacy ≥2/3 attestation layer, disclosed as older/floats); contracts `TRIONOracleV3.quorumRequired = 2` signatures.
- **current compliance**: **PARTIAL** — the engine is real and tested, but no live network; on-chain oracle quorum is a 2-signature bootstrap value (not the full validator-set supermajority).
- **deviations**: On-chain quorumRequired=2 is a bootstrap configuration, not a spec deviation per se (the route-attestation path now requires distinct validator signatures in ascending order — S3/C2 fix).
- **security impact**: Critical (DD S4: "no consensus implementation behind the consensus-only-oracle claim" — now mitigated by the Go engine + signature-verified attestations, but the fleet is absent).
- **required remediation**: Deploy the fleet; raise on-chain validatorCount; keep signature-verified release path.
- **verification method**: `validator/internal/consensus/engine_test.go` (8 engine tests incl. boundary quorum); `tests/contracts/test_btcp_escrow_sol.py`.

#### R-VC-04 — HHI enforcement tiers + geographic constraints
- **requirement**: `HHI = Σ_j (s_j·d_j/Σ s_k·d_k)² × 10000`; <1500 HEALTHY; 1500–2500 WARNING (2× reward underrepresented); 2500–4000 DANGER (weight cap, no cluster >15%); >4000 CRITICAL (consensus paused, governance emergency); N_continents ≥ 4; max region < 0.40; max jurisdiction < 0.30; automatic incentive for underrepresented regions.
- **source**: MD L4.1 "HHI Enforcement"; V2 L4.8.
- **specification section**: MD L4.1; V2 L4.8.
- **mathematical definition**: Effective-stake HHI ×10 000 + geographic constraints.
- **canonical data structure**: `ValidatorStake{effective_stake, region, jurisdiction}` → tier.
- **canonical implementation**: `core/spiritual/hhi_monitor.py`.
- **all implementations**: `core/spiritual/hhi_monitor.py`; Go `mesh.go` HHI check; `core/spiritual/consensus.py` hhi field; rust verify_proof scale-normalized HHI parity (Task 20 d031d62); `tests/master_formula_verification.py` (L4.8).
- **current compliance**: **COMPLIANT** (all thresholds, tiers, caps, geographic constants 0.40/0.30/4).
- **deviations**: L4.md's 0–1-scale HHI_geo/HHI_infra supplementary (K11).
- **security impact**: Critical (F8/F9).
- **required remediation**: None (add infra-HHI as documented extension).
- **verification method**: `tests/master_formula_verification.py`; Go mesh tests; rust parity tests.

#### R-VC-05 — Epochs and validator rotation
- **requirement**: Diversity recomputed every epoch (V2 L4.2 invariant); L4.md adds G1 rotation every 365 epochs, recombination every 30 epochs; seasonal recombination enforced (L6.md R4).
- **source**: V2 L4.2 ("Diversity is recomputed every epoch"); L4.md/L6.md (subordinate detail).
- **specification section**: V2 L4.2 invariants.
- **mathematical definition**: Per-epoch recompute; periodic key events.
- **canonical data structure**: epoch counters in registry.
- **canonical implementation**: `core/spiritual/validator_registry.py` + Go engine height/round state.
- **all implementations**: `core/spiritual/validator_registry.py` (registry ops, tests in test_validator_registry.py); Go engine (per-height rounds); living_security recombination interval (86400s — daily, not 30-epoch).
- **current compliance**: **PARTIAL** — per-epoch diversity recompute happens with data flow; 365-epoch G1 rotation and 30-epoch recombination schedules are not enforced timers (recombination is time-interval based).
- **deviations**: Rotation schedule unenforced.
- **security impact**: Medium (long-lived keys without rotation).
- **required remediation**: Enforce G1 rotation timer in the validator lifecycle.
- **verification method**: `tests/unit/trion_protocol/test_validator_registry.py`; **MUST-CREATE**: rotation-timer test.

#### R-VC-06 — Reward structure (diversity paid)
- **requirement**: `REWARD = BASE × accuracy_factor × diversity_factor × uptime_factor × (1−slashing_penalty)`; `diversity_factor = 1 + γ_diversity·d_j` (validators paid to be independent); plus BTCP coverage bonus and route reward 60/40 anchor/execution split.
- **source**: V2 9.3; BTCP §11 Fix 4.
- **specification section**: V2 9.3 "Reward Structure"; BTCP Fix 4.
- **mathematical definition**: Multiplicative reward with explicit diversity term.
- **canonical data structure**: reward computation per validator per period.
- **canonical implementation**: `core/btcp/modules.py::ValidatorFeeCalculator` (coverage bonus + rarity + 60/40 split + cost offset).
- **all implementations**: `core/btcp/modules.py::ValidatorFeeCalculator`; rust `validator_fee_calculator.rs`; Go `consensus.go` DiversityGamma=0.20 constant; api `POST /api/v1/btcp/validator_fee`.
- **current compliance**: **COMPLIANT** (coverage bonus formula, rarity, volume, uptime, 60/40 split; V2's base signal reward × diversity factor present in Go constants and staking contract hooks).
- **deviations**: None.
- **security impact**: High (incentive design is the Nash equilibrium enforcement).
- **required remediation**: None.
- **verification method**: `tests/btcp/test_btcp_api_surface.py` (exact fee math: rarity 2.0/3.33, bonus 451.33, 600/400 split); rust fee tests.

#### R-VC-07 — Slashing conditions and dispute resolution
- **requirement**: V2 L4.9 five conditions: COORDINATED_ATTACK_CONFIRMED 50% + permanent exclusion; SUSTAINED_LOW_ACCURACY 3%/30-day; HARDWARE_SECURITY_FAILURE 10%; UPTIME_FAILURE 0.1%/day; SYBIL_CLUSTER_CONFIRMED 25% all in cluster; δ-window exclusion ≠ slash; dispute: notification + evidence, 72h challenge window, challenge bond, review by 3 validators + 1 human council, reverse-or-stand, all logged in Akashic.
- **source**: V2 L4.9; MD (silent → V2 wins); L4.md S1–S6 supplementary (K12).
- **specification section**: V2 L4.9.
- **mathematical definition**: Percentage registry + dispute flow.
- **canonical data structure**: `SlashType` enum + `SlashDecision` + dispute records.
- **canonical implementation**: `core/spiritual/slashing.py` (conditions) + `core/governance/slashing.py` (7-step dispute flow).
- **all implementations**: `core/spiritual/slashing.py`; `core/governance/slashing.py` (irreversible step-6 per semi-immutability); Go `validator/internal/consensus/slashing.go` (evidence-based, 313 LOC, double-signing + liveness); `contracts/vyper/TRIONStaking.vy` + `TRIONToken.vy::slash_validator` (on-chain execution, 50% insurance/50% burn); `tests/unit/trion_protocol/test_governance_modules.py`.
- **current compliance**: **COMPLIANT** (all five conditions with exact percentages; 72h window; bond 5%; dispute chain; on-chain slash execution exists).
- **deviations**: L4.md S1–S6 partially overlapping (double-sign 100% exists only in Go path); TRIONStaking "7-type" comment vs 5 canonical — docs drift (K12).
- **security impact**: Critical (slashing is the enforcement teeth).
- **required remediation**: Unify the three slash registries into one table in W4 docs.
- **verification method**: `tests/unit/trion_protocol/test_governance_modules.py`; Go slashing tests; `tests/contracts/test_btcp_escrow_vy.py`.

#### R-VC-08 — Validator hardware and fleet minimums
- **requirement**: 32+ cores EPYC/Xeon, 256GB DDR5 ECC, 10TB NVMe, A100/H100, 10Gbps, HSM Thales Luna 7 / YubiHSM 2 (NON-NEGOTIABLE); ≥100 validators across ≥4 continents at launch; 12-month terms; N_continents ≥ 4 at all times.
- **source**: MD §21 (validator node minimum requirements); V2 9.2.
- **specification section**: V2 9.2 "Validator Hardware Requirements"; MD §21.
- **mathematical definition**: n/a (ops requirements).
- **canonical data structure**: validator onboarding spec.
- **canonical implementation**: — (fleet not deployed; HSM abstraction flagged by DD as env-mode only).
- **all implementations**: `core/spiritual/validator_registry.py` (registry only); relayer KMS abstraction (DD S7: broken beyond env mode).
- **current compliance**: **MISSING** (no validator onboarding, staking fleet, or HSM attestation — DD C10 "Not started").
- **deviations**: None (absence, not deviation).
- **security impact**: Critical (all consensus guarantees are conditional on the fleet).
- **required remediation**: Fleet deployment program (Wave 3/O); HSM attestation in onboarding; fix relayer KMS beyond env mode.
- **verification method**: **MUST-CREATE**: onboarding conformance test (hardware attestation fields); live fleet integration run.

---

## Domain 11 — Oracle publication (on-chain truth layer)

Canonical: BTCP §14.3 (escrow's oracle interface), §2 (existing TRIONOracleV3 audit); MD §15 (contracts are output-only).

#### R-OP-01 — publishBehavioralTruth (sensing oracle)
- **requirement**: Publish the behavioral truth signal on-chain: (entityId, publicCommitment, coherenceScore, threshold, coherent, limitingPlane) with BehavioralTruth / SilenceSignal events; only authorized relayers; SILENCE formally recorded with gap.
- **source**: BTCP §7.1/§14.2 (BEHAVIORAL_TRUTH_SIGNAL); repo contract surface.
- **specification section**: BTCP §7.1 (BEHAVIORAL_TRUTH_SIGNAL); BTCP §2 file map (TRIONSensingOracle).
- **mathematical definition**: coherence ≥ threshold ⇒ coherent; ×1e6 fixed-point.
- **canonical data structure**: `Signal{entityId, publicCommitment, coherenceScore, threshold, coherent, limitingPlane, blockNumber}`.
- **canonical implementation**: `contracts/solidity/TRIONSensingOracle.sol::publishBehavioralTruth`.
- **all implementations**: `contracts/solidity/TRIONSensingOracle.sol` (single + batch ≤50, relayer-gated, input validation); `api/blockchain.py` (relayer call builder, 6-arg); `api/app.py::publish_signal` (POST/GET /api/v1/publish/<entity_id>); `relayer/relayer.js`.
- **current compliance**: **COMPLIANT** (validation, events, batch, relayer ACL; API route live with real tx hashes when relay configured).
- **deviations**: Relayer trust is centralized (DD S3-family for the sensing oracle; the V3 oracle's route path now requires signature quorum — see R-OP-03).
- **security impact**: High (this is the on-chain truth interface).
- **required remediation**: Migrate sensing-oracle publication to the same signature-verified attestation discipline as TRIONOracleV3.
- **verification method**: `tests/contracts/` hardhat suite; api smoke tests in worklog Task 21-a (13/13).

#### R-OP-02 — publishBehavioralSignal / full signal etching
- **requirement**: Publish the full BehavioralSignal on-chain (C(t), Θ, gap, limiting plane, CI bounds) with SilenceRecorded/V2 events; structured-null payload etched for indexers.
- **source**: BTCP §2 (TRIONOracleV3 responsibilities).
- **specification section**: BTCP §2 "TRIONOracleV3.sol — C(t) signal publication".
- **mathematical definition**: on-chain ×1e6 encoding; V1 + V2 silence events.
- **canonical data structure**: `BehavioralSignal` struct + events.
- **canonical implementation**: `contracts/solidity/TRIONOracleV3.sol::publishBehavioralSignal`.
- **all implementations**: `contracts/solidity/TRIONOracleV3.sol` (+ `hardhat/contracts/` deployment twin, `evm-tools/compiled/TRIONOracleV3.json`); `cairo/src` port.
- **current compliance**: **COMPLIANT** (input validation: plane ≤4, ranges, silence events V1+V2).
- **deviations**: None.
- **security impact**: High.
- **required remediation**: None.
- **verification method**: hardhat tests; `scripts/phase7_contract_verify.py`.

#### R-OP-03 — publishSignal quorum + BTCP route attestations (on-chain gates)
- **requirement**: On-chain etching must be gated by validator evidence: publishSignal requires ≥quorumRequired ECDSA signatures; publishBTCPRoute requires a supermajority of the live validator set with distinct, ascending-order signers; freshness only refreshable by NEW distinct attestations.
- **source**: MD §15 (contracts output-only, backed by consensus); BTCP §14.3 ("TRION consensus is the only oracle"); BTCP §10 Gap B/C.
- **specification section**: BTCP §14.3 escrow release discipline; repo S3/C2/M2 fixes.
- **mathematical definition**: `signatures.length ≥ quorumRequired`; route attestations ≥ minRouteAttestations(validatorCount); signer set distinct + sorted.
- **canonical data structure**: signature arrays + `BTCPRoute{anchorBH, executionBH, coherence, threshold, settledAt, ...}`.
- **canonical implementation**: `contracts/solidity/TRIONOracleV3.sol::publishSignal` + `submitRouteAttestation`.
- **all implementations**: TRIONOracleV3.sol (MessageHashUtils inlined; eth-signed message hashing; validator registry); `contracts/solidity/BTCPEscrow.sol` (route binding + releaseEscrow requires verified route).
- **current compliance**: **COMPLIANT** (the DD S3 "caller-supplied coherence" finding is remediated: release now requires a signature-verified route verdict; quorumRequired=2 is the bootstrap floor — flagged in R-VC-03).
- **deviations**: quorumRequired=2 (bootstrap; not ≥2/3 of 100 validators — fleet absent).
- **security impact**: Critical (single-key publication = falsifiable truth).
- **required remediation**: Raise on-chain quorum with the fleet; keep the ascending-distinct-signer invariant.
- **verification method**: `tests/contracts/test_btcp_escrow_sol.py`; hardhat TRIONExecutionGate tests.

#### R-OP-04 — Freshness windows
- **requirement**: Route safety verdicts expire: BTCP_ROUTE_FRESHNESS_SECONDS = 300; escrow may only release within the freshness window; signal TTL bounds on-chain (≤30 epochs non-critical / ≤90 critical per signal_types.md).
- **source**: BTCP §14.3 (escrow release timing); repo freshness fix; signal_types.md invariant.
- **specification section**: BTCP §14.3 + signal emission rules.
- **mathematical definition**: `block.timestamp − route.settledAt ≤ 300s` for release eligibility.
- **canonical data structure**: settledAt + freshness constant.
- **canonical implementation**: `contracts/solidity/TRIONOracleV3.sol` (BTCP_ROUTE_FRESHNESS_SECONDS=300, M2 fix: only new distinct attestations refresh).
- **all implementations**: TRIONOracleV3.sol; `BTCPEscrow.sol` release path; `contracts/vyper/BTCP_ESCROW.vy` (release via verifyExecution route verdict).
- **current compliance**: **COMPLIANT** (300s window enforced; freshness refresh discipline fixed).
- **deviations**: signal TTL (30/90 epoch) not enforced in the Solidity signal store (ttl field absent on-chain).
- **security impact**: High (stale verdict replay).
- **required remediation**: Add expiry to the on-chain BehavioralSignal store.
- **verification method**: hardhat tests; **MUST-CREATE**: stale-verdict-rejection test.

---

## Domain 12 — BTCP (Behavioral Transaction Continuity Protocol)

Canonical: BTCP_SPEC.txt governs absolutely; MD L1.1/§18 for BTCP_score and BIBL.

#### R-BT-01 — Step 1: BIBL analysis (intent registration)
- **requirement**: On intent submission, BIBL activates in the inter-block window reading all integrated chains simultaneously, producing `BIBLAnalysis{chain_id, nl_score, gas_forecast(CI_95), cc_coherence, beo_state, mf_score, block_capacity, finality_dist}` per chain.
- **source**: BTCP §4.2 Step 1.
- **specification section**: BTCP §4.2 "Step 1 — Intent Registration and BIBL Analysis".
- **mathematical definition**: Per-chain analysis vector.
- **canonical data structure**: `BIBLAnalysis` (rust) / per-chain state in `core/btcp/bibl_engine.py`.
- **canonical implementation**: `core/btcp/orchestrator.py` Step 1 (wired to real anima APIs: forecast_gas, predict_optimal_window, JurisdictionRegistry — Task 20 commit 73d5e9e, 6/6 legs).
- **all implementations**: `core/btcp/orchestrator.py`; `core/btcp/bibl_engine.py`; `rust/src/bibl_engine.rs`; `rust/src/btcp_router.rs::analyze_intent`; `anima-service/btcp_gas_forecast.py`; `anima-service/nl_score_engine.py`.
- **current compliance**: **COMPLIANT** (analysis object + real data legs).
- **deviations**: None.
- **security impact**: High (routing quality root).
- **required remediation**: None.
- **verification method**: `tests/btcp/test_btcp_api_surface.py` (orchestrate steps); `tests/unit/btcp_continuum`.

#### R-BT-02 — Intent object (§4.1 full field set)
- **requirement**: Intent carries: entity_id (bytes32, BEO across ALL chains); action (SWAP|TRANSFER|LIQUIDITY|STAKE|BORROW); value (uint256); asset_in/asset_out (bytes32 universal ids); constraints{deadline (uint64), max_total_gas (uint128 USD), min_finality (FAST|STANDARD|SECURE), min_NL_score (uint16 ×1000, default 0.30→300), chain_pref (OPTIMAL|[list]|SINGLE_CHAIN), privacy (PUBLIC|ZK_CREDENTIAL|INVISIBLE)}; btcp_version (semver bytes12); nonce (per-entity monotonic uint64). Registered by hash; full object off-chain in Akashic Index, referenced on-chain by `intent_hash = keccak256(abi.encode(intent))`.
- **source**: BTCP §4.1.
- **specification section**: BTCP §4.1 "Intent Object".
- **mathematical definition**: Field set + hash registration.
- **canonical data structure**: `BITPIntent` dataclass (core/btcp/modules.py) with legacy-6 + §4.1 fields; rust `Intent`/`IntentConstraints`.
- **canonical implementation**: `core/btcp/modules.py::BITPIntent` (9 §4.1 fields added, spec defaults, canonical hash) — Task 21-b commit 9583ef3.
- **all implementations**: 5 intent representations now carry the field set: (1) `core/btcp/modules.py::BITPIntent`; (2) `rust/src/types.rs::Intent/IntentConstraints` (67e51eb + mechanical literals); (3) `adapters/__init__.py::BTCPIntent` (orchestrator/crossvm — 21-e alignment); (4) `rust/src/bitp_matcher.rs::BITPIntentData` (clipboard entry, §17 proof root/nonce); (5) api layer `api/btcp_continuum_routes.py` transport fields. Contracts: `contracts/solidity/BTCPIntent.sol` (hash registry).
- **current compliance**: **COMPLIANT** after Task 21-b/21-e (field-coverage matrix all ✓ in both languages; parity pinned by static tests since cargo absent).
- **deviations**: Honest representation differences remain: rust value u128-amount vs spec uint256; rust action=string alias vs enum; rust carries BOTH legacy privacy_level and spec privacy (bridged); py btcp_version str vs typed SemVer; api min_nl_score float 0.30 vs ×1000 uint16 in private_bibl (documented in Task 21-b stage summary).
- **security impact**: High (intent is the user's enforceable commitment — missing constraint fields = unenforceable guarantees).
- **required remediation**: Unify the min_nl_score scale across api paths; make rust action a typed enum.
- **verification method**: `tests/unit/test_intent_spec_fields.py` (24 tests incl. cross-language static parity); `tests/unit/test_adapters_intent_spec_fields.py`.

#### R-BT-03 — Six-step execution sequence
- **requirement**: Step 1 BIBL analysis; Step 2 optimal route calculation (BTCP_score, route types, selection priority NETTING > SINGLE_CHAIN > SPLIT > PARALLEL > BITP > DEFERRED); Step 3 cross-chain proof construction; Step 4 VM translation layer; Step 5 gas sharing; Step 6 finalization + Akashic recording (BTCPRouteSignal).
- **source**: BTCP §4.2.
- **specification section**: BTCP §4.2 "Six-Step Execution Sequence".
- **mathematical definition**: Ordered pipeline with per-step artifacts.
- **canonical data structure**: route dict with per-step results.
- **canonical implementation**: `core/btcp/orchestrator.py::BTCPOrchestrator.create_route` (6 steps + ZK + S7 write-through to SQLite + schema.sql tables).
- **all implementations**: `core/btcp/orchestrator.py`; `rust/src/btcp_router.rs`; `api/btcp_continuum_routes.py::POST /api/v1/btcp/orchestrate` (per-step results returned); `core/btcp/state_store.py`; `tests/btcp/test_btcp_api_surface.py` (steps, proofs, persistence, restart survival).
- **current compliance**: **COMPLIANT** (all six steps, priority order, persistence verified).
- **deviations**: None.
- **security impact**: Critical (the whole cross-chain flow).
- **required remediation**: None.
- **verification method**: `tests/btcp/test_btcp_api_surface.py` (39 tests); `tests/unit/btcp_continuum` (216).

#### R-BT-04 — BTCP_score and route types
- **requirement**: `BTCP_score = [0.25·NL + 0.20·normalize_gas + 0.20·finality_conf + 0.15·CC_coherence + 0.20·BEO_continuity]·(1−MF_score)`; `normalize_gas = max(0, 1−G_total/G_99th)`; route types SingleChain/Split/Netting/Parallel/MultiHop/Deferred/BITP; highest score wins with the §4.2 priority.
- **source**: MD L1.1; BTCP §4.2 Step 2.
- **specification section**: BTCP §4.2 Step 2; MD §5 L1.1.
- **mathematical definition**: Weighted sum × manipulation discount.
- **canonical data structure**: `Route` + `RouteType` enum.
- **canonical implementation**: `rust/src/btcp_router.rs::btcp_score` (K1 resolution comment) + `core/master/btcp_score.py`.
- **all implementations**: `rust/src/btcp_router.rs`; `core/master/btcp_score.py`; `core/btcp/orchestrator.py` (route selection); `anima-service` NL/gas inputs; `tests/unit/btcp_continuum`.
- **current compliance**: **COMPLIANT** (weights exact in both languages; route-type selection incl. MultiHop).
- **deviations**: None.
- **security impact**: High (a wrong score routes value into manipulated venues).
- **required remediation**: None.
- **verification method**: `tests/master_formula_verification.py` (BTCP score); rust router tests; `tests/btcp/test_btcp_api_surface.py`.

#### R-BT-05 — BTCP proof construction
- **requirement**: `BTCPProof{anchor_bh, consensus_proof{validator_signatures s_j·d_j·sign_j(anchor_BH), diversity_cert, hhi_at_emission, coherence_score, threshold_margin}, intent_hash, btcp_route_id, anchor_chain, execution_chain, btcp_version, feature_flags, min_verifier_ver}`; chain B verifies against known TRION validator set; reorg protection window (Gap B).
- **source**: BTCP §4.2 Step 3; §10 Gap B.
- **specification section**: BTCP §4.2 Step 3 + §10 row B.
- **mathematical definition**: Attestation bundle over the anchor BH.
- **canonical data structure**: `BTCPProof`/`ConsensusProof` (core/btcp/modules.py; rust mirror).
- **canonical implementation**: `core/btcp/modules.py::BTCPProofBuilder`; `rust/src/btcp_proof_builder.rs`.
- **all implementations**: both; `core/btcp/orchestrator.py` (proof step + verification verdict, fail-closed on zk_pending); rust verify parity `d031d62` (HHI scale-normalized, ≥3 signers, distinct, 65B sigs + parity tests).
- **current compliance**: **COMPLIANT** (structure + verification discipline; py verify now matches the full rust structural contract).
- **deviations**: Signatures are structural (65B shape, distinct, sorted) — live signature-set verification on-chain is the TRIONOracleV3 path (R-OP-03).
- **security impact**: Critical (this is the "stronger than multi-sig" claim, Claim A).
- **required remediation**: None.
- **verification method**: `tests/unit/btcp_continuum` proof tests; `tests/btcp/test_btcp_api_surface.py` (fail-closed zk).

#### R-BT-06 — VM translation layer (adapters)
- **requirement**: Thin per-chain adapters translating economic intent into native execution: `ChainAdapter` trait with execute_swap/transfer/liquidity/borrow/stake + verify_execution; event mapping table (EVM Uniswap/Curve, SVM Jupiter/Orca, Cosmos Osmosis, Move Aptos DEX …); implementation priority EVM → SVM → Cosmos; unknown chains → OOA adapter (§5.2), never silent EVM default.
- **source**: BTCP §4.2 Step 4.
- **specification section**: BTCP §4.2 Step 4 "VM Translation Layer".
- **mathematical definition**: Adapter trait + per-VM event mapping.
- **canonical data structure**: `ChainAdapter` trait (rust); `adapters/__init__.py` python adapters.
- **canonical implementation**: `rust/src/adapters/evm.rs` + `adapters/__init__.py` (EVM canonical).
- **all implementations**: `rust/src/adapters/` (evm.rs, mod.rs); `adapters/__init__.py` (py adapters incl. OOA for unknown chains — Task 20 commit 037104a); VM-agnostic event layer via `core/primitives/event_types_generated.py` bindings for 18 VM families; `tests/crossvm/`; `tests/per_vm_e2e_test.py`.
- **current compliance**: **PARTIAL** — EVM adapter real; SVM/Cosmos/Move adapters are stubs/template ports per DD ("facade" tiers for deep VMs); unknown-chain OOA routing fixed.
- **deviations**: Non-EVM execution adapters not production (W2 agents G–L own these).
- **security impact**: High (DD: TON cell overflow, SVM full-balance lock in template ports — do not route value).
- **required remediation**: W2 per-VM hardening; block value-routing through non-EVM adapters until audited.
- **verification method**: `tests/crossvm/run_btcp_crossvm_full.py`; W2 per-VM test suites (MUST-CREATE per VM).

#### R-BT-07 — Gas sharing and abstraction
- **requirement**: `G_total(route) = Σ_chains [G_chain(i) × execution_fraction(i)]`; IAP per-entity share `G_per_entity = G_total × (value/total)` (value-weighted per §5.3); gas abstraction: user pays in source-chain value or TRION token; never needs execution-chain gas; coverage of execution gas natively (Gap A/J).
- **source**: BTCP §4.2 Step 5; §5.3; §10 rows A/J.
- **specification section**: BTCP §4.2 Step 5 "Gas Sharing Protocol".
- **mathematical definition**: Fraction-weighted gas sum; value-proportional shares.
- **canonical data structure**: gas forecast + share table.
- **canonical implementation**: `core/btcp/modules.py::IntentAggregator` (equal AND value-weighted per-user gas — Task 20 bef84e4); `anima-service/btcp_gas_forecast.py` (CI_95 forecast).
- **all implementations**: both; `contracts/solidity/BTCPGasAbstraction.sol`; rust `intent_aggregator.rs`; `api/btcp_continuum_routes.py::POST /netting /aggregate`.
- **current compliance**: **PARTIAL** — sharing math + forecast real; on-chain gas abstraction contract is a reference deployment (no live sponsored execution).
- **deviations**: None structural.
- **security impact**: Medium (gas metering errors = overcharge).
- **required remediation**: Live sponsored-gas pilot before production.
- **verification method**: `tests/btcp/test_btcp_api_surface.py` (aggregate equal + value-weighted); gas floor 0.05.

#### R-BT-08 — BTCP_ESCROW two-state atomicity
- **requirement**: Two states ONLY: HOLDING → RELEASED | REVERTED; `lock(intent_hash, entity_id, timeout_blocks, destination)`; `release(btcp_route_signal)` requires valid consensus proof (verifyExecution isSafe AND coherence ≥ threshold); `revert_on_timeout()`; no partial execution by design; no multi-sig, no governance — TRION consensus is the only oracle; ETH-only v1 per spec code.
- **source**: BTCP §14.3 (full Vyper spec).
- **specification section**: BTCP §14.3 "BTCP_ESCROW.vy — Full Implementation".
- **mathematical definition**: Terminal state machine.
- **canonical data structure**: `EscrowRecord{intent_hash, entity_id, amount, token, lock_block, timeout_blocks, state, destination}`.
- **canonical implementation**: `contracts/vyper/BTCP_ESCROW.vy` (spec-faithful; release permissionless but requires verified route verdict; check-effects-interactions; terminal-before-transfer).
- **all implementations**: `contracts/vyper/BTCP_ESCROW.vy`; `contracts/solidity/BTCPEscrow.sol` (499-line 6-state EVM flagship with cascade revert + 7-day emergency exit); `core/btcp/escrow_monitor.py`; `rust/src/btcp_escrow_monitor.rs`; `api/btcp_continuum_routes.py::GET /api/v1/btcp/escrow/<id>`; `tests/contracts/test_btcp_escrow_vy.py` + `test_btcp_escrow_sol.py`.
- **current compliance**: **COMPLIANT** (two-state discipline in Vyper; Solidity tier's extra states are hardened superset — documented; escrow state persisted via BtcpStateStore, 404 honest).
- **deviations**: BTCPEscrow.sol's 6-state model vs spec's 2-state minimalism (superset, audit-approved); Solidity release historically trusted caller-supplied coherence — now route-verdict-bound (S3/C2 fix).
- **security impact**: Critical (escrow atomicity = "funds never at risk" guarantee).
- **required remediation**: None (keep the verifyExecution binding on every release path).
- **verification method**: `tests/contracts/test_btcp_escrow_vy.py`; `tests/contracts/test_btcp_escrow_sol.py`; hardhat suite.

#### R-BT-09 — BITP (CUT/MATCH/PASTE)
- **requirement**: CUT: commitment `Hash_DNA(entity_id ∥ intent_hash ∥ behavioral_proof_root ∥ timestamp ∥ nonce)` posted to Akashic clipboard, asset stays on chain A, status POSTED_TO_CLIPBOARD. MATCH: complement search (asset_in↔asset_out, magnitude within behavioral_price_tolerance, different entity, unexpired) → PASTE or becomes BLO. PASTE: dual native transfers, both escrowed until confirmed; zero cross-chain movement, no bridge contract, no wrapped token. Price discovery: `exchange_rate = VALUATION(X)/VALUATION(Y)`; divergence > tolerance ⇒ match rejected.
- **source**: BTCP §5.1.
- **specification section**: BTCP §5.1 "Water Carrying Minerals — BITP".
- **mathematical definition**: Commitment/match/paste protocol.
- **canonical data structure**: `bitp_clipboard` table (schema.sql); BITPIntent + complement search.
- **canonical implementation**: `core/btcp/modules.py::BITPMatcher` (find_complement + execute_paste).
- **all implementations**: `core/btcp/modules.py::BITPMatcher`; `rust/src/bitp_matcher.rs` (BITPIntentData with proof root/nonce); `api/btcp_continuum_routes.py::POST /bitp/match` (PASTE result); `schema.sql::bitp_clipboard`; `tests/test_btcp_bitp_sba_bibl.py`.
- **current compliance**: **COMPLIANT** (phases, tolerance matching, PASTE emission, clipboard persistence).
- **deviations**: None.
- **security impact**: High (this is the lock/mint elimination claim).
- **required remediation**: None.
- **verification method**: `tests/test_btcp_bitp_sba_bibl.py`; `tests/btcp/test_btcp_api_surface.py` (bitp/match).

#### R-BT-10 — Behavioral Limit Orders (BLO)
- **requirement**: Unmatched intent becomes BLO: commitment, expiry_block, status OPEN|PARTIALLY_FILLED|FILLED|EXPIRED, filled_amount; partial fill keeps remainder as new BLO with same expiry; expiry reverts commitment with honest behavioral record (no penalty); bidder ranking `BTCP_score(bidder) × counterparty_behavioral_health`; `blo_orders` table.
- **source**: BTCP §5.5.
- **specification section**: BTCP §5.5 "Water Finding Cracks in Time".
- **mathematical definition**: Persistent order lifecycle.
- **canonical data structure**: `BehavioralLimitOrder` + `blo_orders` table.
- **canonical implementation**: `core/btcp/modules.py` BLO path (matcher fallback) + `rust/src/blo_scheduler.rs`.
- **all implementations**: `core/btcp/modules.py`; `rust/src/blo_scheduler.rs` (BRT-scheduled activation); `contracts/solidity/BehavioralLimitOrder.sol` (on-chain storage + partial fill); `contracts/vyper` BLO note; `schema.sql::blo_orders`.
- **current compliance**: **PARTIAL** — py/rust order lifecycle + scheduler real; on-chain BLO contract is reference-tier (not deployed in the live path); `blo_orders` TimescaleDB table has no writer (Task 20 gap #7 residual: schema tables btcp_* now written by orchestrator; blo/bitp/shadow/genesis tables still writer-less except clipboard in SQLite).
- **deviations**: Persistence split SQLite vs schema.sql.
- **security impact**: Medium (order book integrity).
- **required remediation**: Route BLO writes through the state store to schema.sql tables (Wave 3/D or F).
- **verification method**: `tests/unit/btcp_continuum` BLO tests; **MUST-CREATE**: `tests/unit/test_blo_persistence.py`.

#### R-BT-11 — Netting (counterparty matching)
- **requirement**: Find intent_B with `asset_in_B == asset_out_A` (opposite direction); rank by `BTCP_score × behavioral_health`; activate both escrows simultaneously; partial netting splits remainder; netting score typically 0.95–0.99 (top priority route type); zero movement.
- **source**: BTCP §4.2 route priority + §14.1 Phase 2 item 6.
- **specification section**: BTCP §14.1 netting_engine.rs.
- **mathematical definition**: Complement matching + ranking.
- **canonical data structure**: netting pair result.
- **canonical implementation**: `core/btcp/modules.py::NettingEngine` (find_netting_pair, gas floor 0.05).
- **all implementations**: `core/btcp/modules.py::NettingEngine`; `rust/src/netting_engine.rs`; `api/btcp_continuum_routes.py::POST /netting`.
- **current compliance**: **COMPLIANT**.
- **deviations**: None.
- **security impact**: High (primary value proposition).
- **required remediation**: None.
- **verification method**: `tests/btcp/test_btcp_api_surface.py` (netting happy+edge+400s).

#### R-BT-12 — Intent Aggregation Protocol (IAP)
- **requirement**: Pool ≥3 same-direction intents within window; `should_aggregate` checks direction, deadline, pool size; gas share per entity (value-weighted); privacy via ZK share proof (deferred to Phase 4 — transparent shares first); behavioral credit preserved per BEO; pool structure transparent at protocol level.
- **source**: BTCP §5.3.
- **specification section**: BTCP §5.3 "Water Pooling".
- **mathematical definition**: Pooling predicate + share math.
- **canonical data structure**: `IntentPool{direction, participants, total_value, window_deadline, min_size=3}`.
- **canonical implementation**: `core/btcp/modules.py::IntentAggregator`.
- **all implementations**: `core/btcp/modules.py::IntentAggregator`; `rust/src/intent_aggregator.rs`; `api/btcp_continuum_routes.py::POST /aggregate`; `zk-circuits/zk_iap_share_proof/` (circuit, unbuilt).
- **current compliance**: **PARTIAL** — pooling + shares real (transparent first, per spec Phase 3); ZK share proof is circuit-only (spec itself defers to Phase 4).
- **deviations**: None (spec-ordered deferral).
- **security impact**: Medium (share correctness affects billing).
- **required remediation**: ZK share proof build (W2+ ZK track).
- **verification method**: `tests/btcp/test_btcp_api_surface.py` (aggregate).

#### R-BT-13 — OOA + Shadow Observation
- **requirement**: OOA: `ooa_confidence(depth) = conf_max·(1−e^(−k·depth))` (conf_max 0.85, k 0.001); `Θ_OOA = Θ_base × ooa_penalty_factor`; OOA chains score lower in routing (integration incentive). Shadow: collect cross-chain references to hostile chain (transfers, oracle updates, bridge events, dex trades, governance refs) with confidence weights; `compute_shadow_bh` weighted Hash_DNA; ultra-light node ~80 bytes/block headers; dead-zone principle; rejoin sequence (shadow history → genesis baseline → channel 6 → full integration).
- **source**: BTCP §5.2 + §8.
- **specification section**: BTCP §5.2 "Water Through Rock"; §8 "Break-Rejoin".
- **mathematical definition**: Asymptotic confidence growth + weighted shadow hash.
- **canonical data structure**: `OOAConfig`; `ShadowSource` list.
- **canonical implementation**: `core/btcp/modules.py::OOAAnchor` + `ShadowObserver`.
- **all implementations**: `core/btcp/modules.py` (both classes); `rust/src/ooa_anchor.rs`; `rust/src/shadow_observer.rs`; `adapters/__init__.py` OOA routing for unknown chains; `schema.sql::shadow_observations` (writer-less, gap #7 residual).
- **current compliance**: **PARTIAL** — confidence math + shadow collection implemented; live hostile-chain shadowing needs external RPCs; shadow_observations table unwritten.
- **deviations**: Persistence gap (table without writer).
- **security impact**: Medium (OOA confidence overstates ⇒ routing into unobservable chains).
- **required remediation**: Wire shadow observer writes to schema.sql.
- **verification method**: `tests/unit/btcp_continuum` OOA/shadow tests; **MUST-CREATE**: shadow persistence test.

#### R-BT-14 — Sensing Oracle (privacy from TRION itself)
- **requirement**: Entity computes behavioral_hash privately; `public_commitment = Hash(behavioral_hash)`; ZK proof of coherence with historical BEO root; TRION stores ONLY public_commitment; emits BEHAVIORAL_TRUTH_SIGNAL{entity_id, public_commitment, coherence_score, plane_results[7], behavior_content ABSENT, amount ABSENT, counterparty ABSENT, protocol ABSENT, chain ABSENT}. [CONJECTURE — circuit 500k–2M constraints; proof aggregation likely required.]
- **source**: BTCP §7.
- **specification section**: BTCP §7.1 "The Dark Field Principle".
- **mathematical definition**: Hash-of-hash commitment + coherence SNARK.
- **canonical data structure**: BEHAVIORAL_TRUTH_SIGNAL.
- **canonical implementation**: `core/planes/seven_plane_coherence.py` (plane check) + `zk-circuits/zk_behavioral_credential/` (circuit, unbuilt).
- **all implementations**: seven_plane_coherence.py; TRIONSensingOracle.sol (publishes the signal shape); zk circuit sketch.
- **current compliance**: **RESEARCH-ONLY** (spec itself rates 58%; circuit not built — honest).
- **deviations**: None (conjecture labeled).
- **security impact**: High-if-shipped-wrong (privacy claims must not be simulated in production).
- **required remediation**: Keep research label until circuits + zkeys exist.
- **verification method**: `tests/unit/test_all_planes.py`; circuit build (future).

#### R-BT-15 — Behavioral State Capsule + BSC (state channels)
- **requirement**: Capsule: anchor block/hash + price + balance + governance snapshot + `staleness_ci95` per state type (Price: ANIMA drift CI; Balance: (0,0) via escrow lock; Governance: (0,0) read-only) + escrow_lock flag; chain B executes from capsule, not live chain A. BSC: channel open (collateral both sides, one tx each), operate (zero on-chain cost per interaction, all 20 event types, validator co-sign), close (final state to both chains, escrow settles; 50 interactions → 2 on-chain txs).
- **source**: BTCP §5.4 + §5.7.
- **specification section**: BTCP §5.4 "Water Through Metal"; §5.7 "Water as Vapor".
- **mathematical definition**: Staleness estimator + channel lifecycle.
- **canonical data structure**: `BehavioralStateCapsule`; `BehavioralStateChannel`.
- **canonical implementation**: `core/btcp/modules.py::StateCapsule/StateCapsuleBuilder` + `BehavioralStateChannel`.
- **all implementations**: `core/btcp/modules.py` (both); `rust/src/state_capsule.rs`; `rust/src/behavioral_state_channel.rs`.
- **current compliance**: **PARTIAL** — structures + staleness estimation implemented; validator co-signing per interaction requires the live mesh; no production channel usage.
- **deviations**: None structural.
- **security impact**: Medium (capsule staleness mis-estimation = executing on drifted state).
- **required remediation**: Live co-signing integration when mesh deploys.
- **verification method**: `tests/unit/btcp_continuum` capsule/BSC tests.

#### R-BT-16 — BRT intent scheduling (optimal window)
- **requirement**: Find intersection of circadian gas minimum, NL peak, MEV valley; if `brt_gas_correlation.p_value > 0.05` fall back to ANIMA forecast; BRT correlation is a CONJECTURE (F14) — must be validated over 90-day/1M+ block sample before presented as reliable; UI must label "experimental optimization"; WAIT ⇒ intent stored as BLO with scheduled_activation.
- **source**: BTCP §5.8.
- **specification section**: BTCP §5.8 "Water Following the Gradient".
- **mathematical definition**: Three-curve intersection with statistical fallback.
- **canonical data structure**: `OptimalWindow{blocks_from_now, predicted_gas_gwei, current_gas_gwei, expected_saving_pct, confidence}`.
- **canonical implementation**: `anima-service/brt_scheduler.py`.
- **all implementations**: `anima-service/brt_scheduler.py` (real BRT scheduler — signal_factory docstring notes it lives here, not in akashic/); `rust/src/blo_scheduler.rs` (BLO scheduled activation); `core/extended/biological_rhythm.py` (BRT phases).
- **current compliance**: **COMPLIANT** (scheduler + p-value fallback + conjecture labeling discipline in code).
- **deviations**: None.
- **security impact**: Low (optimization, not safety) — but misrepresenting it as reliable violates the honest-conjecture rule.
- **required remediation**: Keep CONJECTURE labeling until F14 resolved.
- **verification method**: brt_scheduler unit tests; F14 registry monitor.

#### R-BT-17 — ZK Intent Commitment + Travel Rule
- **requirement**: ZK Intent: Phase 1 commit `H_intent = Hash_DNA(intent_details ∥ random_nonce ∥ entity_id)` (MEV bots see nothing); Phase 2 ZK complementarity proof (asset_in_A==asset_out_B ∧ magnitude≈, without revelation); Phase 3 atomic same-block reveal; Phase 4 execution (zero front-run window); opt-in via privacy ZK_CREDENTIAL|INVISIBLE. Travel Rule (Fix 1): disclosure encrypted to regulator key, entity submits ZK proof of compliance, TRION stores disclosure_hash only, emits TRAVEL_RULE_COMPLIANT=TRUE; Chameleon levels modulate requirement.
- **source**: BTCP §5.6 + §11 Fix 1.
- **specification section**: BTCP §5.6 "Water Underground"; §11 Fix 1.
- **mathematical definition**: Commit-reveal with SNARK complementarity.
- **canonical data structure**: commitment records + zk proofs.
- **canonical implementation**: `zk-circuits/zk_intent_commitment/` + `zk-circuits/zk_complementarity_proof/` + `zk-circuits/zk_travel_rule/` (Circom circuits, no zkeys); `contracts/solidity/TravelRuleCompliance.sol`.
- **all implementations**: the circuits + contract; `zk/` simulated prover layer; orchestrator zk_pending fail-closed path.
- **current compliance**: **RESEARCH-ONLY** (circuits unbuilt; Groth16 "style" simulation only — honest per labels).
- **deviations**: Spec estimates ~50k constraints/4–8 weeks — not started.
- **security impact**: High-if-faked (MEV protection claims).
- **required remediation**: Build zk circuits (W2+ ZK track) or keep deferred labels.
- **verification method**: circuit presence checks; future build pipeline.

#### R-BT-18 — Failure classifier (EXTERNAL vs ENTITY cause)
- **requirement**: `FailureCause::External` (chain outage, NL < 0.10 at failure, reorg > SAFE_CONFIRMATIONS, MF spike) / `Entity` (invalid proof, collateral withdrawal, conflicting intents, systematic timeout) / `Ambiguous` (first two = External; third within 90 days → Entity). BEO impact: EXTERNAL zero; ENTITY → warning, D(t) growth −10% for 30 days, conf reduced, BEHAVIORAL_ANOMALY. Resurrection extension: EXTERNAL → intent preserved; entity chooses WAIT (auto-retry) | CANCEL (escrow returns) | REROUTE. CHAIN_RELIABILITY_SIGNAL emission.
- **source**: BTCP §11 Fix 2.
- **specification section**: BTCP §11 Fix 2 "Failed Route Behavioral Recording".
- **mathematical definition**: Cause decision tree + BEO penalty schedule.
- **canonical data structure**: `FailureCause` enum + classification result.
- **canonical implementation**: `core/btcp/modules.py::FailureClassifier` (8 boolean indicators, escalation).
- **all implementations**: `core/btcp/modules.py::FailureClassifier`; `rust/src/btcp_failure_classifier.rs`; `api/btcp_continuum_routes.py::POST /failure_classify`.
- **current compliance**: **COMPLIANT** (indicators + ambiguous escalation + 8 bool outputs).
- **deviations**: CHAIN_RELIABILITY_SIGNAL not in the signal enum (see R-SG-03).
- **security impact**: Medium (mis-attribution unfairly punishes honest entities).
- **required remediation**: Register CHAIN_RELIABILITY signal type.
- **verification method**: `tests/btcp/test_btcp_api_surface.py` (failure_classify escalation).

#### R-BT-19 — Version handler (cross-chain protocol governance)
- **requirement**: `BTCPVersionProof{btcp_version, min_verifier_ver, feature_flags}`; `is_compatible(verifier ≥ min_verifier_ver)`; incompatible ⇒ BIBL reroutes to compatible adapter; major = 6-month transition (unupgraded → OOA), minor = optional, patch = always compatible; ADAPTER_VERSION_BONUS routing preference; outdated chains' BTCP_score reduced proportionally.
- **source**: BTCP §11 Fix 3.
- **specification section**: BTCP §11 Fix 3 "Cross-Chain Governance for Protocol Updates".
- **mathematical definition**: Semver compatibility predicate.
- **canonical data structure**: `BTCPVersionProof` + SemVer.
- **canonical implementation**: `core/btcp/modules.py::VersionHandler`.
- **all implementations**: `core/btcp/modules.py::VersionHandler` (semver compat + breaking verdicts); `rust/src/btcp_version_handler.rs`; `rust/src/types.rs::SemVer`; `contracts/solidity/BTCPVersionRegistry.sol`; `api/btcp_continuum_routes.py::GET /version`.
- **current compliance**: **COMPLIANT** (compat semantics + version embedding in proofs/intents).
- **deviations**: 6-month major-transition scheduler not automated (policy, not code).
- **security impact**: Medium (version skew = incompatible verification).
- **required remediation**: None.
- **verification method**: `tests/btcp/test_btcp_api_surface.py` (version verdicts); `tests/unit/test_intent_spec_fields.py`.

#### R-BT-20 — Genesis commitments + Sponsored Genesis sybil resistance (5 layers)
- **requirement**: Null-state theorem ⇒ genesis commitments necessary. Pathways: Asset genesis, Identity genesis (stake/signature/social), Sponsored genesis (sponsor with D > D_minimum stakes bond; new entity inherits conf_sponsored; manipulation ⇒ bond partially slashed). Five sybil layers: (1) `max_sponsored(j) = floor(log₂(D(j)/D_minimum) × BASE_SPONSOR_CAP)`, cap 10; (2) scrutiny multiplier `1 + n×0.2`; (3) similarity > 0.85 ⇒ SOCKPUPPET_ALERT + depth frozen + Conscious review; (4) `MIN_SPACING(n) = 7 days × n²`; (5) sponsor network graph: star pattern anomaly, chain depth ≤ 3 hops.
- **source**: BTCP §9.
- **specification section**: BTCP §9 "GENESIS COMMITMENTS — THE NULL-STATE THEOREM" + §9.3.
- **mathematical definition**: Log-cap + scrutiny + similarity + spacing + graph layers.
- **canonical data structure**: SponsoredGenesis records; `genesis_commitments` table.
- **canonical implementation**: `core/btcp/modules.py::GenesisCommitmentProcessor` + `SybilResistance` (5 layers computed).
- **all implementations**: `core/btcp/modules.py` (both); `rust/src/genesis_commitment.rs`; `contracts/solidity/GenesisCommitment.sol`; `api/btcp_continuum_routes.py::POST /sybil` (all 5 layers); schema table (writer-less residual).
- **current compliance**: **COMPLIANT** for the 5-layer math (cap 30, multiplier 1.8, spacing 112 days @ n=4, star flag tested); **PARTIAL** for on-chain bond custody (reference contract only).
- **deviations**: genesis_commitments table without writer (gap #7 residual).
- **security impact**: High (sybil bypass defeats the whole trust model).
- **required remediation**: Wire genesis writes to schema.sql; deploy bond custody.
- **verification method**: `tests/btcp/test_btcp_api_surface.py` (sybil all five layers).

#### R-BT-21 — Liquidity Ocean
- **requirement**: `LIQUIDITY_OCEAN_SCORE(asset, chain, t) = Σ_forms [VALUE(form) × 1/SHIFT_COST × 1/SHIFT_TIME × BEHAVIORAL_HEALTH(holder)]`; > 0 ⇒ routable; form-transforming events (STAKE, UNSTAKE, MINT, BURN, LIQUIDITY, BORROW, REPAY) tracked in real time; LIQUIDITY_OCEAN_SIGNAL emits asset, ocean_score, form_breakdown, best_form_path, estimated_slippage.
- **source**: BTCP §6.
- **specification section**: BTCP §6.1 "No Asset Has Zero Liquidity".
- **mathematical definition**: Form-equivalent liquidity sum.
- **canonical data structure**: form breakdown + ocean score.
- **canonical implementation**: `anima-service/liquidity_ocean.py`.
- **all implementations**: `anima-service/liquidity_ocean.py`; `contracts/solidity/LiquidityOcean.sol`; `tests/unit/trion_protocol/test_liquidity_ocean.py`.
- **current compliance**: **COMPLIANT** (score + form decomposition; live form tracking depends on ingestion breadth).
- **deviations**: LIQUIDITY_OCEAN signal type not in enum (R-SG-03).
- **security impact**: Medium (missed liquidity = suboptimal routes).
- **required remediation**: Register the signal type.
- **verification method**: `tests/unit/trion_protocol/test_liquidity_ocean.py`.

#### R-BT-22 — Dispute resolution + finality normalization
- **requirement**: Behavioral Evidence Standard: TRION vs chain validators disagree ⇒ Conscious Layer 3-of-5 + stake-and-slash (`dispute_resolution.rs`). Finality normalization (Gap D): `effective_latency = max(finality_A, finality_B)` — NOT the sum; BTCP_ESCROW waits max(A,B).
- **source**: BTCP §10 rows D + I; §14.1 item 17.
- **specification section**: BTCP §10 "Ten Architectural Gaps — Resolved".
- **mathematical definition**: max() finality rule; 3-of-5 evidence review.
- **canonical data structure**: dispute records; finality pairs.
- **canonical implementation**: `core/btcp/dispute_resolution.py`; `core/btcp/modules.py::FinalityNormalizer`.
- **all implementations**: `core/btcp/dispute_resolution.py`; `rust/src/dispute_resolution.rs`; `rust/src/finality_normalizer.rs`; `core/btcp/orchestrator.py` (uses normalizer).
- **current compliance**: **PARTIAL** — finality max() rule implemented; the Conscious 3-of-5 dispute review depends on the (undeployed) conscious network.
- **deviations**: None structural.
- **security impact**: Medium (finality underestimation = reorg exposure).
- **required remediation**: Conscious-layer dispute wiring when annotators exist.
- **verification method**: `tests/unit/btcp_continuum` finality tests.

---

## Domain 13 — Semi-immutability architecture

Canonical: MD §14 (conflict K6 for the P5 naming). Formula-level detail cross-referenced at R-SG-05.

#### R-SI-01 — Formal two-property definition
- **requirement**: `bytecode(P,t) = bytecode(P,t′) ∀t>t′` AND `expression(P,t) = f(bytecode(P), EL_state(t))`; EL_state = g(Threat_level, Network_entropy, Validator_health); g defined by deployed bytecode so the expression range is immutably bounded; NOT a proxy pattern (no governance-mediated redeployment).
- **source**: MD §14 "Formal Definition".
- **specification section**: MD §14.
- **mathematical definition**: As stated.
- **canonical data structure**: EL state + expression mode.
- **canonical implementation**: `core/spiritual/living_security/__init__.py::EpigeneticLayer` (EL_state as function of threat/health/entropy → expression mode).
- **all implementations**: EpigeneticLayer; `core/akashic/epigenetics.py`; `core/spiritual/epigenetic.py`; contract side: Vyper escrows (no proxy, no upgrade path) — the bytecode-immutability half holds by construction.
- **current compliance**: **PARTIAL** (expression side implemented; no on-chain artifact demonstrates the bounded-g property; Solidity suite has TRIONGuard/Firewall contracts whose upgrade story must stay proxy-free).
- **deviations**: None structural.
- **security impact**: Medium-high (proxy drift would silently void the property).
- **required remediation**: Add a repo-wide check that semi-immutability-critical contracts deploy without proxies/upgrades (W4).
- **verification method**: **MUST-CREATE**: `tests/contracts/test_no_proxies.py` (scan deployed artifacts for proxy bytecode patterns).

#### R-SI-02 — Semi-immutability stack table
- **requirement**: Protocol bytecode immutable (standard EVM); behavioral expression semi-mutable (Epigenetic L4.5); internal components semi-mutable via fitness (Evolutionary Fitness Engine L0.6); security keys continuously evolving (Genomic Key L4.3); attack surface semi-mutable (CRISPR L4.6).
- **source**: MD §14 "The Semi-Immutability Stack".
- **specification section**: MD §14 stack table.
- **mathematical definition**: five-layer mutability lattice.
- **canonical data structure**: component registry with mutability class.
- **canonical implementation**: component-wise across `core/` (epigenetic, evolutionary_fitness, genomic evolver, CRISPR).
- **all implementations**: `core/primitives/evolutionary_fitness.py`; `core/spiritual/living_security/` (GK + CRISPR); `core/spiritual/living_security/__init__.py::EpigeneticLayer`.
- **current compliance**: **COMPLIANT** component-wise (all five mechanisms exist at their layers).
- **deviations**: No single "stack" registry artifact (components scattered).
- **security impact**: Low (documentation-level).
- **required remediation**: A stack overview doc mapping mechanism → mutability class (W4/R).
- **verification method**: component tests already listed per mechanism.

#### R-SI-03 — CRISPR "contract that cannot be attacked" sequence
- **requirement**: New attack → ADAPTIVE characterization ≤24h → signature into permanent library → every future matching transaction intercepted before execution → attack vector closed in the interaction layer; target bytecode never changes; F4 falsification binding (breach without causal-history reproduction).
- **source**: MD §14 "The CRISPR Mechanism" + §20 F4.
- **specification section**: MD §14 sequence + [FALSIFIABLE F4].
- **mathematical definition**: signature interception pipeline.
- **canonical data structure**: CRISPR library + adaptive queue.
- **canonical implementation**: `core/spiritual/living_security/__init__.py::CRISPRDefense`.
- **all implementations**: CRISPRDefense (+ cross-chain signature library incl. 2025 ZK-rollup bypass class); `anima-service/crispr_anomaly.py`; `contracts/solidity/TRIONFirewall.sol` (on-chain intercept analog).
- **current compliance**: **PARTIAL** (library + matching real; pre-execution mempool interception pending — see R-LS-03; the DD flagged the fabricated "2026 attacks" citations — keep them labeled as illustrative).
- **deviations**: DD S8: natural_liquidity.py's hardcoded "March 12, 2026" is a synthetic motivating vector — must never be cited as external evidence.
- **security impact**: High (F4).
- **required remediation**: Purge/label synthetic incident citations from security modules (DD S8 remediation).
- **verification method**: `tests/test_gk_living_security.py`; adversarial suite.

---

## Domain 14 — Chameleon protocol (regulatory adaptation)

Canonical: MD §17; V2 §14.2–14.4 (governance side).

#### R-CH-01 — Threat-level adaptation sequence
- **requirement**: LOW: increase privacy defaults, surface ZK credential options. MEDIUM: ZK proofs default output, Right_to_Invisibility auto-enforced in jurisdiction, raw behavioral data access restricted. HIGH: validator weight in hostile jurisdiction de-emphasized, geographic HHI rebalances automatically (algorithmic), outputs jurisdiction-specific ZK only. CRITICAL: signal disaggregation across neutral jurisdictions, no single jurisdiction sees complete signal, individual invisibility fully enforced. WEAPONIZATION_ATTEMPT: AWA_enforced → FALSE → emission FROZEN.
- **source**: MD §17 "Adaptation Sequence".
- **specification section**: MD §17 THREAT LEVEL → EXPRESSION CHANGE.
- **mathematical definition**: 5-level threat ladder.
- **canonical data structure**: `ThreatLevel` enum → `ExpressionMode`.
- **canonical implementation**: `core/novel/chameleon.py`.
- **all implementations**: `core/novel/chameleon.py` (ThreatLevel, ExpressionMode incl. ZK_DEFAULT, JURISDICTION_REBALANCED); `core/novel/behavioral_identity_recovery.py` (epigenetic record); novel_primitives.md P7 (jurisdiction views, consistency invariant).
- **current compliance**: **PARTIAL** — ladder + expression modes implemented; P7's per-jurisdiction Chameleon_view registry (canonical_state_hash identical across views + BZK consistency proof) is only modeled, and jurisdiction rebalancing hooks into HHI are not wired.
- **deviations**: P7 view registry MISSING; consistency invariant unenforced.
- **security impact**: High (a wrong-jurisdiction disclosure leaks sovereign/user data; spec itself rates 55%).
- **required remediation**: Implement Chameleon_view registry + consistency invariant; wire HIGH-level HHI rebalancing to `hhi_monitor`.
- **verification method**: chameleon module tests; **MUST-CREATE**: view-consistency test (same canonical hash across jurisdictions).

#### R-CH-02 — AWA (Anti-Weaponization Architecture)
- **requirement**: `AWA_enforced iff all_of: no_single_entity_controls_signal_weights; no_single_entity_controls_validator_selection; Public_Good_Charter_minimum ≥ 15%; Sovereignty_Dignity_Protocol_active; Right_to_Invisibility_enforced; Gratitude ≥ 1`. AWA_enforced = FALSE ⇒ signal emission FROZEN automatically; cannot be overridden by any single entity; also: `AWA_enforced = FALSE if Right_to_Invisibility = FALSE` (MD §16).
- **source**: MD §17 "The AWA"; V2 §14.2.
- **specification section**: MD §17 AWA block; V2 14.2.
- **mathematical definition**: 6-condition conjunction → emission gate.
- **canonical data structure**: AWA state machine (ENFORCED/SUSPENDED/DEGRADED/FROZEN/EMERGENCY).
- **canonical implementation**: `core/governance/awa.py`.
- **all implementations**: `core/governance/awa.py` (8-condition superset: quorum, HHI, gratitude, public good + 4 anti-centralization; FROZEN state implements the emission freeze).
- **current compliance**: **DEVIANT** — implements a *superset* with different condition names (conflict K15); two canonical conditions (Sovereignty_Dignity_Protocol_active, Right_to_Invisibility_enforced) are not encoded as named checks (Right_to_Invisibility exists separately in `core/governance/right_to_invisibility.py` but is not an AWA conjunct).
- **deviations**: Naming ("Adaptive Watchdog Architecture") + condition mapping incomplete.
- **security impact**: Critical (this is the anti-capture freeze; F12).
- **required remediation**: Rename to Anti-Weaponization Architecture; encode all six canonical conditions explicitly (importing the right_to_invisibility + SDP states); emission path must consult AWA state.
- **verification method**: **MUST-CREATE**: `tests/unit/test_awa_freeze.py` (each canonical condition false ⇒ FROZEN ⇒ emission blocked).

#### R-CH-03 — BIRP (Behavioral Identity Recovery Protocol)
- **requirement**: Enrollment: DNA_Code (content secret, length secret, change schedule secret — timing itself a secret layer); TRION stores only `BIRP_anchor = Hash_DNA(BEO_baseline ∥ Hash(DNA_Code) ∥ enrollment_timestamp ∥ behavioral_entropy_seed)`; DNA_Code at T+interval invalid. Recovery phases: (1) DNA_Code verification — exact timing window (zero tolerance), exact length (partial silently rejected), dual-strand hash check; (2) behavioral proof — Akashic BEO challenge, behavioral_match > 0.85; (3) temporal cluster challenge — tx from any BEO address within N random minutes; (4) Conscious Layer 3 independent verifiers (2-of-3, behavioral evidence only, no identity) for high-value; (5) 7-day waiting period with notification to all cluster addresses; fraudulent recovery blocked + permanently recorded. Honest limitation: challenges from recent history (drift).
- **source**: MD §16 BIRP; novel_primitives.md P6 (adds RR_BIRP weights).
- **specification section**: MD §16 "Behavioral Identity Recovery Protocol (BIRP)".
- **mathematical definition**: anchor construction + 5-phase protocol.
- **canonical data structure**: `BIRPRequest`, `DNACodeRegistration`, phase results.
- **canonical implementation**: `core/novel/birp.py` (all 5 phases: phase1_dna_verification incl. epoch rotation, phase2 behavioral proof w/ merkle root, phase3 temporal cluster, phase4 conscious votes 2-of-3, phase5 quarantine status) + `core/novel/behavioral_identity_recovery.py`.
- **all implementations**: `core/novel/birp.py`; `core/novel/behavioral_identity_recovery.py`; `tests/unit/trion_protocol/test_birp_dna_code.py`.
- **current compliance**: **COMPLIANT** (phases, zero-tolerance timing, silent partial rejection, 7-day quarantine, epoch rotation; P6's cooldown counters implemented).
- **deviations**: None material (phase 4 depends on conscious network availability — same fleet caveat).
- **security impact**: Critical (identity recovery is account-takeover surface).
- **required remediation**: None.
- **verification method**: `tests/unit/trion_protocol/test_birp_dna_code.py`.

#### R-CH-04 — Sovereignty Dignity Protocol + sovereign signals
- **requirement**: Every SBA signal includes appeal_mechanism, cultural_context_vector, data_sources (full provenance), uncertainty_bounds (CI_95); appeals are permanent record; SBA = w_E·E + w_I·I + w_S·S + w_G·G + w_C·C.
- **source**: MD §10 L8.1 (SBA + SDP framing); V2 L8.1 (weights 0.30/0.25/0.20/0.15/0.10 + mandatory metadata).
- **specification section**: MD L8.1; V2 L8.1.
- **mathematical definition**: 5-axis weighted assessment.
- **canonical data structure**: SBA result + mandatory metadata.
- **canonical implementation**: `core/governance/sba_engine.py`; `core/extended/sovereign_behavioral.py`.
- **all implementations**: `core/governance/sba_engine.py`; `core/extended/sovereign_behavioral.py` (+ `sovereign_data_fetcher.py`); SOVEREIGN_BEHAVIORAL signal in signal_factory; L8.md's SDP privileges/obligations (P1–P5, O1–O5) — supplementary detail, not implemented as a privilege engine.
- **current compliance**: **PARTIAL** — SBA math + mandatory metadata implemented; the appeal mechanism is a record stub (no appeal workflow); SDP privilege suspension logic absent.
- **deviations**: SDP privilege engine MISSING.
- **security impact**: Medium (sovereign handling without appeal channels = reputational/regulatory exposure).
- **required remediation**: Implement appeal records + SDP privilege state machine.
- **verification method**: `tests/master_formula_verification.py` (SBA); **MUST-CREATE**: SDP appeal test.

#### R-CH-05 — Gratitude Protocol + unknown-unknown provision
- **requirement**: `Gratitude(t) = Value_given_to_life / Value_received ≥ 1`; Gratitude < 1 sustained ⇒ governance emergency; `Budget_unknown = 0.10·Revenue`, not allocated without >75% supermajority, 30-day time-lock multisig.
- **source**: V2 §14.3/§14.4 (MD silent → V2 wins).
- **specification section**: V2 14.3 "The Gratitude Protocol"; 14.4 "Unknown Unknown Provision".
- **mathematical definition**: gratitude ratio + 10% reserve.
- **canonical data structure**: gratitude score + reserve account.
- **canonical implementation**: `core/governance/love_protocol.py`; `core/governance/unknown_unknown.py`; gratitude in `core/governance/awa.py`.
- **all implementations**: the three files (gratitude scoring with 0.95/week decay; unknown-unknown budget model).
- **current compliance**: **PARTIAL** (models exist; no treasury execution — no revenue yet).
- **deviations**: None structural.
- **security impact**: Low direct; governance-critical later.
- **required remediation**: Wire to treasury when revenue exists.
- **verification method**: `tests/unit/trion_protocol/test_governance_modules.py`.

---

## Domain 15 — Tokenomics

Canonical status: MD/V2 Part 15.3 define utility + fixed supply qualitatively; the repo has canonicalized specifics in docs/TOKENOMICS.md (resolving DD finding 5.4). Numeric burn rate (0.05%) is repo-canonical, spec-silent.

#### R-TK-01 — Fixed supply, no inflation, burn-on-use
- **requirement**: "Token supply: fixed at genesis. No inflation mechanism. Deflationary: consumption bonding burns small fraction on each use." 1B TRION @ 18 decimals across implementations; genesis distribution on-chain enforced (15% public good, 85% treasury/vesting); governance_mint always reverts.
- **source**: V2 15.3 (MD silent on numbers → V2 + repo canonical doc).
- **specification section**: V2 15.3 "TRION Token — Complete Utility Specification".
- **mathematical definition**: TOTAL_SUPPLY constant; 0.05% transfer fee (repo canon), 15% of fee to public good, 85% burned.
- **canonical data structure**: Vyper ERC-20 with fee/burn hooks.
- **canonical implementation**: `contracts/vyper/TRIONToken.vy`.
- **all implementations**: `contracts/vyper/TRIONToken.vy` (1B @ 18dec, mint-once, fee split, slash_validator 50/50 insurance/burn); NEAR/TON/ink! ports aligned per docs/TOKENOMICS.md (DD 5.4 resolution); `contracts/solidity/MockTRIONToken.sol` (test).
- **current compliance**: **COMPLIANT** (supply/decimals/distribution identical across implementations per the canonical doc; DD's three-stories finding resolved).
- **deviations**: 0.05% fee and the 15/85 split are repo-canonical (spec says only "small fraction" + "15% of fee revenue" — document as canonical decision).
- **security impact**: Medium (supply integrity).
- **required remediation**: Keep docs/TOKENOMICS.md as the numeric canon; add a supply-parity test across the four token implementations.
- **verification method**: `tests/contracts/`; **MUST-CREATE**: cross-VM supply-parity test.

#### R-TK-02 — Validator staking + slashing economics (Vyper)
- **requirement**: Vyper is the economic-coordination language: validator staking, slashing, TRION token; stake scales with influence (HHI management); coverage tiers; challenge bond 5%; slash execution with insurance/burn split.
- **source**: MD §15/§21 (Vyper role); V2 15.3 utility 1.
- **specification section**: MD §21 tech stack (Vyper row); V2 15.3.
- **mathematical definition**: staking contract economics.
- **canonical data structure**: `TRIONStaking.vy` records.
- **canonical implementation**: `contracts/vyper/TRIONStaking.vy`.
- **all implementations**: `contracts/vyper/TRIONStaking.vy` (region stakes, effective stake s_j·d_j, coverage tiers 1–4, slash schedule event hooks); `core/spiritual/slashing.py` (condition computation).
- **current compliance**: **COMPLIANT** as reference implementation (not deployed with live stake).
- **deviations**: "7-type slashing schedule" comment vs 5 canonical conditions (K12 docs drift).
- **security impact**: High when live.
- **required remediation**: Align the comment table with V2 L4.9 (W4).
- **verification method**: `tests/contracts/` vyper tests.

#### R-TK-03 — Utility functions (5) + tiered access
- **requirement**: (1) validator staking; (2) governance (AWA changes >75% supermajority; emergency 3-of-5 multisig + vote); (3) signal consumption staking (quality bonds, tiered Basic/Professional/Institutional, burned if weaponizing); (4) data market participation; (5) public good charter enforcement (15%).
- **source**: V2 15.3 items 1–5.
- **specification section**: V2 15.3.
- **mathematical definition**: utility matrix.
- **canonical data structure**: tier registry + bond accounting.
- **canonical implementation**: `contracts/vyper/TRIONStaking.vy` (tiers) + `TRIONToken.vy` (public-good routing).
- **all implementations**: staking/token contracts; `core/governance/` (AWA supermajority logic).
- **current compliance**: **PARTIAL** — staking + public good on-chain; consumption-tier access control and data-market payments not implemented (no consumers yet).
- **deviations**: Tiers 1–4 coverage exist (AUDIT-4); Basic/Professional/Institutional access tiers MISSING.
- **security impact**: Medium (bond-burn enforcement is the anti-weaponization economic teeth).
- **required remediation**: Consumption-tier contract when API monetizes.
- **verification method**: **MUST-CREATE**: tier-access tests when implemented.

---

## Top 10 remediation items by security impact

1. **Validator fleet + on-chain quorum floor** (R-VC-03/R-VC-08) — every consensus-backed guarantee (escrow release, route attestations, Σ plane) is conditional on a deployed fleet and a raised on-chain quorum; today quorumRequired=2 and HSM/KMS is env-mode. *Owner: Wave 3 deployment + Wave 4 red team.*
2. **AWA canonical condition set + emission freeze wiring** (R-CH-02) — the anti-weaponization freeze must encode all six MD §17 conditions and gate the actual emission path. *Owner: code wave (governance) + test.*
3. **Degradation-tier route suspension + 50-block BIBL snapshot** (R-ME-07) — funds-at-risk guarantee during coherence degradation is currently unwired. *Owner: BTCP wave (F-adjacent).*
4. **CRISPR pre-execution interception channel** (R-LS-03/R-SI-03) — the "contract that cannot be attacked" claim currently detects post-block; mempool subscription (channel C7) required. *Owner: indexer/network wave.*
5. **Sensing-oracle publication trust** (R-OP-01) — TRIONSensingOracle.publishBehavioralTruth is still relayer-gated without signature quorum (unlike the V3 route path); migrate to attested publication. *Owner: contract wave (G).*
6. **Wash-trading depth discount + conservation audit automation** (R-EC-03/R-EC-06) — spec-mandated defenses missing from the depth engine; lunar audit not automated. *Owner: math wave (D).*
7. **Fork multi-factor tie-break** (R-AK-06) + **asset-id registry** (R-HD-02) — single-factor fork resolution and unvalidated asset ids both corrupt cross-chain semantics. *Owner: Akashic wave (D).*
8. **Signal registry completion** (R-SG-03) — CHAIN_RELIABILITY, BTCP_TIMEOUT, LIQUIDITY_OCEAN, GENESIS_COMMITMENT, SHADOW_CHAIN, BEHAVIORAL_TRUTH absent from the enum; route-failure signaling weakened. *Owner: signal wave.*
9. **schema.sql writer completion** (R-BT-10/13/20) — blo_orders, bitp_clipboard, shadow_observations, genesis_commitments tables remain without TimescaleDB writers (gap #7 residual). *Owner: storage wave (N).*
10. **Spec hygiene pass** (K1–K22 + R-BH-01, R-SG-05, R-CH-02, R-TK-01) — two-primitive BH split, BIBL/P5 rename, AWA rename, falsifiability renumbering, L0/L1/L2/L4/L5.md obsolete formulas: the spec corpus itself carries 22 recorded contradictions; leaving them invites future agents to implement the wrong layer doc. *Owner: W4/R (docs conformance).*

## Unresolved / needs-lead-decision items

- **Cargo-gated verifications**: Rust cross-language BH parity, magnitude determinism, reorg-window, and the 94 rust unit tests cannot execute in-sandbox (no cargo). Static parity tests pin the contract; live verification deferred to a cargo-capable environment.
- **D(t) bootstrap scale**: "full EVM history from genesis" is a data-ops program (billions of events); the spec's completion criterion cannot be honestly claimed until run. Current D_MINIMUM=10 000-event operationalization is a repo-canonical decision — spec silent on the numeric form.
- **PQC optional dependencies**: kyber-py/dilithium-py absent (1 pre-existing adversarial failure + 4 skips) — environmental, not code.
- **Novel_primitives P2 (Argon2id BCK) vs MD L4.3 (chained Hash_DNA GK)**: two different BCK constructions in the authoritative set; MD wins by hierarchy (implemented), but P2's KDF form is a legitimate future primitive — lead should decide implement-vs-defer.
- **Seven-plane enumeration**: BTCP §7.1 requires 7 plane results without naming them; `core/planes/seven_plane_coherence.py` picks a set — needs spec enumeration.


