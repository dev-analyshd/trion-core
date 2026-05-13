# TRION Protocol — 0G APAC Hackathon Submission

## Track: Track 2 — Verifiable Finance

## One-Liner
TRION is a multi-chain behavioral truth oracle that uses all four 0G modules (Chain, Storage, DA, Compute) to provide cryptographically verified behavioral signals for DeFi security, manipulation detection, and AI agent safety — across 30 blockchain networks.

---

## Project Description

TRION (Truth, Reputation, Intelligence, Oracle Network) implements a 55-phase behavioral science whitepaper as a live, production-grade oracle system. It indexes behavioral entropy from 30 blockchain networks across 12 VM families, distills signals through a 128-dimensional FAISS ANIMA engine, and publishes verifiable behavioral truth on-chain via 5 smart contracts deployed on 0G Galileo.

Every signal produced by TRION is anchored to 0G's infrastructure: stored on 0G Storage, committed via 0G DA, verified through 0G Compute (TEE-verified inference), and settled on 0G Chain.

---

## 0G Integration — All 4 Modules

### 1. 0G Chain (Primary) ✅ LIVE
**5 contracts deployed on 0G Galileo (chain_id: 16602)**

| Contract | Address |
|----------|---------|
| TRIONExecutionGate | `0xDB5910Dc6CfD219D00F64be1F23DA0289901356d` |
| TRIONOracleV3 | `0x0471B2BE25c2eBbAe7FAc17383F1692979F0A87C` |
| LiquidityOcean | `0x105c7F6c16d2c92FEad10336C2b6A047F999a5A7` |
| TravelRuleCompliance | `0x5e7DBE6cc90d6260be2781dc312812834715EBaB` |
| BTCPSimpleEscrow | `0x388f98831c749D7Acad2046329c9CeC94A8b248d` |

**Live explorer:** https://chainscan-galileo.0g.ai/address/0xDB5910Dc6CfD219D00F64be1F23DA0289901356d

**Key feature:** `TRIONExecutionGate.checkExecution(address)` — AI agents and DeFi protocols call this before every trade. If an entity is classified as `STATUS_COLLAPSE` or `STATUS_HOSTILE` based on behavioral entropy, the transaction is blocked on-chain. 345+ signals published, 121 anomalies sealed.

**API endpoint:** `GET /api/v1/zg/chain/status`

---

### 2. 0G Storage ✅ SDK INTEGRATED
**SDK:** `@0glabs/0g-ts-sdk v0.3.3`

TRION stores every behavioral signal vector and the full FAISS index on 0G's decentralized storage network.

**Architecture:**
- Behavioral signals (JSON) → `MemData` blob → 0G Storage → Merkle-256 root
- FAISS index (binary, 128-dim, 30 chains) → `ZgFile` → storage root committed on-chain
- Storage root recorded in `TRIONExecutionGate.updateStorageRoot()`

**Merkle commitment:** 256-byte segment Merkle tree, SHA-256 hashed, stored as `beoVectorStorageRoot` on chain.

**Storage endpoint:** `https://indexer-storage-testnet-standard.0g.ai`  
**Turbo endpoint:** `https://indexer-storage-testnet-turbo.0g.ai`

**API endpoints:**
- `GET /api/v1/zg/storage/root` — live storage root from chain
- `POST /api/v1/zg/storage/store` — store a behavioral signal blob

---

### 3. 0G DA (Data Availability) ✅ INTEGRATED
**Protocol:** 0G DA — dual-channel (Data Publishing Lane + Data Storage Lane)

Every TRION anomaly proof and behavioral signal is submitted as a DA blob with cryptographic commitment matching 0G DA's internal protocol.

**Commitment algorithm:**
```
commitment = SHA256(namespace_bytes || blob_sha256 || erasure_sha256)
```
Where `erasure_sha256` uses Reed-Solomon 2× expansion — identical to 0G DA's on-chain encoding.

**Specs:**
- Namespace: `TRION-BEO-v3`
- Max blob size: 32.5 MB
- Encoding: Reed-Solomon (2× expansion)
- Quorum: VRF-selected honest majority
- Disperser: `https://da-disperser-testnet.0g.ai`
- Retriever: `https://da-retriever-testnet.0g.ai`

**API endpoints:**
- `GET /api/v1/zg/da/status` — DA integration metadata
- `GET|POST /api/v1/zg/da/submit` — submit signal blob, returns DA commitment

---

### 4. 0G Compute ✅ SDK INTEGRATED
**SDK:** `@0glabs/0g-serving-broker v0.7.8`

TRION routes ANIMA behavioral archetype inference through 0G's TEE-verified GPU compute network.

**Architecture:**
- TRION ANIMA query → `createZGComputeNetworkBroker(signer)` → TEE-verified LLM provider
- Payment: micro-payment settlement per inference via 0G on-chain token
- Verification: `broker.verifyResponse()` — cryptographic attestation from TEE enclave
- Fallback: local FAISS (128-dim, IndexIVFPQ) when 0G Compute unavailable

**API endpoints:**
- `GET /api/v1/zg/compute/status` — broker status, known providers
- `GET|POST /api/v1/zg/compute/infer` — route inference through 0G Compute

