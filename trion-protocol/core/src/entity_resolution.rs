//! Entity Resolution Protocol (ERP) — TRION L0
//! BEO_confidence = weighted(CF, ST, SC, BP)
//! Valid only when BEO_confidence > 0.75

use serde::{Deserialize, Serialize};

const W_CF:  f64 = 0.40;
const W_ST:  f64 = 0.25;
const W_SC:  f64 = 0.25;
const W_BP:  f64 = 0.10;
const W_SUM: f64 = W_CF + W_ST + W_SC + W_BP;

const BEO_THRESHOLD:       f64 = 0.75;
const RHO_TIMING:          f64 = 0.85;
const GRAPH_SIM_THRESHOLD: f64 = 0.80;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AddressCluster {
    pub addresses:  Vec<String>,
    pub confidence: f64,
    pub cf_score:   f64,
    pub st_score:   f64,
    pub sc_score:   f64,
    pub bp_score:   f64,
    pub is_valid:   bool,
    pub entity_id:  Option<String>,
}

impl AddressCluster {
    pub fn compute(
        addresses: Vec<String>,
        cf_score:  f64,
        st_score:  f64,
        sc_score:  f64,
        bp_score:  f64,
    ) -> Self {
        let confidence = (W_CF * cf_score + W_ST * st_score
                        + W_SC * sc_score + W_BP * bp_score)
                        / W_SUM;
        let confidence = confidence.clamp(0.0, 1.0);
        let is_valid   = confidence > BEO_THRESHOLD;

        let entity_id = if is_valid {
            let input = addresses.join("|");
            let hash  = sha3_256_hex(input.as_bytes());
            Some(format!("BEO_{}", &hash[..16]))
        } else {
            None
        };

        Self { addresses, confidence, cf_score, st_score,
               sc_score, bp_score, is_valid, entity_id }
    }

    pub fn compute_st_score(correlation: f64) -> f64 {
        if correlation > RHO_TIMING { correlation } else { correlation * 0.5 }
            .clamp(0.0, 1.0)
    }

    pub fn compute_bp_score(graph_similarity: f64) -> f64 {
        if graph_similarity > GRAPH_SIM_THRESHOLD { graph_similarity } else { 0.0 }
    }
}

fn sha3_256_hex(input: &[u8]) -> String {
    use sha3::{Digest, Sha3_256};
    let mut hasher = Sha3_256::new();
    hasher.update(input);
    hex::encode(hasher.finalize())
}
