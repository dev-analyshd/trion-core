//! btcp_proof_builder.rs — BTCP proof construction with reorg protection
//! Per BTCP Master Implementation Spec §Phase 2
//!
//! HONEST LIMITATION: `verify_proof` performs STRUCTURAL checks only.
//! This crate has no secp256k1/ECDSA dependency (see Cargo.toml: sha3 +
//! hex only), so no signature is ever cryptographically verified here.
//! The best outcome is `ProofVerificationStatus::UnverifiedSignatures` —
//! on-chain/quorum verification is required before releasing funds.

use crate::types::*;
use std::collections::HashSet;

/// Deterministic SHA3-based pseudo-random fixture generation —
/// TEST-ONLY (see `generate_mock_signatures_for_tests` in `mod tests`)

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

/// Outcome of `BTCPProofBuilder::verify_proof`.
///
/// HONEST LIMITATION — no cryptographic signature verification is
/// performed by this crate: there is no secp256k1/ECDSA dependency, so no
/// signature is ever checked against a public key or validator set. The
/// best possible outcome is [`ProofVerificationStatus::UnverifiedSignatures`]:
/// every *structural* check passed (validity window, coherence, HHI, ≥3
/// distinct signers with well-formed 65-byte signatures, version), but
/// the signatures themselves remain unverified. An on-chain / quorum
/// signature verification step (recover pubkey → derive address → check
/// validator-set membership) is REQUIRED before this proof may release
/// any funds.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProofVerificationStatus {
    /// All structural checks passed; the signatures are 65-byte
    /// well-formed and come from ≥3 distinct validator IDs — but they are
    /// NOT cryptographically verified. On-chain/quorum verification is
    /// required before release.
    UnverifiedSignatures,
    /// Certification expired: current block is beyond the anchor block's
    /// reorg-protection window (`MAX_PROOF_VALIDITY_BLOCKS`).
    Expired,
    /// Coherence score below the consensus threshold.
    CoherenceBelowThreshold,
    /// Validator set too concentrated (HHI above the 0.5 limit).
    TooConcentrated,
    /// Fewer than 3 validator signatures.
    InsufficientSigners,
    /// The same validator_id appears more than once in the signature set
    /// (padding the signer count with duplicates is not consensus).
    DuplicateSigner,
    /// A signature is not a well-formed 65-byte secp256k1 ECDSA value
    /// (r[32] || s[32] || v[1]) — length/shape check only, NOT a
    /// cryptographic check.
    MalformedSignature,
    /// Incompatible proof version.
    VersionIncompatible,
}

