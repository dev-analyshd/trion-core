/// TRION Protocol — Canonical Certificate, family 3 (Starknet / Cairo)
/// ====================================================================
/// TWIN FILE — byte-identical copies live at
///   contracts/starknet/src/trion_certificate.cairo  (this file)
///   contracts/cairo/src/trion_certificate.cairo     (the twin)
/// Identity is enforced by tests/contracts/test_btcp_escrow_cairo.py.
/// NEVER edit one copy without the other.
///
/// Reference: docs/protocol/CANONICAL_CERTIFICATE.md (Wave 1, Agent E) and
/// the normative Python encoder core/consensus/certificate.py. This module
/// implements the STARKNET / CAIRO family-3 leg of §3.2:
///
///   P (the 346-byte canonical payload, §2) is chunked into felts:
///       f_i = big-endian bytes [31·i, 31·(i+1)) of P,  346 bytes → 12 felts
///         (11 full 31-byte chunks + a final 5-byte chunk read as one
///          integer — chunk widths are FIXED by the format, so the chunking
///          is injective and rebuilds P exactly).
///   domain_felt = felt("TRION-CERT-V1")   — 13-char short string, one felt
///   D_stark     = Poseidon(domain_felt, f_0 .. f_11)
///   signature   = (r, s) felt pair on the STARK curve
///   verify      = starknet::ecdsa::verify_ecdsa_signature(stark_pubkey,
///                                                          D_stark, (r, s))
///
/// FELT-RANGE DESIGN (the audit's felt-specific risk list):
///   • Every 31-byte chunk is < 2^248 < 2^251 < STARK_PRIME, and every
///     intermediate product in the chunk composition is range-asserted, so
///     NO felt arithmetic in this module can wrap around the field prime.
///     A wrapped product could collide with a genuinely signed chunk and
///     decouple the binding checks from the signed payload — structurally
///     impossible here.
///   • 32-byte payload fields cannot fit one felt. They cross the ABI as
///     PRE-SPLIT felt pieces cut exactly at the chunk boundaries (e.g.
///     escrow_id → escrow_hi2 ‖ escrow_lo30). The split is injective, every
///     piece is range-asserted to its byte width, and the chunks are
///     DERIVED on-chain from the pieces — the caller never supplies
///     "chunks" separately, so a fields≠chunks mismatch attack has no
///     surface. Parity with certificate.py's stark_felt_chunks() is pinned
///     by tests/contracts/test_btcp_escrow_cairo.py.
///   • Starknet deployment identifiers are felts (< 2^251). A certificate's
///     32-byte escrow_id / route_id / destination / entity_id binds them as
///     the zero-extended 32-byte form of the felt; the binding helpers
///     assert the high pieces are small enough that the recomposition stays
///     below the prime (no wrap ⇒ exact equality).
///
/// AGENT K DECISION (CANONICAL_CERTIFICATE §14.1 — Poseidon vs Pedersen):
///   D_stark uses POSEIDON (starknet::crypto::poseidon_hash_span) — the
///   Starknet-native cheap hash — as the frozen family-3 choice. Pedersen
///   remains a documented per-deployment alternative (§3.2 "fixed per
///     deployment family"); switching would be a one-line change in
///     stark_digest() plus a format-version bump of the domain tag.
///
/// This module is a pure library: it contains NO storage and NO authority.
/// The §6 fail-closed sequence (epoch registry → freshness → preconditions
/// → signatures → quorum → binding → nonce) is driven by the consuming
/// contracts (btcp_escrow.cairo / trion_execution_gate.cairo) against the
/// TrionEpochRegistry (trion_epoch_registry.cairo — the §10.2 registrar).

use core::traits::Into;
use core::array::{ArrayTrait, SpanTrait};
use starknet::crypto::poseidon_hash_span;
use starknet::ecdsa;

// ── §2 / §3.2 constants (cross-VM template — see the Solidity twin
//    contracts/solidity/libraries/CanonicalCertificate.sol for the family-1
//    leg and identical constant values) ──────────────────────────────────

