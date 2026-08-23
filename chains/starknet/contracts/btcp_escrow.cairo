// BTCP Escrow — Cairo (Starknet)
// =================================================================
// Two-state atomic escrow for cross-chain behavioral routing.
// Whitepaper: BTCP §4.3 (Six-Step Execution) and §11 (Five Final Fixes):
//   • lock_escrow     — entity locks funds, escrow enters HOLDING
//   • release_escrow  — relayer + coherence proof releases to destination
//   • revert_escrow   — timeout / coherence-failure refunds locked_by
//   • emergency_revert — 7-day absolute escape hatch (Gap 8), anyone
//   • cascade_revert  — multi-hop nested escrow support (Gap 9)
//   • enter_pending_akashic — 24h recovery window (E1)
//
// Funds stay on the source Starknet chain at all times. No cross-chain
// asset movement occurs — this is the BTCP zero-bridge paradigm.

#[starknet::contract]
mod btcp_escrow {
    use starknet::storage::{
        StoragePointerReadAccess, StoragePointerWriteAccess,
        StorageMap, StorageMapAccess,
    };
    use starknet::get_block_timestamp;

    // ── Escrow states (extended per spec Phase 1.1) ──────────────────────────
    const HOLDING:            u8 = 0;
    const PENDING_AKASHIC:   u8 = 1;
    const RELEASED:           u8 = 2;
    const REVERTED:           u8 = 3;
    const EMERGENCY_REVERTED: u8 = 4;

    // ── Revert reasons (whitepaper BTCP §11) ───────────────────────────────
    const REASON_TIMEOUT:                u8 = 0;
    const REASON_COHERENCE_FAILURE:     u8 = 1;
    const REASON_ROUTE_INVALID:          u8 = 2;
    const REASON_MANUAL:                 u8 = 3;
    const REASON_AKASHIC_OUTAGE_24H:    u8 = 4;
    const REASON_CASCADE_REVERT:         u8 = 5;
    const REASON_EMERGENCY_ESCAPE:       u8 = 6;

    // ── Timeouts ────────────────────────────────────────────────────────────
    // 7 days in seconds (Gap 8 absolute escape hatch)
    const EMERGENCY_ESCAPE_SECONDS: u64 = 7 * 24 * 60 * 60;
    // 24h PENDING_AKASHIC recovery window (E1)
    const AKASHIC_RECOVERY_SECONDS: u64 = 24 * 60 * 60;

    // ── Storage layout ──────────────────────────────────────────────────────
    #[storage]
    struct Storage {
        escrow_state: StorageMap<felt252, u8>,
        escrow_amount: StorageMap<felt252, u256>,
        escrow_entity: StorageMap<felt252, felt252>,
        escrow_destination: StorageMap<felt252, felt252>,
        escrow_locked_by: StorageMap<felt252, felt252>,
        escrow_lock_timestamp: StorageMap<felt252, u64>,
        escrow_timeout_seconds: StorageMap<felt252, u64>,
        escrow_min_coherence: StorageMap<felt252, u64>,
        coherence_verified: StorageMap<felt252, bool>,
        escrow_parent: StorageMap<felt252, felt252>, // for cascade revert
        relayer: felt252,
        owner: felt252,
    }

    // ── Constructor ─────────────────────────────────────────────────────────
    #[constructor]
    fn constructor(ref self: ContractState, owner: felt252, relayer: felt252) {
        self.owner.write(owner);
        self.relayer.write(relayer);
    }

    // ── Modifier-like helpers ────────────────────────────────────────────────
    fn assert_relayer(ref self: ContractState, caller: felt252) {
        let owner = self.owner.read();
        let relayer = self.relayer.read();
        assert!(caller == relayer || caller == owner, 'NOT_RELAYER');
    }

    fn assert_exists(ref self: ContractState, route_id: felt252) {
        let state = self.escrow_state.read(route_id);
        // state == 0 is HOLDING (default zero) — disambiguate via amount
        let amount = self.escrow_amount.read(route_id);
        assert!(amount > 0_u256 || state != 0_u8, 'ESCROW_NOT_FOUND');
    }

    // ── lock_escrow ─────────────────────────────────────────────────────────
    #[external(v0)]
    fn lock_escrow(
        ref self: ContractState,
        route_id: felt252,
        entity_id: felt252,
        destination: felt252,
        amount: u256,
        min_coherence: u64,
        timeout_seconds: u64,
        parent_route_id: felt252,
    ) {
        let caller = starknet::get_caller_address();
        assert_relayer(ref self, caller);

        assert!(amount > 0_u256, 'ZERO_AMOUNT');
        assert!(destination != 0, 'ZERO_DESTINATION');
        assert!(min_coherence <= 1_000_000, 'INVALID_COHERENCE');
        assert!(timeout_seconds > 0, 'ZERO_TIMEOUT');

        self.escrow_state.write(route_id, HOLDING);
        self.escrow_amount.write(route_id, amount);
        self.escrow_entity.write(route_id, entity_id);
        self.escrow_destination.write(route_id, destination);
        self.escrow_locked_by.write(route_id, caller);
        self.escrow_lock_timestamp.write(route_id, get_block_timestamp());
        self.escrow_timeout_seconds.write(route_id, timeout_seconds);
        self.escrow_min_coherence.write(route_id, min_coherence);
        self.coherence_verified.write(route_id, false);
        self.escrow_parent.write(route_id, parent_route_id);
    }

