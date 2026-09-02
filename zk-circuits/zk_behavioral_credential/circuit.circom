// TRION Protocol — BTCP Master Implementation Spec §14.1 Phase 4, item 23
// ZK BEHAVIORAL CREDENTIAL — Sensing Oracle behavioral coherence proof
// (LONG TERM — designed for proof aggregation / recursive proofs)
//
// "Sensing Oracle implementation. Multi-year behavioral record as ZK circuit
//  input. Proof aggregation (recursive proofs) for efficiency."
//
// A behavioral credential lets a BEO prove "my behavioral history is coherent
// with the pattern commitment my credential was issued against" WITHOUT
// revealing the underlying behavioral record. The credential is issued by the
// TRION Sensing Oracle against a BEO pattern commitment; the on-chain
// behavioral_hash is the public digest of the pattern.
//
// Proven statement — WITHOUT revealing the behavioral pattern:
//
//   1. behavioral_hash === Poseidon(entity_id || pattern_fields || epoch)
//        — the public BH is derived from the private pattern fields
//          (coherence C, plane breakdown Φ/M/Σ/K/A, manipulation factor),
//   2. pattern_commitment === Poseidon(pattern_fields || epoch || nonce)
//        — the pattern commitment the Sensing Oracle signed,
//   3. credential === Poseidon(pattern_commitment || entity_id || epoch)
//        — the issued credential binds entity + epoch + pattern commitment.
//
// Together: the behavioral_hash is coherent with the BEO pattern commitment
// that the credential attests — all three public values are linked to the
// same private pattern through one proof.
//
// Pattern field layout (7 fields — the five-plane coherence state):
//   pattern_fields[0] = C        (aggregate coherence, scaled 1e6)
//   pattern_fields[1] = phi      (Φ plane score, scaled 1e6)
//   pattern_fields[2] = m        (M plane score, scaled 1e6)
//   pattern_fields[3] = sigma    (Σ plane score, scaled 1e6)
//   pattern_fields[4] = k        (K plane score, scaled 1e6)
//   pattern_fields[5] = anima    (A plane score, scaled 1e6)
//   pattern_fields[6] = mf       (manipulation factor discount, scaled 1e6)
//
// Proving scheme: Groth16 (snarkjs). See README.md for trusted setup and the
// recursive-aggregation roadmap (Nova/Plonky2 folding for multi-year records).

pragma circom 2.1.6;

include "../node_modules/circomlib/circuits/poseidon.circom";
include "../node_modules/circomlib/circuits/bitify.circom";

template ZKBehavioralCredential(nFields, scoreBits) {
    // ── Private inputs (witness) ──────────────────────────────────────────
    signal input entity_id;                // BEO identifier
    signal input pattern_fields[nFields];  // five-plane coherence state — never revealed
    signal input epoch;                    // credential epoch
    signal input nonce;                    // blinding nonce for the pattern commitment

    // ── Public inputs ─────────────────────────────────────────────────────
    signal input behavioral_hash;   // public BH digest of the pattern (on-chain)
    signal input pattern_commitment; // commitment the Sensing Oracle signed
    signal input credential;        // the issued ZK credential

    // 1) Behavioral-hash binding:
    //    behavioral_hash === Poseidon(entity_id || pattern_fields || epoch)
    component bh = Poseidon(nFields + 2);
    bh.inputs[0] <== entity_id;
    for (var i = 0; i < nFields; i++) {
        bh.inputs[i + 1] <== pattern_fields[i];
    }
    bh.inputs[nFields + 1] <== epoch;
    bh.out === behavioral_hash;

    // 2) Pattern commitment binding:
    //    pattern_commitment === Poseidon(pattern_fields || epoch || nonce)
    component pc = Poseidon(nFields + 2);
    for (var i = 0; i < nFields; i++) {
        pc.inputs[i] <== pattern_fields[i];
    }
    pc.inputs[nFields] <== epoch;
    pc.inputs[nFields + 1] <== nonce;
    pc.out === pattern_commitment;

    // 3) Credential binding:
    //    credential === Poseidon(pattern_commitment || entity_id || epoch)
    component cr = Poseidon(3);
    cr.inputs[0] <== pattern_commitment;
    cr.inputs[1] <== entity_id;
    cr.inputs[2] <== epoch;
    cr.out === credential;

    // 4) Range checks: pattern scores are 1e6-scaled values in [0, 2^scoreBits).
    //    (Coherence scores are bounded by 1.0 ⇒ 1_000_000 < 2^21; scoreBits
    //    leaves headroom for future precision.)
    component rngPattern[nFields];
    for (var i = 0; i < nFields; i++) {
        rngPattern[i] = Num2Bits(scoreBits);
        rngPattern[i].in <== pattern_fields[i];
    }
}

// 7 pattern fields, 32-bit score range (1e6-scaled coherence values).
component main {public [behavioral_hash, pattern_commitment, credential]} = ZKBehavioralCredential(7, 32);
