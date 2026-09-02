// SPDX-License-Identifier: MIT
// MockTRIONToken — Cairo version for Starknet
// Simple ERC-20 style test token for Zero-Bridge testing.

#[starknet::interface]
pub trait IMockTRIONToken<TContractState> {
    fn get_name(self: @TContractState) -> ByteArray;
    fn get_symbol(self: @TContractState) -> ByteArray;
    fn get_decimals(self: @TContractState) -> u8;
    fn get_total_supply(self: @TContractState) -> u256;
    fn get_balance(self: @TContractState, account: starknet::ContractAddress) -> u256;
    fn transfer(ref self: TContractState, recipient: starknet::ContractAddress, amount: u256) -> bool;
    fn approve(ref self: TContractState, spender: starknet::ContractAddress, amount: u256) -> bool;
    fn transfer_from(ref self: TContractState, sender: starknet::ContractAddress, recipient: starknet::ContractAddress, amount: u256) -> bool;
    fn mint(ref self: TContractState, to: starknet::ContractAddress, amount: u256);
    fn burn(ref self: TContractState, from: starknet::ContractAddress, amount: u256);
    fn get_owner(self: @TContractState) -> starknet::ContractAddress;
}

#[starknet::contract]
pub mod MockTRIONToken {
    use starknet::{
        ContractAddress, get_caller_address,
        storage::{Map, StorageMapReadAccess, StorageMapWriteAccess}
    };
    use core::integer::u256;

    #[storage]
    struct Storage {
        name: ByteArray,
        symbol: ByteArray,
        decimals: u8,
        total_supply: u256,
        balance_of: Map<ContractAddress, u256>,
        allowance: Map<(ContractAddress, ContractAddress), u256>,
        owner: ContractAddress,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        Transfer: Transfer,
        Approval: Approval,
    }

    #[derive(Drop, starknet::Event)]
    pub struct Transfer {
        #[key]
        pub from: ContractAddress,
        #[key]
        pub to: ContractAddress,
        pub value: u256,
    }

    #[derive(Drop, starknet::Event)]
    pub struct Approval {
        #[key]
        pub owner: ContractAddress,
        #[key]
        pub spender: ContractAddress,
        pub value: u256,
    }

    #[constructor]
    fn constructor(ref self: ContractState, initial_supply: u256) {
        let sender = get_caller_address();
        self.name.write("Mock TRION Token");
        self.symbol.write("MTRION");
        self.decimals.write(18);
        self.total_supply.write(initial_supply);
        self.balance_of.write(sender, initial_supply);
        self.owner.write(sender);
        self.emit(Transfer {
            from: starknet::contract_address_const::<0>(),
            to: sender,
            value: initial_supply,
        });
    }

    #[abi(embed_v0)]
    impl TokenImpl of super::IMockTRIONToken<ContractState> {
        fn get_name(self: @ContractState) -> ByteArray { self.name.read() }
        fn get_symbol(self: @ContractState) -> ByteArray { self.symbol.read() }
        fn get_decimals(self: @ContractState) -> u8 { self.decimals.read() }
        fn get_total_supply(self: @ContractState) -> u256 { self.total_supply.read() }
        fn get_balance(self: @ContractState, account: ContractAddress) -> u256 {
            self.balance_of.read(account)
        }

        fn transfer(ref self: ContractState, recipient: ContractAddress, amount: u256) -> bool {
            let sender = get_caller_address();
            let balance = self.balance_of.read(sender);
            assert(balance >= amount, 'Insufficient balance');
            self.balance_of.write(sender, balance - amount);
            let recipient_balance = self.balance_of.read(recipient);
            self.balance_of.write(recipient, recipient_balance + amount);
            self.emit(Transfer { from: sender, to: recipient, value: amount });
            true
        }

        fn approve(ref self: ContractState, spender: ContractAddress, amount: u256) -> bool {
            let owner = get_caller_address();
            self.allowance.write((owner, spender), amount);
            self.emit(Approval { owner, spender, value: amount });
            true
        }

        fn transfer_from(ref self: ContractState, sender: ContractAddress, recipient: ContractAddress, amount: u256) -> bool {
            let caller = get_caller_address();
            let allowed = self.allowance.read((sender, caller));
            assert(allowed >= amount, 'Allowance exceeded');
            let balance = self.balance_of.read(sender);
            assert(balance >= amount, 'Insufficient balance');
            self.allowance.write((sender, caller), allowed - amount);
            self.balance_of.write(sender, balance - amount);
            let recipient_balance = self.balance_of.read(recipient);
            self.balance_of.write(recipient, recipient_balance + amount);
            self.emit(Transfer { from: sender, to: recipient, value: amount });
            true
        }

        fn mint(ref self: ContractState, to: ContractAddress, amount: u256) {
            assert(get_caller_address() == self.owner.read(), 'Not owner');
            let current = self.balance_of.read(to);
            self.balance_of.write(to, current + amount);
            let supply = self.total_supply.read();
            self.total_supply.write(supply + amount);
            self.emit(Transfer {
                from: starknet::contract_address_const::<0>(),
                to, value: amount,
            });
        }

        fn burn(ref self: ContractState, from: ContractAddress, amount: u256) {
            assert(get_caller_address() == self.owner.read(), 'Not owner');
            let balance = self.balance_of.read(from);
            assert(balance >= amount, 'Insufficient balance');
            self.balance_of.write(from, balance - amount);
            let supply = self.total_supply.read();
            self.total_supply.write(supply - amount);
            self.emit(Transfer {
                from,
                to: starknet::contract_address_const::<0>(),
                value: amount,
            });
        }

        fn get_owner(self: @ContractState) -> ContractAddress { self.owner.read() }
    }
}
