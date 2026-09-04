//! bitp_matcher.rs — CUT/MATCH/PASTE engine for illiquid pairs
//! Per BTCP Master Implementation Spec §Water Principle 1

use crate::types::*;
use std::collections::HashMap;

/// BITP Intent — Behavioral Information Transfer Protocol
/// Water carries minerals: assets don't move, behavioral commitments do.
///
/// This is the **Akashic clipboard entry** the matcher stores: the
/// §4.1 intent field set PLUS the §17 proof binding
/// (`behavioral_proof_root`) that makes each CUT commitment unique per
/// behavioral state. The §4.1 constraint fields below mirror the python
/// twins (`core/btcp/modules.py` `BITPIntent`, `adapters/__init__.py`
/// `BTCPIntent`) and `types::Intent` / `types::IntentConstraints` — all
/// intent representations in the repo now carry the same spec §4.1
/// field set. `deadline` and `nonce` were already legacy fields here and
/// already match the spec (uint64; nonce doubles as the §17 replay
/// protection counter).
///
/// Matching (`find_complement`) uses only entity / assets / magnitude /
/// deadline — the §4.1 fields are routing constraints carried for the
/// router, not inputs to complementarity — but they ARE bound into the
/// CUT commitment (append-only, see [`BITPMatcher::execute_cut`]), so a
/// different constraint set is a different commitment.
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
    /// CUT commitment per BTCP spec §17; spec §4.1: per-entity
    /// monotonic counter (uint64)
    pub nonce: u64,
    // ── BTCP Master Spec §4.1 field set (defaults per spec) ─────────
    /// action: SWAP | TRANSFER | LIQUIDITY | STAKE | BORROW (default SWAP)
    pub action: String,
    /// value: amount in behavioral magnitude units (spec uint256);
    /// `None` = unset — the legacy `magnitude` f64 carries the same
    /// information for matching (mirrors the python representations)
    pub value: Option<u128>,
    /// max_total_gas: USD equivalent across all chains (spec uint128);
    /// `None` = unbounded
    pub max_total_gas: Option<u128>,
    /// min_finality: FAST | STANDARD | SECURE (default STANDARD)
    pub min_finality: MinFinality,
    /// min_nl_score: liquidity-health floor scaled ×1000 (spec name
    /// min_NL_score; default 300 = 0.30)
    pub min_nl_score: u16,
    /// chain_pref: OPTIMAL | SINGLE_CHAIN | allow-list (default OPTIMAL)
    pub chain_pref: ChainPreference,
    /// privacy: PUBLIC | ZK_CREDENTIAL | INVISIBLE (default PUBLIC)
    pub privacy: SpecPrivacy,
    /// btcp_version: semver (default 1.0.0)
    pub btcp_version: SemVer,
}

impl BITPIntentData {
    /// Construct a clipboard entry with the §4.1 spec defaults for the
    /// constraint fields (action=SWAP, value/max_total_gas unbounded,
    /// STANDARD finality, NL floor 300, OPTIMAL routing, PUBLIC privacy,
    /// btcp_version 1.0.0).
    pub fn new(
        entity_id: BEOId,
        asset_in: Vec<u8>,
        asset_out: Vec<u8>,
        magnitude: f64,
        chain_id: ChainId,
        deadline: u64,
        behavioral_proof_root: H256,
        nonce: u64,
    ) -> Self {
        BITPIntentData {
            entity_id,
            asset_in,
            asset_out,
            magnitude,
            chain_id,
            deadline,
            behavioral_proof_root,
            nonce,
            action: "SWAP".to_string(),
            value: None,
            max_total_gas: None,
            min_finality: MinFinality::Standard,
            min_nl_score: 300,
            chain_pref: ChainPreference::Optimal,
            privacy: SpecPrivacy::Public,
            btcp_version: SemVer::new(1, 0, 0),
        }
    }

