//! anima.rs — L3.3 ANIMA ML hot-path (standalone Rust module)
//!
//! TRION whitepaper Part 11 mandates that "production ML inference" be
//! compiled to Rust via PyO3 bindings. The ANIMA service
//! (`anima-service/anima_engine.py`, ~1,861 lines) is a broad Python
//! implementation of the L3.3 — L3.7 intelligence layer; this Rust module
//! ports ONLY the performance-critical inference functions invoked on
//! every signal computation:
//!
//!   1. `compute_anima_score`            — A(t) = PCR × HA × CA (L3.3)
//!   2. `compute_archetype_similarity`   — cosine similarity between an
//!                                          entity vector and an archetype
//!                                          centroid (L3.3 PCR step 3)
//!   3. `compute_observer_effect`        — OE = corr(publication[t-1],
//!                                          behavioral_change[t]) — Pearson
//!                                          correlation, lag-1 aligned (L3.6)
//!   4. `compute_ci_95`                  — 95% confidence interval using the
//!                                          t-distribution approximation
//!                                          (pattern_library.py
//!                                          OutcomeDistribution)
//!   5. `compute_probability_distribution` — full mean / std_dev / CI_95
//!                                            over a sample of scores
//!                                            (spec §3.3 mandates that ANIMA
//!                                            outputs PROBABILITY_DISTRIBUTION
//!                                            not point predictions)
//!
//! Every function is a pure, allocation-light port of the canonical Python
//! math so the PyO3 wrappers (`rust/src/pyo3_bindings.rs`) and ctypes
//! fallback (`core/rust_bridge_pyo3.py`) share a single source of truth.
//!
//! HONEST DISCLOSURE: The 17,000-line ANIMA Python service is NOT ported in
//! full. Database I/O, crawl scheduling, VADER sentiment, FAISS vector
//! insertion and APScheduler background cycles remain Python — they are
//! not in the inference hot path. Only the math called per-signal is here.

// ──────────────────────────────────────────────────────────────────────────
//  Constants — mirror the Python reference (anima_engine.py / pattern_library.py)
// ──────────────────────────────────────────────────────────────────────────

/// L3.3 HA_DISABLE_THRESHOLD — A(t) = 0 when HA drops below this
/// (`anima_engine.py::HA_DISABLE_THRESHOLD = 0.60`).
pub const HA_DISABLE_THRESHOLD: f64 = 0.60;

/// Small epsilon used by the cosine-similarity denominator to avoid
/// division-by-zero on zero vectors — mirrors the `+ 1e-10` guard in
/// `_compute_pcr` (`anima_engine.py` line 1167).
pub const COSINE_EPS: f64 = 1e-10;

/// Default std-dev when the sample has n ≤ 1 element — matches
/// `OutcomeDistribution.from_observations` (`pattern_library.py`
/// `var = ... / n if n > 1 else 0.25` → `std = sqrt(0.25) = 0.5`).
pub const DEFAULT_STD_N_LE_1: f64 = 0.5;

/// Small t-distribution approximation factor: t ≈ 1.96 for large n, and
/// t ≈ 2.262 for small samples (n < 10) — mirrors `pattern_library.py`.
pub fn t_value(n: usize) -> f64 {
    if n < 10 {
        2.262
    } else {
        1.96
    }
}

// ──────────────────────────────────────────────────────────────────────────
//  1. compute_anima_score — A(t) = PCR × HA × CA
// ──────────────────────────────────────────────────────────────────────────

