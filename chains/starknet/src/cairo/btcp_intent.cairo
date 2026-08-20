/// TRION Protocol — BTCPIntent (Starknet)
/// ========================================
/// Mirrors contracts/solidity/BTCPIntent.sol on Starknet.
/// Registers user intents: what they want, not how to execute.
/// Full intent object stored off-chain in Akashic Index; on-chain stores
/// only the intent hash + minimal routing metadata.
///
/// Whitepaper BTCP §4.1 — Intent lifecycle: PENDING -> ROUTING -> EXECUTING
///   -> COMPLETED  |  FAILED -> RESURRECTED  |  EXPIRED.

#[starknet::interface]
pub trait IBTCPIntent<TContractState> {
    fn register_intent(
        ref self: TContractState,
        intent_hash:  felt252,
        entity_id:    felt252,
        action:       u8,
        asset_in:     felt252,
        asset_out:    felt252,
        magnitude:    u256,
        source_chain: u64,
        dest_chain:   u64,
        deadline:     u64,
        max_gas_usd:  u64,
        min_nl_score: u16,
        privacy:      u8,
    );
    fn update_status(ref self: TContractState, intent_hash: felt252, new_status: u8);
    fn get_intent(self: @TContractState, intent_hash: felt252) -> IntentRecord;
    fn intent_count(self: @TContractState) -> u64;
    fn set_relayer(ref self: TContractState, new_relayer: starknet::ContractAddress);
}

#[derive(Drop, Serde, Copy, starknet::Store)]
pub struct IntentRecord {
    pub intent_hash: felt252,
    pub entity_id:  felt252,
    pub action:     u8,    // 0=SWAP 1=TRANSFER 2=LIQUIDITY 3=STAKE 4=BORROW
    pub asset_in:   felt252,
    pub asset_out:  felt252,
    pub magnitude:  u256,
    pub source_chain: u64,
    pub dest_chain:   u64,
    pub deadline:   u64,
    pub max_gas_usd:u64,
    pub min_nl_score: u16,
    pub privacy:    u8,    // 0=PUBLIC 1=ZK_CREDENTIAL 2=INVISIBLE
    pub status:     u8,    // 0=PENDING 1=ROUTING 2=EXECUTING 3=COMPLETED 4=FAILED 5=EXPIRED 6=RESURRECTED
    pub created_at: u64,
}

#[starknet::contract]
pub mod BTCPIntent {
    use super::{IntentRecord, IBTCPIntent};
    use starknet::{
        ContractAddress, get_caller_address, get_block_timestamp,
        storage::{Map, StorageMapReadAccess, StorageMapWriteAccess,
                  StoragePointerReadAccess, StoragePointerWriteAccess},
    };

    const STATUS_PENDING:      u8 = 0;
    const STATUS_ROUTING:      u8 = 1;
    const STATUS_EXECUTING:    u8 = 2;
    const STATUS_COMPLETED:    u8 = 3;
    const STATUS_FAILED:       u8 = 4;
    const STATUS_EXPIRED:      u8 = 5;
    const STATUS_RESURRECTED:  u8 = 6;

    #[storage]
    struct Storage {
        owner: ContractAddress,
        relayer: ContractAddress,
        intents: Map<felt252, IntentRecord>,
        intent_count: u64,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        IntentRegistered: IntentRegistered,
        IntentStatusUpdated: IntentStatusUpdated,
        RelayerUpdated: RelayerUpdated,
    }

    #[derive(Drop, starknet::Event)]
    pub struct IntentRegistered {
        #[key]
        pub intent_hash: felt252,
        #[key]
        pub entity_id: felt252,
        pub action: u8,
        pub magnitude: u256,
        pub deadline: u64,
    }

    #[derive(Drop, starknet::Event)]
    pub struct IntentStatusUpdated {
        #[key]
        pub intent_hash: felt252,
        pub old_status: u8,
        pub new_status: u8,
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
        self.intent_count.write(0);
    }

    /// Valid status transitions per whitepaper BTCP §4.1.
    fn valid_transition(from: u8, to: u8) -> bool {
        // PENDING -> ROUTING, FAILED, EXPIRED
        if (from == STATUS_PENDING) {
            return to == STATUS_ROUTING || to == STATUS_FAILED || to == STATUS_EXPIRED;
        }
        // ROUTING -> EXECUTING, FAILED, EXPIRED
        if (from == STATUS_ROUTING) {
            return to == STATUS_EXECUTING || to == STATUS_FAILED || to == STATUS_EXPIRED;
        }
        // EXECUTING -> COMPLETED, FAILED
        if (from == STATUS_EXECUTING) {
            return to == STATUS_COMPLETED || to == STATUS_FAILED;
        }
        // FAILED -> RESURRECTED
        if (from == STATUS_FAILED) {
            return to == STATUS_RESURRECTED;
        }
        false
    }

    #[abi(embed_v0)]
    impl BTCPIntentImpl of IBTCPIntent<ContractState> {
        fn register_intent(
            ref self: ContractState,
            intent_hash: felt252,
            entity_id:   felt252,
            action:      u8,
            asset_in:    felt252,
            asset_out:   felt252,
            magnitude:   u256,
            source_chain: u64,
            dest_chain:  u64,
            deadline:    u64,
            max_gas_usd: u64,
            min_nl_score:u16,
            privacy:     u8,
        ) {
            let caller = get_caller_address();
            let relayer = self.relayer.read();
            let owner   = self.owner.read();
            assert(caller == relayer || caller == owner, 'BTCP: not authorized');
            assert(action <= 4_u8, 'BTCP: invalid action');
            assert(magnitude > 0_u256, 'BTCP: zero magnitude');
            assert(deadline > get_block_timestamp(), 'BTCP: deadline past');
            assert(privacy <= 2_u8, 'BTCP: invalid privacy');

            let existing = self.intents.read(intent_hash);
            assert(existing.magnitude == 0_u256, 'BTCP: intent exists');

            let rec = IntentRecord {
                intent_hash, entity_id, action, asset_in, asset_out, magnitude,
                source_chain, dest_chain, deadline, max_gas_usd, min_nl_score, privacy,
                status: STATUS_PENDING,
                created_at: get_block_timestamp(),
            };
            self.intents.write(intent_hash, rec);
            let count = self.intent_count.read();
            self.intent_count.write(count + 1);

            self.emit(IntentRegistered {
                intent_hash, entity_id, action, magnitude, deadline,
            });
        }

        fn update_status(ref self: ContractState, intent_hash: felt252, new_status: u8) {
            let caller = get_caller_address();
            let relayer = self.relayer.read();
            let owner   = self.owner.read();
            assert(caller == relayer || caller == owner, 'BTCP: not authorized');

            let mut rec = self.intents.read(intent_hash);
            assert(rec.magnitude != 0_u256, 'BTCP: not found');
            assert(valid_transition(rec.status, new_status), 'BTCP: invalid transition');
            let old = rec.status;
            rec.status = new_status;
            self.intents.write(intent_hash, rec);
            self.emit(IntentStatusUpdated { intent_hash, old_status: old, new_status });
        }

        fn get_intent(self: @ContractState, intent_hash: felt252) -> IntentRecord {
            self.intents.read(intent_hash)
        }

        fn intent_count(self: @ContractState) -> u64 {
            self.intent_count.read()
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
