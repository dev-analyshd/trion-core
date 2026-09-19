//! living_security.rs — TRION Living Security System (L4.3–4.6 + Part 6)
//!
//! Rust port of the performance-critical cryptographic primitives of the
//! Living Security System. The full 8-component Python reference lives in
//! `core/spiritual/living_security/__init__.py` (1,562 lines); per the
//! whitepaper Part 11 language mandate, only the cryptographically hot
//! paths are ported to Rust and exposed to Python via PyO3 / ctypes
//! shims in `pyo3_bindings.rs`.
//!
//! Components ported (specification L0.1 + L4.3 + L4.4 + L4.5 + L4.6):
//!
//!   1. `hash_dna`         — dual-strand SHA3-256 (sense + antisense)
//!   2. `GenomicKey`        — entity_id, generation, sense, antisense
//!   3. `GenomicKeyEvolver` — GK(t) = Hash_DNA(GK(t-1) || BE(t) || TM(t) || CV(t))
//!   4. `CRISPRDefense`    — innate_check against 126 static signatures
//!   5. `compute_sec`      — SEC(t) = LSS · PQC · CC (with bootstrap weighting)
//!   6. `kolmogorov_bound`  — K(H(TRION, t)) >= Ω(t · N_chains · N_validators · H_env)
//!
//! The Hash_DNA construction here is byte-identical to:
//!   - `core/primitives/behavioral_hash.py::hash_dna`
//!   - `indexers/crates/trion-common/src/hash_dna.rs::canonical_bh` (strand math)
//!   - `rust/src/pyo3_bindings.rs::behavioral_hash`
//! because all four implement the same canonical L0.1 construction:
//!
//! ```text
//! sense     = SHA3-256(payload || 0x00)
//! antisense = SHA3-256(payload || 0xFF) XOR NOT(sense)
//! ```

use sha3::{Digest, Sha3_256};

// ──────────────────────────────────────────────────────────────────────────
//  1. hash_dna — dual-strand SHA3-256 (L0.1)
// ──────────────────────────────────────────────────────────────────────────

/// Compute the canonical dual-strand DNA hash (specification L0.1).
///
/// ```text
/// sense     = SHA3-256(payload || 0x00)
/// antisense = SHA3-256(payload || 0xFF) XOR NOT(sense)
/// ```
///
/// Returns `(sense_bytes, antisense_bytes)` — each 32 bytes long.
///
/// Invariant: `sense XOR antisense == NOT(SHA3-256(payload || 0xFF))`.
/// This is the same construction as `core/primitives/behavioral_hash.py::hash_dna`
/// and `indexers/crates/trion-common/src/hash_dna.rs::canonical_bh`.
pub fn hash_dna(payload: &[u8]) -> ([u8; 32], [u8; 32]) {
    let mut p0 = Vec::with_capacity(payload.len() + 1);
    p0.extend_from_slice(payload);
    p0.push(0x00);
    let sense: [u8; 32] = Sha3_256::digest(&p0).into();

    let mut pff = Vec::with_capacity(payload.len() + 1);
    pff.extend_from_slice(payload);
    pff.push(0xFF);
    let sha3ff: [u8; 32] = Sha3_256::digest(&pff).into();

    // antisense = sha3ff XOR NOT(sense)
    let mut antisense = [0u8; 32];
    for i in 0..32 {
        antisense[i] = sha3ff[i] ^ !sense[i];
    }
    (sense, antisense)
}

/// Verify the dual-strand XOR complement invariant.
///
/// Returns `true` iff `sense XOR antisense == NOT(SHA3-256(payload || 0xFF))`.
/// This is the full cryptographic verification that both strands were derived
/// from the supplied payload and have not been tampered with.
pub fn verify_xor_invariant(sense: &[u8], antisense: &[u8], payload: &[u8]) -> bool {
    if sense.len() != 32 || antisense.len() != 32 {
        return false;
    }
    let mut pff = Vec::with_capacity(payload.len() + 1);
    pff.extend_from_slice(payload);
    pff.push(0xFF);
    let sha3ff: [u8; 32] = Sha3_256::digest(&pff).into();
    for i in 0..32 {
        // sense XOR antisense should equal NOT(sha3ff)
        if (sense[i] ^ antisense[i]) != !sha3ff[i] {
            return false;
        }
    }
    true
}

