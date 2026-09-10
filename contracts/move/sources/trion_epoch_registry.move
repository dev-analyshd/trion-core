/// TRION Epoch Registry — validator-set authority for Move (Aptos / Movement)
/// ============================================================================
/// Implements CANONICAL_CERTIFICATE.md §10.2 (epoch registration) and the
/// registry-side half of the §6 verification algorithm (steps 2, 4, 5, 6)
/// for the Move signature family (§3.2 family 2 — Ed25519 over the RAW
/// 346-byte payload P, no pre-hash).
///
/// WHAT MOVE CAN AND CANNOT DO HERE (master command §11 — documented
/// boundary, never a silent downgrade):
///   • Aptos (the deployment target pinned in Move.toml, rev "mainnet")
///     exposes NATIVE Ed25519 verification — `aptos_std::ed25519::
///     signature_verify_strict` — a native (off-VM-arithmetic) check that
///     also rejects small-subgroup public keys. This module uses it for
///     EVERY signature: one failed check fails the whole certificate
///     (batch fail-closed, §6 step 5a). No module in this tree vendors a
///     pure-Move Ed25519 — the primitive comes from the pinned aptos-core
///     framework dependency in Move.toml ([dependencies.AptosStdlib],
///     rev "mainnet"), resolved at build time exactly like every other
///     Aptos package. VERIFIED SEMANTICS: RFC 8032 PureEdDSA over the
///     raw 346-byte P (the py mirror + real keys in
///     tests/contracts/test_btcp_escrow_move.py verify exactly this).
///     UNVERIFIED DETAIL (no Move toolchain in this environment): the
///     exact parameter shape of the native call (message by-value vs by
///     reference) drifts across framework revisions — pin and confirm at
///     first `aptos move compile`.
///   • Sui divergence (honest, documented): Sui's Move dialect does not
///     expose Ed25519 verification to module code (it is a
///     programmable-transaction-level check there). A Sui deployment
///     keeps THIS module's registry/quorum/binding logic byte-identical
///     and swaps only the Ed25519 dispatch inside `verify_certificate`
///     (or verifies via PTB witness validation before ingress).
///     Unverified until a Sui toolchain exists; NOT silently downgraded.
///   • The pubkeys verified against are the REGISTERED ones (§6 step 5b)
///     — a caller-submitted key never enters verification.
///
/// AUTHORITY MODEL (who holds what — see the capability audit in
/// btcp_escrow.move's header):
///   • `EpochAdminCap` — created once by `initialize`, held under the
///     module account @trion (the deployment binding per §7's domain
///     note). Sole authority to publish an epoch set (`register_epoch`).
///     This is the registrar role of §10.2: ONE transaction per epoch
///     boundary, gas-bounded, TRION-consensus-signed off-chain.
///   • No other signer authority exists in this module. Quorum weight is
///     computed ONLY from the registered set (§5 — "never from
///     caller-supplied values"); envelope weights are cross-checked
///     claims, never inputs (§6 step 5c).
///
/// Storage layout (follows the @trion shared-resource scheme of
/// trion::btcp_intent — ONE registry under the module account):
///   @trion: Registry { current_epoch, epochs: Table<u64, EpochSetData> }
///   @trion: EpochAdminCap (created by initialize, transferable)
///   EpochSetData.validators: Table<validator_id(bytes32), ValidatorEntry>
module trion::epoch_registry {
    use std::signer;
    use std::vector;
    use aptos_std::table::{Self, Table};
    use aptos_std::ed25519;
    use trion::canonical_cert;

