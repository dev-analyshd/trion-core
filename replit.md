# TRION Protocol — Behavioral Truth Oracle

**Author & Originator**: Hudu Yusuf (Analys) | CC0 — This knowledge belongs to everyone
**Whitepaper**: V1.0 (complete) + v0.3 + v0.4 (extended) | February 2026

---

## What Is TRION

TRION is a multi-chain behavioral truth oracle. Where Chainlink/Pyth/Band aggregate CEX prices and deliver them on-chain faster — faster pipes carrying the same compromised water — TRION derives truth from the actual record of what every entity did on every chain, stripped of manipulation, weighted by coherence, bounded by liquidity health.

**The Inverted Truth Hierarchy**: Layer 4 Retail → Layer 3 DeFi → Layer 2 Oracles (band-aid) → Layer 1 CEX (root corruption) → **TRION Layer 0: behavioral ground truth**.

It provides cryptographically verified behavioral signals for: DeFi security, manipulation detection, liquidity health, pre-execution checks, contract auditing, investment signals, entity reputation, and AI agent safety validation.

---

## Current System Status

| Metric | Value |
|--------|-------|
| **API routes** | 139 (Flask) + 122 (FAISS FastAPI) |
| **Whitepaper formulas** | **84 — all LIVE (100% coverage)** |
| **Chains indexed** | **37** (35 mainnet + 2 testnet) |
| **Rust L0 crates** | **13** (trion-common + 12 chain crates) |
| **Active workflows** | 8 |
| **Test results** | 328 passing, 24 skipped |
| **BH per-tx pipeline** | Live on all 37 chains |
| **FAISS vectors** | 11,000–15,000+ (grows continuously) |
| **Signal types** | 19 |
| **Living Security components** | 8 DNA-mimetic |
| **Languages implemented** | 7 (whitepaper Part 11 compliance) |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  User / DeFi Protocol / AI Agent                        │
└────────────────────┬────────────────────────────────────┘
                     │ REST / WebSocket
┌────────────────────▼────────────────────────────────────┐
│  Oracle API  —  oracle_api/app.py  (Flask, port 5000)   │
│  139 endpoints • dashboard • SDK spec • BTV engine      │
└──────────┬──────────────────────────┬───────────────────┘
           │ proxy                    │ proxy
┌──────────▼──────────┐   ┌──────────▼──────────────────┐
│  FAISS ANIMA        │   │  src/ Python Engine          │
│  akashic/           │   │  55+ behavioral modules      │
│  FastAPI, port 8000 │   │  L0–L10 whitepaper formulas  │
│  128-dim vectors    │   │  coherence • MF • BTV • BFT  │
└──────────┬──────────┘   └─────────────────────────────┘
           │ add_batch / add_tx_bh_batch
┌──────────▼────────────────────────────────────────────┐
│  L0 Rust Indexers  —  rust-indexers/crates/           │
│  13 binaries • per-tx canonical BH • 37 chains       │
│  trion-evm (14 EVM) • trion-svm • trion-near         │
│  trion-ton • trion-cosmos • trion-aptos • trion-sui  │
│  trion-tron • trion-utxo • trion-starknet • trion-pi │
│  trion-pvm • trion-movement                          │
└──────────────────────────────────────────────────────┘
           │ publish signals
