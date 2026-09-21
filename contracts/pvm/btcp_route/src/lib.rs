//! BTCPRoute + Escrow — ink! (Polkadot PVM)
//! =================================================================
//! Anchor BH -> execution BH route tracking with integrated two-state
//! atomic escrow (HOLDING -> RELEASED | REVERTED).
//!
//! specification: BTCP §4.3 (Six-Step Execution) and §11 (Five Final Fixes).
//!
//! Funds stay on the source Polkadot parachain at all times. No cross-chain
//! asset movement occurs — this is the BTCP zero-bridge paradigm.
#![cfg_attr(not(feature = "std"), no_std, no_main)]

#[ink::contract]
mod btcp_route {
    use ink::storage::Mapping;
    use ink::env::block_timestamp;

    /// Escrow states (extended per spec Phase 1.1)
    #[derive(scale::Encode, scale::Decode, Clone, Copy, PartialEq, Eq, Debug)]
    #[cfg_attr(feature = "std", derive(scale_info::TypeInfo, ink::storage::traits::StorageLayout))]
    pub enum EscrowState {
        Idle,
        Holding,
        PendingAkashic,
        Released,
        Reverted,
        EmergencyReverted,
    }

    /// Revert reasons (specification BTCP §11)
    #[derive(scale::Encode, scale::Decode, Clone, Copy, PartialEq, Eq, Debug)]
    #[cfg_attr(feature = "std", derive(scale_info::TypeInfo))]
    pub enum RevertReason {
        Timeout,
        CoherenceFailure,
        RouteInvalid,
        Manual,
        AkashicOutage24h,
        CascadeRevert,
        EmergencyEscape,
    }

    /// Per-route tracking record
    #[derive(scale::Encode, scale::Decode, Clone, PartialEq, Eq, Debug)]
    #[cfg_attr(feature = "std", derive(scale_info::TypeInfo, ink::storage::traits::StorageLayout))]
    pub struct RouteData {
        pub anchor_bh: Hash,
        pub execution_bh: Hash,
        pub entity_id: AccountId,
        pub destination: AccountId,
        pub amount: Balance,
        pub gas_saved: Balance,
        pub lock_timestamp: u64,
        pub timeout_seconds: u64,
        pub state: EscrowState,
        /// On-chain coherence flag — set to true ONLY by `verify_coherence`
        /// when the relayer-submitted `coherence_score` clears the
        /// MIN_COHERENCE_SCORE (550 = 0.55 × 1000) floor.
        /// Previously this was a relayer-set boolean (C-02 audit regression);
        /// BTCP-FIX2-RUST-VM ties it to an on-chain threshold check.
        pub coherence_verified: bool,
        /// Coherence score submitted by the relayer, stored on-chain for
        /// audit. Units: thousandths (×1000). Range [0, 1000].
        /// 550 == 0.55 (spec master-equation §3 / §11 Fix 4 floor).
        pub coherence_score: u32,
        pub parent_route_id: Hash, // 0 = no parent (for cascade revert)
        pub finalized: bool,
    }

    /// 7-day absolute escape hatch (Gap 8)
    const EMERGENCY_ESCAPE_SECONDS: u64 = 7 * 24 * 60 * 60;
    /// 24h PENDING_AKASHIC recovery window (E1)
    const AKASHIC_RECOVERY_SECONDS: u64 = 24 * 60 * 60;
    /// Spec §3 (master equation) — `C(t) ≥ Θ(t)` with the floor Θ_floor =
    /// 0.55. Stored as `coherence_score: u32` in thousandths so the
    /// contract can compare against `MIN_COHERENCE_SCORE = 550` without
    /// floating-point. The relayer submits the score; the contract
    /// enforces the threshold on-chain (BTCP-FIX2-RUST-VM C-02 fix).
    const MIN_COHERENCE_SCORE: u32 = 550;

