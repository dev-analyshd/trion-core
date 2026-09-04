/// TRION Canonical Certificate — Move codec + structural verifier
/// =====================================================================
/// Implements the Move-VM half of docs/protocol/CANONICAL_CERTIFICATE.md
/// (the ONE canonical cross-VM consensus certificate):
///
///   • the byte-exact 346-byte signing payload P (§2 offset table),
///   • the payload-internal structural checks (§6 steps 1 and 4),
///   • freshness (§9 — issued_at/ttl against a caller-supplied clock
///     reading, so the escrow can pass `timestamp::now_seconds()`),
///   • the canonical certificate hash SHA3-256(P) (§2.1 — FIPS 202, the
///     same value core/consensus/certificate.py computes).
///
/// MOVE CAPABILITY BOUNDARY (master command §11 — documented, never
/// silently downgraded):
///   Move has no keccak256 and no Poseidon; it does not need them. §3.2
///   assigns Move signature FAMILY 2 — Ed25519 over the RAW payload P
///   (Ed25519 is its own hash; there is no pre-hash digest). Native
///   Ed25519 verification on Aptos is `aptos_std::ed25519` (strict,
///   small-subgroup rejecting) — invoked by `trion::epoch_registry`,
///   not here. Native SHA3-256 is `std::hash::sha3_256` (FIPS 202), so
///   the canonical certificate hash is recomputed ON-CHAIN with zero
///   drift from the Python reference encoder.
///
/// Purity contract: this module has NO global state, NO signer, NO coin
/// access, NO capability — it is a pure function library over
/// `vector<u8>` and is the single place that knows the §2 byte layout.
/// Every field reader is a bounds-checked big-endian read at the exact
/// canonical offset; a wrong offset here fails the py mirror test
/// (tests/contracts/test_btcp_escrow_move.py) against the golden vector
/// pinned in tests/unit/test_certificate_domain_separation.py.
///
/// Field order below is the §2 table, byte-for-byte:
///   0    13  domain_tag "TRION-CERT-V1"
///   13    1  certificate_kind        (1 = ESCROW_RELEASE)
///   14    3  protocol_version        (uint24 packed semver, BE)
///   17    4  validator_epoch         (uint32)
///   21    8  certificate_nonce       (uint64, per (epoch, escrow_id))
///   29   32  escrow_id               (destination escrow id)
///   61   32  route_id
///   93   32  intent_hash
///   125  32  entity_id
///   157   4  source_chain            (TRION registry chain id)
///   161   4  dest_chain              (TRION registry chain id)
///   165  32  destination             (canonical destination account)
///   197  32  amount                  (uint256, raw dest-native units)
///   229  32  anchor_bh
///   261  32  execution_bh
///   293   8  coherence               (×1e6)
///   301   8  threshold               (×1e6)
///   309   8  hhi_at_emission         (×1e4, 0–10000)
///   317   8  total_effective_power   (×1e6, Σ s_j·d_j)
///   325   4  validator_count
///   329   1  awa_enforced
///   330   8  issued_at               (unix seconds, consensus clock)
///   338   8  ttl                     (seconds)
///   ─────────
///   346 bytes total
module trion::canonical_cert {
    use std::vector;
    use std::hash;

    // ── §2 layout constants ────────────────────────────────────────────
    const PAYLOAD_WIDTH: u64 = 346;
    const DOMAIN_TAG: vector<u8> = b"TRION-CERT-V1";

    // Offsets (§2) — pinned by the golden vector; a change is a format
    // version bump. (3 + 4 + 8 + 4·32 + 2·4 + 32 + 8·4 + 4 + 1 + 2·8 = 346.)
    const OFF_KIND:                  u64 = 13;
    const OFF_VERSION:               u64 = 14;
    const OFF_EPOCH:                 u64 = 17;
    const OFF_NONCE:                 u64 = 21;
    const OFF_ESCROW_ID:             u64 = 29;
    const OFF_ROUTE_ID:              u64 = 61;
    const OFF_INTENT_HASH:           u64 = 93;
    const OFF_ENTITY_ID:             u64 = 125;
    const OFF_SOURCE_CHAIN:          u64 = 157;
    const OFF_DEST_CHAIN:            u64 = 161;
    const OFF_DESTINATION:           u64 = 165;
    const OFF_AMOUNT:                u64 = 197;
    const OFF_ANCHOR_BH:             u64 = 229;
    const OFF_EXECUTION_BH:          u64 = 261;
    const OFF_COHERENCE:             u64 = 293;
    const OFF_THRESHOLD:             u64 = 301;
    const OFF_HHI:                   u64 = 309;
    const OFF_TOTAL_POWER:           u64 = 317;
    const OFF_VALIDATOR_COUNT:       u64 = 325;
    const OFF_AWA:                   u64 = 329;
    const OFF_ISSUED_AT:             u64 = 330;
    const OFF_TTL:                   u64 = 338;

