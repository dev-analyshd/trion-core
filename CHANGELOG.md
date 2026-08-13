# Changelog

All notable changes to TRION Protocol are documented here.

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
