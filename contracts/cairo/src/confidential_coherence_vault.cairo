// SPDX-License-Identifier: MIT
// ConfidentialCoherenceVault — Cairo version for Starknet
// ERC-20 vault gated by TRION behavioral coherence.

#[starknet::interface]
pub trait IConfidentialCoherenceVault<TContractState> {
    fn coherence_wrap(ref self: TContractState, amount: u256, entity_id: felt252);
    fn coherence_unwrap(ref self: TContractState, amount: u256, entity_id: felt252);
    fn get_balance(self: @TContractState, user: starknet::ContractAddress) -> u256;
    fn get_total_deposited(self: @TContractState) -> u256;
    fn set_oracle(ref self: TContractState, new_oracle: starknet::ContractAddress);
}

#[starknet::contract]
pub mod ConfidentialCoherenceVault {
    use starknet::{
        ContractAddress, get_caller_address,
        storage::{Map, StorageMapReadAccess, StorageMapWriteAccess, StoragePointerReadAccess, StoragePointerWriteAccess}
    };
    use core::integer::u256;

    #[storage]
    struct Storage {
        underlying_token: ContractAddress,
        trion_oracle: ContractAddress,
        balance_of: Map<ContractAddress, u256>,
        total_deposited: u256,
        owner: ContractAddress,
        coherence_cache: Map<felt252, bool>,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        CoherenceGatedWrap: CoherenceGatedWrap,
        CoherenceGatedUnwrap: CoherenceGatedUnwrap,
        OracleUpdated: OracleUpdated,
    }

    #[derive(Drop, starknet::Event)]
    pub struct CoherenceGatedWrap {
        #[key]
        pub entity_id: felt252,
        #[key]
        pub user: ContractAddress,
        pub amount: u256,
    }

    #[derive(Drop, starknet::Event)]
    pub struct CoherenceGatedUnwrap {
        #[key]
        pub entity_id: felt252,
        #[key]
        pub user: ContractAddress,
        pub amount: u256,
    }

    #[derive(Drop, starknet::Event)]
    pub struct OracleUpdated {
        #[key]
        pub new_oracle: ContractAddress,
    }

    #[constructor]
    fn constructor(ref self: ContractState, underlying: ContractAddress, oracle: ContractAddress) {
        let sender = get_caller_address();
        self.underlying_token.write(underlying);
        self.trion_oracle.write(oracle);
        self.owner.write(sender);
        self.total_deposited.write(u256 { low: 0, high: 0 });
    }

    #[abi(embed_v0)]
    impl VaultImpl of super::IConfidentialCoherenceVault<ContractState> {
        fn coherence_wrap(ref self: ContractState, amount: u256, entity_id: felt252) {
            // Coherence gate: entity must be coherent
            // Simplified: check coherence cache
            let is_coherent = self.coherence_cache.read(entity_id);
            assert(is_coherent, 'Coherence gate failed');

            let caller = get_caller_address();
            let current = self.balance_of.read(caller);
            self.balance_of.write(caller, current + amount);
            let total = self.total_deposited.read();
            self.total_deposited.write(total + amount);
            self.emit(CoherenceGatedWrap { entity_id, user: caller, amount });
        }

        fn coherence_unwrap(ref self: ContractState, amount: u256, entity_id: felt252) {
            let is_coherent = self.coherence_cache.read(entity_id);
            assert(is_coherent, 'Coherence gate failed');

            let caller = get_caller_address();
            let balance = self.balance_of.read(caller);
            assert(balance >= amount, 'Insufficient balance');

            self.balance_of.write(caller, balance - amount);
            let total = self.total_deposited.read();
            self.total_deposited.write(total - amount);
            self.emit(CoherenceGatedUnwrap { entity_id, user: caller, amount });
        }

        fn get_balance(self: @ContractState, user: ContractAddress) -> u256 {
            self.balance_of.read(user)
        }

        fn get_total_deposited(self: @ContractState) -> u256 {
            self.total_deposited.read()
        }

        fn set_oracle(ref self: ContractState, new_oracle: ContractAddress) {
            assert(get_caller_address() == self.owner.read(), 'Not owner');
            assert(new_oracle != starknet::contract_address_const::<0>(), 'Zero address');
            self.trion_oracle.write(new_oracle);
            self.emit(OracleUpdated { new_oracle });
        }
    }

    #[external(v0)]
    fn set_coherence_cache(ref self: ContractState, entity_id: felt252, is_coherent: bool) {
        assert(get_caller_address() == self.owner.read(), 'Not owner');
        self.coherence_cache.write(entity_id, is_coherent);
    }
}
