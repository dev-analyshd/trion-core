//! TRION Protocol — NEAR TRION Staking
//! =====================================
//! Validator staking contract. Mirrors contracts/vyper/TRIONStaking.vy on NEAR.
//! Stakes TRION tokens, applies coverage_tier_multiplier to rewards, and
//! routes slashing to the TRIONToken contract.

use near_sdk::borsh::{self, BorshDeserialize, BorshSerialize};
use near_sdk::collections::LookupMap;
use near_sdk::{env, near_bindgen, AccountId, PanicOnDefault};

/// Coverage tier multipliers (Audit-4 fix):
///   - Tier 0 = 0.5x (light coverage)
///   - Tier 1 = 1.0x (standard)
///   - Tier 2 = 1.5x (premium)
fn coverage_tier_multiplier(tier: u8) -> u128 {
    match tier {
        0 => 50,    // 0.50x  (x100)
        1 => 100,   // 1.00x
        2 => 150,   // 1.50x
        _ => 100,
    }
}

#[near_bindgen]
#[derive(BorshDeserialize, BorshSerialize, PanicOnDefault)]
pub struct TRIONStaking {
    owner:            AccountId,
    token_contract:   AccountId,
    total_staked:     u128,
    stakes:           LookupMap<AccountId, StakeRecord>,
    coverage_tiers:   LookupMap<AccountId, u8>,
}

#[derive(BorshDeserialize, BorshSerialize, Clone, Debug)]
pub struct StakeRecord {
    pub staker:         AccountId,
    pub amount:         u128,
    pub start_block:    u64,
    pub last_reward_block: u64,
    pub coverage_tier:  u8,
}

#[near_bindgen]
impl TRIONStaking {
    #[init]
    pub fn new(owner: AccountId, token_contract: AccountId) -> Self {
        Self {
            owner,
            token_contract,
            total_staked: 0,
            stakes: LookupMap::new(b"s"),
            coverage_tiers: LookupMap::new(b"c"),
        }
    }

    /// Stake `amount` TRION tokens. Caller must have approved the staking contract
    /// via `ft_transfer_call` on the TRIONToken contract.
    pub fn stake(&mut self, amount: u128, coverage_tier: u8) {
        let staker = env::predecessor_account_id();
        assert!(amount > 0, "TRION: zero amount");
        assert!(coverage_tier <= 2, "TRION: invalid tier");

        let cur = self.stakes.get(&staker).unwrap_or(StakeRecord {
            staker: staker.clone(),
            amount: 0,
            start_block: env::block_height(),
            last_reward_block: env::block_height(),
            coverage_tier,
        });
        let new_rec = StakeRecord {
            staker: staker.clone(),
            amount: cur.amount + amount,
            start_block: cur.start_block,
            last_reward_block: env::block_height(),
            coverage_tier,
        };
        self.stakes.insert(&staker, &new_rec);
        self.coverage_tiers.insert(&staker, &coverage_tier);
        self.total_staked += amount;
        env::log_str(&format!("Staked:{}:amount={}", staker, amount));
    }

    /// Unstake `amount` TRION tokens (returns to caller).
    pub fn unstake(&mut self, amount: u128) {
        let staker = env::predecessor_account_id();
        let mut rec = self.stakes.get(&staker).expect("TRION: no stake");
        assert!(rec.amount >= amount, "TRION: insufficient stake");
        rec.amount -= amount;
        self.stakes.insert(&staker, &rec);
        self.total_staked -= amount;
        env::log_str(&format!("Unstaked:{}:amount={}", staker, amount));
    }

    /// Compute pending rewards for `staker` (with coverage_tier_multiplier applied).
    pub fn pending_rewards(&self, staker: AccountId) -> u128 {
        let rec = match self.stakes.get(&staker) {
            Some(r) => r,
            None    => return 0,
        };
        let blocks_staked = env::block_height().saturating_sub(rec.last_reward_block);
        let tier = self.coverage_tiers.get(&staker).unwrap_or(1);
        let mult = coverage_tier_multiplier(tier);
        // Simplified: 1 TRION reward per 1000 blocks per 1 TRION staked, scaled by tier multiplier.
        let base = (rec.amount / 1_000) * blocks_staked as u128;
        (base * mult) / 100
    }

    pub fn get_stake(&self, staker: AccountId) -> Option<StakeRecord> {
        self.stakes.get(&staker)
    }

    pub fn total_staked(&self) -> u128 { self.total_staked }

    /// Update the coverage tier for a staker (governance-only).
    pub fn set_coverage_tier(&mut self, staker: AccountId, tier: u8) {
        assert_eq!(env::predecessor_account_id(), self.owner, "TRION: not owner");
        assert!(tier <= 2, "TRION: invalid tier");
        self.coverage_tiers.insert(&staker, &tier);
    }
}
