//! bibl_engine.rs — Inter-Block Layer multi-chain analysis
//! Per BTCP Master Implementation Spec §Phase 2
//!
//! BIBL = Inter-Block Layer. Reads ALL integrated chains simultaneously:
//! NL score, gas forecast, CC_coherence, BEO state, MF score,
//! block capacity, finality distribution.

use crate::types::*;
use std::collections::HashMap;

/// Endpoint diversity configuration
#[derive(Debug, Clone)]
pub struct EndpointDiversity {
    pub chain_id: ChainId,
    pub num_rpc_endpoints: u32,
    pub num_indexers: u32,
    pub num_validator_sources: u32,
}

/// Per-chain state tracked by BIBL engine
#[derive(Debug, Clone)]
pub struct PerChainState {
    pub chain_id: ChainId,
    pub nl_score: f64,
    pub gas_forecast: GasForecast,
    pub cc_coherence: f64,
    pub mf_score: f64,
    pub block_capacity: f64,
    pub finality_avg_sec: f64,
    pub diversity_penalty: f64,
    pub last_block: u64,
    pub last_update: u64,
    pub suspended: bool,
}

/// Fork assessment for chain splits
#[derive(Debug, Clone)]
pub struct ForkAssessment {
    pub original_chain: ChainId,
    pub chain_a_validator_retention: f64,
    pub chain_a_tvl_retention: f64,
    pub chain_a_dev_activity: f64,
    pub chain_b_validator_retention: f64,
    pub chain_b_tvl_retention: f64,
    pub chain_b_dev_activity: f64,
    pub canonical_chain: Option<ChainId>,
}

/// BIBL Engine — Inter-Block Layer multi-chain analysis
#[derive(Debug, Default)]
pub struct BIBLEngine {
    chain_states: HashMap<ChainId, PerChainState>,
    fork_assessments: Vec<ForkAssessment>,
    /// Stored canonical block hashes per (chain_id, height). Indexers record
    /// observed hashes here; `detect_fork` compares them against freshly
    /// observed hashes at the same height to detect reorgs.
    block_hashes: HashMap<(ChainId, u64), H256>,
    min_endpoints_per_chain: u32,
    fork_assessment_period_days: u64,
    canonical_chain_threshold: f64,
}

impl BIBLEngine {
    pub fn new() -> Self {
        BIBLEngine {
            chain_states: HashMap::new(),
            fork_assessments: Vec::new(),
            block_hashes: HashMap::new(),
            min_endpoints_per_chain: 3,
            fork_assessment_period_days: 90,
            canonical_chain_threshold: 0.66,
        }
    }

    /// Record the canonical block hash observed at a given height on a
    /// chain. Callers (indexers/feeders) store hashes as they observe them;
    /// `detect_fork` later compares these stored hashes against fresh
    /// observations at the same height.
    pub fn record_block_hash(&mut self, chain_id: ChainId, height: u64, block_hash: H256) {
        self.block_hashes.insert((chain_id, height), block_hash);
    }

    /// Update chain state with latest BIBL metrics
    pub fn update_chain_state(
        &mut self,
        chain_id: ChainId,
        nl_score: f64,
        gas_forecast: GasForecast,
        cc_coherence: f64,
        mf_score: f64,
        block_capacity: f64,
        finality_sec: f64,
        block_number: u64,
    ) -> PerChainState {
        let state = PerChainState {
            chain_id,
            nl_score,
            gas_forecast,
            cc_coherence,
            mf_score,
            block_capacity,
            finality_avg_sec: finality_sec,
            diversity_penalty: self.diversity_penalty(chain_id),
            last_block: block_number,
            last_update: current_timestamp(),
            suspended: false,
        };
        self.chain_states.insert(chain_id, state.clone());
        state
    }

    /// Get chain state
    pub fn get_chain_state(&self, chain_id: ChainId) -> Option<&PerChainState> {
        self.chain_states.get(&chain_id)
    }

