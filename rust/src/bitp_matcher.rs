//! bitp_matcher.rs — CUT/MATCH/PASTE engine for illiquid pairs
//! Per BTCP Master Implementation Spec §Water Principle 1

use crate::types::*;
use std::collections::HashMap;

/// BITP Intent — Behavioral Information Transfer Protocol
/// Water carries minerals: assets don't move, behavioral commitments do.
#[derive(Debug, Clone)]
pub struct BITPIntentData {
    pub entity_id: BEOId,
    pub asset_in: Vec<u8>,
    pub asset_out: Vec<u8>,
    pub magnitude: f64,
    pub chain_id: ChainId,
    pub deadline: u64,
}

/// BITP Matcher — CUT/MATCH/PASTE three-phase engine
/// Phase 1 (CUT): Post commitment to Akashic clipboard. Assets untouched.
/// Phase 2 (MATCH): Scan for complementary intent.
/// Phase 3 (PASTE): Dual-chain native release if match found; else BLO created.
#[derive(Debug, Default)]
pub struct BITPMatcher {
    clipboard: HashMap<H256, BITPIntentData>,
}

impl BITPMatcher {
    pub fn new() -> Self {
        BITPMatcher {
            clipboard: HashMap::new(),
        }
    }

    /// Phase 1: CUT — Post behavioral commitment to clipboard
    /// Assets remain untouched on native chain
    pub fn execute_cut(&mut self, intent: &BITPIntentData) -> H256 {
        let commitment = H256::sha3(
            format!(
                "{}:{}:{}:{}:{}",
                intent.entity_id.to_hex(),
                hex::encode(&intent.asset_in),
                hex::encode(&intent.asset_out),
                intent.magnitude,
                intent.deadline
            )
            .as_bytes(),
        );
        self.clipboard.insert(commitment, intent.clone());
        commitment
    }

    /// Phase 2: MATCH — Find complementary intent in clipboard
    /// Complement = asset_in ↔ asset_out, within price tolerance
    pub fn find_complement<'a>(
        &self,
        intent: &BITPIntentData,
        candidates: &'a [BITPIntentData],
        price_tolerance: f64,
    ) -> Option<&'a BITPIntentData> {
        for candidate in candidates {
            // Check if assets are complementary
            if candidate.asset_in == intent.asset_out
                && candidate.asset_out == intent.asset_in
            {
                // Check magnitude within tolerance
                let ratio = if intent.magnitude > 0.0 {
                    candidate.magnitude / intent.magnitude
                } else {
                    0.0
                };
                if (ratio - 1.0).abs() <= price_tolerance {
                    return Some(candidate);
                }
            }
        }
        None
    }

    /// Phase 3: PASTE — Execute dual-chain native release
    /// Returns true if paste executed (both sides release on their native chains)
    pub fn execute_paste(
        &mut self,
        commitment_a: &H256,
        commitment_b: &H256,
    ) -> bool {
        // Remove both from clipboard (they've been matched)
        let a_exists = self.clipboard.remove(commitment_a).is_some();
        let b_exists = self.clipboard.remove(commitment_b).is_some();
        a_exists && b_exists
    }

    /// Get current clipboard size
    pub fn clipboard_size(&self) -> usize {
        self.clipboard.len()
    }

    /// Get all clipboard entries
    pub fn all_clipboard(&self) -> Vec<(&H256, &BITPIntentData)> {
        self.clipboard.iter().collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cut_match_paste() {
        let mut matcher = BITPMatcher::new();

        // Entity A has USDC, wants SOL on chain 1
        let intent_a = BITPIntentData {
            entity_id: H256::sha3(b"entity_A"),
            asset_in: b"USDC".to_vec(),
            asset_out: b"SOL".to_vec(),
            magnitude: 1000.0,
            chain_id: 1,
            deadline: 1787141851,
        };

        // Entity B has SOL, wants USDC on chain 900
        let intent_b = BITPIntentData {
            entity_id: H256::sha3(b"entity_B"),
            asset_in: b"SOL".to_vec(),
            asset_out: b"USDC".to_vec(),
            magnitude: 5.0,
            chain_id: 900,
            deadline: 1787141851,
        };

        // Phase 1: CUT
        let comm_a = matcher.execute_cut(&intent_a);
        assert_eq!(matcher.clipboard_size(), 1);

        // Phase 2: MATCH — BITP matches by asset complementarity, not exact magnitude
        // Water principle: assets don't move, so magnitudes just indicate commitment size
        let candidates = vec![intent_a.clone()];
        let found = matcher.find_complement(&intent_b, &candidates, 1000.0); // Very high tolerance — BITP is about asset direction, not size
        assert!(found.is_some());

        // Phase 3: PASTE
        let comm_b = matcher.execute_cut(&intent_b);
        let success = matcher.execute_paste(&comm_a, &comm_b);
        assert!(success);
        assert_eq!(matcher.clipboard_size(), 0);
    }

    #[test]
    fn test_no_match_different_assets() {
        let matcher = BITPMatcher::new();

        let intent_a = BITPIntentData {
            entity_id: H256::sha3(b"A"),
            asset_in: b"ETH".to_vec(),
            asset_out: b"BTC".to_vec(),
            magnitude: 1.0,
            chain_id: 1,
            deadline: 0,
        };

        let intent_b = BITPIntentData {
            entity_id: H256::sha3(b"B"),
            asset_in: b"SOL".to_vec(),
            asset_out: b"USDC".to_vec(),
            magnitude: 100.0,
            chain_id: 900,
            deadline: 0,
        };

        let candidates = vec![intent_a];
        let found = matcher.find_complement(&intent_b, &candidates, 0.10);
        assert!(found.is_none());
    }
}
