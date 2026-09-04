//! Core types for TRION BTCP Zero-Bridge
//! Per BTCP Master Implementation Spec


use sha3::{Digest, Sha3_256};
use std::fmt;

/// 256-bit hash type (HashDNA, BH, intent hashes)
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Default)]
pub struct H256(pub [u8; 32]);

impl H256 {
    pub fn zero() -> Self {
        H256([0u8; 32])
    }

    pub fn from_slice(slice: &[u8]) -> Self {
        let mut arr = [0u8; 32];
        let len = slice.len().min(32);
        arr[..len].copy_from_slice(&slice[..len]);
        H256(arr)
    }

    pub fn from_hex(hex: &str) -> Result<Self, hex::FromHexError> {
        let bytes = hex::decode(hex.trim_start_matches("0x"))?;
        Ok(Self::from_slice(&bytes))
    }

    pub fn to_hex(&self) -> String {
        format!("0x{}", hex::encode(self.0))
    }

    pub fn sha3(data: &[u8]) -> Self {
        let mut hasher = Sha3_256::new();
        hasher.update(data);
        let result = hasher.finalize();
        let mut arr = [0u8; 32];
        arr.copy_from_slice(&result);
        H256(arr)
    }
}

impl fmt::Display for H256 {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.to_hex())
    }
}

/// Behavioral Entity Object ID — substrate-independent identity
pub type BEOId = H256;

/// Chain identifier (EIP-155 chain IDs for EVM, custom for others)
pub type ChainId = u64;

/// Asset identifier
pub type AssetId = String;

/// Semantic version
#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
pub struct SemVer {
    pub major: u32,
    pub minor: u32,
    pub patch: u32,
}

impl SemVer {
    pub fn new(major: u32, minor: u32, patch: u32) -> Self {
        SemVer { major, minor, patch }
    }

    pub fn parse(s: &str) -> Option<Self> {
        let parts: Vec<&str> = s.split('.').collect();
        if parts.len() != 3 {
            return None;
        }
        Some(SemVer {
            major: parts[0].parse().ok()?,
            minor: parts[1].parse().ok()?,
            patch: parts[2].parse().ok()?,
        })
    }
}

impl fmt::Display for SemVer {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}.{}.{}", self.major, self.minor, self.patch)
    }
}

/// Feature flags for BTCP capabilities
#[derive(Debug, Clone, Default)]
pub struct FeatureFlags {
    pub sensing_oracle: bool,
    pub zk_travel_rule: bool,
    pub behavioral_state_channels: bool,
    pub shadow_observation: bool,
    pub genesis_commitment: bool,
}

/// Gas forecast with confidence interval
#[derive(Debug, Clone)]
pub struct GasForecast {
    pub mean: f64,
    pub ci_95_low: f64,
    pub ci_95_high: f64,
}

impl Default for GasForecast {
    fn default() -> Self {
        GasForecast {
            mean: 50.0,
            ci_95_low: 40.0,
            ci_95_high: 60.0,
        }
    }
}

/// Statistical finality distribution
#[derive(Debug, Clone)]
pub struct FinalityDistribution {
    pub mean_sec: f64,
    pub ci95: f64,
    pub safe_confirmations: u64,
}

impl Default for FinalityDistribution {
    fn default() -> Self {
        FinalityDistribution {
            mean_sec: 2.5,
            ci95: 0.95,
            safe_confirmations: 64,
        }
    }
}

/// BEO behavioral state on a specific chain
#[derive(Debug, Clone, Default)]
pub struct BEOState {
    pub entity_id: BEOId,
    pub akashic_depth: f64,
    pub coherence_score: f64,
    pub manipulation_fingerprint: f64,
    pub archetype: String,
}

/// Intent — what the user wants (not how to execute it)
/// Field set covers the BTCP Master Spec §4.1 Intent object. The router
/// legacy fields are kept: `intent_type` ≙ spec `action`, `amount_in` ≙
/// spec `value`, and the spec constraint block lives on
/// [`IntentConstraints`] alongside its legacy fields.
#[derive(Debug, Clone)]
pub struct Intent {
    pub intent_id: H256,
    pub entity_id: BEOId,
    pub source_address: String,
    pub dest_address: String,
    pub source_chain: ChainId,
    pub dest_chain: ChainId,
    pub asset_in: AssetId,
    pub asset_out: AssetId,
    pub amount_in: u128,
    pub intent_type: String,
    pub deadline: u64,
    pub nonce: u64,
    pub constraints: IntentConstraints,
    /// Spec §4.1 `btcp_version` — protocol semver (spec encodes bytes12).
    /// Defaults to the crate's `BTCP_VERSION` major.minor.patch (1.0.0).
    pub btcp_version: SemVer,
}