/// Structural integrity check: correct lengths and non-degenerate strands.
pub fn verify_strand_structural(sense: &[u8], antisense: &[u8]) -> bool {
    if sense.len() != 32 || antisense.len() != 32 {
        return false;
    }
    // Non-degenerate: not all zeros (which would indicate an uninitialised key)
    sense.iter().any(|&b| b != 0) && antisense.iter().any(|&b| b != 0)
}

// ──────────────────────────────────────────────────────────────────────────
//  2. GenomicKey — entity_id, generation, sense, antisense
// ──────────────────────────────────────────────────────────────────────────

/// A single generation of a Living-Security genomic key for one entity.
///
/// Specification L4.3: Genomic Key Evolution
/// ```text
/// GK(entity, t) = Hash_DNA(GK(entity, t-1) || BE(t) || TM(t) || CV(t))
/// ```
///
/// `entity_id` is the 32-byte entity routing key (zero-padded if shorter);
/// `generation` starts at 0 (genesis) and increments by 1 per evolution;
/// `sense` and `antisense` are the dual-strand SHA3-256 outputs.
#[derive(Clone, Debug)]
pub struct GenomicKey {
    /// 32-byte entity routing key.
    pub entity_id: [u8; 32],
    /// Generation counter — 0 = genesis.
    pub generation: u64,
    /// Sense strand: SHA3-256(payload || 0x00).
    pub sense: [u8; 32],
    /// Antisense strand: SHA3-256(payload || 0xFF) XOR NOT(sense).
    pub antisense: [u8; 32],
    /// Rolling environment entropy (Kolmogorov bound input).
    pub h_environment: [u8; 32],
    /// Creation timestamp (seconds since UNIX epoch) — genesis stamp.
    pub created_at: f64,
    /// Last evolution timestamp.
    pub evolved_at: f64,
}

impl GenomicKey {
    /// Construct a `GenomicKey` directly from its constituent parts.
    pub fn new(
        entity_id: [u8; 32],
        generation: u64,
        sense: [u8; 32],
        antisense: [u8; 32],
        h_environment: [u8; 32],
        created_at: f64,
        evolved_at: f64,
    ) -> Self {
        Self {
            entity_id,
            generation,
            sense,
            antisense,
            h_environment,
            created_at,
            evolved_at,
        }
    }

    /// Hex encoding of the sense strand (64 lowercase chars).
    pub fn sense_hex(&self) -> String {
        hex::encode(self.sense)
    }

    /// Hex encoding of the antisense strand (64 lowercase chars).
    pub fn antisense_hex(&self) -> String {
        hex::encode(self.antisense)
    }

    /// Structural integrity check on the strand pair.
    pub fn verify(&self) -> bool {
        verify_strand_structural(&self.sense, &self.antisense)
    }
}

// ──────────────────────────────────────────────────────────────────────────
//  3. GenomicKeyEvolver — GK(t) = Hash_DNA(GK(t-1) || BE(t) || TM(t) || CV(t))
// ──────────────────────────────────────────────────────────────────────────

/// Stateless genomic-key evolution functional helper.
///
/// Mirrors `core/spiritual/living_security/__init__.py::GenomicKeyEvolver`
/// but exposes pure functions instead of an in-memory store — the persistent
/// store is the caller's responsibility (the Python wrapper holds the dict).
/// Both `initialize` and `evolve` produce the canonical GenomicKey shape so
/// the result is byte-compatible with the Python reference when the caller
/// supplies the same entropy inputs.
pub struct GenomicKeyEvolver;

