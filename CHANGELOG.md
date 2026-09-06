## [Unreleased — Canonical Reconstruction, Waves 1–4] — 2026-09-04

Autonomous multi-wave reconstruction loop (per TRION master command): a frozen
specification hierarchy was established, every normative requirement extracted
into a matrix, and the implementation brought into conformance — with honest
labels wherever a component is research/partial/external. Append-only record:
`docs/audit/AUTONOMOUS_MASTER_WORKLOG.md`.

### Wave 1 — Foundation (d7ca82e…298a1d6)
- `docs/audit/CANONICAL_SPEC_MATRIX.md`: 107 requirements + 22 spec conflicts
  (K1–K22) resolved against the authoritative set (WHITEPAPER_MD, WHITEPAPER_V2,
  BTCP_SPEC, L0–L9 + supporting tables).
- `docs/protocol/CANONICAL_BH.md`: canonical 93-byte BH layout; py/TS/rust
  builder parity fixes (deterministic rust magnitude + timestamps across 21
  indexer crates); 52 golden vectors / 134 tests.
- `docs/protocol/CANONICAL_CERTIFICATE.md` + `core/consensus/certificate.py`:
  346-byte cross-VM certificate with per-family domain separation; validator
  security audit opened as the Wave 2 work order (C-01…C-06, H-01…H-08).
- `docs/protocol/BTCP_STATE_MACHINE.md` (26 states / 33 transitions) +
  `docs/security/CANONICAL_INVARIANTS.md` (INV-001…022; py layer 18 ENFORCED /
  3 PARTIAL / 0 UNENFORCED; 49 attack tests).

### Wave 2 — VM Security Parity (942a503…eaa5daa)
- EVM: `CanonicalCertificate.sol` library + `TrionEpochRegistry`; V4
  `submitCertificateAttestation` (§6 sequence, weight quorum, nonce ordering,
  equivocation evidence); permissionless `BTCPEscrow.releaseEscrowCanonical`;
  M-05 bind-time oracle-interface pinning.
- Solana: oracle-key release gate replaced by certificate verification (C-03).
- Move: `coherence_verified` relayer flag removed; permissionless release on
  canonical certificate (C-02).
- TON (C-01) + NEAR (C-05): full §6 sequences, native ed25519, epoch dicts,
  forward-only registration.
- Starknet/Cairo: escrow + execution gates closed (C-04); Vyper: dynamic quorum,
  structurally fail-closed (M-03); PVM legacy oracle honestly labeled
  non-production.
- Battery: 47 contract pytest + 574 direct-script checks across 9 real-VM
  suites; all green.

### Wave 3 — Infrastructure, Math, API Truth (dcda8d5…1de698d)
- Registry: one canonical `config/chain_registry.json` enforced everywhere
  (129 chains / 18 VM families / 40 integrated; disposition matrix for
  hardcoded chain-id sites).
- Math: AWA canonical 6-condition set + fail-closed `EmissionGate` (no unfreeze
  API); HHI 4000-CRITICAL; second-based value-tier TTL (py/rust/doc identical);
  29 canonical signal types per the M-073 owner ruling (19 base + 10
  BTCP-family; id space fork-gated at 24); wash-trading D_eff discount +
  conservation audit; clipboard expiry + BEO witness binding + persisted
  per-entity nonces. Master formula verification: 104/0/1 — "ALL FORMULAS
  ENFORCED AS SPECIFIED".
- API/relayer/SDK: truth boundaries (caller-supplied truth labeled, settlement
  gate derived from persisted proofs, tolerance caps, SSRF guard, X-API-Key
  write auth — 34-test attack battery); relayer documented as submit-only
  single-signature custody; SDK trust model (no client-side signing/quorum
  truth).
- Storage: all 35 `schema.sql` tables dispositioned (12 operative sqlite-mirror,
  6 deploy-gated, 17 honest `NONE`), atomic step-6 writes, crash-injection
  tests, replay/equivocation store guards.
- Deployment: custody matrix (dev-only raw keys refused under
  `TRION_ENV=production`; KMS/HSM path), per-profile topology, runbook truth,
  zero dead env vars.
- API emission gate: AWA freeze wired into `/api/v1/publish` (frozen ⇒ 503
  `silence:true`, no chain write).
- Battery at close: 1019 unit + 9 skipped · 87 btcp + 1 xfail · 134 golden ·
  contract suites green · master formula 104/0/1 · api truth 34/34.

