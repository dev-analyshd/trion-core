# TRION Protocol

Multi-chain behavioral truth oracle and pre-execution DeFi firewall. Analyzes on-chain behavior across 100+ chains to score entities and block hostile wallets before transactions execute.

## Architecture

| Service | Port | Workflow |
|---|---|---|
| Oracle API + WebSocket frontend (serve.py) | 5000 | Start application |
| FAISS ANIMA vector engine (akashic/faiss_service.py) | 8000 | FAISS ANIMA |
| TRION Dashboard (Next.js) | 3000 | TRION Dashboard |
| Attack Alert Webhook | 6000 | Attack Alert Webhook |
| TRION Relayer (EVM multi-chain) | — | TRION Relayer |
| Extended Chain Relayer (38 non-EVM chains) | — | Extended Chain Relayer |
| Native Relayer (SVM, NEAR, TON, Polkadot, StarkNet) | — | Native Relayer |
| Rust Indexers (EVM + SVM) | — | Rust Indexers |

All services start together via the **Project** run button.

## Running

Press the **Run** button (or use the "Project" workflow). Services start in parallel. The preview pane shows the Oracle API dashboard at port 5000. The Next.js monitoring dashboard runs on port 3000.

## Important: Dashboard SWC Workaround

`dashboard/.babelrc` forces Next.js 14 to use Babel instead of its native SWC compiler. This is required because the SWC binary (`@next/swc-linux-x64-gnu`) was corrupt in the original import. Do not remove `.babelrc` without verifying SWC works (`next build` should complete without SIGBUS).

## Signing Keys (for live on-chain publishing)

Relayers default to **DRY_RUN** mode without signing keys — they read and score but don't publish. To activate live mode, add secrets:

- `RELAYER_PRIVATE_KEY` — EVM private key (hex, no 0x prefix) for TRION Relayer + 0G Gate
- `DEPLOY_0G_PRIVATE` — 0G chain private key
- `TRON_PRIVATE_KEY` — Tron chain (Extended Relayer)
- `XLM_PRIVATE_KEY` — Stellar
- `XRPL_PRIVATE_KEY` — XRP Ledger
- `ALGORAND_PRIVATE_KEY` — Algorand
- `SUI_PRIVATE_KEY` — Sui
- `COSMOS_MNEMONIC` (or per-chain variants) — Cosmos-family chains
- Other chain keys: `CARDANO_PRIVATE_KEY`, `FLOW_PRIVATE_KEY`, `HEDERA_PRIVATE_KEY`, `VECHAIN_PRIVATE_KEY`, etc.
- Native VM chains: `SOLANA_RELAYER_PRIVATE_KEY`, `NEAR_MNEMONIC`, `TON_MNEMONIC`, `POLKADOT_MNEMONIC`, `STARKNET_PRIVATE_KEY`

## Python Dependencies

Managed via `uv` and `pyproject.toml`. Run `uv sync` to install.

## Node Dependencies

- `relayer/` — run `npm install` for ethers, axios, and chain SDKs
- `native-relayer/` — run `npm install` for Solana, NEAR, TON, Polkadot, StarkNet SDKs
- `dashboard/` — run `npm install` for Next.js 14, recharts, swr
- `trion-0g/` — run `npm install --legacy-peer-deps` for 0G storage SDK

## User Preferences

- Keep existing project structure; do not restructure or migrate.
