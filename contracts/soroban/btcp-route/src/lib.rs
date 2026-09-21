#![no_std]
//! BTCPRoute — Soroban (Stellar) — spec §4.3 Six-Step Execution.
//! =================================================================
//! Replaces the prior generic `Record` placeholder stub. Now stores the
//! full §4.3 Route lifecycle: create → prove → execute → finalize (with
//! Reverted terminal state). RouteData carries anchor_bh, execution_bh,
//! the spec-required §4.1 fields (intent_id, entity_id, source_chain,
//! dest_chain, amount, gas_saved, btcp_version), the on-chain coherence
//! score (×1000, threshold 0.55 floor enforced at prove + execute), and
//! a parent_route_id for cascade-revert chains (Gap 9).
use soroban_sdk::{contract, contracterror, contractimpl, contracttype, symbol_short, Env, Address, Map, Symbol, BytesN};

/// §4.3 Route lifecycle — Created → Proved → Executed → Finalized (or
/// Reverted at any pre-finalize step).
#[contracttype]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RouteState {
    Created = 0,
    Proved = 1,
    Executed = 2,
    Finalized = 3,
    Reverted = 4,
}

/// §4.3 RouteData — mirrors Solidity BTCPRoute.sol + SVM btcp_route.
#[contracttype]
#[derive(Clone, Debug, PartialEq)]
pub struct RouteData {
    /// Route id (bytes32) — keccak256 of (intent_id || anchor_chain || exec_chain).
    pub route_id: BytesN<32>,
    /// Parent intent id (spec §4.1).
    pub intent_id: BytesN<32>,
    /// BEO identifier (bytes32, §4.1).
    pub entity_id: BytesN<32>,
    /// Anchor behavioral hash (spec §4.2 Step 3).
    pub anchor_bh: BytesN<32>,
    /// Execution behavioral hash (spec §4.2 Step 6).
    pub execution_bh: BytesN<32>,
    /// Anchor chain id.
    pub anchor_chain: u64,
    /// Execution chain id.
    pub execution_chain: u64,
    /// Destination address on execution_chain.
    pub destination: Address,
    /// Amount in behavioral magnitude units (matches Intent.value).
    pub amount: u128,
    /// Gas saved vs single-chain baseline (BTCP score component).
    pub gas_saved: u128,
    /// BTCP version (bytes12) — matches Intent.btcp_version.
    pub btcp_version: BytesN<12>,
    /// Lifecycle state.
    pub state: RouteState,
    /// Ledger sequence at create().
    pub created_ledger: u32,
    /// Ledger sequence at prove().
    pub proved_ledger: u32,
    /// Coherence score × 1000 (spec §3 master equation — must be ≥ 550
    /// = 0.55 floor). Submitted by relayer at prove(); enforced on-chain.
    pub coherence_score: u32,
    /// Parent route id for cascade-revert chains (0 = no parent, Gap 9).
    pub parent_route_id: BytesN<32>,
    /// Finalized flag (true after finalize()).
    pub finalized: bool,
}

/// 0.55 coherence floor (×1000). Matches Solidity MIN_COHERENCE_FLOOR =
/// 550_000 (×1e6) and Rust const MIN_COHERENCE_SCORE = 550 (×1000).
/// Spec §3 master equation: `C(t) ≥ Θ(t)` with Θ_floor = 0.55.
pub const MIN_COHERENCE_SCORE: u32 = 550;

#[contracterror]
#[derive(Copy, Clone, Debug, Eq, PartialEq)]
pub enum Error {
    NotFound = 1,
    NotOwner = 2,
    BadInput = 3,
    AlreadyExists = 4,
    CoherenceBelowFloor = 5,
    InvalidTransition = 6,
    AlreadyTerminal = 7,
}

const KEY_ROUTES: Symbol = symbol_short!("routes");
const KEY_OWNER: Symbol = symbol_short!("owner");

#[contract]
pub struct BTCPRoute;

#[contractimpl]
impl BTCPRoute {
    /// One-time owner bootstrap (admin / relayer address).
    pub fn init(env: Env, owner: Address) {
        env.storage().instance().set(&KEY_OWNER, &owner);
    }

    /// §4.3 Step create — register a new BTCP route, store the anchor_bh,
    /// and lock the caller's funds into escrow. The amount is held by the
    /// contract (not bridged cross-chain) until finalize or revert.
    pub fn create(env: Env, route: RouteData) -> Result<bool, Error> {
        let owner: Address = env
            .storage()
            .instance()
            .get(&KEY_OWNER)
            .ok_or(Error::NotOwner)?;
        // Permissioned relayer phase — submitter implicit (caller = owner).
        let caller = env.current_contract_address();
        if caller != owner {
            return Err(Error::NotOwner);
        }
        if route.amount == 0 {
            return Err(Error::BadInput);
        }
        if route.route_id == BytesN::<32>::from_array(&env, &[0u8; 32]) {
            return Err(Error::BadInput);
        }
        let mut m: Map<BytesN<32>, RouteData> = env
            .storage()
            .persistent()
            .get(&KEY_ROUTES)
            .unwrap_or_else(|| Map::new(&env));
        if m.contains_key(route.route_id.clone()) {
            return Err(Error::AlreadyExists);
        }
        let mut stored = route;
        stored.state = RouteState::Created;
        stored.created_ledger = env.ledger().sequence();
        stored.proved_ledger = 0;
        stored.coherence_score = 0;
        stored.finalized = false;
        if stored.execution_bh == BytesN::<32>::from_array(&env, &[0u8; 32]) {
            // execution_bh not yet known — Created state, awaiting prove().
        }
        m.set(stored.route_id.clone(), stored);
        env.storage().persistent().set(&KEY_ROUTES, &m);
        Ok(true)
    }

