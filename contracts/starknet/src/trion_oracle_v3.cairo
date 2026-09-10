// SPDX-License-Identifier: MIT
// TRIONOracleV3 — Cairo version for Starknet
// Behavioral truth oracle with BTCP route registry.

#[starknet::interface]
pub trait ITRIONOracleV3<TContractState> {
    fn publish_btcp_route(ref self: TContractState, route_id: felt252, anchor_bh: felt252,
        execution_bh: felt252, coherence_score: u256, threshold_score: u256);
    fn verify_execution(self: @TContractState, tx_id: felt252) -> (bool, u32, u32);
    fn get_signal_info(self: @TContractState, tx_id: felt252) -> (u8, u32, u32, u64, u64);
    fn add_validator(ref self: TContractState, validator: starknet::ContractAddress);
    fn set_quorum(ref self: TContractState, new_quorum: u256);
    fn transfer_ownership(ref self: TContractState, new_owner: starknet::ContractAddress);
    fn get_owner(self: @TContractState) -> starknet::ContractAddress;
    fn get_quorum_required(self: @TContractState) -> u256;
    fn is_validator(self: @TContractState, addr: starknet::ContractAddress) -> bool;
    fn get_btcp_route(self: @TContractState, route_id: felt252) -> (felt252, felt252, u256, u256, bool, u64, bool);
}

#[derive(Drop, starknet::Store)]
pub struct LegacySignal {
    pub status: u8,
    pub coherence: u32,
    pub threshold: u32,
    pub block_num: u64,
    pub timestamp: u64,
    pub initialized: bool,
}

#[derive(Drop, starknet::Store)]
pub struct BTCPRoute {
    pub anchor_bh: felt252,
    pub execution_bh: felt252,
    pub coherence: u256,
    pub threshold: u256,
    pub is_safe: bool,
    pub timestamp: u64,
}

#[starknet::contract]
pub mod TRIONOracleV3 {
    use starknet::{
        ContractAddress, get_caller_address, get_block_timestamp, get_block_info,
        storage::{Map, StorageMapReadAccess, StorageMapWriteAccess}
    };
    use core::integer::u256;
    use super::BTCPRoute;

    #[storage]
    struct Storage {
        signals: Map<felt252, super::LegacySignal>,
        is_validator: Map<ContractAddress, bool>,
        quorum_required: u256,
        owner: ContractAddress,
        btcp_routes: Map<felt252, BTCPRoute>,
        btcp_routes_initialized: Map<felt252, bool>,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        BTCPRoutePublished: BTCPRoutePublished,
        ThermodynamicSignalEtched: ThermodynamicSignalEtched,
        ValidatorAdded: ValidatorAdded,
        OwnershipTransferred: OwnershipTransferred,
    }

    #[derive(Drop, starknet::Event)]
    pub struct BTCPRoutePublished {
        #[key]
        pub route_id: felt252,
        pub is_safe: bool,
    }

    #[derive(Drop, starknet::Event)]
    pub struct ThermodynamicSignalEtched {
        #[key]
        pub tx_id: felt252,
        pub status: u8,
        pub coherence: u32,
        pub threshold: u32,
    }

    #[derive(Drop, starknet::Event)]
    pub struct ValidatorAdded {
        #[key]
        pub validator: ContractAddress,
    }

    #[derive(Drop, starknet::Event)]
    pub struct OwnershipTransferred {
        #[key]
        pub previous_owner: ContractAddress,
        #[key]
        pub new_owner: ContractAddress,
    }

    const MAX_QUORUM: u256 = u256 { low: 100, high: 0 };

    #[constructor]
    fn constructor(ref self: ContractState) {
        let sender = get_caller_address();
        self.owner.write(sender);
        self.is_validator.write(sender, true);
        self.quorum_required.write(u256 { low: 2, high: 0 });
        self.emit(OwnershipTransferred {
            previous_owner: starknet::contract_address_const::<0>(),
            new_owner: sender,
        });
        self.emit(ValidatorAdded { validator: sender });
    }