    const BYTES32: u64 = 32;
    // amount (uint256) occupies OFF_AMOUNT..OFF_AMOUNT+32; only the low
    // 8 bytes may be non-zero for a Move escrow (Coin values are u64).
    const AMOUNT_HIGH_BYTES: u64 = 24;

    // ── §3.2 family 2 (Ed25519 / Move) — the ONLY family this VM verifies
    const SIG_FAMILY_ED25519: u64 = 2;
    const SIG_LEN_ED25519: u64 = 64;

    // ── §6 step 1 / §4 invariants ──────────────────────────────────────
    const KIND_ESCROW_RELEASE: u64 = 1;
    const MIN_SIGNERS: u64 = 3;

    // ── §5.3 / §5.4 / §2 scale and precondition bounds ─────────────────
    const HHI_MAX_ACCEPTABLE: u64 = 4000;       // L4.8 CRITICAL tier, ×1e4
    const COHERENCE_SCALE_MAX: u64 = 1_000_000; // ×1e6 fields are ≤ 1.0

    // ── §9 freshness ───────────────────────────────────────────────────
    const CLOCK_DRIFT_TOLERANCE_SECONDS: u64 = 60; // lower bound only
    const TTL_MAX_SECONDS: u64 = 604_800;          // §9.2 one-week clamp

    const MAX_U64: u64 = 18446744073709551615;

    // ── Error codes ────────────────────────────────────────────────────
    const E_PAYLOAD_WIDTH:   u64 = 1;
    const E_DOMAIN_TAG:      u64 = 2;
    const E_UNKNOWN_KIND:    u64 = 3;
    const E_VERSION:         u64 = 4;
    const E_TTL_ZERO:        u64 = 5;
    const E_TTL_TOO_LONG:    u64 = 6;
    const E_NO_DEST_CHAIN:   u64 = 7;
    const E_AWA_NOT_ENFORCED: u64 = 8;
    const E_HHI_CRITICAL:    u64 = 9;
    const E_COHERENCE_SCALE: u64 = 10;
    const E_THRESHOLD_SCALE: u64 = 11;
    const E_NOT_SAFE:        u64 = 12;
    const E_RANGE:           u64 = 13;

    // ── Byte readers (private; bounds-checked, big-endian) ─────────────
    // All offsets used by this module are compile-time constants < 346,
    // and verify_structure pins the width first, so the E_RANGE asserts
    // below are defense-in-depth. An out-of-range read ABORTS — Move's
    // abort semantics are fail-closed (the transaction reverts).

    fun read_u8(p: &vector<u8>, off: u64): u64 {
        assert!(off < vector::length(p), E_RANGE);
        (*vector::borrow(p, off)) as u64
    }

    fun read_u24(p: &vector<u8>, off: u64): u64 {
        assert!(off + 3 <= vector::length(p), E_RANGE);
        (((*vector::borrow(p, off)) as u64) << 16) |
        (((*vector::borrow(p, off + 1)) as u64) << 8) |
        ((*vector::borrow(p, off + 2)) as u64)
    }

    fun read_u32(p: &vector<u8>, off: u64): u64 {
        assert!(off + 4 <= vector::length(p), E_RANGE);
        (((*vector::borrow(p, off)) as u64) << 24) |
        (((*vector::borrow(p, off + 1)) as u64) << 16) |
        (((*vector::borrow(p, off + 2)) as u64) << 8) |
        ((*vector::borrow(p, off + 3)) as u64)
    }

    fun read_u64(p: &vector<u8>, off: u64): u64 {
        assert!(off + 8 <= vector::length(p), E_RANGE);
        (((*vector::borrow(p, off)) as u64) << 56) |
        (((*vector::borrow(p, off + 1)) as u64) << 48) |
        (((*vector::borrow(p, off + 2)) as u64) << 40) |
        (((*vector::borrow(p, off + 3)) as u64) << 32) |
        (((*vector::borrow(p, off + 4)) as u64) << 24) |
        (((*vector::borrow(p, off + 5)) as u64) << 16) |
        (((*vector::borrow(p, off + 6)) as u64) << 8) |
        ((*vector::borrow(p, off + 7)) as u64)
    }

    fun read_bytes(p: &vector<u8>, off: u64, len: u64): vector<u8> {
        assert!(off + len <= vector::length(p), E_RANGE);
        let out = vector::empty<u8>();
        for (i in 0..len) {
            vector::push_back(&mut out, *vector::borrow(p, off + i));
        };
        out
    }

    fun domain_tag_matches(p: &vector<u8>): bool {
        read_bytes(p, 0, 13) == DOMAIN_TAG
    }

