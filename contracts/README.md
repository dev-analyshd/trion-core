# TRION Protocol — Smart Contracts

One directory per VM family. No duplicates across chains/ or hardhat/.

## Structure

| Directory | Language | VM Family | Files | Description |
|-----------|----------|-----------|-------|-------------|
| `solidity/` | Solidity | EVM | 36 | EVM contracts (ETH, ARB, BASE, OP, etc.) |
| `starknet/` | Cairo | CairoVM | 38 | Starknet contracts (merged from contracts/cairo + chains/starknet) |
| `move/` | Move | Move VM | 7 | Aptos + Movement contracts |
| `svm/` | Rust | Solana | 4 | Solana programs (BPF) |
| `ton/` | FunC | TVM | 9 | TON contracts |
| `near/` | Rust | NEAR | 6 | NEAR contracts (WASM) |
| `pvm/` | Rust | Polkadot | 10 | Polkadot/Substrate contracts |
| `cosmwasm/` | Rust | CosmWasm | 3 | Cosmos WASM contracts |
| `soroban/` | Rust | Soroban | 1 | Stellar/Ripple contracts |
| `vyper/` | Vyper | EVM | 3 | Vyper contracts (alternative EVM) |
| `test/` | Solidity | — | 6 | Test contracts |
| `zk-circuits/` | Circom | ZK | 5 | Zero-knowledge circuits |

## Rules

- Each VM family has exactly one directory under `contracts/`
- No contract files in `chains/` — all moved to `contracts/`
- No contract files in `hardhat/` — all moved to `contracts/solidity/`
- `contracts/starknet/` is the single Cairo workspace (merged from `contracts/cairo`)
- Compiled artifacts go in `contracts/solidity/compiled/`

## Clarity Contracts (Stacks)

Chain-agnostic Clarity contracts for the TRION BTCP Zero-Bridge on Stacks:

| Contract | Purpose |
|----------|---------|
| `clarity/BTCSPVVerifier.clar` | Bitcoin SPV light-client verifier (headers, PoW, Merkle proof) |
| `clarity/BTCPEscrow.clar` | BTCP escrow with 3-of-5 quorum, etch-once attestations, dispute fail-closed |
| `clarity/BTCPIntent.clar` | Cross-chain intent registry (5 actions, 7-status lifecycle) |
| `clarity/BTCPRoute.clar` | Route registry linking anchor_bh → execution_bh (7 route types) |
| `clarity/LiquidityOcean.clar` | Liquidity commitments with coherence gate |
| `clarity/BehavioralLimitOrder.clar` | Limit orders with partial-fill support |
| `clarity/Clarinet.toml` | Clarinet project configuration |

### Deployed on Stacks Testnet

- SPV Verifier: `ST969AZNDX2P7N1YJ0DNVGC8QEKT388DBMXGHR9Z.spv-v2`
- Escrow: `ST969AZNDX2P7N1YJ0DNVGC8QEKT388DBMXGHR9Z.btcpescrow`
- 13 BTC headers synced (blocks 5128443–5128455)
- Genesis renounced (immutable)
- 3-of-3 quorum verified (Q1 reverts, Q2 succeeds)
- 20/20 verify-anchor rounds passed

See `docs/proofs/stacks_verify_anchor_results.json` for on-chain proof.
