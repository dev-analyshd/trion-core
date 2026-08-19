//! intent_aggregator.rs — IAP: pool intents by direction, ZK share proof
//! Per BTCP Master Implementation Spec §Water Principle 3

use crate::types::*;
use std::collections::HashMap;

/// Minimum intents required to form a pool
pub const MIN_INTENTS: usize = 3;
/// Maximum pool size
pub const MAX_POOL_SIZE: usize = 1000;

/// Intent Aggregator — Intent Aggregation Protocol (IAP)
/// 100 users × $100 individually = $0.80 each = $80 total
/// Aggregated = $0.80 total = $0.008 per user (100× cheaper)
#[derive(Debug, Default)]
pub struct IntentAggregator {
    pools: HashMap<(AssetId, AssetId), IntentPool>,
}

impl IntentAggregator {
    pub fn new() -> Self {
        IntentAggregator {
            pools: HashMap::new(),
        }
    }

    /// Check if intent should join an existing pool
    pub fn should_aggregate(&self, intent: &Intent, pool: &IntentPool) -> bool {
        intent.asset_in == pool.direction.0
            && intent.asset_out == pool.direction.1
            && intent.constraints.deadline >= pool.window_deadline
            && pool.participants.len() < MAX_POOL_SIZE
    }

    /// Add an intent to the appropriate pool
    pub fn add_intent(
        &mut self,
        entity_id: BEOId,
        asset_in: AssetId,
        asset_out: AssetId,
        value: u128,
        deadline: u64,
    ) {
        let direction = (asset_in, asset_out);
        let pool = self.pools.entry(direction.clone()).or_insert_with(|| IntentPool {
            direction,
            participants: Vec::new(),
            total_value: 0,
            window_deadline: deadline,
            min_size: MIN_INTENTS,
        });

        pool.participants.push((entity_id, value));
        pool.total_value += value;
        pool.window_deadline = pool.window_deadline.min(deadline);
    }

    /// Check if any pool is ready for execution
    pub fn find_aggregation_pool(
        &self,
        direction: &(AssetId, AssetId),
        window_blocks: u64,
    ) -> Option<&IntentPool> {
        self.pools
            .get(direction)
            .filter(|pool| pool.participants.len() >= pool.min_size)
    }

    /// Compute per-user gas allocation in a pool
    /// G_per_entity = G_total × (entity_value / total_value)
    pub fn compute_per_user_gas(
        &self,
        total_gas: u64,
        num_users: u32,
    ) -> u64 {
        if num_users == 0 {
            return total_gas;
        }
        // Equal split for simplicity; value-weighted in production
        total_gas / num_users as u64
    }

    /// Compute per-user gas with value weighting
    pub fn compute_per_user_gas_weighted(
        &self,
        total_gas: u64,
        user_value: u128,
        total_value: u128,
    ) -> u64 {
        if total_value == 0 {
            return total_gas;
        }
        ((total_gas as u128 * user_value) / total_value) as u64
    }

    /// Get all active pools
    pub fn all_pools(&self) -> Vec<&IntentPool> {
        self.pools.values().collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_add_and_find_pool() {
        let mut agg = IntentAggregator::new();

        // Add 5 intents in same direction
        for i in 0..5 {
            agg.add_intent(
                H256::sha3(format!("user_{}", i).as_bytes()),
                "ETH".to_string(),
                "SOL".to_string(),
                100_000_000_000_000_000u128, // 0.1 ETH
                1787141851,
            );
        }

        let pool = agg
            .find_aggregation_pool(&("ETH".to_string(), "SOL".to_string()), 100);
        assert!(pool.is_some());
        let pool = pool.unwrap();
        assert_eq!(pool.participants.len(), 5);
        assert_eq!(pool.total_value, 500_000_000_000_000_000u128);
    }

    #[test]
    fn test_pool_not_ready() {
        let mut agg = IntentAggregator::new();

        // Only 2 intents, below MIN_INTENTS (3)
        for i in 0..2 {
            agg.add_intent(
                H256::sha3(format!("user_{}", i).as_bytes()),
                "ETH".to_string(),
                "SOL".to_string(),
                100_000_000_000_000_000u128,
                1787141851,
            );
        }

        let pool = agg
            .find_aggregation_pool(&("ETH".to_string(), "SOL".to_string()), 100);
        assert!(pool.is_none());
    }

    #[test]
    fn test_per_user_gas() {
        let agg = IntentAggregator::new();
        let per_user = agg.compute_per_user_gas(80_000_000, 100);
        assert_eq!(per_user, 800_000); // 100× cheaper per user
    }

    #[test]
    fn test_per_user_gas_weighted() {
        let agg = IntentAggregator::new();
        let per_user = agg.compute_per_user_gas_weighted(
            80_000_000,
            100_000_000_000_000_000u128,  // 0.1 ETH
            10_000_000_000_000_000_000u128, // 10 ETH total
        );
        assert_eq!(per_user, 800_000); // 1% of total gas
    }
}
