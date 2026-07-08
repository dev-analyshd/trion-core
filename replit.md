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
| Rust Indexers (EVM + SVM) | — | Rust Indexers |

All services start together via the **Project** run button.

## Running

Press the **Run** button (or use the "Project" workflow). Services start in parallel. The preview pane shows the Oracle API dashboard at port 5000. The Next.js dashboard runs on port 3000.

## Signing Keys (for live on-chain publishing)

Relayers default to **DRY_RUN** mode without signing keys — they read and score but don't publish. To activate live mode, add secrets:

- `RELAYER_PRIVATE_KEY` — EVM private key (hex, no 0x prefix) for TRION Relayer + 0G Gate
- `TRON_PRIVATE_KEY` — Tron chain (Extended Relayer)
- `XLM_PRIVATE_KEY` — Stellar
- `XRPL_PRIVATE_KEY` — XRP Ledger
- `ALGORAND_PRIVATE_KEY` — Algorand
- `SUI_PRIVATE_KEY` — Sui
- `COSMOS_MNEMONIC` (or per-chain variants) — Cosmos-family chains
- Other chain keys: `CARDANO_PRIVATE_KEY`, `FLOW_PRIVATE_KEY`, `HEDERA_PRIVATE_KEY`, `VECHAIN_PRIVATE_KEY`, etc.

## Python Dependencies

Managed via `uv` and `pyproject.toml`. Run `uv sync` to install.

## Node Dependencies

- `relayer/` — run `npm install` for ethers, axios, and chain SDKs
- `dashboard/` — run `npm install` for Next.js 14, recharts, swr

## User Preferences

- Keep existing project structure; do not restructure or migrate.
