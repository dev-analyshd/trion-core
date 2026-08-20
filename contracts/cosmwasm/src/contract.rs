//! TRION CosmWasm — Combined TRION Protocol Contract
//! =================================================
//! Implements TRIONOracleV3 + BTCPEscrow + BTCPIntent + BTCPRoute +
//! TRIONExecutionGate logic in a single CosmWasm contract. This is the
//! canonical deployment for the 20 CosmWasm VM chains (Neutron, Archway,
//! Osmosis wasm, Juno, Terra 2, Kujira, Stargaze, Comdex, Crescent,
//! Persistence, Injective wasm, Migaloo, Celestia wasm, Nolus, Sei wasm,
//! Loki, Mantra, etc.).
//!
//! Mirrors contracts/solidity/{TRIONOracleV3,BTCPEscrow,BTCPIntent,BTCPRoute,
//! TRIONExecutionGate}.sol + the Move VM equivalents in contracts/move/.

use cosmwasm_std::{
    entry_point, Addr, BankMsg, Coin, Deps, DepsMut, Env, MessageInfo, Response, StdError,
    StdResult, Storage, Uint128,
};
use serde_json::to_vec;

use crate::state::{
    BTCPRoute, Escrow, GateState, Intent, Route, Signal,
    PREFIX_ESCROWS, PREFIX_INTENTS, PREFIX_ROUTES, PREFIX_SIGNALS,
    STATE_HOLDING, STATE_RELEASED, STATE_REVERTED,
    STATUS_PENDING, STATUS_ROUTING, STATUS_EXECUTING, STATUS_COMPLETED,
    STATUS_FAILED, STATUS_EXPIRED, STATUS_RESURRECTED,
};

// ── Instantiate / Execute / Query message types ──────────────────────────────

#[derive(serde::Serialize, serde::Deserialize, Clone, Debug)]
pub struct InstantiateMsg {
    pub owner:        String,
    pub relayer:      String,
    pub awa_enforced: bool,
}

#[derive(serde::Serialize, serde::Deserialize, Clone, Debug)]
#[serde(rename_all = "snake_case")]
pub enum ExecuteMsg {
    // ── Oracle ───────────────────────────────────────────────────────────────
    PublishSignal {
        entity_id: Vec<u8>,
        coherence: u64,
        threshold: u64,
        emits:     bool,
    },
    PublishBtcpRoute {
        route_id:     Vec<u8>,
        anchor_bh:    Vec<u8>,
        execution_bh: Vec<u8>,
        coherence:    u64,
        threshold:    u64,
    },
    // ── Escrow ───────────────────────────────────────────────────────────────
    LockEscrow {
        escrow_id:      Vec<u8>,
        route_id:       Vec<u8>,
        entity_id:      Vec<u8>,
        destination:    String,
        min_coherence:  u64,
        timeout_blocks: u64,
    },
    ReleaseEscrow {
        escrow_id:    Vec<u8>,
        execution_bh: Vec<u8>,
        coherence:    u64,
    },
    RevertEscrow {
        escrow_id: Vec<u8>,
        reason:    u8,
    },
    // ── Intent ───────────────────────────────────────────────────────────────
    RegisterIntent {
        intent_hash:  Vec<u8>,
        entity_id:   Vec<u8>,
        action:       u8,
        asset_in:     Vec<u8>,
        asset_out:    Vec<u8>,
        magnitude:    u64,
        source_chain: u64,
        dest_chain:   u64,
        deadline:     u64,
        max_gas_usd:  u64,
        min_nl_score: u16,
        nonce:        u64,
    },
    UpdateIntentStatus {
        intent_hash: Vec<u8>,
        new_status:  u8,
    },
    // ── Route ─────────────────────────────────────────────────────────────────
    RegisterRoute {
        route_id:        Vec<u8>,
        intent_hash:     Vec<u8>,
        anchor_bh:       Vec<u8>,
        anchor_chain:    u64,
        execution_chain: u64,
        entity_id:       Vec<u8>,
        route_type:      u8,
    },
    FinalizeRoute {
        route_id:            Vec<u8>,
        execution_bh:        Vec<u8>,
        gas_saved_vs_bridge: u64,
        beo_continuity:      u64,
        cc_coherence:        u64,
    },
    // ── Execution Gate ─────────────────────────────────────────────────────────
    SetGateThreshold {
        gate_id:   Vec<u8>,
        threshold: u64,
    },
    CheckExecution {
        gate_id:          Vec<u8>,
        entity_id:        Vec<u8>,
        phi:              u64,
        route_threshold:  u64,
    },
    // ── Admin ────────────────────────────────────────────────────────────────
    SetRelayer { new_relayer: String },
    SetAwaEnforced { enforced: bool },
}