    // ── Field readers (public — the §2 view of a certificate payload) ──

    /// certificate_kind (§2, ED-K1). Unknown kinds fail closed (§6 step 1).
    public fun kind(p: &vector<u8>): u64 {
        read_u8(p, OFF_KIND)
    }

    /// protocol_version, uint24 packed semver (major<<16|minor<<8|patch).
    public fun version(p: &vector<u8>): u64 {
        read_u24(p, OFF_VERSION)
    }

    /// Supported-version gate: this verifier speaks canonical v1.x.y only
    /// (§6 step 1 "protocol_version ≤ supported max"). A v2 payload needs
    /// a module upgrade — it is rejected here, never reinterpreted.
    public fun version_supported(p: &vector<u8>): bool {
        version(p) >= 0x010000 && version(p) <= 0x01FFFF
    }

    /// validator_epoch (§2, ED-E2) — whose registered set must sign.
    public fun epoch(p: &vector<u8>): u64 {
        read_u32(p, OFF_EPOCH)
    }

    /// certificate_nonce (§2, ED-N1) — strictly increasing per
    /// (validator_epoch, escrow_id); the replay guard of §8.
    public fun nonce(p: &vector<u8>): u64 {
        read_u64(p, OFF_NONCE)
    }

    public fun escrow_id(p: &vector<u8>): vector<u8> {
        read_bytes(p, OFF_ESCROW_ID, BYTES32)
    }

    public fun route_id(p: &vector<u8>): vector<u8> {
        read_bytes(p, OFF_ROUTE_ID, BYTES32)
    }

    public fun intent_hash(p: &vector<u8>): vector<u8> {
        read_bytes(p, OFF_INTENT_HASH, BYTES32)
    }

    public fun entity_id(p: &vector<u8>): vector<u8> {
        read_bytes(p, OFF_ENTITY_ID, BYTES32)
    }

    /// source_chain — TRION registry chain id of the anchor leg (§2).
    public fun source_chain(p: &vector<u8>): u64 {
        read_u32(p, OFF_SOURCE_CHAIN)
    }

    /// dest_chain — TRION registry chain id of the execution leg (§2).
    /// Doubles as the cross-chain replay firewall (§3.3).
    public fun dest_chain(p: &vector<u8>): u64 {
        read_u32(p, OFF_DEST_CHAIN)
    }

    /// destination — the canonical 32-byte destination account (§7). On
    /// the Move family this is the 32-byte BCS encoding of an `address`
    /// (Aptos/Sui addresses are 32 bytes).
    public fun destination(p: &vector<u8>): vector<u8> {
        read_bytes(p, OFF_DESTINATION, BYTES32)
    }

    /// amount is uint256 on the wire; a Move Coin amount is u64. This
    /// checks the high 24 bytes are zero (§7 binding: exact equality with
    /// the escrow's u64 amount is checked by the escrow).
    public fun amount_fits_u64(p: &vector<u8>): bool {
        let i = OFF_AMOUNT;
        while (i < OFF_AMOUNT + AMOUNT_HIGH_BYTES && *vector::borrow(p, i) == 0) {
            i = i + 1
        };
        i == OFF_AMOUNT + AMOUNT_HIGH_BYTES
    }

    /// Low 8 bytes of the uint256 amount, big-endian.
    public fun amount_u64(p: &vector<u8>): u64 {
        read_u64(p, OFF_AMOUNT + AMOUNT_HIGH_BYTES)
    }

    public fun anchor_bh(p: &vector<u8>): vector<u8> {
        read_bytes(p, OFF_ANCHOR_BH, BYTES32)
    }

    public fun execution_bh(p: &vector<u8>): vector<u8> {
        read_bytes(p, OFF_EXECUTION_BH, BYTES32)
    }

    /// C(t) at emission, ×1e6 (§5.4).
    public fun coherence(p: &vector<u8>): u64 {
        read_u64(p, OFF_COHERENCE)
    }

    /// Θ(t) at emission, ×1e6 (§5.4).
    public fun threshold(p: &vector<u8>): u64 {
        read_u64(p, OFF_THRESHOLD)
    }

    /// HHI at emission, ×1e4 (§5.3 — > 4000 means emission was impossible).
    public fun hhi(p: &vector<u8>): u64 {
        read_u64(p, OFF_HHI)
    }

    /// Σ s_j·d_j claimed by the certificate, ×1e6 — cross-checked against
    /// the registered epoch set (§6 step 6: "the certificate lied about
    /// the set" is a rejection).
    public fun total_effective_power(p: &vector<u8>): u64 {
        read_u64(p, OFF_TOTAL_POWER)
    }

    public fun validator_count(p: &vector<u8>): u64 {
        read_u32(p, OFF_VALIDATOR_COUNT)
    }

