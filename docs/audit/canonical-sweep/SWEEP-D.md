# SWEEP-D — Spec Matrix + Claims Verification (TEAM L + M-prep)

Repo: /home/z/trion-core @ HEAD `c6c38e4` (2026-09-04, 722 commits in history).
Agent: TEAM L + M-prep (documentation/whitepaper conformance), master command §1, §13, §15, §32.
Method: research-only; all evidence below re-verified at HEAD (not trusted from prior audit docs).
Parser script: `canonical-evidence/parse_matrix.py`; parsed rows: `canonical-evidence/matrix_entries.json`.

---

## 1. Spec source inventory + precedence

| Source | Claimed date | First/last repo commit | Role in hierarchy |
|---|---|---|---|
| `spec/WHITEPAPER_MD.txt` (1486 ln) | "February 2026 (updated March 2026)" | added 1da47fb 2026-09-02, last mod 8d942a3 2026-09-03 | **1 — canonical protocol semantics; wins semantic conflicts** ("MD") |
| `spec/WHITEPAPER_V2.txt` (1240 ln) | February 2026 | added 1da47fb, last mod 9c38da8 (both 2026-09) | **2 — complete implementation spec; wins where MD is silent** ("V2") |
| `spec/BTCP_SPEC.txt` (1853 ln) | **April 2026** (newest dated spec; "Merged from: BTCP Master Spec · Water Principle Improvements · TRION Whitepaper") | added 1da47fb, last mod 9c38da8 | **3 — governs BTCP absolutely** ("BTCP") |
| `spec/L0..L9 *.md` + `signal_types.md` + `novel_primitives.md` + `falsifiability_registry.md` + `communication_channels.md` | older per-layer drafts | added a6f5b62 2026-08-13, banners 713c42c 2026-09-04 | **4 — authoritative in domain, subordinate to 1–3**; 13 SUPERSEDED banners |
| `spec/DD_REPORT.txt` | audit-era | — | **5 — audit input only, never a spec** |
| `upload/TRION_PROTOCOL_White_paper.txt` | — | **ABSENT**: not in tree and not in any git history (`git rev-list --all --objects` has no `upload/` blob; only `scripts/upload_faiss_0g.mjs`) | Not part of this repo's canon; presumably the external TRION-Protocol org repo file referenced by MD header ("github.com/TRION-Protocol/TRION-Protocol") |

**Precedence order (per `docs/audit/CANONICAL_SPEC_MATRIX.md:15-26`, "fixed at freeze"):** MD > V2 > BTCP_SPEC > layer .md set > DD_REPORT. Newest *by claimed date* is BTCP_SPEC (Apr 2026), but precedence is by role, not date. The claim was verified against the layer-doc banners, which consistently defer to MD/V2/BTCP per this order.

## 2. Protocol summary (15 lines)

