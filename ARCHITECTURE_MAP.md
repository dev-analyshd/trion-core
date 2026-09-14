# TRION Protocol — Architecture Map

**Status:** NORMATIVE
**Identity:** dev-analyshd
**Date:** 2026-09-14

---

## What TRION Is

TRION is a behavioral truth oracle and cross-chain settlement protocol. It
computes a single coherence signal C(t) from on-chain and off-chain data,
emits canonical certificates via diversity-weighted BFT, and routes
liquidity cross-chain through the Bitcoin-Backed Cross-Chain Protocol
(BTCP) — without wrapping, minting, or bridging tokens.

The master equation:

```
T(t) = [C(t) ≥ Θ(t)] · C(t) · e^(M_moat)
```

Where:
- C(t) = α·Φ_adj(t) + β·M_adj(t) + γ·Σ(t) + δ·K(t) + ε·A(t)
- Θ(t) = Θ_min + (Θ_max − Θ_min)·V(t)
- M_moat = e^(D·Q·R·X·F·N)

---

## 10 Build Levels (L0–L9)

| Level | Name | Status | Key Components |
|-------|------|--------|----------------|
| L0 | Ingestion | BUILT | `indexers/` (21 Rust crates), `api/` (bh_streamer 96 workers) |
| L1 | Behavioral Planes | BUILT | `core/spiritual/`, `core/manipulation/`, `signal-processing/` |
| L2 | Coherence Engine | BUILT | `core/consensus/`, `math/` (formulas), `formal/` (Haskell proofs) |
| L3 | Canonical Certificate | BUILT | `core/consensus/certificate.py` (346-byte payload), `validator/` (Go BFT) |
| L4 | On-Chain Publishing | BUILT | `contracts/solidity/`, `contracts/svm/`, `contracts/move/`, etc. |
| L5 | BTCP Cross-Chain Router | BUILT | `core/btcp/`, `btc-tools/`, `relayer/` |
| L6 | Frontend Dashboard | BUILT | `src/` (Next.js 16, React 19) |
| L7 | ZK Behavioral Layer | BUILT | `zk/stark/` (Cairo), `zk/groth16/` (circom) |
| L8 | Governance + Slashing | PARTIAL | `core/governance/`, `validator/internal/slashing/` |
| L9 | Akashic Index | BUILT | `akashic/`, `core/akashic/`, `trion-0g/` |

---

## 5 Behavioral Planes

| Plane | Symbol | Formula Component | Implementation |
|-------|--------|-------------------|----------------|
| Physical | Φ | α·Φ_adj(t) — 9 Shannon entropy signals | `signal-processing/src/`, `core/manipulation/` |
| Mental | M | β·M_adj(t) — prediction confidence | `core/manipulation/prediction/` |
| Spiritual | Σ | γ·Σ(t) — diversity-weighted BFT | `core/spiritual/consensus.py`, `validator/` |
| Conscious | K | δ·K(t) — human annotation | `core/agent/`, `supervisors/` |
| ANIMA | A | ε·A(t) — cross-domain AI calibration | `anima-service/`, `core/agent/` |

Bootstrap parameters (from `config/deployment.env`):
- α (SIGMA_BOOTSTRAP) = 0.25
- β (K_BOOTSTRAP) = 0.10
- γ (ANIMA_BOOTSTRAP) = 0.28
- Θ_min = 0.55, Θ_max = 0.92

---

## 20 Communication Channels

| # | Channel | VM | Adapter | Contract Dir | Status |
|---|---------|----|---------| ------------- |-------|
| 1 | Ethereum | EVM | `adapters/evm/` | `contracts/solidity/` | BUILT |
| 2 | Arbitrum | EVM | `adapters/evm/` | `contracts/solidity/` | BUILT |
| 3 | Base | EVM | `adapters/evm/` | `contracts/solidity/` | BUILT |
| 4 | Optimism | EVM | `adapters/evm/` | `contracts/solidity/` | BUILT |
| 5 | Starknet | Cairo | `chains/starknet/` | `contracts/starknet/`, `contracts/cairo/` | BUILT |
| 6 | Solana | SVM | `adapters/svm/` | `contracts/svm/` | BUILT |
| 7 | Sui | Move | `chains/sui/` | `contracts/move/` | BUILT |
| 8 | Aptos | Move | `adapters/move/` | `contracts/move/` | BUILT |
| 9 | NEAR | NEAR | `chains/near/` | `contracts/near/` | BUILT |
| 10 | TON | Tact | `chains/ton/` | `contracts/ton/` | BUILT |
| 11 | Stacks | Clarity | — | `contracts/clarity/` | BUILT |
| 12 | Stellar | Soroban | — | `contracts/soroban/` | BUILT |
| 13 | Cosmos | CosmWasm | `adapters/cosmos/` | `contracts/cosmwasm/` | BUILT |
| 14 | Polkadot | PVM | `chains/pvm/` | `contracts/pvm/` | BUILT |
| 15 | Bitcoin | UTXO | `btc-tools/` | — (UTXO) | BUILT |
| 16 | OOA | Out-of-band | `adapters/ooa/` | — | BUILT |
| 17 | CosmWasm | Wasm | `adapters/cosmwasm/` | `contracts/cosmwasm/` | BUILT |
| 18 | Move (generic) | Move | `adapters/move/` | `contracts/move/` | BUILT |
| 19 | SVM (generic) | SVM | `adapters/svm/` | `contracts/svm/` | BUILT |
| 20 | EVM (generic) | EVM | `adapters/evm/` | `contracts/solidity/` | BUILT |

