//! Module 2.3: BIBL Engine — Three-Tier Computational Architecture
//! D3 Resolution: <200ms total BIBL latency
//! A1 Resolution: Multi-Path Independent Observation (3+ RPC endpoints)
//! Gap 12: Fork Classification Protocol (30-day, 67% threshold)

use std::collections::{HashMap, HashSet};
use std::time::{SystemTime, UNIX_EPOCH};

const FORK_ASSESSMENT_PERIOD_DAYS: u64 = 30;
const MIN_ENDPOINTS_PER_CHAIN: usize = 3;
const CANONICAL_CHAIN_THRESHOLD: f64 = 0.67;

#[derive(Debug, Clone, Default)]
pub struct PerChainState {
    pub nl_score: f64,
    pub gas_forecast: f64,
    pub gas_ci_95_lower: f64,
    pub gas_ci_95_upper: f64,
    pub cc_coherence: f64,
    pub mf_score: f64,
    pub block_capacity: f64,
    pub finality_avg_sec: f64,
    pub last_block: u64,
    pub last_update: f64,
}

#[derive(Debug, Clone)]
pub struct EndpointDiversity {
    pub chain_id: u64,
    pub regions: Vec<String>,
    pub asns: Vec<String>,
    pub cloud_providers: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct ForkAssessment {
    pub chain_id_original: u64,
    pub chain_a_id: u64,
    pub chain_b_id: u64,
    pub detection_time: f64,
    pub assessment_end: f64,
    pub canonical_chain: Option<u64>,
    pub resolved: bool,
}

fn now() -> f64 {
    SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs_f64()
}

pub struct BiblEngine {
    chain_states: HashMap<u64, PerChainState>,
    endpoint_diversity: HashMap<u64, EndpointDiversity>,
    fork_assessments: Vec<ForkAssessment>,
    suspended_chains: HashSet<u64>,
}

impl BiblEngine {
    pub fn new() -> Self {
        Self {
            chain_states: HashMap::new(),
            endpoint_diversity: HashMap::new(),
            fork_assessments: Vec::new(),
            suspended_chains: HashSet::new(),
        }
    }

    pub fn update_chain_state(&mut self, chain_id: u64, nl: f64, gas: f64,
                              gas_ci: (f64, f64), cc: f64, mf: f64,
                              capacity: f64, finality: f64, block: u64) {
        let state = self.chain_states.entry(chain_id).or_default();
        state.nl_score = nl;
        state.gas_forecast = gas;
        state.gas_ci_95_lower = gas_ci.0;
        state.gas_ci_95_upper = gas_ci.1;
        state.cc_coherence = cc;
        state.mf_score = mf;
        state.block_capacity = capacity;
        state.finality_avg_sec = finality;
        state.last_block = block;
        state.last_update = now();
    }

    pub fn get_chain_state(&self, chain_id: u64) -> Option<&PerChainState> {
        self.chain_states.get(&chain_id)
    }

    /// A1: diversity_penalty — 1.0 = no penalty, <1.0 = penalty
    pub fn diversity_penalty(&self, chain_id: u64) -> f64 {
        match self.endpoint_diversity.get(&chain_id) {
            Some(d) => {
                let regions = d.regions.iter().collect::<std::collections::HashSet<_>>().len();
                let asns = d.asns.iter().collect::<std::collections::HashSet<_>>().len();
                let clouds = d.cloud_providers.iter().collect::<std::collections::HashSet<_>>().len();
                if regions >= MIN_ENDPOINTS_PER_CHAIN && asns >= MIN_ENDPOINTS_PER_CHAIN && clouds >= MIN_ENDPOINTS_PER_CHAIN {
                    1.0
                } else {
                    let score = regions as f64 / MIN_ENDPOINTS_PER_CHAIN as f64 * 0.34
                             + asns as f64 / MIN_ENDPOINTS_PER_CHAIN as f64 * 0.33
                             + clouds as f64 / MIN_ENDPOINTS_PER_CHAIN as f64 * 0.33;
                    score.min(1.0)
                }
            }
            None => 0.5,
        }
    }