    // ── §5 / §10 constants ─────────────────────────────────────────────
    /// Weights are ×1e6 fixed point (§2 scale discipline).
    const SCALE_1E6: u64 = 1_000_000;
    /// Verifier epoch grace (ED-G): certificates older than
    /// current_epoch − 2 are rejected even within ttl (§6 step 2) —
    /// bounds the just-slashed-validator residual window (R-1).
    const EPOCH_GRACE: u64 = 2;
    /// Minimum validators per epoch set (§4 liveness floor; without it a
    /// single validator trivially passes the tier-1 quorum).
    const MIN_EPOCH_SET_SIZE: u64 = 3;
    /// L4.2 D_consensus tier bounds, ×1e6 (§5.2).
    const D_CONSENSUS_TIER1: u64 = 600_000; // ≥ 0.60 → 2/3 STRICT
    const D_CONSENSUS_TIER2: u64 = 400_000; // ≥ 0.40 → 0.75

    const BYTES32: u64 = 32;

    // ── Error codes ────────────────────────────────────────────────────
    const E_NOT_MODULE_ACCOUNT:      u64 = 1;  // initialize from non-@trion
    const E_ALREADY_INITIALIZED:     u64 = 2;
    const E_REGISTRY_NOT_INITIALIZED: u64 = 3;
    const E_NO_ADMIN_CAP:            u64 = 4;
    const E_EPOCH_ORDER:             u64 = 5;  // not (first ≥ 1 | current+1)
    const E_TOO_FEW_VALIDATORS:      u64 = 6;
    const E_ENTRY_WIDTH:             u64 = 7;  // validator_id / pubkey size
    const E_PARALLEL_WIDTHS:         u64 = 8;  // registration arrays disagree
    const E_DUPLICATE_VALIDATOR:     u64 = 9;
    const E_WEIGHT_SCALE:            u64 = 10; // s_j or d_j > 1e6
    const E_EPOCH_UNKNOWN:           u64 = 11; // not in registry (fail-closed,
    //                                            never historical-set accept)
    const E_EPOCH_FUTURE:            u64 = 12;
    const E_EPOCH_STALE:             u64 = 13; // beyond grace
    const E_INSUFFICIENT_SIGNERS:    u64 = 14;
    const E_SIG_WIDTH:               u64 = 15;
    const E_DUPLICATE_SIGNER:        u64 = 16;
    const E_VALIDATOR_NOT_REGISTERED: u64 = 17;
    const E_WEIGHT_CLAIM_MISMATCH:   u64 = 18; // §6 step 5c
    const E_BAD_SIGNATURE:           u64 = 19; // §6 step 5a batch fail-closed
    const E_QUORUM_NOT_MET:          u64 = 20; // §6 step 6 / §5.2 tiers
    const E_COUNT_LIE:               u64 = 21; // validator_count ≠ set size
    const E_POWER_LIE:               u64 = 22; // total_effective_power ≠ Σ w_j
    const E_NOT_FRESH:               u64 = 23; // §6 step 3 / §9 freshness
    const E_AGGREGATE_OVERFLOW:      u64 = 24; // u128 sum > u64 before narrowing

    /// Move `as` casts TRUNCATE silently (arithmetic overflow aborts, a
    /// narrowing cast does NOT). Every u128→u64 narrowing in this module
    /// is therefore guarded by an explicit assert so a hostile (gas-bound
    /// impossible, but still) registration input cannot wrap a power total
    /// into the u64 range and forge quorum arithmetic.
    const MAX_U64: u128 = 18446744073709551615;

    // ── Capabilities & storage ─────────────────────────────────────────

    /// Registrar capability. Created ONCE by `initialize` (which itself
    /// requires the @trion account — fail-closed), held under the
    /// registrar account. `has key` only: cannot be copied, dropped,
    /// or forged; only `register_epoch` / `transfer_admin` consume it.
    struct EpochAdminCap has key {}

    /// One validator's epoch-scoped state (§10.2 registration tuple).
    struct ValidatorEntry has store {
        /// 32-byte Ed25519 public key — the ONLY key material used by
        /// verification (§6 step 5b: recovered identity ∈ registered set).
        ed25519_pubkey: vector<u8>,
        /// s_j ×1e6 (stake weight).
        stake_weight: u64,
        /// d_j ×1e6 (diversity weight).
        diversity_weight: u64,
    }

