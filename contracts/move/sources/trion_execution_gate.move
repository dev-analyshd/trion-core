/// TRION Execution Gate — Move VM implementation
/// Behavioral pre-execution firewall
module trion::execution_gate {
    use std::signer;

    struct Gate has key {
        paused: bool,
        min_coherence: u64,     // ×1e6
        min_threshold: u64,     // ×1e6
    }

    const E_PAUSED: u64 = 1;
    const E_COHERENCE_LOW: u64 = 2;

    public entry fun initialize(admin: &signer) {
        move_to(admin, Gate { paused: false, min_coherence: 550000, min_threshold: 550000 });
    }

    public fun check_execution(entity_coherence: u64, entity_threshold: u64): bool acquires Gate {
        // In production, this reads from a config resource
        // Simplified: coherence must be >= threshold
        entity_coherence >= entity_threshold
    }

    public entry fun pause(admin: &signer) acquires Gate {
        let addr = signer::address_of(admin);
        assert!(exists<Gate>(addr), E_PAUSED);
        let g = borrow_global_mut<Gate>(addr);
        g.paused = true;
    }

    public entry fun unpause(admin: &signer) acquires Gate {
        let addr = signer::address_of(admin);
        assert!(exists<Gate>(addr), E_PAUSED);
        let g = borrow_global_mut<Gate>(addr);
        g.paused = false;
    }
}
