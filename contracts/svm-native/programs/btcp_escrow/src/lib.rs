//! BTCP Escrow — Native Solana Program (no Anchor)
//! Two-state atomic escrow: HOLDING → RELEASED | REVERTED.
//! Each escrow is a PDA: ["escrow", escrow_id]. SOL held in vault PDA: ["vault", escrow_id].

use solana_program::{
    account_info::{next_account_info, AccountInfo},
    entrypoint,
    entrypoint::ProgramResult,
    msg,
    program::invoke_signed,
    program_error::ProgramError,
    pubkey::Pubkey,
    system_instruction,
    sysvar::{clock::Clock, Sysvar},
};
use borsh::{BorshDeserialize, BorshSerialize};

#[derive(BorshSerialize, BorshDeserialize, Debug, Clone)]
pub struct ProgramConfig {
    pub owner: Pubkey,
    pub relayer: Pubkey,
    pub count: u64,
}

#[derive(BorshSerialize, BorshDeserialize, Debug, Clone)]
pub struct Escrow {
    pub escrow_id: [u8; 32],
    pub route_id: [u8; 32],
    pub entity_id: [u8; 32],
    pub destination: Pubkey,
    pub amount: u64,
    pub min_coherence: u64,
    pub lock_slot: u64,
    pub timeout_slots: u64,
    pub state: u8, // 0=HOLDING 1=RELEASED 2=REVERTED
    pub locked_by: Pubkey,
}

const INIT: u8 = 0;
const LOCK: u8 = 1;
const RELEASE: u8 = 2;
const REVERT: u8 = 3;

entrypoint!(process_instruction);

