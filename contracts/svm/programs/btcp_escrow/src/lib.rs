//! BTCPEscrow — Two-State Atomic Escrow for BTCP Cross-Chain Settlement
//!
//! Solana Anchor port of `BTCPEscrow.sol`, Wave 2 hardened (C-03 closure).
//!
//! Holds native SOL in HOLDING state until a **TRION canonical certificate**
//! (docs/protocol/CANONICAL_CERTIFICATE.md) is presented and verified
//! on-chain, then releases or reverts atomically.
//!
//! State model (docs/protocol/BTCP_STATE_MACHINE.md, M2):
//!   HOLDING → RELEASED           (valid canonical certificate, not expired)
//!   HOLDING → REVERTED           (timeout | relayer failure)
//!   HOLDING → EMERGENCY_REVERTED (permissionless 7-day escape hatch, E6)
//!   All three terminal states have NO outgoing transitions.
//!
//! RELEASE AUTHORITY — C-03 closure (docs/audit/VALIDATOR_SECURITY_AUDIT.md):
//! the release gate is CERTIFICATE VERIFICATION, not a key. The
//! `release_escrow` instruction implements the canonical §6 sequence,
//! fail-closed, in order:
//!
//!   1. STRUCTURE  — 346-byte payload, "TRION-CERT-V1" tag, kind 1,
//!                   protocol_version ≤ supported, family-2 envelope,
//!                   ≥ 3 distinct signers, 64-byte signatures.
//!   2. EPOCH      — cert epoch resolves to a registered epoch-registry PDA
//!                   (["trion","validators",epoch_be]) and is within the
//!                   2-epoch grace window of `config.latest_epoch`.
//!   3. FRESHNESS  — issued_at − 60 s ≤ Clock.unix_timestamp ≤
//!                   issued_at + ttl; 0 < ttl ≤ 7 days.
//!   4. CONSENSUS  — hhi ≤ 4000; awa_enforced; coherence ≥ threshold;
//!                   threshold == registered epoch Θ(t);
//!                   validator_count == registered set size.
//!   5. SIGNATURES — every envelope signature must be covered by a
//!                   native Ed25519SigVerify (precompile) instruction that
//!                   EXECUTED EARLIER in the same transaction: the program
//!                   introspects those instructions through the
//!                   instructions sysvar and requires the runtime to have
//!                   verified exactly (registered validator pubkey,
//!                   envelope signature, this RAW 346-byte payload P) —
//!                   a three-way exact byte match parsed with the
//!                   runtime's own offsets semantics (the Relay
//!                   "wrong-offset" bypass class is closed).
//!   6. QUORUM     — signed_power = Σ s_j·d_j over verified signers,
//!                   recomputed from the REGISTRY (never envelope claims);
//!                   L4.2 tier check in exact u128 integer arithmetic.
//!   7. BINDING    — escrow_id, route_id, intent_hash, entity_id,
//!                   destination, amount, source/dest chain, anchor_bh,
//!                   execution_bh must equal the escrow's own state; the
//!                   settlement tuple (destination, amount) closes
//!                   escrow-substitution (ED-B2).
//!   8. NONCE      — consumed-certificate PDA
//!                   (["trion","consumed",escrow_id]): same SHA-256(P) →
//!                   idempotent no-op (observability); a different
//!                   certificate → CONFLICT + equivocation-evidence event.
//!   9. Only then: state → RELEASED and the lamports transfer.
//!
//! The old single-oracle-key release-authority gate is
//! REMOVED: compromise of one key no longer unilaterally releases escrows.
//! The bound TRION key is retained as a PAUSE authority ONLY — it pauses
//! NEW locks; it can never release, and pause never blocks settling or
//! reverting existing escrows (M2 pause semantics). There is deliberately
//! NO dev fallback release path: bootstrap certificates (kind 2) are
//! pending a governance decision (CANONICAL_CERTIFICATE.md §14.4) and fail
//! closed here; before the first epoch is registered the program simply
//! rejects every certificate (`NoEpochRegistered`).
//!
//! ARITHMETIC discipline (master command §10): every u64 add/mul is checked
//! (checked_* → `Overflow`); quorum products are u128; weights and D_consensus
//! round DOWN (integer division — the conservative direction); the
//! certificate's uint256 amount must fit u64 lamports (high 24 bytes zero,
//! else `AmountTooLarge`); lamports (native SOL) are the only value
//! representation — no SPL token accounts and no decimal conversion on this
//! path, so wrap/native and rounding hazards do not arise.
//!
//! Solana-specific notes:
//!   • Escrow PDA:       ["escrow", escrow_id]
//!   • Vault PDA:        ["vault", escrow_id]   (holds the SOL)
//!   • Epoch registry:   ["trion", "validators", epoch_be]  (u32 big-endian)
//!   • Consumed cert:    ["trion", "consumed", escrow_id]
//!   • `block.timestamp` → `Clock::get()?.unix_timestamp`;
//!     `block.number`    → `Clock::get()?.slot`
//!   • The canonical certificate hash is SHA3-256(P) (FIPS 202), which the
//!     SVM cannot compute on-chain (no SHA3 precompile/syscall). Per
//!     CANONICAL_CERTIFICATE.md §7 (Solana row) the SVM consumed key /
//!     conflict key is **SHA-256(P)** via `solana_program::hash::hash`
//!     (the sha256 syscall) — the same collision-resistance class, a
//!     documented deviation. The canonical SHA3-256 id remains an
//!     off-chain (Akashic) identifier.
//!   • No unsafe code, no new dependencies. ed25519 verification uses the
//!     native Ed25519SigVerify program: the submitting transaction carries
//!     its verification instructions as TOP-LEVEL instructions placed
//!     before `release_escrow`, and this program introspects them via
//!     `solana_program::sysvar::instructions` (see
//!     `verify_ed25519_signature` for why the CPI and dalek alternatives
//!     were rejected).

use anchor_lang::{
    prelude::*,
    solana_program::{
        ed25519_program,
        hash,
        instruction::Instruction,
        program::{invoke, invoke_signed},
        sysvar::instructions as ix_sysvar,
        system_instruction,
    },
};
use btcp_common::*;

// Program-level authority + state account
#[account]
pub struct ProgramConfig {
    /// Admin authority (set_relayer / bind_pause_authority /
    /// set_registry_admin). Set to the deployer at `initialize`.
    pub owner: Pubkey,
    /// Operational authority for locks and non-timeout reverts.
    pub relayer: Pubkey,
    /// Validator-registry registrar (the TRION registrar relayer role —
    /// the ONLY writer of epoch registrations; one tx per epoch boundary,
    /// CANONICAL_CERTIFICATE.md §7 bridging rule / §10.2).
    pub registry_admin: Pubkey,
    /// The formerly-omnipotent TRION oracle key, re-scoped (C-03): it may
    /// PAUSE new locks — it can NEVER release. Default (all-zero) = unset:
    /// only the owner may pause until bound. Binding is one-way.
    pub pause_authority: Pubkey,
    /// Canonical TRION chain id (config/chain_registry.json — Solana = 900)
    /// of THIS deployment. Every certificate's dest_chain must equal it.
    pub self_chain: u32,
    /// Launch-threshold policy (V2 §9.2): registered sets smaller than this
    /// cannot verify certificates (default/minimum 3 = CERT_MIN_SIGNERS;
    /// mainnet deployments should raise it toward the 100-validator
    /// launch threshold — CANONICAL_CERTIFICATE.md §1 allows rejection
    /// below 100).
    pub min_validator_count: u32,
    /// Latest registered validator epoch; 0 = none registered yet (every
    /// certificate fails closed until the registrar lands epoch 1).
    pub latest_epoch: u32,
    /// Pause flag — blocks NEW lock_escrow only.
    pub paused: bool,
    pub count: u64,
    pub bump: u8,
}

impl ProgramConfig {
    pub const SIZE: usize = 8
        + 32    // owner
        + 32    // relayer
        + 32    // registry_admin
        + 32    // pause_authority
        + 4     // self_chain
        + 4     // min_validator_count
        + 4     // latest_epoch
        + 1     // paused
        + 8     // count
        + 1;    // bump

    pub fn is_authorized(&self, signer: &Pubkey) -> bool {
        signer == &self.owner || signer == &self.relayer
    }

    pub fn is_owner(&self, signer: &Pubkey) -> bool {
        signer == &self.owner
    }

