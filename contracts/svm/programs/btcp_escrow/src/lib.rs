//! BTCPEscrow — Two-State Atomic Escrow for BTCP Cross-Chain Settlement
//!
//! Solana Anchor port of `BTCPEscrow.sol`.
//!
//! Holds SOL in HOLDING state until TRION consensus verifies both parties'
//! behavioral coherence, then releases or reverts atomically.
//!
//! State model:
//!   HOLDING → RELEASED (coherence ≥ threshold, not expired)
//!   HOLDING → REVERTED (expired, OR relayer triggers failure)
//!
//! Design notes (Solana-specific):
//!   • Each escrow is a PDA: ["escrow", escrow_id]
//!   • Native SOL is held in a separate vault PDA: ["vault", escrow_id]
//!     (PDAs can be program-owned and receive SOL via system program)
//!   • `block.number` → `Clock::get()?.slot`
//!   • `block.timestamp` → `Clock::get()?.unix_timestamp`

use anchor_lang::{
    prelude::*,
    solana_program::{
        program::invoke_signed,
        system_instruction,
    },
};
use btcp_common::*;

// Program-level authority account
#[account]
pub struct ProgramConfig {
    pub owner: Pubkey,
    pub relayer: Pubkey,
    pub count: u64,
    pub bump: u8,
}

impl ProgramConfig {
    pub const SIZE: usize = 8 + 32 + 32 + 8 + 1;

    pub fn is_authorized(&self, signer: &Pubkey) -> bool {
        signer == &self.owner || signer == &self.relayer
    }

    pub fn is_owner(&self, signer: &Pubkey) -> bool {
        signer == &self.owner
    }
}

declare_id!("54r6REJKQ3d2MSV7zYikwiPmck3h7QRaeG44vnRHetWZ");

// ── Accounts ─────────────────────────────────────────────────────────────────

/// Escrow state account. PDA: ["escrow", escrow_id_bytes]
#[account]
pub struct Escrow {
    pub escrow_id: [u8; 32],
    pub route_id: [u8; 32],
    pub entity_id: BEOIdentity,
    pub destination: Pubkey,
    pub amount: u64,
    pub min_coherence: u64,
    pub lock_slot: u64,
    pub timeout_slots: u64,
    pub state: EscrowState,
    pub revert_reason: RevertReason,
    pub settled_at: i64,
    pub reverted_at: i64,
    pub locked_by: Pubkey,
    pub bump: u8,
    pub vault_bump: u8,
}

impl Escrow {
    /// Account size: discriminator (8) + fields
    pub const SIZE: usize = 8
        + 32    // escrow_id
        + 32    // route_id
        + 32    // entity_id (BEOIdentity)
        + 32    // destination (Pubkey)
        + 8     // amount
        + 8     // min_coherence
        + 8     // lock_slot
        + 8     // timeout_slots
        + 1     // state
        + 1     // revert_reason
        + 8     // settled_at
        + 8     // reverted_at
        + 32    // locked_by
        + 1     // bump
        + 1;    // vault_bump

    /// Check if escrow is expired (current slot > lock_slot + timeout_slots)
    pub fn is_expired(&self, current_slot: u64) -> bool {
        self.state == EscrowState::Holding
            && current_slot > self.lock_slot.saturating_add(self.timeout_slots)
    }
}

// ── Instructions ────────────────────────────────────────────────────────────

#[program]
pub mod btcp_escrow {
    use super::*;

    /// Initialize the program config (owner + relayer).
    /// Must be called once after deployment.
    pub fn initialize(ctx: Context<Initialize>) -> Result<()> {
        let config = &mut ctx.accounts.config;
        config.owner = ctx.accounts.payer.key();
        config.relayer = ctx.accounts.payer.key();
        config.count = 0;
        config.bump = ctx.bumps.config;
        Ok(())
    }