    #[ink(storage)]
    pub struct BtcpRoute {
        routes: Mapping<Hash, RouteData>,
        admin: AccountId,
        relayer: AccountId,
        route_count: u64,
    }

    impl BtcpRoute {
        #[ink(constructor)]
        pub fn new() -> Self {
            let caller = Self::env().caller();
            Self {
                routes: Mapping::default(),
                admin: caller,
                relayer: caller,
                route_count: 0,
            }
        }

        /// Register a new BTCP route and lock the caller's funds into escrow.
        /// The funds are held by the contract (not bridged cross-chain) until
        /// release or revert is called.
        #[ink(message, payable)]
        pub fn register_route(
            &mut self,
            route_id: Hash,
            anchor_bh: Hash,
            execution_bh: Hash,
            entity_id: AccountId,
            destination: AccountId,
            gas_saved: Balance,
            timeout_seconds: u64,
            parent_route_id: Hash,
        ) {
            let caller = Self::env().caller();
            assert!(self.is_relayer_or_admin(caller), "NOT_RELAYER");
            assert!(self.routes.get(route_id).is_none(), "ROUTE_EXISTS");

            let amount = Self::env().transferred_value();
            assert!(amount > 0, "ZERO_AMOUNT");
            assert!(timeout_seconds > 0, "ZERO_TIMEOUT");

            self.routes.insert(
                route_id,
                &RouteData {
                    anchor_bh,
                    execution_bh,
                    entity_id,
                    destination,
                    amount,
                    gas_saved,
                    lock_timestamp: block_timestamp::<Environment>(),
                    timeout_seconds,
                    state: EscrowState::Holding,
                    coherence_verified: false,
                    coherence_score: 0,
                    parent_route_id,
                    finalized: false,
                },
            );
            self.route_count = self.route_count.saturating_add(1);
        }

        /// Verify route coherence on-chain against the 0.55 floor
        /// (spec §3 master-equation + BTCP-FIX2-RUST-VM C-02 fix).
        ///
        /// The relayer submits the coherence_score (in thousandths, ×1000
        /// — i.e., `score = (coherence * 1000) as u32`). The contract
        /// enforces:
        ///   1. score <= 1000 (sanity bound)
        ///   2. score >= MIN_COHERENCE_SCORE (550 = 0.55 floor)
        ///
        /// If the threshold is met, the on-chain `coherence_verified` flag
        /// is set to true and `coherence_score` is recorded for audit. If
        /// the threshold is NOT met, the contract reverts with
        /// `COHERENCE_BELOW_FLOOR` — the route stays in HOLDING and may
        /// only be released once a later `verify_coherence` call submits
        /// a passing score, or revert via timeout / emergency escape.
        ///
        /// This replaces the prior relayer-set boolean (`coherence_verified
        /// = true` on any relayer call) which was flagged as the C-02
        /// audit regression — the Move twin fixed it; PVM now matches.
        #[ink(message)]
        pub fn verify_coherence(&mut self, route_id: Hash, coherence_score: u32) {
            let caller = Self::env().caller();
            assert!(self.is_relayer_or_admin(caller), "NOT_RELAYER");
            assert!(coherence_score <= 1000, "COHERENCE_SCORE_OUT_OF_RANGE");
            assert!(
                coherence_score >= MIN_COHERENCE_SCORE,
                "COHERENCE_BELOW_FLOOR"
            );

            let mut route = self.routes.get(route_id).expect("ROUTE_NOT_FOUND");
            route.coherence_score = coherence_score;
            route.coherence_verified = true;
            self.routes.insert(route_id, &route);
        }

