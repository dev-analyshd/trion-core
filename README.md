# TRION Protocol

**Behavioral Truth Infrastructure**

TRION is a substrate-independent behavioral coherence oracle and cross-chain settlement protocol. It treats behavior as a permanent, portable, self-verifying substance that identity is made of and systems can be organized around. TRION computes, scores, and publishes the *truth quality* of sequential action patterns across any domain — answering not merely "what happened," but "does the pattern of what happened cohere as genuine?"

Operating at the intersection of information theory, cryptography, game theory, and biology, TRION provides verified behavioral continuity rooted in mathematics, physics, and biology. In an era where generative AI can produce any output indistinguishable from human creation, TRION establishes the verification substrate underneath identity, security, finance, governance, and artificial intelligence.

> TRION is not a price oracle. Not an identity system. Not a security tool. Not an AI safety layer. Not a bridge. It is the **foundational verification layer** that all of these depend on.

---

## Vision — The Witness World

TRION is the engineering surface of a larger philosophical framework called the **Witness World**. In the Witness World, every action leaves a permanent behavioral trace — a behavioral hash (BH) — that is observable, verifiable, and immutable. Identity is not a credential; it is the continuity of behavior across time, witnessed by independent planes.

The **Action Economy** is the economic layer of the Witness World: every action has a coherence cost and a coherence yield. Actions that cohere (consistent across the five planes) accumulate **Biological Capital** BC(t). Actions that do not cohere are silent — they produce no signal, no certificate, no settlement. Silence is the protocol's core security property.

Key concepts:

- **Witness World** — the ontology where behavior is the substrate of identity, truth, and value. TRION is its verification engine.
- **Action Economy** — actions have coherence cost and yield; coherent actions accumulate biological capital; non-coherent actions are silent.
- **Akashic Index** — the append-only, thermodynamically-conserved record of all behavioral hashes (the "ledger of the Witness World").
- **Right to Invisibility** — an entity can prove compliance without revealing behavior; the AWA (Adaptive Work Authorization) freeze enforces fail-closed emission.
- **BZK (Behavioral Zero-Knowledge)** — one projection of the Witness World's privacy law: prove compliance without exposing PII.
- **Five-Plane Coherence** — truth is not agreement; it is coherence across five independent epistemologies.

---

## The TRION Paradigm Shift

TRION replaces the axiom of *truth-as-agreement* with **truth-as-coherence**.

Instead of asking "do most sources say the same thing?" TRION asks "does this entity's behavior *cohere* across five fundamentally independent planes of verification?"

```
C(t) = α·Φ(t) + β·M_adj(t) + γ·Σ(t) + δ·K(t) + ε·A(t)

α = 0.25 · Physical     (Empiricism — measure what happened)
β = 0.30 · Mental       (Rationalism — predict and verify)
γ = 0.25 · Spiritual    (Consensus — independent witnesses)
δ = 0.10 · Conscious    (Hermeneutics — human interpretation)
ε = 0.10 · ANIMA        (Coherentism — cross-domain intelligence)
```

Five fundamentally different approaches to knowing the world. Five independent epistemologies. When all five converge, you do not merely have consensus — you have **coherence**. And coherence is exponentially harder to manufacture than agreement.

The master equation:

```
T(t) = [C(t) ≥ Θ(t)] · C(t) · e^(M_moat)
```

Where:
- **C(t)** = five-plane coherence signal (formula above)
- **Θ(t)** = dynamic threshold: `Θ_min + (Θ_max − Θ_min)·V(t)` — adapts to volatility
- **M_moat** = moat factor: `e^(D·Q·R·X·F·N)` — diversity, quality, resilience, etc.

When C(t) ≥ Θ(t), TRION emits a signal. When it does not, TRION is **silent** — no false output, no partial signal. This silence is the core security property.

---

## Architecture Overview

TRION implements a five-plane behavioral coherence engine, a diversity-weighted BFT consensus layer, and the Bitcoin-Backed Cross-Chain Protocol (BTCP) Zero-Bridge.

