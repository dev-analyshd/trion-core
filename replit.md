# TRION Protocol

## Overview
TRION is a multi-chain behavioral truth oracle and pre-execution DeFi firewall. It derives cryptographically verified behavioral signals from on-chain activity across 100+ chains and 13 VM families to identify and block attackers (flash loans, oracle manipulation, etc.) before they execute.

## Stack
- **Core / API**: Python (Flask + Flask-SocketIO), port 5000 — `serve.py` / `oracle_api/app.py`
- **FAISS ANIMA engine**: Python (FastAPI), port 8000 — `akashic/faiss_service.py`; 64 trained behavioral archetypes, k-NN vector search
- **Relayers** (Node.js / ESM): `relayer/` — EVM + 0G; `native-relayer/` — SVM/NEAR/TON/PVM/StarkNet; `relayer/extended_chain_relayer.js` — 38 non-EVM chains (UTXO, Cosmos, Move, etc.)
- **Rust indexers**: `rust-indexers/` — EVM (53 chains) + Solana mainnet
- **Dashboard**: Next.js 14, port 3000 — `dashboard/`
- **Attack Alert Webhook**: Python, port 6000 — `attack_alert_webhook.py`
- **Genesis Backfill**: `scripts/genesis_backfill_runner.sh`
- **Package management**: `uv` (Python), `npm` (Node.js), `cargo` (Rust)

## Running on Replit
All 9 services are configured as Replit workflows and start automatically:

| Workflow | Port | Notes |
|---|---|---|
| Start application | 5000 | Oracle API + frontend |
| FAISS ANIMA | 8000 | Vector DB; must start before Rust Indexers |
| TRION Relayer | — | EVM + 0G relayer supervisor |
| Extended Chain Relayer | — | 38 non-EVM chains |
| Native Relayer | — | SVM/NEAR/TON/PVM/StarkNet |
| Rust Indexers | — | Waits for FAISS on port 8000 |
| Attack Alert Webhook | 6000 | Monitors entities every 30s |
| TRION Dashboard | 3000 | Next.js UI |
| Genesis Backfill | — | Historical block indexer |

## Secrets required to go live
All relayers run in **DRY_RUN** mode until private keys are configured:
- `RELAYER_PRIVATE_KEY` — EVM relayer signing key
- `DEPLOY_0G_PRIVATE` — 0G chain signing key
- Per-chain keys for native relayer: `SVM_PRIVATE_KEY`, `NEAR_PRIVATE_KEY`, `TON_MNEMONIC`, `PVM_MNEMONIC`, `STK_PRIVATE_KEY`
- Per-chain keys for extended relayer: BTC/LTC/DOGE/DASH/CARDANO/Cosmos ecosystem/APTOS/MOVEMENT/SUI/TRON/etc.

## User preferences
<!-- Add user preferences here -->
