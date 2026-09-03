//! Shared types and constants for TRION BTCP Solana programs.
//!
//! These types are used across btcp_escrow, btcp_intent, and btcp_route
//! to ensure consistent BEO identity handling, state representations,
//! and PDA seed conventions.

use anchor_lang::prelude::*;

// ── PDA Seed Constants ────────────────────────────────────────────────────────
pub const SEED_CONFIG: &[u8] = b"config";
pub const SEED_ESCROW: &[u8] = b"escrow";
pub const SEED_INTENT: &[u8] = b"intent";
pub const SEED_ROUTE: &[u8] = b"route";
pub const SEED_VAULT: &[u8] = b"vault";

// ── Scaling Constants ────────────────────────────────────────────────────────
/// Coherence scores are stored ×1e6 (0 to 1,000,000)
pub const SCALE: u64 = 1_000_000;

/// Maximum valid coherence score
pub const MAX_COHERENCE: u64 = 1_000_000;

// ── Behavioral Entity Oracle (BEO) Identity ─────────────────────────────────
/// BEO identity: SHA3-256(normalize(chain_address))
/// Stored as 32-byte array, same as Solana pubkey layout but semantically
/// distinct (it's a hash, not a public key).
#[derive(AnchorSerialize, AnchorDeserialize, Clone, Copy, PartialEq, Eq, Debug)]
pub struct BEOIdentity(pub [u8; 32]);

impl BEOIdentity {
    pub const ZERO: Self = Self([0u8; 32]);

    pub fn is_zero(&self) -> bool {
        self.0 == [0u8; 32]
    }

    pub fn as_bytes(&self) -> &[u8; 32] {
        &self.0
    }
}

impl Default for BEOIdentity {
    fn default() -> Self {
        Self::ZERO
    }
}

// ── Universal Asset Identifier ──────────────────────────────────────────────
/// Cross-chain asset identifier: keccak256("SOL"), keccak256("BOT"), etc.
/// Allows matching intents across chains without depending on local
/// token mint addresses.
#[derive(AnchorSerialize, AnchorDeserialize, Clone, Copy, PartialEq, Eq, Debug)]
pub struct AssetId(pub [u8; 32]);

impl AssetId {
    pub const ZERO: Self = Self([0u8; 32]);

    pub fn is_zero(&self) -> bool {
        self.0 == [0u8; 32]
    }
}

impl Default for AssetId {
    fn default() -> Self {
        Self::ZERO
    }
}

// ── Config Account (shared pattern across all 3 programs) ───────────────────
/// Stores program-level authority: owner and relayer.
/// Mirrors Solidity's `owner` + `relayer` state variables.
///
/// NOTE: Each program defines its own #[account] wrapper because the
/// anchor `#[account]` macro requires `crate::ID` (program ID).
/// Use `ProgramConfigData` as the inner data in each program's account.
#[derive(AnchorSerialize, AnchorDeserialize, Clone, Debug)]
pub struct ProgramConfigData {
    pub owner: Pubkey,
    pub relayer: Pubkey,
    pub count: u64,
    pub bump: u8,
}

impl ProgramConfigData {
    pub const SIZE: usize = 8 + 32 + 32 + 8 + 1;

    /// Check if signer is owner OR relayer
    pub fn is_authorized(&self, signer: &Pubkey) -> bool {
        signer == &self.owner || signer == &self.relayer
    }

    /// Check if signer is owner only
    pub fn is_owner(&self, signer: &Pubkey) -> bool {
        signer == &self.owner
    }
}

// ── Revert Reason (Escrow) ──────────────────────────────────────────────────
/// Why an escrow was reverted. Matches Solidity RevertReason enum.
#[derive(AnchorSerialize, AnchorDeserialize, Clone, Copy, PartialEq, Eq, Debug)]
#[repr(u8)]
pub enum RevertReason {
    Timeout = 0,
    CoherenceFailure = 1,
    RouteInvalid = 2,
    Manual = 3,
}

impl Default for RevertReason {
    fn default() -> Self {
        RevertReason::Timeout
    }
}

// ── Escrow State ────────────────────────────────────────────────────────────
#[derive(AnchorSerialize, AnchorDeserialize, Clone, Copy, PartialEq, Eq, Debug)]
#[repr(u8)]
pub enum EscrowState {
    Holding = 0,
    Released = 1,
    Reverted = 2,
}

impl Default for EscrowState {
    fn default() -> Self {
        EscrowState::Holding
    }
}

// ── Intent Action Types ─────────────────────────────────────────────────────
/// Matches Solidity Action enum (BTCP §4.1)
#[derive(AnchorSerialize, AnchorDeserialize, Clone, Copy, PartialEq, Eq, Debug)]
#[repr(u8)]
pub enum IntentAction {
    Swap = 0,
    Transfer = 1,
    Liquidity = 2,
    Stake = 3,
    Borrow = 4,
}

impl IntentAction {
    pub fn from_u8(v: u8) -> Result<Self> {
        match v {
            0 => Ok(Self::Swap),
            1 => Ok(Self::Transfer),
            2 => Ok(Self::Liquidity),
            3 => Ok(Self::Stake),
            4 => Ok(Self::Borrow),
            _ => Err(error!(BTCPError::InvalidAction)),
        }
    }
}

impl Default for IntentAction {
    fn default() -> Self {
        IntentAction::Swap
    }
}

