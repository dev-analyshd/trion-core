//! TRION PVM Liquidity Commitment — ink! contract (Polkadot)
//!
//! Mirrors LiquidityOcean.sol + BTCP_ESCROW.vy.
//! Commitment statuses: 0=PENDING 1=SETTLED 2=REVERTED
//! Revert reasons: 0=TIMEOUT 1=COHERENCE_FAILURE 2=ROUTE_INVALID 3=MANUAL

#![cfg_attr(not(feature = "std"), no_std, no_main)]

#[ink::contract]
mod trion_pvm_liquidity {
    use ink::prelude::vec::Vec;
    use ink::storage::Mapping;

    #[ink(storage)]
    pub struct TRIONPVMLiquidity {
        owner:            AccountId,
        validators:       Vec<AccountId>,
        commitments:      Mapping<[u8; 32], LiquidityCommitment>,
        commitment_count: u64,
    }

    #[derive(Debug, Clone, scale::Encode, scale::Decode)]
    #[cfg_attr(feature = "std", derive(scale_info::TypeInfo, ink::storage::traits::StorageLayout))]
    pub struct LiquidityCommitment {
        pub commitment_id: [u8; 32],
        pub entity_id:     [u8; 32],
        pub route_id:      [u8; 32],
        pub asset:         [u8; 32],
        pub amount:        u64,
        pub min_coherence: u64,
        pub expiry:        u64,
        pub status:        u8,
        pub created_at:    u64,
        pub committed_by:  AccountId,
        pub execution_bh:  [u8; 32],
        pub settled_at:    u64,
        pub revert_at:     u64,
        pub revert_code:   u8,
    }

    #[ink(event)]
    pub struct LiquidityCommitted {
        #[ink(topic)]
        commitment_id: [u8; 32],
        entity_id:     [u8; 32],
        route_id:      [u8; 32],
        amount:        u64,
        min_coherence: u64,
    }

    #[ink(event)]
    pub struct CommitmentSettled {
        #[ink(topic)]
        commitment_id: [u8; 32],
        entity_id:     [u8; 32],
        execution_bh:  [u8; 32],
        coherence:     u64,
    }

    #[ink(event)]
    pub struct CommitmentReverted {
        #[ink(topic)]
        commitment_id: [u8; 32],
        entity_id:     [u8; 32],
        reason:        u8,
    }

    #[derive(Debug, PartialEq, Eq, scale::Encode, scale::Decode)]
    #[cfg_attr(feature = "std", derive(scale_info::TypeInfo))]
    pub enum Error {
        Unauthorized,
        InvalidScore,
        CommitmentAlreadyExists,
        CommitmentNotFound,
        CommitmentFinalized,
        CommitmentExpired,
        CoherenceTooLow,
        TooManyValidators,
        /// INV-003 (follow-on 2): sub-floor min_coherence at commit
        /// (tighten-only — the same 0.55 protocol floor as the escrows)
        CoherenceFloor,
    }
    pub type Result<T> = core::result::Result<T, Error>;

    impl TRIONPVMLiquidity {
        #[ink(constructor)]
        pub fn new() -> Self {
            Self {
                owner:            Self::env().caller(),
                validators:       ink::prelude::vec![],
                commitments:      Mapping::default(),
                commitment_count: 0,
            }
        }

        #[ink(message)]
        pub fn commit_liquidity(
            &mut self,
            commitment_id: [u8; 32],
            entity_id:     [u8; 32],
            route_id:      [u8; 32],
            asset:         [u8; 32],
            amount:        u64,
            min_coherence: u64,
            expiry:        u64,
        ) -> Result<()> {
            if min_coherence > 1_000_000 { return Err(Error::InvalidScore); }
            // INV-003 (follow-on 2): tightening-only — the commitment-local
            // floor may sit ABOVE Θ_min 0.55 (550000 ×1e6), never below it
            // (escrow-tier parity, fail-fast at commit)
            if min_coherence < 550_000 { return Err(Error::CoherenceFloor); }
            if self.commitments.get(commitment_id).is_some() {
                return Err(Error::CommitmentAlreadyExists);
            }
            let now = self.env().block_timestamp();
            if expiry <= now { return Err(Error::CommitmentExpired); }

            let lc = LiquidityCommitment {
                commitment_id,
                entity_id,
                route_id,
                asset,
                amount,
                min_coherence,
                expiry,
                status:       0,
                created_at:   now,
                committed_by: self.env().caller(),
                execution_bh: [0u8; 32],
                settled_at:   0,
                revert_at:    0,
                revert_code:  0,
            };
            self.commitments.insert(commitment_id, &lc);
            self.commitment_count += 1;

            self.env().emit_event(LiquidityCommitted {
                commitment_id, entity_id, route_id, amount, min_coherence,
            });
            Ok(())
        }

