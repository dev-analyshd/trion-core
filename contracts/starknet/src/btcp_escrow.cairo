/// TRION Protocol — BTCPEscrow (Starknet)
/// ========================================
/// Mirrors contracts/solidity/BTCPEscrow.sol on Starknet.
/// Two-state atomic escrow: HOLDING -> RELEASED or HOLDING -> REVERTED
/// (or HOLDING -> EMERGENCY_REVERTED via the 7-day escape hatch).
///
/// ── CUSTODY VERDICT (master command §13): RECORDS ACCOUNTING ONLY ──────
/// This contract performs NO token transfers and holds NO real assets:
/// there is no ERC-20 / SNIP-2 custody wiring and no native-asset (L1
/// messaging) integration. `lock_escrow` records an accounting entry
/// (per-funder `locked_balance`, global `total_locked_balance`), and
/// `release_escrow` / `revert_escrow` clear it. It MUST NOT be represented
/// as production asset custody. When custody wiring lands (a future wave),
/// the certificate gate implemented here is already the release authority
/// the wiring must call — the authority model does not need to change.
///
/// ── C-04 REMEDIATION (VALIDATOR_SECURITY_AUDIT, CRITICAL) ──────────────
/// Release authority is the CANONICAL CERTIFICATE (docs/protocol/
/// CANONICAL_CERTIFICATE.md), NOT caller-supplied coherence: the legacy
/// `release_escrow(escrow_id, execution_bh, coherence)` entrypoint — which
/// trusted a relayer/owner-supplied coherence u64 with no signatures, no
/// quorum, no binding, no freshness — is REMOVED. The new
/// `release_escrow(escrow_id, cert, sigs)` runs the full fail-closed §6
/// sequence: structure + felt-range discipline → epoch (registry, grace) →
/// freshness → HHI/AWA/isSafe preconditions → STARK-curve ECDSA signature
/// verification (family 3: Poseidon over the felt-chunked 346-byte payload)
/// → L4.2 weight quorum from REGISTERED state → settlement-tuple binding
/// vs the escrow record → nonce/consumed replay rules. Submission is
/// PERMISSIONLESS: the cryptography is the authority (the relayer remains
/// the expected operational submitter). Caller-supplied data carries no
/// release authority anywhere in this contract.
///
/// ── Hardening ported from the EVM tier (DD finding 4.2, commit 9c52c36) ─
/// • Locked-balance accounting: per-funder `locked_balance` and global
///   `total_locked_balance`, tracked on lock / release / revert / emergency
///   so the locked pool is always auditable and can never be double-spent.
/// • Emergency exit: `revert_emergency()` — after 7 days ANY caller can
///   recover a stuck escrow (Solidity Gap 8 Resolution).
/// • Cascade revert: `parent_escrow_id` + cascade loop so dependent child
///   escrows revert together with their parent (Solidity Gap 9 Resolution).
///
/// Whitepaper BTCP §4.3 (Six-Step Execution) + §11 (Five Final Fixes);
/// BTCP_STATE_MACHINE.md M2 (E1 lock, E3 release, E5 revert, E6 emergency,
/// E7 cascade). Pause blocks NEW LOCKS only — settlements are never
/// pausable (M2 E3: "pause never blocks settling escrows").

use crate::trion_certificate::{Certificate, SigEntry};

#[starknet::interface]
pub trait IBTCPEscrow<TContractState> {
    fn lock_escrow(
        ref self: TContractState,
        escrow_id:     felt252,
        route_id:      felt252,
        entity_id:     felt252,
        destination:   starknet::ContractAddress,
        amount:        u256,
        min_coherence: u64,
        timeout_blocks:u64,
    );
    /// Multi-hop lock: `parent_escrow_id` != 0 links this escrow to a parent
    /// so a parent revert cascades into this one (Gap 9 cascade revert).
    fn lock_escrow_with_parent(
        ref self: TContractState,
        escrow_id:       felt252,
        route_id:        felt252,
        entity_id:       felt252,
        destination:     starknet::ContractAddress,
        amount:          u256,
        min_coherence:   u64,
        timeout_blocks:  u64,
        parent_escrow_id: felt252,
    );
    /// CANONICAL RELEASE (C-04 fix). PERMISSIONLESS: anyone may submit;
    /// the certificate's quorum of STARK-curve signatures over the
    /// Poseidon digest of the felt-chunked 346-byte payload is the ONLY
    /// release authority. Replaces the removed caller-coherence entrypoint
    /// (whose `coherence: u64` argument was the C-04 finding — it exists
    /// nowhere in this ABI anymore).
    fn release_escrow(
        ref self: TContractState,
        escrow_id: felt252,
        cert:      Certificate,
        sigs:      Span<SigEntry>,
    );
    fn revert_escrow(ref self: TContractState, escrow_id: felt252, reason: u8);
    /// Gap 8: 7-day absolute escape hatch — callable by ANYONE.
    fn revert_emergency(ref self: TContractState, escrow_id: felt252);
    fn get_escrow(self: @TContractState, escrow_id: felt252) -> EscrowRecord;
    fn is_expired(self: @TContractState, escrow_id: felt252) -> bool;
    fn emergency_escape_available(self: @TContractState, escrow_id: felt252) -> bool;
    fn escrow_count(self: @TContractState) -> u64;
    /// Global value currently locked in active (HOLDING) escrows.
    fn total_locked_balance(self: @TContractState) -> u256;
    /// Value currently locked in active escrows funded by `funder`.
    fn locked_balance(self: @TContractState, funder: starknet::ContractAddress) -> u256;
    fn set_relayer(ref self: TContractState, new_relayer: starknet::ContractAddress);
    /// One-way binding of the TrionEpochRegistry (§10.2 registrar). Zero
    /// may be passed at deploy and bound exactly once afterwards.
    fn bind_registry(ref self: TContractState, registry: starknet::ContractAddress);
    fn get_registry(self: @TContractState) -> starknet::ContractAddress;
    /// Pause blocks NEW LOCKS only (M2 E1). Settlements (release) and the
    /// revert/emergency lifecycle are deliberately NOT pausable.
    fn pause(ref self: TContractState);
    fn unpause(ref self: TContractState);
    fn is_paused(self: @TContractState) -> bool;
}

