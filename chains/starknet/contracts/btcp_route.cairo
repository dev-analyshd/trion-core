// BTCP Route — Cairo (Starknet)
#[starknet::contract]
mod btcp_route {
    use starknet::storage::{StoragePointerReadAccess, StoragePointerWriteAccess, StorageMap};

    #[storage]
    struct Storage {
        route_anchor: StorageMap<felt252, felt252>,
        route_execution: StorageMap<felt252, felt252>,
        route_entity: StorageMap<felt252, felt252>,
        route_gas_saved: StorageMap<felt252, u256>,
        route_finalized: StorageMap<felt252, bool>,
    }

    #[external(v0)]
    fn register_route(ref self: ContractState, route_id: felt252, anchor_bh: felt252, execution_bh: felt252, entity_id: felt252, gas_saved: u256) {
        self.route_anchor.write(route_id, anchor_bh);
        self.route_execution.write(route_id, execution_bh);
        self.route_entity.write(route_id, entity_id);
        self.route_gas_saved.write(route_id, gas_saved);
        self.route_finalized.write(route_id, false);
    }

    #[external(v0)]
    fn finalize(ref self: ContractState, route_id: felt252) {
        self.route_finalized.write(route_id, true);
    }

    #[external(v0)]
    fn is_finalized(ref self: ContractState, route_id: felt252) -> bool {
        self.route_finalized.read(route_id)
    }
}
