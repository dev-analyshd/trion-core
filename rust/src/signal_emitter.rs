//! signal_emitter.rs — §14.2 Signal Emissions (BTCP Master Implementation
//! Spec §14.2, lines 2073–2101)
//!
//! The Rust crate previously emitted ZERO signals (AUDIT-RUST [MISSING]
//! item 3 — emission lived only in Python `core/master/signal_factory.py`
//! and the TS SDK). This module ports the canonical 24-type signal
//! registry and the master-equation emission gate to Rust.
//!
//! Registry parity (ids 0–23, exact names):
//!   - `core/master/signal_factory.py::SignalType` (IntEnum, ids 0–23) —
//!     the canonical registry.
//!   - `sdk/src/wasm/signal_processor.wat` globals `$ST_VALUATION` …
//!     `$ST_CONSENSUS_ADAPT` (0–23) — byte-identical ids.
//!
//! Emission gate (whitepaper §3, BTCP spec §14.2):
//!   T(t) = [C(t) ≥ Θ(t)] · S(t) · e^(M_moat · t)
//!   [C ≥ Θ] = 1 → VALUATION emits (payload = T(t))
//!   [C ≥ Θ] = 0 → SILENCE emits (payload = coherence gap Θ − C)
//!
//! "Silence is information": an incoherent entity does NOT emit nothing —
//! it emits a SILENCE signal carrying the gap (the phantom-type invariant
//! SILENCE ≠ VALUATION is Theorem T2 in `formal/src/TRION/Theorems.hs`).
//! Note the spec §14.2 list contains additional BTCP-specific TS-side
//! names (BEHAVIORAL_TRUTH, SHADOW_CHAIN, LIQUIDITY_OCEAN,
//! CHAIN_RELIABILITY, BTCP_ESCROW_EVENT, BTCP_TIMEOUT,
//! GENESIS_COMMITMENT); those exist in NO canonical registry (Python /
//! wasm use the 24 ids below — see AUDIT-FORMAL-DB SDK drift findings) and
//! are therefore NOT added here.

use crate::master_equation::{coherence, master_equation, threshold, FivePlanes, PlaneWeights};
use crate::types::BEOId;

/// Number of canonical signal types in the registry (Python `signal_factory`
/// asserts `len(sigs) == 24`; wasm `signal_type_count` = 24).
pub const SIGNAL_TYPE_COUNT: usize = 24;

/// Canonical signal type registry — ids 0–23.
///
/// Variant ids mirror `SignalType` in `core/master/signal_factory.py`
/// (IntEnum) and the wasm `$ST_*` globals exactly; `name()` returns the
/// canonical SCREAMING_SNAKE registry string.
#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum SignalType {
    /// Signal value published — coherence cleared the threshold gate
    Valuation = 0,
    /// Coherence below threshold — silence is information
    Silence = 1,
    /// Manipulation fingerprint detected (BLOCK_IMMEDIATELY)
    ManipulationAlert = 2,
    /// New entity/asset genesis commitment
    Genesis = 3,
    /// Failed route recovery options
    Resurrection = 4,
    /// Chain fork divergence detected
    ForkDivergence = 5,
    /// Long-horizon behavioral trajectory change
    Trajectory = 6,
    /// Structural absence — the information not carried
    NegativeSpace = 7,
    /// Regime / phase transition detected
    PhaseTransition = 8,
    /// Systemic risk propagation warning
    SystemicRisk = 9,
    /// Liquidity health alert (NL < 0.30)
    LiquidityHealth = 10,
    /// Governance signal (proposal / voting power state)
    GovernanceSignal = 11,
    /// Cross-chain behavioral coherence
    CrossChainCoherence = 12,
    /// Stablecoin health signal
    StablecoinHealth = 13,
    /// MEV exposure (Python alias history: MEV_BEHAVIORAL → MEV_EXPOSURE)
    MevExposure = 14,
    /// Institutional behavior
    InstitutionalBhv = 15,
    /// Regulatory behavior
    RegulatoryBhv = 16,
    /// Ecosystem health
    EcosystemHealth = 17,
    /// Bootstrap-phase entity signal
    Bootstrap = 18,
    /// L8.1 SBA — sovereign entity behavioral divergence
    SovereignBehavioral = 19,
    /// L7.2 EP — energy participation index signal
    EnergyParticipation = 20,
    /// L6.1 BC — biological capital ecosystem health
    BiologicalCapital = 21,
    /// BIBL — behavioral transaction continuity routing
    BtcpRoute = 22,
    /// L4.1 — adaptive consensus mechanism state change
    ConsensusAdaptation = 23,
}

