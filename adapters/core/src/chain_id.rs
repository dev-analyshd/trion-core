//! `ChainId` — canonical chain identifier (EIP-155 style for EVM, custom
//! for non-EVM). Re-exported as a type alias for `u64` so adapters can
//! use it in `match` arms without boxing.

/// Canonical TRION chain identifier.
///
/// EVM chains use their EIP-155 ids verbatim (1=Mainnet, 10=OP, 56=BNB,
/// 137=Polygon, 8453=Base, 42161=Arbitrum, 43114=Avalanche).
/// Non-EVM chains use the ids from `config/chain_registry.json`.
pub type ChainId = u64;
