//! netting_engine.rs — Counterparty matching for NETTING routes
//! Per BTCP Master Implementation Spec §Water Principle 1 extension

use crate::types::*;
use std::collections::HashMap;

/// Netting Engine — finds counterparties with opposite intents
/// When counterparty found: zero asset movement, just behavioral settlement
#[derive(Debug, Default)]
pub struct NettingEngine {
    pending_intents: HashMap<(ChainId, AssetId, AssetId), Vec<(BEOId, u128)>>,
}

impl NettingEngine {
    pub fn new() -> Self {
        NettingEngine {
            pending_intents: HashMap::new(),
        }
    }

    /// Add an intent to the netting pool
    pub fn add_intent(
        &mut self,
        entity_id: BEOId,
        asset_from: AssetId,
        asset_to: AssetId,
        amount: u128,
        chain_id: ChainId,
    ) {
        let key = (chain_id, asset_from, asset_to);
        self.pending_intents
            .entry(key)
            .or_default()
            .push((entity_id, amount));
    }

    /// Find netting opportunity — counterparty with reversed direction
    pub fn find_netting_pair(
        &self,
        entity_id: &BEOId,
        asset_from: &AssetId,
        asset_to: &AssetId,
        chain_id: ChainId,
        tolerance: f64,
    ) -> Option<BEOId> {
        // Look for opposite direction: (chain, asset_to, asset_from)
        let reverse_key = (chain_id, asset_to.clone(), asset_from.clone());

        if let Some(candidates) = self.pending_intents.get(&reverse_key) {
            for (candidate_id, _amount) in candidates {
                if candidate_id != entity_id {
                    return Some(*candidate_id);
                }
            }
        }
        None
    }

    /// Calculate netting gas cost savings
    /// Individual: N users × cost_each
    /// Netting: 1 settlement for all counterparties
    pub fn netting_gas_cost(&self, num_users: u32, individual_gas: f64) -> f64 {
        // Netting settles once instead of N times
        // Plus small overhead for matching and proof
        individual_gas * 0.05 + (num_users as f64 * 0.001)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_find_netting_pair() {
        let mut engine = NettingEngine::new();
        let entity_a = H256::sha3(b"entity_A");
        let entity_b = H256::sha3(b"entity_B");

        // Entity A: ETH → USDC on chain 1
        engine.add_intent(
            entity_a,
            "ETH".to_string(),
            "USDC".to_string(),
            1_000_000_000_000_000_000u128,
            1,
        );

        // Entity B: USDC → ETH on chain 1 (opposite direction)
        let found = engine.find_netting_pair(
            &entity_b,
            &"USDC".to_string(),
            &"ETH".to_string(),
            1,
            0.10,
        );

        assert_eq!(found, Some(entity_a));
    }

    #[test]
    fn test_no_netting_same_direction() {
        let mut engine = NettingEngine::new();
        let entity_a = H256::sha3(b"entity_A");
        let entity_b = H256::sha3(b"entity_B");

        engine.add_intent(
            entity_a,
            "ETH".to_string(),
            "USDC".to_string(),
            1_000_000_000_000_000_000u128,
            1,
        );

        // Same direction, not opposite
        let found = engine.find_netting_pair(
            &entity_b,
            &"ETH".to_string(),
            &"USDC".to_string(),
            1,
            0.10,
        );

        assert!(found.is_none());
    }

    #[test]
    fn test_netting_gas_savings() {
        let engine = NettingEngine::new();
        let cost = engine.netting_gas_cost(100, 80.0);
        println!("Netting cost for 100 users: ${:.4}", cost);
        assert!(cost < 10.0); // Should be much less than individual $80
    }
}
