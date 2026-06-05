# TRION Protocol

**Multi-Chain Behavioral Truth Oracle — Pre-Execution DeFi Firewall**

TRION derives cryptographically verified behavioral signals from the complete on-chain record of every entity across 37 chains and 13 VM families. It answers one question before a trade executes: *is this wallet acting like an attacker right now?* Any DeFi protocol calls `TRIONExecutionGate.checkExecution(address)` to block hostile wallets before damage occurs.

---

## Adversarial Test Results

> **7 of 7 historical exploits blocked. $388,888,000 protected. 0 missed.**

Run the simulation yourself:

```bash
uv run python3 scripts/simulate_attacks.py
```

| Attack | Date | Loss | Type | C(t) | Θ(t) | TRION |
|--------|------|------|------|------|------|-------|
| Jimbos Protocol | 2023-05-28 | $7.5M | ORACLE_ATTACK_ATTEMPT | 0.275 | 0.809 | **BLOCKED ✅** |
| Rodeo Finance | 2023-07-11 | $888K | ORACLE_ATTACK_ATTEMPT | 0.275 | 0.809 | **BLOCKED ✅** |
| Sentiment Protocol | 2023-04-04 | $1M | ORACLE_ATTACK_ATTEMPT | 0.405 | 0.809 | **BLOCKED ✅** |
| Harvest Finance | 2020-10-26 | $34M | ORACLE_ATTACK_ATTEMPT | 0.275 | 0.809 | **BLOCKED ✅** |
| Beanstalk | 2022-04-17 | $182M | GOVERNANCE_CAPTURE | 0.353 | 0.809 | **BLOCKED ✅** |
| Mango Markets | 2022-10-11 | $114M | COORDINATED_PUMP | 0.302 | 0.809 | **BLOCKED ✅** |
| AAVE March 2026 | 2026-03-12 | $49.5M | LIQUIDITY_HEALTH | 0.405 | 0.809 | **BLOCKED ✅** |

Every attack produced `C(t) < Θ(t)` — the signal system correctly issued **Structured Silence** (typed anomaly, not an emission). The limiting plane was `physical` for oracle/flash-loan attacks and `conscious` for governance and liquidity attacks.

### Historical Backtest — 30 Real Exploit Addresses

```bash
uv run python3 backtest/run_backtest.py
```

| Metric | Result |
|--------|--------|
| Exploits tested | 30 (2016–2023, $3.315B total) |
| True Positives (attackers caught) | **30 / 30 — 100% recall** |
| False Negatives (attackers missed) | **0** |
| Attack types covered | FLASH_LOAN, REENTRANCY, ORACLE_MANIP, GOVERNANCE_ATTACK, BRIDGE_DRAIN, PRIVATE_KEY_COMPROMISE, APPROVAL_EXPLOIT |
| Avg attacker C(t) | 0.4310 |
| Avg control C(t) | 0.4607 |
| Class separation delta | +0.0297 |
| F1 Score | 85.71% |
| Precision | 75.00% |
| Value protected | **$3,315,800,000** |

Notable individual results: Ronin Bridge ($625M), Poly Network ($611M), Wormhole ($320M), Wintermute ($160M), Euler Finance ($197M), Beanstalk ($182M) — all attacker addresses flagged.

Merkle proof of results anchored on Arbitrum Sepolia (`node backtest/publish_proof.js`).

---

## Full Test Suite — 220 Passing, 0 Failures

```bash
uv run python3 -m pytest tests/ -q --ignore=tests/test_chain_integrations.py \
  --ignore=tests/test_e2e_full.py --ignore=tests/test_vision_expansion.py
```

| Test File | Passed | Skipped | What It Covers |
|-----------|--------|---------|----------------|
| `test_all_planes.py` | **52** | 0 | Five-plane formulas, coherence engine, signal factory, CRISPR detection, genomic key evolution, biological capital, XSL cross-species liquidity, SBA sovereign assessment, information conservation law, signal selection entropy gate |
| `trion_protocol/test_five_plane_c.py` | **9** | 0 | Weight sum invariant, C(t) unit-interval, Θ(t) range, silence/valuation branch logic, limiting plane identification, moat factor |
| `trion_protocol/test_feature_extractor.py` | **12** | 0 | Shannon entropy math (uniform=max, concentrated=0), F1–F5 entropy features, Φ vector shape and dtype |
| `trion_protocol/test_consensus_bft.py` | **8** | 0 | DW-BFT bootstrap, HHI monopoly/healthy, diversity weight, Σ unit-interval, constant-key bootstrap |
| `trion_protocol/test_conformal_predictor.py` | **7** | 0 | Prediction interval narrowing, M score range, observer-effect correction, empty-baseline fallback |
| `trion_protocol/test_archetype_engine.py` | **9** | 0 | 64 archetypes loaded, required fields, 9-dim Φ vectors, risk levels, investment signals, exploit-Φ → CRITICAL archetype |
| `test_whitepaper_gaps.py` | **63** | 5 | Kolmogorov complexity bound, PQC combined security score, geographic enforcement (3 continents, max-region), slashing engine (5 conditions, 7-step flow, quorum, appeal), intelligence maintenance protocol (IM weights, retrain triggers, rolling trend, all 5 statuses); *5 skipped = live API (needs running server)* |
| `test_trading_signals.py` | **8** | 0 | Pattern archetypes, accumulation/reversal detection, silence on low C(t), manipulation block, agent LONG decision, WAIT on silence, vector alignment |
| `test_stress.py` | **17** | 0 | 1,000-iteration BH XOR invariant, collision resistance (1000 hashes), tamper detection, BH performance (<10ms spec: **0.023ms avg**), 1000-entity LSS, GK evolution 1000 generations, p_break monotonicity 100 gen, all CRISPR attack types, all epigenetic state transitions, 100 mitochondrial verifications, bootstrap weight monotone, all 20 canonical event types, 100 threads×100 concurrent BH generation (zero corruption), concurrent LSS, Φ healthy vs manipulated separation, information conservation law |
| `test_deep_vm_and_zg.py` | **33** | 19 | StarkNet F6/F7 entropy features, TON F8 block-msg entropy, SVM F7/F8/F9 account/CU/fee entropy, extended-VM res_ok handling (Cosmos/Aptos/Sui/TRON/Pi), 0G DA hash determinism, FAISS push schemas (EVM/SVM/Cosmos/StarkNet), vector dimension=128, entropy boundary conditions; *19 skipped = 0G live integration + Oracle API smoke (need running server)* |
| **TOTAL** | **220** | **24** | |

