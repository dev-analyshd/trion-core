//! BTCPRoute — ink! (Polkadot PVM)
//! Anchor BH → execution BH route tracking
#![cfg_attr(not(feature = "std"), no_std)]
use ink::storage::Mapping;

#[ink::contract]
mod btcp_route {
    #[ink(storage)]
    pub struct BtcpRoute {
        routes: Mapping<Hash, RouteData>,
        admin: AccountId,
    }

    #[derive(scale::Encode, scale::Decode, Clone)]
    #[cfg_attr(feature = "std", derive(Debug, PartialEq))]
    pub struct RouteData {
        anchor_bh: Hash,
        execution_bh: Hash,
        entity_id: AccountId,
        gas_saved: Balance,
        finalized: bool,
    }

    impl BtcpRoute {
        #[ink(constructor)]
        pub fn new() -> Self {
            Self { routes: Mapping::default(), admin: Self::env().caller() }
        }

        #[ink(message)]
        pub fn register_route(&mut self, route_id: Hash, anchor_bh: Hash, execution_bh: Hash, entity_id: AccountId, gas_saved: Balance) {
            self.routes.insert(route_id, &RouteData { anchor_bh, execution_bh, entity_id, gas_saved, finalized: false });
        }

        #[ink(message)]
        pub fn finalize(&mut self, route_id: Hash) {
            if let Some(mut route) = self.routes.get(route_id) {
                route.finalized = true;
                self.routes.insert(route_id, &route);
            }
        }

        #[ink(message)]
        pub fn get_route(&self, route_id: Hash) -> Option<RouteData> {
            self.routes.get(route_id)
        }
    }
}