#[derive(serde::Serialize, serde::Deserialize, Clone, Debug)]
#[serde(rename_all = "snake_case")]
pub enum QueryMsg {
    GetSignal        { entity_id: Vec<u8> },
    GetBtcpRoute     { route_id:  Vec<u8> },
    VerifyExecution  { route_id:  Vec<u8> },
    GetEscrow        { escrow_id: Vec<u8> },
    GetIntent        { intent_hash: Vec<u8> },
    GetRoute         { route_id:  Vec<u8> },
    GetGate          { gate_id:   Vec<u8> },
    GetOwner         {},
    GetRelayer       {},
    AwaEnforced      {},
}

// ── Storage helpers ───────────────────────────────────────────────────────────

fn write_owner(storage: &mut dyn Storage, addr: &Addr) -> StdResult<()> {
    storage.set(b"trion::owner", &addr.as_bytes())
}
fn read_owner(storage: &dyn Storage) -> StdResult<Addr> {
    let bytes = storage.get(b"trion::owner")
        .ok_or_else(|| StdError::not_found("owner"))?;
    let s = String::from_utf8(bytes)?;
    Addr::try_from(s).map_err(|e| StdError::generic_err(e.to_string()))
}
fn write_relayer(storage: &mut dyn Storage, addr: &Addr) -> StdResult<()> {
    storage.set(b"trion::relayer", &addr.as_bytes())
}
fn read_relayer(storage: &dyn Storage) -> StdResult<Addr> {
    let bytes = storage.get(b"trion::relayer")
        .ok_or_else(|| StdError::not_found("relayer"))?;
    let s = String::from_utf8(bytes)?;
    Addr::try_from(s).map_err(|e| StdError::generic_err(e.to_string()))
}
fn write_awa(storage: &mut dyn Storage, enforced: bool) -> StdResult<()> {
    storage.set(b"trion::awa_enforced", &[if enforced { 1u8 } else { 0u8 }])
}
fn read_awa(storage: &dyn Storage) -> bool {
    storage.get(b"trion::awa_enforced").map(|v| !v.is_empty() && v[0] != 0).unwrap_or(false)
}

fn key(prefix: &[u8], id: &[u8]) -> Vec<u8> {
    let mut k = Vec::with_capacity(prefix.len() + id.len());
    k.extend_from_slice(prefix);
    k.extend_from_slice(id);
    k
}

fn require_owner(deps: &DepsMut, info: &MessageInfo) -> StdResult<()> {
    let owner = read_owner(deps.storage)?;
    if info.sender != owner {
        return Err(StdError::generic_err("TRION: not authorized (owner only)"));
    }
    Ok(())
}

fn require_owner_or_relayer(deps: &DepsMut, info: &MessageInfo) -> StdResult<()> {
    let owner   = read_owner(deps.storage)?;
    let relayer = read_relayer(deps.storage)?;
    if info.sender != owner && info.sender != relayer {
        return Err(StdError::generic_err("TRION: not authorized (owner/relayer only)"));
    }
    Ok(())
}