    /// Effective power w_j = s_j·d_j carried ×1e6 (§5.1) — floor division
    /// to match core/consensus/certificate.py exactly.
    fun effective_power(stake: u64, diversity: u64): u64 {
        (stake * diversity) / SCALE_1E6
    }

    /// One epoch's registered set, stored as a table keyed by
    /// validator_id (bytes32) so verification is a direct lookup.
    struct EpochSetData has store {
        validator_count: u64,
        /// Σ w_j over the set, ×1e6 — the value the certificate's
        /// total_effective_power must equal (§6 step 6 cross-check).
        total_effective_power: u64,
        /// Mean d_j over the set, ×1e6 (L4.2) — selects the quorum tier.
        d_consensus: u64,
        validators: Table<vector<u8>, ValidatorEntry>,
    }

    /// The shared registry, under @trion (the deployment binding).
    struct Registry has key {
        current_epoch: u64,
        epochs: Table<u64, EpochSetData>,
    }

    /// One envelope signature entry (§4): validator_id + its weight
    /// CLAIMS (×1e6) + the 64-byte Ed25519 signature over P. The claims
    /// are cross-checked against the registered set (§6 step 5c) and are
    /// NEVER an input to quorum arithmetic.
    struct CertificateSignature has drop {
        validator_id: vector<u8>,
        stake_weight: u64,
        diversity_weight: u64,
        signature: vector<u8>,
    }

    /// Public constructor for the envelope entry — Move struct literals
    /// are private to the DEFINING module, so trion::btcp_escrow (and any
    /// future relayer module) assembles entries through THIS function.
    /// No validation here by design: the entry is untrusted input and
    /// every field is validated (widths, membership, claim equality, the
    /// signature itself) inside verify_certificate, §6 step 5.
    public fun new_signature(
        validator_id: vector<u8>,
        stake_weight: u64,
        diversity_weight: u64,
        signature: vector<u8>,
    ): CertificateSignature {
        CertificateSignature {
            validator_id,
            stake_weight,
            diversity_weight,
            signature,
        }
    }

    // ── Initialization (once, @trion only) ─────────────────────────────

    /// Publish the shared Registry under @trion and mint the registrar
    /// capability. Fail-closed: initializing from any other account
    /// would leave every other entry point reading @trion and aborting.
    public entry fun initialize(admin: &signer) {
        let addr = signer::address_of(admin);
        assert!(addr == @trion, E_NOT_MODULE_ACCOUNT);
        assert!(!exists<Registry>(@trion), E_ALREADY_INITIALIZED);
        move_to(admin, Registry {
            current_epoch: 0,
            epochs: table::new<u64, EpochSetData>(),
        });
        move_to(admin, EpochAdminCap {});
    }

    /// Rotate the registrar capability to a new account (key ceremony
    /// path). Requires BOTH the current registrar's signer and the new
    /// holder's signer — no unilateral theft surface.
    public entry fun transfer_admin(current: &signer, new_admin: &signer) acquires EpochAdminCap {
        let from = signer::address_of(current);
        assert!(exists<EpochAdminCap>(from), E_NO_ADMIN_CAP);
        let cap = move_from<EpochAdminCap>(from);
        move_to(new_admin, cap);
    }

    // ── §10.2 epoch registration (registrar only) ──────────────────────