1. TRION is a **behavioral truth oracle**: it reads accumulated on-chain behavioral history (not spot price) and emits signals only when five independent evidence planes cohere.
2. Root atom: **93-byte canonical Behavioral Hash** `entity_id(32)‖event_type(1)‖magnitude(8)‖context(8)‖timestamp(8)‖chain_id(4)‖block_hash(32)` (MD L0.1/V2 L0.1; pinned by tri-language golden vectors).
3. BH is dual-strand self-verifying: `sense = SHA3-256(payload‖0x00)`, `antisense = SHA3-256(payload‖0xFF) XOR complement(sense)` — tamper with either strand breaks complementarity.
4. **20 canonical VM-agnostic event types** (TRANSFER…CLAIM); **Hash_DNA** is the separate 14-field keccak256 BTCP-layer commitment hash (domain-separated, nonce+btcp_version replay-protected).
5. **BEO** resolves multi-wallet economic actors via `SHA3-256(normalize(identifier))`; BEO_confidence over CF/ST/SC/BP(+GX) channels, valid > 0.75; every BH's entity_id is a BEO id.
6. The **Akashic Index** is the append-only permanent BH store; its depth D(t) feeds genesis inference and the moat.
7. **Five-plane coherence:** `C(t) = α·Φ_adj + β·M_adj + γ·Σ + δ·K + ε·A`, weights sum 1 (DEFAULT 0.25/0.30/0.25/0.10/0.10); Φ_adj = Φ·(1−MF_score), M_adj = M·(1−OE_factor).
8. **Dynamic threshold:** `Θ(t) = 0.55 + 0.37·V(t)`, V(t)∈[0,1] market volatility.
9. **Master equation:** `T(t) = [C(t)≥Θ(t)]·S(t)·e^(M_moat·t)` (exponent clamp 36); indicator 0 ⇒ **structured SILENCE** `{coherence_gap, limiting_plane, trend, eta}` — silence is information.
10. `M_moat = D·Q·R·X·F·N` — six multiplicative compounding factors (depth, quality, regulatory record, cross-chain, falsifiability, network).
11. **7 manipulation fingerprints** (wash, coordinated pump, oracle attack, sybil liquidity, governance capture, MEV, fake volume) with exact trigger/score formulas gate Φ collapse → SILENCE.
12. **DW-BFT consensus:** effective power `s_j·d_j` with `d_j = 1−corr(M_j,M̄)` (Coordination Collapse); HHI over effective stake ×10 000 with 1500/2500/4000 tiers + geographic constraints; strict >2/3 quorum.
13. **TRION↔BTCP boundary:** TRION produces behavioral truth (C(t) verdicts, BEO continuity, MF, NL); **BIBL (Behavioral Inter-Block Layer)** is the inter-block intelligence window (MD §18/BTCP §4.2 Step 1) where TRION evidence is consumed to analyze intents; verified routes then release escrow by TRION consensus certificate.
14. **BTCP** = Behavioral Transaction Continuity Protocol: users submit *intents*, not transactions; **6-step orchestration**: (1) intent registration + BIBL analysis over all integrated chains, (2) BTCP_score route scoring, (3) route selection (7 route types) + cross-chain proof construction, (4) VM translation via thin adapters, (5) escrow lock + gas sharing/abstraction, (6) TRION-consensus-verified release + Akashic recording.
15. `BTCP_score = [0.25·NL + 0.20·normalize_gas + 0.20·finality + 0.15·CC + 0.20·BEO_continuity]·(1−MF_score)`; 24 canonical signals (19 MD + 5 V2 extended); AWA (Anti-Weaponization Architecture) freezes all emission unless six anti-capture conditions hold.

## 3. Spec-matrix verification (§15)

### 3a. Stats (parsed by script, 107 rows confirmed)

| Rating | Count |
|---|---|
| COMPLIANT | 53 |
| PARTIAL | 37 |
| COMPLIANT + PARTIAL (mixed) | 8 |
| RESEARCH-ONLY | 5 |
| MISSING | 1 |
| DEVIANT | 1 |
| cross-reference rows (rating deferred to R-CH-01/R-CH-03) | 2 |
| **Total** | **107** |

15 domains; 22 K-conflicts (K1–K22). The "107 normative requirements" claim is **accurate**.

### 3b. 20 re-verified requirements (10 random seed=42 + 10 highest-security-impact)

Verdict scale: CONFIRMED / CONFIRMED-WITH-NUANCE / CONTRADICTED / NOT-FOUND.

**Random-10 (seed 42):**