    pub fn is_registry_admin(&self, signer: &Pubkey) -> bool {
        signer == &self.registry_admin
    }

    /// PAUSE authority: the owner, or the bound TRION key (the old
    /// oracle). Never grants release — release requires a certificate.
    pub fn is_pause_authority(&self, signer: &Pubkey) -> bool {
        self.is_owner(signer)
            || (self.pause_authority != Pubkey::default()
                && &self.pause_authority == signer)
    }
}

declare_id!("54r6REJKQ3d2MSV7zYikwiPmck3h7QRaeG44vnRHetWZ");

// ── Accounts ─────────────────────────────────────────────────────────────────

/// Escrow state account. PDA: ["escrow", escrow_id]
///
/// The §4.2 Step-3 binding set is stored at lock time so the certificate's
/// step-7 checks are all against the escrow's OWN state:
/// escrow/route/intent/entity ids, the settlement tuple (destination,
/// amount), the route legs (source/dest chain) and the anchor/execution
/// behavioral hashes.
#[account]
pub struct Escrow {
    pub escrow_id: [u8; 32],
    pub route_id: [u8; 32],
    pub intent_hash: [u8; 32],
    pub entity_id: BEOIdentity,
    pub destination: Pubkey,
    pub amount: u64,
    pub min_coherence: u64,
    pub source_chain: u32,
    pub dest_chain: u32,
    pub anchor_bh: [u8; 32],
    pub execution_bh: [u8; 32],
    pub lock_slot: u64,
    /// unix seconds at lock — the E6 7-day emergency-escape clock.
    pub locked_at: i64,
    pub timeout_slots: u64,
    pub state: EscrowState,
    pub revert_reason: RevertReason,
    pub settled_at: i64,
    pub reverted_at: i64,
    pub locked_by: Pubkey,
    pub bump: u8,
    pub vault_bump: u8,
}

impl Escrow {
    /// Account size: discriminator (8) + fields
    pub const SIZE: usize = 8
        + 32    // escrow_id
        + 32    // route_id
        + 32    // intent_hash
        + 32    // entity_id (BEOIdentity)
        + 32    // destination (Pubkey)
        + 8     // amount
        + 8     // min_coherence
        + 4     // source_chain
        + 4     // dest_chain
        + 32    // anchor_bh
        + 32    // execution_bh
        + 8     // lock_slot
        + 8     // locked_at
        + 8     // timeout_slots
        + 1     // state
        + 1     // revert_reason
        + 8     // settled_at
        + 8     // reverted_at
        + 32    // locked_by
        + 1     // bump
        + 1;    // vault_bump

    /// Check if escrow is expired (current slot > lock_slot + timeout_slots)
    pub fn is_expired(&self, current_slot: u64) -> bool {
        self.state == EscrowState::Holding
            && current_slot > self.lock_slot.saturating_add(self.timeout_slots)
    }
}

/// One validator's canonical epoch-scoped state (CANONICAL_CERTIFICATE.md
/// §10.2 / §4): 32-byte ed25519 family pubkey + the s_j, d_j weights
/// (×1e6). Quorum is computed from THESE registered values — never from
/// envelope claims.
#[derive(AnchorSerialize, AnchorDeserialize, Clone, Copy, PartialEq, Eq, Debug)]
pub struct ValidatorEntry {
    /// SHA3-256("TRION-VALIDATOR" || epoch || key_index) — canonical id.
    pub validator_id: [u8; 32],
    /// Ed25519 verification key (§3.2 family 2 — the SVM family).
    pub ed25519_pubkey: [u8; 32],
    /// s_j ×1e6 — stake weight, (0, 1e6].
    pub stake_weight: u64,
    /// d_j ×1e6 — diversity weight, [0, 1e6].
    pub diversity_weight: u64,
}

impl ValidatorEntry {
    pub const SIZE: usize = 32 + 32 + 8 + 8;
}

/// TRION epoch registry PDA: ["trion", "validators", epoch_be].
///
/// Written exactly once per epoch by the registrar (register_epoch —
/// strictly increasing epochs, immutable sets, rotation at boundary only,
/// §10.2). Read by `release_escrow` for membership, weights, quorum and
/// the epoch threshold Θ(t).
#[account]
pub struct TrionEpochRegistry {
    pub epoch: u32,
    pub validator_count: u32,
    /// Σ_j s_j·d_j ×1e6 — registrar claim, re-verified against the
    /// entries on every release (RegistryPowerMismatch).
    pub total_effective_power: u64,
    /// Θ(t) of this epoch ×1e6 — the registered threshold the certificate
    /// must agree with (H-03: the proof never sets its own pass bar).
    pub threshold: u64,
    /// SHA-256("TRION-EPOCHSET" || epoch_be || canonical entries) — the
    /// SVM analog of the §10.2 epoch-set root (SHA3 unavailable on SVM;
    /// documented deviation, same class as the consumed key).
    pub set_root: [u8; 32],
    /// Entries sorted by validator_id (registration enforces order +
    /// distinctness; release lookups are binary searches).
    pub validators: Vec<ValidatorEntry>,
}

impl TrionEpochRegistry {
    /// 8 (disc) + epoch 4 + count 4 + power 8 + threshold 8 + root 32 +
    /// Vec length prefix 4.
    pub const SPACE_BASE: usize = 8 + 4 + 4 + 8 + 8 + 32 + 4;

    pub fn space_for(n_validators: usize) -> usize {
        Self::SPACE_BASE + n_validators * ValidatorEntry::SIZE
    }
}

/// Consumed-certificate PDA: ["trion", "consumed", escrow_id].
///
/// Records the certificate that consumed this escrow's single release
/// (§8.2). `init_if_needed` + transaction atomicity guarantee a persisted
/// account implies a prior successful release (is_set == 1); a failed
/// verification rolls the account creation back with the transaction.
#[account]
pub struct ConsumedCertificate {
    /// 1 once a certificate has been consumed for this escrow.
    pub is_set: u8,
    pub epoch: u32,
    pub nonce: u64,
    /// SHA-256(P) of the consumed certificate — the SVM consumed key
    /// (canonical SHA3-256 unavailable on-chain; §7 Solana row).
    pub cert_sha256: [u8; 32],
}

impl ConsumedCertificate {
    pub const SIZE: usize = 8 + 1 + 4 + 8 + 32;
}

// ── Instruction arguments (envelope — §4) ───────────────────────────────────

/// One validator signature over P plus its weight CLAIMS (§4). The claims
/// are cross-checked against the registered epoch set at step 5c — they
/// are carried for relayers, never trusted as authority.
#[derive(AnchorSerialize, AnchorDeserialize, Clone, Debug)]
pub struct EnvelopeSignature {
    pub validator_id: [u8; 32],
    pub stake_weight: u64,
    pub diversity_weight: u64,
    /// Exactly 64 bytes on the SVM family (checked at step 1).
    pub signature: Vec<u8>,
}

/// The certificate envelope as submitted with `release_escrow`.
#[derive(AnchorSerialize, AnchorDeserialize, Clone, Debug)]
pub struct CertificateEnvelopeArg {
    /// Must be 2 (ed25519) — the family of this VM (§6 step 1).
    pub family: u8,
    pub signatures: Vec<EnvelopeSignature>,
}

// ── Payload decoding (§2 — offsets pinned by the py reference encoder) ──────

struct CertificateView {
    kind: u8,
    protocol_version: u32,
    validator_epoch: u32,
    certificate_nonce: u64,
    escrow_id: [u8; 32],
    route_id: [u8; 32],
    intent_hash: [u8; 32],
    entity_id: [u8; 32],
    source_chain: u32,
    dest_chain: u32,
    destination: [u8; 32],
    amount: u64,
    anchor_bh: [u8; 32],
    execution_bh: [u8; 32],
    coherence: u64,
    threshold: u64,
    hhi_at_emission: u64,
    total_effective_power: u64,
    validator_count: u32,
    awa_enforced: u8,
    issued_at: u64,
    ttl: u64,
}

fn be_u32(b: &[u8]) -> u32 {
    u32::from_be_bytes([b[0], b[1], b[2], b[3]])
}

fn be_u64(b: &[u8]) -> u64 {
    u64::from_be_bytes([b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7]])
}