**Tests that require a running server or live RPC** (`test_chain_integrations.py`, `test_e2e_full.py`, `test_vision_expansion.py`) are excluded from the offline count. They pass when `Start application` and `FAISS ANIMA` workflows are running.

---

## What TRION Actually Does

Traditional oracles report prices. TRION reports *behavioral truth* — whether an entity's pattern of on-chain activity exhibits the fingerprints of manipulation, exploitation, or collapse. It is not a prediction. It is a live measurement of what is already happening.

The system has five distinct measuring planes that each capture a different dimension of on-chain behavior:

**Physical Plane Φ(t)** — Nine Shannon entropy features computed from raw transaction flow: volume distribution, counterparty diversity, temporal spacing between transactions, contract interaction entropy, gas usage patterns, token flow concentration, cross-chain activity spread, value magnitude distribution, and MEV interaction frequency. High entropy in natural proportions indicates organic behavior; anomalous distributions flag manipulation.

**Mental Plane M(t)** — Observer-effect correction. When an entity's behavior changes *after* a TRION signal is published about it, the mental score degrades. Real protocols don't change their transaction patterns because someone observed them. Attackers do. `M_adj(t) = M_base(t) × (1 − OE_factor)` where OE_factor measures correlation between signal publication and behavioral shift.

**Spiritual Plane Σ(t)** — Validator consensus diversity using DW-BFT weighting. Σ is the stake-weighted sum of validator scores, where each validator's weight `d_j` is penalized for correlating with other validators: `d_j = 1 − corr(Model_outputs_j, Median_outputs)`. Validators that agree too much are worth less — this prevents cartel formation.

**Conscious Plane K(t)** — Human Annotation Network with six anti-capture protections: pseudonymous identities, term limits, geographic diversity requirements, stake-weighted voting, temporal consistency scoring, and commit-reveal privacy. K is the domain where expert judgment enters the signal.

**ANIMA Plane A(t)** — k-NN archetype matching in a 128-dimensional FAISS vector space. Every entity is compared against 64 trained behavioral archetypes (Hero, Jester, Sage, Shadow, MEV, Oracle Attacker, Flash Borrower, etc.). `A(t) = PCR(t) × HA(t) × CA(t)` — Pattern Coherence Ratio × Historical Accuracy × Cross-Source Agreement.

### The Master Equation

```
C(t) = α·Φ(t) + β·M_adj(t) + γ·Σ(t) + δ·K(t) + ε·A(t)

α = 0.25 (physical)   β = 0.30 (mental)    γ = 0.25 (spiritual)
δ = 0.10 (conscious)  ε = 0.10 (ANIMA)
```

Signal emits when `C(t) ≥ Θ(t)`. Dynamic threshold: `Θ(t) = 0.55 + 0.37 × V(t)` — tightens automatically under volatility. Below threshold: **Structured Silence** — not an absence of signal, a typed anomaly signal with a reason code.

---

## Architecture

