//! BTCPRoute — Route ID tracking with anchor BH → execution BH linkage
//!
//! Solana Anchor port of `BTCPRoute.sol`.
//!
//! Records the behavioral proof of a cross-chain BTCP route.
//! Each route links an anchor behavioral hash (on source chain) to an
//! execution behavioral hash (on target chain) with consensus proof.
//!
//! PDA: ["route", route_id_bytes]

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

declare_id!("9B9Mb8uBB1sHrTvX53B9vP9c96Hb5uENjyPngmK5PBYK");

// ── Accounts ─────────────────────────────────────────────────────────────────

/// Route state account. PDA: ["route", route_id_bytes]
#[account]
pub struct Route {
    pub route_id: [u8; 32],
    pub intent_hash: [u8; 32],
    pub anchor_bh: [u8; 32],
    pub execution_bh: [u8; 32],
    pub anchor_chain: u64,
    pub execution_chain: u64,
    pub entity_id: BEOIdentity,
    pub gas_saved_vs_bridge: u64,
    pub beo_continuity: u64,
    pub cc_coherence: u64,
    pub route_type: u8,
    pub is_verified: bool,
    pub created_at: i64,
    pub finalized_at: i64,
    pub bump: u8,
}

impl Route {
    pub const SIZE: usize = 8
        + 32    // route_id
        + 32    // intent_hash
        + 32    // anchor_bh
        + 32    // execution_bh
        + 8     // anchor_chain
        + 8     // execution_chain
        + 32    // entity_id
        + 8     // gas_saved_vs_bridge
        + 8     // beo_continuity
        + 8     // cc_coherence
        + 1     // route_type
        + 1     // is_verified
        + 8     // created_at
        + 8     // finalized_at
        + 1;    // bump
}

// ── Instructions ────────────────────────────────────────────────────────────

#[program]
pub mod btcp_route {
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

    /// Publish a new BTCP route with anchor behavioral hash.
    ///
    /// Equivalent to Solidity `publishRoute()`.
    /// Called when the source-chain anchor event is observed.
    pub fn publish_route(
        ctx: Context<PublishRoute>,
        route_id: [u8; 32],
        intent_hash: [u8; 32],
        anchor_bh: [u8; 32],
        anchor_chain: u64,
        execution_chain: u64,
        entity_id: BEOIdentity,
        route_type: u8,
    ) -> Result<()> {
        let config = &ctx.accounts.config;
        require!(config.is_authorized(&ctx.accounts.relayer.key()), BTCPError::NotAuthorized);

        require!(anchor_bh != [0u8; 32], BTCPError::ZeroAnchor);

        // Validate route type
        let _ = RouteType::from_u8(route_type)?;

        let clock = Clock::get()?;
        let route = &mut ctx.accounts.route;

        route.route_id = route_id;
        route.intent_hash = intent_hash;
        route.anchor_bh = anchor_bh;
        route.execution_bh = [0u8; 32];
        route.anchor_chain = anchor_chain;
        route.execution_chain = execution_chain;
        route.entity_id = entity_id;
        route.gas_saved_vs_bridge = 0;
        route.beo_continuity = 0;
        route.cc_coherence = 0;
        route.route_type = route_type;
        route.is_verified = false;
        route.created_at = clock.unix_timestamp;
        route.finalized_at = 0;
        let (_pda, bump) = Pubkey::find_program_address(&[SEED_ROUTE, &route_id], &crate::ID);
        route.bump = bump;

        ctx.accounts.config.count = ctx.accounts.config.count.checked_add(1).ok_or(BTCPError::Overflow)?;

        emit!(RoutePublished {
            route_id,
            intent_hash,
            anchor_bh,
            anchor_chain,
            execution_chain,
            route_type,
        });

        Ok(())
    }

    /// Finalize a route with execution BH and savings data.
    ///
    /// Equivalent to Solidity `finalizeRoute()`.
    /// Called after both sides settle and the relayer has computed the
    /// final coherence and gas savings metrics.
    pub fn finalize_route(
        ctx: Context<FinalizeRoute>,
        execution_bh: [u8; 32],
        gas_saved_vs_bridge: u64,
        beo_continuity: u64,
        cc_coherence: u64,
    ) -> Result<()> {
        let config = &ctx.accounts.config;
        require!(config.is_authorized(&ctx.accounts.relayer.key()), BTCPError::NotAuthorized);

        let route = &mut ctx.accounts.route;
        require!(!route.is_verified, BTCPError::AlreadyVerified);
        require!(execution_bh != [0u8; 32], BTCPError::ZeroExecutionBH);
        require!(beo_continuity <= MAX_COHERENCE, BTCPError::InvalidScore);
        require!(cc_coherence <= MAX_COHERENCE, BTCPError::InvalidScore);

        let clock = Clock::get()?;

        route.execution_bh = execution_bh;
        route.gas_saved_vs_bridge = gas_saved_vs_bridge;
        route.beo_continuity = beo_continuity;
        route.cc_coherence = cc_coherence;
        route.is_verified = true;
        route.finalized_at = clock.unix_timestamp;

        emit!(RouteFinalized {
            route_id: route.route_id,
            execution_bh,
            gas_saved_vs_bridge,
            beo_continuity,
            cc_coherence,
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
#[instruction(route_id: [u8; 32])]
pub struct PublishRoute<'info> {
    #[account(mut, seeds = [SEED_CONFIG], bump = config.bump)]
    pub config: Account<'info, ProgramConfig>,

    /// Must be owner or relayer
    #[account(mut)]
    pub relayer: Signer<'info>,

    /// Route state PDA
    #[account(
        init,
        payer = relayer,
        space = Route::SIZE,
        seeds = [SEED_ROUTE, &route_id],
        bump,
    )]
    pub route: Account<'info, Route>,

    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct FinalizeRoute<'info> {
    #[account(seeds = [SEED_CONFIG], bump = config.bump)]
    pub config: Account<'info, ProgramConfig>,

    pub relayer: Signer<'info>,

    #[account(
        mut,
        seeds = [SEED_ROUTE, &route.route_id],
        bump = route.bump,
    )]
    pub route: Account<'info, Route>,
}

#[derive(Accounts)]
pub struct SetRelayer<'info> {
    #[account(mut, seeds = [SEED_CONFIG], bump = config.bump)]
    pub config: Account<'info, ProgramConfig>,

    pub owner: Signer<'info>,
}

// ── Events ──────────────────────────────────────────────────────────────────

#[event]
pub struct RoutePublished {
    #[index]
    pub route_id: [u8; 32],
    #[index]
    pub intent_hash: [u8; 32],
    pub anchor_bh: [u8; 32],
    pub anchor_chain: u64,
    pub execution_chain: u64,
    pub route_type: u8,
}

#[event]
pub struct RouteFinalized {
    #[index]
    pub route_id: [u8; 32],
    pub execution_bh: [u8; 32],
    pub gas_saved_vs_bridge: u64,
    pub beo_continuity: u64,
    pub cc_coherence: u64,
}

#[event]
pub struct RelayerUpdated {
    #[index]
    pub old_relayer: Pubkey,
    #[index]
    pub new_relayer: Pubkey,
}