/// Decode the canonical 346-byte payload P at the CANONICAL_CERTIFICATE.md
/// §2 offsets — byte-identical to `core/consensus/certificate.py`
/// (`OFFSETS`); the offset set is pinned by
/// tests/contracts/test_btcp_escrow_svm.py (static parity + golden vector).
fn parse_certificate(p: &[u8]) -> Result<CertificateView> {
    require!(p.len() == CERT_PAYLOAD_WIDTH, BTCPError::MalformedCertificate);
    require!(&p[0..13] == CERT_DOMAIN_TAG, BTCPError::MalformedCertificate);
    let mut escrow_id = [0u8; 32];
    escrow_id.copy_from_slice(&p[29..61]);
    let mut route_id = [0u8; 32];
    route_id.copy_from_slice(&p[61..93]);
    let mut intent_hash = [0u8; 32];
    intent_hash.copy_from_slice(&p[93..125]);
    let mut entity_id = [0u8; 32];
    entity_id.copy_from_slice(&p[125..157]);
    let mut destination = [0u8; 32];
    destination.copy_from_slice(&p[165..197]);
    let mut anchor_bh = [0u8; 32];
    anchor_bh.copy_from_slice(&p[229..261]);
    let mut execution_bh = [0u8; 32];
    execution_bh.copy_from_slice(&p[261..293]);
    // amount is uint256 BE at [197..229]; Solana-native value is u64
    // lamports — the 24 high bytes must be zero, else the certificate can
    // never match a u64 escrow amount and is rejected (fail-closed).
    let amount_bytes = &p[197..229];
    require!(
        amount_bytes[0..24].iter().all(|&b| b == 0),
        BTCPError::AmountTooLarge
    );
    Ok(CertificateView {
        kind: p[13],
        // uint24 → u32 (prepend a zero byte)
        protocol_version: be_u32(&[0, p[14], p[15], p[16]]),
        validator_epoch: be_u32(&p[17..21]),
        certificate_nonce: be_u64(&p[21..29]),
        escrow_id,
        route_id,
        intent_hash,
        entity_id,
        source_chain: be_u32(&p[157..161]),
        dest_chain: be_u32(&p[161..165]),
        destination,
        amount: be_u64(&amount_bytes[24..32]),
        anchor_bh,
        execution_bh,
        coherence: be_u64(&p[293..301]),
        threshold: be_u64(&p[301..309]),
        hhi_at_emission: be_u64(&p[309..317]),
        total_effective_power: be_u64(&p[317..325]),
        validator_count: be_u32(&p[325..329]),
        awa_enforced: p[329],
        issued_at: be_u64(&p[330..338]),
        ttl: be_u64(&p[338..346]),
    })
}

/// w_j = s_j · d_j (×1e6 carried) — integer division, rounds DOWN
/// (conservative: the validator's counted power never rounds up).
fn effective_power(v: &ValidatorEntry) -> Result<u64> {
    v.stake_weight
        .checked_mul(v.diversity_weight)
        .map(|product| product / SCALE)
        .ok_or(BTCPError::Overflow)
}

/// Registry lookup (entries are sorted by validator_id at registration).
fn find_validator<'a>(
    registry: &'a TrionEpochRegistry,
    validator_id: &[u8; 32],
) -> Option<&'a ValidatorEntry> {
    registry
        .validators
        .binary_search_by(|v| v.validator_id.cmp(validator_id))
        .ok()
        .map(|idx| &registry.validators[idx])
}

// ── Ed25519SigVerify introspection (§6 step 5a) ─────────────────────────────

/// Ed25519SigVerify instruction-data layout (Solana runtime / the
/// Relay-discipline, blog.asymmetric.re 2025-09):
/// `u8 num_signatures ‖ u8 padding ‖ (per signature) 14-byte offsets
/// struct`, followed by the referenced byte regions. One offsets struct is
/// seven u16 LITTLE-endian fields: signature_offset,
/// signature_instruction_index, public_key_offset,
/// public_key_instruction_index, message_data_offset, message_data_size,
/// message_instruction_index. An index of `u16::MAX` means "this
/// instruction's own data"; any other value indexes into the transaction's
/// top-level instruction list (the precompile itself resolves data across
/// instructions exactly this way).
const ED_IX_PREFIX_LEN: usize = 2;
const ED_IX_OFFSETS_LEN: usize = 14;
const ED_SIG_LEN: usize = CERT_ED25519_SIG_LEN; // 64
const ED_PUBKEY_LEN: usize = 32;

#[derive(Clone, Copy)]
struct Ed25519Offsets {
    signature_offset: u16,
    signature_instruction_index: u16,
    public_key_offset: u16,
    public_key_instruction_index: u16,
    message_data_offset: u16,
    message_data_size: u16,
    message_instruction_index: u16,
}

/// Parse the i'th offsets struct of an Ed25519SigVerify instruction.
fn read_ed_offsets(data: &[u8], entry: usize) -> Option<Ed25519Offsets> {
    let base = ED_IX_PREFIX_LEN + entry * ED_IX_OFFSETS_LEN;
    let b = data.get(base..base + ED_IX_OFFSETS_LEN)?;
    let u = |i: usize| u16::from_le_bytes([b[2 * i], b[2 * i + 1]]);
    Some(Ed25519Offsets {
        signature_offset: u(0),
        signature_instruction_index: u(1),
        public_key_offset: u(2),
        public_key_instruction_index: u(3),
        message_data_offset: u(4),
        message_data_size: u(5),
        message_instruction_index: u(6),
    })
}

/// Resolve one (offset, instruction_index) pair to a byte slice — the
/// EXACT semantics of the Ed25519SigVerify program itself: index ==
/// `u16::MAX` → the ed instruction's own data at `offset`; otherwise
/// `tx[index].data` at `offset`. Bounds-checked (usize math, u16 offsets).
fn ed_slice<'a>(
    tx: &'a [Instruction],
    ed_data: &'a [u8],
    index: u16,
    offset: u16,
    len: usize,
) -> Option<&'a [u8]> {
    let start = offset as usize;
    let end = start.checked_add(len)?;
    if index == u16::MAX {
        ed_data.get(start..end)
    } else {
        tx.get(usize::from(index))?.data.get(start..end)
    }
}

/// Verify that the Solana RUNTIME (the native Ed25519SigVerify program)
/// already verified exactly `(pubkey, signature, payload)` in an
/// instruction of THIS transaction that executed BEFORE `release_escrow`.
///
/// PATTERN CHOICE (the only viable one on anchor-lang 0.29 /
/// solana-program 1.18 — verified against the published crate docs):
/// the submitting transaction carries top-level Ed25519SigVerify
/// instructions ahead of the release instruction; the precompile verifies
/// each (pubkey, signature, message) triple when it executes, and this
/// program confirms — via instructions-sysvar introspection — that the
/// verified triple is exactly the one this release needs. One missing or
/// divergent verification fails the WHOLE certificate (batch
/// fail-closed, §6 step 5a).
///
/// Alternatives, documented as rejected:
///   • CPI into Ed25519SigVerify — the runtime REJECTS cross-program
///     invocations of the precompile (Solana docs; solana.stackexchange
///     19127), and the `new_ed25519_instruction` builder is solana-sdk
///     (client-side only) — it does not exist in solana-program 1.18.
///   • in-program ed25519-dalek — solana-program 1.18 re-exports no
///     `ed25519_dalek`, the crate is not in the locked dependency set,
///     and a software verify would burn a large CU budget per signature.
///   • runtime wallet-sigverify — only covers transaction signatures of
///     signers, never instruction-embedded certificate signatures.
///
/// SECURITY DISCIPLINE (the Relay "Wrong Offset" lesson): never trust
/// hardcoded offsets. Every entry's offsets struct is parsed and the
/// (signature, pubkey, message) bytes are resolved with the runtime's own
/// index semantics, then required to match the envelope entry and the
/// payload under verification byte-for-byte. A divergent offset simply
/// finds no match → fail-closed.
fn verify_ed25519_signature(
    tx: &[Instruction],
    current_index: usize,
    payload: &[u8],
    pubkey: &[u8; 32],
    signature: &[u8],
) -> Result<()> {
    // Only instructions that have ALREADY EXECUTED (index < current) are
    // introspected — an Ed25519SigVerify instruction placed after
    // release_escrow is never credited.
    debug_assert!(tx.len() <= current_index);
    for ix in tx.iter().take(current_index) {
        if ix.program_id != ed25519_program::id() {
            continue;
        }
        // The Ed25519SigVerify program is stateless — a verification
        // instruction carries no accounts. Anything else is not a
        // verification source.
        if !ix.accounts.is_empty() {
            continue;
        }
        let data = &ix.data;
        if data.len() < ED_IX_PREFIX_LEN {
            continue;
        }
        let num_sigs = data[0] as usize;
        for entry in 0..num_sigs {
            let Some(off) = read_ed_offsets(data, entry) else {
                // malformed tail — the runtime would have failed the
                // instruction; nothing here can be a match anyway
                break;
            };
            // Bounds-checked resolution with the runtime's index
            // semantics: the slices below are the very bytes the
            // Ed25519SigVerify program verified when this instruction
            // executed (a failed verification would have aborted the
            // transaction before release_escrow ran).
            let (sig, pk, msg) = match (
                ed_slice(tx, data, off.signature_instruction_index, off.signature_offset, ED_SIG_LEN),
                ed_slice(tx, data, off.public_key_instruction_index, off.public_key_offset, ED_PUBKEY_LEN),
                ed_slice(tx, data, off.message_instruction_index, off.message_data_offset, off.message_data_size as usize),
            ) {
                (Some(sig), Some(pk), Some(msg)) => (sig, pk, msg),
                // unresolvable offsets cannot be what the runtime verified
                _ => continue,
            };
            // THREE-WAY exact match: runtime-verified (pk, sig, msg) ==
            // (registered validator key, envelope signature, THIS payload).
            if msg == payload && pk == pubkey.as_slice() && sig == signature {
                return Ok(());
            }
        }
    }
    Err(error!(BTCPError::SignatureVerificationFailed))
}