    /// Lock native SOL in escrow.
    ///
    /// Equivalent to Solidity `lockEscrow() external payable` — `amount` is
    /// the lamports to lock (the analog of msg.value).
    /// Caller (relayer) must be authorized; the SOL is transferred from the
    /// `vault_funder` signer to the vault PDA which is owned by this program.
    ///
    /// SECURITY FIX (P1): this previously locked `vault_funder.lamports()` —
    /// the funder's ENTIRE wallet balance. The locked amount is now an
    /// explicit argument; it is recorded in `Escrow.amount` and release/
    /// revert pay out exactly that amount.
    pub fn lock_escrow(
        ctx: Context<LockEscrow>,
        escrow_id: [u8; 32],
        route_id: [u8; 32],
        entity_id: BEOIdentity,
        amount: u64,
        min_coherence: u64,
        timeout_slots: u64,
    ) -> Result<()> {
        let config = &ctx.accounts.config;
        require!(config.is_authorized(&ctx.accounts.relayer.key()), BTCPError::NotAuthorized);

        require!(min_coherence <= MAX_COHERENCE, BTCPError::InvalidCoherence);
        require!(timeout_slots > 0, BTCPError::ZeroTimeout);
        require!(!entity_id.is_zero(), BTCPError::ZeroDestination);

        // SECURITY FIX (P1): encumber exactly the specified amount, never the
        // funder's whole balance. The explicit balance check gives a clean
        // typed error (the system-program transfer below would also fail on
        // insufficient funds; the runtime additionally keeps the funder
        // rent-exempt).
        require!(amount > 0, BTCPError::ZeroAmount);
        require!(
            ctx.accounts.vault_funder.lamports() >= amount,
            BTCPError::InsufficientFunds
        );

        let clock = Clock::get()?;

        // Transfer SOL from funder to vault PDA
        let transfer_ix = system_instruction::transfer(
            &ctx.accounts.vault_funder.key(),
            &ctx.accounts.vault.key(),
            amount,
        );
        anchor_lang::solana_program::program::invoke(
            &transfer_ix,
            &[
                ctx.accounts.vault_funder.to_account_info(),
                ctx.accounts.vault.to_account_info(),
                ctx.accounts.system_program.to_account_info(),
            ],
        )?;

        // Initialize escrow state
        let escrow = &mut ctx.accounts.escrow;
        escrow.escrow_id = escrow_id;
        escrow.route_id = route_id;
        escrow.entity_id = entity_id;
        escrow.destination = ctx.accounts.destination.key();
        escrow.amount = amount;
        escrow.min_coherence = min_coherence;
        escrow.lock_slot = clock.slot;
        escrow.timeout_slots = timeout_slots;
        escrow.state = EscrowState::Holding;
        escrow.revert_reason = RevertReason::Timeout;
        escrow.settled_at = 0;
        escrow.reverted_at = 0;
        escrow.locked_by = ctx.accounts.vault_funder.key();
        let (_escrow_pda, escrow_bump) = Pubkey::find_program_address(
            &[SEED_ESCROW, &escrow_id],
            &crate::ID,
        );
        let (_vault_pda, vault_bump) = Pubkey::find_program_address(
            &[SEED_VAULT, &escrow_id],
            &crate::ID,
        );
        escrow.bump = escrow_bump;
        escrow.vault_bump = vault_bump;

        // Increment counter
        ctx.accounts.config.count = ctx.accounts.config.count.checked_add(1).ok_or(BTCPError::Overflow)?;

        emit!(EscrowLocked {
            escrow_id,
            route_id,
            entity_id,
            destination: ctx.accounts.destination.key(),
            amount,
            min_coherence,
            timeout_slots,
        });

        Ok(())
    }

    /// Release escrow to destination. Requires TRION consensus verification.
    ///
    /// Equivalent to Solidity `releaseEscrow()`.
    /// Transfers SOL from vault PDA to destination.
    pub fn release_escrow(
        ctx: Context<ReleaseEscrow>,
        execution_bh: [u8; 32],
        coherence: u64,
    ) -> Result<()> {
        let config = &ctx.accounts.config;
        require!(config.is_authorized(&ctx.accounts.relayer.key()), BTCPError::NotAuthorized);

        let escrow = &mut ctx.accounts.escrow;
        require!(escrow.state == EscrowState::Holding, BTCPError::NotHolding);

        let clock = Clock::get()?;
        require!(!escrow.is_expired(clock.slot), BTCPError::Expired);
        require!(coherence >= escrow.min_coherence, BTCPError::CoherenceInsufficient);

        let amount = escrow.amount;
        let destination = escrow.destination;
        let route_id = escrow.route_id;

        escrow.state = EscrowState::Released;
        escrow.settled_at = clock.unix_timestamp;

        // Transfer SOL from vault PDA to destination
        let escrow_id_bytes = escrow.escrow_id;
        let vault_seeds: &[&[u8]] = &[
            SEED_VAULT,
            &escrow_id_bytes,
            &[escrow.vault_bump],
        ];
        invoke_signed(
            &system_instruction::transfer(
                &ctx.accounts.vault.key(),
                &destination,
                amount,
            ),
            &[
                ctx.accounts.vault.to_account_info(),
                ctx.accounts.destination.to_account_info(),
                ctx.accounts.system_program.to_account_info(),
            ],
            &[vault_seeds],
        )?;

        emit!(EscrowReleased {
            escrow_id: escrow.escrow_id,
            route_id,
            execution_bh,
            coherence,
            settled_at: clock.unix_timestamp,
        });

        Ok(())
    }

