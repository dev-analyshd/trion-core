//! TRION Protocol — NEAR TRION Oracle (TRIONOracleV3 equivalent)
//! =============================================================
//!
//! C-05 (CRITICAL, Wave 2 / Agent J2) closure: `publish_btcp_route` was an
//! owner/relayer-write route store — no signatures, no quorum, no epoch, no
//! freshness. The "TRION consensus is the only oracle" invariant was absent.
//! That path is GONE. Route publication is now the TRIONOracleV3
//! `submitRouteAttestation` / `submitCertificateAttestation` discipline
//! ported to NEAR against the landed canonical pattern
//! (`contracts/solidity/TRIONOracleV3.sol` + `TrionEpochRegistry` +
//! `CanonicalCertificate.sol`):
//!
//!   * `publish_btcp_route(payload, attestations)` carries P — the 346-byte
//!     canonical signing payload of `docs/protocol/CANONICAL_CERTIFICATE.md`
//!     §2, byte-for-byte the `core/consensus/certificate.py` reference —
//!     plus the Ed25519 signature chain (family 2, §3.2: the signature is
//!     over RAW P — NEAR's host `ed25519_verify` takes arbitrary-length
//!     messages, so NO digest deviation is needed, unlike TVM).
//!   * Verification follows §6 EXACTLY, in order, fail-closed:
//!     structure → epoch → freshness → consensus preconditions →
//!     signatures → quorum → binding → nonce/replay → write.
//!   * Quorum is the L4.2 tier table over REGISTERED w_j = s_j·d_j weights
//!     (×1e6 fixed point, u128 integer math — no floats, no overflow).
//!   * Threshold provenance (H-03): the certificate's signed threshold must
//!     EQUAL the epoch-registered Θ(t) — the pass bar is canonical state.
//!   * The message sender is only a TRANSPORT (relayers submit envelopes;
//!     anyone may call, nobody authorizes) — the validator quorum's
//!     signatures are the only route authority.
//!
//! Owner / registrar trust root (documented, R-4): the owner administers
//! the validator registry (master command §9 "validator governance" —
//! owner-controlled validator membership) exactly like the EVM
//! `TrionEpochRegistry` registrar: one forward-only registration per epoch
//! (epoch == latest + 1, immutable once written — no mid-epoch set swap),
//! bounded ranges, weights re-derived as s·d/1e6. The owner CANNOT forge
//! consensus: writing a route still requires a weight-quorum of Ed25519
//! signatures from the REGISTERED validator keys over the exact P.
//!
//! Clock (§9): NEAR block timestamp (ms → s). Freshness is
//! issued_at ≤ now ≤ issued_at + ttl with a 60 s drift tolerance widening
//! the LOWER bound only (consensus-time skew tolerated, expiry never).
//!
//! Consumed-key (§7 NEAR row): SHA3-256(P) — the canonical cross-VM
//! certificate hash, computed NATIVELY on NEAR via the RustCrypto `sha3`
//! crate (FIPS 202, identical to `core/consensus/certificate.py`
//! `certificate_hash()`); used for §8.2 idempotency and conflict evidence.
//!
//! HONEST UNVERIFIED BOUNDARY: no cargo/rust toolchain exists in this
//! sandbox — `cargo build` against near-sdk 5.1.0 + sha3 0.10 is the
//! documented compile boundary; the logic is pinned by the py mirror
//! `tests/contracts/test_trion_oracle_near.py` (same check order, same
//! assert messages, real ed25519 signatures over real P bytes) and by
//! static source assertions.
//!
//! DEPLOYMENT NOTE: the storage layout changed in Wave 2 (owner, epoch
//! registry, nonce registries, extended RouteRecord) — fresh-deployment
//! layout; migrate, do not upgrade in place.
//!
//! Storage layout:
//!   - `owner: AccountId`              (registrar role — R-4 trust root)
//!   - `relayer: AccountId`            (signal path only — NOT route authority)
//!   - `signals: LookupMap<String, SignalRecord>`
//!   - `routes:  LookupMap<String, RouteRecord>`   (key = hex(route_id))
//!   - `epochs:  LookupMap<u32, EpochRecord>`      (per-epoch validator state)
//!   - `validators: LookupMap<(u32, [u8;32]), ValidatorEntry>`
//!   - `highest_nonce: LookupMap<(u32, [u8;32]), u64>`   (epoch, escrow_id)
//!   - `nonce_digest: LookupMap<(u32, [u8;32]), [u8;32]>` (cert hash at nonce)
//!   - `latest_epoch: u32`, `epoch_grace: u32` (default 2, bounded 0..=10)
//!   - `signal_count: u64`, `route_count: u64`

