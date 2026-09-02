//! btcp_proof_builder.rs — BTCP proof construction with reorg protection
//! Per BTCP Master Implementation Spec §Phase 2

use crate::types::*;

/// Simple deterministic pseudo-random generator based on SHA3
/// Used for test mock signature generation

/// Certification window constants by value tier
pub const CERT_WINDOWS: [(u64, u64); 4] = [
    (0, 50000),        // < $10k: 50k blocks
    (10_000, 100000),  // $10k-$100k: 100k blocks
    (100_000, 200000), // $100k-$1M: 200k blocks
    (1_000_000, 500000), // > $1M: 500k blocks
];

/// Maximum number of blocks after the certification (anchor) block within
/// which a BTCP proof remains valid (reorg / expiry guard).
///
/// `verify_proof` rejects a proof when
/// `current_block > anchor_block + MAX_PROOF_VALIDITY_BLOCKS` (the anchor
/// block is the certification block stored in the proof's diversity
/// certificate). Past this window the certification is expired and the
/// anchor may have been reorged out — the advertised reorg protection of
/// this module depends on this check. Mirrors the Python reference
/// (`core/btcp/modules.py`: `current_block > proof.certification_expiry →
/// invalid`). Defaults to the most conservative certification window tier
/// (`CERT_WINDOWS[0].1` = 50,000 blocks — the sub-$10k tier).
pub const MAX_PROOF_VALIDITY_BLOCKS: u64 = 50_000;

/// BTCP Proof Builder — constructs consensus proofs for cross-chain routes
#[derive(Debug, Default)]
pub struct BTCPProofBuilder {
    current_block: u64,
}

impl BTCPProofBuilder {
    pub fn new() -> Self {
        BTCPProofBuilder { current_block: 0 }
    }

    pub fn with_block(block: u64) -> Self {
        BTCPProofBuilder { current_block: block }
    }

    /// Build a complete BTCP proof
    pub fn build_proof(
        &self,
        anchor_bh: H256,
        intent_hash: H256,
        route_type: &str,
        certification_block: u64,
        value_usd: f64,
        validator_signatures: Vec<WeightedSignature>,
        diversity_weights: Vec<f64>,
        hhi: f64,
        coherence: f64,
        threshold: f64,
        validator_key_version: &str,
    ) -> BTCPProof {
        let btcp_route_id = H256::sha3(
            format!(
                "{}:{}:{}:{}",
                anchor_bh.to_hex(),
                intent_hash.to_hex(),
                route_type,
                certification_block
            )
            .as_bytes(),
        );

        let diversity_cert = DiversityCertificate {
            hhi,
            num_validators: validator_signatures.len() as u32,
            weights: diversity_weights,
            block_number: certification_block,
        };

        let consensus_proof = ConsensusProof {
            validator_signatures,
            diversity_cert,
            coherence_score: coherence,
            threshold,
        };

        BTCPProof {
            anchor_bh,
            consensus_proof,
            intent_hash,
            btcp_route_id,
            anchor_chain: 0, // Set by caller
            execution_chain: 0, // Set by caller
            btcp_version: SemVer::parse(crate::BTCP_VERSION).unwrap_or(SemVer::new(1, 0, 0)),
            feature_flags: FeatureFlags::default(),
            min_verifier_ver: SemVer::parse(validator_key_version)
                .unwrap_or(SemVer::new(1, 0, 0)),
        }
    }

    /// Compute certification expiry block based on route value
    pub fn compute_cert_expiry(&self, value_usd: f64) -> u64 {
        for (threshold, window) in CERT_WINDOWS.iter().rev() {
            if value_usd >= *threshold as f64 {
                return *window;
            }
        }
        CERT_WINDOWS[0].1
    }

    /// Verify a BTCP proof
    ///
    /// Checks, in order (mirrors the Python reference Module 2.4):
    /// 1. Reorg/expiry: current block must be within
    ///    MAX_PROOF_VALIDITY_BLOCKS of the anchor (certification) block
    /// 2. Consensus coherence exceeds threshold
    /// 3. HHI indicates reasonable distribution (not too concentrated)
    /// 4. Minimum validator signatures
    /// 5. Version compatibility
    pub fn verify_proof(&self, proof: &BTCPProof, current_block: u64) -> bool {
        // Reorg / expiry check: block-height validity window relative to the
        // anchor (certification) block recorded in the diversity certificate.
        // A proof consumed too many blocks after certification is stale —
        // the anchor may no longer be part of the canonical chain.
        let anchor_block = proof.consensus_proof.diversity_cert.block_number;
        if current_block > anchor_block.saturating_add(MAX_PROOF_VALIDITY_BLOCKS) {
            return false; // certification expired / anchor too deep (reorg risk)
        }

        // Check consensus coherence exceeds threshold
        if proof.consensus_proof.coherence_score < proof.consensus_proof.threshold {
            return false;
        }

        // Check HHI indicates reasonable distribution (not too concentrated)
        if proof.consensus_proof.diversity_cert.hhi > 0.5 {
            return false;
        }

        // Check minimum validator signatures
        if proof.consensus_proof.validator_signatures.len() < 3 {
            return false;
        }

        // Check version compatibility
        if proof.btcp_version.major < 1 {
            return false;
        }

        true
    }

