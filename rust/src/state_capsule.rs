//! state_capsule.rs — Behavioral State Capsule for cross-chain state reads
//! Per BTCP Master Implementation Spec §Water Principle 4
//!
//! Water through metal: Chain A state dissolves into BTCP anchor at creation.
//! Chain B reads from capsule, NOT live Chain A. Escrow lock guarantees
//! zero balance drift during execution.

use crate::types::*;

/// State Capsule Builder — dissolves Chain A state into BTCP anchor
#[derive(Debug, Default)]
pub struct StateCapsuleBuilder;

impl StateCapsuleBuilder {
    pub fn new() -> Self {
        StateCapsuleBuilder
    }

    /// Build a behavioral state capsule from anchor chain data
    pub fn build_capsule(
        &self,
        anchor_chain: ChainId,
        anchor_block: u64,
        block_hash: H256,
        price: PricePoint,
        balance: u128,
        governance: GovSnapshot,
        staleness_ci95: (f64, f64),
    ) -> BehavioralStateCapsule {
        BehavioralStateCapsule {
            anchor_chain,
            anchor_block,
            block_hash_a: block_hash,
            price_a: price,
            balance_x: balance,
            gov_state: governance,
            staleness_ci95,
            escrow_lock: balance > 0, // If balance provided, assume escrow locked
        }
    }

    /// Convenience builder with minimal parameters.
    ///
    /// The anchor `block_hash` MUST be supplied by the caller — it is the
    /// real hash of `anchor_block` on `anchor_chain` (read from the chain /
    /// indexer). This method previously fabricated a synthetic hash
    /// (`H(block_number)`), which misrepresented provenance; that
    /// fabrication is removed.
    ///
    /// NOTE: the staleness CI95 default `(0.0, 0.02)` is a placeholder —
    /// callers should pass the output of `estimate_staleness` via
    /// `build_capsule` instead of relying on this convenience default.
    pub fn build(
        &self,
        anchor_chain: ChainId,
        anchor_block: u64,
        block_hash: H256,
        price: f64,
        balance: u128,
    ) -> BehavioralStateCapsule {
        self.build_capsule(
            anchor_chain,
            anchor_block,
            block_hash,
            PricePoint {
                asset_pair: "DEFAULT".to_string(),
                price,
                block_number: anchor_block,
            },
            balance,
            GovSnapshot::default(),
            (0.0, 0.02),
        )
    }

    /// Estimate staleness drift between anchor and execution chains
    /// CI_95 estimate of price/balance drift by execution time
    pub fn estimate_staleness(
        &self,
        anchor_chain: ChainId,
        execution_chain: ChainId,
        anchor_finality_sec: f64,
        exec_finality_sec: f64,
        volatility: f64,
    ) -> (f64, f64) {
        let expected_latency = anchor_finality_sec.max(exec_finality_sec);
        // Staleness grows with sqrt(time) × volatility
        let drift = volatility * (expected_latency / 60.0).sqrt();
        (0.0, drift.min(0.1)) // CI_95: [0, drift]
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_build_capsule() {
        let builder = StateCapsuleBuilder::new();

        let capsule = builder.build_capsule(
            1, // Ethereum
            18000000,
            H256::sha3(b"block_hash"),
            PricePoint {
                asset_pair: "ETH/USDC".to_string(),
                price: 2000.0,
                block_number: 18000000,
            },
            100_000_000_000_000_000_000u128, // 100 ETH
            GovSnapshot {
                proposal_id: Some(123),
                voting_power: 1_000_000,
                state: "active".to_string(),
            },
            (0.0, 0.02),
        );

        assert_eq!(capsule.anchor_chain, 1);
        assert_eq!(capsule.anchor_block, 18000000);
        assert_eq!(capsule.price_a.price, 2000.0);
        assert_eq!(capsule.balance_x, 100_000_000_000_000_000_000u128);
        assert_eq!(capsule.gov_state.proposal_id, Some(123));
        assert_eq!(capsule.staleness_ci95, (0.0, 0.02));
        assert!(capsule.escrow_lock);
    }

    #[test]
    fn test_simple_build() {
        let builder = StateCapsuleBuilder::new();

        // Caller supplies the real anchor block hash — none is fabricated.
        let real_block_hash = H256::sha3(b"real_block_hash_from_chain");
        let capsule = builder.build(
            1,
            18000000,
            real_block_hash,
            2000.0,
            100_000_000_000_000_000_000u128,
        );

        assert_eq!(capsule.anchor_chain, 1);
        assert_eq!(capsule.price_a.price, 2000.0);
        assert_eq!(capsule.block_hash_a, real_block_hash);
        assert!(capsule.escrow_lock);
    }

    #[test]
    fn test_estimate_staleness() {
        let builder = StateCapsuleBuilder::new();

        // Fast chains: low staleness
        let (low, high) = builder.estimate_staleness(42161, 900, 2.5, 0.4, 0.05);
        assert_eq!(low, 0.0);
        assert!(high < 0.05);
        println!("Fast chain staleness CI95: [0, {:.4}]", high);

        // Slow chains: higher staleness
        let (low2, high2) = builder.estimate_staleness(1, 1, 600.0, 600.0, 0.10);
        assert!(high2 > high);
        println!("Slow chain staleness CI95: [0, {:.4}]", high2);
    }
}