    /// awa_enforced bit (§5.4, ED-A1) — 0 means emission was frozen.
    public fun awa_enforced(p: &vector<u8>): bool {
        read_u8(p, OFF_AWA) == 1
    }

    public fun issued_at(p: &vector<u8>): u64 {
        read_u64(p, OFF_ISSUED_AT)
    }

    public fun ttl(p: &vector<u8>): u64 {
        read_u64(p, OFF_TTL)
    }

    // ── §2.1 canonical certificate hash ────────────────────────────────
    /// SHA3-256(P), FIPS 202 — identical bytes to
    /// core/consensus/certificate.py::CanonicalCertificate.certificate_hash().
    /// This is the consumed-certificate key on Move (§7) and the value the
    /// Akashic Index records.
    public fun certificate_hash(payload: &vector<u8>): vector<u8> {
        hash::sha3_256(*payload)
    }

    // ── §6 step 1 + step 4 (payload-internal halves) ───────────────────
    /// Fail-closed structural verification of P itself. No registry, no
    /// clock, no escrow — those come next in the §6 order, in
    /// trion::epoch_registry and trion::btcp_escrow respectively.
    public fun verify_structure(payload: &vector<u8>) {
        assert!(vector::length(payload) == PAYLOAD_WIDTH, E_PAYLOAD_WIDTH);
        assert!(domain_tag_matches(payload), E_DOMAIN_TAG);
        assert!(kind(payload) == KIND_ESCROW_RELEASE, E_UNKNOWN_KIND);
        assert!(version_supported(payload), E_VERSION);
        // §9.2: ttl comes from the value-tier table — 0 is born-expired,
        // > 1 week outlives a full epoch-rotation cycle: both malformed.
        assert!(ttl(payload) > 0, E_TTL_ZERO);
        assert!(ttl(payload) <= TTL_MAX_SECONDS, E_TTL_TOO_LONG);
        // §2.3: dest_chain is the cross-VM replay firewall — 0 unbound.
        assert!(dest_chain(payload) != 0, E_NO_DEST_CHAIN);
        // §5.4 verdict preconditions (payload half).
        assert!(awa_enforced(payload), E_AWA_NOT_ENFORCED);
        assert!(hhi(payload) <= HHI_MAX_ACCEPTABLE, E_HHI_CRITICAL);
        assert!(coherence(payload) <= COHERENCE_SCALE_MAX, E_COHERENCE_SCALE);
        assert!(threshold(payload) <= COHERENCE_SCALE_MAX, E_THRESHOLD_SCALE);
        // isSafe (§5.4): C(t) ≥ Θ(t) at emission.
        assert!(coherence(payload) >= threshold(payload), E_NOT_SAFE);
    }

    // ── §9 freshness ───────────────────────────────────────────────────
    /// issued_at − 60s ≤ now ≤ issued_at + ttl, with the 60 s drift
    /// tolerance widening the LOWER bound only (consensus-time skew is
    /// tolerated; expiry never is). Overflow-safe: a ttl large enough to
    /// wrap `issued_at + ttl` is treated as not-yet-expired (mathematically
    /// correct: the sum exceeds the u64 horizon).
    public fun is_fresh_at(payload: &vector<u8>, now: u64): bool {
        let issued = issued_at(payload);
        let t = ttl(payload);
        let not_future = if (issued <= now) {
            true
        } else {
            (issued - now) <= CLOCK_DRIFT_TOLERANCE_SECONDS
        };
        let not_expired = if (issued > MAX_U64 - t) {
            true
        } else {
            now <= issued + t
        };
        not_future && not_expired
    }

    // ── §3.2 / §4 envelope constants for the Move family ───────────────
    /// The signature family this VM verifies (§3.2 family 2 — Ed25519).
    public fun expected_signature_family(): u64 {
        SIG_FAMILY_ED25519
    }

    /// Ed25519 signature width (§4 sig_len for family 2).
    public fun expected_signature_len(): u64 {
        SIG_LEN_ED25519
    }

    /// Minimum distinct signers (§4 envelope invariant 4 — liveness floor;
    /// the real bar is the weight quorum).
    public fun min_signers(): u64 {
        MIN_SIGNERS
    }

    /// The exact fixed payload width (§2) — asserted by the escrow before
    /// any byte is read.
    public fun payload_width(): u64 {
        PAYLOAD_WIDTH
    }

    /// Decode summary for observability (state field order: kind, epoch,
    /// nonce, coherence, threshold, ttl). Read-only, aborts on malformed
    /// payloads exactly like verify_structure.
    public fun summarize(payload: &vector<u8>): (u64, u64, u64, u64, u64, u64) {
        verify_structure(payload);
        (
            kind(payload),
            epoch(payload),
            nonce(payload),
            coherence(payload),
            threshold(payload),
            ttl(payload),
        )
    }
}
