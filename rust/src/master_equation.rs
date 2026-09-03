//! master_equation.rs — L5 Five-Plane Coherence C(t) and the Master Equation
//! TRION Whitepaper §3 (Master Equation, lines 129–161) — Rust port of the
//! canonical Python reference `core/master/coherence.py` (C(t), Θ(t), weight
//! profiles) and `core/master/master_equation.py` (T(t), moat exponent clamp).
//!
//! Whitepaper §3:
//!   C(t)  = α·Φ_adj(t) + β·M_adj(t) + γ·Σ(t) + δ·K(t) + ε·A(t)
//!   Θ(t)  = Θ_min + (Θ_max − Θ_min)·V(t),  Θ_min = 0.55, Θ_max = 0.92
//!   T(t)  = [C(t) ≥ Θ(t)] · S(t) · e^(M_moat · t)
//!     [C≥Θ] = 1 → signal emits; [C≥Θ] = 0 → SILENCE emits
//!
//! Cross-language parity:
//!   - Θ(t) matches `compute_threshold` in the wasm module
//!     (`sdk/src/wasm/signal_processor.wat`: THETA_MIN 0.55, THETA_MAX 0.92,
//!     clamp V to [0,1]) — golden points threshold(0)=0.55,
//!     threshold(1)=0.92, coherence(1,1,1,1,1)=1.
//!   - Weight profiles mirror `WEIGHT_PROFILES` in `core/master/coherence.py`
//!     exactly (7 asset profiles; the 4 query-mode profiles SPEED /
//!     INTELLIGENCE / CERTAINTY / FULL_SPECTRUM are NOT ported here — the
//!     7 asset profiles are the ones required by the whitepaper L5.2 table).
//!   - T(t) mirrors `MasterEquation.compute` in
//!     `core/master/master_equation.py`: moat exponent clamped at
//!     MAX_MOAT_EXPONENT = 36.0 (e^36 ≈ 4.3e15 — decades of compounding
//!     without overflow), negative time clamped to 0, and silence = no
//!     output at all (represented as `None`).

/// Θ_min — minimum dynamic threshold (whitepaper §3, coherence.py, wasm).
pub const THETA_MIN: f64 = 0.55;

/// Θ_max — maximum dynamic threshold (whitepaper §3, coherence.py, wasm).
pub const THETA_MAX: f64 = 0.92;

/// Numerical-stability clamp for the moat exponent (master_equation.py):
/// e^36 ≈ 4.3e15 — large enough to express decades of compounding, small
/// enough to avoid overflow.
pub const MAX_MOAT_EXPONENT: f64 = 36.0;

/// Five plane scores at time t — the inputs of C(t).
///
/// Field names mirror `CoherenceInput` / the `plane_breakdown` dict in
/// `core/master/coherence.py` (and `trion.ts`): Φ_adj (physical, after
/// manipulation correction), M_adj (mental, after observer-effect
/// correction), Σ (spiritual — diversity-weighted validator consensus),
/// K (conscious — human annotation network), A (anima — offchain
/// intelligence).
#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct FivePlanes {
    /// Φ_adj — physical behavioral entropy × (1 − manipulation_score)
    pub phi_adj: f64,
    /// M_adj — AI model confidence × (1 − observer_effect_factor)
    pub m_adj: f64,
    /// Σ — diversity-weighted validator consensus (spiritual plane)
    pub sigma: f64,
    /// K — human annotation network (conscious plane)
    pub k_plane: f64,
    /// A — ANIMA offchain intelligence score
    pub anima: f64,
}

impl FivePlanes {
    /// All planes at 1.0 — the wasm/Python parity golden input
    /// (coherence(1,1,1,1,1) = 1 with any normalized weights).
    pub const PERFECT: FivePlanes = FivePlanes {
        phi_adj: 1.0,
        m_adj: 1.0,
        sigma: 1.0,
        k_plane: 1.0,
        anima: 1.0,
    };
}

/// Plane weights (α, β, γ, δ, ε) for the C(t) linear combination.
///
/// All canonical profiles sum to 1.0; `is_normalized()` mirrors the
/// ValueError guard in `core/master/coherence.py` (tolerance 1e-9).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct PlaneWeights {
    /// α — weight of the physical plane Φ_adj
    pub alpha: f64,
    /// β — weight of the mental plane M_adj
    pub beta: f64,
    /// γ — weight of the spiritual plane Σ
    pub gamma: f64,
    /// δ — weight of the conscious plane K
    pub delta: f64,
    /// ε — weight of the anima plane A
    pub epsilon: f64,
}