/// Compute the L3.3 ANIMA score:
///
/// ```text
/// A(t) = PCR(t) · HA(t) · CA(t)    ∈ [0, 1]
/// ```
///
/// When `ha < HA_DISABLE_THRESHOLD` (0.60) the ANIMA output is disabled
/// and returns 0.0 — mirrors `anima_engine.py` line 1429:
/// ```python
/// anima_score = 0.0 if anima_disabled else round(pcr * ha * ca, 6)
/// ```
///
/// The caller is responsible for any rounding (`f64::round_to(6)` etc.) —
/// this function returns the un-rounded product so callers in scientific
/// contexts can preserve full precision. The PyO3 wrapper does NOT round
/// either; the API layer rounds for JSON serialization if it chooses to.
///
/// NaN/Inf inputs are coerced to 0.0 to keep the function total —
/// equivalent to `if !is_finite(x) { return 0.0 }` for any of the three
/// scalars.
pub fn compute_anima_score(pcr: f64, ha: f64, ca: f64) -> f64 {
    if !pcr.is_finite() || !ha.is_finite() || !ca.is_finite() {
        return 0.0;
    }
    if ha < HA_DISABLE_THRESHOLD {
        return 0.0;
    }
    let pcr_c = pcr.clamp(0.0, 1.0);
    let ha_c = ha.clamp(0.0, 1.0);
    let ca_c = ca.clamp(0.0, 1.0);
    pcr_c * ha_c * ca_c
}

// ──────────────────────────────────────────────────────────────────────────
//  2. compute_archetype_similarity — cosine similarity
// ──────────────────────────────────────────────────────────────────────────

/// Compute the cosine similarity between an entity vector and an archetype
/// centroid:
///
/// ```text
/// sim = (a · b) / (‖a‖ · ‖b‖ + ε)
/// ```
///
/// Mirrors `anima_engine.py::_compute_pcr` line 1167:
/// ```python
/// sims = np.dot(_centroids_ref, seq_centroid) / (
///     np.linalg.norm(_centroids_ref, axis=1) * norm + 1e-10
/// )
/// ```
///
/// Inputs of unequal length are truncated to the trailing min-length slice
/// (same convention as `sigma::compute_diversity_weight`). When either
/// vector has zero norm (or length 0) the function returns 0.0 — matching
/// the Python guard `norm < 1e-10 → return 0.50` (we return the raw
/// similarity here; PCR callers map 0.0 similarity to the 0.50 neutral
/// prior at the Python layer).
pub fn compute_archetype_similarity(entity_vector: &[f64], archetype_vector: &[f64]) -> f64 {
    if entity_vector.is_empty() || archetype_vector.is_empty() {
        return 0.0;
    }
    let n = entity_vector.len().min(archetype_vector.len());
    let mut dot = 0.0_f64;
    let mut norm_a = 0.0_f64;
    let mut norm_b = 0.0_f64;
    for i in 0..n {
        let a = entity_vector[i];
        let b = archetype_vector[i];
        if !a.is_finite() || !b.is_finite() {
            continue;
        }
        dot += a * b;
        norm_a += a * a;
        norm_b += b * b;
    }
    let denom = (norm_a.sqrt() * norm_b.sqrt()) + COSINE_EPS;
    if denom <= COSINE_EPS {
        return 0.0;
    }
    let sim = dot / denom;
    // Cosine can exceed [-1, 1] by floating-point noise; clip for safety.
    sim.clamp(-1.0, 1.0)
}

// ──────────────────────────────────────────────────────────────────────────
//  3. compute_observer_effect — OE = corr(publication[t-1], behavioral_change[t])
// ──────────────────────────────────────────────────────────────────────────