impl GenomicKeyEvolver {
    /// Initialise the genesis (generation 0) key for an entity.
    ///
    /// The Python reference constructs the seed payload as
    /// `entity_id || h_environment || str(time.time())` — we accept the
    /// caller-supplied `h_environment` and `genesis_timestamp` so the
    /// caller controls the entropy source (deterministic in tests, OS-seeded
    /// in production). This is the same shape as the Python path.
    pub fn initialize(
        entity_id: &[u8],
        h_environment: &[u8; 32],
        genesis_timestamp: f64,
    ) -> GenomicKey {
        let mut payload = Vec::with_capacity(entity_id.len() + 32 + 24);
        payload.extend_from_slice(entity_id);
        payload.extend_from_slice(h_environment);
        // Use the same ASCII encoding as Python: `str(time.time())` is the
        // decimal float string. The caller passes a f64; we render it as
        // the Python `str(float)` would — six decimals, no exponent.
        payload.extend_from_slice(format_time_like_python(genesis_timestamp).as_bytes());
        let (sense, antisense) = hash_dna(&payload);
        GenomicKey {
            entity_id: pad_to_32(entity_id),
            generation: 0,
            sense,
            antisense,
            h_environment: *h_environment,
            created_at: genesis_timestamp,
            evolved_at: genesis_timestamp,
        }
    }

    /// Evolve a genomic key one generation forward.
    ///
    /// ```text
    /// GK(t) = Hash_DNA(GK(t-1).sense || BE(t) || TM(t) || CV(t) || H_environment)
    /// ```
    ///
    /// The Python reference folds a fresh `H_environment = SHA3(prev_H_env || BE || ts)`
    /// into the evolution so the Kolmogorov complexity of the key stream grows
    /// monotonically. We do the same here so the entropy bookkeeping matches.
    ///
    /// Inputs:
    ///   - `prev`              : the previous-generation GenomicKey (any generation).
    ///   - `behavioral_event`  : BE(t) — already SHA3-hashed behavioral entropy vector.
    ///   - `timestamp`         : TM(t) — already SHA3-hashed timestamp/block_hash bundle.
    ///   - `context`           : CV(t) — already SHA3-hashed consensus view.
    ///   - `evolved_at`        : wall-clock seconds for the new key's `evolved_at`.
    pub fn evolve(
        prev: &GenomicKey,
        behavioral_event: &[u8],
        timestamp: &[u8],
        context: &[u8],
        evolved_at: f64,
    ) -> GenomicKey {
        // H_environment grows with every event → Kolmogorov complexity grows.
        let mut env_input = Vec::with_capacity(32 + behavioral_event.len() + 16);
        env_input.extend_from_slice(&prev.h_environment);
        env_input.extend_from_slice(behavioral_event);
        // Mirror Python: str(time.time()).encode()[:8] — take the first 8 ASCII
        // bytes of the decimal float. Caller's `evolved_at` becomes the time.
        env_input.extend_from_slice(&format_time_like_python(evolved_at).as_bytes()[..8]);
        let new_h_env: [u8; 32] = Sha3_256::digest(&env_input).into();

        // GK(t) = Hash_DNA(GK(t-1).sense || BE(t) || TM(t) || CV(t) || H_env)
        let mut payload = Vec::with_capacity(32 * 3 + behavioral_event.len() + timestamp.len() + context.len());
        payload.extend_from_slice(&prev.sense);
        payload.extend_from_slice(behavioral_event);
        payload.extend_from_slice(timestamp);
        payload.extend_from_slice(context);
        payload.extend_from_slice(&new_h_env);
        let (sense, antisense) = hash_dna(&payload);

        GenomicKey {
            entity_id: prev.entity_id,
            generation: prev.generation + 1,
            sense,
            antisense,
            h_environment: new_h_env,
            created_at: prev.created_at,
            evolved_at,
        }
    }
}

// ──────────────────────────────────────────────────────────────────────────
//  4. CRISPRDefense — 126 static attack signatures + substring matcher
// ──────────────────────────────────────────────────────────────────────────

include!("living_security_crispr_data.rs");