    /// Revert escrow — return funds to original locker.
    ///
    /// Equivalent to Solidity `revertEscrow()`.
    /// - Anyone can call on timeout
    /// - Only relayer/owner can call for other reasons
    pub fn revert_escrow(
        ctx: Context<RevertEscrow>,
        reason: u8,
    ) -> Result<()> {
        let escrow = &mut ctx.accounts.escrow;
        require!(escrow.state == EscrowState::Holding, BTCPError::NotHolding);

        let clock = Clock::get()?;
        let is_timeout = escrow.is_expired(clock.slot);

        let revert_reason = match reason {
            0 => RevertReason::Timeout,
            1 => RevertReason::CoherenceFailure,
            2 => RevertReason::RouteInvalid,
            3 => RevertReason::Manual,
            _ => return Err(error!(BTCPError::InvalidAction)),
        };

        if !is_timeout {
            // Non-timeout: must be relayer or owner
            require!(
                ctx.accounts.config.is_authorized(&ctx.accounts.caller.key()),
                BTCPError::NotRelayerForRevert
            );
            require!(revert_reason != RevertReason::Timeout, BTCPError::NotRelayerForRevert);
        }

        let amount = escrow.amount;
        let locked_by = escrow.locked_by;
        let escrow_id = escrow.escrow_id;
        let vault_bump = escrow.vault_bump;

        escrow.state = EscrowState::Reverted;
        escrow.revert_reason = revert_reason;
        escrow.reverted_at = clock.unix_timestamp;

        // Transfer SOL from vault back to locker
        let vault_seeds: &[&[u8]] = &[
            SEED_VAULT,
            &escrow_id,
            &[vault_bump],
        ];
        invoke_signed(
            &system_instruction::transfer(
                &ctx.accounts.vault.key(),
                &locked_by,
                amount,
            ),
            &[
                ctx.accounts.vault.to_account_info(),
                ctx.accounts.locked_by.to_account_info(),
                ctx.accounts.system_program.to_account_info(),
            ],
            &[vault_seeds],
        )?;

        emit!(EscrowReverted {
            escrow_id,
            reason: revert_reason as u8,
            reverted_at: clock.unix_timestamp,
        });

        Ok(())
    }

    /// Update relayer address. Only owner.
    pub fn set_relayer(ctx: Context<SetRelayer>, new_relayer: Pubkey) -> Result<()> {
        let config = &mut ctx.accounts.config;
        require!(config.is_owner(&ctx.accounts.owner.key()), BTCPError::NotOwner);

        let old_relayer = config.relayer;
        config.relayer = new_relayer;

        emit!(RelayerUpdated { old_relayer, new_relayer });
        Ok(())
    }
}

// ── Context Structs ─────────────────────────────────────────────────────────

#[derive(Accounts)]
pub struct Initialize<'info> {
    #[account(
        init,
        payer = payer,
        space = ProgramConfig::SIZE,
        seeds = [SEED_CONFIG],
        bump,
    )]
    pub config: Account<'info, ProgramConfig>,

    #[account(mut)]
    pub payer: Signer<'info>,

    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
