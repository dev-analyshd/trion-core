//! btcp_failure_classifier.rs — EXTERNAL_CAUSE vs ENTITY_CAUSE classification
//! Per BTCP Master Implementation Spec §Phase 2
//!
//! EXTERNAL_CAUSE: chain outage, NL collapse, reorg, MF spike → BEO impact = ZERO
//! ENTITY_CAUSE: invalid proof, collateral withdrawal, conflicting intents → BEO penalty

use crate::types::*;
use crate::SAFE_CONFIRMATIONS;
use std::collections::HashMap;

/// Failure classifier — distinguishes system failures from entity failures
///
/// BEO impact rules:
/// - EXTERNAL_CAUSE: BEO impact = ZERO, intent preserved in Akashic Index
/// - ENTITY_CAUSE: warning → D(t) growth -10% for 30 days → conf reduced
/// - AMBIGUOUS: first two treated as External; third within 90 days → Entity
#[derive(Debug, Default)]
pub struct FailureClassifier {
    ambiguous_counts: HashMap<BEOId, u32>,
    ambiguous_timestamps: HashMap<BEOId, Vec<u64>>,
}

impl FailureClassifier {
    pub fn new() -> Self {
        FailureClassifier {
            ambiguous_counts: HashMap::new(),
            ambiguous_timestamps: HashMap::new(),
        }
    }

    /// Classify a route failure
    pub fn classify(
        &mut self,
        failure: &RouteFailure,
        chain_outage: bool,
        nl_collapsed: bool,
        reorg_depth_exceeded: bool,
        mf_spike: bool,
        invalid_proof: bool,
        collateral_withdrawn: bool,
        conflicting_intents: bool,
        systematic_timeout: bool,
        prior_ambiguous_count: u32,
    ) -> FailureCause {
        // External cause indicators
        if chain_outage || nl_collapsed || reorg_depth_exceeded || mf_spike {
            return FailureCause::External;
        }

        // Entity cause indicators
        if invalid_proof || collateral_withdrawn || conflicting_intents || systematic_timeout {
            return FailureCause::Entity;
        }

        // Ambiguous — apply three-strikes rule
        self.record_ambiguous(failure.entity_id, failure.timestamp);
        let count = self.ambiguous_counts.get(&failure.entity_id).copied().unwrap_or(0);

        // First two treated as External; third within 90 days → Entity
        if count >= 3 && self.within_90_days(failure.entity_id, failure.timestamp) {
            FailureCause::Entity
        } else {
            FailureCause::Ambiguous
        }
    }

    /// Convenience: classify with default parameters
    pub fn classify_failure(
        &mut self,
        failure: &RouteFailure,
    ) -> FailureCause {
        self.classify(
            failure,
            false, // chain_outage
            false, // nl_collapsed
            false, // reorg_depth_exceeded
            false, // mf_spike
            false, // invalid_proof
            false, // collateral_withdrawn
            false, // conflicting_intents
            false, // systematic_timeout
            0,     // prior_ambiguous_count
        )
    }

    /// Check if reorg depth exceeds safe confirmations
    pub fn reorg_depth_exceeded(&self, reorg_depth: u64) -> bool {
        reorg_depth > SAFE_CONFIRMATIONS
    }

    /// Check if NL dropped below critical threshold
    pub fn nl_dropped_below_critical(&self, nl_score: f64) -> bool {
        nl_score < 0.10
    }

    /// Record an ambiguous failure
    fn record_ambiguous(&mut self, entity_id: BEOId, timestamp: u64) {
        *self.ambiguous_counts.entry(entity_id).or_insert(0) += 1;
        self.ambiguous_timestamps
            .entry(entity_id)
            .or_default()
            .push(timestamp);
    }

    /// Check if ambiguous failures clustered within 90 days
    fn within_90_days(&self, entity_id: BEOId, current_ts: u64) -> bool {
        if let Some(timestamps) = self.ambiguous_timestamps.get(&entity_id) {
            let ninety_days = 90 * 24 * 60 * 60;
            timestamps
                .iter()
                .any(|&ts| current_ts.saturating_sub(ts) <= ninety_days)
        } else {
            false
        }
    }

    /// Get ambiguous count for an entity
    pub fn ambiguous_count(&self, entity_id: &BEOId) -> u32 {
        self.ambiguous_counts.get(entity_id).copied().unwrap_or(0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn create_failure(entity_id: BEOId) -> RouteFailure {
        RouteFailure {
            route_id: H256::sha3(b"route"),
            anchor_chain: 42161,
            execution_chain: 900,
            entity_id,
            failure_type: "unknown".to_string(),
            timestamp: 1787141851,
        }
    }

    #[test]
    fn test_external_cause_chain_outage() {
        let mut classifier = FailureClassifier::new();
        let entity = H256::sha3(b"entity");
        let failure = create_failure(entity);

        let cause = classifier.classify(
            &failure, true, false, false, false, false, false, false, false, 0,
        );
        assert_eq!(cause, FailureCause::External);
    }

    #[test]
    fn test_external_cause_nl_collapse() {
        let mut classifier = FailureClassifier::new();
        let entity = H256::sha3(b"entity");
        let failure = create_failure(entity);

        let cause = classifier.classify(
            &failure, false, true, false, false, false, false, false, false, 0,
        );
        assert_eq!(cause, FailureCause::External);
    }

    #[test]
    fn test_entity_cause_invalid_proof() {
        let mut classifier = FailureClassifier::new();
        let entity = H256::sha3(b"entity");
        let failure = create_failure(entity);

        let cause = classifier.classify(
            &failure, false, false, false, false, true, false, false, false, 0,
        );
        assert_eq!(cause, FailureCause::Entity);
    }

    #[test]
    fn test_ambiguous_then_entity() {
        let mut classifier = FailureClassifier::new();
        let entity = H256::sha3(b"entity");

        // First ambiguous failure
        let f1 = create_failure(entity);
        let c1 = classifier.classify_failure(&f1);
        assert_eq!(c1, FailureCause::Ambiguous);
        assert_eq!(classifier.ambiguous_count(&entity), 1);

        // Second ambiguous
        let f2 = create_failure(entity);
        let c2 = classifier.classify_failure(&f2);
        assert_eq!(c2, FailureCause::Ambiguous);
        assert_eq!(classifier.ambiguous_count(&entity), 2);

        // Third ambiguous within 90 days → Entity
        let f3 = create_failure(entity);
        let c3 = classifier.classify_failure(&f3);
        assert_eq!(c3, FailureCause::Entity);
    }

    #[test]
    fn test_reorg_depth_check() {
        let classifier = FailureClassifier::new();
        assert!(!classifier.reorg_depth_exceeded(10));
        assert!(classifier.reorg_depth_exceeded(100));
    }

    #[test]
    fn test_nl_critical_check() {
        let classifier = FailureClassifier::new();
        assert!(classifier.nl_dropped_below_critical(0.05));
        assert!(!classifier.nl_dropped_below_critical(0.50));
    }
}
