# Language Matrix — Components, Production Usage, Integration Status

**Task ID:** 9-c · **Source:** deep-read worklog (Tasks 4-a…4-i, 7 synthesis) + matrix M-233/M-234/M-235/M-236; re-checked against this session's toolchain use.
**Integration legend:** CONNECTED = wired into the running pipeline and exercised by tests this sandbox can run · DISCONNECTED = genuine standalone implementation, not called by the running services · UNBUILDABLE-IN-SANDBOX = statically verified only (toolchain absent) · UNBUILT = sources exist, no artifacts.

Language-stack note (M-233, contradiction-flagged): D1 assigns Rust to "core protocol"; the repo's core engine is Python (154 files/50k lines) with Rust as the parity/indexer/BTCP layer. D2 self-counts 10 languages while listing 11 rows. All 10 mandated languages are present.

---

| Language | Component(s) | Size (deep read) | Production usage | Integration status | This session |
|---|---|---|---|---|---|
| **Python** | core/ engine (154 files), api/ Flask Oracle (11k lines, ~181 routes), anima-service/ FAISS FastAPI (11k lines, 165 routes), backfill + regulatory + price engines, full test suite (~97 files, ~1730 pytest functions) | ~337 files | THE behavioral engine + both services; the relayer polls it; everything else feeds it | **CONNECTED** — pytest runs (1650P baseline; targeted waves this session); Flask boots from repo root; FAISS boots keyed | FAISS auth + key threading (7-a/8-a); Flask fail-closed/CORS/SHA3/SSRF (7-c); SILENCE/provenance (8-c) |
| **Rust** | indexers/ (22-crate workspace: 21 chain crates + trion-common), rust/ trion-btcp (21 lib modules + 2 bins, 147 #[test]), contracts/{cosmwasm, svm-programs, ink} | ~89 files | chain ingest → canonical BH → FAISS (X-API-Key now); BTCP routing suite | **CONNECTED (design) / UNBUILDABLE-IN-SANDBOX** — no cargo; statically verified (golden-vector pins, brace balance, field maps) | hash integrity 5 crates + hedera (7-d/8-b); event bytes; faiss.rs key headers; **cargo check remains mandatory follow-up** |
| **Go** | validator/ (Tendermint-style BFT, 36 tests; validator_mesh, bft_mesh, crawler coordination), network/health_monitor.go (19 endpoints) | ~20 files | validator node software — designed for the (nonexistent) fleet | **DISCONNECTED operationally / UNBUILDABLE-IN-SANDBOX** (no go toolchain) | untouched; fleet gap unchanged (M-184) |
| **TypeScript/JS** | relayer/relayer.js + kms_provider.js, evm-tools (compile/deploy), sdk/ (TrionSDK.ts + wasm), 2 Next.js 16 frontends, chains/starknet bridges, btc-tools | ~143 files | signal publication relay (single-sig), EVM deploy toolchain, SDK, operator UIs | **CONNECTED** — node/bun/tsc exercised this session; frontends reach services via server-side proxies | derive-address redaction (7-e); birp-bridge real signing + 4 test-script paths (7-b) |
| **Solidity** | contracts/solidity (51 files: TRIONOracleV3, BTCPEscrow, ExecutionGate, Intent/Route/BLO/Genesis/TravelRule/GasAbstraction, vaults, AttackSimulator) + hardhat twins + compiled artifacts | 51 files | on-chain oracle + escrow value path; testnet-deployed (self-reported) | **CONNECTED** — compiles under BOTH solc 0.8.24 (solcx via_ir) and solcjs 0.8.36 (compile.mjs); artifacts regenerated + pinned | escrow-bound digest (7-f); SHA3-256 publish identity (7-c) |
| **Vyper** | contracts/vyper (TRIONToken.vy, BTCP_ESCROW.vy) | 2 files | security-critical token + oracle-attestation escrow tier | **CONNECTED** — vyper 0.3.10 (exact version required; undeclared dep — housekeeping item) | escrow tier untouched by design (oracle-tier, not canonical-cert path) |
| **Cairo** | contracts/starknet (33 files: BIRPAttestation, trion_certificate, btcp_escrow, epoch registry…), chains/starknet crate + bridges | 33 files | Starknet attestation/escrow tiers | **PARTIALLY BUILDABLE** — chains/starknet compiles (fixed this session, scarb 2.8.4+2.10.1); BIRPAttestation clean in isolated crate; **contracts/starknet crate still fails on 34 pre-existing corelib-skew errors in 4 files** (trion_certificate 17, btcp_escrow 15, BTCFiGuard 1, trion_epoch_registry 1) | SEC-04 rewrite + SEC-06 fix + SEC-25 paths (7-b) |
| **FunC (TON)** | contracts/ton/token.fc (18 FunC files incl. tests) | 18 files | TRION token TON tier | **UNBUILDABLE-IN-SANDBOX** (no func) — TRUTHFUL-NOTE u64 unit hazard (SEC-12, open) | untouched |
| **Move** | contracts/move (7 files), chains/pvm genesis/travel-rule | 7 files | Aptos/Move VM tier | **UNBUILDABLE-IN-SANDBOX** — static; mirror tests cover logic in Python | untouched |
| **NEAR TS** | chains/near (deploy scripts, contracts) | — | NEAR tier | **UNBUILDABLE-IN-SANDBOX** — static; deploy scripts carry the Replit-path/portability note | untouched (dead cjs/mjs duplicate flagged in FILE_DISPOSITION) |
| **Anchor (SVM)** | contracts/svm (btcp_common/escrow/intent/route programs + Anchor) | — | Solana VM tier | **UNBUILDABLE-IN-SANDBOX** — Cargo redirect to contracts/svm/programs (CLEANUP-1 consolidated); svm mirror tests in Python | untouched |
| **CosmWasm (Rust)** | contracts/cosmwasm (contract.rs, state.rs) | — | Cosmos VM tier | **UNBUILDABLE-IN-SANDBOX** — P1 fixes verified statically pre-audit (SEC-11) | untouched |
| **Soroban (Rust)** | contracts/soroban | — | Stellar VM tier | **UNBUILDABLE-IN-SANDBOX** — static | untouched |
| **Haskell** | formal/ (Theorems + hspec, 642 L) | 642 L | formal verification layer (consensus-safety statements) | **DISCONNECTED research layer** — runs in CI (runghc workflow), not consumed by services; theorem-as-type encoding not achieved (M-235) | untouched |
| **Julia** | math/ (471 L) + ci-julia workflow | 471 L | scale-invariance / entropy-budget / PI validation | **DISCONNECTED research layer** — CI-only | untouched |
| **C++** | signal-processing/ (651 L) | 651 L | FFT / signal conditioning (spec'd) | **DISCONNECTED** — FFT/hardware-driver usage not evidenced (M-236) | untouched |
| **WebAssembly** | sdk/src/wasm signal_processor.wat (298 L) + compiled .wasm | 2 files | browser-side signal processing (24 types, threshold, coherence, BRT) | **CONNECTED** — WebAssembly.Module.exports verified in the canonical sweep | untouched |
| **Circom** | zk-circuits/ (5 circuits: intent commitment, complementarity, behavioral credential, travel rule, IAP share) | 12 files | ZK privacy legs | **UNBUILT** — no zkeys/r1cs/ptau/verifiers; ceremony pending (SEC-08, open) | untouched |

---

## Reading the matrix

- **The runtime spine is Python + TS + Solidity** (engine, relay, chain) with Rust statically-verified on both sides of the spine (ingest in, BTCP suite beside it). Go/Cairo-non-starknet-chain/Haskell/Julia/C++ are honest research or future-tier layers.
- **Contract breadth vs spec:** 9–10 contract languages against a spec that says contracts exist for "exactly two things" (M-168 CONTRADICTORY). The breadth is deliberate (cross-VM parity is a core claim: certificate verification implemented in 6+ VM families).
- **Toolchain boundary:** every UNBUILDABLE-IN-SANDBOX row was compensated in-session with static verification (full-file reads, byte/field maps, brace balance, mirror tests in Python) — this is the repo's standing verification boundary, recorded in EXTERNAL_VERIFICATION_BOUNDARIES.md and RISK_REGISTER.md.
- **The Cairo exception:** chains/starknet went E0005-failing → compiling this session; the contracts/starknet 34 corelib-skew errors pre-date this session and are twin-pinned to contracts/cairo — a version-migration item for the cairo owner, not a new regression.
