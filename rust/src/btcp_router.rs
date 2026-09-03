//! btcp_router.rs — Core routing, BTCP_score computation, route selection
//! Per BTCP Master Implementation Spec §Phase 2

use crate::types::*;
use crate::{GAS_99TH_PERCENTILE, MIN_BTCP_SCORE};
use std::collections::HashMap;

/// Router configuration — explicit, overridable tunables for the BTCP gate.
///
/// Mirrors the tunables of the canonical Python reference
/// (`core/btcp/router.py`): the Python implementation hardcodes
/// `MIN_BTCP_SCORE = 0.10` and a rolling 30-day gas P99
/// (`BIBLState.gas_reference`); this struct makes both explicit and
/// overridable per router instance instead of burying them as magic
/// crate constants.
#[derive(Debug, Clone)]
pub struct RouterConfig {
    /// Minimum BTCP score for a route to be considered valid.
    /// Default: [`crate::MIN_BTCP_SCORE`] (0.10 — unified with the Python
    /// canonical gate; this crate previously diverged at 0.50).
    pub min_btcp_score: f64,
    /// 99th-percentile gas cost (USD) used by `normalize_gas`.
    /// Default: [`crate::GAS_99TH_PERCENTILE`] — a documented PLACEHOLDER
    /// requiring chain-specific calibration (the Python reference uses a
    /// rolling 30-day P99, ~31 USD for Ethereum).
    pub gas_p99: f64,
}

impl Default for RouterConfig {
    fn default() -> Self {
        RouterConfig {
            min_btcp_score: MIN_BTCP_SCORE,
            gas_p99: GAS_99TH_PERCENTILE,
        }
    }
}

/// Gas normalization: `(1 - g/g_ref)` clamped to [0, 1].
///
/// Mirrors `normalize_gas` in the Python reference (`core/btcp/router.py`):
/// a non-positive `g_ref` yields the neutral 0.5 instead of dividing by
/// zero.
pub fn normalize_gas(gas_cost: f64, gas_p99: f64) -> f64 {
    if gas_p99 <= 0.0 {
        return 0.5;
    }
    (1.0 - gas_cost / gas_p99).max(0.0)
}

/// ── Gap G: BTCP_ROUTE_OE_FACTOR (Observer-Effect correction) ─────────────
/// BTCP routing improves NL scores → circular reinforcement. The
/// observer-effect correction discounts routing-layer scores that TRION
/// itself caused. `oe_factor` is clamped to [0, 1] and applied
/// multiplicatively so self-caused liquidity improvements score lower
/// than organic ones. Mirrors `apply_oe_correction` in the Python
/// reference (`core/btcp/router.py`) exactly.
pub fn apply_oe_correction(btcp_score: f64, oe_factor: f64) -> f64 {
    let oe = oe_factor.clamp(0.0, 1.0);
    btcp_score * (1.0 - oe)
}

/// BTCP Router — Step 1: Intent registration + BIBL analysis
/// Step 2: BTCP_score computation + route type selection
#[derive(Debug, Default)]
pub struct BTCPRouter {
    routes: HashMap<H256, Route>,
    intents: HashMap<H256, Intent>,
    /// Gap E: Behavioral Balance Reservation — entity → reserved value.
    /// Concurrent routes must not double-spend the same source assets:
    /// intents reserve against the entity's available behavioral balance
    /// in real time (port of `core/btcp/router.py` `_balance_reservations`).
    balance_reservations: HashMap<BEOId, f64>,
    config: RouterConfig,
}

/// Route-selection thresholds (BTCP Master Spec §4.2, §5.1, §5.5, §5.8)
pub mod route_policy {
    /// NL below this on the destination ⇒ pair treated as illiquid ⇒ BITP
    /// (matches the LIQUIDITY_HEALTH alert threshold, whitepaper L7.1)
    pub const NL_ILLIQUID: f64 = 0.30;
    /// NL above this qualifies a chain as a Parallel split leg
    pub const NL_PARALLEL_LEG: f64 = 0.60;
    /// Amount (in asset base units, 18-dec normalized) above which PARALLEL
    /// routing is considered — 1e21 = 1,000 whole tokens (institutional size;
    /// the spec's PARALLEL case is "large intent split across multiple chains")
    pub const PARALLEL_AMOUNT_THRESHOLD: u128 = 1_000_000_000_000_000_000_000;
    /// Minimum seconds until deadline for DEFERRED (BRT scheduling) to apply
    pub const DEFER_MIN_LEAD_SECS: u64 = 3_600;
    /// NL lift an intermediate chain needs over BOTH endpoints to justify MULTIHOP
    pub const MULTIHOP_NL_LIFT: f64 = 0.10;
}