/// felt("TRION-CERT-V1") — the §3.2 family-3 domain separation felt.
/// Equals int.from_bytes(b"TRION-CERT-V1", "big") in the Python reference.
pub const DOMAIN_FELT: felt252 = 'TRION-CERT-V1';

/// 346 — total signed payload width (§2). Informational on this VM: the
/// chunks are the wire form, and their widths are fixed by the format.
pub const PAYLOAD_WIDTH: u64 = 346;

/// certificate_kind 1 = ESCROW_RELEASE (ED-K1). Unknown kinds fail closed.
pub const CERT_KIND_ESCROW_RELEASE: u8 = 1;

/// Highest protocol_version (packed semver) this verifier accepts
/// (§6 step 1: protocol_version ≤ supported max). pack(1, 2, 3) = 0x010203.
pub const SUPPORTED_PROTOCOL_VERSION: u64 = 66051;

/// Minimum distinct signers (§4 invariant 4 — liveness floor; the real bar
/// is the L4.2 weight quorum of §5.2).
pub const MIN_SIGNERS: u64 = 3;

/// L4.8 concentration bound (0-10000 HHI scale) — above it the consensus is
/// CRITICAL/frozen and no valid emission exists (§5.3).
pub const HHI_MAX_ACCEPTABLE: u64 = 4000;

/// §9 clock drift tolerance (seconds) — widens the freshness LOWER bound
/// only (consensus-time skew tolerated, expiry never).
pub const CLOCK_DRIFT_TOLERANCE: u64 = 60;

/// §5.2 L4.2 quorum tier boundaries on D_consensus (×1e6).
pub const D_CONSENSUS_TIER1: u64 = 600000; // ≥ 0.60 → 2/3  (STRICT >)
pub const D_CONSENSUS_TIER2: u64 = 400000; // ≥ 0.40 → 0.75

/// ×1e6 fixed-point scale of weights / coherence / power fields.
pub const SCALE_1E6: u64 = 1000000;

/// Verifier epoch grace (ED-G, §10.2): certificates older than
/// latest_registered − grace are rejected (§6 step 2).
pub const EPOCH_GRACE: u64 = 2;

// ── felt-range powers of two (2^k as hex — zero counts are pinned by the
//    static source assertions in tests/contracts/test_btcp_escrow_cairo.py;
//    a typo here is a chunk-composition bug, so it is machine-checked) ──

pub const P2_8: felt252 = 0x100;
pub const P2_11: felt252 = 0x800;
pub const P2_16: felt252 = 0x10000;
pub const P2_32: felt252 = 0x100000000;
pub const P2_72: felt252 = 0x1000000000000000000;
pub const P2_80: felt252 = 0x100000000000000000000;
pub const P2_88: felt252 = 0x10000000000000000000000;
pub const P2_96: felt252 = 0x1000000000000000000000000;
pub const P2_104: felt252 = 0x100000000000000000000000000;
pub const P2_112: felt252 = 0x10000000000000000000000000000;
pub const P2_128: felt252 = 0x100000000000000000000000000000000;
pub const P2_136: felt252 = 0x10000000000000000000000000000000000;
pub const P2_144: felt252 = 0x1000000000000000000000000000000000000;
pub const P2_152: felt252 = 0x100000000000000000000000000000000000000;
pub const P2_160: felt252 = 0x10000000000000000000000000000000000000000;
pub const P2_163: felt252 = 0x80000000000000000000000000000000000000000;
pub const P2_168: felt252 = 0x1000000000000000000000000000000000000000000;
pub const P2_192: felt252 = 0x1000000000000000000000000000000000000000000000000;
pub const P2_200: felt252 = 0x100000000000000000000000000000000000000000000000000;
pub const P2_235: felt252 = 0x80000000000000000000000000000000000000000000000000000000000;
pub const P2_240: felt252 = 0x1000000000000000000000000000000000000000000000000000000000000;
pub const P2_248: felt252 = 0x100000000000000000000000000000000000000000000000000000000000000;

// ── §2 canonical certificate, family-3 ABI form ──────────────────────────

