//! validator_fee_calculator.rs — Coverage Bonus, BTCP_ROUTE_REWARD formula
//! Per BTCP Master Implementation Spec §Phase 2
//!
//! Economic incentive flows AUTOMATICALLY to underserved chains.
//! rarity_factor = total_validators / validators_covering_chain
//! Chain covered by 5% of validators → rarity = 20×.

use crate::types::*;
use std::collections::HashMap;

/// Base reward rate
pub const BASE_RATE: f64 = 100.0;

/// BTCP route reward split: 60% to anchor chain, 40% to execution chain
pub const BTCP_ROUTE_SPLIT_ANCHOR: f64 = 0.6;
pub const BTCP_ROUTE_SPLIT_EXEC: f64 = 0.4;

/// BTCP route fee rate (basis points of route value)
pub const BTCP_ROUTE_FEE_RATE: f64 = 0.001; // 0.1%

/// Real network statistics backing validator-fee computation.
/// Replaces the former hardcoded placeholders — all values are supplied
/// by the caller from live protocol state (registry + route ledger).
#[derive(Debug, Clone, Default)]
pub struct NetworkStats {
    /// Total number of active validators in the network.
    pub total_validators: u32,
    /// Number of validators covering each chain (for rarity).
    pub validators_per_chain: HashMap<ChainId, u32>,
    /// Fraction of BTCP routes through each chain in the period.
    pub route_volume_share: HashMap<ChainId, f64>,
    /// This validator's verified uptime per chain in the period.
    pub validator_uptime: HashMap<ChainId, f64>,
    /// Total value of BTCP routes this validator certified in the period.
    pub certified_route_value: f64,
}

impl NetworkStats {
    /// Single-chain convenience constructor.
    pub fn for_chain(
        total_validators: u32,
        validators_covering: u32,
        volume_share: f64,
        uptime: f64,
        certified_route_value: f64,
    ) -> Self {
        let mut stats = NetworkStats {
            total_validators,
            certified_route_value,
            ..Default::default()
        };
        stats.validators_per_chain.insert(0, validators_covering);
        stats.route_volume_share.insert(0, volume_share);
        stats.validator_uptime.insert(0, uptime);
        stats
    }
}

/// Validator Fee Calculator — validator economics
/// Coverage bonus rewards validators who cover underserved chains.
#[derive(Debug, Default)]
pub struct ValidatorFeeCalculator {
    /// Live network statistics; when absent, chain-level bonuses are 0
    /// (never invented) and only the base signal reward accrues.
    stats: Option<NetworkStats>,
}

impl ValidatorFeeCalculator {
    pub fn new() -> Self {
        ValidatorFeeCalculator { stats: None }
    }

    /// Attach real network statistics (from the validator registry + route ledger).
    pub fn with_stats(stats: NetworkStats) -> Self {
        ValidatorFeeCalculator { stats: Some(stats) }
    }

    /// Total validator reward for a period
    /// total = base_signal_reward + coverage_bonus + btcp_route_reward - coverage_cost_offset
    pub fn total_reward(&self, validator: &Validator, period: &Period) -> f64 {
        self.base_signal_reward(validator, period)
            + self.coverage_bonus(validator, period)
            + self.btcp_route_reward(validator, period)
            - self.coverage_cost_offset(validator, period)
    }

    /// Base signal reward
    pub fn base_signal_reward(&self, _validator: &Validator, _period: &Period) -> f64 {
        BASE_RATE
    }

    /// Coverage bonus — rewards validators covering underserved chains
    ///
    /// Spec formula (Fix 4):
    ///   COVERAGE_BONUS = Σ_chains [ BASE_RATE × rarity × volume × uptime ]
    ///     rarity = total_validators / validators_covering_chain
    ///     volume = btcp_routes_through(chain, period) / total_btcp_routes(period)
    ///     uptime = verified_observations / expected_observations
    ///
    /// All inputs come from attached NetworkStats — no placeholders.
    pub fn coverage_bonus(&self, validator: &Validator, _period: &Period) -> f64 {
        let stats = match &self.stats {
            Some(s) => s,
            None => return 0.0, // no real data attached — do not invent rewards
        };
        if stats.total_validators == 0 {
            return 0.0;
        }
        validator
            .covered_chains
            .iter()
            .filter_map(|chain| {
                let covering = *stats.validators_per_chain.get(chain)? as f64;
                if covering <= 0.0 {
                    return None;
                }
                let rarity = stats.total_validators as f64 / covering;
                let volume = stats.route_volume_share.get(chain).copied().unwrap_or(0.0);
                let uptime = stats.validator_uptime.get(chain).copied().unwrap_or(0.0);
                Some(BASE_RATE * rarity * volume * uptime)
            })
            .sum()
    }

