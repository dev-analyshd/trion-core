//! TravelRuleCompliance — ink! (Polkadot PVM)
//! ZK FATF Travel Rule proof storage
#![cfg_attr(not(feature = "std"), no_std)]
use ink::storage::Mapping;

#[ink::contract]
mod travel_rule {
    #[ink(storage)]
    pub struct TravelRule {
        proofs: Mapping<AccountId, Hash>,
    }

    impl TravelRule {
        #[ink(constructor)]
        pub fn new() -> Self {
            Self { proofs: Mapping::default() }
        }

        #[ink(message)]
        pub fn submit_proof(&mut self, entity: AccountId, proof_hash: Hash) {
            self.proofs.insert(entity, &proof_hash);
        }

        #[ink(message)]
        pub fn has_proof(&self, entity: AccountId) -> bool {
            self.proofs.contains(entity)
        }
    }
}
