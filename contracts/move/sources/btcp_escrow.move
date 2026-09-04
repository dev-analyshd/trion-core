/// BTCP Zero-Bridge Escrow — Move VM implementation (Aptos / Movement)
/// =====================================================================
/// Two-state atomic escrow: HOLDING → RELEASED | REVERTED (+ escape
/// hatches), funds never leave the source Move chain (BTCP §4.3 six-step
/// execution, §11 five final fixes; zero-bridge paradigm).
///
/// ═════════════════════════════════════════════════════════════════════
/// WAVE 2 / AGENT I — CLOSURE OF AUDIT FINDING C-02 (CRITICAL)
/// ═════════════════════════════════════════════════════════════════════
/// The pre-Wave-2 release path was:
///
///     verify_coherence(relayer, escrow_addr)   // relayer flips a bool
///     release_escrow(relayer, escrow_addr)     // requires the bool
///
/// i.e. RELEASE AUTHORITY = one relayer key flipping
/// `esc.coherence_verified` with ZERO on-chain verification
/// (contracts/move/sources/btcp_escrow.move:120-138, 196-207 at the
/// audit HEAD). That flag — and the entire `verify_coherence` entry
/// point — is REMOVED. Release authority is now EXACTLY ONE thing:
///
///     a canonical TRION certificate (CANONICAL_CERTIFICATE.md §2)
///     carrying a diversity-weighted Ed25519 quorum of the REGISTERED
///     epoch validator set, bound to THIS escrow.
///
/// Why removed outright instead of kept behind a dev flag: a dev-mode
/// resource that any admin call can create is reachable on mainnet by
/// construction; a `#[test_only]` path cannot be exercised without a
/// Move toolchain and provides false comfort. The relayer retains ONLY
/// safe-direction authorities (non-timeout revert → funds return to the
/// LOCKER; enter_pending_akashic marking) — a compromised relayer key
/// can no longer route funds anywhere except back to their owner.
///
/// RELEASE IS PERMISSIONLESS: any account may submit the certificate
/// (mirroring the Vyper tier's permissionless `release()` and the EVM
/// `submitRouteAttestation` discipline) — security is the quorum, not
/// the caller. The submitter gains nothing (settlement goes to the
/// certificate's bound destination, which must equal the escrow's).
///
/// ═════════════════════════════════════════════════════════════════════
/// CAPABILITY / AUTHORITY MAP (master command §11 audit)
/// ═════════════════════════════════════════════════════════════════════
///   Holder                    Capability              May do
///   ───────────────────────── ────────────────────── ──────────────────
///   @trion account key        epoch_registry::        publish an epoch
///   (registrar, one tx per    EpochAdminCap           validator set
///   epoch, §10.2)                                     (strict +1 order)
///   @trion account key        btcp_escrow::           set_relayer,
///   (deployment admin)        EscrowAdminCap          pause, unpause
///   the locking entity        own funds (self-        lock_escrow
///   (any Coin holder)         custody)
///   ANY account (no signer    a valid canonical       release_escrow —
///   authority at all)         certificate quorum      the ONLY release
///                                                     path
///   relayer (EscrowConfig)    safe-direction only     revert (non-
///                                                     timeout),
///                                                     enter_pending_
///                                                     akashic
///   ANY account               time / 7-day elapsed    revert_escrow
///                                                     (timeout),
///                                                     emergency_revert
///
///   • No mint authority exists: the module never mints; it can only
///     move the Coin that lock_escrow placed inside the escrow resource.
///   • Resource-safety: `Escrow` (has key, no drop) is stored under the
///     escrow account; its `held_coin` field is readable/writable ONLY
///     through this module (Move field privacy). A foreign module can
///     relocate the whole resource but cannot extract the Coin (no
///     field access, no drop); value is conserved until release/revert.
///   • EscrowAdminCap and EpochAdminCap are `has key` only — no copy,
///     no drop, no forge.
///
/// ═════════════════════════════════════════════════════════════════════
/// RELEASE PATH — CANONICAL §6 VERIFICATION, IN ORDER, FAIL-CLOSED
/// ═════════════════════════════════════════════════════════════════════
///   1. STRUCTURE        346-byte P, domain tag, kind, version, ttl,
///                       dest_chain, AWA, HHI, isSafe, scales
///                        (trion::canonical_cert::verify_structure)
///   2. EPOCH            registered + not-future + within grace (§6.2)
///   3. FRESHNESS        issued_at − 60s ≤ now ≤ issued_at + ttl (§9)
///   4. PRECONDITIONS    validator_count & total_effective_power equal
///                       the REGISTERED set (§6.4) + escrow's own
///                       min_coherence floor (INV-003)
///   5. SIGNATURES       every Ed25519 sig verified against the
///                       REGISTERED pubkey; weight claims cross-checked
///                       (§6.5) — batch fail-closed
///   6. QUORUM           L4.2 tier table in u128 integer math over
///                       REGISTERED weights (§6.6) — strict 2/3
///                       at tier 1; 0.75 / 0.85 at tiers 2/3
///   7. BINDING          escrow_id (= BCS of the escrow account
///                       address — not caller-chosen), route_id,
///                       intent_hash, entity_id, source/dest chain,
///                       destination, amount, anchor_bh, execution_bh
///                       all equal the escrow's own lock-time record
///   8. NONCE/CONSUMED   certificate_nonce strictly increasing per
///                       (epoch, escrow_id); same-hash resubmission is
///                       an idempotent no-op; terminal states are the
///                       exactly-once guard (§8)
///   9. EFFECTS          state → RELEASED BEFORE the transfer
///                       (check-effects-interactions, M2 discipline),
///                       consumed epoch/nonce/hash recorded, then the
///                       Coin moves to the bound destination
///
/// Steps 1–6 live in trion::epoch_registry::verify_certificate (the
/// registry owns the validator set); steps 7–9 live here (they are
/// escrow state). NO caller-supplied coherence/threshold/quorum value
/// exists anywhere on the release path.
module trion::btcp_escrow {
    use std::signer;
    use std::vector;
    use std::bcs;
    use aptos_framework::coin;
    use aptos_framework::timestamp;
    use aptos_framework::event;
    use trion::canonical_cert;
    use trion::epoch_registry::{Self, CertificateSignature};