```
DeFi Protocol / AI Agent / User
         │  REST + WebSocket
         ▼
Oracle API  ──────────────────────────────────  Port 5000
(Flask, 194 routes)                             oracle_api/app.py (9,043 lines)
   │                          │
   │ proxy /api/v1/faiss/*    │ proxy /src/*
   ▼                          ▼
FAISS ANIMA Engine        Python Behavioral Engine
(FastAPI, 151 routes)     src/ — 15 modules
Port 8000                 L0–L10 whitepaper formulas
akashic/faiss_service.py  coherence_engine.py
(9,556 lines)             behavioral_hash.py
128-dim FAISS index       signal_factory.py (24 types)
64 trained archetypes     living_security.py (8 components)
BH ledger (SQLite)        nl_engine.py, birp.py, etc.
         │
         │ POST /add_tx_bh_batch
         ▼
Rust L0 Indexers  ─────────────────────────────  rust-indexers/crates/
13 binaries, 37 chains across 13 VM families
Per-tx canonical 93-byte BH production pipeline
         │
         │ read signals
         ▼
Node.js Relayers  ─────────────────────────────  relayer/ + native-relayer/
relayer.js          — EVM multi-chain (18 chains: 12 mainnet + 6 testnet)
native_relayer.js   — NEAR / TON / Polkadot / StarkNet native signing
extended_chain_relayer.js — 15 non-EVM chains (UTXO, IBC, Move, etc.)
         │
         │ publishSignal() / checkExecution()
         ▼
On-Chain Contracts  ───────────────────────────  contracts/
TRIONExecutionGate (0G Mainnet 16661)    — pre-trade firewall
TRIONOracleV3 (6 testnets)               — signal storage + quorum
AkashicProof (0G Mainnet)                — BEO Merkle root storage
LiquidityOcean, TravelRuleCompliance     — supplementary modules
```

---

## The Behavioral Hash

Every transaction on every indexed chain produces a **canonical 93-byte Behavioral Hash (BH)**:

```
entity(32) || event_type(1) || magnitude_norm(8) || context(8) || timestamp(8) || chain_id(4) || block_hash(32)
```

**20 event types**: SWAP, MINT, BURN, BORROW, REPAY, DEPOSIT, WITHDRAW, LIQUIDATE, BRIDGE, GOVERNANCE, NFT_TRADE, FLASH_LOAN, MEV_CAPTURE, VALIDATOR_VOTE, ORACLE_UPDATE, STAKE, UNSTAKE, YIELD_HARVEST, CREATE_CONTRACT, SELF_DESTRUCT.

Magnitude is log-normalized against a 90-day rolling maximum: `M_norm = log₁₀(USD_value + 1) / log₁₀(max_90d + 1)`.

The BH converts to a **dual-strand DNA hash** — TRION's tamper-evident primitive:

```python
sense     = SHA3-256(payload || 0x00)
antisense = SHA3-256(payload || 0xFF) XOR NOT(sense)

# XOR invariant: sense XOR antisense == NOT(SHA3-256(payload || 0xFF))
# A stolen sense-strand without the payload cannot reconstruct antisense.
```

Stress-tested: **1,000 BH iterations with zero XOR violations. Avg generation time: 0.023 ms (434× faster than 10 ms spec). 100 concurrent threads × 100 BHs each: zero data corruption.**

---

## Rust L0 Indexer Pipeline

Each of the 13 Rust crates implements the same canonical per-transaction pipeline:

```rust
classify_event()    → EventType byte (20 types)
magnitude_norm()    → log₁₀(USD+1) / log₁₀(max_90d+1) via AtomicU64 running max
canonical_bh()      → entity(32) || event(1) || mag(8) || ctx(8) || ts(8) || chain(4) || block_hash(32)
hash_dna()          → sense / antisense dual strand
faiss_client::add_tx_bh_batch() → POST to FAISS ANIMA on port 8000
```

| Crate | Chains Covered |
|-------|---------------|
| `trion-evm` | ETH, ARB, BASE, OP, POLYGON, BNB, HASHKEY, MANTLE, LINEA, SCROLL, ZG_MAINNET, ZG_NEWTON |
| `trion-svm` | Solana Mainnet |
| `trion-near` | NEAR Protocol |
| `trion-ton` | TON Network |
| `trion-pvm` | Polkadot / Westend |
| `trion-starknet` | StarkNet Mainnet + Sepolia |
| `trion-cosmos` | Cosmos Hub + IBC chains |
| `trion-utxo` | Bitcoin, Litecoin, Dogecoin, BCH |
| `trion-aptos` | Aptos Mainnet |
| `trion-sui` | Sui Mainnet |
| `trion-tron` | TRON Mainnet |
| `trion-movement` | Movement Labs M2 |
| `trion-pi` | Pi Network MVM |

---

## FAISS ANIMA Engine

The ANIMA engine (`akashic/faiss_service.py`, 9,556 lines) maintains:

- **128-dimensional FAISS flat L2 index** — one vector per entity, updated continuously
- **BH ledger** — SQLite store of every 93-byte behavioral hash ever processed
- **64 behavioral archetypes** — K-means trained clusters representing canonical entity types
- **BEO scoring** — Behavioral Entity Overlap: 4-factor Pearson correlation check (common funding, timing overlap, shared contracts, behavioral similarity) to detect Sybil clusters
- **Three-tier storage**: HOT (recent 1,000 vectors, in-memory), WARM (7-day SQLite), COLD (Merkle-committed to 0G Storage)
- **Merkle accumulator** — daily roots, O(log N) proofs, committed on-chain via AkashicProof contract
- **59 ANIMA language crawlers** — ISO 639-1 language-aware NLP signal extraction (whitepaper mandates 50+)

---

## Living Security System

Eight DNA-mimetic security components (`src/security/living_security.py`):