#[derive(Drop, Serde, Copy, starknet::Store)]
pub struct EscrowRecord {
    pub escrow_id:       felt252,
    pub route_id:        felt252,
    pub entity_id:       felt252,
    pub destination:    starknet::ContractAddress,
    pub amount:         u256,
    pub min_coherence:  u64,
    pub lock_height:    u64,
    pub timeout_blocks: u64,
    pub state:          u8,    // 0=HOLDING 1=RELEASED 2=REVERTED 3=EMERGENCY_REVERTED
    pub revert_reason:  u8,
    pub settled_at:     u64,
    pub reverted_at:    u64,
    pub locked_by:      starknet::ContractAddress,
    /// For cascade revert (multi-hop) — 0 if single-hop (Gap 9).
    pub parent_escrow_id: felt252,
}

#[starknet::contract]
pub mod BTCPEscrow {
    use super::{EscrowRecord, IBTCPEscrow};
    use core::num::traits::Zero;
    use starknet::{
        ContractAddress, get_caller_address, get_block_timestamp,
        storage::{Map, StorageMapReadAccess, StorageMapWriteAccess,
                  StoragePointerReadAccess, StoragePointerWriteAccess},
    };
    use crate::trion_certificate::{
        Certificate, SigEntry, EPOCH_GRACE, HHI_MAX_ACCEPTABLE,
        check_structure, is_fresh, quorum_met, stark_digest,
        escrow_id_matches, route_id_matches, destination_matches,
        amount_matches, felt_lt, verify_signature,
    };
    use crate::trion_epoch_registry::{
        IEpochRegistryDispatcher, IEpochRegistryDispatcherTrait,
    };

    const STATE_HOLDING:    u8 = 0;
    const STATE_RELEASED:   u8 = 1;
    const STATE_REVERTED:   u8 = 2;
    const STATE_EMERGENCY_REVERTED: u8 = 3;  // Gap 8: 7-day escape terminal state

    /// Revert reasons (whitepaper BTCP §11) — mirrors the Solidity enum.
    const REASON_TIMEOUT:           u8 = 0;
    const REASON_COHERENCE_FAILURE: u8 = 1;
    const REASON_ROUTE_INVALID:     u8 = 2;
    const REASON_MANUAL:            u8 = 3;
    const REASON_AKASHIC_OUTAGE:    u8 = 4;
    const REASON_CASCADE_REVERT:    u8 = 5;  // Gap 9: multi-hop
    const REASON_EMERGENCY_ESCAPE:  u8 = 6;  // Gap 8

    /// Gap 8: absolute maximum lockup before anyone can force a revert.
    const EMERGENCY_ESCAPE_SECONDS: u64 = 7 * 24 * 60 * 60;

    /// INV-003 protocol coherence floor (×1e6): callers may tighten the
    /// escrow's min_coherence at lock time, never loosen it below 0.55 —
    /// the same constant as the py proof builder's
    /// DEFAULT_COHERENCE_THRESHOLD (core/btcp/modules.py).
    const MIN_COHERENCE_FLOOR: u64 = 550000;

    /// Gas bound on the signature batch (registry roster cap is 128; the
    /// quorum itself is the real bar — MIN_SIGNERS=3 is the liveness floor
    /// checked from trion_certificate).
    const MAX_SIG_ENTRIES: u64 = 128;

    /// 2^251 — felt-range bound for escrow/route ids at lock time, so the
    /// certificate's zero-extended 32-byte binding can always represent
    /// them (ids in the prime's dark range [2^251, P) fail closed here).
    const FELT_ID_MAX: felt252 = 0x800000000000000000000000000000000000000000000000000000000000000;

