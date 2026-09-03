// SPDX-License-Identifier: MIT
// ReentrantAttacker — Cairo version for Starknet
// Test contract for verifying reentrancy protection.

#[starknet::interface]
pub trait IReentrantAttacker<TContractState> {
    fn initiate_attack(ref self: TContractState);
    fn get_attack_count(self: @TContractState) -> u256;
    fn set_target(ref self: TContractState, target: starknet::ContractAddress);
}

#[starknet::contract]
pub mod ReentrantAttacker {
    use starknet::{
        ContractAddress, get_caller_address,
    };
    use core::integer::u256;

    #[storage]
    struct Storage {
        target: ContractAddress,
        attack_count: u256,
        max_attacks: u256,
        owner: ContractAddress,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        AttackAttempted: AttackAttempted,
    }

    #[derive(Drop, starknet::Event)]
    pub struct AttackAttempted {
        pub attempt: u256,
        pub success: bool,
    }

    #[constructor]
    fn constructor(ref self: ContractState, target: ContractAddress) {
        let sender = get_caller_address();
        self.target.write(target);
        self.attack_count.write(u256 { low: 0, high: 0 });
        self.max_attacks.write(u256 { low: 3, high: 0 });
        self.owner.write(sender);
    }

    #[abi(embed_v0)]
    impl AttackerImpl of super::IReentrantAttacker<ContractState> {
        fn initiate_attack(ref self: ContractState) {
            assert(get_caller_address() == self.owner.read(), 'Not owner');
            self.attack_count.write(u256 { low: 0, high: 0 });
            self.emit(AttackAttempted { attempt: u256 { low: 1, high: 0 }, success: false });
        }

        fn get_attack_count(self: @ContractState) -> u256 {
            self.attack_count.read()
        }

        fn set_target(ref self: ContractState, target: ContractAddress) {
            assert(get_caller_address() == self.owner.read(), 'Not owner');
            self.target.write(target);
        }
    }
}
