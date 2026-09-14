//! `Intent` — the economic intent object the router translates through
//! adapters (BTCP Master Implementation Spec §4.1). Minimal field set
//! sufficient for the adapter trait signature; richer Intent objects in
//! `rust/src/types.rs` (separate workspace) carry the full spec payload.

use crate::chain_id::ChainId;
use serde::{Deserialize, Serialize};

/// Action class — drives adapter dispatch (which `execute_*` method the
/// router routes this intent to). Mirrors the BTCP Master Spec §4.1
/// action enum used in the existing `rust/src/types.rs` Intent (0=SWAP,
/// 1=TRANSFER, 2=LIQUIDITY, 3=STAKE, 4=BORROW).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[repr(u8)]
pub enum IntentAction {
    Swap       = 0,
    Transfer   = 1,
    Liquidity  = 2,
    Stake      = 3,
    Borrow     = 4,
}

impl Default for IntentAction {
    fn default() -> Self {
        IntentAction::Swap
    }
}

impl IntentAction {
    /// Lowercase label used in adapter dispatch logs and SYNTHETIC-DEMO
    /// calldata tags.
    pub fn as_str(&self) -> &'static str {
        match self {
            IntentAction::Swap      => "swap",
            IntentAction::Transfer  => "transfer",
            IntentAction::Liquidity => "liquidity",
            IntentAction::Stake     => "stake",
            IntentAction::Borrow    => "borrow",
        }
    }
}

/// Economic intent — what the user wants, not how to execute it.
///
/// This minimal struct carries the fields every adapter actually needs
/// to encode a chain-native transaction (asset pair, amount, source /
/// destination address, deadline, action class). The richer spec §4.1
/// Intent (constraints, privacy, max_total_gas, min_finality, etc.)
/// lives in `rust/src/types.rs::Intent` — adapters that need those
/// constraints can lift them via a `From` impl in the consuming crate.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Intent {
    /// User-specified action class — drives adapter dispatch.
    pub action: IntentAction,
    /// Source chain (canonical ChainId).
    pub source_chain: ChainId,
    /// Destination chain (canonical ChainId).
    pub dest_chain: ChainId,
    /// Source asset ticker / contract address (chain-native encoding is
    /// the adapter's responsibility).
    pub asset_in: String,
    /// Destination asset ticker / contract address.
    pub asset_out: String,
    /// Source amount in the smallest native unit (wei, lamports, etc.).
    pub amount_in: u128,
    /// Source address (EVM hex, SVM base58, Cosmos bech32, Move hex).
    pub source_address: String,
    /// Destination address.
    pub dest_address: String,
    /// Optional minimum output amount (slippage protection) — encoded
    /// into the swap call's `amountOutMinimum` / equivalent.
    pub min_amount_out: Option<u128>,
    /// Unix-seconds deadline; adapters reject intents past this.
    pub deadline: u64,
}
