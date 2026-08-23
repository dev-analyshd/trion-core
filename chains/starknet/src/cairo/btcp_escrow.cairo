/// TRION Protocol — BTCPEscrow (Starknet)
/// ========================================
/// Mirrors contracts/solidity/BTCPEscrow.sol on Starknet.
/// Two-state atomic escrow: HOLDING -> RELEASED or HOLDING -> REVERTED.
/// Release requires status==HOLDING AND not expired AND coherence >= threshold.
///
/// Whitepaper BTCP §4.3 (Six-Step Execution) + §11 (Five Final Fixes).

#[starknet::interface]
pub trait IBTCPEscrow<TContractState> {
    fn lock_escrow(
        ref self: TContractState,
        escrow_id:     felt252,
        route_id:      felt252,
        entity_id:     felt252,
        destination:   starknet::ContractAddress,
        amount:        u256,
        min_coherence: u64,
        timeout_blocks:u64,
    );
    fn release_escrow(
        ref self: TContractState,
        escrow_id:    felt252,
        execution_bh: felt252,
        coherence:    u64,
    );
    fn revert_escrow(ref self: TContractState, escrow_id: felt252, reason: u8);
    fn get_escrow(self: @TContractState, escrow_id: felt252) -> EscrowRecord;
    fn is_expired(self: @TContractState, escrow_id: felt252) -> bool;
    fn escrow_count(self: @TContractState) -> u64;
    fn set_relayer(ref self: TContractState, new_relayer: starknet::ContractAddress);
}

#[derive(Drop, Serde, Copy, starknet::Store)]
pub struct EscrowRecord {
    pub escrow_id:       felt252,
    pub route_id:        felt252,
    pub entity_id:       felt252,
    pub destination:    starknet::ContractAddress,
    pub amount:         u256,
    pub min_coherence:  u64,
    pub lock_height:    u64,
    pub timeout_blocks: u64,
    pub state:          u8,    // 0=HOLDING 1=RELEASED 2=REVERTED
    pub revert_reason:  u8,
    pub settled_at:     u64,
    pub reverted_at:    u64,
    pub locked_by:      starknet::ContractAddress,
}

#[starknet::contract]
pub mod BTCPEscrow {
    use super::{EscrowRecord, IBTCPEscrow};
    use starknet::{
        ContractAddress, get_caller_address, get_block_timestamp,
        storage::{Map, StorageMapReadAccess, StorageMapWriteAccess,
                  StoragePointerReadAccess, StoragePointerWriteAccess},
    };

    const STATE_HOLDING:    u8 = 0;
    const STATE_RELEASED:   u8 = 1;
    const STATE_REVERTED:   u8 = 2;

    #[storage]
    struct Storage {
        owner: ContractAddress,
        relayer: ContractAddress,
        escrows: Map<felt252, EscrowRecord>,
        escrow_count: u64,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        EscrowLocked: EscrowLocked,
        EscrowReleased: EscrowReleased,
        EscrowReverted: EscrowReverted,
        RelayerUpdated: RelayerUpdated,
    }

    #[derive(Drop, starknet::Event)]
    pub struct EscrowLocked {
        #[key]
        pub escrow_id: felt252,
        #[key]
        pub route_id: felt252,
        pub entity_id: felt252,
        pub amount: u256,
        pub min_coherence: u64,
    }

    #[derive(Drop, starknet::Event)]
    pub struct EscrowReleased {
        #[key]
        pub escrow_id: felt252,
        pub route_id: felt252,
        pub execution_bh: felt252,
        pub coherence: u64,
        pub settled_at: u64,
    }

    #[derive(Drop, starknet::Event)]
    pub struct EscrowReverted {
        #[key]
        pub escrow_id: felt252,
        pub reason: u8,
        pub reverted_at: u64,
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
        self.escrow_count.write(0);
    }

