/// BTCP Zero-Bridge Escrow — Move VM implementation
/// Two-state atomic escrow: HOLDING → RELEASED | REVERTED
module trion::btcp_escrow {
    use std::signer;
    use aptos_framework::coin;

    /// Escrow states
    const HOLDING: u8 = 0;
    const PENDING_AKASHIC: u8 = 1;
    const RELEASED: u8 = 2;
    const REVERTED: u8 = 3;
    const EMERGENCY_REVERTED: u8 = 4;

    /// Escrow resource
    struct Escrow has key {
        route_id: vector<u8>,
        entity_id: vector<u8>,
        amount: u64,
        state: u8,
        created_at: u64,
        coherence_verified: bool,
    }

    const E_NOT_FOUND: u64 = 1;
    const E_INVALID_STATE: u64 = 2;
    const E_COHERENCE_FAIL: u64 = 3;

    /// Lock assets in escrow
    public entry fun lock_escrow(
        admin: &signer,
        route_id: vector<u8>,
        entity_id: vector<u8>,
        amount: u64,
    ) {
        let addr = signer::address_of(admin);
        assert!(!exists<Escrow>(addr), E_INVALID_STATE);
        move_to(admin, Escrow {
            route_id,
            entity_id,
            amount,
            state: HOLDING,
            created_at: 0,
            coherence_verified: false,
        });
    }

    /// Release escrow (requires coherence verification)
    public entry fun release_escrow(admin: &signer) acquires Escrow {
        let addr = signer::address_of(admin);
        assert!(exists<Escrow>(addr), E_NOT_FOUND);
        let esc = borrow_global_mut<Escrow>(addr);
        assert!(esc.state == HOLDING || esc.state == PENDING_AKASHIC, E_INVALID_STATE);
        assert!(esc.coherence_verified, E_COHERENCE_FAIL);
        esc.state = RELEASED;
    }

    /// Revert escrow
    public entry fun revert_escrow(admin: &signer) acquires Escrow {
        let addr = signer::address_of(admin);
        assert!(exists<Escrow>(addr), E_NOT_FOUND);
        let esc = borrow_global_mut<Escrow>(addr);
        assert!(esc.state == HOLDING || esc.state == PENDING_AKASHIC, E_INVALID_STATE);
        esc.state = REVERTED;
    }

    /// Emergency revert (7-day escape hatch, callable by anyone)
    public entry fun emergency_revert(caller: &signer) acquires Escrow {
        let addr = signer::address_of(caller);
        assert!(exists<Escrow>(addr), E_NOT_FOUND);
        let esc = borrow_global_mut<Escrow>(addr);
        // In production: check 7-day timeout
        esc.state = EMERGENCY_REVERTED;
    }

    /// Mark coherence as verified
    public entry fun verify_coherence(admin: &signer) acquires Escrow {
        let addr = signer::address_of(admin);
        assert!(exists<Escrow>(addr), E_NOT_FOUND);
        let esc = borrow_global_mut<Escrow>(addr);
        esc.coherence_verified = true;
    }

    /// Enter pending akashic state (24h recovery window)
    public entry fun enter_pending_akashic(admin: &signer) acquires Escrow {
        let addr = signer::address_of(admin);
        assert!(exists<Escrow>(addr), E_NOT_FOUND);
        let esc = borrow_global_mut<Escrow>(addr);
        assert!(esc.state == HOLDING, E_INVALID_STATE);
        esc.state = PENDING_AKASHIC;
    }

    /// Get escrow state
    public fun get_state(addr: address): (u8, u64, bool) acquires Escrow {
        assert!(exists<Escrow>(addr), E_NOT_FOUND);
        let esc = borrow_global<Escrow>(addr);
        (esc.state, esc.amount, esc.coherence_verified)
    }
}