┌──────────▼────────────────────────────────────────────┐
│  Relayers — EVM + Native VM + Extended Chains         │
│  relayer/ (Node.js, 12 EVM mainnet + testnets)       │
│  native-relayer/ → chains/*/execute.ts               │
│  extended_chain_relayer.js (15 non-EVM)              │
│  0G ExecutionGate (Galileo testnet)                  │
└──────────────────────────────────────────────────────┘
```

---

## Five Behavioral Planes

| Plane | Symbol | What It Measures |
|-------|--------|-----------------|
| Physical | Φ | On-chain behavioral entropy — tx patterns, velocity, MEV, liquidity |
| Mental | M | Predictive accuracy, Genesis Inference, valuation coherence |
| Spiritual | Σ | Validator consensus quality, BFT diversity, coordination resistance |
| Conscious | K | Human annotation, governance participation, Elder Wisdom |
| ANIMA | A | Pre-manifestation signals — off-chain narrative, sentiment, intent |

**Five-plane coherence**: `C(t) = α·Φ + β·M + γ·Σ + δ·K + ε·A` — weighted sum across all planes.
**Emission condition**: signal emits only when `C(t) ≥ Θ(t)`. Below threshold: Structured Silence.

---

## Whitepaper Formula Coverage — 84 Formulas, 100% LIVE

### L0 — Behavioral Foundation
| ID | Formula | Endpoint |
|----|---------|---------|
| L0.1 | Canonical BH: `entity(32)\|\|event(1)\|\|mag(8)\|\|ctx(8)\|\|ts(8)\|\|chain(4)\|\|block_hash(32)` | `/api/v1/bh/<id>` |
| L0.2 | Dual-strand: `sense=SHA3(payload\|\|0x00)`, `antisense=SHA3(payload\|\|0xFF)⊕NOT(sense)` | `/api/v1/bh/<id>` |
| L0.3 | Shannon entropy: `H(X) = -Σ p(xᵢ)·log₂p(xᵢ)` | `/api/v1/entropy/<id>` |
| L0.4 | Magnitude norm: `M_norm = log₁₀(USD+1) / log₁₀(max_90d+1)` | `/api/v1/bh` (POST) |
| L0.5 | Moat: `M_moat = D·Q·R·X·F·N` (6-factor multiplicative) | `/api/v1/moat` |
| L0.6 | Akashic depth: `D(t) = Σ BH_count × chain_weight` | `/api/v1/trion/<id>` |
| L0.7 | BTV: `BTV = P_ref × Ω × (1−MF_discount) × C_weight × NL_weight` | `/api/v1/price/btv/<base>` |
| L0.8 | Inverted Truth Hierarchy: Layer 0–4 manipulation discount table | `/api/v1/price/hierarchy` |

### L1 — Physical Plane
| ID | Formula | Endpoint |
|----|---------|---------|
| L1.1 | `Φ(t) = w₁f₁ + w₂f₂ + ... + w₉f₉` (9 Shannon entropy features) | `/api/v1/signal/<id>` |
| L1.2 | MF score: `MF(e,t) = max(WASH,SYBIL,GOV_CAPTURE,MEV,PUMP,FAKE_VOL)` | `/api/v1/security/<id>/mf` |
| L1.3 | Temporal coherence: `TC(t) = 1 − maxᵢ(\|t_plane_i − t_ref\|) / TTL_min` | `/api/v1/signal/<id>` |
| L1.4 | Natural liquidity: `NL = LD·LO·LC·LS` | `/api/v1/liquidity/<asset>` |
| H1 | Homomorphic Mapping: `H: Dₐ→U`, `rel(e₁,e₂) in A ≅ rel(H(e₁),H(e₂)) in U` | `/api/v1/homomorphic/<chain>/<id>` |
| H1-AL | Adaptive Layer: `t_canonical=t+Δf(A)`, `f_norm=(f_raw−μ)/σ`, `w_A=1−e^(−λ·T)` | `/api/v1/homomorphic/adaptive_layer` |

### L2 — Manipulation Fingerprints (6 patterns)
| ID | Formula | Endpoint |
|----|---------|---------|
| L2.1 | WASH: `0.70 × cyclic_flow_ratio` (threshold >0.60, counterparties <5) | `/api/v1/security/<id>/mf` |
| L2.2 | SYBIL: `0.60 × funding_concentration` | `/api/v1/security/<id>/mf` |
| L2.3 | GOV_CAPTURE: `0.50 × (HHI−2500)/7500` | `/api/v1/security/<id>/mf` |
| L2.4 | MEV: `0.40 × (rate−0.005)/0.045` | `/api/v1/security/<id>/mf` |
| L2.5 | PUMP: `0.85 × sync_buy_ratio` | `/api/v1/security/<id>/mf` |
| L2.6 | FAKE_VOL: `0.80 × (1 − vol_entropy/H_baseline)` | `/api/v1/security/<id>/mf` |

### L3 — Mental Plane
| ID | Formula | Endpoint |
|----|---------|---------|
| L3.1 | Genesis Inference: `conf_genesis = 1 − e^(−0.001·D)` | `/api/v1/genesis/<asset>` |
| L3.2 | Observer Effect: `OE_factor = corr(signal_pub(t-1), behavioral_change(t))` | `/api/v1/signal/<id>` |
| L3.3 | M_adj: `M_adj(t) = M_base(t) × (1 − OE_factor(t))` | `/api/v1/signal/<id>` |
| L3.4 | Predictive limit: `PC_limit(t) = 1 − H_irreducible / H(future)` | `/api/v1/predictive_limit` |
| L3.5 | Manifestation Gap: `MG(S,t) = B_predicted(t) − B_observed(t)` | `/api/v1/manifestation_gap/<id>` |

### L4 — Spiritual Plane / Diversity-Weighted BFT
| ID | Formula | Endpoint |
|----|---------|---------|
| L4.1 | Diversity weight: `d_j = 1 − corr(M_j, M̄)` | `/api/v1/dw_bft` |
| L4.2 | Σ(t): `Σⱼ[sⱼ·dⱼ·𝟙(\|vⱼ−v̄\|≤δ)] / Σⱼ[sⱼ·dⱼ]` | `/api/v1/dw_bft` |
| L4.3 | BFT safety: `Σ_honest sⱼ·dⱼ > (2/3)·Σ_all sⱼ·dⱼ`; `lim_{coord→1} Σ_Byz sⱼ·dⱼ = 0` | `/api/v1/dw_bft` |
| L4.4 | Validator credibility: `CRED(s,t) = CRED(s,t-1)·α + events·β` | `/api/v1/validator/credibility/<id>` |

### L5 — Resonance Threshold
| ID | Formula | Endpoint |
|----|---------|---------|
| L5.1 | Dynamic threshold: `Θ(t) = Θ_min + (Θ_max − Θ_min)·V(t)` | `/api/v1/signal/<id>` |
| L5.2 | Five-plane coherence: `C(t) = α·Φ + β·M + γ·Σ + δ·K + ε·A` | `/api/v1/signal/<id>` |
| L5.3 | Coherence trend: slope over 20-point rolling C(t) history (RISING/FALLING/STABLE) | `/api/v1/signal/<id>` |
| L5.4 | Structured Silence: `Gap = Θ(t)−C(t)`, limiting_plane, ETA to threshold | `/api/v1/silence/<id>` |
| L5.5 | Complete TRIONSignal object (34 fields incl. genomic_signature, CI_95, TTL) | `/api/v1/signal/<id>` |

### L6 — Living Security System
| ID | Formula | Endpoint |
|----|---------|---------|
| L6.1 | GK evolution: `GK(t) = Hash_DNA(GK(t-1) \|\| BE(t) \|\| TM(t) \|\| CV(t))` | `/api/v1/security/<id>/genomic` |
| L6.2 | Complementary strand XOR invariant: `sense XOR antisense = NOT(SHA3(payload\|\|0xFF))` | `/api/v1/immune/<id>` |
| L6.3 | SEC: `SEC(t) = LSS(t) · PQC(t) · CC(t)` (PQC=Kyber+Dilithium+SPHINCS+) | `/api/v1/immune/<id>` |
| L6.4 | Quantum resistance: `K(H(TRION,t)) ≥ Ω(t · N_chains · N_val · H_env)` | `/api/v1/immune/<id>` |
| L6.5 | P(break LSS): monotonically decreasing via Kolmogorov complexity bound | `/api/v1/immune/<id>` |
| L6.6 | Epigenetic state: `EL = f(threat_level, validator_health, network_entropy)` (4 states) | `/api/v1/immune/<id>` |
| L6.7 | CRISPR defense: 8 known DeFi attack signatures with adaptive library | `/api/v1/immune/<id>` |
| L6.8 | Mitochondrial integrity: independent protocol DNA, 2nd auth layer | `/api/v1/immune/<id>` |
| L6.9 | Bootstrap decay: `w(D) = e^(−0.0001·D)` → fully live at D≈50000 | `/api/v1/immune/<id>` |
| L6.10 | Genetic recombination: all security params re-derived from history every 24h | `/api/v1/immune/<id>` |
| L6.11 | Chameleon Protocol: `output = T_true + ε(σ)`, σ escalates on probing | `/api/v1/chameleon/<id>` |

### L7 — Signal Types (19 total)
All 19 signal types live: VALUATION, SILENCE, MANIPULATION_ALERT, LIQUIDITY_HEALTH, CROSS_CHAIN_COHERENCE, GOVERNANCE_SIGNAL, SYSTEMIC_RISK, MEV_EXPOSURE, INSTITUTIONAL_BHV, REGULATORY_BHV, ECOSYSTEM_HEALTH, BOOTSTRAP, PRE_MANIFESTATION, FORK_RESOLUTION, RESURRECTION, ARBITRAGE_OPPORTUNITY, STABLECOIN_HEALTH, SMART_CONTRACT_RISK, AGENT_SAFETY — endpoints at `/api/v1/signal/type/<type>/<id>`

### L8 — Ecosystem & Governance
| ID | Formula | Endpoint |
|----|---------|---------|
| L8.1 | SBA: `SBA = 0.30·E + 0.25·I + 0.20·S + 0.15·G + 0.10·C` | `/api/v1/sba/<nation_id>` |
| L8.2 | XSL: `XSL = TV·FS·RR/(1+TP)` (KEYSTONE/BRIDGE/ISOLATED tiers) | `/api/v1/xsl/<id>` |
| L8.3 | AWA state machine: 4 conditions for Adjusted Weighted Allocation | `/api/v1/governance/awa` |
| L8.4 | Gratitude Protocol: `G(t) = G(t-1) × 0.95` weekly decay | `/api/v1/governance/gratitude` |
| L8.5 | Bootstrap Protocol: `BRT = e^(−0.0001·D)` | `/api/v1/bootstrap/status` |
| L8.6 | Falsifiability Registry: 15 conditions with live status | `/api/v1/governance/falsifiability` |
| F1–F15 | All 15 falsifiability conditions tracked live | `/api/v1/governance/falsifiability` |

### L9 — Cross-Chain & Provenance
| ID | Formula | Endpoint |
|----|---------|---------|
| L9.1 | BEO weights: `BEO = 0.40·w_CF + 0.25·w_ST + 0.25·w_SC + 0.10·w_BP` | `/api/v1/trion/<id>` |
| L9.2 | Source credibility: `CRED(s,t) = CRED(s,t-1)·α_decay + events·β_update` | `/api/v1/validator/credibility/<id>` |
| L9.3 | UAI: `SHA3-256(chain_id \|\| address \|\| entity_type \|\| genesis_block)` | `/api/v1/universal_asset/<chain>/<addr>` |
| Ψ1 | Phase Transition: `Ψ(t) = Endogenous_Truth_Weight / Total_Truth_Weight` | `/api/v1/phase_transition` |

### L10 — Grand Unified & Phase Roadmap
| ID | Formula | Endpoint |
|----|---------|---------|
| L10.1 | Living Index: `LI = T(t)·e^M · SEC(t) · BC · EP · BRT` (APEX/PRIME/ACTIVE/BOOTSTRAP) | `/api/v1/living_index/<id>` |
| L10.2 | UAI (see L9.3) | `/api/v1/universal_asset/<chain>/<addr>` |
| L10.3 | Emergence: `C(t) > max(Φ_adj, M_adj, Σ, K, A)` — 90-day empirical record | `/api/v1/emergence/<id>` |
| L10.4 | DNA Immune System (INNATE+ADAPTIVE+MEMORY+CRISPR) | `/api/v1/immune/<id>` |
| L10.5 | Chameleon Protocol | `/api/v1/chameleon/<id>` |
| L10.6 | Manifestation Gap Monitor | `/api/v1/manifestation_gap/<id>` |
| L10.7 | TRION Token: 1B fixed supply, 7 allocation categories, 5 utility classes | `/api/v1/token/distribution` |
| L10.8 | 10-Phase Roadmap: L0→L10 gates, capital milestones, team requirements | `/api/v1/phases` |

### Signal Types (SIG-1 through SIG-19) — all 19 live

---

## API Reference (Selected Key Endpoints)

### Behavioral Hash
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/bh/<entity_id>` | Dual-strand BH with all 20 event types |
| POST | `/api/v1/bh` | Compute BH from JSON body (93-byte canonical) |
| GET | `/api/v1/bh/ledger/<entity_id>` | Per-tx BH history from FAISS ledger |
| GET | `/api/v1/bh/stats` | Global BH stats: total, per-chain, per-event-type |

### Signals
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/signal/<entity_id>` | Full 34-field TRIONSignal |
| GET | `/api/v1/trion/<entity_id>` | Core TRION score |
| GET | `/api/v1/silence/<entity_id>` | Structured Silence (Gap, limiting plane, ETA) |
| POST | `/api/v1/signal/batch` | Batch lookup 1–50 entities |
| GET | `/api/v1/signal/type/<type>/<id>` | Specific signal type |

### Behavioral True Value (BTV)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/price/btv/<base>` | Full 10-step BTV derivation + 95% CI |
| GET | `/api/v1/price/btv/<base>/<quote>` | BTV for specific quote currency |
| GET | `/api/v1/price/hierarchy` | Cross-asset Inverted Truth Hierarchy (ETH/BTC/SOL/ARB) |

### Consensus & Validation
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/dw_bft` | L4.1/L4.2/L4.3 Diversity-Weighted BFT |
| GET | `/api/v1/phase_transition` | Ψ(t) phase transition order parameter |
| GET | `/api/v1/moat` | M_moat = D·Q·R·X·F·N |
| GET | `/api/v1/entropy/<entity_id>` | Shannon entropy breakdown |

### Cross-Chain Mapping
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/homomorphic/<chain>/<entity_id>` | H: Dₐ→U with 9-dim feature vector |
| GET | `/api/v1/homomorphic/adaptive_layer` | Adaptive Layer status across 12 architectures |
| GET | `/api/v1/universal_asset/<chain>/<address>` | Universal Asset Identifier |

### Security & Immune System
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/immune/<entity_id>` | All 8 Living Security components + SEC(t) |
| GET | `/api/v1/chameleon/<entity_id>` | Chameleon anti-fingerprinting |
| GET | `/api/v1/security/<id>/mf` | Manipulation fingerprint (6 patterns) |
| GET | `/api/v1/security/<id>/genomic` | Public genomic key sense/antisense |

### Intelligence & Planes
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/planes/<id>/all` | All 5 plane scores |
| GET | `/api/v1/planes/<id>/physical\|mental\|spiritual\|conscious\|anima` | Per-plane breakdown |
| GET | `/api/v1/living_index/<entity_id>` | Grand Unified Living Index (APEX/PRIME/ACTIVE) |
| GET | `/api/v1/emergence/<entity_id>` | Emergence verification |
| GET | `/api/v1/manifestation_gap/<entity_id>` | Manifestation Gap monitor |

### DeFi Intelligence
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/liquidity/<asset>` | Natural Liquidity score NL = LD·LO·LC·LS |
| GET | `/api/v1/audit/<address>` | Contract audit: risk score + 20 vulnerabilities |
| GET | `/api/v1/invest/<entity_id>` | Investment signal engine |
| GET | `/api/v1/reputation/leaderboard` | Behavioral reputation leaderboard |
| GET | `/api/v1/thermodynamics/<entity_id>` | Thermodynamic phase (SOLID/LIQUID/GAS/PLASMA) |
| GET | `/api/v1/lifecycle/<entity_id>` | Entity lifecycle stage |
| GET | `/api/v1/agent/validate` | AI agent safety (5-gate pipeline) |

### Governance
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/governance/awa` | AWA state machine |
| GET | `/api/v1/governance/falsifiability` | All 15 falsifiability conditions |
| GET | `/api/v1/governance/gratitude` | Gratitude Protocol decay |
| GET | `/api/v1/sba/<nation_id>` | Sovereign Behavioral Assessment |
| GET | `/api/v1/bootstrap/status` | Bootstrap decay curve |
| GET | `/api/v1/phases` | 10-Phase Roadmap status |
| GET | `/api/v1/token/distribution` | TRION token genesis plan |

### 0G Integration
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/zg/integration` | All 4 modules combined |
| GET | `/api/v1/zg/chain/status` | Live 0G chain stats |
| GET | `/api/v1/zg/storage/root` | BEO Merkle root from chain |
| POST | `/api/v1/zg/da/submit` | Submit DA blob (Reed-Solomon commitment) |
| POST | `/api/v1/zg/compute/infer` | Route inference via 0G Compute (TEE) |

### Meta
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/whitepaper/coverage` | 84 formulas, 100% LIVE |
| GET | `/api/v1/sdk/spec` | Full SDK specification |
| GET | `/api/v1/genesis/<asset>` | Genesis Inference signal |
| GET | `/api/v1/predictive_limit` | Predictive Completeness Limit |

---

## Chain Coverage — 37 Chains

### EVM Mainnet (14 chains via trion-evm)
ETH_MAINNET (1) · ARB_MAINNET (42161) · BASE_MAINNET (8453) · OP_MAINNET (10) · BNB_MAINNET (56) · POLYGON (137) · AVALANCHE (43114) · HASHKEY (177) · MANTLE (5000) · LINEA (59144) · SCROLL (534352) · ZG_MAINNET · CELO · GNOSIS

### EVM Testnet (5 chains)
ARB_SEPOLIA · ETH_SEPOLIA · BASE_SEPOLIA · OP_SEPOLIA · HASHKEY_SEPOLIA

### Solana (1)
SOLANA_MAINNET (via trion-svm)

### Native VM (4 via Rust)
NEAR_MAINNET · TON_MAINNET · STARKNET_MAINNET · POLKADOT_PVM (Westend)

### Extended VM (13 via Rust)
BITCOIN_MAINNET · COSMOS_HUB · KAVA · INJECTIVE · SEI · DYDX · INITIA · APTOS_MAINNET · SUI_MAINNET · TRON_MAINNET · PI_MVM · MOVEMENT_MAINNET · 0G_MAINNET

---

## Rust L0 Crate Architecture

All 13 crates implement the same canonical per-tx BH pipeline (whitepaper L0.1):

```
classify_event()        → EventType byte (20 types: SWAP=1, BORROW=3, FLASH_LOAN=15, MEV_CAPTURE=17…)
magnitude_norm()        → log₁₀ formula with AtomicU64 running max
build_bh_batch()        → per-tx canonical 93-byte BH construction
canonical_bh()          → entity(32)||event(1)||mag(8)||ctx(8)||ts(8)||chain(4)||block_hash(32)
sense / antisense       → SHA3-256(payload||0x00) / SHA3-256(payload||0xFF)⊕NOT(sense)
faiss.add_tx_bh_batch() → POST per-tx BHs to FAISS ledger
```

| Crate | Chains | VM Type |
|-------|--------|---------|
| trion-common | shared | Library: hash_dna, faiss client, living_security, entropy |
| trion-evm | 14 EVM mainnet | EVM (ethers-rs) |
| trion-svm | Solana | SVM (solana-client) |
| trion-near | NEAR | WebAssembly VM |
| trion-ton | TON | TVM |
| trion-starknet | StarkNet | Cairo VM |
| trion-pvm | Polkadot | Substrate |
| trion-cosmos | Cosmos, Kava, Injective, SEI, dYdX, Initia | Cosmos SDK |
| trion-aptos | Aptos | Move VM |
| trion-movement | Movement | Move VM |
| trion-sui | SUI | Move VM |
| trion-tron | TRON | TVM (EVM-like) |
| trion-utxo | Bitcoin | UTXO |
| trion-pi | Pi Network | Pi VM |

---

## FAISS ANIMA Intelligence Engine

- **Index**: 128-dimensional behavioral feature vectors
- **Live vectors**: 11,000–15,000+ (grows continuously as chains produce blocks)
- **BH ledger**: SQLite `bh_ledger.db` — per-tx canonical BHs with sense/antisense verification
- **Archetypes**: 64 trained (IndexIVFPQ promoted after training)
- **Port**: 8000 (FastAPI, 122+ endpoints)
- **Phase 2 learning**: Φ weight adaptation active (depth 14,000+ vectors)
- **BH ledger stats**: Chains tracked per-event-type, verifies complementary strand invariant per batch

---

## Living Security System (8 DNA-Mimetic Components)

`SEC(t) = LSS(t) · PQC(t) · CC(t)`

| Component | Mechanism |
|-----------|-----------|
| GK Evolution | `GK(t) = Hash_DNA(GK(t-1)\|\|BE(t)\|\|TM(t)\|\|CV(t))` — stolen snapshot instantly outdated |
| Complementary Strand | XOR invariant — cryptographically tamper-evident |
| Immune System | INNATE + ADAPTIVE + MEMORY — permanent memory, never decays |
| Epigenetic Layer | 4 states: NORMAL / ELEVATED / DEFENSIVE / LOCKDOWN |
| Genetic Recombination | All security params re-derived from behavioral history every 24h |
| Cryptographic Noise | Decoy sequences — the noise pattern itself is authentication |
| Mitochondrial Core | Independent protocol integrity DNA, 2nd auth layer |
| CRISPR Defense | 8 known DeFi attack signatures: Harvest, Beanstalk, Mango, Jimbos, Euler, Curve, Ronin, Wormhole |

**Post-quantum layer**: CRYSTALS-Kyber + CRYSTALS-Dilithium + SPHINCS+
**Classical layer**: SHA-3-256 + AES-256 + Zero-knowledge proofs
**P(break LSS)**: Monotonically decreasing (proved via Kolmogorov complexity bound)

---

## Behavioral True Value Engine (L0.7)

**Formula**: `BTV = P_ref × Ω × (1 − MF_discount) × C_weight × NL_weight`

- `P_ref` — CEX reference price (Chainlink/Pyth baseline)
- `Ω = tanh(chains/10) × D_eff` — 37-chain behavioral consensus weight
- `MF_discount = 2.5% + MF_score × 35%` — manipulation fingerprint stripped out
- `C_weight = 0.95 + 0.07 × C(t)` — five-plane coherence weighting
- `NL_weight = 0.95 + 0.07 × NL` — natural liquidity health

**Live manipulation discounts** (May 19, 2026): ETH −20.3% · BTC −16.4% · SOL −23.1% · ARB −19.6%

**Performance**: concurrent `ThreadPoolExecutor` + shared BH stats cache → 29s → **5.3s** for full hierarchy

---

## Diversity-Weighted BFT (L4.1/L4.2/L4.3)

The key insight: Byzantine validators who coordinate to attack consensus simultaneously make their `d_j → 0`, eliminating their own effective voting weight. Coordination is **structurally self-defeating**.

```
d_j = 1 − corr(M_j, M̄)                         # L4.1: diversity weight
Σ(t) = Σⱼ[sⱼ·dⱼ·𝟙(|vⱼ−v̄|≤δ)] / Σⱼ[sⱼ·dⱼ]  # L4.2: consensus score
Safety: Σ_honest sⱼ·dⱼ > (2/3)·Σ_all sⱼ·dⱼ    # L4.3: BFT condition
lim_{coordination→1} Σ_{Byzantine} sⱼ·dⱼ = 0   # L4.3 proof: QED
```

Live: σ = 0.90, HHI = 1183 [HEALTHY], coordination attack simulation included in response.

---

## Homomorphic Behavioral Mapping + Adaptive Layer

**Problem**: A Bitcoin UTXO coin-days-destroyed metric and an EVM token velocity metric cannot be directly compared without a formal translation preserving behavioral meaning.

**Solution**: `H: Dₐ → U` such that `rel(e₁,e₂) in A ≅ rel(H(e₁),H(e₂)) in U`

**Adaptive Layer**:
```
t_canonical(e) = t_observed(e) + Δf(A)      # temporal alignment (finality delta)
f_normalized   = (f_raw(e) − μ_A(t)) / σ_A  # magnitude normalization (z-score)
w_A(t)         = 1 − e^(−λ_A · T_A(t))      # maturity weight (converges to 1)
```

**Universal Feature Space** (9-dim): velocity · holder_distribution · liquidity_depth · accumulation_index · mev_risk · cross_chain_flow · conviction_velocity · governance_activity · ecosystem_engagement

Architecture-specific mappers: EVM (native reference) · BTC (UTXO/CDD/HODL waves) · SOL (Jito bundles/SPL) · Cosmos (IBC packet flows/governance) · Generic (NEAR/TON/SUI/TRON/APTOS/STK/PVM/PI)

---

## On-Chain Deployments

### 0G Galileo Testnet (Chain ID 16602) — Primary
| Contract | Address |
|----------|---------|
| TRIONOracleV3 | `0x0471B2BE25c2eBbAe7FAc17383F1692979F0A87C` |
| LiquidityOcean | `0x105c7F6c16d2c92FEad10336C2b6A047F999a5A7` |
| TravelRuleCompliance | `0x5e7DBE6cc90d6260be2781dc312812834715EBaB` |
| BTCPSimpleEscrow | `0x388f98831c749D7Acad2046329c9CeC94A8b248d` |
| TRIONExecutionGate | `0xDB5910Dc6CfD219D00F64be1F23DA0289901356d` |
| Explorer | https://chainscan-galileo.0g.ai |

### EVM Testnets (active relayer)
- Arb Sepolia · Eth Sepolia · Base Sepolia · Op Sepolia · HashKey Sepolia

### Native VMs
| VM | Status |
|----|--------|
| NEAR (trion.testnet) | DEPLOYED — 304,895-byte WASM (TX: 9rxW1azrR3eJYS3mXuJiSt2tUePR9BuotYv7bghXK5S6) |
| TON | BOC compiled, wallet funded 5.999 TON |
| SVM (Solana devnet) | 5 txns/cycle via execute.ts |
| SUI devnet | 5/5 real txns executed |
| Aptos devnet | Address 0x7d45211… funded via faucet |
| StarkNet Sepolia | Cairo contracts compiled (3), awaiting ETH |

---

## 0G Full-Stack Integration (4 Modules)

| Module | Implementation | Status |
|--------|---------------|--------|
| 0G Chain | Live stats from all 5 Galileo contracts | Active |
| 0G Storage | Merkle-256 root, `@0glabs/0g-ts-sdk` MemData+Indexer | Active |
| 0G DA | Reed-Solomon 2× erasure: `SHA256(namespace\|\|blob_sha256\|\|erasure_sha256)` | Active (local proof fallback) |
| 0G Compute | TEE-verified ANIMA inference, `createZGComputeNetworkBroker` | Active |

---

## Workflows (8 active)

| Workflow | Command | Purpose |
|----------|---------|---------|
| Start application | `PORT=5000 uv run python3 serve.py` | Flask Oracle API + dashboard |
| FAISS ANIMA | `uv run python3 akashic/faiss_service.py` | FAISS intelligence engine |
| Rust Indexers | `bash supervisors/rust_indexers.sh` | trion-evm (14 chains) + trion-svm |
| Native VM Indexers | `bash supervisors/native_vm_indexers.sh` | trion-near, trion-ton, trion-pvm, trion-starknet |
| Extended VM Indexers | `bash supervisors/extended_vm_indexers.sh` | trion-utxo, trion-cosmos, trion-aptos, trion-movement, trion-sui, trion-tron, trion-pi |
| Native VM Relayer | `node native-relayer/native_relayer.js` | chains/*/execute.ts signing dispatcher |
| Extended Chain Relayer | `node relayer/extended_chain_relayer.js` | 15 non-EVM chains, 90s interval |
| TRION Relayer | `bash supervisors/trion_and_zg_relayer.sh` | EVM relayer + 0G ExecutionGate, 60s interval |

