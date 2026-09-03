// SPDX-License-Identifier: MIT
// TRION Protocol — Cairo Contracts for Starknet
// Author: Hudu Yusuf (Analys)
//
// Core behavioral truth infrastructure ported from Solidity to Cairo 2.x.
// These contracts enable Zero-Bridge cross-chain tests between Starknet and
// EVM, SVM, WASM (NEAR), and TVM (TON) chains.

mod mock_oracle;
mod trion_oracle_v3;
mod mock_trion_token;
mod trion_sensing_oracle;
mod trion_execution_gate;
mod trion_price_feed;
mod trion_firewall;
mod trion_liquidity_guard;
mod akashic_proof;
mod confidential_coherence_vault;
mod trion_protected_vault;
mod reentrant_attacker;
mod attack_simulator;
