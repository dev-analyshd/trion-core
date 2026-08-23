//! netting_engine.rs — Counterparty matching for NETTING routes
//! Per BTCP Master Implementation Spec §Water Principle 1 extension

use crate::types::*;
use std::collections::HashMap;

/// A matched netting pair with amount reconciliation.
#[derive(Debug, Clone, PartialEq)]
pub struct NettingMatch {
    pub counterparty:  BEOId,
    /// Counterparty's posted amount (in asset_from units of the searching intent).
    pub matched_amount: u128,
    /// True when the counterparty amount fully covers the requested amount.
    pub full_fill:     bool,
}

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

    /// Find netting opportunity — counterparty with reversed direction.
    ///
    /// `tolerance` is the acceptable relative amount mismatch ∈ [0, 1]:
    /// a counterparty qualifies when
    ///   |counterparty_amount − amount| ≤ tolerance × amount.
    /// tolerance = 0.0 requires an exact-amount match.
    pub fn find_netting_pair(
        &self,
        entity_id: &BEOId,
        asset_from: &AssetId,
        asset_to: &AssetId,
        chain_id: ChainId,
        amount: u128,
        tolerance: f64,
    ) -> Option<NettingMatch> {
        // Look for opposite direction: (chain, asset_to, asset_from)
        let reverse_key = (chain_id, asset_to.clone(), asset_from.clone());
        let tol = tolerance.clamp(0.0, 1.0);

        if let Some(candidates) = self.pending_intents.get(&reverse_key) {
            for (candidate_id, candidate_amount) in candidates {
                if candidate_id == entity_id {
                    continue;
                }
                // Amount tolerance check (u128-safe)
                let diff = if candidate_amount > &amount {
                    candidate_amount - amount
                } else {
                    amount - candidate_amount
                };
                let allowed = ((amount as f64) * tol).ceil() as u128;
                if diff <= allowed {
                    return Some(NettingMatch {
                        counterparty:   *candidate_id,
                        matched_amount: *candidate_amount,
                        full_fill:      candidate_amount >= &amount,
                    });
                }
            }
        }
        None
    }

    /// Legacy-compatible lookup that ignores amount tolerance (any amount).
    /// Kept for callers that only need the counterparty identity.
    pub fn find_any_counterparty(
        &self,
        entity_id: &BEOId,
        asset_from: &AssetId,
        asset_to: &AssetId,
        chain_id: ChainId,
    ) -> Option<BEOId> {
        let reverse_key = (chain_id, asset_to.clone(), asset_from.clone());
        if let Some(candidates) = self.pending_intents.get(&reverse_key) {
            for (candidate_id, _) in candidates {
                if candidate_id != entity_id {
                    return Some(*candidate_id);
                }
            }
        }
        None
    }

    /// Remove a matched intent from the pool (post-settlement).
    pub fn remove_intent(
        &mut self,
        entity_id: &BEOId,
        asset_from: &AssetId,
        asset_to: &AssetId,
        chain_id: ChainId,
        amount: u128,
    ) -> bool {
        let key = (chain_id, asset_from.clone(), asset_to.clone());
        if let Some(candidates) = self.pending_intents.get_mut(&key) {
            let before = candidates.len();
            candidates.retain(|(id, amt)| !(id == entity_id && amt == &amount));
            return candidates.len() < before;
        }
        false
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

        let amount = 1_000_000_000_000_000_000u128;

        // Entity A: ETH → USDC on chain 1
        engine.add_intent(entity_a, "ETH".to_string(), "USDC".to_string(), amount, 1);

        // Entity B: USDC → ETH on chain 1 (opposite direction) — amount within tolerance
        let found = engine.find_netting_pair(
            &entity_b,
            &"USDC".to_string(),
            &"ETH".to_string(),
            1,
            amount,
            0.10,
        );

        let match_result = found.expect("netting match expected within tolerance");
        assert_eq!(match_result.counterparty, entity_a);
        assert!(match_result.full_fill);
    }

    #[test]
    fn test_netting_amount_tolerance_rejects_mismatch() {
        let mut engine = NettingEngine::new();
        let entity_a = H256::sha3(b"entity_A");
        let entity_b = H256::sha3(b"entity_B");

        // A wants 1000 units; B offers only 10 units in reverse — 99% mismatch
        engine.add_intent(entity_a, "ETH".to_string(), "USDC".to_string(), 1000, 1);

        let found = engine.find_netting_pair(
            &entity_b,
            &"USDC".to_string(),
            &"ETH".to_string(),
            1,
            10,
            0.10, // 10% tolerance — must NOT match a 99% mismatch
        );
        assert!(found.is_none(), "amount mismatch beyond tolerance must not net");
    }

    #[test]
    fn test_netting_partial_fill_within_tolerance() {
        let mut engine = NettingEngine::new();
        let entity_a = H256::sha3(b"entity_A");
        let entity_b = H256::sha3(b"entity_B");

        // A wants 100 units; B offers 95 in reverse — 5% mismatch, 10% tolerance
        engine.add_intent(entity_a, "ETH".to_string(), "USDC".to_string(), 100, 1);

        let found = engine.find_netting_pair(
            &entity_b,
            &"USDC".to_string(),
            &"ETH".to_string(),
            1,
            95,
            0.10,
        );
        assert!(found.is_some(), "5% mismatch within 10% tolerance should net");
        let m = found.unwrap();
        assert_eq!(m.matched_amount, 100);
        assert!(m.full_fill);
    }

    #[test]
    fn test_no_netting_same_direction() {
        let mut engine = NettingEngine::new();
        let entity_a = H256::sha3(b"entity_A");
        let entity_b = H256::sha3(b"entity_B");

        engine.add_intent(entity_a, "ETH".to_string(), "USDC".to_string(), 100, 1);

        // Same direction, not opposite
        let found = engine.find_netting_pair(
            &entity_b,
            &"ETH".to_string(),
            &"USDC".to_string(),
            1,
            100,
            0.10,
        );

        assert!(found.is_none());
    }

    #[test]
    fn test_remove_intent() {
        let mut engine = NettingEngine::new();
        let entity_a = H256::sha3(b"entity_A");

        engine.add_intent(entity_a, "ETH".to_string(), "USDC".to_string(), 100, 1);
        assert!(engine.remove_intent(&entity_a, &"ETH".to_string(), &"USDC".to_string(), 1, 100));
        assert!(!engine.remove_intent(&entity_a, &"ETH".to_string(), &"USDC".to_string(), 1, 100));
    }

    #[test]
    fn test_netting_gas_savings() {
        let engine = NettingEngine::new();
        let cost = engine.netting_gas_cost(100, 80.0);
        println!("Netting cost for 100 users: ${:.4}", cost);
        assert!(cost < 10.0); // Should be much less than individual $80
    }
}
