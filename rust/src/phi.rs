//! phi.rs — L1.1 Physical Richness Score Φ (standalone Rust module)
//!
//! TRION specification §L1.1:
//!
//! ```text
//! Φ(t) = (1/N) · Σ_i [ w_i · H(f_i(t)) ]      (N = number of features = 9)
//! ```
//!
//! `w_i` is a feature-importance weight, learned from Akashic history
//! (`learn_weights_from_history`) — NOT a hand-picked constant in the
//! spec-compliant path. The legacy fixed weights `PHI_WEIGHTS` are
//! retained as a backward-compatible cold-start fallback (mirroring
//! `core/physical/phi_engine.py::PHI_WEIGHTS`).
//!
//! This is a port of the canonical Python reference
//! (`core/physical/phi_engine.py`) so the PyO3 binding layer and the
//! Python engine share the exact same 9 Shannon-entropy feature
//! definitions. Cross-language golden vectors in
//! `tests/unit/test_feature_extractor.py` must produce identical
//! feature values for identical transaction windows.
//!
//! All 9 features:
//!   f1: Volume entropy            (10-bucket histogram of value_wei)
//!   f2: Counterparty diversity    (entropy of `to_addr` distribution)
//!   f3: Temporal spacing          (10-bucket histogram of inter-tx gaps)
//!   f4: Smart-contract entropy    (entropy of contract_addr distribution)
//!   f5: Value-flow directionality (entropy of received vs sent)
//!   f6: Wallet architecture       (entropy of EOA vs contract usage)
//!   f7: Cross-protocol            (entropy of contract-prefix buckets)
//!   f8: Gas pattern               (10-bucket histogram of gas_used)
//!   f9: MEV interaction           (5-category entropy heuristic)

use std::collections::HashMap;

/// Number of Φ features (f1..f9).
pub const N_FEATURES: usize = 9;

/// Legacy fixed weights — cold-start fallback only (matches
/// `PHI_WEIGHTS` in `core/physical/phi_engine.py`). The spec-compliant
/// path learns the weights from Akashic history via
/// `learn_weights_from_history`.
pub const PHI_WEIGHTS: [f64; N_FEATURES] = [
    0.15, 0.15, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10,
];

/// A single behavioural transaction record. Mirrors the Python
/// `TransactionData` dataclass so the PyO3 adapter
/// (`rust/src/pyo3_bindings.rs::PyTransactionData`) can pass records
/// straight from the indexer / FAISS adapter without translation.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct TransactionData {
    /// Canonical transaction hash (0x…), used by f4/f7 to derive protocol buckets.
    pub tx_hash: String,
    /// Value transferred, in wei. Used by f1 (volume histogram) and f5 (flow).
    pub value_wei: u128,
    /// Gas consumed by the tx. Used by f8 (gas pattern histogram).
    pub gas_used: u64,
    /// Contract invoked (if any). Used by f4 and f7; empty for plain EOA transfers.
    pub contract_addr: String,
    /// Sender address. Used by f5 (sent volume) and f6 (wallet architecture).
    pub from_addr: String,
    /// Recipient address. Used by f2 (counterparty diversity) and f5 (received volume).
    pub to_addr: String,
    /// Block height. Used as the canonical ordering tiebreaker.
    pub block_num: u64,
    /// Unix-seconds timestamp. Used by f3 (inter-tx gap histogram).
    pub timestamp: f64,
}

impl TransactionData {
    /// True when this record represents a smart-contract call (non-empty
    /// `contract_addr`). Mirrors `is_contract=True` on the Python side.
    pub fn is_contract(&self) -> bool {
        !self.contract_addr.is_empty()
    }
}

/// Shannon entropy (base-2) of a discrete distribution given as a
/// frequency slice. Matches `shannon_entropy` in
/// `core/physical/phi_engine.py`.
pub fn shannon_entropy(values: &[f64]) -> f64 {
    let total: f64 = values.iter().copied().sum();
    if values.is_empty() || total <= 0.0 {
        return 0.0;
    }
    let mut h = 0.0;
    for &v in values {
        if v <= 0.0 {
            continue;
        }
        let p = v / total;
        h -= p * p.log2();
    }
    h
}

