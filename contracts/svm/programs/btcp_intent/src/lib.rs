//! BTCPIntent — Behavioral Transaction Continuity Protocol Intent Registry
//!
//! Solana Anchor port of `BTCPIntent.sol`.
//!
//! Registers user intents (what they want, not how to execute).
//! Full intent object stored off-chain in Akashic Index; on-chain stores
//! only the intent hash + minimal routing metadata.
//!
//! PDA: ["intent", intent_hash_bytes]

use anchor_lang::prelude::*;
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

declare_id!("EgPA8JdQBKDF4fAGG1LsG5cqTpPoSXZBVUPoFLP2KJsj");

// ── Accounts ─────────────────────────────────────────────────────────────────

/// Intent state account. PDA: ["intent", intent_hash_bytes]
#[account]
pub struct Intent {
    pub intent_hash: [u8; 32],
    pub entity_id: BEOIdentity,
    pub action: u8,
    pub asset_in: AssetId,
    pub asset_out: AssetId,
    pub magnitude: u64,
    pub deadline: i64,
    pub max_total_gas: u128,
    pub min_finality: u8,
    pub min_nl_score: u16,
    pub privacy: u8,
    pub status: IntentStatus,
    pub created_at: i64,
    pub submitter: Pubkey,
    pub bump: u8,
}

impl Intent {
    pub const SIZE: usize = 8
        + 32    // intent_hash
        + 32    // entity_id
        + 1     // action
        + 32    // asset_in
        + 32    // asset_out
        + 8     // magnitude
        + 8     // deadline (i64)
        + 16    // max_total_gas (u128)
        + 1     // min_finality
        + 2     // min_nl_score
        + 1     // privacy
        + 1     // status
        + 8     // created_at (i64)
        + 32    // submitter
        + 1;    // bump
}

// ── Instructions ────────────────────────────────────────────────────────────

#[program]
pub mod btcp_intent {
    use super::*;

    /// Initialize program config. Must be called once after deployment.
    pub fn initialize(ctx: Context<Initialize>) -> Result<()> {
        let config = &mut ctx.accounts.config;
        config.owner = ctx.accounts.payer.key();
        config.relayer = ctx.accounts.payer.key();
        config.count = 0;
        config.bump = ctx.bumps.config;
        Ok(())
    }

    /// Register a new intent.
    ///
    /// Equivalent to Solidity `registerIntent()`.
    /// Full intent object is stored off-chain; on-chain we store only the
    /// intent hash + routing metadata.
    pub fn register_intent(
        ctx: Context<RegisterIntent>,
        intent_hash: [u8; 32],
        entity_id: BEOIdentity,
        action: u8,
        asset_in: AssetId,
        asset_out: AssetId,
        magnitude: u64,
        deadline: i64,
        max_total_gas: u128,
        min_finality: u8,
        min_nl_score: u16,
        privacy: u8,
    ) -> Result<()> {
        let config = &ctx.accounts.config;
        require!(config.is_authorized(&ctx.accounts.relayer.key()), BTCPError::NotAuthorized);

        // Validate inputs
        require!(magnitude > 0, BTCPError::ZeroMagnitude);
        let clock = Clock::get()?;
        require!(deadline > clock.unix_timestamp, BTCPError::DeadlinePast);
        require!(action <= 4, BTCPError::InvalidAction);
        require!(min_finality <= 2, BTCPError::InvalidFinality);
        require!(privacy <= 2, BTCPError::InvalidPrivacy);

        // Validate action enum
        let _ = IntentAction::from_u8(action)?;

        let intent = &mut ctx.accounts.intent;
        intent.intent_hash = intent_hash;
        intent.entity_id = entity_id;
        intent.action = action;
        intent.asset_in = asset_in;
        intent.asset_out = asset_out;
        intent.magnitude = magnitude;
        intent.deadline = deadline;
        intent.max_total_gas = max_total_gas;
        intent.min_finality = min_finality;
        intent.min_nl_score = min_nl_score;
        intent.privacy = privacy;
        intent.status = IntentStatus::Pending;
        intent.created_at = clock.unix_timestamp;
        intent.submitter = ctx.accounts.relayer.key();
        let (_pda, bump) = Pubkey::find_program_address(&[SEED_INTENT, &intent_hash], &crate::ID);
        intent.bump = bump;

        ctx.accounts.config.count = ctx.accounts.config.count.checked_add(1).ok_or(BTCPError::Overflow)?;

        emit!(IntentRegistered {
            intent_hash,
            entity_id,
            action,
            magnitude,
            deadline,
        });

        Ok(())
    }

    /// Update intent status. Only relayer. Enforces valid transitions.
    ///
    /// Equivalent to Solidity `updateStatus()`.
    pub fn update_status(
        ctx: Context<UpdateStatus>,
        new_status: u8,
    ) -> Result<()> {
        let config = &ctx.accounts.config;
        require!(config.is_authorized(&ctx.accounts.relayer.key()), BTCPError::NotAuthorized);

        let intent = &mut ctx.accounts.intent;
        let old_status = intent.status;

        let next = match new_status {
            0 => IntentStatus::Pending,
            1 => IntentStatus::Routing,
            2 => IntentStatus::Executing,
            3 => IntentStatus::Completed,
            4 => IntentStatus::Failed,
            5 => IntentStatus::Expired,
            6 => IntentStatus::Resurrected,
            _ => return Err(error!(BTCPError::InvalidTransition)),
        };

        require!(old_status.can_transition_to(next), BTCPError::InvalidTransition);

        intent.status = next;

        emit!(IntentStatusUpdated {
            intent_hash: intent.intent_hash,
            old_status: old_status as u8,
            new_status: new_status,
        });

        Ok(())
    }

    /// Update relayer. Only owner.
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
#[instruction(intent_hash: [u8; 32])]
pub struct RegisterIntent<'info> {
    #[account(mut, seeds = [SEED_CONFIG], bump = config.bump)]
    pub config: Account<'info, ProgramConfig>,

    /// Must be owner or relayer
    #[account(mut)]
    pub relayer: Signer<'info>,

    /// Intent state PDA
    #[account(
        init,
        payer = relayer,
        space = Intent::SIZE,
        seeds = [SEED_INTENT, &intent_hash],
        bump,
    )]
    pub intent: Account<'info, Intent>,

    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct UpdateStatus<'info> {
    #[account(seeds = [SEED_CONFIG], bump = config.bump)]
    pub config: Account<'info, ProgramConfig>,

    #[account(mut)]
    pub relayer: Signer<'info>,

    #[account(
        mut,
        seeds = [SEED_INTENT, &intent.intent_hash],
        bump = intent.bump,
    )]
    pub intent: Account<'info, Intent>,
}

#[derive(Accounts)]
pub struct SetRelayer<'info> {
    #[account(mut, seeds = [SEED_CONFIG], bump = config.bump)]
    pub config: Account<'info, ProgramConfig>,

    pub owner: Signer<'info>,
}

// ── Events ──────────────────────────────────────────────────────────────────

#[event]
pub struct IntentRegistered {
    #[index]
    pub intent_hash: [u8; 32],
    #[index]
    pub entity_id: BEOIdentity,
    pub action: u8,
    pub magnitude: u64,
    pub deadline: i64,
}

#[event]
pub struct IntentStatusUpdated {
    #[index]
    pub intent_hash: [u8; 32],
    pub old_status: u8,
    pub new_status: u8,
}

#[event]
pub struct RelayerUpdated {
    #[index]
    pub old_relayer: Pubkey,
    #[index]
    pub new_relayer: Pubkey,
}
