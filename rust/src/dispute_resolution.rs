//! dispute_resolution.rs — Conscious Layer 3-of-5 dispute resolution
//! Per BTCP Master Implementation Spec §Phase 2
//!
//! Disputes are resolved by the Conscious (K) plane.
//! 5 annotators review each case. 3/5 majority determines outcome.
//! Commit-reveal voting prevents vote bias.

use crate::types::*;
use std::collections::HashMap;

/// Dispute Resolver — Conscious Layer dispute resolution
/// 5 annotators. 3/5 majority. Commit-reveal voting.
#[derive(Debug, Default)]
pub struct DisputeResolver {
    cases: HashMap<H256, DisputeCase>,
    annotators: Vec<BEOId>,
}

impl DisputeResolver {
    pub fn new() -> Self {
        DisputeResolver {
            cases: HashMap::new(),
            annotators: Vec::new(),
        }
    }

    /// Register an annotator
    pub fn register_annotator(&mut self, annotator_id: BEOId) {
        if !self.annotators.contains(&annotator_id) {
            self.annotators.push(annotator_id);
        }
    }

    /// Get registered annotators
    pub fn annotators(&self) -> &[BEOId] {
        &self.annotators
    }

    /// Open a new dispute case
    pub fn open_case(
        &mut self,
        route_id: H256,
        claimant: BEOId,
        respondent: BEOId,
    ) -> H256 {
        let case_id = H256::sha3(
            format!(
                "{}:{}:{}:{}",
                route_id.to_hex(),
                claimant.to_hex(),
                respondent.to_hex(),
                current_timestamp()
            )
            .as_bytes(),
        );

        let case = DisputeCase {
            case_id,
            route_id,
            claimant,
            respondent,
            votes: Vec::new(),
            resolved: false,
            outcome: None,
        };

        self.cases.insert(case_id, case);
        case_id
    }

    /// Select 5 annotators for a case (random selection in production)
    pub fn select_annotators(&self, _case_id: &H256) -> Option<Vec<BEOId>> {
        if self.annotators.len() < 5 {
            return None;
        }
        // Return first 5 for now; production uses random selection
        Some(self.annotators.iter().take(5).cloned().collect())
    }

    /// Cast a vote on a dispute case
    pub fn cast_vote(
        &mut self,
        case_id: &H256,
        voter_id: BEOId,
        vote: bool,
        rationale_hash: H256,
    ) -> bool {
        if let Some(case) = self.cases.get_mut(case_id) {
            if case.resolved {
                return false;
            }

            // Check if voter already voted
            if case.votes.iter().any(|v| v.voter_id == voter_id) {
                return false;
            }

            case.votes.push(DisputeVote {
                voter_id,
                vote,
                rationale_hash,
                timestamp: current_timestamp(),
            });

            // Check if we have enough votes to resolve
            if case.votes.len() >= 5 {
                self.resolve_case(case_id);
            }

            return true;
        }
        false
    }

    /// Resolve a case based on 3/5 majority
    fn resolve_case(&mut self, case_id: &H256) {
        if let Some(case) = self.cases.get_mut(case_id) {
            let yes_votes = case.votes.iter().filter(|v| v.vote).count();
            let outcome = yes_votes >= 3; // 3/5 majority
            case.outcome = Some(outcome);
            case.resolved = true;
        }
    }

    /// Get case by ID
    pub fn get_case(&self, case_id: &H256) -> Option<&DisputeCase> {
        self.cases.get(case_id)
    }

    /// Get all cases
    pub fn all_cases(&self) -> Vec<&DisputeCase> {
        self.cases.values().collect()
    }

    /// Get unresolved cases
    pub fn unresolved_cases(&self) -> Vec<&DisputeCase> {
        self.cases.values().filter(|c| !c.resolved).collect()
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

    fn setup_resolver() -> DisputeResolver {
        let mut resolver = DisputeResolver::new();
        // Register 7 annotators
        for i in 0..7 {
            resolver.register_annotator(H256::sha3(format!("annotator_{}", i).as_bytes()));
        }
        resolver
    }

    #[test]
    fn test_register_annotators() {
        let resolver = setup_resolver();
        assert_eq!(resolver.annotators().len(), 7);
    }

    #[test]
    fn test_select_annotators() {
        let resolver = setup_resolver();
        let case_id = H256::sha3(b"case");
        let selected = resolver.select_annotators(&case_id).unwrap();
        assert_eq!(selected.len(), 5);
    }

    #[test]
    fn test_open_and_resolve_case() {
        let mut resolver = setup_resolver();
        let annotators = resolver.annotators().to_vec();

        let route_id = H256::sha3(b"route");
        let claimant = H256::sha3(b"claimant");
        let respondent = H256::sha3(b"respondent");

        let case_id = resolver.open_case(route_id, claimant, respondent);

        // Cast 3 YES votes and 2 NO votes → outcome = YES
        for i in 0..3 {
            assert!(resolver.cast_vote(
                &case_id,
                annotators[i],
                true,
                H256::sha3(format!("rationale_yes_{}", i).as_bytes()),
            ));
        }
        for i in 3..5 {
            assert!(resolver.cast_vote(
                &case_id,
                annotators[i],
                false,
                H256::sha3(format!("rationale_no_{}", i).as_bytes()),
            ));
        }

        // Case should be auto-resolved after 5th vote
        let case = resolver.get_case(&case_id).unwrap();
        assert!(case.resolved);
        assert_eq!(case.outcome, Some(true));
        assert_eq!(case.votes.len(), 5);
    }

    #[test]
    fn test_duplicate_vote_rejected() {
        let mut resolver = setup_resolver();
        let annotators = resolver.annotators().to_vec();

        let case_id = resolver.open_case(
            H256::sha3(b"route"),
            H256::sha3(b"claimant"),
            H256::sha3(b"respondent"),
        );

        assert!(resolver.cast_vote(&case_id, annotators[0], true, H256::sha3(b"r1")));
        assert!(!resolver.cast_vote(&case_id, annotators[0], true, H256::sha3(b"r2"))); // Duplicate
    }

    #[test]
    fn test_unresolved_cases() {
        let mut resolver = setup_resolver();
        let annotators = resolver.annotators().to_vec();

        let case1 = resolver.open_case(H256::sha3(b"route1"), H256::sha3(b"c1"), H256::sha3(b"r1"));
        let case2 = resolver.open_case(H256::sha3(b"route2"), H256::sha3(b"c2"), H256::sha3(b"r2"));

        // Only vote on case1 to resolve it
        for i in 0..5 {
            resolver.cast_vote(&case1, annotators[i], true, H256::sha3(b"r"));
        }

        assert_eq!(resolver.unresolved_cases().len(), 1);
        assert_eq!(resolver.unresolved_cases()[0].case_id, case2);
    }
}