    /// Publish the validator set for `epoch`. Enforced disciplines:
    ///   • registrar capability (EpochAdminCap at the signer);
    ///   • strict epoch ordering: the FIRST set may be any epoch ≥ 1,
    ///     every later set must be exactly current + 1 — rotation takes
    ///     effect only at boundaries, exactly one write per epoch (§10.2);
    ///   • ≥ MIN_EPOCH_SET_SIZE validators (§4 liveness floor);
    ///   • validator_id and ed25519_pubkey exactly 32 bytes each;
    ///   • weights ×1e6, each ≤ 1e6 (scale discipline);
    ///   • no duplicate validator ids (padding is not consensus, §4);
    ///   • parallel input arrays must agree in length.
    ///
    /// total_effective_power and d_consensus are COMPUTED HERE and stored
    /// — the certificate's claims are cross-checked against these values
    /// at verification (§6 steps 4/6), so a lying certificate is rejected.
    public entry fun register_epoch(
        admin: &signer,
        epoch: u64,
        validator_ids: vector<vector<u8>>,
        pubkeys: vector<vector<u8>>,
        stakes: vector<u64>,
        diversities: vector<u64>,
    ) acquires Registry {
        let addr = signer::address_of(admin);
        assert!(exists<Registry>(@trion), E_REGISTRY_NOT_INITIALIZED);
        assert!(exists<EpochAdminCap>(addr), E_NO_ADMIN_CAP);

        let n = vector::length(&validator_ids);
        assert!(n == vector::length(&pubkeys), E_PARALLEL_WIDTHS);
        assert!(n == vector::length(&stakes), E_PARALLEL_WIDTHS);
        assert!(n == vector::length(&diversities), E_PARALLEL_WIDTHS);
        assert!(n >= MIN_EPOCH_SET_SIZE, E_TOO_FEW_VALIDATORS);

        {
            let registry = borrow_global_mut<Registry>(@trion);
            let current = registry.current_epoch;
            if (current == 0) {
                assert!(epoch >= 1, E_EPOCH_ORDER);
            } else {
                assert!(epoch == current + 1, E_EPOCH_ORDER);
            };
        };

        // Validate every entry BEFORE writing anything (fail-closed).
        for (i in 0..n) {
            let vid = vector::borrow(&validator_ids, i);
            let pk = vector::borrow(&pubkeys, i);
            let s = *vector::borrow(&stakes, i);
            let d = *vector::borrow(&diversities, i);
            assert!(vector::length(vid) == BYTES32, E_ENTRY_WIDTH);
            assert!(vector::length(pk) == BYTES32, E_ENTRY_WIDTH);
            assert!(s <= SCALE_1E6, E_WEIGHT_SCALE);
            assert!(d <= SCALE_1E6, E_WEIGHT_SCALE);
            // Duplicate detection: O(n²) over ids (n bounded by gas; the
            // canonical fleet is 100 validators).
            for (j in 0..n) {
                if (j != i) {
                    assert!(
                        *vector::borrow(&validator_ids, i) != *vector::borrow(&validator_ids, j),
                        E_DUPLICATE_VALIDATOR
                    );
                };
            };
        };

        // Compute the set aggregates in u128 then narrow — sums of ≤1e6
        // values over a gas-bounded set cannot overflow u64, but the
        // u128 accumulation makes that a theorem, not an assumption. The
        // asserts below pin the narrowing: `as u64` TRUNCATES in Move
        // (it does not abort), so the cast is guarded explicitly.
        let total_power: u128 = 0;
        let diversity_sum: u128 = 0;
        for (i in 0..n) {
            let s = *vector::borrow(&stakes, i);
            let d = *vector::borrow(&diversities, i);
            total_power = total_power + (effective_power(s, d) as u128);
            diversity_sum = diversity_sum + (d as u128);
        };
        assert!(total_power <= MAX_U64, E_AGGREGATE_OVERFLOW);
        assert!(diversity_sum <= MAX_U64, E_AGGREGATE_OVERFLOW);
        // Floor division matches core/consensus/certificate.py
        // (total_effective_power / d_consensus); the mean of ≤1e6 values
        // is ≤ 1e6, so d_consensus needs no further narrowing guard.
        let total_power_u64 = (total_power as u64);
        let d_consensus = ((diversity_sum / (n as u128)) as u64);

        let set = EpochSetData {
            validator_count: n,
            total_effective_power: total_power_u64,
            d_consensus,
            validators: table::new<vector<u8>, ValidatorEntry>(),
        };
        for (i in 0..n) {
            table::add(
                &mut set.validators,
                *vector::borrow(&validator_ids, i),
                ValidatorEntry {
                    ed25519_pubkey: *vector::borrow(&pubkeys, i),
                    stake_weight: *vector::borrow(&stakes, i),
                    diversity_weight: *vector::borrow(&diversities, i),
                },
            );
        };

        let registry = borrow_global_mut<Registry>(@trion);
        assert!(
            !table::contains(&registry.epochs, epoch),
            E_EPOCH_ORDER
        );
        table::add(&mut registry.epochs, epoch, set);
        registry.current_epoch = epoch;
    }