// ── Entry points ─────────────────────────────────────────────────────────────

#[entry_point]
pub fn instantiate(
    deps:   DepsMut,
    _env:   Env,
    _info:  MessageInfo,
    msg:    InstantiateMsg,
) -> StdResult<Response> {
    let owner   = deps.api.addr_validate(&msg.owner)?;
    let relayer = deps.api.addr_validate(&msg.relayer)?;
    write_owner(deps.storage, &owner)?;
    write_relayer(deps.storage, &relayer)?;
    write_awa(deps.storage, msg.awa_enforced)?;
    Ok(Response::new()
        .add_attribute("action",    "instantiate")
        .add_attribute("owner",     owner)
        .add_attribute("relayer",   relayer)
        .add_attribute("awa_enforced", msg.awa_enforced.to_string()))
}

#[entry_point]
pub fn execute(
    deps:  DepsMut,
    env:   Env,
    info:  MessageInfo,
    msg:   ExecuteMsg,
) -> StdResult<Response> {
    match msg {
        // ── Oracle ───────────────────────────────────────────────────────────
        ExecuteMsg::PublishSignal { entity_id, coherence, threshold, emits } =>
            execute_publish_signal(deps, env, info, entity_id, coherence, threshold, emits),
        ExecuteMsg::PublishBtcpRoute { route_id, anchor_bh, execution_bh, coherence, threshold } =>
            execute_publish_btcp_route(deps, env, info, route_id, anchor_bh, execution_bh, coherence, threshold),
        // ── Escrow ───────────────────────────────────────────────────────────
        ExecuteMsg::LockEscrow { escrow_id, route_id, entity_id, destination, min_coherence, timeout_blocks } =>
            execute_lock_escrow(deps, env, info, escrow_id, route_id, entity_id, destination, min_coherence, timeout_blocks),
        ExecuteMsg::ReleaseEscrow { escrow_id, execution_bh, coherence } =>
            execute_release_escrow(deps, env, info, escrow_id, execution_bh, coherence),
        ExecuteMsg::RevertEscrow { escrow_id, reason } =>
            execute_revert_escrow(deps, env, info, escrow_id, reason),
        // ── Intent ───────────────────────────────────────────────────────────
        ExecuteMsg::RegisterIntent { intent_hash, entity_id, action, asset_in, asset_out, magnitude, source_chain, dest_chain, deadline, max_gas_usd, min_nl_score, nonce } =>
            execute_register_intent(deps, env, info, intent_hash, entity_id, action, asset_in, asset_out, magnitude, source_chain, dest_chain, deadline, max_gas_usd, min_nl_score, nonce),
        ExecuteMsg::UpdateIntentStatus { intent_hash, new_status } =>
            execute_update_intent_status(deps, env, info, intent_hash, new_status),
        // ── Route ────────────────────────────────────────────────────────────
        ExecuteMsg::RegisterRoute { route_id, intent_hash, anchor_bh, anchor_chain, execution_chain, entity_id, route_type } =>
            execute_register_route(deps, env, info, route_id, intent_hash, anchor_bh, anchor_chain, execution_chain, entity_id, route_type),
        ExecuteMsg::FinalizeRoute { route_id, execution_bh, gas_saved_vs_bridge, beo_continuity, cc_coherence } =>
            execute_finalize_route(deps, env, info, route_id, execution_bh, gas_saved_vs_bridge, beo_continuity, cc_coherence),
        // ── Gate ─────────────────────────────────────────────────────────────
        ExecuteMsg::SetGateThreshold { gate_id, threshold } =>
            execute_set_gate_threshold(deps, env, info, gate_id, threshold),
        ExecuteMsg::CheckExecution { gate_id, entity_id, phi, route_threshold } =>
            execute_check_execution(deps, env, info, gate_id, entity_id, phi, route_threshold),
        // ── Admin ────────────────────────────────────────────────────────────
        ExecuteMsg::SetRelayer { new_relayer } => {
            require_owner(&deps, &info)?;
            let addr = deps.api.addr_validate(&new_relayer)?;
            write_relayer(deps.storage, &addr)?;
            Ok(Response::new().add_attribute("action", "set_relayer").add_attribute("relayer", addr))
        }
        ExecuteMsg::SetAwaEnforced { enforced } => {
            require_owner(&deps, &info)?;
            write_awa(deps.storage, enforced)?;
            Ok(Response::new().add_attribute("action", "set_awa_enforced").add_attribute("enforced", enforced.to_string()))
        }
    }
}

