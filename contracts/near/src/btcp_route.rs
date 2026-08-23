//! TRION Protocol — NEAR BTCP Route (BTCPRoute equivalent)
//! ========================================================
//! Records the behavioral proof of a cross-chain BTCP route. Mirrors
//! contracts/solidity/BTCPRoute.sol and contracts/move/sources/btcp_route.move.
//!
//! Each route links an anchor behavioral hash (chain A) to an execution
//! behavioral hash (chain B) with consensus proof.

use near_sdk::borsh::{self, BorshDeserialize, BorshSerialize};
use near_sdk::collections::LookupMap;
use near_sdk::{env, near_bindgen, AccountId, PanicOnDefault};

#[near_bindgen]
#[derive(BorshDeserialize, BorshSerialize, PanicOnDefault)]
pub struct BTCPRouteContract {
    relayer: AccountId,
    routes:  LookupMap<String, RouteRecord>,
    route_count: u64,
}

#[derive(BorshDeserialize, BorshSerialize, Clone, Debug)]
pub struct RouteRecord {
    pub route_id:            String,
    pub intent_hash:         String,
    pub anchor_bh:           String,
    pub execution_bh:        String,
    pub anchor_chain:        u64,
    pub execution_chain:     u64,
    pub entity_id:           String,
    pub gas_saved_vs_bridge:u64,
    pub beo_continuity:     u64,
    pub cc_coherence:        u64,
    pub route_type:          u8,
    pub is_verified:         bool,
    pub created_at:         u64,
    pub finalized_at:       u64,
}

#[near_bindgen]
impl BTCPRouteContract {
    #[init]
    pub fn new(relayer: AccountId) -> Self {
        Self {
            relayer,
            routes: LookupMap::new(b"r"),
            route_count: 0,
        }
    }

    /// Publish a new BTCP route with anchor BH. Mirrors `publishRoute(...)`.
    pub fn register_route(
        &mut self,
        route_id:        String,
        intent_hash:     String,
        anchor_bh:       String,
        anchor_chain:    u64,
        execution_chain: u64,
        entity_id:       String,
        route_type:      u8,
    ) {
        self.assert_relayer();
        assert!(!anchor_bh.is_empty(), "TRION: zero anchor");
        assert!(route_type <= 6, "TRION: invalid type");
        assert!(self.routes.get(&route_id).is_none(), "TRION: route exists");

        let ts = env::block_timestamp_ms() / 1000;
        let r = RouteRecord {
            route_id: route_id.clone(),
            intent_hash,
            anchor_bh,
            execution_bh: String::new(),
            anchor_chain,
            execution_chain,
            entity_id,
            gas_saved_vs_bridge: 0,
            beo_continuity: 0,
            cc_coherence: 0,
            route_type,
            is_verified: false,
            created_at: ts,
            finalized_at: 0,
        };
        self.routes.insert(&route_id, &r);
        self.route_count += 1;
        env::log_str(&format!("RoutePublished:{}", route_id));
    }

    /// Finalize a route with execution BH + savings data.
    pub fn finalize_route(
        &mut self,
        route_id:            String,
        execution_bh:        String,
        gas_saved_vs_bridge:u64,
        beo_continuity:     u64,
        cc_coherence:        u64,
    ) {
        self.assert_relayer();
        assert!(!execution_bh.is_empty(), "TRION: zero exec bh");
        assert!(beo_continuity <= 1_000_000, "TRION: invalid score");
        assert!(cc_coherence <= 1_000_000, "TRION: invalid score");

        let mut r = self.routes.get(&route_id).expect("TRION: route not found");
        assert!(!r.is_verified, "TRION: already verified");
        r.execution_bh          = execution_bh;
        r.gas_saved_vs_bridge   = gas_saved_vs_bridge;
        r.beo_continuity        = beo_continuity;
        r.cc_coherence          = cc_coherence;
        r.is_verified           = true;
        r.finalized_at          = env::block_timestamp_ms() / 1000;
        self.routes.insert(&route_id, &r);
        env::log_str(&format!("RouteFinalized:{}", route_id));
    }

    /// Read route by id.
    pub fn get_route(&self, route_id: String) -> Option<RouteRecord> {
        self.routes.get(&route_id)
    }

    pub fn route_count(&self) -> u64 { self.route_count }

    pub fn set_relayer(&mut self, new_relayer: AccountId) {
        self.assert_relayer();
        self.relayer = new_relayer;
    }

    fn assert_relayer(&self) {
        assert_eq!(
            env::predecessor_account_id(),
            self.relayer,
            "TRION: not relayer"
        );
    }
}
