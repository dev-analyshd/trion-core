//! ═══════════════════════════════════════════════════════════════════════
//! ⚠ RESEARCH / NON-PRODUCTION — NOT AN ORACLE OF RECORD (audit C-05) ⚠
//! ═══════════════════════════════════════════════════════════════════════
//!
//! TRION PVM Legacy Oracle — ink! Smart Contract (RESEARCH STUB)
//! Runs on Polkadot's contracts pallet (PVM / PolkaVM).
//!
//! WHAT THIS IS: a legacy route-store stub kept for research/reference
//! parity with the shape of TRIONOracleV3.sol. It is NOT the Polkadot
//! equivalent of TRIONOracleV3 and MUST NOT be deployed or wired to any
//! funded consumer as an oracle of record.
//!
//! WHY (audit finding C-05, PVM leg — MEDIUM):
//!   `publish_btcp_route` (lines ~95-136) is an OWNER-VALIDATOR WRITE with
//!   NO signatures, NO quorum, NO validator epoch, NO freshness — any key
//!   in the owner/validator list can mark any route "safe" unilaterally.
//!   The whitepaper invariant "TRION consensus is the only oracle" is
//!   absent here. No funded escrow consumer exists in this repo (the
//!   `gate` crate stores an `oracle_addr` but never calls it; the
//!   `chains/pvm/execute.ts` relayer never invokes this contract), which
//!   is why the tier is MEDIUM, not CRITICAL.
//!
//! HONESTY FLAGS (misuse must be loud, not silent):
//!   - `PRODUCTION_STATUS` const below — "RESEARCH_NON_PRODUCTION".
//!   - `is_oracle_of_record()` message — always returns `false`; any
//!     integrating contract can (and MUST) check it and refuse to bind.
//!   - This header + the doc comments on `publish_btcp_route`.
//!   - CANONICAL_INVARIANTS.md registers the PVM tier as research/partial.
//!
//! CANONICAL UPGRADE PATH (what a production PVM oracle of record needs,
//! per docs/protocol/CANONICAL_CERTIFICATE.md §3.2/§7 — NOT implemented
//! here, Wave-2 follow-on once the epoch registrar lands):
//!   * Signature verification — ink! CAN do it natively:
//!     `ink_env::crypto::verify_signature` supports Ed25519, Sr25519 AND
//!     Ecdsa (secp256k1), so both certificate families (1 = secp256k1
//!     EIP-191 for EVM-compat chains, 2 = Ed25519 raw-P) verify in-contract.
//!     Family choice for PVM per CANONICAL_CERTIFICATE §14.5: sr25519 is
//!     ink!'s native scheme but is NOT family 2 — either standardize PVM on
//!     Ed25519 or register a family 5 (sr25519); that decision is open.
//!   * Hashing — ink! natively provides Keccak256, Sha2x256, Blake2x256
//!     (`ink_env::hash`). The canonical `certificate_hash` is FIPS-202
//!     SHA3-256, which ink! does NOT provide natively — a production tier
//!     must either take the certificate hash as a registrar-published input
//!     (same pattern as the TON tier) or document a Keccak256 consumed-key
//!     deviation. EIP-191 wrapping for family 1 uses Keccak256 (native).
//!   * Epoch registry — `ink::storage::Mapping` supports the per-epoch
//!     validator set (id → pubkey + s_j·d_j weights ×1e6) + total power;
//!     §10.2 grace rule is plain integer arithmetic on `block_timestamp`.
//!   * Weight quorum — the L4.2 tier checks (3·signed > 2·total, etc.) are
//!     u128 integer math, directly expressible; `Self::env()` callers carry
//!     no authority — authority must live in the signatures, exactly like
//!     TRIONOracleV3.submitRouteAttestation.
//!
//! Messages:
//!   - new()                 — constructor, sets caller as owner
//!   - publish_btcp_route()  — store route with coherence/threshold (OWNER
//!                             WRITE — see C-05 note above; not consensus)
//!   - verify_execution()    — returns (is_safe, coherence, threshold) (a
//!                             DATA READ of the stored row, nothing more)
//!   - add_validator()       — owner-only validator management
//!   - get_route()           — read route state
//!   - is_oracle_of_record() — ALWAYS false (honesty flag)

