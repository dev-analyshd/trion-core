//! TRION PVM Execution Gate — ink! contract (Polkadot)
//!
//! Mirrors TRIONExecutionGate.sol.
//! Acts as a behavioral firewall: gate_check passes only when phi >= threshold.
//! Integrating protocols call gate_check before executing sensitive operations.

#![cfg_attr(not(feature = "std"), no_std, no_main)]

#[ink::contract]
mod trion_pvm_gate {
    use ink::prelude::vec::Vec;
    use ink::storage::Mapping;

    #[ink(storage)]
    pub struct TRIONPVMGate {
        owner:        AccountId,
        validators:   Vec<AccountId>,
        gates:        Mapping<[u8; 32], GateState>,
        oracle_addr:  Option<AccountId>,
    }

    #[derive(Debug, Clone, scale::Encode, scale::Decode)]
    #[cfg_attr(feature = "std", derive(scale_info::TypeInfo, ink::storage::traits::StorageLayout))]
    pub struct GateState {
        pub gate_id:          [u8; 32],
        pub custom_threshold: u64,
        pub check_count:      u64,
        pub pass_count:       u64,
        pub block_count:      u64,
        pub last_phi:         u64,
        pub last_entity:      [u8; 32],
    }

    #[ink(event)]
    pub struct GatePassed {
        #[ink(topic)]
        gate_id:   [u8; 32],
        entity_id: [u8; 32],
        phi:       u64,
        threshold: u64,
    }

    #[ink(event)]
    pub struct GateBlocked {
        #[ink(topic)]
        gate_id:   [u8; 32],
        entity_id: [u8; 32],
        phi:       u64,
        threshold: u64,
    }

    #[derive(Debug, PartialEq, Eq, scale::Encode, scale::Decode)]
    #[cfg_attr(feature = "std", derive(scale_info::TypeInfo))]
    pub enum Error {
        Unauthorized,
        InvalidScore,
        GateBlocked,
        GateNotFound,
        TooManyValidators,
    }
    pub type Result<T> = core::result::Result<T, Error>;

    impl TRIONPVMGate {
        #[ink(constructor)]
        pub fn new() -> Self {
            Self {
                owner:       Self::env().caller(),
                validators:  ink::prelude::vec![],
                gates:       Mapping::default(),
                oracle_addr: None,
            }
        }

        /// Set a custom threshold for a gate (overrides oracle route threshold).
        /// threshold = 0 means use oracle route threshold.
        #[ink(message)]
        pub fn set_gate_threshold(&mut self, gate_id: [u8; 32], threshold: u64) -> Result<()> {
            if threshold > 1_000_000 { return Err(Error::InvalidScore); }
            let caller = self.env().caller();
            if caller != self.owner && !self.validators.contains(&caller) {
                return Err(Error::Unauthorized);
            }
            let mut gate = self.gates.get(gate_id).unwrap_or(GateState {
                gate_id,
                custom_threshold: 0,
                check_count:      0,
                pass_count:       0,
                block_count:      0,
                last_phi:         0,
                last_entity:      [0u8; 32],
            });
            gate.custom_threshold = threshold;
            self.gates.insert(gate_id, &gate);
            Ok(())
        }

        /// Evaluate the behavioral gate.
        /// phi: live coherence for this entity, ×1_000_000.
        /// route_threshold: the route's threshold from the oracle (caller provides; oracle cross-contract call optional).
        /// Returns Ok(true) if passed, Err(GateBlocked) if not.
        #[ink(message)]
        pub fn gate_check(
            &mut self,
            gate_id:         [u8; 32],
            entity_id:       [u8; 32],
            phi:             u64,
            route_threshold: u64,
        ) -> Result<bool> {
            let mut gate = self.gates.get(gate_id).unwrap_or(GateState {
                gate_id,
                custom_threshold: 0,
                check_count:      0,
                pass_count:       0,
                block_count:      0,
                last_phi:         0,
                last_entity:      [0u8; 32],
            });

            let threshold = if gate.custom_threshold > 0 {
                gate.custom_threshold
            } else {
                route_threshold
            };

            gate.check_count += 1;
            gate.last_phi    = phi;
            gate.last_entity = entity_id;

            if phi >= threshold {
                gate.pass_count += 1;
                self.gates.insert(gate_id, &gate);
                self.env().emit_event(GatePassed { gate_id, entity_id, phi, threshold });
                Ok(true)
            } else {
                gate.block_count += 1;
                self.gates.insert(gate_id, &gate);
                self.env().emit_event(GateBlocked { gate_id, entity_id, phi, threshold });
                Err(Error::GateBlocked)
            }
        }

        #[ink(message)]
        pub fn get_gate(&self, gate_id: [u8; 32]) -> Option<GateState> {
            self.gates.get(gate_id)
        }

        #[ink(message)]
        pub fn add_validator(&mut self, validator: AccountId) -> Result<()> {
            if self.env().caller() != self.owner { return Err(Error::Unauthorized); }
            if self.validators.len() >= 20 { return Err(Error::TooManyValidators); }
            if !self.validators.contains(&validator) { self.validators.push(validator); }
            Ok(())
        }

        #[ink(message)]
        pub fn set_oracle(&mut self, oracle: AccountId) -> Result<()> {
            if self.env().caller() != self.owner { return Err(Error::Unauthorized); }
            self.oracle_addr = Some(oracle);
            Ok(())
        }

        #[ink(message)]
        pub fn owner(&self) -> AccountId { self.owner }
    }

    #[cfg(test)]
    mod tests {
        use super::*;

        #[ink::test]
        fn gate_passes_above_threshold() {
            let mut g = TRIONPVMGate::new();
            let gate_id = [1u8; 32];
            let _ = g.set_gate_threshold(gate_id, 700_000);
            let res = g.gate_check(gate_id, [2u8; 32], 800_000, 700_000);
            assert_eq!(res, Ok(true));
        }

        #[ink::test]
        fn gate_blocks_below_threshold() {
            let mut g = TRIONPVMGate::new();
            let gate_id = [1u8; 32];
            let _ = g.set_gate_threshold(gate_id, 700_000);
            let res = g.gate_check(gate_id, [2u8; 32], 500_000, 700_000);
            assert_eq!(res, Err(Error::GateBlocked));
        }
    }
}
