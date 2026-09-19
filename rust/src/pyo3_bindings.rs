//! pyo3_bindings.rs — PyO3 wrappers for the TRION Rust core
//!
//! Part 11 language mandate: "Performance-critical paths compiled to Rust
//! via PyO3 bindings." This module is the seam between the Python
//! pipeline (`core/rust_bridge_pyo3.py`) and the native Rust
//! implementations of:
//!
//!   1. Behavioral Hash — dual-strand SHA3-256 (L0.1)
//!   2. Physical Richness Score Φ — 9-feature entropy engine (L1.1)
//!   3. Spiritual Plane Σ — diversity-weighted BFT (L4.1)
//!   4. The Master Equation — T(t) = [C≥Θ]·S·e^(M·t) (L5)
//!
//! All Python-exposed functions live behind `#[cfg(feature = "pyo3")]` so
//! `cargo build` (default features) compiles the crate without pulling in
//! the Python linkage; enable with `cargo build --features pyo3`. The
//! same module also exports `#[no_mangle] extern "C"` shims for the
//! ctypes fallback path used when the Python interpreter cannot import
//! the PyO3 extension module directly (e.g., in frozen/embedded
//! deployments).
//!
//! The Python side (`core/rust_bridge_pyo3.py`) tries the PyO3 import
//! first and falls back to the ctypes shims when only a `libtrion_btcp.so`
//! is available. Both paths produce byte-identical results because they
//! call into the same `phi` / `sigma` / `master_equation` modules.

#[cfg(feature = "pyo3")]
use pyo3::prelude::*;

#[cfg(feature = "pyo3")]
use pyo3::types::PyModule;

#[cfg(feature = "pyo3")]
use sha3::{Digest, Sha3_256};

#[cfg(feature = "pyo3")]
use crate::master_equation::master_equation;
#[cfg(feature = "pyo3")]
use crate::phi::{compute_phi as rust_compute_phi, TransactionData};
#[cfg(feature = "pyo3")]
use crate::sigma::{compute_sigma as rust_compute_sigma, compute_diversity_weight};
#[cfg(feature = "pyo3")]
use crate::anima::{
    compute_anima_score as rust_compute_anima_score,
    compute_archetype_similarity as rust_compute_archetype_similarity,
    compute_ci_95 as rust_compute_ci_95,
    compute_ci_95_unbounded as rust_compute_ci_95_unbounded,
    compute_observer_effect as rust_compute_observer_effect,
    compute_pattern_library_pcr as rust_compute_pattern_library_pcr,
    compute_probability_distribution as rust_compute_probability_distribution,
    pearson_correlation as rust_pearson_correlation,
};
#[cfg(feature = "pyo3")]
use crate::living_security::{
    compute_sec_native as rust_compute_sec_native,
    CRISPRDefense, GenomicKeyEvolver, hash_dna as rust_hash_dna,
    kolmogorov_bound as rust_kolmogorov_bound,
};

// ──────────────────────────────────────────────────────────────────────────
//  PyTransactionData — Python-facing mirror of `phi::TransactionData`
// ──────────────────────────────────────────────────────────────────────────

/// Python-visible `TransactionData` record. Mirrors the field set of
/// `phi::TransactionData` exactly so the PyO3 conversion is a struct
/// copy with no translation logic.
#[cfg(feature = "pyo3")]
#[pyclass(name = "TransactionData")]
#[derive(Clone, Default)]
pub struct PyTransactionData {
    #[pyo3(get, set)]
    pub tx_hash: String,
    #[pyo3(get, set)]
    pub value_wei: u128,
    #[pyo3(get, set)]
    pub gas_used: u64,
    #[pyo3(get, set)]
    pub contract_addr: String,
    #[pyo3(get, set)]
    pub from_addr: String,
    #[pyo3(get, set)]
    pub to_addr: String,
    #[pyo3(get, set)]
    pub block_num: u64,
    #[pyo3(get, set)]
    pub timestamp: f64,
}

#[cfg(feature = "pyo3")]
#[pymethods]
impl PyTransactionData {
    /// Construct a new `TransactionData` from Python.
    #[new]
    #[pyo3(signature = (
        tx_hash = String::new(),
        value_wei = 0,
        gas_used = 0,
        contract_addr = String::new(),
        from_addr = String::new(),
        to_addr = String::new(),
        block_num = 0,
        timestamp = 0.0,
    ))]
    #[allow(clippy::too_many_arguments)]
    fn new(
        tx_hash: String,
        value_wei: u128,
        gas_used: u64,
        contract_addr: String,
        from_addr: String,
        to_addr: String,
        block_num: u64,
        timestamp: f64,
    ) -> Self {
        Self {
            tx_hash,
            value_wei,
            gas_used,
            contract_addr,
            from_addr,
            to_addr,
            block_num,
            timestamp,
        }
    }
}

#[cfg(feature = "pyo3")]
impl From<&PyTransactionData> for TransactionData {
    fn from(p: &PyTransactionData) -> Self {
        TransactionData {
            tx_hash: p.tx_hash.clone(),
            value_wei: p.value_wei,
            gas_used: p.gas_used,
            contract_addr: p.contract_addr.clone(),
            from_addr: p.from_addr.clone(),
            to_addr: p.to_addr.clone(),
            block_num: p.block_num,
            timestamp: p.timestamp,
        }
    }
}

// ──────────────────────────────────────────────────────────────────────────
//  Behavioral Hash — dual-strand SHA3-256 (L0.1)
// ──────────────────────────────────────────────────────────────────────────

/// Canonical dual-strand BH construction (whitepaper L0.1 / CANONICAL_BH.md):
///
/// ```text
/// sense     = SHA3-256(payload || 0x00)
/// antisense = SHA3-256(payload || 0xFF) XOR complement(sense)
/// ```
///
/// Identical to `hash_dna` in `core/primitives/behavioral_hash.py` and
/// `trion-common::hash_dna::canonical_bh` in the indexer crate. The
/// returned tuple is `(sense_bytes, antisense_bytes)`, each 32 bytes long.
#[cfg(feature = "pyo3")]
pub fn behavioral_hash(payload: &[u8]) -> (Vec<u8>, Vec<u8>) {
    let mut p0 = Vec::with_capacity(payload.len() + 1);
    p0.extend_from_slice(payload);
    p0.push(0x00);
    let sense: [u8; 32] = Sha3_256::digest(&p0).into();

    let mut pff = Vec::with_capacity(payload.len() + 1);
    pff.extend_from_slice(payload);
    pff.push(0xFF);
    let sha3ff: [u8; 32] = Sha3_256::digest(&pff).into();

    // antisense = sha3ff XOR NOT(sense)  (complement transform)
    let mut antisense = Vec::with_capacity(32);
    for (ff, s) in sha3ff.iter().zip(sense.iter()) {
        antisense.push(ff ^ !s);
    }
    (sense.to_vec(), antisense)
}