    #[storage]
    struct Storage {
        owner: ContractAddress,
        relayer: ContractAddress,
        escrows: Map<felt252, EscrowRecord>,
        escrow_count: u64,
        /// SECURITY: per-funder locked value — sum of amounts over that
        /// funder's escrows still in HOLDING (mirrors Solidity lockedBy
        /// accounting; keyed on the record's `locked_by`).
        locked_balance: Map<ContractAddress, u256>,
        /// SECURITY: global locked value — sum of amounts over ALL active
        /// (HOLDING) escrows, tracked on lock/release/revert/emergency
        /// (mirrors Solidity `_lockedBalance`).
        total_locked_balance: u256,
        /// §10.2 registrar binding — ONE-WAY (bind once, never rebind).
        registry: ContractAddress,
        registry_bound: bool,
        /// M2 E1: pause blocks NEW LOCKS only (never settlements).
        paused: bool,
        /// §8.1 consumed-certificate registry, escrow-scoped:
        /// highest consumed certificate_nonce per (validator_epoch, escrow_id).
        /// Consumed-key discipline (§7 Starknet row): the digest map stores
        /// D_stark (the Poseidon felt actually verified) so same-nonce /
        /// different-payload conflicts are detectable on-chain.
        /// STORAGE KEYS: compiler-derived from these distinct field names —
        /// (epoch, escrow_id) 2-tuples cannot collide with the escrow record
        /// map (felt252 keys) or the per-funder balance map (address keys).
        consumed_nonce: Map<(u64, felt252), u64>,
        consumed_digest: Map<(u64, felt252), felt252>,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        EscrowLocked: EscrowLocked,
        EscrowReleased: EscrowReleased,
        EscrowReverted: EscrowReverted,
        EmergencyRevert: EmergencyRevert,
        CascadeRevert: CascadeRevert,
        RelayerUpdated: RelayerUpdated,
        RegistryBound: RegistryBound,
        Paused: Paused,
        Unpaused: Unpaused,
        CertificateConflict: CertificateConflict,
    }

    #[derive(Drop, starknet::Event)]
    pub struct EscrowLocked {
        #[key]
        pub escrow_id: felt252,
        #[key]
        pub route_id: felt252,
        pub entity_id: felt252,
        pub amount: u256,
        pub min_coherence: u64,
    }

    #[derive(Drop, starknet::Event)]
    pub struct EscrowReleased {
        #[key]
        pub escrow_id: felt252,
        #[key]
        pub route_id: felt252,
        /// D_stark — the Poseidon digest of the certificate payload whose
        /// quorum authorized this release (the §7 Starknet consumed-key).
        pub d_stark: felt252,
        /// The SIGNED coherence (×1e6) from the certificate — never a
        /// caller-supplied value (C-04).
        pub coherence: u64,
        pub settled_at: u64,
    }

    #[derive(Drop, starknet::Event)]
    pub struct EscrowReverted {
        #[key]
        pub escrow_id: felt252,
        pub reason: u8,
        pub reverted_at: u64,
    }

    #[derive(Drop, starknet::Event)]
    pub struct EmergencyRevert {
        #[key]
        pub escrow_id: felt252,
        #[key]
        pub caller: ContractAddress,
        pub reverted_at: u64,
    }

    #[derive(Drop, starknet::Event)]
    pub struct CascadeRevert {
        #[key]
        pub child_escrow_id: felt252,
        #[key]
        pub parent_escrow_id: felt252,
        pub reverted_at: u64,
    }

    #[derive(Drop, starknet::Event)]
    pub struct RelayerUpdated {
        pub old_relayer: ContractAddress,
        pub new_relayer: ContractAddress,
    }

    #[derive(Drop, starknet::Event)]
    pub struct RegistryBound {
        #[key]
        pub registry: ContractAddress,
    }

    #[derive(Drop, starknet::Event)]
    pub struct Paused {
        #[key]
        pub by: ContractAddress,
    }

    #[derive(Drop, starknet::Event)]
    pub struct Unpaused {
        #[key]
        pub by: ContractAddress,
    }

    /// §8.2 equivocation evidence: same (epoch, escrow, nonce), two
    /// different certificate digests. Emitted from a SUCCESSFUL no-op tx
    /// (Starknet does not persist events of reverting transactions) so the
    /// evidence actually lands on-chain for L4.9 S1 slashing.
    #[derive(Drop, starknet::Event)]
    pub struct CertificateConflict {
        #[key]
        pub escrow_id: felt252,
        pub validator_epoch: u64,
        pub certificate_nonce: u64,
        pub digest_a: felt252,
        pub digest_b: felt252,
    }

