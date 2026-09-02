/// TRION Protocol — LiquidityOcean (Starknet)
/// ===========================================
/// Mirrors contracts/solidity/LiquidityOcean.sol on Starknet.
/// Aggregates Natural Liquidity (NL) scores across all integrated chains
/// to compute a global Liquidity Ocean score for BTCP routing decisions.
///
/// Whitepaper BTCP §6 — The Liquidity Ocean:
///   L_ocean = Σ(NL_k × W_k × availability) / Σ W_k

#[starknet::interface]
pub trait ILiquidityOcean<TContractState> {
    fn register_chain(ref self: TContractState, chain_id: u64, weight: u128);
    fn update_nl_score(ref self: TContractState, chain_id: u64, nl_score: u128, tvl: u128);
    fn recompute_ocean(ref self: TContractState);
    fn get_best_chain(self: @TContractState) -> (u64, u128);
    fn get_ocean_score(self: @TContractState) -> u128;
    fn get_routing_threshold(self: @TContractState) -> u128;
    fn set_routing_threshold(ref self: TContractState, threshold: u128);
    fn get_chain_count(self: @TContractState) -> u64;
    fn get_chain(self: @TContractState, chain_id: u64) -> ChainLiquidity;
    fn get_chain_at_index(self: @TContractState, index: u64) -> u64;
    fn get_owner(self: @TContractState) -> starknet::ContractAddress;
    fn get_relayer(self: @TContractState) -> starknet::ContractAddress;
    fn set_relayer(ref self: TContractState, new_relayer: starknet::ContractAddress);
    fn transfer_ownership(ref self: TContractState, new_owner: starknet::ContractAddress);
}

#[derive(Drop, Serde, Copy, starknet::Store)]
pub struct ChainLiquidity {
    pub chain_id: u64,
    pub nl_score: u128,
    pub weight: u128,
    pub tvl: u128,
    pub last_updated: u64,
    pub active: bool,
}

#[starknet::contract]
pub mod LiquidityOcean {
    use super::{ChainLiquidity, ILiquidityOcean};
    use starknet::{
        ContractAddress, get_caller_address, get_block_timestamp,
        storage::{Map, StorageMapReadAccess, StorageMapWriteAccess,
                  StoragePointerReadAccess, StoragePointerWriteAccess},
    };

    const DEFAULT_ROUTING_THRESHOLD: u128 = 300_000_u128;
    const SCALE: u128 = 1_000_000_u128;

    #[storage]
    struct Storage {
        owner: ContractAddress,
        relayer: ContractAddress,
        chains: Map<u64, ChainLiquidity>,
        chain_index: Map<u64, u64>,
        chain_count: u64,
        ocean_score: u128,
        routing_threshold: u128,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        ChainRegistered: ChainRegistered,
        NLScoreUpdated: NLScoreUpdated,
        OceanScoreUpdated: OceanScoreUpdated,
        RelayerUpdated: RelayerUpdated,
        OwnershipTransferred: OwnershipTransferred,
    }

    #[derive(Drop, starknet::Event)]
    pub struct ChainRegistered {
        #[key]
        pub chain_id: u64,
        pub weight: u128,
    }

    #[derive(Drop, starknet::Event)]
    pub struct NLScoreUpdated {
        #[key]
        pub chain_id: u64,
        pub nl_score: u128,
        pub tvl: u128,
    }

    #[derive(Drop, starknet::Event)]
    pub struct OceanScoreUpdated {
        pub ocean_score: u128,
        pub routing_threshold: u128,
    }

    #[derive(Drop, starknet::Event)]
    pub struct RelayerUpdated {
        pub old_relayer: ContractAddress,
        pub new_relayer: ContractAddress,
    }

    #[derive(Drop, starknet::Event)]
    pub struct OwnershipTransferred {
        pub previous_owner: ContractAddress,
        pub new_owner: ContractAddress,
    }

    #[constructor]
    fn constructor(ref self: ContractState, owner: ContractAddress) {
        self.owner.write(owner);
        self.relayer.write(owner);
        self.routing_threshold.write(DEFAULT_ROUTING_THRESHOLD);
        self.ocean_score.write(0_u128);
        self.chain_count.write(0_u64);
    }