// ── Oracle impl ──────────────────────────────────────────────────────────────

fn execute_publish_signal(
    deps:      DepsMut,
    env:       Env,
    info:      MessageInfo,
    entity_id: Vec<u8>,
    coherence: u64,
    threshold: u64,
    emits:     bool,
) -> StdResult<Response> {
    require_owner_or_relayer(&deps, &info)?;
    if coherence > 1_000_000 || threshold > 1_000_000 {
        return Err(StdError::generic_err("TRION: invalid coherence/threshold"));
    }
    let k = key(PREFIX_SIGNALS, &entity_id);
    let existing = deps.storage.get(&k);
    let update_count = existing.as_ref()
        .and_then(|v| serde_json::from_slice::<Signal>(v).ok())
        .map(|s: Signal| s.update_count + 1)
        .unwrap_or(1);
    let sig = Signal {
        entity_id: entity_id.clone(),
        coherence,
        threshold,
        emits_signal: emits,
        timestamp: env.block.time.seconds(),
        update_count,
    };
    deps.storage.set(&k, &to_vec(&sig)?);
    Ok(Response::new()
        .add_attribute("action", "publish_signal")
        .add_attribute("coherence", coherence.to_string())
        .add_attribute("threshold", threshold.to_string())
        .add_attribute("emits", emits.to_string()))
}

fn execute_publish_btcp_route(
    deps:        DepsMut,
    env:         Env,
    info:        MessageInfo,
    route_id:    Vec<u8>,
    anchor_bh:   Vec<u8>,
    execution_bh:Vec<u8>,
    coherence:   u64,
    threshold:   u64,
) -> StdResult<Response> {
    require_owner_or_relayer(&deps, &info)?;
    if coherence > 1_000_000 || threshold > 1_000_000 {
        return Err(StdError::generic_err("TRION: invalid score"));
    }
    let k = key(PREFIX_SIGNALS, &route_id);  // BTCP routes share the signals namespace
    if deps.storage.get(&k).is_some() {
        return Err(StdError::generic_err("TRION: route exists"));
    }
    let route = BTCPRoute {
        route_id:     route_id.clone(),
        anchor_bh,
        execution_bh,
        coherence,
        threshold,
        is_safe: coherence >= threshold,
        timestamp: env.block.time.seconds(),
    };
    deps.storage.set(&k, &to_vec(&route)?);
    Ok(Response::new()
        .add_attribute("action", "publish_btcp_route")
        .add_attribute("is_safe", (coherence >= threshold).to_string()))
}

// ── Escrow impl ──────────────────────────────────────────────────────────────