    #[constructor]
    fn constructor(ref self: ContractState, owner: ContractAddress, registry: ContractAddress) {
        self.owner.write(owner);
        self.relayer.write(owner);
        self.escrow_count.write(0);
        self.total_locked_balance.write(0);
        // §10.2 registrar binding — zero = bind later (exactly once).
        if !registry.is_zero() {
            self.registry.write(registry);
            self.registry_bound.write(true);
            self.emit(RegistryBound { registry });
        };
        self.paused.write(false);
    }

    /// The §6 fail-closed sequence, escrow edition. Panics on every
    /// failure (caller-supplied data is never authority); the ONE
    /// non-panic rejection is the §8.2 equivocation conflict, which
    /// returns (false, _) after emitting evidence so the event persists.
    #[generate_trait]
    impl CertificateGate of CertificateGateTrait {
        fn verify_release_certificate(
            ref self: ContractState,
            escrow_id: felt252,
            rec: EscrowRecord,
            cert: Certificate,
            sigs: Span<SigEntry>,
        ) -> (bool, felt252) {
            // ── §6 step 1: STRUCTURE (envelope half) ─────────────────────
            // check_structure (trion_certificate) asserts the payload half:
            // kind, version, ranges — including every felt piece bound to
            // its byte width so no chunk product can wrap the prime.
            check_structure(@cert);
            let n = sigs.len();
            let n_u64: u64 = n.into();
            assert(n >= 3, 'CERT: sig count');
            assert(n_u64 <= MAX_SIG_ENTRIES, 'CERT: too many sigs');
            // distinct signers — duplicate padding is not consensus (§4)
            let mut i: usize = 0;
            loop {
                if i >= n { break; }
                let a = *sigs.at(i);
                let mut j: usize = i + 1;
                loop {
                    if j >= n { break; }
                    let b = *sigs.at(j);
                    assert(
                        !(a.vid_hi16 == b.vid_hi16 && a.vid_lo16 == b.vid_lo16),
                        'CERT: dup signer',
                    );
                    j += 1;
                };
                i += 1;
            };

            // ── §6 step 2: EPOCH (registry + grace — no historical sets) ─
            assert(self.registry_bound.read(), 'CERT: registry unbound');
            let registry = IEpochRegistryDispatcher {
                contract_address: self.registry.read(),
            };
            let (count, total_power, d_consensus, sealed) =
                registry.get_epoch(cert.validator_epoch);
            assert(sealed, 'CERT: unknown epoch');
            let latest = registry.latest_epoch();
            assert(cert.validator_epoch <= latest, 'CERT: future epoch');
            assert(latest - cert.validator_epoch <= EPOCH_GRACE, 'CERT: stale epoch');

            // ── §6 step 3: FRESHNESS (§9 — drift widens lower bound only) ─
            let now = get_block_timestamp();
            assert(is_fresh(cert.issued_at, cert.ttl, now), 'CERT: expired');

            // ── §6 step 4: CONSENSUS PRECONDITIONS ───────────────────────
            assert(cert.hhi <= HHI_MAX_ACCEPTABLE, 'CERT: hhi critical');
            assert(cert.awa_enforced == 1, 'CERT: awa not enforced');
            assert(cert.coherence >= cert.threshold, 'CERT: not safe');
            assert(cert.validator_count == count, 'CERT: count mismatch');
            assert(cert.total_power == total_power, 'CERT: power mismatch');

            // ── §6 step 5: SIGNATURES (batch fail-closed) ────────────────
            // D_stark = Poseidon('TRION-CERT-V1', 12 felt chunks of P).
            let d_stark = stark_digest(@cert);
            // signed_power is recomputed from REGISTERED weights (§5 —
            // envelope weight claims are cross-checked, never summed).
            let mut signed_power: u128 = 0;
            let mut k: usize = 0;
            loop {
                if k >= n { break; }
                let sig = *sigs.at(k);
                let (pubkey, stake, diversity, active) = registry.get_validator(
                    cert.validator_epoch, sig.vid_hi16, sig.vid_lo16,
                );
                // 5b: membership (fail-closed on unknown/inactive signer)
                assert(active, 'CERT: validator inactive');
                // 5c: envelope weight claims == registered values, exact
                assert(
                    sig.stake_weight == stake && sig.diversity_weight == diversity,
                    'CERT: weight mismatch',
                );
                // 5a: STARK-curve ECDSA over D_stark — one bad signature
                // fails the WHOLE certificate.
                assert(verify_signature(pubkey, d_stark, @sig), 'CERT: bad signature');
                // w_j = s_j·d_j/1e6 from the REGISTERED pair — u64 mul is
                // wrap-free (registry caps weights at 1e6 each).
                let w = stake * diversity / 1000000;
                signed_power += w.into();
                k += 1;
            };

            // ── §6 step 6: QUORUM (L4.2 tier from registered D_consensus) ─
            let total_u128: u128 = total_power.into();
            assert(
                quorum_met(signed_power, total_u128, d_consensus),
                'CERT: quorum not met',
            );

            // ── §6 step 7: BINDING (settlement tuple vs escrow state) ────
            assert(escrow_id_matches(@cert, escrow_id), 'CERT: escrow mismatch');
            assert(route_id_matches(@cert, rec.route_id), 'CERT: route mismatch');
            assert(destination_matches(@cert, rec.destination), 'CERT: dest mismatch');
            assert(amount_matches(@cert, rec.amount), 'CERT: amount mismatch');
            // escrow-local tightening (INV-003): the lock-time
            // min_coherence (floored at 0.55) tightens the SIGNED verdict.
            assert(cert.coherence >= rec.min_coherence, 'CERT: below min coherence');

            // ── §6 step 8: NONCE / CONSUMED (§8 replay rules) ────────────
            let key = (cert.validator_epoch, escrow_id);
            let consumed = self.consumed_nonce.read(key);
            if consumed != 0 {
                if cert.certificate_nonce == consumed {
                    let consumed_d = self.consumed_digest.read(key);
                    if d_stark != consumed_d {
                        // §8.2 conflict (DEFENSIVE leg — the reachable leg
                        // lives in release_escrow's terminal-state branch,
                        // because consumption co-commits with settlement):
                        // same (epoch, escrow, nonce), two different
                        // payloads — equivocation evidence for L4.9 S1.
                        // Successful no-op so the event persists.
                        self.emit(CertificateConflict {
                            escrow_id,
                            validator_epoch: cert.validator_epoch,
                            certificate_nonce: consumed,
                            digest_a: consumed_d,
                            digest_b: d_stark,
                        });
                        return (false, d_stark);
                    };
                    // same nonce + same digest + still HOLDING is impossible
                    // (consumption co-commits with settlement); fail closed.
                    assert(false, 'CERT: replay');
                };
                assert(cert.certificate_nonce > consumed, 'CERT: replay');
            };
            // consumption is recorded HERE — settlement effects follow in
            // release_escrow (same tx, §6 step 9).
            self.consumed_nonce.write(key, cert.certificate_nonce);
            self.consumed_digest.write(key, d_stark);

            (true, d_stark)
        }
    }

