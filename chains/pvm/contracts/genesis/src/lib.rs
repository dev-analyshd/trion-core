//! GenesisCommitment — ink! (Polkadot PVM)
#![cfg_attr(not(feature = "std"), no_std)]
use ink::storage::Mapping;

#[ink::contract]
mod genesis {
    #[ink(storage)]
    pub struct Genesis {
        commitments: Mapping<AccountId, Balance>,
        conf_genesis: Mapping<AccountId, u128>, // ×1e6
    }

    impl Genesis {
        #[ink(constructor)]
        pub fn new() -> Self {
            Self { commitments: Mapping::default(), conf_genesis: Mapping::default() }
        }

        #[ink(message)]
        pub fn commit(&mut self, entity: AccountId, amount: Balance, confidence: u128) {
            self.commitments.insert(entity, &amount);
            self.conf_genesis.insert(entity, &confidence);
        }

        #[ink(message)]
        pub fn get_confidence(&self, entity: AccountId) -> u128 {
            self.conf_genesis.get(entity).unwrap_or(0)
        }
    }
}
