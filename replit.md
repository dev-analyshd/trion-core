# TRION Protocol

Multi-chain behavioral truth oracle and DeFi pre-execution firewall. Ingests live on-chain data across 100+ chains, computes 5-plane behavioral coherence scores, and blocks attacks before execution.

## Architecture

| Layer | Technology | Role |
|-------|-----------|------|
| Oracle API | Python / Flask | Scoring engine, REST + WebSocket, port 5000 |
| FAISS ANIMA | Python / FastAPI | 128-dim vector intelligence, port 8000 |
| L0 Indexers | Rust (13 crates) | Per-VM live BH ingestion |
| TRION Relayer | Node.js / ESM | EVM multi-chain signal publisher + 0G gate |
| Extended Chain Relayer | Node.js / ESM | 38 non-EVM chains (UTXO, Cosmos, Move, SUI, TRON …) |
| Native VM Relayer | Node.js / ESM | SVM, NEAR, TON, PVM, StarkNet signing |
| Akashic Ledger | SQLite + FAISS | BH dual-strand storage, behavioral archive |
| 0G Network | Solidity | On-chain ExecutionGate + DA storage |

## Running the Project

All services are managed as Replit workflows. Start them from the Workflows panel:

1. **Start application** — Oracle API + WebSocket at `http://0.0.0.0:5000`
2. **FAISS ANIMA** — Vector intelligence service at port 8000
3. **Rust Indexers** — 13 L0 crates indexing EVM, SVM, and more
4. **TRION Relayer** — EVM signal publisher + 0G ExecutionGate
5. **Extended Chain Relayer** — 38 non-EVM chain relayer
6. **Native Relayer** — SVM/NEAR/TON/PVM/StarkNet VM signing
7. **Attack Alert Webhook** — Threat webhook at port 6000
8. **Genesis Backfill** — Historical BH accumulation
9. **TRION Dashboard** — Points to the Oracle API dashboard (port 5000)

The unified dashboard is served by the Oracle API at `/` — navigate to the webview after starting **Start application**.

## Key Paths

```
oracle_api/          Flask app, routes, templates
oracle_api/templates/dashboard.html   Single-page unified dashboard
akashic/             FAISS service + BH ledger SQLite + FAISS index
chains/              Per-VM execute.ts scripts (SVM, NEAR, TON, PVM, StarkNet, SUI)
relayer/             TRION multi-chain EVM relayer + 0G gate
native-relayer/      Native VM signing relayer
indexers/            Rust L0 crates (one per VM family)
tests/               Full test suite (E2E, stress, planes, BH, backtest)
backtest/            Historical exploit scoring → backtest_report.json
scripts/             Utility + genesis backfill runner
supervisors/         Shell supervisors for Rust indexers + TRION relayer stack
```

## Test Results (last run)

| Suite | Result |
|-------|--------|
| All Planes (52 tests) | ✅ 52/52 passed |
| Stress (17 tests) | ✅ 17/17 passed |
| BH Collision Resistance (2M samples) | ✅ 0 collisions |
| Trading Signals | ✅ 8/8 passed |
| Backtest (30 exploits, $3.3B) | ✅ 100% recall, 85.71% F1 |
| E2E Full Suite | ✅ 130/137 (94%) |
| Attack Simulation | ✅ All attacks blocked |

## Secrets Required

All signing keys are stored as Replit Secrets. The relayers pick them up automatically by name — no `.env` file needed. Key names:

`RELAYER_PRIVATE_KEY`, `SOLANA_RELAYER_PRIVATE_KEY`, `NEAR_PRIVATE_KEY`, `TON_PRIVATE_KEY_HEX`, `DOT_MNEMONIC`, `STARKNET_PRIVATE_KEY`, `APTOS_PRIVATE_KEY`, `SUI_PRIVATE_KEY`, `TRON_PRIVATE_KEY`, `COSMOS_PRIVATE_KEY`, `KAVA_PRIVATE_KEY`, `INJECTIVE_PRIVATE_KEY`, `SEI_PRIVATE_KEY`, `DYDX_PRIVATE_KEY`, `INITIA_PRIVATE_KEY`, `MOVEMENT_PRIVATE_KEY`, `BTC_TAPROOT_WIF`, `BTC_SEGWIT_NATIVE_WIF`, `BTC_SEGWIT_NESTED_WIF`, `BTC_LEGACY_WIF`, `LITECOIN_PRIVATE_KEY`, `DOGE_PRIVATE_KEY`, `DASH_PRIVATE_KEY`, `DEPLOY_0G_PRIVATE`, `ZG_AKASHIC_CONTRACT`, `TIMESCALEDB_URL`, `SESSION_SECRET`, `PI_SECRET_KEY`

## User Preferences

- Keep all math symbols and Greek-letter formulas out of the frontend — use plain English labels
- `judge.html` is a permanent route at `/judge` — do not delete
- BH Explorer stays as a section in the main dashboard (not a separate page)
- Dashboard is the single-page SPA at `oracle_api/templates/dashboard.html` — do not split into multiple HTML files