/// `#[pyfunction]` wrapper around `behavioral_hash`. Returns a 2-tuple of
/// `bytes` objects `(sense, antisense)`.
#[cfg(feature = "pyo3")]
#[pyfunction]
#[pyo3(name = "compute_behavioral_hash")]
pub fn py_compute_behavioral_hash(payload: &[u8]) -> (Vec<u8>, Vec<u8>) {
    behavioral_hash(payload)
}

// ──────────────────────────────────────────────────────────────────────────
//  Φ — Physical Richness Score (L1.1)
// ──────────────────────────────────────────────────────────────────────────

/// `#[pyfunction]` wrapper around `phi::compute_phi`. Takes a list of
/// `TransactionData` records and a length-9 list of weights.
#[cfg(feature = "pyo3")]
#[pyfunction]
#[pyo3(name = "compute_phi")]
pub fn py_compute_phi(
    transactions: Vec<PyRef<PyTransactionData>>,
    weights: Vec<f64>,
) -> PyResult<f64> {
    if weights.len() != 9 {
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "weights must have 9 entries, got {}",
            weights.len()
        )));
    }
    let mut w = [0.0; 9];
    w.copy_from_slice(&weights);
    let txs: Vec<TransactionData> = transactions.iter().map(TransactionData::from).collect();
    Ok(rust_compute_phi(&txs, &w))
}

// ──────────────────────────────────────────────────────────────────────────
//  Σ — Spiritual Plane diversity-weighted BFT (L4.1)
// ──────────────────────────────────────────────────────────────────────────

/// `#[pyfunction]` wrapper around `sigma::compute_sigma`. The Python
/// caller supplies pre-computed `diversity` weights (or calls
/// `compute_diversity_weight` once per validator and assembles the slice
/// itself — the wrapper exists for callers that prefer the bulk path).
#[cfg(feature = "pyo3")]
#[pyfunction]
#[pyo3(name = "compute_sigma")]
#[pyo3(signature = (stakes, diversity, valuations, median, delta_base, volatility))]
pub fn py_compute_sigma(
    stakes: Vec<f64>,
    diversity: Vec<f64>,
    valuations: Vec<f64>,
    median: f64,
    delta_base: f64,
    volatility: f64,
) -> f64 {
    rust_compute_sigma(
        &stakes,
        &diversity,
        &valuations,
        median,
        delta_base,
        volatility,
    )
}

/// `#[pyfunction]` wrapper around `sigma::compute_diversity_weight` so
/// the Python caller can pre-compute `d_j` per validator.
#[cfg(feature = "pyo3")]
#[pyfunction]
#[pyo3(name = "compute_diversity_weight")]
pub fn py_compute_diversity_weight(messages_j: Vec<f64>, median_messages: Vec<f64>) -> f64 {
    compute_diversity_weight(&messages_j, &median_messages)
}

// ──────────────────────────────────────────────────────────────────────────
//  Master Equation — T(t) = [C≥Θ]·S·e^(M·t) (L5)
// ──────────────────────────────────────────────────────────────────────────

/// `#[pyfunction]` wrapper around `master_equation::master_equation`.
/// Returns `None` (Python `None`) when the gate is closed — that is the
/// SILENCE branch: T(t) = 0 and no valuation output is produced.
#[cfg(feature = "pyo3")]
#[pyfunction]
#[pyo3(name = "compute_master_equation")]
#[pyo3(signature = (c, theta, s, moat, time_years))]
pub fn py_compute_master_equation(
    c: f64,
    theta: f64,
    s: f64,
    moat: f64,
    time_years: f64,
) -> Option<f64> {
    master_equation(c, theta, s, moat, time_years)
}

// ──────────────────────────────────────────────────────────────────────────
//  Signal Emitter — §14.2 24-type SignalType registry lookups (PyO3 wrappers)
// ──────────────────────────────────────────────────────────────────────────
//
// Part 11 language mandate: the canonical 24-type SignalType registry
// (Rust `signal_emitter::SignalType` ↔ Python `SignalType` IntEnum) is
// parity-tested across both implementations. The PyO3 wrappers below expose
// the name ↔ id resolution so `core/rust_bridge_pyo3.py::signal_type_*_
// native` can dispatch through Rust when the PyO3 module is importable;
// the cdylib ctypes fallback path uses the `extern "C"` shims further down.

/// `#[pyfunction]` wrapper around `signal_emitter::SignalType::from_id` —
/// resolves a registry name to its canonical id (0–23). Returns `None`
/// (Python `None`) when the name is not a canonical 24-type member.
#[cfg(feature = "pyo3")]
#[pyfunction]
#[pyo3(name = "signal_type_id_from_name")]
pub fn py_signal_type_id_from_name(name: &str) -> Option<u8> {
    let name_upper = name.to_uppercase();
    for variant in crate::signal_emitter::ALL_SIGNAL_TYPES.iter() {
        if variant.name() == name_upper {
            return Some(variant.id());
        }
    }
    None
}

/// `#[pyfunction]` wrapper around `signal_emitter::SignalType::name` —
/// resolves a canonical id (0–23) to its registry name. Returns `None`
/// when the id is outside 0–23.
#[cfg(feature = "pyo3")]
#[pyfunction]
#[pyo3(name = "signal_type_name_from_id")]
pub fn py_signal_type_name_from_id(id: u8) -> Option<String> {
    crate::signal_emitter::SignalType::from_id(id).map(|v| v.name().to_string())
}

// ──────────────────────────────────────────────────────────────────────────
//  ANIMA ML hot-path (L3.3 / L3.6) — Part 11 language mandate
// ──────────────────────────────────────────────────────────────────────────
//
//  Five performance-critical inference functions ported from the Python
//  ANIMA engine (`anima-service/anima_engine.py` + `core/mental/anima/`):
//
//    1. compute_anima_score(pcr, ha, ca)            → f64
//       A(t) = PCR · HA · CA (L3.3); returns 0 when HA < 0.60.
//
//    2. compute_archetype_similarity(entity, archetype) → f64
//       Cosine similarity between an entity vector and an archetype
//       centroid — `_compute_pcr` step 3.
//
//    3. compute_observer_effect(publications, changes)  → f64
//       Lag-1 Pearson correlation OE = corr(pub[t-1], change[t])
//       (L3.6 Observer Effect / Predictive Completeness Limit).
//
//    4. compute_ci_95(mean, std_dev, n_samples)       → (f64, f64)
//       95% confidence interval using the t-distribution approximation
//       (2.262 for n<10, 1.96 otherwise).
//
//    5. compute_probability_distribution(scores)      → (mean, std, lo, hi)
//       Full PROBABILITY_DISTRIBUTION over a sample of scores — spec §3.3
//       mandates ANIMA outputs are distributions, never point predictions.

