//! TRION CosmWasm — State keys + structs
//! =======================================
//! State layout for the combined TRION Oracle + BTCP Escrow + Intent + Route
//! contract. All keys are namespaced under b"trion::" to avoid collisions.
//!
//! Mirrors contracts/solidity/{TRIONOracleV3,BTCPEscrow,BTCPIntent,BTCPRoute}.sol
//! storage layout. Each Solidity `mapping(bytes32 => T)` becomes a cw_storage_plus
//! `Map<Vec<u8>, T>` keyed by the canonical 32-byte identifier.

use cosmwasm_std::{Addr, Coin};
use serde::{Deserialize, Serialize};

/// Storage key namespaces.
pub const KEY_OWNER:        &[u8] = b"trion::owner";
pub const KEY_RELAYER:      &[u8] = b"trion::relayer";
pub const KEY_AWA_ENFORCED: &[u8] = b"trion::awa_enforced";

pub const PREFIX_SIGNALS:  &[u8] = b"trion::signals::";
pub const PREFIX_ESCROWS:  &[u8] = b"trion::escrows::";
pub const PREFIX_INTENTS:  &[u8] = b"trion::intents::";
pub const PREFIX_ROUTES:   &[u8] = b"trion::routes::";

/// Behavioral signal — mirrors TRIONOracleV3.Signal + BTCPRoute.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct Signal {
    pub entity_id:     Vec<u8>,
    pub coherence:     u64,    // x1_000_000
    pub threshold:     u64,    // x1_000_000
    pub emits_signal:  bool,
    pub timestamp:     u64,
    pub update_count:  u64,
}

/// BTCPRoute proof — stored alongside signals.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct BTCPRoute {
    pub route_id:      Vec<u8>,
    pub anchor_bh:     Vec<u8>,
    pub execution_bh:  Vec<u8>,
    pub coherence:     u64,
    pub threshold:     u64,
    pub is_safe:       bool,
    pub timestamp:     u64,
}

/// Escrow state lifecycle.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct Escrow {
    pub escrow_id:      Vec<u8>,
    pub route_id:       Vec<u8>,
    pub entity_id:      Vec<u8>,
    pub destination:    Addr,
    pub amount:         u128,
    /// Native denom actually locked at lock time (e.g. "uatom", "ujuno",
    /// "uluna") — release/revert pay back in THIS denom. Previously hardcoded
    /// to "uatom", which broke every non-Atom CosmWasm chain.
    pub denom:          String,
    /// SECURITY FIX (P1 — multi-denom payout duplication): exact per-denom
    /// coins received at lock time. Previously only the joined denom string
    /// + the SUM of all amounts were stored, so release/revert paid the total
    /// amount of EVERY denom (lock 100uatom + 50ujuno → paid 150 uatom AND
    /// 150 ujuno — 2x value out). This vector is now the authoritative payout
    /// record; `denom`/`amount` are kept for display and legacy-state fallback
    /// (`serde(default)` keeps pre-fix stored escrows deserializable).
    #[serde(default)]
    pub locked_coins:   Vec<Coin>,
    pub min_coherence:  u64,
    pub lock_height:    u64,
    pub timeout_blocks: u64,
    pub state:          u8,    // 0=HOLDING 1=RELEASED 2=REVERTED
    pub revert_reason:  u8,
    pub settled_at:     u64,
    pub reverted_at:    u64,
    pub locked_by:      Addr,
}

/// Intent action types (whitepaper BTCP §4.1).
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct Intent {
    pub intent_hash:   Vec<u8>,
    pub entity_id:    Vec<u8>,
    pub action:        u8,    // 0=SWAP 1=TRANSFER 2=LIQUIDITY 3=STAKE 4=BORROW
    pub asset_in:      Vec<u8>,
    pub asset_out:     Vec<u8>,
    pub magnitude:     u64,
    pub source_chain:  u64,
    pub dest_chain:    u64,
    pub deadline:      u64,
    pub max_gas_usd:   u64,
    pub min_nl_score:  u16,
    pub nonce:         u64,
    pub status:        u8,    // 0=PENDING 1=ROUTING 2=EXECUTING 3=COMPLETED 4=FAILED 5=EXPIRED 6=RESURRECTED
    pub created_at:    u64,
    pub submitter:     Addr,
}

/// Route record (whitepaper BTCP §3).
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct Route {
    pub route_id:           Vec<u8>,
    pub intent_hash:        Vec<u8>,
    pub anchor_bh:          Vec<u8>,
    pub execution_bh:       Vec<u8>,
    pub anchor_chain:       u64,
    pub execution_chain:    u64,
    pub entity_id:          Vec<u8>,
    pub gas_saved_vs_bridge:u64,
    pub beo_continuity:     u64,
    pub cc_coherence:       u64,
    pub route_type:         u8,
    pub is_verified:        bool,
    pub created_at:         u64,
    pub finalized_at:       u64,
}

/// Gate state for the behavioral firewall.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct GateState {
    pub gate_id:          Vec<u8>,
    pub custom_threshold: u64,
    pub check_count:      u64,
    pub pass_count:       u64,
    pub block_count:      u64,
    pub last_phi:         u64,
    pub last_entity:      Vec<u8>,
}

/// State constants — exported so they can be reused from contract.rs.
pub const STATE_HOLDING:    u8 = 0;
pub const STATE_RELEASED:   u8 = 1;
pub const STATE_REVERTED:   u8 = 2;

pub const STATUS_PENDING:     u8 = 0;
pub const STATUS_ROUTING:     u8 = 1;
pub const STATUS_EXECUTING:  u8 = 2;
pub const STATUS_COMPLETED:  u8 = 3;
pub const STATUS_FAILED:     u8 = 4;
pub const STATUS_EXPIRED:    u8 = 5;
pub const STATUS_RESURRECTED:u8 = 6;
