/// TRION Protocol — BTCPEscrow v2 (Starknet) — Quorum-Bound Release
/// =================================================================
/// Closes A12 / fixes D8: release requires DW-BFT quorum attestation,
/// not relayer self-attestation.
///
/// Key changes from v1:
/// - set_trion_oracle(): one-way, immutable once set.
/// - submit_route_attestation(): validators attest route values.
///   First attestation etches values immutably; mismatch → dispute.
/// - release_escrow(): requires attestation_count >= quorum_required
///   AND freshness (block_time - attestation_time <= 300s).
/// - Relayer self-attested coherence alone CANNOT release.
///
/// specification BTCP §4.3 + §11 + DW-BFT quorum binding.

#[starknet::interface]
pub trait IBTCPEscrowV2<TContractState> {
    /// One-way: set the TRION oracle address. Cannot be changed once set.
    fn set_trion_oracle(ref self: TContractState, oracle: starknet::ContractAddress);

    /// Add a DW-BFT validator to the validator set.
    fn add_validator(ref self: TContractState, validator: starknet::ContractAddress);

    /// Set the quorum threshold (default 3-of-5 for mainnet).
    fn set_quorum_required(ref self: TContractState, quorum: u32);

    /// A validator submits an attestation for a route.
    /// First attestation etches the values; subsequent must match or → dispute.
    fn submit_route_attestation(
        ref self: TContractState,
        route_id: felt252,
        coherence: u64,
        execution_bh: felt252,
        attestation_time: u64,
    );

    /// Lock escrow (same as v1).
    fn lock_escrow(
        ref self: TContractState,
        escrow_id: felt252,
        route_id: felt252,
        entity_id: felt252,
        destination: starknet::ContractAddress,
        amount: u256,
        min_coherence: u64,
        timeout_blocks: u64,
    );

    /// Release escrow — requires quorum-bound attestation.
    /// Relayer self-attested coherence alone CANNOT release.
    fn release_escrow(
        ref self: TContractState,
        escrow_id: felt252,
        execution_bh: felt252,
        coherence: u64,
    );

    fn revert_escrow(ref self: TContractState, escrow_id: felt252, reason: u8);
    fn get_escrow(self: @TContractState, escrow_id: felt252) -> EscrowRecord;
    fn get_route_attestation(self: @TContractState, route_id: felt252) -> RouteAttestation;
    fn is_expired(self: @TContractState, escrow_id: felt252) -> bool;
    fn escrow_count(self: @TContractState) -> u64;
    fn set_relayer(ref self: TContractState, new_relayer: starknet::ContractAddress);
}

#[derive(Drop, Serde, Copy, starknet::Store)]
pub struct EscrowRecord {
    pub escrow_id: felt252,
    pub route_id: felt252,
    pub entity_id: felt252,
    pub destination: starknet::ContractAddress,
    pub amount: u256,
    pub min_coherence: u64,
    pub lock_height: u64,
    pub timeout_blocks: u64,
    pub state: u8,
    pub revert_reason: u8,
    pub settled_at: u64,
    pub reverted_at: u64,
    pub locked_by: starknet::ContractAddress,
}

#[derive(Drop, Serde, Copy, starknet::Store)]
pub struct RouteAttestation {
    pub etched_coherence: u64,
    pub etched_execution_bh: felt252,
    pub attestation_count: u32,
    pub last_attestation_time: u64,
    pub disputed: bool,
}

#[starknet::contract]
pub mod BTCPEscrowV2 {
    use super::{EscrowRecord, RouteAttestation, IBTCPEscrowV2};
    use starknet::{
        ContractAddress, get_caller_address, get_block_timestamp,
        storage::{Map, StorageMapReadAccess, StorageMapWriteAccess,
                  StoragePointerReadAccess, StoragePointerWriteAccess},
    };

    const STATE_HOLDING: u8 = 0;
    const STATE_RELEASED: u8 = 1;
    const STATE_REVERTED: u8 = 2;
    const MAX_ATTESTATION_AGE: u64 = 300; // 5 minutes

    #[storage]
    struct Storage {
        owner: ContractAddress,
        relayer: ContractAddress,
        escrows: Map<felt252, EscrowRecord>,
        escrow_count: u64,
        // ── Quorum-bound release (Phase 1.1) ──
        trion_oracle: ContractAddress,
        oracle_set: bool,
        quorum_required: u32,
        validators: Map<ContractAddress, bool>,
        // route_id → attestation record
        route_attestations: Map<felt252, RouteAttestation>,
        // (route_id, validator) → bool (has this validator attested?)
        route_validator_attested: Map<(felt252, ContractAddress), bool>,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        EscrowLocked: EscrowLocked,
        EscrowReleased: EscrowReleased,
        EscrowReverted: EscrowReverted,
        RelayerUpdated: RelayerUpdated,
        OracleSet: OracleSet,
        ValidatorAdded: ValidatorAdded,
        AttestationSubmitted: AttestationSubmitted,
        AttestationMismatch: AttestationMismatch,
        QuorumReached: QuorumReached,
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
        pub route_id: felt252,
        pub execution_bh: felt252,
        pub coherence: u64,
        pub settled_at: u64,
        pub attestation_count: u32,
    }

