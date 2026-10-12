/// BEO Attestation — Sui Move native implementation
/// Spec §12.4: BEO Identity Continuity Across Chains.
module trion::beo_attestation {
    use sui::event;
    use sui::clock::{Self, Clock};
    use std::string::{Self, String};
    use std::vector;

    const E_EMPTY_ADDRESS: u64 = 1;
    const E_ALREADY_ATTESTED: u64 = 2;

    public struct BEOIdentity has key, store {
        id: UID,
        beo_hash: vector<u8>,
        native_address: String,
        chain_id: u64,
        attestation_count: u64,
        first_seen_ms: u64,
        last_updated_ms: u64,
    }

    public struct BEOAttested has copy, drop {
        beo_hash: vector<u8>,
        native_address: String,
        chain_id: u64,
        timestamp_ms: u64,
    }

    /// compute_beo_hash — SHA3-256 of the normalized address
    public fun compute_beo_hash(native_address: &String): vector<u8> {
        // Get bytes from the string
        let addr_bytes = *string::bytes(native_address);
        // Normalize: strip 0x prefix if present
        let len = vector::length(&addr_bytes);
        let mut normalized = vector::empty<u8>();
        let mut start = 0;
        if (len >= 2) {
            let first = *vector::borrow(&addr_bytes, 0);
            let second = *vector::borrow(&addr_bytes, 1);
            if (first == 0x30 && (second == 0x78 || second == 0x58)) {
                start = 2;
            };
        };
        let mut i = start;
        while (i < len) {
            vector::push_back(&mut normalized, *vector::borrow(&addr_bytes, i));
            i = i + 1;
        };
        std::hash::sha3_256(normalized)
    }

    public entry fun attest_beo(
        native_address: String,
        clock: &Clock,
        ctx: &mut TxContext,
    ): vector<u8> {
        assert!(string::length(&native_address) > 0, E_EMPTY_ADDRESS);

        let beo_hash = compute_beo_hash(&native_address);
        let timestamp_ms = clock.timestamp_ms();

        let mut identity = BEOIdentity {
            id: object::new(ctx),
            beo_hash,
            native_address: native_address,
            chain_id: 1,
            attestation_count: 1,
            first_seen_ms: timestamp_ms,
            last_updated_ms: timestamp_ms,
        };

        let sender = ctx.sender();
        let beo_hash_copy = identity.beo_hash;

        event::emit(BEOAttested {
            beo_hash: identity.beo_hash,
            native_address: identity.native_address,
            chain_id: 1,
            timestamp_ms,
        });

        transfer::public_transfer(identity, sender);
        beo_hash_copy
    }

    public fun verify_beo_continuity(
        beo_hash: vector<u8>,
        native_address: &String,
    ): bool {
        compute_beo_hash(native_address) == beo_hash
    }

    public fun get_beo_hash(identity: &BEOIdentity): &vector<u8> { &identity.beo_hash }
    public fun get_native_address(identity: &BEOIdentity): &String { &identity.native_address }
    public fun get_attestation_count(identity: &BEOIdentity): u64 { identity.attestation_count }
}
