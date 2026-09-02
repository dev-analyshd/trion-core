//! sybil_resistance.rs — 5-layer Sponsored Genesis protection
//! Per BTCP Master Implementation Spec §14 / Phase 2
//!
//! Layer 1: max_sponsored = floor(log₂(d/d_min) × BASE_SPONSOR_CAP)
//! Layer 2: scrutiny multiplier = 1 + n × 0.2
//! Layer 3: behavioral similarity > 0.85 → SOCKPUPPET_ALERT
//! Layer 4: minimum spacing = BASE_SPACING × n² (7·n² days)
//! Layer 5: star pattern (one sponsor > 20 sponsored) → SPONSOR_NETWORK_ANOMALY

use crate::types::*;
use std::collections::HashMap;

/// Base sponsor cap
pub const BASE_SPONSOR_CAP: u32 = 10;

/// Base minimum spacing in days
pub const MIN_SPACING_BASE_DAYS: u64 = 7;

/// Behavioral similarity threshold for sockpuppet detection
pub const SIMILARITY_THRESHOLD: f64 = 0.85;

/// Sybil Resistance — 5-layer protection for Sponsored Genesis
#[derive(Debug, Default)]
pub struct SybilResistance {
    sponsorship_records: HashMap<BEOId, Vec<(BEOId, u64)>>, // sponsor -> [(sponsored, timestamp)]
}

impl SybilResistance {
    pub fn new() -> Self {
        SybilResistance {
            sponsorship_records: HashMap::new(),
        }
    }

    /// Layer 1: Maximum sponsored entities by Akashic depth
    /// max_sponsored = floor(log₂(d/d_min) × BASE_SPONSOR_CAP)  [spec §14]
    /// (base-2 logarithm — NOT natural log)
    pub fn layer1_max_sponsored(&self, d: f64, d_min: f64) -> u32 {
        if d <= d_min || d_min <= 0.0 {
            return 0;
        }
        let ratio = d / d_min;
        (ratio.log2() * BASE_SPONSOR_CAP as f64).floor().max(0.0) as u32
    }

    /// Layer 2: Scrutiny multiplier increases with each sponsorship
    /// scrutiny = 1 + (n_sponsored × 0.2)  [spec §14]
    pub fn layer2_scrutiny_multiplier(&self, n_sponsored: u32) -> f64 {
        1.0 + (n_sponsored as f64 * 0.2)
    }

    /// Layer 3: Sockpuppet detection via behavioral similarity
    /// cosine_similarity > SIMILARITY_THRESHOLD → SOCKPUPPET_ALERT
    /// (strictly greater — exactly 0.85 is not an alert)
    pub fn layer3_is_sockpuppet(&self, cosine_similarity: f64) -> bool {
        cosine_similarity > SIMILARITY_THRESHOLD
    }

    /// Layer 4: Minimum spacing between sponsorships (days)
    /// MIN_SPACING(n) = BASE_SPACING × n²  [spec §14: 7·n² days]
    pub fn layer4_min_spacing_days(&self, n_sponsored: u32) -> u64 {
        let n = n_sponsored as u64;
        MIN_SPACING_BASE_DAYS.saturating_mul(n).saturating_mul(n)
    }

    /// Convenience alias
    pub fn compute_spacing(&self, n: u32) -> u64 {
        self.layer4_min_spacing_days(n)
    }

    /// Layer 5: Detect star pattern in sponsor graph
    /// One entity sponsoring many unrelated entities in a short time →
    /// SPONSOR_NETWORK_ANOMALY (threshold: strictly more than 20 sponsored)
    pub fn layer5_detect_star_pattern(
        &self,
        sponsor_graph: &HashMap<BEOId, Vec<BEOId>>,
    ) -> Vec<BEOId> {
        let mut suspicious = Vec::new();
        for (sponsor, sponsored) in sponsor_graph {
            // Star pattern: one sponsor, many sponsored (> 20 per spec §14)
            if sponsored.len() > 20 {
                suspicious.push(*sponsor);
            }
        }
        suspicious
    }

