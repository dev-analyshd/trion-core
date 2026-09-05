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
/// TRION epoch-registry PDA namespace: ["trion", "validators", epoch_be]
/// (master command §10; the SVM equivalent of the EIP-712 domain salt —
/// CANONICAL_CERTIFICATE.md §7 Solana row).
pub const SEED_TRION: &[u8] = b"trion";
pub const SEED_VALIDATORS: &[u8] = b"validators";
/// Consumed-certificate PDA namespace: ["trion", "consumed", escrow_id]
/// (replay/equivocation tracking, CANONICAL_CERTIFICATE.md §8).
pub const SEED_CONSUMED: &[u8] = b"consumed";

// ── Canonical Certificate Constants (CANONICAL_CERTIFICATE.md) ────────────────
// Mirrors core/consensus/certificate.py — the py reference encoder is the
// normative twin; every value here is pinned by
// tests/contracts/test_btcp_escrow_svm.py static parity checks.

/// Domain tag — offset 0, 13 bytes (§2).
pub const CERT_DOMAIN_TAG: &[u8] = b"TRION-CERT-V1";
/// Total signed payload width (§2) — the single most important constant.
pub const CERT_PAYLOAD_WIDTH: usize = 346;
/// certificate_kind 1 = ESCROW_RELEASE (§2; unknown kinds fail closed, §6.1).
pub const CERT_KIND_ESCROW_RELEASE: u8 = 1;
/// Signature family 2 = Ed25519 (§3.2) — the SVM family. Raw P is signed.
pub const CERT_FAMILY_ED25519: u8 = 2;
/// Ed25519 signature width (§4).
pub const CERT_ED25519_SIG_LEN: usize = 64;
/// Highest protocol_version (uint24 semver) this build verifies: 1.0.0.
pub const CERT_SUPPORTED_VERSION: u32 = 1u32 << 16;
/// Minimum distinct signers — liveness floor (§4 invariant 4).
pub const CERT_MIN_SIGNERS: usize = 3;
/// Verifier epoch grace window in epochs (§10.2, ED-G).
pub const CERT_EPOCH_GRACE: u32 = 2;
/// L4.8 CRITICAL HHI bound on the ×1e4 scale (§5.3) — above it the
/// certificate is INVALID.
pub const CERT_HHI_MAX: u64 = 4_000;
/// Canonical maximum TTL in seconds (§9.2 — no certificate outlives a full
/// epoch-rotation cycle).
pub const CERT_TTL_MAX: u64 = 604_800;
/// Clock drift tolerance in seconds (§9.1) — widens the freshness LOWER
/// bound only; expiry is never widened.
pub const CERT_DRIFT_TOLERANCE_SECS: u64 = 60;
/// L4.2 tier boundaries on D_consensus (×1e6): ≥ 600_000 → tier 1 (2/3
/// STRICT); ≥ 400_000 → tier 2 (0.75); below → tier 3 (0.85).
pub const D_CONSENSUS_TIER1: u64 = 600_000;
pub const D_CONSENSUS_TIER2: u64 = 400_000;
/// Registry size bound (account size + compute bound; the spec target is
/// 100 validators — V2 §9.2).
pub const MAX_VALIDATORS: usize = 256;
/// E6 emergency-revert escape hatch (BTCP_STATE_MACHINE.md M2): anyone may
/// revert a HOLDING escrow after 7 days even if TRION is silent or paused.
pub const EMERGENCY_REVERT_SECONDS: i64 = 7 * 24 * 60 * 60;

// ── Scaling Constants ────────────────────────────────────────────────────────
/// Coherence scores are stored ×1e6 (0 to 1,000,000)
pub const SCALE: u64 = 1_000_000;

/// Maximum valid coherence score
pub const MAX_COHERENCE: u64 = 1_000_000;