```
                    ┌─────────────────────────────────┐
                    │        EXTERNAL DATA SOURCES     │
                    │  Chain RPCs · News · Social ·   │
                    │  Sensors · Validator Network    │
                    └───────────────┬─────────────────┘
                                    │
          ┌─────────────────────────▼─────────────────────────┐
          │   TWO INGESTION PATHS (one live path per deploy):│
          │   bh_streamer (96 workers, Python) → SQLite       │
          │   Rust L0 indexers (21 crates) → FAISS            │
          └─────────────────────────┬─────────────────────────┘
                                    │
          ┌─────────────────────────▼─────────────────────────┐
          │              FIVE BEHAVIORAL PLANES                │
          │  Φ Physical · M Mental · Σ Spiritual               │
          │  K Conscious · A ANIMA                             │
          └─────────────────────────┬─────────────────────────┘
                                    │
          ┌─────────────────────────▼─────────────────────────┐
          │              COHERENCE ENGINE C(t)                │
          │  C(t) = α·Φ_adj + β·M_adj + γ·Σ + δ·K + ε·A       │
          │  Dynamic Threshold: Θ(t) = Θ_min + (Θ_max-Θ_min)V  │
          │  Moat Factor:     M_moat = e^(D·Q·R·X·F·N)         │
          └─────────────────────────┬─────────────────────────┘
                                    │
                    ┌───────────────▼───────────────┐
                    │   C(t) ≥ Θ(t)?                 │
                    │   YES → emit signal            │
                    │   NO  → SILENCE (fail-closed)  │
                    └───────────────┬───────────────┘
                                    │
          ┌─────────────────────────▼─────────────────────────┐
          │   CANONICAL CERTIFICATE (346 bytes)              │
          │   DW-BFT quorum · replay guards · TTL             │
          └─────────────────────────┬─────────────────────────┘
                                    │
          ┌─────────────────────────▼─────────────────────────┐
          │   OUTPUT: On-Chain Publishing + BTCP Router        │
          │   20 communication channels across 10+ VMs         │
          └────────────────────────────────────────────────────┘
```

See [ARCHITECTURE_MAP.md](./ARCHITECTURE_MAP.md) for the complete architecture map (10 build levels, 20 channels, 5 planes, 19 signal types, 7 manipulation fingerprints).

---

## The Akashic Index

The Akashic Index is the **append-only, thermodynamically-conserved record of all behavioral hashes**. It is the "ledger of the Witness World" — every action, once witnessed, is permanently recorded.

### What it stores

Each entry in the Akashic Index is a **Behavioral Hash (BH)** — a 93-byte canonical payload:

```
BH(event) = Hash_DNA(payload)

payload (93 bytes, big-endian):
  offset  width  field
  0       32     entity_id        SHA3-256(normalise(sender))
  32      1      event_type       canonical event-type ID (0..19)
  33      8      magnitude_nano   trunc(magnitude_normalized × 10^9)
  41      8      context          venue/layer flags
  49      8      timestamp_secs   block time (unix seconds)
  57      4      chain_id         TRION canonical chain id
  61      32     block_hash       chain block hash
```

The BH has a **sense** and **antisense** pair (like DNA) — the sense is the hash itself, the antisense is the complementary strand. Both are stored.

### Key properties

1. **Append-only** — no entry is ever deleted or modified. The index grows monotonically.
2. **Thermodynamically conserved** — information conservation law: `dI/dt ≥ 0`. Information can only increase, never decrease.
3. **Cross-VM canonical** — the same transaction produces the same 93-byte BH on every implementation (Python, Rust, TypeScript, Solidity, Cairo, Clarity). Verified by golden vectors in `tests/golded/vectors.json`.
4. **Merkle-accumulated** — daily Merkle roots allow O(log N) inclusion proofs.
5. **FAISS-indexed** — the BH vectors are embedded in a FAISS index for similarity search (archetype detection, anomaly detection).

### Implementation

- **Python core:** `core/akashic/` — `timescale_store.py`, `bibl.py`, `depth.py`, `epigenetics.py`, `fork_resolution.py`, `genesis.py`, `mental_transformer.py`, `archetype.py`
- **FAISS service:** `anima-service/faiss_service.py` — 169 FastAPI routes for BH ingestion, archetype training, similarity search
- **SQLite persistence:** `bh_ledger.db` — the canonical ledger (96-column schema)
- **Rust indexers:** `indexers/crates/trion-common/src/hash_dna.rs` — canonical BH construction for 21 VM families
- **L0 levels:**
  - L0.1 Hash_DNA BH generation
  - L0.2 BEO (Behavioral Entity Oracle) confidence scoring (4-factor)
  - L0.4 Thermodynamic Info Conservation
  - L0.5 Signal Selection Principle
  - L0.6 Merkle Accumulator (daily roots + O(log N) proofs)

