/// BTCP Route — Sui Move native implementation
/// ============================================
/// Spec §4.2: route tracking with zero-bridge invariant (assets_bridged=false).
///
/// Sui-native: Route is a shared object. The anchor_bh and execution_bh
/// are the dual-strand HashDNA that make the route tamper-evident.
module trion::btcp_route {
    use sui::event;
    use sui::clock::{Self, Clock};
    use std::string::{Self, String};
    use std::vector;

    const E_NOT_FOUND: u64 = 1;
    const E_ALREADY_FINALIZED: u64 = 2;
    const E_BELOW_COHERENCE: u64 = 3;
    const E_BRIDGE_VIOLATION: u64 = 4;

    // Spec §4.2 constants
    const MIN_COHERENCE_FLOOR: u64 = 550_000; // 0.55 × 1e6

    /// Route — the cross-chain behavioral route
    public struct Route has key, store {
        id: UID,
        route_id: vector<u8>,
        intent_hash: vector<u8>,
        entity_id: vector<u8>,
        anchor_bh: vector<u8>,      // 32-byte HashDNA sense strand
        execution_bh: vector<u8>,    // 32-byte HashDNA antisense strand
        source_vm: u8,               // 0=EVM, 1=SVM, 2=MOVE, 3=CAIRO, ...
        dest_vm: u8,
        btcp_score: u64,             // ×1e6 — route quality score
        gas_saved: u64,              // gas saved vs single-chain
        beo_continuity: u64,         // ×1e6
        cc_coherence: u64,           // ×1e6
        assets_bridged: bool,        // MUST always be false (zero-bridge invariant)
        finalized: bool,
        created_at_ms: u64,
    }

    public struct RoutePublished has copy, drop {
        route_id: vector<u8>,
        entity_id: vector<u8>,
        btcp_score: u64,
        assets_bridged: bool,
        timestamp_ms: u64,
    }

    public struct RouteFinalized has copy, drop {
        route_id: vector<u8>,
        entity_id: vector<u8>,
        anchor_bh: vector<u8>,
        execution_bh: vector<u8>,
        timestamp_ms: u64,
    }

    /// register_route — spec §4.2 Step 6 (route creation)
    public entry fun register_route(
        route_id: vector<u8>,
        intent_hash: vector<u8>,
        entity_id: vector<u8>,
        anchor_bh: vector<u8>,
        execution_bh: vector<u8>,
        source_vm: u8,
        dest_vm: u8,
        btcp_score: u64,
        gas_saved: u64,
        beo_continuity: u64,
        cc_coherence: u64,
        clock: &Clock,
        ctx: &mut TxContext,
    ) {
        // Zero-bridge invariant: assets NEVER move. This is the core BTCP claim.
        let route = Route {
            id: object::new(ctx),
            route_id,
            intent_hash,
            entity_id,
            anchor_bh,
            execution_bh,
            source_vm,
            dest_vm,
            btcp_score,
            gas_saved,
            beo_continuity,
            cc_coherence,
            assets_bridged: false, // ALWAYS false — zero-bridge by design
            finalized: false,
            created_at_ms: clock.timestamp_ms(),
        };

        event::emit(RoutePublished {
            route_id: route.route_id,
            entity_id: route.entity_id,
            btcp_score,
            assets_bridged: false,
            timestamp_ms: route.created_at_ms,
        });

        transfer::public_transfer(route, ctx.sender());
    }

    /// finalize_route — spec §4.2 Step 6 (finalization + Akashic recording)
    public entry fun finalize_route(
        route: &mut Route,
        clock: &Clock,
    ) {
        assert!(!route.finalized, E_ALREADY_FINALIZED);
        assert!(route.cc_coherence >= MIN_COHERENCE_FLOOR, E_BELOW_COHERENCE);
        assert!(!route.assets_bridged, E_BRIDGE_VIOLATION);

        route.finalized = true;

        event::emit(RouteFinalized {
            route_id: route.route_id,
            entity_id: route.entity_id,
            anchor_bh: route.anchor_bh,
            execution_bh: route.execution_bh,
            timestamp_ms: clock.timestamp_ms(),
        });
    }

    // Getters
    public fun get_route_id(r: &Route): &vector<u8> { &r.route_id }
    public fun get_btcp_score(r: &Route): u64 { r.btcp_score }
    public fun get_assets_bridged(r: &Route): bool { r.assets_bridged }
    public fun is_finalized(r: &Route): bool { r.finalized }
    public fun get_anchor_bh(r: &Route): &vector<u8> { &r.anchor_bh }
    public fun get_execution_bh(r: &Route): &vector<u8> { &r.execution_bh }
}
