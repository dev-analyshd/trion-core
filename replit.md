# TRION Protocol — Multi-Chain Behavioral Truth Oracle

## Overview
TRION is a pre-execution DeFi firewall and behavioral oracle that monitors entity behavior across 100+ chains and 13 VM families. It identifies attackers (flash loans, governance capture, MEV) and can block them before transactions execute via the `TRIONExecutionGate` smart contract.

## Architecture

| Layer | Stack | Port |
|---|---|---|
| Oracle API (intelligence engine) | Python / Flask + SocketIO | 5000 |
| FAISS ANIMA (behavioral memory) | Python / FastAPI + PyTorch | 8000 |
| Attack Alert Webhook | Python / Flask | 6000 |
| EVM Rust Indexers (53 chains) | Rust | — |
| TRION Relayer + 0G stack | Node.js (ethers v6) | — |
| Extended Chain Relayer (38 non-EVM chains) | Node.js | — |
| Native VM Relayer (SVM/NEAR/TON/PVM/StarkNet) | Node.js + chain SDKs | — |

## How to Run

All services are configured as Replit workflows. Start them via the **Run** button or the Workflows panel:

1. **Start application** — Oracle API (`serve.py`) on port 5000 — this is the main entry point / dashboard
2. **FAISS ANIMA** — Behavioral vector engine on port 8000 (start before relayers)
3. **Rust Indexers** — Builds & runs EVM + SVM indexers; waits for FAISS to be ready
4. **TRION Relayer** — EVM relayer + 0G ExecutionGate + DA streamer + sync daemon
5. **Extended Chain Relayer** — 38 non-EVM chain relayer (UTXO, Cosmos, Move, etc.)
6. **Native Relayer** — Live signing for Solana, NEAR, TON, Polkadot, StarkNet
7. **Attack Alert Webhook** — Webhook service polling Oracle API every 30s
8. **Genesis Backfill** — Background backfill of historical behavioral data
9. **TRION Dashboard** — Label-only workflow; dashboard is served by the Oracle API

## Secrets Configured

All private keys, RPC URLs, and contract addresses are stored as Replit Secrets. Key secrets include:
- `RELAYER_PRIVATE_KEY` — EVM relayer signing key
- `ZG_AKASHIC_CONTRACT` — 0G Akashic contract address
- `SOLANA_RELAYER_PRIVATE_KEY`, `NEAR_PRIVATE_KEY`, `TON_PRIVATE_KEY_HEX`, `DOT_MNEMONIC`, `STARKNET_PRIVATE_KEY` — native VM signing keys
- Chain-specific private keys for UTXO/Cosmos/Move VMs
- `TIMESCALEDB_URL` — TimescaleDB for vector persistence

## Known Limitations (as of setup)

- **On-chain contract addresses for mainnet EVM chains are not set** — the TRION Relayer operates in `would publish` mode for most EVM chains; only testnets (Arb Sepolia, ETH Sepolia, Base Sepolia, 0G Galileo) and HashKey Mainnet have deployed contracts
- **0G DA node** (`da-node.0g.ai`) is unreachable — the relayer falls back to local proof hashes
- **Native VM accounts have zero balance** — SVM, TON, NEAR, Cosmos-SDK wallets record block proofs instead of live transactions until funded
- **`bh_ledger.db`** — symlinked from `akashic/bh_ledger.db` to workspace root for the Oracle API's protocol segmentation module
- **`@0glabs/0g-ts-sdk`** — installed in `trion-0g/` for the 0G upload scripts

## Dependencies Installed

```
relayer/          npm install   (ethers, axios, @cosmjs/*, @aptos-labs/ts-sdk, etc.)
native-relayer/   npm install   (@polkadot/api, @solana/web3.js, near-api-js, starknet, etc.)
chains/svm/       npm install   (@solana/web3.js, @coral-xyz/anchor, bs58)
chains/near/      npm install   (near-api-js, bs58, tweetnacl)
chains/ton/       npm install   (@ton/ton, @ton/crypto, @ton/core)
chains/pvm/       npm install   (@polkadot/api, @polkadot/keyring)
chains/starknet/  npm install   (starknet, axios, dotenv)
chains/sui/       npm install   (@mysten/sui, tsx, typescript)
trion-0g/         npm install   (@0glabs/0g-ts-sdk, ethers, crypto-js)
```

## User Preferences
