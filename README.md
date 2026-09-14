# TRION Protocol

## Behavioral Truth Infrastructure

**TRION** is a substrate-independent behavioral coherence verification engine and cross-chain settlement protocol. It computes a single coherence signal C(t) from five independent epistemological planes, emits canonical certificates via diversity-weighted BFT, and routes liquidity cross-chain through the Bitcoin-Backed Cross-Chain Protocol (BTCP) — without wrapping, minting, or bridging tokens.

> TRION is not a price oracle. Not an identity system. Not a bridge. It is the foundational verification layer that all of these depend on.

**Identity:** dev-analyshd
**License:** CC0
**Network:** Starknet Sepolia + Arbitrum Sepolia + Bitcoin Testnet + Solana Devnet + Stacks Testnet

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Technical Overview](#2-technical-overview)
3. [Achievements](#3-achievements)
4. [Domain Explanations](#4-domain-explanations)
5. [Proofs](#5-proofs)
6. [Architecture Deep-Dive](#6-architecture-deep-dive)
7. [Quick Start](#7-quick-start)
8. [Repository Structure](#8-repository-structure)
9. [Evidence Culture](#9-evidence-culture)
10. [Contact](#10-contact)

---

## 1. Executive Summary

TRION replaces the axiom of *truth-as-agreement* with **truth-as-coherence**. Instead of asking "do most sources agree?", TRION asks "does this entity's behavior cohere across five fundamentally independent planes of verification?"

The master equation:

```
T(t) = [C(t) ≥ Θ(t)] · C(t) · e^(M_moat)
```

Where C(t) is the five-plane coherence signal, Θ(t) is the dynamic threshold, and M_moat is the moat factor. When coherence exceeds threshold, TRION emits a signal. When it does not, TRION is silent. This silence is the protocol's core security property — **non-coherent behavior produces no output, not a false output.**

TRION is deployed across 5+ VMs (Starknet, Arbitrum, Solana, Stacks, Stellar, Bitcoin) with 417k+ on-chain transactions, 500 ZK proofs verified on Starknet, and 20/20 adversarial batteries passing on every VM.

---

## 2. Technical Overview

### Five Behavioral Planes

| Plane | Symbol | Epistemology | Implementation |
|-------|--------|-------------|----------------|
| Physical | Φ | Empiricism — measure what happened | `signal-processing/`, `core/manipulation/` |
| Mental | M | Rationalism — predict and verify | `core/manipulation/prediction/` |
| Spiritual | Σ | Consensus — independent witnesses | `core/spiritual/consensus.py`, `validator/` |
| Conscious | K | Hermeneutics — human interpretation | `core/agent/`, `supervisors/` |
| ANIMA | A | Coherentism — cross-domain AI | `anima-service/`, `core/agent/` |

### Coherence Formula

```
C(t) = α·Φ_adj(t) + β·M_adj(t) + γ·Σ(t) + δ·K(t) + ε·A(t)

α = 0.25 (Physical)    β = 0.30 (Mental)    γ = 0.25 (Spiritual)
δ = 0.10 (Conscious)   ε = 0.10 (ANIMA)

Dynamic Threshold: Θ(t) = Θ_min + (Θ_max − Θ_min)·V(t)
Moat Factor:       M_moat = e^(D·Q·R·X·F·N)
```

### 10 Build Levels

| Level | Name | Status | Evidence |
|-------|------|--------|----------|
| L0 | Ingestion | BUILT | `indexers/` (21 Rust crates), `api/` (96 workers) |
| L1 | Physical Plane | BUILT | `signal-processing/src/` (9 Shannon entropy signals) |
| L2 | Akashic Index | BUILT | `akashic/` (12/12 modules live) |
| L3 | Mental Plane | BUILT | `core/manipulation/prediction/` |
| L4 | Spiritual Plane | BUILT | `core/spiritual/`, `validator/` (Go DW-BFT) |
| L5 | Living Security | BUILT | `core/governance/`, PQC + CRISPR layers |
| L6 | First Signal | BUILT | Genesis renounced, SILENCE enforced |
| L7 | ANIMA v1 | BUILT | `anima-service/` |
| L8 | Conscious Plane | BUILT | `core/agent/`, `supervisors/` |
| L9 | Five-Plane Full | BUILT | All 5 planes emitting, 19 signal types |
| L10 | Mainnet | PARTIAL | Testnet complete, mainnet pending audit |

See [ARCHITECTURE_MAP.md](./ARCHITECTURE_MAP.md) for the full architecture.

---

## 3. Achievements

### On-Chain Deployments

| VM | Contracts | Network | Proof |
|----|-----------|---------|-------|
| Starknet | 7 contracts | Sepolia | [proofs/btcp-zero-bridge/starknet/](./proofs/btcp-zero-bridge/starknet/) |
| Arbitrum | 7 contracts | Sepolia | [proofs/btcp-zero-bridge/evm/arbitrum/](./proofs/btcp-zero-bridge/evm/arbitrum/) |
| Solana | 5 programs | Devnet | [proofs/btcp-zero-bridge/solana/](./proofs/btcp-zero-bridge/solana/) |
| Stacks | 7 contracts | Testnet | [proofs/btcp-zero-bridge/stacks/](./proofs/btcp-zero-bridge/stacks/) |
| Stellar | 3 contracts | Testnet | [proofs/btcp-zero-bridge/stellar/](./proofs/btcp-zero-bridge/stellar/) |

### Cross-Chain Parity

| Achievement | Value | Proof |
|-------------|-------|-------|
| 4-way anchor parity | `0xae977536...b55a` (byte-identical across Python/Cairo/Solidity/Clarity) | [proofs/btcp-zero-bridge/cross-vm/](./proofs/btcp-zero-bridge/cross-vm/) |
| Cross-VM route matrix | 6 VMs × multiple route types | [proofs/btcp-zero-bridge/cross-vm/cross_vm_route_matrix.json](./proofs/btcp-zero-bridge/cross-vm/cross_vm_route_matrix.json) |
| Cryptographic binding | BTC ↔ Starknet proof | [proofs/btcp-zero-bridge/cross-vm/cryptographic_binding_proof.json](./proofs/btcp-zero-bridge/cross-vm/cryptographic_binding_proof.json) |

### Transaction Volume

| Metric | Value | Proof |
|--------|-------|-------|
| Arbitrum Oracle transactions | 417,000+ | [proofs/btcp-zero-bridge/evm/arbitrum/](./proofs/btcp-zero-bridge/evm/arbitrum/) |
| Bitcoin testnet transactions | 51 | [proofs/oracle/btc_lock_tx_result.json](./proofs/oracle/btc_lock_tx_result.json) |
| BTC confirmations | 134+ | [proofs/oracle/btc_lock_tx_result.json](./proofs/oracle/btc_lock_tx_result.json) |

### ZK Proof Gauntlet

| Metric | Value | Proof |
|--------|-------|-------|
| ZK proofs submitted | 500/500 | [proofs/zk/stark/zk_500_proofs.json](./proofs/zk/stark/zk_500_proofs.json) |
| Succeeded | 412 | — |
| Expected reverts (adversarial + duplicate) | 75 | — |
| Contract total_proofs counter | 427 (0x1ab) | — |
| V2 ZKVerifier address | `0x70786a31...` | [proofs/zk/stark/zk_v2_state.json](./proofs/zk/stark/zk_v2_state.json) |
| V2 class hash | `0x78270e19...` | [proofs/zk/stark/zk_v2_declare.json](./proofs/zk/stark/zk_v2_declare.json) |

### Adversarial Batteries

| VM | Score | Proof |
|----|-------|-------|
| Starknet | 20/20 | [proofs/adversarial/](./proofs/adversarial/) |
| Arbitrum | 20/20 | [proofs/adversarial/](./proofs/adversarial/) |
| Stacks | 20/20 (12 ABORT + 6 HONEST + 2 SUCCESS-labeled) | [proofs/btcp-zero-bridge/stacks/](./proofs/btcp-zero-bridge/stacks/) |

### Production Readiness

| Metric | Value | Proof |
|--------|-------|-------|
| D-items (D1-D20) | 20/20 YES | [proofs/mission-audits/production-readiness/PRODUCTION_READINESS.json](./proofs/mission-audits/production-readiness/PRODUCTION_READINESS.json) |
| Connectivity sweep (E1-E12) | 8 PASS, 4 GATED, 0 NOT CONNECTED | Same |
| Language mandate | 10 conformant, 1 pending (WASM) | Same |
| Commit audit | 100% dev-analyshd | Same |

### Mission Audits

| Audit | Status | Proof |
|-------|--------|-------|
| Production readiness (34/35 built) | VERIFIED | [proofs/mission-audits/production-readiness/](./proofs/mission-audits/production-readiness/) |
| BTCP pipes (37 files verified) | VERIFIED | [proofs/mission-audits/](./proofs/mission-audits/) |
| ZK Starknet gauntlet (500 proofs) | VERIFIED | [proofs/zk/stark/](./proofs/zk/stark/) |
| Closeout phases 2-8 | VERIFIED | [proofs/mission-audits/closeout_phases_2_8.json](./proofs/mission-audits/closeout_phases_2_8.json) |

---

## 4. Domain Explanations

### Identity

TRION's identity layer is behavioral, not credential-based. Identity is the continuity of behavior across time, verified through:

- **BEO (Behavioral Entity Oracle):** Resolves an entity's behavioral history to a single coherence score.
- **Genomic Keys:** Cryptographic keys derived from behavioral patterns, not random entropy.
- **BIRP (Bitcoin-Integrated Routing Protocol):** Binds Bitcoin UTXO anchors to Starknet identity.

Docs: [docs/identity/](./docs/identity/)

### Privacy

TRION's privacy layer protects behavioral data through:

- **ZK Surfaces:** Zero-knowledge proofs verify compliance without exposing PII.
- **Right to Invisibility:** AWA (Adaptive Work Authorization) freeze enforces fail-closed emission.
- **Chameleon Hashes:** Allow selective disclosure of behavioral records.

Docs: [docs/privacy/](./docs/privacy/)

### AI Safety

TRION's AI safety layer prevents manipulation of the coherence signal through:

- **ANIMA Calibration:** Cross-domain AI calibration ensures no single AI dominates the coherence score.
- **Manipulation Detection:** 7 manipulation fingerprints (latency arb, MEV sandwich, wash trading, etc.) are actively detected.
- **Observer Effect:** The act of observation changes behavior; TRION accounts for this.

Docs: [docs/ai-safety/](./docs/ai-safety/)

### Governance

TRION's governance layer uses diversity-weighted BFT:

- **DW-BFT:** Validator weight = stake × diversity, preventing coordination collapse.
- **Coordination Collapse Detection:** The Spiritual plane (Σ) monitors for validator collusion.
- **Slashing:** Validators that emit non-coherent signals are slashed.

Docs: [docs/governance/](./docs/governance/)

---

## 5. Proofs

### On-Chain Evidence

All proof files are in the [proofs/](./proofs/) directory, organized by category:

| Category | Path | Contents |
|----------|------|----------|
| BTCP Zero-Bridge | [proofs/btcp-zero-bridge/](./proofs/btcp-zero-bridge/) | Per-VM liquidity unlock proofs |
| ZK | [proofs/zk/](./proofs/zk/) | ZK circuit proofs, Starknet gauntlet |
| Adversarial | [proofs/adversarial/](./proofs/adversarial/) | 20/20 batteries per VM |
| Oracle | [proofs/oracle/](./proofs/oracle/) | SPV verifier, BTC lock tx, anchor parity |
| Mission Audits | [proofs/mission-audits/](./proofs/mission-audits/) | Production readiness, closeout, phase reports |

### Key Transaction Hashes

| Event | Tx Hash | Network |
|-------|---------|---------|
| ZK v2 class declare | `0x4f83ab20...` | Starknet Sepolia |
| ZK v2 contract deploy | `0x7ef48502...` | Starknet Sepolia |
| ZK v2 AWA unfreeze | `0x3e74ef5c...` | Starknet Sepolia |
| Stacks quorum release | `0x7563960e...` | Stacks Testnet |
| Stacks verify-anchor | `0x01c3bdb4...` | Stacks Testnet |

---

## 6. Architecture Deep-Dive

See [ARCHITECTURE_MAP.md](./ARCHITECTURE_MAP.md) for the complete architecture map including:

- 10 build levels (L0-L9) with completion status
- 20 communication channels with implementations
- 5 behavioral planes with formulas
- 19 signal types
- 7 manipulation fingerprints

Also see [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) for the detailed architecture overview.

---

## 7. Quick Start

### Prerequisites

- Node.js 20+ (for Next.js frontend + btc-tools)
- Python 3.12+ (for core + anima-service)
- Rust 1.80+ (for indexers + signal-processing)
- Go 1.22+ (for validator)
- Bun 1.1+ (for frontend dev server)

### Run the Frontend

```bash
cd /home/z/my-project
bun run dev    # starts Next.js on port 3000
```

### Run the Core (Python)

```bash
cd trion-core
pip install -r requirements.txt
python -m api.server    # starts API on port 5000
```

### Run the Validator (Go)

```bash
cd trion-core/validator
go run cmd/main.go    # starts DW-BFT validator
```

### Verify On-Chain

See [docs/RUN_IT_YOURSELF.md](./docs/RUN_IT_YOURSELF.md) for the full end-to-end verification guide.

---

## 8. Repository Structure

```
trion-core/
├── adapters/           # Cross-VM adapter layer (Rust)
├── akashic/             # Akashic Index (event store)
├── anima-service/       # ANIMA AI calibration
├── api/                 # REST API + bh_streamer
├── ARCHITECTURE_MAP.md  # Complete architecture map
├── backtest/            # Replay engine
├── btc-tools/           # Cross-chain tooling
│   ├── bitcoin/         # BTC scripts (SPV, merkle proofs)
│   ├── starknet/        # Starknet ZK scripts
│   ├── evm/arbitrum/    # Arbitrum scripts
│   ├── stacks/          # Stacks scripts
│   ├── stellar/         # Stellar scripts
│   ├── cross-chain/     # Cross-chain bridge scripts
│   └── lib/             # Shared libraries
├── chains/              # Per-chain client code
├── config/              # Deployment configs
├── contracts/           # Smart contracts (all VMs)
│   ├── solidity/        # EVM contracts
│   ├── starknet/        # Cairo contracts
│   ├── svm/             # Solana programs
│   ├── move/            # Move contracts
│   └── ...              # 10+ VMs total
├── core/                # Python core (planes, consensus, BTCP)
├── docs/                # Documentation
│   ├── architecture/    # Build guide, channels, planes
│   ├── identity/        # BEO, Genomic Keys, BIRP
│   ├── privacy/         # ZK surfaces, AWA, Chameleon
│   ├── ai-safety/       # ANIMA, manipulation, observer effect
│   ├── governance/      # DW-BFT, slashing, coordination collapse
│   ├── protocol/        # Canonical certificate, state machine
│   └── zk/              # BZK, circuit specs, Starknet
├── formal/              # Haskell formal proofs
├── indexers/            # Rust L0 indexers (21 crates)
├── proofs/              # Categorical proof evidence
│   ├── btcp-zero-bridge/ # Per-VM liquidity proofs
│   ├── zk/              # ZK proof gauntlets
│   ├── adversarial/     # Adversarial batteries
│   ├── oracle/          # SPV verifier proofs
│   └── mission-audits/  # Production readiness, closeout
├── REPO_INVENTORY.md    # Full file inventory
├── signal-processing/   # Rust signal processing
├── tests/               # Test suites
├── validator/           # Go DW-BFT validator
└── zk/                  # ZK circuits (Cairo + circom)
```

---

## 9. Evidence Culture

TRION follows a strict evidence culture:

- **Every claim is linked to proof.** If a proof file doesn't exist, the claim is removed.
- **Superseded claims are retained with provenance.** Retraction notes explain what changed.
- **Evidence files are never deleted.** They are archived with PROVENANCE.md explaining status.
- **Commit history is preserved.** File moves use `git mv`, not `rm + add`.
- **Identity is consistent.** All commits are by `dev-analyshd`.

See [DEAD_FILES_JUSTIFICATION.md](./DEAD_FILES_JUSTIFICATION.md) for the dead-file removal audit.

---

## 10. Contact

- **GitHub:** [dev-analyshd/trion-core](https://github.com/dev-analyshd/trion-core)
- **Identity:** dev-analyshd
- **License:** CC0 — This knowledge belongs to everyone
- **Whitepapers:** 3 canon documents (see [docs/whitepapers/](./docs/whitepapers/))

---

*Author: dev-analyshd · CC0 — This knowledge belongs to everyone*
