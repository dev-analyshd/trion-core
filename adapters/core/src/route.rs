//! `Route` — the BTCP router's chosen execution plan for an [`Intent`].
//!
//! Minimal field set: the adapter trait signature only needs a route id
//! and the underlying intent (the router's chosen leg breakdown, gas
//! forecast, BEO continuity, etc. live in the richer `rust/src/types.rs`
//! `Route` struct).

use crate::intent::Intent;
use crate::tx_hash::TxHash;
use serde::{Deserialize, Serialize};

/// Route identifier — same 32-byte hash family as [`TxHash`].
pub type RouteId = TxHash;

/// BTCP execution route — the chosen path an adapter translates into a
/// chain-native transaction.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Route {
    /// Route id (anchor BH of the BTCP route, or zero for synthetic test
    /// fixtures).
    pub route_id: RouteId,
    /// The intent this route serves.
    pub intent: Intent,
    /// Optional explicit execution-chain override (when the router
    /// picked a non-source chain per BTCP "anchor on A, execute on B").
    pub exec_chain: Option<crate::chain_id::ChainId>,
}