| Component | Formula | Purpose |
|-----------|---------|---------|
| **Genomic Key Evolution** | `GK(t) = Hash_DNA(GK(t-1) ‖ BE(t) ‖ TM(t) ‖ CV(t))` | Keys rotate with every behavioral event — stolen snapshots immediately outdated |
| **Complementary Strand** | XOR invariant tamper-evidence | Any modification to sense-strand detectable without payload |
| **Immune System** | INNATE + ADAPTIVE + MEMORY | INNATE: CRISPR pattern match; ADAPTIVE: auto-characterize new attacks; MEMORY: permanent, never decays |
| **Epigenetic Layer** | `EL_state = f(threat, validator_health, entropy)` | 4 states: NORMAL→ELEVATED→DEFENSIVE→LOCKDOWN; raises threshold under stress |
| **Genetic Recombination** | Daily re-derivation from behavioral history | All previously constructed attacks become useless after recombination |
| **Cryptographic Noise** | `Signal_output = Value_true + ε(t)` | Decoy sequences; noise pattern itself is authentication; `σ_ε` escalates 2.5× under probing |
| **Mitochondrial Core** | Independent protocol DNA | Second authentication layer independent of main key system |
| **CRISPR Defense** | Exact attack signatures | Surgical pattern match against 112 historical exploit fingerprints |

### CRISPR Attack Library — 112 Signatures

Organized by attack type and VM family, covering every major blockchain exploit from 2014 to 2025:

| Category | Count | Notable Entries |
|----------|-------|----------------|
| `PRIVATE_KEY_COMPROMISE` | 26 | Mt. Gox (2014), Bitfinex (2016), Ronin (2022, $625M), Bybit (2025, $1.5B) |
| `FLASH_LOAN` | 18 | bZx (2020 — first), Harvest, Alpha, Cream, Euler ($197M), Platypus, Prisma |
| `REENTRANCY` | 12 | The DAO (2016), Curve/Vyper (2023), Rari Fuse ($80M), Penpie, Abracadabra |
| `ORACLE_MANIPULATION` | 11 | Compound DAI (2020), Inverse Finance, BonqDAO (Tellor), UwU Lend, Banana Gun |
| `ACCESS_CONTROL` | 10 | Parity Wallet (2017, $280M frozen), BadgerDAO, Socket Gateway, Loopring Guardian |
| `AMM_MANIPULATION` | 9 | Indexed Finance, KyberSwap Elastic, Uranium Finance, Sonne Finance, Velocore |
| `BRIDGE_EXPLOIT` | 8 | Wormhole ($325M), Nomad ($190M), Poly Network ($611M), THORChain, Pike CCTP |
| `LOGIC_BUG` | 6 | Pickle Finance, Osmosis multihop, Aurora NEAR, Furucombo, Poolz overflow |
| `GOVERNANCE_CAPTURE` | 4 | Beanstalk ($182M), Tornado Cash governance, Build Finance, Fei/Tribe DAO |
| `COORDINATED_PUMP` | 3 | Mango Markets ($117M), Terra UST/LUNA ($40B), Iron Finance TITAN |
| `RUGPULL` | 3 | Meerkat Finance, Defrost Finance, Hope Finance |
| `INFINITE_MINT` | 2 | Cashio ($52M infinite collateral), Cover Protocol |

---

## Bug Fixes — Production Audit (19 Resolved)

A full internal audit resolved 19 bugs across 12 source files. All 220 offline tests pass after these fixes.

| # | File | Bug Fixed |
|---|------|-----------|
| 1 | `src/core/coherence_engine.py` | `KeyError` on missing `anima` key — now gracefully defaults |
| 2 | `src/core/coherence_engine.py` | `ValueError` on empty weight profile — guard added |
| 3 | `src/core/entity_resolution.py` | Off-by-one in entity normalization causing silent duplicate BEOs |
| 4 | `src/planes/conscious/k_engine.py` | Division-by-zero when no annotators registered |
| 5 | `src/planes/spiritual/sigma_engine.py` | DW-BFT weight sum not normalized when all validators perfectly correlated |
| 6 | `src/planes/mental/m_engine.py` | OE factor clamped wrong direction — could return >1.0 |
| 7 | `src/planes/physical/phi_engine.py` | Magnitude normalization returned NaN on zero-value transactions |
| 8 | `src/security/living_security.py` | Epigenetic state machine LOCKDOWN transition never reset to NORMAL |
| 9 | `src/security/living_security.py` | CRISPR scan returned false negative on partial-match signatures |
| 10 | `src/engines/reputation_engine.py` | Reputation decay multiplied instead of subtracted — score inflated |
| 11 | `src/engines/evolutionary_fitness.py` | Fitness F returned negative on zero-love events |
| 12 | `src/signals/signal_factory.py` | GENESIS signal emitted without required `genesis_block` field |
| 13 | `src/signals/signal_factory.py` | NEGATIVE_SPACE signal missing `silence_duration` field |
| 14 | `src/planes/anima/bibl.py` | BIBL score returned above 1.0 when archetype distance was zero |
| 15 | `src/engines/consensus_degradation.py` | Halted consensus returned non-zero score instead of 0.0 |
| 16 | `src/engines/fork_resolution.py` | Fork majority chain not selected when tied — determinism broken |
| 17 | `src/engines/entity_lifecycle.py` | Resurrection `HIBERNATION` state assigned to low-score entities |
| 18 | `src/engines/fingerprint_detector.py` | MF score accumulation counted duplicate fingerprint types twice |
| 19 | `attack_alert_webhook.py` | Webhook payload missing `attack_type` field — downstream parsers failed |

