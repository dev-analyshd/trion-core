//! TRION BTCP Route — Solana Program
//!
//! Mirrors the EVM BTCPRoute.sol contract:
//!   - Route record with anchor BH, execution BH, route type
//!   - Certification validity windows (A3 Resolution)
//!   - Forward-secure validator keys (A3)
//!   - Gas savings tracking
//!
//! Instructions:
//!   RecordRoute       — record a completed BTCP route
//!   VerifyRoute       — verify a route's certification
//!   GetRouteStats     — read aggregate stats

use borsh::{BorshDeserialize, BorshSerialize};
use solana_program::{
    account_info::{next_account_info, AccountInfo},
    clock::Clock,
    entrypoint,
    entrypoint::ProgramResult,
    msg,
    program_error::ProgramError,
    pubkey::Pubkey,
    sysvar::Sysvar,
};
use thiserror::Error;

// ── Route Types ─────────────────────────────────────────────────────────────
#[derive(Clone, Copy, PartialEq, Eq, BorshSerialize, BorshDeserialize, Debug)]
#[repr(u8)]
#[borsh(use_discriminant=true)]
pub enum RouteType {
    SingleChain = 0,
    Split = 1,
    Netting = 2,
    Parallel = 3,
    MultiHop = 4,
    Deferred = 5,
}

impl Default for RouteType {
    fn default() -> Self {
        RouteType::SingleChain
    }
}

// ── Route Record ────────────────────────────────────────────────────────────
#[derive(BorshSerialize, BorshDeserialize, Debug, Default)]
pub struct Route {
    pub discriminator: [u8; 8],
    /// Route ID (32 bytes)
    pub route_id: [u8; 32],
    /// Anchor behavioral hash
    pub anchor_bh: [u8; 32],
    /// Execution behavioral hash
    pub execution_bh: [u8; 32],
    /// BEO entity identifier
    pub entity_id: [u8; 32],
    /// Anchor chain ID
    pub anchor_chain_id: u64,
    /// Execution chain ID
    pub execution_chain_id: u64,
    /// Route type
    pub route_type: u8,
    /// Gas saved vs single-chain (lamports equivalent)
    pub gas_saved_single: u64,
    /// Gas saved vs bridge
    pub gas_saved_bridge: u64,
    /// BEO continuity score (scaled by 1e6)
    pub beo_continuity: u64,
    /// Cross-chain coherence (scaled by 1e6)
    pub cc_coherence: u64,
    /// Execution confirmed
    pub execution_confirmed: bool,
    /// Certification block
    pub certification_block: u64,
    /// Certification expiry (A3 Resolution)
    pub certification_expiry: u64,
    /// Validator key version (A3: forward-secure keys)
    pub validator_key_version: [u8; 4],
    /// Recorded timestamp
    pub recorded_at: u64,
    /// Bump seed
    pub bump: u8,
}

impl Route {
    pub const LEN: usize = 8 + 32 + 32 + 32 + 32 + 8 + 8 + 1 + 8 + 8 + 8 + 8 + 1 + 8 + 8 + 4 + 8 + 1;

    pub fn route_type_enum(&self) -> Result<RouteType, ProgramError> {
        match self.route_type {
            0 => Ok(RouteType::SingleChain),
            1 => Ok(RouteType::Split),
            2 => Ok(RouteType::Netting),
            3 => Ok(RouteType::Parallel),
            4 => Ok(RouteType::MultiHop),
            5 => Ok(RouteType::Deferred),
            _ => Err(ProgramError::InvalidAccountData),
        }
    }

    pub fn is_certified(&self, current_block: u64) -> bool {
        self.execution_confirmed && current_block < self.certification_expiry
    }
}

// ── Aggregate Stats Account ─────────────────────────────────────────────────
#[derive(BorshSerialize, BorshDeserialize, Debug, Default)]
pub struct RouteStats {
    pub discriminator: [u8; 8],
    pub total_routes: u64,
    pub total_gas_saved: u64,
    pub routes_by_type: [u64; 6], // SingleChain, Split, Netting, Parallel, MultiHop, Deferred
    pub last_route_block: u64,
    pub last_route_timestamp: u64,
    pub bump: u8,
}

