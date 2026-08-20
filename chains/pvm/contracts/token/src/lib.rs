//! TRIONToken — ink! (Polkadot PVM)
//! 0% inflation, 7-type slashing, 50/50 insurance/burn
#![cfg_attr(not(feature = "std"), no_std)]
use ink::storage::Mapping;

#[ink::contract]
mod trion_token {
    use super::*;

    #[ink(storage)]
    pub struct TrionToken {
        total_supply: Balance,
        balances: Mapping<AccountId, Balance>,
        allowances: Mapping<(AccountId, AccountId), Balance>,
        admin: AccountId,
        insurance_pool: AccountId,
    }

    #[ink(event)]
    pub struct Transfer { from: Option<AccountId>, to: Option<AccountId>, value: Balance }

    #[ink(event)]
    pub struct Slashed { validator: AccountId, amount: Balance, reason: u8 }

    impl TrionToken {
        #[ink(constructor)]
        pub fn new(total_supply: Balance, insurance_pool: AccountId) -> Self {
            let mut balances = Mapping::default();
            let caller = Self::env().caller();
            balances.insert(caller, &total_supply);
            Self::env().emit_event(Transfer { from: None, to: Some(caller), value: total_supply });
            Self {
                total_supply,
                balances,
                allowances: Mapping::default(),
                admin: caller,
                insurance_pool,
            }
        }

        #[ink(message)]
        pub fn balance_of(&self, who: AccountId) -> Balance {
            self.balances.get(who).unwrap_or(0)
        }

        #[ink(message)]
        pub fn transfer(&mut self, to: AccountId, value: Balance) -> bool {
            let from = self.env().caller();
            let from_bal = self.balances.get(from).unwrap_or(0);
            assert!(from_bal >= value, "insufficient balance");
            self.balances.insert(from, &(from_bal - value));
            let to_bal = self.balances.get(to).unwrap_or(0);
            self.balances.insert(to, &(to_bal + value));
            self.env().emit_event(Transfer { from: Some(from), to: Some(to), value });
            true
        }

        /// Slash a validator — 50% to insurance pool, 50% burned
        #[ink(message)]
        pub fn slash(&mut self, validator: AccountId, amount: Balance, reason: u8) {
            assert_eq!(self.env().caller(), self.admin, "not admin");
            let bal = self.balances.get(validator).unwrap_or(0);
            let slash_amount = if bal >= amount { amount } else { bal };
            // 50% to insurance pool
            let insurance = slash_amount / 2;
            self.balances.insert(validator, &(bal - slash_amount));
            let pool_bal = self.balances.get(self.insurance_pool).unwrap_or(0);
            self.balances.insert(self.insurance_pool, &(pool_bal + insurance));
            // 50% burned (removed from supply)
            self.total_supply -= slash_amount - insurance;
            self.env().emit_event(Slashed { validator, amount: slash_amount, reason });
        }

        #[ink(message)]
        pub fn total_supply(&self) -> Balance { self.total_supply }
    }
}
