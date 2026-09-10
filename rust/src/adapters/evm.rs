//! adapters/evm.rs — EVM Chain Adapter (BTCP spec §4.2 Step 4 / §14.1
//! build-guide item 5: "adapters/evm/evm_adapter_btcp.rs — Extend
//! existing evm_adapter.rs with BTCP execution")
//!
//! The existing EVM adapter/indexer lives in `indexers/crates/trion-evm`
//! (a separate cargo workspace — NOT modified from here). This module is
//! the BTCP execution-side EVM adapter inside the `rust/` crate:
//!
//! - SWAP:     route to the best Uniswap/Curve pool per NL score
//! - TRANSFER: ERC-20 native transfer (no bridge contract, no wrapped
//!             token)
//! - BORROW:   Aave/Compound integration      — NOT ported (no client)
//! - STAKE:    staking contract routing        — NOT ported (no client)
//!
//! HONEST LIMITATION: `rust/Cargo.toml` carries no RPC/web3 crate
//! (dependencies are sha3 0.10 + hex 0.4 only), so this adapter has NO
//! execution capability. Every execution method returns
//! [`AdapterError::NotConnected`] with the hint "wire to the trion-evm
//! indexer RPC layer" rather than fabricating a transaction hash — no
//! success is simulated (AUDIT-RUST fabrication discipline).

use super::{AdapterError, ChainAdapter, ExecutionReceipt, ExecutionStatus};
use crate::types::{ChainId, Intent, Route};

/// Wiring hint attached to every [`AdapterError::NotConnected`] returned
/// by this adapter.
const HINT_WIRE_TRION_EVM: &str =
    "wire to the trion-evm indexer RPC layer (indexers/crates/trion-evm) — no RPC client dependency exists in rust/Cargo.toml";

/// Gas-token symbol table for well-known EVM chains. Unmapped chain ids
/// resolve to [`UNMAPPED_GAS_TOKEN`] — extending this table is required
/// before relying on gas accounting for exotic chains.
const KNOWN_EVM_GAS_TOKENS: &[(ChainId, &str)] = &[
    (1, "ETH"),      // Ethereum mainnet
    (10, "ETH"),     // OP Mainnet
    (56, "BNB"),     // BNB Smart Chain
    (137, "POL"),    // Polygon PoS (MATIC → POL rename, Sept 2024)
    (8453, "ETH"),   // Base
    (42161, "ETH"),  // Arbitrum One
    (43114, "AVAX"), // Avalanche C-Chain
];

/// Fallback symbol for chain ids missing from [`KNOWN_EVM_GAS_TOKENS`].
/// Deliberately NOT a guess: "UNKNOWN" forces callers to handle unmapped
/// chains instead of silently mis-accounting gas in the wrong token.
const UNMAPPED_GAS_TOKEN: &str = "UNKNOWN";

/// Configuration for the EVM adapter.
#[derive(Debug, Clone)]
pub struct EvmAdapterConfig {
    /// EIP-155 chain id this adapter targets
    pub chain_id: ChainId,
    /// Optional RPC endpoint URL. Storing a URL does NOT connect anything
    /// — no RPC client dependency exists in this crate, so execution
    /// methods still return [`AdapterError::NotConnected`] until the
    /// trion-evm RPC layer is wired.
    pub rpc_url: Option<String>,
}

/// EVM chain adapter — [`ChainAdapter`] implementation for EVM chains.
///
/// Construction is honest bookkeeping only: `new(chain_id)` and
/// `with_rpc_url(...)` store configuration; every execution method
/// returns [`AdapterError::NotConnected`] (see module docs).
#[derive(Debug, Clone)]
pub struct EvmAdapter {
    config: EvmAdapterConfig,
}

impl EvmAdapter {
    /// Create an EVM adapter for `chain_id` with no RPC endpoint.
    pub fn new(chain_id: ChainId) -> Self {
        EvmAdapter {
            config: EvmAdapterConfig {
                chain_id,
                rpc_url: None,
            },
        }
    }