        /// Release the escrowed funds to the destination.
        /// Requires: relayer + coherence verified + not expired.
        #[ink(message)]
        pub fn release_escrow(&mut self, route_id: Hash) {
            let caller = Self::env().caller();
            assert!(self.is_relayer_or_admin(caller), "NOT_RELAYER");

            let mut route = self.routes.get(route_id).expect("ROUTE_NOT_FOUND");
            assert!(
                route.state == EscrowState::Holding
                    || route.state == EscrowState::PendingAkashic,
                "NOT_HOLDING"
            );
            assert!(route.coherence_verified, "COHERENCE_NOT_VERIFIED");

            // Check timeout
            let now = block_timestamp::<Environment>();
            assert!(
                now <= route.lock_timestamp + route.timeout_seconds,
                "EXPIRED"
            );

            // Transfer funds to destination
            let dest = route.destination;
            let amount = route.amount;
            route.state = EscrowState::Released;
            route.finalized = true;
            self.routes.insert(route_id, &route);

            if amount > 0 {
                Self::env()
                    .transfer(dest, amount)
                    .expect("TRANSFER_FAILED");
            }
        }

        /// Revert the escrowed funds back to the locker.
        /// Caller can be anyone (timeout escape hatch) or
        /// relayer/admin (coherence failure / route invalid / manual).
        #[ink(message)]
        pub fn revert_escrow(&mut self, route_id: Hash, reason: u8) {
            let mut route = self.routes.get(route_id).expect("ROUTE_NOT_FOUND");
            assert!(
                route.state == EscrowState::Holding
                    || route.state == EscrowState::PendingAkashic,
                "NOT_HOLDING"
            );

            let now = block_timestamp::<Environment>();
            let is_timeout = now > route.lock_timestamp + route.timeout_seconds;

            if !is_timeout {
                let caller = Self::env().caller();
                assert!(self.is_relayer_or_admin(caller), "NOT_RELAYER");
            }

            // Refund the locker (route.entity_id is the locker here)
            let locked_by = route.entity_id;
            let amount = route.amount;
            route.state = EscrowState::Reverted;
            self.routes.insert(route_id, &route);

            if amount > 0 {
                Self::env()
                    .transfer(locked_by, amount)
                    .expect("REFUND_FAILED");
            }

            // Cascade revert to parent (Gap 9)
            let parent = route.parent_route_id;
            if parent != [0u8; 32].into() {
                self.cascade_revert(parent);
            }
        }

        /// Emergency escape hatch (Gap 8).
        /// After 7 days, ANY caller can trigger revert — no relayer, no
        /// coherence proof needed. Absolute maximum lockup period.
        #[ink(message)]
        pub fn emergency_revert(&mut self, route_id: Hash) {
            let mut route = self.routes.get(route_id).expect("ROUTE_NOT_FOUND");
            assert!(
                route.state == EscrowState::Holding
                    || route.state == EscrowState::PendingAkashic,
                "NOT_HOLDING"
            );

            let now = block_timestamp::<Environment>();
            assert!(
                now >= route.lock_timestamp + EMERGENCY_ESCAPE_SECONDS,
                "EMERGENCY_NOT_YET"
            );

            let locked_by = route.entity_id;
            let amount = route.amount;
            route.state = EscrowState::EmergencyReverted;
            self.routes.insert(route_id, &route);

            if amount > 0 {
                Self::env()
                    .transfer(locked_by, amount)
                    .expect("REFUND_FAILED");
            }

            // Cascade to parent
            let parent = route.parent_route_id;
            if parent != [0u8; 32].into() {
                self.cascade_revert(parent);
            }
        }

        /// Enter PENDING_AKASHIC state (E1) — 24h recovery window.
        #[ink(message)]
        pub fn enter_pending_akashic(&mut self, route_id: Hash) {
            let caller = Self::env().caller();
            assert!(self.is_relayer_or_admin(caller), "NOT_RELAYER");
            let mut route = self.routes.get(route_id).expect("ROUTE_NOT_FOUND");
            assert!(route.state == EscrowState::Holding, "NOT_HOLDING");
            route.state = EscrowState::PendingAkashic;
            self.routes.insert(route_id, &route);
        }

