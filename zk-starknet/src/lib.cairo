// SPDX-License-Identifier: CC0-1.0
// TRION Protocol — ZK Starknet Substrate
// Workspace entry point for S1-S5 ZK circuits
//
// This workspace implements the TRION ZK layer on Starknet (Cairo/STARK),
// substituting the proving substrate from Groth16/PLONK (circom/EVM) to
// STARK (Cairo/Starknet) per C3 §16 permission.
//
// R-DESIGN: all statements, inputs, phases, schemas, tiers, thresholds
// are VERBATIM from canon (BTCP §5.6, §5.3, Fix 1, §7.1; C3 §16).
// Only the proving substrate moved.

pub mod hash_dna;
pub mod s1_intent_commitment;
pub mod s2_iap_share;
pub mod s3_travel_rule;
pub mod s4_sensing_oracle;
pub mod s5_birp;
pub mod zk_verifier;
