# TRION Protocol — Architecture Overview

## System Architecture

TRION Protocol implements a five-plane behavioral coherence engine that
computes a single coherence signal C(t) from on-chain and off-chain data.

```
                    ┌─────────────────────────────────┐
                    │        EXTERNAL DATA SOURCES     │
                    │  Chain RPCs · News · Social ·   │
                    │  Sensors · Validator Network    │
                    └───────────────┬─────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│   TWO INGESTION PATHS (one live path per deploy profile):        │
│   bh_streamer 96 workers (60 EVM + 36 non-EVM) → SQLite ledger   │
│   Rust L0 indexers: 21 crates + trion-common (40 integrated)     │
│  ┌─────────────┐  ┌─────────────┐  ┌────────────────────────────┐ │
│  │  Chain RPC  │  │ BH Pipeline │  │ Off-chain NLP · Sensors    │ │
│  └──────┬──────┘  └──────┬──────┘  └────────────┬───────────────┘ │
└─────────┼────────────────┼────────────────────────┼─────────────────┘
          │                │                        │
          ▼                ▼                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     FIVE BEHAVIORAL PLANES                         │
│                                                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌────────────────────────────┐ │
│  │  Φ Physical │  │  M Mental   │  │      Σ Spiritual           │ │
│  │  9 Shannon  │  │  Prediction │  │  Diversity-Weighted BFT    │ │
│  │  entropy    │  │  confidence │  │  fleet: external gate     │ │
│  └─────────────┘  └─────────────┘  └────────────────────────────┘ │
│                                                                     │
│  ┌─────────────┐  ┌─────────────┐                                    │
│  │ K Conscious │  │  A ANIMA    │                                    │
│  │  Human      │  │  Cross-     │                                    │
│  │  annotation │  │  domain AI  │                                    │
│  └─────────────┘  └─────────────┘                                    │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   COHERENCE ENGINE C(t)                            │
│                                                                     │
│  C(t) = α·Φ_adj(t) + β·M_adj(t) + γ·Σ(t) + δ·K(t) + ε·A(t)         │
│                                                                     │
│  Dynamic Threshold: Θ(t) = Θ_min + (Θ_max-Θ_min)·V(t)              │
│  Moat Factor:     M_moat = e^(D·Q·R·X·F·N)                         │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
            ┌──────────────┴──────────────┐
            ▼                             ▼
┌─────────────────────┐       ┌─────────────────────┐
│  Coherent? C ≥ Θ    │       │  Master Equation    │
│  → Emit signal      │       │  T(t) = [C≥Θ]·C·e^M │
│  → SILENCE if not   │       │                     │
│  → AWA freeze: 503  │       └──────────┬──────────┘
│    silence:true     │                  │
└─────────┬───────────┘                  │
          │                              │
          │                              ▼
┌─────────┴───────────────────────────────┐
│ CANONICAL CERTIFICATE (346 bytes)       │
│ per-epoch registry · weight quorum      │
│ (w_j = s_j·d_j) · fail-closed ·         │
│ nonces + consumed-cert replay guards    │
│ TTL seconds · HHI 4000 critical         │
└─────────┬───────────────────────────────┘
          │
┌─────────────────────────────────────────────────────────────────────┐
│                   OUTPUT & APPLICATION LAYERS                      │
│                                                                     │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────────────┐ │
│  │  On-Chain    │ │  BTCP Cross- │ │   Frontend Dashboard         │ │
│  │  Publishing  │ │  Chain Router│ │   (Next.js · React 19)       │ │
│  │  (Solidity)  │ │ (ZK + VMs)   │ │   Real-time plane data      │ │
│  └──────────────┘ └──────┬───────┘ └──────────────────────────────┘ │
│                         │                                            │
│                         ▼                                            │
│                  ┌──────────────────┐                                │
│                  │  6 VM Adapters   │                                │
│                  │  EVM · SVM ·     │                                │
│                  │  Cosmos · Move · │                                │
│                  │  CosmWasm · OOA  │                                │
│                  │  (registry: 18    │                                │
│                  │   VM families)    │                                │
│                  └──────────────────┘                                │
└─────────────────────────────────────────────────────────────────────┘
```

## Component Deep Dive

### 1. Five Behavioral Planes

#### Physical Plane Φ(t)
Nine Shannon entropy features computed from transaction patterns:
- f₁: Volume distribution
- f₂: Counterparty diversity
- f₃: Temporal spacing
- f₄: Contract entropy
- f₅: Value flow
- f₆: Wallet architecture
- f₇: Cross-protocol activity
- f₈: Gas pattern analysis
- f₉: MEV interaction

**Output**: Φ ∈ [0,1] — higher = more organic, less manipulated

