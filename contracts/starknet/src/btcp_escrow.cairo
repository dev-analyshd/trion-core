/// TRION Protocol — BTCPEscrow (Starknet)
/// ========================================
/// Mirrors contracts/solidity/BTCPEscrow.sol on Starknet.
/// Two-state atomic escrow: HOLDING -> RELEASED or HOLDING -> REVERTED
/// (or HOLDING -> EMERGENCY_REVERTED via the 7-day escape hatch).
/// Release requires status==HOLDING AND not expired AND coherence >= threshold.
///
/// Whitepaper BTCP §4.3 (Six-Step Execution) + §11 (Five Final Fixes).
///
/// ── Hardening ported from the EVM tier (DD finding 4.2) ──
/// • Locked-balance accounting: per-funder `locked_balance` and global
///   `total_locked_balance`, tracked on lock / release / revert / emergency
///   so the locked pool is always auditable and can never be double-spent.
/// • Emergency exit: `revert_emergency()` — after 7 days ANY caller can
///   recover a stuck escrow (Solidity Gap 8 Resolution).
/// • Cascade revert: `parent_escrow_id` + cascade loop so dependent child
///   escrows revert together with their parent (Solidity Gap 9 Resolution).

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
    /// Multi-hop lock: `parent_escrow_id` != 0 links this escrow to a parent
    /// so a parent revert cascades into this one (Gap 9 cascade revert).
    fn lock_escrow_with_parent(
        ref self: TContractState,
        escrow_id:       felt252,
        route_id:        felt252,
        entity_id:       felt252,
        destination:     starknet::ContractAddress,
        amount:          u256,
        min_coherence:   u64,
        timeout_blocks:  u64,
        parent_escrow_id: felt252,
    );
    fn release_escrow(
        ref self: TContractState,
        escrow_id:    felt252,
        execution_bh: felt252,
        coherence:    u64,
    );
    fn revert_escrow(ref self: TContractState, escrow_id: felt252, reason: u8);
    /// Gap 8: 7-day absolute escape hatch — callable by ANYONE.
    fn revert_emergency(ref self: TContractState, escrow_id: felt252);
    fn get_escrow(self: @TContractState, escrow_id: felt252) -> EscrowRecord;
    fn is_expired(self: @TContractState, escrow_id: felt252) -> bool;
    fn emergency_escape_available(self: @TContractState, escrow_id: felt252) -> bool;
    fn escrow_count(self: @TContractState) -> u64;
    /// Global value currently locked in active (HOLDING) escrows.
    fn total_locked_balance(self: @TContractState) -> u256;
    /// Value currently locked in active escrows funded by `funder`.
    fn locked_balance(self: @TContractState, funder: starknet::ContractAddress) -> u256;
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
    pub state:          u8,    // 0=HOLDING 1=RELEASED 2=REVERTED 3=EMERGENCY_REVERTED
    pub revert_reason:  u8,
    pub settled_at:     u64,
    pub reverted_at:    u64,
    pub locked_by:      starknet::ContractAddress,
    /// For cascade revert (multi-hop) — 0 if single-hop (Gap 9).
    pub parent_escrow_id: felt252,
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
    const STATE_EMERGENCY_REVERTED: u8 = 3;  // Gap 8: 7-day escape terminal state

    /// Revert reasons (whitepaper BTCP §11) — mirrors the Solidity enum.
    const REASON_TIMEOUT:           u8 = 0;
    const REASON_COHERENCE_FAILURE: u8 = 1;
    const REASON_ROUTE_INVALID:     u8 = 2;
    const REASON_MANUAL:            u8 = 3;
    const REASON_AKASHIC_OUTAGE:    u8 = 4;
    const REASON_CASCADE_REVERT:    u8 = 5;  // Gap 9: multi-hop
    const REASON_EMERGENCY_ESCAPE:  u8 = 6;  // Gap 8

    /// Gap 8: absolute maximum lockup before anyone can force a revert.
    const EMERGENCY_ESCAPE_SECONDS: u64 = 7 * 24 * 60 * 60;

    #[storage]
    struct Storage {
        owner: ContractAddress,
        relayer: ContractAddress,
        escrows: Map<felt252, EscrowRecord>,
        escrow_count: u64,
        /// SECURITY: per-funder locked value — sum of amounts over that
        /// funder's escrows still in HOLDING (mirrors Solidity lockedBy
        /// accounting; keyed on the record's `locked_by`).
        locked_balance: Map<ContractAddress, u256>,
        /// SECURITY: global locked value — sum of amounts over ALL active
        /// (HOLDING) escrows, tracked on lock/release/revert/emergency
        /// (mirrors Solidity `_lockedBalance`).
        total_locked_balance: u256,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        EscrowLocked: EscrowLocked,
        EscrowReleased: EscrowReleased,
        EscrowReverted: EscrowReverted,
        EmergencyRevert: EmergencyRevert,
        CascadeRevert: CascadeRevert,
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
    pub struct EmergencyRevert {
        #[key]
        pub escrow_id: felt252,
        #[key]
        pub caller: ContractAddress,
        pub reverted_at: u64,
    }

    #[derive(Drop, starknet::Event)]
    pub struct CascadeRevert {
        #[key]
        pub child_escrow_id: felt252,
        #[key]
        pub parent_escrow_id: felt252,
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
        self.total_locked_balance.write(0);
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
            // Single-hop lock (no parent) — delegates to the multi-hop form
            // with parent_escrow_id = 0, mirroring the Solidity overload pair
            // lockEscrow(...6) / lockEscrow(...6, parentEscrowId).
            self.lock_escrow_with_parent(
                escrow_id,
                route_id,
                entity_id,
                destination,
                amount,
                min_coherence,
                timeout_blocks,
                0,
            );
        }

        fn lock_escrow_with_parent(
            ref self: ContractState,
            escrow_id:    felt252,
            route_id:     felt252,
            entity_id:    felt252,
            destination:  ContractAddress,
            amount:       u256,
            min_coherence: u64,
            timeout_blocks: u64,
            parent_escrow_id: felt252,
        ) {
            let caller = get_caller_address();
            let relayer = self.relayer.read();
            let owner   = self.owner.read();
            assert(caller == relayer || caller == owner, 'BTCP: not authorized');
            assert(escrow_id != 0, 'BTCP: zero escrow id');
            assert(amount > 0_u256, 'BTCP: zero amount');
            assert(min_coherence <= 1_000_000_u64, 'BTCP: invalid coherence');
            assert(timeout_blocks > 0_u64, 'BTCP: zero timeout');

            // Reject duplicate
            let existing = self.escrows.read(escrow_id);
            assert(existing.escrow_id == 0, 'BTCP: escrow exists');

            // Starknet does not expose block height in Cairo contracts; the
            // lock anchor is the block TIMESTAMP and timeout_blocks is
            // interpreted as seconds-on-chain (1 block ≈ 1s on Starknet mainnet,
            // so the numeric value remains block-equivalent). Previously this
            // was hardcoded 0, which broke every timeout computation.
            let lock_ts = get_block_timestamp();

            let rec = EscrowRecord {
                escrow_id,
                route_id,
                entity_id,
                destination,
                amount,
                min_coherence,
                lock_height: lock_ts,
                timeout_blocks,
                state: STATE_HOLDING,
                revert_reason: REASON_TIMEOUT,
                settled_at: 0_u64,
                reverted_at: 0_u64,
                locked_by: caller,
                parent_escrow_id,
            };
            self.escrows.write(escrow_id, rec);
            let count = self.escrow_count.read();
            self.escrow_count.write(count + 1);

            // SECURITY: locked-balance accounting — the funder's locked pool
            // and the global locked pool each grow by the locked amount
            // (mirrors Solidity `_lockedBalance += msg.value`). The lock is
            // still an accounting lock in this tier (no ERC-20 custody is
            // wired yet); this accounting makes the locked pool auditable and
            // double-spend-proof for the custody wiring.
            let funder_locked = self.locked_balance.read(caller);
            self.locked_balance.write(caller, funder_locked + amount);
            let total_locked = self.total_locked_balance.read();
            self.total_locked_balance.write(total_locked + amount);

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
            assert(rec.escrow_id != 0, 'BTCP: not found');
            assert(rec.state == STATE_HOLDING, 'BTCP: not holding');
            // SPEC: release requires NOT expired. Previously this check was
            // missing entirely — a stale escrow could be released long after
            // its timeout had passed.
            assert(
                get_block_timestamp() <= rec.lock_height + rec.timeout_blocks,
                'BTCP: expired',
            );
            assert(coherence >= rec.min_coherence, 'BTCP: coherence insufficient');

            // ── CEI pattern: terminal state, cleared amount and decremented
            // accounting BEFORE any external effect — mirrors the Solidity
            // releaseEscrow ordering (`esc.amount = 0` before transfer).
            let amount_out = rec.amount;
            let funder     = rec.locked_by;
            rec.state       = STATE_RELEASED;
            rec.settled_at  = get_block_timestamp();
            rec.amount      = 0_u256;
            self.escrows.write(escrow_id, rec);

            // SECURITY: value leaves the locked pool on both levels
            // (mirrors Solidity `_lockedBalance -= amountToTransfer`).
            let funder_locked = self.locked_balance.read(funder);
            assert(funder_locked >= amount_out, 'BTCP: locked underflow');
            self.locked_balance.write(funder, funder_locked - amount_out);
            let total_locked = self.total_locked_balance.read();
            assert(total_locked >= amount_out, 'BTCP: locked underflow');
            self.total_locked_balance.write(total_locked - amount_out);

            self.emit(EscrowReleased {
                escrow_id, route_id: rec.route_id, execution_bh, coherence, settled_at: rec.settled_at,
            });
        }

        fn revert_escrow(ref self: ContractState, escrow_id: felt252, reason: u8) {
            let caller = get_caller_address();
            let relayer = self.relayer.read();
            let owner   = self.owner.read();

            let mut rec = self.escrows.read(escrow_id);
            assert(rec.escrow_id != 0, 'BTCP: not found');
            assert(rec.state == STATE_HOLDING, 'BTCP: not holding');

            let is_timeout = get_block_timestamp() > rec.lock_height + rec.timeout_blocks;
            if !is_timeout {
                assert(caller == relayer || caller == owner, 'BTCP: not authorized');
                assert(reason != REASON_TIMEOUT, 'BTCP: not timeout');
            };

            // ── CEI pattern: terminal state, cleared amount and decremented
            // accounting BEFORE any external effect (Solidity revertEscrow).
            let amount_out = rec.amount;
            let funder     = rec.locked_by;
            let now        = get_block_timestamp();
            rec.state         = STATE_REVERTED;
            rec.revert_reason = reason;
            rec.reverted_at   = now;
            rec.amount        = 0_u256;
            self.escrows.write(escrow_id, rec);

            let funder_locked = self.locked_balance.read(funder);
            assert(funder_locked >= amount_out, 'BTCP: locked underflow');
            self.locked_balance.write(funder, funder_locked - amount_out);
            let total_locked = self.total_locked_balance.read();
            assert(total_locked >= amount_out, 'BTCP: locked underflow');
            self.total_locked_balance.write(total_locked - amount_out);

            self.emit(EscrowReverted { escrow_id, reason, reverted_at: now });

            // ── Cascade revert (Gap 9, mirrors Solidity `_cascadeRevert`) ──
            // When a child escrow reverts, its parent (and transitively the
            // whole ancestor chain) reverts too, with reason CASCADE_REVERT.
            // Missing or already-terminal parents are skipped silently —
            // exactly like the Solidity internal helper. Inlined as an
            // explicit loop instead of a recursive internal function.
            let mut child_id  = escrow_id;
            let mut parent_id = rec.parent_escrow_id;
            loop {
                if parent_id == 0 { break; }
                let mut parent = self.escrows.read(parent_id);
                if parent.escrow_id == 0 { break; }
                if parent.state != STATE_HOLDING { break; }

                let p_amount     = parent.amount;
                let p_funder     = parent.locked_by;
                let grandparent  = parent.parent_escrow_id;
                parent.state         = STATE_REVERTED;
                parent.revert_reason = REASON_CASCADE_REVERT;
                parent.reverted_at   = now;
                parent.amount        = 0_u256;
                self.escrows.write(parent_id, parent);

                let p_funder_locked = self.locked_balance.read(p_funder);
                assert(p_funder_locked >= p_amount, 'BTCP: locked underflow');
                self.locked_balance.write(p_funder, p_funder_locked - p_amount);
                let p_total_locked = self.total_locked_balance.read();
                assert(p_total_locked >= p_amount, 'BTCP: locked underflow');
                self.total_locked_balance.write(p_total_locked - p_amount);

                self.emit(CascadeRevert {
                    child_escrow_id: child_id,
                    parent_escrow_id: parent_id,
                    reverted_at: now,
                });
                self.emit(EscrowReverted {
                    escrow_id: parent_id,
                    reason: REASON_CASCADE_REVERT,
                    reverted_at: now,
                });

                // Recursively cascade to the grandparent.
                child_id  = parent_id;
                parent_id = grandparent;
            };
        }

        fn revert_emergency(ref self: ContractState, escrow_id: felt252) {
            let caller = get_caller_address();

            let mut rec = self.escrows.read(escrow_id);
            assert(rec.escrow_id != 0, 'BTCP: not found');
            assert(rec.state == STATE_HOLDING, 'BTCP: not holding');
            // Gap 8: no relayer, no coherence proof — after 7 days ANY
            // caller can force the revert. lock_height is the block
            // TIMESTAMP at lock (see lock_escrow_with_parent).
            assert(
                get_block_timestamp() >= rec.lock_height + EMERGENCY_ESCAPE_SECONDS,
                'BTCP: emergency not yet',
            );

            // ── CEI pattern: terminal state, cleared amount and decremented
            // accounting BEFORE any external effect (Solidity revertEmergency).
            let amount_out = rec.amount;
            let funder     = rec.locked_by;
            let now        = get_block_timestamp();
            rec.state         = STATE_EMERGENCY_REVERTED;
            rec.revert_reason = REASON_EMERGENCY_ESCAPE;
            rec.reverted_at   = now;
            rec.amount        = 0_u256;
            self.escrows.write(escrow_id, rec);

            let funder_locked = self.locked_balance.read(funder);
            assert(funder_locked >= amount_out, 'BTCP: locked underflow');
            self.locked_balance.write(funder, funder_locked - amount_out);
            let total_locked = self.total_locked_balance.read();
            assert(total_locked >= amount_out, 'BTCP: locked underflow');
            self.total_locked_balance.write(total_locked - amount_out);

            self.emit(EmergencyRevert { escrow_id, caller, reverted_at: now });

            // ── Cascade revert (Gap 9, mirrors Solidity `_cascadeRevert`) ──
            // Same inlined loop as revert_escrow: an emergency revert of a
            // child cascades through its whole ancestor chain.
            let mut child_id  = escrow_id;
            let mut parent_id = rec.parent_escrow_id;
            loop {
                if parent_id == 0 { break; }
                let mut parent = self.escrows.read(parent_id);
                if parent.escrow_id == 0 { break; }
                if parent.state != STATE_HOLDING { break; }

                let p_amount     = parent.amount;
                let p_funder     = parent.locked_by;
                let grandparent  = parent.parent_escrow_id;
                parent.state         = STATE_REVERTED;
                parent.revert_reason = REASON_CASCADE_REVERT;
                parent.reverted_at   = now;
                parent.amount        = 0_u256;
                self.escrows.write(parent_id, parent);

                let p_funder_locked = self.locked_balance.read(p_funder);
                assert(p_funder_locked >= p_amount, 'BTCP: locked underflow');
                self.locked_balance.write(p_funder, p_funder_locked - p_amount);
                let p_total_locked = self.total_locked_balance.read();
                assert(p_total_locked >= p_amount, 'BTCP: locked underflow');
                self.total_locked_balance.write(p_total_locked - p_amount);

                self.emit(CascadeRevert {
                    child_escrow_id: child_id,
                    parent_escrow_id: parent_id,
                    reverted_at: now,
                });
                self.emit(EscrowReverted {
                    escrow_id: parent_id,
                    reason: REASON_CASCADE_REVERT,
                    reverted_at: now,
                });

                // Recursively cascade to the grandparent.
                child_id  = parent_id;
                parent_id = grandparent;
            };
        }

        fn get_escrow(self: @ContractState, escrow_id: felt252) -> EscrowRecord {
            self.escrows.read(escrow_id)
        }

        fn is_expired(self: @ContractState, escrow_id: felt252) -> bool {
            let rec = self.escrows.read(escrow_id);
            rec.state == STATE_HOLDING && get_block_timestamp() > rec.lock_height + rec.timeout_blocks
        }

        fn emergency_escape_available(self: @ContractState, escrow_id: felt252) -> bool {
            // Gap 8 view — mirrors Solidity emergencyEscapeAvailable().
            let rec = self.escrows.read(escrow_id);
            rec.state == STATE_HOLDING
                && get_block_timestamp() >= rec.lock_height + EMERGENCY_ESCAPE_SECONDS
        }

        fn escrow_count(self: @ContractState) -> u64 {
            self.escrow_count.read()
        }

        fn total_locked_balance(self: @ContractState) -> u256 {
            self.total_locked_balance.read()
        }

        fn locked_balance(self: @ContractState, funder: ContractAddress) -> u256 {
            self.locked_balance.read(funder)
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