/// The canonical certificate as it crosses the Starknet ABI.
///
/// CALldata DESERIALIZATION (no ambiguity): the struct has a FIXED field
/// order (Serde reads exactly these members, in order, each with a fixed
/// felt width) and the signature set is a length-prefixed Span<SigEntry>
/// (explicit felt count — never sentinel-terminated). 32-byte payload
/// fields arrive as the chunk-boundary pre-split felt pairs documented in
/// the module header; every felt piece is range-asserted (check_structure)
/// so out-of-range felts fail closed BEFORE any digest arithmetic.
#[derive(Drop, Serde, Copy)]
pub struct Certificate {
    // header
    pub certificate_kind: u8,   // 1 = ESCROW_RELEASE (§2)
    pub protocol_version: u64, // uint24 packed semver
    pub validator_epoch: u64,  // uint32 — epoch whose set/weights signed
    pub certificate_nonce: u64, // uint64 — per (epoch, escrow) monotonic; 0 is the consumed-map sentinel, rejected
    // binding — 32-byte fields as chunk-boundary felt pieces
    pub escrow_hi2: felt252,   // escrow_id bytes [0:2)   (< 2^16)
    pub escrow_lo30: felt252,  // escrow_id bytes [2:32)  (< 2^240)
    pub route_hi1: felt252,    // route_id bytes [0:1)    (< 2^8)
    pub route_lo31: felt252,   // route_id bytes [1:32)   (< 2^248)
    pub intent_hi31: felt252,  // intent_hash bytes [0:31) (< 2^248)
    pub intent_lo1: felt252,   // intent_hash bytes [31:32) (< 2^8)
    pub entity_hi30: felt252,  // entity_id bytes [0:30)  (< 2^240)
    pub entity_lo2: felt252,   // entity_id bytes [30:32) (< 2^16)
    pub source_chain: u64,     // uint32 TRION registry chain id (anchor)
    pub dest_chain: u64,       // uint32 TRION registry chain id (execution)
    pub dest_hi21: felt252,    // destination bytes [0:21) (< 2^168)
    pub dest_lo11: felt252,    // destination bytes [21:32) (< 2^88)
    pub amount_hi20: felt252,  // amount bytes [0:20)     (< 2^160)
    pub amount_lo12: felt252,  // amount bytes [20:32)    (< 2^96)
    pub anchor_hi19: felt252,  // anchor_bh bytes [0:19)  (< 2^152)
    pub anchor_lo13: felt252,  // anchor_bh bytes [19:32) (< 2^104)
    pub exec_hi18: felt252,    // execution_bh bytes [0:18) (< 2^144)
    pub exec_lo14: felt252,    // execution_bh bytes [18:32) (< 2^112)
    // consensus state at emission
    pub coherence: u64,        // ×1e6 — C(t) at emission
    pub threshold: u64,        // ×1e6 — Θ(t) at emission
    pub hhi: u64,              // ×1e4 — 0-10000 scale (L4.8)
    pub total_power: u64,      // ×1e6 claim — Σ s_j·d_j over the epoch set
    pub validator_count: u64,  // uint32 claim — N of the epoch set
    pub awa_enforced: u8,      // 1 iff AWA held at emission (MD §17)
    // validity
    pub issued_at: u64,        // unix seconds, consensus clock (§9)
    pub ttl: u64,              // seconds until expiry (§9)
}

/// One validator's signature over D_stark plus its weight CLAIMS (§4).
///
/// stake_weight / diversity_weight are ×1e6 claims the verifier MUST
/// cross-check against the registered epoch set (§6 step 5c) — carried for
/// relayers, never trusted as authority. The validator_id is the canonical
/// 32-byte SHA3-256 id, split at 16 bytes into two range-asserted felts.
#[derive(Drop, Serde, Copy)]
pub struct SigEntry {
    pub vid_hi16: felt252,     // validator_id bytes [0:16)   (< 2^128)
    pub vid_lo16: felt252,     // validator_id bytes [16:32)  (< 2^128)
    pub stake_weight: u64,     // s_j ×1e6 claim
    pub diversity_weight: u64, // d_j ×1e6 claim
    pub sig_r: felt252,        // STARK-curve ECDSA r
    pub sig_s: felt252,        // STARK-curve ECDSA s
}

