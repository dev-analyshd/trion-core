//! TRION Protocol — NEAR Contracts (separate)
//! ===========================================
//! This crate exposes the TRION contract surface split into independent
//! modules. The existing combined `BTCPContract` under
//! `chains/near/contract/src/lib.rs` continues to be the canonical
//! deployment — these files provide modular expansions for users that
//! prefer per-feature contracts (oracle / route / gate / token / staking).
//!
//! Modules:
//!   - `trion_oracle`          — TRIONOracleV3 equivalent (signal publication + verification)
//!   - `btcp_route`            — BTCPRoute equivalent (anchor BH -> execution BH)
//!   - `trion_execution_gate` — TRIONExecutionGate equivalent (behavioral firewall)
//!   - `trion_token`          — TRIONToken (NEP-141 fungible token; 0% inflation, 7-type slashing)
//!   - `trion_staking`        — TRIONStaking (validator staking + slashing integration)

pub mod trion_oracle;
pub mod btcp_route;
pub mod trion_execution_gate;
pub mod trion_token;
pub mod trion_staking;
