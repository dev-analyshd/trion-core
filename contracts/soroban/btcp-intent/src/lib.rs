#![no_std]
//! BTCPIntent — Soroban (Stellar) — spec §4.1 Intent Object.
//! =================================================================
//! Replaces the prior generic `Record` placeholder stub. Now stores the
//! full §4.1 Intent schema (entity_id, action, asset_in/out, value,
//! deadline, max_total_gas, min_finality, min_NL_score, chain_pref,
//! privacy, btcp_version, nonce) plus the intent_id / source_chain /
//! dest_chain / source_address / dest_address fields the task requires.
//!
//! The full Intent object is stored on-chain by hash; off-chain Akashic
//! Index storage is referenced by intent_hash (spec §4.1 line 491:
//! "Full object stored off-chain in Akashic Index, referenced on-chain
//! by `intent_hash = keccak256(abi.encode(intent))`").
use soroban_sdk::{contract, contracterror, contractimpl, contracttype, symbol_short, Env, Address, Map, Symbol, BytesN, Vec};

/// §4.1 action enum — SWAP | TRANSFER | LIQUIDITY | STAKE | BORROW.
#[contracttype]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Action {
    Swap = 0,
    Transfer = 1,
    Liquidity = 2,
    Stake = 3,
    Borrow = 4,
}

/// §4.1 min_finality enum — FAST | STANDARD | SECURE (uint8).
#[contracttype]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Finality {
    Fast = 0,
    Standard = 1,
    Secure = 2,
}

/// §4.1 chain_pref enum — OPTIMAL | SINGLE_CHAIN (lists are passed in
/// via the `chain_pref_list` field when `Optimal` is overridden).
#[contracttype]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ChainPref {
    Optimal = 0,
    SingleChain = 1,
    Listed = 2,
}

/// §4.1 privacy enum — PUBLIC | ZK_CREDENTIAL | INVISIBLE (uint8).
#[contracttype]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Privacy {
    Public = 0,
    ZkCredential = 1,
    Invisible = 2,
}

/// §4.1 Intent lifecycle — registered by hash, transitions through
/// Pending → Routing → Executing → Completed | Failed | Expired.
#[contracttype]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum IntentStatus {
    Pending = 0,
    Routing = 1,
    Executing = 2,
    Completed = 3,
    Failed = 4,
    Expired = 5,
}

/// §4.1 Intent object — full schema, mirrors BTCPIntent.sol.
#[contracttype]
#[derive(Clone, Debug, PartialEq)]
pub struct Intent {
    /// BEO identifier — same across ALL chains (bytes32). Spec §4.1.
    pub entity_id: BytesN<32>,
    /// Per-entity monotonic intent id (bytes32) — keccak256(abi.encode(intent)).
    pub intent_id: BytesN<32>,
    /// Action enum (SWAP | TRANSFER | LIQUIDITY | STAKE | BORROW).
    pub action: Action,
    /// Amount in behavioral magnitude units.
    pub value: u128,
    /// Universal asset identifier (in).
    pub asset_in: BytesN<32>,
    /// Universal asset identifier (out).
    pub asset_out: BytesN<32>,
    /// Source chain id (spec BTCP-FIX2-RUST-VM requirement).
    pub source_chain: u64,
    /// Destination chain id.
    pub dest_chain: u64,
    /// Source address on source_chain (Bytes for chain-agnostic encoding).
    pub source_address: Address,
    /// Destination address on dest_chain.
    pub dest_address: Address,
    /// Block number or timestamp deadline (uint64).
    pub deadline: u64,
    /// USD equivalent across all chains (uint128).
    pub max_total_gas: u128,
    /// FAST | STANDARD | SECURE (uint8).
    pub min_finality: Finality,
    /// Liquidity health floor, default 0.30 scaled ×1000 → 300.
    pub min_nl_score: u32,
    /// OPTIMAL | SINGLE_CHAIN | LISTED.
    pub chain_pref: ChainPref,
    /// Optional explicit chain list when chain_pref == Listed.
    pub chain_pref_list: Vec<u64>,
    /// PUBLIC | ZK_CREDENTIAL | INVISIBLE (uint8).
    pub privacy: Privacy,
    /// semver (bytes12, e.g. "1.0.0\0\0\0\0\0\0\0").
    pub btcp_version: BytesN<12>,
    /// Per-entity monotonic counter (uint64).
    pub nonce: u64,
    /// Lifecycle state.
    pub status: IntentStatus,
    /// Ledger sequence at registration.
    pub created_ledger: u32,
    /// Submitting relayer / entity address.
    pub submitter: Address,
}

#[contracterror]
#[derive(Copy, Clone, Debug, Eq, PartialEq)]
pub enum Error {
    NotFound = 1,
    NotOwner = 2,
    BadInput = 3,
    AlreadyExists = 4,
    AlreadyTerminal = 5,
    InvalidTransition = 6,
}

