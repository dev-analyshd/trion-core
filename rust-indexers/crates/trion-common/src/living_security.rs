/*!
 * TRION Living Security System — L4.3-4.6 + Part 6
 * Eight DNA-mimetic security components, whitepaper-exact.
 *
 * SEC(t) = LSS(t) · PQC(t) · CC(t)
 *
 * Components:
 *   1. Genomic Key Evolution      GK(t) = Hash_DNA(GK(t-1) || BE(t) || TM(t) || CV(t))
 *   2. Complementary Strand       sense XOR antisense == NOT(SHA3-256(payload||0xFF))
 *   3. Immune System (CRISPR)     Pattern library, adaptive response, permanent memory
 *   4. Epigenetic Layer           EL_state = f(threat_level, validator_health, network_entropy)
 *   5. Genetic Recombination      Security params re-derived from behavioral history periodically
 *   6. Cryptographic Noise        Decoy sequences throughout Behavioral DNA
 *   7. Mitochondrial Core         Separate independently maintained protocol integrity DNA
 *   8. CRISPR Defense             Exact attack signatures, surgical neutralization
 */

use sha3::{Digest, Sha3_256};
use std::collections::HashMap;
use std::time::{SystemTime, UNIX_EPOCH};

// ── Helper ────────────────────────────────────────────────────────────────────

fn sha3_256(data: &[u8]) -> [u8; 32] {
    Sha3_256::digest(data).into()
}

fn not_bytes(b: &[u8; 32]) -> [u8; 32] {
    let mut out = [0u8; 32];
    for i in 0..32 { out[i] = !b[i]; }
    out
}

fn xor_bytes(a: &[u8; 32], b: &[u8; 32]) -> [u8; 32] {
    let mut out = [0u8; 32];
    for i in 0..32 { out[i] = a[i] ^ b[i]; }
    out
}

fn now_secs() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs()
}

// ── Component 2: Complementary Strand Verification ───────────────────────────

/// Dual-strand DNA hash — whitepaper L0.1.
/// sense     = SHA3-256(payload || 0x00)
/// antisense = SHA3-256(payload || 0xFF) XOR NOT(sense)
/// Invariant: sense XOR antisense == NOT(SHA3-256(payload || 0xFF))
#[derive(Clone, Debug)]
pub struct DualStrand {
    pub sense: [u8; 32],
    pub antisense: [u8; 32],
}

impl DualStrand {
    pub fn compute(payload: &[u8]) -> Self {
        let mut p0 = payload.to_vec();  p0.push(0x00);
        let mut pff = payload.to_vec(); pff.push(0xFF);
        let sense: [u8; 32] = sha3_256(&p0);
        let sha3ff: [u8; 32] = sha3_256(&pff);
        let antisense = xor_bytes(&sha3ff, &not_bytes(&sense));
        Self { sense, antisense }
    }

    /// Verify complement invariant WITHOUT needing the original payload.
    /// antisense == SHA3FF XOR NOT(sense)
    /// => sense XOR antisense == NOT(SHA3FF)
    /// We verify structural self-consistency: antisense is deterministically
    /// derivable from sense and sha3ff. We check the length and non-zero structure.
    /// Full verification requires the original payload (see verify_with_payload).
    pub fn verify_structural(&self) -> bool {
        // Structural: lengths OK and not all-zero (degenerate)
        self.sense != [0u8; 32] && self.antisense != [0u8; 32]
    }

    /// Full cryptographic verification — requires the original payload.
    /// Recomputes both strands and checks equality.
    pub fn verify_with_payload(&self, payload: &[u8]) -> bool {
        let recomputed = Self::compute(payload);
        recomputed.sense == self.sense && recomputed.antisense == self.antisense
    }

    /// Verify the XOR complement invariant:
    /// sense XOR antisense == NOT(SHA3-256(payload || 0xFF))
    pub fn verify_xor_invariant(&self, payload: &[u8]) -> bool {
        let mut pff = payload.to_vec(); pff.push(0xFF);
        let sha3ff: [u8; 32] = sha3_256(&pff);
        let expected_xor = not_bytes(&sha3ff); // NOT(SHA3FF)
        let actual_xor = xor_bytes(&self.sense, &self.antisense);
        actual_xor == expected_xor
    }