---

## Repository Structure

```
/
├── oracle_api/             Flask Oracle API (139 routes, ~9000 lines)
│   ├── app.py              Main Flask application
│   ├── price_feed_routes.py BTV engine endpoints (L0.7/L0.8)
│   ├── templates/          dashboard.html, explorer.html, judge.html
│   └── static/             CSS, favicon
├── akashic/                FAISS ANIMA (FastAPI, port 8000)
│   └── faiss_service.py    122+ endpoints, bh_ledger SQLite
├── rust-indexers/          L0 Rust workspace (13 crates)
│   └── crates/             trion-common, trion-evm, trion-svm … trion-pi
├── src/                    Python behavioral engine
│   ├── core/               behavioral_hash.py, coherence_engine.py, homomorphic_mapping.py
│   ├── consensus/          diversity_weighted_bft.py
│   ├── price/              behavioral_price_engine.py (BTV/L0.7)
│   ├── security/           living_security.py (8-component LSS)
│   ├── planes/             physical/, extended/ (all 5 planes)
│   ├── governance/         sba_engine.py, falsifiability_registry.py, awa_state.py
│   └── signals/            signal_factory.py (34-field TRIONSignal)
├── chains/                 VM execution & signing (execute.ts per VM)
│   ├── near/, ton/, svm/, pvm/, starknet/, sui/
├── relayer/                EVM multi-chain relayer (Node.js, ethers@6)
├── native-relayer/         Native VM dispatcher
├── trion-0g/               0G full-stack integration (4 modules)
├── sdk/                    trion_sdk.py (Python SDK v1.0)
├── hardhat/                15-network Hardhat config + deployment scripts
├── contracts/              Solidity (TRIONOracleV3, ExecutionGate, etc.)
├── supervisors/            Process supervisor shell scripts
├── tests/                  328 passing, 24 skipped
├── docs/research/          formal/proofs.hs, hardware/signal_processor.cpp,
│                           math/trion_math.jl, validator/validator_network.go
├── proof-ledger/           On-chain deployment records (JSON per chain)
└── config/                 config.yaml
```