// ── §6 step 1 — structure + felt-range discipline ───────────────────────

/// Fail-closed structural checks on the certificate (§6 step 1, the
/// payload-side half — the envelope half — signer count, distinctness —
/// lives in the consuming contract, which sees the signature set).
///
/// Every assert here is a RANGE or SHAPE check that must hold before any
/// digest arithmetic runs, so that no felt multiplication in
/// compose_chunks() can wrap the field prime. This is the fix for the
/// audit's felt-range risk: a piece ≥ 2^(8·width) would make a derived
/// chunk wrap mod P and could (without these asserts) collide with a
/// genuinely signed chunk while the binding checks see different values.
pub fn check_structure(cert: @Certificate) {
    let c = *cert;
    assert(c.certificate_kind == CERT_KIND_ESCROW_RELEASE, 'CERT: bad kind');
    assert(c.protocol_version <= SUPPORTED_PROTOCOL_VERSION, 'CERT: version');
    assert(c.validator_epoch <= 0xFFFFFFFF_u64, 'CERT: epoch range');
    // nonce 0 is the consumed-map sentinel — a real certificate is ≥ 1.
    assert(c.certificate_nonce != 0, 'CERT: zero nonce');
    assert(c.source_chain <= 0xFFFFFFFF_u64, 'CERT: source chain');
    assert(c.dest_chain != 0, 'CERT: dest chain 0');
    assert(c.dest_chain <= 0xFFFFFFFF_u64, 'CERT: dest chain');
    assert(c.coherence <= SCALE_1E6, 'CERT: coherence range');
    assert(c.threshold <= SCALE_1E6, 'CERT: threshold range');
    assert(c.hhi <= 10000_u64, 'CERT: hhi range');
    assert(c.awa_enforced <= 1_u8, 'CERT: awa range');
    // §9 wrap-safety: issued_at + ttl must stay below 2^64 in u64 arithmetic.
    assert(c.issued_at < 0x1000000000000_u64, 'CERT: issued range');
    assert(c.ttl < 0x100000000_u64, 'CERT: ttl range');
    // felt piece ranges — each piece is bounded to its byte width so that
    // every product in compose_chunks() stays < 2^248 < 2^251 < STARK_PRIME.
    assert(c.escrow_hi2 < P2_16, 'CERT: escrow_hi2 range');
    assert(c.escrow_lo30 < P2_240, 'CERT: escrow_lo30 range');
    assert(c.route_hi1 < P2_8, 'CERT: route_hi1 range');
    assert(c.route_lo31 < P2_248, 'CERT: route_lo31 range');
    assert(c.intent_hi31 < P2_248, 'CERT: intent_hi31 range');
    assert(c.intent_lo1 < P2_8, 'CERT: intent_lo1 range');
    assert(c.entity_hi30 < P2_240, 'CERT: entity_hi30 range');
    assert(c.entity_lo2 < P2_16, 'CERT: entity_lo2 range');
    assert(c.dest_hi21 < P2_168, 'CERT: dest_hi21 range');
    assert(c.dest_lo11 < P2_88, 'CERT: dest_lo11 range');
    assert(c.amount_hi20 < P2_160, 'CERT: amount_hi20 range');
    assert(c.amount_lo12 < P2_96, 'CERT: amount_lo12 range');
    assert(c.anchor_hi19 < P2_152, 'CERT: anchor_hi19 range');
    assert(c.anchor_lo13 < P2_104, 'CERT: anchor_lo13 range');
    assert(c.exec_hi18 < P2_144, 'CERT: exec_hi18 range');
    assert(c.exec_lo14 < P2_112, 'CERT: exec_lo14 range');
}

// ── §3.2 family-3 digest ─────────────────────────────────────────────────