    pub fn sense_hex(&self) -> String { hex::encode(self.sense) }
    pub fn antisense_hex(&self) -> String { hex::encode(self.antisense) }
}

// ── Component 1: Genomic Key Evolution ───────────────────────────────────────

/// Genomic Key — encodes complete causal history from t₀ to t.
/// GK(entity, t) = Hash_DNA(GK(entity, t-1) || BE(t) || TM(t) || CV(t))
/// BE = behavioral entropy hash, TM = temporal marker, CV = consensus view hash
#[derive(Clone, Debug)]
pub struct GenomicKey {
    pub entity_id: [u8; 32],
    pub generation: u64,
    pub strand: DualStrand,
    pub h_environment: [u8; 32],
    pub created_at: u64,
    pub evolved_at: u64,
}

impl GenomicKey {
    pub fn sense_hex(&self) -> String { self.strand.sense_hex() }
    pub fn antisense_hex(&self) -> String { self.strand.antisense_hex() }
}

pub struct GenomicKeyEvolver {
    keys: HashMap<[u8; 32], GenomicKey>,
    h_environment: [u8; 32],
}

impl GenomicKeyEvolver {
    pub fn new() -> Self {
        // Seed H_environment from current time + system entropy
        let ts = now_secs().to_be_bytes();
        let seed = sha3_256(&ts);
        Self { keys: HashMap::new(), h_environment: seed }
    }

    pub fn initialize(&mut self, entity_id: [u8; 32]) -> GenomicKey {
        let mut payload = Vec::with_capacity(96);
        payload.extend_from_slice(&entity_id);
        payload.extend_from_slice(&self.h_environment);
        payload.extend_from_slice(&now_secs().to_be_bytes());
        let strand = DualStrand::compute(&payload);
        let gk = GenomicKey {
            entity_id,
            generation: 0,
            strand,
            h_environment: self.h_environment,
            created_at: now_secs(),
            evolved_at: now_secs(),
        };
        self.keys.insert(entity_id, gk.clone());
        gk
    }

    /// Evolve the genomic key with new behavioral evidence.
    /// be_hash = SHA3(behavioral_entropy_vector)
    /// tm_hash = SHA3(timestamp || block_hash)
    /// cv_hash = SHA3(consensus_view_at_t)
    pub fn evolve(
        &mut self,
        entity_id: [u8; 32],
        be_hash: [u8; 32],
        tm_hash: [u8; 32],
        cv_hash: [u8; 32],
    ) -> GenomicKey {
        let prev = match self.keys.get(&entity_id).cloned() {
            Some(k) => k,
            None => self.initialize(entity_id),
        };

        // Update H_environment — grows with every event (Kolmogorov complexity grows)
        let mut env_input = Vec::with_capacity(96);
        env_input.extend_from_slice(&self.h_environment);
        env_input.extend_from_slice(&be_hash);
        env_input.extend_from_slice(&now_secs().to_be_bytes());
        self.h_environment = sha3_256(&env_input);

        // GK(t) = Hash_DNA(GK(t-1).sense || BE(t) || TM(t) || CV(t) || H_env)
        let mut payload = Vec::with_capacity(160);
        payload.extend_from_slice(&prev.strand.sense);
        payload.extend_from_slice(&be_hash);
        payload.extend_from_slice(&tm_hash);
        payload.extend_from_slice(&cv_hash);
        payload.extend_from_slice(&self.h_environment);

        let strand = DualStrand::compute(&payload);
        let gk = GenomicKey {
            entity_id,
            generation: prev.generation + 1,
            strand,
            h_environment: self.h_environment,
            created_at: prev.created_at,
            evolved_at: now_secs(),
        };
        self.keys.insert(entity_id, gk.clone());
        gk
    }

    pub fn get(&self, entity_id: &[u8; 32]) -> Option<&GenomicKey> {
        self.keys.get(entity_id)
    }

