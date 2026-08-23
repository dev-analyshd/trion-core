//! sybil_resistance.rs — 5-layer Sponsored Genesis protection
//! Per BTCP Master Implementation Spec §Phase 2
//!
//! Layer 1: max sponsored by Akashic depth
//! Layer 2: scrutiny multiplier by number sponsored
//! Layer 3: behavioral similarity sockpuppet detection
//! Layer 4: minimum spacing between sponsorships
//! Layer 5: star pattern detection in sponsor graph

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
    /// max_sponsored = floor(ln(d/d_min) × BASE_SPONSOR_CAP)
    pub fn layer1_max_sponsored(&self, d: f64, d_min: f64) -> u32 {
        if d < d_min {
            return 0;
        }
        let ratio = d / d_min;
        (ratio.ln() * BASE_SPONSOR_CAP as f64).floor().max(0.0) as u32
    }

    /// Layer 2: Scrutiny multiplier increases with each sponsorship
    /// scrutiny = 1 + (n_sponsored × 0.5)
    pub fn layer2_scrutiny_multiplier(&self, n_sponsored: u32) -> f64 {
        1.0 + (n_sponsored as f64 * 0.5)
    }

    /// Layer 3: Sockpuppet detection via behavioral similarity
    /// cosine_similarity >= SIMILARITY_THRESHOLD → likely sockpuppet
    pub fn layer3_is_sockpuppet(&self, cosine_similarity: f64) -> bool {
        cosine_similarity >= SIMILARITY_THRESHOLD
    }

    /// Layer 4: Minimum spacing between sponsorships (days)
    /// spacing = BASE × (1 + n_sponsored × 0.5)
    pub fn layer4_min_spacing_days(&self, n_sponsored: u32) -> u64 {
        MIN_SPACING_BASE_DAYS * (100 + n_sponsored as u64 * 50) / 100
    }

    /// Convenience alias
    pub fn compute_spacing(&self, n: u32) -> u64 {
        self.layer4_min_spacing_days(n)
    }

    /// Layer 5: Detect star pattern in sponsor graph
    /// One entity sponsoring many in a short time → suspicious
    pub fn layer5_detect_star_pattern(
        &self,
        sponsor_graph: &HashMap<BEOId, Vec<BEOId>>,
    ) -> Vec<BEOId> {
        let mut suspicious = Vec::new();
        for (sponsor, sponsored) in sponsor_graph {
            // Star pattern: one sponsor, many sponsored (≥ 5)
            if sponsored.len() >= 5 {
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
            let min_spacing_sec = self.layer4_min_spacing_days(n) * 24 * 60 * 60;
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
        assert_eq!(sr.layer1_max_sponsored(100.0, 100.0), 0); // ln(1) = 0
        assert!(sr.layer1_max_sponsored(1000.0, 100.0) > 0);
        assert!(sr.layer1_max_sponsored(10000.0, 100.0) > sr.layer1_max_sponsored(1000.0, 100.0));

        println!("Max sponsored at depth 8000: {}", sr.layer1_max_sponsored(8000.0, 100.0));
    }

    #[test]
    fn test_layer2_scrutiny() {
        let sr = SybilResistance::new();
        assert_eq!(sr.layer2_scrutiny_multiplier(0), 1.0);
        assert_eq!(sr.layer2_scrutiny_multiplier(2), 2.0);
        assert_eq!(sr.layer2_scrutiny_multiplier(4), 3.0);
    }

    #[test]
    fn test_layer3_sockpuppet() {
        let sr = SybilResistance::new();
        assert!(sr.layer3_is_sockpuppet(0.92));
        assert!(!sr.layer3_is_sockpuppet(0.50));
        assert!(!sr.layer3_is_sockpuppet(SIMILARITY_THRESHOLD - 0.01));
        assert!(sr.layer3_is_sockpuppet(SIMILARITY_THRESHOLD));
    }

    #[test]
    fn test_layer4_min_spacing() {
        let sr = SybilResistance::new();
        assert_eq!(sr.layer4_min_spacing_days(0), 7);
        assert_eq!(sr.layer4_min_spacing_days(1), 10); // 7 × 1.5 = 10.5 → 10
        assert_eq!(sr.layer4_min_spacing_days(3), 17); // 7 × 2.5 = 17.5 → 17
    }

    #[test]
    fn test_layer5_star_pattern() {
        let sr = SybilResistance::new();
        let mut graph = HashMap::new();

        // Sponsor A has 6 sponsored → star pattern detected
        let sponsor_a = H256::sha3(b"sponsor_a");
        let mut sponsored_a = Vec::new();
        for i in 0..6 {
            sponsored_a.push(H256::sha3(format!("entity_{}", i).as_bytes()));
        }
        graph.insert(sponsor_a, sponsored_a);

        // Sponsor B has 2 sponsored → not a star
        let sponsor_b = H256::sha3(b"sponsor_b");
        graph.insert(sponsor_b, vec![H256::sha3(b"e1"), H256::sha3(b"e2")]);

        let suspicious = sr.layer5_detect_star_pattern(&graph);
        assert_eq!(suspicious.len(), 1);
        assert_eq!(suspicious[0], sponsor_a);
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
        assert!(!sr.can_sponsor(sponsor, 8000.0, 100.0, 0.3, now + 1000));

        // Second sponsorship after enough time: should pass
        let later = now + 30 * 24 * 60 * 60; // 30 days later
        assert!(sr.can_sponsor(sponsor, 8000.0, 100.0, 0.3, later));

        // Sockpuppet attempt: should fail
        assert!(!sr.can_sponsor(sponsor, 8000.0, 100.0, 0.95, later));
    }
}
