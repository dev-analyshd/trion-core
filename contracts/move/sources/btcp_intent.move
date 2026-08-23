/// BTCP Intent Registry — Move VM implementation
module trion::btcp_intent {
    use std::signer;
    use std::vector;

    struct Intent has key {
        intent_hash: vector<u8>,
        entity_id: vector<u8>,
        source_chain: vector<u8>,
        dest_chain: vector<u8>,
        amount: u64,
        active: bool,
    }

    const E_NOT_FOUND: u64 = 1;

    public entry fun register_intent(
        admin: &signer,
        intent_hash: vector<u8>,
        entity_id: vector<u8>,
        source_chain: vector<u8>,
        dest_chain: vector<u8>,
        amount: u64,
    ) {
        let addr = signer::address_of(admin);
        move_to(admin, Intent {
            intent_hash,
            entity_id,
            source_chain,
            dest_chain,
            amount,
            active: true,
        });
    }

    public fun get_intent(addr: address): (vector<u8>, vector<u8>, vector<u8>, u64, bool) acquires Intent {
        assert!(exists<Intent>(addr), E_NOT_FOUND);
        let i = borrow_global<Intent>(addr);
        (i.intent_hash, i.source_chain, i.dest_chain, i.amount, i.active)
    }

    public entry fun deactivate(admin: &signer) acquires Intent {
        let addr = signer::address_of(admin);
        assert!(exists<Intent>(addr), E_NOT_FOUND);
        let i = borrow_global_mut<Intent>(addr);
        i.active = false;
    }
}
