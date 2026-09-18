use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize, Deserialize)]
pub struct TrionSignal {
    pub entity_id: String,
    pub signal_type: String,
    pub coherence_score: f64,
    pub threshold: f64,
    pub coherent: bool,
    pub timestamp: f64,
}
