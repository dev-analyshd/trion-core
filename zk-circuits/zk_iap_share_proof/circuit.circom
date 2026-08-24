// TRION Protocol — BTCP Master Implementation Spec §14.1 Phase 4, item 21
// ZK IAP SHARE PROOF — Intent Aggregation Protocol gas distribution
//
// Phase 3 spec (§14.1 item 11): "Gas distribution: G_per_entity = G_total ×
// share" where share_i = value_i / total_value. Phase 4 defers the ZK share
// proof no longer: this circuit enables fully private IAP participation.
//
// Proven statement — WITHOUT revealing the prover's value or the pool's
// individual values:
//
//   1. total_value === value_i + Σ_j others_j      (the public pool total is
//      the honest sum of the prover's value and all other participants'),
//   2. gas_i × total_value === gas_total × value_i  (the prover's gas
//      allocation is EXACTLY the IAP share:
//          gas_i = gas_total · value_i / total_value),
//   3. range checks preventing field overflow of the products.
//
// The cross-multiplication in (2) is exact integer arithmetic: if
// gas_total · value_i is not divisible by total_value, no valid witness with
// integer gas_i exists.
//
// Proving scheme: Groth16 (snarkjs). See README.md for trusted setup.

pragma circom 2.1.6;

include "../node_modules/circomlib/circuits/bitify.circom";

template ZKIAPShareProof(nOthers, valBits, gasBits) {
    // ── Private inputs (witness) ──────────────────────────────────────────
    signal input value_i;              // prover's intent value — never revealed
    signal input others[nOthers];      // other participants' values — never revealed

    // ── Public inputs (on-chain / to the pool coordinator) ────────────────
    signal input total_value;          // Σ all participant values (public pool total)
    signal input gas_total;            // G_total — total gas paid by the pool
    signal input gas_i;                // G_i — gas attributed to the prover

    // 1) Sum check: total_value === value_i + Σ_j others[j]
    //    (one linear constraint; prevents inflating/deflating the pool total)
    var acc = 0;
    for (var j = 0; j < nOthers; j++) {
        acc = acc + others[j];
    }
    total_value === value_i + acc;

    // 2) Share check (exact rational identity):
    //       gas_i × total_value === gas_total × value_i
    //    ⇔  gas_i = gas_total · value_i / total_value  (IAP share)
    //    Split into two quadratic assignments + one linear equality
    //    (R1CS constraints must be at most quadratic on one side).
    signal lhs;
    lhs <== gas_i * total_value;
    signal rhs;
    rhs <== gas_total * value_i;
    lhs === rhs;

    // 3) Range checks — soundness of the products above:
    //    the BN254 scalar field is ~254 bits; the quadratic constraints are
    //    only meaningful over ℤ (not mod p) when operands are small enough:
    //      value_i, others[j], total_value < 2^valBits
    //      gas_i, gas_total         < 2^gasBits
    //    with valBits + valBits < 253 and gasBits + valBits < 253.
    component rngVi = Num2Bits(valBits);
    rngVi.in <== value_i;
    component rngGt = Num2Bits(gasBits);
    rngGt.in <== gas_total;
    component rngGi = Num2Bits(gasBits);
    rngGi.in <== gas_i;
    // total_value < 2^(valBits+1) because it is a sum of (nOthers+1) values
    // each < 2^valBits; range-check with valBits + ceil(log2(nOthers+1)) + 1
    // bits, conservatively valBits + 8 for pools up to 256 participants.
    component rngTv = Num2Bits(valBits + 8);
    rngTv.in <== total_value;

    component rngOthers[nOthers];
    for (var j = 0; j < nOthers; j++) {
        rngOthers[j] = Num2Bits(valBits);
        rngOthers[j].in <== others[j];
    }
}

// Pool of up to 7 other participants (8 total), 96-bit values (pico-precision
// USD), 96-bit gas amounts.
component main {public [total_value, gas_total, gas_i]} = ZKIAPShareProof(7, 96, 96);