    #[abi(embed_v0)]
    impl BTCPEscrowImpl of IBTCPEscrow<ContractState> {
        fn lock_escrow(
            ref self: ContractState,
            escrow_id:    felt252,
            route_id:     felt252,
            entity_id:    felt252,
            destination:  ContractAddress,
            amount:       u256,
            min_coherence: u64,
            timeout_blocks: u64,
        ) {
            // Single-hop lock (no parent) — delegates to the multi-hop form
            // with parent_escrow_id = 0, mirroring the Solidity overload pair
            // lockEscrow(...6) / lockEscrow(...6, parentEscrowId).
            self.lock_escrow_with_parent(
                escrow_id,
                route_id,
                entity_id,
                destination,
                amount,
                min_coherence,
                timeout_blocks,
                0,
            );
        }

        fn lock_escrow_with_parent(
            ref self: ContractState,
            escrow_id:    felt252,
            route_id:     felt252,
            entity_id:    felt252,
            destination:  ContractAddress,
            amount:       u256,
            min_coherence: u64,
            timeout_blocks: u64,
            parent_escrow_id: felt252,
        ) {
            let caller = get_caller_address();
            let relayer = self.relayer.read();
            let owner   = self.owner.read();
            assert(caller == relayer || caller == owner, 'BTCP: not authorized');
            // M2 E1: pause blocks NEW LOCKS only (settlements/lifecycle
            // are never pausable — see release_escrow).
            assert(!self.paused.read(), 'BTCP: paused');
            assert(escrow_id != 0, 'BTCP: zero escrow id');
            // felt ordering: felt252 has no PartialOrd — the id-range bound
            // compares as u256 through the family-3 library helper (exact
            // integer comparison; same fail-closed semantics).
            assert(felt_lt(escrow_id, FELT_ID_MAX), 'BTCP: escrow id range');
            assert(felt_lt(route_id, FELT_ID_MAX), 'BTCP: route id range');
            assert(amount > 0_u256, 'BTCP: zero amount');
            // INV-003: the coherence gate is protocol-floored — callers
            // may tighten (raise), never loosen below 0.55.
            assert(min_coherence >= MIN_COHERENCE_FLOOR, 'BTCP: coherence floor');
            assert(min_coherence <= 1_000_000_u64, 'BTCP: invalid coherence');
            assert(timeout_blocks > 0_u64, 'BTCP: zero timeout');

            // Reject duplicate
            let existing = self.escrows.read(escrow_id);
            assert(existing.escrow_id == 0, 'BTCP: escrow exists');

            // Starknet does not expose block height in Cairo contracts; the
            // lock anchor is the block TIMESTAMP and timeout_blocks is
            // interpreted as seconds-on-chain (1 block ≈ 1s on Starknet
            // mainnet, so the numeric value remains block-equivalent).
            let lock_ts = get_block_timestamp();

            let rec = EscrowRecord {
                escrow_id,
                route_id,
                entity_id,
                destination,
                amount,
                min_coherence,
                lock_height: lock_ts,
                timeout_blocks,
                state: STATE_HOLDING,
                revert_reason: REASON_TIMEOUT,
                settled_at: 0_u64,
                reverted_at: 0_u64,
                locked_by: caller,
                parent_escrow_id,
            };
            self.escrows.write(escrow_id, rec);
            let count = self.escrow_count.read();
            self.escrow_count.write(count + 1);

            // SECURITY: locked-balance accounting — the funder's locked pool
            // and the global locked pool each grow by the locked amount
            // (mirrors Solidity `_lockedBalance += msg.value`). ACCOUNTING
            // ONLY (see module header): no token custody is wired; this
            // accounting makes the locked pool auditable and
            // double-spend-proof for the future custody wiring.
            let funder_locked = self.locked_balance.read(caller);
            self.locked_balance.write(caller, funder_locked + amount);
            let total_locked = self.total_locked_balance.read();
            self.total_locked_balance.write(total_locked + amount);

            self.emit(EscrowLocked {
                escrow_id, route_id, entity_id, amount, min_coherence,
            });
        }