    #[derive(Drop, starknet::Event)]
    pub struct EscrowReverted {
        #[key]
        pub escrow_id: felt252,
        pub reason: u8,
        pub reverted_at: u64,
    }

    #[derive(Drop, starknet::Event)]
    pub struct RelayerUpdated {
        pub old_relayer: ContractAddress,
        pub new_relayer: ContractAddress,
    }

    #[derive(Drop, starknet::Event)]
    pub struct OracleSet {
        pub oracle: ContractAddress,
    }

    #[derive(Drop, starknet::Event)]
    pub struct ValidatorAdded {
        pub validator: ContractAddress,
    }

    #[derive(Drop, starknet::Event)]
    pub struct AttestationSubmitted {
        #[key]
        pub route_id: felt252,
        pub validator: ContractAddress,
        pub coherence: u64,
        pub execution_bh: felt252,
        pub attestation_count: u32,
    }

    #[derive(Drop, starknet::Event)]
    pub struct AttestationMismatch {
        #[key]
        pub route_id: felt252,
        pub validator: ContractAddress,
        pub etched_coherence: u64,
        pub submitted_coherence: u64,
    }

    #[derive(Drop, starknet::Event)]
    pub struct QuorumReached {
        #[key]
        pub route_id: felt252,
        pub count: u32,
        pub quorum_required: u32,
    }

    #[constructor]
    fn constructor(ref self: ContractState, owner: ContractAddress) {
        self.owner.write(owner);
        self.relayer.write(owner);
        self.escrow_count.write(0);
        self.oracle_set.write(false);
        self.quorum_required.write(3); // 3-of-5 default for mainnet
    }

    #[abi(embed_v0)]
    impl BTCPEscrowV2Impl of IBTCPEscrowV2<ContractState> {
        fn set_trion_oracle(ref self: ContractState, oracle: ContractAddress) {
            let caller = get_caller_address();
            assert(caller == self.owner.read(), 'BTCP: not owner');
            let already = self.oracle_set.read();
            assert(!already, 'BTCP: oracle already set');
            self.trion_oracle.write(oracle);
            self.oracle_set.write(true);
            self.emit(OracleSet { oracle });
        }

        fn add_validator(ref self: ContractState, validator: ContractAddress) {
            let caller = get_caller_address();
            assert(caller == self.owner.read(), 'BTCP: not owner');
            self.validators.write(validator, true);
            self.emit(ValidatorAdded { validator });
        }

        fn set_quorum_required(ref self: ContractState, quorum: u32) {
            let caller = get_caller_address();
            assert(caller == self.owner.read(), 'BTCP: not owner');
            assert(quorum > 0, 'BTCP: zero quorum');
            assert(quorum <= 10, 'BTCP: quorum too high');
            self.quorum_required.write(quorum);
        }

        fn submit_route_attestation(
            ref self: ContractState,
            route_id: felt252,
            coherence: u64,
            execution_bh: felt252,
            attestation_time: u64,
        ) {
            let caller = get_caller_address();
            // Caller must be a registered validator
            let is_validator = self.validators.read(caller);
            assert(is_validator, 'BTCP: not a validator');

            // Check this validator hasn't already attested for this route
            let already_attested = self.route_validator_attested.read((route_id, caller));
            assert(!already_attested, 'BTCP: already attested');

            // Mark this validator as having attested
            self.route_validator_attested.write((route_id, caller), true);

            // Read existing attestation record
            let mut att = self.route_attestations.read(route_id);

            if att.attestation_count == 0 {
                // First attestation: etch the values immutably
                att.etched_coherence = coherence;
                att.etched_execution_bh = execution_bh;
                att.attestation_count = 1;
                att.last_attestation_time = attestation_time;
                att.disputed = false;
            } else {
                // Subsequent attestation: must match etched values
                if coherence != att.etched_coherence || execution_bh != att.etched_execution_bh {
                    // Mismatch → fail-closed dispute state
                    att.disputed = true;
                    self.route_attestations.write(route_id, att);
                    self.emit(AttestationMismatch {
                        route_id,
                        validator: caller,
                        etched_coherence: att.etched_coherence,
                        submitted_coherence: coherence,
                    });
                    return;
                }
                att.attestation_count += 1;
                att.last_attestation_time = attestation_time;
            }

            self.route_attestations.write(route_id, att);
            self.emit(AttestationSubmitted {
                route_id, validator: caller, coherence, execution_bh,
                attestation_count: att.attestation_count,
            });

            // Check if quorum reached
            let quorum = self.quorum_required.read();
            if att.attestation_count >= quorum {
                self.emit(QuorumReached {
                    route_id, count: att.attestation_count, quorum_required: quorum,
                });
            }
        }

