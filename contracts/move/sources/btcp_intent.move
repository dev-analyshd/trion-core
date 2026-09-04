/// BTCP Intent Registry — Move VM implementation (Aptos)
/// =====================================================
/// Registry-pattern rewrite (DD finding 4.2 / Task 13-a).
///
/// Previously register_intent moved a single `Intent` resource under the
/// caller's account — exactly ONE intent per account (a second
/// register_intent aborted with RESOURCE_EXISTS), no shared registry, and
/// get_intent dropped `entity_id` from its return tuple.
///
/// Now mirrors trion::oracle's SignalRegistry fix (and the Solidity
/// `mapping(bytes32 => Intent)`): ONE shared `IntentRegistry` resource
/// under the module account @trion, keyed by unique intent_hash, with a
/// per-account index so an account can hold MANY intents. `entity_id` is
/// preserved in storage AND returned by the getters, and Aptos module
/// events are emitted on register/finalize.
module trion::btcp_intent {
    use std::signer;
    use std::vector;
    use aptos_framework::table::{Self, Table};
    use aptos_framework::event;
    use aptos_framework::timestamp;

    /// ── Errors ─────────────────────────────────────────────────────────
    const E_NOT_INITIALIZED:   u64 = 1;  // registry not created yet
    const E_ALREADY_INIT:      u64 = 2;  // registry already initialized
    const E_INTENT_EXISTS:     u64 = 3;  // intent_hash already registered
    const E_INTENT_NOT_FOUND:  u64 = 4;  // unknown intent_hash
    const E_NOT_OWNER:         u64 = 5;  // caller is not the intent's owner
    const E_ZERO_AMOUNT:       u64 = 6;  // zero-amount intent rejected
    const E_EMPTY_INTENT_HASH: u64 = 7;  // empty intent_hash rejected
    const E_EMPTY_ENTITY_ID:   u64 = 8;  // empty entity_id rejected
    const E_ALREADY_FINALIZED: u64 = 9;  // intent already finalized
    const E_NOT_MODULE_ACCOUNT: u64 = 10; // initialize called by non-@trion account

    /// One registered intent. `store` lets it live inside the registry
    /// table; it is no longer a top-level resource under each account.
    struct Intent has store {
        intent_hash:  vector<u8>,
        entity_id:    vector<u8>,    // BEO identity — preserved in storage AND getters
        source_chain: vector<u8>,
        dest_chain:   vector<u8>,
        amount:       u64,
        active:       bool,
        owner:        address,       // account that registered the intent
        created_at:   u64,
    }

    /// Shared registry — the single source of truth for BOTH register and
    /// read paths (same table handle), stored under the module account
    /// @trion so every caller shares one registry.
    struct IntentRegistry has key {
        intents:      Table<vector<u8>, Intent>,              // intent_hash → Intent
        intents_of:   Table<address, vector<vector<u8>>>,     // owner → intent hashes
        intent_count: u64,
    }

    /// ── Events (Aptos module events) ──────────────────────────────────
    #[event]
    struct IntentRegistered has drop, store {
        intent_hash: vector<u8>,
        entity_id:   vector<u8>,
        owner:       address,
        amount:      u64,
    }

    #[event]
    struct IntentFinalized has drop, store {
        intent_hash: vector<u8>,
        owner:       address,
    }

    /// ── Module init ───────────────────────────────────────────────────
    /// Called once by the module owner account (@trion) to create the
    /// shared registry. The signer pays for the table creation.
    public entry fun initialize(admin: &signer) {
        let addr = signer::address_of(admin);
        // Fail-closed: the registry MUST live under @trion — initializing
        // from any other account would silently brick every other entry
        // point (they all read the registry at @trion).
        assert!(addr == @trion, E_NOT_MODULE_ACCOUNT);
        assert!(!exists<IntentRegistry>(addr), E_ALREADY_INIT);
        move_to(admin, IntentRegistry {
            intents: table::new<vector<u8>, Intent>(admin),
            intents_of: table::new<address, vector<vector<u8>>>(admin),
            intent_count: 0,
        });
    }

