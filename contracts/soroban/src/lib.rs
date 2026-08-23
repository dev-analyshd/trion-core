//! TRION Protocol — Soroban Contract (Stellar)
//! Behavioral truth oracle + BTCP escrow for Stellar network
#![no_std]
use soroban_sdk::{contract, contractimpl, contracttype, Env, Symbol, String, Vec, Map};

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

#[contract]
pub struct TrionContract;

#[contractimpl]
impl TrionContract {
    /// Publish a behavioral signal
    pub fn publish_signal(
        env: Env,
        entity_id: String,
        coherence: i64,
        threshold: i64,
        emits: bool,
        status: u32,
        truth: i64,
    ) {
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

    /// Get signal for an entity
    pub fn get_signal(env: Env, entity_id: String) -> Option<Signal> {
        let signals: Map<String, Signal> = env.storage().instance().get(&SIGNALS).unwrap_or_else(|| Map::new(&env));
        signals.get(entity_id)
    }

    /// Lock escrow
    pub fn lock_escrow(env: Env, route_id: String, entity_id: String, amount: i128) {
        let escrow = Escrow {
            route_id: route_id.clone(),
            entity_id,
            amount,
            state: 0, // HOLDING
        };
        let mut escrows: Map<String, Escrow> = env.storage().instance().get(&ESCROWS).unwrap_or_else(|| Map::new(&env));
        escrows.set(route_id, escrow);
        env.storage().instance().set(&ESCROWS, &escrows);
    }

    /// Release escrow
    pub fn release_escrow(env: Env, route_id: String) {
        let mut escrows: Map<String, Escrow> = env.storage().instance().get(&ESCROWS).unwrap_or_else(|| Map::new(&env));
        if let Some(mut esc) = escrows.get(route_id.clone()) {
            esc.state = 1; // RELEASED
            escrows.set(route_id, esc);
            env.storage().instance().set(&ESCROWS, &escrows);
        }
    }

    /// Revert escrow
    pub fn revert_escrow(env: Env, route_id: String) {
        let mut escrows: Map<String, Escrow> = env.storage().instance().get(&ESCROWS).unwrap_or_else(|| Map::new(&env));
        if let Some(mut esc) = escrows.get(route_id.clone()) {
            esc.state = 2; // REVERTED
            escrows.set(route_id, esc);
            env.storage().instance().set(&ESCROWS, &escrows);
        }
    }

    /// Register intent
    pub fn register_intent(
        env: Env,
        intent_hash: String,
        entity_id: String,
        source_chain: String,
        dest_chain: String,
        amount: i128,
    ) {
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

    /// Check if execution is safe
    pub fn is_execution_safe(env: Env, entity_id: String) -> bool {
        let signals: Map<String, Signal> = env.storage().instance().get(&SIGNALS).unwrap_or_else(|| Map::new(&env));
        if let Some(sig) = signals.get(entity_id) {
            return sig.emits && sig.status == 0;
        }
        false
    }
}