### 19 signal types emitted from the Akashic Index

```
VALUATION | SILENCE | MANIPULATION_ALERT | GENESIS | RESURRECTION
FORK_DIVERGENCE | TRAJECTORY | NEGATIVE_SPACE | PHASE_TRANSITION
SYSTEMIC_RISK | LIQUIDITY_HEALTH | GOVERNANCE_SIGNAL
CROSS_CHAIN_COHERENCE | STABLECOIN_HEALTH | MEV_EXPOSURE
INSTITUTIONAL_BEHAVIORAL | REGULATORY_BEHAVIORAL | ECOSYSTEM_HEALTH | BOOTSTRAP
```

---

## The BTCP Zero-Bridge

The **Bitcoin-Backed Cross-Chain Protocol (BTCP) Zero-Bridge** is TRION's cross-chain liquidity routing layer. It unlocks Bitcoin liquidity to DeFi on other chains **without wrapping, minting, or bridging tokens**.

### How it works

The Zero-Bridge uses **SPV (Simple Payment Verification)** to prove that BTC is locked on Bitcoin, then routes the *economic value* — not the token — to the destination chain.

```
┌──────────────┐                     ┌──────────────────┐
│   BITCOIN    │   1. Lock UTXO      │   DESTINATION     │
│   (UTXO)     │ ──────────────────> │   CHAIN (Starknet,│
│              │                     │   Arbitrum, etc.) │
│  BTC locked  │                     │                   │
│  in UTXO     │   2. SPV proof      │  3. verify_anchor │
│  (no wrap)   │ <────────────────── │     on-chain      │
│              │                     │                   │
│              │   4. Coherence cert │  5. Release       │
│              │     (DW-BFT quorum) │     escrow        │
└──────────────┘                     └──────────────────┘
```

### Key properties

1. **No wrapping** — BTC never leaves Bitcoin. No wrapped BTC (wBTC, tBTC, etc.) is minted.
2. **No minting** — the destination chain does not mint a synthetic token. The economic value is routed via escrow.
3. **No bridging** — there is no cross-chain bridge that holds BTC. The SPV proof is verified on-chain by the destination contract.
4. **SPV-verified** — the destination chain's `BTCSPVVerifier` contract verifies the Bitcoin block header and Merkle proof.
5. **Quorum-gated** — release requires a diversity-weighted BFT quorum certificate (the same canonical certificate used for all TRION attestations).
6. **Fail-closed** — if coherence drops below threshold, the AWA freeze blocks all release. No partial release.
7. **Invariant: `assets_bridged = false`** — BTC never leaves Bitcoin. This is verified on every transaction.

### The 5-step settlement flow

1. **register_intent** — user commits an intent on the destination chain (ZK commitment, MEV-private)
2. **lock_escrow** — BTC is locked in a UTXO on Bitcoin testnet/mainnet
3. **register_route** — the route is registered on the destination chain (escrow bound to the BTC lock)
4. **release_escrow** — DW-BFT quorum certificate authorizes release
5. **finalize_route** — the route is finalized, assets become available

### BTCP route types

| Type | Code | Description |
|------|------|-------------|
| NETTING | `0x01` | Net settlement (offsetting flows) |
| SPLIT | `0x02` | Split settlement (multi-party) |
| IAP | `0x03` | Institutional Asset Participation |
| BSC | `0x04` | Bi-directional Settlement Channel |
| BLO | `0x05` | Block-level Liquidity Operation |
| OOA | `0x06` | Out-of-band Asset |

### Deployed contracts

| VM | Network | Contract | Proof |
|----|---------|----------|-------|
| Starknet | Sepolia | ZKVerifier v2 `0x70786a31...` | [proofs/zk/stark/zk_v2_state.json](./proofs/zk/stark/zk_v2_state.json) |
| Arbitrum | Sepolia | TRIONSensingOracle `0x1d129D34...` | [proofs/btcp-zero-bridge/evm/arbitrum/](./proofs/btcp-zero-bridge/evm/arbitrum/) |
| Solana | Devnet | 5 Anchor programs | [proofs/btcp-zero-bridge/solana/](./proofs/btcp-zero-bridge/solana/) |
| Stacks | Testnet | 7 Clarity contracts `ST969AZND...` | [proofs/btcp-zero-bridge/stacks/](./proofs/btcp-zero-bridge/stacks/) |
| Stellar | Testnet | 3 Soroban contracts | [proofs/btcp-zero-bridge/stellar/](./proofs/btcp-zero-bridge/stellar/) |