// ── Intent Status Lifecycle ────────────────────────────────────────────────
/// Matches Solidity Status enum with valid transition enforcement.
#[derive(AnchorSerialize, AnchorDeserialize, Clone, Copy, PartialEq, Eq, Debug)]
#[repr(u8)]
pub enum IntentStatus {
    Pending = 0,
    Routing = 1,
    Executing = 2,
    Completed = 3,
    Failed = 4,
    Expired = 5,
    Resurrected = 6,
}

impl IntentStatus {
    /// Valid status transitions per whitepaper BTCP §4.1
    pub fn can_transition_to(&self, next: Self) -> bool {
        match self {
            // PENDING → ROUTING, FAILED, EXPIRED
            Self::Pending => matches!(next, Self::Routing | Self::Failed | Self::Expired),
            // ROUTING → EXECUTING, FAILED, EXPIRED
            Self::Routing => matches!(next, Self::Executing | Self::Failed | Self::Expired),
            // EXECUTING → COMPLETED, FAILED
            Self::Executing => matches!(next, Self::Completed | Self::Failed),
            // FAILED → RESURRECTED
            Self::Failed => matches!(next, Self::Resurrected),
            // Terminal states: no outgoing transitions
            _ => false,
        }
    }
}

impl Default for IntentStatus {
    fn default() -> Self {
        IntentStatus::Pending
    }
}

// ── Route Types ─────────────────────────────────────────────────────────────
#[derive(AnchorSerialize, AnchorDeserialize, Clone, Copy, PartialEq, Eq, Debug)]
#[repr(u8)]
pub enum RouteType {
    SingleChain = 0,
    Split = 1,
    Netting = 2,
    Parallel = 3,
    MultiHop = 4,
    Deferred = 5,
    Bitp = 6,
}

impl RouteType {
    pub fn from_u8(v: u8) -> Result<Self> {
        match v {
            0 => Ok(Self::SingleChain),
            1 => Ok(Self::Split),
            2 => Ok(Self::Netting),
            3 => Ok(Self::Parallel),
            4 => Ok(Self::MultiHop),
            5 => Ok(Self::Deferred),
            6 => Ok(Self::Bitp),
            _ => Err(error!(BTCPError::InvalidRouteType)),
        }
    }
}

impl Default for RouteType {
    fn default() -> Self {
        RouteType::SingleChain
    }
}

// ── Finality Level ─────────────────────────────────────────────────────────
#[derive(AnchorSerialize, AnchorDeserialize, Clone, Copy, PartialEq, Eq, Debug)]
#[repr(u8)]
pub enum FinalityLevel {
    Fast = 0,
    Standard = 1,
    Secure = 2,
}

// ── Privacy Mode ────────────────────────────────────────────────────────────
#[derive(AnchorSerialize, AnchorDeserialize, Clone, Copy, PartialEq, Eq, Debug)]
#[repr(u8)]
pub enum PrivacyMode {
    Public = 0,
    ZkCredential = 1,
    Invisible = 2,
}

// ── Error Codes ─────────────────────────────────────────────────────────────
#[error_code]
pub enum BTCPError {
    #[msg("Not authorized — must be owner or relayer")]
    NotAuthorized,

    #[msg("Not owner — must be program owner")]
    NotOwner,

    #[msg("Escrow already exists")]
    EscrowExists,

    #[msg("Escrow not found")]
    EscrowNotFound,

    #[msg("Escrow is not in HOLDING state")]
    NotHolding,

    #[msg("Escrow has expired")]
    Expired,

    #[msg("Coherence score below minimum threshold")]
    CoherenceInsufficient,

    #[msg("Zero amount not allowed")]
    ZeroAmount,

    #[msg("Zero destination not allowed")]
    ZeroDestination,

    #[msg("Invalid coherence score (must be ≤ 1,000,000)")]
    InvalidCoherence,

    #[msg("Timeout blocks must be > 0")]
    ZeroTimeout,

    #[msg("Native SOL transfer failed")]
    TransferFailed,

    #[msg("Refund failed")]
    RefundFailed,

    #[msg("Intent already exists")]
    IntentExists,

    #[msg("Intent not found")]
    IntentNotFound,

    #[msg("Zero magnitude not allowed")]
    ZeroMagnitude,

    #[msg("Deadline is in the past")]
    DeadlinePast,

    #[msg("Invalid action type")]
    InvalidAction,

    #[msg("Invalid finality level")]
    InvalidFinality,

    #[msg("Invalid privacy mode")]
    InvalidPrivacy,

    #[msg("Invalid status transition")]
    InvalidTransition,

    #[msg("Route already exists")]
    RouteExists,

    #[msg("Route not found")]
    RouteNotFound,

    #[msg("Zero anchor behavioral hash")]
    ZeroAnchor,

    #[msg("Zero execution behavioral hash")]
    ZeroExecutionBH,

    #[msg("Route already verified")]
    AlreadyVerified,

    #[msg("Invalid route type")]
    InvalidRouteType,

    #[msg("Invalid score — must be ≤ 1,000,000")]
    InvalidScore,

    #[msg("Arithmetic overflow")]
    Overflow,

    #[msg("Relayer-only: timeout revert can be called by anyone")]
    NotRelayerForRevert,

    #[msg("Insufficient lamports for the requested lock amount")]
    InsufficientFunds,

    #[msg("Invalid argument")]
    InvalidArgument,
}