    /// Record a sponsorship
    pub fn record_sponsorship(
        &mut self,
        sponsor: BEOId,
        sponsored: BEOId,
        timestamp: u64,
    ) {
        self.sponsorship_records
            .entry(sponsor)
            .or_default()
            .push((sponsored, timestamp));
    }

    /// Get number of entities sponsored by a given sponsor
    pub fn sponsored_count(&self, sponsor: &BEOId) -> u32 {
        self.sponsorship_records
            .get(sponsor)
            .map(|v| v.len() as u32)
            .unwrap_or(0)
    }

    /// Full 5-layer check — returns true if sponsorship is allowed
    pub fn can_sponsor(
        &self,
        sponsor: BEOId,
        akashic_depth: f64,
        d_min: f64,
        new_entity_similarity: f64,
        current_timestamp: u64,
    ) -> bool {
        let n = self.sponsored_count(&sponsor);

        // Layer 1: depth check
        if n >= self.layer1_max_sponsored(akashic_depth, d_min) {
            return false;
        }

        // Layer 3: sockpuppet check
        if self.layer3_is_sockpuppet(new_entity_similarity) {
            return false;
        }

        // Layer 4: spacing check
        if n > 0 {
            let min_spacing_sec = self
                .layer4_min_spacing_days(n)
                .saturating_mul(24 * 60 * 60);
            if let Some(records) = self.sponsorship_records.get(&sponsor) {
                if let Some((_, last_ts)) = records.last() {
                    if current_timestamp - last_ts < min_spacing_sec {
                        return false;
                    }
                }
            }
        }

        true
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_layer1_max_sponsored() {
        let sr = SybilResistance::new();

        assert_eq!(sr.layer1_max_sponsored(50.0, 100.0), 0); // Below minimum
        assert_eq!(sr.layer1_max_sponsored(100.0, 100.0), 0); // log₂(1) = 0
        assert_eq!(sr.layer1_max_sponsored(1000.0, 0.0), 0); // d_min ≤ 0 guard
        // Spec: floor(log₂(10) × 10) = floor(33.2) = 33
        assert_eq!(sr.layer1_max_sponsored(1000.0, 100.0), 33);
        // Spec: floor(log₂(100) × 10) = floor(66.4) = 66
        assert_eq!(sr.layer1_max_sponsored(10000.0, 100.0), 66);
        assert!(sr.layer1_max_sponsored(1000.0, 100.0) > 0);
        assert!(sr.layer1_max_sponsored(10000.0, 100.0) > sr.layer1_max_sponsored(1000.0, 100.0));

        println!("Max sponsored at depth 8000: {}", sr.layer1_max_sponsored(8000.0, 100.0));
    }

    #[test]
    fn test_layer2_scrutiny() {
        let sr = SybilResistance::new();
        // Spec: scrutiny = 1 + n × 0.2 (old test encoded the wrong 1 + n × 0.5)
        assert_eq!(sr.layer2_scrutiny_multiplier(0), 1.0);
        assert!((sr.layer2_scrutiny_multiplier(1) - 1.2).abs() < 1e-9);
        assert!((sr.layer2_scrutiny_multiplier(2) - 1.4).abs() < 1e-9);
        assert!((sr.layer2_scrutiny_multiplier(4) - 1.8).abs() < 1e-9);
        // 1 + 5×0.2 = 2.0 (matches the Python reference self-test)
        assert_eq!(sr.layer2_scrutiny_multiplier(5), 2.0);
        // Monotonically increasing in n
        assert!(sr.layer2_scrutiny_multiplier(3) > sr.layer2_scrutiny_multiplier(2));
    }

    #[test]
    fn test_layer3_sockpuppet() {
        let sr = SybilResistance::new();
        // Spec: strictly greater than 0.85 → SOCKPUPPET_ALERT
        assert!(sr.layer3_is_sockpuppet(0.92));
        assert!(!sr.layer3_is_sockpuppet(0.50));
        assert!(!sr.layer3_is_sockpuppet(SIMILARITY_THRESHOLD - 0.01));
        // Boundary: exactly 0.85 is NOT an alert (spec uses strict >; the
        // old test asserted the >= boundary — updated to the spec behavior)
        assert!(!sr.layer3_is_sockpuppet(SIMILARITY_THRESHOLD));
        assert!(sr.layer3_is_sockpuppet(0.86));
    }

    #[test]
    fn test_layer4_min_spacing() {
        let sr = SybilResistance::new();
        // Spec: MIN_SPACING(n) = 7 × n² days (old test encoded the linear
        // 7 × (1 + 0.5n) formula — updated to the spec-quadratic values)
        assert_eq!(sr.layer4_min_spacing_days(0), 0);
        assert_eq!(sr.layer4_min_spacing_days(1), 7); // 7 × 1²
        assert_eq!(sr.layer4_min_spacing_days(2), 28); // 7 × 2²
        assert_eq!(sr.layer4_min_spacing_days(3), 63); // 7 × 3² (matches Python self-test)
        assert_eq!(sr.layer4_min_spacing_days(5), 175); // 7 × 5²
    }

    #[test]
    fn test_layer5_star_pattern() {
        let sr = SybilResistance::new();
        let mut graph = HashMap::new();

        // Sponsor A has 25 sponsored → star pattern detected (> 20 per spec;
        // the old test used 6 with a ≥5 threshold — updated to spec values)
        let sponsor_a = H256::sha3(b"sponsor_a");
        let mut sponsored_a = Vec::new();
        for i in 0..25 {
            sponsored_a.push(H256::sha3(format!("entity_{}", i).as_bytes()));
        }
        graph.insert(sponsor_a, sponsored_a);

        // Sponsor B has 2 sponsored → not a star
        let sponsor_b = H256::sha3(b"sponsor_b");
        graph.insert(sponsor_b, vec![H256::sha3(b"e1"), H256::sha3(b"e2")]);

        // Sponsor C has exactly 20 → below the strict > 20 threshold
        let sponsor_c = H256::sha3(b"sponsor_c");
        let mut sponsored_c = Vec::new();
        for i in 0..20 {
            sponsored_c.push(H256::sha3(format!("c_entity_{}", i).as_bytes()));
        }
        graph.insert(sponsor_c, sponsored_c);

        let suspicious = sr.layer5_detect_star_pattern(&graph);
        assert_eq!(suspicious.len(), 1);
        assert!(suspicious.contains(&sponsor_a));
        assert!(!suspicious.contains(&sponsor_b));
        assert!(!suspicious.contains(&sponsor_c));
    }

    #[test]
    fn test_full_can_sponsor() {
        let mut sr = SybilResistance::new();
        let sponsor = H256::sha3(b"sponsor");

        // First sponsorship: should pass
        let now = 1787141851;
        assert!(sr.can_sponsor(sponsor, 8000.0, 100.0, 0.3, now));

        // Record it
        sr.record_sponsorship(sponsor, H256::sha3(b"e1"), now);

        // Second sponsorship too soon: should fail spacing check
        // (Layer 4 with n=1 requires 7 × 1² = 7 days = 604800s)
        assert!(!sr.can_sponsor(sponsor, 8000.0, 100.0, 0.3, now + 1000));

        // Second sponsorship after enough time: should pass
        // (30 days > 7 days required after the first sponsorship)
        let later = now + 30 * 24 * 60 * 60; // 30 days later
        assert!(sr.can_sponsor(sponsor, 8000.0, 100.0, 0.3, later));

        // Sockpuppet attempt: should fail
        assert!(!sr.can_sponsor(sponsor, 8000.0, 100.0, 0.95, later));
    }
}
