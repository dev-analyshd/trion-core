//! adapters/ — Chain Adapter trait (BTCP Master Implementation Spec §4.2
//! Step 4 "VM Translation Layer" and §14.1 build-guide item 5
//! "adapters/evm/evm_adapter_btcp.rs")
//!
//! Spec §4.2 Step 4: "TRION does not translate bytecode. It translates
//! economic intent into each chain's native execution through thin
//! adapters." The per-event translation table (spec §4.2):
//!
//! | Event    | EVM             | SVM          | Cosmos    | Move       |
//! |----------|-----------------|--------------|-----------|------------|
//! | SWAP     | Uniswap/Curve   | Jupiter/Orca | Osmosis   | Aptos DEX  |
//! | TRANSFER | ERC-20          | SPL token    | bank send | coin xfer  |
//! | BORROW   | Aave/Compound   | Solend       | Mars      | Aries      |
//! | STAKE    | staking contract| stake account| delegation| staking    |
//!
//! Status — HONEST LIMITATION (AUDIT-RUST [MISSING] item 1 closed at the
//! trait level only): this crate carries NO RPC/web3 client dependency
//! (`rust/Cargo.toml`: sha3 0.10 + hex 0.4 only), so no adapter in this
//! workspace can execute anything yet. Execution methods therefore return
//! [`AdapterError::NotConnected`] — "wire to the trion-evm indexer RPC
//! layer" — instead of fabricating transaction hashes. The existing EVM
//! indexer adapter lives in `indexers/crates/trion-evm` (a separate cargo
//! workspace; NOT modified from here).
//!
//! The spec's trait sketch additionally lists `execute_liquidity`,
//! `execute_borrow` and `execute_stake`; those legs are NOT ported yet
//! and will be added alongside a real execution client — no stub
//! implementations are faked here.

use crate::types::{ChainId, Intent, Route};
use std::fmt;

/// Error returned by chain adapters. Deliberately small: the only failure
/// modes that exist today are "no connection wired" and "operation not
/// implemented for this chain" — no error is invented to make a stub look
/// like a working execution path.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AdapterError {
    /// No RPC client is wired. This crate has no web3/RPC dependency
    /// (see module docs) — wire to the trion-evm indexer RPC layer
    /// (`indexers/crates/trion-evm`) before expecting execution.
    NotConnected {
        /// The chain the adapter was constructed for
        chain_id: ChainId,
        /// What to wire up to make this path work
        hint: &'static str,
    },
    /// The requested operation is not implemented for this chain.
    UnsupportedOperation {
        /// The chain the adapter was constructed for
        chain_id: ChainId,
        /// Name of the unimplemented operation
        operation: &'static str,
    },
}

impl fmt::Display for AdapterError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            AdapterError::NotConnected { chain_id, hint } => {
                write!(f, "chain adapter for chain {} is not connected: {}", chain_id, hint)
            }
            AdapterError::UnsupportedOperation { chain_id, operation } => {
                write!(f, "operation '{}' is not supported on chain {}", operation, chain_id)
            }
        }
    }
}

impl std::error::Error for AdapterError {}

/// Execution outcome status of an adapter transaction.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExecutionStatus {
    /// Broadcast to the mempool, not yet included
    Submitted,
    /// Included and finalized on the target chain
    Confirmed,
    /// Reverted or failed on-chain
    Failed,
}

/// Receipt for an executed adapter transaction (spec §4.2 Step 4
/// `verify_execution` target).
///
/// NOTE: no adapter in this crate constructs a receipt today — a wired
/// implementation must fill every field from a real chain response.
/// Field values are never fabricated (AUDIT-RUST fabrication discipline).
#[derive(Debug, Clone)]
pub struct ExecutionReceipt {
    /// Transaction hash on the execution chain
    pub tx_hash: crate::types::H256,
    /// Chain the transaction landed on
    pub chain_id: ChainId,
    /// Gas actually consumed (native gas units)
    pub gas_used: u64,
    /// Inclusion block height
    pub block_number: u64,
    /// Execution outcome
    pub status: ExecutionStatus,
}

/// Chain adapter — the Step 4 VM Translation contract.
///
/// Implementations translate a BTCP [`Intent`] + [`Route`] into the
/// chain's native execution (DEX swap, token transfer, …) and report
/// receipts back to the router. The trait is object-safe so routers can
/// hold `Vec<Box<dyn ChainAdapter>>` keyed by [`ChainAdapter::chain_id`].
///
/// Signatures adapt the spec sketch (`fn execute_swap(&self, intent:
/// &Intent, route: &Route) -> TxHash`) to the honest form used in this
/// crate: `Result<ExecutionReceipt, AdapterError>` — there is no RPC
/// client to produce a `TxHash`, so returning one would be fabrication.
pub trait ChainAdapter {
    /// EIP-155-style chain identifier this adapter targets (for non-EVM
    /// chains the canonical ids from `config/chain_registry.json`).
    fn chain_id(&self) -> ChainId;

    /// Execute the SWAP leg of a route (EVM: route to the best
    /// Uniswap/Curve pool per NL score — spec §14.1 item 5).
    fn execute_swap(
        &self,
        intent: &Intent,
        route: &Route,
    ) -> Result<ExecutionReceipt, AdapterError>;

    /// Execute the TRANSFER leg of a route (EVM: ERC-20 native transfer —
    /// no bridge contract, no wrapped token).
    fn execute_transfer(
        &self,
        intent: &Intent,
        route: &Route,
    ) -> Result<ExecutionReceipt, AdapterError>;

    /// Symbol of the chain's native gas token (e.g. "ETH", "BNB").
    fn native_gas_token(&self) -> &str;

    /// Estimate gas (native units) for the transfer leg of `intent`.
    fn estimate_gas(&self, intent: &Intent) -> Result<u64, AdapterError>;

    /// Verify a previously executed transaction. The spec sketch takes a
    /// bare `TxHash`; this port takes the full [`ExecutionReceipt`] so the
    /// adapter can also check the receipt belongs to its own chain.
    fn verify_execution(&self, receipt: &ExecutionReceipt) -> Result<ExecutionStatus, AdapterError>;
}

pub mod evm;

pub use evm::EvmAdapter;