| ID | Requirement (abbrev) | Evidence check at HEAD | Verdict |
|---|---|---|---|
| R-BT-08 | BTCP_ESCROW two-state atomicity | `contracts/vyper/BTCP_ESCROW.vy:6-7,63-67,199,244-245,266-267` — exactly HOLDING→RELEASED\|REVERTED, terminal-before-transfer; `contracts/solidity/BTCPEscrow.sol:104-111` 6-state superset = disclosed deviation; both test files exist | **CONFIRMED** |
| R-BH-08 | Chain/reorg semantics of BH | `core/primitives/behavioral_hash.py:239-272` (chain_id+block_hash in payload); `rust/src/btcp_proof_builder.rs:45-53,220,416` reorg-depth guard; no reorg integration test in `tests/` (PARTIAL honest) | **CONFIRMED** |
| R-ME-04 | Θ(t)=0.55+0.37·V | `core/master/coherence.py:28-29,88-90`; `tests/master_formula_verification.py:509-511` endpoint tests | **CONFIRMED** |
| R-BT-21 | Liquidity Ocean | `anima-service/liquidity_ocean.py:8-34,53-199` exact Σ VALUE×1/shift_cost×1/shift_time×health formula; `tests/unit/trion_protocol/test_liquidity_ocean.py` (12 tests) | **CONFIRMED** |
| R-EC-06 | I_TRION conservation | `core/primitives/thermodynamics.py:6,94-98,116,235-259`; matrix's "MUST-CREATE conservation audit test" is **stale** — `tests/unit/test_conservation_audit.py` exists (header cites R-EC-06) + L0.4 checks in master-formula suite | **CONFIRMED-WITH-NUANCE** (matrix remediation already done) |
| R-EC-02 | 7 manipulation fingerprints | `core/physical/manipulation_detector.py:4-10,29-141,149-184,238-245` — all 7 with exact triggers/scores (0.70×ratio, cyclic>0.60∧cp<5; 1.00 oracle dev>15%; 0.60×concentration top5>80%∧<3 sources; 0.50×scaled HHI>4000∧<48h; 0.85×sync); F8/F13 in falsifiability_registry:33,38 | **CONFIRMED** |
| R-AK-07 | Archetype library | `core/akashic/archetype.py:23-337` + `test_archetype_engine.py` (8 tests); PARTIAL honest — no <10ms/1B-record performance evidence | **CONFIRMED** |
| R-HD-02 | magnitude_currency_id | `core/primitives/hash_dna.py:37,59-78` keccak256(chain_id‖addr‖symbol); MUST-CREATE test genuinely absent | **CONFIRMED** |
| R-BH-07 | Domain/version separation | `hash_dna.py:31,84-96` DOMAIN_SEPARATOR label+chain+addr; `:246-247,294-311` btcp_version+nonce replay fields; keccak/SHA3 fallback warned `:69-73`; DS-level separation tests `tests/unit/btcp_continuum/test_phase0.py:106,148-164`; hash-level negative test still missing (as flagged) | **CONFIRMED** |
| R-BT-13 | OOA + Shadow Observation | `core/btcp/modules.py:1081-1097` OOAAnchor (conf_max 0.85, k 0.001 exact) + `:1128+` ShadowObserver; matrix's "persistence gap (table without writer)" is **stale** — `core/btcp/state_store.py:1028 record_shadow_observation` is the operative writer (schema.sql:514-515) | **CONFIRMED-WITH-NUANCE** (matrix remediation already done) |

**Targeted-10 (highest security impact: escrow/certificate/quorum/AWA/BH/replay):**

| ID | Requirement (abbrev) | Evidence check at HEAD | Verdict |
|---|---|---|---|
| R-BH-01 | 93-byte dual-strand BH (Critical) | `behavioral_hash.py:276` asserts payload==93; `tests/golden/vectors.json` payload_len 93 (52 vectors); **I re-ran golden suite: 134 passed** | **CONFIRMED** |
| R-BH-09 | sense/antisense invariant (Critical) | `behavioral_hash.py:280-282` inline verify; `core/spiritual/living_security/__init__.py:62-67` verify_strand_structural/with_payload | **CONFIRMED** |
| R-VC-03 | Quorum/block finality (Critical, PARTIAL) | `validator/internal/consensus/engine.go:6-8,86-87` STRICT 3·power>2·total; Tendermint FSM `:13-55`; `engine_test.go` incl. TestExactlyTwoThirdsPrecommitsDoNotCommit, TestHasQuorumStrictBoundaries; `TRIONOracleV3.sol:68` quorumRequired=2 bootstrap disclosed | **CONFIRMED** |
| R-VC-04 | HHI tiers + geo (Critical) | `core/spiritual/hhi_monitor.py:9-17,41-49` — 1500/2500/4000, N_continents≥4, region<0.40, jurisdiction<0.30, cluster 0.15 | **CONFIRMED** |
| R-VC-07 | Slashing + dispute (Critical) | `core/spiritual/slashing.py:6-22,46-67,76,165,193` five V2 conditions exact (50%/3%/10%/0.1%/25%) + 72h window + 3 validators + 1 human council; `core/governance/slashing.py:12-19,153+` 7-step flow | **CONFIRMED** |
| R-VC-08 | Validator hardware/fleet minimums (Critical, MISSING) | Only doc mention `core/master/channel_architecture.py:95,102` (HSM note); no onboarding attestation, no fleet — **absence is real** | **CONFIRMED** (MISSING rating accurate) |
| R-OP-02 | publishBehavioralSignal full etching | `TRIONOracleV3.sol:737-772` — coherence/threshold/limitingPlane + SilenceRecorded & SilenceRecordedV2 with gap+etaBlocks; nuance: etcher is owner-or-validator (single-sender), quorum lives on publishSignal/attestation path | **CONFIRMED** |
| R-OP-03 | publishSignal quorum + route attestations (Critical) | `TRIONOracleV3.sol:837-857` quorum = max(static, live-set ⌈2/3⌉), distinct ascending signers; `:273-353` submitRouteAttestation sorted/distinct, freshness only via NEW distinct attestations | **CONFIRMED** |
| R-BT-05 | BTCP proof construction (Critical) | `core/btcp/modules.py:30-66,76-84` ConsensusProof (s_j·d_j sigs, diversity cert, hhi, coherence, margin, awa_enforced bit); `rust/src/btcp_proof_builder.rs:145-179` full spec field set (btcp_route_id/anchor_chain/execution_chain/btcp_version/feature_flags/min_verifier_ver); Python dataclass is a compact subset (naming differs) — deviation note covers signatures only | **CONFIRMED-WITH-NUANCE** (py field-set subset not explicitly flagged) |
| R-CH-02 | AWA anti-weaponization (Critical, DEVIANT) | `core/governance/awa.py:5-8,81-85` — canonical name + 6-condition set "Encoded explicitly (Wave 3 D, spec-matrix R-CH-02 remediation)"; `tests/unit/test_awa_freeze.py` EXISTS (matrix said MUST-CREATE) with per-condition freeze tests | **CONFIRMED-WITH-NUANCE** (matrix row is stale: DEVIANT rating + MUST-CREATE flag predate the remediation) |

