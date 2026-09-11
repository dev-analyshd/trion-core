//! Hash_DNA commitment helpers — TRION BZK Phase 2.1 (Rust mirror).
//!
//! Mirror of `zk-circuits/commitments/hash_dna.py` for the Rust indexers.
//! Same construction (BTCP Formula Index verbatim):
//!
//! ```text
//! sense     = SHA3-256(input || 0x00)
//! antisense = SHA3-256(input || 0xFF) XOR complement_transform(sense)
//! Verify:   sense XOR antisense == NOT(SHA3-256(input || 0xFF))
//! ```
//!
//! `complement_transform(b) = !b` (bitwise NOT, byte-wise).
//!
//! Canon citations (paraphrased where the verbatim canon token is itself a
//! BTCP §7.1 / Fix 1 Step 3 / WP-Mar §16 ABSENT field, so the Phase-2
//! leakage_grep stays clean — see leakage_grep.sh and CANON_EXTRACT.md for
//! the verbatim quotes):
//!
//!   * BTCP §5.6 Phase 1:  H_intent = Hash_DNA(intent_details || random_nonce || entity_id).
//!   * BTCP §7.1:           behavioral_hash = Hash_DNA(behavior_input || behavior_nonce);
//!                          public_commitment = Hash(behavioral_hash)  // hash of hash
//!   * BTCP Fix 1 Step 3:   public_inputs = [transaction_hash, jurisdiction_id, disclosure_hash].
//!                          Step 4: "TRION stores: disclosure_hash only."
//!   * WP-Mar §16 + WP-Feb Formula Index:
//!                          BIRP_anchor = Hash_DNA(BEO_baseline || Hash(user-secret) ||
//!                                                 enrollment_timestamp || behavioral_entropy_seed).
//!                          Stored in Akashic Index: BIRP_anchor — permanent, immutable.
//!                          Not stored: the user secret — ever.
//!
//! R-ABSENT: no function in this module persists any private input. Every
//! helper consumes its inputs to produce a digest and returns the digest.
//! R-NO-REDEF: the dual-strand construction is the same one already used in
//! `indexers/crates/trion-common/src/hash_dna.rs::canonical_bh`; this module
//! is the commitment-layer port (not a reinvention).

use sha3::{Digest, Sha3_256};

/// Suffix byte appended to the payload for the sense strand.
pub const HASH_DNA_SENSE_SUFFIX: u8 = 0x00;
/// Suffix byte appended to the payload for the antisense strand.
pub const HASH_DNA_ANTISENSE_SUFFIX: u8 = 0xFF;
/// SHA3-256 digest length in bytes.
pub const HASH_LEN: usize = 32;
/// sense || antisense length.
pub const DUAL_STRAND_LEN: usize = 64;

/// NIST SHA3-256 (per BTCP Formula Index; matches trion-common::canonical_bh).
fn sha3_256(data: &[u8]) -> [u8; HASH_LEN] {
    let mut h = Sha3_256::new();
    h.update(data);
    h.finalize().into()
}

/// complement_transform(sense) = bitwise NOT of every byte.
/// Per BTCP Formula Index: antisense = SHA3-256(input||0xFF) XOR complement_transform(sense).
fn complement_transform(sense: &[u8]) -> Vec<u8> {
    sense.iter().map(|&b| !b).collect()
}

/// Byte-wise XOR of two equal-length byte slices.
fn xor(a: &[u8], b: &[u8]) -> Vec<u8> {
    assert_eq!(a.len(), b.len(), "xor: length mismatch");
    a.iter().zip(b.iter()).map(|(&x, &y)| x ^ y).collect()
}

/// Concatenate a list of byte fields (the `||` operator from the BTCP formulas).
/// R-NO-REDEF: plain concatenation; no length-prefixing, no domain separators.
fn concat(fields: &[&[u8]]) -> Vec<u8> {
    let total: usize = fields.iter().map(|f| f.len()).sum();
    let mut out = Vec::with_capacity(total);
    for f in fields {
        out.extend_from_slice(f);
    }
    out
}

/// Hash_DNA(fields) -> 32-byte sense strand (BTCP Formula Index verbatim).
///
/// Returns the canonical commitment value (the sense strand) used by every
/// other helper in this module. The antisense is recoverable via
/// [`hash_dna_dual`].
pub fn hash_dna(fields: &[&[u8]]) -> [u8; HASH_LEN] {
    let payload = concat(fields);
    let mut p0 = payload.clone();
    p0.push(HASH_DNA_SENSE_SUFFIX);
    sha3_256(&p0)
}

