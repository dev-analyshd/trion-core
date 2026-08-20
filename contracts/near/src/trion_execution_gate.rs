//! TRION Protocol — NEAR Execution Gate (TRIONExecutionGate equivalent)
//! =====================================================================
//! Behavioral firewall: gate_check passes only when phi >= threshold.
//! AWA (Anima, Will, Action) enforcement on all sensitive operations.
//! Mirrors contracts/solidity/TRIONExecutionGate.sol.

use near_sdk::borsh::{self, BorshDeserialize, BorshSerialize};
use near_sdk::collections::LookupMap;
use near_sdk::{env, near_bindgen, AccountId, PanicOnDefault};

#[near_bindgen]
#[derive(BorshDeserialize, BorshSerialize, PanicOnDefault)]
pub struct TRIONExecutionGate {
    owner: AccountId,
    awa_enforced: bool,
    gates: LookupMap<String, GateState>,
}

#[derive(BorshDeserialize, BorshSerialize, Clone, Debug)]
pub struct GateState {
    pub gate_id:          String,
    pub custom_threshold: u64,
    pub check_count:      u64,
    pub pass_count:       u64,
    pub block_count:      u64,
    pub last_phi:         u64,
    pub last_entity:      String,
}

#[near_bindgen]
impl TRIONExecutionGate {
    #[init]
    pub fn new(owner: AccountId) -> Self {
        Self {
            owner,
            awa_enforced: true,
            gates: LookupMap::new(b"g"),
        }
    }

    /// Set a custom threshold for a gate. threshold=0 means use route threshold.
    pub fn set_gate_threshold(&mut self, gate_id: String, threshold: u64) {
        self.assert_owner();
        assert!(threshold <= 1_000_000, "TRION: invalid score");
        let mut g = self.gates.get(&gate_id).unwrap_or(GateState {
            gate_id: gate_id.clone(),
            custom_threshold: 0,
            check_count: 0,
            pass_count: 0,
            block_count: 0,
            last_phi: 0,
            last_entity: String::new(),
        });
        g.custom_threshold = threshold;
        self.gates.insert(&gate_id, &g);
    }

    /// Evaluate the behavioral gate. Returns true if passed.
    pub fn check_execution(
        &mut self,
        gate_id:         String,
        entity_id:       String,
        phi:             u64,
        route_threshold: u64,
    ) -> bool {
        assert!(self.awa_enforced, "TRION: AWA not enforced");
        let mut g = self.gates.get(&gate_id).unwrap_or(GateState {
            gate_id: gate_id.clone(),
            custom_threshold: 0,
            check_count: 0,
            pass_count: 0,
            block_count: 0,
            last_phi: 0,
            last_entity: String::new(),
        });
        let threshold = if g.custom_threshold > 0 { g.custom_threshold } else { route_threshold };
        g.check_count += 1;
        g.last_phi    = phi;
        g.last_entity = entity_id.clone();
        let passed = phi >= threshold;
        if passed { g.pass_count += 1; } else { g.block_count += 1; }
        self.gates.insert(&gate_id, &g);
        if passed {
            env::log_str(&format!("GatePassed:{}:phi={}", gate_id, phi));
        } else {
            env::log_str(&format!("GateBlocked:{}:phi={}", gate_id, phi));
        }
        passed
    }

    /// Read gate stats.
    pub fn get_gate(&self, gate_id: String) -> Option<GateState> {
        self.gates.get(&gate_id)
    }

    /// Whether AWA enforcement is currently active.
    pub fn awa_enforced(&self) -> bool { self.awa_enforced }

    /// Toggle AWA enforcement (only owner — used in emergencies).
    pub fn set_awa_enforced(&mut self, enforced: bool) {
        self.assert_owner();
        self.awa_enforced = enforced;
    }

    fn assert_owner(&self) {
        assert_eq!(
            env::predecessor_account_id(),
            self.owner,
            "TRION: not owner"
        );
    }
}
