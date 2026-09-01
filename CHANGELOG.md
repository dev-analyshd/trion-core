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
  (124 total / 41 integrated / 18 VM families, recounted distribution).
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
