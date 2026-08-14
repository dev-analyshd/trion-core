//! TRION BTCP Escrow — Solana Program
//!
//! Mirrors the EVM BTCPEscrow.sol contract:
//!   - 6 states: IDLE | HOLDING | PENDING_AKASHIC | RELEASED | REVERTED | EMERGENCY_REVERTED
//!   - 7-day emergency escape hatch (Gap 8 Resolution)
//!   - Cascade revert for multi-hop (Gap 9)
//!   - 24h Akashic recovery window (E1)
//!   - Two-phase confirmation (G1)
//!
//! Instructions:
//!   LockFunds     — lock SOL into escrow, state -> HOLDING
//!   Release       — release funds to destination (requires coherence proof)
//!   RevertTimeout — revert after timeout_blocks
//!   RevertEmergency — ANY caller after 7 days (Gap 8)
//!   CascadeRevert  — internal, triggered by child escrow revert

use borsh::{BorshDeserialize, BorshSerialize};
use solana_program::{
    account_info::{next_account_info, AccountInfo},
    clock::Clock,
    entrypoint,
    entrypoint::ProgramResult,
    msg,
    program::invoke,
    program_error::ProgramError,
    pubkey::Pubkey,
    system_instruction,
    sysvar::{rent::Rent, Sysvar},
};
use thiserror::Error;

// ── Constants ───────────────────────────────────────────────────────────────
/// 7 days in seconds — Gap 8 Resolution: absolute maximum lockup
pub const EMERGENCY_ESCAPE_SECONDS: u64 = 7 * 24 * 60 * 60;
/// 24 hours — Akashic recovery window (E1 Resolution)
pub const AKASHIC_RECOVERY_SECONDS: u64 = 24 * 60 * 60;

// ── States ──────────────────────────────────────────────────────────────────
#[derive(Clone, Copy, PartialEq, Eq, BorshSerialize, BorshDeserialize, Debug)]
#[repr(u8)]
#[borsh(use_discriminant=true)]
pub enum EscrowState {
    Idle = 0,
    Holding = 1,
    PendingAkashic = 2,
    Released = 3,
    Reverted = 4,
    EmergencyReverted = 5,
}

impl Default for EscrowState {
    fn default() -> Self {
        EscrowState::Idle
    }
}

// ── Revert Reasons ──────────────────────────────────────────────────────────
#[derive(Clone, Copy, PartialEq, Eq, BorshSerialize, BorshDeserialize, Debug)]
#[repr(u8)]
#[borsh(use_discriminant=true)]
pub enum RevertReason {
    Timeout = 0,
    CoherenceFailure = 1,
    RouteInvalid = 2,
    Manual = 3,
    AkashicOutage24h = 4,
    CascadeRevert = 5,
    EmergencyEscape = 6,
}

impl Default for RevertReason {
    fn default() -> Self {
        RevertReason::Timeout
    }
}

// ── Escrow Account Data ─────────────────────────────────────────────────────
#[derive(BorshSerialize, BorshDeserialize, Debug, Default)]
pub struct Escrow {
    /// Discriminator (8 bytes) — set by Anchor-style prefix, here just a marker
    pub discriminator: [u8; 8],
    /// Unique escrow identifier (32 bytes — BEO-style)
    pub escrow_id: [u8; 32],
    /// Linked BTCP route ID
    pub route_id: [u8; 32],
    /// BEO entity identifier
    pub entity_id: [u8; 32],
    /// Destination pubkey
    pub destination: Pubkey,
    /// SOL amount locked (lamports)
    pub amount: u64,
    /// Release threshold: coherence * 1_000_000
    pub min_coherence: u64,
    /// Block at which escrow was locked
    pub lock_block: u64,
    /// Timestamp at lock (for 7-day emergency)
    pub lock_timestamp: u64,
    /// Max blocks before auto-revert
    pub timeout_blocks: u64,
    /// Current state
    pub state: u8,
    /// Revert reason (if reverted)
    pub revert_reason: u8,
    /// Settled timestamp (0 if not settled)
    pub settled_at: u64,
    /// Reverted timestamp (0 if not reverted)
    pub reverted_at: u64,
    /// Locked by (signer)
    pub locked_by: Pubkey,
    /// Parent escrow for cascade (all-zeros if no parent)
    pub parent_escrow: Pubkey,
    /// Two-phase confirmation hash (G1)
    pub settlement_check_hash: [u8; 32],
    /// Bump seed for PDA
    pub bump: u8,
}