    /// Deterministic text encoding of the §4.1 field set for the CUT
    /// commitment (append-only extension; see `execute_cut`). Mirrors the
    /// python canonical encoders (`_canonical_intent_field` in
    /// core/btcp/modules.py, `BTCPIntent::_canonical_field` in
    /// adapters/__init__.py): None → "none", enums → their spec names,
    /// allow-lists → comma-joined.
    fn spec_fields_canonical(&self) -> String {
        let min_finality = match self.min_finality {
            MinFinality::Fast => "FAST",
            MinFinality::Standard => "STANDARD",
            MinFinality::Secure => "SECURE",
        };
        let chain_pref = match &self.chain_pref {
            ChainPreference::Optimal => "OPTIMAL".to_string(),
            ChainPreference::SingleChain => "SINGLE_CHAIN".to_string(),
            ChainPreference::Allowed(ids) => format!(
                "ALLOWED[{}]",
                ids.iter()
                    .map(|id| id.to_string())
                    .collect::<Vec<_>>()
                    .join(",")
            ),
        };
        let privacy = match self.privacy {
            SpecPrivacy::Public => "PUBLIC",
            SpecPrivacy::ZkCredential => "ZK_CREDENTIAL",
            SpecPrivacy::Invisible => "INVISIBLE",
        };
        format!(
            "{}:{}:{}:{}:{}:{}:{}:{}",
            self.action,
            self.value
                .map(|v| v.to_string())
                .unwrap_or_else(|| "none".to_string()),
            self.max_total_gas
                .map(|v| v.to_string())
                .unwrap_or_else(|| "none".to_string()),
            min_finality,
            self.min_nl_score,
            chain_pref,
            privacy,
            self.btcp_version
        )
    }
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
        // The first seven segments below are the pre-§4.1 commitment
        // text (byte-identical for those fields); the §4.1 field set is
        // appended as one further segment (append-only extension policy,
        // same as types::Intent::hash() and the python intent hashes) so a
        // different constraint set yields a different commitment.
        let commitment = H256::sha3(
            format!(
                "{}:{}:{}:{}:{}:{}:{}:{}",
                intent.entity_id.to_hex(),
                hex::encode(&intent.asset_in),
                hex::encode(&intent.asset_out),
                intent.magnitude,
                intent.deadline,
                intent.behavioral_proof_root.to_hex(),
                intent.nonce,
                intent.spec_fields_canonical()
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
        let intent_a = BITPIntentData::new(
            H256::sha3(b"entity_A"),
            b"USDC".to_vec(),
            b"SOL".to_vec(),
            1000.0,
            1,
            1787141851,
            H256::sha3(b"proof_root_A"),
            1,
        );

        // Entity B has SOL, wants USDC on chain 900
        let intent_b = BITPIntentData::new(
            H256::sha3(b"entity_B"),
            b"SOL".to_vec(),
            b"USDC".to_vec(),
            5.0,
            900,
            1787141851,
            H256::sha3(b"proof_root_B"),
            2,
        );

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

        let intent_a = BITPIntentData::new(
            H256::sha3(b"A"),
            b"ETH".to_vec(),
            b"BTC".to_vec(),
            1.0,
            1,
            1787141851,
            H256::sha3(b"proof_A"),
            1,
        );

        let intent_b = BITPIntentData::new(
            H256::sha3(b"B"),
            b"SOL".to_vec(),
            b"USDC".to_vec(),
            100.0,
            900,
            1787141851,
            H256::sha3(b"proof_B"),
            2,
        );

        let now = 1787141000;
        let candidates = vec![intent_a];
        let found = matcher.find_complement(&intent_b, &candidates, 0.10, now);
        assert!(found.is_none());
    }

    #[test]
    fn test_self_match_rejected() {
        // Spec §5.1: entity == counterparty must not match (self-match)
        let matcher = BITPMatcher::new();

        let intent = BITPIntentData::new(
            H256::sha3(b"same_entity"),
            b"USDC".to_vec(),
            b"SOL".to_vec(),
            100.0,
            1,
            1787141851,
            H256::sha3(b"proof"),
            1,
        );

        // Same entity posting both sides of the trade
        let candidates = vec![intent.clone()];
        let found = matcher.find_complement(&intent, &candidates, 0.10, 1787141000);
        assert!(found.is_none(), "self-match must be rejected");
    }

    #[test]
    fn test_expired_candidate_skipped() {
        let matcher = BITPMatcher::new();

        let intent = BITPIntentData::new(
            H256::sha3(b"seeker"),
            b"USDC".to_vec(),
            b"SOL".to_vec(),
            100.0,
            1,
            1787141851,
            H256::sha3(b"proof_seeker"),
            1,
        );

        // Complementary candidate whose deadline has already passed
        let expired_candidate = BITPIntentData::new(
            H256::sha3(b"counterparty"),
            b"SOL".to_vec(),
            b"USDC".to_vec(),
            100.0,
            900,
            1787000000, // earlier than `now` below
            H256::sha3(b"proof_cp"),
            2,
        );

        let candidates = vec![expired_candidate];
        let found = matcher.find_complement(&intent, &candidates, 0.10, 1787141000);
        assert!(found.is_none(), "expired commitment must not match");
    }

    #[test]
    fn test_expired_seeking_intent_matches_nothing() {
        let matcher = BITPMatcher::new();

        // Seeking intent itself is expired
        let intent = BITPIntentData::new(
            H256::sha3(b"late_seeker"),
            b"USDC".to_vec(),
            b"SOL".to_vec(),
            100.0,
            1,
            1787000000,
            H256::sha3(b"proof_late"),
            1,
        );

        let live_candidate = BITPIntentData::new(
            H256::sha3(b"counterparty"),
            b"SOL".to_vec(),
            b"USDC".to_vec(),
            100.0,
            900,
            1787141851,
            H256::sha3(b"proof_live"),
            2,
        );

        let candidates = vec![live_candidate];
        let found = matcher.find_complement(&intent, &candidates, 0.10, 1787141000);
        assert!(found.is_none(), "expired seeking intent must match nothing");
    }

    #[test]
    fn test_commitment_binds_proof_root_and_nonce() {
        // Spec §17: commitment = H(intent || proof_root || nonce).
        // Same intent fields but different proof roots / nonces → different commitments.
        let mut matcher = BITPMatcher::new();

        let base = BITPIntentData::new(
            H256::sha3(b"entity"),
            b"USDC".to_vec(),
            b"SOL".to_vec(),
            100.0,
            1,
            1787141851,
            H256::sha3(b"proof_root_1"),
            1,
        );

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

    #[test]
    fn test_spec_4_1_defaults_and_commitment_binding() {
        // BTCP Master Spec §4.1: the clipboard entry carries the spec field
        // set with the spec defaults, and the CUT commitment is sensitive to
        // every one of them (append-only binding — a different constraint
        // set must be a different commitment).
        let mut matcher = BITPMatcher::new();

        let base = BITPIntentData::new(
            H256::sha3(b"spec_entity"),
            b"USDC".to_vec(),
            b"SOL".to_vec(),
            100.0,
            1,
            1787141851,
            H256::sha3(b"spec_proof"),
            1,
        );

        // §4.1 defaults per spec
        assert_eq!(base.action, "SWAP");
        assert!(base.value.is_none());
        assert!(base.max_total_gas.is_none());
        assert_eq!(base.min_finality, MinFinality::Standard);
        assert_eq!(base.min_nl_score, 300); // ×1000 → 0.30
        assert_eq!(base.chain_pref, ChainPreference::Optimal);
        assert_eq!(base.privacy, SpecPrivacy::Public);
        assert_eq!(base.btcp_version.to_string(), "1.0.0");
        assert_eq!(base.nonce, 1); // §4.1 nonce (already legacy)

        let comm_base = matcher.execute_cut(&base);

        // Every §4.1 field is bound into the commitment
        let mut with_gas_cap = base.clone();
        with_gas_cap.max_total_gas = Some(31);
        assert_ne!(
            matcher.execute_cut(&with_gas_cap),
            comm_base,
            "max_total_gas must be bound into the commitment"
        );

        let mut with_finality = base.clone();
        with_finality.min_finality = MinFinality::Fast;
        assert_ne!(
            matcher.execute_cut(&with_finality),
            comm_base,
            "min_finality must be bound into the commitment"
        );

        let mut with_nl_floor = base.clone();
        with_nl_floor.min_nl_score = 299;
        assert_ne!(
            matcher.execute_cut(&with_nl_floor),
            comm_base,
            "min_nl_score must be bound into the commitment"
        );

        let mut with_chain_pref = base.clone();
        with_chain_pref.chain_pref = ChainPreference::Allowed(vec![1, 8453]);
        assert_ne!(
            matcher.execute_cut(&with_chain_pref),
            comm_base,
            "chain_pref must be bound into the commitment"
        );

        let mut with_privacy = base.clone();
        with_privacy.privacy = SpecPrivacy::ZkCredential;
        assert_ne!(
            matcher.execute_cut(&with_privacy),
            comm_base,
            "privacy must be bound into the commitment"
        );

        let mut with_version = base.clone();
        with_version.btcp_version = SemVer::new(1, 2, 0);
        assert_ne!(
            matcher.execute_cut(&with_version),
            comm_base,
            "btcp_version must be bound into the commitment"
        );

        let mut with_action = base.clone();
        with_action.action = "TRANSFER".to_string();
        assert_ne!(
            matcher.execute_cut(&with_action),
            comm_base,
            "action must be bound into the commitment"
        );

        let mut with_value = base.clone();
        with_value.value = Some(2u128.pow(99));
        assert_ne!(
            matcher.execute_cut(&with_value),
            comm_base,
            "value must be bound into the commitment"
        );
    }
}