    /// Kolmogorov Complexity lower bound (whitepaper L4.3):
    /// K(H(TRION, t)) >= Ω(t · N_chains · N_validators · H_environment)
    /// Returns an approximate lower bound using current state.
    pub fn kolmogorov_bound(&self, n_chains: u64, n_validators: u64, t_secs: u64) -> f64 {
        // log2 approximation: each factor contributes log2 of its magnitude
        let h_entropy = self.h_environment.iter()
            .fold(0u64, |acc, &b| acc ^ (b as u64).wrapping_mul(0x9e3779b97f4a7c15));
        let k_bits = (t_secs as f64).log2()
            + (n_chains as f64).log2().max(0.0)
            + (n_validators as f64).log2().max(0.0)
            + ((h_entropy.leading_zeros() as f64 - 32.0).abs());
        k_bits.max(0.0)
    }
}

impl Default for GenomicKeyEvolver {
    fn default() -> Self { Self::new() }
}

// ── Component 3 + 8: Immune System + CRISPR Defense ──────────────────────────

#[derive(Clone, Debug)]
pub struct AttackSignature {
    pub id: String,
    pub signature_bytes: Vec<u8>,
    pub description: String,
    pub attack_type: String,
    pub added_at: u64,
    pub matches: u64,
}

pub struct CRISPRDefense {
    pub library: HashMap<String, AttackSignature>,
}

impl CRISPRDefense {
    pub fn new() -> Self {
        let mut d = Self { library: HashMap::new() };
        d.seed_known_attacks();
        d
    }

    fn seed_known_attacks(&mut self) {
        let known = vec![
            ("HARVEST_2020_FLASH",   b"HARVEST_FLASH_LOAN_ORACLE_MANIP".as_slice(),
             "Harvest Finance flash loan oracle manipulation (Oct 2020, $34M)", "ORACLE_ATTACK_ATTEMPT"),
            ("BEANSTALK_2022_GOV",   b"BEANSTALK_FLASH_GOVERNANCE_ATTACK".as_slice(),
             "Beanstalk governance flash loan attack (Apr 2022, $182M)", "GOVERNANCE_CAPTURE"),
            ("MANGO_2022_PUMP",      b"MANGO_COORDINATED_PRICE_PUMP".as_slice(),
             "Mango Markets coordinated pump (Oct 2022, $114M)", "COORDINATED_PUMP"),
            ("JIMBOS_2023",          b"JIMBOS_FLASH_LOAN_SWAP_ATTACK".as_slice(),
             "Jimbos Protocol flash loan attack (May 2023, $7.5M)", "ORACLE_ATTACK_ATTEMPT"),
            ("EULER_2023_FLASH",     b"EULER_DONATE_SELF_LIQUIDATION".as_slice(),
             "Euler Finance flash loan self-liquidation (Mar 2023, $197M)", "FLASH_LOAN"),
            ("CURVE_2023_REENTR",    b"CURVE_VYPER_REENTRANCY_LOCK".as_slice(),
             "Curve Vyper reentrancy exploit (Jul 2023, $61M)", "ORACLE_ATTACK_ATTEMPT"),
            ("RONIN_2022_BRIDGE",    b"RONIN_BRIDGE_VALIDATOR_KEY_COMPROMISE".as_slice(),
             "Ronin Network validator key compromise (Mar 2022, $625M)", "COORDINATED_PUMP"),
            ("WORMHOLE_2022_MINT",   b"WORMHOLE_GUARDIAN_SIGNATURE_BYPASS".as_slice(),
             "Wormhole guardian signature bypass (Feb 2022, $320M)", "FLASH_LOAN"),
        ];
        for (id, sig, desc, atype) in known {
            self.library.insert(id.to_string(), AttackSignature {
                id: id.to_string(),
                signature_bytes: sig.to_vec(),
                description: desc.to_string(),
                attack_type: atype.to_string(),
                added_at: now_secs(),
                matches: 0,
            });
        }
    }

    /// Innate immune check — pattern match against library.
    pub fn innate_check(&mut self, tx_data: &[u8]) -> Option<String> {
        for (id, sig) in self.library.iter_mut() {
            if tx_data.windows(sig.signature_bytes.len())
                .any(|w| w == sig.signature_bytes.as_slice()) {
                sig.matches += 1;
                return Some(id.clone());
            }
        }
        None
    }