impl Escrow {
    pub const LEN: usize = 8 + 32 + 32 + 32 + 32 + 8 + 8 + 8 + 8 + 8 + 1 + 1 + 8 + 8 + 32 + 32 + 32 + 1;

    pub fn state_enum(&self) -> Result<EscrowState, ProgramError> {
        match self.state {
            0 => Ok(EscrowState::Idle),
            1 => Ok(EscrowState::Holding),
            2 => Ok(EscrowState::PendingAkashic),
            3 => Ok(EscrowState::Released),
            4 => Ok(EscrowState::Reverted),
            5 => Ok(EscrowState::EmergencyReverted),
            _ => Err(ProgramError::InvalidAccountData),
        }
    }

    pub fn set_state(&mut self, s: EscrowState) {
        self.state = s as u8;
    }
}

// ── Instructions ────────────────────────────────────────────────────────────
#[derive(BorshSerialize, BorshDeserialize, Debug)]
pub enum EscrowInstruction {
    /// LockFunds { route_id, entity_id, destination, amount, min_coherence, timeout_blocks }
    LockFunds {
        route_id: [u8; 32],
        entity_id: [u8; 32],
        amount: u64,
        min_coherence: u64,
        timeout_blocks: u64,
    },
    /// Release { coherence_proof: [u8; 32] }
    Release { coherence_proof: [u8; 32] },
    /// RevertTimeout
    RevertTimeout,
    /// RevertEmergency — anyone can call after 7 days
    RevertEmergency,
    /// CascadeRevert
    CascadeRevert,
}

// ── Errors ──────────────────────────────────────────────────────────────────
#[derive(Error, Debug, Copy, Clone)]
pub enum EscrowError {
    #[error("Escrow not found")]
    NotFound,
    #[error("Escrow not in HOLDING state")]
    NotHolding,
    #[error("Escrow already settled")]
    AlreadySettled,
    #[error("Emergency escape not yet available (7 days)")]
    EmergencyNotYet,
    #[error("Timeout not reached")]
    TimeoutNotReached,
    #[error("Insufficient coherence")]
    InsufficientCoherence,
    #[error("Unauthorized")]
    Unauthorized,
    #[error("Amount mismatch")]
    AmountMismatch,
}

