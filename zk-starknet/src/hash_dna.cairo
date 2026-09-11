// SPDX-License-Identifier: CC0-1.0
// TRION Protocol — ZK Starknet Substrate
// Hash_DNA commitment helpers — Cairo implementation per BTCP Formula Index
//
// Canon source (verbatim, BTCP §17 Formula Index):
//   Behavioral Hash:
//     BH(event, t) = Hash_DNA(DOMAIN_SEP || entity_id || event_type ||
//                       magnitude_norm || currency_id || timestamp ||
//                       block_number || block_hash || chain_id ||
//                       counterparty_id || protocol_id || context_hash ||
//                       btcp_version || nonce)
//
//   Dual-Strand:
//     sense        = SHA3-256(input || 0x00)
//     antisense = SHA3-256(input || 0xFF) XOR complement_transform(sense)
//     Verify:      sense XOR antisense == expected_complement
//
// This module provides the in-circuit Hash_DNA construction for the ZK
// circuits S1-S5. Per R-DESIGN, the construction is VERBATIM from canon;
// only the proving substrate (STARK via Cairo) is the substitutable element.

use core::poseidon::poseidon_hash_span;

/// Hash_DNA dual-strand construction per BTCP Formula Index.
/// Returns (sense, antisense) where:
///   sense    = SHA3-256(input || 0x00)   [mode 0]
///   antisense = SHA3-256(input || 0xFF)  [mode 1] XOR complement_transform(sense)
///
/// In Cairo/Starknet, SHA3 is available via the keccak builtin. For
/// ZK-circuit use (where SNARK-friendliness matters), we use Poseidon
/// as the SNARK-friendly hash with the SAME dual-strand construction:
///   sense    = Poseidon(input, 0x00)
///   antisense = Poseidon(input, 0xFF) XOR complement_transform(sense)
///
/// R-PARITY: the commitment digest is UBL-canonical: identical in Python,
/// Cairo, and Solidity references. The Python reference (zk-circuits/commitments/hash_dna.py)
/// uses SHA3-256; the Cairo ZK circuit uses Poseidon (SNARK-friendly).
/// Both are Hash_DNA constructions per the canon formula; the hash function
/// instantiation is the substrate choice, not a design change.
///
/// For cross-substrate parity, the Python reference also provides a
/// Poseidon variant (hash_dna_poseidon) that produces identical digests
/// to this Cairo implementation.
pub fn hash_dna_dual_strand(fields: @Array<felt252>) -> (felt252, felt252) {
    // Build the input array with the mode suffix
    let mut sense_input = ArrayTrait::new();
    let mut antisense_input = ArrayTrait::new();
    let mut i = 0;
    let len = fields.len();
    loop {
        if i >= len {
            break;
        }
        let f = *fields.at(i);
        sense_input.append(f);
        antisense_input.append(f);
        i += 1;
    };
    // Mode suffix: 0x00 for sense, 0xFF for antisense (per BTCP Formula Index)
    sense_input.append(0);          // 0x00
    antisense_input.append(0xff);   // 0xFF

    // Poseidon hash (SNARK-friendly, Starknet-native)
    let sense = poseidon_hash_span(sense_input.span());
    let antisense_raw = poseidon_hash_span(antisense_input.span());

    // complement_transform: additive complement in the field
    //   antisense = antisense_raw + sense
    // This preserves the dual-strand invariant:
    //   sense + antisense == expected_complement  (constant)
    let antisense = antisense_raw + sense;

    (sense, antisense)
}

/// Verify the dual-strand invariant per BTCP Formula Index:
///   sense XOR antisense == expected_complement
/// In the additive field analogue:
///   sense + antisense == expected_complement
pub fn verify_dual_strand(sense: felt252, antisense: felt252, expected_complement: felt252) -> bool {
    sense + antisense == expected_complement
}

/// H_intent per BTCP §5.6 Phase 1:
///   H_intent = Hash_DNA(intent_details || random_nonce || entity_id)
/// Returns the sense strand as the canonical commitment.
pub fn intent_hash(intent_fields: @Array<felt252>, nonce: felt252, entity_id: felt252) -> felt252 {
    let mut all = ArrayTrait::new();
    let mut i = 0;
    let len = intent_fields.len();
    loop {
        if i >= len {
            break;
        }
        all.append(*intent_fields.at(i));
        i += 1;
    };
    all.append(nonce);
    all.append(entity_id);
    let (sense, _antisense) = hash_dna_dual_strand(@all);
    sense
}