### Run it yourself

See [docs/RUN_IT_YOURSELF.md](./docs/RUN_IT_YOURSELF.md) for the full end-to-end guide (clone → configure → lock BTC → verify anchor → release escrow).

---

## Achievements

### On-Chain Deployments (5+ VMs)

| VM | Contracts | Network | Proof |
|----|-----------|---------|-------|
| Starknet | 7 Cairo contracts | Sepolia | [proofs/btcp-zero-bridge/starknet/](./proofs/btcp-zero-bridge/starknet/) |
| Arbitrum | 7 Solidity contracts | Sepolia | [proofs/btcp-zero-bridge/evm/arbitrum/](./proofs/btcp-zero-bridge/evm/arbitrum/) |
| Solana | 5 Anchor programs | Devnet | [proofs/btcp-zero-bridge/solana/](./proofs/btcp-zero-bridge/solana/) |
| Stacks | 7 Clarity contracts | Testnet | [proofs/btcp-zero-bridge/stacks/](./proofs/btcp-zero-bridge/stacks/) |
| Stellar | 3 Soroban contracts | Testnet | [proofs/btcp-zero-bridge/stellar/](./proofs/btcp-zero-bridge/stellar/) |
| Bitcoin | SPV locks | Testnet | [proofs/oracle/btc_lock_tx_result.json](./proofs/oracle/btc_lock_tx_result.json) |

### Cross-VM Parity

| Achievement | Value | Proof |
|-------------|-------|-------|
| 4-way anchor parity | `0xae9775361e4acf32613c2d0b4c6760aec2d831bb7320d1cccb6821552636b55a` (byte-identical across Python/Cairo/Solidity/Clarity) | [proofs/btcp-zero-bridge/cross-vm/](./proofs/btcp-zero-bridge/cross-vm/) |
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
| V2 ZKVerifier address | `0x70786a313eb52b0b8f4781c23c8e79adb13d42e54dbeb2f229199280c4536c6` | [proofs/zk/stark/zk_v2_state.json](./proofs/zk/stark/zk_v2_state.json) |
| V2 class hash | `0x78270e19591e334709026d5480c8963ba3235d535eb8a8f351ef911d7c67cb5` | [proofs/zk/stark/zk_v2_declare.json](./proofs/zk/stark/zk_v2_declare.json) |

### Adversarial Batteries

| VM | Score | Proof |
|----|-------|-------|
| Starknet | 20/20 (zero-value, duplicate, nonexistent fn) | [proofs/adversarial/](./proofs/adversarial/) |
| Arbitrum | 20/20 | [proofs/adversarial/](./proofs/adversarial/) |
| Stacks | 20/20 (12 ABORT + 6 HONEST_LIMITATION + 2 SUCCESS-labeled) | [proofs/btcp-zero-bridge/stacks/](./proofs/btcp-zero-bridge/stacks/) |

### Production Readiness

| Metric | Value | Proof |
|--------|-------|-------|
| D-items (D1-D20) | 20/20 YES | [proofs/mission-audits/production-readiness/PRODUCTION_READINESS.json](./proofs/mission-audits/production-readiness/PRODUCTION_READINESS.json) |
| Connectivity sweep (E1-E12) | 8 PASS, 4 GATED, 0 NOT CONNECTED | Same |
| Language mandate | 10 conformant, 1 pending (WASM) | Same |
| Commit audit | 100% dev-analyshd | Same |

---

## Domain Explanations

### Identity

TRION's identity layer is behavioral, not credential-based. Identity is the continuity of behavior across time, verified through:

- **BEO (Behavioral Entity Oracle):** Resolves an entity's behavioral history to a single coherence score. 4-factor confidence scoring.
- **Genomic Keys:** Cryptographic keys derived from behavioral patterns (Hash_DNA), not random entropy.
- **BIRP (Bitcoin-Integrated Routing Protocol):** Binds Bitcoin UTXO anchors to cross-chain identity. 5-phase enrollment + recovery.

