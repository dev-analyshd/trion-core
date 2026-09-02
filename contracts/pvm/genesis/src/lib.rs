//! GenesisCommitment — ink! (Polkadot PVM)
//!
//! Sponsored Genesis + Identity Genesis per BTCP Master Spec §9:
//!   - Identity Genesis: an entity stakes value → first behavioral datapoint,
//!     confidence anchors at conf_genesis.
//!   - Sponsored Genesis: a sponsor with established depth stakes a bond to
//!     vouch for a new entity; the bond is SLASHED if the sponsored entity
//!     manipulates during the accountability window.
//!
//! Replaces the previous open-access stub (anyone could overwrite anyone's
//! commitment) with a real relayer/owner-gated, value-carrying commitment.

#![cfg_attr(not(feature = "std"), no_std, no_main)]
#[ink::contract]
mod genesis {
    use ink::storage::Mapping;
    /// Accountability window in blocks for Sponsored Genesis (spec: bond
    /// slashable while the sponsored entity is under observation).
    const ACCOUNTABILITY_BLOCKS: u64 = 14400; // ~1 day at 6s blocks

    #[ink(storage)]
    pub struct Genesis {
        /// admin — deploys, authorizes relayers
        admin: AccountId,
        /// authorized relayer (TRION oracle bridge)
        relayer: AccountId,
        /// entity → staked balance (identity genesis bond)
        commitments: Mapping<AccountId, Balance>,
        /// entity → genesis confidence ×1e6
        conf_genesis: Mapping<AccountId, u128>,
        /// sponsored entity → (sponsor, bond, window_end_block, slashed)
        sponsorships: Mapping<AccountId, (AccountId, Balance, u64, bool)>,
    }

    #[ink(event)]
    pub struct Committed {
        #[ink(topic)]
        entity: AccountId,
        amount: Balance,
        confidence: u128,
    }

    #[ink(event)]
    pub struct Sponsored {
        #[ink(topic)]
        entity: AccountId,
        sponsor: AccountId,
        bond: Balance,
    }

    #[ink(event)]
    pub struct SponsorSlashed {
        #[ink(topic)]
        entity: AccountId,
        sponsor: AccountId,
        bond: Balance,
        reason: u8, // 1=manipulation_detected 2=expired_unresolved
    }

    #[derive(Debug, PartialEq, Eq, scale::Encode, scale::Decode)]
    #[cfg_attr(feature = "std", derive(scale_info::TypeInfo))]
    pub enum GenesisError {
        Unauthorized,
        ZeroAmount,
        ZeroConfidence,
        InvalidConfidence,
        AlreadySponsored,
        SponsorshipNotFound,
        WindowClosed,
        BondAlreadySlashed,
    }

    impl Genesis {
        #[ink(constructor)]
        pub fn new(relayer: AccountId) -> Self {
            Self {
                admin: Self::env().caller(),
                relayer,
                commitments: Mapping::default(),
                conf_genesis: Mapping::default(),
                sponsorships: Mapping::default(),
            }
        }

        // ── Access control ──────────────────────────────────────────────

        fn _require_relayer_or_admin(&self) -> Result<(), GenesisError> {
            let caller = self.env().caller();
            if caller == self.relayer || caller == self.admin {
                Ok(())
            } else {
                Err(GenesisError::Unauthorized)
            }
        }

        fn _require_admin(&self) -> Result<(), GenesisError> {
            if self.env().caller() == self.admin {
                Ok(())
            } else {
                Err(GenesisError::Unauthorized)
            }
        }

        // ── Identity Genesis (spec §9.2 pathway 2) ──────────────────────

        /// Register an identity-genesis commitment: the entity locks value
        /// (bond attached to this call by the relayer on the entity's behalf)
        /// and receives its first behavioral datapoint + genesis confidence.
        #[ink(message, payable)]
        pub fn commit(&mut self, entity: AccountId, confidence: u128) -> Result<(), GenesisError> {
            self._require_relayer_or_admin()?;
            let amount = self.env().transferred_value();
            if amount == 0 {
                return Err(GenesisError::ZeroAmount);
            }
            if confidence == 0 {
                return Err(GenesisError::ZeroConfidence);
            }
            if confidence > 1_000_000 {
                return Err(GenesisError::InvalidConfidence);
            }

            // Stake accrues (multiple commitments deepen the same entity)
            let prev = self.commitments.get(entity).unwrap_or(0);
            self.commitments.insert(entity, &(prev + amount));
            self.conf_genesis.insert(entity, &confidence);

            self.env().emit_event(Committed { entity, amount, confidence });
            Ok(())
        }