impl RouteStats {
    pub const LEN: usize = 8 + 8 + 8 + 48 + 8 + 8 + 1;
}

// ── Instructions ────────────────────────────────────────────────────────────
#[derive(BorshSerialize, BorshDeserialize, Debug)]
pub enum RouteInstruction {
    /// RecordRoute { route_id, anchor_bh, execution_bh, entity_id, anchor_chain, exec_chain, route_type, gas_saved, beo_continuity, cc_coherence, cert_expiry }
    RecordRoute {
        route_id: [u8; 32],
        anchor_bh: [u8; 32],
        execution_bh: [u8; 32],
        entity_id: [u8; 32],
        anchor_chain_id: u64,
        execution_chain_id: u64,
        route_type: u8,
        gas_saved_single: u64,
        beo_continuity: u64,
        cc_coherence: u64,
        certification_expiry: u64,
        validator_key_version: [u8; 4],
    },
    /// VerifyRoute
    VerifyRoute,
}

// ── Errors ──────────────────────────────────────────────────────────────────
#[derive(Error, Debug, Copy, Clone)]
pub enum RouteError {
    #[error("Route not found")]
    NotFound,
    #[error("Route not certified")]
    NotCertified,
    #[error("Certification expired")]
    CertificationExpired,
    #[error("Execution not confirmed")]
    NotConfirmed,
    #[error("Unauthorized")]
    Unauthorized,
}

impl From<RouteError> for ProgramError {
    fn from(e: RouteError) -> Self {
        ProgramError::Custom(e as u32)
    }
}

// ── Entry Point ─────────────────────────────────────────────────────────────
entrypoint!(process_instruction);

pub fn process_instruction(
    program_id: &Pubkey,
    accounts: &[AccountInfo],
    instruction_data: &[u8],
) -> ProgramResult {
    let instruction: RouteInstruction =
        RouteInstruction::try_from_slice(instruction_data).map_err(|_| ProgramError::InvalidInstructionData)?;

    match instruction {
        RouteInstruction::RecordRoute {
            route_id, anchor_bh, execution_bh, entity_id,
            anchor_chain_id, execution_chain_id, route_type,
            gas_saved_single, beo_continuity, cc_coherence,
            certification_expiry, validator_key_version,
        } => record_route(
            program_id, accounts, route_id, anchor_bh, execution_bh, entity_id,
            anchor_chain_id, execution_chain_id, route_type,
            gas_saved_single, beo_continuity, cc_coherence,
            certification_expiry, validator_key_version,
        ),
        RouteInstruction::VerifyRoute => verify_route(program_id, accounts),
    }
}