    // ── Escrow states (M2: 3 terminal, frozen — no outgoing edges) ────
    const HOLDING:            u8 = 0;
    const PENDING_AKASHIC:    u8 = 1;
    const RELEASED:           u8 = 2;
    const REVERTED:           u8 = 3;
    const EMERGENCY_REVERTED: u8 = 4;

    /// Gap-8 absolute escape hatch: after 7 days ANYONE can revert.
    const EMERGENCY_ESCAPE_SECONDS: u64 = 7 * 24 * 60 * 60;
    /// E1: 24h PENDING_AKASHIC recovery window.
    const AKASHIC_RECOVERY_SECONDS: u64 = 24 * 60 * 60;
    /// INV-003: protocol coherence floor (Σ-floor 0.55 — the same
    /// constant as core/btcp/escrow_monitor.py::MIN_COHERENCE_FLOOR and
    /// the proof builder's DEFAULT_COHERENCE_THRESHOLD). A locker may
    /// TIGHTEN their gate (up to 1.0); never loosen it below the floor.
    const MIN_COHERENCE_FLOOR: u64 = 550_000; // ×1e6
    const COHERENCE_CAP: u64 = 1_000_000;     // ×1e6
    /// Escrow timeout is capped at the emergency-escape horizon: a longer
    /// timeout is dead configuration (emergency_revert fires first at 7
    /// days) and would only invite u64 overflow games. This cap also
    /// makes `lock_timestamp + timeout_seconds` overflow-free by
    /// construction (lock_timestamp is real chain time).
    const MAX_TIMEOUT_SECONDS: u64 = 7 * 24 * 60 * 60;

    const BYTES32: u64 = 32;

    // ── Error codes ────────────────────────────────────────────────────
    const E_NOT_FOUND:               u64 = 1;
    const E_INVALID_STATE:           u64 = 2;
    const E_ZERO_AMOUNT:             u64 = 3;
    const E_EMERGENCY_NOT_YET:        u64 = 4;
    const E_NOT_RELAYER:             u64 = 5;
    const E_PAUSED:                  u64 = 6;
    const E_NOT_INITIALIZED:         u64 = 7;
    const E_NOT_MODULE_ACCOUNT:      u64 = 8;
    const E_ALREADY_INITIALIZED:     u64 = 9;
    const E_NO_ADMIN_CAP:            u64 = 10;
    const E_FIELD_WIDTH:             u64 = 11; // 32-byte field malformed
    const E_TIMEOUT_BOUNDS:          u64 = 12;
    const E_COHERENCE_FLOOR:         u64 = 13; // INV-003: below 0.55
    const E_COHERENCE_CAP:           u64 = 14; // above 1.0
    // §6 step 7 binding failures (each names the exact mismatch).
    const E_ESCROW_ID_MISMATCH:      u64 = 15;
    const E_ROUTE_MISMATCH:          u64 = 16;
    const E_INTENT_MISMATCH:         u64 = 17;
    const E_ENTITY_MISMATCH:         u64 = 18;
    const E_SOURCE_CHAIN_MISMATCH:   u64 = 19;
    const E_DEST_CHAIN_MISMATCH:     u64 = 20;
    const E_DESTINATION_MISMATCH:    u64 = 21;
    const E_AMOUNT_MISMATCH:         u64 = 22;
    const E_AMOUNT_TOO_LARGE:        u64 = 23; // u256 > u64 horizon
    const E_ANCHOR_MISMATCH:         u64 = 24;
    const E_EXECUTION_BH_MISMATCH:   u64 = 25;
    // §6 step 8 / escrow-local gate.
    const E_MIN_COHERENCE_NOT_MET:   u64 = 26; // cert C(t) < escrow floor
    const E_STALE_NONCE:             u64 = 27; // replay of an older cert
    const E_SIG_ARRAY_WIDTH:         u64 = 28; // parallel arrays disagree
    const E_COIN_MISMATCH:           u64 = 29; // coin value ≠ declared amount