/// `#[pyfunction]` wrapper around `anima::compute_anima_score`.
///
/// Python: `trion_rust.compute_anima_score(0.85, 0.92, 0.78)` → 0.60996
#[cfg(feature = "pyo3")]
#[pyfunction]
#[pyo3(name = "compute_anima_score")]
pub fn py_compute_anima_score(pcr: f64, ha: f64, ca: f64) -> f64 {
    rust_compute_anima_score(pcr, ha, ca)
}

/// `#[pyfunction]` wrapper around `anima::compute_archetype_similarity`.
///
/// Python: `trion_rust.compute_archetype_similarity([0.1, 0.4], [0.3, 0.2])`
#[cfg(feature = "pyo3")]
#[pyfunction]
#[pyo3(name = "compute_archetype_similarity")]
pub fn py_compute_archetype_similarity(
    entity_vector: Vec<f64>,
    archetype_vector: Vec<f64>,
) -> f64 {
    rust_compute_archetype_similarity(&entity_vector, &archetype_vector)
}

/// `#[pyfunction]` wrapper around `anima::compute_observer_effect`.
///
/// Python:
///   trion_rust.compute_observer_effect([0.5, 0.6, 0.7, 0.8, 0.9],
///                                      [0.2, 0.5, 0.65, 0.78, 0.88])
#[cfg(feature = "pyo3")]
#[pyfunction]
#[pyo3(name = "compute_observer_effect")]
pub fn py_compute_observer_effect(
    publications: Vec<f64>,
    behavioral_changes: Vec<f64>,
) -> f64 {
    rust_compute_observer_effect(&publications, &behavioral_changes)
}

/// `#[pyfunction]` wrapper around `anima::compute_ci_95`.
///
/// Returns the (ci_low, ci_high) tuple clipped to the unit interval.
#[cfg(feature = "pyo3")]
#[pyfunction]
#[pyo3(name = "compute_ci_95")]
pub fn py_compute_ci_95(mean: f64, std_dev: f64, n_samples: usize) -> (f64, f64) {
    rust_compute_ci_95(mean, std_dev, n_samples)
}

/// `#[pyfunction]` wrapper around `anima::compute_ci_95_unbounded` for
/// callers working with non-unit scores (e.g., block counts).
#[cfg(feature = "pyo3")]
#[pyfunction]
#[pyo3(name = "compute_ci_95_unbounded")]
pub fn py_compute_ci_95_unbounded(mean: f64, std_dev: f64, n_samples: usize) -> (f64, f64) {
    rust_compute_ci_95_unbounded(mean, std_dev, n_samples)
}

/// `#[pyfunction]` wrapper around `anima::compute_probability_distribution`.
///
/// Returns `(mean, std_dev, ci_low, ci_high)` — spec §3.3 mandates that
/// ANIMA outputs are PROBABILITY_DISTRIBUTION, never point predictions.
#[cfg(feature = "pyo3")]
#[pyfunction]
#[pyo3(name = "compute_probability_distribution")]
pub fn py_compute_probability_distribution(scores: Vec<f64>) -> (f64, f64, f64, f64) {
    rust_compute_probability_distribution(&scores)
}

/// `#[pyfunction]` wrapper around `anima::pearson_correlation` —
/// raw two-series Pearson correlation, lag-0 alignment.
#[cfg(feature = "pyo3")]
#[pyfunction]
#[pyo3(name = "pearson_correlation")]
pub fn py_pearson_correlation(x: Vec<f64>, y: Vec<f64>) -> f64 {
    rust_pearson_correlation(&x, &y)
}

/// `#[pyfunction]` wrapper around `anima::compute_pattern_library_pcr`.
/// Returns `(pcr, coherent_count, total_count)` — mirrors
/// `ANIMAPatternLibrary.compute_pcr()` in `pattern_library.py`.
#[cfg(feature = "pyo3")]
#[pyfunction]
#[pyo3(name = "compute_pattern_library_pcr")]
pub fn py_compute_pattern_library_pcr(
    coherences: Vec<f64>,
    thresholds: Vec<f64>,
) -> (f64, usize, usize) {
    rust_compute_pattern_library_pcr(&coherences, &thresholds)
}

// ──────────────────────────────────────────────────────────────────────────
//  Living Security System — L4.3-4.6 + Part 6
// ──────────────────────────────────────────────────────────────────────────

/// Internal helper: evolve a GenomicKey one generation forward, starting
/// from a genesis key if `generation == 0`. Mirrors the Python wrapper
/// `core/rust_bridge_pyo3.py::compute_genomic_key_native` so the two paths
/// produce byte-identical sense/antisense for the same inputs.
fn evolve_genomic_key_bytes(
    entity_id: &str,
    generation: u64,
    behavioral_event: &[u8],
    timestamp: &[u8],
    context: &[u8],
) -> (String, String) {
    use std::time::{SystemTime, UNIX_EPOCH};
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0);
    let h_env_seed = {
        use sha3::Digest;
        let mut h = sha3::Sha3_256::new();
        h.update(b"trion_lss_h_env_seed::");
        h.update(entity_id.as_bytes());
        let out: [u8; 32] = h.finalize().into();
        out
    };

    if generation == 0 {
        let gk = GenomicKeyEvolver::initialize(entity_id.as_bytes(), &h_env_seed, now);
        return (gk.sense_hex(), gk.antisense_hex());
    }

    let mut gk = GenomicKeyEvolver::initialize(entity_id.as_bytes(), &h_env_seed, now);
    if generation > 1 {
        let zero_hash: [u8; 32] = sha3::Sha3_256::digest(b"trion_lss_zero_step").into();
        for _ in 1..generation {
            gk = GenomicKeyEvolver::evolve(&gk, &zero_hash, &zero_hash, &zero_hash, now);
        }
    }
    let gk_final = GenomicKeyEvolver::evolve(&gk, behavioral_event, timestamp, context, now);
    (gk_final.sense_hex(), gk_final.antisense_hex())
}