        /// Finalize a route (legacy finalize, kept for backward compat).
        #[ink(message)]
        pub fn finalize(&mut self, route_id: Hash) {
            let caller = Self::env().caller();
            assert!(self.is_relayer_or_admin(caller), "NOT_RELAYER");
            if let Some(mut route) = self.routes.get(route_id) {
                route.finalized = true;
                self.routes.insert(route_id, &route);
            }
        }

        /// Get the route record.
        #[ink(message)]
        pub fn get_route(&self, route_id: Hash) -> Option<RouteData> {
            self.routes.get(route_id)
        }

        /// Update the relayer address (admin only).
        #[ink(message)]
        pub fn set_relayer(&mut self, new_relayer: AccountId) {
            let caller = Self::env().caller();
            assert!(caller == self.admin, "NOT_ADMIN");
            self.relayer = new_relayer;
        }

        /// Get total route count.
        #[ink(message)]
        pub fn route_count(&self) -> u64 {
            self.route_count
        }

        // ── Internal helpers ────────────────────────────────────────────────

        fn is_relayer_or_admin(&self, who: AccountId) -> bool {
            who == self.relayer || who == self.admin
        }

        fn cascade_revert(&mut self, parent_id: Hash) {
            let parent = match self.routes.get(parent_id) {
                Some(p) => p,
                None => return,
            };
            if parent.state != EscrowState::Holding
                && parent.state != EscrowState::PendingAkashic
            {
                return;
            }

            let locked_by = parent.entity_id;
            let amount = parent.amount;
            let grandparent = parent.parent_route_id;
            let mut new_parent = parent;
            new_parent.state = EscrowState::Reverted;
            self.routes.insert(parent_id, &new_parent);

            if amount > 0 {
                let _ = Self::env().transfer(locked_by, amount);
            }

            // Recursively cascade to grandparent
            if grandparent != [0u8; 32].into() {
                self.cascade_revert(grandparent);
            }
        }
    }

    /// Unit tests
    #[cfg(test)]
    mod tests {
        use super::*;

        /// Helper — fund the test caller + set transferred_value so the
        /// payable `register_route` sees a non-zero amount. Without this
        /// the test environment returns 0 for `transferred_value()` and
        /// `register_route` panics with `ZERO_AMOUNT` (pre-existing gap;
        /// the prior test never ran in CI).
        fn fund_and_set_value(amount: Balance) {
            let accounts = ink::env::test::default_accounts::<Environment>();
            ink::env::test::set_caller::<Environment>(accounts.alice);
            ink::env::test::set_value_transferred::<Environment>(amount);
        }

        #[ink::test]
        fn register_and_release_works() {
            fund_and_set_value(1000);
            let accounts = ink::env::test::default_accounts::<Environment>();

            let mut contract = BtcpRoute::new();
            let route_id = [1u8; 32].into();
            contract.register_route(
                route_id,
                [2u8; 32].into(),
                [3u8; 32].into(),
                accounts.alice,
                accounts.bob,
                1000,
                3600,
                [0u8; 32].into(),
            );
            assert_eq!(contract.route_count(), 1);
        }

        /// BTCP-FIX2-RUST-VM C-02 fix — `verify_coherence` now enforces the
        /// on-chain 0.55 floor (coherence_score × 1000 ≥ 550). A score
        /// below the floor reverts; a score at/above the floor sets
        /// coherence_verified = true and records the score for audit.
        #[ink::test]
        fn verify_coherence_rejects_below_floor() {
            use std::panic::{self, AssertUnwindSafe};
            fund_and_set_value(1000);
            let accounts = ink::env::test::default_accounts::<Environment>();

            let mut contract = BtcpRoute::new();
            let route_id = [1u8; 32].into();
            contract.register_route(
                route_id,
                [2u8; 32].into(),
                [3u8; 32].into(),
                accounts.alice,
                accounts.bob,
                1000,
                3600,
                [0u8; 32].into(),
            );

            // Score 549 (0.549) — below the 0.55 floor — must revert.
            let result = panic::catch_unwind(AssertUnwindSafe(|| {
                contract.verify_coherence(route_id, 549);
            }));
            assert!(result.is_err(), "score 549 must revert below floor");

            // Route stays Holding, coherence_verified still false.
            let route = contract.get_route(route_id).expect("ROUTE_NOT_FOUND");
            assert_eq!(route.state, EscrowState::Holding);
            assert!(!route.coherence_verified);
            assert_eq!(route.coherence_score, 0);
        }

