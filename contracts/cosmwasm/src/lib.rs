//! TRION Protocol — CosmWasm Contract
//! Combined Oracle + BTCP Escrow + Intent + Route for Cosmos chains (20 chains)
use cosmwasm_std::{
    entry_point, Deps, DepsMut, Env, MessageInfo, Response, StdResult, StdError,
    Binary, to_binary, Addr, Storage,
};
use serde::{Deserialize, Serialize};
use schemars::JsonSchema;

// ============================================================================
// State
// ============================================================================

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq, JsonSchema)]
pub struct Signal {
    pub entity_id: String,
    pub coherence: u64,     // ×1e6
    pub threshold: u64,      // ×1e6
    pub emits: bool,
    pub status: u8,          // 0=NOMINAL, 1=WARN, 2=COLLAPSE, 3=HOSTILE
    pub truth: u64,
    pub block_number: u64,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq, JsonSchema)]
pub struct Escrow {
    pub route_id: String,
    pub entity_id: String,
    pub amount: u128,
    pub state: u8, // 0=HOLDING, 1=PENDING_AKASHIC, 2=RELEASED, 3=REVERTED
    pub coherence_verified: bool,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq, JsonSchema)]
pub struct Intent {
    pub intent_hash: String,
    pub entity_id: String,
    pub source_chain: String,
    pub dest_chain: String,
    pub amount: u128,
    pub active: bool,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq, JsonSchema)]
pub struct Route {
    pub route_id: String,
    pub anchor_bh: String,   // hex
    pub execution_bh: String,
    pub entity_id: String,
    pub gas_saved: u64,
    pub finalized: bool,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq, JsonSchema)]