        fn lock_escrow(
            ref self: ContractState,
            escrow_id: felt252,
            route_id: felt252,
            entity_id: felt252,
            destination: ContractAddress,
            amount: u256,
            min_coherence: u64,
            timeout_blocks: u64,
        ) {
            let caller = get_caller_address();
            let relayer = self.relayer.read();
            let owner = self.owner.read();
            assert(caller == relayer || caller == owner, 'BTCP: not authorized');
            assert(amount > 0_u256, 'BTCP: zero amount');
            assert(min_coherence <= 1_000_000_u64, 'BTCP: invalid coherence');
            assert(timeout_blocks > 0_u64, 'BTCP: zero timeout');

            let existing = self.escrows.read(escrow_id);
            assert(existing.amount == 0_u256, 'BTCP: escrow exists');

            let lock_ts = get_block_timestamp();
            let rec = EscrowRecord {
                escrow_id, route_id, entity_id, destination, amount,
                min_coherence, lock_height: lock_ts, timeout_blocks,
                state: STATE_HOLDING, revert_reason: 0_u8,
                settled_at: 0_u64, reverted_at: 0_u64, locked_by: caller,
            };
            self.escrows.write(escrow_id, rec);
            let count = self.escrow_count.read();
            self.escrow_count.write(count + 1);
            self.emit(EscrowLocked { escrow_id, route_id, entity_id, amount, min_coherence });
        }

        fn release_escrow(
            ref self: ContractState,
            escrow_id: felt252,
            execution_bh: felt252,
            coherence: u64,
        ) {
            let caller = get_caller_address();
            let relayer = self.relayer.read();
            let owner = self.owner.read();
            assert(caller == relayer || caller == owner, 'BTCP: not authorized');

            let mut rec = self.escrows.read(escrow_id);
            assert(rec.amount != 0_u256, 'BTCP: not found');
            assert(rec.state == STATE_HOLDING, 'BTCP: not holding');
            assert(
                get_block_timestamp() <= rec.lock_height + rec.timeout_blocks,
                'BTCP: expired',
            );

            // ── QUORUM-BOUND RELEASE (closes A12) ──
            // The route must have quorum-bound attestations.
            let att = self.route_attestations.read(rec.route_id);
            let quorum = self.quorum_required.read();

            // R1: quorum must be reached
            assert(att.attestation_count >= quorum, 'BTCP: quorum not reached');

            // R2: attestation must be fresh (block_time - attestation_time <= 300s)
            let now = get_block_timestamp();
            assert(now >= att.last_attestation_time, 'BTCP: attestation future');
            let age = now - att.last_attestation_time;
            assert(age <= MAX_ATTESTATION_AGE, 'BTCP: attestation stale');

            // R3: route must not be in dispute state
            assert(!att.disputed, 'BTCP: route disputed');

            // R4: the coherence and execution_bh must match the etched values
            assert(coherence == att.etched_coherence, 'BTCP: coherence mismatch');
            assert(execution_bh == att.etched_execution_bh, 'BTCP: exec_bh mismatch');

            // Coherence floor check (same as v1)
            assert(coherence >= rec.min_coherence, 'BTCP: coherence insufficient');

            rec.state = STATE_RELEASED;
            rec.settled_at = get_block_timestamp();
            self.escrows.write(escrow_id, rec);

            self.emit(EscrowReleased {
                escrow_id, route_id: rec.route_id, execution_bh, coherence,
                settled_at: rec.settled_at, attestation_count: att.attestation_count,
            });
        }

        fn revert_escrow(ref self: ContractState, escrow_id: felt252, reason: u8) {
            let caller = get_caller_address();
            let relayer = self.relayer.read();
            let owner = self.owner.read();

            let mut rec = self.escrows.read(escrow_id);
            assert(rec.amount != 0_u256, 'BTCP: not found');
            assert(rec.state == STATE_HOLDING, 'BTCP: not holding');

            let is_timeout = get_block_timestamp() > rec.lock_height + rec.timeout_blocks;
            if !is_timeout {
                assert(caller == relayer || caller == owner, 'BTCP: not authorized');
                assert(reason != 0_u8, 'BTCP: not timeout');
            };

            rec.state = STATE_REVERTED;
            rec.revert_reason = reason;
            rec.reverted_at = get_block_timestamp();
            self.escrows.write(escrow_id, rec);
            self.emit(EscrowReverted { escrow_id, reason, reverted_at: rec.reverted_at });
        }

        fn get_escrow(self: @ContractState, escrow_id: felt252) -> EscrowRecord {
            self.escrows.read(escrow_id)
        }

        fn get_route_attestation(self: @ContractState, route_id: felt252) -> RouteAttestation {
            self.route_attestations.read(route_id)
        }

        fn is_expired(self: @ContractState, escrow_id: felt252) -> bool {
            let rec = self.escrows.read(escrow_id);
            rec.state == STATE_HOLDING && get_block_timestamp() > rec.lock_height + rec.timeout_blocks
        }

        fn escrow_count(self: @ContractState) -> u64 {
            self.escrow_count.read()
        }

        fn set_relayer(ref self: ContractState, new_relayer: ContractAddress) {
            let caller = get_caller_address();
            assert(caller == self.owner.read(), 'BTCP: not owner');
            let old = self.relayer.read();
            self.relayer.write(new_relayer);
            self.emit(RelayerUpdated { old_relayer: old, new_relayer });
        }
    }
}