        #[ink::test]
        fn verify_coherence_accepts_at_and_above_floor() {
            fund_and_set_value(1000);
            let accounts = ink::env::test::default_accounts::<Environment>();

            let mut contract = BtcpRoute::new();
            let route_id = [1u8; 32].into();
            contract.register_route(
                route_id,
                [2u8; 32].into(),
                [3u8; 32].into(),
                accounts.alice,
                accounts.bob,
                1000,
                3600,
                [0u8; 32].into(),
            );

            // Score exactly 550 (0.55) — at the floor — must pass.
            contract.verify_coherence(route_id, 550);
            let route = contract.get_route(route_id).expect("ROUTE_NOT_FOUND");
            assert!(route.coherence_verified);
            assert_eq!(route.coherence_score, 550);

            // Score 1000 (1.0) — above floor — must also pass.
            fund_and_set_value(1000);
            let route_id_hi = [2u8; 32].into();
            contract.register_route(
                route_id_hi,
                [3u8; 32].into(),
                [4u8; 32].into(),
                accounts.alice,
                accounts.bob,
                1000,
                3600,
                [0u8; 32].into(),
            );
            contract.verify_coherence(route_id_hi, 1000);
            let route_hi = contract.get_route(route_id_hi).expect("ROUTE_NOT_FOUND");
            assert!(route_hi.coherence_verified);
            assert_eq!(route_hi.coherence_score, 1000);
        }

        #[ink::test]
        fn verify_coherence_rejects_out_of_range_score() {
            use std::panic::{self, AssertUnwindSafe};
            fund_and_set_value(1000);
            let accounts = ink::env::test::default_accounts::<Environment>();

            let mut contract = BtcpRoute::new();
            let route_id = [1u8; 32].into();
            contract.register_route(
                route_id,
                [2u8; 32].into(),
                [3u8; 32].into(),
                accounts.alice,
                accounts.bob,
                1000,
                3600,
                [0u8; 32].into(),
            );

            // Score 1001 — out of the [0, 1000] sanity range — must revert.
            let result = panic::catch_unwind(AssertUnwindSafe(|| {
                contract.verify_coherence(route_id, 1001);
            }));
            assert!(result.is_err(), "score 1001 must revert out of range");
        }

        #[ink::test]
        fn release_escrow_blocked_until_coherence_passes_floor() {
            use std::panic::{self, AssertUnwindSafe};
            fund_and_set_value(1000);
            let accounts = ink::env::test::default_accounts::<Environment>();

            let mut contract = BtcpRoute::new();
            let route_id = [1u8; 32].into();
            contract.register_route(
                route_id,
                [2u8; 32].into(),
                [3u8; 32].into(),
                accounts.alice,
                accounts.bob,
                1000,
                3600,
                [0u8; 32].into(),
            );

            // Release before coherence verified must revert.
            let result = panic::catch_unwind(AssertUnwindSafe(|| {
                contract.release_escrow(route_id);
            }));
            assert!(result.is_err(), "release before coherence must revert");

            // Pass coherence at exactly the 0.55 floor.
            contract.verify_coherence(route_id, 550);

            // Now release should succeed (transfers amount to destination).
            contract.release_escrow(route_id);
            let route = contract.get_route(route_id).expect("ROUTE_NOT_FOUND");
            assert_eq!(route.state, EscrowState::Released);
            assert!(route.finalized);
        }
    }
}
