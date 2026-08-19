//! btcp_router.rs — Core routing, BTCP_score computation, route selection
//! Per BTCP Master Implementation Spec §Phase 2

use crate::types::*;
use crate::{GAS_99TH_PERCENTILE, MIN_BTCP_SCORE};
use std::collections::HashMap;

/// BTCP Router — Step 1: Intent registration + BIBL analysis
/// Step 2: BTCP_score computation + route type selection
#[derive(Debug, Default)]
pub struct BTCPRouter {
    routes: HashMap<H256, Route>,
    intents: HashMap<H256, Intent>,
}

impl BTCPRouter {
    pub fn new() -> Self {
        BTCPRouter {
            routes: HashMap::new(),
            intents: HashMap::new(),
        }
    }

    /// Register an intent and compute its hash
    pub fn register_intent(&mut self, mut intent: Intent) -> H256 {
        let intent_hash = intent.hash();
        intent.intent_id = intent_hash;
        self.intents.insert(intent_hash, intent);
        intent_hash
    }

    /// Step 2: Compute BTCP score for a route given BIBL analysis
    pub fn btcp_score(&self, route: &Route, analysis: &BIBLAnalysis) -> f64 {
        let normalize_gas =
            (1.0 - analysis.gas_forecast.mean / GAS_99TH_PERCENTILE).max(0.0);

        (0.25 * analysis.nl_score
            + 0.20 * normalize_gas
            + 0.20 * analysis.finality_dist.ci95
            + 0.15 * analysis.cc_coherence
            + 0.20 * route.beo_continuity)
            * (1.0 - analysis.mf_score)
    }

    /// Select optimal route type based on multi-chain BIBL analysis
    pub fn select_route_type(
        &self,
        intent: &Intent,
        analyses: &[BIBLAnalysis],
        netting_available: Option<BEOId>,
    ) -> RouteType {
        // Check netting first (counterparty found = zero movement)
        if let Some(counterparty) = netting_available {
            return RouteType::Netting { counterparty };
        }

        // Find best chain
        let dest_analysis = analyses
            .iter()
            .find(|a| a.chain_id == intent.dest_chain);

        let source_analysis = analyses
            .iter()
            .find(|a| a.chain_id == intent.source_chain);

        // If destination is superior across all metrics, SingleChain
        if let Some(dest) = dest_analysis {
            let is_superior = source_analysis.map_or(true, |src| {
                dest.nl_score >= src.nl_score
                    && dest.gas_forecast.mean <= src.gas_forecast.mean
                    && dest.finality_dist.ci95 >= src.finality_dist.ci95
            });

            if is_superior && dest.nl_score > 0.7 {
                return RouteType::SingleChain;
            }
        }

        // Default: Split route (anchor on source, execute on dest)
        RouteType::Split {
            anchor: intent.source_chain,
            exec: intent.dest_chain,
        }
    }

    /// Create a complete route from intent and analyses
    pub fn create_route(
        &mut self,
        intent: Intent,
        analyses: &[BIBLAnalysis],
        beo_continuity: f64,
        netting_available: Option<BEOId>,
    ) -> Route {
        let intent_hash = self.register_intent(intent.clone());

        let route_type = self.select_route_type(&intent, analyses, netting_available);

        let mut route = Route {
            route_id: H256::sha3(
                format!("{}:{}", intent_hash.to_hex(), intent.nonce).as_bytes(),
            ),
            intent,
            route_type,
            beo_continuity,
            btcp_score: 0.0,
            status: RouteStatus::IntentCreated,
            created_at: current_timestamp(),
        };

        // Compute BTCP score using destination analysis if available
        if let Some(dest_analysis) = analyses
            .iter()
            .find(|a| a.chain_id == route.intent.dest_chain)
        {
            route.btcp_score = self.btcp_score(&route, dest_analysis);
        }

        self.routes.insert(route.route_id, route.clone());
        route
    }

    /// Check if route passes minimum score threshold
    pub fn route_is_valid(&self, route: &Route) -> bool {
        route.btcp_score >= MIN_BTCP_SCORE
    }