/// `#[pyfunction]` wrapper around genomic-key evolution. Returns
/// `(sense_hex, antisense_hex)` — each 64 lowercase hex chars.
#[cfg(feature = "pyo3")]
#[pyfunction]
#[pyo3(name = "compute_genomic_key_native")]
#[pyo3(signature = (entity_id, generation, behavioral_event, timestamp, context))]
pub fn py_compute_genomic_key_native(
    entity_id: &str,
    generation: u64,
    behavioral_event: &[u8],
    timestamp: &[u8],
    context: &[u8],
) -> (String, String) {
    evolve_genomic_key_bytes(entity_id, generation, behavioral_event, timestamp, context)
}

/// `#[pyfunction]` wrapper around `living_security::compute_sec_native`.
#[cfg(feature = "pyo3")]
#[pyfunction]
#[pyo3(name = "compute_sec_native")]
#[pyo3(signature = (entity_id, akashic_depth, n_chains, n_validators))]
pub fn py_compute_sec_native(
    entity_id: &str,
    akashic_depth: u64,
    n_chains: u64,
    n_validators: u64,
) -> f64 {
    rust_compute_sec_native(entity_id, akashic_depth, n_chains, n_validators)
}

/// `#[pyfunction]` wrapper around `CRISPRDefense::innate_check`.
#[cfg(feature = "pyo3")]
#[pyfunction]
#[pyo3(name = "crispr_check_native")]
pub fn py_crispr_check_native(transaction_data: &[u8]) -> bool {
    CRISPRDefense::innate_check(transaction_data).is_some()
}

/// `#[pyfunction]` wrapper around `living_security::hash_dna` (L0.1).
#[cfg(feature = "pyo3")]
#[pyfunction]
#[pyo3(name = "lss_hash_dna")]
pub fn py_lss_hash_dna(payload: &[u8]) -> (Vec<u8>, Vec<u8>) {
    let (sense, antisense) = rust_hash_dna(payload);
    (sense.to_vec(), antisense.to_vec())
}

/// `#[pyfunction]` wrapper around `living_security::kolmogorov_bound`.
#[cfg(feature = "pyo3")]
#[pyfunction]
#[pyo3(name = "kolmogorov_bound")]
#[pyo3(signature = (t_seconds, n_chains, n_validators, h_environment))]
pub fn py_kolmogorov_bound(
    t_seconds: f64,
    n_chains: u64,
    n_validators: u64,
    h_environment: &[u8],
) -> PyResult<f64> {
    if h_environment.len() != 32 {
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "h_environment must be 32 bytes, got {}",
            h_environment.len()
        )));
    }
    let mut h = [0u8; 32];
    h.copy_from_slice(h_environment);
    Ok(rust_kolmogorov_bound(t_seconds, n_chains, n_validators, &h))
}

// ──────────────────────────────────────────────────────────────────────────
//  Module entry point — `import trion_rust`
// ──────────────────────────────────────────────────────────────────────────

/// Python module entry point. The `maturin`-built extension is importable
/// as `trion_rust` from Python and exposes:
///
/// ```python
/// import trion_rust
/// sense, antisense = trion_rust.compute_behavioral_hash(b"payload")
/// phi = trion_rust.compute_phi(tx_list, weights)
/// sigma = trion_rust.compute_sigma(stakes, diversity, vals, median, db, v)
/// t = trion_rust.compute_master_equation(c, theta, s, moat, t_years)
/// id  = trion_rust.signal_type_id_from_name("VALUATION")  # → 0
/// name = trion_rust.signal_type_name_from_id(0)           # → "VALUATION"
/// sense_hex, antisense_hex = trion_rust.compute_genomic_key_native(
///     "entity", 1, b"be", b"tm", b"cv")
/// sec = trion_rust.compute_sec_native("entity", 1000, 31, 100)
/// matched = trion_rust.crispr_check_native(tx_bytes)
/// ```
#[cfg(feature = "pyo3")]
#[pymodule]
fn trion_rust(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<PyTransactionData>()?;
    m.add_function(wrap_pyfunction!(py_compute_behavioral_hash, m)?)?;
    m.add_function(wrap_pyfunction!(py_compute_phi, m)?)?;
    m.add_function(wrap_pyfunction!(py_compute_sigma, m)?)?;
    m.add_function(wrap_pyfunction!(py_compute_diversity_weight, m)?)?;
    m.add_function(wrap_pyfunction!(py_compute_master_equation, m)?)?;
    m.add_function(wrap_pyfunction!(py_signal_type_id_from_name, m)?)?;
    m.add_function(wrap_pyfunction!(py_signal_type_name_from_id, m)?)?;
    // ANIMA ML hot-path (L3.3 / L3.6) — Part 11 language mandate.
    m.add_function(wrap_pyfunction!(py_compute_anima_score, m)?)?;
    m.add_function(wrap_pyfunction!(py_compute_archetype_similarity, m)?)?;
    m.add_function(wrap_pyfunction!(py_compute_observer_effect, m)?)?;
    m.add_function(wrap_pyfunction!(py_compute_ci_95, m)?)?;
    m.add_function(wrap_pyfunction!(py_compute_ci_95_unbounded, m)?)?;
    m.add_function(wrap_pyfunction!(py_compute_probability_distribution, m)?)?;
    m.add_function(wrap_pyfunction!(py_pearson_correlation, m)?)?;
    m.add_function(wrap_pyfunction!(py_compute_pattern_library_pcr, m)?)?;
    // Living Security System (L4.3-4.6 + Part 6) — Rust native ports.
    m.add_function(wrap_pyfunction!(py_compute_genomic_key_native, m)?)?;
    m.add_function(wrap_pyfunction!(py_compute_sec_native, m)?)?;
    m.add_function(wrap_pyfunction!(py_crispr_check_native, m)?)?;
    m.add_function(wrap_pyfunction!(py_lss_hash_dna, m)?)?;
    m.add_function(wrap_pyfunction!(py_kolmogorov_bound, m)?)?;
    // Expose module-level constants so the Python side can sanity-check
    // the build (used by core/rust_bridge_pyo3.py).
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add("SUPPORTED_FEATURES", ["bh", "phi", "sigma", "master_equation", "signal_emitter", "anima", "living_security"])?;
    m.add("SIGNAL_TYPE_COUNT", crate::signal_emitter::SIGNAL_TYPE_COUNT)?;
    Ok(())
}

// ──────────────────────────────────────────────────────────────────────────
//  `extern "C"` ctypes shims — fallback path for `core/rust_bridge_pyo3.py`
// ──────────────────────────────────────────────────────────────────────────
//
// The Python bridge first tries `import trion_rust`; if that fails (e.g.
// the .so was compiled without the pyo3 feature, or PyO3's runtime
// version disagrees with the interpreter), it falls back to loading the
// shared library via ctypes and invoking these plain-C entry points.
//
// The shims use a simple C struct layout for the BH result so callers
// do not need to manage heap ownership across the FFI boundary — the
// caller-allocated out-param buffers are 32 bytes each, exactly the
// SHA3-256 digest length.

