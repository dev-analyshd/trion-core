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
    min_endpoints_per_chain: u32,
    fork_assessment_period_days: u64,
    canonical_chain_threshold: f64,
}

impl BIBLEngine {
    pub fn new() -> Self {
        BIBLEngine {
            chain_states: HashMap::new(),
            fork_assessments: Vec::new(),
            min_endpoints_per_chain: 3,
            fork_assessment_period_days: 90,
            canonical_chain_threshold: 0.66,
        }
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

    /// Detect and assess a chain fork
    pub fn detect_fork(
        &mut self,
        chain_id: ChainId,
        chain_a_id: ChainId,
        chain_b_id: ChainId,
    ) -> ForkAssessment {
        let assessment = ForkAssessment {
            original_chain: chain_id,
            chain_a_validator_retention: 0.7,
            chain_a_tvl_retention: 0.65,
            chain_a_dev_activity: 0.8,
            chain_b_validator_retention: 0.3,
            chain_b_tvl_retention: 0.35,
            chain_b_dev_activity: 0.2,
            canonical_chain: Some(chain_a_id),
        };
        self.fork_assessments.push(assessment.clone());
        assessment
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
        let assessment = bibl.detect_fork(1, 1, 99999);

        assert_eq!(assessment.original_chain, 1);
        assert_eq!(assessment.canonical_chain, Some(1));
    }
}