**Score: 17 CONFIRMED, 3 CONFIRMED-WITH-NUANCE, 0 CONTRADICTED, 0 NOT-FOUND (20/20 citations resolve to real code).** All three nuances are cases where the *matrix is behind the code* (remediation landed after matrix compile: R-EC-06, R-BT-13, R-CH-02), not cases where code contradicts the matrix. No fabricated evidence citations were found.

### 3c. K1–K22 banner spot-checks (commit 713c42c)

Commit `713c42c` (2026-09-04): 10 files, **33 insertions, 0 deletions** — pure banner additions, spec bodies untouched (matches commit message "content unchanged"). Spot-checked 6:

| Banner location | K# | Banner points to resolution? |
|---|---|---|
| `spec/L0_universal_primitives.md:21` | K2 (+K22) | YES — defers to V2 L0.1 preimage layout, cites matrix K2, names obsolete draft |
| `spec/L2_akashic_index.md:78` | K8 | YES — V2 growing-form `1−e^(−λ·D)` canonical, L2 decay = different quantity |
| `spec/L4_spiritual_security.md:150` | K11 | YES — ×10 000 HHI canonical, L4 0–1 scale kept as supplement |
| `spec/L5_trion_master.md:49` | K7 | YES — MD plane assignment (Σ=consensus, K=Conscious) canonical, draft non-canonical |
| `spec/signal_types.md:7` | K4+K5 | YES — 24=19+5 count confirmed; S23 "Trusted Channel" expansion declared an error |
| `spec/communication_channels.md:7` | K14 | YES — MD §15 registry canonical; file kept as transport map |

All banners exist, are correctly scoped to the superseded section, and point to the canonical resolution recorded in the matrix. **5/5+ PASS (6 checked).**

## 4. Claims audit (§32)