### Wave 4 — Red Team / Restructure / Docs Conformance (this entry)
- P (red team) and Q (dead-code restructure) ran in parallel; this entry
  records the docs-conformance pass (Agent R): README/ARCHITECTURE/SECURITY
  updated to the current architecture truth (canonical certificate verification
  on every VM tier, AWA emission freeze, two ingestion paths, storage
  dispositions, honest labels); stale counts swept (tests, routes, chains,
  crates, signals, HHI, TTL); K1–K22 resolution banners added to the affected
  `spec/*.md` layer docs; cross-reference integrity pass over `docs/**`.

# Changelog

All notable changes to TRION Protocol are documented here.

## [2.2.0] — 2026-09-02 — Master Agent Command: Phase 0-4 Execution

Autonomous protocol-architect session per TRION_MASTER_AGENT_COMMAND: spec-first
audit (BTCP Master Implementation Spec + TRION Whitepapers read completely),
then Security → Correctness → Completeness → Consolidation → Verification.

### Phase 0 — Environment & Safety
- Full-repo backup + working branch `agent-fix-phase-1`; baseline locked.
- Secret scan: **clean** — zero hardcoded private keys/mnemonics/API keys
  (64-hex hits are backtest exploit tx hashes; PVM mnemonic is env-injected).
- Installed missing PQC deps (kyber-py, dilithium-py, pyspx) — the 3 baseline
  test failures were dependency-only; baseline now 549→0 failures.

### Phase 1 — Security & Correctness (P0)
- **Σ(t) de-circularized** (faiss_service.compute_bft_sigma): validator votes
  were `gauss(phi_adj, 0.05)` — an echo of the oracle's own output carrying no
  independent information. Validators now vote from the entity's REAL behavioral
  records (per-validator staggered view windows = height-offset observers),
  ABSTAIN without data, and rounds under 3 voters return the documented
  SIGMA_BOOTSTRAP=0.25 with `bootstrap_cold_start` status + disclosure (mirrors
  core/spiritual/sigma_engine.py + deployment.env).
- **CosmWasm escrow**: infinite-recursion deserializer (stack overflow on every
  state read) fixed; multi-denom payout duplication (2× fund inflation) fixed
  with per-denom `locked_coins` records, fail-closed legacy state.
- **SVM btcp_escrow**: locked the funder's ENTIRE wallet balance — now takes an
  explicit amount with InsufficientFunds check.
- **Move trion_oracle**: publish/read used different storage paths (every read
  aborted E_SIGNAL_NOT_FOUND) — unified on one SignalRegistry table.
- **BTCPGasAbstraction**: payer overpayment was forfeited to owner — now
  refunded at settlement (CEI preserved, new refund-failure events).
- **TRIONGuardV3**: 24h bypass was re-armable (~96% firewall-off time) — capped
  at 3 lifetime re-arms (fail-closed exhaustion).