impl SignalType {
    /// Canonical registry id (0–23) — matches the Python IntEnum value and
    /// the wasm `$ST_*` globals.
    pub fn id(&self) -> u8 {
        *self as u8
    }

    /// Canonical registry name (e.g. `"CROSS_CHAIN_COHERENCE"`), identical
    /// to the Python `SignalType` member names.
    pub fn name(&self) -> &'static str {
        match self {
            SignalType::Valuation => "VALUATION",
            SignalType::Silence => "SILENCE",
            SignalType::ManipulationAlert => "MANIPULATION_ALERT",
            SignalType::Genesis => "GENESIS",
            SignalType::Resurrection => "RESURRECTION",
            SignalType::ForkDivergence => "FORK_DIVERGENCE",
            SignalType::Trajectory => "TRAJECTORY",
            SignalType::NegativeSpace => "NEGATIVE_SPACE",
            SignalType::PhaseTransition => "PHASE_TRANSITION",
            SignalType::SystemicRisk => "SYSTEMIC_RISK",
            SignalType::LiquidityHealth => "LIQUIDITY_HEALTH",
            SignalType::GovernanceSignal => "GOVERNANCE_SIGNAL",
            SignalType::CrossChainCoherence => "CROSS_CHAIN_COHERENCE",
            SignalType::StablecoinHealth => "STABLECOIN_HEALTH",
            SignalType::MevExposure => "MEV_EXPOSURE",
            SignalType::InstitutionalBhv => "INSTITUTIONAL_BHV",
            SignalType::RegulatoryBhv => "REGULATORY_BHV",
            SignalType::EcosystemHealth => "ECOSYSTEM_HEALTH",
            SignalType::Bootstrap => "BOOTSTRAP",
            SignalType::SovereignBehavioral => "SOVEREIGN_BEHAVIORAL",
            SignalType::EnergyParticipation => "ENERGY_PARTICIPATION",
            SignalType::BiologicalCapital => "BIOLOGICAL_CAPITAL",
            SignalType::BtcpRoute => "BTCP_ROUTE",
            SignalType::ConsensusAdaptation => "CONSENSUS_ADAPTATION",
        }
    }

    /// Reverse lookup by canonical registry id. Returns `None` for ids
    /// outside 0–23 (the wasm module likewise rejects type_id > 23).
    pub fn from_id(id: u8) -> Option<SignalType> {
        match id {
            0 => Some(SignalType::Valuation),
            1 => Some(SignalType::Silence),
            2 => Some(SignalType::ManipulationAlert),
            3 => Some(SignalType::Genesis),
            4 => Some(SignalType::Resurrection),
            5 => Some(SignalType::ForkDivergence),
            6 => Some(SignalType::Trajectory),
            7 => Some(SignalType::NegativeSpace),
            8 => Some(SignalType::PhaseTransition),
            9 => Some(SignalType::SystemicRisk),
            10 => Some(SignalType::LiquidityHealth),
            11 => Some(SignalType::GovernanceSignal),
            12 => Some(SignalType::CrossChainCoherence),
            13 => Some(SignalType::StablecoinHealth),
            14 => Some(SignalType::MevExposure),
            15 => Some(SignalType::InstitutionalBhv),
            16 => Some(SignalType::RegulatoryBhv),
            17 => Some(SignalType::EcosystemHealth),
            18 => Some(SignalType::Bootstrap),
            19 => Some(SignalType::SovereignBehavioral),
            20 => Some(SignalType::EnergyParticipation),
            21 => Some(SignalType::BiologicalCapital),
            22 => Some(SignalType::BtcpRoute),
            23 => Some(SignalType::ConsensusAdaptation),
            _ => None,
        }
    }
}