#### Mental Plane M(t)
Prediction confidence based on behavioral archetype matching:
- FAISS vector similarity to 64 trained archetypes
- Observer effect correction
- Prediction interval computation

**Output**: M ∈ [0,1] — higher = more predictable behavior

#### Spiritual Plane Σ(t)
Diversity-weighted Byzantine Fault Tolerance:
```
Σ(t) = Σⱼ[sⱼ·dⱼ·1(|vⱼ-v̄|≤δ(t))] / Σⱼ[sⱼ·dⱼ]
```
- dⱼ = 1 - correlation(Mⱼ, M̄) — validator diversity
- δ(t) = δ_base × (1 + V(t)) — dynamic tolerance

**Output**: Σ ∈ [0,1] — higher = stronger validator consensus

#### Conscious Plane K(t)
Human annotation network with anti-capture protections:
- 5 annotators per review, 3/5 majority
- Commit-reveal voting prevents herding
- 6 Anti-Capture Protections (ACP1-ACP6)
- 12-month pseudonymous terms

**Output**: K ∈ [0,1] — higher = more human-verified

#### ANIMA Plane A(t)
Cross-domain intelligence absorption:
- PCR: Pattern Completion Ratio
- HA: Human Alignment
- CA: Cultural Alignment
- Akashic depth weighting

**Output**: A ∈ [0,1] — higher = more cross-domain intelligence

### 2. Coherence Engine

Combines all five planes with dynamic weights:
```
C(t) = α·Φ_adj(t) + β·M_adj(t) + γ·Σ(t) + δ·K(t) + ε·A(t)
```

**Weight Profiles**: DEFAULT, NEW_TOKEN, MATURE_PROTOCOL, STABLECOIN,
GOVERNANCE_TOKEN, BRIDGE_ASSET, WRAPPED_ASSET, SPEED, INTELLIGENCE,
CERTAINTY, FULL_SPECTRUM

**Signal Emission Rule**: Signal emitted if and only if C(t) ≥ Θ(t)

### 3. Master Equation

Final output signal with moat amplification:
```
T(t) = [C ≥ Θ] · C(t) · e^(M_moat)
```

Moat factors: D_data · Q_quality · R_reflexivity · X_crosschain · F_falsifiability · N_network

### 4. BTCP Cross-Chain Protocol

#### ZK Privacy Circuits
1. **Intent Commitment** — Prove intent exists without revealing details
2. **Complementarity** — Prove HashDNA dual-strand validity
3. **Behavioral Credential** — Prove entity passes thresholds
4. **Travel Rule** — Prove compliance without revealing counterparties
5. **IAP Share Proof** — Prove fair gas allocation

#### VM Adapters
| Adapter | Chains | Encoding |
|---------|--------|----------|
| EVM | Ethereum, Arbitrum, Optimism, Polygon, BSC, Base | ABI calldata |
| SVM | Solana | Borsh instruction |
| Cosmos | Cosmos Hub, Osmosis, Celestia | Protobuf |
| Move | Aptos, Sui | BCS |
| CosmWasm | Juno, Terra | WASM ExecuteMsg |
| OOA | Fuel | Object-centric |

#### Six-Step BTCP Execution
1. Intent registration + BIBL analysis
2. Optimal route computation
3. Cross-chain proof construction (ZK)
4. VM translation layer encoding
5. Gas sharing protocol (IAP)
6. Finality + Akashic recording

### 5. Security Components

#### Genomic Key
- Dual-strand HashDNA (sense/antisense)
- Lineage depth tracking
- Contamination detection
- Evolution every 100 blocks

#### Living Security
```
SEC_effective = LSS × PQC × CC
```
- LSS: Living Security Score
- PQC: Post-Quantum Cryptography layer
- CC: Coherence Confidence

#### Chameleon Protocol
- Adaptive noise injection
- Probe detection and escalation
- Noise sigma: 0.002 (normal) → 0.025 (adversarial)
- Escalation factor: 2.5×

#### Coordination Collapse Theorem
- Byzantine resistance via diversity weighting
- Collapse bound computation
- Attack simulation framework

### 6. Data Layer

#### FAISS Akashic Index
- 128-dimensional behavioral vectors
- Runtime-dependent state (verify live via `GET :8000/stats`; dev observations:
  ~980 vectors, 16 entities, 64 archetypes, 99.69% archetype coverage)
- L2 distance metric

#### Storage dispositions (honest, Wave 3)
`schema.sql` declares 35 tables, each with an `operative-writer` disposition:
12 operative sqlite-mirror tables (BTCP routes/intents/escrows/clipboard/BLOs/
shadow/genesis + consumed-certificate and certificate-conflict guards — written
atomically at orchestrator step 6), 6 deploy-gated TimescaleDB dual-write tables,
and 17 honestly marked `NONE` (no in-tree writer). The operative in-tree store is
the SQLite mirror + BH ledger; TimescaleDB is deploy-gated.

