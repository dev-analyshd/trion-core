//! `ExecutionResult` — the canonical verification outcome returned by
//! [`crate::ChainAdapter::verify_execution`].
//!
//! Per R-FAILCLOSED, on network error every adapter returns
//! [`ExecutionResult::Failed`] (never panics). The
//! [`ExecutionResult::Simulated`] variant is reserved for SYNTHETIC-DEMO
//! execution paths per R-LABELS — adapters MUST NOT present a simulated
//! execution as `Confirmed`.

use crate::tx_hash::TxHash;

/// Outcome of verifying a previously-broadcast (or simulated) adapter
/// transaction.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ExecutionResult {
    /// Broadcast to mempool but not yet included / finalised.
    Submitted {
        tx_hash: TxHash,
    },
    /// Included and finalised on the target chain — adapter confirmed
        /// the receipt belongs to its own chain.
    Confirmed {
        tx_hash: TxHash,
        block_number: u64,
        gas_used: u64,
    },
    /// SYNTHETIC-DEMO execution path — the adapter did NOT broadcast a
    /// real transaction. R-LABELS compliant: the label "SYNTHETIC-DEMO"
    /// is encoded in the variant so downstream consumers can never
    /// mistake a simulated run for a mainnet confirmation.
    Simulated {
        tx_hash: TxHash,
        label: &'static str,
    },
    /// The requested operation is not implemented for this chain (used
    /// by GATED adapters per BLOCKER PROTOCOL — e.g. an adapter whose
    /// underlying SDK cannot be installed).
    NotImplemented,
    /// Fail-closed outcome: network error, receipt lookup failed, or
    /// `verify_execution(TxHash::zero())` was called (the canonical
    /// "no transaction broadcast" sentinel returned by every
    /// `execute_*` method on R-FAILCLOSED).
    Failed,
}

/// Backwards-compat alias — the existing `rust/src/adapters/mod.rs`
/// uses `ExecutionStatus` for the same concept. Adapters that need to
/// bridge into the older workspace can `From`-convert.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExecutionStatus {
    Submitted,
    Confirmed,
    Failed,
}

impl From<&ExecutionResult> for ExecutionStatus {
    fn from(r: &ExecutionResult) -> Self {
        match r {
            ExecutionResult::Submitted { .. } => ExecutionStatus::Submitted,
            ExecutionResult::Confirmed { .. } => ExecutionStatus::Confirmed,
            ExecutionResult::Simulated { .. } => ExecutionStatus::Submitted,
            ExecutionResult::NotImplemented => ExecutionStatus::Failed,
            ExecutionResult::Failed => ExecutionStatus::Failed,
        }
    }
}