use near_sdk::borsh::{self, BorshDeserialize, BorshSerialize};
use near_sdk::collections::LookupMap;
use near_sdk::{env, near_bindgen, AccountId, PanicOnDefault};
use sha3::{Digest, Sha3_256};

// ═══════════════════════════════════════════════════════════════════════════
// Canonical certificate constants (CANONICAL_CERTIFICATE.md §2/§4/§5/§9)
// ═══════════════════════════════════════════════════════════════════════════

/// The single most important constant — §2.
pub const PAYLOAD_WIDTH: usize = 346;
/// "TRION-CERT-V1" — the ED-DS1 domain tag (13 bytes).
pub const DOMAIN_TAG: &[u8; 13] = b"TRION-CERT-V1";
/// certificate_kind 1 = ESCROW_RELEASE (ED-K1); unknown kinds fail closed.
pub const CERT_KIND_ESCROW_RELEASE: u8 = 1;
/// Highest packed semver this verifier accepts (§6 step 1): pack(1,2,3)
/// = 0x010203 — EVM parity (CanonicalCertificate.SUPPORTEDED_PROTOCOL_VERSION).
pub const SUPPORTED_PROTOCOL_VERSION: u32 = 0x0102_03;
/// §4 invariant 4 — liveness floor (the real bar is the weight quorum).
pub const MIN_SIGNERS: usize = 3;
/// L4.8 concentration bound (0-10000 HHI scale) — above it consensus is
/// frozen and no valid emission exists.
pub const HHI_MAX_ACCEPTABLE: u64 = 4_000;
/// §9 clock drift tolerance — widens the freshness LOWER bound only.
pub const CLOCK_DRIFT_TOLERANCE: u64 = 60;
/// ×1e6 fixed-point scale of the weight/coherence/threshold fields.
pub const SCALE_1E6: u64 = 1_000_000;
/// L4.2 D_consensus tier boundaries (×1e6): ≥ 0.60 → 2/3 strict,
/// ≥ 0.40 → 0.75, else → 0.85.
pub const D_CONSENSUS_TIER1: u64 = 600_000;
pub const D_CONSENSUS_TIER2: u64 = 400_000;
/// §10.2 verifier epoch grace default (ED-G); owner-adjustable, bounded.
pub const EPOCH_GRACE_DEFAULT: u32 = 2;
pub const EPOCH_GRACE_MAX: u32 = 10;

// ═══════════════════════════════════════════════════════════════════════════
// Records
// ═══════════════════════════════════════════════════════════════════════════

#[derive(BorshDeserialize, BorshSerialize, Clone, Debug)]
pub struct SignalRecord {
    pub entity_id:    String,
    pub coherence:    u64,    // x1_000_000
    pub threshold:    u64,    // x1_000_000
    pub emits_signal: bool,
    pub timestamp:    u64,
    pub update_count: u64,
}

/// Per-epoch canonical validator state (§5, §10.2) — what the EVM
/// `TrionEpochRegistry` stores; quorum is computed from THIS, never from
/// certificate- or envelope-supplied values.
#[derive(BorshDeserialize, BorshSerialize, Clone, Debug)]
pub struct EpochRecord {
    pub d_consensus:     u64,       // mean(d_j) ×1e6 — L4.2 tier selector
    pub threshold:       u64,       // registered Θ(t) ×1e6 (H-03 provenance)
    pub hhi:             u64,       // set HHI ×1e4 (0-10000)
    pub total_power:     u64,       // Σ_j s_j·d_j ×1e6 — == cert field
    pub validator_count: u32,       // N of the epoch set — == cert field
    pub registered_at:   u64,       // unix seconds (audit)
    pub epoch_set_root:  [u8; 32],  // off-chain SHA3-256 set root (audit)
}

