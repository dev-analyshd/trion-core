# TRION Protocol

**Multi-Chain Behavioral Truth Oracle — Pre-Execution DeFi Firewall**

TRION monitors 100+ chains and 13 VM families, deriving cryptographically verified behavioral signals to block hostile wallets before any trade executes.

---

## How to Run

All services have pre-configured workflows. Start them from the Replit Workflows panel.

### Core services (start first, in order)

| Workflow | Port | Description |
|---|---|---|
| **Start application** | 5000 | Flask Oracle API + WebSocket dashboard |
| **FAISS ANIMA** | 8000 | AI behavioral vector engine |
| **Attack Alert Webhook** | 6000 | Webhook service for attack alerts |

### Indexers & Relayers (start after core)

| Workflow | Description |
|---|---|
| **TRION Relayer** | EVM chain relayer + 0G execution gate |
| **Extended Chain Relayer** | Extended multi-chain relayer |
| **Native Relayer** | Solana/NEAR/TON/Polkadot/StarkNet relayer (requires private key secrets) |
| **Rust Indexers** | EVM block streamer (auto-builds ~2 min on first run) |
| **Genesis Backfill** | Historical backfill across all chains |

### Dashboard
Navigate to the Replit webview (port 5000) to access the TRION dashboard.

---

## Environment Variables

Copy `.env.example` to `.env` and fill in values. Key variables:

```
# Required for TimescaleDB persistence (FAISS uses this for vector restore on cold boot)
DATABASE_URL=postgresql://...
TIMESCALEDB_URL=postgresql://...

# Optional — relayers run in DRY_RUN mode without these
RELAYER_PRIVATE_KEY=
ZERO_G_PRIVATE_KEY=

# Optional — public RPCs are used as fallback but are rate-limited
ETHEREUM_RPC_URL=
ARBITRUM_RPC_URL=
# ... see .env.example for all chains
```

Set secrets via the Replit Secrets panel (not in `.env` committed to git).

---

## Architecture

- **Oracle API** (`api/app.py`) — 194 Flask routes, port 5000
- **FAISS ANIMA** (`anima-service/faiss_service.py`) — 156 FastAPI routes, port 8000; 128-dim behavioral vector index
- **Behavioral Engine** (`src/`) — 15 module families, L0–L10 signal formulas
- **Relayers** (`relayer/`, `native-relayer/`) — publish signals on-chain
- **Rust Indexers** (`bin/`, compiled from workspace) — high-throughput EVM block streaming
- **Smart Contracts** (`contracts/`, `hardhat/`) — TRIONExecutionGate on 0G Mainnet + Arbitrum Sepolia

## Key Addresses

- TRIONExecutionGate (0G Mainnet): `0xA85B49C73B5710d9ddB1CB5a94c52D0F33c4199b`
- TRIONSensingOracle (Arbitrum Sepolia): `0x1d129D34279d1246aB08a41dfE610EaF8D794237`

---

## User Preferences

- Keep existing project structure and stack — do not restructure or migrate.
- Node.js packages: root uses `npm install --legacy-peer-deps` (ethers peer conflict with @0glabs/0g-ts-sdk).
- Relayer packages: `cd relayer && npm install` works directly.