    // ── Revert reasons (parity with the Cairo/Solidity tiers) ─────────
    const REASON_TIMEOUT:            u8 = 0;
    const REASON_COHERENCE_FAILURE:  u8 = 1;
    const REASON_ROUTE_INVALID:      u8 = 2;
    const REASON_MANUAL:             u8 = 3;
    const REASON_AKASHIC_OUTAGE:     u8 = 4;
    const REASON_EMERGENCY_ESCAPE:   u8 = 6;

    // ── Resources ──────────────────────────────────────────────────────

    /// The escrow itself, under the locking entity's account (one escrow
    /// per account). `has key` only: it cannot be copied or dropped —
    /// value inside is conserved until release/revert/emergency.
    struct Escrow has key {
        // §6 step 7 binding record — everything the certificate must
        // equal. Fixed at lock time; the locker can only brick THEIR
        // OWN escrow by choosing mismatched values (fail-closed).
        route_id:       vector<u8>,   // bytes32
        intent_hash:    vector<u8>,   // bytes32 (§4.1 intent commitment)
        entity_id:      vector<u8>,   // bytes32 (BEO identity)
        anchor_bh:      vector<u8>,   // bytes32 (CANONICAL_BH)
        execution_bh:   vector<u8>,   // bytes32 (CANONICAL_BH)
        source_chain:   u64,          // TRION registry chain id
        dest_chain:     u64,          // TRION registry chain id
        destination:    address,      // 32-byte Move address
        amount:         u64,          // raw destination-native units
        min_coherence:  u64,          // ×1e6, INV-003-clamped at lock
        // lifecycle
        lock_timestamp:  u64,
        timeout_seconds: u64,
        state:           u8,
        locked_by:       address,
        // §8 replay record (nonce scope: (validator_epoch, escrow_id)).
        consumed_epoch:  u64,
        consumed_nonce:  u64,
        released_cert_hash: vector<u8>,  // bytes32 — idempotent resubmit
        // The Coin never leaves this resource until release/revert.
        held_coin:       coin::Coin<TrionToken>,
    }

    /// Placeholder phantom coin type for the TRION token (declared
    /// elsewhere in the live system; reproduced so this module is
    /// self-contained for static verification).
    struct TrionToken {}

    /// Deployment configuration under @trion (module account — the
    /// deployment binding, following the trion::btcp_intent scheme).
    /// `relayer` keeps ONLY safe-direction authorities (see header):
    /// non-timeout revert and enter_pending_akashic.
    struct EscrowConfig has key {
        relayer: address,
        paused: bool,
    }

    /// Escrow administration capability (set_relayer / pause / unpause),
    /// created once by initialize under @trion. `has key` only.
    struct EscrowAdminCap has key {}

    // ── Events ─────────────────────────────────────────────────────────

    #[event]
    struct EscrowLocked has drop, store {
        escrow_addr: address,
        route_id: vector<u8>,
        entity_id: vector<u8>,
        destination: address,
        amount: u64,
        dest_chain: u64,
    }

    #[event]
    struct EscrowReleased has drop, store {
        escrow_addr: address,
        certificate_hash: vector<u8>,
        validator_epoch: u64,
        certificate_nonce: u64,
        signed_power: u128,   // ×1e6
        total_power: u128,    // ×1e6
        quorum_tier: u8,
        submitter: address,
    }

    #[event]
    struct EscrowReverted has drop, store {
        escrow_addr: address,
        reason: u8,
    }