/// Normalize an entropy value to [0, 1] by dividing by log2(n). Mirrors
/// `normalize_entropy` in `core/physical/phi_engine.py`.
pub fn normalize_entropy(h: f64, n: usize) -> f64 {
    if n <= 1 {
        return 0.0;
    }
    let max_h = (n as f64).log2();
    if max_h <= 0.0 {
        return 0.0;
    }
    (h / max_h).min(1.0)
}

/// Histogram a slice of non-negative values into `n_buckets` bins
/// between 0 and `max_val`. Used by f1, f3, and f8.
fn histogram(values: &[f64], n_buckets: usize) -> Vec<f64> {
    let mut buckets = vec![0u64; n_buckets];
    if values.is_empty() {
        return buckets.iter().map(|&c| c as f64).collect();
    }
    let max_val = values.iter().copied().fold(0.0_f64, f64::max);
    if max_val == 0.0 {
        return buckets.iter().map(|&c| c as f64).collect();
    }
    for &v in values {
        let idx = ((v / max_val) * (n_buckets as f64)).floor() as usize;
        let idx = idx.min(n_buckets - 1);
        buckets[idx] += 1;
    }
    buckets.iter().map(|&c| c as f64).collect()
}

/// f1: Shannon entropy of transaction-volume distribution (10 buckets).
pub fn compute_f1_volume_entropy(txs: &[TransactionData]) -> f64 {
    if txs.is_empty() {
        return 0.0;
    }
    let values: Vec<f64> = txs.iter().map(|t| t.value_wei as f64).filter(|v| *v > 0.0).collect();
    if values.is_empty() {
        return 0.0;
    }
    let buckets = histogram(&values, 10);
    let h = shannon_entropy(&buckets);
    normalize_entropy(h, 10)
}

/// f2: Shannon entropy of counterparty (`to_addr`) addresses.
pub fn compute_f2_counterparty_diversity(txs: &[TransactionData]) -> f64 {
    if txs.is_empty() {
        return 0.0;
    }
    let mut counts: HashMap<&str, u64> = HashMap::new();
    for t in txs {
        *counts.entry(t.to_addr.as_str()).or_insert(0) += 1;
    }
    if counts.is_empty() {
        return 0.0;
    }
    let freqs: Vec<f64> = counts.values().map(|c| *c as f64).collect();
    let h = shannon_entropy(&freqs);
    normalize_entropy(h, counts.len())
}

/// f3: Shannon entropy of inter-transaction time gaps (run-length, 10 buckets).
pub fn compute_f3_temporal_spacing(txs: &[TransactionData]) -> f64 {
    if txs.len() < 2 {
        return 0.0;
    }
    let mut ts: Vec<f64> = txs.iter().map(|t| t.timestamp).collect();
    ts.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    let mut gaps: Vec<f64> = Vec::with_capacity(ts.len().saturating_sub(1));
    for i in 1..ts.len() {
        gaps.push(ts[i] - ts[i - 1]);
    }
    if gaps.is_empty() {
        return 0.0;
    }
    let max_gap = gaps.iter().copied().fold(0.0_f64, f64::max);
    if max_gap == 0.0 {
        return 0.0;
    }
    let buckets = histogram(&gaps, 10);
    let h = shannon_entropy(&buckets);
    normalize_entropy(h, 10)
}

/// f4: Shannon entropy of smart-contract interaction distribution.
pub fn compute_f4_contract_entropy(txs: &[TransactionData]) -> f64 {
    if txs.is_empty() {
        return 0.0;
    }
    let contract_txs: Vec<&TransactionData> = txs.iter().filter(|t| t.is_contract()).collect();
    if contract_txs.is_empty() {
        return 0.0;
    }
    let mut counts: HashMap<&str, u64> = HashMap::new();
    for t in &contract_txs {
        *counts.entry(t.contract_addr.as_str()).or_insert(0) += 1;
    }
    if counts.is_empty() {
        return 0.0;
    }
    let freqs: Vec<f64> = counts.values().map(|c| *c as f64).collect();
    let h = shannon_entropy(&freqs);
    normalize_entropy(h, counts.len())
}