        /// coherence: the route's current coherence_score (caller provides; validated off-chain or via oracle cross-call)
        #[ink(message)]
        pub fn settle_commitment(
            &mut self,
            commitment_id: [u8; 32],
            execution_bh:  [u8; 32],
            coherence:     u64,
        ) -> Result<()> {
            let caller = self.env().caller();
            if caller != self.owner && !self.validators.contains(&caller) {
                return Err(Error::Unauthorized);
            }
            let mut lc = self.commitments.get(commitment_id)
                .ok_or(Error::CommitmentNotFound)?;
            if lc.status != 0 { return Err(Error::CommitmentFinalized); }

            let now = self.env().block_timestamp();
            if now > lc.expiry { return Err(Error::CommitmentExpired); }
            if coherence < lc.min_coherence { return Err(Error::CoherenceTooLow); }

            lc.status       = 1;
            lc.execution_bh = execution_bh;
            lc.settled_at   = now;
            self.commitments.insert(commitment_id, &lc);

            self.env().emit_event(CommitmentSettled {
                commitment_id,
                entity_id: lc.entity_id,
                execution_bh,
                coherence,
            });
            Ok(())
        }

        #[ink(message)]
        pub fn revert_commitment(&mut self, commitment_id: [u8; 32], reason: u8) -> Result<()> {
            let caller = self.env().caller();
            if caller != self.owner && !self.validators.contains(&caller) {
                return Err(Error::Unauthorized);
            }
            let mut lc = self.commitments.get(commitment_id)
                .ok_or(Error::CommitmentNotFound)?;
            if lc.status != 0 { return Err(Error::CommitmentFinalized); }

            lc.status      = 2;
            lc.revert_at   = self.env().block_timestamp();
            lc.revert_code = reason;
            self.commitments.insert(commitment_id, &lc);

            self.env().emit_event(CommitmentReverted {
                commitment_id, entity_id: lc.entity_id, reason,
            });
            Ok(())
        }

        #[ink(message)]
        pub fn get_commitment(&self, commitment_id: [u8; 32]) -> Option<LiquidityCommitment> {
            self.commitments.get(commitment_id)
        }

        #[ink(message)]
        pub fn add_validator(&mut self, validator: AccountId) -> Result<()> {
            if self.env().caller() != self.owner { return Err(Error::Unauthorized); }
            if self.validators.len() >= 20 { return Err(Error::TooManyValidators); }
            if !self.validators.contains(&validator) { self.validators.push(validator); }
            Ok(())
        }

        #[ink(message)]
        pub fn commitment_count(&self) -> u64 { self.commitment_count }

        #[ink(message)]
        pub fn owner(&self) -> AccountId { self.owner }
    }

    #[cfg(test)]
    mod tests {
        use super::*;

        #[ink::test]
        fn commit_and_settle() {
            let mut c = TRIONPVMLiquidity::new();
            let cid = [1u8; 32];
            let res = c.commit_liquidity(cid, [2u8;32], [3u8;32], [4u8;32], 1_000, 700_000, u64::MAX);
            assert!(res.is_ok());
            let res2 = c.settle_commitment(cid, [5u8; 32], 800_000);
            assert!(res2.is_ok());
            let lc = c.get_commitment(cid).unwrap();
            assert_eq!(lc.status, 1);
        }

        #[ink::test]
        fn coherence_too_low_rejected() {
            let mut c = TRIONPVMLiquidity::new();
            let cid = [1u8; 32];
            let _ = c.commit_liquidity(cid, [2u8;32], [3u8;32], [4u8;32], 1_000, 700_000, u64::MAX);
            let res = c.settle_commitment(cid, [5u8;32], 500_000);
            assert_eq!(res, Err(Error::CoherenceTooLow));
        }
    }
}
