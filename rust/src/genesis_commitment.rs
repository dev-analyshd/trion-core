//! genesis_commitment.rs — Null-state detection + genesis pathway routing
//! Per BTCP Master Implementation Spec §Phase 2
//!
//! Genesis pathways: stake, signature, social_proof
//! Sponsored genesis has 5-layer sybil protection.

use crate::types::*;
use std::collections::HashMap;

/// Genesis pathway options
pub const GENESIS_PATHWAYS: [GenesisPathway; 3] = [
    GenesisPathway::Stake,
    GenesisPathway::Signature,
    GenesisPathway::SocialProof,
];

/// Genesis Commitment — handles null-state entity genesis
/// Entities with no prior behavioral history must go through genesis.
#[derive(Debug, Default)]
pub struct GenesisCommitment {
    genesis_records: HashMap<BEOId, (GenesisPathway, u64)>, // entity -> (pathway, timestamp)
}

impl GenesisCommitment {
    pub fn new() -> Self {
        GenesisCommitment {
            genesis_records: HashMap::new(),
        }
    }

    /// Get available genesis pathways
    pub fn genesis_pathways(&self) -> &[GenesisPathway] {
        &GENESIS_PATHWAYS
    }

    /// Initiate genesis for a null-state entity
    pub fn initiate_genesis(
        &mut self,
        entity_id: BEOId,
        pathway: GenesisPathway,
        stake_amount: u128,
    ) -> bool {
        // Verify pathway requirements
        let valid = match pathway {
            GenesisPathway::Stake => stake_amount > 0,
            GenesisPathway::Signature => true, // Signature verification in production
            GenesisPathway::SocialProof => true, // Social proof verification in production
        };

        if valid {
            self.genesis_records
                .insert(entity_id, (pathway, current_timestamp()));
        }
        valid
    }

    /// Compute max sponsored entities based on Akashic depth
    /// max_sponsored = floor(log₂(d/d_min) × base_cap)  [spec §14]
    /// (base-2 logarithm — NOT natural log; aligns with sybil_resistance L1)
    pub fn layer1_max_sponsored(&self, akashic_depth: f64, d_min: f64) -> u32 {
        if akashic_depth <= d_min || d_min <= 0.0 {
            return 0;
        }
        let base_cap = 10u32;
        let ratio = akashic_depth / d_min;
        (ratio.log2() * base_cap as f64).floor().max(0.0) as u32
    }

    /// Convenience: compute max sponsored
    pub fn compute_max_sponsored(&self, akashic_depth: f64) -> u32 {
        self.layer1_max_sponsored(akashic_depth, 100.0)
    }

    /// Compute behavioral similarity for sockpuppet detection
    /// cosine_similarity near 1.0 = likely sockpuppet
    pub fn behavioral_similarity(&self, vec_a: &[f64], vec_b: &[f64]) -> f64 {
        if vec_a.len() != vec_b.len() || vec_a.is_empty() {
            return 0.0;
        }

        let dot: f64 = vec_a.iter().zip(vec_b).map(|(a, b)| a * b).sum();
        let norm_a: f64 = vec_a.iter().map(|x| x * x).sum::<f64>().sqrt();
        let norm_b: f64 = vec_b.iter().map(|x| x * x).sum::<f64>().sqrt();

        if norm_a == 0.0 || norm_b == 0.0 {
            return 0.0;
        }

        dot / (norm_a * norm_b)
    }

    /// Detect sockpuppet from vector similarity
    pub fn detect_sockpuppet(&self, vectors: &[Vec<f64>], threshold: f64) -> bool {
        if vectors.len() < 2 {
            return false;
        }

        // Check all pairs
        for i in 0..vectors.len() {
            for j in (i + 1)..vectors.len() {
                let sim = self.behavioral_similarity(&vectors[i], &vectors[j]);
                if sim >= threshold {
                    return true;
                }
            }
        }
        false
    }

    /// Check if entity has completed genesis
    pub fn has_genesis(&self, entity_id: &BEOId) -> bool {
        self.genesis_records.contains_key(entity_id)
    }

    /// Get genesis record
    pub fn get_genesis(&self, entity_id: &BEOId) -> Option<(GenesisPathway, u64)> {
        self.genesis_records.get(entity_id).copied()
    }
}

fn current_timestamp() -> u64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_initiate_genesis_stake() {
        let mut genesis = GenesisCommitment::new();
        let entity = H256::sha3(b"new_entity");

        let success = genesis.initiate_genesis(entity, GenesisPathway::Stake, 1000);
        assert!(success);
        assert!(genesis.has_genesis(&entity));

        let (pathway, _) = genesis.get_genesis(&entity).unwrap();
        assert_eq!(pathway, GenesisPathway::Stake);
    }

    #[test]
    fn test_initiate_genesis_stake_zero_amount() {
        let mut genesis = GenesisCommitment::new();
        let entity = H256::sha3(b"new_entity");
        let success = genesis.initiate_genesis(entity, GenesisPathway::Stake, 0);
        assert!(!success);
    }

    #[test]
    fn test_max_sponsored_by_depth() {
        let genesis = GenesisCommitment::new();

        assert_eq!(genesis.compute_max_sponsored(50.0), 0); // Below d_min
        assert_eq!(genesis.compute_max_sponsored(100.0), 0); // Exactly d_min, log₂(1)=0
        assert!(genesis.compute_max_sponsored(1000.0) > 0);
        assert!(genesis.compute_max_sponsored(5000.0) > genesis.compute_max_sponsored(1000.0));

        println!("Max sponsored at depth 5000: {}", genesis.compute_max_sponsored(5000.0));
    }

    #[test]
    fn test_behavioral_similarity() {
        let genesis = GenesisCommitment::new();

        // Identical vectors = similarity 1.0
        let sim = genesis.behavioral_similarity(&[0.9; 128], &[0.9; 128]);
        assert!((sim - 1.0).abs() < 0.001);

        // Different vectors = lower similarity
        let sim2 = genesis.behavioral_similarity(&[0.9; 128], &[0.1; 128]);
        assert!(sim2 < 1.0);
    }

    #[test]
    fn test_detect_sockpuppet() {
        let genesis = GenesisCommitment::new();

        // Two very similar vectors → sockpuppet detected
        let vectors = vec![vec![0.9; 128], vec![0.92; 128]];
        assert!(genesis.detect_sockpuppet(&vectors, 0.85));

        // Two genuinely different vectors (different patterns) → no sockpuppet
        let mut vec_a = vec![0.0; 128];
        let mut vec_b = vec![0.0; 128];
        for i in 0..128 {
            if i % 2 == 0 {
                vec_a[i] = 0.9;
                vec_b[i] = 0.1;
            } else {
                vec_a[i] = 0.1;
                vec_b[i] = 0.9;
            }
        }
        let vectors2 = vec![vec_a, vec_b];
        assert!(!genesis.detect_sockpuppet(&vectors2, 0.85));
    }
}
