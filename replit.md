# TRION Protocol — Developer Operations Manual

**Author**: Hudu Yusuf (Analys) | CC0 — This knowledge belongs to everyone
**Whitepaper**: v1.0 complete | 84 formulas, 100% live coverage

---

## What Is TRION

TRION is a multi-chain behavioral truth oracle. It derives cryptographically verified behavioral signals from the actual record of what every entity did on every chain — stripped of manipulation, weighted by coherence, bounded by liquidity health. It provides a pre-execution firewall: any DeFi protocol can call `TRIONExecutionGate.checkExecution(address)` before a trade executes to block wallets exhibiting attack fingerprints.

**Not** a price oracle. **Not** a data bridge. A behavioral intelligence layer that would have blocked $44B+ in historical DeFi exploits.

---

## Language Stack

| Language | Version | Role |
|----------|---------|------|
| **Python** | 3.11 | Oracle API (Flask, 194 routes), FAISS ANIMA engine (FastAPI, 151 routes), src/ behavioral engine (15 modules), ZG daemons |
| **Rust** | stable | 13 L0 indexer crates — canonical 93-byte BH per tx across all 37 chains; NEAR/PVM WASM contracts |
| **JavaScript** | ESM / Node 18 | 3 relayers: EVM multi-chain, extended non-EVM chains, 0G ExecutionGate |
| **TypeScript** | 5.x | Native VM chain adapters (`chains/*/execute.ts`), TRION SDK |
| **Solidity** | 0.8.x | 15 EVM contracts — TRIONExecutionGate, TRIONOracleV3, LiquidityOcean, AkashicProof, etc. |
| **Cairo** | 1.x | StarkNet attestation contracts (`chains/starknet/`) |
| **FunC** | TON | TON network contracts (`chains/ton/contracts/`) |
| **Julia** | 1.x | Formal entropy verification (`math/trion_entropy_verification.jl`) |
| **Go** | 1.21 | P2P validator mesh networking (Channel 17), ANIMA 54-language crawler coordination (`go/`) |
| **Haskell** | GHC 9.x | Formal verification — 7 theorems as types; SILENCE≠VALUATION, PC_limit, Θ monotonicity (`math/formal_verification.hs`) |
| **C++** | C++17 | FFT behavioral entropy engine (wash-trading via spectral analysis), hardware sensor interface — BRT/HSM/ecological (`cpp/`) |
| **WebAssembly** | WAT/WASM | Browser-side signal processing; type-safe SILENCE≠VALUATION enforcement; local Θ(t) computation (`wasm/`) |

---

## Services & Ports

| Service | Port | Command | Entry Point |
|---------|------|---------|------------|
| Oracle API + Dashboard | **5000** | `uv run python3 serve.py` | `oracle_api/app.py` |
| FAISS ANIMA Engine | **8000** | `uv run python3 akashic/faiss_service.py` | `akashic/faiss_service.py` |

Everything else (Rust indexers, relayers) communicates with these two services internally.

---

## Workflows (8 active)

| Workflow | Runtime | What it does |
|---------|---------|-------------|
| **Start application** | Python/Flask | Oracle API + dashboard on port 5000; 194 Flask routes |
| **FAISS ANIMA** | Python/FastAPI | 128-dim FAISS vector index + BH ledger on port 8000; 151 routes |
| **Rust Indexers** | Rust/cargo | trion-evm (14 EVM mainnet chains) + trion-svm (Solana) → posts per-tx BH to FAISS |
| **Native VM Indexers** | Bash/Node | trion-near, trion-ton, trion-pvm, trion-starknet → FAISS |
| **Extended VM Indexers** | Bash/Node | trion-utxo, trion-cosmos, trion-aptos, trion-movement, trion-sui, trion-tron, trion-pi → FAISS |
| **Native VM Relayer** | Node.js | Signs block proofs on NEAR, TON, Polkadot, StarkNet using chain-native key schemes |
| **TRION Relayer** | Node+Bash | Publishes C(t) signals to EVM chains every 60s; syncs 0G ExecutionGate |
| **Extended Chain Relayer** | Node.js | Publishes to 15 non-EVM chains every 90s (OP_RETURN, IBC memo, Move calls, etc.) |

The **Project** workflow runs `Start application + FAISS ANIMA + Rust Indexers + TRION Relayer` in parallel as the default run button.

---

## Quick Verification

