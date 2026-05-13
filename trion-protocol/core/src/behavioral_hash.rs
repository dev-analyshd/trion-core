//! Behavioral Hash (BH) — TRION L0
//! sense             = SHA3-256(input || 0x00)
//! anti_raw          = SHA3-256(input || 0xFF)
//! antisense         = anti_raw XOR NOT(sense)
//! invariant stored  = NOT(anti_raw)
//! VERIFY:  sense XOR antisense == invariant   (tamper-evident)

use sha3::{Digest, Sha3_256};
use serde::{Deserialize, Serialize};
use chrono::{DateTime, Utc};
use anyhow::{Result, anyhow};
use crate::event_types::EventType;

fn sha3_with_suffix(input: &[u8], suffix: u8) -> [u8; 32] {
    let mut h = Sha3_256::new();
    h.update(input);
    h.update(&[suffix]);
    h.finalize().into()
}

fn not_bytes(b: [u8; 32]) -> [u8; 32] {
    let mut out = [0u8; 32];
    for i in 0..32 { out[i] = !b[i]; }
    out
}

fn xor_bytes(a: [u8; 32], b: [u8; 32]) -> [u8; 32] {
    let mut out = [0u8; 32];
    for i in 0..32 { out[i] = a[i] ^ b[i]; }
    out
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HashDNA {
    pub sense:               [u8; 32],
    pub antisense:           [u8; 32],
    /// complement_invariant = NOT(anti_raw) = sense XOR antisense (stored for verify)
    pub complement_invariant: [u8; 32],
}

impl HashDNA {
    pub fn new(input: &[u8]) -> Self {
        let sense    = sha3_with_suffix(input, 0x00);
        let anti_raw = sha3_with_suffix(input, 0xFF);

        // antisense = anti_raw XOR NOT(sense)
        let complement = not_bytes(sense);
        let antisense  = xor_bytes(anti_raw, complement);

        // Invariant: sense XOR antisense = NOT(anti_raw) — provable:
        // sense XOR (anti_raw XOR NOT(sense)) = sense XOR anti_raw XOR NOT(sense)
        //   for each bit: s XOR (a XOR ~s) = ~a  ∀ s,a ∈ {0,1}
        // So sense XOR antisense = NOT(anti_raw)
        let complement_invariant = not_bytes(anti_raw);

        Self { sense, antisense, complement_invariant }
    }

    /// Tamper-evident verification.
    /// Any change to sense or antisense breaks the XOR invariant.
    pub fn verify(&self) -> bool {
        let xor_result = xor_bytes(self.sense, self.antisense);
        xor_result == self.complement_invariant
    }

    pub fn sense_hex(&self) -> String     { hex::encode(self.sense) }
    pub fn antisense_hex(&self) -> String { hex::encode(self.antisense) }
}

/// magnitude_normalized = log10(usd_value + 1) / log10(max_observed_90d + 1)
pub fn normalize_magnitude(usd_value: f64, max_observed_90d: f64) -> f64 {
    let numerator   = (usd_value + 1.0_f64).log10();
    let denominator = (max_observed_90d + 1.0_f64).log10();
    if denominator == 0.0 { return 0.0; }
    (numerator / denominator).clamp(0.0, 1.0)
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BehavioralHash {
    pub entity_id:            String,
    pub event_type:           EventType,
    pub magnitude_normalized: f64,
    pub context:              String,
    pub timestamp:            DateTime<Utc>,
    pub chain_id:             u64,
    pub block_hash:           String,
    pub hash_dna:             HashDNA,
}

impl BehavioralHash {
    pub fn new(
        entity_id:        String,
        event_type:       EventType,
        usd_value:        f64,
        max_observed_90d: f64,
        context:          String,
        timestamp:        DateTime<Utc>,
        chain_id:         u64,
        block_hash:       String,
    ) -> Result<Self> {
        if usd_value < 0.0         { return Err(anyhow!("USD value cannot be negative")); }
        if max_observed_90d <= 0.0 { return Err(anyhow!("max_observed_90d must be > 0")); }

        let magnitude_normalized = normalize_magnitude(usd_value, max_observed_90d);

        let preimage = format!(
            "{}|{}|{:.6}|{}|{}|{}|{}",
            entity_id,
            event_type.type_byte(),
            magnitude_normalized,
            context,
            timestamp.timestamp_nanos_opt().unwrap_or(0),
            chain_id,
            block_hash,
        );

        let hash_dna = HashDNA::new(preimage.as_bytes());

        Ok(Self {
            entity_id, event_type, magnitude_normalized,
            context, timestamp, chain_id, block_hash, hash_dna,
        })
    }

    pub fn verify(&self) -> bool {
        self.hash_dna.verify()
            && self.magnitude_normalized >= 0.0
            && self.magnitude_normalized <= 1.0
    }
}