/// C-layout behavioral-hash result. The Python caller allocates two
/// 32-byte buffers and passes pointers via `trion_rust_compute_bh`.
#[cfg(feature = "pyo3")]
#[repr(C)]
pub struct BehavioralHashResult {
    pub sense: [u8; 32],
    pub antisense: [u8; 32],
}

/// C-compatible shim for `compute_behavioral_hash`. Writes the 32-byte
/// sense and antisense digests into the caller-supplied buffers.
///
/// # Safety
/// `payload_ptr` must point to `len` readable bytes; `out_sense` and
/// `out_antisense` must each point to 32 writable bytes.
#[cfg(feature = "pyo3")]
#[no_mangle]
pub extern "C" fn trion_rust_compute_behavioral_hash(
    payload_ptr: *const u8,
    len: usize,
    out_sense: *mut u8,
    out_antisense: *mut u8,
) -> i32 {
    if payload_ptr.is_null() || out_sense.is_null() || out_antisense.is_null() {
        return -1;
    }
    let payload = unsafe { std::slice::from_raw_parts(payload_ptr, len) };
    let (sense, antisense) = behavioral_hash(payload);
    if sense.len() != 32 || antisense.len() != 32 {
        return -2;
    }
    unsafe {
        std::ptr::copy_nonoverlapping(sense.as_ptr(), out_sense, 32);
        std::ptr::copy_nonoverlapping(antisense.as_ptr(), out_antisense, 32);
    }
    0
}

/// C-compatible shim for `compute_phi` taking flat arrays.
///
/// # Safety
/// `tx_ptr` must point to `tx_count` contiguous `f64` values per
/// `field_count` fields (currently 8: value_wei, gas_used, block_num,
/// timestamp, has_contract_flag, contract_hash_short, from_hash_short,
/// to_hash_short). `weights_ptr` must point to 9 `f64` values.
#[cfg(feature = "pyo3")]
#[no_mangle]
pub extern "C" fn trion_rust_compute_phi_flat(
    tx_ptr: *const f64,
    tx_count: usize,
    field_count: usize,
    weights_ptr: *const f64,
) -> f64 {
    if tx_ptr.is_null() || weights_ptr.is_null() || field_count < 4 || tx_count == 0 {
        return 0.0;
    }
    // Defensive: the caller is expected to pass field_count == 8; if a
    // shorter row layout is used we fall back to defaults for the missing
    // fields. The Python adapter (`rust_bridge_pyo3.py`) constructs the
    // flat array, so the contract is documented there.
    let weights = unsafe { std::slice::from_raw_parts(weights_ptr, 9) };
    let mut w = [0.0; 9];
    w.copy_from_slice(weights);

    let txs_flat = unsafe { std::slice::from_raw_parts(tx_ptr, tx_count * field_count) };
    let mut txs = Vec::with_capacity(tx_count);
    for i in 0..tx_count {
        let row = &txs_flat[i * field_count..(i + 1) * field_count];
        txs.push(TransactionData {
            tx_hash: format!("0x{i:064x}"),
            value_wei: row.get(0).copied().unwrap_or(0.0) as u128,
            gas_used: row.get(1).copied().unwrap_or(0.0) as u64,
            contract_addr: if row.get(4).copied().unwrap_or(0.0) > 0.5 {
                format!("0xPROTO{:040}", row.get(5).copied().unwrap_or(0.0) as u64)
            } else {
                String::new()
            },
            from_addr: format!("0x{:040}", row.get(6).copied().unwrap_or(0.0) as u64),
            to_addr: format!("0x{:040}", row.get(7).copied().unwrap_or(0.0) as u64),
            block_num: row.get(2).copied().unwrap_or(0.0) as u64,
            timestamp: row.get(3).copied().unwrap_or(0.0),
        });
    }
    rust_compute_phi(&txs, &w)
}

/// C-compatible shim for `compute_sigma` taking flat arrays of equal length.
///
/// # Safety
/// All three pointers must reference arrays of `count` `f64` values.
#[cfg(feature = "pyo3")]
#[no_mangle]
pub extern "C" fn trion_rust_compute_sigma(
    stakes_ptr: *const f64,
    diversity_ptr: *const f64,
    valuations_ptr: *const f64,
    count: usize,
    median: f64,
    delta_base: f64,
    volatility: f64,
) -> f64 {
    if stakes_ptr.is_null() || diversity_ptr.is_null() || valuations_ptr.is_null() || count == 0 {
        return crate::sigma::SIGMA_BOOTSTRAP;
    }
    let stakes = unsafe { std::slice::from_raw_parts(stakes_ptr, count) };
    let diversity = unsafe { std::slice::from_raw_parts(diversity_ptr, count) };
    let valuations = unsafe { std::slice::from_raw_parts(valuations_ptr, count) };
    rust_compute_sigma(stakes, diversity, valuations, median, delta_base, volatility)
}

/// C-compatible shim for `compute_master_equation`.
///
/// Returns the T(t) value directly, or `-1.0` when the gate is closed
/// (Python `None`). The sentinel `-1.0` is documented because T(t) is
/// always non-negative in the emit branch — `-1.0` is unambiguously the
/// SILENCE branch.
#[cfg(feature = "pyo3")]
#[no_mangle]
pub extern "C" fn trion_rust_compute_master_equation(
    c: f64,
    theta: f64,
    s: f64,
    moat: f64,
    time_years: f64,
) -> f64 {
    match master_equation(c, theta, s, moat, time_years) {
        Some(t) => t,
        None => -1.0,
    }
}

// ──────────────────────────────────────────────────────────────────────────
//  Signal Emitter — §14.2 24-type SignalType registry lookups
// ──────────────────────────────────────────────────────────────────────────
//
// Part 11 language mandate: the canonical 24-type SignalType registry lives
// in Rust (`signal_emitter::SignalType`) and in Python (`core.master.
// signal_factory.SignalType`). The two enums are parity-tested (see
// `signal_emitter::tests::test_names_match_python_registry` and
// `test_all_24_ids_round_trip`) — the ids 0–23 and the SCREAMING_SNAKE
// names are byte-identical across both implementations.
//
// The C ABI shims below expose the Rust name ↔ id resolution so the Python
// bridge (`core/rust_bridge_pyo3.py::signal_type_id_from_name_native` and
// `signal_type_name_from_id_native`) can call into the Rust lookup when
// the cdylib is loaded via ctypes. The shims activate on the next
// `cargo build --features pyo3`; the Python bridge already prefers the
// Rust path and falls back to the Python IntEnum (canonical source of
// truth) when the shims are not linked into the loaded .so.
//
// NOTE: these shims do NOT implement signal *emission* — the master-equation
// gate lives in `signal_emitter::SignalEmitter::emit` and is invoked from
// Python via `compute_master_equation_native` (the [C≥Θ]·S·e^(M·t) gate
// drives VALUATION vs SILENCE selection). The shims here expose only the
// name ↔ id resolution of the 24-type registry itself.

