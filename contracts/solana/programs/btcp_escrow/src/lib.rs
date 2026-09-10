use anchor_lang::prelude::*;

declare_id!("HZbbZZaFF6q4RtzeEfCgiMAW45qCpZFRKhsrGxNmJBVU");

#[account]
pub struct EscrowState {
    pub route_id: [u8; 32],
    pub destination: Pubkey,
    pub amount: u64,
    pub min_coherence: u64,
    pub lock_slot: u64,
    pub timeout: u64,
    pub state: u8, // 0=HOLDING, 1=RELEASED, 2=REVERTED
    pub locked_by: Pubkey,
    pub quorum_required: u32,
    pub owner: Pubkey,
}

#[account]
pub struct Attestation {
    pub coherence: u64,
    pub execution_bh: [u8; 32],
    pub count: u32,
    pub last_time: i64,
    pub disputed: bool,
}

#[error_code]
pub enum EscrowError {
    #[msg("Not holding")]
    NotHolding,
    #[msg("Already released")]
    AlreadyReleased,
    #[msg("Quorum not reached")]
    QuorumNotReached,
    #[msg("Disputed")]
    Disputed,
    #[msg("Coherence mismatch")]
    CoherenceMismatch,
    #[msg("Stale attestation")]
    StaleAttestation,
    #[msg("Not validator")]
    NotValidator,
    #[msg("Already attested")]
    AlreadyAttested,
    #[msg("Not owner")]
    NotOwner,
    #[msg("Bad input")]
    BadInput,
}

#[program]
pub mod btcp_escrow {
    use super::*;

    pub fn initialize(ctx: Context<InitEscrow>) -> Result<()> {
        let state = &mut ctx.accounts.escrow_state;
        state.owner = ctx.accounts.signer.key();
        state.quorum_required = 3;
        Ok(())
    }

    pub fn add_validator(ctx: Context<AddValidator>, validator: Pubkey) -> Result<()> {
        let state = &mut ctx.accounts.escrow_state;
        require!(ctx.accounts.signer.key() == state.owner, EscrowError::NotOwner);
        // In production, store validators in a set account. For simplicity, emit event.
        emit!(ValidatorAdded { validator });
        Ok(())
    }

    pub fn set_quorum(ctx: Context<SetQuorum>, quorum: u32) -> Result<()> {
        let state = &mut ctx.accounts.escrow_state;
        require!(ctx.accounts.signer.key() == state.owner, EscrowError::NotOwner);
        require!(quorum > 0, EscrowError::BadInput);
        state.quorum_required = quorum;
        Ok(())
    }

    pub fn lock_escrow(ctx: Context<LockEscrow>, escrow_id: [u8; 32], route_id: [u8; 32], destination: Pubkey, amount: u64, min_coherence: u64, timeout: u64) -> Result<()> {
        require!(amount > 0, EscrowError::BadInput);
        let escrow = &mut ctx.accounts.escrow;
        escrow.route_id = route_id;
        escrow.destination = destination;
        escrow.amount = amount;
        escrow.min_coherence = min_coherence;
        escrow.lock_slot = Clock::get()?.slot;
        escrow.timeout = timeout;
        escrow.state = 0;
        escrow.locked_by = ctx.accounts.signer.key();
        // Copy quorum from global state
        let global = &ctx.accounts.escrow_state;
        escrow.quorum_required = global.quorum_required;
        escrow.owner = global.owner;
        Ok(())
    }

    pub fn submit_attestation(ctx: Context<SubmitAttestation>, route_id: [u8; 32], coherence: u64, execution_bh: [u8; 32], attestation_time: i64) -> Result<()> {
        let att = &mut ctx.accounts.attestation;
        let now = Clock::get()?.unix_timestamp;

        if att.count == 0 {
            // First attestation
            att.coherence = coherence;
            att.execution_bh = execution_bh;
            att.count = 1;
            att.last_time = attestation_time;
            att.disputed = false;
        } else {
            if att.disputed {
                return Err(EscrowError::Disputed.into());
            }
            if coherence == att.coherence && execution_bh == att.execution_bh {
                att.count += 1;
                att.last_time = attestation_time;
            } else {
                att.disputed = true;
            }
        }
        Ok(())
    }

