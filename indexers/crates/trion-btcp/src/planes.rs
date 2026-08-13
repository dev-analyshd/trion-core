//! 7-Plane Coherence (Gap 2 Resolution)
//! Weights: Magnitude=0.20, Temporal=0.10, Protocol=0.10, Counterparty=0.15,
//! Velocity=0.20, CrossChain=0.20, Statistical=0.05

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum PlaneType {
    Magnitude,    // 0.20
    Temporal,     // 0.10
    Protocol,     // 0.10
    Counterparty, // 0.15
    Velocity,     // 0.20
    CrossChain,   // 0.20
    Statistical,  // 0.05
}

pub const PLANE_WEIGHTS: [(PlaneType, f64); 7] = [
    (PlaneType::Magnitude, 0.20),
    (PlaneType::Temporal, 0.10),
    (PlaneType::Protocol, 0.10),
    (PlaneType::Counterparty, 0.15),
    (PlaneType::Velocity, 0.20),
    (PlaneType::CrossChain, 0.20),
    (PlaneType::Statistical, 0.05),
];

pub const MAGNITUDE_Z_THRESHOLD: f64 = 3.0;
pub const VELOCITY_MAX_MULTIPLIER: f64 = 5.0;
pub const STATISTICAL_KC_THRESHOLD: f64 = 0.30;

#[derive(Debug, Clone)]
pub struct PlaneResult {
    pub plane: PlaneType,
    pub score: f64,
    pub passed: bool,
    pub needs_conscious_review: bool,
}

pub struct SevenPlaneCoherence;

impl SevenPlaneCoherence {
    /// Plane 1: z_score = |m - μ| / σ, pass if < 3.0
    pub fn check_magnitude(magnitude: f64, historical: &[f64]) -> PlaneResult {
        if historical.len() < 2 {
            return PlaneResult { plane: PlaneType::Magnitude, score: 0.5, passed: true, needs_conscious_review: false };
        }
        let mean = historical.iter().sum::<f64>() / historical.len() as f64;
        let variance = historical.iter().map(|x| (x - mean).powi(2)).sum::<f64>() / historical.len() as f64;
        let std = variance.sqrt();
        if std == 0.0 {
            let score = if (magnitude - mean).abs() < 1e-9 { 1.0 } else { 0.0 };
            return PlaneResult { plane: PlaneType::Magnitude, score, passed: score > 0.5, needs_conscious_review: false };
        }
        let z = (magnitude - mean).abs() / std;
        let score = (1.0 - (z / MAGNITUDE_Z_THRESHOLD).min(1.0)).max(0.0);
        PlaneResult { plane: PlaneType::Magnitude, score, passed: z < MAGNITUDE_Z_THRESHOLD, needs_conscious_review: false }
    }

    /// Plane 5: velocity_score = recent / historical_avg, pass if < 5.0×
    pub fn check_velocity(recent: usize, historical_avg: f64) -> PlaneResult {
        if historical_avg <= 0.0 {
            return PlaneResult { plane: PlaneType::Velocity, score: 0.5, passed: true, needs_conscious_review: false };
        }
        let v = recent as f64 / historical_avg;
        let score = if v <= 1.0 { 1.0 } else { (1.0 - (v - 1.0) / (VELOCITY_MAX_MULTIPLIER - 1.0)).max(0.0) };
        PlaneResult { plane: PlaneType::Velocity, score, passed: v < VELOCITY_MAX_MULTIPLIER, needs_conscious_review: false }
    }

    /// Plane 7: KC delta, needs conscious review if > 10% relative change
    pub fn check_statistical(recent_kc: f64, historical_kc: f64) -> PlaneResult {
        if historical_kc <= 0.0 {
            return PlaneResult { plane: PlaneType::Statistical, score: 0.5, passed: true, needs_conscious_review: false };
        }
        let rel_delta = (recent_kc - historical_kc).abs() / historical_kc;
        let score = (1.0 - (rel_delta / STATISTICAL_KC_THRESHOLD).min(1.0)).max(0.0);
        PlaneResult { plane: PlaneType::Statistical, score, passed: rel_delta < STATISTICAL_KC_THRESHOLD, needs_conscious_review: rel_delta > 0.10 }
    }

    /// Compute weighted coherence = Σ(weight_i × score_i)
    pub fn compute_coherence(results: &[PlaneResult; 7]) -> f64 {
        PLANE_WEIGHTS.iter().zip(results.iter())
            .map(|((_, w), r)| w * r.score)
            .sum()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_weights_sum_to_1() {
        let total: f64 = PLANE_WEIGHTS.iter().map(|(_, w)| *w).sum();
        assert!((total - 1.0).abs() < 1e-9);
    }

    #[test]
    fn test_magnitude_perfect() {
        let r = SevenPlaneCoherence::check_magnitude(100.0, &[100.0, 100.0, 100.0, 100.0, 100.0]);
        assert!(r.passed);
        assert!((r.score - 1.0).abs() < 1e-9);
    }

    #[test]
    fn test_velocity_normal() {
        let r = SevenPlaneCoherence::check_velocity(10, 10.0);
        assert!(r.passed);
        assert!((r.score - 1.0).abs() < 1e-9);
    }

    #[test]
    fn test_velocity_spike() {
        let r = SevenPlaneCoherence::check_velocity(100, 10.0); // 10x
        assert!(!r.passed);
    }

    #[test]
    fn test_statistical_review() {
        let r = SevenPlaneCoherence::check_statistical(0.80, 0.50); // 60% increase
        assert!(r.needs_conscious_review);
    }
}
