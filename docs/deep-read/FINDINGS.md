# TRION Core — Full Repository Deep-Read Findings

**Date:** 2026-09-02
**Method:** Every folder, subfolder, file, and component was read — 869 tracked files (~129 MB, ~14 languages) — by nine parallel deep-read passes (one per subsystem), with the two ~500 KB monsters (`api/app.py` @ 10,392 lines, `anima-service/faiss_service.py` @ 11,257 lines) read end-to-end in chunks, and key claims **executed empirically** where possible (test suites actually run, WASM module actually instantiated, registries loaded, backtest JSONs parsed).
**Companion reports:** the nine full per-subsystem reports live alongside this file (`01`–`09` in `docs/deep-read/`). Everything below is backed by file:line citations in those reports.
**Disposition:** read-only audit. No production file was modified.

---

## 1. Executive Summary

TRION is two projects fused into one repository.

**Project A — a genuinely engineered behavioral-data pipeline.** A real ingestion spine exists: Rust indexers (21 chain crates + shared `trion-common`) poll public RPCs, compute 9 Shannon-entropy features per block and a canonical 93-byte dual-strand Behavioral Hash per transaction (sense = `SHA3-256(p‖0x00)`, antisense = `SHA3-256(p‖0xFF) ⊕ NOT(sense)` — XOR invariant verified at every layer, byte-identical across Rust/Python/TS), POST to a real FAISS vector service (FlatL2→IVFPQ auto-promotion, atomic persistence, SQLite WAL ledger, TimescaleDB dual-write, restart survival). On top of it: a real coherence formula engine (C(t)=αΦ+βM+γΣ+δK+εA, dynamic Θ(t), master equation T(t)=[C≥Θ]·S·e^(M_moat·t), six-factor moat), real cryptography (Bellare-Neven Schnorr multisig, FIPS 203/204/205 PQC round-trips with honest dependency gating), a real ANIMA crawler layer (SEC EDGAR, GitHub, 19 RSS feeds, CFTC/FCA/ESMA/MAS, arXiv, GDELT, GBIF — with a credibility ledger and time-delayed outcome verification), a well-built 33-table TimescaleDB schema whose "thermodynamic deletion" trigger genuinely raises *Thermodynamic Violation (L0.4)* on any UPDATE/DELETE, a solid EVM Solidity tier (quorum ECDSA with EIP-2 high-s rejection, two-step ownership, pause, fail-closed uninitialized entities, CEI-clean escrow), and a genuinely excellent 517-line Hardhat adversarial test suite. The Rust BTCP crate's numeric claims are *literally true by structure*: exactly 94 `#[test]`s, 7 route types all reachable, BTCP_score weights 0.25/0.20/0.20/0.15/0.20×(1−MF) exactly as documented.

**Project B — a marketing/theatrical layer draped over Project A.** The README's flagship numbers do not survive contact with the artifacts that supposedly prove them. The committed backtest that anchors "**30/30 — 100% recall, F1 85.71%**" is a degenerate run in which **all 40 entities — the 30 attackers *and* all 10 innocent controls (Uniswap, Aave, Vitalik, Gnosis Safe) — scored coherence 0.0** (FPR = 100%, separation = 0.0): the arithmetic of a flag-everything classifier. "105/105 formulas ALL PASS" is 104/105 in a bare environment (the PQC check honestly fails without optional libs — the only failure is the honesty working). The "CRISPR Defense" matches mnemonic ASCII strings by substring search and its library contains **five fabricated 2026-dated attacks**, including an invented "March 12, 2026 AAVE collapse" that is cross-cited as *evidence* by two other modules. ~60 Flask endpoints present hash-seed-derived synthetic numbers at production paths. The cross-VM "test evidence" scripts cannot run anywhere (they hardcode `/home/user/.super_doubao/…` paths from a foreign AI sandbox) and compute the README-quoted BTCP score 0.8655 from typed constants. The Makefile uses 8 spaces instead of tabs — **every `make` target fails**. The claimed evidence file `crossvm_zero_bridge_result.json` does not exist in the repo.

The through-line of the entire audit: **the project's own honesty labeling is its most credible feature, and its own internal audit documents (TRION_AUDIT_REPORT.md, MAINNET_RUNBOOK) are its most truthful documents** — both concede what the README inflates. The repo shows an active, incomplete remediation arc: synthetic data is progressively being *labeled* (SYNTHETIC, "estimated", CONJECTURE, bootstrap disclosures) rather than removed.