fn execute_lock_escrow(
    deps:          DepsMut,
    env:           Env,
    info:          MessageInfo,
    escrow_id:     Vec<u8>,
    route_id:      Vec<u8>,
    entity_id:     Vec<u8>,
    destination:   String,
    min_coherence: u64,
    timeout_blocks:u64,
) -> StdResult<Response> {
    require_owner_or_relayer(&deps, &info)?;
    if info.funds.is_empty() {
        return Err(StdError::generic_err("TRION: zero amount"));
    }
    if min_coherence > 1_000_000 {
        return Err(StdError::generic_err("TRION: invalid coherence"));
    }
    if timeout_blocks == 0 {
        return Err(StdError::generic_err("TRION: zero timeout"));
    }
    let dest_addr = deps.api.addr_validate(&destination)?;

    let k = key(PREFIX_ESCROWS, &escrow_id);
    if deps.storage.get(&k).is_some() {
        return Err(StdError::generic_err("TRION: escrow exists"));
    }
    let amount_u128: u128 = info.funds.iter()
        .map(|c| c.amount.u128())
        .sum::<u128>().min(u128::MAX);

    let esc = Escrow {
        escrow_id:      escrow_id.clone(),
        route_id,
        entity_id,
        destination:    dest_addr,
        amount:         amount_u128,
        min_coherence,
        lock_height:    env.block.height,
        timeout_blocks,
        state:          STATE_HOLDING,
        revert_reason:  0,
        settled_at:     0,
        reverted_at:    0,
        locked_by:      info.sender.clone(),
    };
    deps.storage.set(&k, &to_vec(&esc)?);

    Ok(Response::new()
        .add_attribute("action", "lock_escrow")
        .add_attribute("amount", amount_u128.to_string()))
}

fn execute_release_escrow(
    deps:        DepsMut,
    env:         Env,
    info:        MessageInfo,
    escrow_id:   Vec<u8>,
    execution_bh:Vec<u8>,
    coherence:   u64,
) -> StdResult<Response> {
    require_owner_or_relayer(&deps, &info)?;
    let k = key(PREFIX_ESCROWS, &escrow_id);
    let mut esc: Escrow = serde_json::from_slice(
        &deps.storage.get(&k).ok_or_else(|| StdError::generic_err("TRION: escrow not found"))?
    )?;
    if esc.state != STATE_HOLDING {
        return Err(StdError::generic_err("TRION: not holding"));
    }
    if env.block.height > esc.lock_height + esc.timeout_blocks {
        return Err(StdError::generic_err("TRION: expired"));
    }
    if coherence < esc.min_coherence {
        return Err(StdError::generic_err("TRION: coherence insufficient"));
    }
    esc.state       = STATE_RELEASED;
    esc.settled_at  = env.block.time.seconds();
    deps.storage.set(&k, &to_vec(&esc)?);

    // Send the locked funds to the destination
    let coins: Vec<Coin> = vec![Coin {
        denom:  "uatom".to_string(), // denom tracked from lock_escrow; simplified
        amount: Uint128::new(esc.amount),
    }];
    Ok(Response::new()
        .add_message(BankMsg::Send { to_address: esc.destination.to_string(), amount: coins })
        .add_attribute("action", "release_escrow")
        .add_attribute("execution_bh_len", execution_bh.len().to_string()))
}

fn execute_revert_escrow(
    deps:      DepsMut,
    env:       Env,
    info:      MessageInfo,
    escrow_id: Vec<u8>,
    reason:    u8,
) -> StdResult<Response> {
    let k = key(PREFIX_ESCROWS, &escrow_id);
    let mut esc: Escrow = serde_json::from_slice(
        &deps.storage.get(&k).ok_or_else(|| StdError::generic_err("TRION: escrow not found"))?
    )?;
    if esc.state != STATE_HOLDING {
        return Err(StdError::generic_err("TRION: not holding"));
    }
    let is_timeout = env.block.height > esc.lock_height + esc.timeout_blocks;
    if !is_timeout {
        require_owner_or_relayer(&deps, &info)?;
        if reason == 0 {
            return Err(StdError::generic_err("TRION: not timeout"));
        }
    }
    esc.state         = STATE_REVERTED;
    esc.revert_reason = reason;
    esc.reverted_at   = env.block.time.seconds();
    deps.storage.set(&k, &to_vec(&esc)?);

    let coins: Vec<Coin> = vec![Coin {
        denom:  "uatom".to_string(),
        amount: Uint128::new(esc.amount),
    }];
    Ok(Response::new()
        .add_message(BankMsg::Send { to_address: esc.locked_by.to_string(), amount: coins })
        .add_attribute("action", "revert_escrow")
        .add_attribute("reason", reason.to_string()))
}

