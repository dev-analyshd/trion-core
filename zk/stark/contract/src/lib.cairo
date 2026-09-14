// SPDX-License-Identifier: CC0-1.0
// TRION Protocol — ZK Starknet Substrate v2 (HARDENED)
//
// Fixes from v1 (0x05613dd22...):
//   1. Zero-value input validation — rejects h_intent=0, entity_id=0, tx_hash=0, birp_anchor=0
//   2. Duplicate intent collision detection — committing same h_intent twice reverts
//   3. Duplicate BIRP enrollment detection — re-enrolling same entity reverts
//   4. Duplicate travel rule submission detection — same tx_hash reverts
//   5. AWA frozen default — true (fail-closed); owner can unfreeze via set_awa_state(false)
//
// Behavioral categories:
//   S1: commit_intent(h_intent, entity_id) — intent commitment registry
//   S2: get_intent(h_intent) — view committed intent
//   S3: submit_travel_rule_proof(entity_id, tx_hash, jurisdiction_id, disclosure_hash_val)
//   S4: enroll_birp(entity_id, birp_anchor_val)
//   S5: set_awa_state(frozen) — owner-only AWA freeze management
//   Hash_DNA: uses Pedersen hash mod felt252 prime (binding fits in felt252)
//   Adversarial: zero inputs → revert; duplicate inputs → revert; nonexistent fn → revert

#[starknet::contract]
pub mod ZKVerifier {
    use starknet::storage::{
        Map, StorageMapReadAccess, StorageMapWriteAccess,
        StoragePointerReadAccess, StoragePointerWriteAccess,
    };
    use starknet::{ContractAddress, get_caller_address, get_block_info};
    use core::pedersen;

    // ── S1 Phase 1: Intent commitment registry (BTCP §5.6) ──────────────
    #[derive(Drop, starknet::Store)]
    pub struct IntentCommitment {
        pub timestamp: u64,
        pub entity_id: felt252,
    }

    #[storage]
    struct Storage {
        owner: ContractAddress,
        awa_frozen: bool,
        intent_commitments: Map<felt252, IntentCommitment>,
        intent_committed_flag: Map<felt252, bool>,  // FIX: track existence for collision detection
        travel_rule_hashes: Map<felt252, felt252>,
        travel_rule_submitted_flag: Map<felt252, bool>,  // FIX: track duplicate tx_hash
        birp_anchors: Map<felt252, felt252>,
        birp_enrolled_flag: Map<felt252, bool>,  // FIX: track duplicate enrollment
        total_proofs: u64,  // FIX: counter for total proofs submitted
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        IntentCommitted: IntentCommitted,
        TravelRuleCompliant: TravelRuleCompliant,
        BIRPEnrolled: BIRPEnrolled,
        AWAStateChange: AWAStateChange,
        ProofCountUpdated: ProofCountUpdated,
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

    #[derive(Drop, starknet::Event)]
    pub struct ProofCountUpdated {
        pub total: u64,
    }

    #[constructor]
    fn constructor(ref self: ContractState) {
        self.owner.write(get_caller_address());
        // R-FAILCLOSED: AWA defaults FROZEN (emission blocked until explicitly thawed)
        self.awa_frozen.write(true);
        self.total_proofs.write(0);
    }

    // ── S1 Phase 1: commit_intent (BTCP §5.6 verbatim) ──────────────────
    // FIX: validates h_intent != 0, entity_id != 0
    // FIX: reverts on duplicate h_intent (intent collision detection)
    #[external(v0)]
    fn commit_intent(ref self: ContractState, h_intent: felt252, entity_id: felt252) {
        // FIX: zero-value validation
        assert(h_intent != 0, 'h_intent zero');
        assert(entity_id != 0, 'entity_id zero');
        // R-INVISIBILITY: AWA freeze blocks all emission
        assert(!self.awa_frozen.read(), 'AWA frozen');
        // FIX: duplicate intent collision detection
        let already_committed = self.intent_committed_flag.read(h_intent);
        assert(!already_committed, 'intent exists');
        let timestamp = get_block_info().block_timestamp;
        self.intent_commitments.write(h_intent, IntentCommitment { timestamp, entity_id });
        self.intent_committed_flag.write(h_intent, true);
        self.total_proofs.write(self.total_proofs.read() + 1);
        self.emit(IntentCommitted { entity_id, h_intent, timestamp });
        self.emit(ProofCountUpdated { total: self.total_proofs.read() });
    }

    // ── S1 Phase 1: get_intent (NO routing — just timestamp + entity_id) ──
    #[external(v0)]
    fn get_intent(self: @ContractState, h_intent: felt252) -> (u64, felt252) {
        let ic = self.intent_commitments.read(h_intent);
        (ic.timestamp, ic.entity_id)
    }