---

## 19 Signal Types

The Physical plane (Φ) computes 9 Shannon entropy signals. Combined with
the Mental plane's prediction confidence, the system tracks 19 distinct
signal types:

1. Price manipulation (flash crash/spike)
2. Volume anomaly (wash trading)
3. Order flow imbalance
4. Spread compression
5. Latency arbitrage fingerprint
6. MEV sandwich detection
7. Oracle stalemate / silence
8. Validator coordination collapse
9. Cross-domain divergence
10. Liquidity drain
11. Funding rate divergence
12. Basis trade unwind
13. Stablecoin depeg
14. Governance attack
15. Bridge censorship
16. Front-running
17. Back-running
18. Time-bandit (reorg)
19. Long-range attack

Implementation: `core/manipulation/`, `signal-processing/src/`

---

## 7 Manipulation Fingerprints

| # | Fingerprint | Detection | Status |
|---|-------------|-----------|--------|
| 1 | Latency arbitrage | `signal-processing/src/latency_arb.rs` | DETECTED |
| 2 | MEV sandwich | `core/manipulation/sandwich.rs` | DETECTED |
| 3 | Wash trading | `core/manipulation/wash_trade.rs` | DETECTED |
| 4 | Oracle staleness | `core/manipulation/oracle_stale.rs` | DETECTED |
| 5 | Coordination collapse | `core/spiritual/coordination.py` | DETECTED |
| 6 | Cross-domain divergence | `core/manipulation/cross_domain.rs` | DETECTED |
| 7 | Long-range attack | `validator/internal/security/` | DETECTED |

---

## Core Directories

| Directory | Purpose | Key Files |
|-----------|---------|-----------|
| `adapters/` | Cross-VM adapter layer (Rust) | `adapters/core/`, `adapters/evm/`, `adapters/svm/`, `adapters/move/` |
| `akashic/` | Akashic Index (event store) | `akashic/`, `trion-0g/` |
| `anima-service/` | ANIMA AI calibration service | `anima-service/` |
| `api/` | REST API + bh_streamer | `api/routes/`, `api/middleware/` |
| `backtest/` | Replay engine + held-out results | `backtest/replay_engine.py` |
| `btc-tools/` | BTC + cross-chain tooling (JS) | `btc-tools/*.mjs` (149 scripts) |
| `chains/` | Per-chain client code | `chains/starknet/`, `chains/svm/`, `chains/near/` |
| `config/` | Deployment configs | `config/deployment.env` |
| `contracts/` | Smart contracts (all VMs) | `contracts/solidity/`, `contracts/svm/`, `contracts/starknet/` |
| `core/` | Python core (planes, consensus, BTCP) | `core/spiritual/`, `core/consensus/`, `core/btcp/` |
| `docs/` | Documentation | `docs/ARCHITECTURE.md`, `docs/protocol/` |
| `evm-tools/` | EVM-specific tooling | `evm-tools/compiled/` |
| `formal/` | Haskell formal proofs | `formal/src/`, `formal/app/` |
| `hardhat/` | EVM Hardhat project | `hardhat/contracts/`, `hardhat/scripts/` |
| `indexers/` | Rust L0 indexers (21 crates) | `indexers/crates/` |
| `math/` | Mathematical formulas (Rust) | `math/src/` |
| `proof-ledger/` | Proof ledger | `proof-ledger/` |
| `relayer/` | Cross-chain relayer | `relayer/` |
| `rust/` | Rust core | `rust/src/` |
| `scripts/` | Python utility scripts | `scripts/` |
| `signal-processing/` | Rust signal processing | `signal-processing/src/` |
| `tests/` | Test suites | `tests/adversarial/`, `tests/unit/`, `tests/integration/` |
| `validator/` | Go validator (DW-BFT) | `validator/cmd/`, `validator/internal/` |
| `zk/` | ZK circuits + proofs | `zk/stark/`, `zk/groth16/`, `zk/shared/` |

---

## Key Achievements (with proof links)

| Achievement | Evidence | Status |
|-------------|---------|--------|
| 5-VM deployments | `docs/proofs/` contract addresses | VERIFIED |
| 6-way parity | `zk/shared/parity_vectors.json` | VERIFIED |
| 20/20 adversarial battery | `tests/adversarial/` | VERIFIED |
| 417k+ Arbitrum Oracle txs | `docs/proofs/arbitrum_btc_liquidity_proof.json` | VERIFIED |
| 51 Bitcoin testnet txs | `docs/proofs/btc_lock_tx_result.json` | VERIFIED |
| ZK 500-proof gauntlet | `docs/proofs/zk_500_proofs.json` (412 succeeded + 75 expected reverts) | VERIFIED |
| Production-readiness | `docs/proofs/PRODUCTION_READINESS.json` | VERIFIED (34/35) |
| BTCP pipes (37 files) | `docs/conformance/` | VERIFIED |
| Akashic Index live | `akashic/` (12/12 modules) | VERIFIED |