/// One validator's registered epoch-scoped state (§10.2).
#[derive(BorshDeserialize, BorshSerialize, Clone, Debug)]
pub struct ValidatorEntry {
    pub ed25519_pubkey:   [u8; 32],  // family-2 public key
    pub stake_weight:     u64,       // s_j ×1e6
    pub diversity_weight: u64,       // d_j ×1e6 (0..=1e6)
    pub effective_weight: u64,       // w_j = s_j·d_j/1e6 ×1e6 — re-derived
}

/// One envelope attestation (§4): the signature over RAW P plus the weight
/// CLAIMS (cross-checked against the registry at §6 step 5c — never
/// authority).
#[derive(BorshDeserialize, BorshSerialize, Clone, Debug)]
pub struct Attestation {
    pub validator_id:      [u8; 32],
    pub stake_weight:      u64,      // s_j claim ×1e6
    pub diversity_weight:  u64,      // d_j claim ×1e6
    pub signature:         [u8; 64], // ed25519 over raw P (§3.2 family 2)
}

/// The BTCP route record — now the product of a VERIFIED canonical
/// certificate (the §6 step 7 settlement tuple the quorum signed is part
/// of the record: a route can only ever re-verify for the exact
/// escrow/destination/amount it was first attested for).
#[derive(BorshDeserialize, BorshSerialize, Clone, Debug)]
pub struct RouteRecord {
    pub route_id:     String,        // hex(bytes32) — key mirror
    pub anchor_bh:    String,        // hex(bytes32)
    pub execution_bh: String,        // hex(bytes32)
    pub coherence:    u64,
    pub threshold:    u64,
    pub is_safe:      bool,
    pub timestamp:    u64,
    // canonical binding (what the quorum authorized)
    pub escrow_id:        String,    // hex(bytes32)
    pub entity_id:        String,    // hex(bytes32)
    pub intent_hash:      String,    // hex(bytes32)
    pub destination:      String,    // hex(bytes32)
    pub amount:           u128,      // raw destination-native units
    pub source_chain:     u32,
    pub dest_chain:       u32,
    pub validator_epoch:  u32,
    pub certificate_nonce: u64,
    pub certificate_hash: [u8; 32],  // SHA3-256(P) — the cross-VM id
    pub signed_power:     u128,      // Σ registered w_j over verified signers
    pub total_power:      u128,      // registered epoch total
}

// ═══════════════════════════════════════════════════════════════════════════
// Canonical payload P (§2) — strict parse, fixed offsets, big-endian
// ═══════════════════════════════════════════════════════════════════════════

pub struct ParsedCert {
    pub certificate_kind:    u8,
    pub protocol_version:    u32,
    pub validator_epoch:     u32,
    pub certificate_nonce:   u64,
    pub escrow_id:           [u8; 32],
    pub route_id:            [u8; 32],
    pub intent_hash:         [u8; 32],
    pub entity_id:           [u8; 32],
    pub source_chain:        u32,
    pub dest_chain:          u32,
    pub destination:         [u8; 32],
    pub amount:              u128,   // uint256 field, enforced ≤ u128
    pub anchor_bh:           [u8; 32],
    pub execution_bh:        [u8; 32],
    pub coherence:           u64,
    pub threshold:           u64,
    pub hhi_at_emission:     u64,
    pub total_effective_power: u64,
    pub validator_count:     u32,
    pub awa_enforced:        u8,
    pub issued_at:           u64,
    pub ttl:                 u64,
}

