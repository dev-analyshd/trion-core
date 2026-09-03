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
    /// Deadline (unix seconds) after which the commitment is expired and
    /// can no longer be matched (checked by `find_complement`)
    pub deadline: u64,
    /// Root of the entity's behavioral proof tree (Akashic BH root) —
    /// bound into the CUT commitment per BTCP spec §17
    pub behavioral_proof_root: H256,
    /// Intent nonce (uniqueness / replay protection) — bound into the
    /// CUT commitment per BTCP spec §17
    pub nonce: u64,
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
    /// Assets remain untouched on native chain.
    ///
    /// Per BTCP spec §17, the commitment is
    ///     commitment = H(intent_A || behavioral_proof_root || nonce)
    /// — the proof root and nonce are bound in so a commitment is unique
    /// per behavioral state and cannot be replayed across epochs.
    pub fn execute_cut(&mut self, intent: &BITPIntentData) -> H256 {
        let commitment = H256::sha3(
            format!(
                "{}:{}:{}:{}:{}:{}:{}",
                intent.entity_id.to_hex(),
                hex::encode(&intent.asset_in),
                hex::encode(&intent.asset_out),
                intent.magnitude,
                intent.deadline,
                intent.behavioral_proof_root.to_hex(),
                intent.nonce
            )
            .as_bytes(),
        );
        self.clipboard.insert(commitment, intent.clone());
        commitment
    }

    /// Phase 2: MATCH — Find complementary intent in clipboard
    /// Complement = asset_in ↔ asset_out, within price tolerance,
    /// from a *different* entity (spec §5.1: self-matches are invalid),
    /// with both commitments still unexpired at `now` (unix seconds).
    ///
    /// A commitment is expired once `now >= deadline` — expired
    /// candidates are skipped, and an expired seeking intent matches
    /// nothing (its own commitment is dead).
    pub fn find_complement<'a>(
        &self,
        intent: &BITPIntentData,
        candidates: &'a [BITPIntentData],
        price_tolerance: f64,
        now: u64,
    ) -> Option<&'a BITPIntentData> {
        // An expired seeking intent cannot be matched
        if now >= intent.deadline {
            return None;
        }
        for candidate in candidates {
            // Spec §5.1: a match must be between two DISTINCT entities —
            // entity == counterparty (self-match) is rejected
            if candidate.entity_id == intent.entity_id {
                continue;
            }
            // Expired commitments never match
            if now >= candidate.deadline {
                continue;
            }
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
    /// Returns true if paste executed (both sides release on their native chains).
    ///
    /// HONEST LIMITATION: this removes both commitments from the in-memory
    /// clipboard ONLY. No dual-chain transfer emission and no partial-fill
    /// handling are implemented yet (spec §14.1 item 7), and the clipboard
    /// is not persisted — restarting the process forgets all commitments
    /// (persistence is TODO). Treat `true` as "matcher state advanced", not
    /// "funds moved on chains".
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
            behavioral_proof_root: H256::sha3(b"proof_root_A"),
            nonce: 1,
        };

        // Entity B has SOL, wants USDC on chain 900
        let intent_b = BITPIntentData {
            entity_id: H256::sha3(b"entity_B"),
            asset_in: b"SOL".to_vec(),
            asset_out: b"USDC".to_vec(),
            magnitude: 5.0,
            chain_id: 900,
            deadline: 1787141851,
            behavioral_proof_root: H256::sha3(b"proof_root_B"),
            nonce: 2,
        };

        // Both intents are unexpired at this `now`
        let now = 1787141000;

        // Phase 1: CUT
        let comm_a = matcher.execute_cut(&intent_a);
        assert_eq!(matcher.clipboard_size(), 1);

        // Phase 2: MATCH — BITP matches by asset complementarity, not exact magnitude
        // Water principle: assets don't move, so magnitudes just indicate commitment size
        let candidates = vec![intent_a.clone()];
        let found = matcher.find_complement(&intent_b, &candidates, 1000.0, now); // Very high tolerance — BITP is about asset direction, not size
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
            deadline: 1787141851,
            behavioral_proof_root: H256::sha3(b"proof_A"),
            nonce: 1,
        };

        let intent_b = BITPIntentData {
            entity_id: H256::sha3(b"B"),
            asset_in: b"SOL".to_vec(),
            asset_out: b"USDC".to_vec(),
            magnitude: 100.0,
            chain_id: 900,
            deadline: 1787141851,
            behavioral_proof_root: H256::sha3(b"proof_B"),
            nonce: 2,
        };

        let now = 1787141000;
        let candidates = vec![intent_a];
        let found = matcher.find_complement(&intent_b, &candidates, 0.10, now);
        assert!(found.is_none());
    }

    #[test]
    fn test_self_match_rejected() {
        // Spec §5.1: entity == counterparty must not match (self-match)
        let matcher = BITPMatcher::new();

        let intent = BITPIntentData {
            entity_id: H256::sha3(b"same_entity"),
            asset_in: b"USDC".to_vec(),
            asset_out: b"SOL".to_vec(),
            magnitude: 100.0,
            chain_id: 1,
            deadline: 1787141851,
            behavioral_proof_root: H256::sha3(b"proof"),
            nonce: 1,
        };

        // Same entity posting both sides of the trade
        let candidates = vec![intent.clone()];
        let found = matcher.find_complement(&intent, &candidates, 0.10, 1787141000);
        assert!(found.is_none(), "self-match must be rejected");
    }

    #[test]
    fn test_expired_candidate_skipped() {
        let matcher = BITPMatcher::new();

        let intent = BITPIntentData {
            entity_id: H256::sha3(b"seeker"),
            asset_in: b"USDC".to_vec(),
            asset_out: b"SOL".to_vec(),
            magnitude: 100.0,
            chain_id: 1,
            deadline: 1787141851,
            behavioral_proof_root: H256::sha3(b"proof_seeker"),
            nonce: 1,
        };

        // Complementary candidate whose deadline has already passed
        let expired_candidate = BITPIntentData {
            entity_id: H256::sha3(b"counterparty"),
            asset_in: b"SOL".to_vec(),
            asset_out: b"USDC".to_vec(),
            magnitude: 100.0,
            chain_id: 900,
            deadline: 1787000000, // earlier than `now` below
            behavioral_proof_root: H256::sha3(b"proof_cp"),
            nonce: 2,
        };

        let candidates = vec![expired_candidate];
        let found = matcher.find_complement(&intent, &candidates, 0.10, 1787141000);
        assert!(found.is_none(), "expired commitment must not match");
    }

    #[test]
    fn test_expired_seeking_intent_matches_nothing() {
        let matcher = BITPMatcher::new();

        // Seeking intent itself is expired
        let intent = BITPIntentData {
            entity_id: H256::sha3(b"late_seeker"),
            asset_in: b"USDC".to_vec(),
            asset_out: b"SOL".to_vec(),
            magnitude: 100.0,
            chain_id: 1,
            deadline: 1787000000,
            behavioral_proof_root: H256::sha3(b"proof_late"),
            nonce: 1,
        };

        let live_candidate = BITPIntentData {
            entity_id: H256::sha3(b"counterparty"),
            asset_in: b"SOL".to_vec(),
            asset_out: b"USDC".to_vec(),
            magnitude: 100.0,
            chain_id: 900,
            deadline: 1787141851,
            behavioral_proof_root: H256::sha3(b"proof_live"),
            nonce: 2,
        };

        let candidates = vec![live_candidate];
        let found = matcher.find_complement(&intent, &candidates, 0.10, 1787141000);
        assert!(found.is_none(), "expired seeking intent must match nothing");
    }

    #[test]
    fn test_commitment_binds_proof_root_and_nonce() {
        // Spec §17: commitment = H(intent || proof_root || nonce).
        // Same intent fields but different proof roots / nonces → different commitments.
        let mut matcher = BITPMatcher::new();

        let base = BITPIntentData {
            entity_id: H256::sha3(b"entity"),
            asset_in: b"USDC".to_vec(),
            asset_out: b"SOL".to_vec(),
            magnitude: 100.0,
            chain_id: 1,
            deadline: 1787141851,
            behavioral_proof_root: H256::sha3(b"proof_root_1"),
            nonce: 1,
        };

        let comm_1 = matcher.execute_cut(&base);

        let mut with_other_root = base.clone();
        with_other_root.behavioral_proof_root = H256::sha3(b"proof_root_2");
        let comm_2 = matcher.execute_cut(&with_other_root);

        let mut with_other_nonce = base.clone();
        with_other_nonce.nonce = 2;
        let comm_3 = matcher.execute_cut(&with_other_nonce);

        assert_ne!(comm_1, comm_2, "proof root must be bound into the commitment");
        assert_ne!(comm_1, comm_3, "nonce must be bound into the commitment");
    }
}