impl ProofVerificationStatus {
    /// True when the proof passed every check this crate can perform.
    ///
    /// NOTE: even `true` does NOT mean the signatures were verified —
    /// the best outcome this crate can produce is
    /// [`ProofVerificationStatus::UnverifiedSignatures`].
    pub fn passed_structural_checks(&self) -> bool {
        matches!(self, Self::UnverifiedSignatures)
    }
}

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

    /// Verify a BTCP proof (structural checks only — see below).
    ///
    /// Checks, in order (mirrors the Python reference Module 2.4):
    /// 1. Reorg/expiry: current block must be within
    ///    MAX_PROOF_VALIDITY_BLOCKS of the anchor (certification) block
    /// 2. Consensus coherence exceeds threshold
    /// 3. HHI indicates reasonable distribution (not too concentrated)
    /// 4. Minimum 3 signatures, from 3 *distinct* validator IDs, each
    ///    signature a well-formed 65-byte value (r||s||v — length check
    ///    only, not a cryptographic check)
    /// 5. Version compatibility
    ///
    /// HONEST LIMITATION: signatures are NOT cryptographically verified
    /// (no secp256k1/ECDSA dependency in this crate). On success this
    /// returns [`ProofVerificationStatus::UnverifiedSignatures`] — an
    /// on-chain / quorum verification step is REQUIRED before the proof
    /// may be used to release funds.
    pub fn verify_proof(&self, proof: &BTCPProof, current_block: u64) -> ProofVerificationStatus {
        // Reorg / expiry check: block-height validity window relative to the
        // anchor (certification) block recorded in the diversity certificate.
        // A proof consumed too many blocks after certification is stale —
        // the anchor may no longer be part of the canonical chain.
        let anchor_block = proof.consensus_proof.diversity_cert.block_number;
        if current_block > anchor_block.saturating_add(MAX_PROOF_VALIDITY_BLOCKS) {
            return ProofVerificationStatus::Expired; // certification expired / anchor too deep (reorg risk)
        }

        // Check consensus coherence exceeds threshold
        if proof.consensus_proof.coherence_score < proof.consensus_proof.threshold {
            return ProofVerificationStatus::CoherenceBelowThreshold;
        }

        // Check HHI indicates reasonable distribution (not too concentrated)
        if proof.consensus_proof.diversity_cert.hhi > 0.5 {
            return ProofVerificationStatus::TooConcentrated;
        }

        // Check minimum validator signatures
        if proof.consensus_proof.validator_signatures.len() < 3 {
            return ProofVerificationStatus::InsufficientSigners;
        }

        // Distinct, well-formed signers: one signature per validator, each
        // exactly 65 bytes (secp256k1 ECDSA r[32] || s[32] || v[1]). This is
        // a length/shape check only — it is NOT a cryptographic check.
        let mut seen_validators = HashSet::new();
        for sig in &proof.consensus_proof.validator_signatures {
            if !seen_validators.insert(sig.validator_id) {
                return ProofVerificationStatus::DuplicateSigner;
            }
            if sig.signature.len() != 65 {
                return ProofVerificationStatus::MalformedSignature;
            }
        }

        // Check version compatibility
        if proof.btcp_version.major < 1 {
            return ProofVerificationStatus::VersionIncompatible;
        }

        // All structural checks passed — but the signatures remain
        // UNVERIFIED (no crypto in this crate). On-chain/quorum
        // verification is required before releasing funds.
        ProofVerificationStatus::UnverifiedSignatures
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Generate mock validator signatures FOR TESTS ONLY.
    ///
    /// TEST FIXTURE FABRICATION — deliberately NOT production code:
    /// the "signatures" are deterministic 65-byte filler (not real
    /// secp256k1 ECDSA values) and would never pass real cryptographic
    /// verification. This function lives inside `#[cfg(test)]` so it can
    /// never be compiled into a production path. Uses deterministic
    /// SHA3-based pseudo-random generation.
    fn generate_mock_signatures_for_tests(num: u32) -> (Vec<WeightedSignature>, Vec<f64>, f64) {
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
                // 65 bytes: secp256k1 ECDSA r[32] || s[32] || v[1] shape
                signature: vec![i as u8; 65],
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

    #[test]
    fn test_build_proof() {
        let builder = BTCPProofBuilder::with_block(18000000);

        let (sigs, weights, hhi) = generate_mock_signatures_for_tests(5);

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
        let (sigs, weights, hhi) = generate_mock_signatures_for_tests(5);

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

        // Structural checks pass — but signatures remain UNVERIFIED
        // (this is the best outcome this crate can produce).
        let status = builder.verify_proof(&proof, 18001000);
        assert_eq!(status, ProofVerificationStatus::UnverifiedSignatures);
        assert!(status.passed_structural_checks());

        // Invalid: coherence below threshold
        proof.consensus_proof.coherence_score = 0.40;
        assert_eq!(
            builder.verify_proof(&proof, 18001000),
            ProofVerificationStatus::CoherenceBelowThreshold
        );
    }

    #[test]
    fn test_verify_proof_expiry() {
        let builder = BTCPProofBuilder::with_block(18000000);
        let (sigs, weights, hhi) = generate_mock_signatures_for_tests(5);

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
        assert_eq!(
            builder.verify_proof(&proof, 18001000),
            ProofVerificationStatus::UnverifiedSignatures
        );

        // Last block of the validity window: still valid (window is inclusive)
        assert_eq!(
            builder.verify_proof(&proof, anchor_block + MAX_PROOF_VALIDITY_BLOCKS),
            ProofVerificationStatus::UnverifiedSignatures
        );

        // One block past the window: expired (reorg / staleness risk)
        assert_eq!(
            builder.verify_proof(&proof, anchor_block + MAX_PROOF_VALIDITY_BLOCKS + 1),
            ProofVerificationStatus::Expired
        );

        // Far past the window: expired
        assert_eq!(
            builder.verify_proof(&proof, anchor_block + 500_000),
            ProofVerificationStatus::Expired
        );
    }

    #[test]
    fn test_hhi_calculation() {
        let (_, _, hhi_5) = generate_mock_signatures_for_tests(5);
        let (_, _, hhi_100) = generate_mock_signatures_for_tests(100);

        // More validators = lower HHI = more distributed
        assert!(hhi_100 < hhi_5);
        println!("HHI (5 validators): {:.4}", hhi_5);
        println!("HHI (100 validators): {:.6}", hhi_100);
    }

    #[test]
    fn test_verify_proof_rejects_duplicate_signers() {
        // Padding the signer count with a duplicate validator_id is not
        // consensus — the same validator signing twice counts once.
        let builder = BTCPProofBuilder::with_block(18000000);
        let (mut sigs, weights, hhi) = generate_mock_signatures_for_tests(5);

        // Duplicate the first validator's ID under the second signature
        sigs[1].validator_id = sigs[0].validator_id;

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

        assert_eq!(
            builder.verify_proof(&proof, 18001000),
            ProofVerificationStatus::DuplicateSigner
        );
    }

    #[test]
    fn test_verify_proof_rejects_malformed_signatures() {
        // Signatures must be well-formed 65-byte values (r||s||v);
        // a 64-byte blob is malformed. (Length check only — still NOT
        // a cryptographic verification.)
        let builder = BTCPProofBuilder::with_block(18000000);
        let (mut sigs, weights, hhi) = generate_mock_signatures_for_tests(5);

        // Truncate one signature to 64 bytes
        sigs[0].signature.truncate(64);

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

        assert_eq!(
            builder.verify_proof(&proof, 18001000),
            ProofVerificationStatus::MalformedSignature
        );
    }

    #[test]
    fn test_verify_proof_rejects_insufficient_signers() {
        let builder = BTCPProofBuilder::with_block(18000000);
        let (sigs, weights, hhi) = generate_mock_signatures_for_tests(2);

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

        assert_eq!(
            builder.verify_proof(&proof, 18001000),
            ProofVerificationStatus::InsufficientSigners
        );
    }
}