---

## 2. What the repository actually is

- **Origin:** git history is a single author over ~3.5 months; root `package.json` still names the project `trion-arbilink-agent` — the repo grew out of an earlier "ArbiLink" Arbitrum hackathon ChainGPT-era app and was progressively re-skinned into the TRION whitepaper universe (ARCHITECTURE.md still describes the old Arb-Sepolia ChainGPT app; README describes the new protocol).
- **Languages:** Python (core engine, API, services, tests), Rust (21 indexer crates + BTCP crate), TypeScript (chains adapters, trion-0g SDK, relayers, two Next.js frontends, SDK), Solidity/Vyper/Cairo/ink!/Move/NEAR Rust/Soroban/FunC (contracts), Go (validator), C++ (FFT engine), Haskell (formal), Julia (math), Circom (ZK circuits), SQL (schema).
- **Live deployments:** 3 contracts on Arbitrum Sepolia (per ARCHITECTURE.md/deployments.json — from the hackathon era), plus a 0G-mainnet ExecutionGate read target baked into Railway env. **Every committed mainnet deployment and the live relayer wallet is the exact address (`0xdBbf66…42d20`) that the repo's own preflight tool blocks as "compromised"** per the BTCP Master Spec.

---

## 3. The genuinely strong tier (what works)

1. **Canonical Behavioral Hash** — the best cross-language artifact: 93-byte dual-strand construction, identical in `indexers/crates/trion-common`, `core/primitives/behavioral_hash.py`, `chains/shared/canonical_bh.ts`, and `faiss_service.py` ingest verification; invariant self-verified per hash.
2. **FAISS service data plane** (`anima-service/faiss_service.py`) — documented locking strategy, cross-process SQLite retry/backoff, atomic writes, TimescaleDB dual-write + cold-boot restore, honest `/stats` lock decisions, COLD_START refusal to fabricate.
3. **ANIMA engine** (`anima_engine.py`) — real crawls of EDGAR filing bodies (VADER NLP), GitHub API, news RSS, regulators, arXiv, GDELT; credibility ledger with decay; time-delayed outcome verification. A real feedback loop, not a mock.
4. **Rust BTCP crate** — uniform, unsafe-free, dependency-light; exactly 94 tests; 7 route types; weights match docs; netting/OOA/finality-max(A,B)/IAP-gas-split all as specified.
5. **EVM contracts** — `TRIONExecutionGate` (689 lines: quorum ECDSA, distinct-signer dedup, EIP-2 high-s rejection, AWA governance freeze, decision pruning), `BTCPEscrow` (CEI-clean; the sweepETH hardening fix verified sound), `ConfidentialCoherenceVault` BEO binding (verified genuine), `TRIONOracleV3` 300s verdict expiry (verified present).
6. **Hardhat test suite** (517 lines) — EIP-2 malleable-twin forgery, AWA freeze bits, storage-slot reentrancy simulation: the repo's best QA artifact.
7. **Go validator** — stdlib-only incl. clean-room Keccak; real DW-BFT math (Σ(t), d_j=1−corr(model,median), dynamic δ(t), HHI tiers with signal-freeze >4000); 821-line test suite.
8. **C++ FFT engine** — correct radix-2 Cooley-Tukey, PSD-entropy wash-trade detection, real stdin bridge used by the Python pipeline.
9. **schema.sql** — 33-table TimescaleDB design with hypertables, 7-day compression, and the working "thermodynamic deletion" trigger.
10. **Relayers** — genuinely fail-closed (halt on SILENCED or unreachable oracle), with honest SYNTHETIC labeling of non-EVM block-proof vectors.
11. **Institutional frontend** — Next.js 16 hash-routed terminal; all 20 distinct endpoints it polls verified to exist in the Flask app; BTCP K1 route simulator is a genuine server-scored simulation with fail-closed mode.
12. **Python math in core/** — coherence/moat/BH/consensus/BTCP formula implementations match the whitepaper exactly and pass self-tests; BIBL pattern store genuinely starts empty with Bayesian calibration; BRT uses real circular statistics over observed timestamps.
13. **Per-language CI is real** — Python/Rust/Go/Haskell/Julia/TS jobs that actually run those suites.

---

## 4. Critical bugs (highest severity, with file:line in companion reports)

| # | Bug | Where |
|---|-----|-------|
| 1 | `publish_signal()` has no body; real publish code orphaned as dead code inside `get_behavioral_signal()` → `/api/v1/publish/{id}` 500s on a ready relay | `api/blockchain.py:247-254`, dead code `:372-412` |
| 2 | CosmWasm: `from_json_bytes` infinitely recurses (every state read overflows); multi-denom escrow pays `amount` of *each* denom (value duplication) | `contracts/cosmwasm/` |
| 3 | SVM `lock_escrow` locks the funder's **entire wallet balance** (no amount parameter); Anchor program IDs mismatch `declare_id!` | `contracts/svm/` |
| 4 | TON FunC contracts non-functional as written: 4 files pack >1023 bits into single cells (guaranteed overflow), dict-value type confusion, `send_ton` amount misplaced into VALUE (0-TON payouts, stranded funds), deployer dataCell sets owner=zero (permanently bricked oracle) | `chains/ton/*.fc` |
| 5 | Makefile indented with 8 spaces — **every target fails** ("missing separator") while CONTRIBUTING.md mandates `make test` | `Makefile` |
| 6 | `from adapters.evm import …` — module doesn't exist → `/api/v1/stack/native` always 500s | `api/app.py:4303` |
| 7 | MEV event-type off-by-one: EVM/BOT indexers emit type **17 (FLASH_LOAN)** where canonical table says 16 (MEV_CAPTURE) — corrupts BH event semantics | `indexers/crates/*/src/main.rs` |
| 8 | KMS/HSM layer non-functional beyond env mode: SHA3-256 instead of keccak-256 for address derivation, AWS KMS curve mismatch, invented YubiHSM REST API, fail-open v-recovery | `relayer/kms_provider.js` |
| 9 | Move oracle writes one global signal while reading per-entity storage (always "not found"); AWA check hardcoded `true`; gate takes caller-supplied coherence | `contracts/move/` |
| 10 | NEAR timeout-revert refunds `predecessor` when entity_id isn't a valid AccountId — sweepable by anyone | `chains/near/` |
| 11 | chain-ID collisions reintroduced in JS/Python layer: SVM=900 & PVM=900; Sui=101 collides; 5 mismatches vs Rust indexers; `relayer_non_evm.js` uses its own ad-hoc scheme (btc=2000, sui=6001…) recreating the fixed bug class; three irreconcilable Solana IDs (200101/5773521/900) | multiple (report 02, 03) |
| 12 | sdk wasm calls `compute_coherence`/`shannon_entropy` which **do not exist** in the wasm module (empirically instantiated); sanctions check **fails open** (`sanctioned:false` on error); wrong API-key header | `sdk/src/` |
| 13 | `genesis_backfill_runner.py` imports a registry file that doesn't exist; phase7/final_cross_check/run_whitepaper_tests target pre-restructure paths; deploy/docker COPYs nonexistent root files; `deploy_akashic_proof.mjs` would deploy empty `"0x"` bytecode | `scripts/`, `deploy/` |
| 14 | TRIONGuardV3's 1h cool-down lets the owner keep the firewall off ~96% of the time, contradicting its own "cannot disable indefinitely" comment | `contracts/solidity/` |
| 15 | ZK Python Σ-protocol: all policy predicates (coherence-pass, travel-rule, fair-share) are prover-asserted booleans outside the proof statement; intent nonce leaks in proof_data | `zk/__init__.py` |

---

## 5. Claims vs reality (the flagship audit table)

| Claim | Verdict | Reality |
|---|---|---|
| "30/30 — 100% recall, F1 85.71%, $3.315B" (README Proven Results) | **UNSUPPORTED** | Committed `backtest/results/backtest_report.json`: all 40 entities coherence 0.0 (incl. all 10 innocent controls), FPR=100%, separation=0.0, archetype "Explorer" for everyone — a flag-everything run. Merkle root of on-chain anchor (d5f611…) ≠ committed tree (b4132f…). Held-out "non-circular" backtest never executed. |
| "105/105 formulas ALL PASS" | **CONDITIONAL** | Empirical re-run: 104 pass / 1 fail (PQC needs kyber-py/dilithium-py/pyspx; the failure is the honesty layer working). |
| "549 passed, 0 failed" (CHANGELOG 2.1.0) | **CONDITIONAL** | 555 collected = 549+6 **only with PQC deps**; bare env: 545 pass / 3 fail / 6 skip. |
| "671 passed" (README) | **STALE** | Full `pytest tests/` collects 930; unit+adversarial+root = 723; 671 matches nothing reproducible. |
| "Consensus 6/6 — 50 sybils, 75.8% nominal → 0.00% effective" | **UNVERIFIABLE** | No test in the repo produces this; "75.8" appears only in README. |
| Cross-VM BTCP table (0.8655/0.9205, "no asset left native chain") | **FABRICATED** | Scores hardcoded from typed constants in scripts that hardcode foreign-sandbox paths (`/home/user/.super_doubao/…`) — cannot run in this repo. Claimed evidence file `crossvm_zero_bridge_result.json` absent. |
| "Zero mock data — every signal published on-chain" | **FALSE** | ~60 hash-seeded synthetic Flask endpoints (leaderboard, SBA, XSL, MEV, Love, revenue, attack-sim with fabricated phase phis, price baselines); Φ features faked as phi×0.15; `_market_volatility()` = sin(t/3600)+md5-noise drives Θ(t). True only for bh_ledger/FAISS/ANIMA/CEX/backfill paths. |
| "CRISPR Defense: surgical excision of attack patterns" | **THEATRICAL** | Substring matching of mnemonics (`b"HARVEST_FLASH_LOAN_ORACLE_MANIP"`) against tx bytes; includes 5 fabricated 2026 attacks; zero real interception capability. |
| "Living Security: theft self-invalidating at N+1" | **TRUE in-memory only** | GenomicKey generations reset on restart (no persistence) — the property evaporates across restarts. |
| "96 mainnet-only chains" / "124 chains / 18 VM families" / "160 · 22" / "174 · 22" | **INCONSISTENT** | Counts oscillate 12/13/14/16/18/21/22/24/52/53/55/78/96/100/124/160/174 across docs and code; institutional frontend hardcodes "174 chains" while its own registry returns 160 (94 live, **23 testnet**, 43 indexed); registry has no network field, so "mainnet-only" is untrackable. |
| "BEO identity byte-for-byte identical across 6 VMs" | **CONTRADICTED** | Per-chain native encodings differ; four different beo_id truncations inside StarkNet alone; chain-ID collisions (above) corrupt the canonical BH input that BEO derives from. |
| "94/94 Rust tests" / "19/19 modules" | **TRUE by count** | 94 `#[test]`s, 20 `pub mod` — but sybil-resistance deviates on 4 of 5 layers vs spec (ln vs log₂, 0.5n vs 0.2n, linear vs 7n², ≥5 vs >20), 6-state escrow is 4-state, HHI scale 0–1 vs ×10⁴ elsewhere, `verify_proof` ignores reorg/expiry. |
| "ZK circuits 6/6 PASS — real secp256k1 Schnorr-Pedersen" | **HALF-TRUE** | Σ-protocols are real; but policy predicates are prover-asserted outside the statement, nonce leaks, and **zero build artifacts/zkeys/proofs committed** — unreproducible. Circom circuits structurally sound but unbuilt. |
| "7 Theorems" (Haskell formal verification) | **OVERSOLD** | GADT modeling + example-based boolean self-checks, not machine-checked proofs; T8 refutable with `dropAll _ = BHEmpty`; T9's "hash" is string concatenation. |
| "Mainnet deployment ready / live" | **NOT AS COMMITTED** | `deploy_mainnet.py` prints a plan, deploys nothing; on-chain "proofs" record placeholder hashes (`"ab"×16`), a random synthetic 1KB buffer's hash, or zero tx-hash commitments; every mainnet address in config.yaml is `0x000…0`; and all deployments came from the wallet the preflight itself blocks as compromised. |
| "HSM NON-NEGOTIABLE" | **ASPIRATIONAL** | KMS abstraction broken beyond env mode (bug #8 above). |
| "Σ=0.25 / K=0.10 / A=0.10 bootstrap" | **HONEST** | Genuinely disclosed — which concedes that today three of five planes are constants, and Σ's 10 seeded validators vote `gauss(oracle's own Φ, 0.05)` (circular). |
| "BIBL real historical matches" (audit fix) | **GENUINELY FIXED** | SQLite store starts empty, Bayesian calibration ≥10 samples. Real. |
| "PQC real FIPS 203/204/205" | **TRUE with deps** | Honest False otherwise. |
| "genetic transformer (real PyTorch)" | **TRUE** | Trained on disclosed synthetic data. |

---

## 6. Per-subsystem verdicts (one line each; details in companion reports)

- **core/** (149 files) — "A well-documented formula engine whose math is real but whose operational-security claims are synthetic." 24 specific bugs incl. fabricated future-dated evidence laundering, 5 duplicated conflicting module pairs, memory-only state everywhere. *(report 01)*
- **chains/ + trion-0g/** (100 files) — Demo-layer: 8 near-identical executors firing 1-wei self-transfers with φ fabricated as a loop-index ramp; best artifacts are `canonical_bh.ts` (byte-exact, but imported by nothing) and `svm_indexer.py`. TON contracts bricked; BIRP accepts unverified oracle signatures. *(report 02)*
- **indexers/ + validator/ + signal-processing/ + relayer/ + supervisors/** (82 files) — The real ingestion edge; hash_dna.rs is the repo's best file. MEV event-type off-by-one, KMS broken, ad-hoc chain-IDs in non-EVM relayer, quality uneven (StarkNet f7/f8 always 0, Sui uses tx digest as entity). *(report 03)*
- **contracts/ + hardhat/ + zk-circuits/ + zk/ + formal/ + math/** (119 files) — "Genuinely engineered EVM tier atop degraded multi-chain ports." CosmWasm/SVM/Move/NEAR/Soroban critical bugs; Vyper economics move no tokens; foundry tests empty; Deploy.s.sol commented out. *(report 04)*
- **frontend/ + frontend-institutional/ + sdk/** (75 files) — Institutional app is credible and live-wired (with silent fallback values + hardcoded "174 chains"); legacy frontend is a 134-page SPA with fabricated BOT-Chain metrics, invalid hex addresses, 100%-null wagmi contract map; SDK broken (nonexistent wasm exports, fail-open sanctions). *(report 05)*
- **api/ + anima-service/ + akashic/ + adapters/** (62 files) — "A real data spine under a heavily synthetic presentation layer." ~250 routes with three conflicting self-counts (131/139/194); the publish-path refactor accident; Σ circular; K empty; 0.85 prior. *(report 06)*
- **docs/ + spec/ + rust/ + proof-ledger/** (80 files) — "Three mutually inconsistent canonical layers (spec/ vs FORMULA_REFERENCE vs rust/), 0% spec-overlap for the Rust crate; code-level claims check out, protocol-level claims inflated or stale." Four different PCR/HA/CA expansions; four different BTCP acronym expansions. proof-ledger is honest at leaf level — and shows the compromised-wallet provenance. *(report 07)*
- **tests/ + backtest/** (63 files) — "A genuinely solid core wrapped in claims that fail re-execution." The degenerate backtest (above); conftest excludes the claims-bearing suites from headline counts; golden test's closing lines are hardcoded prints; the "36 inventions" never enumerated. *(report 08)*
- **scripts/ + zg/ + deploy/ + config/ + .github/ + top-level** (~112 files) — "Tier-one ops shell, tier-two breakage." Real preflights (incl. the compromised-wallet blocklist), real per-language CI — but dead Makefile, phantom audit artifacts, scripts citing files that don't exist, Slither/audit jobs `|| true`-masked, no CI job compiles the main 29-contract Solidity suite, LICENSE (CC0) contradicts package.json (MIT). *(report 09)*

---

## 7. Root patterns (cross-cutting)

1. **Evidence laundering** — synthetic data created in one module is cited as motivating evidence by another (fabricated "March 12, 2026 AAVE collapse" in `natural_liquidity.py` docstring ↔ fabricated CRISPR entry `AAVE_2026_LIQUIDITY`; simulated attack phis attached to real historical attack names on-chain).
2. **Count inflation & drift** — chains 12→174, VMs 12→22, tests 25→671→930, routes 131→139→194: every count has 2–4 simultaneously "true" values in the tree.
3. **Bootstrap constants as planes** — Σ, K, A are honestly-labeled constants today; C(t) is effectively Φ·M + constants; most profiles can never clear Θ.
4. **Memory-only state** — routes, escrows, disputes, genomic keys, annotations, slash ledgers: trust state evaporates on restart, contradicting the compounding/Akashic-depth narrative.
5. **The restructure scar** — v2.0.0's restructure left path-rot everywhere (channel impl_paths, audit-cited scripts that don't exist, deploy scripts targeting old layouts, Makefile/deploy/docker breakage).
6. **Honesty as the growth direction** — SYNTHETIC/estimated/CONJECTURE/bootstrap labeling, COLD_START refusals, fail-closed relayers, and the candid internal audit docs show real remediation intent, incomplete.

---

## 8. Recommended remediation priorities

1. **Fix the five ship-blockers:** `blockchain.py` publish dead-code; CosmWasm recursion/denom-duplication; SVM lock-entire-balance; TON cell overflows; Makefile tabs.
2. **Repair or delete the flagship evidence:** re-run the backtest with a working oracle and real benign controls (current committed run proves the opposite of the claim); reconcile the Merkle roots; execute the held-out backtest; run the cross-VM scripts from repo-relative paths (or remove the claims).
3. **Unify the registries:** one chain-ID namespace (the Rust canonical), one registry file, one count, add the `network` field; delete the ad-hoc relayer scheme.
4. **Pick one canonical spec layer** (spec/, FORMULA_REFERENCE, or docs) and align the other two; fix the sybil-resistance/HHI/escrow-state deviations in the Rust crate.
5. **Persist or remove in-memory trust state** (genomic keys, routes, escrows, annotations) — Akashic-depth claims are currently restart-fiction.
6. **Soften the README** to match the honest internal docs (TRION_AUDIT_REPORT's tone is the model); replace "105/105", "100% recall", "zero mock data", "mainnet live" with dependency-conditional truth; reconcile CC0/MIT.
7. **Commit ZK build artifacts or mark circuits experimental;** port the 300s verdict expiry to non-EVM oracles; add quorum to `publishBTCPRoute`; make sanctions checks fail-closed in the SDK.
8. **CI:** remove `|| true` masking, add a job that actually compiles `contracts/solidity/`, fix the stress-job `--ci` flag, make `make test` work.

---

## 8.5 Supplement: PR #4 — Cairo contracts (merged during the read)

After the main read completed, PR #4 (`feat: add Cairo 2.x contracts for Starknet deployment`, merge 59d9cd0) landed 22 new files. All were read in full and audited in **10-cairo-contracts-pr4-supplement.md**. Headline: a third Cairo generation now coexists with the two already in `chains/starknet/`; the ports are structurally clean Cairo 2.x but drop the EVM tier's security substance — `AttackSimulator.record_attack_proof` **hardcodes `would_have_blocked = true`** (self-labeled placeholder) and its `demo_attack_block` can never succeed (`assert(status != 1)` after `status = 1`); `TRIONFirewall.gate()` **always approves** ("Simplified: always approve for testing"); `ConfidentialCoherenceVault`'s coherence gate is an owner-set cache, the oracle is stored but never called, and `coherence_wrap` mints unbacked balance (no token custody); `TRIONOracleV3`'s `quorum_required` is stored but never checked and BTCP routes never expire; `AkashicProof` is deployer-asserted counters with an unused `manifest_hash` parameter; the `src/interfaces/` directory is **excluded from the build** (missing `mod interfaces;` in `lib.cairo`); no Cairo tests or CI were added. The Sensing Oracle port is the one near-production-quality contract.

---

## 9. Overall assessment

The repository's **mathematical skeleton is real and unusually well-documented** — formula-by-formula correspondence between whitepaper, spec, and code that is rare even in serious protocol repos. The **data spine (indexers → FAISS → ledger → ANIMA) is genuine**. The **security narrative is not yet real** — the immune system is substring matching, the consensus is a noisy echo, three of five planes are constants, and the flagship backtest proves zero discriminative power. The most valuable asset in the repo is its **honesty labeling culture and its own internal audit trail**; the recommended path is to finish the remediation arc it already started — label, persist, unify, and re-prove — rather than to continue layering claims on top of artifacts that cannot reproduce them.

*Deep-read reports: 01-core-engine.md · 02-chains-and-trion-0g.md · 03-indexers-validator-relayer-supervisors.md · 04-contracts-zk-formal-math.md · 05-frontends-sdk.md · 06-api-anima-service.md · 07-docs-spec-rust-proof-ledger.md · 08-tests-backtest.md · 09-scripts-deploy-ci-top-level.md · 10-cairo-contracts-pr4-supplement.md (this directory)*