        /// Release an entity's identity bond back to `beneficiary`
        /// (admin/relayer only — honest entities get bonds returned).
        #[ink(message)]
        pub fn release_commitment(
            &mut self,
            entity: AccountId,
            beneficiary: AccountId,
        ) -> Result<(), GenesisError> {
            self._require_relayer_or_admin()?;
            let amount = self.commitments.take(entity).unwrap_or(0);
            if amount > 0 {
                self.env()
                    .transfer(beneficiary, amount)
                    .map_err(|_| GenesisError::ZeroAmount)?;
            }
            Ok(())
        }

        // ── Sponsored Genesis (spec §9.2 pathway 3) ─────────────────────

        /// A sponsor vouches for a new entity: `bond` is attached as value
        /// and held for the accountability window.
        #[ink(message, payable)]
        pub fn sponsor(&mut self, entity: AccountId) -> Result<(), GenesisError> {
            self._require_relayer_or_admin()?;
            let bond = self.env().transferred_value();
            if bond == 0 {
                return Err(GenesisError::ZeroAmount);
            }
            if self.sponsorships.contains(entity) {
                return Err(GenesisError::AlreadySponsored);
            }

            let sponsor = self.env().caller();
            let window_end = self.env().block_timestamp() + ACCOUNTABILITY_BLOCKS;
            self.sponsorships.insert(entity, &(sponsor, bond, window_end, false));

            self.env().emit_event(Sponsored { entity, sponsor, bond });
            Ok(())
        }

        /// Slash a sponsor's bond when the sponsored entity manipulated
        /// (relayer/admin only, reason recorded permanently).
        #[ink(message)]
        pub fn slash_sponsor(&mut self, entity: AccountId, reason: u8) -> Result<Balance, GenesisError> {
            self._require_relayer_or_admin()?;
            let (sponsor, bond, window_end, slashed) = self
                .sponsorships
                .get(entity)
                .ok_or(GenesisError::SponsorshipNotFound)?;
            if slashed {
                return Err(GenesisError::BondAlreadySlashed);
            }
            // Manipulation detected inside the window (or expired unresolved → 2)
            let now = self.env().block_timestamp();
            if now > window_end + ACCOUNTABILITY_BLOCKS && reason == 1 {
                return Err(GenesisError::WindowClosed);
            }

            self.sponsorships.insert(entity, &(sponsor, 0, window_end, true));
            // Slashed bonds stay in the contract (governance sweep) — the
            // value is removed from the sponsor's claim.
            self.env().emit_event(SponsorSlashed { entity, sponsor, bond, reason });
            Ok(bond)
        }

        /// Return the sponsor bond after an honest accountability window.
        #[ink(message)]
        pub fn release_sponsorship(&mut self, entity: AccountId) -> Result<(), GenesisError> {
            let (sponsor, bond, window_end, slashed) = self
                .sponsorships
                .get(entity)
                .ok_or(GenesisError::SponsorshipNotFound)?;
            if slashed {
                return Err(GenesisError::BondAlreadySlashed);
            }
            let now = self.env().block_timestamp();
            if now <= window_end as u64 {
                return Err(GenesisError::WindowClosed);
            }

            self.sponsorships.insert(entity, &(sponsor, 0, window_end, true));
            if bond > 0 {
                self.env()
                    .transfer(sponsor, bond)
                    .map_err(|_| GenesisError::ZeroAmount)?;
            }
            Ok(())
        }

        // ── Reads ───────────────────────────────────────────────────────

        #[ink(message)]
        pub fn get_confidence(&self, entity: AccountId) -> u128 {
            self.conf_genesis.get(entity).unwrap_or(0)
        }

        #[ink(message)]
        pub fn get_commitment(&self, entity: AccountId) -> Balance {
            self.commitments.get(entity).unwrap_or(0)
        }

        #[ink(message)]
        pub fn get_sponsorship(&self, entity: AccountId) -> Option<(AccountId, Balance, u64, bool)> {
            self.sponsorships.get(entity)
        }

        #[ink(message)]
        pub fn admin(&self) -> AccountId {
            self.admin
        }

        #[ink(message)]
        pub fn relayer(&self) -> AccountId {
            self.relayer
        }

        #[ink(message)]
        pub fn set_relayer(&mut self, new_relayer: AccountId) -> Result<(), GenesisError> {
            self._require_admin()?;
            self.relayer = new_relayer;
            Ok(())
        }
    }
}