#![cfg_attr(not(feature = "std"), no_std, no_main)]

#[ink::contract]
mod trion_pvm_oracle {
    use ink::prelude::vec::Vec;
    use ink::storage::Mapping;

    // ── Honesty flag (audit C-05) ─────────────────────────────────────────

    /// RESEARCH / NON-PRODUCTION marker. This contract is a legacy
    /// owner-write route store, NOT a TRION oracle of record: it verifies
    /// no signatures, no quorum, no validator epoch. Do not deploy against
    /// value. Pinned by tests/contracts/test_pvm_oracle.py.
    pub const PRODUCTION_STATUS: &str = "RESEARCH_NON_PRODUCTION";

    // ── Storage ───────────────────────────────────────────────────────────────

    #[ink(storage)]
    pub struct TRIONPVMOracle {
        owner:       AccountId,
        validators:  Vec<AccountId>,
        routes:      Mapping<[u8; 32], BtcpRoute>,
        route_count: u64,
        version:     u8,
    }

    // ── Data types ────────────────────────────────────────────────────────────

    #[derive(Debug, Clone, scale::Encode, scale::Decode)]
    #[cfg_attr(feature = "std", derive(scale_info::TypeInfo, ink::storage::traits::StorageLayout))]
    pub struct BtcpRoute {
        pub route_id:        [u8; 32],
        pub anchor_bh:       [u8; 32],
        pub execution_bh:    [u8; 32],
        pub coherence_score: u64,
        pub threshold_score: u64,
        pub published_at:    u64,
        pub publisher:       AccountId,
        pub is_active:       bool,
    }

    // ── Events ────────────────────────────────────────────────────────────────

    #[ink(event)]
    pub struct BtcpRoutePublished {
        #[ink(topic)]
        route_id:        [u8; 32],
        coherence_score: u64,
        threshold_score: u64,
        publisher:       AccountId,
    }

    #[ink(event)]
    pub struct ExecutionVerified {
        #[ink(topic)]
        route_id:  [u8; 32],
        is_safe:   bool,
        coherence: u64,
        threshold: u64,
    }

    // ── Errors ────────────────────────────────────────────────────────────────

    #[derive(Debug, PartialEq, Eq, scale::Encode, scale::Decode)]
    #[cfg_attr(feature = "std", derive(scale_info::TypeInfo))]
    pub enum Error {
        Unauthorized,
        InvalidScore,
        RouteNotFound,
        RouteInactive,
        TooManyValidators,
    }

    pub type Result<T> = core::result::Result<T, Error>;

    // ── Implementation ────────────────────────────────────────────────────────

    impl TRIONPVMOracle {
        /// Constructor — sets caller as owner, version = 3 (TRIONOracleV3 equivalent)
        #[ink(constructor)]
        pub fn new() -> Self {
            Self {
                owner:       Self::env().caller(),
                validators:  Vec::new(),
                routes:      Mapping::default(),
                route_count: 0,
                version:     3,
            }
        }

        /// Publish a BTCP route.
        /// coherence_score and threshold_score are scaled ×1_000_000
        ///
        /// ⚠ C-05 (RESEARCH STUB): this is an OWNER-VALIDATOR data write —
        /// NO validator signatures, NO quorum, NO epoch, NO freshness are
        /// checked. A row written here is NOT TRION consensus evidence and
        /// must never gate the movement of funds. `is_safe` in
        /// `verify_execution()` merely restates `coherence ≥ threshold` for
        /// the row THIS caller wrote. A production tier must replace this
        /// entrypoint with signature-verified attestations over the
        /// canonical certificate payload (see the module header's upgrade
        /// path notes).
        #[ink(message)]
        pub fn publish_btcp_route(
            &mut self,
            route_id:        [u8; 32],
            anchor_bh:       [u8; 32],
            execution_bh:    [u8; 32],
            coherence_score: u64,
            threshold_score: u64,
        ) -> Result<()> {
            if coherence_score > 1_000_000 || threshold_score > 1_000_000 {
                return Err(Error::InvalidScore);
            }
            let caller = self.env().caller();
            if caller != self.owner && !self.validators.contains(&caller) {
                return Err(Error::Unauthorized);
            }

            let route = BtcpRoute {
                route_id,
                anchor_bh,
                execution_bh,
                coherence_score,
                threshold_score,
                published_at: self.env().block_timestamp(),
                publisher:    caller,
                is_active:    true,
            };

            self.routes.insert(route_id, &route);
            self.route_count += 1;

            self.env().emit_event(BtcpRoutePublished {
                route_id,
                coherence_score,
                threshold_score,
                publisher: caller,
            });

            Ok(())
        }

