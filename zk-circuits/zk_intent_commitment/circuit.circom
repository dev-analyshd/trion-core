// TRION Protocol — BTCP Master Implementation Spec §14.1 Phase 4, item 19
// ZK INTENT COMMITMENT — "Water Underground" (spec §5.6)
//
// Phase 1 (Commit) of the four-phase MEV-privacy protocol:
//
//   H_intent   = Hash_DNA(intent_details || random_nonce || entity_id)   [spec §5.6]
//   commitment = Poseidon(intent_hash, nonce)
//
// The user submits ONLY the commitment to BTCPIntent.sol. MEV bots observe a
// commitment hash — no direction, no amount, nothing actionable.
//
// This circuit proves, WITHOUT revealing the intent:
//   1. knowledge of (intent_fields, nonce, entity_id) whose Poseidon hash
//      equals the public intent_hash  (the intent is well-formed & owned), and
//   2. commitment == Poseidon(intent_hash, nonce)  (the commitment binds the
//      same nonce, so the Phase 3 atomic reveal is verifiable).
//
// Intent field layout (6 fields; entity_id is a separate input):
//   intent_fields[0] = chain_in       (source TRION chain id)
//   intent_fields[1] = chain_out      (destination TRION chain id)
//   intent_fields[2] = asset_in       (canonical asset id, field element)
//   intent_fields[3] = asset_out      (canonical asset id, field element)
//   intent_fields[4] = magnitude      (normalized, scaled integer)
//   intent_fields[5] = deadline       (unix time, seconds)
//
// NOTE: zk_complementarity_proof uses the IDENTICAL H_intent construction
// (Poseidon(intent_fields || nonce || entity_id)) so the commitment chain
// verifies end-to-end across Phases 1-3.
//
// Proving scheme: Groth16 (snarkjs). See README.md for trusted setup.

pragma circom 2.1.6;

include "../node_modules/circomlib/circuits/poseidon.circom";

template ZKIntentCommitment(nFields) {
    // ── Private inputs (witness) ──────────────────────────────────────────
    signal input intent_fields[nFields]; // intent contents — never revealed
    signal input nonce;                  // random 248-bit nonce (Phase 1 entropy)

    // ── Public inputs (on-chain) ──────────────────────────────────────────
    signal input entity_id;              // BEO identifier (field element)
    signal input intent_hash;            // H_intent — stored in BTCPIntent.sol
    signal input commitment;             // Poseidon(intent_hash, nonce)

    // 1) Intent-hash binding (spec §5.6 Phase 1):
    //    intent_hash === Poseidon(intent_fields || nonce || entity_id)
    component h = Poseidon(nFields + 2);
    for (var i = 0; i < nFields; i++) {
        h.inputs[i] <== intent_fields[i];
    }
    h.inputs[nFields] <== nonce;
    h.inputs[nFields + 1] <== entity_id;
    h.out === intent_hash;

    // 2) Commitment binding:
    //    commitment === Poseidon(intent_hash || nonce)
    component c = Poseidon(2);
    c.inputs[0] <== intent_hash;
    c.inputs[1] <== nonce;
    c.out === commitment;
}

// nFields = 6 intent fields → Poseidon(8) for H_intent, Poseidon(2) for commitment
component main {public [entity_id, intent_hash, commitment]} = ZKIntentCommitment(6);