---

## Language Compliance (Whitepaper Part 11 — All 7 Languages)

| Language | Role | Key Files |
|----------|------|-----------|
| **Rust** | L0 core indexers, canonical BH, living security | `rust-indexers/crates/` |
| **Python** | Oracle API, FAISS AI engine, behavioral engine | `oracle_api/`, `akashic/`, `src/` |
| **TypeScript** | SDK, VM execution scripts, relayer | `sdk/`, `chains/*/execute.ts`, `relayer/` |
| **Haskell** | Formal proofs (coherence, BFT safety) | `docs/research/formal/proofs.hs` |
| **C++** | Signal processing hardware layer | `docs/research/hardware/signal_processor.cpp` |
| **Go** | Network health monitor (concurrent, all 37 chains) | `network/health_monitor.go` |
| **Julia** | Mathematical validation (entropy, norms, bootstrap, Kolmogorov) | `math/trion_entropy_verification.jl` |

---

## Test Suite

```bash
python3 -m pytest tests/ -q                          # 328 passing, 24 skipped
LIVE=1 ORACLE_URL=http://127.0.0.1:5000 python3 -m pytest tests/ -v  # includes live chain tests
```

**Stress test highlights** (`tests/test_stress.py`, 17/17 passing):
- BH performance: **0.023ms avg** (target <10ms — 434× faster than spec)
- 1000 BH XOR invariant verifications, 10,000 collision check, 500 tamper detections
- 100 concurrent threads × 100 BHs — zero corruption
- All 8 CRISPR attack signatures detected in <10ms
- Φ(healthy entity) = 0.89 > 0.70 threshold; Φ(manipulated entity) = 0.07 < 0.30 threshold

---

## Running Locally

```bash
# Start Oracle API (port 5000)
PORT=5000 uv run python3 serve.py

# Start FAISS ANIMA (port 8000)
PORT=8000 uv run python3 akashic/faiss_service.py

# Start Rust indexers
FAISS_SERVICE_URL=http://127.0.0.1:8000 bash supervisors/rust_indexers.sh

# Run tests
python3 -m pytest tests/ -q
```

**Entry points**:
- Dev: `serve.py` → `oracle_api/app.py`
- Production: `main.py` → `oracle_api/app.py` (gunicorn-compatible)

---

## User Preferences

- All formulas must match whitepaper exactly — no approximations
- Every endpoint must return live computed values, not stubs
- Rust is the L0 language; Python handles L1–L10 oracle logic
- TypeScript/Node.js handles chain signing and relaying only
- Test suite must stay green (328 passing) after every change
- `replit.md` is the authoritative reference document — keep it current