/// f5: Value-flow directionality entropy (received vs sent for `entity_addr`).
///
/// `entity_addr` is the canonical address of the entity being scored; it
/// is matched case-insensitively against `from_addr` and `to_addr` on
/// each tx, matching the Python reference.
pub fn compute_f5_value_flow(txs: &[TransactionData], entity_addr: &str) -> f64 {
    if txs.is_empty() {
        return 0.0;
    }
    let entity_lc = entity_addr.to_lowercase();
    let mut received: f64 = 0.0;
    let mut sent: f64 = 0.0;
    for t in txs {
        if t.to_addr.to_lowercase() == entity_lc {
            received += t.value_wei as f64;
        }
        if t.from_addr.to_lowercase() == entity_lc {
            sent += t.value_wei as f64;
        }
    }
    if received + sent == 0.0 {
        return 0.0;
    }
    if received <= 0.0 || sent <= 0.0 {
        return 0.0;
    }
    // Shannon entropy over the 2-element distribution [received, sent].
    shannon_entropy(&[received, sent])
}

/// f6: Wallet architecture entropy (EOA vs contract usage).
pub fn compute_f6_wallet_architecture(txs: &[TransactionData]) -> f64 {
    if txs.is_empty() {
        return 0.0;
    }
    let contract_count = txs.iter().filter(|t| t.is_contract()).count();
    let eoa_count = txs.len().saturating_sub(contract_count);
    let h = shannon_entropy(&[eoa_count as f64, contract_count as f64]);
    normalize_entropy(h, 2)
}

/// f7: Cross-protocol interaction entropy (6-char contract-address prefix
/// or "EOA" for plain transfers).
pub fn compute_f7_cross_protocol(txs: &[TransactionData]) -> f64 {
    if txs.is_empty() {
        return 0.0;
    }
    let mut counts: HashMap<String, u64> = HashMap::new();
    for t in txs {
        let key = if t.is_contract() {
            t.contract_addr.chars().take(6).collect::<String>()
        } else {
            "EOA".to_string()
        };
        *counts.entry(key).or_insert(0) += 1;
    }
    if counts.is_empty() {
        return 0.0;
    }
    let freqs: Vec<f64> = counts.values().map(|c| *c as f64).collect();
    let h = shannon_entropy(&freqs);
    normalize_entropy(h, counts.len())
}

/// f8: Gas-usage pattern entropy (10-bucket histogram of `gas_used`).
pub fn compute_f8_gas_pattern(txs: &[TransactionData]) -> f64 {
    if txs.is_empty() {
        return 0.0;
    }
    let values: Vec<f64> = txs.iter().map(|t| t.gas_used as f64).filter(|v| *v > 0.0).collect();
    if values.is_empty() {
        return 0.0;
    }
    let buckets = histogram(&values, 10);
    let h = shannon_entropy(&buckets);
    normalize_entropy(h, 10)
}

/// f9: MEV-interaction entropy (5-category heuristic — same construction
/// as `compute_f9_mev_interaction` in the Python reference).
pub fn compute_f9_mev_interaction(txs: &[TransactionData]) -> f64 {
    if txs.is_empty() {
        return 0.0;
    }
    // Heuristic: zero-value contract calls with long inputs suggest MEV activity.
    // The Python side uses `input_len > 100`; here we approximate input_len by
    // the length of the contract_addr (a stand-in since TransactionData does not
    // carry a dedicated input_len field in the Rust port).
    let mev_like = txs
        .iter()
        .filter(|t| t.is_contract() && t.value_wei == 0 && t.contract_addr.len() > 8)
        .count();
    let total = txs.len();
    if total == 0 {
        return 0.0;
    }
    let ratio = mev_like as f64 / total as f64;
    let cats = [
        (ratio * 0.3).max(0.01),
        (ratio * 0.2).max(0.01),
        (ratio * 0.2).max(0.01),
        (ratio * 0.1).max(0.01),
        (1.0 - ratio).max(0.01),
    ];
    let h = shannon_entropy(&cats);
    normalize_entropy(h, 5)
}