    /// Compute rarity factor for a chain
    /// Chain covered by 5% of validators → rarity = 20
    pub fn compute_rarity_factor(
        &self,
        validators_covering_chain: u32,
        total_validators: u32,
    ) -> f64 {
        if validators_covering_chain == 0 {
            return 0.0;
        }
        total_validators as f64 / validators_covering_chain as f64
    }

    /// Convenience alias
    pub fn compute_rarity(&self, validators_covering_chain: u32, total_validators: u32) -> f64 {
        self.compute_rarity_factor(validators_covering_chain, total_validators)
    }

    /// Compute coverage bonus with explicit parameters
    pub fn compute_coverage_bonus(
        &self,
        chains_covered: u32,
        validators_per_chain: u32,
        total_validators: u32,
        volume_per_chain: f64,
        uptime_per_chain: f64,
    ) -> f64 {
        let rarity = self.compute_rarity_factor(validators_per_chain, total_validators);
        BASE_RATE * rarity * volume_per_chain * uptime_per_chain * chains_covered as f64
    }

    /// BTCP route reward for a validator
    /// 60% to anchor chain validators, 40% to execution chain validators
    ///
    /// reward = Σ_certified_routes route.value × BTCP_ROUTE_FEE_RATE
    /// The certified route value comes from attached NetworkStats (route
    /// ledger); with no stats attached the reward is 0 — never a placeholder.
    pub fn btcp_route_reward(&self, _validator: &Validator, _period: &Period) -> f64 {
        self.stats
            .as_ref()
            .map(|s| s.certified_route_value * BTCP_ROUTE_FEE_RATE)
            .unwrap_or(0.0)
    }

    /// Compute BTCP route reward with explicit parameters
    pub fn compute_btcp_route_reward(
        &self,
        total_route_reward: f64,
        is_anchor: bool,
    ) -> f64 {
        if is_anchor {
            total_route_reward * BTCP_ROUTE_SPLIT_ANCHOR
        } else {
            total_route_reward * BTCP_ROUTE_SPLIT_EXEC
        }
    }

    /// Coverage cost offset — small operational cost deduction
    pub fn coverage_cost_offset(&self, validator: &Validator, _period: &Period) -> f64 {
        // Small cost per chain covered (RPC, indexer, etc.)
        validator.covered_chains.len() as f64 * 1.0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_validator(chains: Vec<ChainId>) -> Validator {
        Validator {
            id: H256::sha3(b"validator_1"),
            covered_chains: chains,
            stake: 1_000_000,
        }
    }

    fn test_period() -> Period {
        Period {
            start_block: 18000000,
            end_block: 18001000,
            duration_seconds: 12000,
        }
    }

    #[test]
    fn test_total_reward() {
        let calc = ValidatorFeeCalculator::new();
        let v = test_validator(vec![1, 42161, 900]);
        let p = test_period();

        let reward = calc.total_reward(&v, &p);
        assert!(reward > 0.0);
        println!("Total validator reward: ${:.2}", reward);
    }

    #[test]
    fn test_rarity_factor() {
        let calc = ValidatorFeeCalculator::new();

        // Chain covered by 5% of validators (5/100)
        let rarity = calc.compute_rarity_factor(5, 100);
        assert_eq!(rarity, 20.0);

        // Well-covered chain
        let rarity2 = calc.compute_rarity_factor(50, 100);
        assert_eq!(rarity2, 2.0);

        println!("Rarity (5/100 validators): {:.1}×", rarity);
        println!("Rarity (50/100 validators): {:.1}×", rarity2);
    }

    #[test]
    fn test_btcp_route_reward_split() {
        let calc = ValidatorFeeCalculator::new();

        let total = 100.0;
        let anchor = calc.compute_btcp_route_reward(total, true);
        let exec = calc.compute_btcp_route_reward(total, false);

        assert_eq!(anchor, 60.0); // 60%
        assert_eq!(exec, 40.0); // 40%
        assert_eq!(anchor + exec, 100.0);
    }

    #[test]
    fn test_coverage_bonus_underserved() {
        let calc = ValidatorFeeCalculator::new();

        // Validator covering an underserved chain
        let bonus_rare = calc.compute_coverage_bonus(1, 5, 100, 0.1, 0.99);

        // Validator covering a well-served chain
        let bonus_common = calc.compute_coverage_bonus(1, 50, 100, 0.1, 0.99);

        // Underserved chain should give much higher bonus
        assert!(bonus_rare > bonus_common);
        println!("Rare chain bonus: ${:.2}", bonus_rare);
        println!("Common chain bonus: ${:.2}", bonus_common);
    }

    #[test]
    fn test_constants() {
        assert_eq!(BASE_RATE, 100.0);
        assert_eq!(BTCP_ROUTE_SPLIT_ANCHOR, 0.6);
        assert_eq!(BTCP_ROUTE_SPLIT_EXEC, 0.4);
        assert_eq!(BTCP_ROUTE_FEE_RATE, 0.001);
    }
}