impl Intent {
    pub fn hash(&self) -> H256 {
        // Legacy 9-field prefix (order preserved) with the spec §4.1
        // fields appended after it — the same append-only extension
        // policy as the Python `BITPIntent::hash` in core/btcp/modules.py
        // (the two objects carry different legacy field sets, so the byte
        // streams differ; the construction policy is identical).
        let max_total_gas = match self.constraints.max_total_gas {
            Some(gas) => gas.to_string(),
            None => "none".to_string(),
        };
        let data = format!(
            "{}:{}:{}:{}:{}:{}:{}:{}:{}:{}:{}:{}:{}:{}:{}",
            self.entity_id.to_hex(),
            self.source_chain,
            self.dest_chain,
            self.asset_in,
            self.asset_out,
            self.amount_in,
            self.intent_type,
            self.deadline,
            self.nonce,
            self.btcp_version,
            max_total_gas,
            self.constraints.min_finality as u8,
            self.constraints.min_nl_score,
            format!("{:?}", self.constraints.chain_pref),
            self.constraints.privacy as u8,
        );
        H256::sha3(data.as_bytes())
    }
}

/// Intent execution constraints
/// Legacy router constraints plus the BTCP Master Spec §4.1 constraint
/// field set (`max_total_gas`, `min_finality`, `min_nl_score`,
/// `chain_pref`, `privacy`).
#[derive(Debug, Clone)]
pub struct IntentConstraints {
    // legacy router constraints
    pub max_slippage: f64,
    pub deadline: u64,
    pub privacy_level: PrivacyLevel,
    pub allow_partial_fill: bool,
    pub allow_deferred: bool,
    // BTCP Master Spec §4.1 constraint fields
    /// USD-equivalent gas ceiling across ALL chains (spec uint128);
    /// `None` = unbounded.
    pub max_total_gas: Option<u128>,
    /// Minimum finality band (spec uint8): FAST | STANDARD | SECURE.
    pub min_finality: MinFinality,
    /// Liquidity-health floor scaled ×1000 (spec uint16; 300 = 0.30).
    pub min_nl_score: u16,
    /// Chain routing preference (spec bytes): OPTIMAL | SINGLE_CHAIN |
    /// explicit allow-list.
    pub chain_pref: ChainPreference,
    /// Spec §4.1 privacy (uint8): PUBLIC | ZK_CREDENTIAL | INVISIBLE.
    /// The legacy 5-tier `privacy_level` is kept alongside and bridges
    /// via [`PrivacyLevel::spec_code`] / [`SpecPrivacy::to_legacy`].
    pub privacy: SpecPrivacy,
}

impl Default for IntentConstraints {
    fn default() -> Self {
        IntentConstraints {
            max_slippage: 0.01,
            deadline: 0,
            privacy_level: PrivacyLevel::Standard,
            allow_partial_fill: true,
            allow_deferred: true,
            // spec §4.1 defaults
            max_total_gas: None,
            min_finality: MinFinality::Standard,
            min_nl_score: 300,
            chain_pref: ChainPreference::Optimal,
            privacy: SpecPrivacy::Public,
        }
    }
}

/// Privacy level for BTCP operations
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PrivacyLevel {
    Public,
    Basic,
    Standard,
    Compliant,
    Full,
}

impl PrivacyLevel {
    /// Spec §4.1 privacy code: PUBLIC = 0, ZK_CREDENTIAL = 1,
    /// INVISIBLE = 2. The legacy Basic/Standard/Compliant tiers all fall
    /// in the spec's ZK_CREDENTIAL band; Full maps to INVISIBLE.
    pub fn spec_code(&self) -> u8 {
        match self {
            PrivacyLevel::Public => 0,
            PrivacyLevel::Basic | PrivacyLevel::Standard | PrivacyLevel::Compliant => 1,
            PrivacyLevel::Full => 2,
        }
    }
}

/// Spec §4.1 min_finality (uint8): FAST | STANDARD | SECURE
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MinFinality {
    Fast = 0,
    Standard = 1,
    Secure = 2,
}

impl Default for MinFinality {
    fn default() -> Self {
        MinFinality::Standard
    }
}

/// Spec §4.1 chain_pref (spec encodes as bytes):
/// OPTIMAL | [chain_list] | SINGLE_CHAIN
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ChainPreference {
    /// Router is free to pick the optimal cross-chain route
    Optimal,
    /// Restrict execution to a single chain
    SingleChain,
    /// Explicit allow-list of chains
    Allowed(Vec<ChainId>),
}

