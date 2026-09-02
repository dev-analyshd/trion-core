# TRION Protocol — Smart Contracts

This directory contains all TRION Protocol smart contracts organized by VM family.
Each subdirectory corresponds to a blockchain VM (virtual machine) family.

## Contract Index

### Starknet (Cairo) — 8 contracts
**Location:** [`starknet/`](./starknet/) · **Deployed on:** Starknet Sepolia

| Contract | File | Purpose |
|---|---|---|
| TRIONOracle | [`src/TRIONOracle.cairo`](./starknet/src/TRIONOracle.cairo) | BEO behavioral score store (L2 Akashic) |
| BEOAttestation | [`src/BEOAttestation.cairo`](./starknet/src/BEOAttestation.cairo) | Wallet ↔ BEO identity binding |
| BTCFiGuard | [`src/BTCFiGuard.cairo`](./starknet/src/BTCFiGuard.cairo) | BTCFi anti-sybil risk tier module |
| BTCPIntent | [`src/btcp_intent.cairo`](./starknet/src/btcp_intent.cairo) | Intent registration (BTCP §4.1) |
| BTCPRoute | [`src/btcp_route.cairo`](./starknet/src/btcp_route.cairo) | anchor_BH → execution_BH linkage (BTCP §3) |
| BTCPEscrow | [`src/btcp_escrow.cairo`](./starknet/src/btcp_escrow.cairo) | Two-state atomic escrow (BTCP §4.3) |
| LiquidityOcean | [`src/liquidity_ocean.cairo`](./starknet/src/liquidity_ocean.cairo) | Form-equivalent liquidity aggregation (BTCP §6) |
| BIRPAttestation | [`src/BIRPAttestation.cairo`](./starknet/src/BIRPAttestation.cairo) | Privacy-preserving behavioral attestation |

**Deployment:** [`docs/deployments/starknet_sepolia.json`](../docs/deployments/starknet_sepolia.json)
**Verification:** [`docs/proofs/starknet_verification_report.json`](../docs/proofs/starknet_verification_report.json)

---

### EVM / Solidity — 22 contracts
**Location:** [`solidity/`](./solidity/) · **Deployed on:** ETH/Arb/OP/Base Sepolia

| Contract | File | Purpose |
|---|---|---|
| **BTCP Suite** | | |
| BTCPEscrow | [`BTCPEscrow.sol`](./solidity/BTCPEscrow.sol) | Two-state atomic escrow with G1 two-phase settlement |
| BTCPIntent | [`BTCPIntent.sol`](./solidity/BTCPIntent.sol) | Intent registration + lifecycle |
| BTCPRoute | [`BTCPRoute.sol`](./solidity/BTCPRoute.sol) | Route tracking with anchor/execution BH |
| LiquidityOcean | [`LiquidityOcean.sol`](./solidity/LiquidityOcean.sol) | Form-equivalent liquidity tracking |
| BehavioralLimitOrder | [`BehavioralLimitOrder.sol`](./solidity/BehavioralLimitOrder.sol) | BLO storage + partial fill logic |
| BTCPGasAbstraction | [`BTCPGasAbstraction.sol`](./solidity/BTCPGasAbstraction.sol) | Gas abstraction for cross-chain |
| BTCPVersionRegistry | [`BTCPVersionRegistry.sol`](./solidity/BTCPVersionRegistry.sol) | Protocol versioning |
| GenesisCommitment | [`GenesisCommitment.sol`](./solidity/GenesisCommitment.sol) | Null-state entity genesis |
| TravelRuleCompliance | [`TravelRuleCompliance.sol`](./solidity/TravelRuleCompliance.sol) | ZK Travel Rule FATF compliance |
| **Oracle Suite** | | |
| TRIONOracle | [`TRIONOracle.sol`](./solidity/TRIONOracle.sol) | Base behavioral oracle |
| TRIONOracleV3 | [`TRIONOracleV3.sol`](./solidity/TRIONOracleV3.sol) | Enhanced oracle with BTCP route safety |
| TRIONSensingOracle | [`TRIONSensingOracle.sol`](./solidity/TRIONSensingOracle.sol) | On-chain sensing oracle |
| TRIONPriceFeed | [`TRIONPriceFeed.sol`](./solidity/TRIONPriceFeed.sol) | Chainlink-compatible price feed |
| **Security Suite** | | |
| TRIONExecutionGate | [`TRIONExecutionGate.sol`](./solidity/TRIONExecutionGate.sol) | Pre-execution behavioral firewall |
| TRIONGuardV3 | [`TRIONGuardV3.sol`](./solidity/TRIONGuardV3.sol) | Emergency bypass with time-box |
| TRIONFirewall | [`TRIONFirewall.sol`](./solidity/TRIONFirewall.sol) | Protocol-level firewall |
| TRIONLiquidityGuard | [`TRIONLiquidityGuard.sol`](./solidity/TRIONLiquidityGuard.sol) | Liquidity protection |
| SanctionsOracle | [`SanctionsOracle.sol`](./solidity/SanctionsOracle.sol) | OFAC/EU/UN sanctions screening |
| **Identity & Vault** | | |
| BEOAttestation | [`BEOAttestation.sol`](./solidity/BEOAttestation.sol) | EVM BEO identity binding |
| BTCFiGuard | [`BTCFiGuard.sol`](./solidity/BTCFiGuard.sol) | BTCFi anti-sybil risk tier |
| ConfidentialCoherenceVault | [`ConfidentialCoherenceVault.sol`](./solidity/ConfidentialCoherenceVault.sol) | ERC-20 vault gated by coherence |
| AkashicProof | [`AkashicProof.sol`](./solidity/AkashicProof.sol) | On-chain Akashic proof storage |

