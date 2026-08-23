//! TRION PVM Oracle — ink! Smart Contract
//!
//! Polkadot equivalent of TRIONOracleV3.sol.
//! Runs on Polkadot's contracts pallet (PVM / PolkaVM).
//!
//! Messages:
//!   - new()                 — constructor, sets caller as owner
//!   - publish_btcp_route()  — store route with coherence/threshold
//!   - verify_execution()    — returns (is_safe, coherence, threshold)
//!   - add_validator()       — owner-only validator management
//!   - get_route()           — read route state

#![cfg_attr(not(feature = "std"), no_std, no_main)]

#[ink::contract]
mod trion_pvm_oracle {
    use ink::prelude::vec::Vec;
    use ink::storage::Mapping;

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