pub fn process_instruction(
    program_id: &Pubkey,
    accounts: &[AccountInfo],
    instruction_data: &[u8],
) -> ProgramResult {
    let disc = instruction_data.first().copied().ok_or(ProgramError::InvalidInstructionData)?;
    match disc {
        INIT => {
            let acc_iter = &mut accounts.iter();
            let config_ai = next_account_info(acc_iter)?;
            let payer = next_account_info(acc_iter)?;
            let system_program = next_account_info(acc_iter)?;
            let (config_pda, bump) = Pubkey::find_program_address(&[b"config"], program_id);
            if config_ai.key != &config_pda { return Err(ProgramError::InvalidArgument); }
            let rent = solana_program::rent::Rent::default();
            let lamports = rent.minimum_balance(32 + 32 + 8);
            invoke_signed(
                &system_instruction::create_account(payer.key, config_ai.key, lamports, 72, program_id),
                &[payer.clone(), config_ai.clone(), system_program.clone()],
                &[&[b"config", &[bump]]],
            )?;
            let config = ProgramConfig { owner: *payer.key, relayer: *payer.key, count: 0 };
            config.serialize(&mut *config_ai.data.borrow_mut())?;
            msg!("BTCP Escrow initialized");
            Ok(())
        }
        LOCK => {
            let acc_iter = &mut accounts.iter();
            let config_ai = next_account_info(acc_iter)?;
            let relayer = next_account_info(acc_iter)?;
            let vault_funder = next_account_info(acc_iter)?;
            let escrow_ai = next_account_info(acc_iter)?;
            let vault_ai = next_account_info(acc_iter)?;
            let destination = next_account_info(acc_iter)?;
            let system_program = next_account_info(acc_iter)?;
            let data = &instruction_data[1..];
            if data.len() < 112 { return Err(ProgramError::InvalidInstructionData); }
            let escrow_id: [u8; 32] = data[0..32].try_into().unwrap();
            let route_id: [u8; 32] = data[32..64].try_into().unwrap();
            let entity_id: [u8; 32] = data[64..96].try_into().unwrap();
            let min_coherence = u64::from_le_bytes(data[96..104].try_into().unwrap());
            let timeout_slots = u64::from_le_bytes(data[104..112].try_into().unwrap());
            let (escrow_pda, escrow_bump) = Pubkey::find_program_address(&[b"escrow", &escrow_id], program_id);
            if escrow_ai.key != &escrow_pda { return Err(ProgramError::InvalidArgument); }
            let amount = vault_funder.lamports();
            if amount == 0 { return Err(ProgramError::InsufficientFunds); }
            invoke_signed(
                &system_instruction::transfer(vault_funder.key, vault_ai.key, amount),
                &[vault_funder.clone(), vault_ai.clone(), system_program.clone()],
                &[],
            )?;
            let clock = Clock::get()?;
            let escrow = Escrow { escrow_id, route_id, entity_id, destination: *destination.key, amount, min_coherence, lock_slot: clock.slot, timeout_slots, state: 0, locked_by: *vault_funder.key };
            let rent = solana_program::rent::Rent::default();
            let lamports = rent.minimum_balance(Escrow::SIZE);
            invoke_signed(
                &system_instruction::create_account(relayer.key, escrow_ai.key, lamports, Escrow::SIZE as u64, program_id),
                &[relayer.clone(), escrow_ai.clone(), system_program.clone()],
                &[&[b"escrow", &escrow_id, &[escrow_bump]]],
            )?;
            escrow.serialize(&mut *escrow_ai.data.borrow_mut())?;
            let mut config: ProgramConfig = ProgramConfig::try_from_slice(&config_ai.data.borrow())?;
            config.count += 1;
            config.serialize(&mut *config_ai.data.borrow_mut())?;
            msg!("Escrow locked: {} lamports", amount);
            Ok(())
        }
        RELEASE => {
            let acc_iter = &mut accounts.iter();
            let config_ai = next_account_info(acc_iter)?;
            let relayer = next_account_info(acc_iter)?;
            let escrow_ai = next_account_info(acc_iter)?;
            let vault_ai = next_account_info(acc_iter)?;
            let destination = next_account_info(acc_iter)?;
            let system_program = next_account_info(acc_iter)?;
            let mut escrow: Escrow = Escrow::try_from_slice(&escrow_ai.data.borrow())?;
            if escrow.state != 0 { return Err(ProgramError::InvalidAccountData); }
            let clock = Clock::get()?;
            if clock.slot > escrow.lock_slot + escrow.timeout_slots { return Err(ProgramError::InvalidArgument); }
            let data = &instruction_data[1..];
            if data.len() < 8 { return Err(ProgramError::InvalidInstructionData); }
            let coherence = u64::from_le_bytes(data[0..8].try_into().unwrap());
            if coherence < escrow.min_coherence { return Err(ProgramError::InvalidArgument); }
            let amount = escrow.amount;
            escrow.state = 1;
            escrow.serialize(&mut *escrow_ai.data.borrow_mut())?;
            let (_, vault_bump) = Pubkey::find_program_address(&[b"vault", &escrow.escrow_id], program_id);
            invoke_signed(
                &system_instruction::transfer(vault_ai.key, destination.key, amount),
                &[vault_ai.clone(), destination.clone(), system_program.clone()],
                &[&[b"vault", &escrow.escrow_id, &[vault_bump]]],
            )?;
            msg!("Escrow released: {} lamports", amount);
            Ok(())
        }
        REVERT => {
            let acc_iter = &mut accounts.iter();
            let config_ai = next_account_info(acc_iter)?;
            let _caller = next_account_info(acc_iter)?;
            let escrow_ai = next_account_info(acc_iter)?;
            let vault_ai = next_account_info(acc_iter)?;
            let locked_by = next_account_info(acc_iter)?;
            let system_program = next_account_info(acc_iter)?;
            let mut escrow: Escrow = Escrow::try_from_slice(&escrow_ai.data.borrow())?;
            if escrow.state != 0 { return Err(ProgramError::InvalidAccountData); }
            let clock = Clock::get()?;
            if clock.slot <= escrow.lock_slot + escrow.timeout_slots {
                let config: ProgramConfig = ProgramConfig::try_from_slice(&config_ai.data.borrow())?;
                if config.owner != *_caller.key && config.relayer != *_caller.key {
                    return Err(ProgramError::IllegalOwner);
                }
            }
            let amount = escrow.amount;
            escrow.state = 2;
            escrow.serialize(&mut *escrow_ai.data.borrow_mut())?;
            let (_, vault_bump) = Pubkey::find_program_address(&[b"vault", &escrow.escrow_id], program_id);
            invoke_signed(
                &system_instruction::transfer(vault_ai.key, locked_by.key, amount),
                &[vault_ai.clone(), locked_by.clone(), system_program.clone()],
                &[&[b"vault", &escrow.escrow_id, &[vault_bump]]],
            )?;
            msg!("Escrow reverted: {} lamports", amount);
            Ok(())
        }
        _ => Err(ProgramError::InvalidInstructionData),
    }
}

impl Escrow {
    pub const SIZE: usize = 32 + 32 + 32 + 32 + 8 + 8 + 8 + 8 + 1 + 32;
}
impl ProgramConfig {
    pub const SIZE: usize = 32 + 32 + 8;
}