    // ── Backward-compatible lock_escrow (no parent) ─────────────────────────
    #[external(v0)]
    fn lock_escrow_simple(
        ref self: ContractState,
        route_id: felt252,
        entity_id: felt252,
        amount: u256,
    ) {
        let caller = starknet::get_caller_address();
        assert_relayer(ref self, caller);
        assert!(amount > 0_u256, 'ZERO_AMOUNT');

        self.escrow_state.write(route_id, HOLDING);
        self.escrow_amount.write(route_id, amount);
        self.escrow_entity.write(route_id, entity_id);
        self.escrow_destination.write(route_id, caller);
        self.escrow_locked_by.write(route_id, caller);
        self.escrow_lock_timestamp.write(route_id, get_block_timestamp());
        self.escrow_timeout_seconds.write(route_id, 3600_u64);
        self.escrow_min_coherence.write(route_id, 550_000_u64);
        self.coherence_verified.write(route_id, false);
        self.escrow_parent.write(route_id, 0);
    }

    // ── verify_coherence ────────────────────────────────────────────────────
    #[external(v0)]
    fn verify_coherence(ref self: ContractState, route_id: felt252) {
        let caller = starknet::get_caller_address();
        assert_relayer(ref self, caller);
        self.coherence_verified.write(route_id, true);
    }

    // ── release_escrow ───────────────────────────────────────────────────────
    #[external(v0)]
    fn release_escrow(ref self: ContractState, route_id: felt252) {
        let caller = starknet::get_caller_address();
        assert_relayer(ref self, caller);

        let state = self.escrow_state.read(route_id);
        assert!(state == HOLDING || state == PENDING_AKASHIC, 'Invalid state');
        let verified = self.coherence_verified.read(route_id);
        assert!(verified, 'Coherence not verified');

        // Check timeout
        let lock_ts = self.escrow_lock_timestamp.read(route_id);
        let timeout = self.escrow_timeout_seconds.read(route_id);
        let now = get_block_timestamp();
        assert!(now <= lock_ts + timeout, 'Escrow expired');

        self.escrow_state.write(route_id, RELEASED);
    }

    // ── revert_escrow ────────────────────────────────────────────────────────
    #[external(v0)]
    fn revert_escrow(ref self: ContractState, route_id: felt252, reason: u8) {
        let state = self.escrow_state.read(route_id);
        assert!(state == HOLDING || state == PENDING_AKASHIC, 'Invalid state');

        let lock_ts = self.escrow_lock_timestamp.read(route_id);
        let timeout = self.escrow_timeout_seconds.read(route_id);
        let now = get_block_timestamp();
        let is_timeout = now > lock_ts + timeout;

        if (!is_timeout) {
            // Non-timeout revert: caller must be relayer or owner
            let caller = starknet::get_caller_address();
            assert_relayer(ref self, caller);
            assert!(reason != REASON_TIMEOUT, 'Not timeout');
        }

        self.escrow_state.write(route_id, REVERTED);

        // Cascade revert to parent if multi-hop (Gap 9)
        let parent = self.escrow_parent.read(route_id);
        if (parent != 0) {
            self._cascade_revert(parent);
        }
    }

    // ── emergency_revert — 7-day escape hatch, callable by ANYONE ────────────
    #[external(v0)]
    fn emergency_revert(ref self: ContractState, route_id: felt252) {
        let state = self.escrow_state.read(route_id);
        assert!(state == HOLDING || state == PENDING_AKASHIC, 'Invalid state');

        let lock_ts = self.escrow_lock_timestamp.read(route_id);
        let now = get_block_timestamp();
        assert!(now >= lock_ts + EMERGENCY_ESCAPE_SECONDS, 'Emergency not yet');

        self.escrow_state.write(route_id, EMERGENCY_REVERTED);

        // Cascade to parent
        let parent = self.escrow_parent.read(route_id);
        if (parent != 0) {
            self._cascade_revert(parent);
        }
    }

    // ── enter_pending_akashic — 24h recovery window (E1) ────────────────────
    #[external(v0)]
    fn enter_pending_akashic(ref self: ContractState, route_id: felt252) {
        let caller = starknet::get_caller_address();
        assert_relayer(ref self, caller);

        let state = self.escrow_state.read(route_id);
        assert!(state == HOLDING, 'Invalid state');
        self.escrow_state.write(route_id, PENDING_AKASHIC);
    }

    // ── Internal cascade revert (Gap 9) ──────────────────────────────────────
    fn _cascade_revert(ref self: ContractState, parent_route_id: felt252) {
        let parent_state = self.escrow_state.read(parent_route_id);
        if (parent_state != HOLDING && parent_state != PENDING_AKASHIC) {
            return;
        }
        self.escrow_state.write(parent_route_id, REVERTED);

        // Recursively cascade to grandparent
        let grandparent = self.escrow_parent.read(parent_route_id);
        if (grandparent != 0) {
            self._cascade_revert(grandparent);
        }
    }

    // ── View functions ───────────────────────────────────────────────────────
    #[external(v0)]
    fn get_state(ref self: ContractState, route_id: felt252) -> u8 {
        self.escrow_state.read(route_id)
    }

    #[external(v0)]
    fn get_amount(ref self: ContractState, route_id: felt252) -> u256 {
        self.escrow_amount.read(route_id)
    }

    #[external(v0)]
    fn get_lock_timestamp(ref self: ContractState, route_id: felt252) -> u64 {
        self.escrow_lock_timestamp.read(route_id)
    }

    #[external(v0)]
    fn is_coherence_verified(ref self: ContractState, route_id: felt252) -> bool {
        self.coherence_verified.read(route_id)
    }

    #[external(v0)]
    fn emergency_escape_available(ref self: ContractState, route_id: felt252) -> bool {
        let state = self.escrow_state.read(route_id);
        let lock_ts = self.escrow_lock_timestamp.read(route_id);
        let now = get_block_timestamp();
        (state == HOLDING || state == PENDING_AKASHIC)
            && now >= lock_ts + EMERGENCY_ESCAPE_SECONDS
    }
}