// ── Intent impl ───────────────────────────────────────────────────────────────

fn execute_register_intent(
    deps:         DepsMut,
    env:          Env,
    info:         MessageInfo,
    intent_hash:  Vec<u8>,
    entity_id:    Vec<u8>,
    action:       u8,
    asset_in:     Vec<u8>,
    asset_out:    Vec<u8>,
    magnitude:    u64,
    source_chain: u64,
    dest_chain:   u64,
    deadline:     u64,
    max_gas_usd:  u64,
    min_nl_score: u16,
    nonce:        u64,
) -> StdResult<Response> {
    require_owner_or_relayer(&deps, &info)?;
    if action > 4 {
        return Err(StdError::generic_err("TRION: invalid action"));
    }
    if magnitude == 0 {
        return Err(StdError::generic_err("TRION: zero magnitude"));
    }
    let k = key(PREFIX_INTENTS, &intent_hash);
    if deps.storage.get(&k).is_some() {
        return Err(StdError::generic_err("TRION: intent exists"));
    }
    if deadline <= env.block.time.seconds() {
        return Err(StdError::generic_err("TRION: deadline past"));
    }
    let intent = Intent {
        intent_hash,
        entity_id,
        action,
        asset_in,
        asset_out,
        magnitude,
        source_chain,
        dest_chain,
        deadline,
        max_gas_usd,
        min_nl_score,
        nonce,
        status:     STATUS_PENDING,
        created_at: env.block.time.seconds(),
        submitter:  info.sender.clone(),
    };
    deps.storage.set(&k, &to_vec(&intent)?);
    Ok(Response::new().add_attribute("action", "register_intent"))
}

fn execute_update_intent_status(
    deps:        DepsMut,
    _env:        Env,
    info:        MessageInfo,
    intent_hash: Vec<u8>,
    new_status:  u8,
) -> StdResult<Response> {
    require_owner_or_relayer(&deps, &info)?;
    let k = key(PREFIX_INTENTS, &intent_hash);
    let mut it: Intent = serde_json::from_slice(
        &deps.storage.get(&k).ok_or_else(|| StdError::generic_err("TRION: intent not found"))?
    )?;
    if !valid_transition(it.status, new_status) {
        return Err(StdError::generic_err("TRION: invalid transition"));
    }
    it.status = new_status;
    deps.storage.set(&k, &to_vec(&it)?);
    Ok(Response::new()
        .add_attribute("action", "update_intent_status")
        .add_attribute("new_status", new_status.to_string()))
}

fn valid_transition(from: u8, to: u8) -> bool {
    match from {
        s if s == STATUS_PENDING    => matches!(to, 1 | 4 | 5),
        s if s == STATUS_ROUTING    => matches!(to, 2 | 4 | 5),
        s if s == STATUS_EXECUTING  => matches!(to, 3 | 4),
        s if s == STATUS_FAILED     => to == STATUS_RESURRECTED,
        _ => false,
    }
}

// ── Route impl ───────────────────────────────────────────────────────────────

