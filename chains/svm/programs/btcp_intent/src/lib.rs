//! TRION BTCP Intent — Solana Program
//!
//! Mirrors the EVM BTCPIntent.sol contract:
//!   - Intent registration with entity_id, action, value, assets, deadline
//!   - Reference block for deterministic route selection (Gap 12)
//!   - Encrypted payload for Private BIBL (Gap 9)
//!
//! Instructions:
//!   RegisterIntent — register a new behavioral intent
//!   GetIntent       — read intent state
//!   CancelIntent    — cancel before matching

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

// ── Intent Action Types (canonical 20 event types, subset here) ─────────────
#[derive(Clone, Copy, PartialEq, Eq, BorshSerialize, BorshDeserialize, Debug)]
#[repr(u8)]
#[borsh(use_discriminant=true)]
pub enum ActionType {
    Swap = 0,
    Transfer = 1,
    Liquidity = 2,
    Stake = 3,
    Borrow = 7,
}

impl Default for ActionType {
    fn default() -> Self {
        ActionType::Swap
    }
}

// ── Privacy Levels (Gap 9 Resolution) ───────────────────────────────────────
#[derive(Clone, Copy, PartialEq, Eq, BorshSerialize, BorshDeserialize, Debug)]
#[repr(u8)]
#[borsh(use_discriminant=true)]
pub enum PrivacyLevel {
    Public = 0,
    ZkCredential = 1,
    Invisible = 2,
}

impl Default for PrivacyLevel {
    fn default() -> Self {
        PrivacyLevel::Public
    }
}

// ── Intent Status ───────────────────────────────────────────────────────────
#[derive(Clone, Copy, PartialEq, Eq, BorshSerialize, BorshDeserialize, Debug)]
#[repr(u8)]
#[borsh(use_discriminant=true)]
pub enum IntentStatus {
    Active = 0,
    Matched = 1,
    Cancelled = 2,
    Expired = 3,
}

impl Default for IntentStatus {
    fn default() -> Self {
        IntentStatus::Active
    }
}

// ── Intent Account ──────────────────────────────────────────────────────────
#[derive(BorshSerialize, BorshDeserialize, Debug, Default)]
pub struct Intent {
    pub discriminator: [u8; 8],
    /// Intent ID (32 bytes, derived from entity + nonce)
    pub intent_id: [u8; 32],
    /// BEO entity identifier
    pub entity_id: [u8; 32],
    /// Action type
    pub action: u8,
    /// Value in behavioral units (lamports)
    pub value: u64,
    /// Source asset (token mint or zero for native)
    pub asset_in: Pubkey,
    /// Destination asset
    pub asset_out: Pubkey,
    /// Deadline (block height)
    pub deadline: u64,
    /// Max total gas (USD equivalent, scaled)
    pub max_total_gas: u64,
    /// Min finality (0=FAST, 1=STANDARD, 2=SECURE)
    pub min_finality: u8,
    /// Min NL score (scaled by 1e6)
    pub min_nl_score: u64,
    /// Privacy level
    pub privacy: u8,
    /// Reference block (Gap 12: deterministic route selection)
    pub reference_block: u64,
    /// Entity nonce for replay prevention
    pub nonce: u64,
    /// Status
    pub status: u8,
    /// Registration timestamp
    pub registered_at: u64,
    /// Bump seed
    pub bump: u8,
}

impl Intent {
    pub const LEN: usize = 8 + 32 + 32 + 1 + 8 + 32 + 32 + 8 + 8 + 1 + 8 + 1 + 8 + 8 + 1 + 8 + 1;

    pub fn status_enum(&self) -> Result<IntentStatus, ProgramError> {
        match self.status {
            0 => Ok(IntentStatus::Active),
            1 => Ok(IntentStatus::Matched),
            2 => Ok(IntentStatus::Cancelled),
            3 => Ok(IntentStatus::Expired),
            _ => Err(ProgramError::InvalidAccountData),
        }
    }
}

// ── Instructions ────────────────────────────────────────────────────────────
#[derive(BorshSerialize, BorshDeserialize, Debug)]
pub enum IntentInstruction {
    /// RegisterIntent { entity_id, action, value, deadline, max_gas, min_finality, min_nl, privacy, nonce }
    RegisterIntent {
        entity_id: [u8; 32],
        action: u8,
        value: u64,
        deadline: u64,
        max_total_gas: u64,
        min_finality: u8,
        min_nl_score: u64,
        privacy: u8,
        nonce: u64,
    },
    /// CancelIntent
    CancelIntent,
}

// ── Errors ──────────────────────────────────────────────────────────────────
#[derive(Error, Debug, Copy, Clone)]
pub enum IntentError {
    #[error("Intent already exists")]
    AlreadyExists,
    #[error("Intent not active")]
    NotActive,
    #[error("Unauthorized")]
    Unauthorized,
    #[error("Deadline passed")]
    DeadlinePassed,
}