    #[event]
    struct EmergencyReverted has drop, store {
        escrow_addr: address,
    }

    #[event]
    struct EscrowPaused has drop, store {
        by: address,
    }

    #[event]
    struct EscrowUnpaused has drop, store {
        by: address,
    }

    // ── Module init (once, @trion only) ───────────────────────────────

    /// Publish EscrowConfig (relayer + paused=false) under @trion and
    /// mint the EscrowAdminCap to the initializing account. Fail-closed
    /// from any account other than @trion: every other entry point reads
    /// the config at @trion.
    public entry fun initialize(admin: &signer) {
        let addr = signer::address_of(admin);
        assert!(addr == @trion, E_NOT_MODULE_ACCOUNT);
        assert!(!exists<EscrowConfig>(@trion), E_ALREADY_INITIALIZED);
        move_to(admin, EscrowConfig {
            relayer: addr,
            paused: false,
        });
        move_to(admin, EscrowAdminCap {});
    }

    /// Rotate the EscrowAdminCap (key ceremony). Both signers required.
    public entry fun transfer_admin(current: &signer, new_admin: &signer) acquires EscrowAdminCap {
        let from = signer::address_of(current);
        assert!(exists<EscrowAdminCap>(from), E_NO_ADMIN_CAP);
        let cap = move_from<EscrowAdminCap>(from);
        move_to(new_admin, cap);
    }

    /// Rotate the safe-direction relayer (EscrowAdminCap required).
    public entry fun set_relayer(admin: &signer, new_relayer: address) acquires EscrowConfig {
        let addr = signer::address_of(admin);
        assert!(exists<EscrowAdminCap>(addr), E_NO_ADMIN_CAP);
        let config = borrow_global_mut<EscrowConfig>(@trion);
        config.relayer = new_relayer;
    }

    /// Circuit breaker (EscrowAdminCap required).
    ///
    /// DELIBERATE DESIGN (documented deviation from the Solidity tier's
    /// ingress-only pause): here `paused` blocks lock AND release. This
    /// is the C-02 remediation breaker — if the validator fleet or the
    /// registrar is compromised, forged-certificate releases STOP, while
    /// every egress hatch stays open (timeout revert, non-timeout relayer
    /// revert, and the permissionless 7-day emergency revert). Funds can
    /// never be frozen past the 7-day horizon; they can only be returned
    /// to their locker.
    public entry fun pause(admin: &signer) acquires EscrowConfig {
        let addr = signer::address_of(admin);
        assert!(exists<EscrowAdminCap>(addr), E_NO_ADMIN_CAP);
        let config = borrow_global_mut<EscrowConfig>(@trion);
        config.paused = true;
        event::emit(EscrowPaused { by: addr });
    }

    public entry fun unpause(admin: &signer) acquires EscrowConfig {
        let addr = signer::address_of(admin);
        assert!(exists<EscrowAdminCap>(addr), E_NO_ADMIN_CAP);
        let config = borrow_global_mut<EscrowConfig>(@trion);
        config.paused = false;
        event::emit(EscrowUnpaused { by: addr });
    }

    /// Safe-direction authority check (revert / pending-akashic only —
    /// this is NOT a release authority; release needs the certificate).
    fun assert_relayer(account: &signer) acquires EscrowConfig {
        assert!(exists<EscrowConfig>(@trion), E_NOT_INITIALIZED);
        let addr = signer::address_of(account);
        let config = borrow_global<EscrowConfig>(@trion);
        assert!(config.relayer == addr, E_NOT_RELAYER);
    }

    // ── Lock (value ingress — paused blocks NEW locks, E1) ────────────