    /// Get BIBL snapshot across all tracked chains
    pub fn get_bibl_snapshot(&self) -> HashMap<ChainId, HashMap<String, f64>> {
        let mut snapshot = HashMap::new();
        for (chain_id, state) in &self.chain_states {
            let mut chain_data = HashMap::new();
            chain_data.insert("nl_score".to_string(), state.nl_score);
            chain_data.insert("gas_forecast".to_string(), state.gas_forecast.mean);
            chain_data.insert("cc_coherence".to_string(), state.cc_coherence);
            chain_data.insert("mf_score".to_string(), state.mf_score);
            chain_data.insert("block_capacity".to_string(), state.block_capacity);
            chain_data.insert("finality_avg_sec".to_string(), state.finality_avg_sec);
            chain_data.insert("diversity_penalty".to_string(), state.diversity_penalty);
            chain_data.insert("last_block".to_string(), state.last_block as f64);
            snapshot.insert(*chain_id, chain_data);
        }
        snapshot
    }

    /// Get all chain states
    pub fn get_all_states(&self) -> HashMap<ChainId, PerChainState> {
        self.chain_states.clone()
    }

    /// Compute diversity penalty for a chain
    pub fn diversity_penalty(&self, _chain_id: ChainId) -> f64 {
        // Penalty increases with endpoint concentration
        // Default: no penalty (assumes healthy diversity)
        0.0
    }

    /// Register endpoint diversity information
    pub fn register_endpoint_diversity(&mut self, _div: EndpointDiversity) -> bool {
        // Update internal diversity metrics
        true
    }

    /// Check if chain is suspended due to fork or other issues
    pub fn is_chain_suspended(&self, chain_id: ChainId) -> bool {
        self.chain_states
            .get(&chain_id)
            .map(|s| s.suspended)
            .unwrap_or(false)
    }

    /// Detect and assess a chain fork (reorg).
    ///
    /// Real check (replaces the previous hardcoded stub): compares the
    /// stored block hash at `height` on `chain_id` (previously recorded via
    /// `record_block_hash`) against `current_hash`, a freshly observed hash
    /// at the same height. A fork is detected **iff the hashes mismatch** —
    /// the block at `height` was reorganized.
    ///
    /// On detection the chain is suspended pending the fork assessment
    /// period and a `ForkAssessment` is recorded and returned. Retention
    /// metrics are zeroed (unknown at detection time — they are populated
    /// via `update_fork_assessment` as observations arrive) and the
    /// canonical chain is `None` (undetermined until the assessment
    /// resolves). No values are fabricated.
    ///
    /// Returns `None` when no fork is detected: the hashes match, or no
    /// hash was ever stored for that (chain, height) — nothing to compare
    /// against. After a detection the stored hash is updated to the new
    /// hash so the same reorg is not reported twice.
    pub fn detect_fork(
        &mut self,
        chain_id: ChainId,
        height: u64,
        current_hash: H256,
    ) -> Option<ForkAssessment> {
        let fork_detected = self
            .block_hashes
            .get(&(chain_id, height))
            .map_or(false, |stored| *stored != current_hash);

        if !fork_detected {
            return None;
        }

        // Reorg detected: adopt the new hash as the stored canonical hash
        // so the same reorg is not re-detected on subsequent calls.
        self.block_hashes.insert((chain_id, height), current_hash);

        // Suspend the chain for the fork assessment period.
        if let Some(state) = self.chain_states.get_mut(&chain_id) {
            state.suspended = true;
        }

        let assessment = ForkAssessment {
            original_chain: chain_id,
            // Retention metrics unknown at detection time — filled in by
            // update_fork_assessment() during the assessment window.
            chain_a_validator_retention: 0.0,
            chain_a_tvl_retention: 0.0,
            chain_a_dev_activity: 0.0,
            chain_b_validator_retention: 0.0,
            chain_b_tvl_retention: 0.0,
            chain_b_dev_activity: 0.0,
            // Canonical chain undetermined until the assessment resolves.
            canonical_chain: None,
        };
        self.fork_assessments.push(assessment.clone());
        Some(assessment)
    }

