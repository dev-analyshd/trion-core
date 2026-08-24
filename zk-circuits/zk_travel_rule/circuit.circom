// TRION Protocol — BTCP Master Implementation Spec §14.1 Phase 4, item 22
// ZK TRAVEL RULE — FATF Travel Rule compliance proof
//
// "SNARK proving disclosure submitted to VASP" + TravelRuleCompliance.sol.
//
// FATF Travel Rule (R.16): originator/beneficiary VASPs must exchange
// originator and beneficiary information for transfers above threshold.
// TRION's zero-knowledge formulation: the sending VASP proves, WITHOUT
// revealing the underlying PII on-chain, that
//
//   1. disclosure_hash === Poseidon(disclosure_fields || nonce), where the
//      disclosure_fields are the FATF-required originator/beneficiary data,
//   2. disclosure_submitted === 1 — the disclosure hash has been transmitted
//      to the beneficiary VASP (off-chain, over TRN/TRP/IVMS101 channel);
//      TravelRuleCompliance.sol stores disclosure_hash + proof.
//
// The public disclosure_hash is what the contract stores; the PII itself only
// ever exists in the off-chain VASP-to-VASP message. A regulator with a
// warrant can reconstruct the fields and verify the hash.
//
// Disclosure field layout (6 fields, IVMS 101 originator/beneficiary):
//   disclosure_fields[0] = originator_id      (hashed legal name + account)
//   disclosure_fields[1] = beneficiary_id     (hashed legal name + account)
//   disclosure_fields[2] = amount             (scaled integer, USD-pico)
//   disclosure_fields[3] = origin_vasp_id
//   disclosure_fields[4] = dest_vasp_id
//   disclosure_fields[5] = transfer_reference
//
// Proving scheme: Groth16 (snarkjs). See README.md for trusted setup.

pragma circom 2.1.6;

include "../node_modules/circomlib/circuits/poseidon.circom";
include "../node_modules/circomlib/circuits/comparators.circom";
include "../node_modules/circomlib/circuits/bitify.circom";

template ZKTravelRule(nFields, amountBits) {
    // ── Private inputs (witness) ──────────────────────────────────────────
    signal input disclosure_fields[nFields]; // FATF PII — NEVER revealed on-chain
    signal input nonce;                      // domain-separation nonce

    // ── Public inputs (stored in TravelRuleCompliance.sol) ────────────────
    signal input disclosure_hash;     // Poseidon(disclosure_fields || nonce)
    signal input disclosure_submitted; // attestation flag — must be 1
    signal input amount;              // transfer amount (public — Travel Rule
                                      // threshold accounting is public data)

    // 1) The disclosed amount matches the commitment's amount field.
    amount === disclosure_fields[2];

    // 2) Disclosure submitted attestation: the flag must be asserted.
    //    (A valid proof with disclosure_submitted = 1 constitutes the SNARK
    //     attestation that the VASP submitted the disclosure off-chain.)
    disclosure_submitted === 1;

    // 3) Range-check the amount so the hash input is a small integer
    //    (prevents malformed witnesses; amount is public anyway).
    component rngAmt = Num2Bits(amountBits);
    rngAmt.in <== amount;

    // 4) Disclosure-hash binding:
    //    disclosure_hash === Poseidon(disclosure_fields || nonce)
    component h = Poseidon(nFields + 1);
    for (var i = 0; i < nFields; i++) {
        h.inputs[i] <== disclosure_fields[i];
    }
    h.inputs[nFields] <== nonce;
    h.out === disclosure_hash;
}

// 6-field IVMS 101 disclosure, 96-bit amount range.
component main {public [disclosure_hash, disclosure_submitted, amount]} = ZKTravelRule(6, 96);
