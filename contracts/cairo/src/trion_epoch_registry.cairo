/// TRION Protocol — TrionEpochRegistry (Starknet / Cairo)
/// =======================================================
/// TWIN FILE — byte-identical copies live at
///   contracts/starknet/src/trion_epoch_registry.cairo  (this file)
///   contracts/cairo/src/trion_epoch_registry.cairo     (the twin)
/// Identity is enforced by tests/contracts/test_btcp_escrow_cairo.py.
///
/// The per-epoch validator-set registrar of CANONICAL_CERTIFICATE.md §10.2
/// (the "registrar" §7 names for the Starknet family): the TRION registrar
/// relayer publishes the epoch set here at each epoch boundary — ONE
/// transaction per epoch per chain, never per certificate.
///
/// What it stores (per epoch, append-only):
///   • the validator roster: canonical validator_id (32 bytes, two
///     range-asserted 16-byte felt halves) → STARK-curve public key felt +
///     stake s_j ×1e6 + diversity d_j ×1e6
///   • epoch meta: validator_count, total_effective_power Σ s_j·d_j ×1e6,
///     D_consensus (mean d_j ×1e6 — selects the L4.2 quorum tier)
///
/// Registration rules (fail-closed):
///   • append-only: epoch must be STRICTLY greater than latest_epoch — a
///     sealed epoch is never rewritten (validator-set changes take effect
///     only at boundaries, §10.2)
///   • weights are normalized shares: 0 < s_j ≤ 1e6 and 0 < d_j ≤ 1e6
///     (bounds that make every downstream u64/u128 quorum product provably
///     wrap-free — see trion_certificate.cairo quorum_met)
///   • the low 16-byte half of the validator_id is unique per epoch
///     (registration-time discipline; 128-bit collision odds within a
///     ≤128-validator set are ~2^-122 — the high half is stored IN the
///     entry and verified at lookup, so a low-half collision fails closed)
///   • roster size ≤ 128 (V2 §9.2 launch threshold is 100 validators)
///
/// TRUST MODEL (documented, honest — audit residual R-4): the registrar
/// admin is a single TRION-controlled relayer role, auditable on the TRION
/// chain; a registrar compromise is bounded to one epoch by the TRION-side
/// epoch-set root. This contract CANNOT verify that root (no TRION-side
/// light client on Starknet yet) — the admin writes are the trust anchor
/// for THIS deployment family. Admin = the deployer, immutable (rotation =
/// redeploy). This is the same trust class as the EVM tier's
/// TrionEpochRegistry.sol registrar role.
///
/// The certificate verifier (btcp_escrow.cairo / trion_execution_gate.cairo)
/// reads epochs and validator entries through the auto-generated
/// IEpochRegistryDispatcher — quorum is ALWAYS computed from THIS
/// registered state, never from certificate- or envelope-supplied values
/// (CANONICAL_CERTIFICATE §5; audit H-04/C-06).

#[starknet::interface]
pub trait IEpochRegistry<TContractState> {
    /// Registrar writes ONE epoch per boundary (§10.2 — one tx per epoch).
    fn register_epoch(
        ref self: TContractState,
        epoch: u64,
        entries: Span<ValidatorRegistration>,
    );
    /// Look up a validator of an epoch by its canonical 32-byte id (two
    /// 16-byte felt halves). Returns (stark_pubkey, stake ×1e6,
    /// diversity ×1e6, active). Unknown or high-half-mismatched ids
    /// return (0, 0, 0, false) — callers fail closed on that.
    fn get_validator(
        self: @TContractState,
        epoch: u64,
        vid_hi16: felt252,
        vid_lo16: felt252,
    ) -> (felt252, u64, u64, bool);
    /// Epoch meta: (validator_count, total_effective_power ×1e6,
    /// d_consensus ×1e6, sealed). Unknown epochs return (0, 0, 0, false).
    fn get_epoch(self: @TContractState, epoch: u64) -> (u64, u64, u64, bool);
    /// Highest epoch written so far (0 before any registration).
    fn latest_epoch(self: @TContractState) -> u64;
}