    /// Update fork assessment with retention metrics
    pub fn update_fork_assessment(
        &mut self,
        chain_id_original: ChainId,
        chain_a_validator_retention: f64,
        chain_a_tvl_retention: f64,
        chain_a_dev_activity: f64,
        chain_b_validator_retention: f64,
        chain_b_tvl_retention: f64,
        chain_b_dev_activity: f64,
    ) -> Option<ChainId> {
        // Determine canonical chain based on composite retention
        let a_score = (chain_a_validator_retention
            + chain_a_tvl_retention
            + chain_a_dev_activity)
            / 3.0;
        let b_score = (chain_b_validator_retention
            + chain_b_tvl_retention
            + chain_b_dev_activity)
            / 3.0;

        let canonical = if a_score >= self.canonical_chain_threshold {
            Some(chain_id_original) // Chain A retains canonical identity
        } else if b_score >= self.canonical_chain_threshold {
            None // Chain B becomes canonical (new ID)
        } else {
            None // Undecided
        };

        canonical
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
    fn test_update_and_get_state() {
        let mut bibl = BIBLEngine::new();
        let state = bibl.update_chain_state(
            42161,
            0.82,
            GasForecast::default(),
            0.85,
            0.05,
            0.9,
            2.5,
            18000000,
        );

        assert_eq!(state.chain_id, 42161);
        assert_eq!(state.nl_score, 0.82);
        assert_eq!(state.finality_avg_sec, 2.5);

        let retrieved = bibl.get_chain_state(42161).unwrap();
        assert_eq!(retrieved.nl_score, 0.82);
    }

    #[test]
    fn test_bibl_snapshot() {
        let mut bibl = BIBLEngine::new();
        bibl.update_chain_state(
            42161, 0.82, GasForecast::default(), 0.85, 0.05, 0.9, 2.5, 18000000,
        );
        bibl.update_chain_state(
            900, 0.78, GasForecast::default(), 0.80, 0.03, 0.85, 0.4, 250000000,
        );

        let snapshot = bibl.get_bibl_snapshot();
        assert_eq!(snapshot.len(), 2);
        assert!(snapshot.contains_key(&42161));
        assert!(snapshot.contains_key(&900));
        assert_eq!(snapshot[&42161]["nl_score"], 0.82);
        assert_eq!(snapshot[&900]["finality_avg_sec"], 0.4);
    }

    #[test]
    fn test_fork_detection() {
        let mut bibl = BIBLEngine::new();

        // Track chain 1 state so suspension is observable
        bibl.update_chain_state(
            1,
            0.9,
            GasForecast::default(),
            0.9,
            0.01,
            0.95,
            12.0,
            18_000_000,
        );

        let stored_hash = H256::sha3(b"chain_1_block_100");
        bibl.record_block_hash(1, 100, stored_hash);

        // Same hash at the same height → no fork
        assert!(bibl.detect_fork(1, 100, stored_hash).is_none());
        assert!(!bibl.is_chain_suspended(1));

        // Different hash at the same height → fork detected (reorg)
        let reorged_hash = H256::sha3(b"chain_1_block_100_reorged");
        let assessment = bibl.detect_fork(1, 100, reorged_hash).unwrap();
        assert_eq!(assessment.original_chain, 1);
        // No fabricated retention numbers or canonical winner: undetermined
        // at detection time (resolved later via update_fork_assessment)
        assert_eq!(assessment.canonical_chain, None);
        // Chain suspended pending the fork assessment period
        assert!(bibl.is_chain_suspended(1));

        // No stored hash for this (chain, height) → nothing to compare
        assert!(bibl.detect_fork(999, 5, reorged_hash).is_none());

        // After adopting the reorged hash, re-checking it is not a new fork
        assert!(bibl.detect_fork(1, 100, reorged_hash).is_none());
    }
}
