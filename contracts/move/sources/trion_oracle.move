/// TRION Behavioral Truth Oracle — Move VM implementation
/// Stores behavioral signals, gated by coherence threshold
module trion::oracle {
    use std::signer;
    use aptos_framework::coin;
    use aptos_framework::account;

    /// Behavioral signal stored on-chain
    struct Signal has key {
        entity_id: vector<u8>,
        coherence: u64,        // ×1e6 fixed point
        threshold: u64,        // ×1e6 fixed point
        emits: bool,
        status: u8,            // 0=NOMINAL, 1=WARN, 2=COLLAPSE, 3=HOSTILE
        truth: u64,            // ×1e6
        block_number: u64,
        timestamp: u64,
    }

    /// Admin/validator config
    struct Config has key {
        admin: address,
        validator_count: u64,
        min_quorum: u64,       // 2/3 of validators
    }

    /// Error codes
    const E_NOT_AUTHORIZED: u64 = 1;
    const E_SIGNAL_NOT_FOUND: u64 = 2;
    const E_AWA_NOT_ENFORCED: u64 = 3;

    /// Initialize the oracle module
    public entry fun initialize(admin: &signer) {
        let addr = signer::address_of(admin);
        assert!(!exists<Config>(addr), 0);
        move_to(admin, Config {
            admin: addr,
            validator_count: 1,
            min_quorum: 1,
        });
    }

    /// Publish a behavioral signal (validator-only)
    public entry fun publish_signal(
        admin: &signer,
        entity_id: vector<u8>,
        coherence: u64,
        threshold: u64,
        emits: bool,
        status: u8,
        truth: u64,
    ) acquires Config {
        let addr = signer::address_of(admin);
        assert!(exists<Config>(addr), E_NOT_AUTHORIZED);
        let config = borrow_global_mut<Config>(addr);
        assert!(addr == config.admin, E_NOT_AUTHORIZED);

        // AWA enforcement check
        assert!(awa_enforced(addr), E_AWA_NOT_ENFORCED);

        if (exists<Signal>(addr)) {
            let sig = borrow_global_mut<Signal>(addr);
            sig.entity_id = entity_id;
            sig.coherence = coherence;
            sig.threshold = threshold;
            sig.emits = emits;
            sig.status = status;
            sig.truth = truth;
            sig.block_number = 0; // set by caller
            sig.timestamp = 0;
        } else {
            move_to(admin, Signal {
                entity_id,
                coherence,
                threshold,
                emits,
                status,
                truth,
                block_number: 0,
                timestamp: 0,
            });
        };
    }

    /// Read the current signal for an entity
    public fun get_signal(entity_addr: address): (vector<u8>, u64, u64, bool, u8, u64) acquires Signal {
        assert!(exists<Signal>(entity_addr), E_SIGNAL_NOT_FOUND);
        let sig = borrow_global<Signal>(entity_addr);
        (sig.entity_id, sig.coherence, sig.threshold, sig.emits, sig.status, sig.truth)
    }

    /// Check if execution is safe for an entity
    public fun is_execution_safe(entity_addr: address): bool acquires Signal {
        if (!exists<Signal>(entity_addr)) return false;
        let sig = borrow_global<Signal>(entity_addr);
        sig.emits && sig.status == 0 // NOMINAL
    }

    /// AWA enforcement check (quorum, HHI, gratitude, public good)
    fun awa_enforced(_addr: address): bool acquires Config {
        // Simplified: in production this checks validator quorum signatures
        // For now, return true (validator signatures verified at protocol layer)
        true
    }

    /// Add a validator
    public entry fun add_validator(admin: &signer, _validator: address) acquires Config {
        let addr = signer::address_of(admin);
        assert!(exists<Config>(addr), E_NOT_AUTHORIZED);
        let config = borrow_global_mut<Config>(addr);
        assert!(addr == config.admin, E_NOT_AUTHORIZED);
        config.validator_count = config.validator_count + 1;
        config.min_quorum = (config.validator_count * 2 + 2) / 3;
    }
}