| Claim (location) | Status | Evidence |
|---|---|---|
| "129 chains · 18 VM families · 40 integrated" (README:590-591, 676, 830, 961, 1090) | **VERIFIED** | `config/chain_registry.json`: 129 chain objects, 18 VM families, 40 `integrated:true` (script-counted); pinned by `tests/unit/test_chain_registry_canonical.py` |
| "pytest 1019 unit + 9 skipped … Wave 3 close 2026-09-04" (README:374, 1090; CHANGELOG:62) | **VERIFIED (dated, slight undercount now)** | Dated & measured claim; I re-ran `pytest tests/unit`: **1025 passed, 6 skipped in 48s** — suite grew after the count; all green |
| "87 btcp + 1 xfail" (README:364) | **VERIFIED** | `pytest tests/btcp --collect-only`: 88 collected = 87+1 xfail |
| "tests/golden 134" (README:1001) | **VERIFIED** | Re-ran: 134 passed |
| "master verification suite: 105 formulas, 104/0/1*" (README:1090) | **VERIFIED (now better)** | Re-ran `tests/master_formula_verification.py`: "105 passed, 0 failed, 0 skipped — ALL FORMULAS ENFORCED AS SPECIFIED" |
| "30/30 true positives, 0/10 FPR, recall 1.00 Wilson 95% CI [0.72,1.00], threshold frozen on train only" (README:321-334) | **HONEST-DISCLOSURE** | v1 degenerate backtest (FPR=1.0) explicitly retained + provenance doc; v2 numbers carry CI + frozen threshold + "on well-separated synthetic cohorts — see caveat" |
| Consensus security "sybils 75.76% nominal → 0.00% effective" + "Caveat, measured: at correlation 0.5 sybils retain 49.2%…" (README:360) | **HONEST-DISCLOSURE** | Includes self-identified break of the 2/3 safety bound at intermediate coordination |
| "Bridge Pairs Eliminated N×(N−1)/2 … Bridges: legacy only" (README:290-304) | **HONEST-DISCLOSURE (speculative projection)** | Pure combinatorial arithmetic labeled as a *timeline* projection, not a measured result |
| Deployments: "reportedly deployed … self-reported and not independently verified", Solana devnet "❌ Not deployed — fabricated record purged" (README:1028, 1040-1041, 1066) | **HONEST-DISCLOSURE** | Fabrications explicitly called out, only 0G mainnet single-tx disclosed as sole mainnet record |
| "world's first substrate-independent behavioral coherence verification engine" (README:5,7) | **STALE/VISION (unfalsifiable marketing)** | Positioning claim; not measurable — flag as marketing, not fabrication |
| AI/ML claims: "AI cannot fake 20 years of biological rhythm patterns", "TRION-certified AI agents" (README:407-411, 449) | **VISION/forward-looking** | Love=0→F=0 arithmetic is real+tested (5/5); the "certified AI agents" product framing is prospective |
| "Production Architecture" / relayer custody (README:628-640) | **HONEST-DISCLOSURE** | "submits, never authorizes", "single-signature custody honestly labeled (production custody = KMS/HSM)", live fleet = "operational gate (see MAINNET_RUNBOOK)" |
| Go engine "statically audited + CI — not runnable in this sandbox" (README:375, 640) | **HONEST-DISCLOSURE** | Toolchain honestly labeled external |
| CHANGELOG last 83 commits (f91a19b…c6c38e4 = the entire canonical-reconstruction range) | **HONEST** | "Unreleased — Waves 1-4, 2026-09-04" documents exactly that range: measured counts, purged-fabrication notes (Solana devnet), Σ(t) echo-fix, secret-scan-clean disclosure; entries cross-checked against git log subjects — consistent |

**No FABRICATED claims found in the README/CHANGELOG at HEAD.** The fabricated-deployment and degenerate-backtest history is disclosed rather than hidden. Remaining soft spots: unverifiable "world's first" positioning and forward-looking AI-product framing.

## 5. TRION↔BTCP boundary (BIBL) trace (§13)

Code path, intent → analyze → route:

- **API intake:** `api/btcp_continuum_routes.py:194-246` `POST /api/v1/btcp/route` — BIBL chain state comes from the request body; response carries `"state_provenance": {nl_scores: "caller_supplied", …}` + note "computes a route RECOMMENDATION over caller-supplied evidence… not a TRION-verified route verdict; verified routes come from /api/v1/btcp/orchestrate + on-chain certificate verification" (:235-246). Full 6-step run: `POST /api/v1/btcp/orchestrate` (:1506) → `core/btcp/orchestrator.py::BTCPOrchestrator.create_route` (:990): registry-membership gate (:1028-1042) → intent with persisted per-entity nonce (:1061-1081) → VM encoding → gas → ZK proofs (honestly deferred `zk_pending` without caller witnesses, :1016-1023).
- **TRION signals actually consumed:** `core/btcp/integration.py` (IntegrationHub) imports the **real** anima-service APIs — `nl_score_engine.compute_nl_score` (:82), `btcp_gas_forecast.forecast_gas` (:99-103), `brt_scheduler.predict_optimal_window` (:119-122, keeps CONJECTURE label discipline), `anima_regulatory.get_registry` (:130-133), `liquidity_ocean` (:112), `core.price.btcp_price_oracle` (:92). Wired at commit `73d5e9e` (2026-09-04) after discovering the hub had imported names "that have never existed in anima-service" — i.e. a fabrication-class bug found and fixed.
- **Ledger binding:** `core/btcp/orchestrator.py:542-557` imports `core.akashic.beo_lookup.lookup_beo_binding` (reads `akashic_state.db`, the FAISS service's SQLite state, env `FAISS_STATE_DB`); witness upgrades to `akashic_beo_bound` **only** if the entity is in the ledger; otherwise stays `caller_self_attested` with explicit note. No ledger → honest None (beo_lookup.py:21).
- **TRION-side BIBL:** `core/akashic/bibl.py` + `bibl_pattern_store.py` — SQLite-backed pattern store; "historical_matches from real pattern store (was hardcoded 100)" (bibl.py:274-281; store INSERT/SELECT :260-298).
- **Scoring:** `core/btcp/router.py:270-300` `select_optimal_route` / `btcp_score_final` consume the BIBLState; BEO continuity "real value from BIBLState (Akashic BEO lookup), falling back to the documented bootstrap prior" (:275-277). Rust twin: `rust/src/btcp_router.rs:163-177` (same weights).
- **Residual gap:** `GET /api/v1/btcp/bibl/snapshot` (`api/btcp_continuum_routes.py:256-274`) returns a **hardcoded demo snapshot** (chains 1/137/8453) — disclosed in a code comment ("In production, this would return the live BIBL state. For demo, return a sample snapshot") but **not labeled in the JSON response** (no `demo:true` field). This is the only fabrication-adjacent residue on the boundary.

**Verdict: BIBL does NOT wholesale fabricate.** The router consumes caller-supplied state with explicit provenance labels; the orchestrator binds BEO witnesses to the real Akashic/FAISS ledger when it exists and degrades to labeled self-attestation when it doesn't; the integration hub consumes real anima-service (TRION) signals. One unlabeled demo snapshot endpoint remains (low severity, cosmetic disclosure gap).

## 6. Red-flag sweep

| # | Class | Verdict |
|---|---|---|
| a | Impossible hex addresses `[0-9a-fA-F]{41,}` in frontend/wallet/spec | **CLEAN** — 7 matches of `0x2e49…c6ec` are exactly 64-hex (32-byte) **BEO entity ids** used as dashboard query defaults (canonical format), not addresses; `wallet_pages.tsx:95-102` uses real mainnet contracts (USDC 0xA0b8…eB48, WBTC 0x2260…C599) + labeled zero-address placeholders; zero 41–49-hex strings presented as addresses (targeted scan) |
| b | "March 12 2026" AAVE presented as real | **CLEAN** — every occurrence carries a disclaimer: WHITEPAPER_MD.txt:62-64 "[SIMULATED SCENARIO: hypothetical illustration, not a documented real event]"; `nl_score_engine.py:12-13` "synthetic test vector, NOT a real historical event"; `faiss_service.py:9934` "[SIMULATED SCENARIO]…not a real event"; `natural_liquidity.py:12` "was fabricated" |
| c | "100% exploit recall" | **CLEAN** — phrase purged; replaced by "test recall 1.00, Wilson 95% CI [0.72,1.00]" with held-out split + frozen threshold (README:335) |
| d | Committed private keys (`ghp_`, WIF `cSYN`, `0x93fd`, `0x2c3e`) | **CLEAN** — no `ghp_` tokens, no `cSYN`/`0x93fd`/`0x2c3e` hits in tree; broad WIF base58 scan only hits golden-vector hex payload and lockfile sha512 integrity strings (false positives); `.env.example` keys are all-zero placeholders with KMS/HSM custody config (`TRION_ALLOW_RAW_ENV_KEYS` escape hatch documented, raw keys refused under `TRION_ENV=production` per CHANGELOG) |
| e | "deployed Aug 2026" future-dated claims | **CLEAN** — no matches; deployment section discloses self-reported records, purged Solana-devnet fabrication, single-tx 0G mainnet record as the only mainnet entry |

**Red-flag sweep: 5/5 CLEAN.** All five old fabrication classes remain purged at HEAD.

---

## SWEEP-D bottom line

- Spec hierarchy is real, dated, and enforced (banners + matrix agree; `upload/…White_paper.txt` does not exist in this repo or its history).
- Matrix: 107 rows exactly as claimed; 20/20 re-verified rows cite real code; 17 CONFIRMED + 3 CONFIRMED-WITH-NUANCE (all three = matrix lags behind landed remediations); **0 CONTRADICTED / 0 NOT-FOUND**.
- K-banners: commit 713c42c adds banners only (33+/0−), 6/6 spot-checks point to the recorded resolution.
- Claims: chain counts (129/18/40) verified against the registry; test counts dated and re-runnable (1025+6 unit, 88 btcp, 134 golden, 105/0/0 master formulas — all green when re-executed); no fabricated claims at HEAD; historical fabrications are disclosed, not hidden.
- Boundary: BIBL consumes real TRION state where it exists with honest provenance labels; one demo BIBL-snapshot endpoint lacks a response-level demo label.
- Red flags: all 5 fabrication classes confirmed purged.
