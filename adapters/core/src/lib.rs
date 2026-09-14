//! adapters-core — the shared `ChainAdapter` trait + minimal shared types
//! for the BTCP VM Translation Layer (C3 §4 Step 4 verbatim + §14.1 Phase 5).
//!
//! Per C3 §4 Step 4 verbatim:
//!
//! ```text
//! pub trait ChainAdapter {
//!     fn execute_swap(&self, intent: &Intent, route: &Route) -> TxHash;
//!     fn execute_transfer(&self, intent: &Intent, route: &Route) -> TxHash;
//!     fn execute_liquidity(&self, intent: &Intent, route: &Route) -> TxHash;
//!     fn execute_borrow(&self, intent: &Intent, route: &Route) -> TxHash;
//!     fn execute_stake(&self, intent: &Intent, route: &Route) -> TxHash;
//!     fn verify_execution(&self, tx_hash: TxHash) -> ExecutionResult;
//! }
//! ```
//!
//! This crate defines the trait verbatim and the minimal `Intent`, `Route`,
//! `TxHash`, `ExecutionResult` types the signature depends on. The existing
//! `trion-common` indexer crate does NOT export these (it exports
//! `ChainIndexer` / `FaissClient` / `build_vector` for L0 ingestion), so
//! the BTCP execution layer carries its own minimal copies here.
//!
//! # R-FAILCLOSED compliance
//!
//! Every adapter method must fail closed: on network error the `execute_*`
//! family returns [`TxHash::zero()`] (the canonical "no transaction
//! broadcast" sentinel — provably NOT a real hash because the
//! [`ChainAdapter::verify_execution`] lookup of a zero hash returns
//! [`ExecutionResult::Failed`]), and `verify_execution` itself returns
//! [`ExecutionResult::Failed`] on RPC error. **No method ever panics**.
//!
//! # R-GENERIC compliance
//!
//! Trait method names carry no chain prefix: `execute_swap` (correct), not
//! `evm_swap` (wrong). Chain-specific behaviour lives in the impl, not the
//! signature.
//!
//! # R-LABELS compliance
//!
//! Mock execution paths are labelled `SYNTHETIC-DEMO` in the
//! [`ExecutionResult::Simulated`] variant — never as `Confirmed`.

use sha3::{Digest, Sha3_256};

// ── Public API surface ─────────────────────────────────────────────────────
pub use chain_id::ChainId;
pub use execution::{ExecutionResult, ExecutionStatus};
pub use intent::{Intent, IntentAction};
pub use route::{Route, RouteId};
pub use tx_hash::TxHash;

mod chain_id;
mod execution;
mod intent;
mod route;
mod tx_hash;

/// The Step 4 VM Translation contract (C3 §4 Step 4 verbatim).
///
/// Implementations translate a BTCP [`Intent`] + [`Route`] into the chain's
/// native execution (DEX swap, token transfer, LP position, Aave borrow,
/// validator stake) and report receipts back via [`ChainAdapter::verify_execution`].
///
/// The trait is object-safe so routers can hold `Vec<Box<dyn ChainAdapter>>`
/// keyed by [`ChainAdapter::chain_id`].
pub trait ChainAdapter: Send + Sync {
    /// Canonical chain identifier this adapter targets (EIP-155 style for
    /// EVM, custom ids from `config/chain_registry.json` for non-EVM).
    fn chain_id(&self) -> ChainId;

    /// Human-readable VM family label (e.g. "EVM", "SVM", "COSMOS",
    /// "MOVE", "COSMWASM"). Used for log lines and `ExecutionResult` tags
    /// only — never appears in trait method names (R-GENERIC).
    fn vm_type(&self) -> &'static str;

    /// Execute the SWAP leg of a route.
    ///
    /// Per C3 §4 Step 4 translation table:
    /// - EVM → Uniswap/Curve router
    /// - SVM → Jupiter/Orca aggregator
    /// - Cosmos → Osmosis swap
    /// - Move → Aptos DEX
    ///
    /// Returns a [`TxHash`] on success, [`TxHash::zero()`] on fail-closed
    /// network error (R-FAILCLOSED).
    fn execute_swap(&self, intent: &Intent, route: &Route) -> TxHash;