fn execute_register_route(
    deps:            DepsMut,
    env:             Env,
    info:            MessageInfo,
    route_id:        Vec<u8>,
    intent_hash:     Vec<u8>,
    anchor_bh:       Vec<u8>,
    anchor_chain:    u64,
    execution_chain: u64,
    entity_id:       Vec<u8>,
    route_type:      u8,
) -> StdResult<Response> {
    require_owner_or_relayer(&deps, &info)?;
    if anchor_bh.is_empty() {
        return Err(StdError::generic_err("TRION: zero anchor"));
    }
    if route_type > 6 {
        return Err(StdError::generic_err("TRION: invalid type"));
    }
    let k = key(PREFIX_ROUTES, &route_id);
    if deps.storage.get(&k).is_some() {
        return Err(StdError::generic_err("TRION: route exists"));
    }
    let route = Route {
        route_id:             route_id.clone(),
        intent_hash,
        anchor_bh,
        execution_bh:         Vec::new(),
        anchor_chain,
        execution_chain,
        entity_id,
        gas_saved_vs_bridge:  0,
        beo_continuity:       0,
        cc_coherence:         0,
        route_type,
        is_verified:          false,
        created_at:           env.block.time.seconds(),
        finalized_at:         0,
    };
    deps.storage.set(&k, &to_vec(&route)?);
    Ok(Response::new().add_attribute("action", "register_route"))
}

fn execute_finalize_route(
    deps:                DepsMut,
    env:                 Env,
    info:                MessageInfo,
    route_id:            Vec<u8>,
    execution_bh:        Vec<u8>,
    gas_saved_vs_bridge: u64,
    beo_continuity:      u64,
    cc_coherence:        u64,
) -> StdResult<Response> {
    require_owner_or_relayer(&deps, &info)?;
    if execution_bh.is_empty() {
        return Err(StdError::generic_err("TRION: zero exec bh"));
    }
    if beo_continuity > 1_000_000 || cc_coherence > 1_000_000 {
        return Err(StdError::generic_err("TRION: invalid score"));
    }
    let k = key(PREFIX_ROUTES, &route_id);
    let mut r: Route = serde_json::from_slice(
        &deps.storage.get(&k).ok_or_else(|| StdError::generic_err("TRION: route not found"))?
    )?;
    if r.is_verified {
        return Err(StdError::generic_err("TRION: already verified"));
    }
    r.execution_bh          = execution_bh;
    r.gas_saved_vs_bridge   = gas_saved_vs_bridge;
    r.beo_continuity        = beo_continuity;
    r.cc_coherence          = cc_coherence;
    r.is_verified           = true;
    r.finalized_at          = env.block.time.seconds();
    deps.storage.set(&k, &to_vec(&r)?);
    Ok(Response::new().add_attribute("action", "finalize_route"))
}

// ── Gate impl ─────────────────────────────────────────────────────────────────

fn execute_set_gate_threshold(
    deps:      DepsMut,
    _env:      Env,
    info:      MessageInfo,
    gate_id:   Vec<u8>,
    threshold: u64,
) -> StdResult<Response> {
    require_owner(&deps, &info)?;
    if threshold > 1_000_000 {
        return Err(StdError::generic_err("TRION: invalid score"));
    }
    let k = key(b"trion::gates::", &gate_id);
    let mut g: GateState = match deps.storage.get(&k) {
        Some(v) => serde_json::from_slice(&v)?,
        None => GateState {
            gate_id: gate_id.clone(),
            custom_threshold: 0,
            check_count: 0,
            pass_count: 0,
            block_count: 0,
            last_phi: 0,
            last_entity: Vec::new(),
        },
    };
    g.custom_threshold = threshold;
    deps.storage.set(&k, &to_vec(&g)?);
    Ok(Response::new().add_attribute("action", "set_gate_threshold"))
}