/// C-compatible shim: resolve a canonical signal-type name to its registry id.
///
/// `name_ptr` must point to a NUL-terminated UTF-8 string. Returns the
/// canonical id (0–23) when the name resolves, or `-1` when the name is
/// not a canonical 24-type member.
///
/// # Safety
/// `name_ptr` must point to a NUL-terminated readable byte sequence.
#[cfg(feature = "pyo3")]
#[no_mangle]
pub extern "C" fn trion_rust_signal_type_id_from_name(name_ptr: *const std::os::raw::c_char) -> i32 {
    if name_ptr.is_null() {
        return -1;
    }
    let c_str = unsafe { std::ffi::CStr::from_ptr(name_ptr) };
    let name = match c_str.to_str() {
        Ok(s) => s,
        Err(_) => return -1,
    };
    // The Rust enum uses SCREAMING_SNAKE names; accept either case to mirror
    // the Python `str(name).upper()` normalization.
    let name_upper = name.to_uppercase();
    // Linear scan over the 24-member registry — the registry is small and
    // the lookup is rare (once per emission classification), so a flat
    // scan is faster than a HashMap allocation for this size.
    for variant in crate::signal_emitter::ALL_SIGNAL_TYPES.iter() {
        if variant.name() == name_upper {
            return variant.id() as i32;
        }
    }
    -1
}

/// C-compatible shim: resolve a canonical signal-type id to its registry
/// name. Writes a NUL-terminated UTF-8 string into `out_buf` (at most
/// `buf_len - 1` bytes plus the NUL terminator). Returns 0 on success, or
/// -1 when the id is outside 0–23 or the buffer is too small.
///
/// # Safety
/// `out_buf` must point to at least `buf_len` writable bytes.
#[cfg(feature = "pyo3")]
#[no_mangle]
pub extern "C" fn trion_rust_signal_type_name_from_id(
    id: u8,
    out_buf: *mut std::os::raw::c_char,
    buf_len: usize,
) -> i32 {
    if out_buf.is_null() || buf_len == 0 {
        return -1;
    }
    let variant = match crate::signal_emitter::SignalType::from_id(id) {
        Some(v) => v,
        None => return -1,
    };
    let name = variant.name();
    // Need name.len() + 1 bytes (name + NUL terminator).
    if name.len() + 1 > buf_len {
        return -1;
    }
    unsafe {
        std::ptr::copy_nonoverlapping(name.as_ptr() as *const u8, out_buf as *mut u8, name.len());
        *out_buf.add(name.len()) = 0; // NUL terminator
    }
    0
}

// ──────────────────────────────────────────────────────────────────────────
//  ANIMA ML hot-path — ctypes C-shims for the 5 inference functions
// ──────────────────────────────────────────────────────────────────────────

/// C-compatible shim for `compute_anima_score`. Pure scalar call — no
/// pointer arguments, so the Python ctypes layer calls it directly with
/// `(c_double, c_double, c_double) -> c_double`.
#[cfg(feature = "pyo3")]
#[no_mangle]
pub extern "C" fn trion_rust_compute_anima_score(pcr: f64, ha: f64, ca: f64) -> f64 {
    rust_compute_anima_score(pcr, ha, ca)
}

/// C-compatible shim for `compute_archetype_similarity`. Accepts two flat
/// `f64` arrays of equal length; the caller is responsible for truncating
/// the longer one if lengths differ (mirrors the Rust trait of clamping
/// to min-length internally).
///
/// # Safety
/// Both pointers must reference arrays of at least `count` `f64` values.
#[cfg(feature = "pyo3")]
#[no_mangle]
pub extern "C" fn trion_rust_compute_archetype_similarity(
    entity_ptr: *const f64,
    archetype_ptr: *const f64,
    count: usize,
) -> f64 {
    if entity_ptr.is_null() || archetype_ptr.is_null() || count == 0 {
        return 0.0;
    }
    let entity = unsafe { std::slice::from_raw_parts(entity_ptr, count) };
    let archetype = unsafe { std::slice::from_raw_parts(archetype_ptr, count) };
    rust_compute_archetype_similarity(entity, archetype)
}

/// C-compatible shim for `compute_observer_effect`. Accepts two flat
/// `f64` arrays of equal length; the caller is responsible for
/// truncating if the two series have different lengths.
///
/// # Safety
/// Both pointers must reference arrays of at least `count` `f64` values.
#[cfg(feature = "pyo3")]
#[no_mangle]
pub extern "C" fn trion_rust_compute_observer_effect(
    pubs_ptr: *const f64,
    changes_ptr: *const f64,
    count: usize,
) -> f64 {
    if pubs_ptr.is_null() || changes_ptr.is_null() || count < 2 {
        return 0.0;
    }
    let pubs = unsafe { std::slice::from_raw_parts(pubs_ptr, count) };
    let changes = unsafe { std::slice::from_raw_parts(changes_ptr, count) };
    rust_compute_observer_effect(pubs, changes)
}

/// C-compatible shim for `compute_ci_95`. Writes the (ci_low, ci_high)
/// pair into the caller-supplied 2-element `out` buffer so the Python
/// ctypes layer can read both values without a heap allocation.
///
/// # Safety
/// `out_ptr` must point to 2 writable `f64` slots.
#[cfg(feature = "pyo3")]
#[no_mangle]
pub extern "C" fn trion_rust_compute_ci_95(
    mean: f64,
    std_dev: f64,
    n_samples: usize,
    out_ptr: *mut f64,
) -> i32 {
    if out_ptr.is_null() {
        return -1;
    }
    let (lo, hi) = rust_compute_ci_95(mean, std_dev, n_samples);
    unsafe {
        *out_ptr.add(0) = lo;
        *out_ptr.add(1) = hi;
    }
    0
}

