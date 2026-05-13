//! Physical Feature Extraction — TRION L1
//! Whitepaper Section 3.1: 9 EVM behavioral features
//! f10 (Energy Participation Index) reserved for Phase 9

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PhysicalFeatures {
    pub f1_tx_volume_entropy:      f64,
    pub f2_counterparty_diversity: f64,
    pub f3_temporal_spacing:       f64,
    pub f4_contract_interaction:   f64,
    pub f5_value_directionality:   f64,
    pub f6_wallet_architecture:    f64,
    pub f7_cross_protocol:         f64,
    pub f8_gas_pattern:            f64,
    pub f9_mev_interaction:        f64,
    /// Feature weights — learned from Akashic history, NOT fixed
    pub weights: [f64; 9],
}

impl PhysicalFeatures {
    pub fn with_equal_weights(
        f1: f64, f2: f64, f3: f64, f4: f64, f5: f64,
        f6: f64, f7: f64, f8: f64, f9: f64,
    ) -> Self {
        let w = 1.0 / 9.0;
        Self {
            f1_tx_volume_entropy:      f1.clamp(0.0, 1.0),
            f2_counterparty_diversity: f2.clamp(0.0, 1.0),
            f3_temporal_spacing:       f3.clamp(0.0, 1.0),
            f4_contract_interaction:   f4.clamp(0.0, 1.0),
            f5_value_directionality:   f5.clamp(0.0, 1.0),
            f6_wallet_architecture:    f6.clamp(0.0, 1.0),
            f7_cross_protocol:         f7.clamp(0.0, 1.0),
            f8_gas_pattern:            f8.clamp(0.0, 1.0),
            f9_mev_interaction:        f9.clamp(0.0, 1.0),
            weights: [w; 9],
        }
    }

    pub fn shannon_entropy(probs: &[f64]) -> f64 {
        let sum: f64 = probs.iter().sum();
        if sum == 0.0 { return 0.0; }
        let h: f64 = probs.iter()
            .filter(|&&p| p > 0.0)
            .map(|&p| { let n = p / sum; -n * n.ln() })
            .sum();
        h / (probs.len() as f64).ln().max(1.0)
    }

    pub fn as_array(&self) -> [f64; 9] {
        [
            self.f1_tx_volume_entropy,
            self.f2_counterparty_diversity,
            self.f3_temporal_spacing,
            self.f4_contract_interaction,
            self.f5_value_directionality,
            self.f6_wallet_architecture,
            self.f7_cross_protocol,
            self.f8_gas_pattern,
            self.f9_mev_interaction,
        ]
    }
}