    fn _u256_to_u32_saturating(value: u256) -> u32 {
        let max_u32 = u256 { low: 0xFFFFFFFF, high: 0 };
        if value > max_u32 {
            0xFFFFFFFF_u32
        } else {
            value.low.try_into().unwrap()
        }
    }

    #[abi(embed_v0)]
    impl OracleImpl of super::ITRIONOracleV3<ContractState> {
        fn publish_btcp_route(ref self: ContractState, route_id: felt252, anchor_bh: felt252,
            execution_bh: felt252, coherence_score: u256, threshold_score: u256) {
            let caller = get_caller_address();
            assert(caller == self.owner.read() || self.is_validator.read(caller), 'TRION: not authorized');

            let is_safe = coherence_score >= threshold_score;
            let timestamp = get_block_timestamp();

            self.btcp_routes.write(route_id, BTCPRoute {
                anchor_bh, execution_bh, coherence: coherence_score,
                threshold: threshold_score, is_safe, timestamp,
            });
            self.btcp_routes_initialized.write(route_id, true);
            self.emit(BTCPRoutePublished { route_id, is_safe });
        }

        fn verify_execution(self: @ContractState, tx_id: felt252) -> (bool, u32, u32) {
            if self.btcp_routes_initialized.read(tx_id) {
                let route = self.btcp_routes.read(tx_id);
                if route.timestamp > 0 {
                    let c = _u256_to_u32_saturating(route.coherence);
                    let t = _u256_to_u32_saturating(route.threshold);
                    return (route.is_safe, c, t);
                }
            }

            let signal = self.signals.read(tx_id);
            if !signal.initialized { return (false, 0, 0); }

            let safe = signal.status == 1;
            let current_block = get_block_info().unbox().block_number;
            let current_ts = get_block_timestamp();
            let recent = current_ts - signal.timestamp < 300;
            let bounded = current_block - signal.block_num < 50;

            (safe & recent & bounded, signal.coherence, signal.threshold)
        }

        fn get_signal_info(self: @ContractState, tx_id: felt252) -> (u8, u32, u32, u64, u64) {
            let s = self.signals.read(tx_id);
            (s.status, s.coherence, s.threshold, s.block_num, s.timestamp)
        }

        fn add_validator(ref self: ContractState, validator: ContractAddress) {
            assert(get_caller_address() == self.owner.read(), 'TRION: not owner');
            self.is_validator.write(validator, true);
            self.emit(ValidatorAdded { validator });
        }

        fn set_quorum(ref self: ContractState, new_quorum: u256) {
            assert(get_caller_address() == self.owner.read(), 'TRION: not owner');
            assert(new_quorum >= u256 { low: 1, high: 0 }, 'TRION: quorum >= 1');
            assert(new_quorum <= MAX_QUORUM, 'TRION: quorum too high');
            self.quorum_required.write(new_quorum);
        }

        fn transfer_ownership(ref self: ContractState, new_owner: ContractAddress) {
            assert(get_caller_address() == self.owner.read(), 'TRION: not owner');
            assert(new_owner != starknet::contract_address_const::<0>(), 'TRION: zero address');
            let previous = self.owner.read();
            self.owner.write(new_owner);
            self.emit(OwnershipTransferred { previous_owner: previous, new_owner });
        }

        fn get_owner(self: @ContractState) -> ContractAddress { self.owner.read() }
        fn get_quorum_required(self: @ContractState) -> u256 { self.quorum_required.read() }
        fn is_validator(self: @ContractState, addr: ContractAddress) -> bool { self.is_validator.read(addr) }

        fn get_btcp_route(self: @ContractState, route_id: felt252) -> (felt252, felt252, u256, u256, bool, u64, bool) {
            if !self.btcp_routes_initialized.read(route_id) {
                return (0, 0,
                    u256 { low: 0, high: 0 }, u256 { low: 0, high: 0 }, false, 0, false);
            }
            let r = self.btcp_routes.read(route_id);
            (r.anchor_bh, r.execution_bh, r.coherence, r.threshold, r.is_safe, r.timestamp, true)
        }
    }
}