impl BTCPRouter {
    pub fn new() -> Self {
        BTCPRouter::with_config(RouterConfig::default())
    }

    /// Create a router with explicit tunable configuration
    /// (min score gate + gas P99 reference — see `RouterConfig`).
    pub fn with_config(config: RouterConfig) -> Self {
        BTCPRouter {
            routes: HashMap::new(),
            intents: HashMap::new(),
            balance_reservations: HashMap::new(),
            config,
        }
    }

    /// ── Gap E: Behavioral Balance Reservation ─────────────────────────

    /// Reserve `intent_value` against the entity's available behavioral
    /// balance.
    ///
    /// Returns true if the reservation fits; false if the unreserved
    /// balance is insufficient (prevents double-spending across concurrent
    /// routes). Mirrors `reserve_balance` in the Python reference
    /// (`core/btcp/router.py`) exactly.
    pub fn reserve_balance(&mut self, entity_id: &BEOId, intent_value: f64, available: f64) -> bool {
        let current = self
            .balance_reservations
            .get(entity_id)
            .copied()
            .unwrap_or(0.0);
        if current + intent_value > available {
            return false;
        }
        self.balance_reservations.insert(*entity_id, current + intent_value);
        true
    }

    /// Release a reservation (route finalized/reverted).
    /// Mirrors `release_balance` in the Python reference: the stored
    /// reservation floors at zero on over-release.
    pub fn release_balance(&mut self, entity_id: &BEOId, intent_value: f64) {
        let current = self
            .balance_reservations
            .get(entity_id)
            .copied()
            .unwrap_or(0.0);
        self.balance_reservations
            .insert(*entity_id, (current - intent_value).max(0.0));
    }

    /// Total currently-reserved value for an entity.
    /// Mirrors `reserved_balance` in the Python reference.
    pub fn reserved_balance(&self, entity_id: &BEOId) -> f64 {
        self.balance_reservations
            .get(entity_id)
            .copied()
            .unwrap_or(0.0)
    }

    /// Register an intent and compute its hash
    pub fn register_intent(&mut self, mut intent: Intent) -> H256 {
        let intent_hash = intent.hash();
        intent.intent_id = intent_hash;
        self.intents.insert(intent_hash, intent);
        intent_hash
    }

    /// Step 2: Compute BTCP score for a route given BIBL analysis
    ///
    /// BTCP_score_final = [0.25×NL + 0.20×normalize_gas + 0.20×finality
    ///                     + 0.15×CC + 0.20×BEO] × (1 − MF)  (K1 Resolution)
    ///
    /// Gas normalization uses the router's configured 99th-percentile gas
    /// reference (`RouterConfig::gas_p99`) — a placeholder default that
    /// requires chain-specific calibration.
    pub fn btcp_score(&self, route: &Route, analysis: &BIBLAnalysis) -> f64 {
        let gas_norm = normalize_gas(analysis.gas_forecast.mean, self.config.gas_p99);

        (0.25 * analysis.nl_score
            + 0.20 * gas_norm
            + 0.20 * analysis.finality_dist.ci95
            + 0.15 * analysis.cc_coherence
            + 0.20 * route.beo_continuity)
            * (1.0 - analysis.mf_score)
    }

