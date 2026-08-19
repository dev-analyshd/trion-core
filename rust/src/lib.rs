//! TRION BTCP Zero-Bridge — Rust Implementation
//! 
//! Behavioral Transaction Continuity Protocol
//! The Bridge is Mathematics, Not Contracts.
//! 
//! This crate implements the BTCP core per the BTCP Master Implementation Spec.
//! All 19 required Rust modules are provided, coexisting with the Python
//! reference implementation without breaking it.

pub mod types;
pub mod btcp_router;
pub mod bibl_engine;
pub mod btcp_proof_builder;
pub mod btcp_escrow_monitor;
pub mod bitp_matcher;
pub mod netting_engine;
pub mod intent_aggregator;
pub mod ooa_anchor;
pub mod shadow_observer;
pub mod state_capsule;
pub mod btcp_failure_classifier;
pub mod genesis_commitment;
pub mod blo_scheduler;
pub mod behavioral_state_channel;
pub mod finality_normalizer;
pub mod btcp_version_handler;
pub mod validator_fee_calculator;
pub mod sybil_resistance;
pub mod dispute_resolution;

// Re-exports for convenient access
pub use types::*;
pub use btcp_router::BTCPRouter;
pub use bibl_engine::BIBLEngine;
pub use btcp_proof_builder::BTCPProofBuilder;
pub use btcp_escrow_monitor::EscrowMonitor;
pub use bitp_matcher::BITPMatcher;
pub use netting_engine::NettingEngine;
pub use intent_aggregator::IntentAggregator;
pub use ooa_anchor::OOAAnchor;
pub use shadow_observer::ShadowObserver;
pub use state_capsule::StateCapsuleBuilder;
pub use btcp_failure_classifier::FailureClassifier;
pub use genesis_commitment::GenesisCommitment;
pub use blo_scheduler::BLOScheduler;
pub use behavioral_state_channel::BehavioralStateChannel;
pub use finality_normalizer::FinalityNormalizer;
pub use btcp_version_handler::VersionHandler;
pub use validator_fee_calculator::ValidatorFeeCalculator;
pub use sybil_resistance::SybilResistance;
pub use dispute_resolution::DisputeResolver;

/// BTCP protocol version
pub const BTCP_VERSION: &str = "1.0.0";

/// Gas 99th percentile constant for normalization (spec §Phase 2)
pub const GAS_99TH_PERCENTILE: f64 = 1000.0;

/// Minimum BTCP score threshold for route execution
pub const MIN_BTCP_SCORE: f64 = 0.50;

/// Safe confirmations threshold
pub const SAFE_CONFIRMATIONS: u64 = 64;