/// Strict §2 decode: exact width, exact domain tag, explicit big-endian
/// field reads at the pinned offsets. Any violation → None (fail closed).
pub fn parse_payload(p: &[u8]) -> Option<ParsedCert> {
    if p.len() != PAYLOAD_WIDTH {
        return None;
    }
    if &p[0..13] != DOMAIN_TAG {
        return None;
    }
    let be32 = |o: usize| -> Option<[u8; 32]> {
        let mut a = [0u8; 32];
        a.copy_from_slice(&p[o..o + 32]);
        Some(a)
    };
    let be_u32 = |o: usize| u32::from_be_bytes([p[o], p[o + 1], p[o + 2], p[o + 3]]);
    let be_u24 = |o: usize| -> u32 {
        // uint24 at o: three bytes, big-endian (major<<16|minor<<8|patch)
        ((p[o] as u32) << 16) | ((p[o + 1] as u32) << 8) | (p[o + 2] as u32)
    };
    let be_u64 = |o: usize| -> u64 {
        let mut a = [0u8; 8];
        a.copy_from_slice(&p[o..o + 8]);
        u64::from_be_bytes(a)
    };
    // amount is a uint256 field; NEAR stores u128 — the high 16 bytes must
    // be zero or the certificate is rejected (fail closed, no truncation).
    if p[197..213].iter().any(|&b| b != 0) {
        return None;
    }
    let mut amount_bytes = [0u8; 16];
    amount_bytes.copy_from_slice(&p[213..229]);
    Some(ParsedCert {
        certificate_kind:      p[13],
        protocol_version:      be_u24(14),
        validator_epoch:       be_u32(17),
        certificate_nonce:     be_u64(21),
        escrow_id:             be32(29)?,
        route_id:              be32(61)?,
        intent_hash:           be32(93)?,
        entity_id:             be32(125)?,
        source_chain:          be_u32(157),
        dest_chain:            be_u32(161),
        destination:           be32(165)?,
        amount:                u128::from_be_bytes(amount_bytes),
        anchor_bh:             be32(229)?,
        execution_bh:          be32(261)?,
        coherence:             be_u64(293),
        threshold:             be_u64(301),
        hhi_at_emission:       be_u64(309),
        total_effective_power: be_u64(317),
        validator_count:       be_u32(325),
        awa_enforced:          p[329],
        issued_at:             be_u64(330),
        ttl:                   be_u64(338),
    })
}

/// SHA3-256 (FIPS 202) of P — the canonical cross-VM certificate hash
/// (§2.1/§7 NEAR row); identical to `core/consensus/certificate.py`.
pub fn certificate_hash(payload: &[u8]) -> [u8; 32] {
    let mut h = Sha3_256::new();
    h.update(payload);
    let out = h.finalize();
    let mut a = [0u8; 32];
    a.copy_from_slice(&out);
    a
}

/// L4.2 tier quorum over REGISTERED weights (§5.2) — exact u128 integer
/// arithmetic, no floats, no division:
///   D ≥ 0.60  → 2/3 STRICT:  3·signed >  2·total (exactly-2/3 is NOT a quorum)
///   D ≥ 0.40  → 0.75:        4·signed ≥ 3·total
///   else      → 0.85:       20·signed ≥ 17·total
pub fn quorum_met(signed_power: u128, total_power: u128, d_consensus: u64) -> bool {
    if total_power == 0 {
        return false;
    }
    if d_consensus >= D_CONSENSUS_TIER1 {
        return 3 * signed_power > 2 * total_power;
    }
    if d_consensus >= D_CONSENSUS_TIER2 {
        return 4 * signed_power >= 3 * total_power;
    }
    20 * signed_power >= 17 * total_power
}

fn hex(bytes: &[u8]) -> String {
    let mut s = String::with_capacity(bytes.len() * 2);
    for b in bytes {
        s.push_str(&format!("{:02x}", b));
    }
    s
}

fn now_secs() -> u64 {
    env::block_timestamp_ms() / 1000
}

// ═══════════════════════════════════════════════════════════════════════════
// Contract
// ═══════════════════════════════════════════════════════════════════════════

#[near_bindgen]
#[derive(BorshDeserialize, BorshSerialize, PanicOnDefault)]
pub struct TRIONOracle {
    owner: AccountId,
    relayer: AccountId,
    signals: LookupMap<String, SignalRecord>,
    routes: LookupMap<String, RouteRecord>,
    epochs: LookupMap<u32, EpochRecord>,
    validators: LookupMap<(u32, [u8; 32]), ValidatorEntry>,
    highest_nonce: LookupMap<(u32, [u8; 32]), u64>,
    nonce_digest: LookupMap<(u32, [u8; 32]), [u8; 32]>,
    latest_epoch: u32,
    epoch_grace: u32,
    signal_count: u64,
    route_count: u64,
}