    // ── §6 verification: steps 1–6 in exact canonical order ────────────

    /// THE canonical certificate verification for the Move family.
    /// Implements §6 steps 1 (structure), 2 (epoch + grace), 3 (freshness
    /// against the supplied `now` — the escrow passes
    /// timestamp::now_seconds()), 4 (consensus preconditions' registry
    /// halves: validator_count and total_effective_power), 5 (Ed25519
    /// signatures against REGISTERED keys + weight-claim cross-check) and
    /// 6 (L4.2 tier quorum from REGISTERED weights). Steps 7 (escrow
    /// binding) and 8 (nonce/consumed) live in trion::btcp_escrow —
    /// they are escrow state, not registry state.
    ///
    /// ABORTS on any failure (Move's fail-closed: the transaction
    /// reverts atomically — there is no partial acceptance and no
    /// fallback to weaker checks, §6's "oracle fallback" prohibition).
    ///
    /// Returns (signed_power, total_power, tier) ×1e6 for event emission
    /// by the caller. Quorum comparisons run in u128 so no intermediate
    /// product can overflow.
    public fun verify_certificate(
        payload: &vector<u8>,
        sigs: &vector<CertificateSignature>,
        now: u64,
    ): (u128, u128, u8) acquires Registry {
        // §6 step 1 — STRUCTURE (payload half; envelope half below).
        canonical_cert::verify_structure(payload);

        assert!(exists<Registry>(@trion), E_REGISTRY_NOT_INITIALIZED);

        // §6 step 1 (envelope half) — family/sig width/distinct ids/count.
        let n_sigs = vector::length(sigs);
        assert!(n_sigs >= canonical_cert::min_signers(), E_INSUFFICIENT_SIGNERS);
        for (i in 0..n_sigs) {
            let s = vector::borrow(sigs, i);
            assert!(
                vector::length(&s.signature) == canonical_cert::expected_signature_len(),
                E_SIG_WIDTH
            );
            assert!(
                vector::length(&s.validator_id) == BYTES32,
                E_ENTRY_WIDTH
            );
            for (j in 0..n_sigs) {
                if (j != i) {
                    // Duplicate signers are padding, not consensus (§4).
                    let id_i = vector::borrow(sigs, i).validator_id;
                    let id_j = vector::borrow(sigs, j).validator_id;
                    assert!(id_i != id_j, E_DUPLICATE_SIGNER);
                };
            };
        };

        // §6 step 2 — EPOCH: registered, not future, within grace.
        let cert_epoch = canonical_cert::epoch(payload);
        let registry = borrow_global<Registry>(@trion);
        assert!(
            table::contains(&registry.epochs, cert_epoch),
            E_EPOCH_UNKNOWN
        );
        let latest = registry.current_epoch;
        assert!(cert_epoch <= latest, E_EPOCH_FUTURE);
        assert!(latest - cert_epoch <= EPOCH_GRACE, E_EPOCH_STALE);
        let set = table::borrow(&registry.epochs, cert_epoch);

        // §6 step 3 — FRESHNESS (§9: drift widens the lower bound only;
        // expiry is never tolerated).
        assert!(
            canonical_cert::is_fresh_at(payload, now),
            E_NOT_FRESH
        );

        // §6 step 4 (registry half) — the certificate must not lie about
        // the set: validator_count and total_effective_power.
        assert!(
            canonical_cert::validator_count(payload) == set.validator_count,
            E_COUNT_LIE
        );
        assert!(
            canonical_cert::total_effective_power(payload)
                == set.total_effective_power,
            E_POWER_LIE
        );

        // §6 step 5 — SIGNATURES: verify EVERY signature against the
        // REGISTERED pubkey; one bad signature fails the certificate.
        let signed_power: u128 = 0;
        for (i in 0..n_sigs) {
            let s = vector::borrow(sigs, i);
            assert!(
                table::contains(&set.validators, s.validator_id),
                E_VALIDATOR_NOT_REGISTERED
            );
            let entry = table::borrow(&set.validators, s.validator_id);
            // §6 step 5c — weight claims must equal the registered values.
            assert!(s.stake_weight == entry.stake_weight, E_WEIGHT_CLAIM_MISMATCH);
            assert!(
                s.diversity_weight == entry.diversity_weight,
                E_WEIGHT_CLAIM_MISMATCH
            );
            // §3.2 family 2: Ed25519 over the RAW payload P (no digest).
            // Strict native verification (small-subgroup rejecting).
            let pk = ed25519::new_unvalidated_public_key_from_bytes(
                entry.ed25519_pubkey
            );
            let sig = ed25519::new_signature_from_bytes(s.signature);
            let ok = ed25519::signature_verify_strict(&sig, &pk, *payload);
            assert!(ok, E_BAD_SIGNATURE);
            // Quorum weight comes from the REGISTERED set (§5), never
            // from the envelope.
            signed_power = signed_power + (
                effective_power(entry.stake_weight, entry.diversity_weight) as u128
            );
        };

        // §6 step 6 — QUORUM: L4.2 tier table over registered state,
        // u128 arithmetic (no overflow bypass).
        let total_power = (set.total_effective_power as u128);
        let tier: u8 = if (set.d_consensus >= D_CONSENSUS_TIER1) {
            1u8
        } else if (set.d_consensus >= D_CONSENSUS_TIER2) {
            2u8
        } else {
            3u8
        };
        if (tier == 1u8) {
            // STRICT: exactly 2/3 is NOT a quorum (Go engine discipline).
            assert!(3 * signed_power > 2 * total_power, E_QUORUM_NOT_MET);
        } else if (tier == 2u8) {
            assert!(4 * signed_power >= 3 * total_power, E_QUORUM_NOT_MET);
        } else {
            assert!(20 * signed_power >= 17 * total_power, E_QUORUM_NOT_MET);
        };

        (signed_power, total_power, tier)
    }

