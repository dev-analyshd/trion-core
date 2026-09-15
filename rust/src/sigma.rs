//! sigma.rs — L4.1 Spiritual Plane Σ(t) (standalone Rust module)
//!
//! TRION specification §L4.1 — diversity-weighted BFT validator consensus:
//!
//! ```text
//! Σ(t) = Σ_j [ s_j · d_j · 1(|v_j − v̄| ≤ δ(t)) ] / Σ_j [ s_j · d_j ]
//! d_j  = 1 − corr(M_j, M̄)              (diversity weight)
//! δ(t) = δ_base · (1 + V(t))           (dynamic consensus window)
//! ```
//!
//! `v̄` is the network-wide median valuation; `M_j` is validator `j`'s
//! recent model-output stream; `M̄` is the median model-output stream.
//!
//! This is a port of the canonical Python reference
//! (`core/spiritual/sigma_engine.py`) and the Go consensus implementation
//! (`validator/internal/p2p/consensus.go::ComputeSigma`), so the PyO3
//! binding layer (`rust/src/pyo3_bindings.rs::compute_sigma`) can share
//! the exact same diversity-weighted BFT math.
//!
//! HONEST DISCLOSURE: Σ at bootstrap (no validators registered yet) is
//! the spec's 0.25 baseline — the full diversity-weighted BFT validator
//! network activates at mainnet. The bootstrap constant matches both
//! `core/spiritual/sigma_engine.py::SIGMA_BOOTSTRAP` and the
//! `DiversityWeightedResult{ Sigma: 0.25, Bootstrap: true }` Go default.

/// Bootstrap baseline returned by `compute_sigma` when the validator set
/// is empty (whitepaper §L4.1 honest disclosure — mainnet activation).
pub const SIGMA_BOOTSTRAP: f64 = 0.25;

/// Default dynamic-consensus-window base — `δ_base` in the spec. Mirrors
/// the `delta_base=0.10` default in `core/spiritual/sigma_engine.py`
/// and `validator/internal/p2p/consensus.go`.
pub const DEFAULT_DELTA_BASE: f64 = 0.10;

/// Default volatility V(t) used when none is supplied — matches the
/// `volatility=0.3` default in `core/spiritual/sigma_engine.py`.
pub const DEFAULT_VOLATILITY: f64 = 0.30;

/// Compute the canonical spec diversity weight `d_j = 1 − corr(M_j, M̄)`.
///
/// When Byzantine validators coordinate, their model-output streams
/// correlate with the median, so `corr → 1` and `d_j → 0` — effective
/// stake collapses and honesty is the Nash equilibrium (whitepaper §L4.1).
///
/// Inputs
/// ------
/// `messages_j`     : validator `j`'s recent model-output stream.
/// `median_messages`: the network-wide median stream `M̄`.
///
/// Returns
/// -------
/// A diversity weight in `[0, 1]`. Degenerate inputs (length < 2, zero
/// variance, or NaN correlation) return `1.0` — the same fallback as
/// `compute_diversity_weight` in `core/spiritual/sigma_engine.py` and
/// `ComputeDiversityWeight` in `validator/internal/p2p/consensus.go`.
pub fn compute_diversity_weight(messages_j: &[f64], median_messages: &[f64]) -> f64 {
    if messages_j.len() < 2 || median_messages.len() < 2 {
        return 1.0;
    }
    // Trim both to the trailing min-length slice — matches the Python
    // `mj = model_outputs_j[-min_len:]` / `mbar = median_outputs[-min_len:]`.
    let n = messages_j.len().min(median_messages.len());
    let mj = &messages_j[messages_j.len() - n..];
    let mbar = &median_messages[median_messages.len() - n..];

    let mut mean_j = 0.0;
    let mut mean_b = 0.0;
    for i in 0..n {
        mean_j += mj[i];
        mean_b += mbar[i];
    }
    mean_j /= n as f64;
    mean_b /= n as f64;

    let mut cov = 0.0;
    let mut var_j = 0.0;
    let mut var_b = 0.0;
    for i in 0..n {
        let dj = mj[i] - mean_j;
        let db = mbar[i] - mean_b;
        cov += dj * db;
        var_j += dj * dj;
        var_b += db * db;
    }
    if var_j <= 0.0 || var_b <= 0.0 {
        return 1.0;
    }
    let denom = (var_j * var_b).sqrt();
    if denom == 0.0 {
        return 1.0;
    }
    let corr = cov / denom;
    if corr.is_nan() {
        return 1.0;
    }
    let d = 1.0 - corr;
    if d < 0.0 {
        0.0
    } else if d > 1.0 {
        1.0
    } else {
        d
    }
}

