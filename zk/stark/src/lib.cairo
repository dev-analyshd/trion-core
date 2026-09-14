// SPDX-License-Identifier: CC0-1.0
// TRION Protocol — ZK Starknet Substrate
// Library modules (testable) — the zk_verifier contract is in a separate
// sub-package at zk-starknet/contract/ to avoid #[starknet::contract]
// compilation conflicts with the test runner.

pub mod hash_dna;
pub mod s1_intent_commitment;
pub mod s2_iap_share;
pub mod s3_travel_rule;
pub mod s4_sensing_oracle;
pub mod s5_birp;