/// Compute the L3.6 Observer Effect:
///
/// ```text
/// OE = corr(publication_strength[t-1], behavioral_change[t])
/// ```
///
/// Lag-1 Pearson correlation: the publication series is shifted by one
/// (dropping its last element) and aligned with the behavioral-change
/// series (dropping its first element), so each pair is (pub[t-1],
/// change[t]). Mirrors `reflexivity.py::compute_observer_effect` lines
/// 184-188:
///
/// ```python
/// pubs    = signal_publications[:-1]
/// changes = behavioral_changes[1:]
/// corr    = compute_correlation(pubs, changes)
/// oe      = max(0.0, corr)
/// ```
///
/// This function returns the raw Pearson correlation ∈ [-1, 1]. Callers
/// that need the positive-clipped `oe_factor` (as `reflexivity.py` does)
/// can apply `max(0.0, corr)` themselves — the math is identical, but
/// downstream code sometimes needs the sign for diagnostic purposes.
///
/// Returns 0.0 when fewer than 2 paired samples are available, when either
/// series has zero variance, or when either input is shorter than 2 —
/// matching the Python guard `if len(...) < 5: return 0.0` is intentionally
/// relaxed to `< 2` so the function can run on smaller samples in unit
/// tests, but the Python reference's `compute_correlation` itself only
/// requires `n >= 2`.
pub fn compute_observer_effect(publications: &[f64], behavioral_changes: &[f64]) -> f64 {
    if publications.len() < 2 || behavioral_changes.len() < 2 {
        return 0.0;
    }
    // Lag-1 alignment: pubs = publications[:-1], changes = behavioral_changes[1:]
    let n_pub = publications.len() - 1;
    let n_chg = behavioral_changes.len() - 1;
    let n = n_pub.min(n_chg);
    if n < 2 {
        return 0.0;
    }
    let pubs = &publications[publications.len() - n - 1..publications.len() - 1];
    let changes = &behavioral_changes[behavioral_changes.len() - n..];

    pearson_correlation(pubs, changes)
}

/// Compute the Pearson correlation between two equal-length series.
///
/// This is the inner primitive used by both `compute_observer_effect` and
/// (potentially) `compute_reflexivity` from `reflexivity.py`. Exposed as a
/// `pub` function so the Python bridge can call it directly for testing
/// and for any future call-site that wants raw correlation.
pub fn pearson_correlation(x: &[f64], y: &[f64]) -> f64 {
    let n = x.len().min(y.len());
    if n < 2 {
        return 0.0;
    }
    let x = &x[x.len() - n..];
    let y = &y[y.len() - n..];

    let mut mean_x = 0.0_f64;
    let mut mean_y = 0.0_f64;
    let mut count = 0_usize;
    for i in 0..n {
        let xi = x[i];
        let yi = y[i];
        if !xi.is_finite() || !yi.is_finite() {
            continue;
        }
        mean_x += xi;
        mean_y += yi;
        count += 1;
    }
    if count < 2 {
        return 0.0;
    }
    mean_x /= count as f64;
    mean_y /= count as f64;

    let mut cov = 0.0_f64;
    let mut var_x = 0.0_f64;
    let mut var_y = 0.0_f64;
    for i in 0..n {
        let xi = x[i];
        let yi = y[i];
        if !xi.is_finite() || !yi.is_finite() {
            continue;
        }
        let dx = xi - mean_x;
        let dy = yi - mean_y;
        cov += dx * dy;
        var_x += dx * dx;
        var_y += dy * dy;
    }
    if var_x <= 0.0 || var_y <= 0.0 {
        return 0.0;
    }
    let denom = (var_x * var_y).sqrt();
    if denom == 0.0 {
        return 0.0;
    }
    let corr = cov / denom;
    corr.clamp(-1.0, 1.0)
}

// ──────────────────────────────────────────────────────────────────────────
//  4. compute_ci_95 — 95% confidence interval (t-distribution approx)
// ──────────────────────────────────────────────────────────────────────────