/// The full registry in id order (index == registry id).
pub const ALL_SIGNAL_TYPES: [SignalType; SIGNAL_TYPE_COUNT] = [
    SignalType::Valuation,
    SignalType::Silence,
    SignalType::ManipulationAlert,
    SignalType::Genesis,
    SignalType::Resurrection,
    SignalType::ForkDivergence,
    SignalType::Trajectory,
    SignalType::NegativeSpace,
    SignalType::PhaseTransition,
    SignalType::SystemicRisk,
    SignalType::LiquidityHealth,
    SignalType::GovernanceSignal,
    SignalType::CrossChainCoherence,
    SignalType::StablecoinHealth,
    SignalType::MevExposure,
    SignalType::InstitutionalBhv,
    SignalType::RegulatoryBhv,
    SignalType::EcosystemHealth,
    SignalType::Bootstrap,
    SignalType::SovereignBehavioral,
    SignalType::EnergyParticipation,
    SignalType::BiologicalCapital,
    SignalType::BtcpRoute,
    SignalType::ConsensusAdaptation,
];

/// A signal emission (§14.2). Mirrors the core fields of the Python
/// `build_signal` payload that survive in a substrate-independent Rust
/// crate; the Python factory additionally carries CI_95, BRT phases,
/// genomic signature and provenance lists (see
/// `core/master/signal_factory.py`).
///
/// Payload encoding (both gate outcomes):
///   - VALUATION: 8-byte big-endian f64 of T(t)
///   - SILENCE:   8-byte big-endian f64 of the coherence gap (Θ − C),
///     mirroring `coherence_gap` / `silence_explanation` in
///     `build_silence`.
#[derive(Debug, Clone)]
pub struct Signal {
    /// Emitted signal type (registry id 0–23)
    pub signal_type: SignalType,
    /// Behavioral Entity Object the signal is about
    pub entity_id: BEOId,
    /// C(t) at evaluation time
    pub coherence: f64,
    /// Θ(t) at evaluation time (dynamic threshold)
    pub threshold: f64,
    /// Emission timestamp (unix seconds, caller-supplied — this crate has
    /// no clock dependency)
    pub emitted_at: u64,
    /// Type-specific payload bytes (see struct docs for the gate encoding)
    pub payload: Option<Vec<u8>>,
}

impl Signal {
    /// Decode the 8-byte big-endian f64 payload produced by the emission
    /// gate (T(t) for VALUATION, coherence gap for SILENCE). `None` when
    /// the payload is absent or not 8 bytes.
    pub fn decode_payload_f64(&self) -> Option<f64> {
        let bytes = self.payload.as_ref()?;
        if bytes.len() != 8 {
            return None;
        }
        let mut arr = [0u8; 8];
        arr.copy_from_slice(&bytes[..8]);
        Some(f64::from_bits(u64::from_be_bytes(arr)))
    }

    /// True when this emission is SILENCE — the "silence is information"
    /// invariant (Theorem T2: SILENCE ≠ VALUATION at the type level in
    /// `formal/src/TRION/Theorems.hs`; here enforced by enum identity).
    pub fn is_silence(&self) -> bool {
        self.signal_type == SignalType::Silence
    }
}

/// Signal emitter applying the whitepaper §3 master-equation gate:
/// T(t) = [C ≥ Θ] · S · e^(M·t).
///
/// Five-plane C(t) enters as input (computed via
/// [`crate::master_equation::coherence`]); Θ(t) is derived from the
/// volatility input. The gate outcome selects the emitted type:
/// VALUATION (coherent) or SILENCE (incoherent).
#[derive(Debug, Clone, Default)]
pub struct SignalEmitter;