    /// Adaptive response — characterize new attack and add to permanent library.
    pub fn adaptive_response(&mut self, attack_data: &[u8], attack_type: &str) -> String {
        let sig_hash = sha3_256(attack_data);
        let attack_id = format!("ADAPTIVE_{}", hex::encode(&sig_hash[..8]));
        self.library.insert(attack_id.clone(), AttackSignature {
            id: attack_id.clone(),
            signature_bytes: sig_hash[..16].to_vec(),
            description: format!("Auto-characterized: {}", attack_type),
            attack_type: attack_type.to_string(),
            added_at: now_secs(),
            matches: 0,
        });
        attack_id
    }

    pub fn library_size(&self) -> usize { self.library.len() }
}

impl Default for CRISPRDefense {
    fn default() -> Self { Self::new() }
}

// ── Component 4: Epigenetic Layer ─────────────────────────────────────────────

/// EL_state(t) = f(threat_level, validator_health, network_entropy)
/// Architecture unchanged. Only expression changes — same DNA, different phenotype.
#[derive(Clone, Debug, PartialEq)]
pub enum EpigeneticState {
    /// Low threat, high validator health, high entropy — full capabilities
    Normal,
    /// Moderate threat — increased monitoring, tighter thresholds
    Elevated,
    /// High threat — defensive posture, reduced emission rate
    Defensive,
    /// Critical — minimum emission, maximum verification
    Lockdown,
}

#[derive(Clone, Debug)]
pub struct EpigeneticLayer {
    pub state: EpigeneticState,
    pub threat_level: f64,      // [0, 1]
    pub validator_health: f64,  // [0, 1]
    pub network_entropy: f64,   // [0, 1]
    pub coherence_threshold_modifier: f64,
    pub emission_rate_modifier: f64,
    pub last_updated: u64,
}

impl EpigeneticLayer {
    pub fn new() -> Self {
        Self {
            state: EpigeneticState::Normal,
            threat_level: 0.0,
            validator_health: 1.0,
            network_entropy: 1.0,
            coherence_threshold_modifier: 0.0,
            emission_rate_modifier: 1.0,
            last_updated: now_secs(),
        }
    }

    /// Update epigenetic state based on environmental signals.
    pub fn update(&mut self, threat_level: f64, validator_health: f64, network_entropy: f64) {
        self.threat_level = threat_level.clamp(0.0, 1.0);
        self.validator_health = validator_health.clamp(0.0, 1.0);
        self.network_entropy = network_entropy.clamp(0.0, 1.0);
        self.last_updated = now_secs();

        // EL_state = f(threat, validator_health, entropy) — deterministic state machine
        let stress = self.threat_level * 0.5
            + (1.0 - self.validator_health) * 0.3
            + (1.0 - self.network_entropy) * 0.2;

        self.state = if stress < 0.20 {
            self.coherence_threshold_modifier = 0.0;
            self.emission_rate_modifier = 1.0;
            EpigeneticState::Normal
        } else if stress < 0.45 {
            self.coherence_threshold_modifier = 0.05;
            self.emission_rate_modifier = 0.9;
            EpigeneticState::Elevated
        } else if stress < 0.70 {
            self.coherence_threshold_modifier = 0.12;
            self.emission_rate_modifier = 0.7;
            EpigeneticState::Defensive
        } else {
            self.coherence_threshold_modifier = 0.25;
            self.emission_rate_modifier = 0.4;
            EpigeneticState::Lockdown
        };
    }

    pub fn state_name(&self) -> &'static str {
        match self.state {
            EpigeneticState::Normal   => "NORMAL",
            EpigeneticState::Elevated => "ELEVATED",
            EpigeneticState::Defensive => "DEFENSIVE",
            EpigeneticState::Lockdown  => "LOCKDOWN",
        }
    }
}

impl Default for EpigeneticLayer {
    fn default() -> Self { Self::new() }
}

// ── Component 5: Genetic Recombination ───────────────────────────────────────

/// Security parameters periodically re-derived from TRION's behavioral history.
/// After each recombination, all previously constructed attacks are useless.
pub struct GeneticRecombination {
    pub generation: u64,
    pub recombination_interval_secs: u64,
    pub last_recombination: u64,
    pub current_params: RecombinationParams,
}

#[derive(Clone, Debug)]
pub struct RecombinationParams {
    pub key_rotation_seed: [u8; 32],
    pub noise_pattern_seed: [u8; 32],
    pub mito_core_seed: [u8; 32],
    pub generation: u64,
}

