//! TRION PVM Intent — ink! contract (Polkadot)
//!
//! Mirrors BTCPIntent.sol.
//! Actions: 0=SWAP 1=TRANSFER 2=LIQUIDITY 3=STAKE 4=BORROW
//! Statuses: 0=PENDING 1=ROUTING 2=EXECUTING 3=COMPLETED 4=FAILED 5=EXPIRED 6=RESURRECTED

#![cfg_attr(not(feature = "std"), no_std, no_main)]

#[ink::contract]
mod trion_pvm_intent {
    use ink::prelude::vec::Vec;
    use ink::storage::Mapping;

    // ── Storage ───────────────────────────────────────────────────────────────

    #[ink(storage)]
    pub struct TRIONPVMIntent {
        owner:        AccountId,
        validators:   Vec<AccountId>,
        intents:      Mapping<[u8; 32], IntentRecord>,
        intent_count: u64,
    }

    // ── Types ─────────────────────────────────────────────────────────────────

    #[derive(Debug, Clone, scale::Encode, scale::Decode)]
    #[cfg_attr(feature = "std", derive(scale_info::TypeInfo, ink::storage::traits::StorageLayout))]
    pub struct IntentRecord {
        pub intent_hash:  [u8; 32],
        pub entity_id:    [u8; 32],
        pub action:       u8,
        pub asset_in:     [u8; 32],
        pub asset_out:    [u8; 32],
        pub magnitude:    u64,
        pub source_chain: u64,
        pub deadline:     u64,
        pub max_gas_usd:  u64,
        pub min_nl_score: u16,
        pub nonce:        u64,
        pub status:       u8,
        pub created_at:   u64,
        pub submitter:    AccountId,
    }

    // ── Events ────────────────────────────────────────────────────────────────

    #[ink(event)]
    pub struct IntentRegistered {
        #[ink(topic)]
        intent_hash: [u8; 32],
        entity_id:   [u8; 32],
        action:      u8,
        magnitude:   u64,
    }

    #[ink(event)]
    pub struct IntentStatusUpdated {
        #[ink(topic)]
        intent_hash: [u8; 32],
        old_status:  u8,
        new_status:  u8,
    }

    // ── Errors ────────────────────────────────────────────────────────────────

    #[derive(Debug, PartialEq, Eq, scale::Encode, scale::Decode)]
    #[cfg_attr(feature = "std", derive(scale_info::TypeInfo))]
    pub enum Error {
        Unauthorized,
        IntentAlreadyExists,
        IntentNotFound,
        InvalidAction,
        ZeroMagnitude,
        InvalidStatusTransition,
        TooManyValidators,
    }

    pub type Result<T> = core::result::Result<T, Error>;

    // ── Helpers ───────────────────────────────────────────────────────────────

    fn valid_transition(from: u8, to: u8) -> bool {
        matches!(
            (from, to),
            (0, 1) | (0, 4) | (0, 5)
            | (1, 2) | (1, 4) | (1, 5)
            | (2, 3) | (2, 4)
            | (4, 6)
        )
    }

    // ── Implementation ────────────────────────────────────────────────────────

    impl TRIONPVMIntent {
        #[ink(constructor)]
        pub fn new() -> Self {
            Self {
                owner:        Self::env().caller(),
                validators:   ink::prelude::vec![],
                intents:      Mapping::default(),
                intent_count: 0,
            }
        }

        #[ink(message)]
        pub fn register_intent(
            &mut self,
            intent_hash:  [u8; 32],
            entity_id:    [u8; 32],
            action:       u8,
            asset_in:     [u8; 32],
            asset_out:    [u8; 32],
            magnitude:    u64,
            source_chain: u64,
            deadline:     u64,
            max_gas_usd:  u64,
            min_nl_score: u16,
            nonce:        u64,
        ) -> Result<()> {
            if action > 4 { return Err(Error::InvalidAction); }
            if magnitude == 0 { return Err(Error::ZeroMagnitude); }
            if self.intents.get(intent_hash).is_some() { return Err(Error::IntentAlreadyExists); }

            let rec = IntentRecord {
                intent_hash,
                entity_id,
                action,
                asset_in,
                asset_out,
                magnitude,
                source_chain,
                deadline,
                max_gas_usd,
                min_nl_score,
                nonce,
                status:     0, // PENDING
                created_at: self.env().block_timestamp(),
                submitter:  self.env().caller(),
            };
            self.intents.insert(intent_hash, &rec);
            self.intent_count += 1;

            self.env().emit_event(IntentRegistered { intent_hash, entity_id, action, magnitude });
            Ok(())
        }

        #[ink(message)]
        pub fn update_intent_status(&mut self, intent_hash: [u8; 32], new_status: u8) -> Result<()> {
            let caller = self.env().caller();
            if caller != self.owner && !self.validators.contains(&caller) {
                return Err(Error::Unauthorized);
            }
            let mut rec = self.intents.get(intent_hash).ok_or(Error::IntentNotFound)?;
            if !valid_transition(rec.status, new_status) {
                return Err(Error::InvalidStatusTransition);
            }
            let old = rec.status;
            rec.status = new_status;
            self.intents.insert(intent_hash, &rec);
            self.env().emit_event(IntentStatusUpdated { intent_hash, old_status: old, new_status });
            Ok(())
        }

        #[ink(message)]
        pub fn get_intent(&self, intent_hash: [u8; 32]) -> Option<IntentRecord> {
            self.intents.get(intent_hash)
        }

        #[ink(message)]
        pub fn add_validator(&mut self, validator: AccountId) -> Result<()> {
            if self.env().caller() != self.owner { return Err(Error::Unauthorized); }
            if self.validators.len() >= 20 { return Err(Error::TooManyValidators); }
            if !self.validators.contains(&validator) { self.validators.push(validator); }
            Ok(())
        }

        #[ink(message)]
        pub fn remove_validator(&mut self, validator: AccountId) -> Result<()> {
            if self.env().caller() != self.owner { return Err(Error::Unauthorized); }
            self.validators.retain(|v| v != &validator);
            Ok(())
        }

        #[ink(message)]
        pub fn intent_count(&self) -> u64 { self.intent_count }

        #[ink(message)]
        pub fn owner(&self) -> AccountId { self.owner }
    }

    // ── Tests ─────────────────────────────────────────────────────────────────

    #[cfg(test)]
    mod tests {
        use super::*;

        #[ink::test]
        fn register_and_update() {
            let mut contract = TRIONPVMIntent::new();
            let hash = [1u8; 32];
            let res = contract.register_intent(
                hash, [2u8; 32], 0, [3u8; 32], [4u8; 32],
                1_000, 1, 9999999, 100, 300, 1,
            );
            assert!(res.is_ok());
            let rec = contract.get_intent(hash).unwrap();
            assert_eq!(rec.status, 0);

            let res2 = contract.update_intent_status(hash, 1);
            assert!(res2.is_ok());
            assert_eq!(contract.get_intent(hash).unwrap().status, 1);
        }

        #[ink::test]
        fn invalid_action_rejected() {
            let mut c = TRIONPVMIntent::new();
            let res = c.register_intent(
                [1u8; 32], [2u8; 32], 9, [3u8; 32], [4u8; 32], 1000, 1, 9999, 0, 300, 1,
            );
            assert_eq!(res, Err(Error::InvalidAction));
        }
    }
}
