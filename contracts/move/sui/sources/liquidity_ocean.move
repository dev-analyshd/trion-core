/// Liquidity Ocean — Sui Move native implementation
/// =================================================
/// Spec §6.1: No asset has zero liquidity.
/// ocean_score = f(1/cost, 1/time, BEO_health)
///
/// Sui-native: Liquidity commitments are objects. The ocean aggregates
/// liquidity across VMs — a Sui DeFi protocol can access liquidity from
/// Ethereum, Solana, Bitcoin without moving assets.
module trion::liquidity_ocean {
    use sui::event;
    use sui::clock::{Self, Clock};
    use std::string::{Self, String};
    use std::vector;

    const E_ZERO_AMOUNT: u64 = 1;
    const E_EMPTY_ENTITY: u64 = 2;
    const E_ALREADY_SETTLED: u64 = 3;
    const E_BELOW_COHERENCE: u64 = 4;

    /// LiquidityCommitment — a commitment to provide liquidity
    public struct LiquidityCommitment has key, store {
        id: UID,
        commitment_id: vector<u8>,
        entity_id: vector<u8>,      // BEO identity of liquidity provider
        route_id: vector<u8>,        // associated BTCP route
        source_chain: u64,           // where the liquidity lives
        asset: String,               // asset identifier
        amount: u64,                 // committed amount
        cost_score: u64,             // 1/cost (×1e6) — higher = cheaper
        time_score: u64,             // 1/time (×1e6) — higher = faster
        beo_health: u64,            // BEO health score (×1e6)
        ocean_score: u64,            // computed: cost × time × beo_health (×1e6)
        settled: bool,
        reverted: bool,
        created_at_ms: u64,
    }

    public struct LiquidityCommitted has copy, drop {
        commitment_id: vector<u8>,
        entity_id: vector<u8>,
        route_id: vector<u8>,
        ocean_score: u64,
        timestamp_ms: u64,
    }

    public struct LiquiditySettled has copy, drop {
        commitment_id: vector<u8>,
        entity_id: vector<u8>,
        coherence: u64,
        execution_bh: vector<u8>,
        timestamp_ms: u64,
    }

    public struct LiquidityReverted has copy, drop {
        commitment_id: vector<u8>,
        reason: String,
        timestamp_ms: u64,
    }

    /// commit_liquidity — spec §6.1: register a liquidity commitment
    public entry fun commit_liquidity(
        entity_id: vector<u8>,
        route_id: vector<u8>,
        source_chain: u64,
        asset: String,
        amount: u64,
        cost_score: u64,    // 1/cost ×1e6
        time_score: u64,    // 1/time ×1e6
        beo_health: u64,    // BEO health ×1e6
        clock: &Clock,
        ctx: &mut TxContext,
    ): vector<u8> {
        assert!(amount > 0, E_ZERO_AMOUNT);
        assert!(vector::length(&entity_id) > 0, E_EMPTY_ENTITY);

        let commitment_id = std::hash::sha3_256(route_id);
        let timestamp_ms = clock.timestamp_ms();

        // ocean_score = cost_score × time_score × beo_health / 1e12
        // (scaled by 1e6 each, so divide by 1e12 to keep in ×1e6 range)
        let ocean_score = (cost_score * time_score) / 1_000_000;
        let ocean_score = (ocean_score * beo_health) / 1_000_000;

        let commitment = LiquidityCommitment {
            id: object::new(ctx),
            commitment_id,
            entity_id,
            route_id,
            source_chain,
            asset,
            amount,
            cost_score,
            time_score,
            beo_health,
            ocean_score,
            settled: false,
            reverted: false,
            created_at_ms: timestamp_ms,
        };

        event::emit(LiquidityCommitted {
            commitment_id,
            entity_id,
            route_id,
            ocean_score,
            timestamp_ms,
        });

        transfer::public_transfer(commitment, ctx.sender());
        commitment_id
    }

    /// settle_commitment — spec §6.1: settle the liquidity (route executed)
    public entry fun settle_commitment(
        commitment: &mut LiquidityCommitment,
        coherence: u64,
        execution_bh: vector<u8>,
        clock: &Clock,
    ) {
        assert!(!commitment.settled && !commitment.reverted, E_ALREADY_SETTLED);
        assert!(coherence >= 550_000, E_BELOW_COHERENCE);

        commitment.settled = true;

        event::emit(LiquiditySettled {
            commitment_id: commitment.commitment_id,
            entity_id: commitment.entity_id,
            coherence,
            execution_bh,
            timestamp_ms: clock.timestamp_ms(),
        });
    }

    /// revert_commitment — spec §6.1: revert the liquidity (route failed)
    public entry fun revert_commitment(
        commitment: &mut LiquidityCommitment,
        reason: String,
        clock: &Clock,
    ) {
        assert!(!commitment.settled && !commitment.reverted, E_ALREADY_SETTLED);
        commitment.reverted = true;

        event::emit(LiquidityReverted {
            commitment_id: commitment.commitment_id,
            reason,
            timestamp_ms: clock.timestamp_ms(),
        });
    }

    // Getters
    public fun get_ocean_score(c: &LiquidityCommitment): u64 { c.ocean_score }
    public fun get_amount(c: &LiquidityCommitment): u64 { c.amount }
    public fun get_entity_id(c: &LiquidityCommitment): &vector<u8> { &c.entity_id }
    public fun is_settled(c: &LiquidityCommitment): bool { c.settled }
}
