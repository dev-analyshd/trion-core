// SPDX-License-Identifier: CC0-1.0
// TRIONSensingOracle — Cairo version for Starknet
// Publishes BEHAVIORAL_TRUTH signals with privacy guarantee.

#[starknet::interface]
pub trait ITRIONSensingOracle<TContractState> {
    fn is_coherent(self: @TContractState, entity_id: felt252) -> bool;
    fn get_coherence_detail(self: @TContractState, entity_id: felt252) -> (u256, u256, bool, u8, u64, bool);
    fn publish_behavioral_truth(ref self: TContractState, entity_id: felt252,
        public_commitment: felt252, coherence_score: u256, threshold: u256,
        coherent: bool, limiting_plane: u8);
    fn set_relayer(ref self: TContractState, relayer: starknet::ContractAddress, auth: bool);
    fn get_owner(self: @TContractState) -> starknet::ContractAddress;
}

#[derive(Drop, starknet::Store)]
pub struct Signal {
    pub entity_id: felt252,
    pub public_commitment: felt252,
    pub coherence_score: u256,
    pub threshold: u256,
    pub coherent: bool,
    pub limiting_plane: u8,
    pub signal_block: u64,
}

#[starknet::contract]
pub mod TRIONSensingOracle {
    use starknet::{
        ContractAddress, get_caller_address, get_block_info,
        storage::{Map, StorageMapReadAccess, StorageMapWriteAccess, StoragePointerReadAccess, StoragePointerWriteAccess}
    };
    use core::integer::u256;
    use super::Signal;

    const FRESHNESS_BLOCKS: u64 = 300;

    #[storage]
    struct Storage {
        owner: ContractAddress,
        authorized_relayers: Map<ContractAddress, bool>,
        total_signals: u256,
        latest_signal: Map<felt252, Signal>,
        signal_initialized: Map<felt252, bool>,
        signal_count: Map<felt252, u256>,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        BehavioralTruth: BehavioralTruth,
        SilenceSignal: SilenceSignal,
        RelayerSet: RelayerSet,
        OwnershipTransferred: OwnershipTransferred,
    }

    #[derive(Drop, starknet::Event)]
    pub struct BehavioralTruth {
        #[key]
        pub entity_id: felt252,
        pub coherence_score: u256,
        pub threshold: u256,
        pub coherent: bool,
        pub limiting_plane: u8,
        pub block_number: u64,
    }

    #[derive(Drop, starknet::Event)]
    pub struct SilenceSignal {
        #[key]
        pub entity_id: felt252,
        pub coherence_score: u256,
        pub threshold: u256,
        pub limiting_plane: u8,
    }

    #[derive(Drop, starknet::Event)]
    pub struct RelayerSet {
        #[key]
        pub relayer: ContractAddress,
        pub authorized: bool,
    }

    #[derive(Drop, starknet::Event)]
    pub struct OwnershipTransferred {
        #[key]
        pub previous_owner: ContractAddress,
        #[key]
        pub new_owner: ContractAddress,
    }

    #[constructor]
    fn constructor(ref self: ContractState, initial_relayer: ContractAddress) {
        let sender = get_caller_address();
        self.owner.write(sender);
        self.authorized_relayers.write(initial_relayer, true);
        self.total_signals.write(u256 { low: 0, high: 0 });
        self.emit(RelayerSet { relayer: initial_relayer, authorized: true });
    }

    #[abi(embed_v0)]
    impl OracleImpl of super::ITRIONSensingOracle<ContractState> {
        fn is_coherent(self: @ContractState, entity_id: felt252) -> bool {
            if !self.signal_initialized.read(entity_id) {
                return false;
            }
            let s = self.latest_signal.read(entity_id);
            if s.signal_block == 0 {
                return false;
            }
            let current = get_block_info().unbox().block_number;
            if current > s.signal_block + FRESHNESS_BLOCKS {
                return false;
            }
            s.coherent
        }

        fn get_coherence_detail(self: @ContractState, entity_id: felt252) -> (u256, u256, bool, u8, u64, bool) {
            if !self.signal_initialized.read(entity_id) {
                return (u256 { low: 0, high: 0 }, u256 { low: 0, high: 0 }, false, 0, 0, false);
            }
            let s = self.latest_signal.read(entity_id);
            let current = get_block_info().unbox().block_number;
            let fresh = current <= s.signal_block + FRESHNESS_BLOCKS;
            (s.coherence_score, s.threshold, s.coherent, s.limiting_plane, s.signal_block, fresh)
        }

        fn publish_behavioral_truth(ref self: ContractState, entity_id: felt252,
            public_commitment: felt252, coherence_score: u256, threshold: u256,
            coherent: bool, limiting_plane: u8) {
            assert(self.authorized_relayers.read(get_caller_address()), 'Not relayer');
            assert(entity_id != 0, 'Invalid entity');
            assert(public_commitment != 0, 'Invalid commitment');
            assert(limiting_plane <= 4, 'Invalid plane');

            let max_val = u256 { low: 1_000_000, high: 0 };
            assert(coherence_score <= max_val, 'Score out of range');
            assert(threshold <= max_val, 'Threshold out of range');

            let block_info = get_block_info().unbox();

            self.latest_signal.write(entity_id, Signal {
                entity_id, public_commitment, coherence_score,
                threshold, coherent, limiting_plane,
                signal_block: block_info.block_number,
            });
            self.signal_initialized.write(entity_id, true);

            let count = self.signal_count.read(entity_id);
            self.signal_count.write(entity_id, count + u256 { low: 1, high: 0 });

            let total = self.total_signals.read();
            self.total_signals.write(total + u256 { low: 1, high: 0 });

            if coherent {
                self.emit(BehavioralTruth {
                    entity_id, coherence_score, threshold, coherent,
                    limiting_plane, block_number: block_info.block_number,
                });
            } else {
                self.emit(SilenceSignal {
                    entity_id, coherence_score, threshold, limiting_plane,
                });
            }
        }

        fn set_relayer(ref self: ContractState, relayer: ContractAddress, auth: bool) {
            assert(get_caller_address() == self.owner.read(), 'Not owner');
            self.authorized_relayers.write(relayer, auth);
            self.emit(RelayerSet { relayer, authorized: auth });
        }

        fn get_owner(self: @ContractState) -> ContractAddress {
            self.owner.read()
        }
    }
}