    /// Select optimal route type based on multi-chain BIBL analysis.
    ///
    /// Spec priority order (BTCP Master Spec §4.2 — highest priority first):
    ///   1. NETTING      — counterparty with opposite intent (zero movement)
    ///   2. SINGLE_CHAIN — destination already optimal (NL > 0.7, superior metrics)
    ///   3. SPLIT        — anchor on source, execute on destination
    ///      (MULTIHOP variant when an intermediate chain is materially deeper)
    ///   4. PARALLEL     — large intent split across chains with healthy NL
    ///   5. BITP         — illiquid destination pair → behavioral commitment
    ///                      transfer (assets never move until matched)
    ///   6. DEFERRED     — BRT scheduling for non-urgent intents when current
    ///                      conditions are suboptimal (last resort per spec)
    pub fn select_route_type(
        &self,
        intent: &Intent,
        analyses: &[BIBLAnalysis],
        netting_available: Option<BEOId>,
    ) -> RouteType {
        use route_policy::*;

        // 1. NETTING — counterparty found = zero movement (score typically 0.95-0.99)
        if let Some(counterparty) = netting_available {
            return RouteType::Netting { counterparty };
        }

        let dest_analysis = analyses
            .iter()
            .find(|a| a.chain_id == intent.dest_chain);

        let source_analysis = analyses
            .iter()
            .find(|a| a.chain_id == intent.source_chain);

        let dest_nl = dest_analysis.map_or(0.0, |a| a.nl_score);

        // 2. SINGLE_CHAIN — destination superior across all metrics
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

        // 3. SPLIT / MULTIHOP — anchor on source, execute on destination.
        //    MULTIHOP when an intermediate chain (not source/dest) has
        //    materially better liquidity than both endpoints.
        if source_analysis.is_some() && dest_analysis.is_some() {
            let best_intermediate = analyses
                .iter()
                .filter(|a| a.chain_id != intent.source_chain && a.chain_id != intent.dest_chain)
                .max_by(|a, b| {
                    a.nl_score
                        .partial_cmp(&b.nl_score)
                        .unwrap_or(std::cmp::Ordering::Equal)
                });
            if let Some(via) = best_intermediate {
                let endpoint_nl = source_analysis.map_or(0.0, |a| a.nl_score)
                    .max(dest_analysis.map_or(0.0, |a| a.nl_score));
                if via.nl_score >= endpoint_nl + MULTIHOP_NL_LIFT {
                    return RouteType::MultiHop { via: via.chain_id };
                }
            }
        }

        // 4. PARALLEL — large intent batched across chains with healthy NL
        //    (Spec §4.2 route type: large intent split across multiple chains)
        if intent.amount_in >= PARALLEL_AMOUNT_THRESHOLD {
            let legs: Vec<ChainId> = analyses
                .iter()
                .filter(|a| a.nl_score >= NL_PARALLEL_LEG)
                .map(|a| a.chain_id)
                .collect();
            if legs.len() >= 2 {
                return RouteType::Parallel(legs);
            }
        }

        // 5. BITP — illiquid pair on destination: do not route, post a
        //    behavioral commitment (CUT → MATCH → PASTE; Spec §5.1)
        if dest_nl < NL_ILLIQUID && intent.constraints.allow_partial_fill {
            let commitment_input = format!(
                "bitp:{}:{}:{}",
                intent.entity_id.to_hex(),
                intent.hash().to_hex(),
                intent.nonce
            );
            return RouteType::BITP {
                commitment_hash: H256::sha3(commitment_input.as_bytes()),
            };
        }

        // 6. DEFERRED — BRT scheduling for non-urgent intents (Spec §5.8).
        //    Last priority per spec: applied only when the intent can wait
        //    AND current conditions are suboptimal (destination NL mediocre).
        if intent.constraints.allow_deferred
            && dest_nl >= NL_ILLIQUID
            && dest_nl <= NL_PARALLEL_LEG
            && intent.deadline.saturating_sub(current_timestamp()) > DEFER_MIN_LEAD_SECS
        {
            // Schedule to the next 90-min ultradian window boundary (BRT)
            let now = current_timestamp();
            let optimal_window = now + (5_400 - (now % 5_400));
            return RouteType::Deferred { optimal_window };
        }

        // 3b. SPLIT — anchor on source, execute on destination (default)
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
    ///
    /// Default gate: 0.10 (unified with the Python canonical
    /// `MIN_BTCP_SCORE`); override via `RouterConfig::min_btcp_score`.
    pub fn route_is_valid(&self, route: &Route) -> bool {
        route.btcp_score >= self.config.min_btcp_score
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

    // ── Spec §4.2: full route-type coverage tests ────────────────────────────

    #[test]
    fn test_route_type_bitp_illiquid_destination() {
        // Destination NL < 0.30 → illiquid pair → BITP behavioral commitment
        let router = BTCPRouter::new();
        let intent = create_test_intent();
        let analyses = vec![
            create_test_analysis(42161, 0.75),
            create_test_analysis(900, 0.20), // illiquid destination
        ];
        let rt = router.select_route_type(&intent, &analyses, None);
        assert!(matches!(rt, RouteType::BITP { .. }), "expected BITP, got {:?}", rt);
    }

    #[test]
    fn test_route_type_parallel_large_intent() {
        // Large intent + ≥2 chains with healthy NL → PARALLEL
        let router = BTCPRouter::new();
        let mut intent = create_test_intent();
        intent.amount_in = 5_000_000_000_000_000_000_000; // 5000 tokens
        let analyses = vec![
            create_test_analysis(42161, 0.75),
            create_test_analysis(900, 0.65),
            create_test_analysis(137, 0.70),
        ];
        let rt = router.select_route_type(&intent, &analyses, None);
        assert!(matches!(rt, RouteType::Parallel(_)), "expected Parallel, got {:?}", rt);
    }

    #[test]
    fn test_route_type_multihop_intermediate_liquidity() {
        // Intermediate chain materially deeper than both endpoints → MULTIHOP
        let router = BTCPRouter::new();
        let intent = create_test_intent();
        let analyses = vec![
            create_test_analysis(42161, 0.40),
            create_test_analysis(900, 0.45),
            create_test_analysis(8453, 0.95), // Base much deeper
        ];
        let rt = router.select_route_type(&intent, &analyses, None);
        assert!(matches!(rt, RouteType::MultiHop { via } if via == 8453), "expected MultiHop(8453), got {:?}", rt);
    }

    #[test]
    fn test_route_type_deferred_non_urgent_mediocre() {
        // Non-urgent intent + mediocre destination NL (0.30–0.60) → DEFERRED
        let router = BTCPRouter::new();
        let mut intent = create_test_intent();
        intent.deadline = current_timestamp() + 7_200; // 2h away
        let analyses = vec![
            create_test_analysis(42161, 0.75),
            create_test_analysis(900, 0.45), // mediocre
        ];
        let rt = router.select_route_type(&intent, &analyses, None);
        assert!(matches!(rt, RouteType::Deferred { .. }), "expected Deferred, got {:?}", rt);
    }

    #[test]
    fn test_route_type_urgent_not_deferred() {
        // Same mediocre conditions but deadline close → SPLIT (execute now)
        let router = BTCPRouter::new();
        let mut intent = create_test_intent();
        intent.deadline = current_timestamp() + 60; // 1 min away — urgent
        let analyses = vec![
            create_test_analysis(42161, 0.75),
            create_test_analysis(900, 0.45),
        ];
        let rt = router.select_route_type(&intent, &analyses, None);
        assert!(matches!(rt, RouteType::Split { .. }), "expected Split, got {:?}", rt);
    }

    #[test]
    fn test_route_type_single_chain_superior_destination() {
        let router = BTCPRouter::new();
        let intent = create_test_intent();
        let analyses = vec![
            create_test_analysis(42161, 0.65),
            create_test_analysis(900, 0.85), // dest superior
        ];
        let rt = router.select_route_type(&intent, &analyses, None);
        assert!(matches!(rt, RouteType::SingleChain), "expected SingleChain, got {:?}", rt);
    }

    // ── Threshold unification (Python canonical MIN_BTCP_SCORE = 0.10) ─────

    #[test]
    fn test_min_btcp_score_matches_python_canonical() {
        // The Python reference gate is MIN_BTCP_SCORE = 0.10
        // (core/btcp/router.py); Rust must use the same default
        // (previously diverged at 0.50).
        assert_eq!(crate::MIN_BTCP_SCORE, 0.10);
        assert_eq!(RouterConfig::default().min_btcp_score, 0.10);
    }

    #[test]
    fn test_route_validity_uses_configured_threshold() {
        let mut router =
            BTCPRouter::with_config(RouterConfig { min_btcp_score: 0.90, ..Default::default() });
        let intent = create_test_intent();
        let analyses = vec![
            create_test_analysis(42161, 0.75),
            create_test_analysis(900, 0.65),
        ];

        let route = router.create_route(intent, &analyses, 0.95, None);

        // Same route: invalid under a strict 0.90 gate, valid under the
        // canonical 0.10 default.
        assert!(!router.route_is_valid(&route));
        let default_router = BTCPRouter::new();
        assert!(default_router.route_is_valid(&route));
    }

    // ── normalize_gas parity with core/btcp/router.py ─────────────────────

    #[test]
    fn test_normalize_gas_parity_with_python() {
        // Mirrors the Python reference self-test:
        //   normalize_gas(31.0, gas_reference=31.0) == 0.0
        //   normalize_gas(0.0)  == 1.0
        //   normalize_gas(15.5) == 0.5
        assert_eq!(normalize_gas(31.0, 31.0), 0.0);
        assert_eq!(normalize_gas(0.0, 31.0), 1.0);
        assert_eq!(normalize_gas(15.5, 31.0), 0.5);
        // Non-positive reference → neutral 0.5 (Python: g_ref <= 0 → 0.5)
        assert_eq!(normalize_gas(10.0, 0.0), 0.5);
        // Above the P99 → clamped to 0
        assert_eq!(normalize_gas(100.0, 31.0), 0.0);
    }

    #[test]
    fn test_gas_p99_override_changes_score() {
        // RouterConfig.gas_p99 must flow through the BTCP score computation.
        let intent = create_test_intent();
        let analysis = create_test_analysis(900, 0.82); // gas mean = 50.0
        let route = Route {
            route_id: H256::zero(),
            intent,
            route_type: RouteType::SingleChain,
            beo_continuity: 0.95,
            btcp_score: 0.0,
            status: RouteStatus::Pending,
            created_at: 0,
        };

        let default_router = BTCPRouter::new(); // gas_p99 = 1000.0 placeholder
        let tight_router = BTCPRouter::with_config(RouterConfig { gas_p99: 50.0, ..Default::default() });

        // gas mean 50 at g_ref 50 → normalize_gas = 0 → strictly lower score
        let tight_score = tight_router.btcp_score(&route, &analysis);
        let default_score = default_router.btcp_score(&route, &analysis);
        assert!(tight_score < default_score);
    }

    // ── Gap E: Behavioral Balance Reservation (port of router.py L57-97) ──

    #[test]
    fn test_reserve_balance_fits() {
        let mut router = BTCPRouter::new();
        let entity = H256::sha3(b"entity");

        assert!(router.reserve_balance(&entity, 40.0, 100.0));
        assert_eq!(router.reserved_balance(&entity), 40.0);

        // 40 + 60 == 100 exactly fits (Python: `current + value > available`
        // is the reject condition — equality is allowed)
        assert!(router.reserve_balance(&entity, 60.0, 100.0));
        assert_eq!(router.reserved_balance(&entity), 100.0);
    }

    #[test]
    fn test_reserve_balance_rejects_double_spend() {
        let mut router = BTCPRouter::new();
        let entity = H256::sha3(b"entity");

        assert!(router.reserve_balance(&entity, 70.0, 100.0));
        // 70 + 40 > 100 → rejected: no double-spending across concurrent routes
        assert!(!router.reserve_balance(&entity, 40.0, 100.0));
        // Rejected reservation must not change the stored amount
        assert_eq!(router.reserved_balance(&entity), 70.0);
    }

    #[test]
    fn test_release_balance_floors_at_zero() {
        let mut router = BTCPRouter::new();
        let entity = H256::sha3(b"entity");

        router.reserve_balance(&entity, 30.0, 100.0);
        router.release_balance(&entity, 50.0); // over-release
        assert_eq!(router.reserved_balance(&entity), 0.0);

        // Release for an entity with no reservation is a no-op (0 floor)
        router.release_balance(&H256::sha3(b"nobody"), 10.0);
        assert_eq!(router.reserved_balance(&H256::sha3(b"nobody")), 0.0);
    }

    #[test]
    fn test_reserve_release_roundtrip() {
        let mut router = BTCPRouter::new();
        let entity = H256::sha3(b"entity");

        assert!(router.reserve_balance(&entity, 60.0, 100.0));
        router.release_balance(&entity, 60.0);
        // Full release → capacity available again
        assert!(router.reserve_balance(&entity, 100.0, 100.0));
    }

    // ── Gap G: Observer-Effect correction (port of router.py L87-98) ──────

    #[test]
    fn test_oe_correction_discounts_self_caused_score() {
        // oe_factor 0.25 → score discounted by 25%: 0.80 → 0.60
        assert!((apply_oe_correction(0.80, 0.25) - 0.60).abs() < 1e-9);
    }

    #[test]
    fn test_oe_correction_clamps_factor() {
        // oe_factor above 1 clamps to 1 → fully discounted score
        assert!((apply_oe_correction(0.80, 2.0) - 0.0).abs() < 1e-9);
        // oe_factor below 0 clamps to 0 → unchanged score
        assert!((apply_oe_correction(0.80, -1.0) - 0.80).abs() < 1e-9);
    }

    #[test]
    fn test_oe_correction_zero_factor_no_discount() {
        // Organic improvement (oe = 0) is not discounted
        assert!((apply_oe_correction(0.90, 0.0) - 0.90).abs() < 1e-9);
    }
}