impl PlaneWeights {
    /// DEFAULT_BALANCED (Python registry name: `DEFAULT`) —
    /// α=0.25, β=0.30, γ=0.25, δ=0.10, ε=0.10
    pub const DEFAULT_BALANCED: PlaneWeights = PlaneWeights {
        alpha: 0.25,
        beta: 0.30,
        gamma: 0.25,
        delta: 0.10,
        epsilon: 0.10,
    };

    /// NEW_TOKEN (<90 days) — α=0.40, β=0.15, γ=0.30, δ=0.10, ε=0.05
    pub const NEW_TOKEN: PlaneWeights = PlaneWeights {
        alpha: 0.40,
        beta: 0.15,
        gamma: 0.30,
        delta: 0.10,
        epsilon: 0.05,
    };

    /// MATURE_PROTOCOL (Python registry name: `MATURE`) —
    /// α=0.20, β=0.30, γ=0.20, δ=0.15, ε=0.15
    pub const MATURE_PROTOCOL: PlaneWeights = PlaneWeights {
        alpha: 0.20,
        beta: 0.30,
        gamma: 0.20,
        delta: 0.15,
        epsilon: 0.15,
    };

    /// STABLECOIN — α=0.25, β=0.35, γ=0.25, δ=0.05, ε=0.10
    pub const STABLECOIN: PlaneWeights = PlaneWeights {
        alpha: 0.25,
        beta: 0.35,
        gamma: 0.25,
        delta: 0.05,
        epsilon: 0.10,
    };

    /// GOVERNANCE_TOKEN (Python registry name: `GOVERNANCE`) —
    /// α=0.15, β=0.20, γ=0.25, δ=0.25, ε=0.15
    pub const GOVERNANCE_TOKEN: PlaneWeights = PlaneWeights {
        alpha: 0.15,
        beta: 0.20,
        gamma: 0.25,
        delta: 0.25,
        epsilon: 0.15,
    };

    /// BRIDGE_ASSET (Python registry name: `BRIDGE`) —
    /// α=0.30, β=0.25, γ=0.30, δ=0.05, ε=0.10
    pub const BRIDGE_ASSET: PlaneWeights = PlaneWeights {
        alpha: 0.30,
        beta: 0.25,
        gamma: 0.30,
        delta: 0.05,
        epsilon: 0.10,
    };

    /// WRAPPED_ASSET (Python registry name: `WRAPPED`) —
    /// α=0.20, β=0.25, γ=0.35, δ=0.05, ε=0.15
    pub const WRAPPED_ASSET: PlaneWeights = PlaneWeights {
        alpha: 0.20,
        beta: 0.25,
        gamma: 0.35,
        delta: 0.05,
        epsilon: 0.15,
    };

    /// Sum of the five weights — canonical profiles must sum to 1.0.
    pub fn sum(&self) -> f64 {
        self.alpha + self.beta + self.gamma + self.delta + self.epsilon
    }

    /// True when the weights sum to 1.0 within 1e-9 — mirrors the
    /// `ValueError` guard in `core/master/coherence.py::compute_coherence`.
    pub fn is_normalized(&self) -> bool {
        (self.sum() - 1.0).abs() < 1e-9
    }
}

/// Asset-type calibration profile selecting a weight set
/// (whitepaper L5.2 table — mirrors `AssetProfile` in
/// `core/master/coherence.py`, asset-type entries only).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AssetProfile {
    /// Default balanced profile
    Default,
    /// New token (<90 days)
    NewToken,
    /// Mature protocol
    Mature,
    /// Stablecoin
    Stablecoin,
    /// Governance token
    Governance,
    /// Bridge asset
    Bridge,
    /// Wrapped asset
    Wrapped,
}