**Compiled artifacts:** [`solidity/compiled/`](./solidity/compiled/) (ABI + bytecode JSON)
**Deployment:** [`docs/deployments/evm_sepolia.json`](../docs/deployments/evm_sepolia.json)

---

### Vyper — 2 contracts
**Location:** [`vyper/`](./vyper/)

| Contract | File | Purpose |
|---|---|---|
| TRIONToken | [`TRIONToken.vy`](./vyper/TRIONToken.vy) | TRION token (0% inflation, 7-type slashing) |
| TRIONStaking | [`TRIONStaking.vy`](./vyper/TRIONStaking.vy) | Staking with coverage tiers |

---

### NEAR (Rust) — 5 contracts
**Location:** [`near/`](./near/) · **Deployed on:** NEAR testnet (`trion.testnet`)

| Contract | File | Purpose |
|---|---|---|
| BTCPContract | [`src/lib.rs`](./near/src/lib.rs) | Combined intent + escrow contract |
| BTCPRoute | [`src/btcp_route.rs`](./near/src/btcp_route.rs) | Route tracking |
| TRIONOracle | [`src/trion_oracle.rs`](./near/src/trion_oracle.rs) | Behavioral oracle |
| TRIONExecutionGate | [`src/trion_execution_gate.rs`](./near/src/trion_execution_gate.rs) | Execution gate |
| TRIONToken | [`src/trion_token.rs`](./near/src/trion_token.rs) | TRION token |

**Deployment:** [`docs/deployments/near_testnet.json`](../docs/deployments/near_testnet.json)

---

### Solana (SVM/Anchor) — 4 programs
**Location:** [`svm/`](./svm/) · **Deployed on:** Solana devnet

| Program | File | Purpose |
|---|---|---|
| btcp_common | [`programs/btcp_common/src/lib.rs`](./svm/programs/btcp_common/src/lib.rs) | Shared types + errors |
| btcp_escrow | [`programs/btcp_escrow/src/lib.rs`](./svm/programs/btcp_escrow/src/lib.rs) | Escrow with PDA vault |
| btcp_intent | [`programs/btcp_intent/src/lib.rs`](./svm/programs/btcp_intent/src/lib.rs) | Intent registration |
| btcp_route | [`programs/btcp_route/src/lib.rs`](./svm/programs/btcp_route/src/lib.rs) | Route tracking |

**Deployment:** [`docs/deployments/solana_devnet.json`](../docs/deployments/solana_devnet.json)

---

### TON (FunC) — 9 contracts
**Location:** [`ton/`](./ton/)

