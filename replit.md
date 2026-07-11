# TRION Protocol

Multi-chain behavioral truth oracle and DeFi firewall. Tracks wallet behavior across 100+ chains via "Behavioral Hashes" (BH), computing a Coherence score C(t) to flag hostile wallets pre-execution.

## Stack

- **Oracle API / Frontend** — Python (Flask + Flask-SocketIO), port 5000
- **FAISS ANIMA Engine** — Python (FastAPI + FAISS), port 8000
- **Rust Indexers** — Rust crates in `rust-indexers/`, poll 53+ EVM chains + SVM
- **EVM Relayer** — Node.js (`relayer/`), publishes signals on-chain
- **Extended Chain Relayer** — Node.js (`relayer/`), 38 non-EVM chains
- **Native Relayer** — Node.js (`native-relayer/`), Solana / NEAR / TON / Polkadot / StarkNet
- **TRION Dashboard** — Next.js (`dashboard/`), port 3000
- **Attack Alert Webhook** — Python (Flask), port 6000

## Running

All services are configured as Replit workflows. Start them from the Workflows panel:

| Workflow | Purpose |
|---|---|
| Start application | Oracle API + frontend (port 5000) |
| FAISS ANIMA | Vector similarity engine (port 8000) — start first |
| TRION Relayer | EVM + 0G on-chain signal publisher |
| Extended Chain Relayer | 38 non-EVM chains (UTXO, Cosmos, Move, etc.) |
| Native Relayer | Solana, NEAR, TON, Polkadot, StarkNet |
| Rust Indexers | High-performance per-chain transaction indexers |
| Attack Alert Webhook | Protocol monitoring webhook (port 6000) |
| TRION Dashboard | Next.js dashboard (port 3000) |

**Recommended startup order:** FAISS ANIMA → Start application → everything else.

## Dependencies

- Python: managed by `uv` (`pyproject.toml`). Run `uv sync` if packages are missing.
- `relayer/`: `npm install` inside `relayer/`
- `native-relayer/`: `npm install` inside `native-relayer/`
- `dashboard/`: `npm install` inside `dashboard/`
- `trion-0g/`: `npm install --legacy-peer-deps` inside `trion-0g/`
- `chains/svm|near|ton|pvm|starknet|sui`: each has its own `npm install`
  - Note: `chains/ton` may fail on `protobufjs` due to security policy; TON VM in the Native Relayer will skip gracefully.

## Configuration

- `config/config.yaml` — main settings
- `zg_config.py` — 0G (ZeroGravity) integration settings
- Secrets managed via Replit Secrets (see below)

## Key Secrets

| Secret | Used by |
|---|---|
| `RELAYER_PRIVATE_KEY` | EVM relayer signing |
| `DEPLOY_0G_PRIVATE` | 0G gate relayer |
| `TIMESCALEDB_URL` | TimescaleDB dual-write |
| `SOLANA_RELAYER_PRIVATE_KEY` | SVM native relayer |
| `NEAR_PRIVATE_KEY` | NEAR native relayer |
| `TON_PRIVATE_KEY_HEX` | TON native relayer |
| `DOT_MNEMONIC` | Polkadot (PVM) native relayer |
| `STARKNET_PRIVATE_KEY` | StarkNet native relayer |
| `ZG_AKASHIC_CONTRACT` | 0G Akashic contract address |
| `APTOS_PRIVATE_KEY`, `SUI_PRIVATE_KEY`, etc. | Extended chain relayer |

## Setup notes

- All 8 workflows verified running as of 2026-07-11: Start application, FAISS ANIMA, TRION Relayer, Extended Chain Relayer, Native Relayer, Rust Indexers, Attack Alert Webhook, TRION Dashboard.
- Dependencies are installed: Python via `uv sync`; Node via `npm install` in `dashboard/`, `relayer/`, `native-relayer/`, and the `chains/*` subpackages (svm, near, pvm, starknet, sui).
- `chains/ton` cannot fully install (`protobufjs` blocked by Replit's package security policy). The Native Relayer already handles this gracefully by skipping TON with a module-not-found error each cycle — this is a known/expected limitation, not a bug.
- Relayers run in LIVE mode against real chains once their secrets are present. "Insufficient funds" errors mean the signing wallet needs funding on that chain; "no *_ORACLE_ADDR" means no mainnet contract is deployed yet for that chain — both fall back to block-proof recording automatically, per the Notes section below.

## Notes

- On-chain publishing to mainnet chains requires deploying oracle contracts and setting `*_ORACLE_ADDR` env vars (currently only testnets are configured).
- The 0G Gate wallet needs ETH on the 0G Galileo testnet to submit on-chain proofs.
- The 0G DA endpoint (`da-rpc.0g.ai`) is currently unreachable from Replit; DA blobs fall back to local hash proofs automatically.
- Wallet balances (SOL, ETH on testnets) being too low causes "block proof only" mode — top up the respective wallets to enable live signing.
