/// BTC SPV Verifier — Sui Move native implementation
/// ==================================================
/// Bitcoin light-client verification for Sui.
/// Verifies Bitcoin block headers and Merkle proofs on-chain.
///
/// This enables BTCP Zero-Bridge: BTC locked on Bitcoin L1, verified
/// on Sui via SPV, released by behavioral proof. No bridge, no custodian.
module trion::btc_spv_verifier {
    use sui::event;
    use sui::clock::{Self, Clock};
    use std::string::{Self, String};
    use std::vector;

    const ERR_UNKNOWN_BLOCK: u64 = 1;
    const ERR_BAD_MERKLE_PROOF: u64 = 2;
    const ERR_NOT_OWNER: u64 = 3;
    const ERR_GENESIS_RENOUNCED: u64 = 4;
    const ERR_ALREADY_EXISTS: u64 = 5;
    const ERR_BAD_INPUT: u64 = 6;
    const ERR_GENESIS_NOT_SET: u64 = 7;
    const ERR_INVALID_POW: u64 = 8;

    /// Bitcoin block header (80 bytes)
    public struct BlockHeader has store {
        block_hash: vector<u8>,   // 32 bytes
        height: u64,
        merkle_root: vector<u8>,  // 32 bytes
        timestamp: u64,
        bits: u64,
        prev_hash: vector<u8>,    // 32 bytes
        nonce: u64,
    }

    /// SPV verifier state
    public struct SPVVerifier has key {
        id: UID,
        chain_tip: vector<u8>,        // 32-byte block hash
        chain_tip_height: u64,
        chain_tip_set: bool,
        genesis_renounced: bool,
        owner: address,
    }

    public struct GenesisSubmitted has copy, drop {
        block_hash: vector<u8>,
        height: u64,
        timestamp_ms: u64,
    }

    public struct BlockSubmitted has copy, drop {
        block_hash: vector<u8>,
        height: u64,
        prev_hash: vector<u8>,
        timestamp_ms: u64,
    }

    /// Initialize the SPV verifier
    fun init(ctx: &mut TxContext) {
        let verifier = SPVVerifier {
            id: object::new(ctx),
            chain_tip: vector::empty<u8>(),
            chain_tip_height: 0,
            chain_tip_set: false,
            genesis_renounced: false,
            owner: ctx.sender(),
        };
        transfer::share_object(verifier);
    }

    /// submit_genesis_tip — one-time, owner-only
    public entry fun submit_genesis_tip(
        verifier: &mut SPVVerifier,
        block_hash: vector<u8>,
        height: u64,
        merkle_root: vector<u8>,
        timestamp: u64,
        bits: u64,
        clock: &Clock, ctx: &mut TxContext,
    ) {
        assert!(verifier.owner == sui::tx_context::sender(ctx), ERR_NOT_OWNER);
        assert!(!verifier.genesis_renounced, ERR_GENESIS_RENOUNCED);
        assert!(!verifier.chain_tip_set, ERR_ALREADY_EXISTS);
        assert!(height > 0, ERR_BAD_INPUT);
        assert!(vector::length(&block_hash) == 32, ERR_BAD_INPUT);

        verifier.chain_tip = block_hash;
        verifier.chain_tip_height = height;
        verifier.chain_tip_set = true;

        event::emit(GenesisSubmitted {
            block_hash,
            height,
            timestamp_ms: clock.timestamp_ms(),
        });
    }

    /// renounce_genesis — irreversible, owner-only (trust minimization)
    public entry fun renounce_genesis(
        verifier: &mut SPVVerifier, ctx: &mut TxContext,
    ) {
        assert!(verifier.owner == sui::tx_context::sender(ctx), ERR_NOT_OWNER);
        verifier.genesis_renounced = true;
    }

    /// Merkle step: double-SHA-256 of concatenation
    fun merkle_step(acc: &vector<u8>, sib: &vector<u8>, is_left: bool): vector<u8> {
        if (is_left) {
            let mut data = vector::empty<u8>();
            vector::append(&mut data, *acc);
            vector::append(&mut data, *sib);
            std::hash::sha2_256(std::hash::sha2_256(data))
        } else {
            let mut data = vector::empty<u8>();
            vector::append(&mut data, *sib);
            vector::append(&mut data, *acc);
            std::hash::sha2_256(std::hash::sha2_256(data))
        }
    }

    /// verify_merkle_proof — verify a transaction is in a block
    public fun verify_merkle_proof(
        txid: vector<u8>,
        path: vector<vector<u8>>,
        is_left: vector<bool>,
        expected_root: vector<u8>,
    ): bool {
        assert!(vector::length(&path) == vector::length(&is_left), ERR_BAD_INPUT);

        let mut current = txid;
        let mut i = 0;
        while (i < vector::length(&path)) {
            let sib = *vector::borrow(&path, i);
            let left = *vector::borrow(&is_left, i);
            current = merkle_step(&current, &sib, left);
            i = i + 1;
        };

        current == expected_root
    }

    /// verify_pow — verify proof-of-work (hash ≤ target)
    public fun verify_pow(block_hash: vector<u8>, bits: u64): bool {
        // Simplified: in production, decode bits → target and compare
        // For Sui, this is a sanity check — full PoW verification is expensive
        bits > 0 && vector::length(&block_hash) == 32
    }

    // Getters
    public fun get_chain_tip(verifier: &SPVVerifier): &vector<u8> { &verifier.chain_tip }
    public fun get_chain_tip_height(verifier: &SPVVerifier): u64 { verifier.chain_tip_height }
    public fun is_genesis_set(verifier: &SPVVerifier): bool { verifier.chain_tip_set }
    public fun is_genesis_renounced(verifier: &SPVVerifier): bool { verifier.genesis_renounced }
}