fn record_route(
    program_id: &Pubkey,
    accounts: &[AccountInfo],
    route_id: [u8; 32],
    anchor_bh: [u8; 32],
    execution_bh: [u8; 32],
    entity_id: [u8; 32],
    anchor_chain_id: u64,
    execution_chain_id: u64,
    route_type: u8,
    gas_saved_single: u64,
    beo_continuity: u64,
    cc_coherence: u64,
    certification_expiry: u64,
    validator_key_version: [u8; 4],
) -> ProgramResult {
    let account_info_iter = &mut accounts.iter();
    let route_info = next_account_info(account_info_iter)?;
    let stats_info = next_account_info(account_info_iter)?;
    let signer_info = next_account_info(account_info_iter)?;

    if route_info.owner != program_id || stats_info.owner != program_id {
        return Err(ProgramError::IncorrectProgramId);
    }

    if !signer_info.is_signer {
        return Err(RouteError::Unauthorized.into());
    }

    // Derive PDAs
    let (route_pda, route_bump) = Pubkey::find_program_address(
        &[b"route", route_id.as_ref()],
        program_id,
    );
    if route_pda != *route_info.key {
        return Err(ProgramError::InvalidSeeds);
    }

    let (stats_pda, stats_bump) = Pubkey::find_program_address(
        &[b"route_stats"],
        program_id,
    );
    if stats_pda != *stats_info.key {
        return Err(ProgramError::InvalidSeeds);
    }

    let clock = Clock::get()?;

    // Write route record
    let mut route = Route::try_from_slice(&route_info.data.borrow())?;
    route.discriminator = [b'b', b't', b'c', b'p', b'_', b'r', b't', b'e'];
    route.route_id = route_id;
    route.anchor_bh = anchor_bh;
    route.execution_bh = execution_bh;
    route.entity_id = entity_id;
    route.anchor_chain_id = anchor_chain_id;
    route.execution_chain_id = execution_chain_id;
    route.route_type = route_type;
    route.gas_saved_single = gas_saved_single;
    route.gas_saved_bridge = gas_saved_single * 3 / 2; // estimate
    route.beo_continuity = beo_continuity;
    route.cc_coherence = cc_coherence;
    route.execution_confirmed = true;
    route.certification_block = clock.slot;
    route.certification_expiry = certification_expiry;
    route.validator_key_version = validator_key_version;
    route.recorded_at = clock.unix_timestamp as u64;
    route.bump = route_bump;
    route.serialize(&mut *route_info.data.borrow_mut())?;

    // Update aggregate stats
    let mut stats = RouteStats::try_from_slice(&stats_info.data.borrow())?;
    stats.discriminator = [b'b', b't', b'c', b'p', b's', b't', b'a', b't'];
    stats.total_routes += 1;
    stats.total_gas_saved += gas_saved_single;
    if (route_type as usize) < 6 {
        stats.routes_by_type[route_type as usize] += 1;
    }
    stats.last_route_block = clock.slot;
    stats.last_route_timestamp = clock.unix_timestamp as u64;
    stats.bump = stats_bump;
    stats.serialize(&mut *stats_info.data.borrow_mut())?;

    msg!(
        "BTCP Route: recorded route_type={} gas_saved={} total_routes={}",
        route_type, gas_saved_single, stats.total_routes
    );
    Ok(())
}

fn verify_route(program_id: &Pubkey, accounts: &[AccountInfo]) -> ProgramResult {
    let account_info_iter = &mut accounts.iter();
    let route_info = next_account_info(account_info_iter)?;

    if route_info.owner != program_id {
        return Err(ProgramError::IncorrectProgramId);
    }

    let route = Route::try_from_slice(&route_info.data.borrow())?;
    let clock = Clock::get()?;

    if !route.execution_confirmed {
        return Err(RouteError::NotConfirmed.into());
    }

    if clock.slot >= route.certification_expiry {
        return Err(RouteError::CertificationExpired.into());
    }

    msg!(
        "BTCP Route: verified route_id={:?} certified until block={}",
        &route.route_id[..8], route.certification_expiry
    );
    Ok(())
}

// ── Tests ───────────────────────────────────────────────────────────────────
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_route_serialization() {
        let mut route = Route::default();
        route.route_type = RouteType::Netting as u8;
        route.execution_confirmed = true;
        let data = route.try_to_vec().unwrap();
        let decoded = Route::try_from_slice(&data).unwrap();
        assert_eq!(decoded.route_type, 2);
        assert!(decoded.execution_confirmed);
    }

    #[test]
    fn test_route_types() {
        assert_eq!(RouteType::SingleChain as u8, 0);
        assert_eq!(RouteType::Split as u8, 1);
        assert_eq!(RouteType::Netting as u8, 2);
        assert_eq!(RouteType::MultiHop as u8, 4);
        assert_eq!(RouteType::Deferred as u8, 5);
    }

    #[test]
    fn test_certification_check() {
        let mut route = Route::default();
        route.execution_confirmed = true;
        route.certification_expiry = 1000;
        assert!(route.is_certified(500));
        assert!(!route.is_certified(1001));
        route.execution_confirmed = false;
        assert!(!route.is_certified(500));
    }

    #[test]
    fn test_stats_serialization() {
        let mut stats = RouteStats::default();
        stats.total_routes = 42;
        stats.total_gas_saved = 1_000_000;
        stats.routes_by_type[2] = 10; // 10 netting routes
        let data = stats.try_to_vec().unwrap();
        let decoded = RouteStats::try_from_slice(&data).unwrap();
        assert_eq!(decoded.total_routes, 42);
        assert_eq!(decoded.routes_by_type[2], 10);
    }
}