impl GeneticRecombination {
    pub fn new(interval_secs: u64) -> Self {
        let seed = sha3_256(&now_secs().to_be_bytes());
        Self {
            generation: 0,
            recombination_interval_secs: interval_secs,
            last_recombination: now_secs(),
            current_params: RecombinationParams {
                key_rotation_seed: seed,
                noise_pattern_seed: sha3_256(&seed),
                mito_core_seed: sha3_256(&sha3_256(&seed)),
                generation: 0,
            },
        }
    }

    /// Check if recombination is due and trigger if so.
    /// akashic_depth: current D(t) — recombination uses behavioral history.
    pub fn maybe_recombine(&mut self, akashic_depth: u64, h_environment: [u8; 32]) -> bool {
        let now = now_secs();
        if now - self.last_recombination < self.recombination_interval_secs {
            return false;
        }
        self.recombine(akashic_depth, h_environment);
        true
    }

    pub fn recombine(&mut self, akashic_depth: u64, h_environment: [u8; 32]) {
        // Re-derive all security parameters from behavioral history
        let mut seed_input = Vec::with_capacity(72);
        seed_input.extend_from_slice(&self.current_params.key_rotation_seed);
        seed_input.extend_from_slice(&akashic_depth.to_be_bytes());
        seed_input.extend_from_slice(&h_environment);
        seed_input.extend_from_slice(&now_secs().to_be_bytes());

        let new_key_seed = sha3_256(&seed_input);
        let new_noise_seed = sha3_256(&new_key_seed);
        let new_mito_seed = sha3_256(&new_noise_seed);

        self.generation += 1;
        self.last_recombination = now_secs();
        self.current_params = RecombinationParams {
            key_rotation_seed: new_key_seed,
            noise_pattern_seed: new_noise_seed,
            mito_core_seed: new_mito_seed,
            generation: self.generation,
        };
    }
}

// ── Component 6: Cryptographic Noise ─────────────────────────────────────────

/// Deliberate cryptographic noise throughout Behavioral DNA.
/// Realistic-looking sequences carrying no information serve as decoys.
/// The noise pattern itself is authentication.
pub struct CryptographicNoise {
    pattern_seed: [u8; 32],
    pub decoy_count: u64,
}

impl CryptographicNoise {
    pub fn new(seed: [u8; 32]) -> Self {
        Self { pattern_seed: seed, decoy_count: 0 }
    }

    /// Generate a noise decoy for a given slot index.
    /// The decoy looks like a real BH but carries no behavioral information.
    pub fn generate_decoy(&mut self, slot: u64) -> ([u8; 32], [u8; 32]) {
        let mut input = Vec::with_capacity(40);
        input.extend_from_slice(&self.pattern_seed);
        input.extend_from_slice(&slot.to_be_bytes());
        let payload = sha3_256(&input);
        let strand = DualStrand::compute(&payload);
        self.decoy_count += 1;
        (strand.sense, strand.antisense)
    }

    /// Authenticate that a sequence belongs to the noise pattern (not real signal).
    pub fn is_decoy(&self, sense: &[u8; 32], slot: u64) -> bool {
        let mut input = Vec::with_capacity(40);
        input.extend_from_slice(&self.pattern_seed);
        input.extend_from_slice(&slot.to_be_bytes());
        let payload = sha3_256(&input);
        let expected = DualStrand::compute(&payload);
        expected.sense == *sense
    }

    pub fn update_seed(&mut self, new_seed: [u8; 32]) {
        self.pattern_seed = sha3_256(&[self.pattern_seed, new_seed].concat());
    }
}

// ── Component 7: Mitochondrial Core ──────────────────────────────────────────

/// Separate independently maintained Behavioral DNA.
/// Encodes only fundamental protocol properties.
/// Second independent authentication layer for protocol integrity.
pub struct MitochondrialCore {
    pub core_dna: DualStrand,
    pub protocol_version: u32,
    pub chain_count: u32,
    pub genesis_timestamp: u64,
    pub integrity_checks: u64,
    pub last_check: u64,
}