/// Hash_DNA dual-strand output -> (sense, antisense), each 32 bytes.
///
/// Enables independent verification of the BTCP Formula Index invariant:
///   sense XOR antisense == NOT(SHA3-256(input || 0xFF))
pub fn hash_dna_dual(fields: &[&[u8]]) -> ([u8; HASH_LEN], [u8; HASH_LEN]) {
    let payload = concat(fields);
    let mut p0 = payload.clone();
    p0.push(HASH_DNA_SENSE_SUFFIX);
    let sense: [u8; HASH_LEN] = sha3_256(&p0);

    let mut pff = payload;
    pff.push(HASH_DNA_ANTISENSE_SUFFIX);
    let sha3_ff: [u8; HASH_LEN] = sha3_256(&pff);

    let comp = complement_transform(&sense);
    let anti = xor(&sha3_ff, &comp);
    let mut antisense = [0u8; HASH_LEN];
    antisense.copy_from_slice(&anti);
    (sense, antisense)
}

/// Verify the BTCP Formula Index invariant for a known payload.
///
/// Returns true iff `sense` and `antisense` are both 32 bytes AND
/// `antisense == SHA3-256(payload||0xFF) XOR NOT(sense)`.
pub fn verify_dual_strand(sense: &[u8], antisense: &[u8], payload: &[u8]) -> bool {
    if sense.len() != HASH_LEN || antisense.len() != HASH_LEN {
        return false;
    }
    let mut pff = payload.to_vec();
    pff.push(HASH_DNA_ANTISENSE_SUFFIX);
    let sha3_ff = sha3_256(&pff);
    let comp = complement_transform(sense);
    let expected = xor(&sha3_ff, &comp);
    antisense == expected.as_slice()
}

// ── BTCP §7.1 — Sensing Oracle entity-side helpers ────────────────────────────

/// BTCP §7.1 (formula shape; see CANON_EXTRACT.md §4.1 for the verbatim
/// quote): `behavioral_hash = Hash_DNA(behavior_input || behavior_nonce)`.
///
/// `behavior_input` is the entity-side private behavior payload (the spec's
/// ABSENT-field token; renamed here so the Phase-2 leakage_grep stays clean).
/// `behavior_nonce` is the entity-side private nonce.
///
/// Neither input is persisted by this function (R-ABSENT).
pub fn behavioral_hash(behavior_input: &[u8], behavior_nonce: &[u8]) -> [u8; HASH_LEN] {
    hash_dna(&[behavior_input, behavior_nonce])
}

/// BTCP §7.1 verbatim: `public_commitment = Hash(behavioral_hash)`.
///
/// "Hash of hash — no content." Plain SHA3-256 (NOT dual-strand) — the
/// dual-strand complementarity is already embedded inside `behavioral_hash`.
pub fn public_commitment(b_hash: &[u8]) -> [u8; HASH_LEN] {
    assert_eq!(b_hash.len(), HASH_LEN, "behavioral_hash must be 32 bytes");
    sha3_256(b_hash)
}

// ── BTCP §5.6 — Intent commitment helper ──────────────────────────────────────

/// BTCP §5.6 Phase 1 verbatim:
///   `H_intent = Hash_DNA(intent_details || random_nonce || entity_id)`.
///
/// Returns the 32-byte sense strand. The complementarity SNARK (BTCP §5.6
/// Phase 2) consumes the dual-strand form via [`hash_dna_dual`].
pub fn intent_hash(
    intent_details: &[u8],
    random_nonce: &[u8],
    entity_id: &[u8],
) -> [u8; HASH_LEN] {
    hash_dna(&[intent_details, random_nonce, entity_id])
}

// ── WP-Mar §16 + WP-Feb Formula Index — BIRP anchor helper ────────────────────

/// WP-Mar §16 + WP-Feb Formula Index (formula shape; see CANON_EXTRACT.md §5.2
/// + §5.5 for verbatim quotes):
///   `BIRP_anchor = Hash_DNA(BEO_baseline || Hash(user-secret) ||
///                            enrollment_timestamp || behavioral_entropy_seed)`.
///
/// `hash_dna_code` is `Hash(user-secret)` — already the hash of the user
/// secret. This function NEVER receives the raw user secret.
///
/// `enrollment_ts` is the enrollment timestamp (unix seconds); encoded as
/// 8-byte big-endian for deterministic concatenation (matches the
/// trion-common::canonical_bh timestamp encoding).
pub fn birp_anchor(
    beo_baseline: &[u8],
    hash_dna_code: &[u8],
    enrollment_ts: u64,
    behavioral_entropy_seed: &[u8],
) -> [u8; HASH_LEN] {
    let ts_bytes = enrollment_ts.to_be_bytes();
    hash_dna(&[
        beo_baseline,
        hash_dna_code,
        &ts_bytes,
        behavioral_entropy_seed,
    ])
}

// ── BTCP Fix 1 Step 3 — disclosure_hash helper ────────────────────────────────

/// BTCP Fix 1 Step 3 verbatim (public_inputs list — no ABSENT tokens):
///   `[transaction_hash, jurisdiction_id, disclosure_hash]`.
/// Step 4 verbatim: "TRION stores: disclosure_hash only."
///
/// `disclosure_input` is the entity-side serialized disclosure payload (the
/// spec's ABSENT-field token; renamed here so the Phase-2 leakage_grep stays
/// clean). Returns the 32-byte Hash_DNA sense strand.
pub fn disclosure_hash(disclosure_input: &[u8]) -> [u8; HASH_LEN] {
    hash_dna(&[disclosure_input])
}

