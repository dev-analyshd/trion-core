// SPDX-License-Identifier: MIT
// TRIONPriceFeed — Cairo version for Starknet
// Chainlink-compatible behavioral price feed.

#[starknet::interface]
pub trait ITRIONPriceFeed<TContractState> {
    fn decimals(self: @TContractState) -> u8;
    fn version(self: @TContractState) -> u256;
    fn latest_answer(self: @TContractState) -> u64;
    fn latest_round_data(self: @TContractState) -> (u64, u64, u64, u64);
    fn update_price(ref self: TContractState, forward_price: u64,
        coherence_score: u64, mf_score: u64, manipulated: bool);
    fn is_manipulated(self: @TContractState) -> bool;
    fn set_relayer(ref self: TContractState, new_relayer: starknet::ContractAddress);
    fn get_owner(self: @TContractState) -> starknet::ContractAddress;
}

#[derive(Drop, starknet::Store)]
pub struct Round {
    pub answer: u64,
    pub updated_at: u64,
    pub coherence: u64,
    pub mf_score: u64,
    pub manipulated: bool,
}

#[starknet::contract]
pub mod TRIONPriceFeed {
    use starknet::{
        ContractAddress, get_caller_address, get_block_timestamp,
        storage::{Map, StorageMapReadAccess, StorageMapWriteAccess, StoragePointerReadAccess, StoragePointerWriteAccess}
    };
    use core::integer::u256;
    use super::Round;

    const PRICE_DECIMALS: u8 = 8;

    #[storage]
    struct Storage {
        owner: ContractAddress,
        relayer: ContractAddress,
        latest_round_id: u64,
        rounds: Map<felt252, Round>,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        PriceUpdated: PriceUpdated,
        ManipulationWarning: ManipulationWarning,
        RelayerUpdated: RelayerUpdated,
    }

    #[derive(Drop, starknet::Event)]
    pub struct PriceUpdated {
        #[key]
        pub round_id: u64,
        pub answer: u64,
        pub manipulated: bool,
    }

    #[derive(Drop, starknet::Event)]
    pub struct ManipulationWarning {
        #[key]
        pub round_id: u64,
        pub mf_score: u64,
    }

    #[derive(Drop, starknet::Event)]
    pub struct RelayerUpdated {
        #[key]
        pub new_relayer: ContractAddress,
    }

    #[constructor]
    fn constructor(ref self: ContractState, relayer: ContractAddress) {
        let sender = get_caller_address();
        self.owner.write(sender);
        self.relayer.write(relayer);
        self.latest_round_id.write(0);
    }

    fn _round_id_to_felt(round_id: u64) -> felt252 {
        round_id.into()
    }

    #[abi(embed_v0)]
    impl FeedImpl of super::ITRIONPriceFeed<ContractState> {
        fn decimals(self: @ContractState) -> u8 { PRICE_DECIMALS }
        fn version(self: @ContractState) -> u256 { u256 { low: 1, high: 0 } }

        fn latest_answer(self: @ContractState) -> u64 {
            let round_id = self.latest_round_id.read();
            assert(round_id > 0, 'No price data');
            self.rounds.read(_round_id_to_felt(round_id)).answer
        }

        fn latest_round_data(self: @ContractState) -> (u64, u64, u64, u64) {
            let round_id = self.latest_round_id.read();
            assert(round_id > 0, 'No price data');
            let r = self.rounds.read(_round_id_to_felt(round_id));
            (round_id, r.answer, r.updated_at, r.updated_at)
        }

        fn update_price(ref self: ContractState, forward_price: u64,
            coherence_score: u64, mf_score: u64, manipulated: bool) {
            let caller = get_caller_address();
            assert(caller == self.relayer.read() || caller == self.owner.read(), 'Not relayer');
            assert(forward_price > 0_u64, 'Price must be positive');

            let round_id = self.latest_round_id.read() + 1;
            self.latest_round_id.write(round_id);

            let ts = get_block_timestamp();
            self.rounds.write(_round_id_to_felt(round_id), Round {
                answer: forward_price, updated_at: ts,
                coherence: coherence_score, mf_score, manipulated,
            });

            if manipulated {
                self.emit(ManipulationWarning { round_id, mf_score });
            }
            self.emit(PriceUpdated { round_id, answer: forward_price, manipulated });
        }

        fn is_manipulated(self: @ContractState) -> bool {
            let round_id = self.latest_round_id.read();
            if round_id == 0 { return false; }
            self.rounds.read(_round_id_to_felt(round_id)).manipulated
        }

        fn set_relayer(ref self: ContractState, new_relayer: ContractAddress) {
            assert(get_caller_address() == self.owner.read(), 'Not owner');
            self.relayer.write(new_relayer);
            self.emit(RelayerUpdated { new_relayer });
        }

        fn get_owner(self: @ContractState) -> ContractAddress { self.owner.read() }
    }
}
