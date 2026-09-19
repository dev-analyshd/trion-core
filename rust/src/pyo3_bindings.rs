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
    // Expose module-level constants so the Python side can sanity-check
    // the build (used by core/rust_bridge_pyo3.py).
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add("SUPPORTED_FEATURES", ["bh", "phi", "sigma", "master_equation"])?;
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
