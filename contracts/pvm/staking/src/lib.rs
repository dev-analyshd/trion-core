//! TRIONStaking — ink! (Polkadot PVM)
//! Validator staking with coverage_tier_multiplier
#![cfg_attr(not(feature = "std"), no_std, no_main)]

#[ink::contract]
mod trion_staking {
    use ink::storage::Mapping;
    #[ink(storage)]
    pub struct Staking {
        stakes: Mapping<AccountId, Balance>,
        coverage_tiers: Mapping<AccountId, u8>, // 1x, 5x, 10x
        admin: AccountId,
        total_staked: Balance,
    }

    #[ink(event)]
    pub struct Staked { validator: AccountId, amount: Balance, tier: u8 }

    impl Staking {
        #[ink(constructor)]
        pub fn new() -> Self {
            Self {
                stakes: Mapping::default(),
                coverage_tiers: Mapping::default(),
                admin: Self::env().caller(),
                total_staked: 0,
            }
        }

        #[ink(message)]
        pub fn stake(&mut self, amount: Balance, tier: u8) {
            let caller = self.env().caller();
            let current = self.stakes.get(caller).unwrap_or(0);
            self.stakes.insert(caller, &(current + amount));
            self.coverage_tiers.insert(caller, &tier);
            self.total_staked += amount;
            self.env().emit_event(Staked { validator: caller, amount, tier });
        }

        #[ink(message)]
        pub fn effective_stake(&self, validator: AccountId) -> Balance {
            let base = self.stakes.get(validator).unwrap_or(0);
            let tier = self.coverage_tiers.get(validator).unwrap_or(1);
            let multiplier = match tier { 1 => 1, 2 => 5, 3 => 10, _ => 1 };
            base * multiplier
        }

        #[ink(message)]
        pub fn total_staked(&self) -> Balance { self.total_staked }
    }
}