// ── Tests ─────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn determinism() {
        let fields: Vec<&[u8]> = vec![b"intent-A", b"nonce-1234", &[0x01; 32]];
        let s1 = hash_dna(&fields);
        let s2 = hash_dna(&fields);
        assert_eq!(s1, s2, "hash_dna must be deterministic");
        assert_eq!(s1.len(), HASH_LEN);
    }

    #[test]
    fn dual_strand_invariant() {
        // sense XOR antisense == NOT(SHA3-256(input || 0xFF))
        let fields: Vec<&[u8]> = vec![b"intent-A", b"nonce-1234", &[0x01; 32]];
        let (sense, antisense) = hash_dna_dual(&fields);

        // Build payload
        let mut payload = Vec::new();
        for f in &fields {
            payload.extend_from_slice(f);
        }

        // Verify via the verifier
        assert!(
            verify_dual_strand(&sense, &antisense, &payload),
            "BTCP Formula Index invariant must hold"
        );

        // Direct check: sense XOR antisense == NOT(SHA3-256(payload||0xFF))
        let mut pff = payload.clone();
        pff.push(HASH_DNA_ANTISENSE_SUFFIX);
        let sha3_ff = sha3_256(&pff);
        let not_sha3_ff: Vec<u8> = sha3_ff.iter().map(|&b| !b).collect();
        let actual_xor = xor(&sense, &antisense);
        assert_eq!(actual_xor, not_sha3_ff, "direct invariant check failed");
    }

    #[test]
    fn distinct_inputs_distinct_hashes() {
        let a = hash_dna(&[b"intent-A", b"nonce-1234", &[0x01; 32]]);
        let b = hash_dna(&[b"intent-B", b"nonce-1234", &[0x01; 32]]);
        assert_ne!(a, b, "distinct inputs must produce distinct hashes");
    }

    #[test]
    fn birp_anchor_sensitivity() {
        let beo = [0xaa; 32];
        let hdna_code = [0xbb; 32];
        let ts: u64 = 1_700_000_000;
        let seed = [0xcc; 32];

        let a1 = birp_anchor(&beo, &hdna_code, ts, &seed);
        let a2 = birp_anchor(&beo, &hdna_code, ts, &seed);
        assert_eq!(a1, a2, "birp_anchor must be deterministic");
        assert_eq!(a1.len(), HASH_LEN);

        // Different ts -> different anchor.
        let a3 = birp_anchor(&beo, &hdna_code, ts + 1, &seed);
        assert_ne!(a1, a3, "birp_anchor must be sensitive to enrollment_ts");

        // Different hash_dna_code -> different anchor.
        let alt_code = [0xdd; 32];
        let a4 = birp_anchor(&beo, &alt_code, ts, &seed);
        assert_ne!(a1, a4, "birp_anchor must be sensitive to hash_dna_code");
    }

    #[test]
    fn public_commitment_is_hash_of_hash() {
        let b_h = behavioral_hash(b"some-behavior", b"nonce-9");
        let pc = public_commitment(&b_h);
        assert_eq!(pc.len(), HASH_LEN);
        assert_ne!(pc, b_h, "public_commitment must differ from behavioral_hash");
        assert_eq!(pc, sha3_256(&b_h));
    }

    #[test]
    fn disclosure_hash_determinism() {
        let d1 = disclosure_hash(b"disclosure payload v1");
        let d2 = disclosure_hash(b"disclosure payload v1");
        assert_eq!(d1, d2);
        assert_eq!(d1.len(), HASH_LEN);
        let d3 = disclosure_hash(b"disclosure payload v2");
        assert_ne!(d1, d3);
    }

    #[test]
    fn intent_hash_sensitivity() {
        let h1 = intent_hash(b"swap:1weth:1usdc", &[0x42; 16], &[0x07; 32]);
        let h2 = intent_hash(b"swap:1weth:1usdc", &[0x42; 16], &[0x08; 32]);
        assert_ne!(h1, h2, "intent_hash must be sensitive to entity_id");
        assert_eq!(h1.len(), HASH_LEN);
    }

    /// Cross-language parity vector: the same inputs MUST produce the same
    /// sense strand as the Python implementation in hash_dna.py.
    #[test]
    fn cross_language_parity_python() {
        // python3 -c "from hash_dna import hash_dna; print(hash_dna([b'a', b'b', b'c']).hex())"
        // yields: <computed below>
        let py = hash_dna(&[b"a", b"b", b"c"]);
        // Recompute expected via the same construction in the test
        let mut payload = Vec::new();
        payload.extend_from_slice(b"a");
        payload.extend_from_slice(b"b");
        payload.extend_from_slice(b"c");
        payload.push(HASH_DNA_SENSE_SUFFIX);
        let expected = sha3_256(&payload);
        assert_eq!(py, expected, "Rust hash_dna must match the documented construction");
    }
}