/// Compute Σ(t) — the diversity-weighted BFT consensus score.
///
/// Inputs (all per-validator, same length, indexed by validator `j`)
/// -----------------------------------------------------------------
/// `stakes`     : `s_j` — raw validator stake.
/// `diversity`  : `d_j` — precomputed diversity weight (call
///                 `compute_diversity_weight` once per validator).
/// `valuations` : `v_j` — validator's current behavioural valuation.
/// `median`     : `v̄` — network-wide median valuation.
/// `delta_base` : `δ_base` — base consensus window.
/// `volatility` : `V(t)` — current volatility V(t) (clamped to [0, 1]).
///
/// Returns
/// -------
/// Σ(t) in `[0, 1]`. Returns `SIGMA_BOOTSTRAP` (0.25) when the validator
/// set is empty — the spec's honest bootstrap disclosure. Returns `0.0`
/// when total effective stake collapses to zero.
pub fn compute_sigma(
    stakes: &[f64],
    diversity: &[f64],
    valuations: &[f64],
    median: f64,
    delta_base: f64,
    volatility: f64,
) -> f64 {
    // Bootstrap disclosure: empty validator set → 0.25 (spec §L4.1).
    if stakes.is_empty() || diversity.is_empty() || valuations.is_empty() {
        return SIGMA_BOOTSTRAP;
    }
    let n = stakes.len().min(diversity.len()).min(valuations.len());
    if n == 0 {
        return SIGMA_BOOTSTRAP;
    }

    let v = volatility.clamp(0.0, 1.0);
    let delta_t = delta_base * (1.0 + v);

    let mut numerator: f64 = 0.0;
    let mut denominator: f64 = 0.0;
    for i in 0..n {
        let w = stakes[i] * diversity[i];
        denominator += w;
        if (valuations[i] - median).abs() <= delta_t {
            numerator += w;
        }
    }
    if denominator <= 0.0 {
        return 0.0;
    }
    (numerator / denominator).clamp(0.0, 1.0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_diversity_weight_fallback_on_short_inputs() {
        assert_eq!(compute_diversity_weight(&[], &[]), 1.0);
        assert_eq!(compute_diversity_weight(&[1.0], &[1.0]), 1.0);
    }

    #[test]
    fn test_diversity_weight_uncorrelated_streams_near_one() {
        // Maximally anti-correlated streams → corr = -1 → d_j = 2 → clamped to 1.0.
        let a = [0.0, 1.0, 2.0, 3.0];
        let b = [3.0, 2.0, 1.0, 0.0];
        assert!((compute_diversity_weight(&a, &b) - 1.0).abs() < 1e-9);
    }

    #[test]
    fn test_diversity_weight_identical_streams_zero() {
        // Identical streams → corr = 1 → d_j = 0.
        let a = [0.1, 0.4, 0.5, 0.9];
        assert!((compute_diversity_weight(&a, &a)).abs() < 1e-9);
    }

    #[test]
    fn test_diversity_weight_zero_variance_returns_one() {
        let constant = [0.5; 4];
        let varying = [0.1, 0.2, 0.3, 0.4];
        assert_eq!(compute_diversity_weight(&constant, &varying), 1.0);
        assert_eq!(compute_diversity_weight(&varying, &constant), 1.0);
    }

    #[test]
    fn test_sigma_bootstrap_when_empty_validator_set() {
        assert_eq!(
            compute_sigma(&[], &[], &[], 0.5, DEFAULT_DELTA_BASE, DEFAULT_VOLATILITY),
            SIGMA_BOOTSTRAP
        );
    }

    #[test]
    fn test_sigma_zero_when_total_effective_stake_collapses() {
        // All validators have zero stake → denominator 0 → sigma = 0.
        let s = vec![0.0, 0.0, 0.0];
        let d = vec![1.0, 1.0, 1.0];
        let v = vec![0.5, 0.5, 0.5];
        assert_eq!(compute_sigma(&s, &d, &v, 0.5, DEFAULT_DELTA_BASE, DEFAULT_VOLATILITY), 0.0);
    }

    #[test]
    fn test_sigma_honest_validators_agree_near_one() {
        // Five honest validators with identical valuations (all in the
        // consensus window) → Σ ≈ 1.0.
        let s = vec![1000.0; 5];
        let d = vec![1.0; 5];
        let v = vec![0.72; 5];
        let sigma = compute_sigma(&s, &d, &v, 0.72, DEFAULT_DELTA_BASE, DEFAULT_VOLATILITY);
        assert!((sigma - 1.0).abs() < 1e-9, "sigma = {sigma}");
    }

    #[test]
    fn test_sigma_byzantine_self_defeat() {
        // Byzantine validators with d_j = 0 (corr = 1) contribute nothing
        // — only the honest validators count toward the numerator.
        let stakes = vec![1000.0; 10];
        let diversity = vec![0.0; 5].into_iter().chain(vec![1.0; 5]).collect::<Vec<_>>();
        let valuations = vec![0.50; 5].into_iter().chain(vec![0.72; 5]).collect::<Vec<_>>();
        let sigma = compute_sigma(&stakes, &diversity, &valuations, 0.72, DEFAULT_DELTA_BASE, DEFAULT_VOLATILITY);
        // Numerator: 5 honest × 1000 × 1.0 (all in window) = 5000.
        // Denominator: 5 byzantine × 0 (d=0) + 5 honest × 1000 = 5000.
        // Σ = 1.0 — byzantine stake collapses to zero effective weight.
        assert!((sigma - 1.0).abs() < 1e-9, "sigma = {sigma}");
    }

    #[test]
    fn test_sigma_dynamic_window_widens_with_volatility() {
        // Same valuations, but volatility high enough to widen δ(t) and
        // pull an outlier back into the consensus window.
        let stakes = vec![100.0, 100.0];
        let diversity = vec![1.0, 1.0];
        let valuations = vec![0.50, 0.65];
        // δ(t) = 0.10 × (1 + 0.5) = 0.15 → |0.65 − 0.575| = 0.075 ≤ 0.15 → both in.
        let sigma_in =
            compute_sigma(&stakes, &diversity, &valuations, 0.575, DEFAULT_DELTA_BASE, 0.5);
        assert!((sigma_in - 1.0).abs() < 1e-9);

        // δ(t) = 0.10 × (1 + 0.0) = 0.10 → |0.65 − 0.575| = 0.075 ≤ 0.10 → both in.
        let sigma_in2 =
            compute_sigma(&stakes, &diversity, &valuations, 0.575, DEFAULT_DELTA_BASE, 0.0);
        assert!((sigma_in2 - 1.0).abs() < 1e-9);

        // Push the outlier further out so it falls outside the narrow window.
        let valuations_out = vec![0.50, 0.95];
        // median = 0.725, δ(t) = 0.10, |0.95 − 0.725| = 0.225 > 0.10 → excluded.
        let sigma_out =
            compute_sigma(&stakes, &diversity, &valuations_out, 0.725, DEFAULT_DELTA_BASE, 0.0);
        assert!((sigma_out - 0.5).abs() < 1e-9, "sigma = {sigma_out}");
    }
}