impl SignalEmitter {
    pub fn new() -> Self {
        SignalEmitter
    }

    /// Emit through the master-equation gate using five-plane C(t).
    ///
    /// C(t) = Σ weights × planes; Θ(t) = 0.55 + 0.37·clamp(V, 0, 1);
    /// S(t) falls back to C(t) — "coherence IS the truth measure"
    /// (mirrors `MasterEquation.compute` in
    /// `core/master/master_equation.py`, S fallback path).
    ///
    /// - C ≥ Θ → VALUATION, payload = T(t) as 8-byte BE f64
    /// - C < Θ → SILENCE, payload = coherence gap (Θ − C) as 8-byte BE f64
    ///
    /// NaN plane scores compare false against the threshold and therefore
    /// produce SILENCE (no valuation is ever emitted from an undefined
    /// coherence — the honest outcome).
    pub fn emit(
        &self,
        entity_id: BEOId,
        planes: &FivePlanes,
        weights: &PlaneWeights,
        volatility: f64,
        moat: f64,
        time_years: f64,
        emitted_at: u64,
    ) -> Signal {
        let c = coherence(planes, weights);
        let theta = threshold(volatility);
        self.emit_from_coherence(entity_id, c, theta, None, moat, time_years, emitted_at)
    }

    /// Same gate with a caller-supplied signal value S(t) (e.g. a price
    /// estimate) instead of the C(t) fallback.
    pub fn emit_with_value(
        &self,
        entity_id: BEOId,
        planes: &FivePlanes,
        weights: &PlaneWeights,
        volatility: f64,
        signal_value: f64,
        moat: f64,
        time_years: f64,
        emitted_at: u64,
    ) -> Signal {
        let c = coherence(planes, weights);
        let theta = threshold(volatility);
        self.emit_from_coherence(
            entity_id,
            c,
            theta,
            Some(signal_value),
            moat,
            time_years,
            emitted_at,
        )
    }

    /// Build a non-gated signal of an arbitrary registry type
    /// (e.g. `BTCP_ROUTE` on finalization, `RESURRECTION` from the failure
    /// classifier). NO master-equation gate is applied for these types —
    /// the caller owns the emission condition, exactly as the Python
    /// `build_*` factories do (only VALUATION/SILENCE are gate-selected).
    pub fn emit_typed(
        &self,
        signal_type: SignalType,
        entity_id: BEOId,
        coherence: f64,
        threshold: f64,
        emitted_at: u64,
        payload: Option<Vec<u8>>,
    ) -> Signal {
        Signal {
            signal_type,
            entity_id,
            coherence,
            threshold,
            emitted_at,
            payload,
        }
    }