// ── Instructions ────────────────────────────────────────────────────────────

#[program]
pub mod btcp_escrow {
    use super::*;

    /// Initialize the program config. Callable EXACTLY ONCE — the `init`
    /// constraint on the config PDA is atomic and exclusive (a second call
    /// fails because the account already exists).
    ///
    /// Authority bootstrap (master command §10 separation, documented):
    /// the deployer payer becomes owner, relayer AND registry_admin; the
    /// owner then separates roles via set_relayer / set_registry_admin /
    /// bind_pause_authority (the latter one-way). latest_epoch = 0: no
    /// certificate verifies until the registrar registers epoch 1.
    pub fn initialize(
        ctx: Context<Initialize>,
        self_chain: u32,
        min_validator_count: u32,
    ) -> Result<()> {
        require!(self_chain != 0, BTCPError::ZeroChain);
        require!(
            min_validator_count >= CERT_MIN_SIGNERS as u32,
            BTCPError::TooFewValidators
        );
        let config = &mut ctx.accounts.config;
        config.owner = ctx.accounts.payer.key();
        config.relayer = ctx.accounts.payer.key();
        config.registry_admin = ctx.accounts.payer.key();
        config.pause_authority = Pubkey::default();
        config.self_chain = self_chain;
        config.min_validator_count = min_validator_count;
        config.latest_epoch = 0;
        config.paused = false;
        config.count = 0;
        config.bump = ctx.bumps.config;
        Ok(())
    }

    /// Register a validator epoch — the ONE per-epoch on-chain write
    /// (§10.2, §7 bridging rule). registry_admin only; epochs strictly
    /// increase (an epoch set is immutable once registered; rotation
    /// happens only at boundaries). Entries are stored sorted by
    /// validator_id with distinct ids AND distinct ed25519 pubkeys
    /// (key-sharing cannot inflate weight).
    pub fn register_epoch(
        ctx: Context<RegisterEpoch>,
        epoch: u32,
        entries: Vec<ValidatorEntry>,
        threshold: u64,
    ) -> Result<()> {
        let config = &mut ctx.accounts.config;
        require!(
            config.is_registry_admin(&ctx.accounts.admin.key()),
            BTCPError::NotRegistryAdmin
        );
        require!(epoch >= 1, BTCPError::InvalidEpoch);
        // strictly increasing — no re-registration, no overwrite, no gaps
        // that would resurrect a retired set.
        require!(epoch > config.latest_epoch, BTCPError::EpochAlreadyRegistered);
        require!(!entries.is_empty(), BTCPError::InvalidValidatorSet);
        require!(entries.len() <= MAX_VALIDATORS, BTCPError::InvalidValidatorSet);
        require!(
            threshold >= 1 && threshold <= SCALE,
            BTCPError::InvalidThreshold
        );

        // distinct validator ids (sorted storage order)
        let mut sorted = entries.clone();
        sorted.sort_by(|a, b| a.validator_id.cmp(&b.validator_id));
        for pair in sorted.windows(2) {
            require!(
                pair[0].validator_id != pair[1].validator_id,
                BTCPError::DuplicateValidator
            );
        }
        // distinct pubkeys — one key must not carry two validators' power
        let mut by_key = entries.clone();
        by_key.sort_by(|a, b| a.ed25519_pubkey.cmp(&b.ed25519_pubkey));
        for pair in by_key.windows(2) {
            require!(
                pair[0].ed25519_pubkey != pair[1].ed25519_pubkey,
                BTCPError::DuplicateValidatorKey
            );
        }

        // weight bounds + total power (checked math, rounds down)
        let mut total_power: u64 = 0;
        for v in &sorted {
            require!(
                v.stake_weight > 0 && v.stake_weight <= SCALE,
                BTCPError::InvalidWeight
            );
            require!(v.diversity_weight <= SCALE, BTCPError::InvalidWeight);
            total_power = total_power
                .checked_add(effective_power(v)?)
                .ok_or(BTCPError::Overflow)?;
        }
        require!(total_power > 0, BTCPError::ZeroPower);

        // epoch-set root (SVM: SHA-256 — SHA3 unavailable on-chain,
        // documented deviation): SHA-256("TRION-EPOCHSET" || epoch_be ||
        // each entry's canonical serialization).
        let mut root_input: Vec<u8> =
            Vec::with_capacity(13 + 4 + sorted.len() * ValidatorEntry::SIZE);
        root_input.extend_from_slice(b"TRION-EPOCHSET");
        root_input.extend_from_slice(&epoch.to_be_bytes());
        for v in &sorted {
            root_input.extend_from_slice(&v.validator_id);
            root_input.extend_from_slice(&v.ed25519_pubkey);
            root_input.extend_from_slice(&v.stake_weight.to_be_bytes());
            root_input.extend_from_slice(&v.diversity_weight.to_be_bytes());
        }
        let set_root = hash::hash(&root_input).to_bytes();

        let registry = &mut ctx.accounts.registry;
        registry.epoch = epoch;
        registry.validator_count = sorted.len() as u32;
        registry.total_effective_power = total_power;
        registry.threshold = threshold;
        registry.set_root = set_root;
        registry.validators = sorted;

        config.latest_epoch = epoch;

        emit!(EpochRegistered {
            epoch,
            validator_count: registry.validator_count,
            total_effective_power: total_power,
            threshold,
            set_root,
        });
        Ok(())
    }