impl AssetProfile {
    /// The canonical weight set for this profile.
    pub fn weights(&self) -> PlaneWeights {
        match self {
            AssetProfile::Default => PlaneWeights::DEFAULT_BALANCED,
            AssetProfile::NewToken => PlaneWeights::NEW_TOKEN,
            AssetProfile::Mature => PlaneWeights::MATURE_PROTOCOL,
            AssetProfile::Stablecoin => PlaneWeights::STABLECOIN,
            AssetProfile::Governance => PlaneWeights::GOVERNANCE_TOKEN,
            AssetProfile::Bridge => PlaneWeights::BRIDGE_ASSET,
            AssetProfile::Wrapped => PlaneWeights::WRAPPED_ASSET,
        }
    }

    /// Registry name, identical to the Python `AssetProfile` string values
    /// ("DEFAULT", "NEW_TOKEN", "MATURE_PROTOCOL", "STABLECOIN",
    /// "GOVERNANCE_TOKEN", "BRIDGE_ASSET", "WRAPPED_ASSET").
    pub fn name(&self) -> &'static str {
        match self {
            AssetProfile::Default => "DEFAULT",
            AssetProfile::NewToken => "NEW_TOKEN",
            AssetProfile::Mature => "MATURE_PROTOCOL",
            AssetProfile::Stablecoin => "STABLECOIN",
            AssetProfile::Governance => "GOVERNANCE_TOKEN",
            AssetProfile::Bridge => "BRIDGE_ASSET",
            AssetProfile::Wrapped => "WRAPPED_ASSET",
        }
    }
}

/// C(t) = α·Φ_adj + β·M_adj + γ·Σ + δ·K + ε·A, clamped to [0, 1].
///
/// Mirrors `CoherenceEngine.compute_coherence` in
/// `core/master/coherence.py` (weighted linear sum then
/// `max(0.0, min(1.0, C))`).
pub fn coherence(planes: &FivePlanes, w: &PlaneWeights) -> f64 {
    let c = w.alpha * planes.phi_adj
        + w.beta * planes.m_adj
        + w.gamma * planes.sigma
        + w.delta * planes.k_plane
        + w.epsilon * planes.anima;
    c.clamp(0.0, 1.0)
}

/// Θ(t) = Θ_min + (Θ_max − Θ_min)·clamp(V(t), 0, 1)
///      = 0.55 + 0.37·clamp(V, 0, 1)
///
/// Byte-identical to `compute_threshold` in the wasm module
/// (`sdk/src/wasm/signal_processor.wat`) and to
/// `CoherenceEngine.compute_threshold` in `core/master/coherence.py`.
pub fn threshold(volatility: f64) -> f64 {
    THETA_MIN + (THETA_MAX - THETA_MIN) * volatility.clamp(0.0, 1.0)
}

/// The Heaviside gate [C(t) ≥ Θ(t)]: `true` → signal emits, `false` →
/// SILENCE. Boundary is inclusive (C == Θ emits), per whitepaper §3
/// "[C(t) >= Θ(t)] = 1 → signal emits" and `emits = C >= theta` in
/// `core/master/coherence.py`.
pub fn emits(c: f64, theta: f64) -> bool {
    c >= theta
}

