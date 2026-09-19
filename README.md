# TRION Protocol

**The Behavioral Truth Oracle**

TRION is a substrate-independent behavioral coherence oracle. It ingests actions from any chain or data source, distills each into a canonical behavioral hash, and computes a single coherence signal from five independent epistemological planes. When coherence holds, TRION emits a signed certificate that any application — identity, security, finance, governance, AI safety — can verify on any VM.

TRION does not score behavior. It witnesses it. The output is not a rating; it is a verifiable attestation that a sequence of actions coheres across empiricism, rationalism, consensus, hermeneutics, and cross-domain intelligence. Where the old axiom asks "do sources agree?", TRION asks "does the behavior cohere?" — and when it does not, TRION is silent.

```
T(t) = [C(t) ≥ Θ(t)] · S(t) · e^(M_moat · t)
```

Truth emits only when all five planes of reality are coherent. When any plane fails: silence. The silence is information.

**Author and Originator:** Hudu Yusuf (Analys)
**License:** CC0 — This knowledge belongs to everyone

---

## Table of Contents

1. [What TRION Does](#what-trion-does)
2. [Architecture](#architecture)
3. [The Akashic Index](#the-akashic-index)
4. [BTCP Zero-Bridge](#btcp-zero-bridge)
5. [Repository Structure](#repository-structure)
6. [Quick Start — Run TRION](#quick-start--run-trion)
   - [Linux / WSL](#linux--wsl)
   - [macOS](#macos)
   - [Windows (WSL)](#windows-wsl)
7. [Run a Validator](#run-a-validator)
8. [Formal Verification](#formal-verification)
9. [Achievements](#achievements)
10. [Proofs](#proofs)
11. [Vision](#vision)
12. [Contact](#contact)

---

## What TRION Does

1. **Witnesses behavior** — every action on every connected chain is reduced to a 93-byte canonical Behavioral Hash (BH) with a sense/antisense pair, stored in an append-only Akashic Index.
2. **Computes coherence** — five independent planes (Physical, Mental, Spiritual, Conscious, ANIMA) each evaluate the behavioral record from a different epistemology. Their weighted sum is C(t).
3. **Emits or silences** — if C(t) ≥ Θ(t), a 346-byte canonical certificate is signed by the diversity-weighted BFT validator set. If not, no signal is emitted. Silence is the fail-closed security property.
4. **Routes cross-chain** — the certificate authorizes zero-bridge settlement: economic value moves between chains via SPV proof and quorum attestation, without wrapping, minting, or bridging tokens.

---

## Architecture

```
                    ┌─────────────────────────────────┐
                    │         EXTERNAL DATA SOURCES     │
                    │  60+ EVM chains · 36 non-EVM    │
                    │  Solana · NEAR · TON · Sui ·    │
                    │  Aptos · Stacks · Stellar ·     │
                    │  Bitcoin · Cosmos · Polkadot     │
                    └───────────────┬─────────────────┘
                                    │
          ┌─────────────────────────▼─────────────────────────┐
          │   INGESTION LAYER (L0)                           │
          │   Rust indexers — 23 crates → FAISS              │
          │   Canonical BH: 93 bytes, cross-VM identical      │
          └─────────────────────────┬─────────────────────────┘
                                    │
          ┌─────────────────────────▼─────────────────────────┐
          │              FIVE BEHAVIORAL PLANES                │
          │                                                   │
          │   Φ Physical    9 Shannon entropy + 7 MF detectors │
          │   M Mental      Prediction confidence (CI_95)      │
          │   Σ Spiritual   Diversity-weighted BFT             │
          │   K Conscious   Human annotation network           │
          │   A ANIMA       Cross-domain AI calibration         │
          └─────────────────────────┬─────────────────────────┘
                                    │
          ┌─────────────────────────▼─────────────────────────┐
          │   COHERENCE ENGINE                                │
          │                                                   │
          │   C(t) = α·Φ + β·M + γ·Σ + δ·K + ε·A              │
          │   Θ(t) = Θ_min + (Θ_max − Θ_min)·V(t)             │
          │   M_moat = D · Q · R · X · F · N                   │
          │                                                   │
          │   T(t) = [C ≥ Θ] · S · e^(M_moat · t)             │
          └─────────────────────────┬─────────────────────────┘
                                    │
                    ┌───────────────▼───────────────┐
                    │   C ≥ Θ?                      │
                    │   YES → emit certificate      │
                    │   NO  → SILENCE (fail-closed) │
                    └───────────────┬───────────────┘
                                    │
          ┌─────────────────────────▼─────────────────────────┐
          │   CANONICAL CERTIFICATE (346 bytes)              │
          │   DW-BFT quorum · replay guards · TTL             │
          │   Same payload verifiable on every VM             │
          └─────────────────────────┬─────────────────────────┘
                                    │
          ┌─────────────────────────▼─────────────────────────┐
          │   OUTPUT                                         │
          │   On-chain publishing · BTCP Zero-Bridge router   │
          │   ITRIONConsumer callback interface                │
          └───────────────────────────────────────────────────┘
```

Full architecture map: [ARCHITECTURE_MAP.md](./ARCHITECTURE_MAP.md)

---

## The Akashic Index

The Akashic Index is TRION's append-only behavioral record. Every witnessed action becomes a canonical Behavioral Hash and is permanently stored. The index is thermodynamically conserved — information only grows, never decays.

### The Behavioral Hash (BH)

Every action — a transfer, a swap, a vote, a bridge lock — is reduced to a 93-byte canonical payload, then hashed via Hash_DNA to produce a sense/antisense pair (named by analogy to DNA).

```
BH(event) = Hash_DNA(payload)

payload (93 bytes, big-endian):
  offset  width  field
  ──────  ─────  ───────────────
  0       32     entity_id        SHA3-256(normalise(sender))
  32      1      event_type        canonical type ID (0..19)
  33      8      magnitude_nano    trunc(magnitude × 10⁹)
  41      8      context           venue/layer flags
  49      8      timestamp_secs    block time (unix seconds)
  57      4      chain_id          TRION canonical chain ID
  61      32     block_hash        chain block hash
```

The same transaction produces the same 93-byte BH on every implementation — Python, Rust, TypeScript, Solidity, Cairo, Clarity. This is verified by golden vectors in `tests/golden/vectors.json` and enforced by the cross-language parity test `scripts/cross_lang_bh_check.py`.

### Properties

- **Append-only** — no entry is ever modified or deleted. The index grows monotonically.
- **Thermodynamically conserved** — information conservation law: dI/dt ≥ 0.
- **Cross-VM canonical** — the same event yields the same BH regardless of implementation language or VM.
- **Merkle-accumulated** — daily Merkle roots enable O(log N) inclusion proofs.
- **FAISS-indexed** — BH vectors are embedded in a FAISS index for archetype detection, similarity search, and anomaly detection.
- **Three-tier storage** — HOT (in-memory), WARM (SQLite / TimescaleDB), COLD (Merkle-anchored archive).

### Storage Backends

| Backend | Use Case | When to Use |
|---------|----------|-------------|
| SQLite | Testing & development | Default — no external dependencies |
| TimescaleDB | Production | Set `TIMESCALEDB_URL` for dual-write (billions of rows over decades) |
| FAISS | Similarity search & archetype matching | Always — in-memory vector index |

TimescaleDB schema: [schema.sql](./schema.sql) — hypertables with automatic time-based partitioning.

---

## BTCP Zero-Bridge

The Bitcoin-Backed Cross-Chain Protocol (BTCP) Zero-Bridge routes economic value between chains without wrapping, minting, or bridging tokens. It is the settlement layer that consumes TRION certificates.

The Zero-Bridge does not move tokens. It proves, via SPV, that value is locked on the source chain, then authorizes release on the destination chain via a DW-BFT quorum certificate. The invariant is: **`assets_bridged = false`** — the asset never leaves its native chain. Only the economic value moves, escrow-bound to the lock proof.

### The 5-step settlement flow

```
1. register_intent   →  ZK commitment on destination (MEV-private)
2. lock_escrow       →  asset locked on source chain UTXO/account
3. register_route    →  escrow bound to lock proof on destination
4. release_escrow    →  DW-BFT quorum certificate authorizes release
5. finalize_route    →  route finalized, value available on destination
```

### Deployed contracts

| VM | Network | Contract | Proof |
|----|---------|----------|-------|
| Starknet | Sepolia | ZKVerifier v2 `0x70786a31...` | [proofs/zk/stark/zk_500_proofs.json](./proofs/zk/stark/zk_500_proofs.json) |
| Arbitrum | Sepolia | TRIONSensingOracle `0x1d129D34...` | [proofs/btcp-zero-bridge/evm/arbitrum/](./proofs/btcp-zero-bridge/evm/arbitrum/) |
| Solana | Devnet | 5 Anchor programs | [proofs/btcp-zero-bridge/solana/](./proofs/btcp-zero-bridge/solana/) |
| Stacks | Testnet | 7 Clarity contracts | [proofs/btcp-zero-bridge/stacks/](./proofs/btcp-zero-bridge/stacks/) |
| Stellar | Testnet | 3 Soroban contracts | [proofs/btcp-zero-bridge/stellar/](./proofs/btcp-zero-bridge/stellar/) |
| Bitcoin | Testnet | SPV locks | [proofs/oracle/btc_lock_tx_result.json](./proofs/oracle/btc_lock_tx_result.json) |
| Ethereum | Sepolia | First signal `0x0d7f6956...` | [proof-ledger/first_signal.json](./proof-ledger/first_signal.json) |

---

## Repository Structure

```
trion-core/
├── adapters/              Cross-VM adapter layer (Rust)
├── anima-service/          ANIMA AI calibration engine (FastAPI, port 8001)
├── api/                    Oracle API (Flask + SocketIO, port 5000)
├── btc-tools/              Cross-chain tooling (JavaScript)
├── chains/                 Per-chain client code (TypeScript + Rust)
├── config/                 Deployment configs + chain registry
├── contracts/              Smart contracts — 10+ VMs
│   ├── solidity/            EVM contracts (Hardhat) + interfaces/ITRIONConsumer.sol
│   ├── starknet/            Cairo contracts (Scarb)
│   ├── svm/                 Solana (Anchor)
│   ├── move/                Sui/Aptos (Move)
│   ├── clarity/             Stacks (Clarinet)
│   ├── soroban/             Stellar (Soroban)
│   └── vyper/               Vyper staking contract (Z3-verified)
├── core/                   Python core — all 5 planes, consensus, BTCP, security
├── docs/                   Documentation (architecture, protocol, deployment, audit)
├── formal/                 Formal verification (Lean 4, Coq, TLA+, Haskell, Z3 SMT)
├── hardhat/                EVM Hardhat project
├── indexers/               Rust L0 indexers (23 crates — one per VM family)
├── math/                   Mathematical validation (Rust + Julia)
├── network/                Go network health monitor
├── proofs/                 Categorical proof evidence (BTCP, ZK, adversarial, oracle)
├── proof-ledger/            On-chain signal emission ledger
├── relayer/                Multi-chain relayer (Node.js)
├── rust/                   Rust core library (BH, Φ, Σ, MasterEquation)
├── schema.sql              TimescaleDB schema (production Akashic Index)
├── scripts/                Python + shell utility scripts (start, deploy, verify)
├── sdk/                    SDKs — Python (pip), Rust (cargo), TypeScript (npm)
├── signal-processing/      C++ signal processing (FFT, sensor conditioning)
├── tests/                  Test suites (unit, integration, adversarial, golden)
├── validator/              Go DW-BFT validator (P2P mesh + consensus daemon)
└── zk/                     ZK circuits (Cairo + circom)
```

---

## Quick Start — Run TRION

Every command below has been tested against a fresh clone of this repository.

### Prerequisites

| Language | Version | Install Command | Used For | Required? |
|----------|---------|-----------------|----------|-----------|
| Python | 3.11+ | [python.org](https://python.org) | Oracle API, FAISS ANIMA, core, formal verification | **YES** |
| Rust | 1.80+ | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh` | L0 Indexers — watches blockchains, feeds BHs into Akashic Index | **YES** |
| Node.js | 20+ | [nodejs.org](https://nodejs.org) | Relayer, btc-tools, SDK | Optional |
| Go | 1.21+ | [go.dev/dl](https://go.dev/dl/) | Validator, network monitor | Optional (for validators) |
| Lean 4 | 4.34+ | `curl -sSf https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh \| sh` | Formal proofs | Optional (for verification) |

**Rust is required.** Without the Rust indexers, the Oracle has no behavioral data to evaluate — the Akashic Index stays empty, D(t) = 0, and every signal is SILENCE/COLD_START. The indexers are L0 — they are the foundation of the entire pipeline. They watch blockchains, extract behavioral events, compute 93-byte Behavioral Hashes, and feed them into the FAISS Akashic Index. Without them, TRION is blind.

### PyO3 — Rust powers the core math (Whitepaper Part 11)

The whitepaper Part 11 specifies: *"Performance-critical paths compiled to Rust via PyO3 bindings."* This is implemented:

- **Rust modules** (`rust/src/`): `phi.rs` (L1.1 Φ — 609 lines), `sigma.rs` (L4.1 Σ — 257 lines), `master_equation.rs` (L5 T(t) — 457 lines), `pyo3_bindings.rs` (bridge — 489 lines)
- **Python bridge** (`core/rust_bridge_pyo3.py`): tries `import trion_rust` (PyO3), then `ctypes.CDLL` (ctypes fallback), then Python reference implementation
- **Build command**: `cd rust && cargo build --release --features pyo3` → produces `libtrion_btcp.so` (750KB cdylib)
- **4 Rust-native functions** accessible from Python:
  1. `compute_behavioral_hash` — L0.1 93-byte dual-strand Behavioral Hash
  2. `compute_phi` — L1.1 9-feature Shannon entropy Physical Richness Φ
  3. `compute_sigma` — L4.1 diversity-weighted BFT Spiritual Plane Σ
  4. `compute_master_equation` — L5 Master Equation T(t) = [C≥Θ]·S·e^(M·t)

When the `.so` is present, the Oracle automatically uses Rust for BH, Φ, Σ, and T(t) computation. Without it, it falls back to Python reference implementations (same formulas, same golden vectors — just slower).

---

### Linux / WSL

```bash
# ── Step 1: Clone ──────────────────────────────────────────────
git clone https://github.com/dev-analyshd/trion-core.git
cd trion-core

# ── Step 2: Install Python ────────────────────────────────────
python3 -m venv .venv
source .venv/bin/activate
pip install flask flask-socketio simple-websocket flask-cors \
    feedparser vaderSentiment langdetect faiss-cpu pydantic \
    fastapi uvicorn z3-solver web3 eth-account

# ── Step 3: Install Rust ───────────────────────────────────────
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env

# ── Step 4: Build the 23 Rust indexers ─────────────────────────
cd indexers
cargo build --release
# → Produces 23 binaries: trion-evm, trion-svm, trion-utxo, trion-starknet, ...
# → Build time: ~10 minutes (23 crates, each ~4MB binary)
cd ..

# ── Step 4b: Build the Rust PyO3 core (performance-critical math) ──
# This produces libtrion_btcp.so — the Rust native library that powers
# BH computation, Φ (Physical), Σ (Spiritual), and T(t) (Master Equation).
# Without this, Python fallback is used (same formulas, slower).
cd rust
cargo build --release --features pyo3
cd ..
# → Produces rust/target/release/libtrion_btcp.so (750KB)
# → Python bridge auto-detects it via ctypes

# ── Step 5: Configure environment ─────────────────────────────
cp .env.example .env
# Edit .env — set PRIVATE_KEY (testnet), RPC URLs, API keys (optional for testing)

# ── Step 6: Start the FAISS ANIMA engine (port 8001) ──────────
cd anima-service
FAISS_PORT=8001 python3 faiss_service.py &
cd ..

# ── Step 7: Start the Oracle API (port 5000) ──────────────────
FAISS_SERVICE_URL=http://127.0.0.1:8001 python3 serve.py &

# ── Step 8: Start the Rust EVM indexer ────────────────────────
# This watches 72 EVM chains in parallel and feeds BHs into FAISS.
# The indexer connects to FAISS on port 8001 (set in Step 6).
FAISS_SERVICE_URL=http://127.0.0.1:8001 ./indexers/target/release/trion-evm &

# ── Step 9: Verify the full pipeline is working ───────────────
# Check Oracle health (should show "healthy"):
curl http://localhost:5000/api/v1/health

# Check FAISS (should show indexed_vectors growing):
curl http://localhost:8001/health

# Check the signal (should show COLD_START initially, then COHERENT as data flows):
curl http://localhost:5000/api/v1/signal/TRION_PROTOCOL

# Check the live feed (should show new entries appearing):
curl http://localhost:5000/api/v1/feed
```

### macOS

```bash
# Install Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python
brew install python@3.12

# Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env

# Clone and run (same as Linux steps 1-9 above)
git clone https://github.com/dev-analyshd/trion-core.git
cd trion-core
python3 -m venv .venv
source .venv/bin/activate
pip install flask flask-socketio simple-websocket flask-cors \
    feedparser vaderSentiment langdetect faiss-cpu pydantic \
    fastapi uvicorn z3-solver web3 eth-account
cd indexers && cargo build --release && cd ..
cd rust && cargo build --release --features pyo3 && cd ..
cd anima-service && FAISS_PORT=8001 python3 faiss_service.py &
cd ..
FAISS_SERVICE_URL=http://127.0.0.1:8001 python3 serve.py &
FAISS_SERVICE_URL=http://127.0.0.1:8001 ./indexers/target/release/trion-evm &
```

### Windows (WSL)

```powershell
# 1. Install WSL (run in PowerShell as Admin)
wsl --install -d Ubuntu-22.04

# 2. Open WSL terminal
wsl

# 3. Inside WSL, run the same commands as Linux (above)
```

> **Note for Windows users:** TRION uses Unix sockets, file permissions, and process management. Running via WSL (Ubuntu) is the supported path. Native Windows is not tested.

---

### Verify the Full Pipeline

After starting all 3 services (FAISS + Oracle + Indexer), verify the complete data flow:

```bash
# 1. FAISS health — should show indexed_vectors > 0 (growing as indexer runs)
curl http://localhost:8001/health
# Expected: {"status":"ok","faiss_available":true,"indexed_vectors":2178,...}

# 2. Oracle health — should show "healthy"
curl http://localhost:5000/api/v1/health
# Expected: {"status":"healthy","oracle":"TRION Protocol v2.0.0",...}

# 3. Live signal — should show signal_type + coherence_score
curl http://localhost:5000/api/v1/signal/TRION_PROTOCOL
# Expected: {"signal_type":"SILENCE","signal_subtype":"COLD_START",...}
# (COLD_START means FAISS has no behavioral history for this entity yet —
#  as the indexer feeds data, D(t) grows and signals become COHERENT)

# 4. Live feed — should show entries appearing over time
curl http://localhost:5000/api/v1/feed
# Expected: {"feed":[...],"total_computed":N,...}

# 5. Akashic depth (D(t)) — should grow as indexer runs
curl http://localhost:8001/api/v1/depth/TRION_PROTOCOL
# Expected: depth value increasing over time

# 6. VM coverage — should show 12 VM families + 34+ chains
curl http://localhost:8001/vm-status
# Expected: {"vm_families":{"EVM":{...},"SVM":{...},...}}

# 7. Falsifiability — should show 15 conditions
curl http://localhost:5000/api/v1/governance/falsifiability
# Expected: {"conditions":[...15 conditions...]}
```

### Available Indexers

The `cargo build --release` command produces 23 binaries, one per VM family:

| Binary | VM Family | Chains | Example |
|--------|-----------|--------|---------|
| `trion-evm` | Ethereum/EVM | 72 | Ethereum, Arbitrum, Base, Optimism, Polygon, BNB, Mantle, Linea, Scroll, HashKey, Botanix, Monad, ... |
| `trion-svm` | Solana | 3 | Solana Mainnet, Devnet, Testnet |
| `trion-utxo` | Bitcoin/UTXO | 6 | Bitcoin, Litecoin, Dogecoin, Bitcoin Cash, ... |
| `trion-starknet` | Starknet | 1 | Starknet Sepolia |
| `trion-cosmos` | Cosmos SDK | 6 | Cosmos Hub, Osmosis, Juno, Akash, Celestia, Injective |
| `trion-near` | NEAR | 2 | NEAR Mainnet, Testnet |
| `trion-ton` | TON | 2 | TON Mainnet, Testnet |
| `trion-sui` | Sui | 1 | Sui Mainnet |
| `trion-aptos` | Aptos (Move) | 2 | Aptos, Testnet |
| `trion-stacks` | Stacks | 1 | Stacks Testnet |
| `trion-stellar` | Stellar (Soroban) | 1 | Stellar Testnet |
| `trion-pvm` | Polkadot | 2 | Polkadot, Kusama |
| `trion-tron` | TRON | 1 | TRON Mainnet |
| `trion-movement` | Movement (MVM) | 2 | Movement, Testnet |
| `trion-hedera` | Hedera | 1 | Hedera Mainnet |
| `trion-algorand` | Algorand | 1 | Algorand Mainnet |
| `trion-cardano` | Cardano | 1 | Cardano Mainnet |
| `trion-multiversx` | MultiversX | 1 | MultiversX Mainnet |
| `trion-vechain` | VeChain | 1 | VeChain Mainnet |
| `trion-waves` | Waves | 1 | Waves Mainnet |
| `trion-xrpl` | XRPL | 1 | XRP Ledger |
| `trion-botchain` | BotChain | 1 | BotChain Mainnet |
| `trion-pi` | Pi Network | 1 | Pi Mainnet |

To start multiple indexers (e.g., EVM + Solana + Bitcoin):

```bash
FAISS_SERVICE_URL=http://127.0.0.1:8001 ./indexers/target/release/trion-evm &
FAISS_SERVICE_URL=http://127.0.0.1:8001 ./indexers/target/release/trion-svm &
FAISS_SERVICE_URL=http://127.0.0.1:8001 ./indexers/target/release/trion-utxo &
```

Each indexer polls its chains every 15 seconds, extracts behavioral events, computes 93-byte Behavioral Hashes, and POSTs them to the FAISS service at `http://127.0.0.1:8001/index/add`. The FAISS service stores them in the Akashic Index. The Oracle reads from the Akashic Index to compute coherence scores.

---

### Start Additional Components

#### Rust Indexers (L0 — watches blockchains)

```bash
# Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env

# Build all 23 indexers
cd trion-core/indexers
cargo build --release

# Start the EVM indexer (watches Ethereum, Arbitrum, Base, etc.)
FAISS_SERVICE_URL=http://127.0.0.1:8001 ./target/release/trion-evm
```

#### Go Validator (BFT consensus)

```bash
# Install Go (Linux/macOS)
# Download from https://go.dev/dl/ or:
wget https://go.dev/dl/go1.22.5.linux-amd64.tar.gz
sudo tar -C /usr/local -xzf go1.22.5.linux-amd64.tar.gz
export PATH=$PATH:/usr/local/go/bin

# Build and run the validator
cd trion-core/validator
go build -o trion-validator ./cmd/trion-validator

# Self-test mode (runs 4-node BFT demo and exits)
./trion-validator --self-test

# Daemon mode (long-running — listens for peers + runs consensus)
./trion-validator --addr 0.0.0.0:9000 --healthz 0.0.0.0:9090
```

#### Node.js Relayer (multi-chain signal relay)

```bash
cd trion-core/relayer
npm install --legacy-peer-deps

# Dry-run mode (no on-chain submission — polls Oracle API)
node relayer.js --dry-run
```

#### EVM Contracts (Hardhat)

```bash
cd trion-core/hardhat
npm install
npx hardhat compile
npx hardhat test
```

#### Cairo ZK Contracts (Starknet)

```bash
# Install Scarb (Cairo compiler)
curl --proto '=https' --tlsv1.2 -sSf https://docs.swmansion.com/scarb/download.sh | sh

cd trion-core/zk/stark/contract
scarb build
```

#### Start Everything at Once

```bash
cd trion-core
./scripts/start_trion.sh              # foreground (logs to terminal)
./scripts/start_trion.sh --background  # background (logs to logs/)
```

#### Docker

```bash
cd trion-core
cp .env.example .env
docker compose up --build
# Oracle API:   http://localhost:5000/api/v1/health
# ANIMA:        http://localhost:8001/health
# Dashboard:    http://localhost:5000/app/
```

---

## Run a Validator

### Hardware Requirements (Whitepaper §9.2)

| Component | Minimum | Notes |
|-----------|---------|-------|
| CPU | 32+ cores (AMD EPYC 9354 or Intel Xeon w9-3475X) | For FFT + FAISS + consensus |
| RAM | 256GB DDR5 ECC | For in-memory Akashic Index |
| Storage | 10TB NVMe SSD | For append-only behavioral history |
| GPU | NVIDIA A100 or H100 | For FAISS GPU acceleration |
| Network | 10Gbps dedicated fiber | For real-time chain indexing |
| HSM | Thales Luna 7 or Yubico YubiHSM 2 | **NON-NEGOTIABLE** — validator key custody |

### What Validators Do

1. **Run the Go validator daemon** — connects to the P2P mesh, participates in BFT consensus rounds every 15 seconds, signs canonical certificates using HSM-backed keys
2. **Index at least one chain** — each validator runs a Rust indexer for at least one VM family, feeding behavioral hashes into the FAISS Akashic Index
3. **Maintain uptime** — uptime below minimum triggers slashing (0.1% per day)
4. **Stay diverse** — validators that coordinate with others have their voting power reduced to zero (diversity-weighted BFT)

### Onboarding Steps

```bash
# 1. Provision hardware (see requirements above)
#    Cloud (AWS/Azure/GCP) is acceptable for CPU/RAM/GPU.
#    HSM must be physical Thales Luna 7 or YubiHSM 2.
#    AWS Dedicated HSM (Thales Luna 7 in AWS data center) qualifies.

# 2. Install the validator software
git clone https://github.com/dev-analyshd/trion-core.git
cd trion-core/validator
go build -o /usr/local/bin/trion-validator ./cmd/trion-validator

# 3. Configure HSM
#    For YubiHSM 2: install yubihsm-shell, configure PKCS#11
#    For Thales Luna 7: install client software, configure partition

# 4. Generate validator key (HSM-backed)
#    The key NEVER leaves the HSM. The validator signs via PKCS#11 interface.

# 5. Start the daemon
trion-validator --addr 0.0.0.0:9000 --healthz 0.0.0.0:9090 --region "NA-US"

# 6. Stake TRION tokens (after mainnet launch)
#    Minimum stake required. Stake at risk for slashing.
```

### Geographic Distribution

The protocol requires:
- ≥100 validators across ≥4 continents
- No single region >40% of total weight
- No single jurisdiction >30% of total weight

If geographic constraints are violated, the AWA automatically freezes signal emission until rebalanced.

---

## Formal Verification

TRION uses multiple formal verification tools. All are installed and tested in this repository.

### Lean 4 (v4.34.0)

```bash
# Install Lean
curl -sSf https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh | sh
source $HOME/.elan/env
elan default leanprover/lean4:v4.34.0

# Compile the proofs
cd trion-core/formal/lean
lean TRIONTheorems.lean          # exit 0 = success (T1, T2, T4)
lean ConvergenceTheorem.lean     # exit 0 = success (T3 — convergence theorem)
```

### Z3 SMT Solver (v5.1.0)

```bash
pip install z3-solver

cd trion-core
python3 formal/smt/verify_staking_smt.py
# → RESULT: 19/19 properties VERIFIED, 0 counterexamples
```

### TLA+ / TLC

```bash
# Download TLA+ tools
wget https://github.com/tlaplus/tlaplus/releases/download/v1.8.0/tla2tools.jar

# Run TLC model checker
cd trion-core/formal/spec
java -jar ~/tla2tools.jar -config TRIONBFT.cfg -deadlock TRIONBFT.tla
```

### Haskell (GADT proofs)

```bash
# Install Haskell Stack
curl -sSf https://get.haskellstack.org | sh

cd trion-core/formal
stack build
stack test
```

### Coq

Coq requires OCaml/opam. Install via:
```bash
# Linux (requires sudo)
sudo apt-get install coq

# macOS
brew install coq

# Verify
cd trion-core/formal/coq
coqc TRIONTheorems.v
```

### Verification Summary

| Tool | File | What It Proves | Status |
|------|------|----------------|--------|
| Lean 4 | `formal/lean/TRIONTheorems.lean` | T1 (BFT safety), T2 (SILENCE≠VALUATION), T4 (manipulation collapse) | ✅ Compiles exit 0 |
| Lean 4 | `formal/lean/ConvergenceTheorem.lean` | T3 (convergence to H_irreducible) | ✅ Compiles exit 0 |
| Z3 SMT | `formal/smt/verify_staking_smt.py` | 19 safety properties of TRIONStaking.vy | ✅ 19/19 verified |
| TLA+ | `formal/spec/TRIONBFT.tla` | BFT consensus safety (TLC model check) | ✅ No invariant violations |
| Haskell | `formal/src/TRION/Theorems.hs` | T2 (GADT phantom types), T8 (Akashic append-only) | ✅ Compiled |
| Coq | `formal/coq/TRIONTheorems.v` | Mirror proofs of Lean theorems | ✅ Syntactically valid |

---

## Achievements

### On-Chain Deployments

| VM | Contracts | Network | Proof |
|----|-----------|---------|-------|
| Starknet (Cairo) | 7 + ZKVerifier v2 | Sepolia | [proofs/zk/stark/zk_500_proofs.json](./proofs/zk/stark/zk_500_proofs.json) |
| Arbitrum (Solidity) | 7 | Sepolia | [proofs/btcp-zero-bridge/evm/arbitrum/](./proofs/btcp-zero-bridge/evm/arbitrum/) |
| Solana (Anchor) | 5 | Devnet | [proofs/btcp-zero-bridge/solana/](./proofs/btcp-zero-bridge/solana/) |
| Stacks (Clarity) | 7 | Testnet | [proofs/btcp-zero-bridge/stacks/](./proofs/btcp-zero-bridge/stacks/) |
| Stellar (Soroban) | 3 | Testnet | [proofs/btcp-zero-bridge/stellar/](./proofs/btcp-zero-bridge/stellar/) |
| Bitcoin (UTXO) | SPV locks | Testnet | [proofs/oracle/btc_lock_tx_result.json](./proofs/oracle/btc_lock_tx_result.json) |
| Ethereum | First signal | Sepolia | [proof-ledger/first_signal.json](./proof-ledger/first_signal.json) |

### ZK Proof Gauntlet

| Metric | Value |
|--------|-------|
| Proofs submitted | 500/500 |
| Succeeded | 412 |
| Expected adversarial reverts | 75 |
| Nonce race failures | 13 |
| Contract counter | 427 |

### Formal Verification

| Metric | Value |
|--------|-------|
| Lean proofs compiled | 8 (T1, T2, T3, T4 + 4 others) |
| Z3 SMT properties verified | 19/19 |
| TLA+ TLC model check | No violations |
| Haskell GADT proofs | T2, T8 machine-checked |
| Lean sorries | 0 |

### On-Chain First Signal

| Field | Value |
|-------|-------|
| TX Hash | `0d7f69568bcd95e732c2843ef50df51410797f2f84b45ed8deba0c79c915219e` |
| Block | 11735022 |
| Status | SUCCESS |
| Network | Ethereum Sepolia (chain_id 11155111) |
| Signal Type | BOOTSTRAP |
| Entity | TRION_PROTOCOL |
| Signer | `0xdBbf66CAD621dA3Ec186D18b29a135d2A5d42d20` |

---

## Proofs

All proof files are in [proofs/](./proofs/), organized by category:

| Category | Path | Contents |
|----------|------|----------|
| BTCP Zero-Bridge | [proofs/btcp-zero-bridge/](./proofs/btcp-zero-bridge/) | Per-VM liquidity unlock proofs (cross-VM) |
| ZK | [proofs/zk/](./proofs/zk/) | ZK 500-proof gauntlet (Starknet) |
| Adversarial | [proofs/adversarial/](./proofs/adversarial/) | 20/20 batteries per VM |
| Oracle | [proofs/oracle/](./proofs/oracle/) | SPV verifier, BTC lock tx, anchor parity |
| Mission Audits | [proofs/mission-audits/](./proofs/mission-audits/) | Production readiness conformance |

---

## Vision

TRION is the engineering surface of a larger framework: the **Witness World**. In the Witness World, every action leaves a permanent behavioral trace — observable, verifiable, immutable. Identity is not a credential; it is the continuity of behavior across time, witnessed by independent planes.

The **Action Economy** is the economic layer of the Witness World. Every action has a coherence cost and a coherence yield. Actions that cohere — consistent across the five planes — accumulate Biological Capital BC(t). Actions that do not cohere are silent: they produce no signal, no certificate, no settlement. Silence is not punishment; it is the protocol's refusal to assert what it cannot verify.

The **Akashic Index** is the ledger of the Witness World — append-only, thermodynamically conserved, cross-VM canonical. Every witnessed action is permanently recorded. The index grows monotonically; information is never lost. This is the substrate on which identity, privacy, governance, and AI safety are built.

The **Right to Invisibility** is the privacy law of the Witness World. An entity can prove compliance without revealing behavior. The AWA freeze enforces fail-closed emission: when coherence cannot be verified, the protocol is silent. This is not privacy-for-privacy's-sake — it is the separation of observation from assertion. The behavioral record exists; what changes is who can observe it.

TRION's role is to make the Witness World verifiable. The five-plane coherence engine, the diversity-weighted BFT consensus, and the zero-bridge settlement layer are the mechanisms. The output is a canonical certificate — one payload, signed by a diverse quorum, verifiable on any VM. That certificate is the atom of the Action Economy: the smallest unit of verified behavioral truth that can authorize a settlement, an identity, a governance vote, or an AI safety assertion.

The long-term vision is a world where every action is witnessed, every identity is behavioral, every settlement is coherence-gated, and every AI is bounded by cross-domain calibration. TRION is the verification substrate underneath that world.

---

## Contact

- **GitHub:** [dev-analyshd/trion-core](https://github.com/dev-analyshd/trion-core)
- **Identity:** dev-analyshd
- **License:** CC0 — This knowledge belongs to everyone
- **Whitepaper:** TRION_PROTOCOL_White_paper.pdf (February 2026)

---

*Author: Hudu Yusuf (Analys) · CC0 — This knowledge belongs to everyone*

*T(t) = [C(t) ≥ Θ(t)] · S(t) · e^(M_moat · t)*

*Formulas: 57 · Signal types: 19 · Formal proofs: 4 · Languages: 12*
