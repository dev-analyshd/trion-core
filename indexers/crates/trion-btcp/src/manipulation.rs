//! 7 MF Fingerprint Types (BTCP_15 Gap 3 Resolution)
//! T1-Sandwich(0.20), T2-Wash(0.15), T3-Oracle(0.25), T4-Layering(0.15),
//! T5-Spoofing(0.10), T6-CrossProtocol(0.10), T7-Statistical(0.05)
//! MF_score = weighted_max, T7 holds at 0.5 pending Conscious review

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum MfType { T1, T2, T3, T4, T5, T6, T7 }

pub const MF_WEIGHTS: [(MfType, f64); 7] = [
    (MfType::T1, 0.20), (MfType::T2, 0.15), (MfType::T3, 0.25),
    (MfType::T4, 0.15), (MfType::T5, 0.10), (MfType::T6, 0.10),
    (MfType::T7, 0.05),
];

#[derive(Debug, Clone)]
pub struct MfResult {
    pub mf_type: MfType,
    pub detected: bool,
    pub score: f64,
}

pub struct MfDetector;

impl MfDetector {
    /// T1: Sandwich — opposite sides + victim between + similar magnitude
    pub fn detect_t1(intent_a_side: &str, intent_b_side: &str,
                     victim_between: bool, magnitude_sim: f64) -> MfResult {
        let opposite = (intent_a_side == "BUY" && intent_b_side == "SELL")
                     || (intent_a_side == "SELL" && intent_b_side == "BUY");
        let score = if opposite && victim_between && magnitude_sim > 0.8 { magnitude_sim } else { 0.0 };
        MfResult { mf_type: MfType::T1, detected: score > 0.8, score }
    }

    /// T2: Wash Trading — self_trade_ratio × (1 - diversity)
    pub fn detect_t2(self_trade_ratio: f64, diversity: f64, frequency: f64) -> MfResult {
        if self_trade_ratio <= 0.0 {
            return MfResult { mf_type: MfType::T2, detected: false, score: 0.0 };
        }
        let freq_factor = (frequency / 10.0).min(1.0);
        let score = (self_trade_ratio * (1.0 - diversity) * (0.5 + 0.5 * freq_factor)).min(1.0);
        MfResult { mf_type: MfType::T2, detected: score > 0.5, score }
    }

    /// T3: Oracle Manipulation — deviation + borrow/liquidate window
    pub fn detect_t3(swap_dev: f64, oracle_dev: f64, borrow_liquidate: bool) -> MfResult {
        let max_dev = swap_dev.max(oracle_dev);
        let base = (max_dev / 0.20).min(1.0);
        let amplifier = if borrow_liquidate { 5.0 } else { 1.0 };
        let score = (base * amplifier).min(1.0);
        let detected = borrow_liquidate && base > 0.25;
        MfResult { mf_type: MfType::T3, detected, score }
    }

    /// T7: Statistical Anomaly — KC delta, holds at 0.5
    pub fn detect_t7(kc_delta: f64, historical_kc: f64) -> MfResult {
        if historical_kc <= 0.0 {
            return MfResult { mf_type: MfType::T7, detected: false, score: 0.0 };
        }
        let rel = kc_delta.abs() / historical_kc;
        let score = (rel / 0.30).min(1.0);
        MfResult { mf_type: MfType::T7, detected: rel > 0.30, score }
    }

    /// MF_score = weighted_max, T7 holds at 0.5
    pub fn compute_mf_score(results: &[MfResult; 7]) -> (f64, bool) {
        let max_weighted = MF_WEIGHTS.iter().zip(results.iter())
            .map(|((_, w), r)| w * r.score)
            .fold(0.0f64, f64::max);

        let detected_any = results.iter().any(|r| r.detected);
        let max_detected_weight = MF_WEIGHTS.iter().zip(results.iter())
            .filter(|(_, r)| r.detected)
            .map(|((_, w), _)| *w)
            .fold(0.0f64, f64::max);

        let mut mf_score = if detected_any { max_weighted.max(max_detected_weight) } else { max_weighted };
        let t7_detected = results[6].detected;
        if t7_detected { mf_score = mf_score.max(0.5); }
        (mf_score.clamp(0.0, 1.0), t7_detected)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_weights_sum_to_1() {
        let total: f64 = MF_WEIGHTS.iter().map(|(_, w)| *w).sum();
        assert!((total - 1.0).abs() < 1e-9);
    }

    #[test]
    fn test_t1_sandwich() {
        let r = MfDetector::detect_t1("BUY", "SELL", true, 0.95);
        assert!(r.detected);
    }

    #[test]
    fn test_t2_wash() {
        let r = MfDetector::detect_t2(0.8, 0.2, 8.0);
        assert!(r.detected);
    }

    #[test]
    fn test_t7_holds_at_0_5() {
        let r = MfDetector::detect_t7(0.25, 0.50); // 50% delta
        assert!(r.detected);
        // When T7 is detected in the full array, score holds at >= 0.5
        let results = [
            MfResult { mf_type: MfType::T1, detected: false, score: 0.0 },
            MfResult { mf_type: MfType::T2, detected: false, score: 0.0 },
            MfResult { mf_type: MfType::T3, detected: false, score: 0.0 },
            MfResult { mf_type: MfType::T4, detected: false, score: 0.0 },
            MfResult { mf_type: MfType::T5, detected: false, score: 0.0 },
            MfResult { mf_type: MfType::T6, detected: false, score: 0.0 },
            r,
        ];
        let (score, review) = MfDetector::compute_mf_score(&results);
        assert!(review);
        assert!(score >= 0.5);
    }
}
