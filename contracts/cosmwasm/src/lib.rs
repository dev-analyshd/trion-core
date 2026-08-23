//! TRION Protocol — CosmWasm Contract (canonical wiring)
//! =====================================================
//! Single contract implementing TRIONOracleV3 + BTCPEscrow + BTCPIntent +
//! BTCPRoute + TRIONExecutionGate for the 20 CosmWasm VM chains (Neutron,
//! Archway, Osmosis wasm, Juno, Terra 2, Kujira, Stargaze, Comdex, Crescent,
//! Persistence, Injective wasm, Migaloo, Celestia wasm, Nolus, Sei wasm,
//! Loki, Mantra, etc.).
//!
//! The legacy self-contained variant was consolidated into `contract.rs`
//! (canonical, mirrors the Solidity/Move reference implementations) plus
//! `state.rs` (storage layout). Entry points are re-exported below.

pub mod contract;
pub mod state;

pub use contract::{execute, instantiate, query, ExecuteMsg, InstantiateMsg, QueryMsg};
pub use state::{
    BTCPRoute, Escrow, GateState, Intent, Route, Signal,
};
