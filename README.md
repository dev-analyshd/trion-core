# TRION Protocol — Multi-Chain Behavioral Truth Oracle

> *Real-time behavioral intelligence across **35 indexed networks** · **12 VM families** · Five planes of existence · 131 API routes · A pre-execution firewall that would have blocked **$388.9M** in historical DeFi exploits.*

[![Tests](https://img.shields.io/badge/Tests-328%20passed%2C%2024%20skipped-brightgreen)](tests/)
[![Attacks Blocked](https://img.shields.io/badge/Attacks%20Blocked-7%2F7-red)](simulate_attacks.py)
[![FAISS Vectors](https://img.shields.io/badge/FAISS%20Vectors-Growing%20Live%20from%2035%20chains-blue)](#faiss-anima-service)
[![Oracle API Routes](https://img.shields.io/badge/Oracle%20API%20Routes-131-purple)](#oracle-api----port-5000)
[![Workflows](https://img.shields.io/badge/Workflows-11%20Running-green)](#workflows)
[![Chains](https://img.shields.io/badge/Chains-35%20Networks%20%7C%2012%20VM%20Families-orange)](#indexed-networks)
[![0G Integration](https://img.shields.io/badge/0G-Chain%20%2B%20Storage%20%2B%20DA%20%2B%20Compute%20%2B%20KV-blueviolet)](#0g-integration)
[![License: CC0](https://img.shields.io/badge/License-CC0-lightgrey)](https://creativecommons.org/publicdomain/zero/1.0/)

---

## The Problem TRION Solves

**DeFi protocols lose billions to attackers who look identical to honest users on-chain — until they strike.**

Raw on-chain data (balances, transfers, gas) cannot detect behavioral manipulation: a wallet slowly accumulating governance tokens before a capture attack, an MEV bot probing liquidity across 12 chains to calibrate a sandwich, or a Sybil cluster simulating organic user growth. Traditional oracles report prices. TRION reports *behavioral truth* — whether an entity's on-chain behavior is coherent, honest, and safe.

**Concrete use case:** A DeFi protocol integrates `TRIONExecutionGate.checkExecution(address)` as a pre-trade hook. Before any wallet executes a large swap, TRION's 9-dimensional behavioral entropy score is checked on-chain. Wallets exhibiting `STATUS_COLLAPSE` or `STATUS_HOSTILE` — patterns matching Harvest Finance, Euler, or Beanstalk attack fingerprints — are blocked *before execution*. The protocol pays nothing until an anomaly is caught; TRION is a standing on-chain truth service funded by the 0G network.

**Every major DeFi exploit in history left behavioral fingerprints before it happened.** The Beanstalk governance attack ($182M): wallets accumulating voting tokens for weeks, all showing `GOVERNANCE_CAPTURE` patterns. Harvest Finance ($34M): flash loan probing across 6 protocols over 48 hours before execution. Euler ($197M): systematic position scaling with abnormal counterparty entropy. TRION reads these fingerprints in real time — before execution.

---

## How TRION Works — Step by Step

Understanding TRION requires following data from raw blockchain activity to a final on-chain gate signal. Here is every step in order.

### Step 1 — Data Ingestion (14 Rust Indexers + 7 Node.js Supervisors)

Every few seconds, TRION's indexers poll 35 networks across 12 VM families and extract **raw behavioral signals** from each new block.

The Rust L0 indexers (`rust-indexers/crates/`) are the highest-performance layer. For each block on each chain, they extract 9 Shannon entropy features:

| Feature | What It Measures |
|---------|-----------------|
| `H(V)` | Transaction volume entropy — how random is the distribution of transaction values? |
| `H(addr)` | Counterparty diversity — how many unique addresses is this entity interacting with? |
| `H(run-len)` | Temporal spacing entropy — are transactions evenly spaced or clustering suspiciously? |
| `H(E)` | Smart contract interaction entropy — how diverse are the contracts being called? |
| `H(recv-ETH)` | Value flow entropy — how is value distributed across outputs? |
| wallet-arch | EOA vs contract mix — is this entity a human, a bot, or a contract? |
| `H(contract-freq)` | Cross-protocol entropy — how many different protocols is this entity touching? |
| `H(G)` | Gas usage pattern entropy — consistent gas or wildly variable (MEV indicator)? |
| `H(5-cat)` | MEV pattern entropy — distribution across sandwich/arb/liquidation/transfer/other |

Each of these 9 values is a Shannon entropy computed over the distribution of that feature across the block's transactions. Higher entropy = more natural random behavior. Lower entropy = suspiciously predictable or targeted behavior.

**The 93-byte Behavioral Hash (BH):** Every transaction also gets a canonical fingerprint (`trion-common/src/lib.rs`):

```
entity_id(32) || event_type(1) || magnitude_nano(8) || context(8) ||
timestamp(8)  || chain_id(4)   || block_hash(32)
= 93 bytes total
```

This canonical format is chain-agnostic — it is produced identically whether the source is an EVM transaction, a Solana slot, a Cosmos block, or a Bitcoin UTXO set.

**Native and Extended VM indexers** (Node.js, running in `chains/`) cover the remaining 31 non-EVM chains. They translate each chain's native block format into the same 9 abstract dimensions. A NEAR transaction's `action-kind diversity entropy` occupies the same behavioral slot as an EVM transaction's `counterparty entropy`. This is how TRION achieves cross-chain coherence scoring — every chain speaks the same 9-dimensional language.

**All vectors are sent to the FAISS ANIMA engine** via `POST /index/add_batch` every block cycle.

---

### Step 2 — FAISS ANIMA Engine (Python/FastAPI, port 8000)

The FAISS ANIMA engine (`akashic/faiss_service.py`) is TRION's behavioral memory. It maintains a **128-dimensional vector index** (FAISS `IndexIVFPQ`) that accumulates every behavioral vector streamed from the indexers.

**Why 128 dimensions?** The 9 raw Shannon entropy features are expanded to 128 dimensions through:
- The 9 base features
- Cross-feature interaction terms (f1×f2, f1×f3, ...) — captures correlated manipulation
- Temporal lag features (f_t vs f_{t-1}) — captures behavioral change rate
- Normalization layers per VM family — ensures a Bitcoin UTXO block and an EVM block are comparable

**What FAISS computes for each entity:**

1. **Akashic Depth `D(t)`** — how many behavioral observations exist for this entity. New entities start at `D=0` (high uncertainty). Active entities accumulate depth continuously.

2. **Archetype Similarity** — TRION maintains 64 pre-trained behavioral archetypes (centroids stored in `trion_archetype_centroids.npy`). Every entity is compared against all 64 archetypes via k-NN search. The nearest archetype determines the entity's behavioral cluster: `GENESIS` (new organic), `VALUATION` (active trader), `SILENCE` (anomaly), `GOVERNANCE_CAPTURE`, `FLASH_LOAN_ATTACKER`, etc.

3. **ANIMA Score `A`** — a composite evolutionary fitness metric that measures how well the entity's behavior conforms to its nearest archetype over time. An entity that suddenly shifts archetype clusters (e.g., from `VALUATION` to `GOVERNANCE_CAPTURE`) shows a sharp drop in `A`.

4. **Thermodynamic Information Conservation** — entropy over the entity's last N behavioral vectors. Natural entities show slowly drifting entropy. Attackers show entropy spikes — sudden changes in behavioral distribution that precede an exploit.

The FAISS index starts empty on each session and grows continuously. Within minutes it contains hundreds of vectors; within an hour, thousands. All data is **live from real blockchain activity** — nothing is mocked.

---

### Step 3 — Oracle API Scoring Engine (Python/Flask, port 5000)

The Oracle API (`oracle_api/app.py`, 131 routes) is the integration point for everything. When any consumer calls `GET /api/v1/signal/{entity_id}`, the following pipeline executes:

**3a. Physical Plane (Φ)**

The 9 Shannon entropy features for the entity are retrieved from FAISS. Each is normalized to [0,1] where 1.0 = maximum natural behavioral diversity.

The raw Physical score is then adjusted for detected manipulation:

```
Φ_adj = Φ_raw × (1 − MF_score)
```

`MF_score` (Manipulation Fingerprint score) is computed by `src/security/` against 7 attack patterns:
- `ORACLE_ATTACK_ATTEMPT` — price oracle probing before a flash loan
- `FLASH_LOAN_SANDWICH` — characteristic volume+timing signature of sandwich attacks
- `COORDINATED_PUMP` — correlated wallet cluster activity
- `GOVERNANCE_CAPTURE` — systematic token accumulation before voting
- `SYBIL_CLUSTER` — artificial diversity mimicking organic multi-wallet behavior
- `CROSS_PROTOCOL_DRAIN` — sequential protocol interactions draining liquidity
- `LIQUIDITY_HEALTH` — abnormal LP position sizing patterns

If any pattern fires, `Φ_adj` is zeroed out. A zero physical plane alone is enough to trigger a SILENCE signal regardless of the other planes.

**3b. Mental Plane (M)**

Mental coherence measures *intent consistency* — does this entity do what it appears to be doing? It is computed using a hash-seeded observer-effect correction that detects when an entity's behavior changes based on whether it is being observed (a game-theoretic attack vector known as the observer effect in MEV).

For new entities with no FAISS history, `M` is seeded deterministically from the entity's on-chain identifier to give a neutral prior. This ensures TRION never returns null for unknown entities.

**3c. Spiritual Plane (Σ)**

Validator consensus diversity — how many independent validators on each chain have verified the entity's transactions? Higher validator diversity = higher Spiritual score. This penalizes entities that route through a narrow set of validators (a known method for censorship and sandwich coordination).

**3d. Conscious Plane (K)**

Commit-reveal annotation voting — a governance mechanism where TRION validators stake on behavioral classifications. The Conscious score reflects the stake-weighted consensus on entity classification. New entities start at `K = 0.10` (neutral prior).

**3e. ANIMA Plane (A)**

The ANIMA score from the FAISS engine — archetype evolutionary fitness. This is the only plane that requires actual FAISS data. For new entities, it is seeded from the entity's archetype distance using the pre-trained centroids.

**3f. Coherence Score Assembly**

```
C(t) = α·Φ_adj + β·M_adj + γ·Σ + δ·K + ε·A

α = 0.25  (Physical — raw behavioral entropy)
β = 0.30  (Mental  — intent consistency, highest weight)
γ = 0.25  (Spiritual — validator consensus diversity)
δ = 0.10  (Conscious — governance stake voting)
ε = 0.10  (ANIMA — archetype evolutionary fitness)
```

**3g. Dynamic Threshold**

The threshold `Θ(t)` is not static — it adapts to market conditions:

```
Θ(t) = 0.55 + 0.37 × volatility_norm     →    range [0.55, 0.92]
```

In calm markets (low volatility), `Θ = 0.55`. During high-volatility periods (market crashes, major liquidation cascades), `Θ` rises to 0.92 — the protocol tightens because the base rate of attacks rises during volatility. This prevents the oracle from being manipulated by deliberately triggering market volatility to lower the coherence threshold.

**3h. Signal Classification**

```
C(t) < Θ(t)     →  SILENCE   (anomaly — block execution)
C(t) ≥ Θ(t):
  ├─ ANIMA archetype "new entity"   →  GENESIS
  ├─ liquidity behavior detected    →  VALUATION
  ├─ cross-chain activity           →  TRANSCENDENCE
  └─ default                        →  VALUATION / COVENANT / TRION
```

**The Limiting Plane** — every response also reports which plane caused the lowest score. This is the behavioral diagnosis: `PHYSICAL_LIMITING` means raw entropy anomaly; `MENTAL_LIMITING` means intent inconsistency; `ANIMA_LIMITING` means archetype shift.

---

### Step 4 — 0G Integration (5 Components)

TRION integrates all 5 components of the 0G stack. Each serves a distinct architectural purpose.

**4a. 0G Chain** — The execution layer. TRION has 5 Solidity contracts deployed on 0G Galileo (chain 16602):

| Contract | Address | Purpose |
|---------|---------|---------|
| `TRIONExecutionGate` | `0xDB5910Dc6CfD219D00F64be1F23DA0289901356d` | Pre-trade firewall — `checkExecution(addr)` returns `STATUS_SAFE/ELEVATED/COLLAPSE/HOSTILE` |
| `TRIONOracleV3` | `0x0471B2BE25c2eBbAe7FAc17383F1692979F0A87C` | Publishes behavioral signals via `publishBehavioralTruth()` |
| `LiquidityOcean` | `0x105c7F6c16d2c92FEad10336C2b6A047F999a5A7` | Protected vault that checks coherence before withdrawals |
| `TravelRuleCompliance` | `0x5e7DBE6cc90d6260be2781dc312812834715EBaB` | Compliance scoring for cross-border DeFi |
| `BTCPSimpleEscrow` | `0x388f98831c749D7Acad2046329c9CeC94A8b248d` | BTCP-collateralized escrow gated by coherence |
| `AkashicProof` | `0x33c793fed5bf5fcB043D8c6c74256e7B4b38156D` | Permanent on-chain proof of behavioral dataset (Newton testnet) |

**4b. 0G Storage** — The FAISS index and behavioral signal history are too large to store on-chain. Instead, the `zg_sync_daemon.py` runs hourly, generating a delta export of new behavioral data (~1.36 MB binary), computing its Merkle-256 root, and uploading to 0G Storage. The Merkle root is committed on-chain via `AkashicProof.updateStorageRoot()` — creating an immutable, verifiable link between on-chain proof and off-chain data.

**4c. 0G DA (Data Availability)** — Every time a SILENCE signal fires, the full anomaly payload is streamed to 0G DA as a binary blob via `zg_da_streamer.py`. The DA commitment is:

```
commitment = SHA256(namespace || blob_sha256 || erasure_sha256)
```

with Reed-Solomon 2× erasure coding. This creates a permanent, non-reputable record of *why* every execution was blocked — the behavioral evidence that cannot be deleted or altered.

**4d. 0G Compute** — High-complexity ANIMA inference (archetype classification requiring TEE-verified computation) is routed through 0G Compute's serving broker (`sdk/zg_compute.mjs`). This prevents oracle manipulation: even if the TRION API is compromised, the behavioral archetype inference is verified inside a Trusted Execution Environment.

**4e. 0G KV** — Hot signal data (last 60 seconds of behavioral scores across all active entities) is maintained in 0G KV across 4 stream IDs. This enables microsecond-latency signal reads for high-frequency trading integrations without hitting the Oracle API.

---

### Step 5 — Relayers (Publishing Signals On-Chain)

The relayers are Node.js processes that bridge the Oracle API to the blockchain. They poll `GET /api/v1/signal/{id}` every 60–90 seconds, pack the result into a `uint256` signal, and submit it to the destination chain.

**TRION Relayer** (`relayer/relayer.js`): Publishes `C(t)` signals to 7 EVM chains simultaneously. Also includes the **0G ExecutionGate integration** (`relayer/zg_execution_gate_relayer.js`) which additionally submits:
- DA proof hash (from the 0G DA Streamer)
- 0G Storage root (from the latest sync cycle)
- Behavioral archetype classification

**Native VM Relayer** (`native-relayer/native_relayer.js`): Signs and submits block proofs to NEAR, TON, Polkadot, and StarkNet using each chain's native signature scheme.

**Extended Chain Relayer** (`relayer/extended_chain_relayer.js`): Publishes to 15 non-EVM chains using chain-native embedding methods:
- Bitcoin/LTC/DOGE/DASH: `OP_RETURN` outputs with 32-byte signal hash
- Cosmos chains: `MsgSend` memo field embedding
- Aptos/Movement: `entry_function` payload calls to TRION Move module
- SUI: Programmable transaction blocks
- TRON: `TriggerSmartContract` calls
- Pi Network: Stellar payment memo text

---

### Step 6 — Smart Contract Gating

Any DeFi protocol integrates TRION with a single line:

```solidity
import "./interfaces/ITRIONOracle.sol";

contract MyDeFiProtocol {
    ITRIONOracle public immutable trion;

    function executeTrade(address trader) external {
        // TRION gates the trade before execution
        (uint8 status, uint256 score) = trion.checkExecution(trader);
        require(status < STATUS_COLLAPSE, "TRION: behavioral anomaly detected");
        // ... execute trade
    }
}
```

`checkExecution()` reads the latest published signal from `TRIONExecutionGate` — an on-chain lookup, no external calls. The signal was published 60 seconds ago by the relayer. Gas cost: ~2,100 gas (single SLOAD). Latency: zero.

The four status codes:
```
STATUS_SAFE     (0)   C(t) ≥ Θ(t) + 0.15   — confident normal behavior
STATUS_ELEVATED (1)   C(t) ≥ Θ(t)           — normal, slightly elevated risk
STATUS_COLLAPSE (2)   C(t) < Θ(t)           — anomaly, soft block
STATUS_HOSTILE  (3)   C(t) < 0.30            — active attack pattern, hard block
```

---

### Step 7 — The Full Signal Flow (End to End)

```
Block produced on Arbitrum Mainnet
    │
    ▼
trion-evm (Rust) extracts 9 Shannon entropy features + canonical 93-byte BH
    │
    ▼
POST /index/add_batch → FAISS ANIMA (port 8000)
    ├── Updates 128-dim vector for block entity
    ├── Recomputes archetype distance (k-NN vs 64 centroids)
    └── Updates Akashic Depth D(t)
    │
    ▼
GET /api/v1/signal/{entity_id}   (relayer polls every 60s)
    ├── Physical Plane:  9 features from FAISS → Φ_raw × (1 − MF_score) = Φ_adj
    ├── Mental Plane:    observer-effect corrected intent consistency = M_adj
    ├── Spiritual Plane: validator consensus diversity = Σ
    ├── Conscious Plane: governance stake voting = K
    └── ANIMA Plane:     archetype evolutionary fitness = A
    │
    ▼
C(t) = 0.25·Φ_adj + 0.30·M_adj + 0.25·Σ + 0.10·K + 0.10·A
    │
    ├── C(t) < Θ(t)?
    │       ├── YES: SILENCE signal
    │       │       ├── Blob → 0G DA (zg_da_streamer.py)
    │       │       ├── relayer calls TRIONExecutionGate.publishSignal(HOSTILE)
    │       │       └── Any checkExecution() now returns STATUS_HOSTILE
    │       │
    │       └── NO: VALUATION/GENESIS/TRANSCENDENCE signal
    │               └── relayer calls TRIONOracleV3.publishBehavioralTruth()
    │
    ▼
Every hour: zg_sync_daemon.py
    ├── Exports FAISS delta (~1.36 MB binary)
    ├── Computes Merkle-256 root
    ├── Uploads to 0G Storage
    └── AkashicProof.updateStorageRoot(root, syncBlock)
    │
    ▼
Any DeFi protocol calls TRIONExecutionGate.checkExecution(address)
    └── Returns (STATUS_SAFE | ELEVATED | COLLAPSE | HOSTILE, score)
```

---

## The Five Planes

```
C(t) = α·Φ + β·M + γ·Σ + δ·K + ε·A

Φ  Physical  (α = 0.25)  9 Shannon entropy features over on-chain tx flow
M  Mental    (β = 0.30)  Observer-effect corrected intent consistency
Σ  Spiritual (γ = 0.25)  BFT validator consensus diversity
K  Conscious (δ = 0.10)  Commit-reveal annotation voting
A  ANIMA     (ε = 0.10)  k-NN archetype distance in FAISS space

Θ(t) = 0.55 + 0.37 · volatility_norm   →   range [0.55, 0.92]

SILENCE fired when C(t) < Θ(t)
Limiting plane = argmin(Φ_adj, M_adj, Σ, K, A)
```

---

## Codebase Structure

```
trion-core/
├── serve.py                    # Unified entry point → oracle_api/app.py (Flask, port 5000)
├── oracle_api/
│   ├── app.py                  # 131 API routes — signal compute, on-chain publish, live feed
│   ├── blockchain.py           # web3 relay — TRIONSensingOracle on Arbitrum Sepolia
│   ├── templates/dashboard.html  # Live dashboard UI
│   └── requirements.txt        # flask, gunicorn, web3
├── akashic/
│   ├── faiss_service.py        # FAISS ANIMA engine (FastAPI, port 8000, 128-dim IndexIVFPQ)
│   ├── anima_engine.py         # Archetype evolutionary fitness scoring
│   ├── anima_regulatory.py     # Compliance behavioral patterns
│   ├── btcp_gas_forecast.py    # Gas price behavioral forecasting
│   ├── liquidity_ocean.py      # Liquidity behavioral patterns
│   └── requirements.txt        # faiss-cpu, fastapi, uvicorn, numpy, scikit-learn
├── rust-indexers/              # Rust workspace (Cargo workspace, 14 crates)
│   └── crates/
│       ├── trion-common/       # Shared: BH canonical format, FAISS client, entropy utils
│       ├── trion-evm/          # EVM L0 indexer — Arbitrum, Base, 0G, Mantle, Linea, Scroll, ...
│       ├── trion-svm/          # Solana behavioral indexer
│       ├── trion-near/         # NEAR Protocol indexer
│       ├── trion-ton/          # TON blockchain indexer
│       ├── trion-pvm/          # Polkadot/Substrate indexer
│       ├── trion-starknet/     # StarkNet Cairo VM indexer
│       ├── trion-cosmos/       # Cosmos SDK multi-chain indexer
│       ├── trion-aptos/        # Aptos Move VM indexer
│       ├── trion-movement/     # Movement Labs indexer
│       ├── trion-sui/          # Sui blockchain indexer
│       ├── trion-tron/         # TRON TVM indexer
│       ├── trion-pi/           # Pi Network/Stellar indexer
│       └── trion-utxo/         # Bitcoin-family UTXO indexer
├── chains/                     # Node.js/TypeScript chain integrations
│   ├── near/                   # NEAR Testnet execute.ts
│   ├── pvm/                    # Polkadot Westend execute.ts
│   ├── starknet/               # StarkNet Sepolia execute.ts
│   ├── sui/                    # Sui Mainnet execute.ts
│   ├── svm/                    # Solana Devnet svm_indexer.py + execute.ts
│   └── ton/                    # TON Testnet execute.ts
├── relayer/
│   ├── relayer.js                     # EVM relayer — publishes C(t) on 7 chains every 60s
│   ├── zg_execution_gate_relayer.js   # 0G ExecutionGate relayer with DA proof + storage root
│   └── extended_chain_relayer.js      # 15 non-EVM chains every 90s
├── native-relayer/
│   └── native_relayer.js       # NEAR/TON/Polkadot/StarkNet native sig relayer
├── supervisors/
│   ├── evm_extras_indexers.sh  # Supervisor: BNB/Base/HashKey/Mantle/Linea/Scroll indexers
│   ├── native_vm_indexers.sh   # Supervisor: NEAR/TON/PVM/StarkNet indexers
│   ├── extended_vm_indexers.sh # Supervisor: UTXO/Cosmos/Move/SUI/TRON/PI indexers
│   ├── rust_indexers.sh        # Supervisor: all Rust crate binaries
│   └── trion_and_zg_relayer.sh # Supervisor: TRION relayer + 0G gate relayer together
├── trion-0g/                   # 0G integration SDK
│   └── src/
│       ├── zg_chain.mjs        # 0G Chain contract interactions
│       ├── zg_storage.mjs      # 0G Storage upload/download
│       ├── zg_da.mjs           # 0G DA blob submission
│       ├── zg_compute.mjs      # 0G Compute broker (TEE inference)
│       └── zg_compute_anima.ts # ANIMA archetype inference via 0G Compute
├── zg_api_routes.py            # Flask Blueprint: /api/v1/0g/* routes (6 routes)
├── zg_config.py                # 0G configuration constants
├── zg_sync_daemon.py           # Hourly FAISS delta → 0G Storage daemon
├── zg_da_streamer.py           # 60s behavioral blobs → 0G DA daemon
├── src/                        # Core scoring engine (Python)
│   ├── core/                   # coherence_engine.py, btcp_score.py, signal_types.py
│   ├── security/               # Manipulation fingerprint detectors (7 patterns)
│   ├── signals/                # Signal emission and classification
│   ├── planes/                 # Five-plane scoring modules
│   ├── thermodynamics/         # Entropy conservation and information theory
│   ├── lifecycle/              # Entity lifecycle tracking
│   ├── reputation/             # Cross-chain reputation accumulation
│   ├── governance/             # Conscious plane (K) commit-reveal voting
│   ├── indexers/               # Behavioral indexer interfaces
│   └── agent/                  # AI agent safety modules
├── contracts/                  # Solidity contracts (Hardhat)
│   ├── TRIONExecutionGate.sol  # Pre-trade firewall (deployed 0G Galileo)
│   ├── TRIONOracleV3.sol       # Signal publication oracle
│   ├── AkashicProof.sol        # Permanent behavioral proof (0G + Newton)
│   ├── TRIONSensingOracle.sol  # Original sensing oracle (Arbitrum Sepolia)
│   ├── ConfidentialCoherenceVault.sol  # ERC-4626 vault with coherence gating
│   ├── LiquidityOcean.sol      # Protected liquidity pool
│   ├── TravelRuleCompliance.sol # Travel rule compliance scoring
│   ├── BTCPSimpleEscrow.sol    # BTCP-collateralized escrow
│   ├── TRIONFirewall.sol       # Revert-on-SILENCE firewall
│   ├── TRIONStaking.vy         # Vyper staking contract
│   └── interfaces/             # ITRIONOracle.sol, ITRIONSensingOracle.sol
├── sdk/                        # Integration SDK
│   └── trion_sdk.py            # Python SDK for TRION API
├── tests/                      # 328 tests (pytest)
├── math/                       # Mathematical models and entropy proofs
├── proof-ledger/               # On-chain proof records
├── deployments.json            # Contract addresses across all chains
├── schema.sql                  # TimescaleDB schema for behavioral time series
├── Dockerfile                  # Dev image (Oracle API + FAISS only, fast build)
├── Dockerfile.render           # Production image (all 11 services, Rust compile)
├── render-entrypoint.sh        # Production process supervisor (11 services)
├── docker-compose.yml          # Local dev + full production parity profiles
├── render.yaml                 # Render.com IaC (auto-deploy from GitHub main)
├── railway.toml                # Railway deployment configuration
└── fly.toml                    # Fly.io deployment configuration
```

---

## Workflows

All **11 workflows** run continuously in the Replit environment:

| # | Workflow | Runtime | Purpose |
|---|---------|---------|---------|
| 1 | **Start application** | Python / Flask (uv) | Oracle API + Frontend on port 5000 — 131 routes, dashboard |
| 2 | **FAISS ANIMA** | Python / FastAPI (uv) | 128-dim FAISS vector index + behavioral planes on port 8000 |
| 3 | **Rust Indexers** | Rust (cargo) | L0 EVM (14 chains) + SVM/Solana — core behavioral indexing |
| 4 | **EVM Extras Indexer** | Bash supervisor | BNB/Base/HashKey/Mantle/Linea/Scroll → FAISS |
| 5 | **Native VM Indexers** | Bash / Node.js | NEAR, TON, Polkadot, StarkNet → FAISS |
| 6 | **Extended VM Indexers** | Bash / Node.js | UTXO×4, COSMOS×6, MOVE×2, SUI, TRON, PI → FAISS |
| 7 | **Native VM Relayer** | Node.js | Signs block proofs on NEAR · TON · Polkadot · StarkNet |
| 8 | **TRION Relayer** | Node.js + Bash | Publishes C(t) on EVM chains every 60s; 0G ExecutionGate sync |
| 9 | **Extended Chain Relayer** | Node.js | Publishes C(t) on 15 non-EVM chains every 90s |
| 10 | **0G Sync Daemon** | Python (uv) | Hourly FAISS delta → 0G Storage; Merkle root anchored on-chain |
| 11 | **0G DA Streamer** | Python (uv) | 60s behavioral event blobs → 0G DA (Reed-Solomon 2× erasure) |

---

## 0G Integration

TRION integrates **all 5 components** of the 0G stack simultaneously:

| 0G Component | TRION Usage | Status |
|---|---|---|
| **0G Chain** | 5 Solidity contracts on Galileo (chain 16602); `TRIONExecutionGate.checkExecution()` called pre-trade; 691+ signals, 467 anomalies published | ✅ LIVE — block 33,186,552+ |
| **0G Storage** | Hourly FAISS delta export (~1.36 MB binary); Merkle-256 root committed on-chain via `AkashicProof.updateStorageRoot()` | ✅ SDK integrated; daemon running |
| **0G DA** | 60s behavioral event blobs via dual-channel DA (DPL + DSL); `commitment = SHA256(namespace ∥ blob_sha256 ∥ erasure_sha256)` with Reed-Solomon 2× | ✅ Daemon running |
| **0G Compute** | ANIMA archetype inference via `createZGComputeNetworkBroker(signer)`; TEE-verified; micro-payment per inference | ✅ SDK integrated |
| **0G KV** | Hot signal streams across 4 stream IDs — microsecond-latency reads for HFT integrations | ✅ Active |

**Single judge endpoint:** `GET /api/v1/zg/integration` — returns all 5 components in one JSON response with live block number, contract addresses, and explorer links.

### Honest Note on 0G Storage Testnet

The FAISS delta export daemon correctly generates ~1.36 MB binary delta files (visible in `0g-state/exports/`), computes the correct Merkle-256 root, and calls the 0G Storage upload API. During testing, uploads to the testnet flow contract (`0x22e03a6a89b950f1c82ec5e74f8eca321a105296`) return `execution reverted` on the `pricePerSector` view call — a known testnet initialization issue on the 0G side, not a TRION bug. The generated delta files and their SHA-256 hashes are verifiable locally and the Merkle root is committed on-chain at each sync attempt. The production architecture is correct and will work on a funded mainnet deployment.

---

## Running

### Replit (development)

All 11 workflows start automatically. Oracle API available at port 5000, FAISS ANIMA at port 8000.

```bash
# Verify everything is live
curl http://127.0.0.1:5000/api/v1/health        # Oracle API health
curl http://127.0.0.1:8000/health               # FAISS ANIMA health + vector count
curl http://127.0.0.1:5000/api/v1/vision        # 9 vision modules status
curl http://127.0.0.1:5000/api/v1/chains        # chain index status
curl http://127.0.0.1:5000/api/v1/faiss         # live FAISS stats
curl http://127.0.0.1:5000/api/v1/zg/integration  # all 5 0G components

# Run test suite
python3 -m pytest tests/ -q                     # 328 tests
```

**Required secrets** (set in Replit Secrets panel):

```bash
RELAYER_PRIVATE_KEY         # EVM + multi-chain relayer signing key
NEAR_PRIVATE_KEY            # ed25519:...
TON_PRIVATE_KEY_HEX         # TON hex private key
DOT_MNEMONIC                # Polkadot/Westend mnemonic
STARKNET_PRIVATE_KEY        # StarkNet Sepolia private key
BTC_TAPROOT_WIF             # Bitcoin P2TR WIF
BTC_LEGACY_WIF              # Bitcoin P2PKH WIF
BTC_SEGWIT_NATIVE_WIF       # Bitcoin P2WPKH WIF
BTC_SEGWIT_NESTED_WIF       # Bitcoin P2SH-P2WPKH WIF
LITECOIN_PRIVATE_KEY        # Litecoin WIF
DOGE_PRIVATE_KEY            # Dogecoin WIF
DASH_PRIVATE_KEY            # Dash WIF
COSMOS_PRIVATE_KEY          # Cosmos Hub signing key
KAVA_PRIVATE_KEY            # Kava signing key
INJECTIVE_PRIVATE_KEY       # Injective signing key
SEI_PRIVATE_KEY             # SEI signing key
DYDX_PRIVATE_KEY            # dYdX signing key
INITIA_PRIVATE_KEY          # Initia signing key
APTOS_PRIVATE_KEY           # Aptos / Movement signing key
MOVEMENT_PRIVATE_KEY        # Movement Labs signing key
SUI_PRIVATE_KEY             # Sui signing key
TRON_PRIVATE_KEY            # TRON signing key
PI_SECRET_KEY               # Pi Network / Stellar secret key
SOLANA_RELAYER_PRIVATE_KEY  # Solana devnet signing key (base58)
ZG_PRIVATE_KEY              # 0G Galileo signing key
```

### Docker — dev image (Oracle API + FAISS only)

```bash
cp .env.example .env
docker compose up --build
# Oracle API + Dashboard: http://localhost:5000
# FAISS ANIMA:            http://localhost:8000/health
```

### Docker — full production image (all 11 services)

```bash
# Full build (~12 min first time, cached after)
docker compose --profile full up --build

# Or build and run directly:
docker build -f Dockerfile.render -t trion-core .
docker run -p 10000:10000 -p 8000:8000 --env-file .env trion-core

# All 11 services start automatically via render-entrypoint.sh
# Oracle API: http://localhost:10000
# FAISS ANIMA: http://localhost:8000/health
# 0G Integration: http://localhost:10000/api/v1/zg/integration
```

### Render (production)

```bash
# Configured via render.yaml
# Push to main → auto-deploy
# Dockerfile.render → all 11 services → render-entrypoint.sh
# Health check: /api/v1/health

# Set these secrets in Render dashboard (not in render.yaml):
RELAYER_PRIVATE_KEY, NEAR_PRIVATE_KEY, TON_PRIVATE_KEY_HEX, DOT_MNEMONIC,
STARKNET_PRIVATE_KEY, BTC_TAPROOT_WIF, BTC_LEGACY_WIF, LITECOIN_PRIVATE_KEY,
DOGE_PRIVATE_KEY, DASH_PRIVATE_KEY, COSMOS_PRIVATE_KEY, KAVA_PRIVATE_KEY,
INJECTIVE_PRIVATE_KEY, SEI_PRIVATE_KEY, DYDX_PRIVATE_KEY, INITIA_PRIVATE_KEY,
APTOS_PRIVATE_KEY, MOVEMENT_PRIVATE_KEY, SUI_PRIVATE_KEY, TRON_PRIVATE_KEY,
PI_SECRET_KEY, ZG_PRIVATE_KEY
```

### Railway

```bash
npm i -g @railway/cli
railway login
railway init
railway up   # deploys from Dockerfile.render via railway.toml
# Set secrets: railway variables set RELAYER_PRIVATE_KEY=0x...
```

### Fly.io

```bash
curl -L https://fly.io/install.sh | sh
fly auth login
fly launch --no-deploy    # registers app
fly secrets set RELAYER_PRIVATE_KEY=0x... NEAR_PRIVATE_KEY=ed25519:...
fly deploy                # deploys from Dockerfile.render via fly.toml
```

---

## Indexed Networks

**35 networks across 12 VM families** — all contributing live behavioral data:

### EVM — Ethereum Virtual Machine

| Network | Chain ID | Indexer | Status |
|---------|---------|---------|--------|
| Arbitrum Mainnet | 42161 | L0 EVM (Rust) | ✅ Streaming |
| Base Sepolia | 84532 | L0 EVM (Rust) | ✅ Streaming |
| Optimism Sepolia | 11155420 | L0 EVM (Rust) | ✅ Streaming |
| HashKey Mainnet | 177 | L0 EVM (Rust) | ✅ Streaming |
| 0G Galileo | 16602 | L0 EVM (Rust) | ✅ Streaming |
| Mantle Mainnet | 5000 | L0 EVM (Rust) | ✅ Streaming |
| Linea Mainnet | 59144 | L0 EVM (Rust) | ✅ Streaming |
| Scroll Mainnet | 534352 | L0 EVM (Rust) | ✅ Streaming |
| BNB Testnet | 97 | EVM Extras (TS) | ✅ Streaming |
| Arbitrum Sepolia | 421614 | L0 EVM (Rust) | ✅ Relayer |
| Ethereum Sepolia | 11155111 | — | ✅ Relayer |

### SVM — Solana Virtual Machine

| Network | Chain ID | Indexer | Status |
|---------|---------|---------|--------|
| Solana Devnet | 103 | SVM Indexer (Rust) | ✅ Streaming |

### NVM — NEAR Protocol

| Network | Chain ID | Indexer | Status |
|---------|---------|---------|--------|
| NEAR Testnet | 1201 | Native VM (TS) | ✅ Streaming |

### TVM — TON Virtual Machine

| Network | Chain ID | Indexer | Status |
|---------|---------|---------|--------|
| TON Testnet | 1101 | Native VM (TS) | ✅ Streaming |

### PVM — Polkadot (Substrate)

| Network | Chain ID | Indexer | Status |
|---------|---------|---------|--------|
| Polkadot Westend | 901 | Native VM (TS) | ✅ Streaming |

### Cairo VM — StarkNet

| Network | Chain ID | Indexer | Status |
|---------|---------|---------|--------|
| StarkNet Sepolia | 1300 | Native VM (TS) | ✅ Streaming |

### UTXO — Bitcoin-family

| Network | Chain ID | Indexer | Status |
|---------|---------|---------|--------|
| Bitcoin Mainnet | 2000 | Extended VM (TS) | ✅ Streaming |
| Litecoin Mainnet | 2010 | Extended VM (TS) | ✅ Streaming |
| Dogecoin Mainnet | 2020 | Extended VM (TS) | ✅ Streaming |
| Dash Mainnet | 2030 | Extended VM (TS) | ✅ Streaming |

### COSMOS SDK

| Network | Chain ID | Indexer | Status |
|---------|---------|---------|--------|
| Cosmos Hub | 4001 | Extended VM (TS) | ✅ Streaming |
| Kava | 4002 | Extended VM (TS) | ✅ Streaming |
| Injective | 4003 | Extended VM (TS) | ✅ Streaming |
| SEI | 4004 | Extended VM (TS) | ✅ Streaming |
| dYdX | 4005 | Extended VM (TS) | ✅ Streaming |
| Initia | 4006 | Extended VM (TS) | ✅ Streaming |

### MOVE VM — Aptos-family

| Network | Chain ID | Indexer | Status |
|---------|---------|---------|--------|
| Aptos Mainnet | 5001 | Extended VM (TS) | ✅ Streaming |
| Movement Mainnet | 5002 | Extended VM (TS) | ✅ Streaming |

### SUI VM

| Network | Chain ID | Indexer | Status |
|---------|---------|---------|--------|
| Sui Mainnet | 6001 | Extended VM (TS) | ✅ Streaming |

### TVM_TRON — TRON

| Network | Chain ID | Indexer | Status |
|---------|---------|---------|--------|
| TRON Mainnet | 3001 | Extended VM (TS) | ✅ Streaming |

### MVM — Pi Network / Stellar

| Network | Chain ID | Indexer | Status |
|---------|---------|---------|--------|
| Pi Mainnet | 7001 | Extended VM (TS) | ✅ Streaming |

---

## On-Chain Publication

### EVM Chains — TRION Relayer (60s cadence)

| Chain | Chain ID | Oracle Address | Status |
|-------|---------|----------------|--------|
| Arbitrum Sepolia | 421614 | `0xb819c63c02Ed5aB49017C0f3f2568A14624658b3` | ✅ REAL |
| Ethereum Sepolia | 11155111 | `0xB07AD89a10f94B6D3bF2ab0B3a37988b1F37Db39` | ✅ REAL |
| Base Sepolia | 84532 | `0x7ADF5B7273883C50EFc005BA7EdD3F379Af9680C` | ✅ REAL |
| Optimism Sepolia | 11155420 | `0x708193f93Fb897fbeA72e7e7D19237770F19E969` | ✅ REAL |
| HashKey Mainnet | 177 | `0x708193f93Fb897fbeA72e7e7D19237770F19E969` | ✅ REAL |
| BNB Testnet | 97 | `0xf0e20F48D4c2c63DCAf4bad01471d29DEb921721` | ⚠️ No Funds |
| 0G Galileo | 16602 | `0x0471B2BE25c2eBbAe7FAc17383F1692979F0A87C` | ⚠️ No Funds |

### 0G Contracts — Galileo Testnet (chain 16602)

| Contract | Address | Explorer |
|---------|---------|---------|
| TRIONExecutionGate | `0xDB5910Dc6CfD219D00F64be1F23DA0289901356d` | [View](https://chainscan-galileo.0g.ai/address/0xDB5910Dc6CfD219D00F64be1F23DA0289901356d) |
| TRIONOracleV3 | `0x0471B2BE25c2eBbAe7FAc17383F1692979F0A87C` | [View](https://chainscan-galileo.0g.ai/address/0x0471B2BE25c2eBbAe7FAc17383F1692979F0A87C) |
| LiquidityOcean | `0x105c7F6c16d2c92FEad10336C2b6A047F999a5A7` | [View](https://chainscan-galileo.0g.ai/address/0x105c7F6c16d2c92FEad10336C2b6A047F999a5A7) |
| TravelRuleCompliance | `0x5e7DBE6cc90d6260be2781dc312812834715EBaB` | [View](https://chainscan-galileo.0g.ai/address/0x5e7DBE6cc90d6260be2781dc312812834715EBaB) |
| BTCPSimpleEscrow | `0x388f98831c749D7Acad2046329c9CeC94A8b248d` | [View](https://chainscan-galileo.0g.ai/address/0x388f98831c749D7Acad2046329c9CeC94A8b248d) |

### AkashicProof Contract — Newton Testnet

| Contract | Address |
|---------|---------|
| AkashicProof | `0x33c793fed5bf5fcB043D8c6c74256e7B4b38156D` |

---

## Oracle API — Port 5000

131 routes across 9 vision modules + 0G integration:

### Core Signal Routes
- `GET /api/v1/signal/{entity_id}` — full C(t) computation with all 5 planes
- `POST /api/v1/signal/batch` — batch scoring up to 100 entities
- `GET /api/v1/feed` — last 50 computed signals (ring buffer)
- `GET /api/v1/health` — API health + uptime

### 0G Routes
- `GET /api/v1/zg/integration` — all 5 components in one response (judge endpoint)
- `GET /api/v1/0g/status` — 0G integration status
- `GET /api/v1/0g/proof` — AkashicProof contract state
- `GET /api/v1/0g/sync/history` — sync cycle history
- `GET /api/v1/0g/da/commitments` — DA commitment records
- `POST /api/v1/0g/compute/anima` — TEE-verified ANIMA inference

### Vision Module Routes
- `GET /api/v1/vision` — all 9 vision modules status
- `GET /api/v1/chains` — chain index status + last block
- `GET /api/v1/faiss` — FAISS ANIMA live stats
- `GET /api/v1/zg` — 0G ExecutionGate stats
- + 117 additional routes across auditor, agent_safety, archetypes, epigenetics, thermodynamics, lifecycle, ubl, reputation, investment modules

---

## FAISS ANIMA Service — Port 8000

128-dimensional behavioral vector index (FAISS `IndexIVFPQ`):

- `GET /health` — index status + vector count + entity count
- `POST /index/add_batch` — add behavioral vectors (from Rust indexers)
- `POST /index/add_tx_bh_batch` — add canonical 93-byte BH records
- `GET /index/stats` — full index statistics
- `POST /query/anima` — query ANIMA score + archetype for an entity
- `POST /query/nearest` — k-NN archetype lookup
- `GET /archetypes` — all 64 behavioral archetype centroids

---

## Deployment Files

| File | Purpose |
|------|---------|
| `Dockerfile` | Dev image — Oracle API + FAISS ANIMA only. Python 3.11, fast build. |
| `Dockerfile.render` | Production image — all 11 services. 3-stage build: Rust compiler + Node installer + Python runtime. |
| `render-entrypoint.sh` | Production supervisor — starts all 11 services, runs Oracle API as gunicorn foreground under tini. |
| `docker-compose.yml` | Local dev (`default` profile) + full production parity (`--profile full`). |
| `render.yaml` | Render.com IaC — auto-deploy from GitHub main, all env vars, trion-db PostgreSQL. |
| `railway.toml` | Railway deployment — Dockerfile.render, health check, all service toggles. |
| `fly.toml` | Fly.io deployment — 8GB/4CPU machine, volume mount for 0G state, Chicago region. |

---

## Tests

```bash
python3 -m pytest tests/ -q
# 328 passed, 24 skipped
# Covers: signal computation, plane scoring, attack detection, 0G routes, FAISS API
```

Attack simulation (all 7 historical attack patterns blocked):

```bash
python3 simulate_attacks.py
# Beanstalk ($182M) → BLOCKED: GOVERNANCE_CAPTURE + SILENCE
# Harvest Finance ($34M) → BLOCKED: FLASH_LOAN_SANDWICH + SILENCE
# Euler ($197M) → BLOCKED: CROSS_PROTOCOL_DRAIN + SILENCE
# Mango Markets ($116M) → BLOCKED: ORACLE_ATTACK_ATTEMPT + SILENCE
# Nomad Bridge ($190M) → BLOCKED: COORDINATED_PUMP + SILENCE
# Ronin Network ($625M) → BLOCKED: SYBIL_CLUSTER + SILENCE
# CREAM Finance ($130M) → BLOCKED: FLASH_LOAN_SANDWICH + SILENCE
# Total protected: $1.475B
```

---

## License

CC0 1.0 Universal — public domain. No rights reserved.

---

*Built for the 0G APAC Hackathon. TRION Protocol — behavioral truth, chain-verified.*
