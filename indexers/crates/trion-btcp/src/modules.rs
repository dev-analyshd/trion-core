//! Modules 2.4-2.18: Proof Builder, BITP, Netting, Intent Aggregator,
//! OOA Anchor, Shadow Observer, State Capsule, Failure Classifier,
//! Genesis Commitment, BLO Scheduler, State Channel, Finality Normalizer,
//! Version Handler, Validator Fee Calculator, Sybil Resistance

use std::collections::HashMap;
use sha3::{Digest, Sha3_256};

// ── Module 2.4: BTCP Proof Builder ─────────────────────────────────────────

pub struct BtcpProofBuilder;

impl BtcpProofBuilder {
    /// A3: Certification validity windows by value tier
    pub fn compute_cert_expiry(value_usd: f64) -> u64 {
        if value_usd < 1_000.0 { 10_000 }
        else if value_usd < 100_000.0 { 50_000 }
        else if value_usd < 10_000_000.0 { 200_000 }
        else { 500_000 }
    }
}

// ── Module 2.5: BITP Matcher ───────────────────────────────────────────────

pub struct BitpMatcher;

impl BitpMatcher {
    /// Find complement: B wants what A has, has what A wants, different chain
    pub fn find_complement<'a>(a_asset_in: &[u8; 32], a_asset_out: &[u8; 32],
                               candidates: &'a [([u8; 32], [u8; 32], u64)]) -> Option<u64> {
        for (b_in, b_out, chain) in candidates {
            if b_in == a_asset_out && b_out == a_asset_in {
                return Some(*chain);
            }
        }
        None
    }
}

// ── Module 2.6: Netting Engine ─────────────────────────────────────────────

pub struct NettingEngine;

impl NettingEngine {
    pub const NETTING_GAS_COST: f64 = 0.05; // $0.05
}

// ── Module 2.7: Intent Aggregator ──────────────────────────────────────────

pub struct IntentAggregator;

impl IntentAggregator {
    pub const MIN_INTENTS: usize = 3;

    pub fn compute_per_user_gas(total_gas: f64, num_users: usize) -> f64 {
        if num_users == 0 { total_gas } else { total_gas / num_users as f64 }
    }
}

// ── Module 2.8: OOA Anchor ─────────────────────────────────────────────────

pub struct OoaAnchor;

impl OoaAnchor {
    pub const OOA_PENALTY_FACTOR: f64 = 1.5;

    pub fn compute_ooa_confidence(observation_depth: u64, integrated_conf: f64) -> f64 {
        if observation_depth == 0 { return 0.0; }
        let factor = 1.0 - (-(observation_depth as f64) / 1000.0).exp();
        integrated_conf * factor
    }
}

// ── Module 2.9: Shadow Observer ────────────────────────────────────────────

pub struct ShadowObserver;

impl ShadowObserver {
    pub fn reconstruct_shadow_bh(sources: &[(Vec<u8>, f64)]) -> ([u8; 32], f64) {
        if sources.is_empty() { return ([0; 32], 0.0); }
        let mut hasher = Sha3_256::new();
        let total_weight: f64 = sources.iter().map(|(_, w)| *w).sum();
        for (data, weight) in sources.iter() {
            hasher.update(data);
            hasher.update(&weight.to_le_bytes());
        }
        let result = hasher.finalize();
        let mut bh = [0u8; 32];
        bh.copy_from_slice(&result);
        (bh, (total_weight / 10.0).min(1.0))
    }
}

// ── Module 2.10: State Capsule ─────────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct StateCapsule {
    pub price_at_anchor: f64,
    pub balance_x: f64,
    pub block_hash_a: [u8; 32],
    pub staleness_ci_95: f64,
}

// ── Module 2.11: Failure Classifier ────────────────────────────────────────

pub struct FailureClassifier;

impl FailureClassifier {
    pub fn classify(external_indicators: usize, entity_indicators: usize,
                    prior_ambiguous: usize) -> &'static str {
        if entity_indicators >= 2 { return "ENTITY_CAUSE"; }
        if external_indicators >= 2 { return "EXTERNAL_CAUSE"; }
        if external_indicators >= 1 && entity_indicators == 0 { return "EXTERNAL_CAUSE"; }
        if entity_indicators >= 1 && external_indicators == 0 { return "ENTITY_CAUSE"; }
        if prior_ambiguous >= 2 { return "ENTITY_CAUSE"; }
        "EXTERNAL_CAUSE" // benefit of doubt
    }
}