    /// Create an EVM adapter with a stored RPC endpoint URL.
    /// NOTE: storing the URL does not connect — execution still returns
    /// [`AdapterError::NotConnected`] until an RPC client is wired.
    pub fn with_rpc_url(chain_id: ChainId, rpc_url: String) -> Self {
        EvmAdapter {
            config: EvmAdapterConfig {
                chain_id,
                rpc_url: Some(rpc_url),
            },
        }
    }

    /// The stored adapter configuration.
    pub fn config(&self) -> &EvmAdapterConfig {
        &self.config
    }
}

impl ChainAdapter for EvmAdapter {
    fn chain_id(&self) -> ChainId {
        self.config.chain_id
    }

    /// SWAP execution (Uniswap/Curve routing per NL score) — NOT WIRED.
    fn execute_swap(
        &self,
        _intent: &Intent,
        _route: &Route,
    ) -> Result<ExecutionReceipt, AdapterError> {
        Err(AdapterError::NotConnected {
            chain_id: self.config.chain_id,
            hint: HINT_WIRE_TRION_EVM,
        })
    }

    /// TRANSFER execution (ERC-20 native transfer) — NOT WIRED.
    fn execute_transfer(
        &self,
        _intent: &Intent,
        _route: &Route,
    ) -> Result<ExecutionReceipt, AdapterError> {
        Err(AdapterError::NotConnected {
            chain_id: self.config.chain_id,
            hint: HINT_WIRE_TRION_EVM,
        })
    }

    fn native_gas_token(&self) -> &str {
        for &(chain_id, symbol) in KNOWN_EVM_GAS_TOKENS {
            if chain_id == self.config.chain_id {
                return symbol;
            }
        }
        UNMAPPED_GAS_TOKEN
    }

    /// Gas estimation (eth_estimateGas) — NOT WIRED.
    fn estimate_gas(&self, _intent: &Intent) -> Result<u64, AdapterError> {
        Err(AdapterError::NotConnected {
            chain_id: self.config.chain_id,
            hint: HINT_WIRE_TRION_EVM,
        })
    }