- **NL score engine verified spec-exact** (whitepaper L7.1): LD entropy, LO
  sybil ratio, LC Pearson-vs-baseline, LS stress ratio; simulated March 12 2026
  AAVE scenario (synthetic test vector, not a real event) NL=0.000 < 0.30 →
  alert fires (matrix #13 PASS).
- **Schema audit**: all 7 spec-required BTCP tables present (33 total) with FK
  constraints; sqlglot-validated (86 statements; DO-blocks structurally balanced).

### Phase 2 — Missing Components (P1)
- **rust/btcp_proof_builder**: verify_proof now enforces a reorg/expiry window
  (MAX_PROOF_VALIDITY_BLOCKS=50_000, inclusive boundary) — previously accepted
  arbitrarily stale proofs.
- **rust/bibl_engine**: detect_fork stub (hardcoded retention values) → real
  stored-hash vs current-hash reorg detection with chain suspension.
- **rust/sybil_resistance + genesis_commitment**: all 5 Sponsored-Genesis layers
  aligned to spec §9.3 — log₂ (was ln), 1+0.2n scrutiny (was 0.5n), strict
  >0.85 similarity, 7·n² days spacing (was linear), >20 star threshold (was ≥5).
- **core/extended/biological_rhythm**: real BRT-gas circular-linear correlation
  with p-value significance + ANIMA fallback rule (spec: p>0.05 → fallback).
- **core/master/signal_factory**: provenance chain now carried (was always []);
  broken akashic.brt_scheduler import repaired.
- **core/btcp/orchestrator**: dummy ZK witness + hardcoded IAP economics →
  honest zk_pending deferral status.
- **core/mental/anima/data_streams**: OBSERVED | CLOCK_FALLBACK source labeling.
- **core/btcp/bibl_engine**: statistical finality distribution in BIBL snapshot.

### Phase 3 — Consolidation (P2)
- btcp_price_oracle.py: 2 copies → 1 canonical (core/price/) — matrix #18.
- config/chain_registry.json: single source of truth created, readers updated,
  superseded registries removed — matrix #17; scripts/generate_chain_bindings.py
  emits bindings from the canonical registry.
- Dead code deleted (dependent-verified): replit platform files,
  attack_alert_webhook.py (Replit-only), regenerable build artifacts;
  .gitignore hardened.
- docs/architecture/RESTRUCTURE_PLAN.md: full target-layout migration map with
  phased risk assessment (P2 architectural gap documented per completion
  criteria).

### Phase 4 — Verification & Honesty
- **bh_cross_language_vector.py repaired** (was failing on original main):
  schema path + key structure fixed; sense/antisense digests now verified
  byte-exact against the canonical vector (matrix #14 PASS).
- BTCP_ROUTE in all 5 SDK surfaces (matrix #19); SILENCE V2 event carries
  coherence_gap + etaBlocks (matrix #20, V1 topic0 stable for indexers).
- Unit suite: 549 → **573 passed, 0 failed** (+24 new tests). Full-tree
  failures are pre-existing live-service integration tests — byte-identical
  failure set verified against the pristine backup (Golden Rule parity).
- Honest plane-status disclosure: Σ bootstrap 0.25 until validators observe
  records; K proxy (0.7Σ+0.3A) until annotations exist — both machine-readable
  via `bootstrap` flags.

### Environment-Limited Checks (documented)
cargo/forge/solc/slither/echidna/docker/psql unavailable in this sandbox —
Rust/Solidity/Docker matrix items deferred to CI; all Rust changes are
hand-traced against their 95 unit tests, contract changes verified by
full-context reading + Python settlement-math simulation.
# Changelog

All notable changes to TRION Protocol are documented here.

## [2.1.0] — 2026-09-01 — Master Agent Audit & Remediation

### Independent Master-Command Audit (source: BTCP Master Spec + whitepapers)
Spec Compliance Matrix verified against the PDFs: five-plane C(t), NL(LD·LO·LC·LS),
BTCP_score weights, Θ(t), all 21 BTCP Rust modules, all BTCP contracts, ZK
scaffolds, and the 25-table schema are REAL and present — the BTCP spec §2
"MISSING" list is obsolete post-restructure. The audit's real findings were
operational path-rot and honesty gaps, all fixed below.

### Fixed — CI / Build / Deploy
- **ci.yml**: flagship test job ran pre-restructure paths (tests/test_*.py) —
  failed on collection since the v2 restructure. Rewired to tests/unit|integration;
  added the deps the suites import (ecdsa, pynacl, hypothesis, kyber-py,
  dilithium-py, pyspx) so the PQC round-trip assertion is verifiable in CI.
- **Dockerfile.railway**: `COPY trion-svm/` referenced a directory removed in
  the v2 restructure — Railway build failed as committed. Removed (SVM content
  lives in indexers/ + chains/solana/, both already copied).
- **railway-entrypoint.sh**: Go validator package dir fixed (cmd/trion-validator,
  was cmd/validator); one-shot self-test no longer daemonized as a fake server;
  C++ signal binary name fixed (trion_fft_engine --stdin, there was never a
  trion_signal target).
- **Makefile**: deploy target now runs the real flow (preflight →
  scripts/deploy_mainnet.py) instead of the removed scripts/deploy_testnet.sh.
- **package.json / tsconfig.json / SECURITY.md**: removed scripts pointing at
  never-committed files; inlined the missing external tsconfig.base.json;
  replaced the reference to a KEYS file that was never committed.
- **supply-chain.yml**: Slither paths fixed to contracts/solidity/*; npm
  lockfile loop now discovers all package.json dirs (zg has none — was a no-op).
- **run_0g_full.sh / run_crossvm_zero_bridge.py**: hardhat project path fixed;
  dev-machine hardcoded result path removed.

### Fixed — 0G / zg subsystem
- **ZG-1**: zg daemons resolved trion-0g as <repo>/zg/trion-0g (never existed)
  — every SDK upload failed silently; ANIMA compute always returned "queued".
  Added repo-anchored TRION_0G_DIR resolver used by all paths + correct cwd.
- **ZG-2**: 0G mainnet chain-id 16601 (a typo) corrected to 16661 everywhere
  (faiss_service evm_chains set, zg_config, .env.example, .replit).
- **ABI-1/2**: AkashicProof ABI artifact committed (source-derived, 41 functions
  + 7 events, generator script with source-coverage verification). The 3 zg
  loaders + deploy scripts referenced it via CWD-relative paths that never
  resolved; fallback ABI was stale (getFullProof really returns 10 outputs).

### Fixed — Chain registry integrity
- 4 literal duplicate chains removed (Cardano/Algorand + testnets existed as
  BOTH UTXO 210xx stubs AND live-indexer entries); header counts corrected
  (129 total / 40 integrated / 18 VM families per the config/chain_registry.json
  recount — 2026-09-04 correction; the 124/41 figures recorded at 2.1.0
  predated the Wave-3 registry recount).
- Dead divergent TS registry deleted (zero importers; namespace collided with
  relayer TRON=7001 and SVM 900).
- api gap-fill entries pointed at canonical live-indexer families; supervisor
  chain-id comments corrected to real indexer constants.

### Added — Testing
- **math/test/runtests.jl**: real suite over every TRIONMath function (was a
  1+1==2 placeholder that never imported the module). + ci-julia.yml workflow.
- **formal/test/Spec.hs**: real hspec suite over all 9 theorems (was a println
  stub). package.yaml restructured with proper library + Main wrapper; CI
  runs the spec.
- hypothesis dependency declared in pyproject.toml.

### Fixed — Relayer honesty
- **REL-1**: relayer_non_evm self-halt aligned to fail-closed (was permissive —
  proceeded when the oracle was unreachable; relayer.js already failed closed).
- **REL-2**: extended-chain block-proof vectors now labeled
  data_provenance=SYNTHETIC_BLOCK_PROOF / synthetic=true — fabricated
  sha256-derived features are distinguishable from real behavioral-indexer
  vectors in FAISS.

### Verified
- pytest tests/unit/: **549 passed, 6 skipped, 0 failed**
- golden_test.py: ALL SYSTEMS VERIFIED (124 chains / 18 VM families,
  105 formulas, 36 inventions)
- chain_coverage_audit: no regression (identical pre-existing VM-name mismatches)
- PQC round-trip: kyber/dilithium/sphincs real cryptographic verification PASS
- Rust/Solidity compile checks: not runnable in this environment (no cargo/forge) —
  CI workflows cover both (ci-rust.yml, ci-solidity.yml + hardhat build)


## [2.0.0] — 2026-08-13

### Institutional-Grade Restructure
- Restructured entire repository to match institutional-grade execution plan
- `src/` → `core/` with exact module layout (primitives/physical/akashic/mental/spiritual/master/extended/novel/governance)
- `oracle_api/` → `api/` with routes/ and middleware/ structure
- `akashic/` → `anima-service/`
- `rust-indexers/` → `indexers/`
- `go/` + `p2p/` → `validator/` with cmd/internal/test structure
- `cpp/` → `signal-processing/`
- `math/formal_verification.hs` → `formal/src/TRION/Theorems.hs`
- `math/trion_entropy_verification.jl` → `math/src/TRIONMath.jl`
- `wasm/` → `sdk/src/wasm/`
- `tests/` restructured into `unit/` + `integration/` + `adversarial/`

### New Components
- 14 `spec/` files with canonical specifications from whitepapers
- `Makefile` for top-level build/test orchestration
- `CONTRIBUTING.md` and `CHANGELOG.md`
- `core/pyproject.toml`
- `contracts/foundry.toml` + `contracts/script/Deploy.s.sol`
- 7 GitHub CI workflows

### BTCP + Continuum
- 8 BTCP smart contracts (Intent, Escrow, BLO, Route, LiquidityOcean, GenesisCommitment, TravelRuleCompliance, VersionRegistry)
- ContinuumDEX.sol with 5 engines (BID, CME, PMO, BDC, thermodynamic settlement)
- trion-botchain — 14th Rust indexer crate for BOT Chain (chainId 677)

### Bug Fixes
- trion-pi chain_id collision (7001 → 8001)
- Go SHA-256 → SHA3-256 (clean-room Keccak implementation)
- NEAR event_type mapping (STAKE=3, UNSTAKE=4, BORROW=7, REPAY=8)
- TON duplicate match arm + f7/f8 feature duplication
- Movement testnet endpoint removed from production

### Consolidation
- 4 relayers → 2 (EVM + non-EVM)
- Single unified frontend (17 dashboard pages)
- All 14 programming languages wired live