    /// Lock native SOL in escrow.
    ///
    /// Equivalent to Solidity `lockEscrow() external payable` — `amount`
    /// is the lamports to lock. Caller (relayer/owner) must be authorized;
    /// the SOL is transferred from the `vault_funder` signer to the vault
    /// PDA owned by this program.
    ///
    /// The full §4.2 Step-3 binding set is recorded here so the release
    /// certificate's step-7 checks bind against the escrow's own state:
    /// intent_hash, the route legs, and the anchor/execution behavioral
    /// hashes (the EVM tier's anchorBH==escrowId overload is replaced by
    /// explicit fields — ED-B1/B2).
    ///
    /// SECURITY FIX (P1, retained): only the explicit `amount` is
    /// encumbered — never the funder's whole balance.
    pub fn lock_escrow(
        ctx: Context<LockEscrow>,
        escrow_id: [u8; 32],
        route_id: [u8; 32],
        intent_hash: [u8; 32],
        entity_id: BEOIdentity,
        amount: u64,
        min_coherence: u64,
        source_chain: u32,
        dest_chain: u32,
        anchor_bh: [u8; 32],
        execution_bh: [u8; 32],
        timeout_slots: u64,
    ) -> Result<()> {
        let config = &ctx.accounts.config;
        require!(
            config.is_authorized(&ctx.accounts.relayer.key()),
            BTCPError::NotAuthorized
        );
        // Pause (C-03 re-scoping): blocks NEW locks ONLY — settling and
        // reverting existing escrows is never pausable (M2).
        require!(!config.paused, BTCPError::Paused);

        require!(min_coherence <= MAX_COHERENCE, BTCPError::InvalidCoherence);
        require!(timeout_slots > 0, BTCPError::ZeroTimeout);
        require!(!entity_id.is_zero(), BTCPError::ZeroDestination);
        require!(escrow_id != [0u8; 32], BTCPError::InvalidArgument);
        require!(intent_hash != [0u8; 32], BTCPError::ZeroIntentHash);
        require!(source_chain != 0, BTCPError::ZeroChain);
        require!(dest_chain == config.self_chain, BTCPError::WrongChain);
        require!(!anchor_bh.iter().all(|&b| b == 0), BTCPError::ZeroAnchor);
        require!(!execution_bh.iter().all(|&b| b == 0), BTCPError::ZeroExecutionBH);

        require!(amount > 0, BTCPError::ZeroAmount);
        require!(
            ctx.accounts.vault_funder.lamports() >= amount,
            BTCPError::InsufficientFunds
        );

        let clock = Clock::get()?;
        // Checked expiry arithmetic: an escrow whose lock_slot +
        // timeout_slots would overflow u64 is rejected at lock time
        // instead of silently saturating into an un-expiring lock.
        let _expiry_slot = clock
            .slot
            .checked_add(timeout_slots)
            .ok_or(BTCPError::Overflow)?;

        // Transfer SOL from funder to vault PDA
        let transfer_ix = system_instruction::transfer(
            &ctx.accounts.vault_funder.key(),
            &ctx.accounts.vault.key(),
            amount,
        );
        invoke(
            &transfer_ix,
            &[
                ctx.accounts.vault_funder.to_account_info(),
                ctx.accounts.vault.to_account_info(),
                ctx.accounts.system_program.to_account_info(),
            ],
        )?;

        // Initialize escrow state
        let escrow = &mut ctx.accounts.escrow;
        escrow.escrow_id = escrow_id;
        escrow.route_id = route_id;
        escrow.intent_hash = intent_hash;
        escrow.entity_id = entity_id;
        escrow.destination = ctx.accounts.destination.key();
        escrow.amount = amount;
        escrow.min_coherence = min_coherence;
        escrow.source_chain = source_chain;
        escrow.dest_chain = dest_chain;
        escrow.anchor_bh = anchor_bh;
        escrow.execution_bh = execution_bh;
        escrow.lock_slot = clock.slot;
        escrow.locked_at = clock.unix_timestamp;
        escrow.timeout_slots = timeout_slots;
        escrow.state = EscrowState::Holding;
        escrow.revert_reason = RevertReason::Timeout;
        escrow.settled_at = 0;
        escrow.reverted_at = 0;
        escrow.locked_by = ctx.accounts.vault_funder.key();
        let (_escrow_pda, escrow_bump) = Pubkey::find_program_address(
            &[SEED_ESCROW, &escrow_id],
            &crate::ID,
        );
        let (_vault_pda, vault_bump) = Pubkey::find_program_address(
            &[SEED_VAULT, &escrow_id],
            &crate::ID,
        );
        escrow.bump = escrow_bump;
        escrow.vault_bump = vault_bump;

        // Increment counter
        ctx.accounts.config.count = ctx
            .accounts
            .config
            .count
            .checked_add(1)
            .ok_or(BTCPError::Overflow)?;

        emit!(EscrowLocked {
            escrow_id,
            route_id,
            intent_hash,
            entity_id,
            destination: ctx.accounts.destination.key(),
            amount,
            min_coherence,
            source_chain,
            dest_chain,
            anchor_bh,
            execution_bh,
            timeout_slots,
        });

        Ok(())
    }

