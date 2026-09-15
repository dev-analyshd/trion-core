use serde::{Deserialize, Serialize};

/// The 19+ TRION signal types (whitepaper Part 5).
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum SignalType {
    Valuation,
    Silence,
    ManipulationAlert,
    Genesis,
    Resurrection,
    ForkDivergence,
    Trajectory,
    NegativeSpace,
    PhaseTransition,
    SystemicRisk,
    LiquidityHealth,
    GovernanceSignal,
    CrossChainCoherence,
    StablecoinHealth,
    MevExposure,
    InstitutionalBehavioral,
    RegulatoryBehavioral,
    EcosystemHealth,
    Bootstrap,
}

impl SignalType {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Valuation => "VALUATION",
            Self::Silence => "SILENCE",
            Self::ManipulationAlert => "MANIPULATION_ALERT",
            Self::Genesis => "GENESIS",
            Self::Resurrection => "RESURRECTION",
            Self::ForkDivergence => "FORK_DIVERGENCE",
            Self::Trajectory => "TRAJECTORY",
            Self::NegativeSpace => "NEGATIVE_SPACE",
            Self::PhaseTransition => "PHASE_TRANSITION",
            Self::SystemicRisk => "SYSTEMIC_RISK",
            Self::LiquidityHealth => "LIQUIDITY_HEALTH",
            Self::GovernanceSignal => "GOVERNANCE_SIGNAL",
            Self::CrossChainCoherence => "CROSS_CHAIN_COHERENCE",
            Self::StablecoinHealth => "STABLECOIN_HEALTH",
            Self::MevExposure => "MEV_EXPOSURE",
            Self::InstitutionalBehavioral => "INSTITUTIONAL_BEHAVIORAL",
            Self::RegulatoryBehavioral => "REGULATORY_BEHAVIORAL",
            Self::EcosystemHealth => "ECOSYSTEM_HEALTH",
            Self::Bootstrap => "BOOTSTRAP",
        }
    }
}

/// Five-plane breakdown (whitepaper Part 5).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlaneBreakdown {
    pub physical: f64,    // Phi_adj
    pub mental: f64,      // M_adj
    pub spiritual: f64,   // Sigma
    pub conscious: f64,   // K
    pub anima: f64,       // A
    pub limiting_plane: String,
}

/// Biological time (whitepaper Part 5, L6.2).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BiologicalTime {
    pub circadian_phase: f64,
    pub ultradian_phase: f64,
    pub lunar_phase: f64,
    pub seasonal_phase: f64,
}

/// TRIONSignal — complete schema (whitepaper Part 5).
/// No field optional. No partial signals.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TRIONSignal {
    // Identity
    pub signal_id: String,
    pub signal_type: String,
    pub entity_id: String,
    // Content
    pub signal_value: f64,
    pub ci_95: [f64; 2],
    // Coherence state
    pub coherence: f64,
    pub threshold: f64,
    pub margin: f64,
    pub plane_breakdown: PlaneBreakdown,
    // Quality metadata
    pub temporal_coherence: f64,
    pub entropy: f64,
    pub akashic_depth: f64,
    pub observer_effect: f64,
    pub bootstrap_phase: bool,
    pub conf_genesis: f64,
    pub reflexivity_flag: bool,
    // Living security
    pub genomic_signature: String,
    pub immune_clearance: bool,
    pub security_generation: u32,
    // Provenance
    pub provenance: Vec<serde_json::Value>,
    pub validator_count: u32,
    pub validator_hhi: f64,
    // Timing
    pub timestamp: i64,
    pub ttl_seconds: u64,
    pub biological_time: BiologicalTime,
}

/// Asset type profiles (whitepaper L5.2).
#[derive(Debug, Clone, Copy)]
pub enum AssetType {
    NewToken,
    Mature,
    Stablecoin,
    Governance,
    Bridge,
    Wrapped,
}

impl AssetType {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::NewToken => "NEW_TOKEN",
            Self::Mature => "MATURE",
            Self::Stablecoin => "STABLECOIN",
            Self::Governance => "GOVERNANCE",
            Self::Bridge => "BRIDGE",
            Self::Wrapped => "WRAPPED",
        }
    }
}

/// Weight profiles (whitepaper L5.2).
#[derive(Debug, Clone, Copy)]
pub enum WeightProfile {
    Balanced,
    Speed,
    Intelligence,
    Certainty,
    FullSpectrum,
}

impl WeightProfile {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Balanced => "BALANCED",
            Self::Speed => "SPEED",
            Self::Intelligence => "INTELLIGENCE",
            Self::Certainty => "CERTAINTY",
            Self::FullSpectrum => "FULL_SPECTRUM",
        }
    }
}