    /// The entity locks Coin<T> in escrow, recording the full §6 step 7
    /// binding tuple the future certificate must match. The escrow_id is
    /// NOT caller-chosen: it is the BCS encoding of the escrow account's
    /// own address (32 bytes on Aptos/Sui) — a certificate for any other
    /// escrow id cannot release this escrow.
    public entry fun lock_escrow(
        entity: &signer,
        route_id: vector<u8>,
        intent_hash: vector<u8>,
        entity_id: vector<u8>,
        anchor_bh: vector<u8>,
        execution_bh: vector<u8>,
        source_chain: u64,
        dest_chain: u64,
        destination: address,
        amount: u64,
        min_coherence: u64,
        timeout_seconds: u64,
        to_lock: coin::Coin<TrionToken>,
    ) acquires EscrowConfig {
        let addr = signer::address_of(entity);
        assert!(exists<EscrowConfig>(@trion), E_NOT_INITIALIZED);
        assert!(!borrow_global<EscrowConfig>(@trion).paused, E_PAUSED);
        // One escrow per account (pre-existing layout constraint).
        assert!(!exists<Escrow>(addr), E_INVALID_STATE);
        assert!(amount > 0, E_ZERO_AMOUNT);
        assert!(coin::value(&to_lock) == amount, E_COIN_MISMATCH);
        // §6 step 7 binding fields — exact bytes32 widths.
        assert!(vector::length(&route_id) == BYTES32, E_FIELD_WIDTH);
        assert!(vector::length(&intent_hash) == BYTES32, E_FIELD_WIDTH);
        assert!(vector::length(&entity_id) == BYTES32, E_FIELD_WIDTH);
        assert!(vector::length(&anchor_bh) == BYTES32, E_FIELD_WIDTH);
        assert!(vector::length(&execution_bh) == BYTES32, E_FIELD_WIDTH);
        // INV-003: the coherence gate may tighten, never loosen.
        assert!(min_coherence >= MIN_COHERENCE_FLOOR, E_COHERENCE_FLOOR);
        assert!(min_coherence <= COHERENCE_CAP, E_COHERENCE_CAP);
        // Timeout discipline: > 0, ≤ the 7-day emergency horizon (this
        // bound makes every later `lock_timestamp + timeout_seconds`
        // u64-overflow-free by construction).
        assert!(timeout_seconds > 0, E_TIMEOUT_BOUNDS);
        assert!(timeout_seconds <= MAX_TIMEOUT_SECONDS, E_TIMEOUT_BOUNDS);
        // dest_chain is the cross-VM replay firewall — must be bound.
        assert!(dest_chain != 0, E_DEST_CHAIN_MISMATCH);

        move_to(entity, Escrow {
            route_id,
            intent_hash,
            entity_id,
            anchor_bh,
            execution_bh,
            source_chain,
            dest_chain,
            destination,
            amount,
            min_coherence,
            lock_timestamp: timestamp::now_seconds(),
            timeout_seconds,
            state: HOLDING,
            locked_by: addr,
            consumed_epoch: 0,
            consumed_nonce: 0,
            released_cert_hash: vector::empty<u8>(),
            held_coin: to_lock,
        });
        // Event fields are read back OUT of the stored resource (single
        // ownership of the moved values — no use-after-move surface).
        {
            let esc = borrow_global<Escrow>(addr);
            event::emit(EscrowLocked {
                escrow_addr: addr,
                route_id: esc.route_id,
                entity_id: esc.entity_id,
                destination: esc.destination,
                amount: esc.amount,
                dest_chain: esc.dest_chain,
            });
        };
    }

    // ── Release (permissionless; certificate-gated; C-02 closure) ─────

    /// THE release path. `submitter` carries NO authority (any account
    /// may relay a certificate — observability and censorship
    /// resistance); the ONLY authority is the certificate's quorum.
    ///
    /// Envelope input is four parallel arrays (primitive types only —
    /// maximally robust across wallets/CLIs/toolchains); they are
    /// assembled into §4 CertificateSignature entries and validated
    /// together: same length, distinct validator ids, 64-byte
    /// signatures, weight claims (cross-checked against the registry).
    public entry fun release_escrow(
        submitter: &signer,
        escrow_addr: address,
        payload: vector<u8>,
        validator_ids: vector<vector<u8>>,
        stake_claims: vector<u64>,
        diversity_claims: vector<u64>,
        signatures: vector<vector<u8>>,
    ) acquires Escrow, EscrowConfig {
        assert!(vector::length(&payload) == canonical_cert::payload_width(), E_FIELD_WIDTH);
        let n = vector::length(&validator_ids);
        assert!(n == vector::length(&stake_claims), E_SIG_ARRAY_WIDTH);
        assert!(n == vector::length(&diversity_claims), E_SIG_ARRAY_WIDTH);
        assert!(n == vector::length(&signatures), E_SIG_ARRAY_WIDTH);

        // Assembled through the registry's public constructor — Move
        // struct literals are private to the defining module
        // (trion::epoch_registry::new_signature).
        let sigs = vector::empty<CertificateSignature>();
        for (i in 0..n) {
            vector::push_back(&mut sigs, epoch_registry::new_signature(
                *vector::borrow(&validator_ids, i),
                *vector::borrow(&stake_claims, i),
                *vector::borrow(&diversity_claims, i),
                *vector::borrow(&signatures, i),
            ));
        };
        release_escrow_with_sigs(submitter, escrow_addr, payload, sigs);
    }