Docs: [docs/identity/](./docs/identity/)

### Privacy

TRION's privacy layer protects behavioral data through:

- **ZK Surfaces (BZK):** Zero-knowledge proofs verify compliance without exposing PII. 5 circuits: S1 (intent commitment), S2 (IAP share), S3 (travel rule), S4 (sensing oracle), S5 (BIRP).
- **Right to Invisibility:** AWA (Adaptive Work Authorization) freeze enforces fail-closed emission. When AWA is frozen, no signal is emitted — not a false signal, but silence.
- **Chameleon Hashes:** Allow selective disclosure of behavioral records.

> **Critical clarification:** TRION does not help users evade laws. ZK proofs prove **compliance** — they do not hide non-compliance. An illegal transaction with a ZK behavioral privacy proof is still illegal and the behavioral record still exists in the Akashic Index. What ZK changes is *who can observe* the record — not whether it exists.

Docs: [docs/privacy/](./docs/privacy/), [docs/zk/BZK.md](./docs/zk/BZK.md)

### AI Safety

TRION's AI safety layer prevents manipulation of the coherence signal through:

- **ANIMA Calibration:** Cross-domain AI calibration ensures no single AI dominates the coherence score. ANIMA score = PCR × HA × CA.
- **Manipulation Detection:** 7 manipulation fingerprints (latency arb, MEV sandwich, wash trading, oracle staleness, coordination collapse, cross-domain divergence, long-range attack) are actively detected.
- **Observer Effect:** The act of observation changes behavior; TRION accounts for this via OE_factor.
- **Love Protocol:** F (Love) = 0 if any plane is adversarial. Coherence requires all five planes to align.

Docs: [docs/ai-safety/](./docs/ai-safety/)

### Governance

TRION's governance layer uses diversity-weighted BFT:

- **DW-BFT:** Validator weight = stake × diversity (d_j). Prevents coordination collapse.
- **Coordination Collapse Detection:** The Spiritual plane (Σ) monitors HHI (Herfindahl-Hirschman Index) for validator concentration. HHI > 4000 = critical.
- **Slashing:** Validators that emit non-coherent signals are slashed. 72-hour dispute resolution window.
- **Canonical Certificate:** 346-byte signed payload, same across all VMs. See [docs/protocol/CANONICAL_CERTIFICATE.md](./docs/protocol/CANONICAL_CERTIFICATE.md).

Docs: [docs/governance/](./docs/governance/), [docs/protocol/CANONICAL_CERTIFICATE.md](./docs/protocol/CANONICAL_CERTIFICATE.md)

---

## Repository Structure

