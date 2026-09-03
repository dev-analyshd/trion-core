# TRION Cairo Contracts — Starknet

Cairo 2.x implementations of the TRION Protocol core contracts, ported from Solidity.
These enable Zero-Bridge cross-chain tests between Starknet and EVM, SVM (Solana),
WASM (NEAR), and TVM (TON) chains.

## Contracts

| Contract | Purpose | Status |
|----------|---------|--------|
| `TRIONOracleV3` | Behavioral truth oracle with BTCP route registry | ✅ Compiled |
| `TRIONExecutionGate` | Autonomous execution safety layer | ✅ Compiled |
| `TRIONSensingOracle` | Behavioral truth publishing with privacy | ✅ Compiled |
| `TRIONPriceFeed` | Chainlink-compatible behavioral price feed | ✅ Compiled |
| `TRIONFirewall` | Pre-execution behavioral firewall | ✅ Compiled |
| `TRIONLiquidityGuard` | NL-score gated swap router guard | ✅ Compiled |
| `AkashicProof` | Permanent onchain proof of behavioral truth | ✅ Compiled |
| `ConfidentialCoherenceVault` | Coherence-gated ERC-20 vault | ✅ Compiled |
| `TRIONProtectedVault` | Test vault protected by coherence gate | ✅ Compiled |
| `MockOracle` | Test mock oracle (always returns safe) | ✅ Compiled |
| `MockTRIONToken` | ERC-20 style test token | ✅ Compiled |
| `ReentrantAttacker` | Reentrancy test contract | ✅ Compiled |

## Build

```bash
scarb build
```

Artifacts are produced in `target/dev/`:
- `*.contract_class.json` — for deployment via ArgentX or Starknet.js
- `*.compiled_contract_class.json` — compiled CASM

## Zero-Bridge Deployment Order (Starknet ↔ BOT Chain)

1. Deploy `TRIONOracleV3` — publish BTCP routes
2. Deploy `MockTRIONToken` — test asset
3. Deploy `TRIONExecutionGate` — execution safety
4. Run Zero-Bridge test: Entity A locks on Starknet, Entity B locks on BOT Chain,
   TRION Oracle verifies BEO identity continuity, BTCP Score ≥ 0.50, dual release.

## Author

Hudu Yusuf (Analys) — `dev-analyshd` on GitHub