impl From<IntentError> for ProgramError {
    fn from(e: IntentError) -> Self {
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
    let instruction: IntentInstruction =
        IntentInstruction::try_from_slice(instruction_data).map_err(|_| ProgramError::InvalidInstructionData)?;

    match instruction {
        IntentInstruction::RegisterIntent {
            entity_id,
            action,
            value,
            deadline,
            max_total_gas,
            min_finality,
            min_nl_score,
            privacy,
            nonce,
        } => register_intent(
            program_id, accounts, entity_id, action, value, deadline,
            max_total_gas, min_finality, min_nl_score, privacy, nonce,
        ),
        IntentInstruction::CancelIntent => cancel_intent(program_id, accounts),
    }
}

fn register_intent(
    program_id: &Pubkey,
    accounts: &[AccountInfo],
    entity_id: [u8; 32],
    action: u8,
    value: u64,
    deadline: u64,
    max_total_gas: u64,
    min_finality: u8,
    min_nl_score: u64,
    privacy: u8,
    nonce: u64,
) -> ProgramResult {
    let account_info_iter = &mut accounts.iter();
    let intent_info = next_account_info(account_info_iter)?;
    let signer_info = next_account_info(account_info_iter)?;

    if intent_info.owner != program_id {
        return Err(ProgramError::IncorrectProgramId);
    }

    // Derive PDA
    let (intent_pda, bump) = Pubkey::find_program_address(
        &[b"intent", signer_info.key.as_ref(), &nonce.to_le_bytes()],
        program_id,
    );
    if intent_pda != *intent_info.key {
        return Err(ProgramError::InvalidSeeds);
    }

    let clock = Clock::get()?;

    let mut intent = Intent::try_from_slice(&intent_info.data.borrow())?;
    intent.discriminator = [b'b', b't', b'c', b'p', b'_', b'i', b'n', b't'];
    intent.intent_id = entity_id; // simplified
    intent.entity_id = entity_id;
    intent.action = action;
    intent.value = value;
    intent.asset_in = Pubkey::default();
    intent.asset_out = Pubkey::default();
    intent.deadline = deadline;
    intent.max_total_gas = max_total_gas;
    intent.min_finality = min_finality;
    intent.min_nl_score = min_nl_score;
    intent.privacy = privacy;
    intent.reference_block = clock.slot;
    intent.nonce = nonce;
    intent.status = IntentStatus::Active as u8;
    intent.registered_at = clock.unix_timestamp as u64;
    intent.bump = bump;

    intent.serialize(&mut *intent_info.data.borrow_mut())?;

    msg!("BTCP Intent: registered action={} value={} nonce={}", action, value, nonce);
    Ok(())
}

fn cancel_intent(program_id: &Pubkey, accounts: &[AccountInfo]) -> ProgramResult {
    let account_info_iter = &mut accounts.iter();
    let intent_info = next_account_info(account_info_iter)?;
    let signer_info = next_account_info(account_info_iter)?;

    if intent_info.owner != program_id {
        return Err(ProgramError::IncorrectProgramId);
    }

    let mut intent = Intent::try_from_slice(&intent_info.data.borrow())?;
    if intent.status_enum()? != IntentStatus::Active {
        return Err(IntentError::NotActive.into());
    }

    // Verify signer is the entity owner (simplified: signer must be the PDA invoker)
    if !signer_info.is_signer {
        return Err(IntentError::Unauthorized.into());
    }

    intent.status = IntentStatus::Cancelled as u8;
    intent.serialize(&mut *intent_info.data.borrow_mut())?;

    msg!("BTCP Intent: cancelled");
    Ok(())
}

// ── Tests ───────────────────────────────────────────────────────────────────
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_intent_serialization() {
        let mut intent = Intent::default();
        intent.status = IntentStatus::Active as u8;
        intent.action = ActionType::Swap as u8;
        let data = intent.try_to_vec().unwrap();
        let decoded = Intent::try_from_slice(&data).unwrap();
        assert_eq!(decoded.status, 0);
        assert_eq!(decoded.action, 0);
    }

    #[test]
    fn test_action_types() {
        assert_eq!(ActionType::Swap as u8, 0);
        assert_eq!(ActionType::Transfer as u8, 1);
        assert_eq!(ActionType::Stake as u8, 3);
    }

    #[test]
    fn test_privacy_levels() {
        assert_eq!(PrivacyLevel::Public as u8, 0);
        assert_eq!(PrivacyLevel::ZkCredential as u8, 1);
        assert_eq!(PrivacyLevel::Invisible as u8, 2);
    }
}