/// C-compatible shim for `compute_probability_distribution`. Writes the
/// 4-tuple `(mean, std_dev, ci_low, ci_high)` into the caller-supplied
/// 4-element `out` buffer.
///
/// # Safety
/// `out_ptr` must point to 4 writable `f64` slots.
#[cfg(feature = "pyo3")]
#[no_mangle]
pub extern "C" fn trion_rust_compute_probability_distribution(
    scores_ptr: *const f64,
    count: usize,
    out_ptr: *mut f64,
) -> i32 {
    if scores_ptr.is_null() || out_ptr.is_null() {
        return -1;
    }
    let scores = unsafe { std::slice::from_raw_parts(scores_ptr, count) };
    let (mean, std_dev, lo, hi) = rust_compute_probability_distribution(scores);
    unsafe {
        *out_ptr.add(0) = mean;
        *out_ptr.add(1) = std_dev;
        *out_ptr.add(2) = lo;
        *out_ptr.add(3) = hi;
    }
    0
}

/// C-compatible shim for `compute_pattern_library_pcr`. Writes the
/// 3-tuple `(pcr, coherent_count, total_count)` into the caller-supplied
/// 3-element `out` buffer (count slots are `f64` for ABI portability —
/// integer counts are cast losslessly).
///
/// # Safety
/// `coherences_ptr` and `thresholds_ptr` must each point to `count`
/// `f64` values. `out_ptr` must point to 3 writable `f64` slots.
#[cfg(feature = "pyo3")]
#[no_mangle]
pub extern "C" fn trion_rust_compute_pattern_library_pcr(
    coherences_ptr: *const f64,
    thresholds_ptr: *const f64,
    count: usize,
    out_ptr: *mut f64,
) -> i32 {
    if coherences_ptr.is_null() || thresholds_ptr.is_null() || out_ptr.is_null() {
        return -1;
    }
    let coherences = unsafe { std::slice::from_raw_parts(coherences_ptr, count) };
    let thresholds = unsafe { std::slice::from_raw_parts(thresholds_ptr, count) };
    let (pcr, coherent, total) = rust_compute_pattern_library_pcr(coherences, thresholds);
    unsafe {
        *out_ptr.add(0) = pcr;
        *out_ptr.add(1) = coherent as f64;
        *out_ptr.add(2) = total as f64;
    }
    0
}

// ──────────────────────────────────────────────────────────────────────────
//  Living Security System — C-compatible ctypes shims
// ──────────────────────────────────────────────────────────────────────────

/// C-layout genomic-key result: two 64-char hex strings packed into
/// fixed 65-byte buffers (64 hex chars + NUL terminator). Documented for
/// callers that prefer a struct-based FFI; the
/// `trion_rust_compute_genomic_key` shim below uses raw out-pointers for
/// simplicity, but the layout here matches what that shim writes.
#[cfg(feature = "pyo3")]
#[repr(C)]
#[allow(dead_code)]
pub struct GenomicKeyHexResult {
    pub sense_hex: [u8; 65],
    pub antisense_hex: [u8; 65],
}

/// C-compatible shim for `compute_genomic_key_native`. Evolves a genomic
/// key one generation forward (or initialises the genesis key when
/// `generation == 0`) and writes the 64-char hex sense + antisense into
/// the caller-supplied buffers (each 65 bytes — NUL-terminated).
///
/// Returns 0 on success, negative on error.
///
/// # Safety
/// All four pointers must be non-null. `entity_id_ptr` must point to
/// `entity_id_len` readable bytes; `be_ptr`/`tm_ptr`/`cv_ptr` must point
/// to `be_len`/`tm_len`/`cv_len` readable bytes respectively. The two
/// out-buffers must each be at least 65 bytes writable.
#[cfg(feature = "pyo3")]
#[no_mangle]
pub extern "C" fn trion_rust_compute_genomic_key(
    entity_id_ptr: *const u8,
    entity_id_len: usize,
    generation: u64,
    be_ptr: *const u8,
    be_len: usize,
    tm_ptr: *const u8,
    tm_len: usize,
    cv_ptr: *const u8,
    cv_len: usize,
    out_sense_hex: *mut u8,
    out_antisense_hex: *mut u8,
) -> i32 {
    if entity_id_ptr.is_null()
        || be_ptr.is_null()
        || tm_ptr.is_null()
        || cv_ptr.is_null()
        || out_sense_hex.is_null()
        || out_antisense_hex.is_null()
    {
        return -1;
    }
    let entity_id_bytes = unsafe { std::slice::from_raw_parts(entity_id_ptr, entity_id_len) };
    let be = unsafe { std::slice::from_raw_parts(be_ptr, be_len) };
    let tm = unsafe { std::slice::from_raw_parts(tm_ptr, tm_len) };
    let cv = unsafe { std::slice::from_raw_parts(cv_ptr, cv_len) };
    let entity_id_str = match std::str::from_utf8(entity_id_bytes) {
        Ok(s) => s.to_string(),
        Err(_) => String::from_utf8_lossy(entity_id_bytes).into_owned(),
    };
    let (sense_hex, antisense_hex) =
        evolve_genomic_key_bytes(&entity_id_str, generation, be, tm, cv);
    if sense_hex.len() != 64 || antisense_hex.len() != 64 {
        return -2;
    }
    unsafe {
        std::ptr::copy_nonoverlapping(sense_hex.as_ptr(), out_sense_hex, 64);
        *out_sense_hex.add(64) = 0;
        std::ptr::copy_nonoverlapping(antisense_hex.as_ptr(), out_antisense_hex, 64);
        *out_antisense_hex.add(64) = 0;
    }
    0
}

/// C-compatible shim for `compute_sec_native`. Returns the bootstrap-
/// weighted effective SEC(t) ∈ [0, 1] as a plain f64.
///
/// # Safety
/// `entity_id_ptr` must point to `entity_id_len` readable bytes.
#[cfg(feature = "pyo3")]
#[no_mangle]
pub extern "C" fn trion_rust_compute_sec(
    entity_id_ptr: *const u8,
    entity_id_len: usize,
    akashic_depth: u64,
    n_chains: u64,
    n_validators: u64,
) -> f64 {
    if entity_id_ptr.is_null() {
        return 0.0;
    }
    let entity_id_bytes = unsafe { std::slice::from_raw_parts(entity_id_ptr, entity_id_len) };
    let entity_id_str = match std::str::from_utf8(entity_id_bytes) {
        Ok(s) => s.to_string(),
        Err(_) => String::from_utf8_lossy(entity_id_bytes).into_owned(),
    };
    rust_compute_sec_native(&entity_id_str, akashic_depth, n_chains, n_validators)
}

/// C-compatible shim for `crispr_check_native`. Returns 1 if any of the
/// 126 static CRISPR attack signatures matches as a substring of the
/// supplied transaction bytes, 0 otherwise.
///
/// # Safety
/// `tx_ptr` must point to `tx_len` readable bytes.
#[cfg(feature = "pyo3")]
#[no_mangle]
pub extern "C" fn trion_rust_crispr_check(
    tx_ptr: *const u8,
    tx_len: usize,
) -> i32 {
    if tx_ptr.is_null() {
        return 0;
    }
    let tx = unsafe { std::slice::from_raw_parts(tx_ptr, tx_len) };
    if CRISPRDefense::innate_check(tx).is_some() {
        1
    } else {
        0
    }
}