#### BIBL Engine
- Mempool pattern classification
- Chain memory signal computation
- Cross-chain health assessment
- Batch opportunity detection
- MEV opportunity detection

### 7. Consensus & Settlement Verification (Waves 1–3)

Every VM tier (EVM/Solidity+Vyper, Solana, Move, TON, NEAR, Starknet/Cairo,
PVM-as-research) verifies the **346-byte canonical certificate** against a
**per-epoch validator registry** with **weight quorum** — full contract:
`docs/protocol/CANONICAL_CERTIFICATE.md`; invariant register:
`docs/security/CANONICAL_INVARIANTS.md`.

- Effective power `w_j = s_j · d_j` recomputed from the registered epoch set
  (envelope weights are claims, not authority); the L4.2 tier table sets the
  required quorum (2/3 strict / 3/4 / 17/20 by validator diversity D_consensus).
- Fail-closed verification (no oracle fallback, no partial acceptance);
  forward-only epoch registration (init-takeover guard).
- Replay protection: strictly-increasing per-scope nonces + consumed-certificate
  tracking (on-chain mappings + store guards) + equivocation evidence → slashing.
- Freshness: value-tier TTL in seconds (1h/24h/3d/7d); `hhi_at_emission > 4000`
  ⇒ INVALID (HHI CRITICAL).
- Emission gate: AWA (Anti-Weaponization Architecture, MD §17) six-condition set;
  `EmissionGate` singleton (`core/governance/awa.py`) — no unfreeze API; frozen ⇒
  `/api/v1/publish` 503 `silence:true`, no chain write.

**External/honest labels:** live validator fleet = operational gate (see
`docs/MAINNET_RUNBOOK.md`); Go components = external toolchain (static-audited
here, built in CI); PQC = optional external crypto libs; PVM `legacy_oracle` =
research reference, not an oracle of record; ZK circuits = software simulation
(Circom sources ship without zkeys or proofs).

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Core Engine | Python 3.10, NumPy, SciPy |
| API Server | Flask, Gunicorn (282 routes; X-API-Key write auth) |
| Akashic Index | FAISS, FastAPI |
| Smart Contracts | Solidity 0.8+, Vyper (+ Cairo, Move, FunC, ink!, CosmWasm, Soroban) |
| Validator Network | Go, P2P gossip (external toolchain — static-audited in this repo, build in CI) |
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS 4 |
| ZK Proofs | Python-native (SHA3 + Merkle) simulation; Circom circuits ship WITHOUT zkeys/proofs (research) |
| Deployment | Docker, systemd, Nginx |
| Monitoring | Prometheus, Grafana (metric-less today — honest notes in DEPLOYMENT.md) |

## Configuration Parameters

### Key Thresholds
| Parameter | Value | Purpose |
|-----------|-------|---------|
| Θ_min | 0.55 | Minimum coherence threshold |
| Θ_max | 0.92 | Maximum coherence threshold |
| Σ_bootstrap | 0.25 | Fallback when <10 validators |
| K_bootstrap | 0.10 | Fallback when annotations scarce |
| A_bootstrap | 0.28 | Fallback when depth < D_min |
| D_minimum | 10,000 | Minimum depth for full ANIMA |

### Manipulation Detection
| Attack Type | Threshold |
|-------------|-----------|
| Oracle attack | 0.15 |
| Wash trading | 0.60 |
| Coordinated pump | 0.80 |
| Sybil liquidity | 0.80 |
| Governance capture | 4,000 |
| MEV extraction | 0.005 |
| Fake volume spike | 10.0× |

## Deployment Sizing

### Minimum Production
- **CPU**: 4 cores
- **RAM**: 8 GB
- **Disk**: 100 GB SSD
- **Network**: 1 Gbps

### Recommended Production
- **CPU**: 8-16 cores
- **RAM**: 16-32 GB
- **Disk**: 500 GB NVMe SSD
- **Network**: 10 Gbps

### Large Scale (>1M entities)
- **CPU**: 32+ cores
- **RAM**: 64-128 GB
- **Disk**: 2 TB NVMe SSD
- **GPU**: NVIDIA A100 for FAISS
- **Network**: 25 Gbps

---

*TRION Protocol v2.0.0 — Architecture Specification*
*Based on whitepaper V1 + BTCP Master Implementation Spec; conformance layer
reconstructed Waves 1–3 (canonical docs in `docs/protocol/`, `docs/security/`,
`docs/audit/CANONICAL_SPEC_MATRIX.md`)*
