/// TRION Behavioral Truth Oracle — Move VM implementation
/// Stores behavioral signals, gated by coherence threshold
///
/// STORAGE MODEL (SECURITY FIX, P1): publish and read share ONE table.
/// Previously `publish_signal` moved a single global `Signal` resource under
/// the ADMIN's address (overwriting it on every publish) while `get_signal`
/// read `Signal` at the ENTITY's address — storage that was never written —
/// so every read aborted with E_SIGNAL_NOT_FOUND. Both paths now use the
/// `SignalRegistry` table (keyed by entity_id, stored under the oracle/admin
/// account), mirroring the Solidity `mapping(bytes32 => Signal)`.
module trion::oracle {
    use std::signer;
    use aptos_framework::coin;
    use aptos_framework::account;
    use aptos_framework::table::{Self, Table};

    /// Behavioral signal stored on-chain.
    /// `store` (added by the P1 fix) lets it live inside the registry table;
    /// `key` is retained for layout compatibility with pre-fix resource state.
    struct Signal has key, store {
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

    /// Per-entity signal registry under the oracle (admin) account.
    /// Single source of truth for BOTH publish_signal and get_signal /
    /// is_execution_safe — same table handle, same value type.
    struct SignalRegistry has key {
        signals: Table<vector<u8>, Signal>,
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
        move_to(admin, SignalRegistry {
            signals: table::new<vector<u8>, Signal>(admin),
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
    ) acquires Config, SignalRegistry {
        let addr = signer::address_of(admin);
        assert!(exists<Config>(addr), E_NOT_AUTHORIZED);
        {
            let config = borrow_global<Config>(addr);
            assert!(addr == config.admin, E_NOT_AUTHORIZED);
        };

        // AWA enforcement check
        assert!(awa_enforced(addr), E_AWA_NOT_ENFORCED);

        // Lazily create the registry for modules initialized before the
        // storage fix (Config exists, SignalRegistry does not).
        if (!exists<SignalRegistry>(addr)) {
            move_to(admin, SignalRegistry {
                signals: table::new<vector<u8>, Signal>(admin),
            });
        };

        let registry = borrow_global_mut<SignalRegistry>(addr);
        if (table::contains(&registry.signals, entity_id)) {
            let sig = table::borrow_mut(&mut registry.signals, entity_id);
            sig.entity_id = entity_id;
            sig.coherence = coherence;
            sig.threshold = threshold;
            sig.emits = emits;
            sig.status = status;
            sig.truth = truth;
            sig.block_number = 0; // set by caller
            sig.timestamp = 0;
        } else {
            table::add(&mut registry.signals, entity_id, Signal {
                entity_id,
                coherence,
                threshold,
                emits,
                status,
                truth,
                block_number: 0, // set by caller
                timestamp: 0,
            });
        };
    }

    /// Read the current signal for an entity.
    /// `oracle` is the address of the oracle (admin) account that owns the
    /// SignalRegistry — the exact table publish_signal writes to.
    public fun get_signal(oracle: address, entity_id: vector<u8>): (vector<u8>, u64, u64, bool, u8, u64) acquires SignalRegistry {
        assert!(exists<SignalRegistry>(oracle), E_SIGNAL_NOT_FOUND);
        let registry = borrow_global<SignalRegistry>(oracle);
        assert!(table::contains(&registry.signals, entity_id), E_SIGNAL_NOT_FOUND);
        let sig = table::borrow(&registry.signals, entity_id);
        (sig.entity_id, sig.coherence, sig.threshold, sig.emits, sig.status, sig.truth)
    }

    /// Check if execution is safe for an entity (fail-closed when unknown)
    public fun is_execution_safe(oracle: address, entity_id: vector<u8>): bool acquires SignalRegistry {
        if (!exists<SignalRegistry>(oracle)) return false;
        let registry = borrow_global<SignalRegistry>(oracle);
        if (!table::contains(&registry.signals, entity_id)) return false;
        let sig = table::borrow(&registry.signals, entity_id);
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
