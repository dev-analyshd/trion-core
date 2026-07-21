# TRION Sensing Oracle

## Project Overview

TRION is a multi-language, multi-service behavioral intelligence oracle for DeFi. It indexes on-chain activity from 100+ blockchains, extracts behavioral feature vectors via Rust L0 indexers, stores them in a FAISS vector database, and publishes signed oracle signals on-chain via Node.js relayers.

### Architecture

| Layer | Technology | Port | Purpose |
|-------|-----------|------|---------|
| Oracle API | Python / Flask | 5000 | 194 REST routes + WebSocket dashboard |
| FAISS ANIMA | Python / FastAPI | 8000 | 128-dim behavioral vector index, 64 archetypes |
| Rust L0 Indexers | Rust (13 binaries) | — | 100+ chains, 93-byte BH pipeline |
| EVM Relayer | Node.js | — | 57 EVM chains, 60s poll |
| Extended Relayer | Node.js | — | 38 non-EVM chains, 90s poll |
| Native VM Relayer | Node.js | — | Solana, NEAR, TON, Polkadot, StarkNet |
| 0G Gate Relayer | Node.js | — | 0G Mainnet ExecutionGate |
| Attack Alert Webhook | Python / Flask | 6000 | Real-time attack alerting |
| Genesis Backfill | Python | — | Historical chain indexing |

### Languages in Use
- **Python** — Oracle API, FAISS ANIMA engine, Attack Alert Webhook, Genesis Backfill, chain adapters
- **Rust** — 13 L0 indexer binaries (trion-evm, trion-svm, trion-cosmos, trion-ton, trion-near, trion-pvm, trion-starknet, trion-aptos, trion-sui, trion-tron, trion-utxo, trion-pi, trion-movement)
- **Node.js / JavaScript** — EVM relayer, Extended chain relayer, Native VM relayer, 0G gate relayer, 0G DA/sync daemons, SDK
- **Solidity** — TRIONExecutionGate contract, oracle contracts

### How to Run

The project uses `uv` for Python package management. All workflows are pre-configured in Replit.

**Start all services** via the Replit workflow panel:
1. **Start application** — Oracle API + WebSocket dashboard (`uv run python serve.py`, port 5000)
2. **FAISS ANIMA** — Vector engine (`uv run python3 akashic/faiss_service.py`, port 8000)
3. **Rust Indexers** — Builds and runs all 13 Rust binaries
4. **TRION Relayer** — EVM + 0G relayer stack
5. **Extended Chain Relayer** — 38 non-EVM chains
6. **Native Relayer** — SVM/NEAR/TON/PVM/StarkNet
7. **Attack Alert Webhook** — port 6000
8. **Genesis Backfill** — Historical indexing
9. **TRION Dashboard** — Served by Oracle API at port 5000

### Tests

```bash
# Full test suite (all components)
uv run python -m pytest tests/ tests/trion_protocol/ -v

# Key test files
tests/test_e2e_full.py           # End-to-end
tests/test_anima_full.py         # FAISS ANIMA (201 tests)
tests/test_stress.py             # Stress / security (17 tests)
tests/test_gk_living_security.py # Living security system (64 tests)
tests/test_all_planes.py         # All behavioral planes (148 tests)
tests/test_chain_integrations.py # Chain wiring (148 tests)
tests/trion_protocol/            # Core protocol math (52 tests)
```

### Key Environment Variables

See `.env.example` for the full list. Key ones:
- `TIMESCALEDB_URL` / `DATABASE_URL` — TimescaleDB/Postgres (required for signal persistence)
- `FAISS_SERVICE_URL` — FAISS engine URL (default: `http://127.0.0.1:8000`)
- `RELAYER_PRIVATE_KEY` — EVM relayer signing key (dry-run mode if unset)
- `SOLANA_RELAYER_PRIVATE_KEY`, `NEAR_PRIVATE_KEY`, `TON_PRIVATE_KEY_HEX`, etc. — Native VM relayer keys
- `ZG_AKASHIC_CONTRACT` — 0G ExecutionGate contract address

### Notes
- Node packages must be installed at three roots: root `/`, `relayer/`, and `native-relayer/` — run `npm install --legacy-peer-deps` in each (the `@0glabs/0g-ts-sdk` peer dep conflict with ethers requires `--legacy-peer-deps`).
- `bh_ledger.db` symlink: `serve.py` auto-creates `bh_ledger.db → akashic/bh_ledger.db` at startup. If missing, recreate with: `ln -sf akashic/bh_ledger.db bh_ledger.db`
- The TRION relayer runs in **LIVE mode** with `RELAYER_PRIVATE_KEY` set; it needs deployed oracle contract addresses (`ETH_MAINNET_ORACLE_ADDR`, etc.) to publish on-chain — otherwise logs `would publishSignal(...)`.

## User Preferences
- Run comprehensive component-by-component live system tests when asked.