    // ── S1 Phase 1: intent_exists (FIX: view for collision detection) ──
    #[external(v0)]
    fn intent_exists(self: @ContractState, h_intent: felt252) -> bool {
        self.intent_committed_flag.read(h_intent)
    }

    // ── S3 Step 4: store disclosure_hash ONLY (BTCP Fix 1 verbatim) ──────
    // FIX: validates entity_id != 0, tx_hash != 0, disclosure_hash_val != 0
    // FIX: reverts on duplicate tx_hash
    #[external(v0)]
    fn submit_travel_rule_proof(
        ref self: ContractState,
        entity_id: felt252,
        tx_hash: felt252,
        jurisdiction_id: felt252,
        disclosure_hash_val: felt252,
    ) {
        // FIX: zero-value validation
        assert(entity_id != 0, 'entity_id zero');
        assert(tx_hash != 0, 'tx_hash zero');
        assert(disclosure_hash_val != 0, 'disclosure zero');
        // R-INVISIBILITY: AWA freeze blocks all emission (CRITICAL tier)
        assert(!self.awa_frozen.read(), 'AWA frozen');
        // FIX: duplicate tx_hash detection
        let already_submitted = self.travel_rule_submitted_flag.read(tx_hash);
        assert(!already_submitted, 'tx_hash exists');
        // R-ABSENT: NO disclosure_contents or regulator_receipt stored
        self.travel_rule_hashes.write(tx_hash, disclosure_hash_val);
        self.travel_rule_submitted_flag.write(tx_hash, true);
        self.total_proofs.write(self.total_proofs.read() + 1);
        self.emit(TravelRuleCompliant {
            entity_id, tx_hash, disclosure_hash: disclosure_hash_val,
        });
        self.emit(ProofCountUpdated { total: self.total_proofs.read() });
    }

    // ── S5: BIRP enrollment — store BIRP_anchor ONLY (C3 §16 verbatim) ──
    // FIX: validates entity_id != 0, birp_anchor_val != 0
    // FIX: reverts on duplicate entity_id (already enrolled)
    #[external(v0)]
    fn enroll_birp(
        ref self: ContractState,
        entity_id: felt252,
        birp_anchor_val: felt252,
    ) {
        // FIX: zero-value validation
        assert(entity_id != 0, 'entity_id zero');
        assert(birp_anchor_val != 0, 'birp zero');
        // R-INVISIBILITY: AWA freeze blocks enrollment
        assert(!self.awa_frozen.read(), 'AWA frozen');
        // FIX: duplicate enrollment detection
        let already_enrolled = self.birp_enrolled_flag.read(entity_id);
        assert(!already_enrolled, 'already enrolled');
        let ts = get_block_info().block_timestamp;
        self.birp_anchors.write(entity_id, birp_anchor_val);
        self.birp_enrolled_flag.write(entity_id, true);
        self.total_proofs.write(self.total_proofs.read() + 1);
        self.emit(BIRPEnrolled {
            entity_id, birp_anchor: birp_anchor_val, enrollment_timestamp: ts,
        });
        self.emit(ProofCountUpdated { total: self.total_proofs.read() });
    }

    // ── Hash_DNA: compute Pedersen binding hash (mod felt252 prime) ──
    // FIX: Pedersen output mod Stark prime to fit in felt252
    // This is a view function — the caller computes the binding hash, then
    // commits it via commit_intent.
    #[external(v0)]
    fn compute_hash_dna(
        self: @ContractState,
        entity_id: felt252,
        system_id: felt252,
    ) -> felt252 {
        // Pedersen hash of (entity_id, system_id)
        let h = pedersen::pedersen(entity_id, system_id);
        // The Pedersen hash output is already a valid felt252 (it's reduced mod the Stark prime)
        // No additional mod needed — pedersen() returns felt252
        h
    }

    // ── R-INVISIBILITY: AWA freeze management ──────────────────────────
    // FIX: only owner can change AWA state (kept from v1)
    #[external(v0)]
    fn set_awa_state(ref self: ContractState, frozen: bool) {
        assert(get_caller_address() == self.owner.read(), 'Not owner');
        self.awa_frozen.write(frozen);
        let block = get_block_info().block_timestamp;
        self.emit(AWAStateChange { frozen, block });
    }

    #[external(v0)]
    fn is_awa_frozen(self: @ContractState) -> bool {
        self.awa_frozen.read()
    }

    // FIX: view for total proofs submitted
    #[external(v0)]
    fn get_total_proofs(self: @ContractState) -> u64 {
        self.total_proofs.read()
    }

    // FIX: view for owner
    #[external(v0)]
    fn get_owner(self: @ContractState) -> ContractAddress {
        self.owner.read()
    }
}
