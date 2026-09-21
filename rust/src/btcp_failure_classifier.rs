//! btcp_failure_classifier.rs — EXTERNAL_CAUSE vs ENTITY_CAUSE classification
//! Per BTCP Master Implementation Spec §11 Fix 2 (spec L1940-1984)
//!
//! EXTERNAL_CAUSE: chain outage, NL collapse, reorg, MF spike → BEO impact = ZERO
//! ENTITY_CAUSE: invalid proof, collateral withdrawal, conflicting intents,
//!   systematic timeout → BEHAVIORAL_ANOMALY (D(t) growth −10% for 30 days).
//! AMBIGUOUS: first two treated as External; third within 90 days → Entity.
//!
//! Spec §11 Fix 2 "Entity choice: WAIT (auto-retry) | CANCEL (escrow
//! returns) | REROUTE (immediate)" — the entity that owns the failed
//! route picks how to proceed. The classifier maps each `FailureCause`
//! to a *recommended* `EntityChoice` so the relayer has a sane default
//! while still allowing the entity to override:
//!
//!   External  → Reroute  (chain-level fault; pick a different path now)
//!   Entity    → Cancel   (entity at fault; escrow returns)
//!   Ambiguous → Wait     (benefit of the doubt; auto-retry)

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
        // External cause indicators — any single one is sufficient (spec §11 Fix 2):
        //   chain_outage || nl_collapsed || reorg_depth_exceeded || mf_spike
        let _ = prior_ambiguous_count; // tracked inside self (stateful three-strike)
        if chain_outage || nl_collapsed || reorg_depth_exceeded || mf_spike {
            return FailureCause::External;
        }

        // Entity cause indicators — any single one is sufficient (spec §11 Fix 2):
        //   invalid_proof || collateral_withdrawn || conflicting_intents || systematic_timeout
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

    /// Spec §11 Fix 2 — "Entity choice: WAIT (auto-retry) | CANCEL (escrow
    /// returns) | REROUTE (immediate)".
    ///
    /// Maps a `FailureCause` to the recommended entity action:
    /// - `External`  → `Reroute` (chain-level fault; pick a different path now)
    /// - `Entity`    → `Cancel`  (entity at fault; escrow returns to entity)
    /// - `Ambiguous` → `Wait`    (benefit of the doubt; auto-retry)
    ///
    /// This is the *recommended* default — the owning entity may always
    /// override (e.g., choose `Reroute` for an Entity cause if it has a
    /// known good alternative).
    pub fn recommend_entity_choice(cause: FailureCause) -> EntityChoice {
        match cause {
            FailureCause::External => EntityChoice::Reroute,
            FailureCause::Entity => EntityChoice::Cancel,
            FailureCause::Ambiguous => EntityChoice::Wait,
        }
    }

    /// Spec §11 Fix 2 — `classify_and_recommend_failure(route_data) -> FailureClassification`.
    ///
    /// Returns the full classification (cause + recommended entity choice).
    /// `route_data` is the bag of boolean failure indicators observed for
    /// this route. The classifier is stateful across calls for the same
    /// entity (three-strike Ambiguous → Entity rule).
    pub fn classify_and_recommend_failure(
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
    ) -> FailureClassification {
        let cause = self.classify(
            failure,
            chain_outage,
            nl_collapsed,
            reorg_depth_exceeded,
            mf_spike,
            invalid_proof,
            collateral_withdrawn,
            conflicting_intents,
            systematic_timeout,
            prior_ambiguous_count,
        );
        let recommended_choice = Self::recommend_entity_choice(cause);
        FailureClassification::new(cause, recommended_choice)
    }

    /// Convenience: classify + recommend with default parameters (no
    /// observed indicators — exercises the Ambiguous three-strike path).
    pub fn classify_and_recommend(
        &mut self,
        failure: &RouteFailure,
    ) -> FailureClassification {
        let cause = self.classify_failure(failure);
        let recommended_choice = Self::recommend_entity_choice(cause);
        FailureClassification::new(cause, recommended_choice)
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

    // ── Spec §11 Fix 2 — WAIT/CANCEL/REROUTE entity choice ──────────────────

    #[test]
    fn test_recommend_entity_choice_external_reroute() {
        // External cause → recommend Reroute (chain-level fault; try a
        // different path immediately).
        assert_eq!(
            FailureClassifier::recommend_entity_choice(FailureCause::External),
            EntityChoice::Reroute
        );
    }

    #[test]
    fn test_recommend_entity_choice_entity_cancel() {
        // Entity cause → recommend Cancel (entity at fault; escrow returns).
        assert_eq!(
            FailureClassifier::recommend_entity_choice(FailureCause::Entity),
            EntityChoice::Cancel
        );
    }

    #[test]
    fn test_recommend_entity_choice_ambiguous_wait() {
        // Ambiguous cause → recommend Wait (auto-retry, benefit of the doubt).
        assert_eq!(
            FailureClassifier::recommend_entity_choice(FailureCause::Ambiguous),
            EntityChoice::Wait
        );
    }

    #[test]
    fn test_classify_and_recommend_external() {
        let mut classifier = FailureClassifier::new();
        let entity = H256::sha3(b"entity_ext");
        let failure = create_failure(entity);

        let result = classifier.classify_and_recommend_failure(
            &failure, true, false, false, false, false, false, false, false, 0,
        );
        assert_eq!(result.cause, FailureCause::External);
        assert_eq!(result.recommended_choice, EntityChoice::Reroute);
    }

    #[test]
    fn test_classify_and_recommend_entity() {
        let mut classifier = FailureClassifier::new();
        let entity = H256::sha3(b"entity_ent");
        let failure = create_failure(entity);

        let result = classifier.classify_and_recommend_failure(
            &failure, false, false, false, false, true, false, false, false, 0,
        );
        assert_eq!(result.cause, FailureCause::Entity);
        assert_eq!(result.recommended_choice, EntityChoice::Cancel);
    }

    #[test]
    fn test_classify_and_recommend_ambiguous_first_is_wait() {
        let mut classifier = FailureClassifier::new();
        let entity = H256::sha3(b"entity_amb");
        let f1 = create_failure(entity);

        // First Ambiguous occurrence → recommended Wait (auto-retry).
        let r1 = classifier.classify_and_recommend(&f1);
        assert_eq!(r1.cause, FailureCause::Ambiguous);
        assert_eq!(r1.recommended_choice, EntityChoice::Wait);
    }

    #[test]
    fn test_classify_and_recommend_ambiguous_third_becomes_entity_cancel() {
        let mut classifier = FailureClassifier::new();
        let entity = H256::sha3(b"entity_amb3");

        // Three ambiguous failures within the 90-day window → third becomes
        // Entity → recommended Cancel.
        let f1 = create_failure(entity);
        let f2 = create_failure(entity);
        let f3 = create_failure(entity);
        let _ = classifier.classify_and_recommend(&f1);
        let _ = classifier.classify_and_recommend(&f2);
        let r3 = classifier.classify_and_recommend(&f3);
        assert_eq!(r3.cause, FailureCause::Entity);
        assert_eq!(r3.recommended_choice, EntityChoice::Cancel);
    }

    #[test]
    fn test_entity_choice_as_str_matches_spec_tags() {
        // Spec §11 Fix 2 mandates the exact string tags WAIT / CANCEL / REROUTE.
        assert_eq!(EntityChoice::Wait.as_str(), "WAIT");
        assert_eq!(EntityChoice::Cancel.as_str(), "CANCEL");
        assert_eq!(EntityChoice::Reroute.as_str(), "REROUTE");
        // Display impl delegates to as_str.
        assert_eq!(format!("{}", EntityChoice::Wait), "WAIT");
        assert_eq!(format!("{}", EntityChoice::Cancel), "CANCEL");
        assert_eq!(format!("{}", EntityChoice::Reroute), "REROUTE");
    }
}