    pub fn register_endpoint_diversity(&mut self, div: EndpointDiversity) -> bool {
        let regions = div.regions.iter().collect::<std::collections::HashSet<_>>().len();
        let asns = div.asns.iter().collect::<std::collections::HashSet<_>>().len();
        let clouds = div.cloud_providers.iter().collect::<std::collections::HashSet<_>>().len();
        if regions < MIN_ENDPOINTS_PER_CHAIN || asns < MIN_ENDPOINTS_PER_CHAIN || clouds < MIN_ENDPOINTS_PER_CHAIN {
            return false;
        }
        self.endpoint_diversity.insert(div.chain_id, div);
        true
    }

    /// Gap 12: Detect fork, suspend chain for 30 days
    pub fn detect_fork(&mut self, chain_id: u64, chain_a: u64, chain_b: u64) {
        self.fork_assessments.push(ForkAssessment {
            chain_id_original: chain_id, chain_a_id: chain_a, chain_b_id: chain_b,
            detection_time: now(),
            assessment_end: now() + FORK_ASSESSMENT_PERIOD_DAYS as f64 * 86400.0,
            canonical_chain: None, resolved: false,
        });
        self.suspended_chains.insert(chain_id);
    }

    /// Gap 12: Resolve fork — canonical chain must retain ≥67%
    pub fn update_fork_assessment(&mut self, original: u64,
                                  a_val: f64, a_tvl: f64, a_dev: f64,
                                  b_val: f64, b_tvl: f64, b_dev: f64) -> Option<u64> {
        for fa in self.fork_assessments.iter_mut() {
            if fa.chain_id_original != original || fa.resolved { continue; }
            let score_a = 0.50 * a_val + 0.30 * a_tvl + 0.20 * a_dev;
            let score_b = 0.50 * b_val + 0.30 * b_tvl + 0.20 * b_dev;
            if score_a >= CANONICAL_CHAIN_THRESHOLD && score_a > score_b {
                fa.canonical_chain = Some(fa.chain_a_id);
                fa.resolved = true;
                self.suspended_chains.remove(&original);
                return fa.canonical_chain;
            } else if score_b >= CANONICAL_CHAIN_THRESHOLD && score_b > score_a {
                fa.canonical_chain = Some(fa.chain_b_id);
                fa.resolved = true;
                self.suspended_chains.remove(&original);
                return fa.canonical_chain;
            }
            return None;
        }
        None
    }

    pub fn is_chain_suspended(&self, chain_id: u64) -> bool {
        self.suspended_chains.contains(&chain_id)
    }

    /// Get BIBL snapshot excluding suspended chains
    pub fn get_bibl_snapshot(&self) -> HashMap<u64, PerChainState> {
        self.chain_states.iter()
            .filter(|(k, _)| !self.suspended_chains.contains(k))
            .map(|(k, v)| (*k, v.clone()))
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_update_chain_state() {
        let mut bibl = BiblEngine::new();
        bibl.update_chain_state(1, 0.85, 31.0, (28.0, 34.0), 0.90, 0.02, 0.80, 12.0, 18000000);
        assert!((bibl.get_chain_state(1).unwrap().nl_score - 0.85).abs() < 1e-9);
    }

    #[test]
    fn test_diversity_no_penalty() {
        let mut bibl = BiblEngine::new();
        bibl.register_endpoint_diversity(EndpointDiversity {
            chain_id: 1,
            regions: vec!["us".into(), "eu".into(), "ap".into()],
            asns: vec!["AS1".into(), "AS2".into(), "AS3".into()],
            cloud_providers: vec!["aws".into(), "gcp".into(), "azure".into()],
        });
        assert!((bibl.diversity_penalty(1) - 1.0).abs() < 1e-9);
    }

    #[test]
    fn test_fork_detection_and_resolution() {
        let mut bibl = BiblEngine::new();
        bibl.detect_fork(1, 1, 1001);
        assert!(bibl.is_chain_suspended(1));
        let canonical = bibl.update_fork_assessment(1, 0.80, 0.85, 0.90, 0.20, 0.15, 0.10);
        assert_eq!(canonical, Some(1));
        assert!(!bibl.is_chain_suspended(1));
    }
}