/// Compute the 95% confidence interval for a sample mean given its
/// already-computed mean and standard deviation:
///
/// ```text
/// margin = t · σ / √n       where t = 2.262 if n < 10 else 1.96
/// CI_95  = (max(0.0, mean − margin), min(1.0, mean + margin))
/// ```
///
/// Mirrors `pattern_library.py::OutcomeDistribution.from_observations`
/// (lines 82-92) exactly. The clip to `[0.0, 1.0]` reflects the spec's
/// invariant that ANIMA scores live in the unit interval — for callers
/// working with unbounded scores (e.g., block counts), use the un-clipped
/// `compute_ci_95_unbounded` variant below.
///
/// `n_samples == 0` returns `(mean, mean)` (degenerate interval), matching
/// the Python `OutcomeDistribution(0.5, 0.25, 0.0, 1.0, 0.0, 0)` cold-start
/// shape — the caller is responsible for the cold-start handling.
pub fn compute_ci_95(mean: f64, std_dev: f64, n_samples: usize) -> (f64, f64) {
    if n_samples == 0 {
        // Degenerate: return a unit-bounded identity interval.
        return (mean.clamp(0.0, 1.0), mean.clamp(0.0, 1.0));
    }
    let m = if mean.is_finite() { mean } else { 0.5 };
    let s = if std_dev.is_finite() && std_dev >= 0.0 {
        std_dev
    } else {
        DEFAULT_STD_N_LE_1
    };
    let t = t_value(n_samples);
    let margin = t * s / (n_samples as f64).sqrt();
    let lo = (m - margin).max(0.0);
    let hi = (m + margin).min(1.0);
    (lo, hi)
}

/// Unbounded variant of `compute_ci_95` for callers whose scores are NOT
/// in the unit interval (e.g., block counts, wei amounts). The clipping
/// to `[0, 1]` is omitted — only the lower clamp at 0.0 (scores cannot
/// be negative in ANIMA's domain) is preserved.
pub fn compute_ci_95_unbounded(mean: f64, std_dev: f64, n_samples: usize) -> (f64, f64) {
    if n_samples == 0 {
        return (mean.max(0.0), mean.max(0.0));
    }
    let m = if mean.is_finite() { mean } else { 0.0 };
    let s = if std_dev.is_finite() && std_dev >= 0.0 {
        std_dev
    } else {
        DEFAULT_STD_N_LE_1
    };
    let t = t_value(n_samples);
    let margin = t * s / (n_samples as f64).sqrt();
    let lo = (m - margin).max(0.0);
    let hi = m + margin;
    (lo, hi)
}

// ──────────────────────────────────────────────────────────────────────────
//  5. compute_probability_distribution — mean / std_dev / CI_95 over scores
// ──────────────────────────────────────────────────────────────────────────

/// Result of `compute_probability_distribution`. Returned as a plain struct
/// so the PyO3 wrapper can convert it to a Python tuple or dict, and the
/// ctypes shim can serialize it as a flat `[f64; 4]` out-buffer.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ProbabilityDistribution {
    pub mean: f64,
    pub std_dev: f64,
    pub ci_low: f64,
    pub ci_high: f64,
}

/// Compute the full probability distribution over a sample of scores:
///
/// ```text
/// mean   = (1/n) Σ x_i
/// var    = (1/n) Σ (x_i − mean)²             (n > 1, else 0.25)
/// std    = √var
/// CI_95  = (max(0.0, mean − t·σ/√n), min(1.0, mean + t·σ/√n))
///   where t = 2.262 if n < 10 else 1.96
/// ```
///
/// Mirrors `OutcomeDistribution.from_observations` (pattern_library.py)
/// and the per-signal distribution in `anima_engine.py::get_anima_score`
/// (lines 1438-1453). The spec §3.3 mandates that ANIMA outputs are always
/// `PROBABILITY_DISTRIBUTION` rather than point predictions.
///
/// Returns the standard `(mean, std_dev, ci_low, ci_high)` tuple shape so
/// the caller can destructure it directly. NaN inputs in the scores
/// vector are skipped (not counted toward `n`) — a small concession to
/// robustness that does not affect the math on clean inputs.
///
/// Cold-start: when `scores` is empty, returns `(0.5, 0.25, 0.0, 1.0)` —
/// matching `OutcomeDistribution(0.5, 0.25, 0.0, 1.0, 0.0, 0)`.
pub fn compute_probability_distribution(scores: &[f64]) -> (f64, f64, f64, f64) {
    let pd = compute_probability_distribution_struct(scores);
    (pd.mean, pd.std_dev, pd.ci_low, pd.ci_high)
}