    /// Generate mock validator signatures for testing
    /// Uses deterministic SHA3-based pseudo-random generation
    pub fn generate_mock_signatures(num: u32) -> (Vec<WeightedSignature>, Vec<f64>, f64) {
        let mut sigs = Vec::new();
        let mut weights = Vec::new();

        for i in 0..num {
            // Deterministic pseudo-random based on index
            let seed1 = H256::sha3(format!("stake_{}", i).as_bytes());
            let seed2 = H256::sha3(format!("div_{}", i).as_bytes());
            
            let stake_weight = 0.5 + (seed1.0[0] as f64 / 255.0);
            let diversity_weight = 0.7 + (seed2.0[0] as f64 / 255.0) * 0.3;

            sigs.push(WeightedSignature {
                validator_id: H256::sha3(format!("validator_{}", i).as_bytes()),
                signature: vec![i as u8; 64],
                stake_weight,
                diversity_weight,
            });
            weights.push(diversity_weight);
        }

        // HHI: sum of squared shares. For uniform distribution of N validators, HHI ≈ 1/N
        let share = 1.0 / num as f64;
        let hhi = num as f64 * share * share;

        (sigs, weights, hhi)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_build_proof() {
        let builder = BTCPProofBuilder::with_block(18000000);

        let (sigs, weights, hhi) = BTCPProofBuilder::generate_mock_signatures(5);

        let proof = builder.build_proof(
            H256::sha3(b"anchor"),
            H256::sha3(b"intent"),
            "SPLIT",
            18000000,
            3000.0,
            sigs,
            weights,
            hhi,
            0.82,
            0.55,
            "2.0.0",
        );

        assert_ne!(proof.btcp_route_id, H256::zero());
        assert_eq!(proof.consensus_proof.coherence_score, 0.82);
        assert_eq!(proof.consensus_proof.threshold, 0.55);
        assert_eq!(proof.consensus_proof.validator_signatures.len(), 5);
        assert_eq!(proof.feature_flags.sensing_oracle, false);
    }

    #[test]
    fn test_cert_expiry() {
        let builder = BTCPProofBuilder::new();
        assert_eq!(builder.compute_cert_expiry(500.0), 50000);
        assert_eq!(builder.compute_cert_expiry(50_000.0), 100000);
        assert_eq!(builder.compute_cert_expiry(500_000.0), 200000);
        assert_eq!(builder.compute_cert_expiry(5_000_000.0), 500000);
    }

    #[test]
    fn test_verify_proof() {
        let builder = BTCPProofBuilder::with_block(18000000);
        let (sigs, weights, hhi) = BTCPProofBuilder::generate_mock_signatures(5);

        let mut proof = builder.build_proof(
            H256::sha3(b"anchor"),
            H256::sha3(b"intent"),
            "SPLIT",
            18000000,
            3000.0,
            sigs,
            weights,
            hhi,
            0.82,
            0.55,
            "2.0.0",
        );

        // Valid proof
        assert!(builder.verify_proof(&proof, 18001000));

        // Invalid: coherence below threshold
        proof.consensus_proof.coherence_score = 0.40;
        assert!(!builder.verify_proof(&proof, 18001000));
    }

    #[test]
    fn test_verify_proof_expiry() {
        let builder = BTCPProofBuilder::with_block(18000000);
        let (sigs, weights, hhi) = BTCPProofBuilder::generate_mock_signatures(5);

        // Proof certified (anchored) at block 18000000
        let proof = builder.build_proof(
            H256::sha3(b"anchor"),
            H256::sha3(b"intent"),
            "SPLIT",
            18000000,
            3000.0,
            sigs,
            weights,
            hhi,
            0.82,
            0.55,
            "2.0.0",
        );

        let anchor_block = proof.consensus_proof.diversity_cert.block_number;
        assert_eq!(anchor_block, 18000000);

        // Well within the validity window: valid
        assert!(builder.verify_proof(&proof, 18001000));

        // Last block of the validity window: still valid (window is inclusive)
        assert!(builder.verify_proof(&proof, anchor_block + MAX_PROOF_VALIDITY_BLOCKS));

        // One block past the window: expired (reorg / staleness risk)
        assert!(!builder.verify_proof(&proof, anchor_block + MAX_PROOF_VALIDITY_BLOCKS + 1));

        // Far past the window: expired
        assert!(!builder.verify_proof(&proof, anchor_block + 500_000));
    }

    #[test]
    fn test_hhi_calculation() {
        let builder = BTCPProofBuilder::new();
        let (_, _, hhi_5) = BTCPProofBuilder::generate_mock_signatures(5);
        let (_, _, hhi_100) = BTCPProofBuilder::generate_mock_signatures(100);

        // More validators = lower HHI = more distributed
        assert!(hhi_100 < hhi_5);
        println!("HHI (5 validators): {:.4}", hhi_5);
        println!("HHI (100 validators): {:.6}", hhi_100);
    }
}