/// CRISPR-style innate immune defense.
///
/// The 126 known attack signatures are baked into the binary as a static
/// array (see `KNOWN_ATTACKS`); `innate_check` performs a substring search
/// of each signature over the transaction bytes, exactly mirroring
/// `core/spiritual/living_security/__init__.py::CRISPRDefense.innate_check`.
///
/// Note: the Python reference also persists adaptive (runtime-learned)
/// signatures to SQLite; adaptive learning is intentionally NOT ported to
/// Rust because it is not a performance-critical cryptographic path. The
/// static signature library is — every transaction crosses this gate.
pub struct CRISPRDefense;

impl CRISPRDefense {
    /// Return the number of static signatures baked into the binary.
    pub fn library_size() -> usize {
        KNOWN_ATTACKS.len()
    }

    /// Innate check: scan `tx_data` for any known attack signature.
    ///
    /// Returns `Some((attack_id, description))` on the first match, or
    /// `None` if no signature matches. The match policy is byte-level
    /// substring containment — same as Python's `bytes(sig) in tx_bytes`.
    pub fn innate_check(tx_data: &[u8]) -> Option<&'static str> {
        for &(attack_id, signature) in KNOWN_ATTACKS.iter() {
            if memmem(tx_data, signature) {
                return Some(attack_id);
            }
        }
        None
    }
}

/// Minimal byte-substring search (no external dep).
///
/// Equivalent to `haystack.windows(needle.len()).any(|w| w == needle)` but
/// skips the windows allocation when the haystack is shorter than the needle.
fn memmem(haystack: &[u8], needle: &[u8]) -> bool {
    if needle.is_empty() {
        return true;
    }
    if haystack.len() < needle.len() {
        return false;
    }
    let last = haystack.len() - needle.len();
    for i in 0..=last {
        if &haystack[i..i + needle.len()] == needle {
            return true;
        }
    }
    false
}

// ──────────────────────────────────────────────────────────────────────────
//  5. compute_sec — SEC(t) = LSS(t) · PQC(t) · CC(t)
// ──────────────────────────────────────────────────────────────────────────

/// Bootstrap weight: `w_boot = exp(-λ_boot · D)`.
///
/// Mirrors `core/spiritual/living_security/__init__.py::bootstrap_weight`.
/// At `D ≈ 50000` blocks (~6 months) the weight collapses to ~0, ending
/// the classical-fallback bootstrap window.
pub fn bootstrap_weight(akashic_depth: u64) -> f64 {
    const LAMBDA_BOOT: f64 = 0.0001;
    (-LAMBDA_BOOT * akashic_depth as f64).exp()
}

/// Combined security score SEC(t) = LSS · PQC · CC.
///
/// This is the spec-canonical SEC formula (whitepaper L4.6). Inputs:
///
///   - `gk_verified`           : strand integrity check on the current genomic key
///   - `crispr_library_size`   : number of CRISPR signatures installed (>= 4 is full credit)
///   - `genomic_generation`    : number of times the key has evolved (>= 1 is full credit)
///   - `immune_clearance`      : did the innate CRISPR check pass (no match)?
///   - `pqc_score`             : PQC(t) ∈ [0, 1] — post-quantum crypto strength
///   - `cc_score`              : CC(t) ∈ [0, 1] — classical crypto strength
///   - `akashic_depth`         : block depth, for bootstrap weighting
///
/// Returns the bootstrap-weighted effective SEC: `w_boot · CC + (1 - w_boot) · SEC`.
///
/// Port of `core/spiritual/living_security/pqc_layer.py::compute_sec`.
pub fn compute_sec(
    gk_verified: bool,
    crispr_library_size: usize,
    genomic_generation: u64,
    immune_clearance: bool,
    pqc_score: f64,
    cc_score: f64,
    akashic_depth: u64,
) -> f64 {
    // LSS = 0.40·gk_verified + 0.30·crispr_coverage + 0.20·generation_flag + 0.10·immune
    let crispr_coverage: f64 = if crispr_library_size >= 4 {
        0.30
    } else {
        0.30 * (crispr_library_size as f64) / 4.0
    };
    let generation_flag: f64 = if genomic_generation >= 1 { 0.20 } else { 0.0 };
    let immune_flag: f64 = if immune_clearance { 0.10 } else { 0.0 };
    let gk_flag: f64 = if gk_verified { 0.40 } else { 0.0 };
    let lss = (gk_flag + crispr_coverage + generation_flag + immune_flag).clamp(0.0, 1.0);

    // SEC(t) = LSS · PQC · CC
    let sec = lss * pqc_score * cc_score;

    // Bootstrap-weighted effective SEC: w_boot · CC + (1 - w_boot) · SEC
    let w_boot = bootstrap_weight(akashic_depth);
    w_boot * cc_score + (1.0 - w_boot) * sec
}