    pub fn release_escrow(ctx: Context<ReleaseEscrow>, execution_bh: [u8; 32], coherence: u64, current_time: i64) -> Result<()> {
        let escrow = &mut ctx.accounts.escrow;
        require!(escrow.state == 0, EscrowError::AlreadyReleased);

        let att = &ctx.accounts.attestation;
        require!(att.count >= escrow.quorum_required, EscrowError::QuorumNotReached);
        require!(!att.disputed, EscrowError::Disputed);
        require!(coherence == att.coherence, EscrowError::CoherenceMismatch);
        require!(execution_bh == att.execution_bh, EscrowError::CoherenceMismatch);
        require!(current_time - att.last_time <= 300, EscrowError::StaleAttestation);

        escrow.state = 1;
        Ok(())
    }

    pub fn revert_escrow(ctx: Context<RevertEscrow>, _reason: u8) -> Result<()> {
        let escrow = &mut ctx.accounts.escrow;
        require!(escrow.state == 0, EscrowError::AlreadyReleased);
        escrow.state = 2;
        Ok(())
    }
}

#[event]
pub struct ValidatorAdded {
    pub validator: Pubkey,
}

#[derive(Accounts)]
pub struct InitEscrow<'info> {
    #[account(init, payer = signer, space = 8 + 32 + 32 + 8 + 8 + 8 + 8 + 1 + 32 + 4 + 32, seeds = [b"escrow_state"], bump)]
    pub escrow_state: Account<'info, EscrowState>,
    #[account(mut)]
    pub signer: Signer<'info>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct AddValidator<'info> {
    #[account(mut, seeds = [b"escrow_state"], bump)]
    pub escrow_state: Account<'info, EscrowState>,
    #[account(mut)]
    pub signer: Signer<'info>,
}

#[derive(Accounts)]
pub struct SetQuorum<'info> {
    #[account(mut, seeds = [b"escrow_state"], bump)]
    pub escrow_state: Account<'info, EscrowState>,
    #[account(mut)]
    pub signer: Signer<'info>,
}

#[derive(Accounts)]
#[instruction(escrow_id: [u8; 32])]
pub struct LockEscrow<'info> {
    #[account(init, payer = signer, space = 8 + 32 + 32 + 8 + 8 + 8 + 8 + 1 + 32 + 4 + 32, seeds = [b"escrow".as_ref(), escrow_id.as_ref()], bump)]
    pub escrow: Account<'info, EscrowState>,
    #[account(seeds = [b"escrow_state"], bump)]
    pub escrow_state: Account<'info, EscrowState>,
    #[account(mut)]
    pub signer: Signer<'info>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
#[instruction(route_id: [u8; 32])]
pub struct SubmitAttestation<'info> {
    #[account(init, payer = signer, space = 8 + 8 + 32 + 4 + 8 + 1, seeds = [b"attestation".as_ref(), route_id.as_ref()], bump)]
    pub attestation: Account<'info, Attestation>,
    #[account(mut)]
    pub signer: Signer<'info>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
#[instruction(escrow_id: [u8; 32])]
pub struct ReleaseEscrow<'info> {
    #[account(mut, seeds = [b"escrow".as_ref(), escrow_id.as_ref()], bump)]
    pub escrow: Account<'info, EscrowState>,
    #[account(seeds = [b"attestation".as_ref(), escrow.route_id.as_ref()], bump)]
    pub attestation: Account<'info, Attestation>,
}

#[derive(Accounts)]
#[instruction(escrow_id: [u8; 32])]
pub struct RevertEscrow<'info> {
    #[account(mut, seeds = [b"escrow".as_ref(), escrow_id.as_ref()], bump)]
    pub escrow: Account<'info, EscrowState>,
}