    /// Struct-envelope variant (same verification, §4 shape).
    public entry fun release_escrow_with_sigs(
        _submitter: &signer,
        escrow_addr: address,
        payload: vector<u8>,
        sigs: vector<CertificateSignature>,
    ) acquires Escrow, EscrowConfig {
        assert!(exists<Escrow>(escrow_addr), E_NOT_FOUND);

        // §8.2 idempotent resubmission: the SAME certificate hash on an
        // already-RELEASED escrow is a no-op (observability, retry
        // safety — no settlement effect, no re-verification needed).
        // A DIFFERENT certificate hash on any terminal escrow aborts
        // (E_INVALID_STATE): terminal states have no outgoing edges
        // (M2) — this is the double-release / substitution firewall.
        let cert_hash = canonical_cert::certificate_hash(&payload);
        {
            let esc = borrow_global<Escrow>(escrow_addr);
            if (esc.state == RELEASED) {
                assert!(esc.released_cert_hash == cert_hash, E_INVALID_STATE);
                return
            } else {
                assert!(
                    esc.state == HOLDING || esc.state == PENDING_AKASHIC,
                    E_INVALID_STATE
                );
            };
        };

        // Circuit breaker: blocks certificate releases during an
        // incident (funds remain recoverable via revert/emergency).
        assert!(exists<EscrowConfig>(@trion), E_NOT_INITIALIZED);
        assert!(!borrow_global<EscrowConfig>(@trion).paused, E_PAUSED);

        // §6 steps 1–6, in canonical order, against the registry.
        // (structure → epoch → freshness → preconditions → signatures
        //  → quorum; every failure ABORTS — fail-closed, no fallback.)
        //
        // FRESHNESS CLOCK (documented honestly): `now` is
        // aptos_framework::timestamp::now_seconds() — the block timestamp
        // written by the Aptos validator consensus at block creation
        // (CANONICAL_CERTIFICATE §7 Move row). This is a CONSENSUS
        // BLOCK-TIME PROXY for the certificate's consensus clock, NOT a
        // trust-the-relayer value: it is produced by the chain's own
        // quorum (never by the certificate submitter), is monotonic
        // within a chain view, and bounds certificate age to ±1 Aptos
        // block (~1 s) of wall time. The 60 s lower-bound drift
        // tolerance (canonical_cert::is_fresh_at) absorbs the residual
        // skew between TRION consensus time and this proxy.
        let now = timestamp::now_seconds();
        let (signed_power, total_power, tier) =
            epoch_registry::verify_certificate(&payload, &sigs, now);

        // Escrow-local precondition (INV-003): the certificate's C(t)
        // must also clear THIS escrow's locked-in coherence floor.
        {
            let esc = borrow_global<Escrow>(escrow_addr);
            assert!(
                canonical_cert::coherence(&payload) >= esc.min_coherence,
                E_MIN_COHERENCE_NOT_MET
            );
        };

        // §6 step 7 — BINDING against the escrow's own lock-time record.
        // escrow_id is DERIVED (BCS of the escrow account address), so
        // the certificate must name exactly this escrow.
        {
            let esc = borrow_global<Escrow>(escrow_addr);
            assert!(
                canonical_cert::escrow_id(&payload) == bcs::to_bytes<address>(&escrow_addr),
                E_ESCROW_ID_MISMATCH
            );
            assert!(canonical_cert::route_id(&payload) == esc.route_id, E_ROUTE_MISMATCH);
            assert!(
                canonical_cert::intent_hash(&payload) == esc.intent_hash,
                E_INTENT_MISMATCH
            );
            assert!(canonical_cert::entity_id(&payload) == esc.entity_id, E_ENTITY_MISMATCH);
            assert!(
                canonical_cert::source_chain(&payload) == esc.source_chain,
                E_SOURCE_CHAIN_MISMATCH
            );
            assert!(
                canonical_cert::dest_chain(&payload) == esc.dest_chain,
                E_DEST_CHAIN_MISMATCH
            );
            assert!(
                canonical_cert::destination(&payload) == bcs::to_bytes<address>(&esc.destination),
                E_DESTINATION_MISMATCH
            );
            // uint256 amount must equal the escrow's u64 exactly.
            assert!(
                canonical_cert::amount_fits_u64(&payload),
                E_AMOUNT_TOO_LARGE
            );
            assert!(
                canonical_cert::amount_u64(&payload) == esc.amount,
                E_AMOUNT_MISMATCH
            );
            assert!(canonical_cert::anchor_bh(&payload) == esc.anchor_bh, E_ANCHOR_MISMATCH);
            assert!(
                canonical_cert::execution_bh(&payload) == esc.execution_bh,
                E_EXECUTION_BH_MISMATCH
            );
        };

        // §6 step 8 — NONCE / CONSUMED (§8: strictly increasing per
        // (validator_epoch, escrow_id)). A newer epoch resets the scope;
        // the same epoch demands a higher nonce; an older epoch is
        // stale (also caught by the registry's grace window).
        {
            let esc = borrow_global<Escrow>(escrow_addr);
            let cert_epoch = canonical_cert::epoch(&payload);
            let cert_nonce = canonical_cert::nonce(&payload);
            if (esc.consumed_epoch == 0) {
                // Never consumed: any registered epoch is acceptable.
                assert!(cert_epoch >= 1, E_STALE_NONCE);
            } else if (cert_epoch == esc.consumed_epoch) {
                assert!(cert_nonce > esc.consumed_nonce, E_STALE_NONCE);
            } else {
                assert!(cert_epoch > esc.consumed_epoch, E_STALE_NONCE);
            };
        };

        // §6 step 9 — EFFECTS: record consumption and flip the state
        // FIRST (terminal freeze / check-effects-interactions, M2),
        // then move the value exactly once.
        let cert_epoch = canonical_cert::epoch(&payload);
        let cert_nonce = canonical_cert::nonce(&payload);
        {
            let esc = borrow_global_mut<Escrow>(escrow_addr);
            esc.consumed_epoch = cert_epoch;
            esc.consumed_nonce = cert_nonce;
            esc.released_cert_hash = cert_hash;
            esc.state = RELEASED;
        };
        {
            let esc = borrow_global_mut<Escrow>(escrow_addr);
            let coin_to_send = coin::extract_all(&mut esc.held_coin);
            coin::deposit<TrionToken>(esc.destination, coin_to_send);
        };
        event::emit(EscrowReleased {
            escrow_addr,
            certificate_hash: borrow_global<Escrow>(escrow_addr).released_cert_hash,
            validator_epoch: cert_epoch,
            certificate_nonce: cert_nonce,
            signed_power,
            total_power,
            quorum_tier: tier,
            submitter: signer::address_of(_submitter),
        });
    }