    /// Release escrow to the certificate-bound destination.
    ///
    /// PERMISSIONLESS: any submitter may present the certificate and pays
    /// the consumed-PDA rent; the SUBMITTER HAS NO AUTHORITY — the
    /// canonical certificate is the only release authority (C-03 closure;
    /// the old oracle-key release-authority gate is deleted).
    ///
    /// Verification follows CANONICAL_CERTIFICATE.md §6 steps 1–8 exactly,
    /// fail-closed, in order (see the module docs for the full list);
    /// settlement effects (step 9) only after every check passes.
    pub fn release_escrow(
        ctx: Context<ReleaseEscrow>,
        payload: Vec<u8>,
        cert_epoch: u32,
        envelope: CertificateEnvelopeArg,
    ) -> Result<()> {
        let config = &ctx.accounts.config;
        let registry = &ctx.accounts.registry;
        let escrow = &mut ctx.accounts.escrow;
        let consumed = &mut ctx.accounts.consumed;

        // ── §6 STEP 1 — STRUCTURE (fail-closed) ────────────────────────
        let cert = parse_certificate(&payload)?;
        require!(
            cert.kind == CERT_KIND_ESCROW_RELEASE,
            BTCPError::UnknownCertificateKind
        );
        require!(
            cert.protocol_version <= CERT_SUPPORTED_VERSION,
            BTCPError::VersionIncompatible
        );
        require!(
            envelope.family == CERT_FAMILY_ED25519,
            BTCPError::WrongSignatureFamily
        );
        require!(
            envelope.signatures.len() >= CERT_MIN_SIGNERS,
            BTCPError::InsufficientSigners
        );
        require!(
            envelope.signatures.len() <= MAX_VALIDATORS,
            BTCPError::InvalidValidatorSet
        );
        for sig in &envelope.signatures {
            require!(
                sig.signature.len() == CERT_ED25519_SIG_LEN,
                BTCPError::MalformedSignature
            );
        }
        // distinct validator ids — duplicate signer padding is not
        // consensus (§4 invariant 2) and would double-count power.
        for i in 0..envelope.signatures.len() {
            for j in (i + 1)..envelope.signatures.len() {
                require!(
                    envelope.signatures[i].validator_id
                        != envelope.signatures[j].validator_id,
                    BTCPError::DuplicateSigner
                );
            }
        }
        // The registry-PDA seed argument must equal the payload's epoch —
        // otherwise the loaded registry would not be the one the
        // certificate names (the seeds constraint alone derives from the
        // ARG; this binds ARG == PAYLOAD).
        require!(
            cert.validator_epoch == cert_epoch,
            BTCPError::EpochArgumentMismatch
        );

        // ── §6 STEP 2 — EPOCH (registry + grace; no historical sets) ───
        require!(config.latest_epoch > 0, BTCPError::NoEpochRegistered);
        require!(
            cert.validator_epoch <= config.latest_epoch,
            BTCPError::EpochFuture
        );
        let grace_floor = config.latest_epoch.saturating_sub(CERT_EPOCH_GRACE);
        require!(cert.validator_epoch >= grace_floor, BTCPError::EpochStale);
        require!(
            registry.epoch == cert.validator_epoch,
            BTCPError::RegistryEpochMismatch
        );

        // ── §6 STEP 3 — FRESHNESS (§9; Clock sysvar) ───────────────────
        require!(cert.ttl > 0 && cert.ttl <= CERT_TTL_MAX, BTCPError::InvalidTtl);
        let clock = Clock::get()?;
        require!(clock.unix_timestamp >= 0, BTCPError::InvalidClock);
        let now = clock.unix_timestamp as u64;
        // drift tolerance widens the LOWER bound only; expiry never.
        let now_with_drift = now
            .checked_add(CERT_DRIFT_TOLERANCE_SECS)
            .ok_or(BTCPError::Overflow)?;
        require!(
            cert.issued_at <= now_with_drift,
            BTCPError::CertificateFutureDated
        );
        let expires_at = cert
            .issued_at
            .checked_add(cert.ttl)
            .ok_or(BTCPError::Overflow)?;
        require!(now <= expires_at, BTCPError::CertificateExpired);

        // ── §6 STEP 4 — CONSENSUS PRECONDITIONS (L4.8/MD§17/H-03) ─────
        require!(cert.hhi_at_emission <= CERT_HHI_MAX, BTCPError::HhiCritical);
        require!(cert.awa_enforced == 1, BTCPError::AwaNotEnforced);
        require!(
            cert.coherence >= cert.threshold,
            BTCPError::CoherenceBelowThreshold
        );
        // H-03: the pass bar comes from the REGISTERED epoch threshold,
        // not from the proof — the certificate's bound threshold must
        // agree with the registry's Θ(t).
        require!(registry.threshold == cert.threshold, BTCPError::ThresholdMismatch);
        require!(
            cert.validator_count == registry.validator_count,
            BTCPError::ValidatorCountMismatch
        );
        require!(
            registry.validators.len() as u32 == registry.validator_count,
            BTCPError::RegistryCorrupt
        );
        require!(
            registry.validator_count >= config.min_validator_count,
            BTCPError::TooFewValidators
        );

        // ── §6 STEP 5 — SIGNATURES (batch fail-closed) ─────────────────
        // The submitting transaction must carry native Ed25519SigVerify
        // instructions covering every envelope entry. Introspect them via
        // the instructions sysvar: everything strictly BEFORE the current
        // top-level instruction has already executed (and any failed
        // verification would have aborted the transaction).
        let sysvar_info = ctx.accounts.instructions.to_account_info();
        let current_index = usize::from(
            ix_sysvar::load_current_index_checked(&sysvar_info)
                .map_err(|_| error!(BTCPError::InvalidInstructionSysvar))?,
        );
        let mut tx_instructions: Vec<Instruction> = Vec::with_capacity(current_index);
        for i in 0..current_index {
            tx_instructions.push(
                ix_sysvar::load_instruction_at_checked(i, &sysvar_info)
                    .map_err(|_| error!(BTCPError::InvalidInstructionSysvar))?,
            );
        }
        for sig in &envelope.signatures {
            // 5b — membership in the registered epoch set (the lookup also
            // supplies the verification key).
            let entry = find_validator(registry, &sig.validator_id)
                .ok_or(BTCPError::UnregisteredValidator)?;
            // 5c — envelope weights are CLAIMS, never authority: exact
            // equality with the registered ×1e6 values.
            require!(
                sig.stake_weight == entry.stake_weight,
                BTCPError::WeightClaimMismatch
            );
            require!(
                sig.diversity_weight == entry.diversity_weight,
                BTCPError::WeightClaimMismatch
            );
            // 5a — the RUNTIME (Ed25519SigVerify precompile) verified this
            // exact (registered validator pubkey, envelope signature, RAW
            // 346-byte payload P) triple earlier in this transaction
            // (§3.2 family 2 — ed25519 over raw P). One missing or
            // divergent verification fails the WHOLE certificate.
            verify_ed25519_signature(
                &tx_instructions,
                current_index,
                &payload,
                &entry.ed25519_pubkey,
                &sig.signature,
            )?;
        }

        // ── §6 STEP 6 — QUORUM (recomputed from the REGISTERED set) ────
        let mut total_power: u128 = 0;
        let mut d_sum: u64 = 0;
        for v in &registry.validators {
            total_power = total_power
                .checked_add(u128::from(effective_power(v)?))
                .ok_or(BTCPError::Overflow)?;
            d_sum = d_sum
                .checked_add(v.diversity_weight)
                .ok_or(BTCPError::Overflow)?;
        }
        require!(total_power > 0, BTCPError::ZeroPower);
        // the certificate must not lie about the set it was issued over
        require!(
            u128::from(cert.total_effective_power) == total_power,
            BTCPError::PowerMismatch
        );
        // nor may the registry's stored claim drift from its own entries
        require!(
            u128::from(registry.total_effective_power) == total_power,
            BTCPError::RegistryPowerMismatch
        );

        let mut signed_power: u128 = 0;
        for sig in &envelope.signatures {
            if let Some(entry) = find_validator(registry, &sig.validator_id) {
                signed_power = signed_power
                    .checked_add(u128::from(effective_power(entry)?))
                    .ok_or(BTCPError::Overflow)?;
            }
        }

        // D_consensus = mean(d_j) over the REGISTERED set (×1e6, floor
        // division — ED-X4: recomputed, never certificate-supplied).
        let d_consensus = d_sum / (registry.validators.len() as u64);
        // L4.2 tier table — exact integer arithmetic, u128 products.
        let quorum_met = if d_consensus >= D_CONSENSUS_TIER1 {
            // TIER 1 — STRICT: exactly-2/3 is NOT a quorum (3·signed > 2·total)
            3u128
                .checked_mul(signed_power)
                .ok_or(BTCPError::Overflow)?
                > 2u128
                    .checked_mul(total_power)
                    .ok_or(BTCPError::Overflow)?
        } else if d_consensus >= D_CONSENSUS_TIER2 {
            // TIER 2 — 4·signed ≥ 3·total (0.75)
            4u128
                .checked_mul(signed_power)
                .ok_or(BTCPError::Overflow)?
                >= 3u128
                    .checked_mul(total_power)
                    .ok_or(BTCPError::Overflow)?
        } else {
            // TIER 3 — 20·signed ≥ 17·total (0.85)
            20u128
                .checked_mul(signed_power)
                .ok_or(BTCPError::Overflow)?
                >= 17u128
                    .checked_mul(total_power)
                    .ok_or(BTCPError::Overflow)?
        };
        require!(quorum_met, BTCPError::InsufficientQuorum);

        // ── §6 STEP 7 — BINDING against the escrow's own state ─────────
        require!(cert.escrow_id == escrow.escrow_id, BTCPError::EscrowMismatch);
        require!(cert.route_id == escrow.route_id, BTCPError::RouteMismatch);
        require!(cert.intent_hash == escrow.intent_hash, BTCPError::IntentMismatch);
        require!(cert.entity_id == escrow.entity_id.0, BTCPError::EntityMismatch);
        require!(
            cert.destination == escrow.destination.to_bytes(),
            BTCPError::DestinationMismatch
        );
        require!(cert.amount == escrow.amount, BTCPError::AmountMismatch);
        require!(cert.source_chain == escrow.source_chain, BTCPError::ChainMismatch);
        require!(cert.dest_chain == escrow.dest_chain, BTCPError::ChainMismatch);
        // cross-chain replay firewall: the certificate must name THIS chain
        require!(cert.dest_chain == config.self_chain, BTCPError::WrongChain);
        require!(cert.anchor_bh == escrow.anchor_bh, BTCPError::AnchorMismatch);
        require!(
            cert.execution_bh == escrow.execution_bh,
            BTCPError::ExecutionMismatch
        );
        // escrow-deployment-local tightening (INV-003 discipline): the
        // escrow may require STRICTER coherence than Θ(t), never looser —
        // the floor was etched at lock time, not supplied by the caller.
        require!(
            cert.coherence >= escrow.min_coherence,
            BTCPError::CoherenceInsufficient
        );

        // ── §6 STEP 8 — NONCE / CONSUMED certificate (§8) ─────────────
        // SVM consumed key: SHA-256(P) via the sha256 syscall (see module
        // docs for the documented SHA3 deviation).
        let payload_sha256 = hash::hash(&payload).to_bytes();
        if consumed.is_set == 1 {
            if consumed.cert_sha256 == payload_sha256 {
                // §8.2 idempotent resubmission of the SAME certificate —
                // observability / retry safety, ZERO settlement effect.
                require!(
                    escrow.state == EscrowState::Released,
                    BTCPError::InconsistentReplayState
                );
                return Ok(());
            }
            // Same escrow scope, different certificate: on-chain
            // equivocation evidence (§10.3) — reject and emit for the
            // slashing intake (L4.9 S1).
            emit!(EquivocationDetected {
                escrow_id: escrow.escrow_id,
                epoch: consumed.epoch,
                nonce: consumed.nonce,
                existing_sha256: consumed.cert_sha256,
                new_sha256: payload_sha256,
            });
            return Err(error!(BTCPError::CertificateConflict));
        }

        // ── §6 STEP 9 — settlement guard + effects (exactly once) ─────
        // The escrow state machine is the ultimate exactly-once guard.
        require!(escrow.state == EscrowState::Holding, BTCPError::NotHolding);
        require!(!escrow.is_expired(clock.slot), BTCPError::Expired);
        let amount = escrow.amount;
        require!(
            ctx.accounts.vault.lamports() >= amount,
            BTCPError::InsufficientFunds
        );
        let destination = escrow.destination;
        let route_id = escrow.route_id;
        let escrow_id_bytes = escrow.escrow_id;

        // Record consumption BEFORE the transfer — same transaction,
        // atomic: a failed transfer rolls this back with everything else.
        consumed.is_set = 1;
        consumed.epoch = cert.validator_epoch;
        consumed.nonce = cert.certificate_nonce;
        consumed.cert_sha256 = payload_sha256;

        escrow.state = EscrowState::Released;
        escrow.settled_at = clock.unix_timestamp;

        // Transfer SOL from the vault PDA to the certificate-bound
        // destination (settlement tuple checked at step 7).
        let vault_seeds: &[&[u8]] = &[
            SEED_VAULT,
            &escrow_id_bytes,
            &[escrow.vault_bump],
        ];
        invoke_signed(
            &system_instruction::transfer(
                &ctx.accounts.vault.key(),
                &destination,
                amount,
            ),
            &[
                ctx.accounts.vault.to_account_info(),
                ctx.accounts.destination.to_account_info(),
                ctx.accounts.system_program.to_account_info(),
            ],
            &[vault_seeds],
        )?;

        emit!(EscrowReleased {
            escrow_id: escrow_id_bytes,
            route_id,
            execution_bh: cert.execution_bh,
            coherence: cert.coherence,
            epoch: cert.validator_epoch,
            nonce: cert.certificate_nonce,
            cert_sha256: payload_sha256,
            settled_at: clock.unix_timestamp,
        });

        Ok(())
    }

