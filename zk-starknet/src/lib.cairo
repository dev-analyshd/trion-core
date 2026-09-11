// SPDX-License-Identifier: CC0-1.0
// TRION Protocol — ZK Starknet Substrate
// Workspace entry point for S1-S5 ZK circuits (library modules — testable)
//
// The zk_verifier contract module is compiled separately via the
// [[target.starknet-contract]] target in Scarb.toml. It is NOT included
// here because #[starknet::contract] modules cannot be compiled in the
// library (test) context.

pub mod hash_dna;
pub mod s1_intent_commitment;
pub mod s2_iap_share;
pub mod s3_travel_rule;
pub mod s4_sensing_oracle;
pub mod s5_birp;