/// Rebuild the 12 felt chunks f_0..f_11 of P from the certificate fields.
///
/// The formulas are the fixed 31-byte chunk grid of §3.2 written out as
/// big-endian integer concatenation (all shifts in BYTES·8; every operand
/// range-asserted). Parity with certificate.py stark_felt_chunks() is
/// pinned by tests/contracts/test_btcp_escrow_cairo.py — the Python
/// reference splits P into the same 12 chunks, so any drift in these
/// formulas breaks a pinned test, not production.
pub fn compose_chunks(cert: @Certificate) -> Array<felt252> {
    let c = *cert;
    // defensive: the structural range asserts must have run — re-assert the
    // pieces this function multiplies (a library user calling only
    // stark_digest() still gets the full range discipline).
    assert(c.escrow_lo30 < P2_240, 'CERT: escrow_lo30 range');
    assert(c.route_hi1 < P2_8, 'CERT: route_hi1 range');
    assert(c.route_lo31 < P2_248, 'CERT: route_lo31 range');
    assert(c.intent_hi31 < P2_248, 'CERT: intent_hi31 range');
    assert(c.intent_lo1 < P2_8, 'CERT: intent_lo1 range');
    assert(c.entity_hi30 < P2_240, 'CERT: entity_hi30 range');
    assert(c.entity_lo2 < P2_16, 'CERT: entity_lo2 range');
    assert(c.dest_hi21 < P2_168, 'CERT: dest_hi21 range');
    assert(c.dest_lo11 < P2_88, 'CERT: dest_lo11 range');
    assert(c.amount_hi20 < P2_160, 'CERT: amount_hi20 range');
    assert(c.amount_lo12 < P2_96, 'CERT: amount_lo12 range');
    assert(c.anchor_hi19 < P2_152, 'CERT: anchor_hi19 range');
    assert(c.anchor_lo13 < P2_104, 'CERT: anchor_lo13 range');
    assert(c.exec_hi18 < P2_144, 'CERT: exec_hi18 range');
    assert(c.exec_lo14 < P2_112, 'CERT: exec_lo14 range');

    // small integer fields → felt (Into is total for u8/u64 → felt252).
    let kind_f: felt252 = c.certificate_kind.into();
    let ver_f: felt252 = c.protocol_version.into();
    let epoch_f: felt252 = c.validator_epoch.into();
    let nonce_f: felt252 = c.certificate_nonce.into();
    let src_f: felt252 = c.source_chain.into();
    let dst_f: felt252 = c.dest_chain.into();
    let coherence_f: felt252 = c.coherence.into();
    let threshold_f: felt252 = c.threshold.into();
    let power_f: felt252 = c.total_power.into();
    let vcount_f: felt252 = c.validator_count.into();
    let awa_f: felt252 = c.awa_enforced.into();
    let issued_f: felt252 = c.issued_at.into();
    let ttl_f: felt252 = c.ttl.into();
    // hhi and ttl straddle chunk boundaries — split at their byte edges.
    let hhi_hi1_f: felt252 = (c.hhi / 0x100000000000000_u64).into();
    let hhi_lo7_f: felt252 = (c.hhi % 0x100000000000000_u64).into();
    let ttl_hi3_f: felt252 = (c.ttl / 0x10000000000_u64).into();
    let ttl_lo5_f: felt252 = (c.ttl % 0x10000000000_u64).into();

    // c0 = bytes [0:31):  domain(13) kind(1) ver(3) epoch(4) nonce(8) escrow[0:2)
    let c0 = DOMAIN_FELT * P2_144 + kind_f * P2_136 + ver_f * P2_112
        + epoch_f * P2_80 + nonce_f * P2_16 + c.escrow_hi2;
    // c1 = bytes [31:62): escrow[2:32](30) route[0:1](1)
    let c1 = c.escrow_lo30 * P2_8 + c.route_hi1;
    // c2 = bytes [62:93): route[1:32](31)
    let c2 = c.route_lo31;
    // c3 = bytes [93:124): intent[0:31](31)
    let c3 = c.intent_hi31;
    // c4 = bytes [124:155): intent[31:32](1) entity[0:30](30)
    let c4 = c.intent_lo1 * P2_240 + c.entity_hi30;
    // c5 = bytes [155:186): entity[30:32](2) source(4) dest(4) destn[0:21](21)
    let c5 = c.entity_lo2 * P2_232 + src_f * P2_200 + dst_f * P2_168
        + c.dest_hi21;
    // c6 = bytes [186:217): destn[21:32](11) amount[0:20](20)
    let c6 = c.dest_lo11 * P2_160 + c.amount_hi20;
    // c7 = bytes [217:248): amount[20:32](12) anchor[0:19](19)
    let c7 = c.amount_lo12 * P2_152 + c.anchor_hi19;
    // c8 = bytes [248:279): anchor[19:32](13) exec[0:18](18)
    let c8 = c.anchor_lo13 * P2_144 + c.exec_hi18;
    // c9 = bytes [279:310): exec[18:32](14) coherence(8) threshold(8) hhi[0:1]
    let c9 = c.exec_lo14 * P2_136 + coherence_f * P2_72 + threshold_f * P2_8
        + hhi_hi1_f;
    // c10 = bytes [310:341): hhi[1:8](7) power(8) vcount(4) awa(1) issued(8) ttl[0:3]
    let c10 = hhi_lo7_f * P2_192 + power_f * P2_128 + vcount_f * P2_96
        + awa_f * P2_88 + issued_f * P2_24 + ttl_hi3_f;
    // c11 = bytes [341:346): ttl[3:8](5)
    let c11 = ttl_lo5_f;

    let mut chunks: Array<felt252> = ArrayTrait::new();
    chunks.append(c0);
    chunks.append(c1);
    chunks.append(c2);
    chunks.append(c3);
    chunks.append(c4);
    chunks.append(c5);
    chunks.append(c6);
    chunks.append(c7);
    chunks.append(c8);
    chunks.append(c9);
    chunks.append(c10);
    chunks.append(c11);
    chunks
}