| Contract | File | Purpose |
|---|---|---|
| escrow | [`escrow.fc`](./ton/escrow.fc) | Two-state atomic escrow |
| intent | [`intent.fc`](./ton/intent.fc) | Intent registration |
| route | [`route.fc`](./ton/route.fc) | Route tracking |
| oracle | [`oracle.fc`](./ton/oracle.fc) | TRION Oracle V3 |
| gate | [`gate.fc`](./ton/gate.fc) | Behavioral firewall |
| liquidity | [`liquidity.fc`](./ton/liquidity.fc) | Liquidity tracking |
| staking | [`staking.fc`](./ton/staking.fc) | Coverage-tier staking |
| token | [`token.fc`](./ton/token.fc) | TRION token (1B supply) |
| stdlib | [`stdlib.fc`](./ton/stdlib.fc) | Minimal stdlib shim |

---

### Polkadot PVM (ink!) — 8 contracts
**Location:** [`pvm/`](./pvm/)

| Contract | File | Purpose |
|---|---|---|
| btcp_route | [`btcp_route/src/lib.rs`](./pvm/btcp_route/src/lib.rs) | 6-state escrow + cascade revert |
| gate | [`gate/src/lib.rs`](./pvm/gate/src/lib.rs) | Behavioral firewall |
| genesis | [`genesis/src/lib.rs`](./pvm/genesis/src/lib.rs) | Identity + sponsored genesis |
| intent | [`intent/src/lib.rs`](./pvm/intent/src/lib.rs) | 7-state intent lifecycle |
| liquidity | [`liquidity/src/lib.rs`](./pvm/liquidity/src/lib.rs) | Commitment contract |
| staking | [`staking/src/lib.rs`](./pvm/staking/src/lib.rs) | Coverage-tier staking |
| token | [`token/src/lib.rs`](./pvm/token/src/lib.rs) | 0% inflation token |
| travel_rule | [`travel_rule/src/lib.rs`](./pvm/travel_rule/src/lib.rs) | Chameleon FATF modes |

---

### Move (Aptos/Sui) — 5 contracts
**Location:** [`move/`](./move/)

| Contract | File | Purpose |
|---|---|---|
| btcp_escrow | [`sources/btcp_escrow.move`](./move/sources/btcp_escrow.move) | Escrow |
| btcp_intent | [`sources/btcp_intent.move`](./move/sources/btcp_intent.move) | Intent registration |
| btcp_route | [`sources/btcp_route.move`](./move/sources/btcp_route.move) | Route tracking |
| trion_oracle | [`sources/trion_oracle.move`](./move/sources/trion_oracle.move) | Behavioral oracle |
| trion_execution_gate | [`sources/trion_execution_gate.move`](./move/sources/trion_execution_gate.move) | Execution gate |

---

### Stellar Soroban (Rust) — 1 contract
**Location:** [`soroban/`](./soroban/)

| Contract | File | Purpose |
|---|---|---|
| TRION Soroban | [`src/lib.rs`](./soroban/src/lib.rs) | Stellar BTCP contract |

---

### CosmWasm (Rust) — 1 contract
**Location:** [`cosmwasm/`](./cosmwasm/)

| Contract | File | Purpose |
|---|---|---|
| TRION CosmWasm | [`src/contract.rs`](./cosmwasm/src/contract.rs) | Combined BTCP contract |

---

### Cairo (Legacy) — 12 contracts
**Location:** [`cairo/`](./cairo/) · **Note:** Older Cairo contracts (pre-restructure)

Includes: `trion_oracle_v3.cairo`, `trion_sensing_oracle.cairo`, `trion_execution_gate.cairo`, `trion_firewall.cairo`, `trion_liquidity_guard.cairo`, `trion_price_feed.cairo`, `trion_protected_vault.cairo`, `confidential_coherence_vault.cairo`, `akashic_proof.cairo`, `attack_simulator.cairo`, `mock_oracle.cairo`, `mock_trion_token.cairo`

---

### Deployment Scripts & Tests
- **Foundry scripts:** [`script/Deploy.s.sol`](./script/Deploy.s.sol)
- **Solidity tests:** [`test/`](./test/) (ExecutionGate, Pause, Quorum, Reentrancy)
- **Foundry config:** [`foundry.toml`](./foundry.toml)

## Total: 65+ contracts across 9 VM families

---

*All contracts are open source under CC0. See [main README](../README.md) for deployment addresses and on-chain proofs.*