    /// Revert escrow — return funds to the original locker.
    ///
    /// - Anyone can call on timeout (permissionless escape).
    /// - Anyone can call after 7 days (E6 emergency escape — even if
    ///   TRION is silent or the program is paused).
    /// - Otherwise only relayer/owner.
    pub fn revert_escrow(ctx: Context<RevertEscrow>, reason: u8) -> Result<()> {
        let escrow = &mut ctx.accounts.escrow;
        require!(escrow.state == EscrowState::Holding, BTCPError::NotHolding);

        let clock = Clock::get()?;
        let is_timeout = escrow.is_expired(clock.slot);

        let revert_reason = match reason {
            0 => RevertReason::Timeout,
            1 => RevertReason::CoherenceFailure,
            2 => RevertReason::RouteInvalid,
            3 => RevertReason::Manual,
            4 => RevertReason::Emergency,
            _ => return Err(error!(BTCPError::InvalidAction)),
        };

        // E6 — the 7-day permissionless emergency escape (checked math:
        // locked_at + 7d must not overflow i64).
        let emergency_ready = clock.unix_timestamp
            >= escrow
                .locked_at
                .checked_add(EMERGENCY_REVERT_SECONDS)
                .ok_or(BTCPError::Overflow)?;

        if !is_timeout && !emergency_ready {
            // Non-timeout, non-emergency: must be relayer or owner.
            require!(
                ctx.accounts.config.is_authorized(&ctx.accounts.caller.key()),
                BTCPError::NotRelayerForRevert
            );
            require!(
                revert_reason != RevertReason::Timeout,
                BTCPError::NotRelayerForRevert
            );
        }

        let amount = escrow.amount;
        let locked_by = escrow.locked_by;
        let escrow_id = escrow.escrow_id;
        let vault_bump = escrow.vault_bump;

        escrow.revert_reason = revert_reason;
        escrow.reverted_at = clock.unix_timestamp;
        escrow.state = if revert_reason == RevertReason::Emergency {
            EscrowState::EmergencyReverted
        } else {
            EscrowState::Reverted
        };

        // Transfer SOL from vault back to locker
        let vault_seeds: &[&[u8]] = &[
            SEED_VAULT,
            &escrow_id,
            &[vault_bump],
        ];
        invoke_signed(
            &system_instruction::transfer(
                &ctx.accounts.vault.key(),
                &locked_by,
                amount,
            ),
            &[
                ctx.accounts.vault.to_account_info(),
                ctx.accounts.locked_by.to_account_info(),
                ctx.accounts.system_program.to_account_info(),
            ],
            &[vault_seeds],
        )?;

        emit!(EscrowReverted {
            escrow_id,
            reason: revert_reason as u8,
            reverted_at: clock.unix_timestamp,
        });

        Ok(())
    }

    /// Update relayer address. Only owner.
    pub fn set_relayer(ctx: Context<SetRelayer>, new_relayer: Pubkey) -> Result<()> {
        let config = &mut ctx.accounts.config;
        require!(config.is_owner(&ctx.accounts.owner.key()), BTCPError::NotOwner);

        let old_relayer = config.relayer;
        config.relayer = new_relayer;

        emit!(RelayerUpdated { old_relayer, new_relayer });
        Ok(())
    }

    /// Update the validator-registry admin (registrar role separation).
    /// Only owner.
    pub fn set_registry_admin(ctx: Context<SetRegistryAdmin>, new_admin: Pubkey) -> Result<()> {
        let config = &mut ctx.accounts.config;
        require!(config.is_owner(&ctx.accounts.owner.key()), BTCPError::NotOwner);
        require!(new_admin != Pubkey::default(), BTCPError::InvalidArgument);

        let old_admin = config.registry_admin;
        config.registry_admin = new_admin;

        emit!(RegistryAdminUpdated { old_admin, new_admin });
        Ok(())
    }

    /// Bind the TRION pause authority — the ONLY remaining role of the
    /// formerly-omnipotent oracle key (C-03): it may PAUSE new locks; it
    /// can NEVER release escrows. One-way by policy: once a non-default
    /// authority is bound it cannot be replaced. Owner-gated.
    pub fn bind_pause_authority(
        ctx: Context<BindPauseAuthority>,
        new_authority: Pubkey,
    ) -> Result<()> {
        let config = &mut ctx.accounts.config;
        require!(config.is_owner(&ctx.accounts.owner.key()), BTCPError::NotOwner);
        require!(new_authority != Pubkey::default(), BTCPError::InvalidArgument);
        // One-way: an already-bound authority cannot be replaced.
        require!(
            config.pause_authority == Pubkey::default(),
            BTCPError::NotAuthorized
        );

        config.pause_authority = new_authority;
        emit!(PauseAuthorityBound { pause_authority: new_authority });
        Ok(())
    }

    /// Pause — blocks NEW lock_escrow only. Authority: the bound pause
    /// authority (the old oracle key) or the owner. Release (certificate
    /// path) and revert (timeout / 7-day emergency) are NEVER pausable.
    pub fn pause(ctx: Context<PauseUnpause>) -> Result<()> {
        let config = &mut ctx.accounts.config;
        let signer = ctx.accounts.authority.key();
        require!(
            config.is_pause_authority(&signer),
            BTCPError::NotAuthorized
        );
        require!(!config.paused, BTCPError::InvalidArgument);
        config.paused = true;
        emit!(EscrowPaused { by: signer });
        Ok(())
    }

    /// Un-pause. Same authority as pause.
    pub fn unpause(ctx: Context<PauseUnpause>) -> Result<()> {
        let config = &mut ctx.accounts.config;
        let signer = ctx.accounts.authority.key();
        require!(
            config.is_pause_authority(&signer),
            BTCPError::NotAuthorized
        );
        require!(config.paused, BTCPError::InvalidArgument);
        config.paused = false;
        emit!(EscrowUnpaused { by: signer });
        Ok(())
    }
}

// ── Context Structs ─────────────────────────────────────────────────────────

#[derive(Accounts)]
pub struct Initialize<'info> {
    #[account(
        init,
        payer = payer,
        space = ProgramConfig::SIZE,
        seeds = [SEED_CONFIG],
        bump,
    )]
    pub config: Account<'info, ProgramConfig>,

    #[account(mut)]
    pub payer: Signer<'info>,

    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
#[instruction(epoch: u32, entries: Vec<ValidatorEntry>)]
pub struct RegisterEpoch<'info> {
    #[account(
        mut,
        seeds = [SEED_CONFIG],
        bump = config.bump,
    )]
    pub config: Account<'info, ProgramConfig>,

    /// Epoch-registry PDA — ["trion", "validators", epoch_be]. `init`
    /// guarantees the epoch set is created exactly once (an existing
    /// account at these seeds fails the instruction).
    #[account(
        init,
        payer = admin,
        space = TrionEpochRegistry::space_for(entries.len()),
        seeds = [SEED_TRION, SEED_VALIDATORS, &epoch.to_be_bytes()],
        bump,
    )]
    pub registry: Account<'info, TrionEpochRegistry>,

    /// Must be the registry_admin (checked in the instruction body —
    /// role separation per master command §10). Also pays rent.
    #[account(mut)]
    pub admin: Signer<'info>,

    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