    /// Shared gate core: apply [C ≥ Θ]·S·e^(M·t) and package the signal.
    fn emit_from_coherence(
        &self,
        entity_id: BEOId,
        c: f64,
        theta: f64,
        s_override: Option<f64>,
        moat: f64,
        time_years: f64,
        emitted_at: u64,
    ) -> Signal {
        let s = s_override.unwrap_or(c);
        match master_equation(c, theta, s, moat, time_years) {
            Some(t_val) => Signal {
                signal_type: SignalType::Valuation,
                entity_id,
                coherence: c,
                threshold: theta,
                emitted_at,
                payload: Some(t_val.to_be_bytes().to_vec()),
            },
            None => Signal {
                signal_type: SignalType::Silence,
                entity_id,
                coherence: c,
                threshold: theta,
                emitted_at,
                payload: Some((theta - c).max(0.0).to_be_bytes().to_vec()),
            },
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn planes_all(v: f64) -> FivePlanes {
        FivePlanes {
            phi_adj: v,
            m_adj: v,
            sigma: v,
            k_plane: v,
            anima: v,
        }
    }

    /// Coherent entity (C = 0.9 ≥ Θ = 0.587) → VALUATION with payload T(t).
    #[test]
    fn test_coherent_emits_valuation() {
        let emitter = SignalEmitter::new();
        let entity = BEOId::from_slice(b"coherent-entity");
        let signal = emitter.emit(
            entity,
            &planes_all(0.9),
            &PlaneWeights::DEFAULT_BALANCED,
            0.1, // Θ = 0.55 + 0.037 = 0.587
            0.5, // moat
            2.0, // t → T = 0.9 · e^1 = 2.4464536456131407
            1_700_000_000,
        );

        assert_eq!(signal.signal_type, SignalType::Valuation);
        assert!(!signal.is_silence());
        assert_eq!(signal.entity_id, entity);
        assert_eq!(signal.emitted_at, 1_700_000_000);
        assert!((signal.coherence - 0.9).abs() < 1e-9);
        assert!((signal.threshold - 0.587).abs() < 1e-9);
        let t = signal.decode_payload_f64().expect("valuation payload decodes");
        assert!((t - 2.4464536456131407).abs() < 1e-9);
    }

    /// Incoherent entity (C = 0.2 < Θ = 0.587) → SILENCE carrying the gap
    /// ("silence is information" — the emission is a SILENCE signal, not
    /// nothing).
    #[test]
    fn test_incoherent_emits_silence() {
        let emitter = SignalEmitter::new();
        let entity = BEOId::from_slice(b"incoherent-entity");
        let signal = emitter.emit(
            entity,
            &planes_all(0.2),
            &PlaneWeights::DEFAULT_BALANCED,
            0.1, // Θ = 0.587, gap = 0.387
            0.5,
            2.0,
            42,
        );

        assert_eq!(signal.signal_type, SignalType::Silence);
        assert!(signal.is_silence());
        assert_eq!(signal.entity_id, entity);
        assert!((signal.coherence - 0.2).abs() < 1e-9);
        assert!((signal.threshold - 0.587).abs() < 1e-9);
        let gap = signal.decode_payload_f64().expect("silence payload decodes");
        assert!((gap - 0.387).abs() < 1e-9);
    }

    /// Boundary C == Θ emits VALUATION (inclusive [C ≥ Θ] gate).
    /// Construction chosen for exact f64 equality (verified against
    /// Python): all planes 0.55 → C == 0.55 exactly; Θ(0) == 0.55 exactly.
    #[test]
    fn test_boundary_coherence_equals_threshold_emits() {
        let emitter = SignalEmitter::new();
        let signal = emitter.emit(
            BEOId::zero(),
            &planes_all(0.55),
            &PlaneWeights::DEFAULT_BALANCED,
            0.0, // Θ(0) = 0.55 == C
            0.0,
            1.0,
            0,
        );
        assert_eq!(signal.coherence, 0.55);
        assert_eq!(signal.threshold, 0.55);
        assert_eq!(signal.signal_type, SignalType::Valuation);
    }

    /// NaN planes → SILENCE (comparison false — no valuation from an
    /// undefined coherence).
    #[test]
    fn test_nan_planes_emit_silence() {
        let emitter = SignalEmitter::new();
        let nan_planes = FivePlanes {
            phi_adj: f64::NAN,
            m_adj: 0.9,
            sigma: 0.9,
            k_plane: 0.9,
            anima: 0.9,
        };
        let signal = emitter.emit(
            BEOId::zero(),
            &nan_planes,
            &PlaneWeights::DEFAULT_BALANCED,
            0.0,
            0.0,
            1.0,
            0,
        );
        assert_eq!(signal.signal_type, SignalType::Silence);
    }

    /// Caller-supplied S(t) is used verbatim in T(t) (zero moat → T = S).
    #[test]
    fn test_emit_with_value_uses_signal_value() {
        let emitter = SignalEmitter::new();
        let signal = emitter.emit_with_value(
            BEOId::zero(),
            &planes_all(0.9),
            &PlaneWeights::DEFAULT_BALANCED,
            0.0,
            0.5, // S = 0.5
            0.0, // moat 0 → T = S · e^0 = 0.5
            1.0,
            7,
        );
        assert_eq!(signal.signal_type, SignalType::Valuation);
        assert!((signal.decode_payload_f64().unwrap() - 0.5).abs() < 1e-12);
    }

    /// All 24 registry ids round-trip id → from_id → id, matching the
    /// Python IntEnum and the wasm `$ST_*` globals.
    #[test]
    fn test_all_24_ids_round_trip() {
        assert_eq!(ALL_SIGNAL_TYPES.len(), SIGNAL_TYPE_COUNT);
        for (i, signal_type) in ALL_SIGNAL_TYPES.iter().enumerate() {
            assert_eq!(signal_type.id() as usize, i, "registry order == id");
            let back = SignalType::from_id(i as u8)
                .unwrap_or_else(|| panic!("id {} must resolve", i));
            assert_eq!(back, *signal_type);
            assert_eq!(back.id() as usize, i);
        }
        // Out-of-registry ids are rejected (wasm rejects type_id > 23).
        assert_eq!(SignalType::from_id(24), None);
        assert_eq!(SignalType::from_id(255), None);
    }

    /// Registry names match the canonical Python member names.
    #[test]
    fn test_names_match_python_registry() {
        let expected = [
            "VALUATION",
            "SILENCE",
            "MANIPULATION_ALERT",
            "GENESIS",
            "RESURRECTION",
            "FORK_DIVERGENCE",
            "TRAJECTORY",
            "NEGATIVE_SPACE",
            "PHASE_TRANSITION",
            "SYSTEMIC_RISK",
            "LIQUIDITY_HEALTH",
            "GOVERNANCE_SIGNAL",
            "CROSS_CHAIN_COHERENCE",
            "STABLECOIN_HEALTH",
            "MEV_EXPOSURE",
            "INSTITUTIONAL_BHV",
            "REGULATORY_BHV",
            "ECOSYSTEM_HEALTH",
            "BOOTSTRAP",
            "SOVEREIGN_BEHAVIORAL",
            "ENERGY_PARTICIPATION",
            "BIOLOGICAL_CAPITAL",
            "BTCP_ROUTE",
            "CONSENSUS_ADAPTATION",
        ];
        for (signal_type, name) in ALL_SIGNAL_TYPES.iter().zip(expected.iter()) {
            assert_eq!(signal_type.name(), *name);
        }
    }

    /// Non-gated typed emission (e.g. BTCP_ROUTE on finalization).
    #[test]
    fn test_emit_typed_constructs_without_gate() {
        let emitter = SignalEmitter::new();
        let signal = emitter.emit_typed(
            SignalType::BtcpRoute,
            BEOId::zero(),
            0.9,
            0.55,
            123,
            Some(vec![1, 2, 3]),
        );
        assert_eq!(signal.signal_type, SignalType::BtcpRoute);
        assert_eq!(signal.signal_type.id(), 22);
        assert_eq!(signal.emitted_at, 123);
        assert_eq!(signal.payload, Some(vec![1, 2, 3]));
        assert_eq!(signal.decode_payload_f64(), None); // not an 8-byte gate payload
    }

    /// Payload decode rejects short/absent payloads.
    #[test]
    fn test_payload_decode_rejects_non_f64_payloads() {
        let mut signal = Signal {
            signal_type: SignalType::Silence,
            entity_id: BEOId::zero(),
            coherence: 0.0,
            threshold: 0.55,
            emitted_at: 0,
            payload: None,
        };
        assert_eq!(signal.decode_payload_f64(), None);
        signal.payload = Some(vec![0u8; 4]);
        assert_eq!(signal.decode_payload_f64(), None);
    }

    /// Big-endian payload encoding round-trips an exact f64 bit pattern.
    #[test]
    fn test_payload_be_encoding_round_trip() {
        let value: f64 = 0.661;
        let signal = Signal {
            signal_type: SignalType::Valuation,
            entity_id: BEOId::zero(),
            coherence: 0.661,
            threshold: 0.55,
            emitted_at: 0,
            payload: Some(value.to_be_bytes().to_vec()),
        };
        assert_eq!(signal.decode_payload_f64(), Some(value));
    }
}