// ── Module 2.12: Genesis Commitment ────────────────────────────────────────

pub struct GenesisCommitmentProcessor;

impl GenesisCommitmentProcessor {
    pub const GENESIS_PATHWAYS: &'static [&'static str] = &["stake", "signature", "social_proof"];
}

// ── Module 2.13: BLO Scheduler ─────────────────────────────────────────────

pub struct BloScheduler;

impl BloScheduler {
    pub fn find_optimal_window(circadian_low: &[u32], nl_peak: &[u32], mev_valley: &[u32]) -> Vec<u32> {
        let c: std::collections::HashSet<_> = circadian_low.iter().cloned().collect();
        let n: std::collections::HashSet<_> = nl_peak.iter().cloned().collect();
        let m: std::collections::HashSet<_> = mev_valley.iter().cloned().collect();
        c.intersection(&n).cloned().collect::<std::collections::HashSet<_>>().intersection(&m).cloned().collect()
    }
}

// ── Module 2.14: Behavioral State Channel ──────────────────────────────────

pub struct BehavioralStateChannel {
    interaction_count: u64,
    state: ChannelState,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ChannelState { Open, Closed }

impl BehavioralStateChannel {
    pub fn new() -> Self { Self { interaction_count: 0, state: ChannelState::Open } }
    pub fn operate(&mut self) -> bool {
        if self.state != ChannelState::Open { return false; }
        self.interaction_count += 1; true
    }
    pub fn close(&mut self) -> bool {
        if self.state != ChannelState::Open { return false; }
        self.state = ChannelState::Closed; true
    }
    pub fn interaction_count(&self) -> u64 { self.interaction_count }
}

// ── Module 2.15: Finality Normalizer ───────────────────────────────────────

pub struct FinalityNormalizer;

impl FinalityNormalizer {
    /// max(A, B), not sum. ETH→Base: max(12s, 2s) = 12s (not 14s)
    pub fn effective_latency(a: f64, b: f64) -> f64 { a.max(b) }
}

// ── Module 2.16: Version Handler ───────────────────────────────────────────

pub struct VersionHandler;

impl VersionHandler {
    pub fn parse_semver(v: &str) -> (u32, u32, u32) {
        let parts: Vec<u32> = v.split('.').map(|s| s.parse().unwrap_or(0)).collect();
        (parts[0], parts.get(1).copied().unwrap_or(0), parts.get(2).copied().unwrap_or(0))
    }
    pub fn is_compatible(verifier: &str, min: &str) -> bool {
        Self::parse_semver(verifier) >= Self::parse_semver(min)
    }
    pub fn is_breaking_change(old: &str, new: &str) -> bool {
        Self::parse_semver(new).0 > Self::parse_semver(old).0
    }
}

// ── Module 2.17: Validator Fee Calculator ──────────────────────────────────

pub struct ValidatorFeeCalculator;

impl ValidatorFeeCalculator {
    pub const BASE_RATE: f64 = 100.0;
    pub const BTCP_ROUTE_SPLIT_ANCHOR: f64 = 0.60;
    pub const BTCP_ROUTE_SPLIT_EXEC: f64 = 0.40;

    /// rarity_factor = total_validators / validators_covering
    pub fn compute_rarity_factor(validators_covering: usize, total: usize) -> f64 {
        if validators_covering == 0 { f64::MAX } else { total as f64 / validators_covering as f64 }
    }

    pub fn compute_btcp_route_reward(total: f64, is_anchor: bool) -> f64 {
        if is_anchor { total * Self::BTCP_ROUTE_SPLIT_ANCHOR }
        else { total * Self::BTCP_ROUTE_SPLIT_EXEC }
    }
}

// ── Module 2.18: Sybil Resistance ──────────────────────────────────────────

pub struct SybilResistance;

impl SybilResistance {
    pub const BASE_SPONSOR_CAP: f64 = 10.0;
    pub const MIN_SPACING_BASE_DAYS: f64 = 7.0;
    pub const SIMILARITY_THRESHOLD: f64 = 0.85;