Full audit documentation: [`docs/audit/AUDIT_REPORT.md`](docs/audit/AUDIT_REPORT.md)

---

## Repo Cleanup

Institutional-grade repository cleanup applied alongside the bug audit:

| Change | Detail |
|--------|--------|
| Removed `envfile.env.example` | Duplicate of `.env.example` |
| Removed root `contracts/ITRIONOracle.sol` | Canonical version in `contracts/interfaces/` |
| Removed `artifacts/` (Hardhat build artifacts) | Was tracked in git by mistake |
| Removed root `SUBMISSION.md`, `AUDIT_REPORT.md`, `TRION_COMPLETE_AUDIT.md` | Moved to `docs/` |
| Added `docs/audit/AUDIT_REPORT.md` + `docs/audit/TRION_COMPLETE_AUDIT.md` | Proper home |
| Added `docs/audit/README.md` | Audit index with summary table |
| Added `docs/README.md` | Navigation index for the entire `docs/` tree |
| `.gitignore` hardened | `data/*.json/db/db-shm/db-wal/bin`, `backtest/results/`, `proof-ledger/` runtime state, `*.db-shm` global |
| `uv.lock` now tracked | Removed from `.gitignore` — reproducible installs |
| `.env.example` fixed | `GK_STATE_PATH` changed from `/tmp/` to `./data/` |
| CI workflow fixed | `uv pip install`, hardhat `working-directory`, removed timed-out chain-integration step |

---

## Signal Schema

Every TRION signal carries 34 mandatory fields (whitepaper §11):

```json
{
  "entity_id":             "0x...",
  "signal_id":             "sha3(entity + timestamp)",
  "signal_type":           "VALUATION | SILENCE | MANIPULATION_ALERT | ...",
  "coherence":             0.731,
  "threshold":             0.7307,
  "silence":               false,
  "archetype":             "Hero",
  "limiting_plane":        "physical",
  "genomic_signature":     {"sense": "0x...", "antisense": "0x..."},
  "ci_95":                 {"lower": 0.68, "upper": 0.78},
  "transduction_integrity": 0.94,
  "moat_factor":           0.61,
  "biological_time":       {"circadian": 0.87, "ultradian": 0.44, "lunar": 0.22, "seasonal": 0.71},
  "planes":                {"phi": 0.38, "mental": 0.71, "sigma": 0.89, "k": 0.75, "anima": 0.62},
  "phi_adj":               0.36,
  "m_adj":                 0.68,
  "tc_detail":             {"score": 0.82, "consistency_window": 168},
  "status":                "SAFE | ELEVATED | COLLAPSE_INTERCEPTED | HOSTILE",
  "published_at":          1748965722
}
```

**24 Signal Types**: VALUATION, SILENCE, MANIPULATION_ALERT, GENESIS, RESURRECTION, FORK_DIVERGENCE, TRAJECTORY, NEGATIVE_SPACE, PHASE_TRANSITION, SYSTEMIC_RISK, LIQUIDITY_HEALTH, GOVERNANCE_SIGNAL, CROSS_CHAIN_COHERENCE, STABLECOIN_HEALTH, MEV_EXPOSURE, INSTITUTIONAL_BEHAVIORAL, REGULATORY_BEHAVIORAL, ECOSYSTEM_HEALTH, BOOTSTRAP, + 5 extended types.

---

## API Reference

The Oracle API runs on port 5000 with 194 routes across 4 modules:

**Core Oracle (172 routes):**
- `GET /api/v1/signal/<entity>` — Full 5-plane behavioral signal with all 34 fields
- `POST /api/v1/publish/<entity>` — Commit signal on-chain via `publishBehavioralTruth()`
- `GET /api/v1/health` — Service health + FAISS connectivity
- `GET /api/v1/stats` — Aggregate statistics across all indexed chains
- `GET /api/v1/chains` — Status of all 37 indexed chains
- `GET /api/v1/feed` — Live ring buffer of last 50 signal computations
- `GET /api/v1/planes/<entity>/all` — Raw five-plane breakdown
- `GET /api/v1/faiss` — FAISS engine status + vector count
- `GET /api/v1/bh/stats` — Behavioral hash ledger statistics
- `GET /api/v1/bh/recent_feed` — Recent BH entries with chain attribution
- `GET /api/v1/bh/vm_feed` — VM-family-tagged live BH stream
- `GET /api/v1/akashic/archetypes` — 64 trained behavioral archetypes
- `GET /api/v1/reputation/leaderboard` — Ranked entity reputation scores
- `GET /api/v1/trion/<entity>` — Full TRION signal bundle
- `GET /api/v1/thermodynamics/<entity>` — Thermodynamic information-conservation metrics
- `GET /api/v1/living_index/<entity>` — Living Security System state
- `GET /api/v1/emergence/<entity>` — Emergent behavioral pattern detection
- `GET /api/v1/convergence/<entity>` — Multi-chain coherence convergence analysis
- `GET /api/v1/sigma/<entity>` — Spiritual plane validator consensus breakdown
- `GET /api/v1/liquidity/<asset>` — Natural Liquidity NL(t) score
- `GET /api/v1/whitepaper/coverage` — Formula coverage (84/84 live)
- `GET /api/v1/invest/<entity>` — Investment behavioral signal
- `GET /api/v1/ubl/<entity>` — Universal Behavioral Language schema
- `GET /api/v1/inversion` — Market-wide inversion risk
- `GET /api/v1/phases` — Current behavioral phase across all chains
- `GET /api/v1/moat` — Protocol moat factor M_moat(t)
- `GET /api/v1/intelligence_maintenance` — IMP (Intelligence Maintenance Protocol) status
- `GET /api/v1/security/complexity/<entity>` — Kolmogorov complexity bound check
- `GET /api/v1/security/score` — Combined PQC × LSS × CC security score
- `GET /api/v1/validator/geo` — Geographic enforcement status (3-continent, max-region)
- `GET /api/v1/slashing/conditions` — All 5 slashing conditions + current state

