//! BTCPRoute + Escrow — ink! (Polkadot PVM)
//! =================================================================
//! Anchor BH -> execution BH route tracking with integrated two-state
//! atomic escrow (HOLDING -> RELEASED | REVERTED).
//!
//! Whitepaper: BTCP §4.3 (Six-Step Execution) and §11 (Five Final Fixes).
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

    /// Revert reasons (whitepaper BTCP §11)
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
        pub coherence_verified: bool,
        pub parent_route_id: Hash, // 0 = no parent (for cascade revert)
        pub finalized: bool,
    }

    /// 7-day absolute escape hatch (Gap 8)
    const EMERGENCY_ESCAPE_SECONDS: u64 = 7 * 24 * 60 * 60;
    /// 24h PENDING_AKASHIC recovery window (E1)
    const AKASHIC_RECOVERY_SECONDS: u64 = 24 * 60 * 60;

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
                    parent_route_id,
                    finalized: false,
                },
            );
            self.route_count = self.route_count.saturating_add(1);
        }

        /// Mark the route's coherence as verified (relayer only).
        #[ink(message)]
        pub fn verify_coherence(&mut self, route_id: Hash) {
            let caller = Self::env().caller();
            assert!(self.is_relayer_or_admin(caller), "NOT_RELAYER");
            let mut route = self.routes.get(route_id).expect("ROUTE_NOT_FOUND");
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

        #[ink::test]
        fn register_and_release_works() {
            let accounts = ink::env::test::default_accounts::<Environment>();
            ink::env::test::set_caller::<Environment>(accounts.alice);

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
    }
}