fn execute_check_execution(
    deps:           DepsMut,
    _env:           Env,
    info:           MessageInfo,
    gate_id:        Vec<u8>,
    entity_id:      Vec<u8>,
    phi:            u64,
    route_threshold:u64,
) -> StdResult<Response> {
    if !read_awa(deps.storage) {
        return Err(StdError::generic_err("TRION: AWA not enforced"));
    }
    let k = key(b"trion::gates::", &gate_id);
    let mut g: GateState = match deps.storage.get(&k) {
        Some(v) => serde_json::from_slice(&v)?,
        None => GateState {
            gate_id: gate_id.clone(),
            custom_threshold: 0,
            check_count: 0,
            pass_count: 0,
            block_count: 0,
            last_phi: 0,
            last_entity: Vec::new(),
        },
    };
    let threshold = if g.custom_threshold > 0 { g.custom_threshold } else { route_threshold };
    g.check_count += 1;
    g.last_phi     = phi;
    g.last_entity  = entity_id.clone();
    let passed = phi >= threshold;
    if passed {
        g.pass_count += 1;
    } else {
        g.block_count += 1;
    }
    deps.storage.set(&k, &to_vec(&g)?);
    if !passed {
        return Err(StdError::generic_err("TRION: gate blocked"));
    }
    Ok(Response::new()
        .add_attribute("action", "check_execution")
        .add_attribute("passed", "true")
        .add_attribute("phi", phi.to_string())
        .add_attribute("threshold", threshold.to_string()))
}

// ── Query ─────────────────────────────────────────────────────────────────────

#[entry_point]
pub fn query(deps: Deps, env: Env, msg: QueryMsg) -> StdResult<cosmwasm_std::Binary> {
    match msg {
        QueryMsg::GetSignal { entity_id } => {
            let k = key(PREFIX_SIGNALS, &entity_id);
            match deps.storage.get(&k) {
                Some(v) => {
                    let sig: Signal = serde_json::from_slice(&v)?;
                    Ok(cosmwasm_std::to_json_binary(&sig)?)
                }
                None => Err(StdError::not_found("signal")),
            }
        }
        QueryMsg::GetBtcpRoute { route_id } | QueryMsg::VerifyExecution { route_id } => {
            let k = key(PREFIX_SIGNALS, &route_id);
            match deps.storage.get(&k) {
                Some(v) => {
                    let r: BTCPRoute = serde_json::from_slice(&v)?;
                    Ok(cosmwasm_std::to_json_binary(&r)?)
                }
                None => Err(StdError::not_found("btcp_route")),
            }
        }
        QueryMsg::GetEscrow { escrow_id } => {
            let k = key(PREFIX_ESCROWS, &escrow_id);
            match deps.storage.get(&k) {
                Some(v) => {
                    let e: Escrow = serde_json::from_slice(&v)?;
                    Ok(cosmwasm_std::to_json_binary(&e)?)
                }
                None => Err(StdError::not_found("escrow")),
            }
        }
        QueryMsg::GetIntent { intent_hash } => {
            let k = key(PREFIX_INTENTS, &intent_hash);
            match deps.storage.get(&k) {
                Some(v) => {
                    let i: Intent = serde_json::from_slice(&v)?;
                    Ok(cosmwasm_std::to_json_binary(&i)?)
                }
                None => Err(StdError::not_found("intent")),
            }
        }
        QueryMsg::GetRoute { route_id } => {
            let k = key(PREFIX_ROUTES, &route_id);
            match deps.storage.get(&k) {
                Some(v) => {
                    let r: Route = serde_json::from_slice(&v)?;
                    Ok(cosmwasm_std::to_json_binary(&r)?)
                }
                None => Err(StdError::not_found("route")),
            }
        }
        QueryMsg::GetGate { gate_id } => {
            let k = key(b"trion::gates::", &gate_id);
            match deps.storage.get(&k) {
                Some(v) => {
                    let g: GateState = serde_json::from_slice(&v)?;
                    Ok(cosmwasm_std::to_json_binary(&g)?)
                }
                None => Err(StdError::not_found("gate")),
            }
        }
        QueryMsg::GetOwner {} => {
            Ok(cosmwasm_std::to_json_binary(&read_owner(deps.storage)?)?)
        }
        QueryMsg::GetRelayer {} => {
            Ok(cosmwasm_std::to_json_binary(&read_relayer(deps.storage)?)?)
        }
        QueryMsg::AwaEnforced {} => {
            let _ = env;
            Ok(cosmwasm_std::to_json_binary(&read_awa(deps.storage))?)
        }
    }
}