/// INV-003 (follow-on 2 ruling): the protocol coherence floor Θ_min
/// 0.55 ×1e6 — the same number as core/btcp/escrow_monitor.py
/// MIN_COHERENCE_FLOOR and the Move twin's MIN_COHERENCE_FLOOR. A
/// locker may TIGHTEN their gate (up to MAX_COHERENCE); never loosen
/// it below the floor — sub-floor values are rejected AT LOCK
/// (fail-fast, Move/Cairo parity).
pub const MIN_COHERENCE_FLOOR: u64 = 550_000;

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
    /// E6 emergency escape: permissionless revert after 7 days
    /// (BTCP_STATE_MACHINE.md M2 E6).
    Emergency = 4,
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
    /// Terminal E6 state — permissionless 7-day escape (M2 E6). No
    /// outgoing transitions.
    EmergencyReverted = 3,
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

    #[msg("INV-003: coherence below the 0.55 protocol floor (tighten-only)")]
    CoherenceFloor,

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

    // ── Canonical certificate verification (C-03 closure) ──────────────────
    #[msg("Certificate payload malformed — wrong width or domain tag")]
    MalformedCertificate,

    #[msg("Unknown certificate kind — only ESCROW_RELEASE (1) is accepted")]
    UnknownCertificateKind,

    #[msg("Certificate protocol version is newer than this build supports")]
    VersionIncompatible,

    #[msg("Envelope family is not ed25519 (family 2) — SVM verifies family 2 only")]
    WrongSignatureFamily,

    #[msg("Fewer than 3 distinct validator signatures")]
    InsufficientSigners,

    #[msg("Signature malformed (not 64 bytes)")]
    MalformedSignature,

    #[msg("ed25519 signature verification failed (the whole certificate fails)")]
    SignatureVerificationFailed,

    #[msg("Duplicate validator signer in the envelope")]
    DuplicateSigner,

    #[msg("Certificate epoch argument does not match the payload epoch")]
    EpochArgumentMismatch,

    #[msg("No validator epoch registered — certificates cannot be verified (fail-closed)")]
    NoEpochRegistered,

    #[msg("Certificate epoch is newer than the latest registered epoch")]
    EpochFuture,

    #[msg("Certificate epoch is older than the verifier grace window (2 epochs)")]
    EpochStale,

    #[msg("Registry account epoch does not match the certificate epoch")]
    RegistryEpochMismatch,

    #[msg("Certificate TTL is zero or above the 7-day canonical maximum")]
    InvalidTtl,

    #[msg("Certificate expired (now > issued_at + ttl)")]
    CertificateExpired,

    #[msg("Certificate dated too far in the future (> 60s drift tolerance)")]
    CertificateFutureDated,

    #[msg("HHI at emission above the L4.8 CRITICAL bound (4000)")]
    HhiCritical,

    #[msg("AWA was not enforced at emission — emission was frozen (MD §17)")]
    AwaNotEnforced,

    #[msg("Certificate coherence is below the emission threshold")]
    CoherenceBelowThreshold,

    #[msg("Certificate validator_count does not match the registered epoch set")]
    ValidatorCountMismatch,

    #[msg("Registered validator count is below the deployment launch threshold")]
    TooFewValidators,

    #[msg("Validator is not registered in this epoch's set")]
    UnregisteredValidator,

    #[msg("Envelope weight claim does not match the registered epoch-set weight")]
    WeightClaimMismatch,

    #[msg("Certificate total_effective_power does not match the registered set")]
    PowerMismatch,

    #[msg("Registry total_effective_power claim does not match its own entries")]
    RegistryPowerMismatch,

    #[msg("Certificate threshold does not match the registered epoch threshold")]
    ThresholdMismatch,

    #[msg("Signed effective power is below the L4.2 tier quorum")]
    InsufficientQuorum,

    #[msg("Certificate escrow_id does not match this escrow")]
    EscrowMismatch,

    #[msg("Certificate route_id does not match the escrow route")]
    RouteMismatch,

    #[msg("Certificate intent_hash does not match the escrow intent")]
    IntentMismatch,

    #[msg("Certificate entity_id does not match the escrow entity")]
    EntityMismatch,

    #[msg("Certificate destination does not match the escrow destination")]
    DestinationMismatch,

    #[msg("Certificate amount does not match the escrow amount")]
    AmountMismatch,

    #[msg("Certificate amount does not fit Solana native u64 (lamports)")]
    AmountTooLarge,

    #[msg("Certificate source/dest chain does not match the escrow route legs")]
    ChainMismatch,

    #[msg("Certificate dest_chain is not this deployment's chain id")]
    WrongChain,

    #[msg("Certificate anchor_bh does not match the escrow anchor BH")]
    AnchorMismatch,

    #[msg("Certificate execution_bh does not match the escrow execution BH")]
    ExecutionMismatch,

    #[msg("Certificate conflicts with an already-consumed certificate (equivocation evidence)")]
    CertificateConflict,

    #[msg("Replayed certificate is inconsistent with the escrow state")]
    InconsistentReplayState,

    #[msg("Program is paused — new locks are blocked (release/revert continue)")]
    Paused,

    #[msg("Invalid epoch — epochs start at 1 and must strictly increase")]
    InvalidEpoch,

    #[msg("Epoch already registered — epoch sets are immutable, rotation at boundary only")]
    EpochAlreadyRegistered,

    #[msg("Invalid validator set — empty or above MAX_VALIDATORS")]
    InvalidValidatorSet,

    #[msg("Duplicate validator id in the registered set")]
    DuplicateValidator,

    #[msg("Duplicate validator ed25519 pubkey in the registered set")]
    DuplicateValidatorKey,

    #[msg("Invalid weight — stake must be in (0, 1e6], diversity in [0, 1e6], ×1e6")]
    InvalidWeight,

    #[msg("Epoch set effective power must be > 0")]
    ZeroPower,

    #[msg("Epoch threshold must be in [1, 1e6] on the ×1e6 scale")]
    InvalidThreshold,

    #[msg("Not the validator-registry admin")]
    NotRegistryAdmin,

    #[msg("Zero intent hash not allowed")]
    ZeroIntentHash,

    #[msg("Zero chain id not allowed")]
    ZeroChain,

    #[msg("Registry data corrupt — count does not match entries")]
    RegistryCorrupt,

    #[msg("Invalid clock — negative unix timestamp")]
    InvalidClock,

    #[msg("Cannot read the instructions sysvar (the signature-introspection source)")]
    InvalidInstructionSysvar,
}
