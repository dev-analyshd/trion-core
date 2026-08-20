//! TRION Protocol — NEAR TRION Oracle (TRIONOracleV3 equivalent)
//! =============================================================
//! Stores behavioral signals keyed by `entity_id` and verifies execution
//! safety via coherence >= threshold. Mirrors contracts/solidity/TRIONOracleV3.sol
//! and contracts/move/sources/trion_oracle.move.
//!
//! Storage layout:
//!   - `relayer: AccountId`
//!   - `signals: LookupMap<String, SignalRecord>`
//!   - `routes:  LookupMap<String, RouteRecord>`
//!   - `signal_count: u64`, `route_count: u64`

use near_sdk::borsh::{self, BorshDeserialize, BorshSerialize};
use near_sdk::collections::LookupMap;
use near_sdk::{env, near_bindgen, AccountId, PanicOnDefault};

#[near_bindgen]
#[derive(BorshDeserialize, BorshSerialize, PanicOnDefault)]
pub struct TRIONOracle {
    relayer: AccountId,
    signals: LookupMap<String, SignalRecord>,
    routes:  LookupMap<String, RouteRecord>,
    signal_count: u64,
    route_count:  u64,
}

#[derive(BorshDeserialize, BorshSerialize, Clone, Debug)]
pub struct SignalRecord {
    pub entity_id:    String,
    pub coherence:    u64,    // x1_000_000
    pub threshold:    u64,    // x1_000_000
    pub emits_signal: bool,
    pub timestamp:    u64,
    pub update_count: u64,
}

#[derive(BorshDeserialize, BorshSerialize, Clone, Debug)]
pub struct RouteRecord {
    pub route_id:     String,
    pub anchor_bh:    String,
    pub execution_bh: String,
    pub coherence:    u64,
    pub threshold:    u64,
    pub is_safe:      bool,
    pub timestamp:    u64,
}

#[near_bindgen]
impl TRIONOracle {
    #[init]
    pub fn new(relayer: AccountId) -> Self {
        Self {
            relayer,
            signals: LookupMap::new(b"s"),
            routes:  LookupMap::new(b"r"),
            signal_count: 0,
            route_count:  0,
        }
    }

    /// Publish a behavioral signal for `entity_id`.
    pub fn publish_signal(
        &mut self,
        entity_id: String,
        coherence: u64,
        threshold: u64,
        emits:    bool,
    ) {
        self.assert_relayer();
        assert!(coherence <= 1_000_000, "TRION: invalid coherence");
        assert!(threshold <= 1_000_000, "TRION: invalid threshold");

        let update_count = self.signals.get(&entity_id)
            .map(|s: SignalRecord| s.update_count + 1)
            .unwrap_or(1);
        let sig = SignalRecord {
            entity_id:    entity_id.clone(),
            coherence,
            threshold,
            emits_signal: emits,
            timestamp:    env::block_timestamp_ms() / 1000,
            update_count,
        };
        self.signals.insert(&entity_id, &sig);
        self.signal_count += 1;
        env::log_str(&format!(
            "SignalPublished:{}:coh={}:thr={}:emits={}",
            entity_id, coherence, threshold, emits
        ));
    }

    /// Publish a BTCP route proof (called by relayer before escrow release).
    pub fn publish_btcp_route(
        &mut self,
        route_id: String,
        anchor_bh: String,
        execution_bh: String,
        coherence: u64,
        threshold: u64,
    ) {
        self.assert_relayer();
        assert!(coherence <= 1_000_000, "TRION: invalid coherence");
        assert!(threshold <= 1_000_000, "TRION: invalid threshold");
        assert!(self.routes.get(&route_id).is_none(), "TRION: route exists");

        let is_safe = coherence >= threshold;
        let r = RouteRecord {
            route_id: route_id.clone(),
            anchor_bh,
            execution_bh,
            coherence,
            threshold,
            is_safe,
            timestamp: env::block_timestamp_ms() / 1000,
        };
        self.routes.insert(&route_id, &r);
        self.route_count += 1;
        env::log_str(&format!("BTCPRoutePublished:{}:is_safe={}", route_id, is_safe));
    }

    /// Verify execution safety for `route_id`.
    /// Returns (is_safe, coherence, threshold).
    pub fn verify_execution(&self, route_id: String) -> (bool, u64, u64) {
        match self.routes.get(&route_id) {
            Some(r) => (r.is_safe, r.coherence, r.threshold),
            None    => (false, 0, 0),
        }
    }

    /// Read the latest signal for `entity_id`.
    pub fn get_signal(&self, entity_id: String) -> Option<SignalRecord> {
        self.signals.get(&entity_id)
    }

    pub fn signal_count(&self) -> u64 { self.signal_count }
    pub fn route_count(&self)  -> u64 { self.route_count }

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