/// Extract all 9 features from a transaction window and return them as a
/// length-9 vector `[f1, f2, ..., f9]` (in spec order).
pub fn extract_features(txs: &[TransactionData], entity_addr: &str) -> [f64; N_FEATURES] {
    [
        compute_f1_volume_entropy(txs),
        compute_f2_counterparty_diversity(txs),
        compute_f3_temporal_spacing(txs),
        compute_f4_contract_entropy(txs),
        compute_f5_value_flow(txs, entity_addr),
        compute_f6_wallet_architecture(txs),
        compute_f7_cross_protocol(txs),
        compute_f8_gas_pattern(txs),
        compute_f9_mev_interaction(txs),
    ]
}

/// Compute the Physical Richness Score Φ(t).
///
/// Inputs
/// ------
/// `transactions` : the entity's transaction window for the current epoch.
/// `weights`      : length-9 array of feature-importance weights. The
///                  spec-compliant path learns these from Akashic history
///                  via `learn_weights_from_history`; the cold-start
///                  fallback is `PHI_WEIGHTS`. Weights are L1-normalized
///                  to sum to 1.0 so Φ stays in [0, 1] regardless of scale.
///
/// Output
/// ------
/// Φ(t) = Σ_i w_i · f_i, clamped to [0, 1].
pub fn compute_phi(transactions: &[TransactionData], weights: &[f64; N_FEATURES]) -> f64 {
    if transactions.is_empty() {
        return 0.0;
    }
    // The entity address is recovered from the most-frequent from_addr;
    // when no transactions are present we already returned 0.0 above.
    let mut counter: HashMap<&str, u64> = HashMap::new();
    for t in transactions {
        *counter.entry(t.from_addr.as_str()).or_insert(0) += 1;
    }
    let entity_addr = counter
        .iter()
        .max_by_key(|(_, v)| **v)
        .map(|(k, _)| *k)
        .unwrap_or("");

    let features = extract_features(transactions, entity_addr);

    // L1-normalize weights so Σ w_i = 1 (spec form). Falls back to the
    // legacy PHI_WEIGHTS when the caller passes a zero vector.
    let total: f64 = weights.iter().copied().sum();
    let w: [f64; N_FEATURES] = if total <= 0.0 || !total.is_finite() {
        PHI_WEIGHTS
    } else {
        let mut out = [0.0; N_FEATURES];
        for i in 0..N_FEATURES {
            out[i] = weights[i] / total;
        }
        out
    };

    let phi = (0..N_FEATURES).map(|i| w[i] * features[i]).sum::<f64>();
    phi.clamp(0.0, 1.0)
}

