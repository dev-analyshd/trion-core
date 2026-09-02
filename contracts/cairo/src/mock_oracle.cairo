// SPDX-License-Identifier: MIT
// MockOracle — Cairo version for Starknet
// Test mock oracle that always returns safe/coherent.

#[starknet::interface]
pub trait IMockOracle<TContractState> {
    fn is_safe(self: @TContractState, tx_id: felt252) -> bool;
    fn verify_execution(self: @TContractState, tx_id: felt252) -> (bool, u32, u32);
    fn get_nl_score(self: @TContractState, asset: starknet::ContractAddress) -> (u256, u256);
    fn get_mf_score(self: @TContractState, entity: starknet::ContractAddress) -> (u256, u8);
    fn set_always_safe(ref self: TContractState, value: bool);
    fn set_signal(ref self: TContractState, tx_id: felt252, safe: bool, coherence: u32, threshold: u32);
    fn get_owner(self: @TContractState) -> starknet::ContractAddress;
}

#[starknet::contract]
pub mod MockOracle {
    use starknet::{
        ContractAddress, get_caller_address,
        storage::{Map, StorageMapReadAccess, StorageMapWriteAccess}
    };
    use core::integer::u256;

    #[storage]
    struct Storage {
        always_safe: bool,
        owner: ContractAddress,
        signals: Map<felt252, (bool, u32, u32)>,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        SignalUpdated: SignalUpdated,
    }

    #[derive(Drop, starknet::Event)]
    pub struct SignalUpdated {
        #[key]
        pub tx_id: felt252,
        pub safe: bool,
    }

    #[constructor]
    fn constructor(ref self: ContractState) {
        let sender = get_caller_address();
        self.owner.write(sender);
        self.always_safe.write(true);
    }

    #[abi(embed_v0)]
    impl MockOracleImpl of super::IMockOracle<ContractState> {
        fn is_safe(self: @ContractState, tx_id: felt252) -> bool {
            if self.always_safe.read() {
                return true;
            }
            let (safe, _, _) = self.signals.read(tx_id);
            safe
        }

        fn verify_execution(self: @ContractState, tx_id: felt252) -> (bool, u32, u32) {
            if self.always_safe.read() {
                return (true, 800000, 500000);
            }
            self.signals.read(tx_id)
        }

        fn get_nl_score(self: @ContractState, asset: ContractAddress) -> (u256, u256) {
            (u256 { low: 500000, high: 0 }, u256 { low: 300000, high: 0 })
        }

        fn get_mf_score(self: @ContractState, entity: ContractAddress) -> (u256, u8) {
            (u256 { low: 100000, high: 0 }, 0)
        }

        fn set_always_safe(ref self: ContractState, value: bool) {
            assert(get_caller_address() == self.owner.read(), 'Not owner');
            self.always_safe.write(value);
        }

        fn set_signal(ref self: ContractState, tx_id: felt252, safe: bool, coherence: u32, threshold: u32) {
            assert(get_caller_address() == self.owner.read(), 'Not owner');
            self.signals.write(tx_id, (safe, coherence, threshold));
            self.emit(SignalUpdated { tx_id, safe });
        }

        fn get_owner(self: @ContractState) -> ContractAddress {
            self.owner.read()
        }
    }
}