/// One validator registration as it crosses the registrar ABI.
#[derive(Drop, Serde, Copy)]
pub struct ValidatorRegistration {
    pub vid_hi16: felt252,     // validator_id bytes [0:16)  (< 2^128)
    pub vid_lo16: felt252,     // validator_id bytes [16:32) (< 2^128)
    pub stark_pubkey: felt252, // STARK-curve public key (< 2^251)
    pub stake_weight: u64,     // s_j ×1e6, 0 < s ≤ 1e6
    pub diversity_weight: u64, // d_j ×1e6, 0 < d ≤ 1e6
}

/// Stored roster entry. NOTE ON STORAGE KEYS: entries are keyed by the
/// 2-tuple (epoch, vid_lo16); the high half rides INSIDE the entry and is
/// verified at lookup. Storage addresses are compiler-derived from the
/// declared field names — the two maps (`validators`, `epoch_meta`) plus
/// the scalars live in disjoint compiler-generated namespaces; the
/// consumed-certificate maps live in the ESCROW, not here, so no
/// consumed-key/registry-key collision is possible by construction.
#[derive(Drop, starknet::Store)]
pub struct ValidatorEntry {
    pub vid_hi16: felt252,
    pub stark_pubkey: felt252,
    pub stake_weight: u64,
    pub diversity_weight: u64,
}

#[derive(Drop, starknet::Store)]
pub struct EpochMeta {
    pub validator_count: u64,
    pub total_power: u64,   // Σ s_j·d_j/1e6, ×1e6 — bounds-proven ≤ 1.28e8
    pub d_consensus: u64,  // mean d_j, ×1e6
    pub sealed: bool,
}

#[starknet::contract]
pub mod TrionEpochRegistry {
    use super::{
        EpochMeta, IEpochRegistry, ValidatorEntry, ValidatorRegistration,
    };
    use starknet::{
        ContractAddress, get_caller_address,
        storage::{
            Map, StorageMapReadAccess, StorageMapWriteAccess,
            StoragePointerReadAccess, StoragePointerWriteAccess,
        },
    };

    /// Roster cap — V2 §9.2 launch threshold is 100 validators; 128 leaves
    /// deployment headroom while bounding every accumulation below.
    const MAX_EPOCH_VALIDATORS: u64 = 128;

    /// Weights are normalized shares ×1e6 (§5.1) — asserted at registration.
    const MAX_WEIGHT: u64 = 1000000;

    /// 2^128 — range bound of each validator_id felt half.
    const P2_128: felt252 = 0x100000000000000000000000000000000;

    /// 2^251 — sanity bound for STARK public keys (felt range discipline).
    const P2_251: felt252 = 0x800000000000000000000000000000000000000000000000000000000000000;

    #[storage]
    struct Storage {
        /// Immutable deployer = the registrar relayer role (R-4 trust).
        admin: ContractAddress,
        latest_epoch: u64,
        /// (epoch, vid_lo16) → roster entry (vid_hi16 verified at lookup).
        validators: Map<(u64, felt252), ValidatorEntry>,
        epoch_meta: Map<u64, EpochMeta>,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        EpochRegistered: EpochRegistered,
    }

    #[derive(Drop, starknet::Event)]
    pub struct EpochRegistered {
        #[key]
        pub epoch: u64,
        pub validator_count: u64,
        pub total_power: u64,
        pub d_consensus: u64,
    }

    #[constructor]
    fn constructor(ref self: ContractState) {
        self.admin.write(get_caller_address());
        self.latest_epoch.write(0);
    }