    /// ── Register an intent ────────────────────────────────────────────
    /// Multiple intents per account are supported: the registry is keyed
    /// by unique intent_hash and indexes every hash under its owner.
    public entry fun register_intent(
        account: &signer,
        intent_hash: vector<u8>,
        entity_id: vector<u8>,
        source_chain: vector<u8>,
        dest_chain: vector<u8>,
        amount: u64,
    ) acquires IntentRegistry {
        let addr = signer::address_of(account);
        assert!(exists<IntentRegistry>(@trion), E_NOT_INITIALIZED);
        assert!(!vector::is_empty(&intent_hash), E_EMPTY_INTENT_HASH);
        assert!(!vector::is_empty(&entity_id), E_EMPTY_ENTITY_ID);
        assert!(amount > 0, E_ZERO_AMOUNT);

        let registry = borrow_global_mut<IntentRegistry>(@trion);
        assert!(
            !table::contains(&registry.intents, intent_hash),
            E_INTENT_EXISTS
        );

        table::add(&mut registry.intents, intent_hash, Intent {
            intent_hash,
            entity_id,
            source_chain,
            dest_chain,
            amount,
            active: true,
            owner: addr,
            created_at: timestamp::now_seconds(),
        });

        // Per-account index: append this hash to the owner's intent list.
        if (!table::contains(&registry.intents_of, addr)) {
            table::add(&mut registry.intents_of, addr, vector::empty<vector<u8>>());
        };
        vector::push_back(
            table::borrow_mut(&mut registry.intents_of, addr),
            intent_hash,
        );

        registry.intent_count = registry.intent_count + 1;

        event::emit(IntentRegistered {
            intent_hash,
            entity_id,
            owner: addr,
            amount,
        });
    }

    /// ── Finalize an intent (active → false) ───────────────────────────
    /// Only the intent's owner can finalize. Emits IntentFinalized.
    public entry fun finalize_intent(
        account: &signer,
        intent_hash: vector<u8>,
    ) acquires IntentRegistry {
        let addr = signer::address_of(account);
        assert!(exists<IntentRegistry>(@trion), E_NOT_INITIALIZED);

        let registry = borrow_global_mut<IntentRegistry>(@trion);
        assert!(
            table::contains(&registry.intents, intent_hash),
            E_INTENT_NOT_FOUND
        );
        let intent = table::borrow_mut(&mut registry.intents, intent_hash);
        assert!(intent.owner == addr, E_NOT_OWNER);
        assert!(intent.active, E_ALREADY_FINALIZED);
        intent.active = false;

        event::emit(IntentFinalized { intent_hash, owner: addr });
    }

    /// Backward-compatible alias for the old stub entry point — now
    /// registry-scoped (takes the intent hash) instead of account-scoped.
    public entry fun deactivate(account: &signer, intent_hash: vector<u8>) {
        finalize_intent(account, intent_hash);
    }

    /// ── View: read a registered intent by its unique intent_hash ──────
    /// Returns (entity_id, source_chain, dest_chain, amount, active).
    /// `entity_id` is returned — the old stub's getter dropped it.
    public fun get_intent(
        intent_hash: vector<u8>,
    ): (vector<u8>, vector<u8>, vector<u8>, u64, bool) acquires IntentRegistry {
        assert!(exists<IntentRegistry>(@trion), E_NOT_INITIALIZED);
        let registry = borrow_global<IntentRegistry>(@trion);
        assert!(
            table::contains(&registry.intents, intent_hash),
            E_INTENT_NOT_FOUND
        );
        let intent = table::borrow(&registry.intents, intent_hash);
        (
            intent.entity_id,
            intent.source_chain,
            intent.dest_chain,
            intent.amount,
            intent.active,
        )
    }

    /// ── View: the BEO entity_id of a registered intent ────────────────
    public fun get_entity_id(intent_hash: vector<u8>): vector<u8> acquires IntentRegistry {
        assert!(exists<IntentRegistry>(@trion), E_NOT_INITIALIZED);
        let registry = borrow_global<IntentRegistry>(@trion);
        assert!(
            table::contains(&registry.intents, intent_hash),
            E_INTENT_NOT_FOUND
        );
        table::borrow(&registry.intents, intent_hash).entity_id
    }

    /// ── View: all intent hashes registered by one account ─────────────
    public fun get_intents_of(owner: address): vector<vector<u8>> acquires IntentRegistry {
        assert!(exists<IntentRegistry>(@trion), E_NOT_INITIALIZED);
        let registry = borrow_global<IntentRegistry>(@trion);
        if (table::contains(&registry.intents_of, owner)) {
            *table::borrow(&registry.intents_of, owner)
        } else {
            vector::empty<vector<u8>>()
        }
    }

    /// ── View: total number of registered intents ──────────────────────
    public fun intent_count(): u64 acquires IntentRegistry {
        assert!(exists<IntentRegistry>(@trion), E_NOT_INITIALIZED);
        borrow_global<IntentRegistry>(@trion).intent_count
    }
}
