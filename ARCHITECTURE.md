# TRION Sensing Oracle

## Project Overview

Behavioral truth oracle that gates access to the CoherenceVault via on-chain coherence checks.
**v2.0.0 — fully live on-chain, zero mock data.**

## Architecture

```
Entity → commitment hash → TRION computes C(t) → publishBehavioralTruth() [REAL TX]
                                                          ↓
                                               isCoherent(entityId) == true
                                                          ↓
                                         coherenceWrap(amount, entityId)
                                                          ↓
                                            Vault token (locked)
```

## Running the App

```bash
python3 serve.py   # Flask on port 5000 (frontend + all /api/v1/* endpoints)
```

## Key Files

| File | Purpose |
|---|---|
| `oracle_api/app.py` | Flask API — signal compute, live chain reads/writes |
| `oracle_api/blockchain.py` | web3.py relay — publishBehavioralTruth + event fetching |
| `oracle_api/requirements.txt` | flask, gunicorn, web3==7.15.0 |
| `contracts/TRIONSensingOracle.sol` | On-chain oracle (deployed Arb Sepolia) |
| `contracts/ConfidentialCoherenceVault.sol` | ERC-20 vault gated by behavioral coherence |
| `contracts/ITRIONSensingOracle.sol` | DeFi integration interface |
| `frontend/index.html` | Live dashboard (Arbiscan tx links, chain stats, coherence gate) |
| `serve.py` | Entry point — runs Flask on port 5000 |
| `feedback.md` | Builder feedback |
| `Dockerfile.render` | Production Docker image for Render |
| `render.yaml` | Render service config (trion-core repo, env vars) |
| `deployments.json` | Deployed contract addresses |

## Deployed Contracts (Arbitrum Sepolia, chainId 421614)

- **TRIONSensingOracle**: `0x1d129D34279d1246aB08a41dfE610EaF8D794237`
- **ConfidentialCoherenceVault**: `0x7cB424b88E0b3fEd0DD5d626f4E413c6D0aAe73d`
- **MockTRIONToken**: `0x8F21dB06b3e08D8724Ea34465fCe2fAC8cCfEA8D`

## Live API Endpoints

```
GET  /                            — Frontend UI
GET  /api/v1/signal/{entity_id}   — Compute five-plane coherence score
POST /api/v1/publish/{entity_id}  — On-chain write → returns real tx_hash + Arbiscan URL
GET  /api/v1/onchain/{entity_id}  — Read latest on-chain signal for entity
GET  /api/v1/stats                — Live chain stats (totalSignals, blockNumber)
GET  /api/v1/health               — Health check (chain_connected, total_signals_onchain)
GET  /api/v1/feed                 — Live event feed (BehavioralTruth + SilenceSignal events)
GET  /api/v1/leaderboard          — Top entities by coherence score
POST /api/chat                    — ChainGPT AI advisor
GET  /deployments.json            — Contract addresses
```

## Environment Variables

```
PRIVATE_KEY       — Authorized relayer key (set in Replit secrets)
ORACLE_ADDRESS    — 0x1d129D34279d1246aB08a41dfE610EaF8D794237
VAULT_ADDRESS     — 0x7cB424b88E0b3fEd0DD5d626f4E413c6D0aAe73d
TOKEN_ADDRESS     — 0x8F21dB06b3e08D8724Ea34465fCe2fAC8cCfEA8D
ARB_SEPOLIA_RPC   — https://sepolia-rollup.arbitrum.io/rpc
CHAIN_ID          — 421614
```

## Blockchain Events

The oracle contract emits two events:
- **`BehavioralTruth`** — when entity IS coherent (score ≥ threshold)
- **`SilenceSignal`** — when entity is NOT coherent (score < threshold)

Both are fetched by `blockchain.py::get_recent_events()` and shown in the live feed.

## Deployment Config

- **GitHub repo**: `dev-analyshd/trion-core` (main branch)
- **Production**: https://trionprotocol.onrender.com
- **Docker**: `Dockerfile.render` (includes gcc for web3 build deps)
- **Run command**: `gunicorn -w 2 -b 0.0.0.0:10000 oracle_api.app:app --timeout 60`

## Dependencies

- Python: flask, gunicorn, web3==7.15.0 (oracle_api/requirements.txt)
- Node: hardhat, ethers (package.json)

## Deployment Checklist

- [x] Contracts deployed on Arbitrum Sepolia (3 contracts)
- [x] Zero mock data — every signal published on-chain with real tx hash
- [x] Live feed reads BehavioralTruth + SilenceSignal events from chain
- [x] Frontend shows real Arbiscan tx links
- [x] CoherenceVault integrated
- [x] Oracle API on Render (trionprotocol.onrender.com)
- [x] GitHub repo: dev-analyshd/trion-core