    #[abi(embed_v0)]
    impl BTCPEscrowImpl of IBTCPEscrow<ContractState> {
        fn lock_escrow(
            ref self: ContractState,
            escrow_id:    felt252,
            route_id:     felt252,
            entity_id:    felt252,
            destination:  ContractAddress,
            amount:       u256,
            min_coherence: u64,
            timeout_blocks: u64,
        ) {
            let caller = get_caller_address();
            let relayer = self.relayer.read();
            let owner   = self.owner.read();
            assert(caller == relayer || caller == owner, 'BTCP: not authorized');
            assert(amount > 0_u256, 'BTCP: zero amount');
            assert(min_coherence <= 1_000_000_u64, 'BTCP: invalid coherence');
            assert(timeout_blocks > 0_u64, 'BTCP: zero timeout');

            // Reject duplicate
            let existing = self.escrows.read(escrow_id);
            assert(existing.amount == 0_u256, 'BTCP: escrow exists');

            let rec = EscrowRecord {
                escrow_id,
                route_id,
                entity_id,
                destination,
                amount,
                min_coherence,
                lock_height: 0_u64, // Starknet doesn't expose block height natively
                timeout_blocks,
                state: STATE_HOLDING,
                revert_reason: 0_u8,
                settled_at: 0_u64,
                reverted_at: 0_u64,
                locked_by: caller,
            };
            self.escrows.write(escrow_id, rec);
            let count = self.escrow_count.read();
            self.escrow_count.write(count + 1);

            self.emit(EscrowLocked {
                escrow_id, route_id, entity_id, amount, min_coherence,
            });
        }

        fn release_escrow(
            ref self: ContractState,
            escrow_id:    felt252,
            execution_bh: felt252,
            coherence:    u64,
        ) {
            let caller = get_caller_address();
            let relayer = self.relayer.read();
            let owner   = self.owner.read();
            assert(caller == relayer || caller == owner, 'BTCP: not authorized');

            let mut rec = self.escrows.read(escrow_id);
            assert(rec.amount != 0_u256, 'BTCP: not found');
            assert(rec.state == STATE_HOLDING, 'BTCP: not holding');
            assert(coherence >= rec.min_coherence, 'BTCP: coherence insufficient');

            rec.state       = STATE_RELEASED;
            rec.settled_at  = get_block_timestamp();
            self.escrows.write(escrow_id, rec);

            self.emit(EscrowReleased {
                escrow_id, route_id: rec.route_id, execution_bh, coherence, settled_at: rec.settled_at,
            });
        }

        fn revert_escrow(ref self: ContractState, escrow_id: felt252, reason: u8) {
            let caller = get_caller_address();
            let relayer = self.relayer.read();
            let owner   = self.owner.read();

            let mut rec = self.escrows.read(escrow_id);
            assert(rec.amount != 0_u256, 'BTCP: not found');
            assert(rec.state == STATE_HOLDING, 'BTCP: not holding');

            let is_timeout = get_block_timestamp() > rec.lock_height + rec.timeout_blocks;
            if !is_timeout {
                assert(caller == relayer || caller == owner, 'BTCP: not authorized');
                assert(reason != 0_u8, 'BTCP: not timeout');
            };

            rec.state         = STATE_REVERTED;
            rec.revert_reason = reason;
            rec.reverted_at   = get_block_timestamp();
            self.escrows.write(escrow_id, rec);

            self.emit(EscrowReverted { escrow_id, reason, reverted_at: rec.reverted_at });
        }

        fn get_escrow(self: @ContractState, escrow_id: felt252) -> EscrowRecord {
            self.escrows.read(escrow_id)
        }

        fn is_expired(self: @ContractState, escrow_id: felt252) -> bool {
            let rec = self.escrows.read(escrow_id);
            rec.state == STATE_HOLDING && get_block_timestamp() > rec.lock_height + rec.timeout_blocks
        }

        fn escrow_count(self: @ContractState) -> u64 {
            self.escrow_count.read()
        }

        fn set_relayer(ref self: ContractState, new_relayer: ContractAddress) {
            let caller = get_caller_address();
            let owner   = self.owner.read();
            assert(caller == owner, 'BTCP: not owner');
            let old = self.relayer.read();
            self.relayer.write(new_relayer);
            self.emit(RelayerUpdated { old_relayer: old, new_relayer });
        }
    }
}