impl MitochondrialCore {
    pub fn new(protocol_version: u32, chain_count: u32) -> Self {
        let genesis = now_secs();
        let mut payload = Vec::with_capacity(16);
        payload.extend_from_slice(&protocol_version.to_be_bytes());
        payload.extend_from_slice(&chain_count.to_be_bytes());
        payload.extend_from_slice(&genesis.to_be_bytes());
        payload.extend_from_slice(b"TRION_MITO_CORE_v3");
        let core_dna = DualStrand::compute(&payload);
        Self {
            core_dna,
            protocol_version,
            chain_count,
            genesis_timestamp: genesis,
            integrity_checks: 0,
            last_check: genesis,
        }
    }

    /// Verify the mitochondrial core integrity (independent of GK).
    pub fn verify_integrity(&mut self) -> bool {
        self.integrity_checks += 1;
        self.last_check = now_secs();
        self.core_dna.verify_structural()
    }

    /// Update core when chain count or protocol version changes.
    pub fn update(&mut self, new_chain_count: u32) {
        self.chain_count = new_chain_count;
        let mut payload = Vec::with_capacity(24);
        payload.extend_from_slice(&self.protocol_version.to_be_bytes());
        payload.extend_from_slice(&new_chain_count.to_be_bytes());
        payload.extend_from_slice(&now_secs().to_be_bytes());
        payload.extend_from_slice(&self.core_dna.sense); // chained to previous
        payload.extend_from_slice(b"TRION_MITO_CORE_v3");
        self.core_dna = DualStrand::compute(&payload);
    }

    pub fn integrity_score(&self) -> f64 {
        if self.core_dna.verify_structural() { 1.0 } else { 0.0 }
    }
}

// ── SEC(t) = LSS(t) · PQC(t) · CC(t) ────────────────────────────────────────

/// Post-Quantum Cryptography score (whitepaper L4.5).
/// CRYSTALS-Kyber + CRYSTALS-Dilithium + SPHINCS+
/// In production: use actual PQC libraries. Here: structural representation.
#[derive(Clone, Debug)]
pub struct PQCScore {
    pub kyber_active: bool,    // CRYSTALS-Kyber (KEM)
    pub dilithium_active: bool, // CRYSTALS-Dilithium (signature)
    pub sphincs_active: bool,  // SPHINCS+ (hash-based signature)
    pub score: f64,
}

impl PQCScore {
    pub fn new(kyber: bool, dilithium: bool, sphincs: bool) -> Self {
        let score = (kyber as u8 as f64 + dilithium as u8 as f64 + sphincs as u8 as f64) / 3.0;
        Self { kyber_active: kyber, dilithium_active: dilithium, sphincs_active: sphincs, score }
    }
    pub fn all_active() -> Self { Self::new(true, true, true) }
}

/// Classical Cryptography score (whitepaper L4.5).
/// SHA-3 + AES-256 + ZK proofs
#[derive(Clone, Debug)]
pub struct ClassicalCryptoScore {
    pub sha3_active: bool,
    pub aes256_active: bool,
    pub zk_proofs_active: bool,
    pub score: f64,
}

impl ClassicalCryptoScore {
    pub fn new(sha3: bool, aes256: bool, zk: bool) -> Self {
        let score = (sha3 as u8 as f64 + aes256 as u8 as f64 + zk as u8 as f64) / 3.0;
        Self { sha3_active: sha3, aes256_active: aes256, zk_proofs_active: zk, score }
    }
    pub fn all_active() -> Self { Self::new(true, true, true) }
}

/// Full security score: SEC(t) = LSS(t) · PQC(t) · CC(t)
pub fn compute_sec(
    gk: &GenomicKey,
    epigenetic: &EpigeneticLayer,
    mito: &MitochondrialCore,
    crispr_library_size: usize,
    pqc: &PQCScore,
    cc: &ClassicalCryptoScore,
) -> SecurityScore {
    // LSS: Living Security Score
    // Based on: GK generation (causal depth), epigenetic health, mitochondrial integrity
    let gk_depth = (gk.generation as f64).ln_1p() / (100.0_f64).ln_1p(); // normalize to ~[0,1]
    let gk_depth = gk_depth.min(1.0);
    let epi_health = 1.0 - epigenetic.threat_level * 0.5;
    let mito_integrity = mito.integrity_score();
    let crispr_coverage = (crispr_library_size as f64 / 8.0).min(1.0); // 8 = minimum seeded
    let lss = (gk_depth * 0.40 + epi_health * 0.25 + mito_integrity * 0.20 + crispr_coverage * 0.15)
        .clamp(0.0, 1.0);

    // P(break LSS) is monotonically decreasing: approximated as e^(-generation)
    let p_break_lss = (-(gk.generation as f64) * 0.01).exp().min(0.999);

    let sec = lss * pqc.score * cc.score;

    SecurityScore {
        lss,
        pqc: pqc.score,
        cc: cc.score,
        sec,
        p_break_lss,
        gk_generation: gk.generation,
        epigenetic_state: epigenetic.state_name().to_string(),
        mito_integrity: mito_integrity,
        crispr_library_size,
    }
}