#[near_bindgen]
impl TRIONOracle {
    #[init]
    pub fn new(owner: AccountId, relayer: AccountId) -> Self {
        Self {
            owner,
            relayer,
            signals: LookupMap::new(b"s"),
            routes: LookupMap::new(b"r"),
            epochs: LookupMap::new(b"e"),
            validators: LookupMap::new(b"v"),
            highest_nonce: LookupMap::new(b"n"),
            nonce_digest: LookupMap::new(b"d"),
            latest_epoch: 0,
            epoch_grace: EPOCH_GRACE_DEFAULT,
            signal_count: 0,
            route_count: 0,
        }
    }

    // ── Registrar administration (owner — documented trust root R-4) ──────

    /// Register the validator set for `epoch` (§10.2 — the ONE per-epoch
    /// on-chain write; the registrar relays the TRION-consensus-signed set).
    /// STRICTLY sequential (epoch == latest + 1) and immutable once
    /// written — no mid-epoch membership swaps (forward-only rotation).
    /// This is owner-controlled validator governance (master command §9):
    /// the owner administers the registry but CANNOT forge consensus —
    /// route writes still require quorum signatures from the registered keys.
    pub fn register_epoch(
        &mut self,
        epoch: u32,
        validator_ids: Vec<[u8; 32]>,
        ed25519_pubkeys: Vec<[u8; 32]>,
        stake_weights: Vec<u64>,
        diversity_weights: Vec<u64>,
        d_consensus: u64,
        threshold: u64,
        hhi: u64,
        epoch_set_root: [u8; 32],
    ) {
        self.assert_owner();
        assert!(epoch == self.latest_epoch + 1, "REG: epoch not sequential");
        let n = validator_ids.len();
        assert!(n >= MIN_SIGNERS, "REG: epoch set too small");
        assert!(
            ed25519_pubkeys.len() == n
                && stake_weights.len() == n
                && diversity_weights.len() == n,
            "REG: shape"
        );
        assert!(d_consensus <= SCALE_1E6, "REG: d range");
        assert!(threshold <= SCALE_1E6, "REG: theta range");
        assert!(hhi <= HHI_MAX_ACCEPTABLE, "REG: hhi critical");

        let mut total_power: u128 = 0;
        let mut last: [u8; 32] = [0u8; 32];
        for i in 0..n {
            let vid = validator_ids[i];
            // dup + order in one check: strictly ascending validator ids
            assert!(vid > last, "REG: validators must be ascending & distinct");
            last = vid;
            let s = stake_weights[i];
            let d = diversity_weights[i];
            assert!(s >= 1, "REG: stake range");
            assert!(d <= SCALE_1E6, "REG: diversity range");
            // w_j = s_j·d_j carried ×1e6 (§5.1) — exact floor division,
            // py reference EpochSetEntry.effective_power() parity
            let w = ((s as u128 * d as u128) / SCALE_1E6 as u128) as u64;
            self.validators.insert(
                &(epoch, vid),
                &ValidatorEntry {
                    ed25519_pubkey: ed25519_pubkeys[i],
                    stake_weight: s,
                    diversity_weight: d,
                    effective_weight: w,
                },
            );
            total_power += w as u128;
        }
        assert!(total_power > 0, "REG: zero total power");
        assert!(total_power <= u64::MAX as u128, "REG: power range"); // cert field is u64

        self.epochs.insert(
            &epoch,
            &EpochRecord {
                d_consensus,
                threshold,
                hhi,
                total_power: total_power as u64,
                validator_count: n as u32,
                registered_at: now_secs(),
                epoch_set_root,
            },
        );
        self.latest_epoch = epoch;
        env::log_str(&format!(
            "EpochRegistered:{}:validators={}:total_power={}",
            epoch, n, total_power
        ));
    }

