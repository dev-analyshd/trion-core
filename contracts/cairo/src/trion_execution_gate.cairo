// SPDX-License-Identifier: MIT
// TRIONExecutionGate — Cairo version for Starknet
// Autonomous Execution Safety Layer.

#[starknet::interface]
pub trait ITRIONExecutionGate<TContractState> {
    fn publish_signal(ref self: TContractState, entity_id: felt252, status: u8,
        phi_t: u32, theta: u32, drop_pct: u32, beo_hash: felt252, da_proof_hash: felt252);
    fn check_execution(ref self: TContractState, entity_id: felt252, caller: starknet::ContractAddress) -> (bool, felt252);
    fn is_execution_safe(self: @TContractState, entity_id: felt252) -> bool;
    fn get_stats(self: @TContractState) -> (u256, u256, u256, u256, u64);
    fn pause(ref self: TContractState);
    fn unpause(ref self: TContractState);
    fn add_validator(ref self: TContractState, validator: starknet::ContractAddress);
    fn get_owner(self: @TContractState) -> starknet::ContractAddress;
}

#[derive(Drop, starknet::Store)]
pub struct BehavioralSignal {
    pub packed_status: u8,
    pub phi_t: u32,
    pub theta: u32,
    pub drop_pct: u32,
    pub beo_hash: felt252,
    pub da_proof_hash: felt252,
    pub initialized: bool,
    pub block_number: u64,
}

#[derive(Drop, starknet::Store)]
pub struct ExecutionDecision {
    pub allowed: bool,
    pub status: u8,
    pub phi_t: u32,
    pub theta: u32,
    pub drop_pct: u32,
    pub checked_at: u64,
}

#[starknet::contract]
pub mod TRIONExecutionGate {
    use starknet::{
        ContractAddress, get_caller_address, get_block_timestamp,
        storage::{Map, StorageMapReadAccess, StorageMapWriteAccess, StoragePointerReadAccess, StoragePointerWriteAccess}
    };
    use core::integer::u256;
    use super::{BehavioralSignal, ExecutionDecision};

    const STATUS_SAFE: u8 = 1;
    const STATUS_ELEVATED: u8 = 2;
    const STATUS_COLLAPSE: u8 = 3;

    #[storage]
    struct Storage {
        owner: ContractAddress,
        is_validator: Map<ContractAddress, bool>,
        paused: bool,
        signals: Map<felt252, BehavioralSignal>,
        decisions: Map<felt252, ExecutionDecision>,
        total_executions_allowed: u256,
        total_executions_blocked: u256,
        total_signals_published: u256,
        total_anomalies_sealed: u256,
        last_storage_sync_block: u64,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        SignalPublished: SignalPublished,
        ExecutionAllowed: ExecutionAllowed,
        ExecutionBlocked: ExecutionBlocked,
        AnomalySealed: AnomalySealed,
        Paused: Paused,
        Unpaused: Unpaused,
        ValidatorAdded: ValidatorAdded,
    }

    #[derive(Drop, starknet::Event)]
    pub struct SignalPublished {
        #[key]
        pub entity_id: felt252,
        pub status: u8,
        pub phi_t: u32,
    }

    #[derive(Drop, starknet::Event)]
    pub struct ExecutionAllowed {
        #[key]
        pub entity_id: felt252,
        #[key]
        pub caller: ContractAddress,
        pub phi_t: u32,
    }

    #[derive(Drop, starknet::Event)]
    pub struct ExecutionBlocked {
        #[key]
        pub entity_id: felt252,
        #[key]
        pub caller: ContractAddress,
        pub reason: u8,
    }

    #[derive(Drop, starknet::Event)]
    pub struct AnomalySealed {
        #[key]
        pub entity_id: felt252,
        pub anomaly_type: u8,
        pub timestamp: u64,
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

    #[derive(Drop, starknet::Event)]
    pub struct ValidatorAdded {
        #[key]
        pub validator: ContractAddress,
    }

    #[constructor]
    fn constructor(ref self: ContractState) {
        let sender = get_caller_address();
        self.owner.write(sender);
        self.is_validator.write(sender, true);
        self.paused.write(false);
        self.total_executions_allowed.write(u256 { low: 0, high: 0 });
        self.total_executions_blocked.write(u256 { low: 0, high: 0 });
        self.total_signals_published.write(u256 { low: 0, high: 0 });
        self.total_anomalies_sealed.write(u256 { low: 0, high: 0 });
        self.emit(ValidatorAdded { validator: sender });
    }