/// Learn the L1.1 Φ feature-importance weights `w` from Akashic history
/// (spec: "w = feature importance weight (learned from Akashic history,
/// not fixed)").
///
/// Inputs
/// ------
/// `features` : (n_samples, 9) matrix of historical f1..f9 observations.
/// `outcomes` : (n_samples,) vector of historical targets the Φ score is
///              meant to predict — typically a realized post-hoc Phi or a
///              binary manipulation label.
///
/// Returns
/// -------
/// A length-9 array of non-negative weights summing to 1.0.
///
/// Method
/// ------
/// Spec-preferred path is mutual information; without an external MI
/// estimator in the Rust stdlib we fall back to the |Pearson r| correlation
/// between each feature column and the target outcome — the same fallback
/// the Python reference uses when `sklearn.feature_selection.mutual_info_regression`
/// is unavailable (`core/physical/phi_engine.py::learn_weights_from_history`).
pub fn learn_weights_from_history(features: &Vec<Vec<f64>>, outcomes: &Vec<f64>) -> [f64; N_FEATURES] {
    let fallback = normalize_weights(&PHI_WEIGHTS);

    let n_samples = features.len();
    if n_samples < 2 || outcomes.len() != n_samples {
        return fallback;
    }

    // Build a (n, 9) matrix; reject malformed rows.
    let mut matrix: Vec<[f64; N_FEATURES]> = Vec::with_capacity(n_samples);
    for row in features {
        if row.len() != N_FEATURES {
            return fallback;
        }
        let mut r = [0.0; N_FEATURES];
        r.copy_from_slice(row);
        matrix.push(r);
    }

    // Outcome statistics — if variance is zero we cannot learn anything.
    let mean_y: f64 = outcomes.iter().copied().sum::<f64>() / n_samples as f64;
    let var_y: f64 =
        outcomes.iter().map(|y| (y - mean_y).powi(2)).sum::<f64>() / n_samples as f64;
    if var_y <= 0.0 || !var_y.is_finite() {
        return fallback;
    }

    // |Pearson r| per column.
    let mut importances = [0.0; N_FEATURES];
    for j in 0..N_FEATURES {
        let col: Vec<f64> = matrix.iter().map(|r| r[j]).collect();
        let mean_x: f64 = col.iter().copied().sum::<f64>() / n_samples as f64;
        let var_x: f64 = col.iter().map(|x| (x - mean_x).powi(2)).sum::<f64>() / n_samples as f64;
        if var_x <= 0.0 || !var_x.is_finite() {
            importances[j] = 0.0;
            continue;
        }
        let cov: f64 = (0..n_samples)
            .map(|i| (col[i] - mean_x) * (outcomes[i] - mean_y))
            .sum::<f64>()
            / n_samples as f64;
        let r = cov / (var_x.sqrt() * var_y.sqrt());
        importances[j] = r.abs();
    }

    let total: f64 = importances.iter().copied().sum();
    if !total.is_finite() || total <= 0.0 {
        return fallback;
    }
    let mut w = [0.0; N_FEATURES];
    for j in 0..N_FEATURES {
        w[j] = importances[j] / total;
    }
    w
}

fn normalize_weights(w: &[f64; N_FEATURES]) -> [f64; N_FEATURES] {
    let total: f64 = w.iter().copied().sum();
    if total <= 0.0 || !total.is_finite() {
        let mut out = [0.0; N_FEATURES];
        out.iter_mut().for_each(|v| *v = 1.0 / N_FEATURES as f64);
        return out;
    }
    let mut out = [0.0; N_FEATURES];
    for i in 0..N_FEATURES {
        out[i] = w[i] / total;
    }
    out
}

/// Tiny frequency-counter helper used by `compute_phi` to recover the
/// entity address when it is not separately provided. Kept private to
/// this module so the public surface matches the spec's `compute_phi`
/// signature.
#[allow(dead_code)]
mod counter {
    use std::collections::HashMap;
    pub struct Counter {
        counts: HashMap<String, u64>,
    }
    impl Counter {
        pub fn new() -> Self {
            Self { counts: HashMap::new() }
        }
        pub fn most_frequent(&self) -> Option<&str> {
            self.counts
                .iter()
                .max_by_key(|(_, v)| **v)
                .map(|(k, _)| k.as_str())
        }
    }
    impl<'a> FromIterator<&'a str> for Counter {
        fn from_iter<I: IntoIterator<Item = &'a str>>(iter: I) -> Self {
            let mut c = Counter::new();
            for s in iter {
                *c.counts.entry(s.to_string()).or_insert(0) += 1;
            }
            c
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_txs() -> Vec<TransactionData> {
        (0..20)
            .map(|i| TransactionData {
                tx_hash: format!("0x{i:064x}"),
                value_wei: (10u128.pow(17)) * (i as u128 + 1),
                gas_used: 21000 + i as u64 * 1000,
                contract_addr: if i % 3 == 0 {
                    format!("0xPROTO{i:040}")
                } else {
                    String::new()
                },
                from_addr: "0xUSER".to_string(),
                to_addr: format!("0x{:040}", i % 10),
                block_num: 18_000_000 + i as u64,
                timestamp: 1_700_000_000.0 + (i as f64) * 3600.0,
            })
            .collect()
    }