    /// Owner-adjustable verifier grace window (§10.2 ED-G), bounded 0..=10.
    pub fn set_epoch_grace(&mut self, grace: u32) {
        self.assert_owner();
        assert!(grace <= EPOCH_GRACE_MAX, "REG: grace too wide");
        self.epoch_grace = grace;
        env::log_str(&format!("EpochGraceUpdated:{}", grace));
    }

    pub fn set_owner(&mut self, new_owner: AccountId) {
        self.assert_owner();
        self.owner = new_owner;
    }

    /// The relayer only remains privileged for the SIGNAL path — it has NO
    /// route authority (C-05): route writes are quorum-only.
    pub fn set_relayer(&mut self, new_relayer: AccountId) {
        self.assert_owner();
        self.relayer = new_relayer;
    }

    // ── Signal path (unchanged discipline — NOT a route authority) ─────────

    /// Publish a behavioral signal for `entity_id` (relayer-gated; the
    /// thermodynamic-signal mirror of V3 publishSignal — no escrow release
    /// path consumes this on NEAR).
    pub fn publish_signal(
        &mut self,
        entity_id: String,
        coherence: u64,
        threshold: u64,
        emits: bool,
    ) {
        self.assert_relayer();
        assert!(coherence <= SCALE_1E6, "TRION: invalid coherence");
        assert!(threshold <= SCALE_1E6, "TRION: invalid threshold");

        let update_count = self.signals.get(&entity_id)
            .map(|s: SignalRecord| s.update_count + 1)
            .unwrap_or(1);
        let sig = SignalRecord {
            entity_id: entity_id.clone(),
            coherence,
            threshold,
            emits_signal: emits,
            timestamp: now_secs(),
            update_count,
        };
        self.signals.insert(&entity_id, &sig);
        self.signal_count += 1;
        env::log_str(&format!(
            "SignalPublished:{}:coh={}:thr={}:emits={}",
            entity_id, coherence, threshold, emits
        ));
    }

    // ── THE C-05 CLOSURE: canonical-certificate route publication ──────────

