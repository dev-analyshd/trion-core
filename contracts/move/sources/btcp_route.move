/// BTCP Route Tracking — Move VM implementation
module trion::btcp_route {
    use std::signer;

    struct Route has key {
        route_id: vector<u8>,
        anchor_bh: vector<u8>,   // 93-byte behavioral hash
        execution_bh: vector<u8>,
        entity_id: vector<u8>,
        gas_saved: u64,
        beo_continuity: u64,     // ×1e6
        cc_coherence: u64,       // ×1e6
        finalized: bool,
    }

    const E_NOT_FOUND: u64 = 1;

    public entry fun register_route(
        admin: &signer,
        route_id: vector<u8>,
        anchor_bh: vector<u8>,
        execution_bh: vector<u8>,
        entity_id: vector<u8>,
        gas_saved: u64,
        beo_continuity: u64,
        cc_coherence: u64,
    ) {
        let addr = signer::address_of(admin);
        move_to(admin, Route {
            route_id,
            anchor_bh,
            execution_bh,
            entity_id,
            gas_saved,
            beo_continuity,
            cc_coherence,
            finalized: false,
        });
    }

    public entry fun finalize(admin: &signer) acquires Route {
        let addr = signer::address_of(admin);
        assert!(exists<Route>(addr), E_NOT_FOUND);
        let r = borrow_global_mut<Route>(addr);
        r.finalized = true;
    }

    public fun get_route(addr: address): (vector<u8>, vector<u8>, u64, u64, bool) acquires Route {
        assert!(exists<Route>(addr), E_NOT_FOUND);
        let r = borrow_global<Route>(addr);
        (r.route_id, r.entity_id, r.gas_saved, r.cc_coherence, r.finalized)
    }
}