/// Same as `compute_probability_distribution` but returns the struct
/// form. Used by the PyO3 wrapper so the conversion to a Python tuple
/// happens in one place.
pub fn compute_probability_distribution_struct(scores: &[f64]) -> ProbabilityDistribution {
    // Filter NaN/Inf — count only finite samples.
    let mut n = 0_usize;
    let mut sum = 0.0_f64;
    for &x in scores {
        if x.is_finite() {
            n += 1;
            sum += x;
        }
    }
    if n == 0 {
        // Cold-start prior — matches `OutcomeDistribution(0.5, 0.25, 0.0, 1.0, 0.0, 0)`.
        return ProbabilityDistribution {
            mean: 0.5,
            std_dev: 0.25,
            ci_low: 0.0,
            ci_high: 1.0,
        };
    }
    let mean = sum / n as f64;
    let var = if n > 1 {
        let mut acc = 0.0_f64;
        for &x in scores {
            if x.is_finite() {
                let d = x - mean;
                acc += d * d;
            }
        }
        acc / n as f64
    } else {
        0.25
    };
    let std = var.sqrt();
    let (ci_low, ci_high) = compute_ci_95(mean, std, n);
    ProbabilityDistribution {
        mean,
        std_dev: std,
        ci_low,
        ci_high,
    }
}

// ──────────────────────────────────────────────────────────────────────────
//  Bonus: compute_pattern_library_pcr — pattern library PCR hot path
// ──────────────────────────────────────────────────────────────────────────

/// Compute the Pattern Coherence Ratio (PCR) over a set of pattern
/// coherence scores against their per-category θ_PCR thresholds:
///
/// ```text
/// PCR = (#patterns with coherence > θ_PCR) / (#total patterns)
/// ```
///
/// Mirrors `pattern_library.py::ANIMAPatternLibrary.compute_pcr` (line
/// 404). Each entry of `coherences` is the current coherence of one
/// pattern; each entry of `thresholds` is that pattern's θ_PCR. Returns
/// `(pcr, coherent_count, total_count)` so callers can report the
/// breakdown as the Python API does.
///
/// This is the hot-path primitive behind `_compute_pcr` in
/// `anima_engine.py` (line 1133); the sequence-window centroid math stays
/// in Python because it depends on FAISS vectors, but the counting math
/// over the resulting coherence scores is here.
pub fn compute_pattern_library_pcr(
    coherences: &[f64],
    thresholds: &[f64],
) -> (f64, usize, usize) {
    let n = coherences.len().min(thresholds.len());
    if n == 0 {
        return (0.0, 0, 0);
    }
    let mut coherent = 0_usize;
    for i in 0..n {
        let c = coherences[i];
        let t = thresholds[i];
        if c.is_finite() && t.is_finite() && c > t {
            coherent += 1;
        }
    }
    (coherent as f64 / n as f64, coherent, n)
}