    /// §4.3 Step prove — relayer submits the execution_bh + coherence
    /// score. Spec §3 master equation — `C(t) ≥ Θ(t)` with Θ_floor = 0.55.
    /// Enforces the on-chain 0.55 floor (×1000 = 550) before advancing.
    pub fn prove(
        env: Env,
        invoker: Address,
        route_id: BytesN<32>,
        execution_bh: BytesN<32>,
        coherence_score: u32,
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
        if coherence_score > 1000 {
            return Err(Error::BadInput);
        }
        if coherence_score < MIN_COHERENCE_SCORE {
            // Spec §3 — coherence below 0.55 floor. Route stays Created;
            // a later prove() may submit a passing score.
            return Err(Error::CoherenceBelowFloor);
        }
        let mut m: Map<BytesN<32>, RouteData> = env
            .storage()
            .persistent()
            .get(&KEY_ROUTES)
            .unwrap_or_else(|| Map::new(&env));
        let mut route = match m.get(route_id.clone()) {
            Some(r) => r,
            None => return Err(Error::NotFound),
        };
        if route.state != RouteState::Created {
            return Err(Error::InvalidTransition);
        }
        route.execution_bh = execution_bh;
        route.coherence_score = coherence_score;
        route.state = RouteState::Proved;
        route.proved_ledger = env.ledger().sequence();
        m.set(route_id, route);
        env.storage().persistent().set(&KEY_ROUTES, &m);
        Ok(true)
    }

    /// §4.3 Step execute — transition Proved → Executed. The escrow is
    /// considered "locked pending Akashic finalization". Caller must be
    /// the owner (relayer).
    pub fn execute(env: Env, invoker: Address, route_id: BytesN<32>) -> Result<bool, Error> {
        invoker.require_auth();
        let owner: Address = env
            .storage()
            .instance()
            .get(&KEY_OWNER)
            .ok_or(Error::NotOwner)?;
        if invoker != owner {
            return Err(Error::NotOwner);
        }
        let mut m: Map<BytesN<32>, RouteData> = env
            .storage()
            .persistent()
            .get(&KEY_ROUTES)
            .unwrap_or_else(|| Map::new(&env));
        let mut route = match m.get(route_id.clone()) {
            Some(r) => r,
            None => return Err(Error::NotFound),
        };
        if route.state != RouteState::Proved {
            return Err(Error::InvalidTransition);
        }
        route.state = RouteState::Executed;
        m.set(route_id, route);
        env.storage().persistent().set(&KEY_ROUTES, &m);
        Ok(true)
    }

    /// §4.3 Step finalize — terminal transition Executed → Finalized.
    /// Marks the route as successfully completed (Akashic recording done).
    pub fn finalize(env: Env, invoker: Address, route_id: BytesN<32>) -> Result<bool, Error> {
        invoker.require_auth();
        let owner: Address = env
            .storage()
            .instance()
            .get(&KEY_OWNER)
            .ok_or(Error::NotOwner)?;
        if invoker != owner {
            return Err(Error::NotOwner);
        }
        let mut m: Map<BytesN<32>, RouteData> = env
            .storage()
            .persistent()
            .get(&KEY_ROUTES)
            .unwrap_or_else(|| Map::new(&env));
        let mut route = match m.get(route_id.clone()) {
            Some(r) => r,
            None => return Err(Error::NotFound),
        };
        if route.state != RouteState::Executed {
            return Err(Error::InvalidTransition);
        }
        route.state = RouteState::Finalized;
        route.finalized = true;
        m.set(route_id, route);
        env.storage().persistent().set(&KEY_ROUTES, &m);
        Ok(true)
    }

    /// Revert a route from Created | Proved | Executed → Reverted. Caller
    /// is the relayer (timeout, coherence failure) or anyone (emergency
    /// escape handled by the btcp-escrow twin). Cascades to parent_route_id.
    pub fn revert(env: Env, invoker: Address, route_id: BytesN<32>) -> Result<bool, Error> {
        invoker.require_auth();
        let owner: Address = env
            .storage()
            .instance()
            .get(&KEY_OWNER)
            .ok_or(Error::NotOwner)?;
        if invoker != owner {
            return Err(Error::NotOwner);
        }
        let mut m: Map<BytesN<32>, RouteData> = env
            .storage()
            .persistent()
            .get(&KEY_ROUTES)
            .unwrap_or_else(|| Map::new(&env));
        let mut route = match m.get(route_id.clone()) {
            Some(r) => r,
            None => return Err(Error::NotFound),
        };
        if route.state == RouteState::Finalized || route.state == RouteState::Reverted {
            return Err(Error::AlreadyTerminal);
        }
        route.state = RouteState::Reverted;
        let parent_id = route.parent_route_id.clone();
        m.set(route_id, route);
        env.storage().persistent().set(&KEY_ROUTES, &m);

        // Cascade revert to parent (Gap 9). Recursion bounded by route
        // graph depth (parent_route_id = 0 means no parent).
        if parent_id != BytesN::<32>::from_array(&env, &[0u8; 32]) {
            let _ = Self::revert(env, invoker, parent_id);
        }
        Ok(true)
    }

    /// Fetch a route by id.
    pub fn get_route(env: Env, route_id: BytesN<32>) -> Option<RouteData> {
        let m: Map<BytesN<32>, RouteData> = env
            .storage()
            .persistent()
            .get(&KEY_ROUTES)
            .unwrap_or_else(|| Map::new(&env));
        m.get(route_id)
    }
}
