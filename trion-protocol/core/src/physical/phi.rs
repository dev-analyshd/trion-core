//! Physical Richness Score Phi — TRION L1
//! Phi(t) = (1/N) * Sum [ w_i * H(f_i(t)) ]
//! Phi_adj = Phi * (1 - MF_score)

use super::features::PhysicalFeatures;
use super::manipulation::{detect_manipulation, ManipulationInput, ManipulationResult};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PhiOutput {
    pub phi_raw:               f64,
    pub phi_adj:               f64,
    pub manipulation:          ManipulationResult,
    pub feature_contributions: [f64; 9],
}

pub fn compute_phi(
    features:    &PhysicalFeatures,
    manip_input: &ManipulationInput,
) -> PhiOutput {

    let feature_vals = features.as_array();

    let mut weighted_sum  = 0.0_f64;
    let mut weight_total  = 0.0_f64;
    let mut contributions = [0.0_f64; 9];

    for i in 0..9 {
        let c = features.weights[i] * feature_vals[i];
        contributions[i] = c;
        weighted_sum     += c;
        weight_total     += features.weights[i];
    }

    // Phi_raw = sum(w_i * f_i) / sum(w_i)  — normalized weighted mean
    let phi_raw = (weighted_sum / weight_total.max(1e-10)).clamp(0.0, 1.0);
    let manip   = detect_manipulation(manip_input);
    let phi_adj = (phi_raw * (1.0 - manip.mf_score)).clamp(0.0, 1.0);

    PhiOutput { phi_raw, phi_adj, manipulation: manip, feature_contributions: contributions }
}

/// TC(t) = 1 - max_lag / TTL_min
/// Valid iff TC > tc_minimum
pub fn temporal_coherence(
    plane_timestamps_ms: &[i64],
    reference_ms:        i64,
    ttl_min_ms:          i64,
    tc_minimum:          f64,
) -> (f64, bool) {
    if plane_timestamps_ms.is_empty() { return (0.0, false); }
    let max_lag = plane_timestamps_ms.iter()
        .map(|&t| (t - reference_ms).abs())
        .max()
        .unwrap_or(0) as f64;
    let tc = (1.0 - max_lag / ttl_min_ms as f64).clamp(0.0, 1.0);
    (tc, tc > tc_minimum)
}
