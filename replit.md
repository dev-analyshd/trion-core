# TRION Protocol

Multi-chain behavioral truth oracle and DeFi firewall. Analyzes transaction patterns across 100+ chains and 13 VM families, computes Behavioral Hashes (BH) and a multi-dimensional Coherence score $C(t)$, then blocks hostile wallets pre-execution.

## Architecture

| Component | Runtime | Port | Workflow |
|---|---|---|---|
| Oracle API + Frontend | Python/Flask + SocketIO | 5000 | `Start application` |
| FAISS ANIMA Engine | Python/FastAPI | 8000 | `FAISS ANIMA` |
| Dashboard | Next.js | 3000 | `TRION Dashboard` |
| EVM + 0G Relayer | Node.js | — | `TRION Relayer` |
| Extended Chain Relayer | Node.js | — | `Extended Chain Relayer` |
| Native VM Relayer | Node.js (tsx) | — | `Native Relayer` |
| Rust Indexers (EVM + SVM) | Rust | — | `Rust Indexers` |
| Attack Alert Webhook | Python/Flask | 6000 | `Attack Alert Webhook` |
| Genesis Backfill | Python | — | `Genesis Backfill` |

## Entry Points

- `serve.py` — Oracle API with WebSocket support (imports from `oracle_api/socket_push.py`)
- `akashic/faiss_service.py` — FAISS vector engine (FastAPI)
- `dashboard/` — Next.js monitoring UI
- `relayer/relayer.js` — EVM signal publisher
- `relayer/extended_chain_relayer.js` — 38 non-EVM chain relayer
- `native-relayer/native_relayer.js` — Solana, NEAR, TON, Polkadot, StarkNet relayer
- `supervisors/trion_and_zg_relayer.sh` — Supervisor for TRION + 0G relayer stack
- `supervisors/rust_indexers.sh` — Rust indexer supervisor (builds on first run ~2 min)

## Python Dependencies

Managed by `uv`. Root environment has `oracle_api/requirements.txt` installed.
FAISS ANIMA has its own `uv` virtualenv (`.pythonlibs/`).

## Node Dependencies

Each subdirectory has its own `node_modules`:
- `relayer/` — ethers, axios, bitcoinjs-lib, @cosmjs/stargate, @mysten/sui, @aptos-labs/ts-sdk
- `native-relayer/` — @polkadot/api, @solana/web3.js, @ton/ton, near-api-js, starknet, tsx
- `dashboard/` — Next.js 14, React, recharts, swr

`tsx` is installed globally at `.config/npm/node_global/bin/tsx` and used by the native relayer.

## Key Data Paths

- `./akashic/akashic_faiss.index` — FAISS vector index (128-dim, up to 100k+ vectors)
- `./akashic/faiss_state.db` — SQLite entity state
- `./akashic/bh_ledger.db` — Behavioral Hash ledger (symlinked to workspace root for Oracle API)
- `./data/trion_gk_state.json` — L0 daemon chain state

## Notes

- `bh_ledger.db` is symlinked from `./akashic/bh_ledger.db` → `./bh_ledger.db` (Oracle API expects it at root)
- FAISS restore: `_persist_all` is guarded with `try/except NameError` in `_restore_from_timescaledb()` because it's called during module init before the function definition at line ~10920 is reached
- Several EVM oracle contract addresses (`ETH_MAINNET_ORACLE_ADDR`, `ARB_MAINNET_ORACLE_ADDR`, etc.) are not set — relayer logs DRY_RUN for those chains
- Some testnet wallets (eth-sepolia, bnb-testnet, 0g-galileo) show "insufficient funds" — fund them to enable those chains
- Cardano, OSMOSIS, XRPL, ALGO, ICP, etc. run in DRY_RUN mode — keys not configured

## Environment Variables

All set as Replit shared env vars. See `.env.example` for the full reference.
Key secrets (in Replit Secrets): `RELAYER_PRIVATE_KEY`, `SOLANA_RELAYER_PRIVATE_KEY`, `NEAR_PRIVATE_KEY`, `TON_PRIVATE_KEY_HEX`, `STARKNET_PRIVATE_KEY`, `APTOS_PRIVATE_KEY`, `SUI_PRIVATE_KEY`, `COSMOS_PRIVATE_KEY`, `TRON_PRIVATE_KEY`, `TIMESCALEDB_URL`, `DEPLOY_0G_PRIVATE`, `ZG_AKASHIC_CONTRACT`, plus BTC/UTXO WIF keys and other chain keys.

## User Preferences

- All private keys and secrets managed via Replit Secrets (never in `.env` files)
- RPC endpoints use public defaults from `.env.example`; override via Replit shared env vars for production
