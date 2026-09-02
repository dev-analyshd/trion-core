/// TRION Protocol — BTCPRoute (Starknet)
/// =======================================
/// Mirrors contracts/solidity/BTCPRoute.sol on Starknet.
/// Records the behavioral proof of a cross-chain BTCP route.
/// Each route links an anchor behavioral hash (chain A) to an execution
/// behavioral hash (chain B) with consensus proof.
///
/// Whitepaper BTCP §3 — Route ID tracking with anchor BH -> execution BH linkage.

#[starknet::interface]
pub trait IBTCPRoute<TContractState> {
    fn register_route(
        ref self: TContractState,
        route_id:        felt252,
        intent_hash:     felt252,
        anchor_bh:       felt252,
        anchor_chain:    u64,
        execution_chain: u64,
        entity_id:       felt252,
        route_type:      u8,
    );
    fn finalize_route(
        ref self: TContractState,
        route_id:            felt252,
        execution_bh:        felt252,
        gas_saved_vs_bridge:u64,
        beo_continuity:     u64,
        cc_coherence:        u64,
    );
    fn get_route(self: @TContractState, route_id: felt252) -> RouteRecord;
    fn route_count(self: @TContractState) -> u64;
    fn set_relayer(ref self: TContractState, new_relayer: starknet::ContractAddress);
}

#[derive(Drop, Serde, Copy, starknet::Store)]
pub struct RouteRecord {
    pub route_id:            felt252,
    pub intent_hash:         felt252,
    pub anchor_bh:           felt252,
    pub execution_bh:        felt252,
    pub anchor_chain:        u64,
    pub execution_chain:     u64,
    pub entity_id:           felt252,
    pub gas_saved_vs_bridge:u64,
    pub beo_continuity:     u64,
    pub cc_coherence:        u64,
    pub route_type:          u8,
    pub is_verified:         bool,
    pub created_at:          u64,
    pub finalized_at:        u64,
}

#[starknet::contract]
pub mod BTCPRoute {
    use super::{RouteRecord, IBTCPRoute};
    use starknet::{
        ContractAddress, get_caller_address, get_block_timestamp,
        storage::{Map, StorageMapReadAccess, StorageMapWriteAccess,
                  StoragePointerReadAccess, StoragePointerWriteAccess},
    };

    #[storage]
    struct Storage {
        owner: ContractAddress,
        relayer: ContractAddress,
        routes: Map<felt252, RouteRecord>,
        route_count: u64,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        RoutePublished: RoutePublished,
        RouteFinalized: RouteFinalized,
        RelayerUpdated: RelayerUpdated,
    }

    #[derive(Drop, starknet::Event)]
    pub struct RoutePublished {
        #[key]
        pub route_id: felt252,
        #[key]
        pub intent_hash: felt252,
        pub anchor_bh: felt252,
        pub anchor_chain: u64,
        pub execution_chain: u64,
        pub route_type: u8,
    }

    #[derive(Drop, starknet::Event)]
    pub struct RouteFinalized {
        #[key]
        pub route_id: felt252,
        pub execution_bh: felt252,
        pub gas_saved: u64,
        pub beo_continuity: u64,
        pub cc_coherence: u64,
    }

    #[derive(Drop, starknet::Event)]
    pub struct RelayerUpdated {
        pub old_relayer: ContractAddress,
        pub new_relayer: ContractAddress,
    }

    #[constructor]
    fn constructor(ref self: ContractState, owner: ContractAddress) {
        self.owner.write(owner);
        self.relayer.write(owner);
        self.route_count.write(0);
    }

    #[abi(embed_v0)]
    impl BTCPRouteImpl of IBTCPRoute<ContractState> {
        fn register_route(
            ref self: ContractState,
            route_id:        felt252,
            intent_hash:     felt252,
            anchor_bh:       felt252,
            anchor_chain:    u64,
            execution_chain: u64,
            entity_id:       felt252,
            route_type:      u8,
        ) {
            let caller = get_caller_address();
            let relayer = self.relayer.read();
            let owner   = self.owner.read();
            assert(caller == relayer || caller == owner, 'BTCP: not authorized');
            assert(anchor_bh != 0, 'BTCP: zero anchor');
            assert(route_type <= 6_u8, 'BTCP: invalid type');

            let existing = self.routes.read(route_id);
            assert(existing.anchor_bh == 0, 'BTCP: route exists');

            let rec = RouteRecord {
                route_id, intent_hash, anchor_bh,
                execution_bh: 0,
                anchor_chain, execution_chain, entity_id,
                gas_saved_vs_bridge: 0,
                beo_continuity: 0,
                cc_coherence: 0,
                route_type,
                is_verified: false,
                created_at: get_block_timestamp(),
                finalized_at: 0,
            };
            self.routes.write(route_id, rec);
            let count = self.route_count.read();
            self.route_count.write(count + 1);

            self.emit(RoutePublished {
                route_id, intent_hash, anchor_bh, anchor_chain, execution_chain, route_type,
            });
        }

        fn finalize_route(
            ref self: ContractState,
            route_id:            felt252,
            execution_bh:        felt252,
            gas_saved_vs_bridge: u64,
            beo_continuity:      u64,
            cc_coherence:        u64,
        ) {
            let caller = get_caller_address();
            let relayer = self.relayer.read();
            let owner   = self.owner.read();
            assert(caller == relayer || caller == owner, 'BTCP: not authorized');
            assert(execution_bh != 0, 'BTCP: zero exec bh');
            assert(beo_continuity <= 1_000_000_u64, 'BTCP: invalid score');
            assert(cc_coherence <= 1_000_000_u64, 'BTCP: invalid score');

            let mut r = self.routes.read(route_id);
            assert(r.anchor_bh != 0, 'BTCP: not found');
            assert(!r.is_verified, 'BTCP: already verified');

            r.execution_bh          = execution_bh;
            r.gas_saved_vs_bridge   = gas_saved_vs_bridge;
            r.beo_continuity        = beo_continuity;
            r.cc_coherence          = cc_coherence;
            r.is_verified           = true;
            r.finalized_at          = get_block_timestamp();
            self.routes.write(route_id, r);

            self.emit(RouteFinalized {
                route_id, execution_bh, gas_saved: gas_saved_vs_bridge,
                beo_continuity, cc_coherence,
            });
        }

        fn get_route(self: @ContractState, route_id: felt252) -> RouteRecord {
            self.routes.read(route_id)
        }

        fn route_count(self: @ContractState) -> u64 {
            self.route_count.read()
        }

        fn set_relayer(ref self: ContractState, new_relayer: ContractAddress) {
            let caller = get_caller_address();
            assert(caller == self.owner.read(), 'BTCP: not owner');
            let old = self.relayer.read();
            self.relayer.write(new_relayer);
            self.emit(RelayerUpdated { old_relayer: old, new_relayer });
        }
    }
}