    #[abi(embed_v0)]
    impl LiquidityOceanImpl of ILiquidityOcean<ContractState> {
        fn register_chain(ref self: ContractState, chain_id: u64, weight: u128) {
            let caller = get_caller_address();
            assert(caller == self.owner.read(), 'LO: not owner');
            assert(weight <= SCALE, 'LO: invalid weight');
            let existing = self.chains.read(chain_id);
            assert(!existing.active, 'LO: chain exists');

            let rec = ChainLiquidity {
                chain_id,
                nl_score: 0_u128,
                weight,
                tvl: 0_u128,
                last_updated: 0_u64,
                active: true,
            };
            self.chains.write(chain_id, rec);
            let idx = self.chain_count.read();
            self.chain_index.write(idx, chain_id);
            self.chain_count.write(idx + 1_u64);
            self.emit(ChainRegistered { chain_id, weight });
        }

        fn update_nl_score(ref self: ContractState, chain_id: u64, nl_score: u128, tvl: u128) {
            let caller = get_caller_address();
            let relayer = self.relayer.read();
            let owner = self.owner.read();
            assert(caller == relayer || caller == owner, 'LO: not relayer');
            assert(nl_score <= SCALE, 'LO: invalid nl');

            let mut rec = self.chains.read(chain_id);
            assert(rec.active, 'LO: chain not found');
            rec.nl_score = nl_score;
            rec.tvl = tvl;
            rec.last_updated = get_block_timestamp();
            self.chains.write(chain_id, rec);
            self.emit(NLScoreUpdated { chain_id, nl_score, tvl });
        }

        fn recompute_ocean(ref self: ContractState) {
            let n = self.chain_count.read();
            let mut weighted_sum: u128 = 0_u128;
            let mut total_weight: u128 = 0_u128;
            let mut i: u64 = 0_u64;
            loop {
                if i >= n { break; }
                let chain_id = self.chain_index.read(i);
                let c = self.chains.read(chain_id);
                if c.active {
                    weighted_sum += c.nl_score * c.weight;
                    total_weight += c.weight;
                }
                i += 1_u64;
            };
            let ocean = if total_weight == 0_u128 { 0_u128 } else { weighted_sum / total_weight };
            self.ocean_score.write(ocean);
            let rt = self.routing_threshold.read();
            self.emit(OceanScoreUpdated { ocean_score: ocean, routing_threshold: rt });
        }

        fn get_best_chain(self: @ContractState) -> (u64, u128) {
            let n = self.chain_count.read();
            let mut best_chain: u64 = 0_u64;
            let mut best_score: u128 = 0_u128;
            let threshold = self.routing_threshold.read();
            let mut i: u64 = 0_u64;
            loop {
                if i >= n { break; }
                let chain_id = self.chain_index.read(i);
                let c = self.chains.read(chain_id);
                if c.active && c.nl_score >= threshold {
                    let score = c.nl_score * c.weight / SCALE;
                    if score > best_score {
                        best_score = score;
                        best_chain = c.chain_id;
                    }
                }
                i += 1_u64;
            };
            (best_chain, best_score)
        }

        fn get_ocean_score(self: @ContractState) -> u128 {
            self.ocean_score.read()
        }

        fn get_routing_threshold(self: @ContractState) -> u128 {
            self.routing_threshold.read()
        }

        fn set_routing_threshold(ref self: ContractState, threshold: u128) {
            let caller = get_caller_address();
            assert(caller == self.owner.read(), 'LO: not owner');
            assert(threshold <= SCALE, 'LO: invalid threshold');
            self.routing_threshold.write(threshold);
        }

        fn get_chain_count(self: @ContractState) -> u64 {
            self.chain_count.read()
        }

        fn get_chain(self: @ContractState, chain_id: u64) -> ChainLiquidity {
            self.chains.read(chain_id)
        }

        fn get_chain_at_index(self: @ContractState, index: u64) -> u64 {
            self.chain_index.read(index)
        }

        fn get_owner(self: @ContractState) -> ContractAddress {
            self.owner.read()
        }

        fn get_relayer(self: @ContractState) -> ContractAddress {
            self.relayer.read()
        }

        fn set_relayer(ref self: ContractState, new_relayer: ContractAddress) {
            let caller = get_caller_address();
            assert(caller == self.owner.read(), 'LO: not owner');
            let old = self.relayer.read();
            self.relayer.write(new_relayer);
            self.emit(RelayerUpdated { old_relayer: old, new_relayer });
        }

        fn transfer_ownership(ref self: ContractState, new_owner: ContractAddress) {
            let caller = get_caller_address();
            assert(caller == self.owner.read(), 'LO: not owner');
            let old = self.owner.read();
            self.owner.write(new_owner);
            self.emit(OwnershipTransferred { previous_owner: old, new_owner });
        }
    }
}