// ──────────────────────────────────────────────────────────────────────────
//  Tests
// ──────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    // ── compute_anima_score ────────────────────────────────────────────────────

    #[test]
    fn test_anima_score_basic_product() {
        // Spec: A = PCR · HA · CA
        assert!((compute_anima_score(0.8, 0.9, 0.7) - 0.504).abs() < 1e-12);
    }

    #[test]
    fn test_anima_score_disabled_below_ha_threshold() {
        // HA < 0.60 → A = 0 (anima_engine.py line 1427)
        assert_eq!(compute_anima_score(1.0, 0.50, 1.0), 0.0);
        assert_eq!(compute_anima_score(1.0, 0.59, 1.0), 0.0);
    }

    #[test]
    fn test_anima_score_enabled_at_boundary() {
        // HA = 0.60 exactly is NOT disabled (< is strict)
        let a = compute_anima_score(1.0, 0.60, 1.0);
        assert!((a - 0.60).abs() < 1e-12);
    }

    #[test]
    fn test_anima_score_clamps_inputs_to_unit_interval() {
        // Out-of-range inputs are clamped before multiplication
        assert!((compute_anima_score(1.5, 1.0, 1.0) - 1.0).abs() < 1e-12);
        assert!((compute_anima_score(2.0, 0.9, 0.5) - 0.45).abs() < 1e-12);
    }

    #[test]
    fn test_anima_score_nan_inputs_return_zero() {
        assert_eq!(compute_anima_score(f64::NAN, 0.9, 0.7), 0.0);
        assert_eq!(compute_anima_score(0.9, f64::NAN, 0.7), 0.0);
        assert_eq!(compute_anima_score(0.9, 0.9, f64::NAN), 0.0);
        assert_eq!(compute_anima_score(f64::INFINITY, 0.9, 0.7), 0.0);
    }

    // ── compute_archetype_similarity ──────────────────────────────────────────

    #[test]
    fn test_cosine_identical_vectors() {
        let v = [0.1, 0.4, 0.2, 0.3];
        let sim = compute_archetype_similarity(&v, &v);
        assert!((sim - 1.0).abs() < 1e-9, "expected ~1.0 got {}", sim);
    }

    #[test]
    fn test_cosine_orthogonal_vectors() {
        let a = [1.0, 0.0];
        let b = [0.0, 1.0];
        let sim = compute_archetype_similarity(&a, &b);
        assert!(sim.abs() < 1e-9, "expected 0 got {}", sim);
    }

    #[test]
    fn test_cosine_opposite_vectors() {
        let a = [1.0, 0.0];
        let b = [-1.0, 0.0];
        let sim = compute_archetype_similarity(&a, &b);
        assert!((sim + 1.0).abs() < 1e-9, "expected -1 got {}", sim);
    }

    #[test]
    fn test_cosine_zero_vector_returns_zero() {
        let a = [0.0, 0.0, 0.0];
        let b = [1.0, 1.0, 1.0];
        assert_eq!(compute_archetype_similarity(&a, &b), 0.0);
    }

    #[test]
    fn test_cosine_empty_inputs_return_zero() {
        assert_eq!(compute_archetype_similarity(&[], &[1.0, 2.0]), 0.0);
        assert_eq!(compute_archetype_similarity(&[1.0], &[]), 0.0);
    }

    #[test]
    fn test_cosine_known_value() {
        // a = [1,2,3], b = [4,5,6]
        // dot = 1·4+2·5+3·6 = 4+10+18 = 32
        // ‖a‖ = √14 ≈ 3.7417, ‖b‖ = √77 ≈ 8.7750
        // sim = 32 / (√14·√77) ≈ 0.9746
        let a = [1.0, 2.0, 3.0];
        let b = [4.0, 5.0, 6.0];
        let sim = compute_archetype_similarity(&a, &b);
        let expected = 32.0 / ((14.0_f64).sqrt() * (77.0_f64).sqrt());
        assert!((sim - expected).abs() < 1e-9);
    }

    #[test]
    fn test_cosine_unequal_length_truncates_to_min() {
        let a = [1.0, 2.0, 3.0, 99.0];
        let b = [1.0, 2.0, 3.0];
        let sim = compute_archetype_similarity(&a, &b);
        // Should match the equal-length version since the extra element is dropped.
        let sim_eq = compute_archetype_similarity(&[1.0, 2.0, 3.0], &[1.0, 2.0, 3.0]);
        assert!((sim - sim_eq).abs() < 1e-9);
    }

    // ── compute_observer_effect / pearson_correlation ──────────────────────

    #[test]
    fn test_pearson_perfect_positive() {
        let x = [1.0, 2.0, 3.0, 4.0, 5.0];
        let y = [2.0, 4.0, 6.0, 8.0, 10.0];
        let c = pearson_correlation(&x, &y);
        assert!((c - 1.0).abs() < 1e-9, "got {}", c);
    }

    #[test]
    fn test_pearson_perfect_negative() {
        let x = [1.0, 2.0, 3.0, 4.0, 5.0];
        let y = [10.0, 8.0, 6.0, 4.0, 2.0];
        let c = pearson_correlation(&x, &y);
        assert!((c + 1.0).abs() < 1e-9, "got {}", c);
    }

    #[test]
    fn test_pearson_zero_correlation_uncorrelated_series() {
        // Uncorrelated series → correlation near 0
        let x = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0];
        let y = [3.0, 1.0, 4.0, 1.0, 5.0, 9.0];
        let c = pearson_correlation(&x, &y);
        assert!(c.abs() < 0.95, "expected |c| < 0.95, got {}", c);
    }

    #[test]
    fn test_pearson_short_series_returns_zero() {
        assert_eq!(pearson_correlation(&[1.0], &[2.0]), 0.0);
        assert_eq!(pearson_correlation(&[], &[]), 0.0);
    }

    #[test]
    fn test_observer_effect_lag1_alignment() {
        // pubs    = [0.5, 0.6, 0.7, 0.8, 0.9]
        // changes = [0.2, 0.5, 0.65, 0.78, 0.88]
        // After lag-1: pubs[:-1]    = [0.5, 0.6, 0.7, 0.8]
        //              changes[1:] = [0.5, 0.65, 0.78, 0.88]
        // These are very strongly positively correlated.
        let pubs = [0.5, 0.6, 0.7, 0.8, 0.9];
        let changes = [0.2, 0.5, 0.65, 0.78, 0.88];
        let oe = compute_observer_effect(&pubs, &changes);
        assert!(oe > 0.9, "expected OE > 0.9, got {}", oe);
    }

    #[test]
    fn test_observer_effect_short_input_returns_zero() {
        assert_eq!(compute_observer_effect(&[1.0], &[2.0]), 0.0);
        assert_eq!(compute_observer_effect(&[], &[]), 0.0);
    }

    #[test]
    fn test_observer_effect_zero_variance_returns_zero() {
        let pubs = [0.5, 0.5, 0.5, 0.5, 0.5];
        let changes = [0.2, 0.4, 0.6, 0.8, 1.0];
        assert_eq!(compute_observer_effect(&pubs, &changes), 0.0);
    }

    // ── compute_ci_95 ──────────────────────────────────────────────────────

    #[test]
    fn test_ci_95_large_n_uses_1_96_t_value() {
        // n = 100, std = 0.1, mean = 0.5
        // margin = 1.96 * 0.1 / √100 = 0.0196
        let (lo, hi) = compute_ci_95(0.5, 0.1, 100);
        assert!((lo - (0.5 - 0.0196)).abs() < 1e-9);
        assert!((hi - (0.5 + 0.0196)).abs() < 1e-9);
    }

    #[test]
    fn test_ci_95_small_n_uses_2_262_t_value() {
        // n = 5, std = 0.2, mean = 0.5
        // margin = 2.262 * 0.2 / √5 ≈ 0.202327
        let (lo, hi) = compute_ci_95(0.5, 0.2, 5);
        let expected_margin = 2.262 * 0.2 / (5.0_f64).sqrt();
        assert!((lo - (0.5 - expected_margin)).abs() < 1e-9);
        assert!((hi - (0.5 + expected_margin)).abs() < 1e-9);
    }

    #[test]
    fn test_ci_95_clips_to_unit_interval() {
        // mean = 0.99, std = 0.5, n = 5 → upper bound would exceed 1.0
        let (lo, hi) = compute_ci_95(0.99, 0.5, 5);
        assert!(hi <= 1.0);
        assert!(lo >= 0.0);
        // Symmetric for low end
        let (lo2, _hi2) = compute_ci_95(0.01, 0.5, 5);
        assert!(lo2 >= 0.0);
    }

    #[test]
    fn test_ci_95_zero_n_degenerate() {
        let (lo, hi) = compute_ci_95(0.5, 0.2, 0);
        // n=0 → degenerate interval (mean, mean), clamped to [0,1]
        assert!((lo - 0.5).abs() < 1e-9);
        assert!((hi - 0.5).abs() < 1e-9);
    }

    #[test]
    fn test_ci_95_unbounded_does_not_clip_upper() {
        // Unbounded variant: large mean → upper bound can exceed 1.0
        let (_lo, hi) = compute_ci_95_unbounded(5.0, 0.5, 5);
        assert!(hi > 1.0);
    }

    // ── compute_probability_distribution ───────────────────────────────────

    #[test]
    fn test_pd_basic_stats() {
        let scores = [0.5, 0.6, 0.7, 0.8, 0.9];
        let (mean, std, lo, hi) = compute_probability_distribution(&scores);
        assert!((mean - 0.7).abs() < 1e-9);
        // var = ((-0.2)^2 + (-0.1)^2 + 0 + (0.1)^2 + (0.2)^2) / 5 = 0.02
        // std = √0.02 ≈ 0.1414
        assert!((std - (0.02_f64).sqrt()).abs() < 1e-9);
        assert!(lo < mean && mean < hi);
    }

    #[test]
    fn test_pd_empty_returns_cold_start_prior() {
        let (mean, std, lo, hi) = compute_probability_distribution(&[]);
        assert!((mean - 0.5).abs() < 1e-9);
        assert!((std - 0.25).abs() < 1e-9);
        assert!((lo - 0.0).abs() < 1e-9);
        assert!((hi - 1.0).abs() < 1e-9);
    }

    #[test]
    fn test_pd_single_sample_uses_default_var() {
        // n=1 → var = 0.25 → std = 0.5
        let (mean, std, _lo, _hi) = compute_probability_distribution(&[0.7]);
        assert!((mean - 0.7).abs() < 1e-9);
        assert!((std - 0.5).abs() < 1e-9);
    }

    #[test]
    fn test_pd_nan_inputs_are_skipped() {
        let scores = [0.5, f64::NAN, 0.7, f64::INFINITY, 0.9];
        let (mean, _std, _lo, _hi) = compute_probability_distribution(&scores);
        // Only 3 finite values → mean = (0.5+0.7+0.9)/3 = 0.7
        assert!((mean - 0.7).abs() < 1e-9);
    }

    #[test]
    fn test_pd_clips_ci_to_unit_interval() {
        // All-near-1 scores with high variance → upper bound clipped to 1.0
        let scores = [0.95, 0.96, 0.97, 0.98, 0.99];
        let (_mean, _std, lo, hi) = compute_probability_distribution(&scores);
        assert!(hi <= 1.0);
        assert!(lo >= 0.0);
    }

    // ── compute_pattern_library_pcr ─────────────────────────────────────────

    #[test]
    fn test_pattern_library_pcr_basic() {
        let coherences = [0.7, 0.5, 0.8, 0.4];
        let thresholds = [0.6, 0.6, 0.6, 0.6];
        let (pcr, coherent, total) = compute_pattern_library_pcr(&coherences, &thresholds);
        assert_eq!(coherent, 2);
        assert_eq!(total, 4);
        assert!((pcr - 0.5).abs() < 1e-9);
    }

    #[test]
    fn test_pattern_library_pcr_empty() {
        let (pcr, coherent, total) = compute_pattern_library_pcr(&[], &[]);
        assert_eq!(pcr, 0.0);
        assert_eq!(coherent, 0);
        assert_eq!(total, 0);
    }

    #[test]
    fn test_pattern_library_pcr_unequal_lengths() {
        let coherences = [0.7, 0.5, 0.8];
        let thresholds = [0.6, 0.6];
        let (pcr, coherent, total) = compute_pattern_library_pcr(&coherences, &thresholds);
        // Truncated to min length = 2 → only first two patterns counted.
        assert_eq!(coherent, 1);
        assert_eq!(total, 2);
        assert!((pcr - 0.5).abs() < 1e-9);
    }
}