impl Default for ChainPreference {
    fn default() -> Self {
        ChainPreference::Optimal
    }
}

/// Spec §4.1 privacy (uint8): PUBLIC | ZK_CREDENTIAL | INVISIBLE
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SpecPrivacy {
    Public = 0,
    ZkCredential = 1,
    Invisible = 2,
}

impl Default for SpecPrivacy {
    fn default() -> Self {
        SpecPrivacy::Public
    }
}

impl SpecPrivacy {
    /// Map onto the legacy 5-tier [`PrivacyLevel`] used by the router.
    pub fn to_legacy(self) -> PrivacyLevel {
        match self {
            SpecPrivacy::Public => PrivacyLevel::Public,
            SpecPrivacy::ZkCredential => PrivacyLevel::Standard,
            SpecPrivacy::Invisible => PrivacyLevel::Full,
        }
    }
}

/// Route type selection
#[derive(Debug, Clone)]
pub enum RouteType {
    /// Target chain superior across all metrics
    SingleChain,
    /// Anchor on A, execute on B
    Split { anchor: ChainId, exec: ChainId },
    /// Opposite intent found — zero movement
    Netting { counterparty: BEOId },
    /// Large intent split across multiple chains
    Parallel(Vec<ChainId>),
    /// A→B→C intermediate liquidity
    MultiHop { via: ChainId },
    /// BRT scheduling for non-urgent
    Deferred { optimal_window: u64 },
    /// Illiquid pair — behavioral info transfer
    BITP { commitment_hash: H256 },
}

/// A complete BTCP route
#[derive(Debug, Clone)]
pub struct Route {
    pub route_id: H256,
    pub intent: Intent,
    pub route_type: RouteType,
    pub beo_continuity: f64,
    pub btcp_score: f64,
    pub status: RouteStatus,
    pub created_at: u64,
}

/// Route execution status
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RouteStatus {
    Pending,
    IntentCreated,
    ProofsGenerated,
    SourceExecuted,
    DestExecuted,
    Completed,
    Failed,
    TimedOut,
}

/// Weighted validator signature
#[derive(Debug, Clone)]
pub struct WeightedSignature {
    pub validator_id: BEOId,
    pub signature: Vec<u8>,
    pub stake_weight: f64,
    pub diversity_weight: f64,
}

/// Diversity certificate — all diversity weights at emission
#[derive(Debug, Clone)]
pub struct DiversityCertificate {
    pub hhi: f64,
    pub num_validators: u32,
    pub weights: Vec<f64>,
    pub block_number: u64,
}

/// Consensus proof for BTCP
#[derive(Debug, Clone)]
pub struct ConsensusProof {
    pub validator_signatures: Vec<WeightedSignature>,
    pub diversity_cert: DiversityCertificate,
    pub coherence_score: f64,
    pub threshold: f64,
}

/// Complete BTCP proof
#[derive(Debug, Clone)]
pub struct BTCPProof {
    pub anchor_bh: H256,
    pub consensus_proof: ConsensusProof,
    pub intent_hash: H256,
    pub btcp_route_id: H256,
    pub anchor_chain: ChainId,
    pub execution_chain: ChainId,
    pub btcp_version: SemVer,
    pub feature_flags: FeatureFlags,
    pub min_verifier_ver: SemVer,
}

/// BTCP Route Signal — stored on finalization
#[derive(Debug, Clone)]
pub struct BTCPRouteSignal {
    pub route_id: H256,
    pub anchor_chain: ChainId,
    pub anchor_bh: H256,
    pub execution_chain: ChainId,
    pub execution_bh: H256,
    pub entity_id: BEOId,
    pub gas_saved_vs_single_chain: f64,
    pub gas_saved_vs_bridge: f64,
    pub beo_continuity_score: f64,
    pub cc_coherence: f64,
}

/// BIBL analysis result for a single chain
#[derive(Debug, Clone)]
pub struct BIBLAnalysis {
    pub chain_id: ChainId,
    pub nl_score: f64,
    pub gas_forecast: GasForecast,
    pub cc_coherence: f64,
    pub beo_state: BEOState,
    pub mf_score: f64,
    pub block_capacity: f64,
    pub finality_dist: FinalityDistribution,
}

/// Price point at a specific block
#[derive(Debug, Clone)]
pub struct PricePoint {
    pub asset_pair: String,
    pub price: f64,
    pub block_number: u64,
}