/// The Master Equation: T(t) = [C(t) ≥ Θ(t)] · S(t) · e^(M_moat · t).
///
/// Returns `None` when the gate is closed — that is the SILENCE branch:
/// T(t) = 0 and, per the "silence is information" invariant, no valuation
/// output is produced at all. Returns `Some(T)` when C ≥ Θ, with the moat
/// exponent clamped exactly like `MasterEquation.compute` in
/// `core/master/master_equation.py`:
///   moat_exp = min(M_moat · max(0, t), MAX_MOAT_EXPONENT)
///   T        = S(t) · e^moat_exp
///
/// `s` is the signal value S(t); callers without a separate signal value
/// should pass C(t) (the Python reference falls back to C — "coherence IS
/// the truth measure").
pub fn master_equation(c: f64, theta: f64, s: f64, moat: f64, t: f64) -> Option<f64> {
    if !emits(c, theta) {
        // [C ≥ Θ] = 0 → SILENCE: T(t) = 0, no valuation output.
        return None;
    }
    let moat_exp = (moat * t.max(0.0)).min(MAX_MOAT_EXPONENT);
    Some(s * moat_exp.exp())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Wasm / Python parity golden points (see module docs):
    /// coherence(1,1,1,1,1) = 1, threshold(0) = 0.55, threshold(1) = 0.92.
    #[test]
    fn test_wasm_parity_golden_points() {
        assert_eq!(coherence(&FivePlanes::PERFECT, &PlaneWeights::DEFAULT_BALANCED), 1.0);
        assert_eq!(threshold(0.0), 0.55);
        assert_eq!(threshold(1.0), 0.92);
    }

    /// Θ(t) clamps V outside [0,1] (wasm `compute_threshold` does the same).
    #[test]
    fn test_threshold_clamps_volatility() {
        assert_eq!(threshold(-1.0), 0.55);
        assert_eq!(threshold(2.5), 0.92);
        assert!((threshold(0.5) - 0.735).abs() < 1e-9);
    }

    /// Mirrors the "Normal" case in `core/master/coherence.py __main__`:
    /// planes (0.72, 0.68, 0.25, 0.10, 0.10), MATURE profile, V = 0.30 →
    /// C = 0.428, Θ = 0.661 → SILENCE.
    #[test]
    fn test_python_normal_case() {
        let planes = FivePlanes {
            phi_adj: 0.72,
            m_adj: 0.68,
            sigma: 0.25,
            k_plane: 0.10,
            anima: 0.10,
        };
        let c = coherence(&planes, &PlaneWeights::MATURE_PROTOCOL);
        assert!((c - 0.428).abs() < 1e-9);
        let theta = threshold(0.30);
        assert!((theta - 0.661).abs() < 1e-9);
        assert!(!emits(c, theta));
        assert!(master_equation(c, theta, c, 1.0, 1.0).is_none());
    }

    /// Mirrors the "Attack" case in `core/master/coherence.py __main__`
    /// (which asserts silence): planes (0.05, 0.40, 0.25, 0.10, 0.10),
    /// MATURE profile, V = 0.80 → C = 0.21, Θ = 0.846 → SILENCE.
    #[test]
    fn test_python_attack_case_is_silence() {
        let planes = FivePlanes {
            phi_adj: 0.05,
            m_adj: 0.40,
            sigma: 0.25,
            k_plane: 0.10,
            anima: 0.10,
        };
        let c = coherence(&planes, &PlaneWeights::MATURE_PROTOCOL);
        assert!((c - 0.21).abs() < 1e-9);
        assert!(!emits(c, threshold(0.80)));
        assert!(master_equation(c, threshold(0.80), c, 1.0, 1.0).is_none());
    }

    /// C(t) clamps to [0, 1] after the weighted sum (Python parity).
    #[test]
    fn test_coherence_clamps_to_unit_interval() {
        let neg = FivePlanes {
            phi_adj: -0.5,
            m_adj: -0.5,
            sigma: -0.5,
            k_plane: -0.5,
            anima: -0.5,
        };
        assert_eq!(coherence(&neg, &PlaneWeights::DEFAULT_BALANCED), 0.0);

        let big = FivePlanes {
            phi_adj: 2.0,
            m_adj: 2.0,
            sigma: 2.0,
            k_plane: 2.0,
            anima: 2.0,
        };
        assert_eq!(coherence(&big, &PlaneWeights::DEFAULT_BALANCED), 1.0);
    }

    /// Weight-profile parity with `WEIGHT_PROFILES` in
    /// `core/master/coherence.py` — exact values, all summing to 1.0
    /// (the Python side raises ValueError otherwise).
    #[test]
    fn test_profiles_match_python_registry() {
        let cases: [(PlaneWeights, [f64; 5]); 7] = [
            (PlaneWeights::DEFAULT_BALANCED, [0.25, 0.30, 0.25, 0.10, 0.10]),
            (PlaneWeights::NEW_TOKEN, [0.40, 0.15, 0.30, 0.10, 0.05]),
            (PlaneWeights::MATURE_PROTOCOL, [0.20, 0.30, 0.20, 0.15, 0.15]),
            (PlaneWeights::STABLECOIN, [0.25, 0.35, 0.25, 0.05, 0.10]),
            (PlaneWeights::GOVERNANCE_TOKEN, [0.15, 0.20, 0.25, 0.25, 0.15]),
            (PlaneWeights::BRIDGE_ASSET, [0.30, 0.25, 0.30, 0.05, 0.10]),
            (PlaneWeights::WRAPPED_ASSET, [0.20, 0.25, 0.35, 0.05, 0.15]),
        ];
        for (w, expected) in cases {
            let got = [w.alpha, w.beta, w.gamma, w.delta, w.epsilon];
            assert_eq!(got, expected);
            assert!(w.is_normalized(), "profile weights must sum to 1.0");
        }
    }

    /// `AssetProfile::weights()` / `name()` cover all 7 registry entries.
    #[test]
    fn test_asset_profile_registry() {
        let all = [
            (AssetProfile::Default, PlaneWeights::DEFAULT_BALANCED, "DEFAULT"),
            (AssetProfile::NewToken, PlaneWeights::NEW_TOKEN, "NEW_TOKEN"),
            (AssetProfile::Mature, PlaneWeights::MATURE_PROTOCOL, "MATURE_PROTOCOL"),
            (AssetProfile::Stablecoin, PlaneWeights::STABLECOIN, "STABLECOIN"),
            (AssetProfile::Governance, PlaneWeights::GOVERNANCE_TOKEN, "GOVERNANCE_TOKEN"),
            (AssetProfile::Bridge, PlaneWeights::BRIDGE_ASSET, "BRIDGE_ASSET"),
            (AssetProfile::Wrapped, PlaneWeights::WRAPPED_ASSET, "WRAPPED_ASSET"),
        ];
        for (profile, weights, name) in all {
            assert_eq!(profile.weights(), weights);
            assert_eq!(profile.name(), name);
            assert!(profile.weights().is_normalized());
        }
    }

    /// Silence branch: C < Θ → None (T(t) = 0 — no valuation output).
    #[test]
    fn test_master_equation_silence_is_none() {
        assert!(master_equation(0.40, 0.90, 0.40, 1.0, 1.0).is_none());
        assert!(master_equation(0.0, 0.55, 0.0, 1.0, 10.0).is_none());
    }

    /// Emit branch with zero moat: T = S·e^0 = S.
    #[test]
    fn test_master_equation_zero_moat_returns_signal_value() {
        let t = master_equation(0.90, 0.55, 0.90, 0.0, 5.0);
        assert!(t.is_some());
        assert!((t.unwrap() - 0.90).abs() < 1e-12);
    }

    /// Moat compounding: T = S·e^(M·t) — golden value e^2 = 7.38905609893065
    /// (matches `math.exp(2.0)` in Python).
    #[test]
    fn test_master_equation_moat_compounds() {
        let t = master_equation(1.0, 0.55, 1.0, 1.0, 2.0);
        assert!((t.unwrap() - 7.38905609893065).abs() < 1e-9);
    }

    /// Exponent clamp mirrors MAX_MOAT_EXPONENT: huge t caps the exponent
    /// at 36 → T = S·e^36 = 4311231547115195.0 (Python `math.exp(36)`).
    #[test]
    fn test_master_equation_exponent_clamp() {
        let t = master_equation(1.0, 0.55, 1.0, 1.0, 1000.0);
        assert!((t.unwrap() - 4311231547115195.0).abs() < 1e6);

        // moat > 1 also saturates the same clamp
        let t2 = master_equation(1.0, 0.55, 1.0, 100.0, 100.0);
        assert!((t2.unwrap() - 4311231547115195.0).abs() < 1e6);
    }

    /// Negative time clamps to 0 (Python: `max(0.0, time_years)`) → e^0 → T = S.
    #[test]
    fn test_master_equation_negative_time_clamps_to_zero() {
        let t = master_equation(0.90, 0.55, 0.75, 1.0, -50.0);
        assert!((t.unwrap() - 0.75).abs() < 1e-12);
    }

    /// Inclusive boundary: C == Θ emits (whitepaper "[C >= Θ] = 1").
    /// Construction chosen for exact f64 equality (verified against
    /// Python): all planes 0.55 → C == 0.55 exactly; Θ(0) == 0.55 exactly.
    #[test]
    fn test_emits_boundary_is_inclusive() {
        assert!(emits(0.92, 0.92));
        assert!(!emits(0.9199999, 0.92));
        let planes = FivePlanes {
            phi_adj: 0.55,
            m_adj: 0.55,
            sigma: 0.55,
            k_plane: 0.55,
            anima: 0.55,
        };
        let c = coherence(&planes, &PlaneWeights::DEFAULT_BALANCED);
        assert_eq!(c, 0.55);
        assert!(emits(c, threshold(0.0)));
    }
}
