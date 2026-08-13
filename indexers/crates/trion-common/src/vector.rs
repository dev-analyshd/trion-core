/*!
 * 128-dimensional behavioral vector construction.
 *
 * Layout (whitepaper L1.1):
 *   [0..9]   — 9 normalised Shannon entropy features f1…f9
 *   [9..18]  — mirrored f1…f9 (complementary strand, L4.4 dual-strand)
 *   [18..27] — pairwise products f_i * f_{i+1} (cross-correlations)
 *   [27]     — mean(f1..f9)
 *   [28]     — std-dev(f1..f9)
 *   [29]     — min(f1..f9)
 *   [30]     — max(f1..f9)
 *   [31..64] — deterministic SHA3-256 noise seeded by (entity_id, block_num)
 *   [64..128] — zeros (reserved for future planes / ephemeral state)
 *
 * The SHA3 noise provides stable entity-level "genomic" variation while
 * keeping feature dimensions orthogonal across different block windows.
 */

use sha3::{Digest, Sha3_256};

/// Build a 128-dim f32 vector from exactly 9 entropy features plus a seed.
///
/// `seed` should uniquely identify the (chain, block, entity) tuple so that
/// the deterministic noise region is stable across replays.
pub fn build_vector(features: &[f64; 9], seed: &str) -> Vec<f32> {
    let mut v = vec![0f32; 128];

    // ── region [0..9]: raw features ──────────────────────────────────────────
    for (i, &f) in features.iter().enumerate() {
        v[i] = f.clamp(0.0, 1.0) as f32;
    }

    // ── region [9..18]: complementary strand (1 - f_i) ───────────────────────
    for i in 0..9 {
        v[9 + i] = 1.0 - v[i];
    }

    // ── region [18..27]: cross-correlation f_i * f_{i+1} ─────────────────────
    for i in 0..8 {
        v[18 + i] = v[i] * v[i + 1];
    }
    v[26] = v[8] * v[0]; // wrap-around

    // ── region [27..31]: aggregate statistics ────────────────────────────────
    let mean = features.iter().sum::<f64>() / 9.0;
    let variance = features.iter().map(|&f| (f - mean).powi(2)).sum::<f64>() / 9.0;
    let std_dev = variance.sqrt();
    let fmin = features.iter().cloned().fold(f64::INFINITY, f64::min);
    let fmax = features.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    v[27] = mean.clamp(0.0, 1.0) as f32;
    v[28] = std_dev.clamp(0.0, 1.0) as f32;
    v[29] = fmin.clamp(0.0, 1.0) as f32;
    v[30] = fmax.clamp(0.0, 1.0) as f32;

    // ── region [31..64]: deterministic SHA3 noise ────────────────────────────
    let hash = Sha3_256::digest(seed.as_bytes());
    for i in 0..32 {
        let byte = hash[i] as f64 / 255.0;
        // blend with mean so noise correlates weakly with signal
        v[31 + i] = ((byte * 0.7 + mean * 0.3) as f32).clamp(0.0, 1.0);
    }

    // [64..128] stays zero — reserved

    debug_assert_eq!(v.len(), 128);
    v
}

/// Φ(t) — scalar physical-plane score: mean of the 9 raw entropy features.
pub fn phi_score(features: &[f64; 9]) -> f64 {
    features.iter().sum::<f64>() / 9.0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn len_is_128() {
        let f = [0.5f64; 9];
        assert_eq!(build_vector(&f, "test:0").len(), 128);
    }

    #[test]
    fn all_values_in_range() {
        let f = [0.1, 0.9, 0.3, 0.7, 0.5, 0.0, 1.0, 0.4, 0.6];
        let v = build_vector(&f, "test:1");
        for &x in &v {
            assert!(x >= 0.0 && x <= 1.0, "out of range: {}", x);
        }
    }

    #[test]
    fn complementary_strand_correct() {
        let f = [0.3f64; 9];
        let v = build_vector(&f, "test:2");
        for i in 0..9 {
            let expected = (1.0 - 0.3f32).clamp(0.0, 1.0);
            assert!((v[9 + i] - expected).abs() < 1e-5);
        }
    }
}