```
trion-core/
├── adapters/              # Cross-VM adapter layer (Rust) — evm, svm, move, cosmos, cosmwasm, ooa
├── akashic/               # Akashic Index runtime state (SQLite + FAISS)
├── anima-service/          # ANIMA AI calibration service (FastAPI, port 8000)
├── api/                    # TRION Oracle API (Flask, port 5000) — 283 routes
├── ARCHITECTURE_MAP.md     # Complete architecture map (10 levels, 20 channels, 5 planes)
├── backtest/               # Replay engine + held-out results
├── btc-tools/              # Cross-chain tooling (JavaScript)
│   ├── bitcoin/            # BTC scripts (merkle proofs, header fetch, lock)
│   ├── starknet/            # Starknet ZK scripts (helpers, deploy, proofs)
│   ├── evm/arbitrum/        # Arbitrum deployment + verification
│   ├── stacks/              # Stacks deployment + anchor verification
│   ├── stellar/             # Stellar deployment
│   ├── cross-chain/         # Cross-chain bridge scripts (BTC↔Starknet, dual-side)
│   └── lib/                 # Shared libraries
├── chains/                 # Per-chain client code (TypeScript + Cargo)
│   ├── botchain/ near/ pvm/ starknet/ sui/ svm/ ton/
│   └── shared/              # canonical_bh.ts, generated_chain_ids.ts
├── config/                 # Deployment configs (deployment.env)
├── contracts/              # Smart contracts (all VMs)
│   ├── solidity/            # 39 EVM contracts (Hardhat)
│   ├── cairo/               # Starknet contracts (Scarb)
│   ├── starknet/            # Starknet contracts (Scarb)
│   ├── svm/                 # Solana programs (Anchor)
│   ├── move/                # Move contracts (Sui/Aptos)
│   ├── clarity/             # Stacks contracts (Clarinet)
│   ├── soroban/             # Stellar contracts (Soroban)
│   ├── near/                # NEAR contracts (Rust)
│   ├── ton/                 # TON contracts (Tact/FunC)
│   ├── pvm/                 # Polkadot contracts (ink!)
│   ├── cosmwasm/            # CosmWasm contracts (Rust)
│   ├── vyper/               # Vyper contracts
│   └── zk/                  # ZK-specific contracts
├── core/                   # Python core (planes, consensus, BTCP)
│   ├── akashic/             # Akashic Index (timescale, bibl, depth, genesis)
│   ├── spiritual/           # Spiritual plane (Σ) — DW-BFT consensus
│   ├── manipulation/        # Mental plane (M) — manipulation detection
│   ├── physical/             # Physical plane (Φ) — Shannon entropy
│   ├── mental/              # Mental plane (M) — prediction
│   ├── consensus/           # Canonical certificate (346 bytes)
│   ├── btcp/                # BTCP Zero-Bridge router + escrow
│   ├── governance/           # Slashing, dispute resolution
│   ├── agent/               # Conscious plane (K) — human annotation
│   └── ...                  # 20+ sub-modules
├── docs/                   # Documentation
│   ├── architecture/        # Build guide, channels, planes
│   ├── identity/ privacy/ ai-safety/ governance/ security/ consensus/
│   ├── protocol/            # Canonical certificate, BH, state machine
│   ├── zk/                  # BZK, circuit specs, Starknet integration
│   └── ARCHITECTURE.md      # Detailed architecture overview
├── evm-tools/              # EVM-specific tooling (deploy, compile)
├── formal/                 # Haskell formal proofs (stack)
├── hardhat/                # EVM Hardhat project (contracts + tests)
├── indexers/               # Rust L0 indexers (21 crates workspace)
│   └── crates/              # trion-evm, trion-svm, trion-starknet, ... (21 VMs)
├── math/                   # Mathematical formulas (Rust + Julia)
├── network/                # Go network health monitor
├── proofs/                 # Categorical proof evidence
│   ├── btcp-zero-bridge/    # Per-VM liquidity proofs (evm, starknet, solana, ...)
│   ├── zk/                  # ZK proof gauntlets (stark, groth16, parity)
│   ├── adversarial/         # Adversarial batteries
│   ├── oracle/              # SPV verifier, BTC lock tx, anchor parity
│   └── mission-audits/      # Production readiness, closeout, phase reports
├── relayer/                # Multi-chain relayer (Node.js)
├── rust/                   # Rust core library
├── scripts/                # Python + shell utility scripts
│   ├── start_trion.sh       # Full-stack startup script
│   ├── deploy_preflight.py  # Deployment preflight checks
│   └── trion_master_indexer.mjs  # Chain indexing orchestrator
├── sdk/                    # TypeScript SDK (@trion-protocol/sdk)
├── signal-processing/      # C++ signal processing (FFT, sensors)
├── tests/                  # Test suites (unit, integration, adversarial, golden)
├── validator/               # Go DW-BFT validator (P2P mesh)
├── zg/                     # 0G data availability layer
└── zk/                     # ZK circuits + proofs
    ├── stark/               # Cairo circuits + zk_verifier contract (Scarb)
    ├── groth16/             # Circom circuits (5 circuits, snarkjs)
    ├── shared/              # Cross-prover parity vectors
    └── facade/              # Python ZK facade (ZKProofSystem)
```

---

## Quick Start

### Prerequisites

The TRION stack spans multiple languages. Install only what you need for the components you want to run.

#### Python (Oracle API + FAISS + core + anima-service)

- **Python 3.11+** (3.12 recommended)
- Install: `pip install -r api/requirements.txt -r anima-service/requirements.txt`
- Or use pyproject.toml: `pip install -e .`

#### Node.js (relayer + btc-tools + evm-tools + SDK)

- **Node.js 20+** (v24 tested)
- **Bun 1.1+** (for running scripts)
- Install per-component: `cd relayer && npm install --legacy-peer-deps`
- btc-tools deps: `cd btc-tools && npm install` (or use parent `node_modules/`)

#### Rust (indexers + adapters + zk/stark + math)