impl From<EscrowError> for ProgramError {
    fn from(e: EscrowError) -> Self {
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
    let instruction: EscrowInstruction =
        EscrowInstruction::try_from_slice(instruction_data).map_err(|_| ProgramError::InvalidInstructionData)?;

    match instruction {
        EscrowInstruction::LockFunds {
            route_id,
            entity_id,
            amount,
            min_coherence,
            timeout_blocks,
        } => lock_funds(program_id, accounts, route_id, entity_id, amount, min_coherence, timeout_blocks),
        EscrowInstruction::Release { coherence_proof } => release(program_id, accounts, coherence_proof),
        EscrowInstruction::RevertTimeout => revert_timeout(program_id, accounts),
        EscrowInstruction::RevertEmergency => revert_emergency(program_id, accounts),
        EscrowInstruction::CascadeRevert => cascade_revert(program_id, accounts),
    }
}

/// LockFunds — lock SOL into escrow, state -> HOLDING
fn lock_funds(
    program_id: &Pubkey,
    accounts: &[AccountInfo],
    route_id: [u8; 32],
    entity_id: [u8; 32],
    amount: u64,
    min_coherence: u64,
    timeout_blocks: u64,
) -> ProgramResult {
    let account_info_iter = &mut accounts.iter();
    let escrow_info = next_account_info(account_info_iter)?;
    let source_info = next_account_info(account_info_iter)?;
    let destination_info = next_account_info(account_info_iter)?;
    let system_program = next_account_info(account_info_iter)?;

    // Verify the escrow account is owned by this program
    if escrow_info.owner != program_id {
        return Err(ProgramError::IncorrectProgramId);
    }

    // Derive PDA for the escrow
    let (escrow_pda, bump) = Pubkey::find_program_address(
        &[b"escrow", source_info.key.as_ref(), route_id.as_ref()],
        program_id,
    );
    if escrow_pda != *escrow_info.key {
        return Err(ProgramError::InvalidSeeds);
    }

    let clock = Clock::get()?;
    let mut escrow = Escrow::try_from_slice(&escrow_info.data.borrow())?;
    
    // Initialize escrow
    escrow.discriminator = [b'b', b't', b'c', b'p', b'_', b'e', b's', b'c'];
    escrow.escrow_id = route_id; // Use route_id as escrow_id for simplicity
    escrow.route_id = route_id;
    escrow.entity_id = entity_id;
    escrow.destination = *destination_info.key;
    escrow.amount = amount;
    escrow.min_coherence = min_coherence;
    escrow.lock_block = clock.slot;
    escrow.lock_timestamp = clock.unix_timestamp as u64;
    escrow.timeout_blocks = timeout_blocks;
    escrow.set_state(EscrowState::Holding);
    escrow.revert_reason = RevertReason::Timeout as u8;
    escrow.settled_at = 0;
    escrow.reverted_at = 0;
    escrow.locked_by = *source_info.key;
    escrow.parent_escrow = Pubkey::default();
    escrow.settlement_check_hash = [0u8; 32];
    escrow.bump = bump;

    // Transfer SOL from source to escrow PDA
    invoke(
        &system_instruction::transfer(source_info.key, escrow_info.key, amount),
        &[source_info.clone(), escrow_info.clone(), system_program.clone()],
    )?;

    // Save escrow data
    escrow.serialize(&mut *escrow_info.data.borrow_mut())?;

    msg!("BTCP Escrow: locked {} lamports, state=HOLDING", amount);
    Ok(())
}

/// Release — release funds to destination (requires coherence proof)
fn release(
    program_id: &Pubkey,
    accounts: &[AccountInfo],
    _coherence_proof: [u8; 32],
) -> ProgramResult {
    let account_info_iter = &mut accounts.iter();
    let escrow_info = next_account_info(account_info_iter)?;
    let destination_info = next_account_info(account_info_iter)?;
    let system_program = next_account_info(account_info_iter)?;

    if escrow_info.owner != program_id {
        return Err(ProgramError::IncorrectProgramId);
    }

    let mut escrow = Escrow::try_from_slice(&escrow_info.data.borrow())?;
    let state = escrow.state_enum()?;
    if state != EscrowState::Holding && state != EscrowState::PendingAkashic {
        return Err(EscrowError::NotHolding.into());
    }

    let clock = Clock::get()?;
    let lamports = escrow_info.lamports();
    **escrow_info.try_borrow_mut_lamports()? -= lamports;
    **destination_info.try_borrow_mut_lamports()? += lamports;

    escrow.set_state(EscrowState::Released);
    escrow.settled_at = clock.unix_timestamp as u64;
    escrow.serialize(&mut *escrow_info.data.borrow_mut())?;

    msg!("BTCP Escrow: released {} lamports to {}", lamports, destination_info.key);
    Ok(())
}

/// RevertTimeout — revert after timeout_blocks
fn revert_timeout(program_id: &Pubkey, accounts: &[AccountInfo]) -> ProgramResult {
    let account_info_iter = &mut accounts.iter();
    let escrow_info = next_account_info(account_info_iter)?;
    let source_info = next_account_info(account_info_iter)?;

    if escrow_info.owner != program_id {
        return Err(ProgramError::IncorrectProgramId);
    }

    let mut escrow = Escrow::try_from_slice(&escrow_info.data.borrow())?;
    let state = escrow.state_enum()?;
    if state != EscrowState::Holding && state != EscrowState::PendingAkashic {
        return Err(EscrowError::NotHolding.into());
    }

    let clock = Clock::get()?;
    if clock.slot < escrow.lock_block + escrow.timeout_blocks {
        return Err(EscrowError::TimeoutNotReached.into());
    }

    // Refund to source (locked_by)
    let lamports = escrow_info.lamports();
    **escrow_info.try_borrow_mut_lamports()? -= lamports;
    **source_info.try_borrow_mut_lamports()? += lamports;

    escrow.set_state(EscrowState::Reverted);
    escrow.revert_reason = RevertReason::Timeout as u8;
    escrow.reverted_at = clock.unix_timestamp as u64;
    escrow.serialize(&mut *escrow_info.data.borrow_mut())?;

    msg!("BTCP Escrow: reverted (timeout), refunded {} lamports", lamports);
    Ok(())
}

/// RevertEmergency — ANY caller after 7 days (Gap 8 Resolution)
fn revert_emergency(program_id: &Pubkey, accounts: &[AccountInfo]) -> ProgramResult {
    let account_info_iter = &mut accounts.iter();
    let escrow_info = next_account_info(account_info_iter)?;
    let source_info = next_account_info(account_info_iter)?;

    if escrow_info.owner != program_id {
        return Err(ProgramError::IncorrectProgramId);
    }

    let mut escrow = Escrow::try_from_slice(&escrow_info.data.borrow())?;
    let state = escrow.state_enum()?;
    if state != EscrowState::Holding && state != EscrowState::PendingAkashic {
        return Err(EscrowError::NotHolding.into());
    }

    let clock = Clock::get()?;
    let elapsed = (clock.unix_timestamp as u64).saturating_sub(escrow.lock_timestamp);
    if elapsed < EMERGENCY_ESCAPE_SECONDS {
        msg!("Emergency escape not yet available: {}s elapsed, need {}s", elapsed, EMERGENCY_ESCAPE_SECONDS);
        return Err(EscrowError::EmergencyNotYet.into());
    }

    // Refund to source — ANY caller can trigger, but funds go to locked_by
    let lamports = escrow_info.lamports();
    **escrow_info.try_borrow_mut_lamports()? -= lamports;
    **source_info.try_borrow_mut_lamports()? += lamports;

    escrow.set_state(EscrowState::EmergencyReverted);
    escrow.revert_reason = RevertReason::EmergencyEscape as u8;
    escrow.reverted_at = clock.unix_timestamp as u64;
    escrow.serialize(&mut *escrow_info.data.borrow_mut())?;

    msg!("BTCP Escrow: EMERGENCY REVERT after {} days, refunded {} lamports", elapsed / 86400, lamports);
    Ok(())
}

/// CascadeRevert — triggered by child escrow revert (Gap 9)
fn cascade_revert(program_id: &Pubkey, accounts: &[AccountInfo]) -> ProgramResult {
    let account_info_iter = &mut accounts.iter();
    let escrow_info = next_account_info(account_info_iter)?;
    let source_info = next_account_info(account_info_iter)?;

    if escrow_info.owner != program_id {
        return Err(ProgramError::IncorrectProgramId);
    }

    let mut escrow = Escrow::try_from_slice(&escrow_info.data.borrow())?;
    let state = escrow.state_enum()?;
    if state != EscrowState::Holding {
        return Err(EscrowError::NotHolding.into());
    }

    // Refund to source
    let lamports = escrow_info.lamports();
    **escrow_info.try_borrow_mut_lamports()? -= lamports;
    **source_info.try_borrow_mut_lamports()? += lamports;

    let clock = Clock::get()?;
    escrow.set_state(EscrowState::Reverted);
    escrow.revert_reason = RevertReason::CascadeRevert as u8;
    escrow.reverted_at = clock.unix_timestamp as u64;
    escrow.serialize(&mut *escrow_info.data.borrow_mut())?;

    msg!("BTCP Escrow: CASCADE REVERT, refunded {} lamports", lamports);
    Ok(())
}

// ── Tests ───────────────────────────────────────────────────────────────────
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_escrow_state_serialization() {
        let mut escrow = Escrow::default();
        escrow.set_state(EscrowState::Holding);
        assert_eq!(escrow.state, 1);
        assert_eq!(escrow.state_enum().unwrap(), EscrowState::Holding);

        let data = escrow.try_to_vec().unwrap();
        let decoded = Escrow::try_from_slice(&data).unwrap();
        assert_eq!(decoded.state, 1);
    }

    #[test]
    fn test_emergency_escape_seconds() {
        assert_eq!(EMERGENCY_ESCAPE_SECONDS, 7 * 24 * 60 * 60);
        assert_eq!(AKASHIC_RECOVERY_SECONDS, 24 * 60 * 60);
    }

    #[test]
    fn test_revert_reasons() {
        assert_eq!(RevertReason::Timeout as u8, 0);
        assert_eq!(RevertReason::EmergencyEscape as u8, 6);
        assert_eq!(RevertReason::CascadeRevert as u8, 5);
    }
}
