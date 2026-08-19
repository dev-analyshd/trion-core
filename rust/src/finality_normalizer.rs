//! finality_normalizer.rs — BTCP_ESCROW waits max(A_finality, B_finality)
//! Per BTCP Master Implementation Spec §Phase 2
//!
//! Effective latency = max(A, B), NOT A + B.
//! Both chains finalize in parallel, not sequentially.

use crate::types::*;

/// Finality Normalizer — normalizes finality across different chains
/// BTCP_ESCROW waits for the SLOWER of the two chains to finalize,
/// not the sum. This is a critical architectural difference from bridges.
#[derive(Debug, Default)]
pub struct FinalityNormalizer;

impl FinalityNormalizer {
    pub fn new() -> Self {
        FinalityNormalizer
    }

    /// Compute effective latency = max(A_finality, B_finality)
    /// NOT A + B. Both chains finalize in parallel.
    pub fn effective_latency(&self, a_finality_sec: f64, b_finality_sec: f64) -> f64 {
        a_finality_sec.max(b_finality_sec)
    }

    /// Convenience alias matching spec naming
    pub fn compute_effective_latency(&self, a_sec: f64, b_sec: f64) -> f64 {
        self.effective_latency(a_sec, b_sec)
    }

    /// Compare against bridge latency (which is typically sequential)
    pub fn compare_vs_bridge(&self, a_finality_sec: f64, b_finality_sec: f64) -> (f64, f64, f64) {
        let btcp = self.effective_latency(a_finality_sec, b_finality_sec);
        let bridge = a_finality_sec + b_finality_sec;
        let improvement = if bridge > 0.0 {
            (bridge - btcp) / bridge
        } else {
            0.0
        };
        (btcp, bridge, improvement)
    }

    /// Compute safe confirmation blocks based on chain finality characteristics
    pub fn safe_confirmations(&self, avg_block_time_sec: f64, finality_sec: f64) -> u64 {
        if avg_block_time_sec <= 0.0 {
            return 64;
        }
        // Add 20% safety margin
        ((finality_sec / avg_block_time_sec) * 1.2).ceil() as u64
    }

    /// Get effective latency with confidence interval
    pub fn effective_latency_with_ci(
        &self,
        a: (f64, f64, f64), // (mean, ci_low, ci_high)
        b: (f64, f64, f64),
    ) -> (f64, f64, f64) {
        let mean = a.0.max(b.0);
        let ci_low = a.1.max(b.1);
        let ci_high = a.2.max(b.2);
        (mean, ci_low, ci_high)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_effective_latency_max_not_sum() {
        let fnorm = FinalityNormalizer::new();

        // Arbitrum (2.5s) + Solana (0.4s)
        let effective = fnorm.effective_latency(2.5, 0.4);
        assert_eq!(effective, 2.5); // max, NOT 2.9
        assert_ne!(effective, 2.9);
    }

    #[test]
    fn test_compare_vs_bridge() {
        let fnorm = FinalityNormalizer::new();

        let (btcp, bridge, improvement) = fnorm.compare_vs_bridge(2.5, 0.4);
        assert_eq!(btcp, 2.5);
        assert_eq!(bridge, 2.9);
        assert!(improvement > 0.0);
        println!("BTCP: {:.1}s vs Bridge: {:.1}s → {:.0}% faster", btcp, bridge, improvement * 100.0);
    }

    #[test]
    fn test_safe_confirmations() {
        let fnorm = FinalityNormalizer::new();

        // Ethereum: 12s blocks, 600s (10min) finality
        let conf = fnorm.safe_confirmations(12.0, 600.0);
        assert!(conf > 50);
        println!("Ethereum safe confirmations: {}", conf);

        // Solana: 0.4s blocks, 12s finality
        let conf_sol = fnorm.safe_confirmations(0.4, 12.0);
        assert!(conf_sol > 30);
        println!("Solana safe confirmations: {}", conf_sol);
    }

    #[test]
    fn test_effective_latency_with_ci() {
        let fnorm = FinalityNormalizer::new();

        let a = (2.5, 2.0, 3.0);
        let b = (0.4, 0.3, 0.5);
        let result = fnorm.effective_latency_with_ci(a, b);

        assert_eq!(result.0, 2.5);
        assert_eq!(result.1, 2.0);
        assert_eq!(result.2, 3.0);
    }

    #[test]
    fn test_equal_finality() {
        let fnorm = FinalityNormalizer::new();
        let effective = fnorm.effective_latency(2.0, 2.0);
        assert_eq!(effective, 2.0);

        let (btcp, bridge, _) = fnorm.compare_vs_bridge(2.0, 2.0);
        assert_eq!(btcp, 2.0);
        assert_eq!(bridge, 4.0);
    }
}