    // ── Revert (timeout = permissionless; else safe-direction relayer) ─

    /// Returns funds to locked_by. Callable by:
    ///   • ANYONE, once the escrow timed out (permissionless escape);
    ///   • ANYONE, in PENDING_AKASHIC past the 24h recovery window;
    ///   • the relayer otherwise (coherence-failure / route-invalid /
    ///     manual — funds go back to the locker, never anywhere else).
    public entry fun revert_escrow(
        caller: &signer,
        escrow_addr: address,
        reason: u8,
    ) acquires Escrow, EscrowConfig {
        assert!(exists<Escrow>(escrow_addr), E_NOT_FOUND);

        // Decide whether relayer authority is needed BEFORE taking the
        // mutable borrow (borrows are block-scoped; the EscrowConfig
        // borrow inside assert_relayer is a different resource).
        let needs_relayer = {
            let esc = borrow_global<Escrow>(escrow_addr);
            assert!(
                esc.state == HOLDING || esc.state == PENDING_AKASHIC,
                E_INVALID_STATE
            );
            let now_ts = timestamp::now_seconds();
            // lock_timestamp + timeout cannot overflow: lock_timestamp is
            // real chain time and timeout_seconds was capped at 7 days.
            let is_timeout = now_ts > esc.lock_timestamp + esc.timeout_seconds;
            let is_akashic_expired = esc.state == PENDING_AKASHIC
                && now_ts > esc.lock_timestamp + AKASHIC_RECOVERY_SECONDS;
            !is_timeout && !is_akashic_expired
        };
        if (needs_relayer) {
            // Non-timeout revert is the relayer's SAFE-direction power.
            assert_relayer(caller);
        };

        let esc = borrow_global_mut<Escrow>(escrow_addr);
        // Refund to the locker (state flips before the transfer).
        esc.state = REVERTED;
        let coin_to_refund = coin::extract_all(&mut esc.held_coin);
        let refund_to = esc.locked_by;
        coin::deposit<TrionToken>(refund_to, coin_to_refund);
        event::emit(EscrowReverted { escrow_addr, reason });
    }

    // ── Emergency revert (Gap 8: 7-day permissionless escape hatch) ────