    /// Layer 1: max_sponsored = floor(log2(D/D_min) × base_cap)
    pub fn layer1_max_sponsored(d: f64, d_min: f64) -> u64 {
        if d <= d_min || d_min <= 0.0 { return 0; }
        ((d / d_min).log2() * Self::BASE_SPONSOR_CAP).floor() as u64
    }

    /// Layer 2: scrutiny = 1 + n × 0.2
    pub fn layer2_scrutiny_multiplier(n: usize) -> f64 { 1.0 + n as f64 * 0.2 }

    /// Layer 3: cosine_similarity > 0.85 → sockpuppet
    pub fn layer3_is_sockpuppet(cos_sim: f64) -> bool { cos_sim > Self::SIMILARITY_THRESHOLD }

    /// Layer 4: MIN_SPACING(n) = BASE × n²
    pub fn layer4_min_spacing_days(n: usize) -> f64 { Self::MIN_SPACING_BASE_DAYS * (n as f64).powi(2) }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_proof_builder_cert_expiry() {
        assert_eq!(BtcpProofBuilder::compute_cert_expiry(500.0), 10_000);
        assert_eq!(BtcpProofBuilder::compute_cert_expiry(50_000.0), 50_000);
        assert_eq!(BtcpProofBuilder::compute_cert_expiry(5_000_000.0), 200_000);
        assert_eq!(BtcpProofBuilder::compute_cert_expiry(50_000_000.0), 500_000);
    }

    #[test]
    fn test_intent_aggregator_100x() {
        assert!((IntentAggregator::compute_per_user_gas(0.80, 100) - 0.008).abs() < 1e-9);
    }

    #[test]
    fn test_finality_max_not_sum() {
        assert!((FinalityNormalizer::effective_latency(12.0, 2.0) - 12.0).abs() < 1e-9);
    }

    #[test]
    fn test_version_handler() {
        assert!(VersionHandler::is_compatible("2.1.0", "2.0.0"));
        assert!(!VersionHandler::is_compatible("1.5.0", "2.0.0"));
        assert!(VersionHandler::is_breaking_change("1.0.0", "2.0.0"));
        assert!(!VersionHandler::is_breaking_change("2.0.0", "2.1.0"));
    }

    #[test]
    fn test_validator_fee_rarity() {
        assert!((ValidatorFeeCalculator::compute_rarity_factor(5, 100) - 20.0).abs() < 1e-9);
        assert!((ValidatorFeeCalculator::compute_btcp_route_reward(100.0, true) - 60.0).abs() < 1e-9);
        assert!((ValidatorFeeCalculator::compute_btcp_route_reward(100.0, false) - 40.0).abs() < 1e-9);
    }

    #[test]
    fn test_sybil_resistance() {
        assert!(SybilResistance::layer1_max_sponsored(10000.0, 100.0) > 0);
        assert!((SybilResistance::layer2_scrutiny_multiplier(5) - 2.0).abs() < 1e-9);
        assert!(SybilResistance::layer3_is_sockpuppet(0.90));
        assert!(!SybilResistance::layer3_is_sockpuppet(0.80));
        assert!((SybilResistance::layer4_min_spacing_days(3) - 63.0).abs() < 1e-9);
    }

    #[test]
    fn test_state_channel_50x() {
        let mut ch = BehavioralStateChannel::new();
        for _ in 0..50 { assert!(ch.operate()); }
        assert_eq!(ch.interaction_count(), 50);
        assert!(ch.close());
    }

    #[test]
    fn test_failure_classifier() {
        assert_eq!(FailureClassifier::classify(2, 0, 0), "EXTERNAL_CAUSE");
        assert_eq!(FailureClassifier::classify(0, 2, 0), "ENTITY_CAUSE");
        assert_eq!(FailureClassifier::classify(0, 0, 0), "EXTERNAL_CAUSE");
        assert_eq!(FailureClassifier::classify(0, 0, 2), "ENTITY_CAUSE");
    }

    #[test]
    fn test_ooa_confidence_grows() {
        let low = OoaAnchor::compute_ooa_confidence(100, 0.85);
        let high = OoaAnchor::compute_ooa_confidence(1000, 0.85);
        assert!(high > low);
    }
}
