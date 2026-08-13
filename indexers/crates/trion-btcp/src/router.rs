//! Module 2.1: BTCP Router — Core routing engine
//!
//! BTCP_score_final = [w_nl×NL + w_gas×normalize_gas + w_fin×finality
//!                     + w_coh×CC + w_beo×BEO] × (1 - MF)
//!
//! K1 Resolution weights: NL=0.25, gas=0.20, finality=0.20, CC=0.15, BEO=0.20

use std::collections::HashMap;

/// Route types per BTCP spec
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum RouteType {
    SingleChain,
    Split,
    Netting,
    Parallel,
    MultiHop,
    Deferred,
    Bitp,
}

/// Tier-1 cached state — updated every block per chain
#[derive(Debug, Clone, Default)]
pub struct BiblState {
    pub nl_scores: HashMap<u64, f64>,
    pub gas_forecasts: HashMap<u64, f64>,
    pub gas_reference: f64,
    pub cc_coherence: HashMap<u64, f64>,
    pub mf_scores: HashMap<u64, f64>,
    pub finality_dist: HashMap<u64, f64>,
}

impl BiblState {
    pub fn new() -> Self {
        Self {
            gas_reference: 31.0, // ETH 99th percentile
            ..Default::default()
        }
    }
}

/// Candidate route for an intent
#[derive(Debug, Clone)]
pub struct Route {
    pub route_id: String,
    pub entity_id: [u8; 32],
    pub route_type: RouteType,
    pub anchor_chain: u64,
    pub execution_chain: u64,
    pub gas_total: f64,
    pub finality_confidence: f64,
    pub beo_continuity: f64,
    pub cc_coherence: f64,
    pub intent_value: f64,
}

// K1 Resolution weights
pub const W_NL: f64 = 0.25;
pub const W_GAS: f64 = 0.20;
pub const W_FIN: f64 = 0.20;
pub const W_COH: f64 = 0.15;
pub const W_BEO: f64 = 0.20;

// Minimum viable route thresholds
pub const MIN_BTCP_SCORE: f64 = 0.10;
pub const MIN_NL: f64 = 0.05;
pub const MIN_FINALITY: f64 = 0.80;
pub const MIN_VALIDATORS_PER_ROUTE: usize = 3;

/// Gas normalization: (1 - g/g_ref) clamped to [0, 1]
pub fn normalize_gas(g: f64, state: &BiblState) -> f64 {
    let g_ref = state.gas_reference;
    if g_ref <= 0.0 {
        return 0.5;
    }
    (1.0 - (g / g_ref)).max(0.0)
}

/// BTCP_score_final = [w_nl×NL + w_gas×gas_norm + w_fin×finality + w_coh×CC + w_beo×BEO] × (1 - MF)
pub fn btcp_score_final(route: &Route, state: &BiblState) -> f64 {
    let nl = state.nl_scores.get(&route.execution_chain).copied().unwrap_or(0.0);
    let gas_norm = normalize_gas(route.gas_total, state);
    let fin = route.finality_confidence;
    let cc = route.cc_coherence;
    let beo = route.beo_continuity;
    let mf = state.mf_scores.get(&route.execution_chain).copied().unwrap_or(0.0);

    let score = W_NL * nl + W_GAS * gas_norm + W_FIN * fin + W_COH * cc + W_BEO * beo;
    score * (1.0 - mf)
}

/// Check if route meets minimum viability thresholds
pub fn route_is_valid(route: &Route, state: &BiblState, validator_count: usize) -> bool {
    if validator_count < MIN_VALIDATORS_PER_ROUTE {
        return false;
    }
    let nl = state.nl_scores.get(&route.execution_chain).copied().unwrap_or(0.0);
    if nl <= MIN_NL {
        return false;
    }
    if route.finality_confidence <= MIN_FINALITY {
        return false;
    }
    if btcp_score_final(route, state) <= MIN_BTCP_SCORE {
        return false;
    }
    true
}