#[instruction(escrow_id: [u8; 32])]
pub struct LockEscrow<'info> {
    #[account(mut, seeds = [SEED_CONFIG], bump = config.bump)]
    pub config: Account<'info, ProgramConfig>,

    /// Must be owner or relayer (pays rent for the escrow account init)
    #[account(mut)]
    pub relayer: Signer<'info>,

    /// Account that provides the SOL to lock (must have at least `amount`
    /// lamports — only the specified amount is transferred, NOT the whole
    /// balance)
    #[account(mut)]
    pub vault_funder: Signer<'info>,

    /// Escrow state PDA
    #[account(
        init,
        payer = relayer,
        space = Escrow::SIZE,
        seeds = [SEED_ESCROW, &escrow_id],
        bump,
    )]
    pub escrow: Account<'info, Escrow>,

    /// Vault PDA that holds the SOL
    /// CHECK: This is a PDA that receives SOL; validated by seeds
    #[account(
        mut,
        seeds = [SEED_VAULT, &escrow_id],
        bump,
    )]
    pub vault: AccountInfo<'info>,

    /// Destination address that receives funds on release
    /// CHECK: Destination is arbitrary; stored in escrow state and bound
    /// into every release certificate (settlement tuple, §6 step 7)
    pub destination: AccountInfo<'info>,

    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
#[instruction(payload: Vec<u8>, cert_epoch: u32)]
pub struct ReleaseEscrow<'info> {
    #[account(seeds = [SEED_CONFIG], bump = config.bump)]
    pub config: Account<'info, ProgramConfig>,

    /// Permissionless submitter — carries NO release authority (the
    /// certificate is the authority); pays rent for the consumed PDA.
    #[account(mut)]
    pub submitter: Signer<'info>,

    /// TRION epoch registry PDA for the certificate's epoch. Existence
    /// and derivation are enforced by the seeds constraint (a registry
    /// for an unregistered epoch simply does not exist → fail-closed);
    /// grace-freshness vs `config.latest_epoch` is enforced in the body.
    /// CHECK: Account<'info, T> enforces program ownership + discriminator.
    #[account(
        seeds = [SEED_TRION, SEED_VALIDATORS, &cert_epoch.to_be_bytes()],
        bump,
    )]
    pub registry: Account<'info, TrionEpochRegistry>,

    #[account(
        mut,
        seeds = [SEED_ESCROW, &escrow.escrow_id],
        bump = escrow.bump,
        constraint = escrow.escrow_id != [0u8; 32] @ BTCPError::EscrowNotFound,
    )]
    pub escrow: Account<'info, Escrow>,

    /// Vault PDA holding the SOL
    /// CHECK: PDA derived from the escrow's own escrow_id + stored bump
    #[account(
        mut,
        seeds = [SEED_VAULT, &escrow.escrow_id],
        bump = escrow.vault_bump,
    )]
    pub vault: AccountInfo<'info>,

    /// Destination account — must match escrow.destination (constraint)
    /// AND the certificate's settlement tuple (instruction body, step 7).
    /// CHECK: address constrained to escrow.destination
    #[account(mut, address = escrow.destination @ BTCPError::DestinationMismatch)]
    pub destination: AccountInfo<'info>,

    /// Consumed-certificate PDA (replay/equivocation tracking, §8).
    /// init_if_needed + tx atomicity: a persisted account implies a prior
    /// successful release; a failed verification rolls creation back.
    /// CHECK: Account<'info, T> enforces program ownership + discriminator.
    #[account(
        init_if_needed,
        payer = submitter,
        space = ConsumedCertificate::SIZE,
        seeds = [SEED_TRION, SEED_CONSUMED, &escrow.escrow_id],
        bump,
    )]
    pub consumed: Account<'info, ConsumedCertificate>,

    /// The instructions sysvar — the introspection source for the
    /// runtime-verified Ed25519SigVerify instructions (§6 step 5a).
    /// CHECK: constrained to the canonical instructions-sysvar address;
    /// the `_checked` loaders additionally verify it.
    #[account(address = ix_sysvar::id())]
    pub instructions: AccountInfo<'info>,

    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct RevertEscrow<'info> {
    #[account(seeds = [SEED_CONFIG], bump = config.bump)]
    pub config: Account<'info, ProgramConfig>,

    /// Can be anyone (for timeout / 7-day emergency) or relayer/owner
    pub caller: Signer<'info>,

    #[account(
        mut,
        seeds = [SEED_ESCROW, &escrow.escrow_id],
        bump = escrow.bump,
        constraint = escrow.escrow_id != [0u8; 32] @ BTCPError::EscrowNotFound,
    )]
    pub escrow: Account<'info, Escrow>,

    /// Vault PDA holding the SOL
    /// CHECK: Validated by seeds
    #[account(
        mut,
        seeds = [SEED_VAULT, &escrow.escrow_id],
        bump = escrow.vault_bump,
    )]
    pub vault: AccountInfo<'info>,

    /// Original locker (gets refund)
    /// CHECK: Verified against escrow.locked_by
    #[account(mut, address = escrow.locked_by @ BTCPError::RefundFailed)]
    pub locked_by: AccountInfo<'info>,

    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct SetRelayer<'info> {
    #[account(mut, seeds = [SEED_CONFIG], bump = config.bump)]
    pub config: Account<'info, ProgramConfig>,

    pub owner: Signer<'info>,
}

#[derive(Accounts)]
pub struct SetRegistryAdmin<'info> {
    #[account(mut, seeds = [SEED_CONFIG], bump = config.bump)]
    pub config: Account<'info, ProgramConfig>,

    pub owner: Signer<'info>,
}

#[derive(Accounts)]
pub struct BindPauseAuthority<'info> {
    #[account(mut, seeds = [SEED_CONFIG], bump = config.bump)]
    pub config: Account<'info, ProgramConfig>,

    pub owner: Signer<'info>,
}

#[derive(Accounts)]
pub struct PauseUnpause<'info> {
    #[account(mut, seeds = [SEED_CONFIG], bump = config.bump)]
    pub config: Account<'info, ProgramConfig>,

    pub authority: Signer<'info>,
}

// ── Events ──────────────────────────────────────────────────────────────────

#[event]
pub struct EscrowLocked {
    #[index]
    pub escrow_id: [u8; 32],
    #[index]
    pub route_id: [u8; 32],
    #[index]
    pub intent_hash: [u8; 32],
    pub entity_id: BEOIdentity,
    pub destination: Pubkey,
    pub amount: u64,
    pub min_coherence: u64,
    pub source_chain: u32,
    pub dest_chain: u32,
    pub anchor_bh: [u8; 32],
    pub execution_bh: [u8; 32],
    pub timeout_slots: u64,
}

#[event]
pub struct EscrowReleased {
    #[index]
    pub escrow_id: [u8; 32],
    #[index]
    pub route_id: [u8; 32],
    pub execution_bh: [u8; 32],
    pub coherence: u64,
    pub epoch: u32,
    pub nonce: u64,
    /// SHA-256(P) — the SVM consumed key (see module docs for the
    /// documented SHA3 deviation).
    pub cert_sha256: [u8; 32],
    pub settled_at: i64,
}

#[event]
pub struct EscrowReverted {
    #[index]
    pub escrow_id: [u8; 32],
    pub reason: u8,
    pub reverted_at: i64,
}

#[event]
pub struct EquivocationDetected {
    #[index]
    pub escrow_id: [u8; 32],
    pub epoch: u32,
    pub nonce: u64,
    pub existing_sha256: [u8; 32],
    pub new_sha256: [u8; 32],
}

#[event]
pub struct EpochRegistered {
    #[index]
    pub epoch: u32,
    pub validator_count: u32,
    pub total_effective_power: u64,
    pub threshold: u64,
    pub set_root: [u8; 32],
}

#[event]
pub struct RelayerUpdated {
    #[index]
    pub old_relayer: Pubkey,
    #[index]
    pub new_relayer: Pubkey,
}

#[event]
pub struct RegistryAdminUpdated {
    #[index]
    pub old_admin: Pubkey,
    #[index]
    pub new_admin: Pubkey,
}

#[event]
pub struct PauseAuthorityBound {
    #[index]
    pub pause_authority: Pubkey,
}

#[event]
pub struct EscrowPaused {
    #[index]
    pub by: Pubkey,
}

#[event]
pub struct EscrowUnpaused {
    #[index]
    pub by: Pubkey,
}