        fn release_escrow(
            ref self: ContractState,
            escrow_id: felt252,
            cert:      Certificate,
            sigs:      Span<SigEntry>,
        ) {
            // PERMISSIONLESS: no caller check — the certificate quorum is
            // the authority (C-04: caller-supplied coherence is gone).
            let mut rec = self.escrows.read(escrow_id);
            assert(rec.escrow_id != 0, 'BTCP: not found');

            if rec.state != STATE_HOLDING {
                // §8.2 idempotent resubmission: a terminal escrow plus the
                // SAME certificate (same epoch-scope nonce and D_stark) is
                // a no-op for observability / retry safety.
                let d = stark_digest(@cert);
                let c_nonce = self.consumed_nonce.read((cert.validator_epoch, escrow_id));
                let c_digest = self.consumed_digest.read((cert.validator_epoch, escrow_id));
                if cert.certificate_nonce == c_nonce {
                    if d == c_digest {
                        return ();
                    };
                    // §8.2 CONFLICT (the reachable leg): same
                    // (epoch, escrow, nonce), a different quorum payload —
                    // post-settlement equivocation evidence for L4.9 S1.
                    // Successful no-op so the event PERSISTS on-chain
                    // (Starknet drops events of reverting txs). NOTE: this
                    // event is an UNVERIFIED evidence POINTER — it fires
                    // before signature verification; the self-
                    // authenticating evidence (both signature sets) is
                    // collected and validated off-chain per §10.3. No
                    // settlement effect either way.
                    self.emit(CertificateConflict {
                        escrow_id,
                        validator_epoch: cert.validator_epoch,
                        certificate_nonce: c_nonce,
                        digest_a: c_digest,
                        digest_b: d,
                    });
                    return ();
                };
                // a genuinely different certificate (different nonce)
                // against a settled escrow fails closed.
                assert(false, 'BTCP: already settled');
            };

            // INV-004 / M2 E3: release requires NOT expired. (Previously
            // this check was missing entirely — a stale escrow could be
            // released long after its timeout had passed.)
            assert(
                get_block_timestamp() <= rec.lock_height + rec.timeout_blocks,
                'BTCP: expired',
            );

            // ── §6 steps 1–8 (fail-closed certificate verification) ──────
            let (ok, d_stark) = self.verify_release_certificate(
                escrow_id, rec, cert, sigs,
            );
            if !ok {
                // §8.2 equivocation conflict — evidence event already
                // emitted inside the gate; no settlement effect.
                return ();
            };

            // ── §6 step 9 + CEI pattern: terminal state, cleared amount and
            // decremented accounting BEFORE any external effect — mirrors
            // the Solidity releaseEscrow ordering (`esc.amount = 0` before
            // transfer). (Accounting-only tier: the external effect is the
            // state/event, not a token transfer — see module header.)
            let amount_out = rec.amount;
            let funder     = rec.locked_by;
            rec.state       = STATE_RELEASED;
            rec.settled_at  = get_block_timestamp();
            rec.amount      = 0_u256;
            self.escrows.write(escrow_id, rec);

            // SECURITY: value leaves the locked pool on both levels
            // (mirrors Solidity `_lockedBalance -= amountToTransfer`).
            let funder_locked = self.locked_balance.read(funder);
            assert(funder_locked >= amount_out, 'BTCP: locked underflow');
            self.locked_balance.write(funder, funder_locked - amount_out);
            let total_locked = self.total_locked_balance.read();
            assert(total_locked >= amount_out, 'BTCP: locked underflow');
            self.total_locked_balance.write(total_locked - amount_out);

            self.emit(EscrowReleased {
                escrow_id,
                route_id: rec.route_id,
                d_stark,
                coherence: cert.coherence,
                settled_at: rec.settled_at,
            });
        }