    #[abi(embed_v0)]
    impl GateImpl of super::ITRIONExecutionGate<ContractState> {
        fn publish_signal(ref self: ContractState, entity_id: felt252, status: u8,
            phi_t: u32, theta: u32, drop_pct: u32, beo_hash: felt252, da_proof_hash: felt252) {
            assert(self.is_validator.read(get_caller_address()), 'Not validator');
            assert(!self.paused.read(), 'Paused');
            assert(status >= 1 && status <= 4, 'Invalid status');

            let block_info_num = 0_u64; // Simplified
            self.signals.write(entity_id, BehavioralSignal {
                packed_status: status, phi_t, theta, drop_pct,
                beo_hash, da_proof_hash, initialized: true,
                block_number: block_info_num,
            });

            let count = self.total_signals_published.read();
            self.total_signals_published.write(count + u256 { low: 1, high: 0 });

            if status >= STATUS_COLLAPSE {
                let anomalies = self.total_anomalies_sealed.read();
                self.total_anomalies_sealed.write(anomalies + u256 { low: 1, high: 0 });
                self.emit(AnomalySealed {
                    entity_id, anomaly_type: status,
                    timestamp: get_block_timestamp(),
                });
            }

            self.emit(SignalPublished { entity_id, status, phi_t });
        }

        fn check_execution(ref self: ContractState, entity_id: felt252, caller: ContractAddress) -> (bool, felt252) {
            assert(!self.paused.read(), 'Paused');
            let ts = get_block_timestamp();

            // Fail-closed for uninitialized entities
            let sig = self.signals.read(entity_id);
            if !sig.initialized {
                let decision_hash = entity_id;
                self.decisions.write(decision_hash, ExecutionDecision {
                    allowed: false, status: 0, phi_t: 0, theta: 0, drop_pct: 0, checked_at: ts,
                });
                let blocked = self.total_executions_blocked.read();
                self.total_executions_blocked.write(blocked + u256 { low: 1, high: 0 });
                self.emit(ExecutionBlocked { entity_id, caller, reason: 0 });
                return (false, decision_hash);
            }

            let allowed = sig.packed_status <= STATUS_ELEVATED;
            let decision_hash = entity_id;

            self.decisions.write(decision_hash, ExecutionDecision {
                allowed, status: sig.packed_status, phi_t: sig.phi_t,
                theta: sig.theta, drop_pct: sig.drop_pct, checked_at: ts,
            });

            if allowed {
                let count = self.total_executions_allowed.read();
                self.total_executions_allowed.write(count + u256 { low: 1, high: 0 });
                self.emit(ExecutionAllowed { entity_id, caller, phi_t: sig.phi_t });
            } else {
                let count = self.total_executions_blocked.read();
                self.total_executions_blocked.write(count + u256 { low: 1, high: 0 });
                self.emit(ExecutionBlocked { entity_id, caller, reason: sig.packed_status });
            }

            (allowed, decision_hash)
        }

        fn is_execution_safe(self: @ContractState, entity_id: felt252) -> bool {
            let sig = self.signals.read(entity_id);
            if !sig.initialized { return false; }
            sig.packed_status <= STATUS_ELEVATED
        }

        fn get_stats(self: @ContractState) -> (u256, u256, u256, u256, u64) {
            (
                self.total_executions_allowed.read(),
                self.total_executions_blocked.read(),
                self.total_signals_published.read(),
                self.total_anomalies_sealed.read(),
                self.last_storage_sync_block.read(),
            )
        }

        fn pause(ref self: ContractState) {
            assert(get_caller_address() == self.owner.read(), 'Not owner');
            self.paused.write(true);
            self.emit(Paused { by: get_caller_address() });
        }

        fn unpause(ref self: ContractState) {
            assert(get_caller_address() == self.owner.read(), 'Not owner');
            self.paused.write(false);
            self.emit(Unpaused { by: get_caller_address() });
        }

        fn add_validator(ref self: ContractState, validator: ContractAddress) {
            assert(get_caller_address() == self.owner.read(), 'Not owner');
            self.is_validator.write(validator, true);
            self.emit(ValidatorAdded { validator });
        }

        fn get_owner(self: @ContractState) -> ContractAddress {
            self.owner.read()
        }
    }
}
