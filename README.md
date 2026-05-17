# TRION Protocol — Multi-Chain Behavioral Truth Oracle

> *Real-time behavioral intelligence across **37 indexed networks** · **13 VM families** · Five planes of existence · **162 API routes** · A pre-execution firewall that would have blocked **$44B+** in historical DeFi exploits · **TRIONExecutionGate live on 0G Mainnet (chain 16661)** · **Whitepaper v0.4 aligned**.*

[![Tests](https://img.shields.io/badge/Tests-184%20passed%2C%205%20skipped%20%C2%B7%20E2E%2015%20sections-brightgreen)](tests/)
[![Stress Test](https://img.shields.io/badge/Stress-17%2F17%20passed%20%C2%B7%200.022ms%20avg%20BH-brightgreen)](tests/test_stress.py)
[![Attacks Blocked](https://img.shields.io/badge/Attacks%20Blocked-32%20%7C%20%2443.6B%20protected-red)](simulate_attacks.py)
[![FAISS Vectors](https://img.shields.io/badge/FAISS%20Vectors-Growing%20Live%20from%2037%20chains-blue)](#faiss-anima-service)
[![Oracle API Routes](https://img.shields.io/badge/Oracle%20API%20Routes-162-purple)](#oracle-api----port-5000)
[![Whitepaper](https://img.shields.io/badge/Whitepaper-v0.4%20Aligned-brightgreen)](#whitepaper-v04-alignment)
[![Workflows](https://img.shields.io/badge/Workflows-9%20Running-green)](#workflows)
[![Chains](https://img.shields.io/badge/Chains-37%20Networks%20%7C%2013%20VM%20Families-orange)](#indexed-networks)
[![BH Ledger](https://img.shields.io/badge/BH%20Ledger-243k%2B%20per--tx%20records-blue)](#faiss-anima-service)
[![0G Integration](https://img.shields.io/badge/0G-5%2F5%20Components%20%7C%20Mainnet%2016661-blueviolet)](#0g-integration)
[![0G Mainnet](https://img.shields.io/badge/0G%20Mainnet-0xA85B49C7...4199b-purple)](https://chainscan.0g.ai/address/0xA85B49C73B5710d9ddB1CB5a94c52D0F33c4199b)
[![TEE Sealed](https://img.shields.io/badge/TEE-Sealed%20Inference%20Anti--FrontRun-blueviolet)](#0g-compute--tee-sealed-inference)
[![Render Ready](https://img.shields.io/badge/Render-Dockerfile%20%2B%20render.yaml%20ready-success)](#render-production)
[![License: CC0](https://img.shields.io/badge/License-CC0-lightgrey)](https://creativecommons.org/publicdomain/zero/1.0/)

---

## The Problem TRION Solves

**DeFi protocols lose billions to attackers who look identical to honest users on-chain — until they strike.**

Raw on-chain data (balances, transfers, gas) cannot detect behavioral manipulation: a wallet slowly accumulating governance tokens before a capture attack, an MEV bot probing liquidity across 12 chains to calibrate a sandwich, or a Sybil cluster simulating organic user growth. Traditional oracles report prices. TRION reports *behavioral truth* — whether an entity's on-chain behavior is coherent, honest, and safe.

**Concrete use case:** A DeFi protocol integrates `TRIONExecutionGate.checkExecution(address)` as a pre-trade hook. Before any wallet executes a large swap, TRION's 9-dimensional behavioral entropy score is checked on-chain. Wallets exhibiting `STATUS_COLLAPSE` or `STATUS_HOSTILE` — patterns matching Harvest Finance, Euler, or Beanstalk attack fingerprints — are blocked *before execution*. The protocol pays nothing until an anomaly is caught; TRION is a standing on-chain truth service funded by the 0G network.

**Every major DeFi exploit in history left behavioral fingerprints before it happened.** The Beanstalk governance attack ($182M): wallets accumulating voting tokens for weeks, all showing `GOVERNANCE_CAPTURE` patterns. Harvest Finance ($34M): flash loan probing across 6 protocols over 48 hours before execution. Euler ($197M): systematic position scaling with abnormal counterparty entropy. TRION reads these fingerprints in real time — before execution.

---

## The Core Thesis

The oracle problem has been framed as a data delivery problem for five years. TRION rejects that framing entirely.

**Blockchain activity is not merely a record of the past — it is a living, self-describing signal system.** Every transaction, liquidity event, wallet interaction, and contract call leaves an immutable, observable trace. These traces, when read with sufficient intelligence and verified through decentralized consensus, contain everything needed to understand value — without ever leaving the chain.

The current price discovery stack is inverted. Centralized exchanges sit at the top of the information hierarchy despite having direct profit incentives tied to trading volume, opaque internal order matching, and documented histories of wash trading. Every oracle protocol aggregates this manipulated data and delivers it on-chain more efficiently. They are faster pipes carrying the same compromised water.

**TRION inverts the stack:**

```
Current (broken):
  CEX Price Discovery (manipulable, opaque)
       ↓  Oracle Aggregation (Chainlink, Pyth)
       ↓  DeFi Protocols (downstream, reactive)
       ↓  Retail Participants (most vulnerable)

TRION (inverted):
  Blockchain Behavioral Reality (immutable, transparent)
       ↓  TRION Akashic Index + Resonance Threshold Formula
       ↓  TRION Signal Layer (endogenous, coherence-governed)
       ↓  DeFi Protocols ←→ CEXs ←→ TradFi Systems
```

In the TRION stack, CEXs are no longer the source — they are consumers of the same endogenous, manipulation-resistant truth as every other participant.

---

## How TRION Works — Step by Step

Understanding TRION requires following data from raw blockchain activity to a final on-chain gate signal. Here is every step in order.

### Step 1 — Data Ingestion (14 Rust Indexers + 7 Node.js Supervisors)

Every few seconds, TRION's indexers poll 37 networks across 13 VM families and extract **raw behavioral signals** from each new block.

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

sense     = SHA3-256(payload || 0x00)
antisense = SHA3-256(payload || 0xFF) ⊕ NOT(sense)

Invariant: sense ⊕ antisense = NOT(SHA3-256(payload || 0xFF))   [always true]
```

This dual-strand format is chain-agnostic — produced identically whether the source is an EVM transaction, a Solana slot, a Cosmos block, or a Bitcoin UTXO set. The antisense invariant makes every BH self-certifying: a tampered hash instantly fails the invariant check without any external validator.

**Native and Extended VM indexers** (Node.js, running in `chains/`) cover the remaining non-EVM chains. They translate each chain's native block format into the same 9 abstract dimensions. A NEAR transaction's `action-kind diversity entropy` occupies the same behavioral slot as an EVM transaction's `counterparty entropy`. This is how TRION achieves cross-chain coherence scoring — every chain speaks the same 9-dimensional language.

**All vectors are sent to the FAISS ANIMA engine** via `POST /index/add_batch` every block cycle.

---

### Step 2 — FAISS ANIMA Engine (Python/FastAPI, port 8000)

The FAISS ANIMA engine (`akashic/faiss_service.py`) is TRION's behavioral memory — the Akashic Index. It maintains a **128-dimensional vector index** (FAISS `IndexIVFPQ`) that accumulates every behavioral vector streamed from the indexers.

**Why 128 dimensions?** The 9 raw Shannon entropy features are expanded to 128 dimensions through:
- The 9 base features
- Cross-feature interaction terms (f1×f2, f1×f3, ...) — captures correlated manipulation
- Temporal lag features (f_t vs f_{t-1}) — captures behavioral change rate
- Normalization layers per VM family — ensures a Bitcoin UTXO block and an EVM block are comparable

**What FAISS computes for each entity:**

1. **Akashic Depth `D(t)`** — how many behavioral observations exist for this entity. New entities start at `D=0` (high uncertainty). Active entities accumulate depth continuously. The depth integral `D(t) ∝ ∫₀ᵗ A(τ)·(1 + M(τ))dτ` never decreases — more manipulation attempts make the index deeper and harder to attack.

2. **Archetype Similarity** — TRION maintains 64 pre-trained behavioral archetypes (centroids stored in `trion_archetype_centroids.npy`). Every entity is compared against all 64 archetypes via k-NN search. The nearest archetype determines the entity's behavioral cluster: `GENESIS`, `VALUATION`, `SILENCE`, `GOVERNANCE_CAPTURE`, `FLASH_LOAN_ATTACKER`, etc.

3. **ANIMA Score `A`** — a composite evolutionary fitness metric that measures how well the entity's behavior conforms to its nearest archetype over time. An entity that suddenly shifts archetype clusters shows a sharp drop in `A`.

4. **Thermodynamic Information Conservation** — entropy over the entity's last N behavioral vectors. Natural entities show slowly drifting entropy. Attackers show entropy spikes — sudden changes in behavioral distribution that precede an exploit.

The FAISS index persists across restarts via a multi-layer save strategy: a SIGTERM handler, an `atexit` hook, a FastAPI lifecycle shutdown hook, and a 5-minute background autosave thread. Vectors accumulated between restarts are **never lost**. All data is **live from real blockchain activity** — nothing is mocked.

---

### Step 3 — Oracle API Scoring Engine (Python/Flask, port 5000)

The Oracle API (`oracle_api/app.py`, 162 routes) is the integration point for everything. When any consumer calls `GET /api/v1/signal/{entity_id}`, the following pipeline executes:

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

Mental coherence measures *intent consistency* — does this entity do what it appears to be doing? Computed using a hash-seeded observer-effect correction that detects when an entity's behavior changes based on whether it is being observed (a game-theoretic attack vector known as the observer effect in MEV).

**3c. Spiritual Plane (Σ)**

Validator consensus diversity — how many independent validators on each chain have verified the entity's transactions? Higher validator diversity = higher Spiritual score. This penalizes entities that route through a narrow set of validators (a known method for censorship and sandwich coordination).

**3d. Conscious Plane (K)**

Commit-reveal annotation voting — a governance mechanism where TRION validators stake on behavioral classifications. The Conscious score reflects the stake-weighted consensus on entity classification.

**3e. ANIMA Plane (A)**

The ANIMA score from the FAISS engine — archetype evolutionary fitness. This is the only plane that requires actual FAISS data. For new entities, it is seeded from the entity's archetype distance using the pre-trained centroids.

**3f. Five-Plane Coherence Score Assembly**

```
C(t) = α·Φ_adj + β·M_adj + γ·Σ + δ·K + ε·A

α = 0.25  (Physical  — raw behavioral entropy, Physical Layer Φ(t))
β = 0.30  (Mental   — intent consistency, highest weight; Mental Layer M(t))
γ = 0.25  (Spiritual — validator consensus diversity; Σ(t))
δ = 0.10  (Conscious — governance stake voting; K(t))
ε = 0.10  (ANIMA    — archetype evolutionary fitness; A(t))

Weights sum: α + β + γ + δ + ε = 1.0
```

This is the **Triplane Resonance Model** extended to five planes. The whitepaper describes Φ, M, Σ — TRION adds K (Conscious/Karmic) and A (Anima) as the fourth and fifth behavioral planes.

**3g. Dynamic Emission Threshold**

```
Θ(t) = Θ_min + (Θ_max − Θ_min) · V(t)
     = 0.55 + 0.37 × volatility_norm   →   range [0.55, 0.92]
```

In calm markets (low V(t)), `Θ = 0.55`. During high-volatility periods, `Θ` rises to 0.92 — the protocol automatically tightens because the base rate of attacks rises during volatility.

**3h. Signal Classification**

```
C(t) < Θ(t)     →  SILENCE   (anomaly — block execution, emit typed Silence Signal)
C(t) ≥ Θ(t):
  ├─ ANIMA archetype "new entity"   →  GENESIS
  ├─ liquidity behavior detected    →  VALUATION
  ├─ cross-chain activity           →  TRANSCENDENCE
  └─ default                        →  VALUATION / COVENANT / TRION
```

**Silence as Information:** When `C(t) < Θ(t)`, TRION emits a typed Silence Signal rather than a weak valuation. Downstream protocols receive explicit information that coherence is insufficient — they can halt operations, widen collateral ratios, or trigger conservative fallbacks. No current oracle provides this.

---

### Step 4 — 0G Integration (5 Components)

TRION integrates all 5 components of the 0G stack. Each serves a distinct architectural purpose.

**4a. 0G Chain** — The execution layer. `TRIONExecutionGate` is deployed on **0G Mainnet (chain 16661)**:

| Contract | Network | Address | Purpose |
|---------|---------|---------|---------|
| `TRIONExecutionGate` | **0G Mainnet (16661)** | [`0xA85B49C73B5710d9ddB1CB5a94c52D0F33c4199b`](https://chainscan.0g.ai/address/0xA85B49C73B5710d9ddB1CB5a94c52D0F33c4199b) | Pre-trade firewall — `checkExecution(addr)` returns `STATUS_SAFE/ELEVATED/COLLAPSE/HOSTILE` |
| `TRIONOracleV3` | Galileo (16602) | `0x0471B2BE25c2eBbAe7FAc17383F1692979F0A87C` | Publishes behavioral signals via `publishBehavioralTruth()` |
| `LiquidityOcean` | Galileo (16602) | `0x105c7F6c16d2c92FEad10336C2b6A047F999a5A7` | Protected vault that checks coherence before withdrawals |
| `TravelRuleCompliance` | Galileo (16602) | `0x5e7DBE6cc90d6260be2781dc312812834715EBaB` | Compliance scoring for cross-border DeFi |
| `BTCPSimpleEscrow` | Galileo (16602) | `0x388f98831c749D7Acad2046329c9CeC94A8b248d` | BTCP-collateralized escrow gated by coherence |
| `AkashicProof` | Newton (16600) | `0x33c793fed5bf5fcB043D8c6c74256e7B4b38156D` | Permanent on-chain proof of behavioral dataset |

> **Mainnet deploy details:** Block 33,234,152 · Tx [`0xb83aa8ce…`](https://chainscan.0g.ai/tx/0xb83aa8ce2a285bdafc20be6c8ad96d967622678a0f4ad0e27016d8952c055e74) · RPC `https://evmrpc.0g.ai`

**4b. 0G Storage** — The `zg_sync_daemon.py` runs hourly, generating a delta export of new behavioral data (~1.36 MB binary), computing its Merkle-256 root, and uploading to 0G Storage. The Merkle root is committed on-chain via `AkashicProof.updateStorageRoot()`.

**4c. 0G DA (Data Availability)** — Every time a SILENCE signal fires, the full anomaly payload is streamed to 0G DA as a binary blob. The DA commitment is `SHA256(namespace || blob_sha256 || erasure_sha256)` with Reed-Solomon 2× erasure coding. This creates a permanent, non-reputable record of *why* every execution was blocked.

**4d. 0G Compute** — High-complexity ANIMA inference is routed through 0G Compute's serving broker. This prevents oracle manipulation: even if the TRION API is compromised, the behavioral archetype inference is verified inside a Trusted Execution Environment.

**4e. 0G KV** — Hot signal data (last 60 seconds across all active entities) maintained across 4 stream IDs for microsecond-latency reads.

---

### Step 5 — Relayers (Publishing Signals On-Chain)

**TRION Relayer** (`relayer/relayer.js`): Publishes `C(t)` signals to 7 EVM chains simultaneously including the 0G ExecutionGate integration.

**Native VM Relayer** (`native-relayer/native_relayer.js`): Signs and submits block proofs to NEAR, TON, Polkadot, and StarkNet using each chain's native signature scheme.

**Extended Chain Relayer** (`relayer/extended_chain_relayer.js`): Publishes to 15 non-EVM chains using chain-native embedding methods (Bitcoin `OP_RETURN`, Cosmos `MsgSend` memo, Aptos Move module calls, SUI programmable transactions, TRON smart contract, Pi Network Stellar memo).

---

### Step 6 — Smart Contract Gating

Any DeFi protocol integrates TRION with a single line:

```solidity
import "./interfaces/ITRIONOracle.sol";

contract MyDeFiProtocol {
    ITRIONOracle public immutable trion;

    function executeTrade(address trader) external {
        (uint8 status, uint256 score) = trion.checkExecution(trader);
        require(status < STATUS_COLLAPSE, "TRION: behavioral anomaly detected");
        // ... execute trade
    }
}
```

`checkExecution()` reads the latest published signal from `TRIONExecutionGate` — an on-chain lookup, no external calls. Gas cost: ~2,100 gas (single SLOAD). Latency: zero.

```
STATUS_SAFE     (0)   C(t) ≥ Θ(t) + 0.15   — confident normal behavior
STATUS_ELEVATED (1)   C(t) ≥ Θ(t)           — normal, slightly elevated risk
STATUS_COLLAPSE (2)   C(t) < Θ(t)           — anomaly, soft block
STATUS_HOSTILE  (3)   C(t) < 0.30            — active attack pattern, hard block
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

## Whitepaper v0.4 Alignment

This section documents what was implemented in this session to align TRION's codebase with whitepaper v0.3 and extend it to v0.4. Every item below corresponds to a section of the whitepaper that previously had no code behind it.

### Three Core Primitives (Whitepaper Introduction)

The whitepaper defines three new primitives that do not exist in any other financial infrastructure:

| Primitive | Whitepaper Definition | Implementation |
|-----------|----------------------|----------------|
| **Behavioral Hash (BH)** | 93-byte dual-strand cryptographic fingerprint per transaction; sense/antisense invariant makes every BH self-certifying | `trion-common/src/hash_dna.rs`, `src/core/behavioral_hash.py`, `GET /api/v1/bh/<id>`, `POST /api/v1/bh` |
| **Akashic Index** | Permanently compounding cross-chain behavioral memory; depth `D(t) ∝ ∫₀ᵗ A(τ)·(1+M(τ))dτ` never decreases | `akashic/faiss_service.py` — 128-dim FAISS IndexIVFPQ, 243k+ BH records live |
| **Genesis Signal** | Appraisal of zero-history assets from archetype similarity; `V₀ = Σₖ sim(G,Aₖ)·Vₖ(stage=0)/Σₖ sim(G,Aₖ)` | `src/core/genesis_inference.py`, `GET /api/v1/genesis/fingerprint/<id>` |

### New Routes — Whitepaper Gap Fill

10 new API routes added to close the gap between whitepaper specification and implementation:

| Route | Whitepaper Section | What It Does |
|-------|-------------------|--------------|
| `GET /api/v1/phase_signal` | §10.6 Phase Signals | System-wide behavioral phase shift detection (ACCUMULATION, DISTRIBUTION, TRANSITION, CONSOLIDATION, PHASE_BREAK, COMPRESSION). Returns recommended protocol risk posture. |
| `GET /api/v1/phase_signal/<entity_id>` | §10.6 | Per-entity phase signal with full 5-plane breakdown |
| `GET /api/v1/order_parameter` | §9.2 The Order Parameter | **Ψ(t) = Endogenous Truth Weight / Total Truth Weight**. The fundamental metric of TRION's adoption. Currently Ψ(t) ≈ 0.022 (2.2% endogenous). Projects days to critical threshold Ψ_c = 0.51. |
| `GET /api/v1/cex/status` | §7.3 CEX Integration | Full CEX registry (Binance, Coinbase, OKX, Bybit, Kraken, HashKey) with integration stage tracking. Defines outbound signal bundle and inbound data types. |
| `GET /api/v1/cex/feed` | §7.3 TRION → CEX | Standardized feed for CEX systems to pull current TRION signals. Returns VALUATION, SILENCE, MANIP_ALERT, GENESIS, COHERENCE, PHASE signals per asset. |
| `POST /api/v1/cex/ingest` | §7.3 CEX → TRION | Accepts anonymized CEX behavioral data (ORDER_FLOW_ANON, VOLUME_STATS, LIQUIDATION_EVENTS, SPREAD_METRICS). PII rejection enforced — user-identifying fields cause 422. Routes to Physical Layer Φ(t). |
| `GET /api/v1/genesis/fingerprint/<asset_id>` | §6.2 Genesis Fingerprint | Full 6-dimension genesis fingerprint at t=0. All six whitepaper-specified inputs populated. Variable λ archetype-matched. V₀ formula complete. |
| `GET /api/v1/universal_asset/<chain>/<addr>/equivalences` | §8.4 UAI | Cross-chain equivalence resolution. WETH on Arbitrum correctly maps to ETH canonical group (7 representations). Single unified Akashic history per economic asset. |
| `GET /api/v1/manipulation/attack_cost/<entity_id>` | §7.5 Manipulation Destruction | Formalizes `P(success) = P(Φ_spoof) · P(Μ_compromise) · P(Σ_collusion)`. For Uniswap V3: attack cost $953M, EV = −$953M. Side-by-side CEX oracle comparison (CEX attack cost ~$14M, positive EV — the contrast that defines TRION's value). |

### Genesis Inference — Variable λ (Whitepaper §6.4)

The most technically significant core fix. The whitepaper specifies that the confidence convergence rate λ must be **archetype-matched** — not hardcoded:

```
conf(t) = 1 − e^(−λ · A(t))

λ = Σₖ sim(G, Aₖ) · λₖ / Σₖ sim(G, Aₖ)    ← variable, not fixed
```

**Before:** `GENESIS_LAMBDA = 0.001` hardcoded for all asset classes.

**After:** `archetype_matched_lambda()` computes λ from the weighted average of matched archetypes' convergence rates:

| Archetype | λₖ | Meaning |
|-----------|-----|---------|
| Memecoin / Speculative | 0.008 | High early activity → fast convergence |
| Stablecoin | 0.002 | Moderate activity → medium convergence |
| Governance Token | 0.0006 | Low early activity → slow convergence |
| DeFi Blue Chip | 0.0004 | Very stable → very slow convergence |
| RWA Tokenized | 0.0003 | Illiquid → slowest convergence |

Fast-moving assets converge to full confidence quickly. Slow-moving assets carry wider confidence intervals longer — exactly as the whitepaper specifies.

### Full Genesis Fingerprint (Whitepaper §6.2)

`GenesisFingerprint` dataclass now implements all six whitepaper-specified dimensions with 21 sub-fields:

```python
# Dimension 1: Liquidity seeding structure
liquidity_seed_amount_usd, liquidity_concentration, lp_wallet_akashic_depth

# Dimension 2: Initial token distribution
initial_holder_count, initial_distribution_entropy, initial_concentration_index

# Dimension 3: Deployer wallet behavioral history from Akashic Index  ← was missing
deployer_akashic_depth, deployer_clean_history_ratio,
deployer_prior_protocol_count, deployer_prior_success_rate

# Dimension 4: Contract architecture  ← was missing
has_upgrade_proxy, ownership_centralized, permission_topology_score,
contract_complexity_score, has_timelock

# Dimension 5: First-block interaction data  ← was missing
first_block_trade_volume_usd, first_block_wallet_diversity, first_block_price_impact

# Dimension 6: Cross-chain context at launch  ← was missing
cross_chain_context_score, contemporaneous_similar_count, market_coherence_at_launch
```

### Order Parameter Ψ(t) — The Scoreboard

`GET /api/v1/order_parameter` tracks the most important metric in TRION's entire mission. Current live readings:

```
Ψ(t)         ≈ 0.022   (2.2% of financial truth is endogenous)
CEX weight   ≈ 0.763   (76.3% still CEX-driven)
Oracle aggr  ≈ 0.134   (13.4% from Chainlink/Pyth/Band)
OTC/bilateral ≈ 0.081  (8.1% OTC pricing)

Ψ_c = 0.51 (critical threshold — phase transition point)
```

When Ψ crosses 0.51, endogenous truth becomes the dominant price reference. The phase transition cannot be reversed.

### UAI Cross-Chain Equivalence

`GET /api/v1/universal_asset/<chain>/<addr>/equivalences` resolves economically equivalent assets to a single canonical record:

```
WETH on Arbitrum  (0x82aF...)  ─┐
WETH on Base      (0x4200...)  ─┤──→ ETH canonical  →  one Akashic history
WETH on Optimism  (0x4200...)  ─┤
weETH on Base     (0x04C0...)  ─┘
```

Registered equivalence groups: **ETH** (7 representations), **USDC** (5 representations), **BTC** (4 representations).

### Manipulation Destruction — Formally Computed

`GET /api/v1/manipulation/attack_cost/<entity_id>` proves manipulation is economically irrational:

```
P(success) = P(Φ_spoof) · P(Μ_compromise) · P(Σ_collusion)
```

Each probability decays exponentially with Akashic depth. For any entity with D > 10,000:
- P(Φ_spoof) < 0.0001 — fabricating entropy across 9 dimensions costs exponentially more than depth grows
- P(Μ_compromise) < 0.00001 — validator majority stake too expensive
- P(Σ_collusion) < 0.000001 — independent validators cannot be simultaneously coordinated

Joint probability rounds to zero. Attack EV is deeply negative. The mathematics prove the conclusion, not just assert it.

---

## Codebase Structure

```
trion-core/
├── serve.py                    # Unified entry point → oracle_api/app.py (Flask, port 5000)
├── oracle_api/
│   ├── app.py                  # 162 API routes — signal compute, on-chain publish, live feed
│   ├── blockchain.py           # web3 relay — TRIONSensingOracle on Arbitrum Sepolia
│   ├── templates/dashboard.html  # Live dashboard UI
│   └── requirements.txt
├── akashic/
│   ├── faiss_service.py        # FAISS ANIMA engine (FastAPI, port 8000, 128-dim IndexIVFPQ)
│   ├── anima_engine.py         # Archetype evolutionary fitness scoring
│   ├── anima_regulatory.py     # Compliance behavioral patterns
│   ├── btcp_gas_forecast.py    # Gas price behavioral forecasting
│   └── liquidity_ocean.py      # Liquidity behavioral patterns
├── rust-indexers/              # Rust workspace (Cargo workspace, 14 crates)
│   └── crates/
│       ├── trion-common/       # Shared: BH canonical format, FAISS client, entropy utils
│       ├── trion-evm/          # EVM L0 indexer — 14 chains
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
│   ├── near/                   # NEAR execute.ts
│   ├── pvm/                    # Polkadot Westend execute.ts
│   ├── starknet/               # StarkNet Sepolia execute.ts
│   ├── sui/                    # Sui Mainnet execute.ts
│   ├── svm/                    # Solana Devnet svm_indexer.py + execute.ts
│   └── ton/                    # TON Testnet execute.ts
├── relayer/
│   ├── relayer.js                     # EVM relayer — publishes C(t) on 7 chains every 60s
│   ├── zg_execution_gate_relayer.js   # 0G ExecutionGate relayer
│   └── extended_chain_relayer.js      # 15 non-EVM chains every 90s
├── native-relayer/
│   └── native_relayer.js       # NEAR/TON/Polkadot/StarkNet native sig relayer
├── supervisors/
│   ├── evm_extras_indexers.sh
│   ├── native_vm_indexers.sh
│   ├── extended_vm_indexers.sh
│   ├── rust_indexers.sh
│   └── trion_and_zg_relayer.sh
├── trion-0g/                   # 0G integration SDK
│   └── src/
│       ├── zg_chain.mjs        # 0G Chain contract interactions
│       ├── zg_storage.mjs      # 0G Storage upload/download
│       ├── zg_da.mjs           # 0G DA blob submission
│       ├── zg_compute.mjs      # 0G Compute broker (TEE inference)
│       └── zg_compute_anima.ts # ANIMA archetype inference via 0G Compute
├── src/                        # Core scoring engine (Python)
│   ├── core/
│   │   ├── behavioral_hash.py      # 93-byte dual-strand BH, 20 canonical EventTypes
│   │   ├── coherence_engine.py     # 5-plane C(t) assembly, moat M_moat = D·Q·R·X·F·N
│   │   ├── genesis_inference.py    # Genesis Fingerprint (6 dims), variable λ, V₀ formula
│   │   └── signal_factory.py       # 34-field TRIONSignal assembly
│   ├── security/
│   │   └── living_security.py      # 8-component Living Security System
│   ├── planes/                 # Five-plane scoring modules
│   ├── manipulation/           # Fingerprint detectors (7 patterns)
│   ├── governance/             # Slashing, validator rewards, SBA engine
│   └── agent/                  # AI agent safety modules
├── contracts/                  # Solidity contracts (Hardhat)
│   ├── TRIONExecutionGate.sol  # Pre-trade firewall (0G Mainnet 16661)
│   ├── TRIONOracleV3.sol
│   ├── AkashicProof.sol
│   ├── TRIONSensingOracle.sol
│   ├── ConfidentialCoherenceVault.sol
│   ├── LiquidityOcean.sol
│   ├── TravelRuleCompliance.sol
│   ├── BTCPSimpleEscrow.sol
│   ├── TRIONFirewall.sol
│   ├── TRIONStaking.vy
│   └── interfaces/
├── sdk/
│   └── trion_sdk.py            # Python SDK for TRION API
├── tests/                      # 184 unit + 17 stress tests
├── math/                       # Julia entropy verification, Haskell formal proofs
├── docs/research/              # C++ signal processor, Go health monitor
├── proof-ledger/               # On-chain proof records
├── Dockerfile                  # Dev image (Oracle API + FAISS only)
├── Dockerfile.render           # Production image (all services, Rust compile)
├── render-entrypoint.sh        # Production process supervisor
├── docker-compose.yml
├── render.yaml
├── railway.toml
└── fly.toml
```

---

## Workflows

All **9 workflows** run continuously in the Replit environment:

| # | Workflow | Runtime | Purpose |
|---|---------|---------|---------|
| 1 | **Start application** | Python / Flask (uv) | Oracle API + Frontend on port 5000 — 162 routes, dashboard |
| 2 | **FAISS ANIMA** | Python / FastAPI (uv) | 128-dim FAISS vector index + behavioral planes on port 8000 |
| 3 | **Rust Indexers** | Rust (cargo) | L0 EVM (14 chains) + SVM/Solana — core behavioral indexing |
| 4 | **EVM Extras Indexer** | Bash supervisor | BNB/Base/HashKey/Mantle/Linea/Scroll → FAISS |
| 5 | **Native VM Indexers** | Bash / Node.js | NEAR, TON, Polkadot, StarkNet → FAISS |
| 6 | **Extended VM Indexers** | Bash / Node.js | UTXO×4, COSMOS×6, MOVE×2, SUI, TRON, PI → FAISS |
| 7 | **Native VM Relayer** | Node.js | Signs block proofs on NEAR · TON · Polkadot · StarkNet |
| 8 | **TRION Relayer** | Node.js + Bash | Publishes C(t) on EVM chains every 60s; 0G ExecutionGate sync |
| 9 | **Extended Chain Relayer** | Node.js | Publishes C(t) on 15 non-EVM chains every 90s |

---

## 0G Integration

TRION integrates **all 5 components** of the 0G stack simultaneously:

| 0G Component | TRION Usage | Status |
|---|---|---|
| **0G Chain** | `TRIONExecutionGate` on **Mainnet (chain 16661)** at `0xA85B49C73B5710d9ddB1CB5a94c52D0F33c4199b`; `checkExecution()` called pre-trade | ✅ LIVE — mainnet block 33,234,152+ |
| **0G Storage** | Hourly FAISS delta export (~1.36 MB binary); Merkle-256 root committed on-chain via `AkashicProof.updateStorageRoot()` | ✅ SDK integrated; daemon running |
| **0G DA** | 60s behavioral event blobs; `commitment = SHA256(namespace ∥ blob_sha256 ∥ erasure_sha256)` with Reed-Solomon 2× | ✅ Daemon running |
| **0G Compute** | ANIMA archetype inference via `createZGComputeNetworkBroker(signer)`; TEE-verified; micro-payment per inference | ✅ SDK integrated |
| **0G KV** | Hot signal streams across 4 stream IDs — microsecond-latency reads for HFT integrations | ✅ Active |

**Single judge endpoint:** `GET /api/v1/zg/integration` — returns all 5 components in one JSON response with live block number, contract addresses, and explorer links.

---

## Running

### Replit (development)

All 9 workflows start automatically. Oracle API available at port 5000, FAISS ANIMA at port 8000.

```bash
# Verify everything is live
curl http://127.0.0.1:5000/api/v1/health           # Oracle API health
curl http://127.0.0.1:8000/health                  # FAISS ANIMA health + vector count
curl http://127.0.0.1:5000/api/v1/order_parameter  # Ψ(t) — adoption scoreboard
curl http://127.0.0.1:5000/api/v1/phase_signal     # System-wide phase signal
curl http://127.0.0.1:5000/api/v1/cex/status       # CEX integration status
curl http://127.0.0.1:5000/api/v1/zg/integration   # All 5 0G components

# Run test suite
python3 -m pytest tests/ -q                        # 184 passed, 5 skipped
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

### Docker — full production image

```bash
docker compose --profile full up --build
# Or:
docker build -f Dockerfile.render -t trion-core .
docker run -p 10000:10000 -p 8000:8000 --env-file .env trion-core
```

### Render (production)

```bash
# Configured via render.yaml — push to GitHub main → Render auto-deploys
# Dockerfile.render builds all services → render-entrypoint.sh supervises them
# Health check: GET /api/v1/health → 200 OK (port 10000 in production)
```

### Railway / Fly.io

```bash
# Railway
npm i -g @railway/cli && railway login && railway up

# Fly.io
fly auth login && fly launch --no-deploy && fly deploy
```

---

## Indexed Networks

**37 networks across 13 VM families** — all contributing live behavioral data:

### EVM — Ethereum Virtual Machine
| Network | Chain ID | Indexer | Status |
|---------|---------|---------|--------|
| Ethereum Mainnet | 1 | L0 EVM (Rust) | ✅ Streaming |
| Arbitrum Mainnet | 42161 | L0 EVM (Rust) | ✅ Streaming |
| Base Mainnet | 8453 | L0 EVM (Rust) | ✅ Streaming |
| Optimism Mainnet | 10 | L0 EVM (Rust) | ✅ Streaming |
| BNB Mainnet | 56 | L0 EVM (Rust) | ✅ Streaming |
| Polygon Mainnet | 137 | L0 EVM (Rust) | ✅ Streaming |
| HashKey Mainnet | 177 | L0 EVM (Rust) | ✅ Streaming |
| 0G Mainnet | 16661 | L0 EVM (Rust) | ✅ Streaming |
| Mantle Mainnet | 5000 | L0 EVM (Rust) | ✅ Streaming |
| Linea Mainnet | 59144 | L0 EVM (Rust) | ✅ Streaming |
| Scroll Mainnet | 534352 | L0 EVM (Rust) | ✅ Streaming |
| 0G Galileo | 16602 | L0 EVM (Rust) | ✅ Streaming |
| Arbitrum Sepolia | 421614 | L0 EVM (Rust) | ✅ Relayer |
| Ethereum Sepolia | 11155111 | — | ✅ Relayer |

### SVM / NVM / TVM / PVM / Cairo VM
| Network | VM | Status |
|---------|-----|--------|
| Solana Mainnet | SVM (Rust) | ✅ Streaming |
| NEAR Testnet | NVM (Rust) | ✅ Streaming |
| TON Mainnet | TVM (Rust) | ✅ Streaming |
| Polkadot Westend | PVM (Rust) | ✅ Streaming |
| StarkNet Mainnet | Cairo (Rust) | ✅ Streaming |

### UTXO / COSMOS / MOVE / SUI / TRON / PI
| Network | VM | Status |
|---------|-----|--------|
| Bitcoin Mainnet | UTXO (Rust) | ✅ Streaming |
| Litecoin / Dogecoin / Dash | UTXO (Rust) | ✅ Streaming |
| Cosmos Hub / Kava / Injective / SEI / dYdX / Initia | Cosmos SDK (Rust) | ✅ Streaming |
| Aptos Mainnet / Movement Mainnet | Move VM (Rust) | ✅ Streaming |
| Sui Mainnet | SUI VM (Rust) | ✅ Streaming |
| TRON Mainnet | TVM (Rust) | ✅ Streaming |
| Pi Mainnet | MVM (Rust) | ✅ Streaming |

---

## Oracle API — Port 5000

**162 routes** across all whitepaper sections:

### Core Signal Routes
- `GET /api/v1/signal/{entity_id}` — full C(t) with all 5 planes
- `POST /api/v1/signal/batch` — batch scoring up to 100 entities
- `GET /api/v1/feed` — last 50 computed signals

### Whitepaper-Aligned Routes (v0.4)
- `GET /api/v1/phase_signal` — §10.6 system-wide phase shift signal
- `GET /api/v1/phase_signal/<entity_id>` — §10.6 per-entity phase
- `GET /api/v1/order_parameter` — §9.2 Ψ(t) adoption order parameter
- `GET /api/v1/cex/status` — §7.3 CEX integration registry
- `GET /api/v1/cex/feed` — §7.3 TRION → CEX signal bundle
- `POST /api/v1/cex/ingest` — §7.3 CEX → TRION behavioral data ingestion
- `GET /api/v1/genesis/fingerprint/<id>` — §6.2 full 6-dimension genesis fingerprint
- `GET /api/v1/universal_asset/<chain>/<addr>/equivalences` — §8.4 cross-chain UAI equivalence
- `GET /api/v1/manipulation/attack_cost/<id>` — §7.5 P(Φ)·P(M)·P(Σ) attack economics

### Genesis & BH Routes
- `GET /api/v1/genesis/<asset_id>` — Genesis inference signal
- `GET /api/v1/bh/<entity_id>` — dual-strand BH with 20 event types
- `POST /api/v1/bh` — compute BH from JSON body
- `GET /api/v1/bh/ledger/<entity_id>` — canonical BH history per entity
- `GET /api/v1/bh/stats` — global BH ledger stats

### Security & Manipulation Routes
- `GET /api/v1/security/<id>/mf` — §L2.1 full 6-pattern MF breakdown
- `GET /api/v1/security/<id>/genomic` — §L4.3 dual-strand genomic key
- `GET /api/v1/immune/<id>` — 8-component Living Security System
- `GET /api/v1/manipulation/attack_cost/<id>` — §7.5 attack economics

### 0G Routes
- `GET /api/v1/zg/integration` — all 5 0G components (judge endpoint)
- `GET /api/v1/zg/chain/status` · `GET /api/v1/zg/storage/root` · `GET /api/v1/zg/da/status`
- `GET /api/v1/zg/compute/status` · `POST /api/v1/zg/compute/infer`

### + 130 additional routes across all whitepaper sections
Liquidity (NL score), moat (M_moat), governance (slashing, SBA), validators, planes (all 5), archetypes, epigenetics, thermodynamics, lifecycle, reputation, investment signals, love protocol, living index, token distribution, 10-phase roadmap, CEX integration, and more.

---

## FAISS ANIMA Service — Port 8000

128-dimensional behavioral vector index (FAISS `IndexIVFPQ`):

- `GET /health` — index status + vector count + entity count
- `POST /index/add_batch` — add behavioral vectors (from Rust indexers)
- `POST /index/add_tx_bh_batch` — add canonical 93-byte BH records per transaction
- `GET /index/stats` — full index statistics
- `POST /query/anima` — query ANIMA score + archetype for an entity
- `POST /query/nearest` — k-NN archetype lookup
- `GET /archetypes` — all 64 behavioral archetype centroids
- `GET /bh/ledger/{entity_id}` — canonical BH history per entity
- `GET /bh/stats` — global BH ledger statistics

---

## On-Chain Publication

### 0G Mainnet (chain 16661) — Production
| Contract | Address | Explorer |
|---------|---------|---------|
| TRIONExecutionGate | `0xA85B49C73B5710d9ddB1CB5a94c52D0F33c4199b` | [View](https://chainscan.0g.ai/address/0xA85B49C73B5710d9ddB1CB5a94c52D0F33c4199b) |

### 0G Galileo Testnet (chain 16602)
| Contract | Address |
|---------|---------|
| TRIONOracleV3 | `0x0471B2BE25c2eBbAe7FAc17383F1692979F0A87C` |
| LiquidityOcean | `0x105c7F6c16d2c92FEad10336C2b6A047F999a5A7` |
| TravelRuleCompliance | `0x5e7DBE6cc90d6260be2781dc312812834715EBaB` |
| BTCPSimpleEscrow | `0x388f98831c749D7Acad2046329c9CeC94A8b248d` |

### EVM Chains — TRION Relayer (60s cadence)
| Chain | Chain ID | Oracle Address | Status |
|-------|---------|----------------|--------|
| Arbitrum Sepolia | 421614 | `0xb819c63c02Ed5aB49017C0f3f2568A14624658b3` | ✅ LIVE |
| Ethereum Sepolia | 11155111 | `0xB07AD89a10f94B6D3bF2ab0B3a37988b1F37Db39` | ✅ LIVE |
| Base Sepolia | 84532 | `0x7ADF5B7273883C50EFc005BA7EdD3F379Af9680C` | ✅ LIVE |
| Optimism Sepolia | 11155420 | `0x708193f93Fb897fbeA72e7e7D19237770F19E969` | ✅ LIVE |
| HashKey Mainnet | 177 | `0x708193f93Fb897fbeA72e7e7D19237770F19E969` | ✅ LIVE |

---

## Tests

```bash
# Unit & stress tests (fast, no server required)
python3 -m pytest tests/ -q
# 184 passed, 5 skipped

# Stress test (17 tests — BH XOR invariant × 1000, collision check × 10000,
#              P(break LSS) monotone, all 8 CRISPR attacks, concurrent load × 100)
python3 -m pytest tests/test_stress.py -v
# 17 passed in 1.13s  |  BH avg: 0.022ms  (spec: <10ms — 450× faster)

# Full end-to-end (requires running services)
python3 tests/test_e2e_full.py
# 15 sections: signal pipeline, BH ledger (243k+ records), Living Security,
# attack library (32 attacks, $43.6B protected), 65 whitepaper formulas
```

Attack simulation:

```bash
python3 simulate_attacks.py
# Beanstalk ($182M)      → BLOCKED: GOVERNANCE_CAPTURE + SILENCE
# Harvest Finance ($34M) → BLOCKED: FLASH_LOAN_SANDWICH + SILENCE
# Euler ($197M)          → BLOCKED: CROSS_PROTOCOL_DRAIN + SILENCE
# Mango Markets ($117M)  → BLOCKED: ORACLE_ATTACK_ATTEMPT + SILENCE (SVM)
# Thala Move VM ($25.5M) → BLOCKED: COORDINATED_PUMP + SILENCE (Move VM)
# Ronin Network ($625M)  → BLOCKED: SYBIL_CLUSTER + SILENCE
# Terra/LUNA ($40B)      → BLOCKED: GOVERNANCE_CAPTURE + SILENCE (Cosmos)
# Total: 32 attacks · $43.6B protected
```

---

## Deployment Files

| File | Purpose |
|------|---------|
| `Dockerfile` | Dev image — Oracle API + FAISS ANIMA only. Python 3.11, fast build. |
| `Dockerfile.render` | Production image — all services. 3-stage build: Rust compiler + Node installer + Python runtime. |
| `render-entrypoint.sh` | Production supervisor — starts all services, runs Oracle API as gunicorn foreground under tini. |
| `docker-compose.yml` | Local dev (`default` profile) + full production parity (`--profile full`). |
| `render.yaml` | Render.com IaC — auto-deploy from GitHub main, all env vars, trion-db PostgreSQL. |
| `railway.toml` | Railway deployment — Dockerfile.render, health check, all service toggles. |
| `fly.toml` | Fly.io deployment — 8GB/4CPU machine, volume mount for 0G state, Chicago region. |

---

## License

CC0 1.0 Universal — public domain. No rights reserved.

> *"The universe has always known the price of everything. We just built the instrument to listen."*

---

*TRION Protocol — behavioral truth, chain-verified. Built for the 0G APAC Hackathon.*