- **Rust 1.80+** (stable)
- Install: `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`
- Build indexers: `cd indexers && cargo build --release`
- Build adapters: `cd adapters && cargo build --release`

#### Go (validator + network monitor)

- **Go 1.21+**
- Install: https://go.dev/doc/install
- Build validator: `cd validator && go build ./cmd/trion-validator`

#### C++ (signal-processing)

- **CMake 3.16+**, **g++** (C++17)
- Build: `cd signal-processing && mkdir -p build && cd build && cmake .. && make`

#### Cairo (zk/stark contracts)

- **Scarb 2.9+** (Cairo 2.9+)
- Install: https://docs.swmansion.com/scarb/download.html
- Build: `cd zk/stark/contract && scarb build`

#### Haskell (formal proofs)

- **Stack** (GHC 9.x)
- Install: https://docs.haskellstack.org/en/stable/install_and_upgrade/
- Build: `cd formal && stack build`

#### Solidity (EVM contracts)

- **Hardhat** (via npm)
- Build: `cd hardhat && npm install && npx hardhat compile`

### Run the Oracle API (Python — the core service)

The Oracle API is the main TRION service — 283 Flask routes serving behavioral truth data, on-chain signals, and the dashboard.

```bash
cd trion-core

# 1. Install Python dependencies
pip install -r api/requirements.txt -r anima-service/requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env: set PRIVATE_KEY (testnet), RPC URLs, API keys

# 3. Run the Oracle API (port 5000)
python3 serve.py
```

The Oracle API will be available at `http://localhost:5000`:
- `GET /api/v1/health` — Oracle health (verified: returns contract addresses, coherence, threshold)
- `GET /app/` — Institutional dashboard
- `GET /api/v1/*` — 283 API routes (signals, entities, BTCP, continuum)

### Run the FAISS Akashic Intelligence Engine (Python — ANIMA service)

```bash
cd trion-core/anima-service

# 1. Install dependencies (if not already)
pip install -r requirements.txt

# 2. Run (port 8000 by default, 127.0.0.1)
python3 faiss_service.py
```

The FAISS service will be available at `http://localhost:8000`:
- `GET /health` — FAISS health (verified: returns indexed_vectors, archetypes, merkle_dates)
- 169 FastAPI routes for BH ingestion, archetype training, similarity search

### Run the Multi-Chain Relayer (Node.js)

```bash
cd trion-core/relayer

# 1. Install dependencies
npm install --legacy-peer-deps

# 2. Dry-run mode (no on-chain submission — just polls Oracle API)
node relayer.js --dry-run

# 3. Live mode (requires RELAYER_PRIVATE_KEY or KMS_PROVIDER)
RELAYER_PRIVATE_KEY=0xYOUR_KEY node relayer.js
```

### Run the Rust Indexers (L0 ingestion)

```bash
cd trion-core/indexers

# 1. Build all 21 indexer crates
cargo build --release

# 2. List indexed chains
node ../scripts/trion_master_indexer.mjs --list

# 3. Start all indexers
node ../scripts/trion_master_indexer.mjs
```

### Run the Go Validator (DW-BFT P2P mesh)

```bash
cd trion-core/validator

# 1. Build
go build ./cmd/trion-validator

# 2. Run (self-test mode prints PASS and exits — see DEPLOYMENT.md)
go run ./cmd/trion-validator
```

### Run the Network Health Monitor (Go)

```bash
cd trion-core/network
go run .
# Serves GET /health and /health/chains on port 6001
```

### Build the C++ Signal Processing

```bash
cd trion-core/signal-processing
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
cmake --build .
# Tests: ctest
```

### Build the Cairo ZK Contracts

```bash
cd trion-core/zk/stark/contract
scarb build
# Output: target/dev/zk_verifier_contract_ZKVerifier.contract_class.json
```

### Build the Haskell Formal Proofs

```bash
cd trion-core/formal
stack build
stack test
```

### Compile the EVM Contracts (Hardhat)

```bash
cd trion-core/hardhat
npm install
npx hardhat compile
# Tests: npx hardhat test
```

### Start Everything at Once

```bash
cd trion-core

# Start all services (FAISS + Oracle API + validator self-test)
# Optionally + frontend if you have one configured
./scripts/start_trion.sh

# Or in background:
./scripts/start_trion.sh --background

# Skip validators (if no Go installed):
./scripts/start_trion.sh --no-validators
```

