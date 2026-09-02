// SPDX-License-Identifier: MIT
// TRIONLiquidityGuard — Cairo version for Starknet
// NL-score gated swap router guard.

#[starknet::interface]
pub trait ITRIONLiquidityGuard<TContractState> {
    fn check_nl(self: @TContractState, entity_id: felt252) -> (bool, u256);
    fn get_oracle(self: @TContractState) -> starknet::ContractAddress;
}

#[derive(Drop, starknet::Store)]
pub struct NLScoreEntry {
    pub score: u256,
    pub timestamp: u64,
}

#[starknet::contract]
pub mod TRIONLiquidityGuard {
    use starknet::{
        ContractAddress, get_caller_address, get_block_timestamp,
        storage::{Map, StorageMapReadAccess, StorageMapWriteAccess, StoragePointerReadAccess, StoragePointerWriteAccess}
    };
    use core::integer::u256;
    use super::NLScoreEntry;

    const NL_MINIMUM: u256 = u256 { low: 300000000000000000, high: 0 };

    #[storage]
    struct Storage {
        oracle: ContractAddress,
        owner: ContractAddress,
        nl_scores: Map<felt252, NLScoreEntry>,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        NLGuardTriggered: NLGuardTriggered,
        OracleUpdated: OracleUpdated,
    }

    #[derive(Drop, starknet::Event)]
    pub struct NLGuardTriggered {
        #[key]
        pub asset_id: felt252,
        pub nl_score: u256,
        pub timestamp: u64,
    }

    #[derive(Drop, starknet::Event)]
    pub struct OracleUpdated {
        #[key]
        pub new_oracle: ContractAddress,
    }

    #[constructor]
    fn constructor(ref self: ContractState, oracle: ContractAddress) {
        self.oracle.write(oracle);
        self.owner.write(get_caller_address());
    }

    #[abi(embed_v0)]
    impl GuardImpl of super::ITRIONLiquidityGuard<ContractState> {
        fn check_nl(self: @ContractState, entity_id: felt252) -> (bool, u256) {
            let entry = self.nl_scores.read(entity_id);
            if entry.timestamp == 0 {
                return (false, u256 { low: 0, high: 0 });
            }
            let current = get_block_timestamp();
            if current - entry.timestamp > 3600 {
                return (false, u256 { low: 0, high: 0 });
            }
            if entry.score < NL_MINIMUM {
                return (false, entry.score);
            }
            (true, entry.score)
        }

        fn get_oracle(self: @ContractState) -> ContractAddress {
            self.oracle.read()
        }
    }

    #[external(v0)]
    fn set_nl_score(ref self: ContractState, entity_id: felt252, score: u256) {
        assert(get_caller_address() == self.owner.read(), 'Not owner');
        self.nl_scores.write(entity_id, NLScoreEntry { score, timestamp: get_block_timestamp() });
    }

    #[external(v0)]
    fn set_oracle(ref self: ContractState, new_oracle: ContractAddress) {
        assert(get_caller_address() == self.owner.read(), 'Not owner');
        self.oracle.write(new_oracle);
        self.emit(OracleUpdated { new_oracle });
    }
}
