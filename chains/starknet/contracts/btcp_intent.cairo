// BTCP Intent — Cairo (Starknet)
#[starknet::contract]
mod btcp_intent {
    use starknet::storage::{StoragePointerReadAccess, StoragePointerWriteAccess, StorageMap};

    #[storage]
    struct Storage {
        intent_hash: StorageMap<felt252, felt252>,
        intent_source: StorageMap<felt252, felt252>,
        intent_dest: StorageMap<felt252, felt252>,
        intent_amount: StorageMap<felt252, u256>,
        intent_active: StorageMap<felt252, bool>,
    }

    #[external(v0)]
    fn register_intent(ref self: ContractState, intent_id: felt252, hash: felt252, source: felt252, dest: felt252, amount: u256) {
        self.intent_hash.write(intent_id, hash);
        self.intent_source.write(intent_id, source);
        self.intent_dest.write(intent_id, dest);
        self.intent_amount.write(intent_id, amount);
        self.intent_active.write(intent_id, true);
    }

    #[external(v0)]
    fn deactivate(ref self: ContractState, intent_id: felt252) {
        self.intent_active.write(intent_id, false);
    }

    #[external(v0)]
    fn is_active(ref self: ContractState, intent_id: felt252) -> bool {
        self.intent_active.read(intent_id)
    }
}