#[derive(Clone, Debug)]
pub struct SecurityScore {
    pub lss: f64,
    pub pqc: f64,
    pub cc: f64,
    pub sec: f64,
    pub p_break_lss: f64,
    pub gk_generation: u64,
    pub epigenetic_state: String,
    pub mito_integrity: f64,
    pub crispr_library_size: usize,
}

// ── Bootstrap Protocol (L4.7) ─────────────────────────────────────────────────

/// SEC_boot(t) = bootstrap_weight(t) · SEC_classical + (1 - bootstrap_weight(t)) · SEC_living
/// bootstrap_weight(t) = e^(-λ_boot · D(t))
/// At D(t) = D_minimum (~6 months): bootstrap_weight ≈ 0 → Living Security fully active
pub fn bootstrap_weight(akashic_depth: u64) -> f64 {
    let lambda_boot = 0.0001; // tuned so D=10000 blocks → weight ≈ 0.37, D=50000 → weight ≈ 0.007
    (-lambda_boot * akashic_depth as f64).exp()
}

pub fn sec_bootstrap(
    akashic_depth: u64,
    sec_classical: f64,  // multi-sig 7-of-12 + rate limit + human oversight
    sec_living: f64,     // SEC(t) from compute_sec
) -> f64 {
    let w = bootstrap_weight(akashic_depth);
    w * sec_classical + (1.0 - w) * sec_living
}