    /// Publish a BTCP route from a CANONICAL validator consensus certificate.
    ///
    /// PERMISSIONLESS: the caller is only a transport (a relayer may submit
    /// envelopes but NEVER authorizes) — authority is the validator
    /// quorum's Ed25519 signatures over the exact 346-byte payload P.
    /// Verification is CANONICAL_CERTIFICATE.md §6, in order, fail-closed,
    /// with NO fallback to any weaker check (no owner bypass, no
    /// relayer-gated coherence — the old C-05 path is gone).
    ///
    /// * `payload`        — the 346-byte canonical signing payload P (§2)
    /// * `attestations`   — Ed25519 signature chain (§4): distinct signers,
    ///                      SORTED ascending by validator_id, each carrying
    ///                      the weight CLAIMS cross-checked at step 5c.
    pub fn publish_btcp_route(&mut self, payload: Vec<u8>, attestations: Vec<Attestation>) {
        // §6 1. STRUCTURE — strict parse, exact width, exact domain tag.
        let cert = parse_payload(&payload)
            .unwrap_or_else(|| env::panic_str("CERT: malformed payload"));
        assert!(
            cert.certificate_kind == CERT_KIND_ESCROW_RELEASE,
            "CERT: unknown kind"
        );
        assert!(
            cert.protocol_version <= SUPPORTED_PROTOCOL_VERSION,
            "CERT: version too new"
        );
        assert!(cert.ttl > 0, "CERT: zero ttl");
        assert!(cert.dest_chain != 0, "CERT: dest chain unbound");
        assert!(
            attestations.len() >= MIN_SIGNERS,
            "CERT: below min signers"
        );

        // §6 2. EPOCH — registered + within the verifier grace window;
        // unknown, future and retired epochs all fail closed (H-01).
        let epoch = cert.validator_epoch;
        let erec = self.epochs.get(&epoch);
        assert!(erec.is_some(), "CERT: validator epoch inactive");
        let erec = erec.unwrap();
        // latest >= epoch always holds for a registered sequential epoch;
        // grace bounds age (stale sets age out even within ttl).
        assert!(
            self.latest_epoch >= epoch
                && self.latest_epoch - epoch <= self.epoch_grace,
            "CERT: validator epoch inactive"
        );

        // Registry conformance — the certificate may not lie about the set
        // (§6 steps 4/6) and Θ(t) comes from the registry, never the
        // certificate alone (H-03 threshold provenance).
        assert!(
            cert.validator_count == erec.validator_count,
            "CERT: validator count mismatch"
        );
        assert!(
            cert.total_effective_power == erec.total_power,
            "CERT: total power mismatch"
        );
        assert!(
            cert.threshold == erec.threshold,
            "CERT: threshold not from registry"
        );

        // §6 3. FRESHNESS — block timestamp clock; the drift tolerance
        // widens the LOWER bound only (future-dated consensus skew is
        // tolerated, expiry never is).
        let now = now_secs();
        assert!(
            cert.issued_at <= now + CLOCK_DRIFT_TOLERANCE,
            "CERT: future-dated"
        );
        assert!(now <= cert.issued_at + cert.ttl, "CERT: expired");

        // §6 4. CONSENSUS PRECONDITIONS.
        assert!(cert.hhi_at_emission <= HHI_MAX_ACCEPTABLE, "CERT: hhi critical");
        assert!(cert.awa_enforced == 1, "CERT: awa not enforced");
        assert!(cert.coherence >= cert.threshold, "CERT: not safe");

        // §6 5. SIGNATURES — batch fail-closed (one bad signature rejects
        // the whole certificate), sorted-distinct (the V3 discipline),
        // registry membership, claim==registered cross-check, Ed25519 over
        // RAW P via the NEAR host function (§3.2 family 2 — no digest
        // deviation on NEAR).
        let mut signed_power: u128 = 0;
        let mut last_vid: [u8; 32] = [0u8; 32];
        for att in &attestations {
            assert!(
                att.validator_id > last_vid,
                "CERT: signer ordering required"
            );
            last_vid = att.validator_id;
            let entry = self.validators.get(&(epoch, att.validator_id));
            assert!(entry.is_some(), "CERT: signer not in epoch set"); // step 5b
            let entry = entry.unwrap();
            assert!(
                att.stake_weight == entry.stake_weight
                    && att.diversity_weight == entry.diversity_weight,
                "CERT: envelope weight claim mismatch" // step 5c
            );
            let ok = env::ed25519_verify(
                &att.signature,
                &payload,
                &entry.ed25519_pubkey,
            );
            assert!(ok, "CERT: bad certificate signature"); // step 5a
            signed_power += entry.effective_weight as u128; // recomputed from REGISTRY (§5)
        }

        // §6 6. QUORUM — L4.2 tier over the REGISTERED D_consensus, u128
        // integer arithmetic (never envelope claims).
        assert!(
            quorum_met(signed_power, erec.total_power as u128, erec.d_consensus),
            "CERT: weight quorum unmet"
        );

        // §6 7. BINDING — etch-or-match the route values (a signature over
        // conflicting values for the same route_id is a dispute → reject);
        // the settlement tuple is part of the record.
        let route_key = hex(&cert.route_id);
        let existing = self.routes.get(&route_key);
        if let Some(r) = &existing {
            assert!(
                r.anchor_bh == hex(&cert.anchor_bh)
                    && r.execution_bh == hex(&cert.execution_bh)
                    && r.coherence == cert.coherence
                    && r.threshold == cert.threshold
                    && r.escrow_id == hex(&cert.escrow_id)
                    && r.entity_id == hex(&cert.entity_id)
                    && r.intent_hash == hex(&cert.intent_hash)
                    && r.destination == hex(&cert.destination)
                    && r.amount == cert.amount
                    && r.source_chain == cert.source_chain
                    && r.dest_chain == cert.dest_chain,
                "CERT: route values mismatch - disputed"
            );
        }

        // §6 8. NONCE ordering + conflict evidence (§8.2): idempotent
        // resubmission of the same certificate (same nonce AND same hash)
        // is a no-op; a same-nonce/different-hash conflict is rejected with
        // the evidence logged (real equivocation — L4.9 S1 slashing input).
        let scope = (epoch, cert.escrow_id);
        let digest = certificate_hash(&payload);
        let highest = self.highest_nonce.get(&scope).unwrap_or(0);
        if cert.certificate_nonce == highest {
            if digest == self.nonce_digest.get(&scope).unwrap_or([0u8; 32]) {
                return; // idempotent resubmission — observability only
            }
            env::log_str(&format!(
                "CertificateEquivocation:{}:{}:{}",
                hex(&cert.escrow_id), epoch, cert.certificate_nonce
            ));
            return; // conflicting certificate rejected (not recorded)
        }
        assert!(
            cert.certificate_nonce > highest,
            "CERT: stale certificate nonce"
        );

        // §6 9. WRITE — only now may the route be written.
        let record = RouteRecord {
            route_id: route_key.clone(),
            anchor_bh: hex(&cert.anchor_bh),
            execution_bh: hex(&cert.execution_bh),
            coherence: cert.coherence,
            threshold: cert.threshold,
            is_safe: cert.coherence >= cert.threshold,
            timestamp: now,
            escrow_id: hex(&cert.escrow_id),
            entity_id: hex(&cert.entity_id),
            intent_hash: hex(&cert.intent_hash),
            destination: hex(&cert.destination),
            amount: cert.amount,
            source_chain: cert.source_chain,
            dest_chain: cert.dest_chain,
            validator_epoch: epoch,
            certificate_nonce: cert.certificate_nonce,
            certificate_hash: digest,
            signed_power,
            total_power: erec.total_power as u128,
        };
        let is_new = existing.is_none();
        self.routes.insert(&route_key, &record);
        if is_new {
            self.route_count += 1;
        }
        self.highest_nonce.insert(&scope, &cert.certificate_nonce);
        self.nonce_digest.insert(&scope, &digest);
        env::log_str(&format!(
            "CertificateAttested:{}:{}:{}:{}:{}",
            hex(&cert.escrow_id), route_key, epoch, cert.certificate_nonce,
            signed_power
        ));
    }