/// C-compatible shim for `lss_hash_dna`. Writes the 32-byte sense and
/// antisense digests into the caller-supplied buffers.
///
/// # Safety
/// `payload_ptr` must point to `len` readable bytes; `out_sense` and
/// `out_antisense` must each point to 32 writable bytes.
#[cfg(feature = "pyo3")]
#[no_mangle]
pub extern "C" fn trion_rust_lss_hash_dna(
    payload_ptr: *const u8,
    len: usize,
    out_sense: *mut u8,
    out_antisense: *mut u8,
) -> i32 {
    if payload_ptr.is_null() || out_sense.is_null() || out_antisense.is_null() {
        return -1;
    }
    let payload = unsafe { std::slice::from_raw_parts(payload_ptr, len) };
    let (sense, antisense) = rust_hash_dna(payload);
    unsafe {
        std::ptr::copy_nonoverlapping(sense.as_ptr(), out_sense, 32);
        std::ptr::copy_nonoverlapping(antisense.as_ptr(), out_antisense, 32);
    }
    0
}

#[cfg(all(test, feature = "pyo3"))]
mod tests {
    use super::*;

    #[test]
    fn test_behavioral_hash_matches_python_golden_shape() {
        // Golden shape from CANONICAL_BH.md: empty payload → known digests.
        // We don't assert exact bytes here (those are golden-vector tested
        // elsewhere); we just verify the antisense strand matches the
        // XOR-NOT construction.
        let payload = b"trion test payload";
        let (sense, antisense) = behavioral_hash(payload);

        // Recompute the antisense directly to verify the construction.
        let mut pff = Vec::with_capacity(payload.len() + 1);
        pff.extend_from_slice(payload);
        pff.push(0xFF);
        let sha3ff: [u8; 32] = Sha3_256::digest(&pff).into();
        for i in 0..32 {
            assert_eq!(antisense[i], sha3ff[i] ^ !sense[i]);
        }
    }

    #[test]
    fn test_py_compute_phi_returns_unit_interval() {
        // We can't easily construct PyRef<TransactionData> without a
        // Python interpreter, so we exercise the underlying math via the
        // C shim instead — it goes through the same `rust_compute_phi`.
        let tx = [1e18_f64, 21000.0, 1.0, 1700000000.0, 0.0, 0.0, 0.0, 0.0];
        let weights = [0.15_f64, 0.15, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10];
        let phi = trion_rust_compute_phi_flat(tx.as_ptr(), 1, 8, weights.as_ptr());
        assert!(phi >= 0.0 && phi <= 1.0, "phi out of range: {phi}");
    }

    #[test]
    fn test_extern_c_master_equation_silence_branch() {
        // C < Θ → SILENCE → sentinel -1.0.
        let t = trion_rust_compute_master_equation(0.40, 0.90, 0.40, 1.0, 1.0);
        assert_eq!(t, -1.0);
    }

    #[test]
    fn test_lss_hash_dna_extern_c_writes_strands() {
        let payload = b"lss test payload";
        let mut sense = [0u8; 32];
        let mut antisense = [0u8; 32];
        let rc = trion_rust_lss_hash_dna(payload.as_ptr(), payload.len(), sense.as_mut_ptr(), antisense.as_mut_ptr());
        assert_eq!(rc, 0);
        // Verify the antisense XOR-NOT invariant.
        let mut pff = Vec::with_capacity(payload.len() + 1);
        pff.extend_from_slice(payload);
        pff.push(0xFF);
        let sha3ff: [u8; 32] = Sha3_256::digest(&pff).into();
        for i in 0..32 {
            assert_eq!(antisense[i], sha3ff[i] ^ !sense[i]);
        }
    }

    #[test]
    fn test_crispr_check_extern_c_matches_signature() {
        let tx = b"prefix_HARVEST_FLASH_LOAN_ORACLE_MANIP_suffix";
        let hit = trion_rust_crispr_check(tx.as_ptr(), tx.len());
        assert_eq!(hit, 1, "expected CRISPR match on Harvest signature");
        let clean = b"clean transaction data";
        let miss = trion_rust_crispr_check(clean.as_ptr(), clean.len());
        assert_eq!(miss, 0);
    }

    #[test]
    fn test_compute_sec_extern_c_returns_unit_interval() {
        let eid = b"uniswap_v3";
        let sec = trion_rust_compute_sec(eid.as_ptr(), eid.len(), 1000, 31, 100);
        assert!(sec > 0.0 && sec <= 1.0, "sec out of range: {sec}");
    }

    #[test]
    fn test_compute_genomic_key_extern_c_writes_hex() {
        let eid = b"test_entity";
        let be = b"behavioral_event";
        let tm = b"timestamp";
        let cv = b"context";
        let mut sense_hex = [0u8; 65];
        let mut antisense_hex = [0u8; 65];
        let rc = trion_rust_compute_genomic_key(
            eid.as_ptr(), eid.len(), 1,
            be.as_ptr(), be.len(),
            tm.as_ptr(), tm.len(),
            cv.as_ptr(), cv.len(),
            sense_hex.as_mut_ptr(), antisense_hex.as_mut_ptr(),
        );
        assert_eq!(rc, 0);
        let s = std::str::from_utf8(&sense_hex[..64]).unwrap();
        let a = std::str::from_utf8(&antisense_hex[..64]).unwrap();
        assert_eq!(s.len(), 64);
        assert_eq!(a.len(), 64);
        assert!(s.chars().all(|c| c.is_ascii_hexdigit()));
        assert!(a.chars().all(|c| c.is_ascii_hexdigit()));
    }
}

// ── From<PyTransactionData> for TransactionData ─────────────────────────────
// Required by the compute_phi_native wrapper which maps a list of
// PyTransactionData (Python-visible) to Vec<TransactionData> (Rust-internal).

#[cfg(feature = "pyo3")]
impl From<&PyRef<'_, PyTransactionData>> for TransactionData {
    fn from(py: &PyRef<'_, PyTransactionData>) -> Self {
        TransactionData {
            tx_hash:      py.tx_hash.clone(),
            value_wei:     py.value_wei,
            gas_used:      py.gas_used,
            contract_addr: py.contract_addr.clone(),
            from_addr:     py.from_addr.clone(),
            to_addr:       py.to_addr.clone(),
            block_num:     py.block_num,
            timestamp:     py.timestamp,
        }
    }
}