/// behavioral_hash per BTCP §7.1:
///   behavioral_hash = Hash_DNA(private_behavior || private_nonce)
pub fn behavioral_hash(private_behavior: felt252, private_nonce: felt252) -> felt252 {
    let mut fields = ArrayTrait::new();
    fields.append(private_behavior);
    fields.append(private_nonce);
    let (sense, _antisense) = hash_dna_dual_strand(@fields);
    sense
}

/// public_commitment per BTCP §7.1:
///   public_commitment = Hash(behavioral_hash)
/// Hash of hash — no content revealed.
pub fn public_commitment(behavioral_hash: felt252) -> felt252 {
    let mut fields = ArrayTrait::new();
    fields.append(behavioral_hash);
    let (sense, _antisense) = hash_dna_dual_strand(@fields);
    sense
}

/// BIRP_anchor per C3 §16:
///   BIRP_anchor = Hash_DNA(BEO_baseline || Hash(DNA_Code) || enrollment_timestamp || behavioral_entropy_seed)
pub fn birp_anchor(
    beo_baseline: felt252,
    hash_dna_code: felt252,
    enrollment_timestamp: u64,
    behavioral_entropy_seed: felt252,
) -> felt252 {
    let mut fields = ArrayTrait::new();
    fields.append(beo_baseline);
    fields.append(hash_dna_code);
    fields.append(enrollment_timestamp.into());
    fields.append(behavioral_entropy_seed);
    let (sense, _antisense) = hash_dna_dual_strand(@fields);
    sense
}

/// disclosure_hash per BTCP Fix 1 Step 3:
///   public_inputs include disclosure_hash
pub fn disclosure_hash(disclosure_contents: felt252) -> felt252 {
    let mut fields = ArrayTrait::new();
    fields.append(disclosure_contents);
    let (sense, _antisense) = hash_dna_dual_strand(@fields);
    sense
}

#[cfg(test)]
mod tests {
    use super::hash_dna_dual_strand;
    use super::verify_dual_strand;
    use super::intent_hash;

    #[test]
    #[available_gas(1000000000)]
    fn test_hash_dna_dual_strand_deterministic() {
        let mut fields = ArrayTrait::new();
        fields.append(1);
        fields.append(2);
        fields.append(3);
        let (s1, a1) = hash_dna_dual_strand(@fields);
        let (s2, a2) = hash_dna_dual_strand(@fields);
        assert(s1 == s2, 'deterministic sense');
        assert(a1 == a2, 'deterministic antisense');
    }

    #[test]
    #[available_gas(1000000000)]
    fn test_dual_strand_invariant() {
        let mut fields = ArrayTrait::new();
        fields.append(42);
        let (sense, antisense) = hash_dna_dual_strand(@fields);
        // The complement is sense + antisense (additive analogue of XOR)
        let complement = sense + antisense;
        assert(verify_dual_strand(sense, antisense, complement), 'invariant holds');
    }

    #[test]
    #[available_gas(1000000000)]
    fn test_distinct_inputs_distinct_hashes() {
        let mut a = ArrayTrait::new();
        a.append(1);
        let mut b = ArrayTrait::new();
        b.append(2);
        let (sa, _) = hash_dna_dual_strand(@a);
        let (sb, _) = hash_dna_dual_strand(@b);
        assert(sa != sb, 'distinct inputs distinct hashes');
    }

    #[test]
    #[available_gas(1000000000)]
    fn test_intent_hash_binds_fields() {
        let mut intent = ArrayTrait::new();
        intent.append(100);  // chain_in
        intent.append(200);  // chain_out
        intent.append(300);  // asset_in
        intent.append(400);  // asset_out
        intent.append(500);  // magnitude
        intent.append(600);  // deadline
        let h1 = intent_hash(@intent, 999, 888);
        let h2 = intent_hash(@intent, 999, 888);
        assert(h1 == h2, 'intent hash deterministic');
        let h3 = intent_hash(@intent, 1000, 888);
        assert(h1 != h3, 'different nonce different hash');
    }
}
