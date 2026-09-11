//! bitp_matcher.rs — CUT/MATCH/PASTE engine for illiquid pairs
//! Per BTCP Master Implementation Spec §Water Principle 1
//!
//! PASTE phase (Phase 3) implements C2 §5.1 dual-chain native release:
//!   * chain_A: "entity_B on chain_B has committed asset_Y. Release
//!     asset_X to entity_B natively."  ← adapter_a.execute_transfer
//!   * chain_B: "entity_A on chain_A has committed asset_X. Release
//!     asset_Y to entity_A natively."  ← adapter_b.execute_transfer
//!   * BTCP_ESCROW holds until both native transfers confirmed.
//!
//! ZERO-BRIDGE INVARIANT: there is NO lock / mint / wrap / bridge call
//! anywhere in the PASTE path. Assets never leave their native chain —
//! only behavioral commitments cross. The forbidden-token-free body of
//! `execute_paste` is asserted at test time by
//! `test_execute_paste_body_has_no_forbidden_primitives` (source-grep
//! over `include_str!`).

use crate::adapters::{AdapterError, ChainAdapter, ExecutionReceipt};
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
    /// python canonical encoder (`_canonical_intent_field` in
    /// core/btcp/modules.py — the follow-on-1 canonical byte-format ruling):
    /// None → "none", enums → their spec names, allow-lists → bracketed
    /// comma-join `[1,137]` (byte-identical to the python list rule).
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
                "[{}]",
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

