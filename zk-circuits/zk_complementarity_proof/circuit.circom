// TRION Protocol — BTCP Master Implementation Spec §14.1 Phase 4, item 20
// ZK COMPLEMENTARITY PROOF — "Water Underground" (spec §5.6, Phase 2 Match)
//
// TRION searches for H_intent_B that is the complement of H_intent_A. Both
// parties prove complementarity through a ZK proof:
//
//   public_inputs:  [entity_id_A, entity_id_B, intent_hash_A, intent_hash_B, tolerance]
//   private_inputs: [intent_A_fields, intent_B_fields, nonce_A, nonce_B]
//
// Verified statement (spec §5.6 Phase 2), WITHOUT revealing intent contents:
//   1. intent_hash_A / intent_hash_B bind to the private intents, using the
//      IDENTICAL construction as zk_intent_commitment Phase 1:
//      H_intent = Poseidon(intent_fields || nonce || entity_id),
//   2. asset_in_A  == asset_out_B,
//   3. asset_out_A == asset_in_B,
//   4. |magnitude_A - magnitude_B| <= tolerance.
//
// If the proof verifies, neither party has revealed intent contents to the
// other. Integrate with netting_engine.rs for INVISIBLE privacy mode.
//
// Intent field layout (must match zk_intent_commitment — 6 fields):
//   intent_fields[0] = chain_in
//   intent_fields[1] = chain_out
//   intent_fields[2] = asset_in
//   intent_fields[3] = asset_out
//   intent_fields[4] = magnitude      (normalized, scaled integer, magBits-bit range)
//   intent_fields[5] = deadline
//
// Proving scheme: Groth16 (snarkjs). Spec estimates ~50k constraints for the
// full Hash_DNA-based variant; this Poseidon scaffold is ~2.5k constraints
// (see README.md).

pragma circom 2.1.6;

include "../node_modules/circomlib/circuits/poseidon.circom";
include "../node_modules/circomlib/circuits/comparators.circom";
include "../node_modules/circomlib/circuits/bitify.circom";

template ZKComplementarityProof(nFields, magBits) {
    // Indexes into the intent field layout
    var IDX_CHAIN_IN  = 0;
    var IDX_CHAIN_OUT = 1;
    var IDX_ASSET_IN  = 2;
    var IDX_ASSET_OUT = 3;
    var IDX_MAG       = 4;

    // ── Private inputs (witness) ──────────────────────────────────────────
    signal input intentA[nFields]; // intent fields of party A — never revealed
    signal input intentB[nFields]; // intent fields of party B — never revealed
    signal input nonceA;
    signal input nonceB;

    // ── Public inputs ─────────────────────────────────────────────────────
    signal input entity_id_A;      // BEO of party A (spec: public)
    signal input entity_id_B;      // BEO of party B (spec: public)
    signal input intent_hash_A;    // H_intent_A (from zk_intent_commitment Phase 1)
    signal input intent_hash_B;    // H_intent_B
    signal input tolerance;        // public magnitude tolerance (scaled integer)

    // 1) Hash bindings — the public hashes commit to the private intents.
    //    intent_hash_X === Poseidon(intent_X_fields || nonce_X || entity_id_X)
    //    (identical construction to zk_intent_commitment Phase 1.)
    component hA = Poseidon(nFields + 2);
    for (var i = 0; i < nFields; i++) {
        hA.inputs[i] <== intentA[i];
    }
    hA.inputs[nFields] <== nonceA;
    hA.inputs[nFields + 1] <== entity_id_A;
    hA.out === intent_hash_A;

    component hB = Poseidon(nFields + 2);
    for (var i = 0; i < nFields; i++) {
        hB.inputs[i] <== intentB[i];
    }
    hB.inputs[nFields] <== nonceB;
    hB.inputs[nFields + 1] <== entity_id_B;
    hB.out === intent_hash_B;

    // 2) Asset complementarity (spec §5.6 Phase 2):
    //    asset_in_A == asset_out_B
    component eqIn = IsEqual();
    eqIn.in[0] <== intentA[IDX_ASSET_IN];
    eqIn.in[1] <== intentB[IDX_ASSET_OUT];
    eqIn.out === 1;

    //    asset_out_A == asset_in_B
    component eqOut = IsEqual();
    eqOut.in[0] <== intentA[IDX_ASSET_OUT];
    eqOut.in[1] <== intentB[IDX_ASSET_IN];
    eqOut.out === 1;

    // (Optional strictness — see README: chain_in_A == chain_out_B and
    //  chain_out_A == chain_in_B can be asserted identically when the
    //  route is a strict two-chain complement.)

    // 3) Magnitude proximity: |magnitude_A - magnitude_B| <= tolerance
    //    Range-check the magnitudes and tolerance so LessThan is sound
    //    (LessThan(n) requires inputs < 2^n).
    component rngA = Num2Bits(magBits);
    rngA.in <== intentA[IDX_MAG];
    component rngB = Num2Bits(magBits);
    rngB.in <== intentB[IDX_MAG];
    component rngT = Num2Bits(magBits);
    rngT.in <== tolerance;

    // |a - b| <= tol  <=>  (a <= b + tol) AND (b <= a + tol)
    // LessThan(n) proves in[0] < in[1]; use +1 for <=.
    // magnitudes < 2^magBits and tolerance < 2^magBits ⇒ operands < 2^(magBits+1).
    component ltAB = LessThan(magBits + 1);
    ltAB.in[0] <== intentA[IDX_MAG];
    ltAB.in[1] <== intentB[IDX_MAG] + tolerance + 1;
    ltAB.out === 1;

    component ltBA = LessThan(magBits + 1);
    ltBA.in[0] <== intentB[IDX_MAG];
    ltBA.in[1] <== intentA[IDX_MAG] + tolerance + 1;
    ltBA.out === 1;

    // ── Public output (advisory: aggregate complement flag for the verifier) ──
    signal output is_complement;
    signal prodEq;
    prodEq <== eqIn.out * eqOut.out;
    signal prodLt;
    prodLt <== ltAB.out * ltBA.out;
    is_complement <== prodEq * prodLt;
}

// 6-field intent layout (matches zk_intent_commitment), 64-bit magnitude
// range (matching BTCP magnitude_nano normalization).
component main {public [entity_id_A, entity_id_B, intent_hash_A, intent_hash_B, tolerance]} = ZKComplementarityProof(6, 64);
