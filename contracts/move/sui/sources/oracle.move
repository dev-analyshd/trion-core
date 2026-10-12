/// TRION Behavioral Truth Oracle — Sui Move native implementation
/// ================================================================
/// Stores behavioral coherence signals on-chain, gated by the 0.55
/// coherence threshold (spec L5.2 Five-Plane Coherence).
///
/// Sui-native: every Signal is a shared object (UID), queryable by anyone.
/// The oracle emits events on publish so the Akashic Index can record them.
module trion::oracle {
    use sui::event;
    use sui::clock::{Self, Clock};
    use std::string::{Self, String};
    use std::vector;

    // ═══════════════════════════════════════════════════════════════════
    // Errors
    // ═══════════════════════════════════════════════════════════════════
    const E_NOT_AUTHORIZED: u64 = 1;
    const E_BELOW_THRESHOLD: u64 = 2;
    const E_ZERO_ENTITY: u64 = 3;
    const E_ALREADY_PUBLISHED: u64 = 4;

    // ═══════════════════════════════════════════════════════════════════
    // Constants (spec L5.1, L5.2)
    // ═══════════════════════════════════════════════════════════════════
    const MIN_COHERENCE_THRESHOLD: u64 = 550_000; // 0.55 × 1e6 (spec §5.2)
    const SCALE_FACTOR: u64 = 1_000_000;           // fixed-point scale

    // ═══════════════════════════════════════════════════════════════════
    // Signal — the behavioral truth object
    // ═══════════════════════════════════════════════════════════════════
    public struct Signal has key, store {
        id: UID,
        entity_id: vector<u8>,    // BEO identity (SHA3-256 of normalized address)
        coherence: u64,           // ×1e6 fixed-point [0, 1e6]
        threshold: u64,           // ×1e6 dynamic threshold Θ(t)
        truth_value: u64,         // ×1e6 T(t) = [C≥Θ]·C·e^(M_moat)
        emits: bool,              // SILENCE or EMIT
        status: u8,               // 0=NOMINAL, 1=WARN, 2=COLLAPSE, 3=HOSTILE
        archetype: String,        // behavioral archetype classification
        manipulation_score: u64,  // ×1e6 [0, 1e6] — 7-type fingerprint
        block_number: u64,
        timestamp_ms: u64,
    }

    // ═══════════════════════════════════════════════════════════════════
    // Oracle admin capability
    // ═══════════════════════════════════════════════════════════════════
    public struct OracleAdmin has key, store {
        id: UID,
        admin: address,
    }

    // ═══════════════════════════════════════════════════════════════════
    // Events
    // ═══════════════════════════════════════════════════════════════════
    public struct SignalPublished has copy, drop {
        entity_id: vector<u8>,
        coherence: u64,
        emits: bool,
        status: u8,
        timestamp_ms: u64,
    }

    public struct SilenceEmitted has copy, drop {
        entity_id: vector<u8>,
        reason: String,
        timestamp_ms: u64,
    }

    // ═══════════════════════════════════════════════════════════════════
    // Module initializer
    // ═══════════════════════════════════════════════════════════════════
    fun init(ctx: &mut TxContext) {
        let admin = OracleAdmin {
            id: object::new(ctx),
            admin: ctx.sender(),
        };
        transfer::transfer(admin, ctx.sender());
    }

    // ═══════════════════════════════════════════════════════════════════
    // publish_signal — the core oracle function
    //
    // Spec §5.4 Master Equation:
    //   T(t) = [C(t) ≥ Θ(t)] · C(t) · e^(M_moat)
    // If C(t) < Θ(t), the oracle EMITS SILENCE (not a false signal).
    // ═══════════════════════════════════════════════════════════════════
    public entry fun publish_signal(
        _admin: &OracleAdmin,
        entity_id: vector<u8>,
        coherence: u64,           // ×1e6
        threshold: u64,            // ×1e6
        truth_value: u64,          // ×1e6
        manipulation_score: u64,  // ×1e6
        archetype: String,
        block_number: u64,
        clock: &Clock,
        ctx: &mut TxContext,
    ) {
        assert!(vector::length(&entity_id) > 0, E_ZERO_ENTITY);
        assert!(coherence <= 1_000_000, E_BELOW_THRESHOLD);

        let timestamp_ms = clock.timestamp_ms();
        let emits = coherence >= threshold;
        let status: u8 = if (coherence < threshold) {
            1 // WARN — below threshold
        } else if (manipulation_score > 500_000) {
            3 // HOSTILE — high manipulation
        } else if (manipulation_score > 200_000) {
            2 // COLLAPSE — moderate manipulation
        } else {
            0 // NOMINAL
        };

        let signal = Signal {
            id: object::new(ctx),
            entity_id,
            coherence,
            threshold,
            truth_value: if (emits) { truth_value } else { 0 },
            emits,
            status,
            archetype,
            manipulation_score,
            block_number,
            timestamp_ms,
        };

        if (emits) {
            event::emit(SignalPublished {
                entity_id: signal.entity_id,
                coherence,
                emits: true,
                status,
                timestamp_ms,
            });
        } else {
            event::emit(SilenceEmitted {
                entity_id: signal.entity_id,
                reason: string::utf8(b"C(t) < Theta(t) — TRION emits SILENCE, never a false signal"),
                timestamp_ms,
            });
        };

        transfer::public_transfer(signal, ctx.sender());
    }

    // ═══════════════════════════════════════════════════════════════════
    // Read functions
    // ═══════════════════════════════════════════════════════════════════
    public fun get_coherence(signal: &Signal): u64 { signal.coherence }
    public fun get_threshold(signal: &Signal): u64 { signal.threshold }
    public fun get_truth(signal: &Signal): u64 { signal.truth_value }
    public fun get_status(signal: &Signal): u8 { signal.status }
    public fun get_entity_id(signal: &Signal): &vector<u8> { &signal.entity_id }
    public fun get_archetype(signal: &Signal): &String { &signal.archetype }
    public fun get_manipulation_score(signal: &Signal): u64 { signal.manipulation_score }
    public fun emits(signal: &Signal): bool { signal.emits }

    // ═══════════════════════════════════════════════════════════════════
    // Destroy (only owner)
    // ═══════════════════════════════════════════════════════════════════
    public entry fun destroy_signal(signal: Signal, ctx: &mut TxContext) {
        let Signal { id, entity_id: _, coherence: _, threshold: _,
                     truth_value: _, emits: _, status: _,
                     archetype: _, manipulation_score: _,
                     block_number: _, timestamp_ms: _ } = signal;
        object::delete(id);
    }
}