    /// Execution verification (receipt lookup) — NOT WIRED.
    fn verify_execution(&self, _receipt: &ExecutionReceipt) -> Result<ExecutionStatus, AdapterError> {
        Err(AdapterError::NotConnected {
            chain_id: self.config.chain_id,
            hint: HINT_WIRE_TRION_EVM,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_intent() -> Intent {
        // Minimal intent fixture for dispatch tests — never executed (the
        // adapter is not connected), only passed through the trait.
        Intent {
            intent_id: crate::types::H256::zero(),
            entity_id: crate::types::BEOId::zero(),
            source_address: String::new(),
            dest_address: String::new(),
            source_chain: 1,
            dest_chain: 137,
            asset_in: String::from("ETH"),
            asset_out: String::from("USDC"),
            amount_in: 1_000_000,
            intent_type: String::from("SWAP"),
            deadline: 0,
            nonce: 0,
            constraints: Default::default(),
            btcp_version: crate::types::SemVer::new(1, 0, 0),
        }
    }

    fn sample_route() -> Route {
        Route {
            route_id: crate::types::H256::zero(),
            intent: sample_intent(),
            route_type: crate::types::RouteType::SingleChain,
            beo_continuity: 0.9,
            btcp_score: 0.9,
            status: crate::types::RouteStatus::Pending,
            created_at: 0,
        }
    }

    /// Trait-object dispatch: `Box<dyn ChainAdapter>` resolves chain_id
    /// and gas token, and execution honestly reports NotConnected.
    #[test]
    fn test_trait_object_dispatch() {
        let adapter: Box<dyn ChainAdapter> = Box::new(EvmAdapter::new(1));
        assert_eq!(adapter.chain_id(), 1);
        assert_eq!(adapter.native_gas_token(), "ETH");

        let intent = sample_intent();
        let route = sample_route();
        match adapter.execute_swap(&intent, &route) {
            Err(AdapterError::NotConnected { chain_id, hint }) => {
                assert_eq!(chain_id, 1);
                assert!(hint.contains("wire to the trion-evm indexer RPC layer"));
            }
            other => panic!("expected NotConnected, got {:?}", other.map(|r| r.tx_hash)),
        }
    }

    /// Every execution path returns NotConnected (no fabricated success).
    #[test]
    fn test_all_execution_paths_not_connected() {
        let adapter = EvmAdapter::new(137);
        let intent = sample_intent();
        let route = sample_route();
        let receipt = ExecutionReceipt {
            tx_hash: crate::types::H256::zero(),
            chain_id: 137,
            gas_used: 21_000,
            block_number: 1,
            status: ExecutionStatus::Submitted,
        };

        for result in [
            adapter.execute_swap(&intent, &route).err(),
            adapter.execute_transfer(&intent, &route).err(),
            adapter.estimate_gas(&intent).err(),
            adapter.verify_execution(&receipt).err(),
        ] {
            match result {
                Some(AdapterError::NotConnected { chain_id, .. }) => assert_eq!(chain_id, 137),
                other => panic!("expected NotConnected, got {:?}", other),
            }
        }
    }

    /// chain_id mapping: constructed id passes through the trait for a
    /// range of EVM chains.
    #[test]
    fn test_chain_id_mapping() {
        for chain_id in [1u64, 10, 56, 137, 8453, 42161, 43114] {
            let adapter: &dyn ChainAdapter = &EvmAdapter::new(chain_id);
            assert_eq!(adapter.chain_id(), chain_id);
        }
    }

    /// Gas-token symbol mapping for well-known chains; unmapped chains
    /// return "UNKNOWN" instead of a guessed symbol.
    #[test]
    fn test_native_gas_token_mapping() {
        let cases: &[(u64, &str)] = &[
            (1, "ETH"),
            (10, "ETH"),
            (56, "BNB"),
            (137, "POL"),
            (8453, "ETH"),
            (42161, "ETH"),
            (43114, "AVAX"),
        ];
        for (chain_id, symbol) in cases {
            let adapter: &dyn ChainAdapter = &EvmAdapter::new(*chain_id);
            assert_eq!(adapter.native_gas_token(), *symbol);
        }
        // Unmapped chain — honest UNKNOWN, never a fabricated symbol
        let unknown: &dyn ChainAdapter = &EvmAdapter::new(999_999);
        assert_eq!(unknown.native_gas_token(), "UNKNOWN");
    }

    /// Storing an RPC URL does not connect: execution still fails with
    /// NotConnected (documented honest limitation).
    #[test]
    fn test_with_rpc_url_still_not_connected() {
        let adapter = EvmAdapter::with_rpc_url(1, String::from("http://localhost:8545"));
        assert_eq!(adapter.config().rpc_url.as_deref(), Some("http://localhost:8545"));
        assert_eq!(adapter.config().chain_id, 1);

        let err = adapter
            .execute_transfer(&sample_intent(), &sample_route())
            .expect_err("not connected by construction");
        assert!(matches!(err, AdapterError::NotConnected { .. }));
    }

    /// AdapterError Display carries the chain id and the wiring hint.
    #[test]
    fn test_adapter_error_display() {
        let err = EvmAdapter::new(42161)
            .estimate_gas(&sample_intent())
            .expect_err("not connected");
        let msg = format!("{}", err);
        assert!(msg.contains("42161"), "message includes chain id: {}", msg);
        assert!(msg.contains("not connected"), "message states failure: {}", msg);
        assert!(
            msg.contains("wire to the trion-evm indexer RPC layer"),
            "message carries wiring hint: {}",
            msg
        );
    }
}
