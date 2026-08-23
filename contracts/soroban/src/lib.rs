//! TRION Protocol — Soroban Contract (Stellar)
//! Behavioral truth oracle + BTCP escrow for Stellar network
//!
//! Security model (BTCP Master Spec — trusted-relayer pattern shared with the
//! EVM/SVM/CosmWasm ports):
//!   - An ADMIN (deployer) authorizes RELAYERS.
//!   - Only authorized relayers publish signals, register intents, and
//!     release/revert escrows.
//!   - The admin cannot release or revert escrows directly — only relayers can.
//!   - publish/lock are permissioned to prevent state spoofing by arbitrary
//!     accounts; every state mutation is fail-closed.
#![no_std]
use soroban_sdk::{contract, contractimpl, contracttype, Address, Env, Symbol, String, Vec, Map};

#[contracttype]
#[derive(Clone, Debug, PartialEq)]
pub struct Signal {
    pub entity_id: String,
    pub coherence: i64,      // ×1e6
    pub threshold: i64,      // ×1e6
    pub emits: bool,
    pub status: u32,         // 0=NOMINAL, 1=WARN, 2=COLLAPSE, 3=HOSTILE
    pub truth: i64,
}

#[contracttype]
#[derive(Clone, Debug, PartialEq)]
pub struct Escrow {
    pub route_id: String,
    pub entity_id: String,
    pub amount: i128,
    pub state: u32,  // 0=HOLDING, 1=RELEASED, 2=REVERTED
}

#[contracttype]
#[derive(Clone, Debug, PartialEq)]
pub struct Intent {
    pub intent_hash: String,
    pub entity_id: String,
    pub source_chain: String,
    pub dest_chain: String,
    pub amount: i128,
}

pub const SIGNALS: Symbol = Symbol::short("signals");
pub const ESCROWS: Symbol = Symbol::short("escrows");
pub const INTENTS: Symbol = Symbol::short("intents");
pub const ADMIN: Symbol = Symbol::short("admin");
pub const RELAYERS: Symbol = Symbol::short("relayers");

#[contract]
pub struct TrionContract;

#[contractimpl]
impl TrionContract {
    /// Deployment — the deploying account becomes admin.
    pub fn init(env: Env, admin: Address) {
        if env.storage().instance().has(&ADMIN) {
            panic!("already initialized");
        }
        env.storage().instance().set(&ADMIN, &admin);
        let relayers: Vec<Address> = Vec::new(&env);
        env.storage().instance().set(&RELAYERS, &relayers);
    }

    fn require_admin(env: &Env) -> Address {
        let admin: Address = env
            .storage()
            .instance()
            .get(&ADMIN)
            .unwrap_or_else(|| panic!("not initialized"));
        admin.require_auth();
        admin
    }

    fn require_relayer(env: &Env) {
        let relayers: Vec<Address> = env
            .storage()
            .instance()
            .get(&RELAYERS)
            .unwrap_or_else(|| panic!("not initialized"));
        let caller = env.invoker();
        let mut authorized = false;
        for r in relayers.iter() {
            if r == caller {
                authorized = true;
                break;
            }
        }
        if !authorized {
            panic!("caller is not an authorized relayer");
        }
    }

    /// Admin: authorize a relayer.
    pub fn add_relayer(env: Env, relayer: Address) {
        Self::require_admin(&env);
        let mut relayers: Vec<Address> = env
            .storage()
            .instance()
            .get(&RELAYERS)
            .unwrap_or_else(|| panic!("not initialized"));
        // idempotent — no duplicate entries
        let mut exists = false;
        for r in relayers.iter() {
            if r == relayer {
                exists = true;
                break;
            }
        }
        if !exists {
            relayers.push_back(relayer);
        }
        env.storage().instance().set(&RELAYERS, &relayers);
    }

    /// Admin: revoke a relayer.
    pub fn remove_relayer(env: Env, relayer: Address) {
        Self::require_admin(&env);
        let relayers: Vec<Address> = env
            .storage()
            .instance()
            .get(&RELAYERS)
            .unwrap_or_else(|| panic!("not initialized"));
        let mut kept: Vec<Address> = Vec::new(&env);
        for r in relayers.iter() {
            if r != relayer {
                kept.push_back(r);
            }
        }
        env.storage().instance().set(&RELAYERS, &kept);
    }