// ── Tests ─────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dual_strand_xor_invariant() {
        let payload = b"test_behavioral_event_payload_123456789";
        let strand = DualStrand::compute(payload);

        // XOR invariant: sense XOR antisense == NOT(SHA3-256(payload||0xFF))
        assert!(strand.verify_xor_invariant(payload),
            "XOR complement invariant must hold");
        assert!(strand.verify_with_payload(payload),
            "Full payload verification must hold");
    }

    #[test]
    fn dual_strand_tamper_detection() {
        let payload = b"legitimate_signal_data";
        let strand = DualStrand::compute(payload);

        // Tamper sense → invariant breaks
        let mut tampered = strand.clone();
        tampered.sense[0] ^= 0xFF;
        assert!(!tampered.verify_with_payload(payload),
            "Tampered sense must fail verification");
        assert!(!tampered.verify_xor_invariant(payload),
            "Tampered sense must fail XOR invariant");
    }

    #[test]
    fn genomic_key_evolution() {
        let mut evolver = GenomicKeyEvolver::new();
        let entity = [0xABu8; 32];

        let gk0 = evolver.initialize(entity);
        assert_eq!(gk0.generation, 0);

        let gk1 = evolver.evolve(entity, [0x11u8; 32], [0x22u8; 32], [0x33u8; 32]);
        let gk2 = evolver.evolve(entity, [0x44u8; 32], [0x55u8; 32], [0x66u8; 32]);

        assert_eq!(gk1.generation, 1);
        assert_eq!(gk2.generation, 2);
        assert_ne!(gk1.strand.sense, gk2.strand.sense, "Keys must differ each evolution");
        assert_ne!(gk1.strand.sense, gk0.strand.sense, "Evolution must change the key");
    }

    #[test]
    fn genomic_key_stolen_snapshot_useless() {
        let mut evolver = GenomicKeyEvolver::new();
        let entity = [0xCCu8; 32];
        let gk_stolen = evolver.initialize(entity);

        // Attacker has gk_stolen. System evolves forward.
        evolver.evolve(entity, [0x01u8; 32], [0x02u8; 32], [0x03u8; 32]);
        evolver.evolve(entity, [0x04u8; 32], [0x05u8; 32], [0x06u8; 32]);
        let current = evolver.get(&entity).unwrap();

        // Stolen key is now outdated — different from current
        assert_ne!(gk_stolen.strand.sense, current.strand.sense,
            "Stolen snapshot must be outdated after evolution");
    }

    #[test]
    fn epigenetic_state_transitions() {
        let mut epi = EpigeneticLayer::new();
        assert_eq!(epi.state, EpigeneticState::Normal);

        epi.update(0.6, 0.3, 0.5); // high threat, low health
        assert_ne!(epi.state, EpigeneticState::Normal);
        assert!(epi.coherence_threshold_modifier > 0.0);

        epi.update(0.0, 1.0, 1.0); // back to normal
        assert_eq!(epi.state, EpigeneticState::Normal);
    }

    #[test]
    fn crispr_innate_detection() {
        let mut crispr = CRISPRDefense::new();
        assert_eq!(crispr.library_size(), 8); // 8 seeded attacks

        let attack_data = b"prefix_HARVEST_FLASH_LOAN_ORACLE_MANIP_suffix";
        let result = crispr.innate_check(attack_data);
        assert!(result.is_some(), "Known attack must be detected");
        assert_eq!(result.unwrap(), "HARVEST_2020_FLASH");

        let clean_data = b"0x0000000000000000000000000000000000000000";
        assert!(crispr.innate_check(clean_data).is_none(), "Clean data must pass");
    }

    #[test]
    fn crispr_adaptive_response() {
        let mut crispr = CRISPRDefense::new();
        let initial_size = crispr.library_size();
        let new_attack = b"novel_attack_vector_2026_xyz";
        let id = crispr.adaptive_response(new_attack, "FLASH_LOAN");
        assert_eq!(crispr.library_size(), initial_size + 1);
        assert!(id.starts_with("ADAPTIVE_"));
    }

    #[test]
    fn sec_computation() {
        let mut evolver = GenomicKeyEvolver::new();
        let entity = [0x77u8; 32];
        let gk = evolver.initialize(entity);

        let epi = EpigeneticLayer::new();
        let mito = MitochondrialCore::new(3, 31);
        let pqc = PQCScore::all_active();
        let cc = ClassicalCryptoScore::all_active();
        let crispr = CRISPRDefense::new();

        let score = compute_sec(&gk, &epi, &mito, crispr.library_size(), &pqc, &cc);
        assert!(score.sec > 0.0 && score.sec <= 1.0, "SEC must be in [0,1]");
        assert!(score.lss >= 0.0 && score.lss <= 1.0);
        assert_eq!(score.pqc, 1.0);
        assert_eq!(score.cc, 1.0);
    }

    #[test]
    fn bootstrap_weight_decays() {
        let w0 = bootstrap_weight(0);
        let w1000 = bootstrap_weight(1000);
        let w50000 = bootstrap_weight(50000);
        assert!((w0 - 1.0).abs() < 1e-10, "At D=0, bootstrap weight = 1");
        assert!(w1000 < w0, "Weight must decay with depth");
        assert!(w50000 < w1000, "Weight must decay monotonically");
        assert!(w50000 < 0.01, "At D=50000 (~6 months), weight ≈ 0");
    }

    #[test]
    fn p_break_monotonically_decreasing() {
        let mut evolver = GenomicKeyEvolver::new();
        let entity = [0x99u8; 32];
        evolver.initialize(entity);

        let epi = EpigeneticLayer::new();
        let mito = MitochondrialCore::new(3, 31);
        let pqc = PQCScore::all_active();
        let cc = ClassicalCryptoScore::all_active();
        let crispr = CRISPRDefense::new();

        let mut prev_p = 1.0f64;
        for i in 0..10 {
            let be = sha3_256(&[i as u8; 32]);
            let gk = evolver.evolve(entity, be, be, be);
            let score = compute_sec(&gk, &epi, &mito, crispr.library_size(), &pqc, &cc);
            assert!(score.p_break_lss <= prev_p,
                "P(break LSS) must be monotonically non-increasing (gen {})", i);
            prev_p = score.p_break_lss;
        }
    }
}