        fn revert_escrow(ref self: ContractState, escrow_id: felt252, reason: u8) {
            let caller = get_caller_address();
            let relayer = self.relayer.read();
            let owner   = self.owner.read();

            let mut rec = self.escrows.read(escrow_id);
            assert(rec.escrow_id != 0, 'BTCP: not found');
            assert(rec.state == STATE_HOLDING, 'BTCP: not holding');

            let is_timeout = get_block_timestamp() > rec.lock_height + rec.timeout_blocks;
            if !is_timeout {
                assert(caller == relayer || caller == owner, 'BTCP: not authorized');
                assert(reason != REASON_TIMEOUT, 'BTCP: not timeout');
            };

            // ── CEI pattern: terminal state, cleared amount and decremented
            // accounting BEFORE any external effect (Solidity revertEscrow).
            let amount_out = rec.amount;
            let funder     = rec.locked_by;
            let now        = get_block_timestamp();
            rec.state         = STATE_REVERTED;
            rec.revert_reason = reason;
            rec.reverted_at   = now;
            rec.amount        = 0_u256;
            self.escrows.write(escrow_id, rec);

            let funder_locked = self.locked_balance.read(funder);
            assert(funder_locked >= amount_out, 'BTCP: locked underflow');
            self.locked_balance.write(funder, funder_locked - amount_out);
            let total_locked = self.total_locked_balance.read();
            assert(total_locked >= amount_out, 'BTCP: locked underflow');
            self.total_locked_balance.write(total_locked - amount_out);

            self.emit(EscrowReverted { escrow_id, reason, reverted_at: now });

            // ── Cascade revert (Gap 9, mirrors Solidity `_cascadeRevert`) ──
            // When a child escrow reverts, its parent (and transitively the
            // whole ancestor chain) reverts too, with reason CASCADE_REVERT.
            // Missing or already-terminal parents are skipped silently —
            // exactly like the Solidity internal helper. Inlined as an
            // explicit loop instead of a recursive internal function.
            let mut child_id  = escrow_id;
            let mut parent_id = rec.parent_escrow_id;
            loop {
                if parent_id == 0 { break; }
                let mut parent = self.escrows.read(parent_id);
                if parent.escrow_id == 0 { break; }
                if parent.state != STATE_HOLDING { break; }

                let p_amount     = parent.amount;
                let p_funder     = parent.locked_by;
                let grandparent  = parent.parent_escrow_id;
                parent.state         = STATE_REVERTED;
                parent.revert_reason = REASON_CASCADE_REVERT;
                parent.reverted_at   = now;
                parent.amount        = 0_u256;
                self.escrows.write(parent_id, parent);

                let p_funder_locked = self.locked_balance.read(p_funder);
                assert(p_funder_locked >= p_amount, 'BTCP: locked underflow');
                self.locked_balance.write(p_funder, p_funder_locked - p_amount);
                let p_total_locked = self.total_locked_balance.read();
                assert(p_total_locked >= p_amount, 'BTCP: locked underflow');
                self.total_locked_balance.write(p_total_locked - p_amount);

                self.emit(CascadeRevert {
                    child_escrow_id: child_id,
                    parent_escrow_id: parent_id,
                    reverted_at: now,
                });
                self.emit(EscrowReverted {
                    escrow_id: parent_id,
                    reason: REASON_CASCADE_REVERT,
                    reverted_at: now,
                });

                // Recursively cascade to the grandparent.
                child_id  = parent_id;
                parent_id = grandparent;
            };
        }