const KEY_INTENTS: Symbol = symbol_short!("intents");
const KEY_OWNER: Symbol = symbol_short!("owner");
const KEY_ENTITY_NONCE: Symbol = symbol_short!("entnonce");

#[contract]
pub struct BTCPIntent;

#[contractimpl]
impl BTCPIntent {
    /// One-time owner bootstrap (admin / relayer address).
    pub fn init(env: Env, owner: Address) {
        env.storage().instance().set(&KEY_OWNER, &owner);
    }

    /// Spec §4.1 — register an Intent by hash. The full object is
    /// stored on-chain by intent_id; the off-chain Akashic Index holds
    /// the larger payload referenced by intent_hash.
    pub fn register_intent(env: Env, intent: Intent) -> Result<bool, Error> {
        let owner: Address = env
            .storage()
            .instance()
            .get(&KEY_OWNER)
            .ok_or(Error::NotOwner)?;
        // Submitting relayer must be the contract owner (permissioned phase).
        if intent.submitter != owner {
            return Err(Error::NotOwner);
        }
        if intent.value == 0 {
            return Err(Error::BadInput);
        }
        // Bump per-entity monotonic nonce (spec §4.1 "per-entity monotonic counter").
        let mut nonces: Map<BytesN<32>, u64> = env
            .storage()
            .persistent()
            .get(&KEY_ENTITY_NONCE)
            .unwrap_or_else(|| Map::new(&env));
        let next_nonce = nonces.get(intent.entity_id.clone()).unwrap_or(0) + 1;
        if intent.nonce != next_nonce {
            return Err(Error::BadInput);
        }
        nonces.set(intent.entity_id.clone(), next_nonce);
        env.storage().persistent().set(&KEY_ENTITY_NONCE, &nonces);

        let mut m: Map<BytesN<32>, Intent> = env
            .storage()
            .persistent()
            .get(&KEY_INTENTS)
            .unwrap_or_else(|| Map::new(&env));
        if m.contains_key(intent.intent_id.clone()) {
            return Err(Error::AlreadyExists);
        }
        let mut stored = intent;
        stored.created_ledger = env.ledger().sequence();
        stored.status = IntentStatus::Pending;
        m.set(stored.intent_id.clone(), stored);
        env.storage().persistent().set(&KEY_INTENTS, &m);
        Ok(true)
    }

    /// Transition the intent to a new lifecycle state. Only the owner
    /// (relayer) may advance the state machine.
    pub fn transition(
        env: Env,
        invoker: Address,
        intent_id: BytesN<32>,
        next: IntentStatus,
    ) -> Result<bool, Error> {
        invoker.require_auth();
        let owner: Address = env
            .storage()
            .instance()
            .get(&KEY_OWNER)
            .ok_or(Error::NotOwner)?;
        if invoker != owner {
            return Err(Error::NotOwner);
        }
        let mut m: Map<BytesN<32>, Intent> = env
            .storage()
            .persistent()
            .get(&KEY_INTENTS)
            .unwrap_or_else(|| Map::new(&env));
        let mut intent = match m.get(intent_id.clone()) {
            Some(i) => i,
            None => return Err(Error::NotFound),
        };
        if matches!(intent.status, IntentStatus::Completed | IntentStatus::Failed | IntentStatus::Expired) {
            return Err(Error::AlreadyTerminal);
        }
        // Spec §4.2 — Pending → Routing → Executing → Completed (or Failed/Expired).
        let allowed = match (intent.status, next) {
            (IntentStatus::Pending, IntentStatus::Routing) => true,
            (IntentStatus::Routing, IntentStatus::Executing) => true,
            (IntentStatus::Executing, IntentStatus::Completed) => true,
            (_, IntentStatus::Failed) => true,
            (_, IntentStatus::Expired) => true,
            _ => false,
        };
        if !allowed {
            return Err(Error::InvalidTransition);
        }
        intent.status = next;
        m.set(intent_id, intent);
        env.storage().persistent().set(&KEY_INTENTS, &m);
        Ok(true)
    }

    /// Fetch an intent by id.
    pub fn get_intent(env: Env, intent_id: BytesN<32>) -> Option<Intent> {
        let m: Map<BytesN<32>, Intent> = env
            .storage()
            .persistent()
            .get(&KEY_INTENTS)
            .unwrap_or_else(|| Map::new(&env));
        m.get(intent_id)
    }

    /// Get the next-expected nonce for an entity (off-chain callers use
    /// this to construct a well-formed Intent).
    pub fn next_nonce(env: Env, entity_id: BytesN<32>) -> u64 {
        let nonces: Map<BytesN<32>, u64> = env
            .storage()
            .persistent()
            .get(&KEY_ENTITY_NONCE)
            .unwrap_or_else(|| Map::new(&env));
        nonces.get(entity_id).unwrap_or(0) + 1
    }
}
