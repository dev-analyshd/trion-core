/// AI Agent Safety — Sui Move native implementation
/// =================================================
/// Spec: Love Protocol — multiplicative structural ethics.
/// F = PA · ICE · AS · Love
/// Love = 0 → F = 0 (kill switch)
///
/// Sui-native: every AI agent gets a behavioral credential. If the agent's
/// behavior becomes harmful, Love=0 kills it instantly — it can't access
/// resources.
module trion::ai_agent_safety {
    use sui::event;
    use sui::clock::{Self, Clock};
    use std::string::{Self, String};
    use std::vector;

    const E_ZERO_AGENT: u64 = 1;
    const E_KILLED: u64 = 2;
    const E_NOT_AUTHORIZED: u64 = 3;

    /// AgentCredential — the behavioral credential for an AI agent
    public struct AgentCredential has key, store {
        id: UID,
        agent_id: vector<u8>,        // SHA3-256 of agent identifier
        beo_hash: vector<u8>,         // BEO identity of the agent owner
        pa_score: u64,               // Performance Accuracy (×1e6)
        ice_score: u64,              // Information Coherence Entropy (×1e6)
        as_score: u64,               // Attack Surface (×1e6)
        love_score: u64,             // Love Protocol score (×1e6) — kill switch
        fitness: u64,                // F = PA·ICE·AS·Love (×1e6)
        killed: bool,                // if true, agent is killed
        kill_reason: String,
        created_at_ms: u64,
        last_evaluated_ms: u64,
    }

    public struct AgentRegistered has copy, drop {
        agent_id: vector<u8>,
        beo_hash: vector<u8>,
        fitness: u64,
        timestamp_ms: u64,
    }

    public struct AgentKilled has copy, drop {
        agent_id: vector<u8>,
        reason: String,
        timestamp_ms: u64,
    }

    public struct AgentEvaluated has copy, drop {
        agent_id: vector<u8>,
        love_score: u64,
        fitness: u64,
        timestamp_ms: u64,
    }

    /// register_agent — create a new AI agent credential
    public entry fun register_agent(
        agent_id: vector<u8>,
        beo_hash: vector<u8>,
        pa_score: u64,
        ice_score: u64,
        as_score: u64,
        love_score: u64,
        clock: &Clock,
        ctx: &mut TxContext,
    ) {
        assert!(vector::length(&agent_id) > 0, E_ZERO_AGENT);
        assert!(vector::length(&beo_hash) > 0, E_ZERO_AGENT);

        let timestamp_ms = clock.timestamp_ms();

        // F = PA · ICE · AS · Love (all ×1e6, so divide by 1e18 to normalize)
        let fitness = (pa_score * ice_score) / 1_000_000;
        let fitness = (fitness * as_score) / 1_000_000;
        let fitness = (fitness * love_score) / 1_000_000;

        // Love = 0 → F = 0 (kill switch)
        let killed = love_score == 0;

        let credential = AgentCredential {
            id: object::new(ctx),
            agent_id,
            beo_hash,
            pa_score,
            ice_score,
            as_score,
            love_score,
            fitness,
            killed,
            kill_reason: if (killed) { string::utf8(b"Love=0 — agent killed by Love Protocol kill switch") } else { string::utf8(b"") },
            created_at_ms: timestamp_ms,
            last_evaluated_ms: timestamp_ms,
        };

        event::emit(AgentRegistered {
            agent_id,
            beo_hash,
            fitness,
            timestamp_ms,
        });

        if (killed) {
            event::emit(AgentKilled {
                agent_id,
                reason: string::utf8(b"Love=0 at registration — agent refused entry"),
                timestamp_ms,
            });
        };

        transfer::public_transfer(credential, ctx.sender());
    }

    /// evaluate_agent — re-evaluate the agent's fitness
    public entry fun evaluate_agent(
        credential: &mut AgentCredential,
        love_score: u64,
        clock: &Clock,
    ) {
        assert!(!credential.killed, E_KILLED);

        credential.love_score = love_score;
        credential.last_evaluated_ms = clock.timestamp_ms();

        // Recompute F = PA · ICE · AS · Love
        let fitness = (credential.pa_score * credential.ice_score) / 1_000_000;
        let fitness = (fitness * credential.as_score) / 1_000_000;
        let fitness = (fitness * love_score) / 1_000_000;
        credential.fitness = fitness;

        // Love = 0 → kill
        if (love_score == 0) {
            credential.killed = true;
            credential.kill_reason = string::utf8(b"Love dropped to 0 — agent killed by Love Protocol");

            event::emit(AgentKilled {
                agent_id: credential.agent_id,
                reason: string::utf8(b"Love=0 during evaluation"),
                timestamp_ms: credential.last_evaluated_ms,
            });
        };

        event::emit(AgentEvaluated {
            agent_id: credential.agent_id,
            love_score,
            fitness,
            timestamp_ms: credential.last_evaluated_ms,
        });
    }

    /// kill_agent — manually kill an agent (emergency)
    public entry fun kill_agent(
        credential: &mut AgentCredential,
        reason: String,
        clock: &Clock,
    ) {
        assert!(!credential.killed, E_KILLED);
        credential.killed = true;
        credential.love_score = 0;
        credential.fitness = 0;
        credential.kill_reason = reason;

        event::emit(AgentKilled {
            agent_id: credential.agent_id,
            reason,
            timestamp_ms: clock.timestamp_ms(),
        });
    }

    // Getters
    public fun get_fitness(c: &AgentCredential): u64 { c.fitness }
    public fun get_love_score(c: &AgentCredential): u64 { c.love_score }
    public fun is_killed(c: &AgentCredential): bool { c.killed }
    public fun get_agent_id(c: &AgentCredential): &vector<u8> { &c.agent_id }
    public fun get_beo_hash(c: &AgentCredential): &vector<u8> { &c.beo_hash }

    /// can_access_resources — the kill switch check
    /// Agents with fitness=0 cannot access resources.
    public fun can_access_resources(c: &AgentCredential): bool {
        !c.killed && c.fitness > 0
    }
}