        fn revert_emergency(ref self: ContractState, escrow_id: felt252) {
            let caller = get_caller_address();

            let mut rec = self.escrows.read(escrow_id);
            assert(rec.escrow_id != 0, 'BTCP: not found');
            assert(rec.state == STATE_HOLDING, 'BTCP: not holding');
            // Gap 8: no relayer, no coherence proof — after 7 days ANY
            // caller can force the revert. lock_height is the block
            // TIMESTAMP at lock (see lock_escrow_with_parent).
            assert(
                get_block_timestamp() >= rec.lock_height + EMERGENCY_ESCAPE_SECONDS,
                'BTCP: emergency not yet',
            );

            // ── CEI pattern: terminal state, cleared amount and decremented
            // accounting BEFORE any external effect (Solidity revertEmergency).
            let amount_out = rec.amount;
            let funder     = rec.locked_by;
            let now        = get_block_timestamp();
            rec.state         = STATE_EMERGENCY_REVERTED;
            rec.revert_reason = REASON_EMERGENCY_ESCAPE;
            rec.reverted_at   = now;
            rec.amount        = 0_u256;
            self.escrows.write(escrow_id, rec);

            let funder_locked = self.locked_balance.read(funder);
            assert(funder_locked >= amount_out, 'BTCP: locked underflow');
            self.locked_balance.write(funder, funder_locked - amount_out);
            let total_locked = self.total_locked_balance.read();
            assert(total_locked >= amount_out, 'BTCP: locked underflow');
            self.total_locked_balance.write(total_locked - amount_out);

            self.emit(EmergencyRevert { escrow_id, caller, reverted_at: now });

            // ── Cascade revert (Gap 9, mirrors Solidity `_cascadeRevert`) ──
            // Same inlined loop as revert_escrow: an emergency revert of a
            // child cascades through its whole ancestor chain.
            let mut child_id  = escrow_id;
            let mut parent_id = rec.parent_escrow_id;
            loop {
                if parent_id == 0 { break; }
                let mut parent = self.escrows.read(parent_id);
                if parent.escrow_id == 0 { break; }
                if parent.state != STATE_HOLDING { break; }

                let p_amount     = parent.amount;
                let p_funder     = parent.locked_by;
                let grandparent  = parent.parent_escrow_id;
                parent.state         = STATE_REVERTED;
                parent.revert_reason = REASON_CASCADE_REVERT;
                parent.reverted_at   = now;
                parent.amount        = 0_u256;
                self.escrows.write(parent_id, parent);

                let p_funder_locked = self.locked_balance.read(p_funder);
                assert(p_funder_locked >= p_amount, 'BTCP: locked underflow');
                self.locked_balance.write(p_funder, p_funder_locked - p_amount);
                let p_total_locked = self.total_locked_balance.read();
                assert(p_total_locked >= p_amount, 'BTCP: locked underflow');
                self.total_locked_balance.write(p_total_locked - p_amount);

                self.emit(CascadeRevert {
                    child_escrow_id: child_id,
                    parent_escrow_id: parent_id,
                    reverted_at: now,
                });
                self.emit(EscrowReverted {
                    escrow_id: parent_id,
                    reason: REASON_CASCADE_REVERT,
                    reverted_at: now,
                });

                // Recursively cascade to the grandparent.
                child_id  = parent_id;
                parent_id = grandparent;
            };
        }

        fn get_escrow(self: @ContractState, escrow_id: felt252) -> EscrowRecord {
            self.escrows.read(escrow_id)
        }

        fn is_expired(self: @ContractState, escrow_id: felt252) -> bool {
            let rec = self.escrows.read(escrow_id);
            rec.state == STATE_HOLDING && get_block_timestamp() > rec.lock_height + rec.timeout_blocks
        }

        fn emergency_escape_available(self: @ContractState, escrow_id: felt252) -> bool {
            // Gap 8 view — mirrors Solidity emergencyEscapeAvailable().
            let rec = self.escrows.read(escrow_id);
            rec.state == STATE_HOLDING
                && get_block_timestamp() >= rec.lock_height + EMERGENCY_ESCAPE_SECONDS
        }

        fn escrow_count(self: @ContractState) -> u64 {
            self.escrow_count.read()
        }

        fn total_locked_balance(self: @ContractState) -> u256 {
            self.total_locked_balance.read()
        }

        fn locked_balance(self: @ContractState, funder: ContractAddress) -> u256 {
            self.locked_balance.read(funder)
        }

        fn set_relayer(ref self: ContractState, new_relayer: ContractAddress) {
            let caller = get_caller_address();
            let owner   = self.owner.read();
            assert(caller == owner, 'BTCP: not owner');
            let old = self.relayer.read();
            self.relayer.write(new_relayer);
            self.emit(RelayerUpdated { old_relayer: old, new_relayer });
        }

        fn bind_registry(ref self: ContractState, registry: ContractAddress) {
            let caller = get_caller_address();
            assert(caller == self.owner.read(), 'BTCP: not owner');
            // ONE-WAY: a bound registry can never be swapped (a rogue
            // registry with fake weights is the R-4 trust boundary —
            // rebinding would make it owner-triggerable).
            assert(!self.registry_bound.read(), 'BTCP: registry bound');
            assert(!registry.is_zero(), 'BTCP: zero registry');
            self.registry.write(registry);
            self.registry_bound.write(true);
            self.emit(RegistryBound { registry });
        }

        fn get_registry(self: @ContractState) -> ContractAddress {
            self.registry.read()
        }

        fn pause(ref self: ContractState) {
            let caller = get_caller_address();
            assert(caller == self.owner.read(), 'BTCP: not owner');
            self.paused.write(true);
            self.emit(Paused { by: caller });
        }

        fn unpause(ref self: ContractState) {
            let caller = get_caller_address();
            assert(caller == self.owner.read(), 'BTCP: not owner');
            self.paused.write(false);
            self.emit(Unpaused { by: caller });
        }

        fn is_paused(self: @ContractState) -> bool {
            self.paused.read()
        }
    }
}