    /// After 7 days ANYONE can revert — no relayer, no certificate, no
    /// TRION signal, no pause. This is the absolute maximum lockup
    /// period; funds can never be frozen beyond it.
    public entry fun emergency_revert(
        _caller: &signer,
        escrow_addr: address,
    ) acquires Escrow {
        assert!(exists<Escrow>(escrow_addr), E_NOT_FOUND);
        let esc = borrow_global_mut<Escrow>(escrow_addr);
        assert!(
            esc.state == HOLDING || esc.state == PENDING_AKASHIC,
            E_INVALID_STATE
        );
        // lock_timestamp + 7 days cannot overflow (real chain time).
        assert!(
            timestamp::now_seconds() >= esc.lock_timestamp + EMERGENCY_ESCAPE_SECONDS,
            E_EMERGENCY_NOT_YET
        );

        esc.state = EMERGENCY_REVERTED;
        let coin_to_refund = coin::extract_all(&mut esc.held_coin);
        let refund_to = esc.locked_by;
        coin::deposit<TrionToken>(refund_to, coin_to_refund);
        event::emit(EmergencyReverted { escrow_addr });
    }

    // ── PENDING_AKASHIC (E1) — safe-direction relayer marking ──────────

    /// Mark the escrow PENDING_AKASHIC (Akashic Index unavailable at
    /// execution time). Opens the 24h recovery window; after it, only
    /// revert remains. Requires the relayer and an unpaused deployment
    /// (parity with the Solidity tier's whenNotPaused).
    public entry fun enter_pending_akashic(
        relayer: &signer,
        escrow_addr: address,
    ) acquires Escrow, EscrowConfig {
        assert_relayer(relayer);
        assert!(exists<EscrowConfig>(@trion), E_NOT_INITIALIZED);
        assert!(!borrow_global<EscrowConfig>(@trion).paused, E_PAUSED);
        assert!(exists<Escrow>(escrow_addr), E_NOT_FOUND);
        let esc = borrow_global_mut<Escrow>(escrow_addr);
        assert!(esc.state == HOLDING, E_INVALID_STATE);
        esc.state = PENDING_AKASHIC;
    }

    // ── Views (no coherence flag — the C-02 regression surface is gone)

    /// (state, amount). NOTE: the pre-Wave-2 getter returned the
    /// relayer-set `coherence_verified` boolean — that flag no longer
    /// exists in any form.
    public fun get_state(addr: address): (u8, u64) acquires Escrow {
        assert!(exists<Escrow>(addr), E_NOT_FOUND);
        let esc = borrow_global<Escrow>(addr);
        (esc.state, esc.amount)
    }

    public fun get_destination(addr: address): address acquires Escrow {
        assert!(exists<Escrow>(addr), E_NOT_FOUND);
        borrow_global<Escrow>(addr).destination
    }

    public fun get_lock_timestamp(addr: address): u64 acquires Escrow {
        assert!(exists<Escrow>(addr), E_NOT_FOUND);
        borrow_global<Escrow>(addr).lock_timestamp
    }

    /// §8 replay record — (consumed_epoch, consumed_nonce).
    public fun get_consumed_nonce(addr: address): (u64, u64) acquires Escrow {
        assert!(exists<Escrow>(addr), E_NOT_FOUND);
        let esc = borrow_global<Escrow>(addr);
        (esc.consumed_epoch, esc.consumed_nonce)
    }

    /// The certificate hash that released this escrow (bytes32; empty
    /// while unreleased) — the idempotent-resubmission key of §8.2.
    public fun get_released_cert_hash(addr: address): vector<u8> acquires Escrow {
        assert!(exists<Escrow>(addr), E_NOT_FOUND);
        borrow_global<Escrow>(addr).released_cert_hash
    }

    public fun is_paused(): bool acquires EscrowConfig {
        assert!(exists<EscrowConfig>(@trion), E_NOT_INITIALIZED);
        borrow_global<EscrowConfig>(@trion).paused
    }

    /// The safe-direction relayer (NOT a release authority).
    public fun relayer(): address acquires EscrowConfig {
        assert!(exists<EscrowConfig>(@trion), E_NOT_INITIALIZED);
        borrow_global<EscrowConfig>(@trion).relayer
    }

    // Revert reason constants are public for integrators/tests.
    public fun reason_timeout(): u8 { REASON_TIMEOUT }
    public fun reason_coherence_failure(): u8 { REASON_COHERENCE_FAILURE }
    public fun reason_route_invalid(): u8 { REASON_ROUTE_INVALID }
    public fun reason_manual(): u8 { REASON_MANUAL }
    public fun reason_akashic_outage(): u8 { REASON_AKASHIC_OUTAGE }
    public fun reason_emergency_escape(): u8 { REASON_EMERGENCY_ESCAPE }
}