    /// Get a route by ID
    pub fn get_route(&self, route_id: &H256) -> Option<&Route> {
        self.routes.get(route_id)
    }

    /// Update route status
    pub fn update_status(&mut self, route_id: &H256, status: RouteStatus) {
        if let Some(route) = self.routes.get_mut(route_id) {
            route.status = status;
        }
    }

    /// Get all routes
    pub fn all_routes(&self) -> Vec<&Route> {
        self.routes.values().collect()
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

    fn create_test_intent() -> Intent {
        Intent {
            intent_id: H256::zero(),
            entity_id: H256::sha3(b"test_entity"),
            source_address: "0x1F98431c8aD98523631AE4a59f267346ea31F984".to_string(),
            dest_address: "Vote111111111111111111111111111111111111111".to_string(),
            source_chain: 42161, // Arbitrum
            dest_chain: 900,     // Solana
            asset_in: "ETH".to_string(),
            asset_out: "SOL".to_string(),
            amount_in: 1_500_000_000_000_000_000u128, // 1.5 ETH
            intent_type: "SWAP".to_string(),
            deadline: 1787141851,
            nonce: 42,
            constraints: IntentConstraints::default(),
        }
    }

    fn create_test_analysis(chain_id: ChainId, nl: f64) -> BIBLAnalysis {
        BIBLAnalysis {
            chain_id,
            nl_score: nl,
            gas_forecast: GasForecast {
                mean: 50.0,
                ci_95_low: 40.0,
                ci_95_high: 60.0,
            },
            cc_coherence: 0.85,
            beo_state: BEOState::default(),
            mf_score: 0.05,
            block_capacity: 0.9,
            finality_dist: FinalityDistribution::default(),
        }
    }

    #[test]
    fn test_register_intent() {
        let mut router = BTCPRouter::new();
        let intent = create_test_intent();
        let hash = router.register_intent(intent.clone());
        assert_ne!(hash, H256::zero());
        assert!(router.intents.contains_key(&hash));
    }

    #[test]
    fn test_btcp_score_computation() {
        let router = BTCPRouter::new();
        let intent = create_test_intent();
        let analysis = create_test_analysis(900, 0.82);

        let route = Route {
            route_id: H256::zero(),
            intent,
            route_type: RouteType::SingleChain,
            beo_continuity: 0.95,
            btcp_score: 0.0,
            status: RouteStatus::Pending,
            created_at: 0,
        };

        let score = router.btcp_score(&route, &analysis);
        assert!(score > 0.0);
        assert!(score <= 1.0);
        println!("BTCP Score: {:.4}", score);
    }

    #[test]
    fn test_create_route_split() {
        let mut router = BTCPRouter::new();
        let intent = create_test_intent();
        let analyses = vec![
            create_test_analysis(42161, 0.75),
            create_test_analysis(900, 0.65),
        ];

        let route = router.create_route(intent, &analyses, 0.95, None);

        assert!(matches!(route.route_type, RouteType::Split { .. }));
        assert!(router.route_is_valid(&route));
        assert_eq!(route.status, RouteStatus::IntentCreated);
    }

    #[test]
    fn test_create_route_netting() {
        let mut router = BTCPRouter::new();
        let intent = create_test_intent();
        let analyses = vec![create_test_analysis(900, 0.82)];
        let counterparty = H256::sha3(b"counterparty");

        let route = router.create_route(intent, &analyses, 0.95, Some(counterparty));

        assert!(matches!(
            route.route_type,
            RouteType::Netting { counterparty: cp } if cp == counterparty
        ));
    }

    #[test]
    fn test_route_status_update() {
        let mut router = BTCPRouter::new();
        let intent = create_test_intent();
        let analyses = vec![create_test_analysis(900, 0.82)];
        let route = router.create_route(intent, &analyses, 0.95, None);

        router.update_status(&route.route_id, RouteStatus::ProofsGenerated);

        let updated = router.get_route(&route.route_id).unwrap();
        assert_eq!(updated.status, RouteStatus::ProofsGenerated);
    }
}