/// Tier-2: Score all candidate routes and select the optimal one
pub fn select_optimal_route(
    intent_value: f64,
    entity_id: [u8; 32],
    state: &BiblState,
    candidate_chains: &[u64],
    validator_counts: &HashMap<u64, usize>,
) -> Option<Route> {
    let route_types = [
        RouteType::SingleChain, RouteType::Split, RouteType::Netting,
        RouteType::Parallel, RouteType::MultiHop, RouteType::Deferred,
    ];

    let mut candidates: Vec<Route> = Vec::new();

    for &chain in candidate_chains {
        let nl = state.nl_scores.get(&chain).copied().unwrap_or(0.0);
        let gas = state.gas_forecasts.get(&chain).copied().unwrap_or(state.gas_reference);
        let fin = 1.0 - (state.finality_dist.get(&chain).copied().unwrap_or(12.0) / 60.0).min(1.0);
        let cc = state.cc_coherence.get(&chain).copied().unwrap_or(0.5);
        let beo = 0.8;
        let vcount = *validator_counts.get(&chain).unwrap_or(&10);

        for &rt in &route_types {
            let route = Route {
                route_id: format!("route_{}_{:?}", chain, rt),
                entity_id,
                route_type: rt,
                anchor_chain: candidate_chains.first().copied().unwrap_or(chain),
                execution_chain: chain,
                gas_total: gas,
                finality_confidence: fin,
                beo_continuity: beo,
                cc_coherence: cc,
                intent_value,
            };
            if route_is_valid(&route, state, vcount) {
                candidates.push(route);
            }
        }
    }

    candidates.into_iter().max_by(|a, b| {
        btcp_score_final(a, state).partial_cmp(&btcp_score_final(b, state)).unwrap()
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_normalize_gas() {
        let state = BiblState { gas_reference: 31.0, ..Default::default() };
        assert!((normalize_gas(31.0, &state) - 0.0).abs() < 1e-9);
        assert!((normalize_gas(0.0, &state) - 1.0).abs() < 1e-9);
        assert!((normalize_gas(15.5, &state) - 0.5).abs() < 1e-9);
    }

    #[test]
    fn test_btcp_score_in_range() {
        let mut state = BiblState::new();
        state.nl_scores.insert(1, 0.85);
        state.gas_forecasts.insert(1, 10.0);
        state.cc_coherence.insert(1, 0.90);
        state.mf_scores.insert(1, 0.02);
        state.finality_dist.insert(1, 12.0);

        let route = Route {
            route_id: "test".into(), entity_id: [1; 32],
            route_type: RouteType::SingleChain, anchor_chain: 1, execution_chain: 1,
            gas_total: 10.0, finality_confidence: 0.95, beo_continuity: 0.8,
            cc_coherence: 0.9, intent_value: 1000.0,
        };
        let score = btcp_score_final(&route, &state);
        assert!(score >= 0.0 && score <= 1.0);
    }

    #[test]
    fn test_route_validity() {
        let mut state = BiblState::new();
        state.nl_scores.insert(1, 0.85);
        state.gas_forecasts.insert(1, 10.0);
        state.cc_coherence.insert(1, 0.90);
        state.finality_dist.insert(1, 12.0);

        let valid = Route {
            route_id: "v".into(), entity_id: [1; 32],
            route_type: RouteType::SingleChain, anchor_chain: 1, execution_chain: 1,
            gas_total: 10.0, finality_confidence: 0.95, beo_continuity: 0.8,
            cc_coherence: 0.9, intent_value: 1000.0,
        };
        assert!(route_is_valid(&valid, &state, 10));

        let invalid = Route { finality_confidence: 0.50, ..valid.clone() };
        assert!(!route_is_valid(&invalid, &state, 10));
    }

    #[test]
    fn test_select_optimal_route() {
        let mut state = BiblState::new();
        state.nl_scores.insert(1, 0.85);
        state.nl_scores.insert(137, 0.90);
        state.gas_forecasts.insert(1, 31.0);
        state.gas_forecasts.insert(137, 0.50);
        state.cc_coherence.insert(1, 0.90);
        state.cc_coherence.insert(137, 0.92);
        state.mf_scores.insert(1, 0.02);
        state.mf_scores.insert(137, 0.01);
        state.finality_dist.insert(1, 12.0);
        state.finality_dist.insert(137, 2.0);

        let mut vc = HashMap::new();
        vc.insert(1, 50);
        vc.insert(137, 40);

        let route = select_optimal_route(10000.0, [1; 32], &state, &[1, 137], &vc);
        assert!(route.is_some());
        let r = route.unwrap();
        assert!(btcp_score_final(&r, &state) > MIN_BTCP_SCORE);
    }
}