/// Governance snapshot
#[derive(Debug, Clone, Default)]
pub struct GovSnapshot {
    pub proposal_id: Option<u64>,
    pub voting_power: u128,
    pub state: String,
}

/// Behavioral State Capsule — cross-chain state dissolved into anchor
#[derive(Debug, Clone)]
pub struct BehavioralStateCapsule {
    pub anchor_chain: ChainId,
    pub anchor_block: u64,
    pub block_hash_a: H256,
    pub price_a: PricePoint,
    pub balance_x: u128,
    pub gov_state: GovSnapshot,
    pub staleness_ci95: (f64, f64),
    pub escrow_lock: bool,
}

/// Shadow source for hostile chain observation
#[derive(Debug, Clone)]
pub struct ShadowSource {
    pub event_hash: H256,
    pub confidence_weight: f64,
    pub diversity_factor: f64,
    pub source_chain: ChainId,
    /// Provenance disclosure: `true` when this source was fabricated by
    /// `ShadowObserver::collect_shadow_sources` (placeholder simulation
    /// derived from timestamps — NOT real indexer data) rather than read
    /// from a real indexer / oracle / DEX / governance feed. Downstream
    /// consumers MUST check this flag before trusting the source.
    pub simulated: bool,
}

/// Route failure information
#[derive(Debug, Clone)]
pub struct RouteFailure {
    pub route_id: H256,
    pub anchor_chain: ChainId,
    pub execution_chain: ChainId,
    pub entity_id: BEOId,
    pub failure_type: String,
    pub timestamp: u64,
}

/// Failure cause classification
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FailureCause {
    External,
    Entity,
    Ambiguous,
}

/// BLO status
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BLOStatus {
    Open,
    PartiallyFilled,
    Filled,
    Expired,
}

/// Behavioral Limit Order
#[derive(Debug, Clone)]
pub struct BehavioralLimitOrder {
    pub commitment: H256,
    pub entity_id: BEOId,
    pub intent: Intent,
    pub expiry_block: u64,
    pub status: BLOStatus,
    pub filled_amount: u128,
}

/// Channel state for BSC
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ChannelState {
    Closed,
    Opening,
    Open,
    Closing,
    Disputed,
}

/// Behavioral State Channel
#[derive(Debug, Clone)]
pub struct BehavioralStateChannelData {
    pub channel_id: H256,
    pub entity_a: BEOId,
    pub entity_b: BEOId,
    pub chain_a: ChainId,
    pub chain_b: ChainId,
    pub collateral_a: u128,
    pub collateral_b: u128,
    pub state: ChannelState,
    pub interaction_count: u64,
    pub akashic_record: H256,
}

/// Intent pool for IAP aggregation
#[derive(Debug, Clone)]
pub struct IntentPool {
    pub direction: (AssetId, AssetId),
    pub participants: Vec<(BEOId, u128)>,
    pub total_value: u128,
    pub window_deadline: u64,
    pub min_size: usize,
}

/// OOA configuration for non-integrated chains
#[derive(Debug, Clone)]
pub struct OOAConfig {
    pub chain_id: ChainId,
    pub observation_depth: u64,
    pub ooa_conf: f64,
    pub ooa_penalty_factor: f64,
}

/// Validator information for fee calculation
#[derive(Debug, Clone)]
pub struct Validator {
    pub id: BEOId,
    pub covered_chains: Vec<ChainId>,
    pub stake: u128,
}

/// Time period for fee calculation
#[derive(Debug, Clone)]
pub struct Period {
    pub start_block: u64,
    pub end_block: u64,
    pub duration_seconds: u64,
}

/// Genesis pathway for null-state entities
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GenesisPathway {
    Stake,
    Signature,
    SocialProof,
}

/// Rejoin result for previously hostile chains
#[derive(Debug, Clone)]
pub struct RejoinResult {
    pub chain_id: ChainId,
    pub shadow_depth_transferred: f64,
    pub new_bridge_pairs_eliminated: u64,
    pub success: bool,
}

/// Dispute resolution vote
#[derive(Debug, Clone)]
pub struct DisputeVote {
    pub voter_id: BEOId,
    pub vote: bool,
    pub rationale_hash: H256,
    pub timestamp: u64,
}

/// Dispute case
#[derive(Debug, Clone)]
pub struct DisputeCase {
    pub case_id: H256,
    pub route_id: H256,
    pub claimant: BEOId,
    pub respondent: BEOId,
    pub votes: Vec<DisputeVote>,
    pub resolved: bool,
    pub outcome: Option<bool>,
}