    #[abi(embed_v0)]
    impl RegistryImpl of IEpochRegistry<ContractState> {
        fn register_epoch(
            ref self: ContractState,
            epoch: u64,
            entries: Span<ValidatorRegistration>,
        ) {
            let caller = get_caller_address();
            assert(caller == self.admin.read(), 'REG: not registrar');

            let n = entries.len();
            let n_u64: u64 = n.into();
            assert(n > 0, 'REG: empty epoch');
            assert(n <= MAX_EPOCH_VALIDATORS, 'REG: epoch too large');
            // Append-only: strictly increasing epochs, a sealed set is
            // never rewritten (§10.2 — changes land at the next boundary).
            let latest = self.latest_epoch.read();
            assert(epoch > latest, 'REG: epoch not newer');

            // accumulate in u64 — every operand is range-proven:
            // s,d ≤ 1e6 ⇒ w = s·d/1e6 ≤ 1e6; n ≤ 128 ⇒ sums ≤ 1.28e8.
            let mut total_power: u64 = 0;
            let mut total_diversity: u64 = 0;
            let mut i: usize = 0;
            loop {
                if i >= n { break; }
                let e = *entries.at(i);

                assert(e.vid_hi16 < P2_128, 'REG: vid_hi range');
                assert(e.vid_lo16 < P2_128, 'REG: vid_lo range');
                assert(e.stark_pubkey < P2_251, 'REG: pubkey range');
                assert(e.stark_pubkey != 0, 'REG: zero pubkey');
                assert(e.stake_weight != 0, 'REG: zero stake');
                assert(e.stake_weight <= MAX_WEIGHT, 'REG: stake cap');
                assert(e.diversity_weight != 0, 'REG: zero diversity');
                assert(e.diversity_weight <= MAX_WEIGHT, 'REG: diversity cap');

                // Low-half uniqueness per epoch (see module header): an
                // existing entry at (epoch, vid_lo16) — whatever its high
                // half — is a hard reject. This also makes the write below
                // collision-free: no registration can overwrite another.
                let existing = self.validators.read((epoch, e.vid_lo16));
                assert(existing.stark_pubkey == 0, 'REG: validator exists');

                let w = e.stake_weight * e.diversity_weight / 1000000;
                total_power += w; // ≤ 128 · 1e6 — no u64 wrap possible
                total_diversity += e.diversity_weight; // ≤ 128 · 1e6

                self.validators.write((epoch, e.vid_lo16), ValidatorEntry {
                    vid_hi16: e.vid_hi16,
                    stark_pubkey: e.stark_pubkey,
                    stake_weight: e.stake_weight,
                    diversity_weight: e.diversity_weight,
                });
                i += 1;
            };

            // D_consensus = mean d_j over the epoch set (§5.2) — floor
            // division; total_diversity ≤ 1.28e8 so no wrap.
            let d_consensus = total_diversity / n_u64;

            self.epoch_meta.write(epoch, EpochMeta {
                validator_count: n_u64,
                total_power,
                d_consensus,
                sealed: true,
            });
            self.latest_epoch.write(epoch);

            self.emit(EpochRegistered {
                epoch, validator_count: n_u64, total_power, d_consensus,
            });
        }

        fn get_validator(
            self: @ContractState,
            epoch: u64,
            vid_hi16: felt252,
            vid_lo16: felt252,
        ) -> (felt252, u64, u64, bool) {
            let entry = self.validators.read((epoch, vid_lo16));
            // High-half must match the stored entry — a low-half-only match
            // is NOT this validator (fail-closed: active=false).
            if entry.stark_pubkey == 0 || entry.vid_hi16 != vid_hi16 {
                return (0, 0, 0, false);
            }
            (entry.stark_pubkey, entry.stake_weight, entry.diversity_weight, true)
        }

        fn get_epoch(
            self: @ContractState, epoch: u64,
        ) -> (u64, u64, u64, bool) {
            let meta = self.epoch_meta.read(epoch);
            (meta.validator_count, meta.total_power, meta.d_consensus, meta.sealed)
        }

        fn latest_epoch(self: @ContractState) -> u64 {
            self.latest_epoch.read()
        }
    }
}