    #[test]
    fn test_shannon_entropy_basic() {
        // Uniform distribution over 4 symbols → entropy = log2(4) = 2.0
        assert!((shannon_entropy(&[1.0, 1.0, 1.0, 1.0]) - 2.0).abs() < 1e-9);
        // Single symbol → entropy = 0
        assert_eq!(shannon_entropy(&[1.0]), 0.0);
        // Empty → 0
        assert_eq!(shannon_entropy(&[]), 0.0);
    }

    #[test]
    fn test_normalize_entropy_clamps_to_unit_interval() {
        assert_eq!(normalize_entropy(0.0, 10), 0.0);
        assert!((normalize_entropy(2.0, 4) - 1.0).abs() < 1e-12); // log2(4)=2 → 2/2 = 1
        assert_eq!(normalize_entropy(10.0, 10), 1.0); // clamped
        assert_eq!(normalize_entropy(1.0, 1), 0.0); // degenerate
    }

    #[test]
    fn test_extract_features_returns_nine() {
        let txs = sample_txs();
        let features = extract_features(&txs, "0xUSER");
        assert_eq!(features.len(), N_FEATURES);
        for f in features.iter() {
            assert!(*f >= 0.0 && *f <= 1.0, "feature out of [0,1]: {f}");
        }
    }

    #[test]
    fn test_compute_phi_in_unit_interval() {
        let txs = sample_txs();
        let phi = compute_phi(&txs, &PHI_WEIGHTS);
        assert!(phi >= 0.0 && phi <= 1.0, "Φ out of [0,1]: {phi}");
    }

    #[test]
    fn test_compute_phi_empty_returns_zero() {
        assert_eq!(compute_phi(&[], &PHI_WEIGHTS), 0.0);
    }

    #[test]
    fn test_learn_weights_fallback_on_empty_input() {
        let w = learn_weights_from_history(&Vec::new(), &Vec::new());
        assert_eq!(w.len(), N_FEATURES);
        assert!((w.iter().sum::<f64>() - 1.0).abs() < 1e-9);
        // The fallback should equal the normalized PHI_WEIGHTS.
        let expected = normalize_weights(&PHI_WEIGHTS);
        for i in 0..N_FEATURES {
            assert!((w[i] - expected[i]).abs() < 1e-9);
        }
    }

    #[test]
    fn test_learn_weights_assigns_largest_weight_to_correlated_feature() {
        // Synthesize a dataset where f1 is the only feature correlated with
        // the outcome; f1 should receive the largest weight (mirrors the
        // Python `learn_weights_from_history` golden case).
        let mut features: Vec<Vec<f64>> = Vec::with_capacity(60);
        let mut outcomes: Vec<f64> = Vec::with_capacity(60);
        // Deterministic LCG for reproducibility (no test-only RNG deps).
        let mut state: u64 = 0x1234_5678_9abc_def0;
        let lcg = |state: &mut u64| -> f64 {
            *state = state.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
            let top = (*state >> 33) as u32;
            (top as f64) / (u32::MAX as f64)
        };
        for _ in 0..60 {
            let f1_v = lcg(&mut state);
            let mut row = vec![f1_v];
            for _ in 0..8 {
                row.push(lcg(&mut state));
            }
            features.push(row);
            // Outcome tracks f1 + small deterministic perturbation.
            outcomes.push(f1_v + 0.05 * (lcg(&mut state) - 0.5));
        }
        let w = learn_weights_from_history(&features, &outcomes);
        assert_eq!(w.len(), N_FEATURES);
        assert!((w.iter().sum::<f64>() - 1.0).abs() < 1e-9);
        let max_w = w.iter().copied().fold(0.0_f64, f64::max);
        assert!(
            (w[0] - max_w).abs() < 1e-9,
            "f1 should be the most important feature, got weights = {w:?}"
        );
    }
}