    // ── Views ──────────────────────────────────────────────────────────────

    /// Verify execution safety for `route_id` (the escrow-side check —
    /// returns the VERIFIED verdict recorded by certificate quorum).
    /// Returns (is_safe, coherence, threshold).
    pub fn verify_execution(&self, route_id: String) -> (bool, u64, u64) {
        match self.routes.get(&route_id) {
            Some(r) => (r.is_safe, r.coherence, r.threshold),
            None => (false, 0, 0),
        }
    }

    /// The full verified route record (observability — consumers re-verify
    /// against the registry; this view is never verification authority).
    pub fn get_route(&self, route_id: String) -> Option<RouteRecord> {
        self.routes.get(&route_id)
    }

    /// Epoch registry observability (None if unregistered).
    pub fn get_epoch_info(&self, epoch: u32) -> Option<EpochRecord> {
        self.epochs.get(&epoch)
    }

    /// Validator entry observability for (epoch, validator_id).
    pub fn get_validator(&self, epoch: u32, validator_id: [u8; 32]) -> Option<ValidatorEntry> {
        self.validators.get(&(epoch, validator_id))
    }

    /// Highest consumed certificate nonce for (epoch, escrow_id) (§8.1).
    pub fn get_highest_nonce(&self, epoch: u32, escrow_id: [u8; 32]) -> u64 {
        self.highest_nonce.get(&(epoch, escrow_id)).unwrap_or(0)
    }

    pub fn latest_epoch(&self) -> u32 {
        self.latest_epoch
    }

    pub fn epoch_grace(&self) -> u32 {
        self.epoch_grace
    }

    /// Read the latest signal for `entity_id`.
    pub fn get_signal(&self, entity_id: String) -> Option<SignalRecord> {
        self.signals.get(&entity_id)
    }

    pub fn signal_count(&self) -> u64 { self.signal_count }

    pub fn route_count(&self) -> u64 { self.route_count }

    fn assert_owner(&self) {
        assert_eq!(
            env::predecessor_account_id(),
            self.owner,
            "TRION: not owner"
        );
    }

    fn assert_relayer(&self) {
        assert_eq!(
            env::predecessor_account_id(),
            self.relayer,
            "TRION: not relayer"
        );
    }
}
