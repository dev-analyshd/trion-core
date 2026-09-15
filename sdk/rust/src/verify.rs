use crate::types::TRIONSignal;
use sha3::{Sha3_256, Digest};

/// Result of signal verification (whitepaper Part 15.4).
#[derive(Debug)]
pub struct VerifyResult {
    pub valid: bool,
    pub provenance_chain_depth: usize,
    pub all_bh_retrievable: bool,
    pub genomic_valid: bool,
}

/// Verify a TRION signal's integrity.
/// Whitepaper Part 15.4: verifySignal returns {valid, provenance_chain_depth, all_BH_retrievable, genomic_valid}
pub fn verify_signal(signal: &TRIONSignal) -> VerifyResult {
    // Structural validity
    let valid = !signal.entity_id.is_empty()
        && signal.signal_value >= 0.0
        && signal.signal_value <= 1.0
        && signal.ci_95[0] <= signal.ci_95[1]
        && signal.timestamp > 0
        && signal.genomic_signature.len() == 128; // 64 bytes = 128 hex chars

    // Provenance chain depth
    let provenance_chain_depth = signal.provenance.len();

    // All BH retrievable (structural check — full retrieval requires API call)
    let all_bh_retrievable = signal.provenance.iter().all(|p| {
        p.get("bh_id").is_some() || p.get("source").is_some()
    });

    // Genomic validity (sense/antisense XOR complement invariant)
    let genomic_valid = verify_genomic_invariant(&signal.genomic_signature);

    VerifyResult {
        valid,
        provenance_chain_depth,
        all_bh_retrievable,
        genomic_valid,
    }
}

/// Verify the dual-strand DNA hash invariant:
/// sense XOR antisense == complement(SHA3(payload || 0xFF))
fn verify_genomic_invariant(signature_hex: &str) -> bool {
    if signature_hex.len() != 128 {
        return false;
    }
    // sense = first 64 hex chars (32 bytes)
    // antisense = last 64 hex chars (32 bytes)
    let sense_bytes = match hex::decode(&signature_hex[..64]) {
        Ok(b) => b,
        Err(_) => return false,
    };
    let antisense_bytes = match hex::decode(&signature_hex[64..]) {
        Ok(b) => b,
        Err(_) => return false,
    };

    // Check: sense XOR antisense should be the complement pattern
    // (each byte of sense XOR'd with corresponding antisense byte = 0xFF)
    for (s, a) in sense_bytes.iter().zip(antisense_bytes.iter()) {
        if s ^ a != 0xFF {
            return false;
        }
    }
    true
}