```bash
# Oracle API health
curl http://127.0.0.1:5000/api/v1/health

# FAISS vector count
curl http://127.0.0.1:8000/health

# Full signal for any entity
curl http://127.0.0.1:5000/api/v1/signal/uniswap

# All 5 0G integration components
curl http://127.0.0.1:5000/api/v1/zg/integration

# Whitepaper formula coverage (84/84 live)
curl http://127.0.0.1:5000/api/v1/whitepaper/coverage

# Signal factory self-test (all 24 signal types)
uv run python3 src/signals/signal_factory.py

# ANIMA language registry (59 ISO 639-1 languages, whitepaper mandates 50+)
uv run python3 -c "from src.planes.anima.anima_data_streams import SUPPORTED_NLP_LANGUAGES; print(len(SUPPORTED_NLP_LANGUAGES))"

# Coherence engine self-test (11 weight profiles, L3.6 PC_limit)
uv run python3 src/core/coherence_engine.py

# Haskell formal verification (7 invariants as types — run with GHC if installed)
# ghc -Wall math/formal_verification.hs -o math/trion_verify && math/trion_verify

# C++ FFT engine self-test (wash-trade spectral detection)
# mkdir -p cpp/build && cd cpp/build && cmake .. -DCMAKE_BUILD_TYPE=Release && cmake --build . && ctest

# Go validator mesh + ANIMA crawler coordinator
# cd go && go test ./...

# WebAssembly signal processor
# bash wasm/build.sh --validate

# Run tests
uv run python3 -m pytest tests/ -q   # 328 passed, 24 skipped
```

---

## Live Deployments

### 0G Mainnet (chain 16661) — Primary