    /// Publish a behavioral signal (authorized relayers only).
    pub fn publish_signal(
        env: Env,
        entity_id: String,
        coherence: i64,
        threshold: i64,
        emits: bool,
        status: u32,
        truth: i64,
    ) {
        Self::require_relayer(&env);
        let signal = Signal {
            entity_id: entity_id.clone(),
            coherence,
            threshold,
            emits,
            status,
            truth,
        };
        let mut signals: Map<String, Signal> = env.storage().instance().get(&SIGNALS).unwrap_or_else(|| Map::new(&env));
        signals.set(entity_id, signal);
        env.storage().instance().set(&SIGNALS, &signals);
    }

    /// Get signal for an entity (read-only, permissionless).
    pub fn get_signal(env: Env, entity_id: String) -> Option<Signal> {
        let signals: Map<String, Signal> = env.storage().instance().get(&SIGNALS).unwrap_or_else(|| Map::new(&env));
        signals.get(entity_id)
    }

    /// Lock escrow (authorized relayers only — BTCP route anchor).
    pub fn lock_escrow(env: Env, route_id: String, entity_id: String, amount: i128) {
        Self::require_relayer(&env);
        let mut escrows: Map<String, Escrow> = env.storage().instance().get(&ESCROWS).unwrap_or_else(|| Map::new(&env));
        if escrows.contains_key(route_id.clone()) {
            panic!("escrow already exists");
        }
        let escrow = Escrow {
            route_id: route_id.clone(),
            entity_id,
            amount,
            state: 0, // HOLDING
        };
        escrows.set(route_id, escrow);
        env.storage().instance().set(&ESCROWS, &escrows);
    }

    /// Release escrow (authorized relayers only; only from HOLDING).
    pub fn release_escrow(env: Env, route_id: String) {
        Self::require_relayer(&env);
        let mut escrows: Map<String, Escrow> = env.storage().instance().get(&ESCROWS).unwrap_or_else(|| Map::new(&env));
        if let Some(mut esc) = escrows.get(route_id.clone()) {
            if esc.state != 0 {
                panic!("escrow not in HOLDING state");
            }
            esc.state = 1; // RELEASED
            escrows.set(route_id, esc);
            env.storage().instance().set(&ESCROWS, &escrows);
        }
    }

    /// Revert escrow (authorized relayers only; only from HOLDING).
    pub fn revert_escrow(env: Env, route_id: String) {
        Self::require_relayer(&env);
        let mut escrows: Map<String, Escrow> = env.storage().instance().get(&ESCROWS).unwrap_or_else(|| Map::new(&env));
        if let Some(mut esc) = escrows.get(route_id.clone()) {
            if esc.state != 0 {
                panic!("escrow not in HOLDING state");
            }
            esc.state = 2; // REVERTED
            escrows.set(route_id, esc);
            env.storage().instance().set(&ESCROWS, &escrows);
        }
    }

    /// Register intent (authorized relayers only).
    pub fn register_intent(
        env: Env,
        intent_hash: String,
        entity_id: String,
        source_chain: String,
        dest_chain: String,
        amount: i128,
    ) {
        Self::require_relayer(&env);
        let intent = Intent {
            intent_hash,
            entity_id: entity_id.clone(),
            source_chain,
            dest_chain,
            amount,
        };
        let mut intents: Map<String, Intent> = env.storage().instance().get(&INTENTS).unwrap_or_else(|| Map::new(&env));
        intents.set(entity_id, intent);
        env.storage().instance().set(&INTENTS, &intents);
    }

    /// Check if execution is safe (read-only, permissionless — the firewall).
    pub fn is_execution_safe(env: Env, entity_id: String) -> bool {
        let signals: Map<String, Signal> = env.storage().instance().get(&SIGNALS).unwrap_or_else(|| Map::new(&env));
        if let Some(sig) = signals.get(entity_id) {
            return sig.emits && sig.status == 0;
        }
        false
    }
}
