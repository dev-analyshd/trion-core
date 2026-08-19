//! ooa_anchor.rs — Observation-Only Anchoring for non-integrated chains
//! Per BTCP Master Implementation Spec §Water Principle 2
//!
//! Water through rock: TRION reads ANY chain without permission.
//! Confidence grows asymptotically with observation depth.

use crate::types::*;

/// OOA penalty factor — non-integrated chains pay threshold penalty
pub const OOA_PENALTY_FACTOR: f64 = 1.5;

/// OOA Anchor — Observation-Only Anchoring for non-integrated chains
/// TRION Channel 6 reads any chain's public data without permission.
/// OOA confidence = conf_max × (1 - e^(-k × depth))
#[derive(Debug, Clone)]
pub struct OOAAnchor {
    pub chain_id: ChainId,
    pub observation_depth: u64,
    pub ooa_conf: f64,
    pub ooa_penalty_factor: f64,
}

impl Default for OOAAnchor {
    fn default() -> Self {
        OOAAnchor {
            chain_id: 0,
            observation_depth: 0,
            ooa_conf: 0.0,
            ooa_penalty_factor: OOA_PENALTY_FACTOR,
        }
    }
}

impl OOAAnchor {
    pub fn new(chain_id: ChainId) -> Self {
        OOAAnchor {
            chain_id,
            observation_depth: 0,
            ooa_conf: 0.0,
            ooa_penalty_factor: OOA_PENALTY_FACTOR,
        }
    }

    /// Compute OOA confidence — grows asymptotically toward integrated_confidence
    /// as observation deepens
    pub fn compute_ooa_confidence(
        &self,
        observation_depth: u64,
        integrated_confidence: f64,
    ) -> f64 {
        let conf_max = integrated_confidence.min(0.85); // Approaches but never reaches integrated
        let k = 0.001_f64; // Growth rate (calibrated)
        conf_max * (1.0 - (-k * observation_depth as f64).exp())
    }

    /// Compute OOA-adjusted threshold
    /// Θ_OOA(t) = Θ_base(t) × ooa_penalty_factor
    pub fn compute_ooa_threshold(&self, base_threshold: f64) -> f64 {
        base_threshold * self.ooa_penalty_factor
    }

    /// Update with new observation depth
    pub fn update_depth(&mut self, new_depth: u64, integrated_confidence: f64) {
        self.observation_depth = new_depth;
        self.ooa_conf = self.compute_ooa_confidence(new_depth, integrated_confidence);
    }

    /// Use case: Entity on non-integrated chain_X receives on integrated chain_B
    /// chain_X: OOA observes, generates anchor_BH at ooa_conf
    /// chain_B: BTCP executes natively (integrated)
    pub fn entity_receives_on_integrated(
        &self,
        entity_id: BEOId,
        integrated_chain: ChainId,
    ) -> (H256, f64) {
        let anchor_data = format!(
            "{}:{}:{}:{}",
            entity_id.to_hex(),
            self.chain_id,
            integrated_chain,
            self.observation_depth
        );
        let anchor_bh = H256::sha3(anchor_data.as_bytes());
        (anchor_bh, self.ooa_conf)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ooa_confidence_growth() {
        let ooa = OOAAnchor::new(99999);

        // At 0 depth: confidence = 0
        let conf_0 = ooa.compute_ooa_confidence(0, 1.0);
        assert_eq!(conf_0, 0.0);

        // At 1000 blocks: some confidence
        let conf_1k = ooa.compute_ooa_confidence(1000, 1.0);
        assert!(conf_1k > 0.0);
        assert!(conf_1k < 0.85);

        // At 10000 blocks: higher confidence
        let conf_10k = ooa.compute_ooa_confidence(10000, 1.0);
        assert!(conf_10k > conf_1k);
        assert!(conf_10k < 0.85);

        // At 100000 blocks: approaching max
        let conf_100k = ooa.compute_ooa_confidence(100000, 1.0);
        assert!(conf_100k > conf_10k);
        assert!(conf_100k <= 0.85);

        println!("OOA confidence growth:");
        println!("  0 blocks:     {:.4}", conf_0);
        println!("  1,000 blocks: {:.4}", conf_1k);
        println!("  10,000 blocks: {:.4}", conf_10k);
        println!("  100,000 blocks: {:.4}", conf_100k);
    }

    #[test]
    fn test_ooa_threshold_penalty() {
        let ooa = OOAAnchor::new(99999);
        let threshold = ooa.compute_ooa_threshold(0.55);
        let expected = 0.55 * OOA_PENALTY_FACTOR;
        assert!((threshold - expected).abs() < 1e-9);
        assert!((threshold - 0.825).abs() < 1e-9);
    }

    #[test]
    fn test_update_depth() {
        let mut ooa = OOAAnchor::new(99999);
        ooa.update_depth(500000, 1.0);
        assert_eq!(ooa.observation_depth, 500000);
        assert!(ooa.ooa_conf > 0.5);
        println!("OOA conf at 500k blocks: {:.4}", ooa.ooa_conf);
    }
}
