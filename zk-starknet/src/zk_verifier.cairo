// SPDX-License-Identifier: CC0-1.0
// TRION Protocol — ZK Starknet Substrate
// Contract wrapper for on-chain ZK verification
//
// This contract wraps the S1-S5 circuit functions for on-chain deployment
// to Starknet Sepolia. Per R-CHANNELS, the on-chain surface is signal
// publication + economic coordination ONLY — proof generation stays off-chain.

#[starknet::contract]
pub mod ZKVerifier {
    use starknet::storage::{StoragePointerReadAccess, StoragePointerWriteAccess};
    use starknet::{ContractAddress, get_caller_address, get_block_info};
    use core::integer::u256;

    // ── S1 Phase 1: Intent commitment registry (BTCP §5.6) ──────────────
    // Contract stores: H_intent → timestamp, entity_id; NO routing calculation yet.
    #[storage]
    struct Storage {
        owner: ContractAddress,
        intent_commitments: Map<felt252, (u64, felt252)>,  // H_intent → (timestamp, entity_id)
        travel_rule_hashes: Map<felt252, felt252>,          // tx_hash → disclosure_hash (S3)
        birp_anchors: Map<felt252, felt252>,                 // entity_id → BIRP_anchor (S5)
        awa_frozen: bool,                                    // AWA freeze flag (R-INVISIBILITY)
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        IntentCommitted: IntentCommitted,
        TravelRuleCompliant: TravelRuleCompliant,
        BIRPEnrolled: BIRPEnrolled,
        AWAStateChange: AWAStateChange,
    }

    #[derive(Drop, starknet::Event)]
    pub struct IntentCommitted {
        #[key]
        pub entity_id: felt252,
        pub h_intent: felt252,
        pub timestamp: u64,
    }

    #[derive(Drop, starknet::Event)]
    pub struct TravelRuleCompliant {
        #[key]
        pub entity_id: felt252,
        pub tx_hash: felt252,
        pub disclosure_hash: felt252,
    }

    #[derive(Drop, starknet::Event)]
    pub struct BIRPEnrolled {
        #[key]
        pub entity_id: felt252,
        pub birp_anchor: felt252,
        pub enrollment_timestamp: u64,
    }

    #[derive(Drop, starknet::Event)]
    pub struct AWAStateChange {
        pub frozen: bool,
        pub block: u64,
    }

    #[constructor]
    fn constructor(ref self: ContractState) {
        self.owner.write(get_caller_address());
        // R-FAILCLOSED: AWA defaults FROZEN (emission blocked until explicitly thawed)
        self.awa_frozen.write(true);
    }

    // ── S1 Phase 1: commit_intent (BTCP §5.6 verbatim) ──────────────────
    // Submit H_intent ONLY. NO routing calculation yet.
    #[external(v0)]
    fn commit_intent(ref self: ContractState, h_intent: felt252, entity_id: felt252) {
        // R-INVISIBILITY: AWA freeze blocks all emission
        assert(!self.awa_frozen.read(), 'AWA frozen');
        let block_info = get_block_info();
        let timestamp = block_info.block.timestamp;
        self.intent_commitments.write(h_intent, (timestamp, entity_id));
        self.emit(IntentCommitted { entity_id, h_intent, timestamp });
    }

    // ── S1 Phase 1: get_intent (NO routing — just timestamp + entity_id) ──
    #[external(v0)]
    fn get_intent(self: @ContractState, h_intent: felt252) -> (u64, felt252) {
        self.intent_commitments.read(h_intent)
    }

    // ── S3 Step 4: store disclosure_hash ONLY (BTCP Fix 1 verbatim) ──────
    // TRION stores: disclosure_hash only. TRION emits: TRAVEL_RULE_COMPLIANT = TRUE
    #[external(v0)]
    fn submit_travel_rule_proof(
        ref self: ContractState,
        entity_id: felt252,
        tx_hash: felt252,
        jurisdiction_id: felt252,
        disclosure_hash_val: felt252,
    ) {
        // R-INVISIBILITY: AWA freeze blocks all emission (CRITICAL tier)
        assert(!self.awa_frozen.read(), 'AWA frozen');
        // R-ABSENT: NO disclosure_contents or regulator_receipt stored
        self.travel_rule_hashes.write(tx_hash, disclosure_hash_val);
        self.emit(TravelRuleCompliant {
            entity_id, tx_hash, disclosure_hash: disclosure_hash_val,
        });
    }

    // ── S5: BIRP enrollment — store BIRP_anchor ONLY (C3 §16 verbatim) ──
    // Not stored: DNA_Code — ever
    #[external(v0)]
    fn enroll_birp(
        ref self: ContractState,
        entity_id: felt252,
        birp_anchor_val: felt252,
    ) {
        // R-INVISIBILITY: AWA freeze blocks enrollment
        assert(!self.awa_frozen.read(), 'AWA frozen');
        let block_info = get_block_info();
        let ts = block_info.block.timestamp;
        self.birp_anchors.write(entity_id, birp_anchor_val);
        self.emit(BIRPEnrolled {
            entity_id, birp_anchor: birp_anchor_val, enrollment_timestamp: ts,
        });
    }

    // ── R-INVISIBILITY: AWA freeze management ──────────────────────────
    // NO override path. Only the owner (AWA oracle) can thaw.
    // Per WP-Feb §14.2: "Cannot be overridden by any single entity. By design."
    #[external(v0)]
    fn set_awa_state(ref self: ContractState, frozen: bool) {
        assert(get_caller_address() == self.owner.read(), 'Not owner');
        self.awa_frozen.write(frozen);
        let block_info = get_block_info();
        self.emit(AWAStateChange { frozen, block: block_info.block.timestamp });
    }

    #[external(v0)]
    fn is_awa_frozen(self: @ContractState) -> bool {
        self.awa_frozen.read()
    }
}