/// D_stark = Poseidon(domain_felt, f_0 .. f_11) — §3.2 family 3.
/// This is the felt the quorum's STARK-curve ECDSA signatures are over.
pub fn stark_digest(cert: @Certificate) -> felt252 {
    let mut input: Array<felt252> = ArrayTrait::new();
    input.append(DOMAIN_FELT);
    let mut chunks = compose_chunks(cert);
    let n = chunks.len();
    let mut i: usize = 0;
    loop {
        if i >= n { break; }
        match chunks.pop_front() {
            Option::Some(chunk) => input.append(chunk),
            Option::None => break,
        };
        i += 1;
    };
    poseidon_hash_span(input.span())
}

/// Verify one STARK-curve ECDSA signature over D_stark against a public
/// key (§6 step 5a — one bad signature fails the whole certificate).
pub fn verify_signature(
    stark_pubkey: felt252, d_stark: felt252, sig: @SigEntry,
) -> bool {
    let s = *sig;
    ecdsa::verify_ecdsa_signature(
        stark_pubkey, d_stark, ecdsa::Signature { r: s.sig_r, s: s.sig_s },
    )
}

// ── §5.2 quorum (integer, wrap-proof) ────────────────────────────────────

/// L4.2 tier quorum check. ALL arithmetic is u128 over range-proven
/// operands: registry weights are asserted ≤ 1e6 each (normalized shares),
/// the epoch set is capped (≤ 128 validators), so w_j = s·d/1e6 ≤ 1e6,
/// total_power ≤ 1.28e8, and every product below (≤ 20·total) is far below
/// 2^128 — Cairo integer arithmetic cannot wrap here. Tier 1 is STRICT
/// (exactly-2/3 is not a quorum — the Go engine discipline).
pub fn quorum_met(signed_power: u128, total_power: u128, d_consensus: u64) -> bool {
    if d_consensus >= D_CONSENSUS_TIER1 {
        3 * signed_power > 2 * total_power
    } else if d_consensus >= D_CONSENSUS_TIER2 {
        4 * signed_power >= 3 * total_power
    } else {
        20 * signed_power >= 17 * total_power
    }
}

