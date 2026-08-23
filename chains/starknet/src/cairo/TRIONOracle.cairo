/// TRION Protocol — Akashic Oracle
/// Starknet Sepolia Contract
///
/// Stores BEO behavioral scores on-chain. Any dApp on Starknet can call
/// get_score(beo_id) to read an entity's ANIMA score, genesis confidence,
/// trajectory alert level, and archetype cluster.
///
/// Owner (TRION oracle bridge) is the only address that can push score updates.
/// All reads are public and free.

#[starknet::interface]
pub trait ITRIONOracle<TContractState> {
    fn update_score(
        ref self: TContractState,
        beo_id: felt252,
        anima_score: u64,
        genesis_confidence: u64,
        trajectory_alert: u8,
        archetype_id: u8,
        akashic_depth: u64,
        is_resurrection: bool,
        dormancy_type: felt252,
    );
    fn get_score(self: @TContractState, beo_id: felt252) -> BEOScore;
    fn get_owner(self: @TContractState) -> starknet::ContractAddress;
    fn transfer_ownership(ref self: TContractState, new_owner: starknet::ContractAddress);
    fn get_score_count(self: @TContractState) -> u64;
    fn get_last_updated(self: @TContractState, beo_id: felt252) -> u64;
}

#[derive(Drop, Serde, Copy, starknet::Store)]
pub struct BEOScore {
    /// ANIMA score: PCR x HA x CA, scaled 0–10000 (2 decimal places)
    pub anima_score: u64,
    /// Genesis confidence: 1-e^(-λD), scaled 0–10000
    pub genesis_confidence: u64,
    /// 0 = CLEAR, 1 = WARN (KL>0.15), 2 = MANIPULATION (KL>0.35)
    pub trajectory_alert: u8,
    /// FAISS archetype cluster 0–63
    pub archetype_id: u8,
    /// Akashic depth D(t), scaled integer
    pub akashic_depth: u64,
    /// True if entity classified as GENUINE_CONTINUATION resurrection
    pub is_resurrection: bool,
    /// Dormancy type: short felt252 of 'ACTIVE','ABANDONED','HIBERNATION',etc.
    pub dormancy_type: felt252,
    /// Block timestamp of last update
    pub last_updated: u64,
    /// Sequential update count for this BEO
    pub update_count: u64,
}

#[starknet::contract]
pub mod TRIONOracle {
    use super::{BEOScore, ITRIONOracle};
    use starknet::{
        ContractAddress, get_caller_address, get_block_timestamp,
        storage::{Map, StorageMapReadAccess, StorageMapWriteAccess, StoragePointerReadAccess, StoragePointerWriteAccess}
    };

    #[storage]
    struct Storage {
        owner: ContractAddress,
        scores: Map<felt252, BEOScore>,
        score_count: u64,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        ScoreUpdated: ScoreUpdated,
        OwnershipTransferred: OwnershipTransferred,
    }

    #[derive(Drop, starknet::Event)]
    pub struct ScoreUpdated {
        #[key]
        pub beo_id: felt252,
        pub anima_score: u64,
        pub trajectory_alert: u8,
        pub archetype_id: u8,
        pub timestamp: u64,
    }

    #[derive(Drop, starknet::Event)]
    pub struct OwnershipTransferred {
        pub previous_owner: ContractAddress,
        pub new_owner: ContractAddress,
    }

    #[constructor]
    fn constructor(ref self: ContractState, owner: ContractAddress) {
        self.owner.write(owner);
        self.score_count.write(0);
    }

    #[abi(embed_v0)]
    impl TRIONOracleImpl of ITRIONOracle<ContractState> {
        fn update_score(
            ref self: ContractState,
            beo_id: felt252,
            anima_score: u64,
            genesis_confidence: u64,
            trajectory_alert: u8,
            archetype_id: u8,
            akashic_depth: u64,
            is_resurrection: bool,
            dormancy_type: felt252,
        ) {
            let caller = get_caller_address();
            assert(caller == self.owner.read(), 'TRION: unauthorized');
            assert(anima_score <= 10000_u64, 'TRION: anima out of range');
            assert(genesis_confidence <= 10000_u64, 'TRION: gc out of range');
            assert(trajectory_alert <= 2_u8, 'TRION: alert level invalid');
            assert(archetype_id <= 63_u8, 'TRION: archetype out of range');

            let ts = get_block_timestamp();
            let existing = self.scores.read(beo_id);
            let new_count = existing.update_count + 1;

            let score = BEOScore {
                anima_score,
                genesis_confidence,
                trajectory_alert,
                archetype_id,
                akashic_depth,
                is_resurrection,
                dormancy_type,
                last_updated: ts,
                update_count: new_count,
            };

            if existing.update_count == 0 {
                let current = self.score_count.read();
                self.score_count.write(current + 1);
            }

            self.scores.write(beo_id, score);

            self.emit(ScoreUpdated {
                beo_id,
                anima_score,
                trajectory_alert,
                archetype_id,
                timestamp: ts,
            });
        }

        fn get_score(self: @ContractState, beo_id: felt252) -> BEOScore {
            self.scores.read(beo_id)
        }

        fn get_owner(self: @ContractState) -> ContractAddress {
            self.owner.read()
        }

        fn transfer_ownership(ref self: ContractState, new_owner: ContractAddress) {
            let caller = get_caller_address();
            assert(caller == self.owner.read(), 'TRION: unauthorized');
            let old_owner = self.owner.read();
            self.owner.write(new_owner);
            self.emit(OwnershipTransferred { previous_owner: old_owner, new_owner });
        }

        fn get_score_count(self: @ContractState) -> u64 {
            self.score_count.read()
        }

        fn get_last_updated(self: @ContractState, beo_id: felt252) -> u64 {
            self.scores.read(beo_id).last_updated
        }
    }
}