    /// Execute the TRANSFER leg of a route (EVM: ERC-20 transfer; SVM:
    /// SPL token transfer; Cosmos: bank send; Move: coin transfer).
    fn execute_transfer(&self, intent: &Intent, route: &Route) -> TxHash;

    /// Execute the LIQUIDITY leg of a route (EVM: LP position; SVM: Raydium
    /// pool; Cosmos: GAMM pool; Move: liquidity module).
    fn execute_liquidity(&self, intent: &Intent, route: &Route) -> TxHash;

    /// Execute the BORROW leg of a route (EVM: Aave/Compound; SVM: Solend;
    /// Cosmos: Mars; Move: Aries Markets).
    fn execute_borrow(&self, intent: &Intent, route: &Route) -> TxHash;

    /// Execute the STAKE leg of a route (EVM: staking contract; SVM: stake
    /// account; Cosmos: delegation; Move: staking module).
    fn execute_stake(&self, intent: &Intent, route: &Route) -> TxHash;

    /// Verify a previously executed transaction by hash. Returns the
    /// canonical [`ExecutionResult`]; on network error returns
    /// [`ExecutionResult::Failed`] (R-FAILCLOSED).
    fn verify_execution(&self, tx_hash: TxHash) -> ExecutionResult;
}

/// Derive a deterministic SYNTHETIC-DEMO TxHash from `payload` (used by
/// every adapter's mock execution path so the returned [`TxHash`] is a
/// reproducible function of the calldata, not a fabricated real hash).
///
/// Per R-LABELS the resulting hash must NOT be presented as a real
/// mainnet hash; the adapter that produced it tags the corresponding
/// [`ExecutionResult`] as [`ExecutionResult::Simulated`].
pub fn synthetic_tx_hash(payload: &[u8]) -> TxHash {
    let mut hasher = Sha3_256::new();
    hasher.update(b"TRION-SYNTHETIC-DEMO|");
    hasher.update(payload);
    let digest = hasher.finalize();
    let mut bytes = [0u8; 32];
    bytes.copy_from_slice(&digest);
    TxHash(bytes)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Trait object dispatch smoke test — every adapter crate re-exports
    /// this pattern in its own tests to confirm `Box<dyn ChainAdapter>`
    /// resolves correctly across VMs.
    struct DummyAdapter;
    impl ChainAdapter for DummyAdapter {
        fn chain_id(&self) -> ChainId { 0 }
        fn vm_type(&self) -> &'static str { "DUMMY" }
        fn execute_swap(&self, _: &Intent, _: &Route) -> TxHash { TxHash::zero() }
        fn execute_transfer(&self, _: &Intent, _: &Route) -> TxHash { TxHash::zero() }
        fn execute_liquidity(&self, _: &Intent, _: &Route) -> TxHash { TxHash::zero() }
        fn execute_borrow(&self, _: &Intent, _: &Route) -> TxHash { TxHash::zero() }
        fn execute_stake(&self, _: &Intent, _: &Route) -> TxHash { TxHash::zero() }
        fn verify_execution(&self, tx: TxHash) -> ExecutionResult {
            if tx.is_zero() {
                ExecutionResult::Failed
            } else {
                ExecutionResult::Simulated {
                    tx_hash: tx,
                    label: "SYNTHETIC-DEMO",
                }
            }
        }
    }

    #[test]
    fn trait_object_dispatch_works() {
        let a: Box<dyn ChainAdapter> = Box::new(DummyAdapter);
        assert_eq!(a.chain_id(), 0);
        assert_eq!(a.vm_type(), "DUMMY");
        let intent = Intent::default();
        let route = Route::default();
        assert!(a.execute_swap(&intent, &route).is_zero());
        assert!(matches!(a.verify_execution(TxHash::zero()), ExecutionResult::Failed));
    }

    #[test]
    fn synthetic_tx_hash_is_deterministic_and_nonzero() {
        let h1 = synthetic_tx_hash(b"swap:1eth:usdc:1000");
        let h2 = synthetic_tx_hash(b"swap:1eth:usdc:1000");
        let h3 = synthetic_tx_hash(b"swap:1eth:usdc:1001");
        assert_eq!(h1, h2, "synthetic hash is deterministic");
        assert_ne!(h1, h3, "different payload → different hash");
        assert!(!h1.is_zero(), "synthetic hash is never the zero sentinel");
    }
}