| Contract | Address | Purpose |
|---------|---------|---------|
| **TRIONExecutionGate** | `0xA85B49C73B5710d9ddB1CB5a94c52D0F33c4199b` | Pre-trade firewall — `checkExecution(addr)` |
| AkashicProof | `0x33c793fed5bf5fcB043D8c6c74256e7B4b38156D` | BEO Merkle root storage |
| Explorer | [chainscan.0g.ai](https://chainscan.0g.ai/address/0xA85B49C73B5710d9ddB1CB5a94c52D0F33c4199b) | |

### 0G Galileo Testnet (chain 16602) — Supplementary

| Contract | Address |
|---------|---------|
| TRIONOracleV3 | `0x0471B2BE25c2eBbAe7FAc17383F1692979F0A87C` |
| LiquidityOcean | `0x105c7F6c16d2c92FEad10336C2b6A047F999a5A7` |
| TravelRuleCompliance | `0x5e7DBE6cc90d6260be2781dc312812834715EBaB` |
| BTCPSimpleEscrow | `0x388f98831c749D7Acad2046329c9CeC94A8b248d` |
| TRIONExecutionGate (Galileo) | `0xDB5910Dc6CfD219D00F64be1F23DA0289901356d` |

### EVM Testnets

| Chain | Chain ID | Oracle |
|-------|---------|--------|
| HashKey Mainnet | 177 | `0x708193f93Fb897fbeA72e7e7D19237770F19E969` |
| Arbitrum Sepolia | 421614 | `0xb819c63c02Ed5aB49017C0f3f2568A14624658b3` |
| Ethereum Sepolia | 11155111 | `0xB07AD89a10f94B6D3bF2ab0B3a37988b1F37Db39` |
| Base Sepolia | 84532 | `0x7ADF5B7273883C50EFc005BA7EdD3F379Af9680C` |
| Optimism Sepolia | 11155420 | `0x708193f93Fb897fbeA72e7e7D19237770F19E969` |

### Native VMs

| VM | Status |
|----|--------|
| NEAR (trion.testnet) | Deployed — 304,895-byte WASM |
| TON | BOC compiled, wallet funded |
| SVM (Solana devnet) | Active |
| SUI devnet | Active |
| Aptos devnet | Active |
| StarkNet Sepolia | Contracts compiled |

---

## Environment Variables

Set these in the Replit Secrets panel to enable live on-chain publishing. Without them the relayers run in `DRY_RUN` mode (signals computed but not published):

```
RELAYER_PRIVATE_KEY          # EVM signing key (hex, no 0x prefix)
NEAR_PRIVATE_KEY             # ed25519:... format
TON_PRIVATE_KEY_HEX          # TON hex private key
DOT_MNEMONIC                 # Polkadot/Westend BIP39 mnemonic
STARKNET_PRIVATE_KEY         # StarkNet signing key
SVM_PRIVATE_KEY_B58          # Solana base58 private key
DATABASE_URL                 # PostgreSQL (optional — SQLite fallback active)
TIMESCALEDB_URL              # TimescaleDB (optional — set to DATABASE_URL)
ZG_PRIVATE_KEY               # 0G Mainnet signing key
ZG_AKASHIC_CONTRACT          # 0x33c793fed5bf5fcB043D8c6c74256e7B4b38156D (pre-set)
```

---

## Architecture

```
User / DeFi Protocol / AI Agent
        │  REST / WebSocket
Oracle API  (Flask, port 5000, 194 routes)
        │ proxy          │ proxy
FAISS ANIMA              Python Engine
(FastAPI, 8000)          src/ — 15 modules
128-dim vectors          L0–L10 formulas
        │ add_tx_bh_batch
L0 Rust Indexers — rust-indexers/crates/ (13 binaries)
trion-evm (14 EVM) · trion-svm · trion-near · trion-ton
trion-cosmos · trion-aptos · trion-sui · trion-tron
trion-utxo · trion-starknet · trion-pvm · trion-pi
trion-movement
        │ publish signals
Relayers — Node.js (EVM + Native VM + Extended Chains)
relayer/ · native-relayer/ · extended_chain_relayer.js
0G ExecutionGate (0G Mainnet chain 16661)
```

---

## Five Behavioral Planes

`C(t) = α·Φ + β·M + γ·Σ + δ·K + ε·A`  where weights sum to 1.0

| Plane | Weight | Measures |
|-------|--------|---------|
| Φ Physical | α = 0.25 | 9 Shannon entropy features over on-chain tx flow |
| M Mental | β = 0.30 | Observer-effect corrected intent consistency |
| Σ Spiritual | γ = 0.25 | Validator consensus diversity (DW-BFT) |
| K Conscious | δ = 0.10 | Commit-reveal annotation stake voting |
| A ANIMA | ε = 0.10 | k-NN archetype distance in FAISS 128-dim space |

Signal emits when `C(t) ≥ Θ(t)`. Below threshold: **Structured Silence** — typed anomaly signal.
Dynamic threshold: `Θ(t) = 0.55 + 0.37 × V(t)` — tightens automatically under market volatility.

---

## Key Files

| File | Lines | What it does |
|------|-------|-------------|
| `oracle_api/app.py` | 9,043 | Main Flask app — 172 direct routes + 22 blueprint routes = 194 total |
| `akashic/faiss_service.py` | 9,556 | FAISS ANIMA engine — 151 FastAPI routes, BH ledger, archetype training |
| `oracle_api/price_feed_routes.py` | 532 | BTV engine (L0.7/L0.8) — Behavioral True Value derivation |
| `oracle_api/cex_integration.py` | 1,024 | CEX bidirectional feed (§7.3) |
| `zg_api_routes.py` | 338 | 0G integration blueprint (5 modules) |
| `zg_sync_daemon.py` | 761 | Hourly FAISS → 0G Storage delta upload |
| `zg_da_streamer.py` | 390 | Anomaly blob → 0G DA with Reed-Solomon erasure |
| `src/core/coherence_engine.py` | — | Five-plane C(t) assembly + Θ(t) + Silence logic |
| `src/security/living_security.py` | — | 8-component DNA-mimetic security system |
| `rust-indexers/crates/trion-common/` | — | Shared BH format, FAISS client, entropy, hash_dna |

---

## Rust L0 Pipeline (per crate)

Every crate implements the same canonical per-tx BH pipeline:

```
classify_event()  → EventType byte (20 types: SWAP=1, BORROW=3, FLASH_LOAN=15, MEV_CAPTURE=17…)
magnitude_norm()  → log₁₀(USD+1) / log₁₀(max_90d+1) with AtomicU64 running max
canonical_bh()    → entity(32) || event(1) || mag(8) || ctx(8) || ts(8) || chain(4) || block_hash(32)
sense / antisense → SHA3-256(payload||0x00) / SHA3-256(payload||0xFF) ⊕ NOT(sense)
faiss.add_tx_bh_batch() → POST per-tx BHs to FAISS ledger
```

---

## Node.js Dependency Note

The root `package.json` and `relayer/package.json` include `@0glabs/0g-ts-sdk` which pulls in `es5-ext` — blocked by Replit's security policy. The workaround: `ethers` and `axios` are installed standalone into `relayer/node_modules/`, `trion-0g/node_modules/`, and `native-relayer/node_modules/` separately. Do not run plain `npm install` in these directories — it will fail on `es5-ext`. Use `npm install <package> --no-save --prefix /tmp/<name>` then copy.

---

## User Preferences

- Do not touch the 9,043-line `oracle_api/app.py` unless specifically asked — risk of regression is high
- Do not touch `akashic/faiss_service.py` unless specifically asked
- All routes follow `/api/v1/` prefix convention
- Python runtime is managed by `uv` — use `uv run python3` not `python3` directly
- Rust builds are slow (~40s cold, ~0s warm) — the supervisor waits for FAISS before starting
- Relayers run in DRY_RUN mode unless `RELAYER_PRIVATE_KEY` is set in Secrets