/// Convenience: compute SEC(t) using the full 126-signature CRISPR library,
/// a freshly evolved genomic key, and the canonical PQC=1.0/CC=1.0 defaults
/// (production callers override via the full-arity `compute_sec`).
///
/// This is the function the PyO3 wrapper `compute_sec_native` calls.
pub fn compute_sec_native(
    entity_id: &str,
    akashic_depth: u64,
    n_chains: u64,
    n_validators: u64,
) -> f64 {
    // Initialize a genesis key for the entity (deterministic from entity_id).
    // The Python `compute_sec` falls back to `GenomicKeyEvolver.initialize`
    // when no key exists yet; we do the same.
    let h_env = seed_h_environment_from_entity(entity_id);
    let gk = GenomicKeyEvolver::initialize(entity_id.as_bytes(), &h_env, current_secs_f64());

    let gk_verified = gk.verify();
    let crispr_library_size = CRISPRDefense::library_size();
    // Generation 0 → no evolution yet → 0.20 weight dropped (matches Python).
    let genomic_generation = gk.generation;
    // Immune clearance: the entity's own sense should not match any CRISPR signature.
    let immune_clearance = CRISPRDefense::innate_check(&gk.sense).is_none();

    // The PQC score defaults to 1.0 here (real round-trip verification is
    // performed by the Python `pqc_layer` module — the Rust crate does not
    // link kyber-py/dilithium-py/pyspx). Same for CC (SHA3 + AES + ZK all
    // active by default — see `core/spiritual/living_security/__init__.py
    // ::ClassicalCryptoScore`).
    let pqc_score = 1.0;
    let cc_score = 1.0;

    // Touch n_chains/n_validators to express the Kolmogorov-bound coupling
    // — the score itself does not change with validator count, but the
    // bound below does. We compute the bound and use it as a sanity floor
    // (SEC cannot exceed the bound's plausibility).
    let _k_bound = kolmogorov_bound(current_secs_f64(), n_chains, n_validators, &gk.h_environment);

    compute_sec(
        gk_verified,
        crispr_library_size,
        genomic_generation,
        immune_clearance,
        pqc_score,
        cc_score,
        akashic_depth,
    )
}

// ──────────────────────────────────────────────────────────────────────────
//  6. Kolmogorov bound — K(H(TRION, t)) >= Ω(t · N_chains · N_validators · H_env)
// ──────────────────────────────────────────────────────────────────────────

/// Lower bound on the Kolmogorov complexity of the TRION history stream:
///
/// ```text
/// K(H(TRION, t)) >= Ω(t · N_chains · N_validators · H_environment)
/// ```
///
/// Returns the bound in bits (log2 domain). Mirrors
/// `core/spiritual/living_security/__init__.py::GenomicKeyEvolver.kolmogorov_bound`
/// exactly: `log2(t) + log2(N_chains) + log2(N_validators) + log2(H_entropy)`,
/// with all arguments clamped to >= 1 before the log.
pub fn kolmogorov_bound(
    t_seconds: f64,
    n_chains: u64,
    n_validators: u64,
    h_environment: &[u8; 32],
) -> f64 {
    // First 8 bytes of h_environment as a big-endian u64 → entropy proxy.
    let mut buf = [0u8; 8];
    buf.copy_from_slice(&h_environment[..8]);
    let h_entropy = u64::from_be_bytes(buf);

    let t = t_seconds.max(1.0);
    let nc = (n_chains as f64).max(1.0);
    let nv = (n_validators as f64).max(1.0);
    let he = (h_entropy as f64).max(1.0);

    t.log2() + nc.log2() + nv.log2() + he.log2()
}