### Docker (Dev Image)

```bash
cd trion-core
cp .env.example .env
docker compose up --build
# Endpoints:
#   http://localhost:5000/app/           Dashboard
#   http://localhost:5000/api/v1/health  Oracle API health
#   http://localhost:8000/health         FAISS ANIMA health
```

### Verify On-Chain (BTCP Zero-Bridge)

See [docs/RUN_IT_YOURSELF.md](./docs/RUN_IT_YOURSELF.md) for the full end-to-end guide:
1. Clone and install
2. Configure environment (Starknet Sepolia account, Bitcoin testnet wallet, Alchemy API key)
3. Lock BTC in a UTXO on Bitcoin testnet
4. Verify the SPV anchor on the destination chain
5. Submit travel rule proof / BIRP enrollment
6. Run the 20-round adversarial battery

---

## Proofs

All proof files are in the [proofs/](./proofs/) directory, organized by category:

| Category | Path | Contents |
|----------|------|----------|
| BTCP Zero-Bridge | [proofs/btcp-zero-bridge/](./proofs/btcp-zero-bridge/) | Per-VM liquidity unlock proofs |
| ZK | [proofs/zk/](./proofs/zk/) | ZK circuit proofs, Starknet 500-proof gauntlet |
| Adversarial | [proofs/adversarial/](./proofs/adversarial/) | 20/20 batteries per VM |
| Oracle | [proofs/oracle/](./proofs/oracle/) | SPV verifier, BTC lock tx, anchor parity |
| Mission Audits | [proofs/mission-audits/](./proofs/mission-audits/) | Production readiness, closeout, phase reports |

### Key Transaction Hashes

| Event | Tx Hash | Network |
|-------|---------|---------|
| ZK v2 class declare | `0x4f83ab20ec420fac1fc87f3e463a92027b9cdcb6c46e7a445277285d2cbab5a` | Starknet Sepolia |
| ZK v2 contract deploy | `0x7ef485024c3d43bdae919c932ce5acdddefb47c7bae84acc71b6b2266a64c0b` | Starknet Sepolia |
| ZK v2 AWA unfreeze | `0x3e74ef5c3742679121a2bd2ae43ca56294f605c4bde0d1255034cc2f0ce2b9c` | Starknet Sepolia |
| Stacks quorum release | `0x7563960ead1931204233f9f88fcb719209b2c7fbf63746c0a0e0246906e8e176` | Stacks Testnet |
| Stacks verify-anchor | `0x01c3bdb45dd562b5affcad7621b9cfefa9977c819c62311dd8b2c9bb3a110d03` | Stacks Testnet |

---

## Architecture Deep-Dive

See [ARCHITECTURE_MAP.md](./ARCHITECTURE_MAP.md) for the complete architecture map including:

- 10 build levels (L0-L9) with completion status
- 20 communication channels with implementations
- 5 behavioral planes with formulas
- 19 signal types
- 7 manipulation fingerprints

Also see [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) for the detailed architecture overview and [docs/protocol/CANONICAL_CERTIFICATE.md](./docs/protocol/CANONICAL_CERTIFICATE.md) for the 346-byte certificate specification.

---

## Evidence Culture

TRION follows a strict evidence culture:

- **Every claim is linked to proof.** If a proof file doesn't exist, the claim is removed.
- **Superseded claims are retained with provenance.** Retraction notes explain what changed.
- **Evidence files are never deleted.** They are archived with PROVENANCE.md explaining status.
- **Commit history is preserved.** File moves use `git mv`, not `rm + add`.
- **Identity is consistent.** All commits are by `dev-analyshd`.

See [DEAD_FILES_JUSTIFICATION.md](./DEAD_FILES_JUSTIFICATION.md) for the dead-file removal audit.

---

## Contact

- **GitHub:** [dev-analyshd/trion-core](https://github.com/dev-analyshd/trion-core)
- **Identity:** dev-analyshd
- **License:** CC0 — This knowledge belongs to everyone
- **Whitepapers:** 3 canon documents (TRION_PROTOCOL_White_paper.pdf Feb 2026, TRION_Protocol_Whitepaper.md.pdf Mar 2026, BTCP_MASTER_IMPLEMENTATION_SPEC.md.pdf Apr 2026)

---

*Author: Hudu Yusuf (Analys) · CC0 — This knowledge belongs to everyone*