// ── §9 freshness (u64, wrap-proof after check_structure) ─────────────────

/// issued_at ≤ now ≤ issued_at + ttl, with the drift tolerance widening
/// the LOWER bound only (consensus-time skew tolerated, expiry never).
/// check_structure() bounds issued_at < 2^48 and ttl < 2^32, so neither
/// u64 addition below can wrap.
pub fn is_fresh(issued_at: u64, ttl: u64, now: u64) -> bool {
    now + CLOCK_DRIFT_TOLERANCE >= issued_at && now <= issued_at + ttl
}

// ── §6 step 7 — binding helpers (felt-recomposition, wrap-proof) ─────────

/// Starknet escrow ids are felt252 (< 2^251). The certificate binds the
/// 32-byte zero-extended form: value = escrow_hi2·2^240 + escrow_lo30.
/// escrow_hi2 < 2^11 (asserted) keeps the product below 2^251 < prime, so
/// the equality is exact — a wrapped recomposition cannot alias a
/// different escrow. Ids in the prime's "dark range" [2^251, P) are
/// rejected by the lock-side range assert (fail-closed, documented).
pub fn escrow_id_matches(cert: @Certificate, escrow_id: felt252) -> bool {
    let c = *cert;
    c.escrow_hi2 < P2_11 && c.escrow_hi2 * P2_240 + c.escrow_lo30 == escrow_id
}

/// Same discipline for the route id (route_hi1 < 2^3 ⇒ product < 2^251).
pub fn route_id_matches(cert: @Certificate, route_id: felt252) -> bool {
    let c = *cert;
    c.route_hi1 < 0x8 && c.route_hi1 * P2_248 + c.route_lo31 == route_id
}

/// Destination binding against a Starknet ContractAddress. Real Starknet
/// addresses are felts < 2^251; dest_hi21 < 2^163 (asserted) keeps
/// hi·2^88 + lo below the prime — exact equality. Addresses in the
/// negligible dark range [2^251, P) (≈ 2^196 of 2^251 values) cannot be
/// bound by a certificate — they fail closed.
pub fn destination_matches(
    cert: @Certificate, destination: starknet::ContractAddress,
) -> bool {
    let c = *cert;
    let addr_felt: felt252 = destination.into();
    c.dest_hi21 < P2_163 && c.dest_hi21 * P2_88 + c.dest_lo11 == addr_felt
}

/// Amount binding against the escrow's u256 amount. The 32-byte
/// certificate amount is [amount_hi20 (20B)][amount_lo12 (12B)]; the u256
/// is { high: H (bytes 0:16), low: L (bytes 16:32) }. Equality iff
///   amount_hi20 == H·2^32 + L / 2^96   and   amount_lo12 == L % 2^96.
/// The u128 divisions are exact integer ops; H·2^32 < 2^160 after the
/// piece range assert — no felt wrap.
pub fn amount_matches(cert: @Certificate, amount: u256) -> bool {
    let c = *cert;
    assert(c.amount_hi20 < P2_160, 'CERT: amount_hi20 range');
    assert(c.amount_lo12 < P2_96, 'CERT: amount_lo12 range');
    let high_f: felt252 = amount.high.into();
    let mid_f: felt252 = (amount.low / 0x1000000000000000000000000_u128).into();
    let lo_f: felt252 = (amount.low % 0x1000000000000000000000000_u128).into();
    c.amount_hi20 == high_f * P2_32 + mid_f && c.amount_lo12 == lo_f
}

/// Entity binding for the execution gate: the certificate's 32-byte
/// entity_id recomposed as a felt key (entity_hi30 < 2^235 ⇒ value <
/// 2^251 — no wrap). Returns the composed entity felt key.
pub fn entity_key(cert: @Certificate) -> felt252 {
    let c = *cert;
    assert(c.entity_hi30 < P2_235, 'CERT: entity_hi30 binding');
    c.entity_hi30 * P2_16 + c.entity_lo2
}