        /// Verify execution — returns (is_safe, coherence, threshold)
        #[ink(message)]
        pub fn verify_execution(&mut self, route_id: [u8; 32]) -> Result<(bool, u64, u64)> {
            let route = self.routes.get(route_id).ok_or(Error::RouteNotFound)?;
            if !route.is_active {
                return Err(Error::RouteInactive);
            }
            let is_safe = route.coherence_score >= route.threshold_score;

            self.env().emit_event(ExecutionVerified {
                route_id,
                is_safe,
                coherence: route.coherence_score,
                threshold: route.threshold_score,
            });

            Ok((is_safe, route.coherence_score, route.threshold_score))
        }

        /// Read a route (non-mutating)
        #[ink(message)]
        pub fn get_route(&self, route_id: [u8; 32]) -> Option<BtcpRoute> {
            self.routes.get(route_id)
        }

        /// Add a validator (owner only, max 20)
        #[ink(message)]
        pub fn add_validator(&mut self, validator: AccountId) -> Result<()> {
            if self.env().caller() != self.owner {
                return Err(Error::Unauthorized);
            }
            if self.validators.len() >= 20 {
                return Err(Error::TooManyValidators);
            }
            if !self.validators.contains(&validator) {
                self.validators.push(validator);
            }
            Ok(())
        }

        /// Remove a validator (owner only)
        #[ink(message)]
        pub fn remove_validator(&mut self, validator: AccountId) -> Result<()> {
            if self.env().caller() != self.owner {
                return Err(Error::Unauthorized);
            }
            self.validators.retain(|v| v != &validator);
            Ok(())
        }

        /// Read-only queries
        #[ink(message)]
        pub fn owner(&self) -> AccountId { self.owner }

        /// HONESTY FLAG (audit C-05): always `false`. This contract is a
        /// research stub, not an oracle of record — integrators MUST refuse
        /// to bind value to any oracle whose `is_oracle_of_record()` is
        /// false. Kept as a message (not just a const) so the mis-binding
        /// attempt is visible on-chain to any auditor.
        #[ink(message)]
        pub fn is_oracle_of_record(&self) -> bool { false }

        #[ink(message)]
        pub fn route_count(&self) -> u64 { self.route_count }

        #[ink(message)]
        pub fn version(&self) -> u8 { self.version }

        #[ink(message)]
        pub fn is_validator(&self, account: AccountId) -> bool {
            self.validators.contains(&account)
        }
    }

    // ── Tests ─────────────────────────────────────────────────────────────────

    #[cfg(test)]
    mod tests {
        use super::*;

        #[ink::test]
        fn test_publish_and_verify() {
            let mut oracle = TRIONPVMOracle::new();
            let route_id   = [1u8; 32];
            let anchor_bh  = [2u8; 32];
            let exec_bh    = [3u8; 32];

            let result = oracle.publish_btcp_route(route_id, anchor_bh, exec_bh, 800_000, 700_000);
            assert!(result.is_ok());

            let (is_safe, coherence, threshold) = oracle.verify_execution(route_id).unwrap();
            assert!(is_safe);
            assert_eq!(coherence, 800_000);
            assert_eq!(threshold, 700_000);
        }

        #[ink::test]
        fn test_invalid_score_rejected() {
            let mut oracle = TRIONPVMOracle::new();
            let result = oracle.publish_btcp_route(
                [1u8; 32], [2u8; 32], [3u8; 32],
                1_100_000,  // > 1_000_000
                700_000,
            );
            assert_eq!(result, Err(Error::InvalidScore));
        }

        #[ink::test]
        fn test_route_not_found() {
            let mut oracle = TRIONPVMOracle::new();
            let result = oracle.verify_execution([99u8; 32]);
            assert_eq!(result, Err(Error::RouteNotFound));
        }
    }
}