pub struct InstantiateMsg {
    pub admin: String,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum ExecuteMsg {
    PublishSignal {
        entity_id: String,
        coherence: u64,
        threshold: u64,
        emits: bool,
        status: u8,
        truth: u64,
    },
    LockEscrow {
        route_id: String,
        entity_id: String,
        amount: u128,
    },
    ReleaseEscrow { route_id: String },
    RevertEscrow { route_id: String },
    RegisterIntent {
        intent_hash: String,
        entity_id: String,
        source_chain: String,
        dest_chain: String,
        amount: u128,
    },
    RegisterRoute {
        route_id: String,
        anchor_bh: String,
        execution_bh: String,
        entity_id: String,
        gas_saved: u64,
    },
    FinalizeRoute { route_id: String },
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum QueryMsg {
    GetSignal { entity_id: String },
    GetEscrow { route_id: String },
    GetIntent { entity_id: String },
    GetRoute { route_id: String },
}

// ============================================================================
// Entry Points
// ============================================================================

#[entry_point]
pub fn instantiate(
    _deps: DepsMut,
    _env: Env,
    info: MessageInfo,
    msg: InstantiateMsg,
) -> StdResult<Response> {
    // Store admin
    cosmwasm_std::ensure_eq(info.sender, _deps.api.addr_validate(&msg.admin)?, StdError::generic_err("Unauthorized"))?;
    Ok(Response::new().add_attribute("method", "instantiate").add_attribute("admin", msg.admin))
}

#[entry_point]
pub fn execute(
    deps: DepsMut,
    env: Env,
    info: MessageInfo,
    msg: ExecuteMsg,
) -> StdResult<Response> {
    match msg {
        ExecuteMsg::PublishSignal { entity_id, coherence, threshold, emits, status, truth } => {
            let sig = Signal { entity_id: entity_id.clone(), coherence, threshold, emits, status, truth, block_number: env.block.height };
            deps.storage.set(signal_key(&entity_id).as_slice(), &to_binary(&sig)?);
            Ok(Response::new().add_attribute("method", "publish_signal").add_attribute("entity", entity_id))
        }
        ExecuteMsg::LockEscrow { route_id, entity_id, amount } => {
            let esc = Escrow { route_id: route_id.clone(), entity_id, amount, state: 0, coherence_verified: false };
            deps.storage.set(escrow_key(&route_id).as_slice(), &to_binary(&esc)?);
            Ok(Response::new().add_attribute("method", "lock_escrow").add_attribute("route", route_id))
        }
        ExecuteMsg::ReleaseEscrow { route_id } => {
            let key = escrow_key(&route_id);
            let mut esc: Escrow = cosmwasm_std::from_binary(
                &deps.storage.get(key.as_slice()).ok_or(StdError::not_found("Escrow"))?
            )?;
            esc.state = 2; // RELEASED
            esc.coherence_verified = true;
            deps.storage.set(key.as_slice(), &to_binary(&esc)?);
            Ok(Response::new().add_attribute("method", "release_escrow"))
        }
        ExecuteMsg::RevertEscrow { route_id } => {
            let key = escrow_key(&route_id);
            let mut esc: Escrow = cosmwasm_std::from_binary(
                &deps.storage.get(key.as_slice()).ok_or(StdError::not_found("Escrow"))?
            )?;
            esc.state = 3; // REVERTED
            deps.storage.set(key.as_slice(), &to_binary(&esc)?);
            Ok(Response::new().add_attribute("method", "revert_escrow"))
        }
        ExecuteMsg::RegisterIntent { intent_hash, entity_id, source_chain, dest_chain, amount } => {
            let intent = Intent { intent_hash, entity_id: entity_id.clone(), source_chain, dest_chain, amount, active: true };
            deps.storage.set(intent_key(&entity_id).as_slice(), &to_binary(&intent)?);
            Ok(Response::new().add_attribute("method", "register_intent"))
        }
        ExecuteMsg::RegisterRoute { route_id, anchor_bh, execution_bh, entity_id, gas_saved } => {
            let route = Route { route_id: route_id.clone(), anchor_bh, execution_bh, entity_id, gas_saved, finalized: false };
            deps.storage.set(route_key(&route_id).as_slice(), &to_binary(&route)?);
            Ok(Response::new().add_attribute("method", "register_route"))
        }
        ExecuteMsg::FinalizeRoute { route_id } => {
            let key = route_key(&route_id);
            let mut route: Route = cosmwasm_std::from_binary(
                &deps.storage.get(key.as_slice()).ok_or(StdError::not_found("Route"))?
            )?;
            route.finalized = true;
            deps.storage.set(key.as_slice(), &to_binary(&route)?);
            Ok(Response::new().add_attribute("method", "finalize_route"))
        }
    }
}

#[entry_point]
pub fn query(deps: Deps, _env: Env, msg: QueryMsg) -> StdResult<Binary> {
    match msg {
        QueryMsg::GetSignal { entity_id } => {
            let sig: Signal = cosmwasm_std::from_binary(
                &deps.storage.get(signal_key(&entity_id).as_slice()).ok_or(StdError::not_found("Signal"))?
            )?;
            to_binary(&sig)
        }
        QueryMsg::GetEscrow { route_id } => {
            let esc: Escrow = cosmwasm_std::from_binary(
                &deps.storage.get(escrow_key(&route_id).as_slice()).ok_or(StdError::not_found("Escrow"))?
            )?;
            to_binary(&esc)
        }
        QueryMsg::GetIntent { entity_id } => {
            let intent: Intent = cosmwasm_std::from_binary(
                &deps.storage.get(intent_key(&entity_id).as_slice()).ok_or(StdError::not_found("Intent"))?
            )?;
            to_binary(&intent)
        }
        QueryMsg::GetRoute { route_id } => {
            let route: Route = cosmwasm_std::from_binary(
                &deps.storage.get(route_key(&route_id).as_slice()).ok_or(StdError::not_found("Route"))?
            )?;
            to_binary(&route)
        }
    }
}

// ============================================================================
// Storage key helpers
// ============================================================================

fn signal_key(entity_id: &str) -> Vec<u8> {
    let mut key = b"s::".to_vec();
    key.extend(entity_id.as_bytes());
    key
}

fn escrow_key(route_id: &str) -> Vec<u8> {
    let mut key = b"e::".to_vec();
    key.extend(route_id.as_bytes());
    key
}

fn intent_key(entity_id: &str) -> Vec<u8> {
    let mut key = b"i::".to_vec();
    key.extend(entity_id.as_bytes());
    key
}

fn route_key(route_id: &str) -> Vec<u8> {
    let mut key = b"r::".to_vec();
    key.extend(route_id.as_bytes());
    key
}