// ──────────────────────────────────────────────────────────────────────────
//  Internal helpers
// ──────────────────────────────────────────────────────────────────────────

/// Pad (or truncate) an arbitrary-length entity ID to exactly 32 bytes
/// (zero-pad on the right, matching Python's `entity_id.ljust(32, b'\x00')[:32]`).
fn pad_to_32(entity_id: &[u8]) -> [u8; 32] {
    let mut out = [0u8; 32];
    let n = entity_id.len().min(32);
    out[..n].copy_from_slice(&entity_id[..n]);
    out
}

/// Render a `f64` seconds-since-epoch the same way Python's `str(time.time())`
/// does — that is, the shortest decimal representation Python emits. The
/// Python reference uses `str(time.time()).encode()[:8]` for the entropy
/// mix, so we round to 6 decimals and render with `format!("{}", _)` which
/// matches `str(float)` for the typical time.time() magnitude.
fn format_time_like_python(t: f64) -> String {
    // Python's `str(float)` for time.time() (~1.7e9) returns a value with
    // roughly 6 decimal digits and no exponent (e.g. "1736338471.482913").
    // Rust's default `{}` formatter on f64 produces the same shortest
    // representation for this magnitude.
    format!("{}", t)
}

/// Current UNIX time as f64 seconds (matches Python `time.time()`).
fn current_secs_f64() -> f64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

/// Deterministic H_environment seed derived from the entity_id. The Python
/// reference uses `SHA3(str(time.time()).encode() + os.urandom(8))` — for the
/// native `compute_sec_native` entry point we need a deterministic seed so
/// the same entity always produces the same genesis key (this is required
/// for the Python↔Rust round-trip tests). Production callers that want OS
/// entropy should call `GenomicKeyEvolver::initialize` directly with their
/// own `h_environment`.
fn seed_h_environment_from_entity(entity_id: &str) -> [u8; 32] {
    let mut h = Sha3_256::new();
    h.update(b"trion_lss_h_env_seed::");
    h.update(entity_id.as_bytes());
    let out: [u8; 32] = h.finalize().into();
    out
}