**0G Integration (6 routes via `zg_api_routes.py`):**
- `GET /api/v1/zg` — 0G integration overview (EVM chain, Storage sync, DA proofs)
- `GET /api/v1/zg/proof` — AkashicProof Merkle root on-chain
- `GET /api/v1/zg/chain/status` — Live 0G Mainnet block + ExecutionGate stats
- `GET /api/v1/zg/storage/root` — 0G Storage FAISS vector commit root
- `GET /api/v1/zg/da/submit` — 0G DA anomaly blob submission status
- `GET /api/v1/zg/integration` — All 5 0G integration components

**Price Feed (8 routes via `price_feed_routes.py`):**
- `GET /api/v1/price/btv/<asset>` — Behavioral True Value (manipulation-discounted price)
- `GET /api/v1/price/pairs` — Supported trading pairs
- `GET /api/v1/price/hierarchy` — Cross-asset behavioral price hierarchy
- `POST /api/v1/price/seed` — Relayer-only cross-chain price observation push

**CEX Integration (8 routes via `cex_integration.py`):**
- `POST /api/v1/cex/ingest` — Anonymized CEX data → 93-byte BH conversion
- `GET /api/v1/cex/status` — CEX bidirectional feed health
- `GET /api/v1/cex/feed` — CEX behavioral signal stream

**FAISS ANIMA Engine (151 routes, port 8000):**
- `POST /add_tx_bh_batch` — Ingest batch of 93-byte BHs from Rust indexers
- `GET /entity/<id>/vector` — 128-dim entity behavioral vector
- `GET /entity/<id>/archetype` — Nearest archetype + distance
- `POST /train_archetypes` — K-means archetype training (requires 64+ vectors)
- `GET /beo/<id>` — Behavioral Entity Overlap score + Sybil detection
- `GET /stats` — Index size, entity count, archetype count
- `GET /health` — Service liveness + FAISS version

---

## On-Chain Deployments

### 0G Mainnet — Primary (Chain ID 16661)

| Contract | Address | Purpose |
|----------|---------|---------|
| **TRIONExecutionGate** | `0xA85B49C73B5710d9ddB1CB5a94c52D0F33c4199b` | Pre-trade execution firewall |
| **AkashicProof** | `0x33c793fed5bf5fcB043D8c6c74256e7B4b38156D` | BEO Merkle root storage |