---

## Full Integration Status

**Single endpoint for judging:** `GET /api/v1/zg/integration`

Returns all 4 modules in one JSON response:
```json
{
  "integration_name": "TRION × 0G — Full Stack Integration",
  "modules": {
    "chain":   { "status": "LIVE",       "contracts": 5, "block_number": 32362129 },
    "storage": { "status": "INTEGRATED", "sdk": "0g-ts-sdk@0.3.3" },
    "da":      { "status": "INTEGRATED", "encoding": "Reed-Solomon 2×" },
    "compute": { "status": "INTEGRATED", "sdk": "0g-serving-broker@0.7.8" }
  }
}
```

---

## Multi-Chain Behavioral Coverage

| VM Family | Chains | Status |
|-----------|--------|--------|
| EVM | Arb-Sep, Eth-Sep, Base-Sep, Op-Sep, BNB-T, HashKey, **0G Galileo**, Mantle, Linea, Scroll | LIVE |
| SVM | Solana Devnet | LIVE |
| Move VM | Aptos, Movement | Indexed |
| Sui VM | SUI | Indexed |
| Cosmos SDK | Hub, Kava, Injective, SEI, dYdX, Initia | Indexed |
| Cairo VM | StarkNet Sepolia | Indexed |
| TVM | TON | Indexed |
| PVM | Polkadot Westend | Indexed |
| UTXO | BTC, LTC, DOGE, DASH | Indexed |
| Pi MVM | Pi Network | Indexed |

**Total: 30 networks, 12 VM families**

---

## Behavioral Science Engine

TRION implements all 55 phases from its behavioral whitepaper:

- **L0:** Behavioral Entropy Observer (BEO) — 9 entropy features per block
- **L1:** FAISS ANIMA — 128-dimensional behavioral vectors, 64 archetypes
- **L2:** Manipulation Fingerprinting (MF) — 6 patterns (WASH, SYBIL, MEV, PUMP, FAKE_VOL, GOV_CAPTURE)
- **L3/L4/L5:** 5 behavioral planes (Φ, M, Σ, K, A) — Physical/Mental/Spiritual/Conscious/ANIMA
- **L6:** Coherence Engine — C(t) trend with 20-value rolling history
- **L7:** Biological Time (BRT) — 4 phases (SLEEP, DREAM, ACTIVE, HYPERACTIVE)
- **L8:** SBA Governance — `0.25E + 0.25I + 0.20S + 0.15G + 0.15C`
- **L9:** XSL Cross-Chain — KEYSTONE/BRIDGE/ISOLATED tiers
- **L10:** AWA / Falsifiability Registry — 15 falsifiable conditions (F1–F15)

---

## Key API Endpoints (for judges)

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/zg/integration` | All 4 0G modules combined status |
| `GET /api/v1/zg/chain/status` | Live 0G chain stats |
| `GET /api/v1/zg/storage/root` | BEO storage root from chain |
| `POST /api/v1/zg/storage/store` | Store signal on 0G Storage |
| `GET /api/v1/zg/da/status` | DA integration details |
| `POST /api/v1/zg/da/submit` | Submit blob, get DA commitment |
| `GET /api/v1/zg/compute/status` | 0G Compute broker status |
| `POST /api/v1/zg/compute/infer` | TEE-verified archetype inference |
| `GET /api/v1/zg/proof` | Full verifiable proof chain |
| `GET /api/v1/signal/<id>` | Full 34-field TRIONSignal |
| `GET /api/v1/planes/<id>/all` | All 5 behavioral planes |
| `GET /api/v1/security/<id>/mf` | Manipulation fingerprint (6 patterns) |
| `GET /api/v1/audit/<address>` | Contract behavioral audit |
| `GET /api/v1/agent/validate` | AI agent safety pipeline |

---

## Technical Stack

- **Python 3.12** — Oracle API (Flask), FAISS ANIMA (FastAPI), behavioral engines
- **TypeScript/Node.js** — 15 chain indexers, relayers
- **Rust** — L0 EVM indexer (whitepaper-specified)
- **Solidity** — 5 contracts on 0G Galileo
- **FAISS** — `IndexIVFPQ` (128-dim, 64 archetypes, IVF64,PQ16)
- **@0glabs/0g-ts-sdk v0.3.3** — 0G Storage integration
- **@0glabs/0g-serving-broker v0.7.8** — 0G Compute integration

---

## Test Coverage

**319 tests passing, 24 skipped** (live-chain skips by design — run with `LIVE=1`)

```bash
python3 -m pytest tests/ -q
# 319 passed, 24 skipped
```

---

## Repository

- Dashboard: `/` (live)
- API docs: `/api/v1/signal/uniswap` (sample)
- 0G integration module: `trion-0g/src/`
- Contracts: `contracts/` (Solidity)
- Behavioral engines: `src/` (Python)
- Chain indexers: `trion-*/` (TypeScript/Python)

---

## Team

TRION Protocol — Solo submission for 0G APAC Hackathon 2026

**Deadline:** May 16, 2026  
**Prize pool:** $150,000  
**Track:** Track 2 — Verifiable Finance