#[instruction(escrow_id: [u8; 32])]
pub struct LockEscrow<'info> {
    #[account(mut, seeds = [SEED_CONFIG], bump = config.bump)]
    pub config: Account<'info, ProgramConfig>,

    /// Must be owner or relayer (pays rent for escrow account init)
    #[account(mut)]
    pub relayer: Signer<'info>,

    /// Account that provides the SOL to lock (must have at least `amount`
    /// lamports — only the specified amount is transferred, NOT the whole
    /// balance)
    #[account(mut)]
    pub vault_funder: Signer<'info>,

    /// Escrow state PDA
    #[account(
        init,
        payer = relayer,
        space = Escrow::SIZE,
        seeds = [SEED_ESCROW, &escrow_id],
        bump,
    )]
    pub escrow: Account<'info, Escrow>,

    /// Vault PDA that holds the SOL
    /// CHECK: This is a PDA that receives SOL; validated by seeds
    #[account(
        mut,
        seeds = [SEED_VAULT, &escrow_id],
        bump,
    )]
    pub vault: AccountInfo<'info>,

    /// Destination address that receives funds on release
    /// CHECK: Destination is arbitrary; stored in escrow state
    pub destination: AccountInfo<'info>,

    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct ReleaseEscrow<'info> {
    #[account(mut, seeds = [SEED_CONFIG], bump = config.bump)]
    pub config: Account<'info, ProgramConfig>,

    pub relayer: Signer<'info>,

    #[account(
        mut,
        seeds = [SEED_ESCROW, &escrow.escrow_id],
        bump = escrow.bump,
        constraint = escrow.escrow_id != [0u8; 32] @ BTCPError::EscrowNotFound,
    )]
    pub escrow: Account<'info, Escrow>,

    /// Vault PDA holding the SOL
    /// CHECK: Validated by seeds matching escrow
    #[account(
        mut,
        seeds = [SEED_VAULT, &escrow.escrow_id],
        bump = escrow.vault_bump,
    )]
    pub vault: AccountInfo<'info>,

    /// Destination account (must match escrow.destination)
    /// CHECK: Verified against escrow.destination
    #[account(mut, address = escrow.destination @ BTCPError::ZeroDestination)]
    pub destination: AccountInfo<'info>,

    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct RevertEscrow<'info> {
    #[account(seeds = [SEED_CONFIG], bump = config.bump)]
    pub config: Account<'info, ProgramConfig>,

    /// Can be anyone (for timeout) or relayer/owner (for other reasons)
    pub caller: Signer<'info>,

    #[account(
        mut,
        seeds = [SEED_ESCROW, &escrow.escrow_id],
        bump = escrow.bump,
        constraint = escrow.escrow_id != [0u8; 32] @ BTCPError::EscrowNotFound,
    )]
    pub escrow: Account<'info, Escrow>,

    /// Vault PDA holding the SOL
    /// CHECK: Validated by seeds
    #[account(
        mut,
        seeds = [SEED_VAULT, &escrow.escrow_id],
        bump = escrow.vault_bump,
    )]
    pub vault: AccountInfo<'info>,

    /// Original locker (gets refund)
    /// CHECK: Verified against escrow.locked_by
    #[account(mut, address = escrow.locked_by @ BTCPError::RefundFailed)]
    pub locked_by: AccountInfo<'info>,

    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct SetRelayer<'info> {
    #[account(mut, seeds = [SEED_CONFIG], bump = config.bump)]
    pub config: Account<'info, ProgramConfig>,

    pub owner: Signer<'info>,
}

// ── Events ──────────────────────────────────────────────────────────────────

#[event]
pub struct EscrowLocked {
    #[index]
    pub escrow_id: [u8; 32],
    #[index]
    pub route_id: [u8; 32],
    #[index]
    pub entity_id: BEOIdentity,
    pub destination: Pubkey,
    pub amount: u64,
    pub min_coherence: u64,
    pub timeout_slots: u64,
}

#[event]
pub struct EscrowReleased {
    #[index]
    pub escrow_id: [u8; 32],
    #[index]
    pub route_id: [u8; 32],
    pub execution_bh: [u8; 32],
    pub coherence: u64,
    pub settled_at: i64,
}

#[event]
pub struct EscrowReverted {
    #[index]
    pub escrow_id: [u8; 32],
    pub reason: u8,
    pub reverted_at: i64,
}

#[event]
pub struct RelayerUpdated {
    #[index]
    pub old_relayer: Pubkey,
    #[index]
    pub new_relayer: Pubkey,
}