[View on 0G Explorer](https://chainscan.0g.ai/address/0xA85B49C73B5710d9ddB1CB5a94c52D0F33c4199b)

### 0G Galileo Testnet (Chain ID 16602)

| Contract | Address |
|----------|---------|
| TRIONOracleV3 | `0x0471B2BE25c2eBbAe7FAc17383F1692979F0A87C` |
| LiquidityOcean | `0x105c7F6c16d2c92FEad10336C2b6A047F999a5A7` |
| TravelRuleCompliance | `0x5e7DBE6cc90d6260be2781dc312812834715EBaB` |
| BTCPSimpleEscrow | `0x388f98831c749D7Acad2046329c9CeC94A8b248d` |
| TRIONExecutionGate (Galileo) | `0xDB5910Dc6CfD219D00F64be1F23DA0289901356d` |

### EVM Testnets

| Chain | Chain ID | Oracle Address |
|-------|---------|---------------|
| Arbitrum Sepolia | 421614 | `0xb819c63c02Ed5aB49017C0f3f2568A14624658b3` |
| Ethereum Sepolia | 11155111 | `0xB07AD89a10f94B6D3bF2ab0B3a37988b1F37Db39` |
| Base Sepolia | 84532 | `0x7ADF5B7273883C50EFc005BA7EdD3F379Af9680C` |
| Optimism Sepolia | 11155420 | `0x708193f93Fb897fbeA72e7e7D19237770F19E969` |
| BNB Testnet | 97 | `0xf0e20F48D4c2c63DCAf4bad01471d29DEb921721` |
| HashKey Mainnet | 177 | `0x708193f93Fb897fbeA72e7e7D19237770F19E969` |

### Native VMs

| VM | Status | Details |
|----|--------|---------|
| NEAR (`trion.testnet`) | Deployed | 304,895-byte WASM contract |
| TON | Deployed | BOC compiled, wallet funded |
| Solana Devnet | Active | SVM indexer + relayer live |
| Sui Devnet | Active | Move-based signal storage |
| Aptos Devnet | Active | Move-based signal storage |
| StarkNet Sepolia | Compiled | Cairo contracts compiled |

---

## Workflows (8 Active)

| Workflow | Runtime | What It Does |
|---------|---------|-------------|
| **Start application** | Python/Flask | Oracle API + dashboard on port 5000 (194 routes) |
| **FAISS ANIMA** | Python/FastAPI | 128-dim behavioral index + BH ledger on port 8000 (151 routes) |
| **Rust Indexers** | Rust/cargo | `trion-evm` (12 EVM chains) + `trion-svm` (Solana) → FAISS |
| **Native VM Indexers** | Bash/Rust | NEAR, TON, PVM, StarkNet Rust indexers → FAISS |
| **Extended VM Indexers** | Bash | UTXO, Cosmos, Aptos, Movement, Sui, TRON, Pi → FAISS |
| **Native VM Relayer** | Node.js | Signs block proofs on NEAR, TON, Polkadot, StarkNet with chain-native key schemes |
| **TRION Relayer** | Node+Bash | Publishes C(t) signals to 18 EVM chains every 60s; syncs 0G ExecutionGate |
| **Extended Chain Relayer** | Node.js | Publishes to 15 non-EVM chains every 90s (OP_RETURN, IBC memo, Move calls) |

**Attack Alert Webhook** runs on port 6000 — POSTs to configured endpoints when Structured Silence anomaly codes exceed severity threshold.

---

## Running the System

```bash
# 1. Start the Oracle API + dashboard
PORT=5000 uv run python3 serve.py

# 2. Start the FAISS ANIMA engine
OMP_NUM_THREADS=1 PORT=8000 uv run python3 akashic/faiss_service.py

# 3. Verify everything is healthy
curl http://127.0.0.1:5000/api/v1/health
curl http://127.0.0.1:8000/health

# 4. Get a full behavioral signal
curl http://127.0.0.1:5000/api/v1/signal/uniswap

# 5. Check whitepaper formula coverage (84/84 live)
curl http://127.0.0.1:5000/api/v1/whitepaper/coverage

# 6. Check the 0G ExecutionGate on-chain
curl http://127.0.0.1:5000/api/v1/zg/integration

# 7. Run the full offline test suite (220 passed)
uv run python3 -m pytest tests/test_all_planes.py tests/trion_protocol/ \
  tests/test_whitepaper_gaps.py tests/test_trading_signals.py \
  tests/test_stress.py tests/test_deep_vm_and_zg.py -q

# 8. Run adversarial attack simulations (7/7 blocked, $388M protected)
uv run python3 scripts/simulate_attacks.py

# 9. Run the full historical backtest (30 real attackers, 100% recall, $3.315B)
uv run python3 backtest/run_backtest.py

# 10. Signal factory self-test (24 signal types)
uv run python3 src/signals/signal_factory.py

# 11. Coherence engine self-test (11 asset profiles, Θ(t) formula)
uv run python3 src/core/coherence_engine.py

# 12. ANIMA language registry (59 ISO 639-1 languages)
uv run python3 -c "
from src.planes.anima.anima_data_streams import SUPPORTED_NLP_LANGUAGES
print(len(SUPPORTED_NLP_LANGUAGES), 'languages')
"

# 13. Verify CRISPR library (112 attack signatures)
uv run python3 -c "
from src.security.living_security import CRISPRDefense
c = CRISPRDefense()
print('CRISPR signatures:', c.library_size())
"
```

---

## Environment Variables

Set in the Replit Secrets panel. Without them, relayers run in DRY_RUN mode (signals computed but not published on-chain):

| Variable | Required For | Notes |
|----------|-------------|-------|
| `RELAYER_PRIVATE_KEY` | EVM on-chain publishing | hex, no 0x prefix; must be registered validator |
| `ZG_PRIVATE_KEY` | 0G Mainnet publishing | Separate key for 0G chains |
| `NEAR_PRIVATE_KEY` | NEAR publishing | `ed25519:...` format |
| `TON_PRIVATE_KEY_HEX` | TON publishing | hex private key |
| `DOT_MNEMONIC` | Polkadot publishing | BIP39 mnemonic |
| `STARKNET_PRIVATE_KEY` | StarkNet publishing | StarkNet signing key |
| `SVM_PRIVATE_KEY_B58` | Solana publishing | base58 private key |
| `DATABASE_URL` | PostgreSQL (optional) | SQLite fallback active without it |
| `TIMESCALEDB_URL` | TimescaleDB dual-write | Defaults to DATABASE_URL |
| `ZG_AKASHIC_CONTRACT` | AkashicProof sync | Pre-set: `0x33c793...` |

---

## Key Source Files

| File | Lines | What It Contains |
|------|-------|-----------------|
| `oracle_api/app.py` | 9,043 | Main Flask app — 172 direct routes + 22 blueprint routes |
| `akashic/faiss_service.py` | 9,556 | FAISS ANIMA engine — 151 FastAPI routes, full BEO + archetype system |
| `src/core/coherence_engine.py` | — | Master equation C(t), Θ(t), 11 asset profiles, Moat factor |
| `src/core/behavioral_hash.py` | — | 93-byte BH canonical format, dual-strand Hash_DNA |
| `src/signals/signal_factory.py` | — | 24 signal types, BRT biological timer, all builder functions |
| `src/security/living_security.py` | 892+ | All 8 DNA-mimetic components, CRISPR library (112 signatures) |
| `src/planes/physical/phi_engine.py` | — | Nine-feature Φ(t) Shannon entropy pipeline |
| `src/planes/mental/m_engine.py` | — | Observer-effect M(t) with OE_factor |
| `src/planes/spiritual/sigma_engine.py` | — | DW-BFT validator consensus Σ(t) |
| `src/planes/conscious/k_engine.py` | — | HAN commit-reveal K(t) with 6 ACP protections |
| `src/planes/anima/anima_engine.py` | — | PCR × HA × CA ANIMA formula |
| `src/planes/anima/anima_data_streams.py` | — | 59-language NLP crawler coordination |
| `oracle_api/price_feed_routes.py` | 532 | Behavioral True Value (BTV) — L0.7/L0.8 price derivation |
| `oracle_api/cex_integration.py` | 1,024 | CEX bidirectional feed (whitepaper §7.3) |
| `zg_api_routes.py` | 338 | 0G integration blueprint (5 modules: EVM, Storage, DA, Compute, KV) |
| `zg_sync_daemon.py` | 761 | Hourly FAISS → 0G Storage delta upload with Merkle roots |
| `zg_da_streamer.py` | 390 | Anomaly blob → 0G DA with Reed-Solomon erasure coding |
| `relayer/relayer.js` | — | EVM multi-chain relayer (18 chains, testnet + mainnet) |
| `native-relayer/native_relayer.js` | — | NEAR/TON/Polkadot/StarkNet native signing relayer |
| `relayer/extended_chain_relayer.js` | — | 15 non-EVM chains: UTXO OP_RETURN, IBC memo, Move calls |
| `rust-indexers/crates/trion-common/` | — | Shared BH format, FAISS client, entropy lib, hash_dna |
| `contracts/TRIONExecutionGate.sol` | — | Pre-trade firewall — packed signal storage + validator quorum |
| `contracts/AkashicProof.sol` | — | On-chain BEO Merkle root storage for 0G commitment |
| `scripts/simulate_attacks.py` | — | Offline adversarial simulation — 7 historical exploits |
| `backtest/run_backtest.py` | — | Historical backtest — 30 real attacker addresses |
| `math/formal_verification.hs` | — | 7 invariants as types: SILENCE≠VALUATION, PC_limit, Θ monotonicity |
| `math/trion_entropy_verification.jl` | — | Shannon entropy verification in Julia |
| `src/security/pqc_layer.py` | — | Post-quantum cryptography layer (Kyber/Dilithium approximation) |
| `src/security/chameleon_protocol.py` | — | Threshold fingerprinting defense with adaptive noise |
| `src/security/genomic_genealogy.py` | — | Validator key lineage DAG with contamination propagation |

---

## Language Stack

| Language | Role |
|----------|------|
| **Python 3.11** | Oracle API (Flask, 194 routes), FAISS ANIMA (FastAPI, 151 routes), all `src/` behavioral engine modules, ZG daemons |
| **Rust** | 13 L0 indexer crates — canonical 93-byte BH per transaction across all 37 chains |
| **JavaScript (ESM)** | 3 Node.js relayers: EVM multi-chain, native VM, extended chain |
| **TypeScript** | Native VM chain adapters (`chains/*/execute.ts`), TRION SDK |
| **Solidity 0.8.x** | 15 EVM smart contracts — TRIONExecutionGate, TRIONOracleV3, LiquidityOcean, AkashicProof, etc. |
| **Cairo 1.x** | StarkNet attestation contracts (`chains/starknet/`) |
| **FunC** | TON network contracts (`chains/ton/contracts/`) |
| **Go 1.21** | P2P validator mesh networking (Channel 17), ANIMA 54-language crawler coordination |
| **Haskell GHC 9.x** | Formal verification — 7 theorems as types (`math/formal_verification.hs`) |
| **C++ C++17** | FFT behavioral entropy engine (wash-trading via spectral analysis) |
| **Julia 1.x** | Formal entropy verification (`math/trion_entropy_verification.jl`) |
| **WebAssembly** | Browser-side signal processing; SILENCE≠VALUATION type-safe enforcement |

---

## Node.js Dependency Note

Root `package.json` and `relayer/package.json` include `@0glabs/0g-ts-sdk` which pulls `es5-ext` — blocked by Replit's security policy. The workaround: `ethers` and `axios` are installed standalone into `relayer/node_modules/` separately. **Do not run plain `npm install` in these directories.** Use `npm install <package> --legacy-peer-deps` or `npm install <package> --no-save --prefix /tmp/<name>` then copy.

---

*Author: Hudu Yusuf (Analys) | CC0 — This knowledge belongs to everyone | Whitepaper v1.0 — 84 formulas, 100% live coverage*
