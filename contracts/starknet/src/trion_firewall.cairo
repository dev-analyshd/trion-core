// SPDX-License-Identifier: CC0-1.0
// TRIONFirewall — Cairo version for Starknet
// Pre-Execution Behavioral Firewall.

#[starknet::interface]
pub trait ITRIONFirewall<TContractState> {
    fn gate(ref self: TContractState, caller: starknet::ContractAddress,
        asset_in: starknet::ContractAddress, amount_in: u256, route_id: felt252) -> bool;
    fn stats(self: @TContractState) -> (u256, u256, u256, u256);
}

#[starknet::contract]
pub mod TRIONFirewall {
    use starknet::{
        ContractAddress,
    };
    use core::integer::u256;

    #[storage]
    struct Storage {
        oracle: ContractAddress,
        protected_protocol: ContractAddress,
        total_approved: u256,
        total_blocked: u256,
        total_value_protected: u256,
        total_attacks_detected: u256,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        FirewallApproved: FirewallApproved,
        FirewallBlocked: FirewallBlocked,
    }

    #[derive(Drop, starknet::Event)]
    pub struct FirewallApproved {
        #[key]
        pub caller: ContractAddress,
        pub amount: u256,
    }

    #[derive(Drop, starknet::Event)]
    pub struct FirewallBlocked {
        #[key]
        pub caller: ContractAddress,
        pub reason: u8,
    }

    #[constructor]
    fn constructor(ref self: ContractState, oracle: ContractAddress, protocol: ContractAddress) {
        self.oracle.write(oracle);
        self.protected_protocol.write(protocol);
        self.total_approved.write(u256 { low: 0, high: 0 });
        self.total_blocked.write(u256 { low: 0, high: 0 });
        self.total_value_protected.write(u256 { low: 0, high: 0 });
        self.total_attacks_detected.write(u256 { low: 0, high: 0 });
    }

    #[abi(embed_v0)]
    impl FirewallImpl of super::ITRIONFirewall<ContractState> {
        fn gate(ref self: ContractState, caller: ContractAddress,
            asset_in: ContractAddress, amount_in: u256, route_id: felt252) -> bool {
            // Simplified: always approve for testing
            // In production: query oracle for NL score, MF score, route verification
            let count = self.total_approved.read();
            self.total_approved.write(count + u256 { low: 1, high: 0 });
            let protected = self.total_value_protected.read();
            self.total_value_protected.write(protected + amount_in);
            self.emit(FirewallApproved { caller, amount: amount_in });
            true
        }

        fn stats(self: @ContractState) -> (u256, u256, u256, u256) {
            (
                self.total_approved.read(),
                self.total_blocked.read(),
                self.total_value_protected.read(),
                self.total_attacks_detected.read(),
            )
        }
    }
}
