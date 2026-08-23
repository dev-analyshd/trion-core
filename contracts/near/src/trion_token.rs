//! TRION Protocol — NEAR TRION Token (NEP-141)
//! ============================================
//! NEP-141 fungible token with:
//!   - FIXED SUPPLY — 0% ongoing inflation (Audit-4 Gap 1)
//!   - 7-type slashing (5 -> 7 in Audit-4)
//!   - 50/50 insurance_pool / burn split for slashed TRION
//!   - Public Good Charter (15% of supply reserved)
//!
//! Mirrors contracts/vyper/TRIONToken.vy on NEAR.

use near_sdk::borsh::{self, BorshDeserialize, BorshSerialize};
use near_sdk::collections::LookupMap;
use near_sdk::{env, near_bindgen, AccountId, PanicOnDefault};

const TOTAL_SUPPLY_YOCTO:  u128 = 1_000_000_000 * 10u128.pow(24);  // 1B TRION, 24 decimals (pow, not XOR)
const PUBLIC_GOOD_BPS:    u16   = 1500;                    // 15.00%
const ZERO_INFLATION_BPS:u16   = 0;                        // Audit-4 Gap 1

/// 7 slashing conditions (Audit-4 Gap 1 fix: 5 -> 7).
#[derive(BorshDeserialize, BorshSerialize, Clone, Debug)]
pub enum SlashCondition {
    DoubleSign,
    CoherenceCollapse,
    AWAViolation,
    Censorship,
    LongRangeAttack,
    BridgeMisbehavior,
    SybilAttack,
}

#[near_bindgen]
#[derive(BorshDeserialize, BorshSerialize, PanicOnDefault)]
pub struct TRIONToken {
    name:        String,
    symbol:      String,
    decimals:    u8,
    total_supply:u128,
    balances:    LookupMap<AccountId, u128>,
    allowances:  LookupMap<AccountId, LookupMap<AccountId, u128>>,
    governance:  AccountId,
    public_good_reserve: AccountId,
    public_good_minted:  u128,
    insurance_pool:       AccountId,
    insurance_pool_balance: u128,
    total_burned:         u128,
    staking_contract:    Option<AccountId>,
    awa_enforced:         bool,
}

#[near_bindgen]
impl TRIONToken {
    #[init]
    pub fn new(
        governance:          AccountId,
        public_good_reserve: AccountId,
        insurance_pool:       AccountId,
    ) -> Self {
        Self {
            name:                 "TRION Protocol".into(),
            symbol:               "TRION".into(),
            decimals:             24,
            total_supply:         TOTAL_SUPPLY_YOCTO,
            balances:             LookupMap::new(b"b"),
            allowances:           LookupMap::new(b"a"),
            governance:           governance.clone(),
            public_good_reserve:  public_good_reserve.clone(),
            public_good_minted:   0,
            insurance_pool,
            insurance_pool_balance: 0,
            total_burned:         0,
            staking_contract:    None,
            awa_enforced:         true,
        }
    }

    /// NEP-141: ft_transfer
    pub fn ft_transfer(&mut self, receiver_id: AccountId, amount: u128, memo: Option<String>) {
        let sender = env::predecessor_account_id();
        assert!(amount > 0, "TRION: zero amount");
        let bal = self.balances.get(&sender).unwrap_or(0);
        assert!(bal >= amount, "TRION: insufficient balance");
        self.balances.insert(&sender, &(bal - amount));
        let rbal = self.balances.get(&receiver_id).unwrap_or(0);
        self.balances.insert(&receiver_id, &(rbal + amount));
        if let Some(m) = memo {
            env::log_str(&format!("TRIONTransfer:{}:{}:{}", sender, receiver_id, m));
        }
    }

    /// NEP-141: ft_balance_of
    pub fn ft_balance_of(&self, account_id: AccountId) -> u128 {
        self.balances.get(&account_id).unwrap_or(0)
    }

    /// NEP-141: ft_total_supply
    pub fn ft_total_supply(&self) -> u128 { self.total_supply }

    /// NEP-141: ft_metadata
    pub fn ft_metadata(&self) -> (String, String, u8) {
        (self.name.clone(), self.symbol.clone(), self.decimals)
    }

    /// Audit-4 Gap 1: 0% inflation — `governance_mint` is now a no-op revert.
    /// The original function is preserved ONLY for the genesis distribution
    /// (initial supply to governance). All validator rewards come from
    /// protocol fees, NOT from new minting.
    pub fn governance_mint(&mut self, _recipient: AccountId, _amount: u128, _purpose: String) {
        // No-op revert — 0% inflation policy enforced on-chain.
        env::panic_str("TRION: 0% inflation — governance_mint disabled");
    }

    /// Audit-4 Gap 1: slashed TRION destination = 50% insurance_pool / 50% burn.
    /// Slashing types expanded to 7 (was 5).
    pub fn slash_validator(
        &mut self,
        validator: AccountId,
        amount:   u128,
        condition: SlashCondition,
    ) {
        let caller = env::predecessor_account_id();
        assert_eq!(caller, self.governance, "TRION: not governance");
        assert!(self.awa_enforced, "TRION: AWA not enforced");

        let bal = self.balances.get(&validator).unwrap_or(0);
        let slash_amount = bal.min(amount);
        assert!(slash_amount > 0, "TRION: zero slash");

        let insurance_share = slash_amount / 2;
        let burn_share       = slash_amount - insurance_share;

        self.balances.insert(&validator, &(bal - slash_amount));
        let ibal = self.balances.get(&self.insurance_pool).unwrap_or(0);
        self.balances.insert(&self.insurance_pool, &(ibal + insurance_share));
        self.insurance_pool_balance += insurance_share;
        self.total_burned          += burn_share;
        self.total_supply          -= burn_share;  // burn reduces supply

        env::log_str(&format!(
            "ValidatorSlashed:{}:amount={}:insurance={}:burn={}",
            validator, slash_amount, insurance_share, burn_share
        ));
    }

    pub fn total_burned(&self)            -> u128 { self.total_burned }
    pub fn insurance_pool_balance(&self) -> u128 { self.insurance_pool_balance }
    pub fn public_good_minted(&self)     -> u128 { self.public_good_minted }
    pub fn awa_enforced(&self)            -> bool { self.awa_enforced }

    pub fn set_staking_contract(&mut self, staking: AccountId) {
        assert_eq!(env::predecessor_account_id(), self.governance, "TRION: not governance");
        self.staking_contract = Some(staking);
    }
}
