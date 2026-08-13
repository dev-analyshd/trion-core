//! TRION BTCP — Behavioral Transaction Continuity Protocol
//!
//! 18 Rust modules implementing the BTCP Master Implementation Spec.
//! This is the production Rust implementation for <200ms BIBL latency.
//!
//! # Modules
//! - `router` — Module 2.1: BTCP route scoring and selection (K1 Resolution)
//! - `escrow` — Module 2.2: Escrow state machine with cascade revert (Gap 8, 9)
//! - `bibl` — Module 2.3: BIBL three-tier engine (D3 Resolution)
//! - `modules` — Modules 2.4-2.18: All remaining BTCP modules
//! - `planes` — 7-Plane coherence (Gap 2 Resolution)
//! - `manipulation` — 7 MF fingerprint types (BTCP_15 Gap 3)
//!
//! # BTCP Score Formula (K1 Resolution)
//! ```text
//! BTCP_score = [0.25×NL + 0.20×gas_norm + 0.20×finality
//!              + 0.15×CC_coh + 0.20×BEO_continuity] × (1 - MF_score)
//! ```

pub mod router;
pub mod escrow;
pub mod bibl;
pub mod modules;
pub mod planes;
pub mod manipulation;

// Re-export key types
pub use router::{BiblState, Route, RouteType, btcp_score_final, select_optimal_route};
pub use escrow::{EscrowMonitor, EscrowState, RevertReason};
pub use bibl::BiblEngine;
pub use modules::*;
pub use planes::SevenPlaneCoherence;
pub use manipulation::MfDetector;