/// Python-repr-compatible f64 text for the canonical §17 CUT commitment
/// (follow-on-1 byte-format ruling): Python `repr(100.0)` == `"100.0"`
/// (finite floats always render a decimal point or exponent) while
/// Rust's `{}` prints `"100"`. Finite integral magnitudes inside
/// |v| < 1e16 therefore gain the trailing `.0` so the commitment text is
/// byte-identical with the python encoder. Beyond 1e16 Python switches
/// to scientific notation (`repr(1e16)` == `"1e+16"`) which Rust's
/// Display never emits — the ruling's documented float domain boundary;
/// the canonical corpus stays inside it.
fn py_repr_f64(v: f64) -> String {
    if v.is_finite() && v == v.trunc() && v.abs() < 1e16 {
        format!("{:.1}", v)
    } else {
        format!("{}", v)
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
    ///
    /// CANONICAL BYTE FORMAT (follow-on-1 ruling, byte-identical with
    /// `core/btcp/modules.py::AkashicClipboard._commitment`): every
    /// segment follows the python canonical encoder — hex WITHOUT the
    /// 0x prefix (`hex::encode`, so a zero proof root is `"0" * 64`,
    /// matching the python None fallback), floats via `py_repr_f64`
    /// (python `repr` semantics — integral values keep the `.0`),
    /// None → "none", allow-lists bracketed. Corpus:
    /// tests/golden/bitp_cut_commitment_vectors.json; static parity
    /// pin: tests/golden/test_bitp_cut_commitment_vectors.py (no cargo
    /// in this sandbox — the Rust side is pinned statically; cargo
    /// build/test remains the documented unverified boundary).
    pub fn execute_cut(&mut self, intent: &BITPIntentData) -> H256 {
        // The first seven segments below are the pre-§4.1 commitment
        // text (byte-identical for those fields); the §4.1 field set is
        // appended as one further segment (append-only extension policy,
        // same as types::Intent::hash() and the python intent hashes) so a
        // different constraint set yields a different commitment.
        let commitment = H256::sha3(
            format!(
                "{}:{}:{}:{}:{}:{}:{}:{}",
                hex::encode(intent.entity_id.0),
                hex::encode(&intent.asset_in),
                hex::encode(&intent.asset_out),
                py_repr_f64(intent.magnitude),
                intent.deadline,
                hex::encode(intent.behavioral_proof_root.0),
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

    /// Phase 3: PASTE — C2 §5.1 dual-chain native release.
    ///
    /// Emits two native transfers — one on chain_A (releasing asset_X
    /// to entity_B), one on chain_B (releasing asset_Y to entity_A) —
    /// and persists one `bitp_clipboard` row per side (status=FILLED).
    /// There is NO lock / mint / wrap / bridge call in this body: each
    /// side is a bare `ChainAdapter::execute_transfer` invocation (the
    /// zero-bridge invariant — assets never leave their native chain).
    ///
    /// R-FAILCLOSED: on either adapter failure or a persistence failure
    /// the matcher rolls back (both commitments re-inserted) and a
    /// named variant of [`PasteOutcome`] is returned — never a silent
    /// `false`. The caller may retry PASTE once the wiring fault is
    /// cleared.
    ///
    /// R-LABELS: tests using this method are labelled SYNTHETIC-DEMO
    /// (intent + adapter are simulated; no real chain interaction).
    pub fn execute_paste(
        &mut self,
        commitment_a: &H256,
        commitment_b: &H256,
        adapter_a: &dyn ChainAdapter,
        adapter_b: &dyn ChainAdapter,
        store: &mut dyn ClipboardPersistence,
        now: u64,
    ) -> PasteOutcome {
        // Pull both commitments out of the clipboard. If either is
        // missing the match is stale — fail-closed, state untouched.
        let intent_a = match self.clipboard.remove(commitment_a) {
            Some(d) => d,
            None => return PasteOutcome::CommitmentNotFound,
        };
        let intent_b = match self.clipboard.remove(commitment_b) {
            Some(d) => d,
            None => {
                // Roll back A (matcher state stays consistent)
                self.clipboard.insert(*commitment_a, intent_a);
                return PasteOutcome::CommitmentNotFound;
            }
        };

        // Build the per-side native transfer payloads. chain_A is
        // entity_A's home chain (intent_a.chain_id); chain_B is
        // entity_B's home chain (intent_b.chain_id).
        let route_a = build_paste_route(&intent_a, &intent_b, *commitment_a);
        let route_b = build_paste_route(&intent_b, &intent_a, *commitment_b);
        let intent_a_native = route_a.intent.clone();
        let intent_b_native = route_b.intent.clone();

        // Chain_A native transfer — entity_A releases asset_X natively
        // on chain_A. NO lock / mint / wrap / bridge call here.
        let receipt_a = match adapter_a.execute_transfer(&intent_a_native, &route_a) {
            Ok(r) => r,
            Err(err) => {
                self.clipboard.insert(*commitment_a, intent_a);
                self.clipboard.insert(*commitment_b, intent_b);
                return PasteOutcome::AdapterAFailed(err);
            }
        };
        // Chain_B native transfer — entity_B releases asset_Y natively
        // on chain_B. NO lock / mint / wrap / bridge call here.
        let receipt_b = match adapter_b.execute_transfer(&intent_b_native, &route_b) {
            Ok(r) => r,
            Err(err) => {
                self.clipboard.insert(*commitment_a, intent_a);
                self.clipboard.insert(*commitment_b, intent_b);
                return PasteOutcome::AdapterBFailed(err);
            }
        };

        // Both native transfers confirmed — persist clipboard rows
        // (FILLED). BLO is NOT created here (BLO exists only for the
        // no-match case per spec §5.1, see `blo_scheduler`).
        if let Err(err) = store.record_paste(commitment_a, commitment_b, now, false) {
            self.clipboard.insert(*commitment_a, intent_a);
            self.clipboard.insert(*commitment_b, intent_b);
            return PasteOutcome::PersistFailed(err);
        }
        if let Err(err) = store.record_paste(commitment_b, commitment_a, now, false) {
            // Best-effort rollback signal; the first row is already
            // persisted but the matcher state must stay consistent —
            // surface the named error so the operator can reconcile.
            self.clipboard.insert(*commitment_a, intent_a);
            self.clipboard.insert(*commitment_b, intent_b);
            return PasteOutcome::PersistFailed(err);
        }

        PasteOutcome::Success {
            receipt_a,
            receipt_b,
        }
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

// ── PASTE persistence layer (schema.sql `bitp_clipboard`) ────────────────────

/// Persistence layer for the `bitp_clipboard` table (schema.sql L489).
/// Mirrors the Python `BtcpStateStore.record_bitp_clipboard` call-site —
/// the matcher writes one row per PASTE-completed side carrying the
/// schema columns `commitment_hash`, `counterparty_hash`, `matched_at`,
/// `blo_created`. Implementations may target SQLite, Postgres/TimescaleDB
/// or in-memory (tests). Store failure does NOT corrupt matcher state —
/// [`BITPMatcher::execute_paste`] rolls the clipboard back on Err.
pub trait ClipboardPersistence {
    /// Record a FILLED clipboard row. `blo_created` is FALSE on every
    /// PASTE success — Behavioral Limit Orders are created by
    /// `blo_scheduler` only when MATCH fails (spec §5.1).
    fn record_paste(
        &mut self,
        commitment_hash: &H256,
        counterparty_hash: &H256,
        matched_at: u64,
        blo_created: bool,
    ) -> Result<(), ClipboardPersistError>;
}

/// Named persistence failures (R-FAILCLOSED). Never a silent `false`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ClipboardPersistError {
    /// No persistence backend wired (mirrors `AdapterError::NotConnected`).
    NotWired,
    /// The write was rejected (duplicate key, store down, schema mismatch).
    WriteFailed { reason: &'static str },
}

/// Default in-memory clipboard store — mirrors the `bitp_clipboard` table
/// column-for-column for SYNTHETIC-DEMO tests and off-chain simulations.
#[derive(Debug, Default)]
pub struct InMemoryClipboardStore {
    rows: Vec<ClipboardRow>,
}

/// One persisted clipboard row (one per PASTE-completed side).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ClipboardRow {
    pub commitment_hash: H256,
    pub counterparty_hash: H256,
    pub matched_at: u64,
    pub blo_created: bool,
}

impl InMemoryClipboardStore {
    /// Empty store — SYNTHETIC-DEMO only.
    pub fn new() -> Self {
        Self::default()
    }

    /// All persisted rows (insertion order).
    pub fn rows(&self) -> &[ClipboardRow] {
        &self.rows
    }
}

impl ClipboardPersistence for InMemoryClipboardStore {
    fn record_paste(
        &mut self,
        commitment_hash: &H256,
        counterparty_hash: &H256,
        matched_at: u64,
        blo_created: bool,
    ) -> Result<(), ClipboardPersistError> {
        self.rows.push(ClipboardRow {
            commitment_hash: *commitment_hash,
            counterparty_hash: *counterparty_hash,
            matched_at,
            blo_created,
        });
        Ok(())
    }
}

// ── PASTE outcome (R-FAILCLOSED: named, not boolean) ─────────────────────────

/// Outcome of the C2 §5.1 PASTE phase. Replaces the prior `bool` return
/// — every failure mode is named so the caller can branch on it.
///
/// NOTE: does not derive `PartialEq` because [`ExecutionReceipt`] (in the
/// `adapters` module) is intentionally `Debug + Clone` only — comparing two
/// receipts by structural equality is meaningless for real chain
/// responses (different tx hashes / block numbers per attempt). Tests
/// branch via `match` / `matches!` instead.
#[derive(Debug, Clone)]
pub enum PasteOutcome {
    /// Both native transfers confirmed; both clipboard rows persisted.
    Success {
        /// Chain_A native transfer receipt (entity_A released asset_X).
        receipt_a: ExecutionReceipt,
        /// Chain_B native transfer receipt (entity_B released asset_Y).
        receipt_b: ExecutionReceipt,
    },
    /// One or both commitments not in the clipboard — match is stale or
    /// already PASTEd. Matcher state untouched.
    CommitmentNotFound,
    /// Chain_A adapter failed (named error). Matcher state rolled back.
    AdapterAFailed(AdapterError),
    /// Chain_B adapter failed (named error). Matcher state rolled back.
    AdapterBFailed(AdapterError),
    /// Clipboard persistence rejected the write. Matcher state rolled back
    /// (the in-memory clipboard is consistent; the partial store row is
    /// surfaced to the operator via the named error).
    PersistFailed(ClipboardPersistError),
}

// ── PASTE payload builders ───────────────────────────────────────────────────

/// Build the per-side [`Route`] for the PASTE native transfer. The
/// intent's source_chain is the entity's home chain (where the native
/// transfer executes); dest_chain is the counterparty's chain (carried
/// for the adapter's routing logic — the transfer itself is single-chain
/// native, no bridge contract).
fn build_paste_route(
    data: &BITPIntentData,
    counterparty: &BITPIntentData,
    commitment: H256,
) -> Route {
    let intent = Intent {
        intent_id: commitment,
        entity_id: data.entity_id,
        source_address: String::new(),
        dest_address: String::new(),
        source_chain: data.chain_id,
        dest_chain: counterparty.chain_id,
        asset_in: String::from_utf8_lossy(&data.asset_in).into_owned(),
        asset_out: String::from_utf8_lossy(&data.asset_out).into_owned(),
        // SYNTHETIC-DEMO magnitude → u128 truncation (the matcher's
        // f64 magnitude is a routing hint; the on-chain amount is the
        // adapter's responsibility, derived from the receipt).
        amount_in: data.magnitude as u128,
        intent_type: data.action.clone(),
        deadline: data.deadline,
        nonce: data.nonce,
        constraints: build_constraints(data),
        btcp_version: data.btcp_version.clone(),
    };
    Route {
        route_id: commitment,
        intent,
        route_type: RouteType::BITP { commitment_hash: commitment },
        beo_continuity: 0.0,
        btcp_score: 0.0,
        status: RouteStatus::Pending,
        created_at: 0,
    }
}

/// Project the §4.1 spec constraint fields from `BITPIntentData` onto
/// `IntentConstraints` (legacy fields keep their defaults).
fn build_constraints(data: &BITPIntentData) -> IntentConstraints {
    IntentConstraints {
        max_total_gas: data.max_total_gas,
        min_finality: data.min_finality,
        min_nl_score: data.min_nl_score,
        chain_pref: data.chain_pref.clone(),
        privacy: data.privacy,
        ..Default::default()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::adapters::{AdapterError, EvmAdapter, ExecutionReceipt, ExecutionStatus};

    // ── SYNTHETIC-DEMO stub adapter ────────────────────────────────────────────
    //
    // Records every `execute_transfer` invocation so tests can assert the
    // PASTE phase called BOTH chain adapters (chain_A + chain_B). Returns
    // a synthetic confirmed receipt — never a fabricated tx hash from a
    // real chain (the in-crate `EvmAdapter` is honestly NotConnected).
    #[derive(Debug, Default)]
    struct RecordingAdapter {
        chain_id: ChainId,
        transfers: std::cell::RefCell<Vec<(H256, ChainId, ChainId, String, String)>>,
    }

    impl RecordingAdapter {
        fn new(chain_id: ChainId) -> Self {
            RecordingAdapter {
                chain_id,
                transfers: std::cell::RefCell::new(Vec::new()),
            }
        }

        fn transfer_calls(&self) -> Vec<(H256, ChainId, ChainId, String, String)> {
            self.transfers.borrow().clone()
        }

        fn call_count(&self) -> usize {
            self.transfers.borrow().len()
        }
    }

    impl ChainAdapter for RecordingAdapter {
        fn chain_id(&self) -> ChainId {
            self.chain_id
        }

        fn execute_swap(
            &self,
            _intent: &Intent,
            _route: &Route,
        ) -> Result<ExecutionReceipt, AdapterError> {
            Err(AdapterError::UnsupportedOperation {
                chain_id: self.chain_id,
                operation: "execute_swap",
            })
        }

        fn execute_transfer(
            &self,
            intent: &Intent,
            route: &Route,
        ) -> Result<ExecutionReceipt, AdapterError> {
            self.transfers.borrow_mut().push((
                intent.intent_id,
                intent.source_chain,
                intent.dest_chain,
                intent.asset_in.clone(),
                intent.asset_out.clone(),
            ));
            Ok(ExecutionReceipt {
                tx_hash: H256::sha3(format!("paste:{}:{}", self.chain_id, intent.nonce).as_bytes()),
                chain_id: self.chain_id,
                gas_used: 21_000,
                block_number: 1,
                status: ExecutionStatus::Confirmed,
            })
        }

        fn native_gas_token(&self) -> &str {
            "SYN-DEMO"
        }

        fn estimate_gas(&self, _intent: &Intent) -> Result<u64, AdapterError> {
            Ok(21_000)
        }

        fn verify_execution(
            &self,
            receipt: &ExecutionReceipt,
        ) -> Result<ExecutionStatus, AdapterError> {
            Ok(receipt.status)
        }
    }

    #[test]
    fn test_cut_match_paste() {
        // SYNTHETIC-DEMO: stub adapters confirm both sides + in-memory store.
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

        // Phase 3: PASTE — dual-chain native release via stub adapters
        let comm_b = matcher.execute_cut(&intent_b);
        let adapter_a = RecordingAdapter::new(intent_a.chain_id);
        let adapter_b = RecordingAdapter::new(intent_b.chain_id);
        let mut store = InMemoryClipboardStore::new();
        let outcome =
            matcher.execute_paste(&comm_a, &comm_b, &adapter_a, &adapter_b, &mut store, now);
        assert!(matches!(outcome, PasteOutcome::Success { .. }));
        assert_eq!(matcher.clipboard_size(), 0);
        assert_eq!(adapter_a.call_count(), 1, "chain_A adapter called exactly once");
        assert_eq!(adapter_b.call_count(), 1, "chain_B adapter called exactly once");
        assert_eq!(store.rows().len(), 2, "both sides persisted to bitp_clipboard");
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

    // ── PASTE phase: dual-adapter call + clipboard persistence ─────────────────
    //
    // SYNTHETIC-DEMO (R-LABELS): the following tests use stub adapters and
    // an in-memory clipboard store to assert the C2 §5.1 PASTE behavior
    // off-chain. No real chain interaction occurs.

    /// Helper: build a complementary intent pair (entity_A on chain 1 with
    /// USDC↔SOL, entity_B on chain 900 with SOL↔USDC).
    fn complementary_pair() -> (BITPIntentData, BITPIntentData) {
        let a = BITPIntentData::new(
            H256::sha3(b"entity_A"),
            b"USDC".to_vec(),
            b"SOL".to_vec(),
            1000.0,
            1,
            1787141851,
            H256::sha3(b"proof_root_A"),
            1,
        );
        let b = BITPIntentData::new(
            H256::sha3(b"entity_B"),
            b"SOL".to_vec(),
            b"USDC".to_vec(),
            5.0,
            900,
            1787141851,
            H256::sha3(b"proof_root_B"),
            2,
        );
        (a, b)
    }

    /// SYNTHETIC-DEMO — the canonical PASTE test:
    /// 1. Calls `ChainAdapter::execute_transfer` on BOTH sides (chain_A + chain_B).
    /// 2. Persists one `bitp_clipboard` row per side (counterparty_hash +
    ///    matched_at + blo_created=FALSE per schema.sql L489-L506).
    /// 3. Receipts are confirmed on both sides; matcher clipboard is empty.
    /// 4. NO forbidden primitive (`lock` / `mint` / `wrap` / `bridge`) appears
    ///    in the execute_paste function body (the source-grep sibling test
    ///    asserts that statically).
    #[test]
    fn test_paste_calls_both_adapters_and_persists_clipboard() {
        let mut matcher = BITPMatcher::new();
        let (intent_a, intent_b) = complementary_pair();
        let now = 1787141000;

        let comm_a = matcher.execute_cut(&intent_a);
        let comm_b = matcher.execute_cut(&intent_b);
        assert_eq!(matcher.clipboard_size(), 2);

        let adapter_a = RecordingAdapter::new(intent_a.chain_id);
        let adapter_b = RecordingAdapter::new(intent_b.chain_id);
        let mut store = InMemoryClipboardStore::new();

        let outcome = matcher.execute_paste(
            &comm_a, &comm_b, &adapter_a, &adapter_b, &mut store, now,
        );

        // 1. Success — both native transfers emitted + confirmed.
        let (receipt_a, receipt_b) = match outcome {
            PasteOutcome::Success { receipt_a, receipt_b } => (receipt_a, receipt_b),
            other => panic!("expected Success, got {:?}", other),
        };
        assert_eq!(receipt_a.chain_id, intent_a.chain_id);
        assert_eq!(receipt_b.chain_id, intent_b.chain_id);
        assert_eq!(receipt_a.status, ExecutionStatus::Confirmed);
        assert_eq!(receipt_b.status, ExecutionStatus::Confirmed);

        // 2. Both adapters invoked exactly once, with the right chain routing.
        assert_eq!(adapter_a.call_count(), 1);
        assert_eq!(adapter_b.call_count(), 1);
        let a_call = &adapter_a.transfer_calls()[0];
        let b_call = &adapter_b.transfer_calls()[0];
        assert_eq!(a_call.1, 1,  "chain_A transfer source = entity_A home chain");
        assert_eq!(a_call.2, 900, "chain_A transfer dest = entity_B home chain");
        assert_eq!(a_call.3, "USDC", "asset_X released on chain_A");
        assert_eq!(a_call.4, "SOL",  "asset_Y is the counterparty commitment");
        assert_eq!(b_call.1, 900, "chain_B transfer source = entity_B home chain");
        assert_eq!(b_call.2, 1,   "chain_B transfer dest = entity_A home chain");
        assert_eq!(b_call.3, "SOL",  "asset_Y released on chain_B");
        assert_eq!(b_call.4, "USDC", "asset_X is the counterparty commitment");

        // 3. Clipboard emptied — both commitments consumed by PASTE.
        assert_eq!(matcher.clipboard_size(), 0);

        // 4. Persistence: one row per side, counterparty_hash symmetric,
        //    matched_at = `now`, blo_created = FALSE (BLO is the no-match
        //    scheduler's responsibility per spec §5.1).
        assert_eq!(store.rows().len(), 2);
        let (row_a, row_b) = (&store.rows()[0], &store.rows()[1]);
        assert_eq!(row_a.commitment_hash, comm_a);
        assert_eq!(row_a.counterparty_hash, comm_b);
        assert_eq!(row_a.matched_at, now);
        assert!(!row_a.blo_created, "BLO must NOT be created on PASTE success");
        assert_eq!(row_b.commitment_hash, comm_b);
        assert_eq!(row_b.counterparty_hash, comm_a);
        assert_eq!(row_b.matched_at, now);
        assert!(!row_b.blo_created);
    }

    /// R-FAILCLOSED: real `EvmAdapter` (honestly `NotConnected` in this
    /// crate — no RPC dependency) on chain_A surfaces a named
    /// `AdapterAFailed(NotConnected)` variant. Matcher rolls back so a
    /// retry is possible once the RPC wiring is added.
    #[test]
    fn test_paste_failclosed_when_chain_a_adapter_not_connected() {
        let mut matcher = BITPMatcher::new();
        let (intent_a, intent_b) = complementary_pair();
        let now = 1787141000;

        let comm_a = matcher.execute_cut(&intent_a);
        let comm_b = matcher.execute_cut(&intent_b);

        let real_evm_a = EvmAdapter::new(intent_a.chain_id);
        let stub_b = RecordingAdapter::new(intent_b.chain_id);
        let mut store = InMemoryClipboardStore::new();

        let outcome = matcher.execute_paste(
            &comm_a, &comm_b, &real_evm_a, &stub_b, &mut store, now,
        );
        match outcome {
            PasteOutcome::AdapterAFailed(AdapterError::NotConnected { chain_id, .. }) => {
                assert_eq!(chain_id, intent_a.chain_id);
            }
            other => panic!("expected AdapterAFailed(NotConnected), got {:?}", other),
        }

        // Fail-closed: matcher state rolled back; store untouched.
        assert_eq!(matcher.clipboard_size(), 2, "matcher rolls back on adapter A failure");
        assert_eq!(stub_b.call_count(), 0, "chain_B adapter never reached");
        assert!(store.rows().is_empty(), "no clipboard row persisted on failure");
    }

    /// R-FAILCLOSED: chain_B adapter fails — A succeeded but the matcher
    /// rolls back BOTH commitments so the operator can retry the pair
    /// atomically (the chain_A receipt is real and must be reconciled
    /// off-chain by the caller — surfaced via the named variant).
    #[test]
    fn test_paste_failclosed_when_chain_b_adapter_not_connected() {
        let mut matcher = BITPMatcher::new();
        let (intent_a, intent_b) = complementary_pair();
        let now = 1787141000;

        let comm_a = matcher.execute_cut(&intent_a);
        let comm_b = matcher.execute_cut(&intent_b);

        let stub_a = RecordingAdapter::new(intent_a.chain_id);
        let real_evm_b = EvmAdapter::new(intent_b.chain_id);
        let mut store = InMemoryClipboardStore::new();

        let outcome = matcher.execute_paste(
            &comm_a, &comm_b, &stub_a, &real_evm_b, &mut store, now,
        );
        match outcome {
            PasteOutcome::AdapterBFailed(AdapterError::NotConnected { chain_id, .. }) => {
                assert_eq!(chain_id, intent_b.chain_id);
            }
            other => panic!("expected AdapterBFailed(NotConnected), got {:?}", other),
        }

        // A's receipt is lost on rollback — the caller reconciles off-chain.
        // Matcher state is consistent: both commitments still resolvable.
        assert_eq!(matcher.clipboard_size(), 2, "matcher rolls back on adapter B failure");
        assert_eq!(stub_a.call_count(), 1, "chain_A adapter was reached (then rolled back)");
        assert!(store.rows().is_empty(), "no clipboard row persisted on failure");
    }

    /// R-FAILCLOSED: stale or already-PASTEd commitments surface as a named
    /// `CommitmentNotFound` variant — never a silent `false`.
    #[test]
    fn test_paste_failclosed_when_commitment_missing() {
        let mut matcher = BITPMatcher::new();
        let (intent_a, _intent_b) = complementary_pair();
        let now = 1787141000;

        // Only A is posted — B was never CUT (or already PASTEd).
        let comm_a = matcher.execute_cut(&intent_a);
        let bogus_comm_b = H256::sha3(b"never_posted");

        let adapter_a = RecordingAdapter::new(intent_a.chain_id);
        let adapter_b = RecordingAdapter::new(900);
        let mut store = InMemoryClipboardStore::new();

        let outcome = matcher.execute_paste(
            &comm_a, &bogus_comm_b, &adapter_a, &adapter_b, &mut store, now,
        );
        assert!(matches!(outcome, PasteOutcome::CommitmentNotFound));

        // A is still in the clipboard (rolled back); no adapter was called.
        assert_eq!(matcher.clipboard_size(), 1);
        assert_eq!(adapter_a.call_count(), 0);
        assert_eq!(adapter_b.call_count(), 0);
        assert!(store.rows().is_empty());
    }

    /// R-FAILCLOSED: persistence layer rejects the write → named variant.
    /// Matcher state is rolled back; the partial store row is surfaced.
    #[test]
    fn test_paste_failclosed_when_persistence_rejects() {
        struct BrokenStore;
        impl ClipboardPersistence for BrokenStore {
            fn record_paste(
                &mut self,
                _commitment_hash: &H256,
                _counterparty_hash: &H256,
                _matched_at: u64,
                _blo_created: bool,
            ) -> Result<(), ClipboardPersistError> {
                Err(ClipboardPersistError::WriteFailed { reason: "test-injected failure" })
            }
        }

        let mut matcher = BITPMatcher::new();
        let (intent_a, intent_b) = complementary_pair();
        let now = 1787141000;
        let comm_a = matcher.execute_cut(&intent_a);
        let comm_b = matcher.execute_cut(&intent_b);

        let adapter_a = RecordingAdapter::new(intent_a.chain_id);
        let adapter_b = RecordingAdapter::new(intent_b.chain_id);
        let mut broken = BrokenStore;

        let outcome = matcher.execute_paste(
            &comm_a, &comm_b, &adapter_a, &adapter_b, &mut broken, now,
        );
        match outcome {
            PasteOutcome::PersistFailed(ClipboardPersistError::WriteFailed { reason }) => {
                assert!(reason.contains("test-injected"));
            }
            other => panic!("expected PersistFailed(WriteFailed), got {:?}", other),
        }
        // Both adapters fired (transfers were emitted), but persistence
        // failed → matcher rolls back so the caller can reconcile.
        assert_eq!(adapter_a.call_count(), 1);
        assert_eq!(adapter_b.call_count(), 1);
        assert_eq!(matcher.clipboard_size(), 2, "matcher rolls back on persist failure");
    }

    /// ZERO-BRIDGE INVARIANT — static source-grep test (R-LABELS: this
    /// test is labelled STATIC-SOURCE-GREP). Reads `bitp_matcher.rs` at
    /// compile time via `include_str!` and asserts the `execute_paste`
    /// function body contains NO method or function call of the form
    /// `lock(` / `mint(` / `wrap(` / `bridge(` — these are the FORBIDDEN
    /// primitives of the BTCP zero-bridge protocol (no asset ever leaves
    /// its native chain).
    ///
    /// This test runs at unit-test time but reads the source statically
    /// (no filesystem access at runtime). It will fail the moment a
    /// forbidden call is introduced into `execute_paste`.
    #[test]
    fn test_execute_paste_body_has_no_forbidden_primitives() {
        let src = include_str!("bitp_matcher.rs");

        // Locate the execute_paste function and its body (matched-brace scan).
        let fn_start = src
            .find("pub fn execute_paste(")
            .expect("execute_paste function not found in source");
        let body_open = src[fn_start..]
            .find('{')
            .expect("execute_paste body open brace found")
            + fn_start
            + 1;
        let bytes = src.as_bytes();
        let mut depth: i32 = 1;
        let mut i = body_open;
        while depth > 0 && i < bytes.len() {
            match bytes[i] {
                b'{' => depth += 1,
                b'}' => depth -= 1,
                _ => {}
            }
            i += 1;
        }
        assert!(depth == 0, "execute_paste body braces balance");
        let body = &src[body_open..i - 1];

        // The forbidden primitive call-forms. Substring scan suffices: a
        // method call `adapter.lock(` and a bare function `lock(` both
        // contain the literal `lock(`. We deliberately do NOT ban the
        // bare words `lock` / `mint` / `wrap` / `bridge` — only the call
        // form — so doc-comments mentioning the words remain legal.
        let forbidden_call_forms = [".lock(", ".mint(", ".wrap(", ".bridge("];
        for token in forbidden_call_forms {
            assert!(
                !body.contains(token),
                "FORBIDDEN call form `{}` found in execute_paste body — BTCP zero-bridge invariant violated",
                token
            );
        }
        // Also ban bare function-form calls (no receiver), guarded by a
        // word-boundary check via the preceding char being non-ident.
        for bare in ["lock(", "mint(", "wrap(", "bridge("] {
            // find every occurrence; ensure each is preceded by an identifier
            // char (which would make it a method call already covered above)
            // OR is itself a forbidden bare call.
            let mut from = 0usize;
            while let Some(idx) = body[from..].find(bare) {
                let abs = from + idx;
                let preceding = if abs == 0 { b' ' } else { body.as_bytes()[abs - 1] };
                // If the preceding char is an identifier-continuation
                // (alnum or underscore), this is a method call already
                // checked above (e.g. `adapter.lock(`). Reject only when
                // it is a bare function call: preceding char is NOT an
                // identifier char.
                let is_ident_char = preceding.is_ascii_alphanumeric() || preceding == b'_';
                if !is_ident_char {
                    panic!(
                        "FORBIDDEN bare call `{}` in execute_paste body at offset {} — zero-bridge invariant",
                        bare, abs
                    );
                }
                from = abs + bare.len();
            }
        }
    }
}