    // ── Read-only views (observability) ────────────────────────────────

    public fun current_epoch(): u64 acquires Registry {
        assert!(exists<Registry>(@trion), E_REGISTRY_NOT_INITIALIZED);
        borrow_global<Registry>(@trion).current_epoch
    }

    public fun epoch_registered(epoch: u64): bool acquires Registry {
        if (!exists<Registry>(@trion)) {
            return false
        };
        let registry = borrow_global<Registry>(@trion);
        table::contains(&registry.epochs, epoch)
    }

    public fun validator_count_of(epoch: u64): u64 acquires Registry {
        assert!(exists<Registry>(@trion), E_REGISTRY_NOT_INITIALIZED);
        let registry = borrow_global<Registry>(@trion);
        assert!(table::contains(&registry.epochs, epoch), E_EPOCH_UNKNOWN);
        table::borrow(&registry.epochs, epoch).validator_count
    }

    public fun total_power_of(epoch: u64): u64 acquires Registry {
        assert!(exists<Registry>(@trion), E_REGISTRY_NOT_INITIALIZED);
        let registry = borrow_global<Registry>(@trion);
        assert!(table::contains(&registry.epochs, epoch), E_EPOCH_UNKNOWN);
        table::borrow(&registry.epochs, epoch).total_effective_power
    }

    public fun d_consensus_of(epoch: u64): u64 acquires Registry {
        assert!(exists<Registry>(@trion), E_REGISTRY_NOT_INITIALIZED);
        let registry = borrow_global<Registry>(@trion);
        assert!(table::contains(&registry.epochs, epoch), E_EPOCH_UNKNOWN);
        table::borrow(&registry.epochs, epoch).d_consensus
    }

    public fun epoch_grace(): u64 {
        EPOCH_GRACE
    }
}
