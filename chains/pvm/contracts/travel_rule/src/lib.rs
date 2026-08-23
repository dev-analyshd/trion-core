//! TravelRuleCompliance — ink! (Polkadot PVM)
//!
//! ZK FATF Travel Rule proof storage with jurisdiction thresholds and
//! Chameleon FATF modes — mirrors contracts/solidity/TravelRuleCompliance.sol.
//!
//! Modes (spec Fix 1):
//!   LOW      proof optional
//!   MEDIUM   proof required above $1,000
//!   HIGH     proof required for all routes
//!   CRITICAL AWA freeze — nothing passes without proof

#![cfg_attr(not(feature = "std"), no_std, no_main)]
#[ink::contract]
mod travel_rule {
    use ink::storage::Mapping;
    /// FATF Travel Rule threshold (USD)
    const FATF_THRESHOLD_USD: u128 = 1_000;

    /// Chameleon FATF compliance modes
    #[derive(Debug, Copy, Clone, PartialEq, Eq, scale::Encode, scale::Decode)]
    #[cfg_attr(feature = "std", derive(scale_info::TypeInfo, ink::storage::traits::StorageLayout))]
    pub enum FatfMode {
        Low,
        Medium,
        High,
        Critical,
    }

    #[derive(Debug, Copy, Clone, PartialEq, Eq, scale::Encode, scale::Decode)]
    #[cfg_attr(feature = "std", derive(scale_info::TypeInfo, ink::storage::traits::StorageLayout))]
    pub struct Proof {
        /// keccak/truncated SHA3 of the disclosure submitted to the VASP
        pub disclosure_hash: Hash,
        /// hash of the jurisdiction (never the raw country code)
        pub jurisdiction_hash: Hash,
        /// unix timestamp of submission
        pub submitted_at: u64,
        /// amount covered, USD
        pub amount_usd: u128,
    }

    #[ink(storage)]
    pub struct TravelRule {
        admin: AccountId,
        relayer: AccountId,
        proofs: Mapping<AccountId, Proof>,
        /// jurisdictionHash → threshold override (USD)
        jurisdiction_thresholds: Mapping<Hash, u128>,
        /// global Chameleon mode
        mode: FatfMode,
    }

    #[ink(event)]
    pub struct ProofSubmitted {
        #[ink(topic)]
        entity: AccountId,
        disclosure_hash: Hash,
        jurisdiction_hash: Hash,
        amount_usd: u128,
    }

    #[derive(Debug, PartialEq, Eq, scale::Encode, scale::Decode)]
    #[cfg_attr(feature = "std", derive(scale_info::TypeInfo))]
    pub enum TravelRuleError {
        Unauthorized,
        ZeroAmount,
        ProofRequired,     // MEDIUM/HIGH: amount at/above threshold without proof
        AwaFrozen,         // CRITICAL: nothing passes
        InvalidAmount,
    }

    impl TravelRule {
        #[ink(constructor)]
        pub fn new(relayer: AccountId) -> Self {
            Self {
                admin: Self::env().caller(),
                relayer,
                proofs: Mapping::default(),
                jurisdiction_thresholds: Mapping::default(),
                mode: FatfMode::Medium,
            }
        }

        fn _require_relayer_or_admin(&self) -> Result<(), TravelRuleError> {
            let caller = self.env().caller();
            if caller == self.relayer || caller == self.admin {
                Ok(())
            } else {
                Err(TravelRuleError::Unauthorized)
            }
        }

        fn _require_admin(&self) -> Result<(), TravelRuleError> {
            if self.env().caller() == self.admin {
                Ok(())
            } else {
                Err(TravelRuleError::Unauthorized)
            }
        }

        /// Submit a ZK compliance proof for an entity (relayer-mediated;
        /// the proof hash is stored, never disclosure contents).
        #[ink(message)]
        pub fn submit_proof(
            &mut self,
            entity: AccountId,
            disclosure_hash: Hash,
            jurisdiction_hash: Hash,
            amount_usd: u128,
        ) -> Result<(), TravelRuleError> {
            self._require_relayer_or_admin()?;
            if amount_usd == 0 {
                return Err(TravelRuleError::InvalidAmount);
            }
            let proof = Proof {
                disclosure_hash,
                jurisdiction_hash,
                submitted_at: self.env().block_timestamp(),
                amount_usd,
            };
            self.proofs.insert(entity, &proof);
            self.env().emit_event(ProofSubmitted {
                entity,
                disclosure_hash,
                jurisdiction_hash,
                amount_usd,
            });
            Ok(())
        }

        /// Travel-rule gate: may a transfer of `amount_usd` from `entity` in
        /// `jurisdiction_hash` proceed under the current mode?
        #[ink(message)]
        pub fn is_compliant(
            &self,
            entity: AccountId,
            jurisdiction_hash: Hash,
            amount_usd: u128,
        ) -> Result<bool, TravelRuleError> {
            if amount_usd == 0 {
                return Err(TravelRuleError::InvalidAmount);
            }
            // CRITICAL: AWA freeze — nothing is compliant without proof
            if self.mode == FatfMode::Critical {
                return Ok(self.proofs.contains(entity));
            }
            // HIGH: proof required for ALL routes
            if self.mode == FatfMode::High {
                return Ok(self.proofs.contains(entity));
            }
            // MEDIUM: proof required at/above the applicable threshold
            if self.mode == FatfMode::Medium {
                let threshold = self
                    .jurisdiction_thresholds
                    .get(jurisdiction_hash)
                    .unwrap_or(FATF_THRESHOLD_USD);
                if amount_usd >= threshold {
                    return Ok(self.proofs.contains(entity));
                }
                return Ok(true);
            }
            // LOW: optional
            Ok(true)
        }

        /// Set a jurisdiction-specific threshold (admin).
        #[ink(message)]
        pub fn set_jurisdiction_threshold(
            &mut self,
            jurisdiction_hash: Hash,
            threshold_usd: u128,
        ) -> Result<(), TravelRuleError> {
            self._require_admin()?;
            self.jurisdiction_thresholds.insert(jurisdiction_hash, &threshold_usd);
            Ok(())
        }

        /// Set the Chameleon FATF mode (admin).
        #[ink(message)]
        pub fn set_mode(&mut self, mode: FatfMode) -> Result<(), TravelRuleError> {
            self._require_admin()?;
            self.mode = mode;
            Ok(())
        }

        // ── Reads ───────────────────────────────────────────────────────

        #[ink(message)]
        pub fn has_proof(&self, entity: AccountId) -> bool {
            self.proofs.contains(entity)
        }

        #[ink(message)]
        pub fn get_proof(&self, entity: AccountId) -> Option<Proof> {
            self.proofs.get(entity)
        }

        #[ink(message)]
        pub fn get_jurisdiction_threshold(&self, jurisdiction_hash: Hash) -> u128 {
            self.jurisdiction_thresholds
                .get(jurisdiction_hash)
                .unwrap_or(FATF_THRESHOLD_USD)
        }

        #[ink(message)]
        pub fn current_mode(&self) -> FatfMode {
            self.mode
        }

        #[ink(message)]
        pub fn admin(&self) -> AccountId {
            self.admin
        }

        #[ink(message)]
        pub fn set_relayer(&mut self, new_relayer: AccountId) -> Result<(), TravelRuleError> {
            self._require_admin()?;
            self.relayer = new_relayer;
            Ok(())
        }
    }
}