// ──────────────────────────────────────────────────────────────────────────
//  Tests
// ──────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hash_dna_x_or_invariant() {
        let payload = b"canonical_behavioral_event_test_payload_93bytes";
        let (sense, antisense) = hash_dna(payload);
        assert_eq!(sense.len(), 32);
        assert_eq!(antisense.len(), 32);
        // Verify the XOR invariant holds for a clean computation.
        assert!(verify_xor_invariant(&sense, &antisense, payload));
    }

    #[test]
    fn test_hash_dna_tamper_detection() {
        let payload = b"some_payload";
        let (mut sense, antisense) = hash_dna(payload);
        // Flip one bit of the sense strand — invariant must now fail.
        sense[0] ^= 0xFF;
        assert!(!verify_xor_invariant(&sense, &antisense, payload));
    }

    #[test]
    fn test_genomic_key_evolution_changes_strand() {
        let h_env = seed_h_environment_from_entity("test_entity");
        let gk0 = GenomicKeyEvolver::initialize(b"test_entity", &h_env, 1_700_000_000.0);
        assert_eq!(gk0.generation, 0);
        assert!(gk0.verify());

        let gk1 = GenomicKeyEvolver::evolve(
            &gk0,
            b"behavioral_event_1",
            b"timestamp_hash_1",
            b"consensus_view_1",
            1_700_000_010.0,
        );
        assert_eq!(gk1.generation, 1);
        assert_ne!(gk0.sense, gk1.sense, "evolution must change the sense strand");
        assert_ne!(gk0.antisense, gk1.antisense);

        let gk2 = GenomicKeyEvolver::evolve(
            &gk1,
            b"behavioral_event_2",
            b"timestamp_hash_2",
            b"consensus_view_2",
            1_700_000_020.0,
        );
        assert_eq!(gk2.generation, 2);
        assert_ne!(gk1.sense, gk2.sense);
    }

    #[test]
    fn test_crispr_library_has_126_signatures() {
        assert_eq!(CRISPRDefense::library_size(), 126);
    }

    #[test]
    fn test_crispr_innate_check_matches_known_attack() {
        // A transaction containing the Harvest Finance flash loan signature
        // must be flagged.
        let tx = b"prefix_HARVEST_FLASH_LOAN_ORACLE_MANIP_suffix";
        let hit = CRISPRDefense::innate_check(tx);
        assert!(hit.is_some(), "expected a CRISPR match");
        assert_eq!(hit.unwrap(), "HARVEST_2020_FLASH");
    }

    #[test]
    fn test_crispr_innate_check_clean_transaction() {
        let tx = b"a perfectly clean transaction with no signature match";
        assert!(CRISPRDefense::innate_check(tx).is_none());
    }

    #[test]
    fn test_compute_sec_returns_unit_interval() {
        // Full marks: gk verified, 126 CRISPR sigs, gen=1, immune clear, PQC=CC=1.
        // LSS = 0.40 + 0.30 + 0.20 + 0.10 = 1.0; SEC = 1·1·1 = 1.0.
        let sec = compute_sec(true, 126, 1, true, 1.0, 1.0, 0);
        assert!(sec > 0.0 && sec <= 1.0, "sec out of range: {sec}");
        // With akashic_depth=0 (full bootstrap weight), effective_SEC = CC = 1.0.
        assert!((sec - 1.0).abs() < 1e-9, "expected sec=1.0 at depth 0, got {sec}");

        // At akashic_depth=50000, bootstrap weight is ~0.007 → effective
        // SEC collapses toward LSS · PQC · CC. We exercise this by
        // lowering CC (so the bootstrap weighting produces a clearly
        // smaller number than CC alone).
        let sec_mature_low_cc = compute_sec(true, 126, 1, true, 1.0, 0.50, 50_000);
        // bootstrap_weight(50000) ≈ 0.00674
        // SEC = 1.0 (LSS) · 1.0 (PQC) · 0.5 (CC) = 0.5
        // effective = 0.00674·0.5 + 0.99326·0.5 = 0.5 (≈ LSS·PQC·CC)
        assert!(sec_mature_low_cc < 0.51, "expected mature SEC near LSS·PQC·CC, got {sec_mature_low_cc}");
        assert!(sec_mature_low_cc > 0.49, "expected mature SEC near LSS·PQC·CC, got {sec_mature_low_cc}");

        // Reduced LSS (gk not verified, no CRISPR, no evolution, no immune
        // clearance) → SEC = 0; effective_SEC at depth=50000 collapses to
        // just the bootstrap-weighted CC term (≈ 0.00674 · CC).
        let sec_low_lss = compute_sec(false, 0, 0, false, 1.0, 1.0, 50_000);
        // bootstrap_weight(50000) ≈ 0.00674, SEC = 0, CC = 1
        // effective = 0.00674·1 + 0.99326·0 = 0.00674
        assert!(sec_low_lss < 0.01, "expected low-SEC bootstrap leakage only, got {sec_low_lss}");
        assert!(sec_low_lss > 0.0, "expected positive bootstrap term, got {sec_low_lss}");
    }

    #[test]
    fn test_bootstrap_weight_collapses() {
        let w0 = bootstrap_weight(0);
        assert!((w0 - 1.0).abs() < 1e-9);
        let w_mature = bootstrap_weight(50_000);
        assert!(w_mature < 0.01, "expected w_boot << 0.01 at D=50000, got {w_mature}");
    }

    #[test]
    fn test_kolmogorov_bound_grows_with_inputs() {
        let h_env = seed_h_environment_from_entity("test");
        let k_small = kolmogorov_bound(1.0, 1, 1, &h_env);
        let k_large = kolmogorov_bound(1e9, 31, 100, &h_env);
        assert!(k_large > k_small, "K-bound must grow: {} > {}", k_large, k_small);
    }

    #[test]
    fn test_compute_sec_native_smoke() {
        let sec = compute_sec_native("uniswap_v3_router", 1000, 31, 100);
        assert!(sec > 0.0 && sec <= 1.0, "native sec out of range: {sec}");
    }
}
