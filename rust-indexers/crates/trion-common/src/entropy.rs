/*!
 * Shannon entropy helpers — whitepaper L1.1 Φ(t) feature extraction.
 *
 * All entropy values are normalised to [0, 1] by dividing by log₂(k)
 * where k is the number of non-zero probability bins.
 */

/// Normalised Shannon entropy over a frequency count vector.
/// Returns 0.0 when the total count is zero or there is only one category.
pub fn shannon_entropy(counts: &[u64]) -> f64 {
    let total: u64 = counts.iter().sum();
    if total == 0 {
        return 0.0;
    }
    let total_f = total as f64;
    let non_zero: Vec<f64> = counts
        .iter()
        .filter(|&&c| c > 0)
        .map(|&c| c as f64 / total_f)
        .collect();
    if non_zero.len() <= 1 {
        return 0.0;
    }
    let h: f64 = -non_zero.iter().map(|&p| p * p.log2()).sum::<f64>();
    let max_h = (non_zero.len() as f64).log2();
    if max_h > 0.0 { (h / max_h).clamp(0.0, 1.0) } else { 0.0 }
}

/// Build a fixed-width histogram from a slice of f64 values then compute entropy.
/// Returns 0.0 when values is empty.
pub fn histogram_entropy(values: &[f64], bins: usize) -> f64 {
    if values.is_empty() || bins == 0 {
        return 0.0;
    }
    let min = values.iter().cloned().fold(f64::INFINITY, f64::min);
    let max = values.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    let range = if (max - min).abs() < f64::EPSILON { 1.0 } else { max - min };
    let mut hist = vec![0u64; bins];
    for &v in values {
        let idx = ((v - min) / range * bins as f64) as usize;
        let idx = idx.min(bins - 1);
        hist[idx] += 1;
    }
    shannon_entropy(&hist)
}

/// Frequency-map entropy over string labels.
pub fn freq_entropy(labels: &[impl AsRef<str>]) -> f64 {
    if labels.is_empty() {
        return 0.0;
    }
    let mut freq: std::collections::HashMap<&str, u64> = std::collections::HashMap::new();
    for l in labels {
        *freq.entry(l.as_ref()).or_insert(0) += 1;
    }
    let counts: Vec<u64> = freq.values().cloned().collect();
    shannon_entropy(&counts)
}

/// Entropy of a ratio (e.g. success/total).  Returns binary entropy H(p).
pub fn ratio_entropy(numerator: u64, total: u64) -> f64 {
    if total == 0 { return 0.0; }
    shannon_entropy(&[numerator, total.saturating_sub(numerator)])
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn uniform_is_one() {
        assert!((shannon_entropy(&[1, 1, 1, 1]) - 1.0).abs() < 1e-9);
    }

    #[test]
    fn single_bin_is_zero() {
        assert_eq!(shannon_entropy(&[100, 0, 0]), 0.0);
    }

    #[test]
    fn empty_is_zero() {
        assert_eq!(shannon_entropy(&[]), 0.0);
        assert_eq!(histogram_entropy(&[], 8), 0.0);
        let empty_strings: Vec<String> = vec![];
        assert_eq!(freq_entropy(&empty_strings), 0.0);
    }

    #[test]
    fn histogram_clamps_to_one() {
        let vals: Vec<f64> = (0..100).map(|i| i as f64).collect();
        let h = histogram_entropy(&vals, 10);
        assert!(h >= 0.0 && h <= 1.0);
    }
}
